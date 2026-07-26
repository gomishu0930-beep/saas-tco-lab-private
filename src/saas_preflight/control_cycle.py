"""Pure offline control decision and content-bound dead-man lease.

The evaluator composes existing immutable artifacts.  It performs no fetch,
write, promotion, rollback, publication, deployment, or external operation.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from .economics import Decision
from .goldset import GoldSetReport, hash_goldset_report
from .models import Sha256, StrictModel
from .operations import (
    BudgetStatus,
    ExceptionQueue,
    ExceptionStatus,
    MonthlyHumanBudget,
    Severity,
)
from .preflight import BusinessDossier, evaluate_business_dossier
from .release import (
    ReleaseAction,
    ReleaseEvent,
    ReleaseManifest,
    ReleaseState,
    evaluate_visibility,
)


class ControlInputError(ValueError):
    """An untrusted copied model cannot be canonicalized safely."""


class ControlDecision(str, Enum):
    STOP = "stop"
    HOLD = "hold"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    MAINTAIN_CURRENT = "maintain_current"


class ControlReason(str, Enum):
    CONFIG_INVALID = "config_invalid"
    TRUST_STORE_INVALID = "trust_store_invalid"
    TRUST_STORE_MISMATCH = "trust_store_mismatch"
    CONTROLLER_KEY_INVALID = "controller_key_invalid"
    BUSINESS_STOP = "business_stop"
    BUSINESS_CONTINUE = "business_continue"
    DOSSIER_INVALID = "dossier_invalid"
    GOLD_REPORT_INVALID = "gold_report_invalid"
    GOLD_REPORT_FUTURE = "gold_report_future"
    GOLD_REPORT_STALE = "gold_report_stale"
    GOLD_NOT_READY = "gold_not_ready"
    GOLD_ATTESTATION_INVALID = "gold_attestation_invalid"
    PARSER_FAILURE_STOP = "parser_failure_stop"
    RIGHTS_BINDING_MISMATCH = "rights_binding_mismatch"
    AFFILIATE_BINDING_MISMATCH = "affiliate_binding_mismatch"
    CANDIDATE_BINDING_MISMATCH = "candidate_binding_mismatch"
    HEARTBEAT_INVALID = "heartbeat_invalid"
    HEARTBEAT_FUTURE = "heartbeat_future"
    HEARTBEAT_STALE = "heartbeat_stale"
    SCHEDULER_INTERVAL_EXCEEDED = "scheduler_interval_exceeded"
    SCHEDULER_LAG = "scheduler_lag"
    OPEN_SEV0 = "open_sev0"
    OPEN_SEV1 = "open_sev1"
    BUDGET_MONTH_MISMATCH = "budget_month_mismatch"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_CURRENT_RELEASE = "no_current_release"
    RELEASE_FUTURE = "release_future"
    RELEASE_HIDDEN = "release_hidden"
    RELEASE_ATTESTATION_INVALID = "release_attestation_invalid"
    LEASE_DEADLINE_REACHED = "lease_deadline_reached"


class SigningRole(str, Enum):
    CONTROLLER = "controller"
    TCO_QA = "tco_qa"
    HUMAN_APPROVER = "human_approver"
    EXECUTOR = "executor"
    DEMAND_PRODUCER = "demand_producer"
    COHORT_PRODUCER = "cohort_producer"
    OPERATIONS_PRODUCER = "operations_producer"
    MEASUREMENT_HUMAN = "measurement_human"
    MEASUREMENT_INDEXER = "measurement_indexer"
    PROVIDER_ADAPTER = "provider_adapter"
    PROVIDER_PROBE = "provider_probe"
    INTEGRATION_EVIDENCE_RUNNER = "integration_evidence_runner"
    PROVIDER_CONFORMANCE = "provider_conformance"
    SECURITY_AUDITOR = "security_auditor"
    STORAGE_AUDITOR = "storage_auditor"
    TIME_AUDITOR = "time_auditor"
    NETWORK_AUDITOR = "network_auditor"
    RECOVERY_AUDITOR = "recovery_auditor"


class AttestationScope(str, Enum):
    GOLD_REPORT_ACCEPTANCE = "gold_report_acceptance"
    CURRENT_RELEASE_DECISION = "current_release_decision"


class LeaseScope(str, Enum):
    SERVE_PROTECTED_CONTENT = "serve_protected_content"


class Ed25519VerificationKey(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    role: SigningRole
    key_id_sha256: Sha256
    public_key_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")

    @model_validator(mode="after")
    def validate_key_id(self) -> Self:
        public_bytes = _decode_base64url(self.public_key_base64url, expected_length=32)
        if hashlib.sha256(public_bytes).hexdigest() != self.key_id_sha256:
            raise ValueError("key_id_sha256 does not match Ed25519 public key")
        return self

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(
            _decode_base64url(self.public_key_base64url, expected_length=32)
        )


class ControlTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    controller: Ed25519VerificationKey
    gold_tco_qa: Ed25519VerificationKey
    release_human: Ed25519VerificationKey

    @model_validator(mode="after")
    def require_separate_role_keys(self) -> Self:
        expected = (
            (self.controller, SigningRole.CONTROLLER),
            (self.gold_tco_qa, SigningRole.TCO_QA),
            (self.release_human, SigningRole.HUMAN_APPROVER),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("verification key role does not match trust-store slot")
        key_ids = {key.key_id_sha256 for key, _ in expected}
        if len(key_ids) != 3:
            raise ValueError("controller, TCO/QA, and Human keys must be distinct")
        return self


class ControlConfig(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    controller_issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    controller_key_id_sha256: Sha256
    trust_store_sha256: Sha256
    lease_scope: Literal[LeaseScope.SERVE_PROTECTED_CONTENT] = (
        LeaseScope.SERVE_PROTECTED_CONTENT
    )
    lease_seconds: int = Field(ge=1, le=3600)
    heartbeat_ttl_seconds: int = Field(ge=1, le=86400)
    gold_report_ttl_seconds: int = Field(ge=1, le=86400)
    schedule_grace_seconds: int = Field(ge=0, le=3600)
    maximum_schedule_interval_seconds: int = Field(ge=1, le=86400)


class ControllerAuthority:
    """Trusted bootstrap bundle; deliberately non-serializable and signer-redacted."""

    __slots__ = ("__config", "__trust_store", "__signer")

    def __init__(
        self,
        config: ControlConfig,
        trust_store: ControlTrustStore,
        signer: Ed25519PrivateKey,
    ) -> None:
        if type(config) is not ControlConfig or type(trust_store) is not ControlTrustStore:
            raise TypeError("authority requires ControlConfig and ControlTrustStore")
        if not isinstance(signer, Ed25519PrivateKey):
            raise TypeError("authority signer must be Ed25519PrivateKey")
        validated_config = ControlConfig.model_validate(config.model_dump())
        validated_trust = ControlTrustStore.model_validate(trust_store.model_dump())
        if (
            validated_config.trust_store_sha256
            != hash_control_trust_store(validated_trust)
        ):
            raise ControlInputError("authority trust store does not match config pin")
        if (
            validated_config.controller_issuer != validated_trust.controller.issuer
            or validated_config.controller_key_id_sha256
            != validated_trust.controller.key_id_sha256
            or not _private_key_matches(signer, validated_trust.controller)
        ):
            raise ControlInputError("authority controller identity or signer is invalid")
        self.__config = validated_config
        self.__trust_store = validated_trust
        self.__signer = signer

    @property
    def config(self) -> ControlConfig:
        return self.__config

    @property
    def trust_store(self) -> ControlTrustStore:
        return self.__trust_store

    def _sign_lease(self, **values: Any) -> ServingLease:
        return _build_lease(private_key=self.__signer, **values)

    def __repr__(self) -> str:
        return (
            "ControllerAuthority("
            f"controller_key_id_sha256='{self.__config.controller_key_id_sha256}', "
            f"trust_store_sha256='{self.__config.trust_store_sha256}', "
            "signer=<redacted>)"
        )

    def __getstate__(self) -> object:
        raise TypeError("ControllerAuthority cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("ControllerAuthority cannot be serialized")


class SchedulerHeartbeat(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    scheduler_id_sha256: Sha256
    run_receipt_sha256: Sha256
    observed_at: datetime
    next_run_at: datetime

    @field_validator("observed_at", "next_run_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "heartbeat timestamp")
        return value

    @model_validator(mode="after")
    def require_forward_schedule(self) -> Self:
        if self.next_run_at <= self.observed_at:
            raise ValueError("next_run_at must be later than observed_at")
        return self


class GoldReportAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA] = SigningRole.TCO_QA
    scope: Literal[AttestationScope.GOLD_REPORT_ACCEPTANCE] = (
        AttestationScope.GOLD_REPORT_ACCEPTANCE
    )
    gold_report_sha256: Sha256
    rights_bundle_sha256: Sha256
    candidate_batch_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "gold attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        _validate_signed_window_and_payload(self, "gold attestation")
        return self


class ReleaseDecisionAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER] = SigningRole.HUMAN_APPROVER
    scope: Literal[AttestationScope.CURRENT_RELEASE_DECISION] = (
        AttestationScope.CURRENT_RELEASE_DECISION
    )
    release_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    manifest_sha256: Sha256
    release_event_sha256: Sha256
    decision_record_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "release attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        _validate_signed_window_and_payload(self, "release attestation")
        return self


class ServingLease(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    controller_key_id_sha256: Sha256
    scope: Literal[LeaseScope.SERVE_PROTECTED_CONTENT] = (
        LeaseScope.SERVE_PROTECTED_CONTENT
    )
    control_input_sha256: Sha256
    release_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "lease timestamp")
        return value

    @model_validator(mode="after")
    def validate_lease(self) -> Self:
        _validate_signed_window_and_payload(self, "lease")
        return self


class ControlReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: ControlDecision
    evaluated_at: datetime
    input_sha256: Sha256
    reasons: tuple[ControlReason, ...]
    business_decision: Decision | None
    gold_report_sha256: Sha256
    budget_status: BudgetStatus | None
    unresolved_sev0_count: int = Field(ge=0)
    unresolved_sev1_count: int = Field(ge=0)
    current_release_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    current_manifest_sha256: Sha256 | None
    current_artifact_sha256: Sha256 | None
    serving_lease: ServingLease | None
    report_sha256: Sha256

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "control report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        canonical_reasons = tuple(sorted(set(self.reasons), key=lambda item: item.value))
        if self.reasons != canonical_reasons:
            raise ValueError("control reasons must be unique and canonically sorted")
        current_values = (
            self.current_release_id,
            self.current_manifest_sha256,
            self.current_artifact_sha256,
        )
        if any(value is None for value in current_values) and any(
            value is not None for value in current_values
        ):
            raise ValueError("current release identity must be all present or all absent")
        if self.decision is ControlDecision.MAINTAIN_CURRENT:
            if self.serving_lease is None:
                raise ValueError("maintain_current requires a serving lease")
            if (
                self.serving_lease.release_id != self.current_release_id
                or self.serving_lease.manifest_sha256 != self.current_manifest_sha256
                or self.serving_lease.artifact_sha256 != self.current_artifact_sha256
            ):
                raise ValueError("serving lease does not match current release")
        elif self.serving_lease is not None:
            raise ValueError("only maintain_current may contain a serving lease")
        if self.report_sha256 != _control_report_hash(self):
            raise ValueError("report_sha256 does not match canonical report")
        return self


def evaluate_control_cycle(
    authority: ControllerAuthority,
    dossier: BusinessDossier,
    gold_report: GoldSetReport,
    release_state: ReleaseState,
    heartbeat: SchedulerHeartbeat,
    exception_queue: ExceptionQueue,
    budget: MonthlyHumanBudget | None,
    *,
    gold_attestation: GoldReportAttestation | None,
    release_attestation: ReleaseDecisionAttestation | None,
    at: datetime,
) -> ControlReport:
    """Evaluate one deterministic cycle without changing any supplied state."""

    if type(authority) is not ControllerAuthority:
        raise TypeError("authority must be ControllerAuthority")
    if type(dossier) is not BusinessDossier:
        raise TypeError("dossier must be BusinessDossier")
    if type(gold_report) is not GoldSetReport:
        raise TypeError("gold_report must be GoldSetReport")
    if type(release_state) is not ReleaseState:
        raise TypeError("release_state must be ReleaseState")
    if type(heartbeat) is not SchedulerHeartbeat:
        raise TypeError("heartbeat must be SchedulerHeartbeat")
    if type(exception_queue) is not ExceptionQueue:
        raise TypeError("exception_queue must be ExceptionQueue")
    if budget is not None and type(budget) is not MonthlyHumanBudget:
        raise TypeError("budget must be MonthlyHumanBudget or None")
    if gold_attestation is not None and type(gold_attestation) is not GoldReportAttestation:
        raise TypeError("gold_attestation must be GoldReportAttestation or None")
    if release_attestation is not None and type(release_attestation) is not ReleaseDecisionAttestation:
        raise TypeError("release_attestation must be ReleaseDecisionAttestation or None")
    _require_utc(at, "evaluation timestamp")

    config = authority.config
    trust_store = authority.trust_store

    try:
        input_sha256 = _control_input_hash(
            config,
            dossier,
            gold_report,
            release_state,
            heartbeat,
            exception_queue,
            budget,
            gold_attestation,
            release_attestation,
            trust_store,
            at,
        )
    except Exception as exc:
        raise ControlInputError("control input cannot be canonicalized") from exc
    hard_stop: set[ControlReason] = set()
    hold: set[ControlReason] = set()

    validated_config = None
    try:
        validated_config = ControlConfig.model_validate(config.model_dump())
    except (TypeError, ValueError):
        hard_stop.add(ControlReason.CONFIG_INVALID)

    validated_trust_store = None
    try:
        validated_trust_store = ControlTrustStore.model_validate(trust_store.model_dump())
    except (TypeError, ValueError):
        hard_stop.add(ControlReason.TRUST_STORE_INVALID)
    if validated_config is not None and validated_trust_store is not None:
        if (
            validated_config.controller_issuer
            != validated_trust_store.controller.issuer
            or validated_config.controller_key_id_sha256
            != validated_trust_store.controller.key_id_sha256
        ):
            hard_stop.add(ControlReason.CONTROLLER_KEY_INVALID)
        if (
            validated_config.trust_store_sha256
            != hash_control_trust_store(validated_trust_store)
        ):
            hard_stop.add(ControlReason.TRUST_STORE_MISMATCH)

    dossier_evaluation = None
    validated_dossier = None
    try:
        validated_dossier = BusinessDossier.model_validate(dossier.model_dump())
    except (TypeError, ValueError):
        hard_stop.add(ControlReason.DOSSIER_INVALID)
    else:
        dossier_evaluation = evaluate_business_dossier(validated_dossier, at=at)
        if dossier_evaluation.decision is Decision.STOP:
            hard_stop.add(ControlReason.BUSINESS_STOP)
        elif dossier_evaluation.decision is Decision.CONTINUE:
            hold.add(ControlReason.BUSINESS_CONTINUE)

    validated_gold_report = None
    try:
        validated_gold_report = GoldSetReport.model_validate(gold_report.model_dump())
    except (TypeError, ValueError):
        hard_stop.add(ControlReason.GOLD_REPORT_INVALID)
    validated_gold_attestation = None
    if gold_attestation is not None:
        try:
            validated_gold_attestation = GoldReportAttestation.model_validate(
                gold_attestation.model_dump()
            )
        except (TypeError, ValueError):
            pass
    if validated_gold_report is not None:
        if (
            validated_gold_report.report_sha256
            != hash_goldset_report(validated_gold_report)
        ):
            hard_stop.add(ControlReason.GOLD_REPORT_INVALID)
        if validated_gold_report.evaluated_at > at:
            hold.add(ControlReason.GOLD_REPORT_FUTURE)
        if at >= validated_gold_report.expires_at:
            hold.add(ControlReason.GOLD_REPORT_STALE)
        if validated_config is not None and at >= (
            validated_gold_report.evaluated_at
            + timedelta(seconds=validated_config.gold_report_ttl_seconds)
        ):
            hold.add(ControlReason.GOLD_REPORT_STALE)
        if validated_gold_report.parser_failure_stop:
            hard_stop.add(ControlReason.PARSER_FAILURE_STOP)
        elif not validated_gold_report.ready_for_release:
            hold.add(ControlReason.GOLD_NOT_READY)
        if (
            validated_dossier is not None
            and validated_gold_report.rights_bundle_sha256
            != validated_dossier.provenance.rights_bundle_sha256
        ):
            hard_stop.add(ControlReason.RIGHTS_BINDING_MISMATCH)

        if (
            validated_gold_attestation is None
            or validated_trust_store is None
            or not _verify_gold_attestation(
                validated_gold_attestation,
                validated_gold_report,
                validated_trust_store.gold_tco_qa,
                at=at,
            )
        ):
            hard_stop.add(ControlReason.GOLD_ATTESTATION_INVALID)
    elif gold_attestation is None:
        hard_stop.add(ControlReason.GOLD_ATTESTATION_INVALID)

    validated_heartbeat = None
    try:
        validated_heartbeat = SchedulerHeartbeat.model_validate(heartbeat.model_dump())
    except (TypeError, ValueError):
        hold.add(ControlReason.HEARTBEAT_INVALID)
    heartbeat_deadline = at
    schedule_deadline = at
    if validated_heartbeat is not None and validated_config is not None:
        heartbeat_deadline = validated_heartbeat.observed_at + timedelta(
            seconds=validated_config.heartbeat_ttl_seconds
        )
        schedule_deadline = validated_heartbeat.next_run_at + timedelta(
            seconds=validated_config.schedule_grace_seconds
        )
        if validated_heartbeat.observed_at > at:
            hold.add(ControlReason.HEARTBEAT_FUTURE)
        if at >= heartbeat_deadline:
            hold.add(ControlReason.HEARTBEAT_STALE)
        if (
            validated_heartbeat.next_run_at - validated_heartbeat.observed_at
            > timedelta(seconds=validated_config.maximum_schedule_interval_seconds)
        ):
            hold.add(ControlReason.SCHEDULER_INTERVAL_EXCEEDED)
        if at >= schedule_deadline:
            hold.add(ControlReason.SCHEDULER_LAG)

    unresolved = tuple(
        item
        for item in exception_queue.items
        if item.status is not ExceptionStatus.RESOLVED
    )
    sev0_count = sum(item.severity is Severity.SEV0 for item in unresolved)
    sev1_count = sum(item.severity is Severity.SEV1 for item in unresolved)
    if sev0_count:
        hard_stop.add(ControlReason.OPEN_SEV0)
    if sev1_count:
        hold.add(ControlReason.OPEN_SEV1)

    budget_status: BudgetStatus | None = None
    expected_month = at.strftime("%Y-%m")
    if budget is None or budget.month != expected_month:
        hold.add(ControlReason.BUDGET_MONTH_MISMATCH)
    else:
        budget_status = budget.status
        if budget_status is BudgetStatus.EXHAUSTED:
            hard_stop.add(ControlReason.BUDGET_EXHAUSTED)

    current = None
    current_event = None
    validated_release_attestation = None
    if release_attestation is not None:
        try:
            validated_release_attestation = ReleaseDecisionAttestation.model_validate(
                release_attestation.model_dump()
            )
        except (TypeError, ValueError):
            pass
    if release_state.current_release_id is not None:
        current = release_state.get(release_state.current_release_id)
        current_event = _current_release_event(release_state)
        if current.prepared_at > at or any(event.occurred_at > at for event in release_state.events):
            hard_stop.add(ControlReason.RELEASE_FUTURE)
        visibility = evaluate_visibility(release_state, at=at)
        if not visibility.visible:
            hard_stop.add(ControlReason.RELEASE_HIDDEN)
        if (
            validated_dossier is not None
            and current.rights_bundle_sha256
            != validated_dossier.provenance.rights_bundle_sha256
        ):
            hard_stop.add(ControlReason.RIGHTS_BINDING_MISMATCH)
        if (
            validated_dossier is not None
            and current.affiliate_bundle_sha256
            != validated_dossier.provenance.affiliate_bundle_sha256
        ):
            hard_stop.add(ControlReason.AFFILIATE_BINDING_MISMATCH)
        if (
            validated_gold_report is not None
            and validated_gold_report.candidate_batch_sha256
            not in current.data_snapshot_sha256s
        ):
            hard_stop.add(ControlReason.CANDIDATE_BINDING_MISMATCH)
        if (
            current_event is None
            or validated_release_attestation is None
            or validated_trust_store is None
            or not _verify_release_attestation(
                validated_release_attestation,
                current,
                current_event,
                validated_trust_store.release_human,
                at=at,
            )
        ):
            hard_stop.add(ControlReason.RELEASE_ATTESTATION_INVALID)

    if hard_stop:
        decision = ControlDecision.STOP
        reasons = hard_stop | hold
    elif hold:
        decision = ControlDecision.HOLD
        reasons = hold
    elif current is None:
        decision = ControlDecision.HUMAN_APPROVAL_REQUIRED
        reasons = {ControlReason.NO_CURRENT_RELEASE}
    else:
        decision = ControlDecision.MAINTAIN_CURRENT
        reasons = set()

    lease = None
    if decision is ControlDecision.MAINTAIN_CURRENT:
        assert current is not None
        assert validated_config is not None
        assert validated_dossier is not None
        assert validated_gold_report is not None
        assert validated_gold_attestation is not None
        assert validated_release_attestation is not None
        lease_expiry = min(
            at + timedelta(seconds=validated_config.lease_seconds),
            heartbeat_deadline,
            schedule_deadline,
            min(validated_dossier.expires_at.items(), key=lambda item: item[1])[1],
            validated_gold_report.expires_at,
            validated_gold_report.evaluated_at
            + timedelta(seconds=validated_config.gold_report_ttl_seconds),
            validated_gold_attestation.expires_at,
            validated_release_attestation.expires_at,
            current.shortest_expiry,
        )
        if lease_expiry <= at:
            decision = ControlDecision.HOLD
            reasons.add(ControlReason.LEASE_DEADLINE_REACHED)
        else:
            lease = authority._sign_lease(
                issuer=validated_config.controller_issuer,
                controller_key_id_sha256=validated_config.controller_key_id_sha256,
                scope=validated_config.lease_scope,
                control_input_sha256=input_sha256,
                release_id=current.release_id,
                manifest_sha256=current.manifest_sha256,
                artifact_sha256=current.artifact_sha256,
                issued_at=at,
                expires_at=lease_expiry,
            )

    report_values: dict[str, Any] = {
        "decision": decision,
        "evaluated_at": at,
        "input_sha256": input_sha256,
        "reasons": tuple(sorted(reasons, key=lambda item: item.value)),
        "business_decision": (
            None if dossier_evaluation is None else dossier_evaluation.decision
        ),
        "gold_report_sha256": (
            validated_gold_report.report_sha256
            if validated_gold_report is not None
            else _canonical_sha256(
                {"invalid_gold_report": gold_report.model_dump(mode="json")}
            )
        ),
        "budget_status": budget_status,
        "unresolved_sev0_count": sev0_count,
        "unresolved_sev1_count": sev1_count,
        "current_release_id": None if current is None else current.release_id,
        "current_manifest_sha256": None if current is None else current.manifest_sha256,
        "current_artifact_sha256": None if current is None else current.artifact_sha256,
        "serving_lease": lease,
    }
    provisional = ControlReport.model_construct(**report_values, report_sha256="0" * 64)
    report_values["report_sha256"] = _control_report_hash(provisional)
    return ControlReport(**report_values)


def create_verification_key(
    public_key: Ed25519PublicKey,
    *,
    issuer: str,
    role: SigningRole,
) -> Ed25519VerificationKey:
    """Create a public-only key receipt; private key material is never serialized."""

    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("public_key must be Ed25519PublicKey")
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return Ed25519VerificationKey(
        issuer=issuer,
        role=role,
        key_id_sha256=hashlib.sha256(raw).hexdigest(),
        public_key_base64url=_encode_base64url(raw),
    )


def hash_control_trust_store(trust_store: ControlTrustStore) -> str:
    """Pin every issuer, role, key ID, and Ed25519 public key as one receipt."""

    if type(trust_store) is not ControlTrustStore:
        raise TypeError("trust_store must be ControlTrustStore")
    validated = ControlTrustStore.model_validate(trust_store.model_dump())
    return _canonical_sha256(validated.model_dump(mode="json"))


def sign_gold_report_attestation(
    report: GoldSetReport,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> GoldReportAttestation:
    """Sign a TCO/QA acceptance receipt without serializing the private key."""

    if type(report) is not GoldSetReport:
        raise TypeError("report must be GoldSetReport")
    validated = GoldSetReport.model_validate(report.model_dump())
    key = _verification_key_from_private(
        private_key,
        issuer=issuer,
        role=SigningRole.TCO_QA,
    )
    return _build_signed_model(
        GoldReportAttestation,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.TCO_QA,
            "scope": AttestationScope.GOLD_REPORT_ACCEPTANCE,
            "gold_report_sha256": validated.report_sha256,
            "rights_bundle_sha256": validated.rights_bundle_sha256,
            "candidate_batch_sha256": validated.candidate_batch_sha256,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
    )


def verify_gold_report_attestation(
    attestation: GoldReportAttestation,
    report: GoldSetReport,
    key: Ed25519VerificationKey,
    *,
    at: datetime,
) -> bool:
    """Verify a gold report acceptance using only its public TCO/QA key."""

    if (
        type(attestation) is not GoldReportAttestation
        or type(report) is not GoldSetReport
        or type(key) is not Ed25519VerificationKey
    ):
        return False
    try:
        _require_utc(at, "gold attestation verification timestamp")
        validated_report = GoldSetReport.model_validate(report.model_dump())
        validated_key = Ed25519VerificationKey.model_validate(key.model_dump())
    except (TypeError, ValueError):
        return False
    return _verify_gold_attestation(
        attestation, validated_report, validated_key, at=at
    )


def sign_release_decision_attestation(
    state: ReleaseState,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> ReleaseDecisionAttestation:
    """Sign the current Human release event, not a caller-created approval object."""

    if type(state) is not ReleaseState:
        raise TypeError("state must be ReleaseState")
    if state.current_release_id is None:
        raise ValueError("cannot attest a release state without a current release")
    event = _current_release_event(state)
    if event is None or event.decision_record_sha256 is None:
        raise ValueError("current release has no Human decision event")
    manifest = state.get(state.current_release_id)
    key = _verification_key_from_private(
        private_key,
        issuer=issuer,
        role=SigningRole.HUMAN_APPROVER,
    )
    return _build_signed_model(
        ReleaseDecisionAttestation,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.HUMAN_APPROVER,
            "scope": AttestationScope.CURRENT_RELEASE_DECISION,
            "release_id": manifest.release_id,
            "manifest_sha256": manifest.manifest_sha256,
            "release_event_sha256": hash_release_event(event),
            "decision_record_sha256": event.decision_record_sha256,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
    )


def hash_release_event(event: ReleaseEvent) -> str:
    if type(event) is not ReleaseEvent:
        raise TypeError("event must be ReleaseEvent")
    return _canonical_sha256(
        {
            "action": event.action,
            "release_id": event.release_id,
            "occurred_at": event.occurred_at,
            "previous_release_id": event.previous_release_id,
            "decision_record_sha256": event.decision_record_sha256,
        }
    )


def verify_serving_lease(
    lease: ServingLease,
    verification_key: Ed25519VerificationKey,
    *,
    expected_issuer: str,
    expected_scope: LeaseScope,
    maximum_ttl_seconds: int,
    at: datetime,
) -> bool:
    """Verify authenticity, fixed identity/scope, time window, and maximum TTL."""

    _require_utc(at, "lease verification timestamp")
    if type(maximum_ttl_seconds) is not int or not 1 <= maximum_ttl_seconds <= 3600:
        raise ValueError("maximum_ttl_seconds must be an integer from 1 through 3600")
    if type(lease) is not ServingLease or type(verification_key) is not Ed25519VerificationKey:
        return False
    try:
        validated = ServingLease.model_validate(lease.model_dump())
        key = Ed25519VerificationKey.model_validate(verification_key.model_dump())
    except (TypeError, ValueError):
        return False
    if (
        key.role is not SigningRole.CONTROLLER
        or validated.issuer != expected_issuer
        or validated.issuer != key.issuer
        or validated.controller_key_id_sha256 != key.key_id_sha256
        or validated.scope is not expected_scope
        or not (validated.issued_at <= at < validated.expires_at)
        or validated.expires_at - validated.issued_at
        > timedelta(seconds=maximum_ttl_seconds)
    ):
        return False
    return _verify_signature(validated, key)


def _build_lease(*, private_key: Ed25519PrivateKey, **values: Any) -> ServingLease:
    return _build_signed_model(ServingLease, values, private_key)


def _build_signed_model(model_type: type[StrictModel], values: dict[str, Any], private_key: Ed25519PrivateKey):
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    provisional = model_type.model_construct(
        **values,
        payload_sha256="0" * 64,
        signature_base64url="A" * 86,
    )
    values = dict(values)
    values["payload_sha256"] = _signed_payload_hash(provisional)
    with_payload = model_type.model_construct(
        **values,
        signature_base64url="A" * 86,
    )
    values["signature_base64url"] = _encode_base64url(
        private_key.sign(_signature_message(with_payload))
    )
    return model_type(**values)


def _control_input_hash(
    config: ControlConfig,
    dossier: BusinessDossier,
    gold_report: GoldSetReport,
    release_state: ReleaseState,
    heartbeat: SchedulerHeartbeat,
    exception_queue: ExceptionQueue,
    budget: MonthlyHumanBudget | None,
    gold_attestation: GoldReportAttestation | None,
    release_attestation: ReleaseDecisionAttestation | None,
    trust_store: ControlTrustStore,
    at: datetime,
) -> str:
    manifests = []
    for manifest in sorted(release_state.manifests, key=lambda item: item.release_id):
        manifests.append(
            {
                "release_id": manifest.release_id,
                "manifest_sha256": manifest.manifest_sha256,
                "artifact_sha256": manifest.artifact_sha256,
                "schema_sha256": manifest.schema_sha256,
                "data_snapshot_sha256s": sorted(manifest.data_snapshot_sha256s),
                "rights_bundle_sha256": manifest.rights_bundle_sha256,
                "affiliate_bundle_sha256": manifest.affiliate_bundle_sha256,
                "data_expires_at": manifest.data_expires_at,
                "rights_expires_at": manifest.rights_expires_at,
                "affiliate_expires_at": manifest.affiliate_expires_at,
                "cta_decision": manifest.cta.decision,
                "cta_destination_sha256": manifest.cta.destination_sha256,
                "cta_disclosure_sha256": manifest.cta.disclosure_sha256,
                "rollback_release_id": manifest.rollback_release_id,
            }
        )
    events = [
        {
            "action": event.action,
            "release_id": event.release_id,
            "occurred_at": event.occurred_at,
            "previous_release_id": event.previous_release_id,
            "decision_record_sha256": event.decision_record_sha256,
        }
        for event in sorted(
            release_state.events,
            key=lambda item: (
                item.occurred_at,
                item.action.value,
                item.release_id,
                item.previous_release_id or "",
            ),
        )
    ]
    exceptions = [
        {
            "exception_key": item.exception_key,
            "fingerprint_sha256": item.fingerprint_sha256,
            "severity": item.severity,
            "status": item.status,
            "detected_at": item.detected_at,
            "acknowledged_at": item.acknowledged_at,
            "acknowledged_by": item.acknowledged_by,
            "resolved_at": item.resolved_at,
            "resolution_sha256": item.resolution_sha256,
        }
        for item in sorted(exception_queue.items, key=lambda item: item.exception_key)
    ]
    budget_payload = None
    if budget is not None:
        budget_payload = {
            "month": budget.month,
            "entries": [
                {
                    "entry_sha256": entry.entry_sha256,
                    "reference": entry.reference,
                    "role": entry.role,
                    "work_class": entry.work_class,
                    "minutes": entry.minutes,
                    "occurred_at": entry.occurred_at,
                }
                for entry in sorted(budget.entries, key=lambda entry: entry.entry_sha256)
            ],
        }
    return _canonical_sha256(
        {
            "config": config.model_dump(mode="json"),
            "dossier": dossier.model_dump(mode="json"),
            "gold_report": gold_report.model_dump(mode="json"),
            "release_state": {
                "current_release_id": release_state.current_release_id,
                "manifests": manifests,
                "events": events,
            },
            "heartbeat": heartbeat.model_dump(mode="json"),
            "gold_attestation": (
                None
                if gold_attestation is None
                else gold_attestation.model_dump(mode="json")
            ),
            "release_attestation": (
                None
                if release_attestation is None
                else release_attestation.model_dump(mode="json")
            ),
            "trust_store": trust_store.model_dump(mode="json"),
            "exceptions": exceptions,
            "budget": budget_payload,
            "evaluated_at": at,
        }
    )


def _verify_gold_attestation(
    attestation: GoldReportAttestation,
    report: GoldSetReport,
    key: Ed25519VerificationKey,
    *,
    at: datetime,
) -> bool:
    try:
        validated = GoldReportAttestation.model_validate(attestation.model_dump())
    except (TypeError, ValueError):
        return False
    return (
        key.role is SigningRole.TCO_QA
        and validated.issuer == key.issuer
        and validated.key_id_sha256 == key.key_id_sha256
        and validated.signer_role is SigningRole.TCO_QA
        and validated.scope is AttestationScope.GOLD_REPORT_ACCEPTANCE
        and validated.gold_report_sha256 == report.report_sha256
        and validated.rights_bundle_sha256 == report.rights_bundle_sha256
        and validated.candidate_batch_sha256 == report.candidate_batch_sha256
        and validated.issued_at <= at < validated.expires_at
        and _verify_signature(validated, key)
    )


def _verify_release_attestation(
    attestation: ReleaseDecisionAttestation,
    manifest: ReleaseManifest,
    event: ReleaseEvent,
    key: Ed25519VerificationKey,
    *,
    at: datetime,
) -> bool:
    try:
        validated = ReleaseDecisionAttestation.model_validate(attestation.model_dump())
    except (TypeError, ValueError):
        return False
    return (
        event.decision_record_sha256 is not None
        and key.role is SigningRole.HUMAN_APPROVER
        and validated.issuer == key.issuer
        and validated.key_id_sha256 == key.key_id_sha256
        and validated.signer_role is SigningRole.HUMAN_APPROVER
        and validated.scope is AttestationScope.CURRENT_RELEASE_DECISION
        and validated.release_id == manifest.release_id
        and validated.manifest_sha256 == manifest.manifest_sha256
        and validated.release_event_sha256 == hash_release_event(event)
        and validated.decision_record_sha256 == event.decision_record_sha256
        and validated.issued_at <= at < validated.expires_at
        and _verify_signature(validated, key)
    )


def _verify_signature(model: StrictModel, key: Ed25519VerificationKey) -> bool:
    try:
        key.public_key().verify(
            _decode_base64url(model.signature_base64url, expected_length=64),  # type: ignore[attr-defined]
            _signature_message(model),
        )
    except (AttributeError, InvalidSignature, TypeError, ValueError):
        return False
    return True


def _private_key_matches(
    private_key: Ed25519PrivateKey,
    verification_key: Ed25519VerificationKey,
) -> bool:
    try:
        public_key = _verification_key_from_private(
            private_key,
            issuer=verification_key.issuer,
            role=SigningRole.CONTROLLER,
        )
    except (TypeError, ValueError):
        return False
    return public_key == verification_key


def _verification_key_from_private(
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    role: SigningRole,
) -> Ed25519VerificationKey:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    return create_verification_key(private_key.public_key(), issuer=issuer, role=role)


def _current_release_event(state: ReleaseState) -> ReleaseEvent | None:
    if state.current_release_id is None:
        return None
    for event in reversed(state.events):
        if (
            event.release_id == state.current_release_id
            and event.action in (ReleaseAction.PROMOTED, ReleaseAction.ROLLED_BACK)
        ):
            return event
    return None


def _validate_signed_window_and_payload(model: StrictModel, label: str) -> None:
    issued_at = model.issued_at  # type: ignore[attr-defined]
    expires_at = model.expires_at  # type: ignore[attr-defined]
    if expires_at <= issued_at:
        raise ValueError(f"{label} expires_at must be later than issued_at")
    _decode_base64url(model.signature_base64url, expected_length=64)  # type: ignore[attr-defined]
    if model.payload_sha256 != _signed_payload_hash(model):  # type: ignore[attr-defined]
        raise ValueError(f"{label} payload_sha256 does not match canonical payload")


def _signed_payload_hash(model: StrictModel) -> str:
    return hashlib.sha256(_unsigned_payload_bytes(model)).hexdigest()


def _unsigned_payload_bytes(model: StrictModel) -> bytes:
    return _canonical_json_bytes(
        model.model_dump(
            mode="json",
            exclude={"payload_sha256", "signature_base64url"},
        )
    )


def _signature_message(model: StrictModel) -> bytes:
    return _canonical_json_bytes(
        model.model_dump(mode="json", exclude={"signature_base64url"})
    )


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str, *, expected_length: int) -> bytes:
    if type(value) is not str:
        raise TypeError("base64url value must be a string")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid canonical base64url value") from exc
    if len(decoded) != expected_length or _encode_base64url(decoded) != value:
        raise ValueError("invalid canonical base64url length or encoding")
    return decoded


def _control_report_hash(report: ControlReport) -> str:
    return _canonical_sha256(report.model_dump(mode="json", exclude={"report_sha256"}))


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be canonicalized")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        _require_utc(value, "canonical datetime")
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _require_utc(value: datetime, label: str) -> None:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


__all__ = [
    "AttestationScope",
    "ControlConfig",
    "ControllerAuthority",
    "ControlDecision",
    "ControlInputError",
    "ControlReason",
    "ControlReport",
    "ControlTrustStore",
    "Ed25519VerificationKey",
    "GoldReportAttestation",
    "LeaseScope",
    "ReleaseDecisionAttestation",
    "SchedulerHeartbeat",
    "ServingLease",
    "SigningRole",
    "create_verification_key",
    "evaluate_control_cycle",
    "hash_release_event",
    "hash_control_trust_store",
    "sign_gold_report_attestation",
    "verify_gold_report_attestation",
    "sign_release_decision_attestation",
    "verify_serving_lease",
]
