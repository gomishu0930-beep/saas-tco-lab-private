"""Offline, signed pre-publication release-assurance boundary.

This module performs no network, filesystem, promotion, deployment, or publication
operation. Local technical assurance and public business approval are deliberately
separate decisions.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Any, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    ControlTrustStore,
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
    hash_control_trust_store,
)
from .economics import Decision
from .models import Sha256, StrictModel
from .preflight import BusinessDossier, evaluate_business_dossier
from .release import ApprovalDecision, CtaDecision, ReleaseManifest


class AssuranceInputError(ValueError):
    """Untrusted assurance input could not be revalidated."""


class AssuranceCheck(str, Enum):
    PYTHON_TESTS = "python_tests"
    WEB_LOCAL_TESTS = "web_local_tests"
    WEB_PRODUCTION_TESTS = "web_production_tests"
    SCHEMA_DETERMINISM = "schema_determinism"
    LOCK_INTEGRITY = "lock_integrity"
    SBOM_CURRENT = "sbom_current"
    SECRET_SCAN = "secret_scan"
    DEPENDENCY_AUDIT = "dependency_audit"
    THREAT_MODEL_REVIEW = "threat_model_review"
    ACCESSIBILITY = "accessibility"
    MOBILE_REFLOW = "mobile_reflow"
    SEO_POLICY = "seo_policy"
    ROLLBACK_FAULTS = "rollback_faults"


class EvidenceFactsKind(str, Enum):
    TEST_SUITE = "test_suite"
    DETERMINISM = "determinism"
    INTEGRITY = "integrity"
    SCAN = "scan"
    REVIEW = "review"
    ROUTE_ASSURANCE = "route_assurance"


REQUIRED_LOCAL_CHECKS: tuple[AssuranceCheck, ...] = tuple(
    sorted(AssuranceCheck, key=lambda item: item.value)
)


_EXPECTED_FACTS_KIND: dict[AssuranceCheck, EvidenceFactsKind] = {
    AssuranceCheck.PYTHON_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.WEB_LOCAL_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.WEB_PRODUCTION_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.ROLLBACK_FAULTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.SCHEMA_DETERMINISM: EvidenceFactsKind.DETERMINISM,
    AssuranceCheck.SBOM_CURRENT: EvidenceFactsKind.DETERMINISM,
    AssuranceCheck.LOCK_INTEGRITY: EvidenceFactsKind.INTEGRITY,
    AssuranceCheck.SECRET_SCAN: EvidenceFactsKind.SCAN,
    AssuranceCheck.DEPENDENCY_AUDIT: EvidenceFactsKind.SCAN,
    AssuranceCheck.THREAT_MODEL_REVIEW: EvidenceFactsKind.REVIEW,
    AssuranceCheck.ACCESSIBILITY: EvidenceFactsKind.ROUTE_ASSURANCE,
    AssuranceCheck.MOBILE_REFLOW: EvidenceFactsKind.ROUTE_ASSURANCE,
    AssuranceCheck.SEO_POLICY: EvidenceFactsKind.ROUTE_ASSURANCE,
}


class TestSuiteFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.TEST_SUITE] = EvidenceFactsKind.TEST_SUITE
    collected: int = Field(ge=1, le=1_000_000)
    passed: int = Field(ge=0, le=1_000_000)
    failed: int = Field(ge=0, le=1_000_000)
    skipped: int = Field(ge=0, le=1_000_000)
    exit_code: int = Field(ge=0, le=255)
    output_sha256: Sha256

    @model_validator(mode="after")
    def require_complete_count(self) -> Self:
        if self.passed + self.failed + self.skipped != self.collected:
            raise ValueError("test facts must exactly classify every collected test")
        return self

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.passed == self.collected and self.failed == 0 and self.skipped == 0


class DeterminismFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.DETERMINISM] = EvidenceFactsKind.DETERMINISM
    generated_items: int = Field(ge=1, le=1_000_000)
    first_sha256: Sha256
    second_sha256: Sha256
    committed_sha256: Sha256
    exit_code: int = Field(ge=0, le=255)

    @property
    def succeeded(self) -> bool:
        return (
            self.exit_code == 0
            and self.first_sha256 == self.second_sha256 == self.committed_sha256
        )


class IntegrityFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.INTEGRITY] = EvidenceFactsKind.INTEGRITY
    checked_items: int = Field(ge=1, le=1_000_000)
    invalid_items: int = Field(ge=0, le=1_000_000)
    drift_items: int = Field(ge=0, le=1_000_000)
    output_sha256: Sha256
    exit_code: int = Field(ge=0, le=255)

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.invalid_items == 0 and self.drift_items == 0


class ScanFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.SCAN] = EvidenceFactsKind.SCAN
    scanned_items: int = Field(ge=1, le=100_000_000)
    findings: int = Field(ge=0, le=1_000_000)
    unresolved_findings: int = Field(ge=0, le=1_000_000)
    output_sha256: Sha256
    exit_code: int = Field(ge=0, le=255)

    @model_validator(mode="after")
    def require_resolved_subset(self) -> Self:
        if self.unresolved_findings > self.findings:
            raise ValueError("unresolved findings cannot exceed all findings")
        return self

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.findings == 0 and self.unresolved_findings == 0


class ReviewFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.REVIEW] = EvidenceFactsKind.REVIEW
    requirements_total: int = Field(ge=1, le=1_000_000)
    requirements_met: int = Field(ge=0, le=1_000_000)
    release_blockers: int = Field(ge=0, le=1_000_000)
    review_artifact_sha256: Sha256
    exit_code: int = Field(ge=0, le=255)

    @property
    def succeeded(self) -> bool:
        return (
            self.exit_code == 0
            and self.requirements_met == self.requirements_total
            and self.release_blockers == 0
        )


class RouteAssuranceFacts(StrictModel):
    kind: Literal[EvidenceFactsKind.ROUTE_ASSURANCE] = EvidenceFactsKind.ROUTE_ASSURANCE
    routes_expected: Literal[5] = 5
    routes_checked: int = Field(ge=0, le=5)
    assertions_executed: int = Field(ge=1, le=1_000_000)
    violations: int = Field(ge=0, le=1_000_000)
    output_sha256: Sha256
    exit_code: int = Field(ge=0, le=255)

    @property
    def succeeded(self) -> bool:
        return (
            self.exit_code == 0
            and self.routes_checked == self.routes_expected
            and self.violations == 0
        )


AssuranceFacts = Annotated[
    TestSuiteFacts
    | DeterminismFacts
    | IntegrityFacts
    | ScanFacts
    | ReviewFacts
    | RouteAssuranceFacts,
    Field(discriminator="kind"),
]


class AssuranceRequirement(StrictModel):
    check: AssuranceCheck
    facts_kind: EvidenceFactsKind
    tool_name: str = Field(min_length=1, max_length=120)
    tool_version: str = Field(min_length=1, max_length=120)
    command_sha256: Sha256
    subject_sha256: Sha256

    @model_validator(mode="after")
    def require_check_specific_kind(self) -> Self:
        if self.facts_kind is not _EXPECTED_FACTS_KIND[self.check]:
            raise ValueError("assurance requirement facts kind does not match check")
        return self


class LocalAssuranceDecision(str, Enum):
    READY = "ready"
    STOP = "stop"


class LocalAssuranceReason(str, Enum):
    CHECK_FAILED = "check_failed"
    EVIDENCE_EXPIRED = "evidence_expired"
    EVIDENCE_FUTURE = "evidence_future"
    EVIDENCE_REQUIREMENT_MISMATCH = "evidence_requirement_mismatch"
    EVIDENCE_SIGNATURE_INVALID = "evidence_signature_invalid"
    EVIDENCE_TTL_EXCEEDED = "evidence_ttl_exceeded"


class PublicReleaseDecision(str, Enum):
    GO = "go"
    STOP = "stop"


class PublicReleaseReason(str, Enum):
    LOCAL_ASSURANCE_NOT_READY = "local_assurance_not_ready"
    LOCAL_ASSURANCE_EXPIRED = "local_assurance_expired"
    ASSURANCE_POLICY_MISMATCH = "assurance_policy_mismatch"
    RELEASE_BINDING_MISMATCH = "release_binding_mismatch"
    MANIFEST_INVALID = "manifest_invalid"
    MANIFEST_FUTURE = "manifest_future"
    MANIFEST_EXPIRED = "manifest_expired"
    CTA_NOT_APPROVED = "cta_not_approved"
    BUSINESS_DOSSIER_INVALID = "business_dossier_invalid"
    BUSINESS_NOT_GO = "business_not_go"
    RIGHTS_BINDING_MISMATCH = "rights_binding_mismatch"
    AFFILIATE_BINDING_MISMATCH = "affiliate_binding_mismatch"
    DATA_BINDING_MISMATCH = "data_binding_mismatch"
    TCO_QA_ATTESTATION_MISSING = "tco_qa_attestation_missing"
    TCO_QA_ATTESTATION_INVALID = "tco_qa_attestation_invalid"
    HUMAN_APPROVAL_MISSING = "human_approval_missing"
    HUMAN_APPROVAL_INVALID = "human_approval_invalid"
    HUMAN_DECISION_NOT_GO = "human_decision_not_go"
    HUMAN_SNAPSHOT_APPROVAL_MISMATCH = "human_snapshot_approval_mismatch"


class AssuranceAttestationScope(str, Enum):
    LOCAL_ASSURANCE_ACCEPTANCE = "local_assurance_acceptance"
    PUBLIC_RELEASE_APPROVAL = "public_release_approval"
    PUBLIC_RELEASE_AUTHORIZATION = "public_release_authorization"


class AssurancePolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    trust_store_sha256: Sha256
    tco_qa_key_id_sha256: Sha256
    human_key_id_sha256: Sha256
    assurance_runner_key_id_sha256: Sha256
    required_local_checks: tuple[AssuranceCheck, ...] = REQUIRED_LOCAL_CHECKS
    requirements: tuple[AssuranceRequirement, ...]
    maximum_evidence_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_attestation_ttl_seconds: int = Field(ge=1, le=604_800)

    @model_validator(mode="after")
    def require_exact_checks(self) -> Self:
        if self.required_local_checks != REQUIRED_LOCAL_CHECKS:
            raise ValueError("required_local_checks must be the complete canonical set")
        if tuple(item.check for item in self.requirements) != REQUIRED_LOCAL_CHECKS:
            raise ValueError("requirements must cover every check in canonical order")
        if self.tco_qa_key_id_sha256 == self.human_key_id_sha256:
            raise ValueError("TCO/QA and Human keys must be distinct")
        if self.assurance_runner_key_id_sha256 in {
            self.tco_qa_key_id_sha256,
            self.human_key_id_sha256,
        }:
            raise ValueError("assurance runner must use the separate controller key")
        return self


class ReleaseAssuranceAuthority:
    """Trusted, immutable policy and public-key bootstrap."""

    __slots__ = ("__policy", "__trust_store", "__controller_signer")

    def __init__(
        self,
        policy: AssurancePolicy,
        trust_store: ControlTrustStore,
        controller_signer: Ed25519PrivateKey,
    ) -> None:
        if type(policy) is not AssurancePolicy or type(trust_store) is not ControlTrustStore:
            raise TypeError("authority requires AssurancePolicy and ControlTrustStore")
        validated_policy = AssurancePolicy.model_validate(policy.model_dump())
        validated_trust = ControlTrustStore.model_validate(trust_store.model_dump())
        if validated_policy.trust_store_sha256 != hash_control_trust_store(validated_trust):
            raise AssuranceInputError("authority trust store does not match policy pin")
        if (
            validated_policy.tco_qa_key_id_sha256
            != validated_trust.gold_tco_qa.key_id_sha256
            or validated_policy.human_key_id_sha256
            != validated_trust.release_human.key_id_sha256
        ):
            raise AssuranceInputError("authority role keys do not match policy")
        if (
            validated_policy.assurance_runner_key_id_sha256
            != validated_trust.controller.key_id_sha256
            or not _private_key_matches(controller_signer, validated_trust.controller)
        ):
            raise AssuranceInputError("authority runner identity or controller signer is invalid")
        self.__policy = validated_policy
        self.__trust_store = validated_trust
        self.__controller_signer = controller_signer

    @property
    def policy(self) -> AssurancePolicy:
        return self.__policy

    @property
    def trust_store(self) -> ControlTrustStore:
        return self.__trust_store

    def __repr__(self) -> str:
        return (
            "ReleaseAssuranceAuthority("
            f"policy_id='{self.__policy.policy_id}', "
            f"trust_store_sha256='{self.__policy.trust_store_sha256}', "
            "controller_signer=<redacted>)"
        )

    def _sign_authorization(self, **values: Any) -> ReleaseAuthorization:
        return _build_signed_authorization(
            values,
            self.__controller_signer,
            self.__trust_store.controller,
        )

    def __getstate__(self) -> object:
        raise TypeError("ReleaseAssuranceAuthority cannot be serialized")


class ReleaseAssuranceVerifier:
    """Credential-blind local-assurance verifier with consumer-owned pins."""

    __slots__ = ("__policy", "__trust_store")

    def __init__(
        self,
        policy: AssurancePolicy,
        trust_store: ControlTrustStore,
        *,
        expected_policy_sha256: str,
        expected_trust_store_sha256: str,
    ) -> None:
        if type(policy) is not AssurancePolicy:
            raise TypeError("policy must be AssurancePolicy")
        if type(trust_store) is not ControlTrustStore:
            raise TypeError("trust_store must be ControlTrustStore")
        validated_policy = AssurancePolicy.model_validate(policy.model_dump())
        validated_trust = ControlTrustStore.model_validate(
            trust_store.model_dump()
        )
        policy_sha256 = hash_assurance_policy(validated_policy)
        trust_sha256 = hash_control_trust_store(validated_trust)
        if (
            expected_policy_sha256 != policy_sha256
            or expected_trust_store_sha256 != trust_sha256
            or validated_policy.trust_store_sha256 != trust_sha256
        ):
            raise AssuranceInputError(
                "consumer local-assurance authority pin mismatch"
            )
        self.__policy = validated_policy
        self.__trust_store = validated_trust

    def verify_local(
        self,
        bundle: AssuranceEvidenceBundle,
        report: LocalAssuranceReport,
        *,
        at: datetime,
    ) -> bool:
        _require_utc(at, "local-assurance report verification time")
        if (
            type(bundle) is not AssuranceEvidenceBundle
            or type(report) is not LocalAssuranceReport
        ):
            return False
        try:
            supplied = LocalAssuranceReport.model_validate(report.model_dump())
            expected = _evaluate_local_assurance(
                bundle,
                self.__policy,
                self.__trust_store,
                at=supplied.evaluated_at,
            )
        except (AssuranceInputError, TypeError, ValueError):
            return False
        return (
            supplied == expected
            and supplied.decision is LocalAssuranceDecision.READY
            and supplied.evaluated_at <= at < supplied.expires_at
        )


class AssuranceEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    check: AssuranceCheck
    release_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    subject_sha256: Sha256
    command_sha256: Sha256
    tool_name: str = Field(min_length=1, max_length=120)
    tool_version: str = Field(min_length=1, max_length=120)
    facts: AssuranceFacts
    observed_at: datetime
    expires_at: datetime
    runner_issuer: str = Field(min_length=1, max_length=120)
    runner_key_id_sha256: Sha256
    runner_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    evidence_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "assurance evidence timestamp")
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("assurance evidence expiry must follow observation")
        if self.facts.kind is not _EXPECTED_FACTS_KIND[self.check]:
            raise ValueError("assurance evidence facts kind does not match check")
        if self.evidence_sha256 != hash_assurance_evidence(self):
            raise ValueError("evidence_sha256 does not match canonical evidence")
        return self

    @property
    def passed(self) -> bool:
        return self.facts.succeeded


class AssuranceEvidenceBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    release_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    evidence: tuple[AssuranceEvidence, ...]
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        expected_order = tuple(item.value for item in REQUIRED_LOCAL_CHECKS)
        actual_order = tuple(item.check.value for item in self.evidence)
        if actual_order != expected_order:
            raise ValueError("bundle must contain every required check in canonical order")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence IDs must be unique")
        binding = (
            self.release_id,
            self.manifest_sha256,
            self.artifact_sha256,
            self.assurance_policy_sha256,
        )
        if any(
            (
                item.release_id,
                item.manifest_sha256,
                item.artifact_sha256,
                item.assurance_policy_sha256,
            )
            != binding
            for item in self.evidence
        ):
            raise ValueError("every assurance evidence item must match bundle binding")
        if self.bundle_sha256 != hash_assurance_bundle(self):
            raise ValueError("bundle_sha256 does not match canonical bundle")
        return self


class LocalAssuranceReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: LocalAssuranceDecision
    evaluated_at: datetime
    release_id: str = Field(min_length=1, max_length=120)
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    evidence_bundle_sha256: Sha256
    reasons: tuple[LocalAssuranceReason, ...]
    passed_checks: tuple[AssuranceCheck, ...]
    failed_checks: tuple[AssuranceCheck, ...]
    expires_at: datetime
    report_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "local assurance report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise ValueError("local assurance reasons must be canonical and unique")
        if self.passed_checks != tuple(sorted(set(self.passed_checks), key=lambda item: item.value)):
            raise ValueError("passed checks must be canonical and unique")
        if self.failed_checks != tuple(sorted(set(self.failed_checks), key=lambda item: item.value)):
            raise ValueError("failed checks must be canonical and unique")
        if set(self.passed_checks) | set(self.failed_checks) != set(REQUIRED_LOCAL_CHECKS):
            raise ValueError("local assurance report must classify every required check")
        if set(self.passed_checks) & set(self.failed_checks):
            raise ValueError("a check cannot pass and fail")
        expected = (
            LocalAssuranceDecision.READY
            if not self.failed_checks and not self.reasons
            else LocalAssuranceDecision.STOP
        )
        if self.decision is not expected:
            raise ValueError("local assurance decision does not match failed checks")
        if self.expires_at <= self.evaluated_at and self.decision is LocalAssuranceDecision.READY:
            raise ValueError("ready local assurance must expire after evaluation")
        if self.report_sha256 != hash_local_assurance_report(self):
            raise ValueError("report_sha256 does not match canonical local report")
        return self


class LocalAssuranceAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(min_length=1, max_length=120)
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA] = SigningRole.TCO_QA
    scope: Literal[AssuranceAttestationScope.LOCAL_ASSURANCE_ACCEPTANCE] = (
        AssuranceAttestationScope.LOCAL_ASSURANCE_ACCEPTANCE
    )
    local_report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    release_id: str = Field(min_length=1, max_length=120)
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "local assurance attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        _validate_attestation_payload(self)
        return self


class PublicReleaseApprovalAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(min_length=1, max_length=120)
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER] = SigningRole.HUMAN_APPROVER
    scope: Literal[AssuranceAttestationScope.PUBLIC_RELEASE_APPROVAL] = (
        AssuranceAttestationScope.PUBLIC_RELEASE_APPROVAL
    )
    local_report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    release_id: str = Field(min_length=1, max_length=120)
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    business_dossier_sha256: Sha256
    approved_data_snapshot_sha256s: tuple[Sha256, ...]
    decision: ApprovalDecision
    decision_record_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "public release approval timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if not self.approved_data_snapshot_sha256s:
            raise ValueError("Human approval must list approved data snapshots")
        if self.approved_data_snapshot_sha256s != tuple(
            sorted(set(self.approved_data_snapshot_sha256s))
        ):
            raise ValueError("approved data snapshots must be canonical and unique")
        _validate_attestation_payload(self)
        return self


class ReleaseAuthorization(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: str = Field(min_length=1, max_length=120)
    controller_key_id_sha256: Sha256
    signer_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    scope: Literal[AssuranceAttestationScope.PUBLIC_RELEASE_AUTHORIZATION] = (
        AssuranceAttestationScope.PUBLIC_RELEASE_AUTHORIZATION
    )
    release_assurance_core_sha256: Sha256
    assurance_policy_sha256: Sha256
    local_report_sha256: Sha256
    business_dossier_sha256: Sha256
    release_id: str = Field(min_length=1, max_length=120)
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "release authorization timestamp")
        return value

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("release authorization expiry must follow issuance")
        payload = self.model_dump(
            mode="json", exclude={"payload_sha256", "signature_base64url"}
        )
        if self.payload_sha256 != _canonical_sha256(payload):
            raise ValueError("release authorization payload hash mismatch")
        return self


class ReleaseAssuranceReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: PublicReleaseDecision
    evaluated_at: datetime
    release_id: str = Field(min_length=1, max_length=120)
    manifest_sha256: Sha256
    artifact_sha256: Sha256
    assurance_policy_sha256: Sha256
    local_report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    business_dossier_sha256: Sha256
    local_assurance_ready: bool
    public_release_ready: bool
    business_decision: Decision
    human_decision: ApprovalDecision | None
    tco_qa_attestation_payload_sha256: Sha256 | None
    human_approval_payload_sha256: Sha256 | None
    human_decision_record_sha256: Sha256 | None
    approved_data_snapshot_sha256s: tuple[Sha256, ...]
    reasons: tuple[PublicReleaseReason, ...]
    expires_at: datetime
    authorization: ReleaseAuthorization | None
    report_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "release assurance report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise ValueError("public release reasons must be canonical and unique")
        if self.approved_data_snapshot_sha256s != tuple(
            sorted(set(self.approved_data_snapshot_sha256s))
        ):
            raise ValueError("approved data snapshots must be canonical and unique")
        expected = not self.reasons
        if self.public_release_ready is not expected:
            raise ValueError("public_release_ready does not match reasons")
        if self.local_assurance_ready is False and expected:
            raise ValueError("public release cannot pass without local assurance")
        if expected and self.business_decision is not Decision.GO:
            raise ValueError("public release cannot pass without business GO")
        if expected and self.human_decision is not ApprovalDecision.GO:
            raise ValueError("public release cannot pass without Human GO")
        signed_receipts = (
            self.tco_qa_attestation_payload_sha256,
            self.human_approval_payload_sha256,
            self.human_decision_record_sha256,
        )
        if expected and any(value is None for value in signed_receipts):
            raise ValueError("public release cannot pass without signed receipt hashes")
        if expected and not self.approved_data_snapshot_sha256s:
            raise ValueError("public release cannot pass without approved snapshots")
        if expected != (self.authorization is not None):
            raise ValueError("only public GO may carry controller authorization")
        if self.decision is not (
            PublicReleaseDecision.GO if expected else PublicReleaseDecision.STOP
        ):
            raise ValueError("public release decision does not match reasons")
        if expected and self.expires_at <= self.evaluated_at:
            raise ValueError("public GO must expire after evaluation")
        if self.report_sha256 != hash_release_assurance_report(self):
            raise ValueError("report_sha256 does not match canonical public report")
        return self


def hash_assurance_policy(policy: AssurancePolicy) -> str:
    validated = AssurancePolicy.model_validate(policy.model_dump())
    return _canonical_sha256(validated.model_dump(mode="json"))


def build_assurance_evidence(
    private_key: Ed25519PrivateKey,
    *,
    runner_issuer: str,
    **values: Any,
) -> AssuranceEvidence:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    key = create_verification_key(
        private_key.public_key(), issuer=runner_issuer, role=SigningRole.CONTROLLER
    )
    payload = dict(values)
    payload.pop("evidence_sha256", None)
    payload.pop("signature_base64url", None)
    payload.setdefault("schema_version", "1.0")
    payload["runner_issuer"] = key.issuer
    payload["runner_key_id_sha256"] = key.key_id_sha256
    payload["runner_role"] = SigningRole.CONTROLLER
    payload["evidence_sha256"] = _canonical_sha256(payload)
    signature = private_key.sign(_canonical_json_bytes(payload))
    return AssuranceEvidence(
        **payload, signature_base64url=_encode_base64url(signature)
    )


def hash_assurance_evidence(evidence: AssuranceEvidence) -> str:
    return _canonical_sha256(
        evidence.model_dump(
            mode="json", exclude={"evidence_sha256", "signature_base64url"}
        )
    )


def build_assurance_bundle(
    *,
    release_id: str,
    manifest_sha256: str,
    artifact_sha256: str,
    assurance_policy_sha256: str,
    evidence: tuple[AssuranceEvidence, ...],
) -> AssuranceEvidenceBundle:
    ordered = tuple(sorted(evidence, key=lambda item: item.check.value))
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "release_id": release_id,
        "manifest_sha256": manifest_sha256,
        "artifact_sha256": artifact_sha256,
        "assurance_policy_sha256": assurance_policy_sha256,
        "evidence": ordered,
    }
    provisional = AssuranceEvidenceBundle.model_construct(**payload, bundle_sha256="0" * 64)
    return AssuranceEvidenceBundle(**payload, bundle_sha256=hash_assurance_bundle(provisional))


def hash_assurance_bundle(bundle: AssuranceEvidenceBundle) -> str:
    return _canonical_sha256(
        bundle.model_dump(mode="json", exclude={"bundle_sha256"})
    )


def evaluate_local_assurance(
    bundle: AssuranceEvidenceBundle,
    authority: ReleaseAssuranceAuthority,
    *,
    at: datetime,
) -> LocalAssuranceReport:
    if type(authority) is not ReleaseAssuranceAuthority:
        raise TypeError("authority must be ReleaseAssuranceAuthority")
    return _evaluate_local_assurance(
        bundle,
        authority.policy,
        authority.trust_store,
        at=at,
    )


def _evaluate_local_assurance(
    bundle: AssuranceEvidenceBundle,
    policy: AssurancePolicy,
    trust_store: ControlTrustStore,
    *,
    at: datetime,
) -> LocalAssuranceReport:
    _require_utc(at, "local assurance evaluation time")
    if type(bundle) is not AssuranceEvidenceBundle:
        raise TypeError("bundle must be AssuranceEvidenceBundle")
    if type(policy) is not AssurancePolicy or type(trust_store) is not ControlTrustStore:
        raise TypeError("local assurance verifier requires policy and trust store")
    try:
        validated = AssuranceEvidenceBundle.model_validate(bundle.model_dump())
        validated_policy = AssurancePolicy.model_validate(policy.model_dump())
        validated_trust = ControlTrustStore.model_validate(
            trust_store.model_dump()
        )
    except (TypeError, ValueError) as exc:
        raise AssuranceInputError("assurance bundle is invalid") from exc
    policy_hash = hash_assurance_policy(validated_policy)
    if (
        validated.assurance_policy_sha256 != policy_hash
        or validated_policy.trust_store_sha256
        != hash_control_trust_store(validated_trust)
    ):
        raise AssuranceInputError("assurance bundle policy binding is invalid")

    failed: set[AssuranceCheck] = set()
    reasons: set[LocalAssuranceReason] = set()
    requirements = {item.check: item for item in validated_policy.requirements}
    for item in validated.evidence:
        requirement = requirements[item.check]
        if (
            item.tool_name != requirement.tool_name
            or item.tool_version != requirement.tool_version
            or item.command_sha256 != requirement.command_sha256
            or item.subject_sha256 != requirement.subject_sha256
            or item.facts.kind is not requirement.facts_kind
        ):
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.EVIDENCE_REQUIREMENT_MISMATCH)
        if not _verify_evidence_signature(
            item, validated_trust.controller
        ):
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.EVIDENCE_SIGNATURE_INVALID)
        if not item.passed:
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.CHECK_FAILED)
        if item.observed_at > at:
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.EVIDENCE_FUTURE)
        if at >= item.expires_at:
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.EVIDENCE_EXPIRED)
        if (
            item.expires_at - item.observed_at
            > timedelta(seconds=validated_policy.maximum_evidence_ttl_seconds)
        ):
            failed.add(item.check)
            reasons.add(LocalAssuranceReason.EVIDENCE_TTL_EXCEEDED)
    passed = set(REQUIRED_LOCAL_CHECKS) - failed
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "decision": (
            LocalAssuranceDecision.READY if not failed else LocalAssuranceDecision.STOP
        ),
        "evaluated_at": at,
        "release_id": validated.release_id,
        "manifest_sha256": validated.manifest_sha256,
        "artifact_sha256": validated.artifact_sha256,
        "assurance_policy_sha256": validated.assurance_policy_sha256,
        "evidence_bundle_sha256": validated.bundle_sha256,
        "reasons": tuple(sorted(reasons, key=lambda item: item.value)),
        "passed_checks": tuple(sorted(passed, key=lambda item: item.value)),
        "failed_checks": tuple(sorted(failed, key=lambda item: item.value)),
        "expires_at": min(item.expires_at for item in validated.evidence),
    }
    provisional = LocalAssuranceReport.model_construct(**values, report_sha256="0" * 64)
    return LocalAssuranceReport(
        **values, report_sha256=hash_local_assurance_report(provisional)
    )


def hash_local_assurance_report(report: LocalAssuranceReport) -> str:
    return _canonical_sha256(report.model_dump(mode="json", exclude={"report_sha256"}))


def sign_local_assurance_report(
    report: LocalAssuranceReport,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> LocalAssuranceAttestation:
    validated = _validate_local_report(report)
    return _build_signed_attestation(
        LocalAssuranceAttestation,
        {
            "issuer": issuer,
            "signer_role": SigningRole.TCO_QA,
            "scope": AssuranceAttestationScope.LOCAL_ASSURANCE_ACCEPTANCE,
            **_report_binding(validated),
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
        role=SigningRole.TCO_QA,
    )


def sign_public_release_approval(
    report: LocalAssuranceReport,
    dossier: BusinessDossier,
    manifest: ReleaseManifest,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    decision: ApprovalDecision,
    decision_record_sha256: str,
    approved_data_snapshot_sha256s: tuple[str, ...],
    issued_at: datetime,
    expires_at: datetime,
) -> PublicReleaseApprovalAttestation:
    validated = _validate_local_report(report)
    validated_dossier = _validate_business_dossier(dossier)
    validated_manifest = _copy_manifest(manifest)
    approved_snapshots = tuple(sorted(set(approved_data_snapshot_sha256s)))
    if (
        approved_snapshots != approved_data_snapshot_sha256s
        or approved_snapshots != tuple(sorted(validated_manifest.data_snapshot_sha256s))
    ):
        raise ValueError("Human-approved snapshots must exactly match the manifest")
    if (
        validated.release_id,
        validated.manifest_sha256,
        validated.artifact_sha256,
    ) != (
        validated_manifest.release_id,
        validated_manifest.manifest_sha256,
        validated_manifest.artifact_sha256,
    ):
        raise ValueError("Human approval manifest does not match local report")
    return _build_signed_attestation(
        PublicReleaseApprovalAttestation,
        {
            "issuer": issuer,
            "signer_role": SigningRole.HUMAN_APPROVER,
            "scope": AssuranceAttestationScope.PUBLIC_RELEASE_APPROVAL,
            **_report_binding(validated),
            "business_dossier_sha256": hash_business_dossier(validated_dossier),
            "approved_data_snapshot_sha256s": approved_snapshots,
            "decision": decision,
            "decision_record_sha256": decision_record_sha256,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
        role=SigningRole.HUMAN_APPROVER,
    )


def evaluate_public_release_assurance(
    local_report: LocalAssuranceReport,
    dossier: BusinessDossier,
    manifest: ReleaseManifest,
    authority: ReleaseAssuranceAuthority,
    *,
    tco_qa_attestation: LocalAssuranceAttestation | None,
    human_approval: PublicReleaseApprovalAttestation | None,
    at: datetime,
) -> ReleaseAssuranceReport:
    _require_utc(at, "public release evaluation time")
    if type(authority) is not ReleaseAssuranceAuthority:
        raise TypeError("authority must be ReleaseAssuranceAuthority")
    validated_local = _validate_local_report(local_report)
    reasons: set[PublicReleaseReason] = set()
    expiries = [validated_local.expires_at]
    policy_matches = (
        validated_local.assurance_policy_sha256
        == hash_assurance_policy(authority.policy)
    )
    if not policy_matches:
        reasons.add(PublicReleaseReason.ASSURANCE_POLICY_MISMATCH)

    local_ready = (
        validated_local.decision is LocalAssuranceDecision.READY
        and validated_local.evaluated_at <= at < validated_local.expires_at
        and policy_matches
    )
    if validated_local.decision is not LocalAssuranceDecision.READY:
        reasons.add(PublicReleaseReason.LOCAL_ASSURANCE_NOT_READY)
    elif not (
        validated_local.evaluated_at <= at < validated_local.expires_at
    ):
        reasons.add(PublicReleaseReason.LOCAL_ASSURANCE_EXPIRED)

    valid_manifest: ReleaseManifest | None = None
    try:
        valid_manifest = _copy_manifest(manifest)
    except (TypeError, ValueError):
        reasons.add(PublicReleaseReason.MANIFEST_INVALID)
    if valid_manifest is not None:
        binding = (
            valid_manifest.release_id,
            valid_manifest.manifest_sha256,
            valid_manifest.artifact_sha256,
        )
        if binding != (
            validated_local.release_id,
            validated_local.manifest_sha256,
            validated_local.artifact_sha256,
        ):
            reasons.add(PublicReleaseReason.RELEASE_BINDING_MISMATCH)
        if valid_manifest.prepared_at > at:
            reasons.add(PublicReleaseReason.MANIFEST_FUTURE)
        if at >= valid_manifest.shortest_expiry:
            reasons.add(PublicReleaseReason.MANIFEST_EXPIRED)
        if valid_manifest.cta.decision is not CtaDecision.APPROVED:
            reasons.add(PublicReleaseReason.CTA_NOT_APPROVED)
        expiries.append(valid_manifest.shortest_expiry)

    business_decision = Decision.STOP
    validated_dossier: BusinessDossier | None = None
    business_dossier_sha256 = "0" * 64
    try:
        validated_dossier = _validate_business_dossier(dossier)
        business_dossier_sha256 = hash_business_dossier(validated_dossier)
        business_decision = evaluate_business_dossier(validated_dossier, at=at).decision
    except (TypeError, ValueError):
        reasons.add(PublicReleaseReason.BUSINESS_DOSSIER_INVALID)
    if business_decision is not Decision.GO:
        reasons.add(PublicReleaseReason.BUSINESS_NOT_GO)
    if validated_dossier is not None:
        expiries.extend(expiry for _, expiry in validated_dossier.expires_at.items())
        if valid_manifest is not None:
            if (
                validated_dossier.provenance.rights_bundle_sha256
                != valid_manifest.rights_bundle_sha256
            ):
                reasons.add(PublicReleaseReason.RIGHTS_BINDING_MISMATCH)
            if (
                validated_dossier.provenance.affiliate_bundle_sha256
                != valid_manifest.affiliate_bundle_sha256
            ):
                reasons.add(PublicReleaseReason.AFFILIATE_BINDING_MISMATCH)
            required_data = {
                validated_dossier.provenance.demand_source_sha256,
                validated_dossier.provenance.cohort_source_sha256,
                validated_dossier.provenance.operations_source_sha256,
            }
            if not required_data.issubset(set(valid_manifest.data_snapshot_sha256s)):
                reasons.add(PublicReleaseReason.DATA_BINDING_MISMATCH)

    tco_valid = False
    if tco_qa_attestation is None:
        reasons.add(PublicReleaseReason.TCO_QA_ATTESTATION_MISSING)
    else:
        tco_valid = _verify_attestation(
            tco_qa_attestation,
            validated_local,
            authority.trust_store.gold_tco_qa,
            authority.policy.maximum_attestation_ttl_seconds,
            expected_business_dossier_sha256=None,
            at=at,
        )
        if not tco_valid:
            reasons.add(PublicReleaseReason.TCO_QA_ATTESTATION_INVALID)
        else:
            expiries.append(tco_qa_attestation.expires_at)

    human_decision: ApprovalDecision | None = None
    human_valid = False
    approved_snapshots: tuple[str, ...] = ()
    if human_approval is None:
        reasons.add(PublicReleaseReason.HUMAN_APPROVAL_MISSING)
    else:
        human_valid = _verify_attestation(
            human_approval,
            validated_local,
            authority.trust_store.release_human,
            authority.policy.maximum_attestation_ttl_seconds,
            expected_business_dossier_sha256=business_dossier_sha256,
            at=at,
        )
        if not human_valid:
            reasons.add(PublicReleaseReason.HUMAN_APPROVAL_INVALID)
        else:
            expiries.append(human_approval.expires_at)
            human_decision = human_approval.decision
            approved_snapshots = human_approval.approved_data_snapshot_sha256s
            if valid_manifest is None or approved_snapshots != tuple(
                sorted(valid_manifest.data_snapshot_sha256s)
            ):
                reasons.add(PublicReleaseReason.HUMAN_SNAPSHOT_APPROVAL_MISMATCH)
            if human_approval.decision is not ApprovalDecision.GO:
                reasons.add(PublicReleaseReason.HUMAN_DECISION_NOT_GO)

    sorted_reasons = tuple(sorted(reasons, key=lambda item: item.value))
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "decision": (
            PublicReleaseDecision.GO if not sorted_reasons else PublicReleaseDecision.STOP
        ),
        "evaluated_at": at,
        "release_id": validated_local.release_id,
        "manifest_sha256": validated_local.manifest_sha256,
        "artifact_sha256": validated_local.artifact_sha256,
        "assurance_policy_sha256": validated_local.assurance_policy_sha256,
        "local_report_sha256": validated_local.report_sha256,
        "evidence_bundle_sha256": validated_local.evidence_bundle_sha256,
        "business_dossier_sha256": business_dossier_sha256,
        "local_assurance_ready": local_ready,
        "public_release_ready": not sorted_reasons,
        "business_decision": business_decision,
        "human_decision": human_decision,
        "tco_qa_attestation_payload_sha256": (
            tco_qa_attestation.payload_sha256 if tco_valid else None
        ),
        "human_approval_payload_sha256": (
            human_approval.payload_sha256 if human_valid else None
        ),
        "human_decision_record_sha256": (
            human_approval.decision_record_sha256 if human_valid else None
        ),
        "approved_data_snapshot_sha256s": approved_snapshots,
        "reasons": sorted_reasons,
        "expires_at": min(expiries),
        "authorization": None,
    }
    if not sorted_reasons:
        core_sha256 = _release_assurance_core_hash(values)
        values["authorization"] = authority._sign_authorization(
            issuer=authority.trust_store.controller.issuer,
            controller_key_id_sha256=authority.trust_store.controller.key_id_sha256,
            signer_role=SigningRole.CONTROLLER,
            scope=AssuranceAttestationScope.PUBLIC_RELEASE_AUTHORIZATION,
            release_assurance_core_sha256=core_sha256,
            assurance_policy_sha256=validated_local.assurance_policy_sha256,
            local_report_sha256=validated_local.report_sha256,
            business_dossier_sha256=business_dossier_sha256,
            release_id=validated_local.release_id,
            manifest_sha256=validated_local.manifest_sha256,
            artifact_sha256=validated_local.artifact_sha256,
            issued_at=at,
            expires_at=min(expiries),
        )
    provisional = ReleaseAssuranceReport.model_construct(**values, report_sha256="0" * 64)
    return ReleaseAssuranceReport(
        **values, report_sha256=hash_release_assurance_report(provisional)
    )


def hash_release_assurance_report(report: ReleaseAssuranceReport) -> str:
    return _canonical_sha256(report.model_dump(mode="json", exclude={"report_sha256"}))


def _release_assurance_core_hash(values: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            key: value
            for key, value in values.items()
            if key not in {"authorization", "report_sha256"}
        }
    )


class ReleaseAssuranceRuntime:
    """Downstream fixed trust root for consuming controller-authorized public GO."""

    __slots__ = ("__controller_key", "__policy_sha256", "__maximum_ttl_seconds")

    def __init__(
        self,
        controller_key: Ed25519VerificationKey,
        *,
        assurance_policy_sha256: str,
        maximum_authorization_ttl_seconds: int,
    ) -> None:
        validated_key = Ed25519VerificationKey.model_validate(controller_key.model_dump())
        if validated_key.role is not SigningRole.CONTROLLER:
            raise ValueError("release assurance runtime requires a controller key")
        if (
            not isinstance(assurance_policy_sha256, str)
            or len(assurance_policy_sha256) != 64
            or any(character not in "0123456789abcdef" for character in assurance_policy_sha256)
        ):
            raise ValueError("runtime assurance policy SHA-256 is invalid")
        if not 1 <= maximum_authorization_ttl_seconds <= 604_800:
            raise ValueError("runtime authorization TTL is out of bounds")
        self.__controller_key = validated_key
        self.__policy_sha256 = assurance_policy_sha256
        self.__maximum_ttl_seconds = maximum_authorization_ttl_seconds

    def allows(self, report: ReleaseAssuranceReport, *, at: datetime) -> bool:
        _require_utc(at, "release assurance runtime time")
        if type(report) is not ReleaseAssuranceReport:
            return False
        try:
            validated = ReleaseAssuranceReport.model_validate(report.model_dump())
        except (TypeError, ValueError):
            return False
        authorization = validated.authorization
        if (
            validated.decision is not PublicReleaseDecision.GO
            or not validated.public_release_ready
            or authorization is None
            or validated.assurance_policy_sha256 != self.__policy_sha256
            or not (validated.evaluated_at <= at < validated.expires_at)
        ):
            return False
        try:
            signature = _decode_base64url(authorization.signature_base64url, 64)
            message = _canonical_json_bytes(
                authorization.model_dump(mode="json", exclude={"signature_base64url"})
            )
            self.__controller_key.public_key().verify(signature, message)
        except (TypeError, ValueError, InvalidSignature):
            return False
        core_values = validated.model_dump(
            mode="json", exclude={"authorization", "report_sha256"}
        )
        return (
            authorization.issuer == self.__controller_key.issuer
            and authorization.controller_key_id_sha256
            == self.__controller_key.key_id_sha256
            and authorization.signer_role is SigningRole.CONTROLLER
            and authorization.scope
            is AssuranceAttestationScope.PUBLIC_RELEASE_AUTHORIZATION
            and authorization.assurance_policy_sha256 == self.__policy_sha256
            and authorization.release_assurance_core_sha256
            == _release_assurance_core_hash(core_values)
            and authorization.local_report_sha256 == validated.local_report_sha256
            and authorization.business_dossier_sha256
            == validated.business_dossier_sha256
            and authorization.release_id == validated.release_id
            and authorization.manifest_sha256 == validated.manifest_sha256
            and authorization.artifact_sha256 == validated.artifact_sha256
            and authorization.issued_at == validated.evaluated_at
            and authorization.expires_at == validated.expires_at
            and authorization.issued_at <= at < authorization.expires_at
            and authorization.expires_at - authorization.issued_at
            <= timedelta(seconds=self.__maximum_ttl_seconds)
        )

    @property
    def controller_key(self) -> Ed25519VerificationKey:
        """Return the immutable downstream controller trust root."""

        return Ed25519VerificationKey.model_validate(
            self.__controller_key.model_dump()
        )

    @property
    def assurance_policy_sha256(self) -> str:
        return self.__policy_sha256


def verify_release_assurance_report(
    report: ReleaseAssuranceReport,
    runtime: ReleaseAssuranceRuntime,
    *,
    at: datetime,
) -> bool:
    """Verify current authorization with a downstream-pinned key and policy."""

    if type(runtime) is not ReleaseAssuranceRuntime:
        return False
    return runtime.allows(report, at=at)


def hash_business_dossier(dossier: BusinessDossier) -> str:
    validated = _validate_business_dossier(dossier)
    return _canonical_sha256(validated.model_dump(mode="json"))


def _report_binding(report: LocalAssuranceReport) -> dict[str, Any]:
    return {
        "local_report_sha256": report.report_sha256,
        "evidence_bundle_sha256": report.evidence_bundle_sha256,
        "release_id": report.release_id,
        "manifest_sha256": report.manifest_sha256,
        "artifact_sha256": report.artifact_sha256,
        "assurance_policy_sha256": report.assurance_policy_sha256,
    }


def _validate_local_report(report: LocalAssuranceReport) -> LocalAssuranceReport:
    if type(report) is not LocalAssuranceReport:
        raise TypeError("report must be LocalAssuranceReport")
    try:
        return LocalAssuranceReport.model_validate(report.model_dump())
    except (TypeError, ValueError) as exc:
        raise AssuranceInputError("local assurance report is invalid") from exc


def _validate_business_dossier(dossier: BusinessDossier) -> BusinessDossier:
    if type(dossier) is not BusinessDossier:
        raise TypeError("dossier must be BusinessDossier")
    try:
        return BusinessDossier.model_validate(dossier.model_dump())
    except (TypeError, ValueError) as exc:
        raise AssuranceInputError("business dossier is invalid") from exc


def _build_signed_attestation(
    model: type[LocalAssuranceAttestation] | type[PublicReleaseApprovalAttestation],
    values: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    role: SigningRole,
) -> LocalAssuranceAttestation | PublicReleaseApprovalAttestation:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    key = create_verification_key(private_key.public_key(), issuer=values["issuer"], role=role)
    payload = dict(values)
    payload.setdefault("schema_version", "1.0")
    payload["key_id_sha256"] = key.key_id_sha256
    _require_utc(payload["issued_at"], "attestation issued_at")
    _require_utc(payload["expires_at"], "attestation expires_at")
    if payload["expires_at"] <= payload["issued_at"]:
        raise ValueError("attestation expiry must follow issuance")
    payload_sha256 = _canonical_sha256(payload)
    signed = {**payload, "payload_sha256": payload_sha256}
    signature = private_key.sign(_canonical_json_bytes(signed))
    return model(**signed, signature_base64url=_encode_base64url(signature))


def _build_signed_authorization(
    values: dict[str, Any],
    private_key: Ed25519PrivateKey,
    verification_key: Ed25519VerificationKey,
) -> ReleaseAuthorization:
    if not _private_key_matches(private_key, verification_key):
        raise AssuranceInputError("controller signer does not match verification key")
    payload = {"schema_version": "1.0", **values}
    payload_sha256 = _canonical_sha256(payload)
    signed = {**payload, "payload_sha256": payload_sha256}
    signature = private_key.sign(_canonical_json_bytes(signed))
    return ReleaseAuthorization(
        **signed, signature_base64url=_encode_base64url(signature)
    )


def _validate_attestation_payload(
    model: LocalAssuranceAttestation | PublicReleaseApprovalAttestation,
) -> None:
    if model.expires_at <= model.issued_at:
        raise ValueError("attestation expiry must follow issuance")
    payload = model.model_dump(
        mode="json", exclude={"payload_sha256", "signature_base64url"}
    )
    if model.payload_sha256 != _canonical_sha256(payload):
        raise ValueError("attestation payload_sha256 does not match canonical payload")


def _verify_evidence_signature(
    evidence: AssuranceEvidence,
    key: Ed25519VerificationKey,
) -> bool:
    try:
        validated = AssuranceEvidence.model_validate(evidence.model_dump())
        signature = _decode_base64url(validated.signature_base64url, 64)
        message = _canonical_json_bytes(
            validated.model_dump(mode="json", exclude={"signature_base64url"})
        )
        key.public_key().verify(signature, message)
    except (TypeError, ValueError, InvalidSignature):
        return False
    return (
        key.role is SigningRole.CONTROLLER
        and validated.runner_role is SigningRole.CONTROLLER
        and validated.runner_issuer == key.issuer
        and validated.runner_key_id_sha256 == key.key_id_sha256
    )


def _verify_attestation(
    attestation: LocalAssuranceAttestation | PublicReleaseApprovalAttestation,
    report: LocalAssuranceReport,
    key: Ed25519VerificationKey,
    maximum_ttl_seconds: int,
    expected_business_dossier_sha256: str | None,
    *,
    at: datetime,
) -> bool:
    expected_type: type[StrictModel]
    expected_role: SigningRole
    expected_scope: AssuranceAttestationScope
    if type(attestation) is LocalAssuranceAttestation:
        expected_type = LocalAssuranceAttestation
        expected_role = SigningRole.TCO_QA
        expected_scope = AssuranceAttestationScope.LOCAL_ASSURANCE_ACCEPTANCE
    elif type(attestation) is PublicReleaseApprovalAttestation:
        expected_type = PublicReleaseApprovalAttestation
        expected_role = SigningRole.HUMAN_APPROVER
        expected_scope = AssuranceAttestationScope.PUBLIC_RELEASE_APPROVAL
    else:
        return False
    try:
        validated = expected_type.model_validate(attestation.model_dump())
        signature = _decode_base64url(validated.signature_base64url, 64)  # type: ignore[attr-defined]
        message = _canonical_json_bytes(
            validated.model_dump(mode="json", exclude={"signature_base64url"})
        )
        key.public_key().verify(signature, message)
    except (TypeError, ValueError, InvalidSignature):
        return False
    common_valid = (
        key.role is expected_role
        and validated.issuer == key.issuer  # type: ignore[attr-defined]
        and validated.key_id_sha256 == key.key_id_sha256  # type: ignore[attr-defined]
        and validated.signer_role is expected_role  # type: ignore[attr-defined]
        and validated.scope is expected_scope  # type: ignore[attr-defined]
        and validated.issued_at >= report.evaluated_at  # type: ignore[attr-defined]
        and validated.issued_at <= at < validated.expires_at  # type: ignore[attr-defined]
        and validated.expires_at - validated.issued_at  # type: ignore[attr-defined]
        <= timedelta(seconds=maximum_ttl_seconds)
        and all(
            getattr(validated, field) == value
            for field, value in _report_binding(report).items()
        )
    )
    if not common_valid:
        return False
    if type(validated) is PublicReleaseApprovalAttestation:
        return (
            expected_business_dossier_sha256 is not None
            and validated.business_dossier_sha256
            == expected_business_dossier_sha256
        )
    return expected_business_dossier_sha256 is None


def _copy_manifest(manifest: ReleaseManifest) -> ReleaseManifest:
    if type(manifest) is not ReleaseManifest:
        raise TypeError("manifest must be ReleaseManifest")
    copied = ReleaseManifest(
        release_id=manifest.release_id,
        prepared_at=manifest.prepared_at,
        artifact_sha256=manifest.artifact_sha256,
        schema_sha256=manifest.schema_sha256,
        data_snapshot_sha256s=manifest.data_snapshot_sha256s,
        rights_bundle_sha256=manifest.rights_bundle_sha256,
        affiliate_bundle_sha256=manifest.affiliate_bundle_sha256,
        data_expires_at=manifest.data_expires_at,
        rights_expires_at=manifest.rights_expires_at,
        affiliate_expires_at=manifest.affiliate_expires_at,
        cta=manifest.cta,
        rollback_release_id=manifest.rollback_release_id,
    )
    if copied.manifest_sha256 != manifest.manifest_sha256:
        raise ValueError("manifest hash was modified")
    return copied


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


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str, expected_length: int) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid canonical base64url") from exc
    if len(decoded) != expected_length or _encode_base64url(decoded) != value:
        raise ValueError("invalid canonical base64url length or encoding")
    return decoded


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


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
    "AssuranceAttestationScope",
    "AssuranceCheck",
    "AssuranceEvidence",
    "AssuranceEvidenceBundle",
    "AssuranceFacts",
    "AssuranceInputError",
    "AssurancePolicy",
    "AssuranceRequirement",
    "DeterminismFacts",
    "EvidenceFactsKind",
    "IntegrityFacts",
    "LocalAssuranceAttestation",
    "LocalAssuranceDecision",
    "LocalAssuranceReason",
    "LocalAssuranceReport",
    "PublicReleaseApprovalAttestation",
    "PublicReleaseDecision",
    "PublicReleaseReason",
    "REQUIRED_LOCAL_CHECKS",
    "ReleaseAssuranceRuntime",
    "ReleaseAssuranceAuthority",
    "ReleaseAssuranceVerifier",
    "ReleaseAssuranceReport",
    "ReleaseAuthorization",
    "ReviewFacts",
    "RouteAssuranceFacts",
    "ScanFacts",
    "TestSuiteFacts",
    "build_assurance_bundle",
    "build_assurance_evidence",
    "evaluate_local_assurance",
    "evaluate_public_release_assurance",
    "hash_assurance_bundle",
    "hash_assurance_evidence",
    "hash_assurance_policy",
    "hash_business_dossier",
    "hash_local_assurance_report",
    "hash_release_assurance_report",
    "sign_local_assurance_report",
    "sign_public_release_approval",
    "verify_release_assurance_report",
]
