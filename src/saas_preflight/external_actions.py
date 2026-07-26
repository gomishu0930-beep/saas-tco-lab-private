"""Signed, provider-neutral boundary for one exact external action.

This module never sends mail, submits an application, loads credentials, calls a
provider, deploys, publishes, or disables. It constructs and verifies content-bound
artifacts and persists only the local one-shot execution state in an explicit
SQLite file; it does not persist provider payloads or an external audit journal.
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import RLock, Thread
from typing import Any, Callable, Iterator, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
)
from .models import Sha256, Slug, StrictModel
from .release import ApprovalDecision
from .release_assurance import (
    PublicReleaseDecision,
    ReleaseAssuranceReport,
    ReleaseAssuranceRuntime,
    verify_release_assurance_report,
)


_EXTERNAL_ACTION_LOCK_TIMEOUT_SECONDS = 5.0


def _bounded_external_store_callback(
    callback: Callable[..., Any],
    *args: Any,
    label: str,
) -> Any:
    output: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, callback(*args)), block=False)
        except BaseException as exc:
            try:
                output.put((False, exc), block=False)
            except BaseException:
                pass

    Thread(target=invoke, name=label, daemon=True).start()
    try:
        succeeded, value = output.get(
            timeout=_EXTERNAL_ACTION_LOCK_TIMEOUT_SECONDS
        )
    except Empty as exc:
        raise ExternalActionInputError(f"{label} timed out") from exc
    if not succeeded:
        raise ExternalActionInputError(f"{label} failed") from (
            value if isinstance(value, BaseException) else None
        )
    return value


class ExternalActionInputError(ValueError):
    """Untrusted action input could not be revalidated."""


class ExternalAction(str, Enum):
    SEND_RIGHTS_INQUIRY = "send_rights_inquiry"
    SUBMIT_AFFILIATE_APPLICATION = "submit_affiliate_application"
    ACTIVATE_PUBLIC_RELEASE = "activate_public_release"
    DISABLE_PUBLIC_RELEASE = "disable_public_release"


class ActionEnvironment(str, Enum):
    VENDOR_CONTACT = "vendor_contact"
    PRODUCTION = "production"


class ActionSignatureScope(str, Enum):
    HUMAN_EXECUTION_APPROVAL = "human_execution_approval"
    CONTROLLER_EXECUTION_GRANT = "controller_execution_grant"
    CONTROLLER_GRANT_REVOCATION = "controller_grant_revocation"
    EXECUTOR_ACTION_RECEIPT = "executor_action_receipt"
    CONTROLLER_JOURNAL_ENTRY = "controller_journal_entry"


class ActionResult(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class JournalEventKind(str, Enum):
    GRANT = "grant"
    CLAIM = "claim"
    REVOCATION = "revocation"
    RECEIPT = "receipt"


class JournalAuthorityState(str, Enum):
    GRANTED = "granted"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class JournalOutcomeState(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


REQUIRED_EXTERNAL_ACTIONS: tuple[ExternalAction, ...] = tuple(
    sorted(ExternalAction, key=lambda item: item.value)
)


class ExternalActionTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    controller: Ed25519VerificationKey
    human: Ed25519VerificationKey
    executor: Ed25519VerificationKey

    @model_validator(mode="after")
    def require_separate_roles(self) -> Self:
        expected = (
            (self.controller, SigningRole.CONTROLLER),
            (self.human, SigningRole.HUMAN_APPROVER),
            (self.executor, SigningRole.EXECUTOR),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("external-action trust-store role mismatch")
        if len({key.key_id_sha256 for key, _ in expected}) != 3:
            raise ValueError("controller, Human, and executor keys must be distinct")
        return self


class ExternalActionTargetRule(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    action: ExternalAction
    environment: ActionEnvironment
    environment_sha256: Sha256
    vendor_slug: Slug | None = None
    property_record_sha256: Sha256
    target_sha256: Sha256

    @model_validator(mode="after")
    def require_action_specific_target(self) -> Self:
        if self.action in {
            ExternalAction.SEND_RIGHTS_INQUIRY,
            ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
        }:
            if (
                self.environment is not ActionEnvironment.VENDOR_CONTACT
                or self.vendor_slug is None
            ):
                raise ValueError(
                    "vendor target rule requires vendor_contact and vendor_slug"
                )
        elif (
            self.environment is not ActionEnvironment.PRODUCTION
            or self.vendor_slug is not None
        ):
            raise ValueError(
                "release target rule requires production without vendor_slug"
            )
        return self


class ExternalActionPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: Slug
    trust_store_sha256: Sha256
    controller_key_id_sha256: Sha256
    human_key_id_sha256: Sha256
    executor_key_id_sha256: Sha256
    allowed_actions: tuple[ExternalAction, ...] = REQUIRED_EXTERNAL_ACTIONS
    target_rules: tuple[ExternalActionTargetRule, ...]
    maximum_request_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_approval_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_grant_ttl_seconds: int = Field(ge=1, le=3_600)
    maximum_receipt_delay_seconds: int = Field(default=3_600, ge=1, le=86_400)

    @model_validator(mode="after")
    def require_exact_policy(self) -> Self:
        if self.allowed_actions != REQUIRED_EXTERNAL_ACTIONS:
            raise ValueError("allowed_actions must be the complete canonical set")
        canonical_rules = tuple(
            sorted(self.target_rules, key=_external_action_target_rule_key)
        )
        if self.target_rules != canonical_rules or len(set(canonical_rules)) != len(
            canonical_rules
        ):
            raise ValueError("target_rules must be canonical and unique")
        if {rule.action for rule in canonical_rules} != set(REQUIRED_EXTERNAL_ACTIONS):
            raise ValueError("target_rules must cover every allowed action")
        if len(
            {
                self.controller_key_id_sha256,
                self.human_key_id_sha256,
                self.executor_key_id_sha256,
            }
        ) != 3:
            raise ValueError("external-action role keys must be distinct")
        return self


class ExternalActionRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Slug
    requester_id: Slug
    action: ExternalAction
    environment: ActionEnvironment
    environment_sha256: Sha256
    external_action_policy_sha256: Sha256
    vendor_slug: Slug | None = None
    property_record_sha256: Sha256
    target_sha256: Sha256
    payload_sha256: Sha256
    idempotency_key_sha256: Sha256
    expected_pre_state_sha256: Sha256
    expected_post_state_sha256: Sha256
    release_id: Slug | None = None
    manifest_sha256: Sha256 | None = None
    artifact_sha256: Sha256 | None = None
    public_release_report_sha256: Sha256 | None = None
    public_release_authorization_sha256: Sha256 | None = None
    requested_at: datetime
    not_before: datetime
    expires_at: datetime
    request_sha256: Sha256

    @field_validator("requested_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "external action request timestamp")
        return value

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.requested_at <= self.not_before < self.expires_at:
            raise ValueError("request times must satisfy requested <= not-before < expiry")
        release_values = (
            self.release_id,
            self.manifest_sha256,
            self.artifact_sha256,
            self.public_release_report_sha256,
            self.public_release_authorization_sha256,
        )
        if self.action in {
            ExternalAction.SEND_RIGHTS_INQUIRY,
            ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
        }:
            if self.environment is not ActionEnvironment.VENDOR_CONTACT:
                raise ValueError("vendor action requires vendor_contact environment")
            if self.vendor_slug is None:
                raise ValueError("vendor action requires vendor_slug")
            if any(value is not None for value in release_values):
                raise ValueError("vendor action cannot carry release authority")
        else:
            if self.environment is not ActionEnvironment.PRODUCTION:
                raise ValueError("release action requires production environment")
            if self.vendor_slug is not None:
                raise ValueError("release action cannot carry vendor_slug")
            required_release = release_values[:3]
            if any(value is None for value in required_release):
                raise ValueError("release action requires release/manifest/artifact")
            if self.action is ExternalAction.ACTIVATE_PUBLIC_RELEASE:
                if any(value is None for value in release_values[3:]):
                    raise ValueError("activation requires P10 report and authorization hashes")
            elif any(value is not None for value in release_values[3:]):
                raise ValueError("disable must not depend on a P10 authorization")
        if self.request_sha256 != hash_external_action_request(self):
            raise ValueError("request_sha256 does not match canonical request")
        return self


class HumanExecutionApproval(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER] = SigningRole.HUMAN_APPROVER
    scope: Literal[ActionSignatureScope.HUMAN_EXECUTION_APPROVAL] = (
        ActionSignatureScope.HUMAN_EXECUTION_APPROVAL
    )
    request_id: Slug
    request_sha256: Sha256
    external_action_policy_sha256: Sha256
    action: ExternalAction
    environment: ActionEnvironment
    decision: ApprovalDecision
    decision_record_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "Human execution approval timestamp")
        return value

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        _validate_signed_window_and_hash(self, "Human execution approval")
        return self


class ControllerExecutionGrant(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    scope: Literal[ActionSignatureScope.CONTROLLER_EXECUTION_GRANT] = (
        ActionSignatureScope.CONTROLLER_EXECUTION_GRANT
    )
    grant_id_sha256: Sha256
    request_id: Slug
    request_sha256: Sha256
    human_approval_payload_sha256: Sha256
    external_action_policy_sha256: Sha256
    action: ExternalAction
    environment: ActionEnvironment
    idempotency_key_sha256: Sha256
    executor_key_id_sha256: Sha256
    release_id: Slug | None = None
    manifest_sha256: Sha256 | None = None
    artifact_sha256: Sha256 | None = None
    public_release_report_sha256: Sha256 | None = None
    public_release_authorization_sha256: Sha256 | None = None
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "controller execution grant timestamp")
        return value

    @model_validator(mode="after")
    def validate_grant(self) -> Self:
        _validate_signed_window_and_hash(self, "controller execution grant")
        return self


class ActionRevocation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    scope: Literal[ActionSignatureScope.CONTROLLER_GRANT_REVOCATION] = (
        ActionSignatureScope.CONTROLLER_GRANT_REVOCATION
    )
    request_sha256: Sha256
    grant_payload_sha256: Sha256
    external_action_policy_sha256: Sha256
    reason_record_sha256: Sha256
    issued_at: datetime
    effective_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "effective_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "action revocation timestamp")
        return value

    @model_validator(mode="after")
    def validate_revocation(self) -> Self:
        if self.effective_at < self.issued_at:
            raise ValueError("revocation cannot be effective before issuance")
        _validate_signed_payload_hash(self, "action revocation")
        return self


class ActionReceipt(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.EXECUTOR] = SigningRole.EXECUTOR
    scope: Literal[ActionSignatureScope.EXECUTOR_ACTION_RECEIPT] = (
        ActionSignatureScope.EXECUTOR_ACTION_RECEIPT
    )
    receipt_id_sha256: Sha256
    request_id: Slug
    request_sha256: Sha256
    grant_payload_sha256: Sha256
    claim_sha256: Sha256
    external_action_policy_sha256: Sha256
    action: ExternalAction
    environment: ActionEnvironment
    idempotency_key_sha256: Sha256
    result: ActionResult
    observed_pre_state_sha256: Sha256
    observed_post_state_sha256: Sha256
    provider_operation_sha256: Sha256
    provider_audit_receipt_sha256: Sha256
    started_at: datetime
    completed_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "action receipt timestamp")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("receipt completion cannot predate start")
        _validate_signed_payload_hash(self, "action receipt")
        return self


class ActionExecutionClaim(StrictModel):
    """Authenticated local one-shot claim emitted by the execution guard."""

    schema_version: Literal["1.0"] = "1.0"
    claim_id_sha256: Sha256
    request_id: Slug
    request_sha256: Sha256
    human_approval_payload_sha256: Sha256
    grant_payload_sha256: Sha256
    external_action_policy_sha256: Sha256
    action: ExternalAction
    environment: ActionEnvironment
    idempotency_key_sha256: Sha256
    observed_pre_state_sha256: Sha256
    claimed_at: datetime
    claim_sha256: Sha256

    @field_validator("claimed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "action execution claim timestamp")
        return value

    @model_validator(mode="after")
    def validate_claim(self) -> Self:
        if self.claim_sha256 != hash_action_execution_claim(self):
            raise ValueError("claim_sha256 does not match canonical execution claim")
        return self


class ActionJournalEntry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    scope: Literal[ActionSignatureScope.CONTROLLER_JOURNAL_ENTRY] = (
        ActionSignatureScope.CONTROLLER_JOURNAL_ENTRY
    )
    journal_id: Slug
    sequence: int = Field(ge=1)
    previous_entry_sha256: Sha256 | None
    event_kind: JournalEventKind
    event_payload_sha256: Sha256
    request_sha256: Sha256
    grant_payload_sha256: Sha256
    idempotency_key_sha256: Sha256
    recorded_at: datetime
    entry_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("recorded_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "journal timestamp")
        return value

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        if self.sequence == 1 and self.previous_entry_sha256 is not None:
            raise ValueError("first journal entry cannot have a predecessor")
        if self.sequence > 1 and self.previous_entry_sha256 is None:
            raise ValueError("non-first journal entry requires a predecessor")
        if self.entry_sha256 != hash_action_journal_entry(self):
            raise ValueError("entry_sha256 does not match canonical journal entry")
        return self


class ActionJournalReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    journal_id: Slug
    request_sha256: Sha256
    grant_payload_sha256: Sha256
    state_store_id_sha256: Sha256
    state_revision: int = Field(ge=0)
    state_anchor_sha256: Sha256
    authority_state: JournalAuthorityState
    outcome_state: JournalOutcomeState
    entry_count: int = Field(ge=1)
    head_entry_sha256: Sha256
    receipt_payload_sha256: Sha256 | None
    revocation_payload_sha256s: tuple[Sha256, ...]
    evaluated_at: datetime
    report_sha256: Sha256

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "journal evaluation timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.revocation_payload_sha256s != tuple(
            sorted(set(self.revocation_payload_sha256s))
        ):
            raise ValueError("revocation hashes must be canonical and unique")
        if (
            self.authority_state is JournalAuthorityState.REVOKED
            and not self.revocation_payload_sha256s
        ):
            raise ValueError("revoked journal must identify a revocation")
        if (
            self.outcome_state is not JournalOutcomeState.PENDING
            and self.receipt_payload_sha256 is None
        ):
            raise ValueError("terminal journal must identify a receipt")
        if (
            self.outcome_state is JournalOutcomeState.PENDING
            and self.receipt_payload_sha256 is not None
        ):
            raise ValueError("pending journal cannot identify a receipt")
        if self.report_sha256 != hash_action_journal_report(self):
            raise ValueError("report_sha256 does not match canonical journal report")
        return self


def hash_external_action_trust_store(store: ExternalActionTrustStore) -> str:
    validated = ExternalActionTrustStore.model_validate(store.model_dump())
    return _canonical_sha256(validated.model_dump(mode="json"))


def hash_external_action_policy(policy: ExternalActionPolicy) -> str:
    validated = ExternalActionPolicy.model_validate(policy.model_dump())
    return _canonical_sha256(validated.model_dump(mode="json"))


def hash_external_action_request(request: ExternalActionRequest) -> str:
    return _canonical_sha256(
        request.model_dump(mode="json", exclude={"request_sha256"})
    )


def build_external_action_request(**values: Any) -> ExternalActionRequest:
    payload = dict(values)
    payload.pop("request_sha256", None)
    payload.setdefault("schema_version", "1.0")
    provisional = ExternalActionRequest.model_construct(
        **payload, request_sha256="0" * 64
    )
    return ExternalActionRequest(
        **payload, request_sha256=hash_external_action_request(provisional)
    )


def sign_human_execution_approval(
    request: ExternalActionRequest,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    decision: ApprovalDecision,
    decision_record_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
) -> HumanExecutionApproval:
    validated = _validate_request(request)
    values = {
        "issuer": issuer,
        "signer_role": SigningRole.HUMAN_APPROVER,
        "scope": ActionSignatureScope.HUMAN_EXECUTION_APPROVAL,
        "request_id": validated.request_id,
        "request_sha256": validated.request_sha256,
        "external_action_policy_sha256": validated.external_action_policy_sha256,
        "action": validated.action,
        "environment": validated.environment,
        "decision": decision,
        "decision_record_sha256": decision_record_sha256,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    return _build_signed_model(
        HumanExecutionApproval,
        values,
        private_key,
        issuer=issuer,
        role=SigningRole.HUMAN_APPROVER,
    )


class ExternalActionAuthority:
    """Fixed policy, trust store, and controller signing capability."""

    __slots__ = ("__policy", "__trust_store", "__controller_signer")

    def __init__(
        self,
        policy: ExternalActionPolicy,
        trust_store: ExternalActionTrustStore,
        controller_signer: Ed25519PrivateKey,
    ) -> None:
        validated_policy = ExternalActionPolicy.model_validate(policy.model_dump())
        validated_trust = ExternalActionTrustStore.model_validate(
            trust_store.model_dump()
        )
        if validated_policy.trust_store_sha256 != hash_external_action_trust_store(
            validated_trust
        ):
            raise ExternalActionInputError("trust store does not match policy pin")
        expected_ids = (
            validated_policy.controller_key_id_sha256,
            validated_policy.human_key_id_sha256,
            validated_policy.executor_key_id_sha256,
        )
        actual_ids = (
            validated_trust.controller.key_id_sha256,
            validated_trust.human.key_id_sha256,
            validated_trust.executor.key_id_sha256,
        )
        if expected_ids != actual_ids:
            raise ExternalActionInputError("role keys do not match policy")
        if not _private_key_matches(
            controller_signer, validated_trust.controller
        ):
            raise ExternalActionInputError("controller signer is invalid")
        self.__policy = validated_policy
        self.__trust_store = validated_trust
        self.__controller_signer = controller_signer

    @property
    def policy(self) -> ExternalActionPolicy:
        return self.__policy

    @property
    def trust_store(self) -> ExternalActionTrustStore:
        return self.__trust_store

    def _sign(
        self,
        model: type[ControllerExecutionGrant]
        | type[ActionRevocation]
        | type[ActionJournalEntry],
        values: dict[str, Any],
    ) -> Any:
        return _build_signed_model(
            model,
            values,
            self.__controller_signer,
            issuer=self.__trust_store.controller.issuer,
            role=SigningRole.CONTROLLER,
        )

    def __repr__(self) -> str:
        return (
            "ExternalActionAuthority("
            f"policy_id='{self.__policy.policy_id}', controller_signer=<redacted>)"
        )

    def __getstate__(self) -> object:
        raise TypeError("ExternalActionAuthority cannot be serialized")


def issue_controller_execution_grant(
    request: ExternalActionRequest,
    approval: HumanExecutionApproval,
    authority: ExternalActionAuthority,
    *,
    at: datetime,
    public_report: ReleaseAssuranceReport | None = None,
    public_runtime: ReleaseAssuranceRuntime | None = None,
) -> ControllerExecutionGrant:
    _require_utc(at, "grant issue time")
    if type(authority) is not ExternalActionAuthority:
        raise TypeError("authority must be ExternalActionAuthority")
    validated_request = _validate_request(request)
    validated_approval = _validate_human_approval(approval)
    policy_sha256 = hash_external_action_policy(authority.policy)
    if validated_request.external_action_policy_sha256 != policy_sha256:
        raise ExternalActionInputError("request policy binding is invalid")
    if validated_request.action not in authority.policy.allowed_actions:
        raise ExternalActionInputError("action is not allowed by policy")
    if not _policy_allows_request(validated_request, authority.policy):
        raise ExternalActionInputError("request target is not allowed by policy")
    if not (
        validated_request.not_before <= at < validated_request.expires_at
    ):
        raise ExternalActionInputError("request is not currently executable")
    if (
        validated_request.expires_at - validated_request.requested_at
        > timedelta(seconds=authority.policy.maximum_request_ttl_seconds)
    ):
        raise ExternalActionInputError("request TTL exceeds policy")
    if not _human_approval_matches(
        validated_request,
        validated_approval,
        authority.trust_store.human,
        authority.policy,
        at=at,
    ):
        raise ExternalActionInputError("Human execution approval is invalid")
    if validated_approval.decision is not ApprovalDecision.GO:
        raise ExternalActionInputError("only Human GO may authorize execution")

    if validated_request.action is ExternalAction.ACTIVATE_PUBLIC_RELEASE:
        if (
            type(public_report) is not ReleaseAssuranceReport
            or type(public_runtime) is not ReleaseAssuranceRuntime
            or not verify_release_assurance_report(public_report, public_runtime, at=at)
        ):
            raise ExternalActionInputError("activation requires current P10 public GO")
        authorization = public_report.authorization
        if authorization is None:
            raise ExternalActionInputError("P10 controller authorization is missing")
        expected = (
            public_report.release_id,
            public_report.manifest_sha256,
            public_report.artifact_sha256,
            public_report.report_sha256,
            authorization.payload_sha256,
        )
        actual = (
            validated_request.release_id,
            validated_request.manifest_sha256,
            validated_request.artifact_sha256,
            validated_request.public_release_report_sha256,
            validated_request.public_release_authorization_sha256,
        )
        if expected != actual or public_report.decision is not PublicReleaseDecision.GO:
            raise ExternalActionInputError("P10 release binding does not match request")
        public_expiry = public_report.expires_at
    else:
        if public_report is not None or public_runtime is not None:
            raise ExternalActionInputError("P10 inputs are only valid for activation")
        public_expiry = validated_request.expires_at

    expires_at = min(
        validated_request.expires_at,
        validated_approval.expires_at,
        public_expiry,
        at + timedelta(seconds=authority.policy.maximum_grant_ttl_seconds),
    )
    if expires_at <= at:
        raise ExternalActionInputError("execution grant has no positive validity")
    grant_id = _canonical_sha256(
        {
            "request_sha256": validated_request.request_sha256,
            "approval_payload_sha256": validated_approval.payload_sha256,
            "issued_at": at,
            "executor_key_id_sha256": authority.trust_store.executor.key_id_sha256,
        }
    )
    values = {
        "issuer": authority.trust_store.controller.issuer,
        "signer_role": SigningRole.CONTROLLER,
        "scope": ActionSignatureScope.CONTROLLER_EXECUTION_GRANT,
        "grant_id_sha256": grant_id,
        "request_id": validated_request.request_id,
        "request_sha256": validated_request.request_sha256,
        "human_approval_payload_sha256": validated_approval.payload_sha256,
        "external_action_policy_sha256": policy_sha256,
        "action": validated_request.action,
        "environment": validated_request.environment,
        "idempotency_key_sha256": validated_request.idempotency_key_sha256,
        "executor_key_id_sha256": authority.trust_store.executor.key_id_sha256,
        "release_id": validated_request.release_id,
        "manifest_sha256": validated_request.manifest_sha256,
        "artifact_sha256": validated_request.artifact_sha256,
        "public_release_report_sha256": validated_request.public_release_report_sha256,
        "public_release_authorization_sha256": validated_request.public_release_authorization_sha256,
        "issued_at": at,
        "expires_at": expires_at,
    }
    return authority._sign(ControllerExecutionGrant, values)


def revoke_execution_grant(
    request: ExternalActionRequest,
    grant: ControllerExecutionGrant,
    authority: ExternalActionAuthority,
    guard: ExternalActionExecutionGuard,
    *,
    reason_record_sha256: str,
    issued_at: datetime,
    effective_at: datetime,
) -> ActionRevocation:
    validated_request = _validate_request(request)
    validated_grant = _validate_grant(grant)
    if not _grant_bindings_match(validated_request, validated_grant):
        raise ExternalActionInputError("grant does not match request")
    values = {
        "issuer": authority.trust_store.controller.issuer,
        "signer_role": SigningRole.CONTROLLER,
        "scope": ActionSignatureScope.CONTROLLER_GRANT_REVOCATION,
        "request_sha256": validated_request.request_sha256,
        "grant_payload_sha256": validated_grant.payload_sha256,
        "external_action_policy_sha256": hash_external_action_policy(
            authority.policy
        ),
        "reason_record_sha256": reason_record_sha256,
        "issued_at": issued_at,
        "effective_at": effective_at,
    }
    revocation = authority._sign(ActionRevocation, values)
    guard.register_revocation(validated_request, validated_grant, revocation)
    return revocation


class ExternalActionRuntime:
    """Fixed downstream verifier for a request, Human GO, grant, and P10 GO."""

    __slots__ = ("__policy", "__policy_sha256", "__trust", "__public_runtime")

    def __init__(
        self,
        policy: ExternalActionPolicy,
        trust_store: ExternalActionTrustStore,
        *,
        release_assurance_runtime: ReleaseAssuranceRuntime | None = None,
    ) -> None:
        validated_policy = ExternalActionPolicy.model_validate(policy.model_dump())
        validated_trust = ExternalActionTrustStore.model_validate(
            trust_store.model_dump()
        )
        if validated_policy.trust_store_sha256 != hash_external_action_trust_store(
            validated_trust
        ):
            raise ValueError("runtime trust store does not match policy pin")
        expected_ids = (
            validated_policy.controller_key_id_sha256,
            validated_policy.human_key_id_sha256,
            validated_policy.executor_key_id_sha256,
        )
        actual_ids = (
            validated_trust.controller.key_id_sha256,
            validated_trust.human.key_id_sha256,
            validated_trust.executor.key_id_sha256,
        )
        if expected_ids != actual_ids:
            raise ValueError("runtime role keys do not match policy")
        if release_assurance_runtime is not None and type(
            release_assurance_runtime
        ) is not ReleaseAssuranceRuntime:
            raise TypeError(
                "release_assurance_runtime must be ReleaseAssuranceRuntime"
            )
        self.__policy = validated_policy
        self.__policy_sha256 = hash_external_action_policy(validated_policy)
        self.__trust = validated_trust
        self.__public_runtime = release_assurance_runtime

    @property
    def policy(self) -> ExternalActionPolicy:
        return self.__policy

    @property
    def trust_store(self) -> ExternalActionTrustStore:
        return self.__trust

    def verifies_artifacts(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        *,
        at: datetime,
        observed_pre_state_sha256: str,
        public_report: ReleaseAssuranceReport | None = None,
    ) -> bool:
        try:
            _require_utc(at, "external action runtime time")
            validated_request = _validate_request(request)
            validated_approval = _validate_human_approval(approval)
            validated_grant = _validate_grant(grant)
        except (TypeError, ValueError, ExternalActionInputError):
            return False
        if (
            not self._verifies_grant_artifact(
                validated_request, validated_approval, validated_grant
            )
            or observed_pre_state_sha256
            != validated_request.expected_pre_state_sha256
            or not (validated_request.not_before <= at < validated_request.expires_at)
            or not (validated_grant.issued_at <= at < validated_grant.expires_at)
            or not _human_approval_matches(
                validated_request,
                validated_approval,
                self.__trust.human,
                self.__policy,
                at=at,
            )
        ):
            return False
        if validated_request.action is ExternalAction.ACTIVATE_PUBLIC_RELEASE:
            if (
                type(public_report) is not ReleaseAssuranceReport
                or self.__public_runtime is None
                or not verify_release_assurance_report(
                    public_report, self.__public_runtime, at=at
                )
                or public_report.authorization is None
            ):
                return False
            authorization = public_report.authorization
            expected = (
                public_report.release_id,
                public_report.manifest_sha256,
                public_report.artifact_sha256,
                public_report.report_sha256,
                authorization.payload_sha256,
            )
            actual = (
                validated_request.release_id,
                validated_request.manifest_sha256,
                validated_request.artifact_sha256,
                validated_request.public_release_report_sha256,
                validated_request.public_release_authorization_sha256,
            )
            if expected != actual:
                return False
        elif public_report is not None:
            return False
        return True

    def _verifies_grant_artifact(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
    ) -> bool:
        return (
            request.external_action_policy_sha256 == self.__policy_sha256
            and grant.external_action_policy_sha256 == self.__policy_sha256
            and request.action in self.__policy.allowed_actions
            and _policy_allows_request(request, self.__policy)
            and request.expires_at - request.requested_at
            <= timedelta(seconds=self.__policy.maximum_request_ttl_seconds)
            and approval.decision is ApprovalDecision.GO
            and approval.payload_sha256 == grant.human_approval_payload_sha256
            and _human_approval_matches(
                request,
                approval,
                self.__trust.human,
                self.__policy,
                at=grant.issued_at,
            )
            and _grant_bindings_match(request, grant)
            and grant.executor_key_id_sha256
            == self.__trust.executor.key_id_sha256
            and request.not_before <= grant.issued_at < request.expires_at
            and approval.issued_at <= grant.issued_at < approval.expires_at
            and grant.issued_at < grant.expires_at <= request.expires_at
            and grant.expires_at <= approval.expires_at
            and grant.expires_at - grant.issued_at
            <= timedelta(seconds=self.__policy.maximum_grant_ttl_seconds)
            and _verify_signed_model(grant, self.__trust.controller)
        )


_STATE_SCHEMA_SQL = """
CREATE TABLE external_action_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE external_action_claims (
    grant_payload_sha256 TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    external_action_policy_sha256 TEXT NOT NULL,
    idempotency_key_sha256 TEXT NOT NULL UNIQUE,
    claim_json TEXT NOT NULL,
    receipt_json TEXT
) STRICT;
CREATE TABLE external_action_revocations (
    grant_payload_sha256 TEXT NOT NULL,
    revocation_payload_sha256 TEXT NOT NULL,
    revocation_json TEXT NOT NULL,
    PRIMARY KEY (
        grant_payload_sha256,
        revocation_payload_sha256
    )
) STRICT;
"""


class _ExternalActionStateStore:
    """Authenticated local SQLite CAS state.

    Creation and recovery are deliberately separate. The companion anchor, a
    caller-held authentication key, and a separately read/committed monotonic pin
    detect reset, row mutation, schema substitution, and old database/anchor
    replacement. A production shared store/fencing system remains a P13 requirement.
    """

    __slots__ = (
        "__path",
        "__anchor_path",
        "__lock_path",
        "__store_id_sha256",
        "__authentication_key",
        "__schema_descriptor",
        "__anchor_commit",
        "__anchor_read",
        "__pinned_anchor_sha256",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        expected_store_id_sha256: str,
        expected_anchor_sha256: str,
        authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> None:
        selected = self._validate_configuration(
            path, expected_store_id_sha256, authentication_key
        )
        self._configure(
            selected,
            store_id_sha256=expected_store_id_sha256,
            authentication_key=authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
            pinned_anchor_sha256=expected_anchor_sha256,
        )
        if not selected.is_file() or not self.__anchor_path.is_file():
            raise ExternalActionInputError(
                "configured external action state or anchor is missing"
            )
        self._verify_existing()

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        store_id_sha256: str,
        authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> _ExternalActionStateStore:
        """Provision a new store once; never use this as a recovery fallback."""

        selected = cls._validate_configuration(
            path, store_id_sha256, authentication_key
        )
        store = object.__new__(cls)
        store._configure(
            selected,
            store_id_sha256=store_id_sha256,
            authentication_key=authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
            pinned_anchor_sha256=None,
        )
        if selected.exists() or store.__anchor_path.exists():
            raise ExternalActionInputError(
                "external action state is already provisioned or incomplete"
            )
        selected.parent.mkdir(parents=True, exist_ok=True)
        store._initialize_new()
        return store

    @staticmethod
    def _validate_configuration(
        path: str | Path,
        store_id_sha256: str,
        authentication_key: bytes,
    ) -> Path:
        if not isinstance(path, (str, Path)):
            raise TypeError("external action state path must be a string or Path")
        selected = Path(path)
        if str(selected) in {"", ":memory:"} or selected.name in {"", ".", ".."}:
            raise ValueError("external action state requires a durable file path")
        if not _is_sha256(store_id_sha256):
            raise ValueError("external action state store ID must be SHA-256")
        if type(authentication_key) is not bytes or len(authentication_key) < 32:
            raise ValueError(
                "external action state authentication key must be at least 32 bytes"
            )
        return selected

    def _configure(
        self,
        path: Path,
        *,
        store_id_sha256: str,
        authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        pinned_anchor_sha256: str | None,
    ) -> None:
        self.__path = path
        self.__anchor_path = path.with_name(f"{path.name}.anchor.json")
        self.__lock_path = path.with_name(f"{path.name}.lock")
        self.__store_id_sha256 = store_id_sha256
        self.__authentication_key = authentication_key
        self.__schema_descriptor = self._expected_schema_descriptor()
        if not callable(anchor_commit):
            raise TypeError("external action anchor commit must be callable")
        if not callable(anchor_read):
            raise TypeError("external action anchor read must be callable")
        if pinned_anchor_sha256 is not None and not _is_sha256(
            pinned_anchor_sha256
        ):
            raise ValueError("external action pinned anchor must be SHA-256")
        self.__anchor_commit = anchor_commit
        self.__anchor_read = anchor_read
        self.__pinned_anchor_sha256 = pinned_anchor_sha256
        if (
            pinned_anchor_sha256 is not None
            and _bounded_external_store_callback(
                anchor_read, label="external-action-anchor-read"
            )
            != pinned_anchor_sha256
        ):
            raise ExternalActionInputError(
                "configured external action anchor pin is stale"
            )

    @property
    def path(self) -> Path:
        return self.__path

    @property
    def store_id_sha256(self) -> str:
        return self.__store_id_sha256

    @property
    def anchor_sha256(self) -> str:
        if self.__pinned_anchor_sha256 is None:
            raise ExternalActionInputError(
                "external action state has no committed anchor"
            )
        return self.__pinned_anchor_sha256

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        import fcntl

        self.__lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.__lock_path.open("a+b") as lock_file:
            deadline = time.monotonic() + _EXTERNAL_ACTION_LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(
                        lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ExternalActionInputError(
                            "external action state lock timed out"
                        ) from exc
                    time.sleep(0.01)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _connect(self) -> sqlite3.Connection:
        if not self.__path.is_file():
            raise ExternalActionInputError(
                "configured external action state is missing"
            )
        connection = sqlite3.connect(
            self.__path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _schema_descriptor(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
              AND NOT (type = 'index' AND sql IS NULL)
            ORDER BY type, name
            """
        ).fetchall()
        return _canonical_sha256([tuple(row) for row in rows])

    @classmethod
    def _expected_schema_descriptor(cls) -> str:
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(_STATE_SCHEMA_SQL)
            return cls._schema_descriptor(connection)

    def _initialize_new(self) -> None:
        connection = sqlite3.connect(
            self.__path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_STATE_SCHEMA_SQL)
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "INSERT INTO external_action_meta(key, value) VALUES (?, ?)",
                (
                    ("schema_version", "2.0"),
                    ("store_id_sha256", self.__store_id_sha256),
                    ("generation", "1"),
                    ("state_revision", "0"),
                    ("state_mac_sha256", "0" * 64),
                ),
            )
            state_mac = self._calculate_state_mac(connection)
            connection.execute(
                "UPDATE external_action_meta SET value = ? WHERE key = 'state_mac_sha256'",
                (state_mac,),
            )
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()
        self._write_anchor(0, state_mac, exclusive=True)
        self._verify_existing()

    def _read_meta(self, connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute(
            "SELECT key, value FROM external_action_meta ORDER BY key"
        ).fetchall()
        meta = {row["key"]: row["value"] for row in rows}
        expected = {
            "schema_version",
            "store_id_sha256",
            "generation",
            "state_revision",
            "state_mac_sha256",
        }
        if set(meta) != expected:
            raise ExternalActionInputError(
                "external action state metadata is invalid"
            )
        return meta

    def _calculate_state_mac(self, connection: sqlite3.Connection) -> str:
        meta = self._read_meta(connection)
        payload = {
            "schema_version": meta["schema_version"],
            "store_id_sha256": meta["store_id_sha256"],
            "generation": meta["generation"],
            "state_revision": meta["state_revision"],
            "claims": [
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT grant_payload_sha256, request_id, request_sha256,
                           external_action_policy_sha256,
                           idempotency_key_sha256, claim_json, receipt_json
                    FROM external_action_claims
                    ORDER BY grant_payload_sha256
                    """
                ).fetchall()
            ],
            "revocations": [
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT grant_payload_sha256, revocation_payload_sha256,
                           revocation_json
                    FROM external_action_revocations
                    ORDER BY grant_payload_sha256, revocation_payload_sha256
                    """
                ).fetchall()
            ],
        }
        return hmac.new(
            self.__authentication_key,
            _canonical_json_bytes(payload),
            hashlib.sha256,
        ).hexdigest()

    def _anchor_payload(
        self, revision: int, state_mac_sha256: str
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "store_id_sha256": self.__store_id_sha256,
            "generation": 1,
            "state_revision": revision,
            "state_mac_sha256": state_mac_sha256,
        }

    def _write_anchor(
        self,
        revision: int,
        state_mac_sha256: str,
        *,
        exclusive: bool = False,
    ) -> None:
        payload = self._anchor_payload(revision, state_mac_sha256)
        record = {
            **payload,
            "anchor_mac_sha256": hmac.new(
                self.__authentication_key,
                _canonical_json_bytes(payload),
                hashlib.sha256,
            ).hexdigest(),
        }
        flags = os.O_WRONLY | os.O_CREAT
        flags |= os.O_EXCL if exclusive else os.O_TRUNC
        descriptor = os.open(self.__anchor_path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as anchor_file:
                serialized = _canonical_json_bytes(record)
                anchor_file.write(serialized)
                anchor_file.flush()
                os.fsync(anchor_file.fileno())
        finally:
            os.close(descriptor)
        anchor_sha256 = hashlib.sha256(serialized).hexdigest()
        _bounded_external_store_callback(
            self.__anchor_commit,
            revision,
            anchor_sha256,
            label="external-action-anchor-commit",
        )
        if _bounded_external_store_callback(
            self.__anchor_read, label="external-action-anchor-read"
        ) != anchor_sha256:
            raise ExternalActionInputError(
                "external action anchor commit was not durably observed"
            )
        self.__pinned_anchor_sha256 = anchor_sha256

    def _read_anchor(self) -> tuple[dict[str, object], str]:
        try:
            raw = self.__anchor_path.read_bytes()
            record = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise ExternalActionInputError(
                "external action state anchor is unavailable or invalid"
            ) from exc
        if type(record) is not dict or set(record) != {
            "schema_version",
            "store_id_sha256",
            "generation",
            "state_revision",
            "state_mac_sha256",
            "anchor_mac_sha256",
        }:
            raise ExternalActionInputError(
                "external action state anchor shape is invalid"
            )
        supplied_mac = record.pop("anchor_mac_sha256")
        expected_mac = hmac.new(
            self.__authentication_key,
            _canonical_json_bytes(record),
            hashlib.sha256,
        ).hexdigest()
        if not isinstance(supplied_mac, str) or not hmac.compare_digest(
            supplied_mac, expected_mac
        ):
            raise ExternalActionInputError(
                "external action state anchor authentication failed"
            )
        return record, hashlib.sha256(raw).hexdigest()

    def _assert_integrity(self, connection: sqlite3.Connection) -> tuple[int, str]:
        if self._schema_descriptor(connection) != self.__schema_descriptor:
            raise ExternalActionInputError(
                "external action state schema fingerprint is invalid"
            )
        meta = self._read_meta(connection)
        if (
            meta["schema_version"] != "2.0"
            or meta["store_id_sha256"] != self.__store_id_sha256
            or meta["generation"] != "1"
            or not meta["state_revision"].isdigit()
            or not _is_sha256(meta["state_mac_sha256"])
        ):
            raise ExternalActionInputError(
                "external action state identity or generation is invalid"
            )
        actual_mac = self._calculate_state_mac(connection)
        if not hmac.compare_digest(actual_mac, meta["state_mac_sha256"]):
            raise ExternalActionInputError(
                "external action state authentication failed"
            )
        revision = int(meta["state_revision"])
        anchor, anchor_sha256 = self._read_anchor()
        external_anchor_sha256 = _bounded_external_store_callback(
            self.__anchor_read, label="external-action-anchor-read"
        )
        if not _is_sha256(external_anchor_sha256):
            raise ExternalActionInputError(
                "external action anchor source returned an invalid pin"
            )
        if (
            anchor != self._anchor_payload(revision, actual_mac)
            or self.__pinned_anchor_sha256 is None
            or not hmac.compare_digest(
                anchor_sha256, external_anchor_sha256
            )
        ):
            raise ExternalActionInputError(
                "external action state rollback or anchor mismatch"
            )
        self.__pinned_anchor_sha256 = external_anchor_sha256
        return revision, actual_mac

    def _advance_integrity(
        self, connection: sqlite3.Connection, previous_revision: int
    ) -> tuple[int, str]:
        revision = previous_revision + 1
        cursor = connection.execute(
            "UPDATE external_action_meta SET value = ? WHERE key = 'state_revision'",
            (str(revision),),
        )
        if cursor.rowcount != 1:
            raise ExternalActionInputError(
                "external action state revision update failed"
            )
        state_mac = self._calculate_state_mac(connection)
        cursor = connection.execute(
            "UPDATE external_action_meta SET value = ? WHERE key = 'state_mac_sha256'",
            (state_mac,),
        )
        if cursor.rowcount != 1:
            raise ExternalActionInputError(
                "external action state authentication update failed"
            )
        return revision, state_mac

    def _verify_existing(self) -> None:
        with self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _register_revocation(
        self,
        grant: ControllerExecutionGrant,
        revocation: ActionRevocation,
    ) -> None:
        serialized = _canonical_model_json(revocation)
        anchor_update: tuple[int, str] | None = None
        with self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                revision, _ = self._assert_integrity(connection)
                existing = connection.execute(
                    """
                    SELECT revocation_json
                    FROM external_action_revocations
                    WHERE grant_payload_sha256 = ?
                      AND revocation_payload_sha256 = ?
                    """,
                    (grant.payload_sha256, revocation.payload_sha256),
                ).fetchone()
                if existing is not None:
                    if existing["revocation_json"] != serialized:
                        raise ExternalActionInputError(
                            "revocation payload conflicts with durable state"
                        )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO external_action_revocations(
                            grant_payload_sha256,
                            revocation_payload_sha256,
                            revocation_json
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            grant.payload_sha256,
                            revocation.payload_sha256,
                            serialized,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ExternalActionInputError(
                            "revocation durable write was not applied"
                        )
                    written = connection.execute(
                        """
                        SELECT revocation_json
                        FROM external_action_revocations
                        WHERE grant_payload_sha256 = ?
                          AND revocation_payload_sha256 = ?
                        """,
                        (grant.payload_sha256, revocation.payload_sha256),
                    ).fetchone()
                    if written is None or written["revocation_json"] != serialized:
                        raise ExternalActionInputError(
                            "revocation durable read-back failed"
                        )
                    anchor_update = self._advance_integrity(connection, revision)
                connection.execute("COMMIT")
                if anchor_update is not None:
                    self._write_anchor(*anchor_update)
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    def _claim_if_unrevoked(
        self,
        claim_factory: Callable[[], ActionExecutionClaim],
        *,
        revocation_validator: Callable[[ActionRevocation], bool],
    ) -> ActionExecutionClaim:
        with self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                revision, _ = self._assert_integrity(connection)
                claim = claim_factory()
                if type(claim) is not ActionExecutionClaim:
                    raise ExternalActionInputError(
                        "execution claim factory returned an invalid artifact"
                    )
                serialized = _canonical_model_json(claim)
                rows = connection.execute(
                    """
                    SELECT revocation_json
                    FROM external_action_revocations
                    WHERE grant_payload_sha256 = ?
                    ORDER BY revocation_payload_sha256
                    """,
                    (claim.grant_payload_sha256,),
                ).fetchall()
                for row in rows:
                    revocation = ActionRevocation.model_validate_json(
                        row["revocation_json"]
                    )
                    if not revocation_validator(revocation):
                        raise ExternalActionInputError(
                            "durable revocation state is invalid"
                        )
                    if revocation.effective_at <= claim.claimed_at:
                        raise ExternalActionInputError("execution grant is revoked")
                if connection.execute(
                    """
                    SELECT 1 FROM external_action_claims
                    WHERE grant_payload_sha256 = ?
                    """,
                    (claim.grant_payload_sha256,),
                ).fetchone() is not None:
                    raise ExternalActionInputError(
                        "execution grant was already claimed"
                    )
                if connection.execute(
                    """
                    SELECT 1 FROM external_action_claims
                    WHERE idempotency_key_sha256 = ?
                    """,
                    (claim.idempotency_key_sha256,),
                ).fetchone() is not None:
                    raise ExternalActionInputError(
                        "idempotency key was already claimed by a grant"
                    )
                if connection.execute(
                    """
                    SELECT 1 FROM external_action_claims
                    WHERE request_id = ?
                    """,
                    (claim.request_id,),
                ).fetchone() is not None:
                    raise ExternalActionInputError(
                        "request ID was already claimed"
                    )
                cursor = connection.execute(
                    """
                    INSERT INTO external_action_claims(
                        grant_payload_sha256,
                        request_id,
                        request_sha256,
                        external_action_policy_sha256,
                        idempotency_key_sha256,
                        claim_json,
                        receipt_json
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        claim.grant_payload_sha256,
                        claim.request_id,
                        claim.request_sha256,
                        claim.external_action_policy_sha256,
                        claim.idempotency_key_sha256,
                        serialized,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExternalActionInputError(
                        "execution claim durable write was not applied"
                    )
                written = connection.execute(
                    """
                    SELECT request_id, request_sha256, external_action_policy_sha256,
                           idempotency_key_sha256, claim_json, receipt_json
                    FROM external_action_claims
                    WHERE grant_payload_sha256 = ?
                    """,
                    (claim.grant_payload_sha256,),
                ).fetchone()
                if written is None or tuple(written) != (
                    claim.request_id,
                    claim.request_sha256,
                    claim.external_action_policy_sha256,
                    claim.idempotency_key_sha256,
                    serialized,
                    None,
                ):
                    raise ExternalActionInputError(
                        "execution claim durable read-back failed"
                    )
                anchor_update = self._advance_integrity(connection, revision)
                connection.execute("COMMIT")
                self._write_anchor(*anchor_update)
                return claim
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    @contextmanager
    def _execution_fence(
        self,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
        *,
        at: datetime,
        not_after: datetime,
        revocation_validator: Callable[[ActionRevocation], bool],
    ) -> Iterator[None]:
        """Hold the revocation writer fence for one external mutation."""

        claim_json = _canonical_model_json(claim)
        with self._file_lock(), self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
                "SELECT claim_json FROM external_action_claims "
                "WHERE grant_payload_sha256 = ?",
                (grant.payload_sha256,),
            ).fetchone()
            if row is None or row["claim_json"] != claim_json:
                raise ExternalActionInputError(
                    "execution claim is not in durable state"
                )
            revocations = connection.execute(
                "SELECT revocation_json FROM external_action_revocations "
                "WHERE grant_payload_sha256 = ? ORDER BY revocation_payload_sha256",
                (grant.payload_sha256,),
            ).fetchall()
            for row in revocations:
                revocation = ActionRevocation.model_validate_json(
                    row["revocation_json"]
                )
                if not revocation_validator(revocation):
                    raise ExternalActionInputError(
                        "durable revocation state is invalid"
                    )
                if revocation.effective_at < not_after:
                    raise ExternalActionInputError("execution grant is revoked")
            yield

    def _commit_receipt(
        self,
        claim: ActionExecutionClaim,
        receipt_factory: Callable[[], ActionReceipt],
    ) -> ActionReceipt:
        claim_json = _canonical_model_json(claim)
        anchor_update: tuple[int, str] | None = None
        with self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                revision, _ = self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT claim_json, receipt_json
                    FROM external_action_claims
                    WHERE grant_payload_sha256 = ?
                    """,
                    (claim.grant_payload_sha256,),
                ).fetchone()
                if row is None or row["claim_json"] != claim_json:
                    raise ExternalActionInputError(
                        "execution claim is not in durable state"
                    )
                receipt = receipt_factory()
                if type(receipt) is not ActionReceipt:
                    raise ExternalActionInputError(
                        "receipt factory returned an invalid artifact"
                    )
                receipt_json = _canonical_model_json(receipt)
                if row["receipt_json"] is not None:
                    if row["receipt_json"] != receipt_json:
                        raise ExternalActionInputError(
                            "execution grant already has a different terminal receipt"
                        )
                else:
                    cursor = connection.execute(
                        """
                        UPDATE external_action_claims
                        SET receipt_json = ?
                        WHERE grant_payload_sha256 = ?
                          AND receipt_json IS NULL
                        """,
                        (receipt_json, claim.grant_payload_sha256),
                    )
                    if cursor.rowcount != 1:
                        raise ExternalActionInputError(
                            "terminal receipt durable write was not applied"
                        )
                    written = connection.execute(
                        """
                        SELECT receipt_json FROM external_action_claims
                        WHERE grant_payload_sha256 = ?
                        """,
                        (claim.grant_payload_sha256,),
                    ).fetchone()
                    if written is None or written["receipt_json"] != receipt_json:
                        raise ExternalActionInputError(
                            "terminal receipt durable read-back failed"
                        )
                    anchor_update = self._advance_integrity(connection, revision)
                connection.execute("COMMIT")
                if anchor_update is not None:
                    self._write_anchor(*anchor_update)
                return receipt
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    def _snapshot_with_anchor(
        self, grant: ControllerExecutionGrant
    ) -> tuple[
        int,
        str,
        ActionExecutionClaim | None,
        ActionReceipt | None,
        tuple[ActionRevocation, ...],
    ]:
        try:
            with self._file_lock(), self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                revision, _ = self._assert_integrity(connection)
                anchor_sha256 = self.anchor_sha256
                state = connection.execute(
                    """
                    SELECT claim_json, receipt_json
                    FROM external_action_claims
                    WHERE grant_payload_sha256 = ?
                    """,
                    (grant.payload_sha256,),
                ).fetchone()
                rows = connection.execute(
                    """
                    SELECT revocation_json
                    FROM external_action_revocations
                    WHERE grant_payload_sha256 = ?
                    ORDER BY revocation_payload_sha256
                    """,
                    (grant.payload_sha256,),
                ).fetchall()
                connection.execute("COMMIT")
            claim = (
                ActionExecutionClaim.model_validate_json(state["claim_json"])
                if state is not None
                else None
            )
            receipt = (
                ActionReceipt.model_validate_json(state["receipt_json"])
                if state is not None and state["receipt_json"] is not None
                else None
            )
            revocations = tuple(
                ActionRevocation.model_validate_json(row["revocation_json"])
                for row in rows
            )
            return revision, anchor_sha256, claim, receipt, revocations
        except ExternalActionInputError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise ExternalActionInputError(
                "external action durable state is invalid"
            ) from exc

    def _snapshot(
        self, grant: ControllerExecutionGrant
    ) -> tuple[
        ActionExecutionClaim | None,
        ActionReceipt | None,
        tuple[ActionRevocation, ...],
    ]:
        _, _, claim, receipt, revocations = self._snapshot_with_anchor(grant)
        return claim, receipt, revocations


_STATE_GUARD_CONSTRUCTION_TOKEN = object()


class ExternalActionExecutionGuard:
    """Atomic durable claim/revocation/receipt authority for a fixed runtime.

    SQLite provides restart-safe CAS/idempotency state. This object deliberately
    cannot be serialized and performs no external action.
    """

    __slots__ = (
        "__runtime",
        "__state_store",
        "__clock",
        "__lock",
    )

    def __init__(
        self,
        runtime: ExternalActionRuntime,
        state_store: _ExternalActionStateStore,
        *,
        clock: Callable[[], datetime],
        _construction_token: object | None = None,
    ) -> None:
        if _construction_token is not _STATE_GUARD_CONSTRUCTION_TOKEN:
            raise TypeError(
                "use ExternalActionExecutionGuard.create() or .open()"
            )
        if type(runtime) is not ExternalActionRuntime:
            raise TypeError("runtime must be ExternalActionRuntime")
        if type(state_store) is not _ExternalActionStateStore:
            raise TypeError("state_store must be the internal state store")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.__runtime = runtime
        self.__state_store = state_store
        self.__clock = clock
        self.__lock = RLock()

    @classmethod
    def create(
        cls,
        runtime: ExternalActionRuntime,
        state_path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> ExternalActionExecutionGuard:
        store = _ExternalActionStateStore.create(
            state_path,
            store_id_sha256=store_id_sha256,
            authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
        )
        return cls(
            runtime,
            store,
            clock=clock,
            _construction_token=_STATE_GUARD_CONSTRUCTION_TOKEN,
        )

    @classmethod
    def open(
        cls,
        runtime: ExternalActionRuntime,
        state_path: str | Path,
        *,
        expected_store_id_sha256: str,
        expected_anchor_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> ExternalActionExecutionGuard:
        store = _ExternalActionStateStore(
            state_path,
            expected_store_id_sha256=expected_store_id_sha256,
            expected_anchor_sha256=expected_anchor_sha256,
            authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
        )
        return cls(
            runtime,
            store,
            clock=clock,
            _construction_token=_STATE_GUARD_CONSTRUCTION_TOKEN,
        )

    @property
    def runtime(self) -> ExternalActionRuntime:
        return self.__runtime

    @property
    def state_anchor_sha256(self) -> str:
        return self.__state_store.anchor_sha256

    @property
    def state_store_id_sha256(self) -> str:
        return self.__state_store.store_id_sha256

    def register_revocation(
        self,
        request: ExternalActionRequest,
        grant: ControllerExecutionGrant,
        revocation: ActionRevocation,
    ) -> None:
        validated_request = _validate_request(request)
        validated_grant = _validate_grant(grant)
        try:
            validated_revocation = ActionRevocation.model_validate(
                revocation.model_dump()
            )
        except (TypeError, ValueError) as exc:
            raise ExternalActionInputError("action revocation is invalid") from exc
        if (
            validated_request.external_action_policy_sha256
            != hash_external_action_policy(self.__runtime.policy)
            or not _grant_bindings_match(validated_request, validated_grant)
            or not _verify_signed_model(
                validated_grant, self.__runtime.trust_store.controller
            )
            or validated_revocation.request_sha256
            != validated_request.request_sha256
            or validated_revocation.grant_payload_sha256
            != validated_grant.payload_sha256
            or validated_revocation.external_action_policy_sha256
            != hash_external_action_policy(self.__runtime.policy)
            or validated_revocation.issued_at < validated_grant.issued_at
            or not _verify_signed_model(
                validated_revocation, self.__runtime.trust_store.controller
            )
        ):
            raise ExternalActionInputError("revocation binding or signature is invalid")
        with self.__lock:
            self.__state_store._register_revocation(
                validated_grant, validated_revocation
            )

    def claim(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        *,
        observed_pre_state_sha256: str,
        public_report: ReleaseAssuranceReport | None = None,
    ) -> ActionExecutionClaim:
        with self.__lock:
            def build_claim_at_cas() -> ActionExecutionClaim:
                at = self.__clock()
                _require_utc(at, "external action guard clock")
                if not self.__runtime.verifies_artifacts(
                    request,
                    approval,
                    grant,
                    at=at,
                    observed_pre_state_sha256=observed_pre_state_sha256,
                    public_report=public_report,
                ):
                    raise ExternalActionInputError(
                        "request, Human GO, grant, or P10 authority is invalid"
                    )
                values = {
                    "schema_version": "1.0",
                    "claim_id_sha256": _canonical_sha256(
                        {
                            "request_sha256": request.request_sha256,
                            "human_approval_payload_sha256": approval.payload_sha256,
                            "grant_payload_sha256": grant.payload_sha256,
                            "claimed_at": at,
                        }
                    ),
                    "request_id": request.request_id,
                    "request_sha256": request.request_sha256,
                    "human_approval_payload_sha256": approval.payload_sha256,
                    "grant_payload_sha256": grant.payload_sha256,
                    "external_action_policy_sha256": grant.external_action_policy_sha256,
                    "action": request.action,
                    "environment": request.environment,
                    "idempotency_key_sha256": request.idempotency_key_sha256,
                    "observed_pre_state_sha256": observed_pre_state_sha256,
                    "claimed_at": at,
                }
                provisional = ActionExecutionClaim.model_construct(
                    **values, claim_sha256="0" * 64
                )
                return ActionExecutionClaim(
                    **values,
                    claim_sha256=hash_action_execution_claim(provisional),
                )

            return self.__state_store._claim_if_unrevoked(
                build_claim_at_cas,
                revocation_validator=lambda item: self._revocation_matches(
                    request, grant, item
                ),
            )

    def _revocation_matches(
        self,
        request: ExternalActionRequest,
        grant: ControllerExecutionGrant,
        revocation: ActionRevocation,
    ) -> bool:
        return (
            revocation.request_sha256 == request.request_sha256
            and revocation.grant_payload_sha256 == grant.payload_sha256
            and revocation.external_action_policy_sha256
            == hash_external_action_policy(self.__runtime.policy)
            and revocation.issued_at >= grant.issued_at
            and _verify_signed_model(
                revocation, self.__runtime.trust_store.controller
            )
        )

    def _claim_matches(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
    ) -> bool:
        try:
            validated_claim = ActionExecutionClaim.model_validate(claim.model_dump())
        except (TypeError, ValueError):
            return False
        if not self._claim_artifact_matches(
            request, approval, grant, validated_claim
        ):
            return False
        try:
            stored, _, _ = self.__state_store._snapshot(grant)
        except ExternalActionInputError:
            return False
        return stored == validated_claim

    def verifies_claim(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
        *,
        at: datetime,
    ) -> bool:
        """Verify that a claim is both content-valid and present in this store.

        This is the narrow downstream splice used by a production consumer.  A
        copied or merely well-shaped claim is never sufficient: the exact claim
        must still be the authoritative durable P11 snapshot.
        """

        try:
            _require_utc(at, "execution claim verification time")
        except (TypeError, ValueError):
            return False
        with self.__lock:
            if not self._claim_matches(request, approval, grant, claim):
                return False
            try:
                _, _, revocations = self.__state_store._snapshot(grant)
            except ExternalActionInputError:
                return False
            return not any(
                self._revocation_matches(request, grant, revocation)
                and revocation.effective_at <= at
                for revocation in revocations
            )

    @contextmanager
    def dispatch_fence(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
        *,
        at: datetime,
        not_after: datetime,
    ) -> Iterator[None]:
        """Atomically bind revocation state to the external mutation window."""

        _require_utc(at, "external action dispatch fence time")
        _require_utc(not_after, "external action dispatch fence deadline")
        if (
            not at < not_after
            or not_after > request.expires_at
            or not_after > approval.expires_at
            or not_after > grant.expires_at
        ):
            raise ExternalActionInputError(
                "external action dispatch deadline exceeds signed authority"
            )
        with self.__lock:
            if not self._claim_artifact_matches(request, approval, grant, claim):
                raise ExternalActionInputError(
                    "execution claim or dispatch authority is invalid"
                )
            with self.__state_store._execution_fence(
                grant,
                claim,
                at=at,
                not_after=not_after,
                revocation_validator=lambda item: self._revocation_matches(
                    request, grant, item
                ),
            ):
                yield

    def _claim_artifact_matches(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
    ) -> bool:
        try:
            validated_claim = ActionExecutionClaim.model_validate(claim.model_dump())
        except (TypeError, ValueError):
            return False
        expected_claim_id = _canonical_sha256(
            {
                "request_sha256": request.request_sha256,
                "human_approval_payload_sha256": approval.payload_sha256,
                "grant_payload_sha256": grant.payload_sha256,
                "claimed_at": validated_claim.claimed_at,
            }
        )
        return (
            validated_claim.claim_id_sha256 == expected_claim_id
            and validated_claim.request_id == request.request_id
            and validated_claim.request_sha256 == request.request_sha256
            and validated_claim.human_approval_payload_sha256
            == approval.payload_sha256
            and validated_claim.grant_payload_sha256 == grant.payload_sha256
            and validated_claim.external_action_policy_sha256
            == grant.external_action_policy_sha256
            and validated_claim.action is request.action
            and validated_claim.environment is request.environment
            and validated_claim.idempotency_key_sha256
            == request.idempotency_key_sha256
            and validated_claim.observed_pre_state_sha256
            == request.expected_pre_state_sha256
            and request.not_before
            <= validated_claim.claimed_at
            < request.expires_at
            and approval.issued_at
            <= validated_claim.claimed_at
            < approval.expires_at
            and grant.issued_at <= validated_claim.claimed_at < grant.expires_at
            and _verify_signed_model(
                approval, self.__runtime.trust_store.human
            )
            and _verify_signed_model(
                grant, self.__runtime.trust_store.controller
            )
        )

    def _sign_and_commit_receipt(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
        private_key: Ed25519PrivateKey,
        *,
        issuer: str,
        result: ActionResult,
        observed_pre_state_sha256: str,
        observed_post_state_sha256: str,
        provider_operation_sha256: str,
        provider_audit_receipt_sha256: str,
    ) -> ActionReceipt:
        with self.__lock:
            if not self._claim_matches(request, approval, grant, claim):
                raise ExternalActionInputError("execution claim is not authoritative")

            def build_receipt_at_cas() -> ActionReceipt:
                completed_at = self.__clock()
                _require_utc(completed_at, "external action guard clock")
                if (
                    completed_at < claim.claimed_at
                    or completed_at - claim.claimed_at
                    > timedelta(
                        seconds=(
                            self.__runtime.policy.maximum_receipt_delay_seconds
                        )
                    )
                ):
                    raise ExternalActionInputError(
                        "guard receipt completion time is outside the allowed window"
                    )
                if result is ActionResult.SUCCEEDED and (
                    observed_post_state_sha256
                    != request.expected_post_state_sha256
                ):
                    raise ExternalActionInputError(
                        "success receipt must match expected post-state"
                    )
                receipt_id = _canonical_sha256(
                    {
                        "request_sha256": request.request_sha256,
                        "grant_payload_sha256": grant.payload_sha256,
                        "claim_sha256": claim.claim_sha256,
                        "completed_at": completed_at,
                        "result": result,
                    }
                )
                values = {
                    "issuer": issuer,
                    "signer_role": SigningRole.EXECUTOR,
                    "scope": ActionSignatureScope.EXECUTOR_ACTION_RECEIPT,
                    "receipt_id_sha256": receipt_id,
                    "request_id": request.request_id,
                    "request_sha256": request.request_sha256,
                    "grant_payload_sha256": grant.payload_sha256,
                    "claim_sha256": claim.claim_sha256,
                    "external_action_policy_sha256": grant.external_action_policy_sha256,
                    "action": request.action,
                    "environment": request.environment,
                    "idempotency_key_sha256": request.idempotency_key_sha256,
                    "result": result,
                    "observed_pre_state_sha256": observed_pre_state_sha256,
                    "observed_post_state_sha256": observed_post_state_sha256,
                    "provider_operation_sha256": provider_operation_sha256,
                    "provider_audit_receipt_sha256": provider_audit_receipt_sha256,
                    "started_at": claim.claimed_at,
                    "completed_at": completed_at,
                }
                receipt = _build_signed_model(
                    ActionReceipt,
                    values,
                    private_key,
                    issuer=issuer,
                    role=SigningRole.EXECUTOR,
                )
                if not _receipt_evidence_matches(
                    request,
                    grant,
                    claim,
                    receipt,
                    self.__runtime.trust_store.executor,
                    maximum_delay_seconds=(
                        self.__runtime.policy.maximum_receipt_delay_seconds
                    ),
                ):
                    raise ExternalActionInputError("action receipt is invalid")
                return receipt

            return self.__state_store._commit_receipt(
                claim, build_receipt_at_cas
            )

    def verifies_receipt(
        self,
        request: ExternalActionRequest,
        approval: HumanExecutionApproval,
        grant: ControllerExecutionGrant,
        claim: ActionExecutionClaim,
        receipt: ActionReceipt,
        *,
        at: datetime,
    ) -> bool:
        try:
            _require_utc(at, "receipt verification time")
        except (TypeError, ValueError):
            return False
        with self.__lock:
            try:
                stored_claim, stored_receipt, _ = self.__state_store._snapshot(grant)
            except ExternalActionInputError:
                return False
            return (
                self._claim_matches(request, approval, grant, claim)
                and stored_claim == claim
                and stored_receipt == receipt
                and receipt.completed_at <= at
                and _receipt_evidence_matches(
                    request,
                    grant,
                    claim,
                    receipt,
                    self.__runtime.trust_store.executor,
                    maximum_delay_seconds=(
                        self.__runtime.policy.maximum_receipt_delay_seconds
                    ),
                )
            )

    def authoritative_snapshot(
        self, grant: ControllerExecutionGrant
    ) -> tuple[
        ActionExecutionClaim | None,
        ActionReceipt | None,
        tuple[ActionRevocation, ...],
    ]:
        with self.__lock:
            return self.__state_store._snapshot(grant)

    def _authoritative_snapshot_with_anchor(
        self, grant: ControllerExecutionGrant
    ) -> tuple[
        int,
        str,
        ActionExecutionClaim | None,
        ActionReceipt | None,
        tuple[ActionRevocation, ...],
    ]:
        with self.__lock:
            return self.__state_store._snapshot_with_anchor(grant)

    def _snapshot_is_current(
        self,
        grant: ControllerExecutionGrant,
        *,
        revision: int,
        anchor_sha256: str,
    ) -> bool:
        with self.__lock:
            try:
                current_revision, current_anchor, _, _, _ = (
                    self.__state_store._snapshot_with_anchor(grant)
                )
            except ExternalActionInputError:
                return False
            return (
                current_revision == revision
                and current_anchor == anchor_sha256
            )

    def verifies_revocation(
        self,
        request: ExternalActionRequest,
        grant: ControllerExecutionGrant,
        revocation: ActionRevocation,
    ) -> bool:
        with self.__lock:
            try:
                _, _, stored = self.__state_store._snapshot(grant)
            except ExternalActionInputError:
                return False
            return (
                revocation in stored
                and self._revocation_matches(request, grant, revocation)
            )

    def __repr__(self) -> str:
        return "ExternalActionExecutionGuard(state=<redacted>)"

    def __getstate__(self) -> object:
        raise TypeError("ExternalActionExecutionGuard cannot be serialized")


def sign_action_receipt(
    request: ExternalActionRequest,
    approval: HumanExecutionApproval,
    grant: ControllerExecutionGrant,
    claim: ActionExecutionClaim,
    guard: ExternalActionExecutionGuard,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    result: ActionResult,
    observed_pre_state_sha256: str,
    observed_post_state_sha256: str,
    provider_operation_sha256: str,
    provider_audit_receipt_sha256: str,
) -> ActionReceipt:
    validated_request = _validate_request(request)
    validated_approval = _validate_human_approval(approval)
    validated_grant = _validate_grant(grant)
    try:
        validated_claim = ActionExecutionClaim.model_validate(claim.model_dump())
    except (TypeError, ValueError) as exc:
        raise ExternalActionInputError("execution claim is invalid") from exc
    if type(guard) is not ExternalActionExecutionGuard or not guard._claim_matches(
        validated_request, validated_approval, validated_grant, validated_claim
    ):
        raise ExternalActionInputError("execution claim is not authoritative")
    return guard._sign_and_commit_receipt(
        validated_request,
        validated_approval,
        validated_grant,
        validated_claim,
        private_key,
        issuer=issuer,
        result=result,
        observed_pre_state_sha256=observed_pre_state_sha256,
        observed_post_state_sha256=observed_post_state_sha256,
        provider_operation_sha256=provider_operation_sha256,
        provider_audit_receipt_sha256=provider_audit_receipt_sha256,
    )


def verify_action_receipt(
    request: ExternalActionRequest,
    approval: HumanExecutionApproval,
    grant: ControllerExecutionGrant,
    claim: ActionExecutionClaim,
    receipt: ActionReceipt,
    guard: ExternalActionExecutionGuard,
    *,
    at: datetime,
    require_success: bool = True,
) -> bool:
    try:
        validated_request = _validate_request(request)
        validated_approval = _validate_human_approval(approval)
        validated_grant = _validate_grant(grant)
        validated_claim = ActionExecutionClaim.model_validate(claim.model_dump())
        validated_receipt = ActionReceipt.model_validate(receipt.model_dump())
    except (TypeError, ValueError, ExternalActionInputError):
        return False
    if type(guard) is not ExternalActionExecutionGuard or not guard.verifies_receipt(
        validated_request,
        validated_approval,
        validated_grant,
        validated_claim,
        validated_receipt,
        at=at,
    ):
        return False
    if require_success:
        return (
            validated_receipt.result is ActionResult.SUCCEEDED
            and validated_receipt.observed_post_state_sha256
            == validated_request.expected_post_state_sha256
        )
    return True


def append_action_journal_entry(
    *,
    journal_id: str,
    entries: tuple[ActionJournalEntry, ...],
    event_kind: JournalEventKind,
    event_payload_sha256: str,
    request: ExternalActionRequest,
    grant: ControllerExecutionGrant,
    authority: ExternalActionAuthority,
    recorded_at: datetime,
) -> ActionJournalEntry:
    _require_utc(recorded_at, "journal record time")
    validated_request = _validate_request(request)
    validated_grant = _validate_grant(grant)
    if (
        not _grant_bindings_match(validated_request, validated_grant)
        or validated_request.external_action_policy_sha256
        != hash_external_action_policy(authority.policy)
        or not _verify_signed_model(
            validated_grant, authority.trust_store.controller
        )
    ):
        raise ExternalActionInputError("journal grant does not match request")
    expected_previous: str | None = None
    for index, raw_entry in enumerate(entries, start=1):
        try:
            entry = ActionJournalEntry.model_validate(raw_entry.model_dump())
        except (TypeError, ValueError) as exc:
            raise ExternalActionInputError("existing journal is invalid") from exc
        if (
            entry.journal_id != journal_id
            or entry.sequence != index
            or entry.previous_entry_sha256 != expected_previous
            or entry.request_sha256 != validated_request.request_sha256
            or entry.grant_payload_sha256 != validated_grant.payload_sha256
            or entry.idempotency_key_sha256
            != validated_request.idempotency_key_sha256
            or not _verify_signed_journal_entry(
                entry, authority.trust_store.controller
            )
        ):
            raise ExternalActionInputError("existing journal chain is invalid")
        expected_previous = entry.entry_sha256
    if entries and recorded_at < entries[-1].recorded_at:
        raise ExternalActionInputError("journal timestamps must be monotonic")
    if recorded_at < validated_grant.issued_at:
        raise ExternalActionInputError("journal cannot predate grant issuance")
    previous = entries[-1].entry_sha256 if entries else None
    values = {
        "issuer": authority.trust_store.controller.issuer,
        "signer_role": SigningRole.CONTROLLER,
        "scope": ActionSignatureScope.CONTROLLER_JOURNAL_ENTRY,
        "journal_id": journal_id,
        "sequence": len(entries) + 1,
        "previous_entry_sha256": previous,
        "event_kind": event_kind,
        "event_payload_sha256": event_payload_sha256,
        "request_sha256": validated_request.request_sha256,
        "grant_payload_sha256": validated_grant.payload_sha256,
        "idempotency_key_sha256": validated_request.idempotency_key_sha256,
        "recorded_at": recorded_at,
    }
    return _build_signed_journal_entry(values, authority)


def fold_action_journal(
    request: ExternalActionRequest,
    approval: HumanExecutionApproval,
    grant: ControllerExecutionGrant,
    claim: ActionExecutionClaim | None,
    entries: tuple[ActionJournalEntry, ...],
    guard: ExternalActionExecutionGuard,
    *,
    revocations: tuple[ActionRevocation, ...] = (),
    receipts: tuple[ActionReceipt, ...] = (),
    public_report: ReleaseAssuranceReport | None = None,
    at: datetime,
) -> ActionJournalReport:
    _require_utc(at, "journal evaluation time")
    validated_request = _validate_request(request)
    validated_approval = _validate_human_approval(approval)
    validated_grant = _validate_grant(grant)
    if type(guard) is not ExternalActionExecutionGuard:
        raise TypeError("guard must be ExternalActionExecutionGuard")
    if not guard.runtime.verifies_artifacts(
        validated_request,
        validated_approval,
        validated_grant,
        at=validated_grant.issued_at,
        observed_pre_state_sha256=validated_request.expected_pre_state_sha256,
        public_report=public_report,
    ):
        raise ExternalActionInputError("journal grant authority is invalid")
    (
        state_revision,
        state_anchor_sha256,
        authoritative_claim,
        authoritative_receipt,
        authoritative_revocations,
    ) = guard._authoritative_snapshot_with_anchor(validated_grant)
    if claim is not None:
        try:
            validated_claim = ActionExecutionClaim.model_validate(claim.model_dump())
        except (TypeError, ValueError) as exc:
            raise ExternalActionInputError("journal claim is invalid") from exc
        if not guard._claim_artifact_matches(
            validated_request,
            validated_approval,
            validated_grant,
            validated_claim,
        ):
            raise ExternalActionInputError("journal claim is not authoritative")
    else:
        validated_claim = None
    if validated_claim != authoritative_claim:
        raise ExternalActionInputError(
            "journal claim does not match durable authoritative state"
        )
    if not entries:
        raise ExternalActionInputError("journal cannot be empty")
    expected_previous: str | None = None
    previous_recorded_at: datetime | None = None
    grant_events = 0
    claim_events = 0
    revocation_hashes: list[str] = []
    receipt_hash: str | None = None
    selected_receipt: ActionReceipt | None = None
    seen_payloads: set[str] = set()
    try:
        validated_revocations = tuple(
            ActionRevocation.model_validate(item.model_dump())
            for item in revocations
        )
        validated_receipts = tuple(
            ActionReceipt.model_validate(item.model_dump()) for item in receipts
        )
    except (TypeError, ValueError) as exc:
        raise ExternalActionInputError("journal sidecar is invalid") from exc
    revocation_map = {
        item.payload_sha256: item for item in validated_revocations
    }
    receipt_map = {item.payload_sha256: item for item in validated_receipts}
    if len(revocation_map) != len(revocations) or len(receipt_map) != len(receipts):
        raise ExternalActionInputError("journal sidecar payloads must be unique")
    authoritative_revocation_map = {
        item.payload_sha256: item for item in authoritative_revocations
    }
    if revocation_map != authoritative_revocation_map:
        raise ExternalActionInputError(
            "journal revocations do not match durable authoritative state"
        )
    authoritative_receipt_map = (
        {authoritative_receipt.payload_sha256: authoritative_receipt}
        if authoritative_receipt is not None
        else {}
    )
    if receipt_map != authoritative_receipt_map:
        raise ExternalActionInputError(
            "journal receipts do not match durable authoritative state"
        )
    journal_id: str | None = None
    for index, raw_entry in enumerate(entries, start=1):
        try:
            entry = ActionJournalEntry.model_validate(raw_entry.model_dump())
        except (TypeError, ValueError) as exc:
            raise ExternalActionInputError("journal entry is invalid") from exc
        if journal_id is None:
            journal_id = entry.journal_id
        if (
            entry.sequence != index
            or entry.previous_entry_sha256 != expected_previous
            or entry.journal_id != journal_id
            or entry.request_sha256 != validated_request.request_sha256
            or entry.grant_payload_sha256 != validated_grant.payload_sha256
            or entry.idempotency_key_sha256
            != validated_request.idempotency_key_sha256
            or not _verify_signed_journal_entry(
                entry, guard.runtime.trust_store.controller
            )
            or entry.event_payload_sha256 in seen_payloads
            or entry.recorded_at > at
            or (
                previous_recorded_at is not None
                and entry.recorded_at < previous_recorded_at
            )
        ):
            raise ExternalActionInputError("journal chain or binding is invalid")
        seen_payloads.add(entry.event_payload_sha256)
        if entry.event_kind is JournalEventKind.GRANT:
            grant_events += 1
            if (
                index != 1
                or entry.event_payload_sha256 != validated_grant.payload_sha256
                or entry.recorded_at < validated_grant.issued_at
            ):
                raise ExternalActionInputError("grant must be the first journal event")
        elif entry.event_kind is JournalEventKind.CLAIM:
            claim_events += 1
            if (
                validated_claim is None
                or entry.event_payload_sha256 != validated_claim.claim_sha256
                or entry.recorded_at < validated_claim.claimed_at
                or receipt_hash is not None
            ):
                raise ExternalActionInputError("journal claim event is invalid")
        elif entry.event_kind is JournalEventKind.REVOCATION:
            revocation = revocation_map.get(entry.event_payload_sha256)
            if (
                revocation is None
                or not guard._revocation_matches(
                    validated_request, validated_grant, revocation
                )
                or entry.recorded_at < revocation.issued_at
            ):
                raise ExternalActionInputError("journal revocation sidecar is missing")
            revocation_hashes.append(revocation.payload_sha256)
        else:
            receipt = receipt_map.get(entry.event_payload_sha256)
            if (
                receipt is None
                or receipt_hash is not None
                or validated_claim is None
                or entry.recorded_at < receipt.completed_at
            ):
                raise ExternalActionInputError("journal terminal receipt is invalid")
            receipt_hash = receipt.payload_sha256
            selected_receipt = receipt
        expected_previous = entry.entry_sha256
        previous_recorded_at = entry.recorded_at
    if grant_events != 1:
        raise ExternalActionInputError("journal must contain exactly one grant")
    expected_claim_events = 1 if validated_claim is not None else 0
    if claim_events != expected_claim_events:
        raise ExternalActionInputError("journal claim cardinality is invalid")
    if set(revocation_map) != set(revocation_hashes):
        raise ExternalActionInputError("journal revocation sidecars are not exact")
    expected_receipts = {receipt_hash} if receipt_hash is not None else set()
    if set(receipt_map) != expected_receipts:
        raise ExternalActionInputError("journal receipt sidecars are not exact")

    effective_revocations = tuple(
        item
        for item in validated_revocations
        if item.payload_sha256 in revocation_hashes
    )
    if selected_receipt is not None:
        if (
            selected_receipt.completed_at > at
            or not _receipt_evidence_matches(
                validated_request,
                validated_grant,
                validated_claim,
                selected_receipt,
                guard.runtime.trust_store.executor,
                maximum_delay_seconds=(
                    guard.runtime.policy.maximum_receipt_delay_seconds
                ),
            )
        ):
            raise ExternalActionInputError("journal receipt verification failed")
        outcome_state = JournalOutcomeState(selected_receipt.result.value)
    else:
        outcome_state = JournalOutcomeState.PENDING
    if any(item.effective_at <= at for item in effective_revocations):
        authority_state = JournalAuthorityState.REVOKED
    elif validated_claim is not None:
        authority_state = JournalAuthorityState.CLAIMED
    elif at >= validated_grant.expires_at:
        authority_state = JournalAuthorityState.EXPIRED
    else:
        authority_state = JournalAuthorityState.GRANTED
    values = {
        "schema_version": "1.0",
        "journal_id": journal_id,
        "request_sha256": validated_request.request_sha256,
        "grant_payload_sha256": validated_grant.payload_sha256,
        "state_store_id_sha256": guard.state_store_id_sha256,
        "state_revision": state_revision,
        "state_anchor_sha256": state_anchor_sha256,
        "authority_state": authority_state,
        "outcome_state": outcome_state,
        "entry_count": len(entries),
        "head_entry_sha256": entries[-1].entry_sha256,
        "receipt_payload_sha256": receipt_hash,
        "revocation_payload_sha256s": tuple(sorted(revocation_hashes)),
        "evaluated_at": at,
    }
    provisional = ActionJournalReport.model_construct(
        **values, report_sha256="0" * 64
    )
    report = ActionJournalReport(
        **values, report_sha256=hash_action_journal_report(provisional)
    )
    if not guard._snapshot_is_current(
        validated_grant,
        revision=state_revision,
        anchor_sha256=state_anchor_sha256,
    ):
        raise ExternalActionInputError(
            "journal durable state changed during evaluation"
        )
    return report


def hash_action_journal_entry(entry: ActionJournalEntry) -> str:
    return _canonical_sha256(
        entry.model_dump(
            mode="json", exclude={"entry_sha256", "signature_base64url"}
        )
    )


def hash_action_execution_claim(claim: ActionExecutionClaim) -> str:
    return _canonical_sha256(
        claim.model_dump(mode="json", exclude={"claim_sha256"})
    )


def hash_action_journal_report(report: ActionJournalReport) -> str:
    return _canonical_sha256(
        report.model_dump(mode="json", exclude={"report_sha256"})
    )


def _receipt_evidence_matches(
    request: ExternalActionRequest,
    grant: ControllerExecutionGrant,
    claim: ActionExecutionClaim,
    receipt: ActionReceipt,
    executor_key: Ed25519VerificationKey,
    *,
    maximum_delay_seconds: int,
) -> bool:
    binding = (
        receipt.request_id,
        receipt.request_sha256,
        receipt.grant_payload_sha256,
        receipt.claim_sha256,
        receipt.external_action_policy_sha256,
        receipt.action,
        receipt.environment,
        receipt.idempotency_key_sha256,
        receipt.observed_pre_state_sha256,
        receipt.started_at,
    )
    expected = (
        request.request_id,
        request.request_sha256,
        grant.payload_sha256,
        claim.claim_sha256,
        grant.external_action_policy_sha256,
        request.action,
        request.environment,
        request.idempotency_key_sha256,
        claim.observed_pre_state_sha256,
        claim.claimed_at,
    )
    return (
        binding == expected
        and receipt.receipt_id_sha256
        == _canonical_sha256(
            {
                "request_sha256": request.request_sha256,
                "grant_payload_sha256": grant.payload_sha256,
                "claim_sha256": claim.claim_sha256,
                "completed_at": receipt.completed_at,
                "result": receipt.result,
            }
        )
        and claim.observed_pre_state_sha256 == request.expected_pre_state_sha256
        and receipt.completed_at - claim.claimed_at
        <= timedelta(seconds=maximum_delay_seconds)
        and (
            receipt.result is not ActionResult.SUCCEEDED
            or receipt.observed_post_state_sha256
            == request.expected_post_state_sha256
        )
        and _verify_signed_model(receipt, executor_key)
    )


def _build_signed_journal_entry(
    values: dict[str, Any], authority: ExternalActionAuthority
) -> ActionJournalEntry:
    return authority._sign(ActionJournalEntry, values)


def _build_signed_model(
    model: type[HumanExecutionApproval]
    | type[ControllerExecutionGrant]
    | type[ActionRevocation]
    | type[ActionReceipt]
    | type[ActionJournalEntry],
    values: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    role: SigningRole,
) -> Any:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    key = create_verification_key(private_key.public_key(), issuer=issuer, role=role)
    payload = {"schema_version": "1.0", **values}
    payload["issuer"] = key.issuer
    payload["key_id_sha256"] = key.key_id_sha256
    payload.pop("signature_base64url", None)
    if model is ActionJournalEntry:
        payload.pop("entry_sha256", None)
        provisional = ActionJournalEntry.model_construct(
            **payload, entry_sha256="0" * 64, signature_base64url="A" * 86
        )
        payload["entry_sha256"] = hash_action_journal_entry(provisional)
    else:
        payload.pop("payload_sha256", None)
        payload["payload_sha256"] = _canonical_sha256(payload)
    signature = private_key.sign(_canonical_json_bytes(payload))
    return model(**payload, signature_base64url=_encode_base64url(signature))


def _validate_signed_window_and_hash(model: StrictModel, label: str) -> None:
    issued_at = getattr(model, "issued_at")
    expires_at = getattr(model, "expires_at")
    if expires_at <= issued_at:
        raise ValueError(f"{label} expiry must follow issuance")
    _validate_signed_payload_hash(model, label)


def _validate_signed_payload_hash(model: StrictModel, label: str) -> None:
    payload = model.model_dump(
        mode="json", exclude={"payload_sha256", "signature_base64url"}
    )
    if getattr(model, "payload_sha256") != _canonical_sha256(payload):
        raise ValueError(f"{label} payload hash mismatch")


def _validate_request(request: ExternalActionRequest) -> ExternalActionRequest:
    if type(request) is not ExternalActionRequest:
        raise TypeError("request must be ExternalActionRequest")
    try:
        return ExternalActionRequest.model_validate(request.model_dump())
    except (TypeError, ValueError) as exc:
        raise ExternalActionInputError("external action request is invalid") from exc


def _validate_human_approval(
    approval: HumanExecutionApproval,
) -> HumanExecutionApproval:
    if type(approval) is not HumanExecutionApproval:
        raise TypeError("approval must be HumanExecutionApproval")
    try:
        return HumanExecutionApproval.model_validate(approval.model_dump())
    except (TypeError, ValueError) as exc:
        raise ExternalActionInputError("Human execution approval is invalid") from exc


def _validate_grant(grant: ControllerExecutionGrant) -> ControllerExecutionGrant:
    if type(grant) is not ControllerExecutionGrant:
        raise TypeError("grant must be ControllerExecutionGrant")
    try:
        return ControllerExecutionGrant.model_validate(grant.model_dump())
    except (TypeError, ValueError) as exc:
        raise ExternalActionInputError("controller execution grant is invalid") from exc


def _external_action_target_rule_key(
    rule: ExternalActionTargetRule,
) -> tuple[str, str, str, str, str, str]:
    return (
        rule.action.value,
        rule.environment.value,
        rule.environment_sha256,
        rule.vendor_slug or "",
        rule.property_record_sha256,
        rule.target_sha256,
    )


def _policy_allows_request(
    request: ExternalActionRequest, policy: ExternalActionPolicy
) -> bool:
    actual = (
        request.action,
        request.environment,
        request.environment_sha256,
        request.vendor_slug,
        request.property_record_sha256,
        request.target_sha256,
    )
    return any(
        actual
        == (
            rule.action,
            rule.environment,
            rule.environment_sha256,
            rule.vendor_slug,
            rule.property_record_sha256,
            rule.target_sha256,
        )
        for rule in policy.target_rules
    )


def _human_approval_matches(
    request: ExternalActionRequest,
    approval: HumanExecutionApproval,
    key: Ed25519VerificationKey,
    policy: ExternalActionPolicy,
    *,
    at: datetime,
) -> bool:
    return (
        approval.request_id == request.request_id
        and approval.request_sha256 == request.request_sha256
        and approval.external_action_policy_sha256
        == request.external_action_policy_sha256
        and approval.action is request.action
        and approval.environment is request.environment
        and approval.issued_at >= request.requested_at
        and approval.issued_at <= at < approval.expires_at
        and approval.expires_at - approval.issued_at
        <= timedelta(seconds=policy.maximum_approval_ttl_seconds)
        and _verify_signed_model(approval, key)
    )


def _grant_bindings_match(
    request: ExternalActionRequest, grant: ControllerExecutionGrant
) -> bool:
    return (
        grant.request_id == request.request_id
        and grant.request_sha256 == request.request_sha256
        and grant.external_action_policy_sha256
        == request.external_action_policy_sha256
        and grant.action is request.action
        and grant.environment is request.environment
        and grant.idempotency_key_sha256 == request.idempotency_key_sha256
        and grant.release_id == request.release_id
        and grant.manifest_sha256 == request.manifest_sha256
        and grant.artifact_sha256 == request.artifact_sha256
        and grant.public_release_report_sha256
        == request.public_release_report_sha256
        and grant.public_release_authorization_sha256
        == request.public_release_authorization_sha256
    )


def _verify_signed_model(model: StrictModel, key: Ed25519VerificationKey) -> bool:
    try:
        signature = _decode_base64url(
            getattr(model, "signature_base64url"), expected_length=64
        )
        message = _canonical_json_bytes(
            model.model_dump(mode="json", exclude={"signature_base64url"})
        )
        key.public_key().verify(signature, message)
    except (TypeError, ValueError, InvalidSignature):
        return False
    return (
        getattr(model, "issuer") == key.issuer
        and getattr(model, "key_id_sha256") == key.key_id_sha256
        and getattr(model, "signer_role") is key.role
    )


def _verify_signed_journal_entry(
    entry: ActionJournalEntry,
    key: Ed25519VerificationKey,
) -> bool:
    return _verify_signed_model(entry, key)


def _private_key_matches(
    private_key: Ed25519PrivateKey,
    verification_key: Ed25519VerificationKey,
) -> bool:
    if not isinstance(private_key, Ed25519PrivateKey):
        return False
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return (
        hashlib.sha256(raw).hexdigest() == verification_key.key_id_sha256
        and _encode_base64url(raw) == verification_key.public_key_base64url
    )


def _require_utc(value: datetime, label: str) -> None:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str, expected_length: int) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid canonical base64url") from exc
    if len(decoded) != expected_length or _encode_base64url(decoded) != value:
        raise ValueError("invalid canonical base64url length or encoding")
    return decoded


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_model_json(value: StrictModel) -> str:
    return _canonical_json_bytes(value.model_dump(mode="json")).decode("utf-8")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if isinstance(value, Enum):
        return value.value
    if type(value) is datetime:
        _require_utc(value, "canonical datetime")
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, StrictModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


__all__ = [
    "ActionEnvironment",
    "ActionExecutionClaim",
    "ExternalActionExecutionGuard",
    "ActionJournalEntry",
    "ActionJournalReport",
    "ActionResult",
    "ActionRevocation",
    "ActionSignatureScope",
    "ActionReceipt",
    "ControllerExecutionGrant",
    "ExternalAction",
    "ExternalActionAuthority",
    "ExternalActionInputError",
    "ExternalActionPolicy",
    "ExternalActionRequest",
    "ExternalActionRuntime",
    "ExternalActionTargetRule",
    "ExternalActionTrustStore",
    "HumanExecutionApproval",
    "JournalEventKind",
    "JournalAuthorityState",
    "JournalOutcomeState",
    "REQUIRED_EXTERNAL_ACTIONS",
    "append_action_journal_entry",
    "build_external_action_request",
    "fold_action_journal",
    "hash_action_journal_entry",
    "hash_action_execution_claim",
    "hash_action_journal_report",
    "hash_external_action_policy",
    "hash_external_action_request",
    "hash_external_action_trust_store",
    "issue_controller_execution_grant",
    "revoke_execution_grant",
    "sign_action_receipt",
    "sign_human_execution_approval",
    "verify_action_receipt",
]
