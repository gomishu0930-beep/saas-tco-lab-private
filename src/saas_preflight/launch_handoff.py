"""Credential-free, non-authoritative launch handoff sequencing.

P16 binds already-produced gate artifacts into one immutable packet for final
Human review.  It deliberately does not reimplement P9-P15, authorize an
external action, contact a provider, or mutate any state.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import Ed25519VerificationKey, SigningRole
from .launch_semantics import (
    LaunchSemanticAuthorityPins,
    LaunchSemanticPacket,
    evaluate_launch_semantics,
    hash_launch_semantic_authority_pins,
)
from .models import Sha256, Slug, StrictModel
from .repository_acceptance import (
    RepositoryAcceptanceAuthorityBundle,
    RepositoryAcceptanceDecision,
    evaluate_repository_acceptance_authority_bundle,
)


class LaunchHandoffInputError(ValueError):
    """An untrusted copied P16 model or cross-model binding is invalid."""


class LaunchHandoffGate(str, Enum):
    LOCAL_CANDIDATE_ACCEPTANCE = "local_candidate_acceptance"
    RIGHTS_APPROVAL = "rights_approval"
    AFFILIATE_ACCEPTANCE = "affiliate_acceptance"
    QUALIFIED_DEMAND = "qualified_demand"
    SHADOW_OPERATIONS = "shadow_operations"
    GOLD_SET_SOURCE_READINESS = "gold_set_source_readiness"
    PRODUCTION_INTEGRATION_READINESS = "production_integration_readiness"
    DEPLOYMENT_PUBLICATION_READINESS = "deployment_publication_readiness"


REQUIRED_LAUNCH_HANDOFF_GATES: tuple[LaunchHandoffGate, ...] = (
    LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
    LaunchHandoffGate.RIGHTS_APPROVAL,
    LaunchHandoffGate.AFFILIATE_ACCEPTANCE,
    LaunchHandoffGate.QUALIFIED_DEMAND,
    LaunchHandoffGate.SHADOW_OPERATIONS,
    LaunchHandoffGate.GOLD_SET_SOURCE_READINESS,
    LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS,
    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS,
)

_GATE_INDEX = {gate: index for index, gate in enumerate(REQUIRED_LAUNCH_HANDOFF_GATES)}

_EXPECTED_SIGNING_ROLE: dict[LaunchHandoffGate, SigningRole] = {
    LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE: SigningRole.HUMAN_APPROVER,
    LaunchHandoffGate.RIGHTS_APPROVAL: SigningRole.HUMAN_APPROVER,
    LaunchHandoffGate.AFFILIATE_ACCEPTANCE: SigningRole.HUMAN_APPROVER,
    LaunchHandoffGate.QUALIFIED_DEMAND: SigningRole.TCO_QA,
    LaunchHandoffGate.SHADOW_OPERATIONS: SigningRole.TCO_QA,
    LaunchHandoffGate.GOLD_SET_SOURCE_READINESS: SigningRole.TCO_QA,
    LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS: SigningRole.TCO_QA,
    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS: SigningRole.HUMAN_APPROVER,
}

_LIVE_GATES = {
    LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS,
    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS,
}


class LaunchHandoffProvenance(str, Enum):
    VERIFIED_RECORD = "verified_record"
    SYNTHETIC_CONTRACT = "synthetic_contract"


class LaunchArtifactComponentKind(str, Enum):
    P18_REPOSITORY_ACCEPTANCE_AUTHORITY_BUNDLE = (
        "p18_repository_acceptance_authority_bundle"
    )
    RIGHTS_DECISION_RECORD = "rights_decision_record"
    AFFILIATE_DECISION_RECORD = "affiliate_decision_record"
    QUALIFIED_DEMAND_RECORD = "qualified_demand_record"
    SHADOW_OPERATIONS_RECORD = "shadow_operations_record"
    GOLD_SOURCE_READINESS_RECORD = "gold_source_readiness_record"
    P15_READINESS_REPORT = "p15_readiness_report"
    P15_TCO_QA_ATTESTATION = "p15_tco_qa_attestation"
    P10_LOCAL_ASSURANCE_REPORT = "p10_local_assurance_report"
    DEPLOYMENT_READINESS_RECORD = "deployment_readiness_record"
    PUBLICATION_READINESS_RECORD = "publication_readiness_record"


_EXPECTED_COMPONENTS: dict[
    LaunchHandoffGate, tuple[LaunchArtifactComponentKind, ...]
] = {
    LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE: (
        LaunchArtifactComponentKind.P18_REPOSITORY_ACCEPTANCE_AUTHORITY_BUNDLE,
    ),
    LaunchHandoffGate.RIGHTS_APPROVAL: (
        LaunchArtifactComponentKind.RIGHTS_DECISION_RECORD,
    ),
    LaunchHandoffGate.AFFILIATE_ACCEPTANCE: (
        LaunchArtifactComponentKind.AFFILIATE_DECISION_RECORD,
    ),
    LaunchHandoffGate.QUALIFIED_DEMAND: (
        LaunchArtifactComponentKind.QUALIFIED_DEMAND_RECORD,
    ),
    LaunchHandoffGate.SHADOW_OPERATIONS: (
        LaunchArtifactComponentKind.SHADOW_OPERATIONS_RECORD,
    ),
    LaunchHandoffGate.GOLD_SET_SOURCE_READINESS: (
        LaunchArtifactComponentKind.GOLD_SOURCE_READINESS_RECORD,
    ),
    LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS: (
        LaunchArtifactComponentKind.P15_READINESS_REPORT,
        LaunchArtifactComponentKind.P15_TCO_QA_ATTESTATION,
    ),
    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS: (
        LaunchArtifactComponentKind.P10_LOCAL_ASSURANCE_REPORT,
        LaunchArtifactComponentKind.DEPLOYMENT_READINESS_RECORD,
        LaunchArtifactComponentKind.PUBLICATION_READINESS_RECORD,
    ),
}


class LaunchArtifactComponent(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    kind: LaunchArtifactComponentKind
    artifact_sha256: Sha256


class LaunchHandoffTrustStore(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    human_approver: Ed25519VerificationKey
    tco_qa: Ed25519VerificationKey

    @model_validator(mode="after")
    def validate_roles_and_separation(self) -> Self:
        if self.human_approver.role is not SigningRole.HUMAN_APPROVER:
            raise ValueError("human_approver key must have the Human Approver role")
        if self.tco_qa.role is not SigningRole.TCO_QA:
            raise ValueError("tco_qa key must have the TCO/QA role")
        if self.human_approver.key_id_sha256 == self.tco_qa.key_id_sha256:
            raise ValueError("Human Approver and TCO/QA keys must be distinct")
        return self


class LaunchHandoffPolicy(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    policy_id: Slug
    trust_store_sha256: Sha256
    maximum_plan_ttl_seconds: int = Field(ge=1, le=31_536_000)
    maximum_evidence_ttl_seconds: int = Field(ge=1, le=31_536_000)
    maximum_live_gate_ttl_seconds: int = Field(ge=1, le=86_400)
    maximum_report_ttl_seconds: int = Field(ge=1, le=86_400)


class LaunchHandoffRequirement(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    gate: LaunchHandoffGate
    evidence_identity_sha256: Sha256
    artifact_components: tuple[LaunchArtifactComponent, ...] = Field(
        min_length=1, max_length=5
    )
    expected_artifact_sha256: Sha256
    subject_sha256: Sha256
    signer_role: SigningRole
    signer_key_id_sha256: Sha256
    command_sha256: Sha256
    tool_name: Slug
    tool_version: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$",
    )

    @model_validator(mode="after")
    def validate_gate_role(self) -> Self:
        if self.signer_role is not _EXPECTED_SIGNING_ROLE[self.gate]:
            raise ValueError("signer role does not match the fixed handoff gate role")
        kinds = tuple(component.kind for component in self.artifact_components)
        if kinds != _EXPECTED_COMPONENTS[self.gate]:
            raise ValueError("artifact components do not match the fixed gate contract")
        if self.expected_artifact_sha256 != hash_launch_artifact_components(
            self.artifact_components
        ):
            raise ValueError("expected_artifact_sha256 does not match components")
        return self


class LaunchHandoffPlan(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    plan_id: Slug
    handoff_policy_sha256: Sha256
    trust_store_sha256: Sha256
    repository_acceptance_authority_pins_sha256: Sha256
    launch_semantic_authority_pins_sha256: Sha256
    candidate_manifest_sha256: Sha256
    property_record_sha256: Sha256
    environment_identity_sha256: Sha256
    release_identity_sha256: Sha256
    release_manifest_sha256: Sha256
    release_artifact_sha256: Sha256
    deployment_candidate_sha256: Sha256
    provider_target_sha256: Sha256
    expected_pre_state_sha256: Sha256
    expected_post_state_sha256: Sha256
    rollback_state_sha256: Sha256
    legal_pages_sha256: Sha256
    affiliate_disclosure_sha256: Sha256
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    requirements: tuple[LaunchHandoffRequirement, ...] = Field(min_length=8, max_length=8)
    plan_sha256: Sha256

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "launch handoff plan timestamp")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if not (self.issued_at <= self.not_before < self.expires_at):
            raise ValueError("plan times must satisfy issued_at <= not_before < expires_at")
        gates = tuple(item.gate for item in self.requirements)
        if gates != REQUIRED_LAUNCH_HANDOFF_GATES:
            raise ValueError("plan requirements must contain the exact ordered P16 gates")
        if len({item.evidence_identity_sha256 for item in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("evidence identities must be unique")
        if self.plan_sha256 != hash_launch_handoff_plan(self):
            raise ValueError("plan_sha256 does not match canonical plan")
        return self


class LaunchGateReceipt(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    receipt_id: Slug
    gate: LaunchHandoffGate
    gate_ordinal: int = Field(ge=1, le=8)
    predecessor_receipt_sha256: Sha256
    plan_sha256: Sha256
    handoff_policy_sha256: Sha256
    requirement_sha256: Sha256
    evidence_identity_sha256: Sha256
    candidate_manifest_sha256: Sha256
    property_record_sha256: Sha256
    environment_identity_sha256: Sha256
    deployment_candidate_sha256: Sha256
    artifact_sha256: Sha256
    subject_sha256: Sha256
    command_sha256: Sha256
    tool_name: Slug
    tool_version: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$",
    )
    provenance: LaunchHandoffProvenance
    observed_at: datetime
    expires_at: datetime
    reviewer_issuer: Slug
    reviewer_key_id_sha256: Sha256
    reviewer_role: SigningRole
    receipt_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "launch gate receipt timestamp")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("receipt expires_at must be later than observed_at")
        if self.reviewer_role is not _EXPECTED_SIGNING_ROLE[self.gate]:
            raise ValueError("reviewer role does not match the fixed handoff gate role")
        if self.gate_ordinal != _GATE_INDEX[self.gate] + 1:
            raise ValueError("gate_ordinal does not match the fixed handoff gate order")
        if self.gate_ordinal == 1 and self.predecessor_receipt_sha256 != "0" * 64:
            raise ValueError("the first receipt must use the zero predecessor")
        if self.gate_ordinal > 1 and self.predecessor_receipt_sha256 == "0" * 64:
            raise ValueError("a later receipt must bind its predecessor")
        if self.receipt_sha256 != hash_launch_gate_receipt(self):
            raise ValueError("receipt_sha256 does not match canonical receipt")
        return self


class LaunchHandoffBundle(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    plan_sha256: Sha256
    handoff_policy_sha256: Sha256
    repository_acceptance: RepositoryAcceptanceAuthorityBundle | None = None
    launch_semantics: LaunchSemanticPacket | None = None
    receipts: tuple[LaunchGateReceipt, ...] = Field(max_length=16)
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        order = tuple(
            (
                _GATE_INDEX[item.gate],
                item.receipt_id,
                item.receipt_sha256,
                item.signature_base64url,
            )
            for item in self.receipts
        )
        if order != tuple(sorted(order)):
            raise ValueError("launch gate receipts must be in canonical order")
        binding = (self.plan_sha256, self.handoff_policy_sha256)
        if any(
            (item.plan_sha256, item.handoff_policy_sha256) != binding
            for item in self.receipts
        ):
            raise ValueError("every receipt must match the bundle binding")
        if self.bundle_sha256 != hash_launch_handoff_bundle(self):
            raise ValueError("bundle_sha256 does not match canonical bundle")
        return self


class LaunchHandoffDecision(str, Enum):
    READY_FOR_FINAL_HUMAN_REVIEW = "ready_for_final_human_review"
    STOP = "stop"


class LaunchHandoffReason(str, Enum):
    CONFLICTING_RECEIPT = "conflicting_receipt"
    DUPLICATE_RECEIPT = "duplicate_receipt"
    MISSING_RECEIPT = "missing_receipt"
    OUT_OF_ORDER_RECEIPT = "out_of_order_receipt"
    PLAN_EXPIRED = "plan_expired"
    PLAN_FUTURE = "plan_future"
    PLAN_TTL_EXCEEDED = "plan_ttl_exceeded"
    PREREQUISITE_NOT_MET = "prerequisite_not_met"
    RECEIPT_BEFORE_PLAN = "receipt_before_plan"
    RECEIPT_EXPIRED = "receipt_expired"
    RECEIPT_FUTURE = "receipt_future"
    RECEIPT_SIGNATURE_INVALID = "receipt_signature_invalid"
    RECEIPT_TTL_EXCEEDED = "receipt_ttl_exceeded"
    REPOSITORY_ACCEPTANCE_INVALID = "repository_acceptance_invalid"
    REPOSITORY_ACCEPTANCE_MISSING = "repository_acceptance_missing"
    REQUIREMENT_MISMATCH = "requirement_mismatch"
    SYNTHETIC_RECEIPT = "synthetic_receipt"
    SEMANTIC_EVIDENCE_MISSING = "semantic_evidence_missing"
    SEMANTIC_EVIDENCE_INVALID = "semantic_evidence_invalid"
    SEMANTIC_REQUIREMENT_MISMATCH = "semantic_requirement_mismatch"
    SEMANTIC_SCOPE_MISMATCH = "semantic_scope_mismatch"
    SEMANTIC_EXPIRY_EXCEEDED = "semantic_expiry_exceeded"


class LaunchHandoffFinding(StrictModel):
    gate: LaunchHandoffGate
    reason: LaunchHandoffReason


class LaunchHandoffReport(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    decision: LaunchHandoffDecision
    evaluated_at: datetime
    plan_sha256: Sha256
    handoff_policy_sha256: Sha256
    trust_store_sha256: Sha256
    launch_authority_sha256: Sha256
    evidence_bundle_sha256: Sha256
    findings: tuple[LaunchHandoffFinding, ...]
    passed_gates: tuple[LaunchHandoffGate, ...]
    failed_gates: tuple[LaunchHandoffGate, ...]
    expires_at: datetime
    authority_effect: Literal["none"] = "none"
    permitted_use: Literal["final_human_review_input_only"] = (
        "final_human_review_input_only"
    )
    does_not_authorize_external_action: Literal[True] = True
    authorizes_external_mutation: Literal[False] = False
    requires_execution_boundary_revalidation: Literal[True] = True
    report_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "launch handoff report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        finding_keys = tuple(
            (_GATE_INDEX[item.gate], item.reason.value) for item in self.findings
        )
        if finding_keys != tuple(sorted(set(finding_keys))):
            raise ValueError("handoff findings must be canonical and unique")
        if self.passed_gates != tuple(
            gate for gate in REQUIRED_LAUNCH_HANDOFF_GATES if gate in self.passed_gates
        ) or len(set(self.passed_gates)) != len(self.passed_gates):
            raise ValueError("passed gates must be canonical and unique")
        if self.failed_gates != tuple(
            gate for gate in REQUIRED_LAUNCH_HANDOFF_GATES if gate in self.failed_gates
        ) or len(set(self.failed_gates)) != len(self.failed_gates):
            raise ValueError("failed gates must be canonical and unique")
        if set(self.passed_gates) | set(self.failed_gates) != set(
            REQUIRED_LAUNCH_HANDOFF_GATES
        ):
            raise ValueError("report must classify every P16 gate")
        if set(self.passed_gates) & set(self.failed_gates):
            raise ValueError("a P16 gate cannot both pass and fail")
        expected = (
            LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
            if not self.failed_gates and not self.findings
            else LaunchHandoffDecision.STOP
        )
        if self.decision is not expected:
            raise ValueError("handoff decision does not match findings")
        if (
            self.decision is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
            and self.expires_at <= self.evaluated_at
        ):
            raise ValueError("ready report must expire after evaluation")
        if self.report_sha256 != hash_launch_handoff_report(self):
            raise ValueError("report_sha256 does not match canonical report")
        return self


def hash_launch_handoff_trust_store(value: LaunchHandoffTrustStore) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_launch_artifact_components(
    value: tuple[LaunchArtifactComponent, ...],
) -> str:
    return _canonical_sha256(
        [component.model_dump(mode="json") for component in value]
    )


def hash_launch_handoff_policy(value: LaunchHandoffPolicy) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_launch_handoff_requirement(value: LaunchHandoffRequirement) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_launch_handoff_plan(value: LaunchHandoffPlan) -> str:
    return _hash_model(value, excluded={"plan_sha256"})


def hash_launch_handoff_authority(
    plan: LaunchHandoffPlan,
    policy: LaunchHandoffPolicy,
    trust_store: LaunchHandoffTrustStore,
) -> str:
    return _canonical_sha256(
        {
            "plan_sha256": plan.plan_sha256,
            "policy_sha256": hash_launch_handoff_policy(policy),
            "trust_store_sha256": hash_launch_handoff_trust_store(
                trust_store
            ),
        }
    )


def hash_launch_gate_receipt(value: LaunchGateReceipt) -> str:
    return _hash_model(value, excluded={"receipt_sha256", "signature_base64url"})


def hash_launch_handoff_bundle(value: LaunchHandoffBundle) -> str:
    return _hash_model(value, excluded={"bundle_sha256"})


def hash_launch_handoff_report(value: LaunchHandoffReport) -> str:
    return _hash_model(value, excluded={"report_sha256"})


def sign_launch_gate_receipt(
    plan: LaunchHandoffPlan,
    policy: LaunchHandoffPolicy,
    requirement: LaunchHandoffRequirement,
    private_key: Ed25519PrivateKey,
    *,
    predecessor_receipt: LaunchGateReceipt | None,
    receipt_id: str,
    reviewer_issuer: str,
    provenance: LaunchHandoffProvenance,
    observed_at: datetime,
    expires_at: datetime,
) -> LaunchGateReceipt:
    validated_plan = _copy(plan, LaunchHandoffPlan)
    validated_policy = _copy(policy, LaunchHandoffPolicy)
    validated_requirement = _copy(requirement, LaunchHandoffRequirement)
    if validated_plan.handoff_policy_sha256 != hash_launch_handoff_policy(
        validated_policy
    ):
        raise LaunchHandoffInputError("plan does not bind the supplied policy")
    if validated_requirement not in validated_plan.requirements:
        raise LaunchHandoffInputError("requirement is not part of the exact plan")
    key_id = _private_key_id(private_key)
    gate_index = _GATE_INDEX[validated_requirement.gate]
    if gate_index == 0:
        if predecessor_receipt is not None:
            raise LaunchHandoffInputError("the first gate cannot have a predecessor")
        predecessor_hash = "0" * 64
    else:
        if predecessor_receipt is None:
            raise LaunchHandoffInputError("a later gate requires its exact predecessor")
        predecessor = _copy(predecessor_receipt, LaunchGateReceipt)
        if (
            predecessor.gate is not REQUIRED_LAUNCH_HANDOFF_GATES[gate_index - 1]
            or predecessor.plan_sha256 != validated_plan.plan_sha256
            or predecessor.handoff_policy_sha256
            != validated_plan.handoff_policy_sha256
        ):
            raise LaunchHandoffInputError("predecessor is not the exact preceding gate")
        predecessor_hash = predecessor.receipt_sha256
    values: dict[str, Any] = {
        "schema_version": "3.0",
        "receipt_id": receipt_id,
        "gate": validated_requirement.gate,
        "gate_ordinal": gate_index + 1,
        "predecessor_receipt_sha256": predecessor_hash,
        "plan_sha256": validated_plan.plan_sha256,
        "handoff_policy_sha256": validated_plan.handoff_policy_sha256,
        "requirement_sha256": hash_launch_handoff_requirement(validated_requirement),
        "evidence_identity_sha256": validated_requirement.evidence_identity_sha256,
        "candidate_manifest_sha256": validated_plan.candidate_manifest_sha256,
        "property_record_sha256": validated_plan.property_record_sha256,
        "environment_identity_sha256": validated_plan.environment_identity_sha256,
        "deployment_candidate_sha256": validated_plan.deployment_candidate_sha256,
        "artifact_sha256": validated_requirement.expected_artifact_sha256,
        "subject_sha256": validated_requirement.subject_sha256,
        "command_sha256": validated_requirement.command_sha256,
        "tool_name": validated_requirement.tool_name,
        "tool_version": validated_requirement.tool_version,
        "provenance": provenance,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "reviewer_issuer": reviewer_issuer,
        "reviewer_key_id_sha256": key_id,
        "reviewer_role": validated_requirement.signer_role,
    }
    provisional = LaunchGateReceipt.model_construct(
        **values, receipt_sha256="0" * 64, signature_base64url="A" * 86
    )
    receipt_hash = hash_launch_gate_receipt(provisional)
    return LaunchGateReceipt(
        **values,
        receipt_sha256=receipt_hash,
        signature_base64url=_sign(private_key, receipt_hash),
    )


def build_launch_handoff_bundle(
    plan: LaunchHandoffPlan,
    policy: LaunchHandoffPolicy,
    receipts: tuple[LaunchGateReceipt, ...],
    *,
    repository_acceptance: RepositoryAcceptanceAuthorityBundle | None = None,
    launch_semantics: LaunchSemanticPacket | None = None,
) -> LaunchHandoffBundle:
    validated_plan = _copy(plan, LaunchHandoffPlan)
    validated_policy = _copy(policy, LaunchHandoffPolicy)
    if validated_plan.handoff_policy_sha256 != hash_launch_handoff_policy(
        validated_policy
    ):
        raise LaunchHandoffInputError("plan does not bind the supplied policy")
    ordered = tuple(
        sorted(
            (_copy(item, LaunchGateReceipt) for item in receipts),
            key=lambda item: (
                _GATE_INDEX[item.gate],
                item.receipt_id,
                item.receipt_sha256,
                item.signature_base64url,
            ),
        )
    )
    values = {
        "schema_version": "3.0",
        "plan_sha256": validated_plan.plan_sha256,
        "handoff_policy_sha256": validated_plan.handoff_policy_sha256,
        "repository_acceptance": (
            None
            if repository_acceptance is None
            else _copy(
                repository_acceptance, RepositoryAcceptanceAuthorityBundle
            )
        ),
        "launch_semantics": (
            None
            if launch_semantics is None
            else _copy(launch_semantics, LaunchSemanticPacket)
        ),
        "receipts": ordered,
    }
    provisional = LaunchHandoffBundle.model_construct(
        **values, bundle_sha256="0" * 64
    )
    return LaunchHandoffBundle(
        **values, bundle_sha256=hash_launch_handoff_bundle(provisional)
    )


def evaluate_launch_handoff(
    bundle: LaunchHandoffBundle,
    plan: LaunchHandoffPlan,
    policy: LaunchHandoffPolicy,
    trust_store: LaunchHandoffTrustStore,
    *,
    at: datetime,
    expected_repository_acceptance_authority_pins_sha256: str,
    expected_launch_handoff_authority_sha256: str,
    launch_semantic_authority_pins: LaunchSemanticAuthorityPins | None = None,
    expected_launch_semantic_authority_pins_sha256: str | None = None,
) -> LaunchHandoffReport:
    _require_utc(at, "launch handoff evaluation timestamp")
    validated_bundle = _copy(bundle, LaunchHandoffBundle)
    validated_plan = _copy(plan, LaunchHandoffPlan)
    validated_policy = _copy(policy, LaunchHandoffPolicy)
    validated_trust = _copy(trust_store, LaunchHandoffTrustStore)
    trust_hash = hash_launch_handoff_trust_store(validated_trust)
    policy_hash = hash_launch_handoff_policy(validated_policy)
    launch_authority_hash = hash_launch_handoff_authority(
        validated_plan, validated_policy, validated_trust
    )
    if not _is_sha256(expected_repository_acceptance_authority_pins_sha256):
        raise LaunchHandoffInputError(
            "expected repository acceptance authority root is invalid"
        )
    if not _is_sha256(expected_launch_handoff_authority_sha256):
        raise LaunchHandoffInputError(
            "expected launch handoff authority root is invalid"
        )
    if expected_launch_semantic_authority_pins_sha256 is not None and not _is_sha256(
        expected_launch_semantic_authority_pins_sha256
    ):
        raise LaunchHandoffInputError(
            "expected launch semantic authority root is invalid"
        )
    if expected_launch_handoff_authority_sha256 != launch_authority_hash:
        raise LaunchHandoffInputError(
            "launch plan, policy, and trust store do not match the consumer root"
        )
    if validated_policy.trust_store_sha256 != trust_hash:
        raise LaunchHandoffInputError("policy trust-store pin mismatch")
    if (
        validated_plan.handoff_policy_sha256 != policy_hash
        or validated_plan.trust_store_sha256 != trust_hash
        or validated_bundle.plan_sha256 != validated_plan.plan_sha256
        or validated_bundle.handoff_policy_sha256 != policy_hash
        or validated_plan.repository_acceptance_authority_pins_sha256
        != expected_repository_acceptance_authority_pins_sha256
    ):
        raise LaunchHandoffInputError(
            "plan, policy, trust store, or bundle binding mismatch"
        )
    if launch_semantic_authority_pins is not None:
        validated_semantic_pins = _copy(
            launch_semantic_authority_pins, LaunchSemanticAuthorityPins
        )
        if (
            expected_launch_semantic_authority_pins_sha256 is None
            or hash_launch_semantic_authority_pins(validated_semantic_pins)
            != expected_launch_semantic_authority_pins_sha256
            or validated_plan.launch_semantic_authority_pins_sha256
            != expected_launch_semantic_authority_pins_sha256
        ):
            raise LaunchHandoffInputError(
                "launch semantic authority pin mismatch"
            )
    else:
        validated_semantic_pins = None

    findings: set[tuple[LaunchHandoffGate, LaunchHandoffReason]] = set()
    failed: set[LaunchHandoffGate] = set()
    expiries: list[datetime] = []
    by_gate: dict[LaunchHandoffGate, list[LaunchGateReceipt]] = {
        gate: [] for gate in REQUIRED_LAUNCH_HANDOFF_GATES
    }
    for receipt in validated_bundle.receipts:
        by_gate[receipt.gate].append(receipt)
    duplicate_ids = {
        receipt.receipt_id
        for receipt in validated_bundle.receipts
        if sum(
            other.receipt_id == receipt.receipt_id
            for other in validated_bundle.receipts
        )
        > 1
    }
    requirements = {item.gate: item for item in validated_plan.requirements}

    semantic_by_gate: dict[str, Any] = {}
    semantic_packet = validated_bundle.launch_semantics
    semantic_gates = REQUIRED_LAUNCH_HANDOFF_GATES[1:]
    if semantic_packet is None or validated_semantic_pins is None:
        for gate in semantic_gates:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.SEMANTIC_EVIDENCE_MISSING))
    else:
        semantic_scope = semantic_packet.scope
        if (
            semantic_scope.candidate_manifest_sha256
            != validated_plan.candidate_manifest_sha256
            or semantic_scope.property_record_sha256
            != validated_plan.property_record_sha256
            or semantic_scope.environment_identity_sha256
            != validated_plan.environment_identity_sha256
            or semantic_scope.release_identity_sha256
            != validated_plan.release_identity_sha256
            or semantic_scope.release_manifest_sha256
            != validated_plan.release_manifest_sha256
            or semantic_scope.release_artifact_sha256
            != validated_plan.release_artifact_sha256
            or semantic_scope.deployment_candidate_sha256
            != validated_plan.deployment_candidate_sha256
            or semantic_scope.provider_target_sha256
            != validated_plan.provider_target_sha256
            or semantic_scope.expected_pre_state_sha256
            != validated_plan.expected_pre_state_sha256
            or semantic_scope.expected_post_state_sha256
            != validated_plan.expected_post_state_sha256
            or semantic_scope.rollback_state_sha256
            != validated_plan.rollback_state_sha256
            or semantic_scope.legal_pages_sha256
            != validated_plan.legal_pages_sha256
            or semantic_scope.affiliate_disclosure_sha256
            != validated_plan.affiliate_disclosure_sha256
        ):
            for gate in semantic_gates:
                failed.add(gate)
                findings.add((gate, LaunchHandoffReason.SEMANTIC_SCOPE_MISMATCH))
        semantic_report = evaluate_launch_semantics(
            semantic_packet,
            validated_semantic_pins,
            at=at,
            expected_authority_pins_sha256=(
                expected_launch_semantic_authority_pins_sha256
            ),
        )
        semantic_by_gate = {
            item.gate.value: item for item in semantic_report.gates
        }
        for gate in semantic_gates:
            semantic = semantic_by_gate[gate.value]
            requirement = requirements[gate]
            semantic_components = tuple(
                (component.kind.value, component.artifact_sha256)
                for component in semantic.components
            )
            requirement_components = tuple(
                (component.kind.value, component.artifact_sha256)
                for component in requirement.artifact_components
            )
            if not semantic.passed:
                failed.add(gate)
                findings.add((gate, LaunchHandoffReason.SEMANTIC_EVIDENCE_INVALID))
            if (
                requirement_components != semantic_components
                or requirement.evidence_identity_sha256
                != semantic.evidence_identity_sha256
                or requirement.subject_sha256 != semantic.subject_sha256
            ):
                failed.add(gate)
                findings.add(
                    (gate, LaunchHandoffReason.SEMANTIC_REQUIREMENT_MISMATCH)
                )
            expiries.append(semantic.expires_at)

    local_gate = LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE
    local_requirement = requirements[local_gate]
    repository_acceptance = validated_bundle.repository_acceptance
    if repository_acceptance is None:
        failed.add(local_gate)
        findings.add(
            (local_gate, LaunchHandoffReason.REPOSITORY_ACCEPTANCE_MISSING)
        )
    else:
        repository_report = evaluate_repository_acceptance_authority_bundle(
            repository_acceptance,
            at=at,
            expected_authority_pins_sha256=(
                expected_repository_acceptance_authority_pins_sha256
            ),
        )
        local_component = local_requirement.artifact_components[0]
        local_binding_valid = (
            local_component.kind
            is LaunchArtifactComponentKind.P18_REPOSITORY_ACCEPTANCE_AUTHORITY_BUNDLE
            and local_component.artifact_sha256
            == repository_acceptance.bundle_sha256
            and local_requirement.evidence_identity_sha256
            == repository_acceptance.human_acceptance.receipt_sha256
            and local_requirement.subject_sha256
            == repository_acceptance.manifest.tree_sha256
            and validated_plan.candidate_manifest_sha256
            == repository_acceptance.manifest.manifest_sha256
            and repository_report.decision
            is RepositoryAcceptanceDecision.ACCEPTED
        )
        if not local_binding_valid:
            failed.add(local_gate)
            findings.add(
                (local_gate, LaunchHandoffReason.REPOSITORY_ACCEPTANCE_INVALID)
            )
        expiries.extend(
            _repository_acceptance_expiries(repository_acceptance)
        )

    if validated_plan.not_before > at:
        _fail_all(findings, failed, LaunchHandoffReason.PLAN_FUTURE)
    if validated_plan.expires_at <= at:
        _fail_all(findings, failed, LaunchHandoffReason.PLAN_EXPIRED)
    if validated_plan.expires_at - validated_plan.issued_at > timedelta(
        seconds=validated_policy.maximum_plan_ttl_seconds
    ):
        _fail_all(findings, failed, LaunchHandoffReason.PLAN_TTL_EXCEEDED)

    single_receipts: dict[LaunchHandoffGate, LaunchGateReceipt] = {}
    for gate in REQUIRED_LAUNCH_HANDOFF_GATES:
        receipts = by_gate[gate]
        if not receipts:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.MISSING_RECEIPT))
            continue
        if len(receipts) > 1:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.DUPLICATE_RECEIPT))
            if len({item.receipt_sha256 for item in receipts}) > 1:
                findings.add((gate, LaunchHandoffReason.CONFLICTING_RECEIPT))
            continue
        receipt = receipts[0]
        single_receipts[gate] = receipt
        requirement = requirements[gate]
        expiries.append(receipt.expires_at)
        if receipt.receipt_id in duplicate_ids:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.DUPLICATE_RECEIPT))
        if receipt.provenance is LaunchHandoffProvenance.SYNTHETIC_CONTRACT:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.SYNTHETIC_RECEIPT))
        if not _receipt_matches_requirement(receipt, requirement, validated_plan):
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.REQUIREMENT_MISMATCH))
        verification_key = _verification_key_for_gate(validated_trust, gate)
        if not _verify_receipt_signature(receipt, verification_key, requirement):
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.RECEIPT_SIGNATURE_INVALID))
        if receipt.observed_at < validated_plan.issued_at:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.RECEIPT_BEFORE_PLAN))
        if receipt.observed_at > at:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.RECEIPT_FUTURE))
        if receipt.expires_at <= at:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.RECEIPT_EXPIRED))
        if receipt.expires_at - receipt.observed_at > timedelta(
            seconds=_maximum_gate_ttl_seconds(gate, validated_policy)
        ):
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.RECEIPT_TTL_EXCEEDED))
        semantic = semantic_by_gate.get(gate.value)
        if semantic is not None and receipt.expires_at > semantic.expires_at:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.SEMANTIC_EXPIRY_EXCEEDED))

    previous_time: datetime | None = None
    previous_receipt: LaunchGateReceipt | None = None
    for gate in REQUIRED_LAUNCH_HANDOFF_GATES:
        receipt = single_receipts.get(gate)
        if receipt is None:
            previous_receipt = None
            continue
        expected_predecessor = (
            "0" * 64
            if _GATE_INDEX[gate] == 0
            else (
                previous_receipt.receipt_sha256
                if previous_receipt is not None
                else None
            )
        )
        if receipt.predecessor_receipt_sha256 != expected_predecessor:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.OUT_OF_ORDER_RECEIPT))
        if previous_time is not None and receipt.observed_at < previous_time:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.OUT_OF_ORDER_RECEIPT))
        previous_time = (
            max(previous_time, receipt.observed_at)
            if previous_time
            else receipt.observed_at
        )
        previous_receipt = receipt

    prior_failed = False
    for gate in REQUIRED_LAUNCH_HANDOFF_GATES:
        if prior_failed:
            failed.add(gate)
            findings.add((gate, LaunchHandoffReason.PREREQUISITE_NOT_MET))
        if gate in failed:
            prior_failed = True

    passed = set(REQUIRED_LAUNCH_HANDOFF_GATES) - failed
    decision = (
        LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
        if not failed and not findings
        else LaunchHandoffDecision.STOP
    )
    expires_at = (
        min(
            min(expiries),
            validated_plan.expires_at,
            at + timedelta(seconds=validated_policy.maximum_report_ttl_seconds),
        )
        if decision is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
        else at
    )
    ordered_findings = tuple(
        LaunchHandoffFinding(gate=gate, reason=reason)
        for gate, reason in sorted(
            findings, key=lambda item: (_GATE_INDEX[item[0]], item[1].value)
        )
    )
    values: dict[str, Any] = {
        "schema_version": "3.0",
        "decision": decision,
        "evaluated_at": at,
        "plan_sha256": validated_plan.plan_sha256,
        "handoff_policy_sha256": policy_hash,
        "trust_store_sha256": trust_hash,
        "launch_authority_sha256": launch_authority_hash,
        "evidence_bundle_sha256": validated_bundle.bundle_sha256,
        "findings": ordered_findings,
        "passed_gates": tuple(
            gate for gate in REQUIRED_LAUNCH_HANDOFF_GATES if gate in passed
        ),
        "failed_gates": tuple(
            gate for gate in REQUIRED_LAUNCH_HANDOFF_GATES if gate in failed
        ),
        "expires_at": expires_at,
        "authority_effect": "none",
        "permitted_use": "final_human_review_input_only",
        "does_not_authorize_external_action": True,
        "authorizes_external_mutation": False,
        "requires_execution_boundary_revalidation": True,
    }
    provisional = LaunchHandoffReport.model_construct(
        **values, report_sha256="0" * 64
    )
    return LaunchHandoffReport(
        **values, report_sha256=hash_launch_handoff_report(provisional)
    )


def _fail_all(
    findings: set[tuple[LaunchHandoffGate, LaunchHandoffReason]],
    failed: set[LaunchHandoffGate],
    reason: LaunchHandoffReason,
) -> None:
    for gate in REQUIRED_LAUNCH_HANDOFF_GATES:
        failed.add(gate)
        findings.add((gate, reason))


def _receipt_matches_requirement(
    receipt: LaunchGateReceipt,
    requirement: LaunchHandoffRequirement,
    plan: LaunchHandoffPlan,
) -> bool:
    return (
        receipt.gate is requirement.gate
        and receipt.requirement_sha256
        == hash_launch_handoff_requirement(requirement)
        and receipt.evidence_identity_sha256 == requirement.evidence_identity_sha256
        and receipt.candidate_manifest_sha256 == plan.candidate_manifest_sha256
        and receipt.property_record_sha256 == plan.property_record_sha256
        and receipt.environment_identity_sha256 == plan.environment_identity_sha256
        and receipt.deployment_candidate_sha256 == plan.deployment_candidate_sha256
        and receipt.artifact_sha256 == requirement.expected_artifact_sha256
        and receipt.subject_sha256 == requirement.subject_sha256
        and receipt.command_sha256 == requirement.command_sha256
        and receipt.tool_name == requirement.tool_name
        and receipt.tool_version == requirement.tool_version
        and receipt.reviewer_role is requirement.signer_role
        and receipt.reviewer_key_id_sha256 == requirement.signer_key_id_sha256
    )


def _verification_key_for_gate(
    trust_store: LaunchHandoffTrustStore, gate: LaunchHandoffGate
) -> Ed25519VerificationKey:
    return (
        trust_store.human_approver
        if _EXPECTED_SIGNING_ROLE[gate] is SigningRole.HUMAN_APPROVER
        else trust_store.tco_qa
    )


def _verify_receipt_signature(
    receipt: LaunchGateReceipt,
    key: Ed25519VerificationKey,
    requirement: LaunchHandoffRequirement,
) -> bool:
    if (
        receipt.reviewer_issuer != key.issuer
        or receipt.reviewer_key_id_sha256 != key.key_id_sha256
        or receipt.reviewer_role is not key.role
        or requirement.signer_key_id_sha256 != key.key_id_sha256
    ):
        return False
    try:
        key.public_key().verify(
            _decode_base64url(receipt.signature_base64url, expected_length=64),
            receipt.receipt_sha256.encode("ascii"),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _maximum_gate_ttl_seconds(
    gate: LaunchHandoffGate, policy: LaunchHandoffPolicy
) -> int:
    return (
        policy.maximum_live_gate_ttl_seconds
        if gate in _LIVE_GATES
        else policy.maximum_evidence_ttl_seconds
    )


def _repository_acceptance_expiries(
    bundle: RepositoryAcceptanceAuthorityBundle,
) -> tuple[datetime, ...]:
    attestations = (
        bundle.manifest.integration_verification,
        bundle.manifest.tco_qa_verification,
    )
    return (
        bundle.manifest.expires_at,
        bundle.human_acceptance.expires_at,
        *(fact.not_after for fact in bundle.manifest.verification.facts),
        *(
            attestation.expires_at
            for attestation in attestations
            if attestation is not None
        ),
    )


def _hash_model(model: StrictModel, *, excluded: set[str]) -> str:
    return _canonical_sha256(model.model_dump(mode="json", exclude=excluded))


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _copy(value: Any, expected_type: Any) -> Any:
    if type(value) is not expected_type:
        raise TypeError(f"expected exact {expected_type.__name__}")
    return expected_type.model_validate(value.model_dump())


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


def _private_key_id(private_key: Ed25519PrivateKey) -> str:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("signer must be an Ed25519 private key")
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(public_bytes).hexdigest()


def _sign(private_key: Ed25519PrivateKey, payload_sha256: str) -> str:
    return _encode_base64url(private_key.sign(payload_sha256.encode("ascii")))


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str, *, expected_length: int) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url encoding") from exc
    if len(decoded) != expected_length:
        raise ValueError("invalid base64url length")
    if _encode_base64url(decoded) != value:
        raise ValueError("non-canonical base64url encoding")
    return decoded
