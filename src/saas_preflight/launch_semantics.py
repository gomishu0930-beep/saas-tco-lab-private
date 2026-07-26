"""Credential-blind semantic re-evaluation for P16 launch Gates 2-8.

The P16 receipt chain proves who reviewed a digest.  This module proves what
that digest means by carrying the exact upstream rows, re-running their public
evaluators, and binding the result to one immutable launch scope.  It grants no
external authority and contains no private signing material.
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

from .control_cycle import (
    ControlTrustStore,
    Ed25519VerificationKey,
    GoldReportAttestation,
    SigningRole,
    hash_control_trust_store,
    verify_gold_report_attestation,
)
from .economics import GateStatus
from .goldset import (
    CandidateBatch,
    GoldSetReport,
    HumanGoldSet,
    evaluate_goldset,
    hash_goldset_report,
    hash_rights_manifest,
)
from .measurement_integrity import (
    MeasurementBoundDossier,
    MeasurementIntegrityVerifier,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
)
from .models import Sha256, StrictModel, VendorPlan
from .preflight import evaluate_business_dossier
from .production_readiness import (
    ProductionIntegrationEvidenceBundle,
    ProductionEvidenceProvenance,
    ProductionIntegrationCheck,
    ProductionIntegrationPlan,
    ProductionIntegrationPolicy,
    ProductionIntegrationTrustStore,
    ProductionReadinessDecision,
    ProductionReadinessReport,
    ProductionTcoQaAttestation,
    ReadinessAttestationDecision,
    evaluate_production_integration_readiness,
    hash_production_integration_bundle,
    hash_production_integration_evidence,
    hash_production_integration_plan,
    hash_production_integration_policy,
    hash_production_integration_trust_store,
    hash_production_readiness_report,
    hash_production_tco_qa_attestation,
    verify_production_tco_qa_attestation,
)
from .readiness_builder import (
    AffiliateDecisionBatch,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)
from .release_assurance import (
    AssuranceEvidenceBundle,
    AssurancePolicy,
    LocalAssuranceReport,
    ReleaseAssuranceVerifier,
    hash_assurance_bundle,
    hash_assurance_policy,
    hash_local_assurance_report,
)
from .traction_control import P12AuthorityPacket


class LaunchSemanticInputError(ValueError):
    """A packet-external semantic authority or exact typed input is invalid."""


class LaunchSemanticGate(str, Enum):
    RIGHTS_APPROVAL = "rights_approval"
    AFFILIATE_ACCEPTANCE = "affiliate_acceptance"
    QUALIFIED_DEMAND = "qualified_demand"
    SHADOW_OPERATIONS = "shadow_operations"
    GOLD_SET_SOURCE_READINESS = "gold_set_source_readiness"
    PRODUCTION_INTEGRATION_READINESS = "production_integration_readiness"
    DEPLOYMENT_PUBLICATION_READINESS = "deployment_publication_readiness"


REQUIRED_LAUNCH_SEMANTIC_GATES: tuple[LaunchSemanticGate, ...] = tuple(
    LaunchSemanticGate
)


class LaunchSemanticReason(str, Enum):
    RIGHTS_INVALID = "rights_invalid"
    AFFILIATE_INVALID = "affiliate_invalid"
    MINIMUM_VENDOR_SET_NOT_MET = "minimum_vendor_set_not_met"
    VENDOR_SET_MISMATCH = "vendor_set_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    MEASUREMENT_INVALID = "measurement_invalid"
    DEMAND_GATE_FAILED = "demand_gate_failed"
    OPERATIONS_GATE_FAILED = "operations_gate_failed"
    GOLD_SET_INVALID = "gold_set_invalid"
    PRODUCTION_READINESS_INVALID = "production_readiness_invalid"
    LOCAL_ASSURANCE_INVALID = "local_assurance_invalid"
    DEPLOYMENT_RECORD_INVALID = "deployment_record_invalid"
    PUBLICATION_RECORD_INVALID = "publication_record_invalid"
    UPSTREAM_EXPIRY_INVALID = "upstream_expiry_invalid"


class LaunchSemanticComponentKind(str, Enum):
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


class LaunchSemanticScope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
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


class RightsSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plans: tuple[VendorPlan, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def canonical_plans(self) -> Self:
        keys = tuple((item.vendor_slug, item.plan_slug, str(item.snapshot_id)) for item in self.plans)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("rights plans must be canonical and unique")
        return self


class AffiliateSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    property_domain: str = Field(min_length=1, max_length=253)
    decisions: AffiliateDecisionBatch

    @field_validator("property_domain")
    @classmethod
    def normalize_property_domain(cls, value: str) -> str:
        normalized = value.strip().lower().rstrip(".")
        if not normalized or "://" in normalized or "/" in normalized:
            raise ValueError("property_domain must be a bare normalized domain")
        return normalized


class MeasurementSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    authority_packet: P12AuthorityPacket
    bound_dossier: MeasurementBoundDossier


class GoldSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    goldset: HumanGoldSet
    candidates: CandidateBatch
    report: GoldSetReport
    attestation: GoldReportAttestation
    tco_qa_verifier: Ed25519VerificationKey


class ProductionSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan: ProductionIntegrationPlan
    policy: ProductionIntegrationPolicy
    trust_store: ProductionIntegrationTrustStore
    evidence_bundle: ProductionIntegrationEvidenceBundle
    report: ProductionReadinessReport
    tco_qa_attestation: ProductionTcoQaAttestation


class DeploymentReadinessFacts(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    property_record_sha256: Sha256
    environment_identity_sha256: Sha256
    release_identity_sha256: Sha256
    release_manifest_sha256: Sha256
    release_artifact_sha256: Sha256
    deployment_candidate_sha256: Sha256
    production_integration_plan_sha256: Sha256
    provider_target_sha256: Sha256
    expected_pre_state_sha256: Sha256
    independent_readback_evidence_sha256: Sha256
    rollback_disable_evidence_sha256: Sha256
    staged_expected_state_sha256: Sha256
    staged_observed_state_sha256: Sha256
    rollback_active_state_sha256: Sha256
    rollback_expected_state_sha256: Sha256
    rollback_observed_state_sha256: Sha256

    @model_validator(mode="after")
    def require_observed_state_matches(self) -> Self:
        if self.staged_observed_state_sha256 != self.staged_expected_state_sha256:
            raise ValueError("staged readback must match the expected active state")
        if self.rollback_active_state_sha256 != self.staged_expected_state_sha256:
            raise ValueError("rollback must start from the staged active state")
        if self.rollback_observed_state_sha256 != self.rollback_expected_state_sha256:
            raise ValueError("rollback readback must match the expected safe state")
        if self.rollback_expected_state_sha256 == self.staged_expected_state_sha256:
            raise ValueError("rollback must reach a distinct safe state")
        return self


class DeploymentReadinessRecord(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    facts: DeploymentReadinessFacts
    provenance: ProductionEvidenceProvenance
    observed_at: datetime
    expires_at: datetime
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.PROVIDER_PROBE] = SigningRole.PROVIDER_PROBE
    record_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        _require_utc(value, "deployment readiness timestamp")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("deployment readiness expiry must follow observation")
        if self.record_sha256 != hash_deployment_readiness_record(self):
            raise ValueError("deployment readiness record hash mismatch")
        return self


class PublicationContentReadback(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    http_status: Literal[200] = 200
    expected_release_manifest_sha256: Sha256
    observed_release_manifest_sha256: Sha256
    expected_release_artifact_sha256: Sha256
    observed_release_artifact_sha256: Sha256
    response_receipt_sha256: Sha256
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        _require_utc(value, "publication content readback timestamp")
        return value

    @model_validator(mode="after")
    def require_exact_content(self) -> Self:
        if (
            self.expected_release_manifest_sha256
            != self.observed_release_manifest_sha256
            or self.expected_release_artifact_sha256
            != self.observed_release_artifact_sha256
        ):
            raise ValueError("published content does not match the release")
        return self


class PublicationIndexabilityReadback(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    robots_allows_indexing: Literal[True] = True
    meta_robots_index: Literal[True] = True
    canonical_matches_property: Literal[True] = True
    response_receipt_sha256: Sha256
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        _require_utc(value, "publication indexability readback timestamp")
        return value


class PublicationDisclosureReadback(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    expected_legal_pages_sha256: Sha256
    observed_legal_pages_sha256: Sha256
    expected_disclosure_sha256: Sha256
    observed_disclosure_sha256: Sha256
    disclosure_visible: Literal[True] = True
    response_receipt_sha256: Sha256
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        _require_utc(value, "publication disclosure readback timestamp")
        return value

    @model_validator(mode="after")
    def require_exact_disclosures(self) -> Self:
        if (
            self.expected_legal_pages_sha256 != self.observed_legal_pages_sha256
            or self.expected_disclosure_sha256
            != self.observed_disclosure_sha256
        ):
            raise ValueError("published legal or disclosure content does not match")
        return self


class PublicationReadinessFacts(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    property_record_sha256: Sha256
    environment_identity_sha256: Sha256
    release_identity_sha256: Sha256
    release_manifest_sha256: Sha256
    release_artifact_sha256: Sha256
    deployment_candidate_sha256: Sha256
    deployment_readiness_record_sha256: Sha256
    rights_bundle_sha256: Sha256
    affiliate_bundle_sha256: Sha256
    approved_partner_ids: tuple[str, ...] = Field(min_length=3)
    content_readback: PublicationContentReadback
    indexability_readback: PublicationIndexabilityReadback
    disclosure_readback: PublicationDisclosureReadback

    @field_validator("approved_partner_ids")
    @classmethod
    def canonical_partners(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("approved partner IDs must be canonical and unique")
        return value


class PublicationReadinessRecord(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    facts: PublicationReadinessFacts
    provenance: ProductionEvidenceProvenance
    observed_at: datetime
    expires_at: datetime
    issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.PROVIDER_PROBE] = SigningRole.PROVIDER_PROBE
    record_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        _require_utc(value, "publication readiness timestamp")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("publication readiness expiry must follow observation")
        if self.observed_at != max(
            self.facts.content_readback.observed_at,
            self.facts.indexability_readback.observed_at,
            self.facts.disclosure_readback.observed_at,
        ):
            raise ValueError("publication record time must equal the latest readback")
        if self.record_sha256 != hash_publication_readiness_record(self):
            raise ValueError("publication readiness record hash mismatch")
        return self


class DeploymentPublicationSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assurance_policy: AssurancePolicy
    assurance_trust_store: ControlTrustStore
    assurance_bundle: AssuranceEvidenceBundle
    local_assurance_report: LocalAssuranceReport
    deployment: DeploymentReadinessRecord
    publication: PublicationReadinessRecord


class LaunchSemanticPacket(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    scope: LaunchSemanticScope
    rights: RightsSemanticPacket
    affiliate: AffiliateSemanticPacket
    measurement: MeasurementSemanticPacket
    gold: GoldSemanticPacket
    production: ProductionSemanticPacket
    deployment_publication: DeploymentPublicationSemanticPacket
    packet_sha256: Sha256

    @model_validator(mode="after")
    def validate_packet_hash(self) -> Self:
        if self.packet_sha256 != hash_launch_semantic_packet(self):
            raise ValueError("launch semantic packet hash mismatch")
        return self


class LaunchSemanticAuthorityPins(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    expected_packet_sha256: Sha256
    expected_rights_packet_sha256: Sha256
    expected_affiliate_packet_sha256: Sha256
    expected_measurement_packet_sha256: Sha256
    expected_measurement_policy_sha256: Sha256
    expected_measurement_trust_store_sha256: Sha256
    expected_measurement_authority_pins_sha256: Sha256
    expected_measurement_plan_sha256: Sha256
    expected_measurement_index_sha256: Sha256
    expected_measurement_report_sha256: Sha256
    expected_gold_packet_sha256: Sha256
    expected_gold_report_sha256: Sha256
    expected_gold_tco_qa_key_id_sha256: Sha256
    expected_production_packet_sha256: Sha256
    expected_production_plan_sha256: Sha256
    expected_production_policy_sha256: Sha256
    expected_production_trust_store_sha256: Sha256
    expected_production_bundle_sha256: Sha256
    expected_production_report_sha256: Sha256
    expected_production_tco_attestation_sha256: Sha256
    expected_deployment_publication_packet_sha256: Sha256
    expected_assurance_policy_sha256: Sha256
    expected_assurance_trust_store_sha256: Sha256
    expected_assurance_bundle_sha256: Sha256
    expected_local_assurance_report_sha256: Sha256
    expected_deployment_record_sha256: Sha256
    expected_publication_record_sha256: Sha256
    pins_sha256: Sha256

    @model_validator(mode="after")
    def validate_pins_hash(self) -> Self:
        if self.pins_sha256 != hash_launch_semantic_authority_pins(self):
            raise ValueError("launch semantic authority pins hash mismatch")
        return self


class LaunchSemanticComponent(StrictModel):
    kind: LaunchSemanticComponentKind
    artifact_sha256: Sha256


class LaunchSemanticGateEvaluation(StrictModel):
    gate: LaunchSemanticGate
    passed: bool
    components: tuple[LaunchSemanticComponent, ...] = Field(min_length=1, max_length=3)
    evidence_identity_sha256: Sha256
    subject_sha256: Sha256
    reasons: tuple[LaunchSemanticReason, ...]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def utc_expiry(cls, value: datetime) -> datetime:
        _require_utc(value, "semantic gate expiry")
        return value

    @model_validator(mode="after")
    def canonical_reasons(self) -> Self:
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise ValueError("semantic reasons must be canonical and unique")
        if self.passed == bool(self.reasons):
            raise ValueError("semantic pass state does not match reasons")
        return self


class LaunchSemanticEvaluation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    packet_sha256: Sha256
    authority_pins_sha256: Sha256
    evaluated_at: datetime
    gates: tuple[LaunchSemanticGateEvaluation, ...] = Field(min_length=7, max_length=7)
    passed: bool
    expires_at: datetime
    authority_effect: Literal["none"] = "none"
    authorizes_external_mutation: Literal[False] = False
    evaluation_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        _require_utc(value, "semantic evaluation timestamp")
        return value

    @model_validator(mode="after")
    def validate_evaluation(self) -> Self:
        if tuple(item.gate for item in self.gates) != REQUIRED_LAUNCH_SEMANTIC_GATES:
            raise ValueError("semantic gates must use the exact canonical order")
        if self.passed != all(item.passed for item in self.gates):
            raise ValueError("semantic aggregate pass state mismatch")
        if self.passed and self.expires_at <= self.evaluated_at:
            raise ValueError("passing semantic evaluation must be current")
        if self.evaluation_sha256 != hash_launch_semantic_evaluation(self):
            raise ValueError("semantic evaluation hash mismatch")
        return self


def hash_rights_semantic_packet(value: RightsSemanticPacket) -> str:
    return _hash_model(_copy(value, RightsSemanticPacket))


def hash_affiliate_semantic_packet(value: AffiliateSemanticPacket) -> str:
    return _hash_model(_copy(value, AffiliateSemanticPacket))


def hash_measurement_semantic_packet(value: MeasurementSemanticPacket) -> str:
    return _hash_model(_copy(value, MeasurementSemanticPacket))


def hash_gold_semantic_packet(value: GoldSemanticPacket) -> str:
    return _hash_model(_copy(value, GoldSemanticPacket))


def hash_production_semantic_packet(value: ProductionSemanticPacket) -> str:
    return _hash_model(_copy(value, ProductionSemanticPacket))


def hash_deployment_publication_semantic_packet(
    value: DeploymentPublicationSemanticPacket,
) -> str:
    return _hash_model(_copy(value, DeploymentPublicationSemanticPacket))


def hash_deployment_readiness_record(value: DeploymentReadinessRecord) -> str:
    return _hash_model(
        value, excluded={"record_sha256", "signature_base64url"}
    )


def hash_publication_readiness_record(value: PublicationReadinessRecord) -> str:
    return _hash_model(
        value, excluded={"record_sha256", "signature_base64url"}
    )


def sign_deployment_readiness_record(
    facts: DeploymentReadinessFacts,
    signing_key: Ed25519PrivateKey,
    verifier: Ed25519VerificationKey,
    *,
    provenance: ProductionEvidenceProvenance,
    observed_at: datetime,
    expires_at: datetime,
) -> DeploymentReadinessRecord:
    """Sign exact staged-readback and rollback facts with the P15 probe role."""

    values = _readiness_signature_values(
        facts,
        signing_key,
        verifier,
        provenance=provenance,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    provisional = DeploymentReadinessRecord.model_construct(
        **values, record_sha256="0" * 64, signature_base64url="A" * 86
    )
    digest = hash_deployment_readiness_record(provisional)
    return DeploymentReadinessRecord(
        **values,
        record_sha256=digest,
        signature_base64url=_sign_digest(signing_key, digest),
    )


def sign_publication_readiness_record(
    facts: PublicationReadinessFacts,
    signing_key: Ed25519PrivateKey,
    verifier: Ed25519VerificationKey,
    *,
    provenance: ProductionEvidenceProvenance,
    observed_at: datetime,
    expires_at: datetime,
) -> PublicationReadinessRecord:
    """Sign exact content/indexability/disclosure readbacks with the probe role."""

    values = _readiness_signature_values(
        facts,
        signing_key,
        verifier,
        provenance=provenance,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    provisional = PublicationReadinessRecord.model_construct(
        **values, record_sha256="0" * 64, signature_base64url="A" * 86
    )
    digest = hash_publication_readiness_record(provisional)
    return PublicationReadinessRecord(
        **values,
        record_sha256=digest,
        signature_base64url=_sign_digest(signing_key, digest),
    )


def hash_launch_semantic_packet(value: LaunchSemanticPacket) -> str:
    return _hash_model(value, excluded={"packet_sha256"})


def hash_launch_semantic_authority_pins(value: LaunchSemanticAuthorityPins) -> str:
    return _hash_model(value, excluded={"pins_sha256"})


def hash_launch_semantic_evaluation(value: LaunchSemanticEvaluation) -> str:
    return _hash_model(value, excluded={"evaluation_sha256"})


def build_launch_semantic_authority_pins(
    packet: LaunchSemanticPacket,
) -> LaunchSemanticAuthorityPins:
    item = _copy(packet, LaunchSemanticPacket)
    p12 = item.measurement.authority_packet
    p15 = item.production
    p10 = item.deployment_publication
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "expected_packet_sha256": item.packet_sha256,
        "expected_rights_packet_sha256": hash_rights_semantic_packet(item.rights),
        "expected_affiliate_packet_sha256": hash_affiliate_semantic_packet(item.affiliate),
        "expected_measurement_packet_sha256": hash_measurement_semantic_packet(item.measurement),
        "expected_measurement_policy_sha256": hash_measurement_policy(p12.policy),
        "expected_measurement_trust_store_sha256": hash_measurement_trust_store(p12.trust_store),
        "expected_measurement_authority_pins_sha256": hash_signed_artifact(p12.authority_pins),
        "expected_measurement_plan_sha256": hash_signed_artifact(p12.plan),
        "expected_measurement_index_sha256": hash_signed_artifact(p12.bundle_index),
        "expected_measurement_report_sha256": hash_signed_artifact(p12.report),
        "expected_gold_packet_sha256": hash_gold_semantic_packet(item.gold),
        "expected_gold_report_sha256": hash_goldset_report(item.gold.report),
        "expected_gold_tco_qa_key_id_sha256": (
            item.gold.tco_qa_verifier.key_id_sha256
        ),
        "expected_production_packet_sha256": hash_production_semantic_packet(p15),
        "expected_production_plan_sha256": hash_production_integration_plan(p15.plan),
        "expected_production_policy_sha256": hash_production_integration_policy(p15.policy),
        "expected_production_trust_store_sha256": hash_production_integration_trust_store(p15.trust_store),
        "expected_production_bundle_sha256": hash_production_integration_bundle(p15.evidence_bundle),
        "expected_production_report_sha256": hash_production_readiness_report(p15.report),
        "expected_production_tco_attestation_sha256": hash_production_tco_qa_attestation(p15.tco_qa_attestation),
        "expected_deployment_publication_packet_sha256": hash_deployment_publication_semantic_packet(p10),
        "expected_assurance_policy_sha256": hash_assurance_policy(p10.assurance_policy),
        "expected_assurance_trust_store_sha256": hash_control_trust_store(p10.assurance_trust_store),
        "expected_assurance_bundle_sha256": hash_assurance_bundle(p10.assurance_bundle),
        "expected_local_assurance_report_sha256": hash_local_assurance_report(p10.local_assurance_report),
        "expected_deployment_record_sha256": p10.deployment.record_sha256,
        "expected_publication_record_sha256": p10.publication.record_sha256,
    }
    provisional = LaunchSemanticAuthorityPins.model_construct(
        **values, pins_sha256="0" * 64
    )
    return LaunchSemanticAuthorityPins(
        **values, pins_sha256=hash_launch_semantic_authority_pins(provisional)
    )


def evaluate_launch_semantics(
    packet: LaunchSemanticPacket,
    pins: LaunchSemanticAuthorityPins,
    *,
    at: datetime,
    expected_authority_pins_sha256: str,
) -> LaunchSemanticEvaluation:
    """Re-run all Gate 2-8 semantics with packet-external authority pins."""

    _require_utc(at, "launch semantic evaluation timestamp")
    item = _copy(packet, LaunchSemanticPacket)
    pinned = _copy(pins, LaunchSemanticAuthorityPins)
    if not _is_sha256(expected_authority_pins_sha256):
        raise LaunchSemanticInputError("expected semantic authority root is invalid")
    if hash_launch_semantic_authority_pins(pinned) != expected_authority_pins_sha256:
        raise LaunchSemanticInputError("semantic authorities do not match the consumer root")
    if pinned != build_launch_semantic_authority_pins(item):
        raise LaunchSemanticInputError("semantic packet does not match consumer-owned pins")

    results: list[LaunchSemanticGateEvaluation] = []
    rights_reasons: set[LaunchSemanticReason] = set()
    affiliate_reasons: set[LaunchSemanticReason] = set()
    demand_reasons: set[LaunchSemanticReason] = set()
    operations_reasons: set[LaunchSemanticReason] = set()
    gold_reasons: set[LaunchSemanticReason] = set()
    production_reasons: set[LaunchSemanticReason] = set()
    deployment_reasons: set[LaunchSemanticReason] = set()

    rights_bundle = None
    affiliate_bundle = None
    try:
        rights_bundle = build_rights_bundle(item.rights.plans, at=at)
        if not rights_bundle.approved:
            rights_reasons.add(LaunchSemanticReason.RIGHTS_INVALID)
        if len(rights_bundle.eligible_vendor_slugs) < 3:
            rights_reasons.add(LaunchSemanticReason.MINIMUM_VENDOR_SET_NOT_MET)
    except (AttributeError, KeyError, TypeError, ValueError):
        rights_reasons.add(LaunchSemanticReason.RIGHTS_INVALID)

    try:
        affiliate_bundle = build_affiliate_bundle(
            item.affiliate.decisions.decisions,
            property_domain=item.affiliate.property_domain,
            at=at,
        )
        if len(affiliate_bundle.approved_partner_ids) < 3:
            affiliate_reasons.add(LaunchSemanticReason.MINIMUM_VENDOR_SET_NOT_MET)
        if (
            rights_bundle is None
            or affiliate_bundle.approved_vendor_slugs
            != rights_bundle.eligible_vendor_slugs
        ):
            affiliate_reasons.add(LaunchSemanticReason.VENDOR_SET_MISMATCH)
    except (AttributeError, KeyError, TypeError, ValueError):
        affiliate_reasons.add(LaunchSemanticReason.AFFILIATE_INVALID)

    p12 = item.measurement.authority_packet
    measurement_valid = False
    dossier_evaluation = None
    try:
        verifier = MeasurementIntegrityVerifier(
            p12.policy, p12.trust_store, p12.authority_pins
        )
        measurement_valid = verifier.verify(
            p12.report,
            p12.plan,
            p12.demand_batch,
            p12.cohort_batch,
            p12.operations_batch,
            p12.demand_attestation,
            p12.cohort_attestation,
            p12.operations_attestation,
            p12.bundle_index,
            at=at,
        )
        dossier = item.measurement.bound_dossier
        rebuilt = build_business_dossier(
            plans=item.rights.plans,
            affiliate_decisions=item.affiliate.decisions.decisions,
            property_domain=item.affiliate.property_domain,
            demand=p12.report.demand,
            cohort=p12.report.cohort,
            operations=p12.report.operations,
            at=dossier.dossier.as_of,
        )
        measurement_valid = (
            measurement_valid
            and dossier.report == p12.report
            and dossier.dossier == rebuilt
            and dossier.dossier_sha256 == hash_signed_artifact(rebuilt)
            and p12.report.property_record_sha256
            == item.scope.property_record_sha256
            and p12.policy.property_record_sha256
            == item.scope.property_record_sha256
            and p12.report.property_domain_sha256
            == _text_sha256(item.affiliate.property_domain)
            and p12.plan.definition.fault_target_release_sha256
            == item.scope.release_identity_sha256
            and p12.plan.definition.fault_target_artifact_sha256
            == item.scope.release_artifact_sha256
            and p12.plan.definition.fault_target_schema_sha256
            == item.scope.deployment_candidate_sha256
        )
        dossier_evaluation = evaluate_business_dossier(dossier.dossier, at=at)
    except (AttributeError, KeyError, TypeError, ValueError):
        measurement_valid = False
    if not measurement_valid or dossier_evaluation is None or dossier_evaluation.economics is None:
        demand_reasons.add(LaunchSemanticReason.MEASUREMENT_INVALID)
        operations_reasons.add(LaunchSemanticReason.MEASUREMENT_INVALID)
    else:
        checks = {check.name: check.status for check in dossier_evaluation.economics.checks}
        demand_names = {
            "bear_qualified_demand", "traction_maturity", "confirmed_epc",
            "bear_target_capacity",
        }
        operations_names = {
            "major_misstatements", "human_hours", "automation_rate",
            "shadow_observation", "job_success_rate", "monthly_exceptions",
            "rollback_test",
        }
        if any(checks.get(name) is not GateStatus.PASS for name in demand_names):
            demand_reasons.add(LaunchSemanticReason.DEMAND_GATE_FAILED)
        if (
            any(checks.get(name) is not GateStatus.PASS for name in operations_names)
            or p12.report.reconciliation.exact_faults_passed != 8
        ):
            operations_reasons.add(LaunchSemanticReason.OPERATIONS_GATE_FAILED)

    try:
        exact_gold_report = evaluate_goldset(
            item.gold.goldset,
            item.gold.candidates,
            at=item.gold.report.evaluated_at,
        )
        gold_ok = (
            exact_gold_report == item.gold.report
            and not exact_gold_report.quarantines
            and item.gold.report.evaluated_at <= at < item.gold.report.expires_at
            and verify_gold_report_attestation(
                item.gold.attestation,
                item.gold.report,
                item.gold.tco_qa_verifier,
                at=at,
            )
            and hash_rights_manifest(item.rights.plans)
            == item.gold.goldset.rights_bundle_sha256
            and tuple(candidate.plan for candidate in item.gold.candidates.plans)
            == item.rights.plans
        )
        if not gold_ok:
            gold_reasons.add(LaunchSemanticReason.GOLD_SET_INVALID)
    except (AttributeError, KeyError, TypeError, ValueError):
        gold_reasons.add(LaunchSemanticReason.GOLD_SET_INVALID)

    p15 = item.production
    try:
        exact_p15 = evaluate_production_integration_readiness(
            p15.evidence_bundle,
            p15.plan,
            p15.policy,
            p15.trust_store,
            at=p15.report.evaluated_at,
        )
        production_ok = (
            exact_p15 == p15.report
            and p15.report.decision
            is ProductionReadinessDecision.READY_FOR_HUMAN_GATE
            and p15.report.evaluated_at <= at < p15.report.expires_at
            and p15.tco_qa_attestation.decision
            is ReadinessAttestationDecision.ACCEPT
            and verify_production_tco_qa_attestation(
                p15.tco_qa_attestation,
                p15.report,
                p15.policy,
                p15.trust_store,
                at=at,
            )
            and _production_scope_matches(item.scope, p15.plan)
        )
        if not production_ok:
            production_reasons.add(
                LaunchSemanticReason.PRODUCTION_READINESS_INVALID
            )
    except (AttributeError, KeyError, TypeError, ValueError):
        production_reasons.add(LaunchSemanticReason.PRODUCTION_READINESS_INVALID)

    p10 = item.deployment_publication
    try:
        local_ok = ReleaseAssuranceVerifier(
            p10.assurance_policy,
            p10.assurance_trust_store,
            expected_policy_sha256=pinned.expected_assurance_policy_sha256,
            expected_trust_store_sha256=pinned.expected_assurance_trust_store_sha256,
        ).verify_local(
            p10.assurance_bundle,
            p10.local_assurance_report,
            at=at,
        )
        if (
            not local_ok
            or _text_sha256(p10.local_assurance_report.release_id)
            != item.scope.release_identity_sha256
            or p10.local_assurance_report.manifest_sha256
            != item.scope.release_manifest_sha256
            or p10.local_assurance_report.artifact_sha256
            != item.scope.release_artifact_sha256
        ):
            deployment_reasons.add(LaunchSemanticReason.LOCAL_ASSURANCE_INVALID)
    except (AttributeError, KeyError, TypeError, ValueError):
        deployment_reasons.add(LaunchSemanticReason.LOCAL_ASSURANCE_INVALID)

    if not _deployment_matches_scope(p10.deployment, item.scope, p15, at):
        deployment_reasons.add(LaunchSemanticReason.DEPLOYMENT_RECORD_INVALID)
    if not _publication_matches(
        p10.publication,
        p10.deployment,
        item.scope,
        rights_bundle,
        affiliate_bundle,
        p15,
        at,
    ):
        deployment_reasons.add(LaunchSemanticReason.PUBLICATION_RECORD_INVALID)

    rights_hash = hash_rights_semantic_packet(item.rights)
    affiliate_hash = hash_affiliate_semantic_packet(item.affiliate)
    measurement_hash = hash_measurement_semantic_packet(item.measurement)
    gold_hash = hash_gold_semantic_packet(item.gold)
    production_hash = hash_production_semantic_packet(item.production)
    deployment_hash = hash_deployment_publication_semantic_packet(p10)
    rights_expiry = rights_bundle.expires_at if rights_bundle else at
    affiliate_expiry = affiliate_bundle.expires_at if affiliate_bundle else at
    measurement_expiry = min(
        p12.report.expires_at,
        p12.bundle_index.expires_at,
        p12.demand_batch.summary.expires_at,
        p12.cohort_batch.expires_at,
        p12.operations_batch.summary.expires_at,
    )
    gold_expiry = min(
        item.gold.goldset.expires_at,
        item.gold.candidates.expires_at,
        item.gold.report.expires_at,
        item.gold.attestation.expires_at,
    )
    production_expiry = min(
        p15.plan.expires_at,
        p15.report.expires_at,
        p15.tco_qa_attestation.expires_at,
    )
    deployment_expiry = min(
        p10.local_assurance_report.expires_at,
        p10.deployment.expires_at,
        p10.publication.expires_at,
    )

    def append(
        gate: LaunchSemanticGate,
        components: tuple[LaunchSemanticComponent, ...],
        identity: str,
        subject: str,
        reasons: set[LaunchSemanticReason],
        expiry: datetime,
    ) -> None:
        if expiry <= at:
            reasons.add(LaunchSemanticReason.UPSTREAM_EXPIRY_INVALID)
        results.append(
            LaunchSemanticGateEvaluation(
                gate=gate,
                passed=not reasons,
                components=components,
                evidence_identity_sha256=identity,
                subject_sha256=subject,
                reasons=tuple(sorted(reasons, key=lambda item: item.value)),
                expires_at=expiry if not reasons else at,
            )
        )

    append(
        LaunchSemanticGate.RIGHTS_APPROVAL,
        (LaunchSemanticComponent(kind=LaunchSemanticComponentKind.RIGHTS_DECISION_RECORD, artifact_sha256=rights_hash),),
        rights_hash,
        rights_bundle.bundle_sha256 if rights_bundle else rights_hash,
        rights_reasons,
        rights_expiry,
    )
    append(
        LaunchSemanticGate.AFFILIATE_ACCEPTANCE,
        (LaunchSemanticComponent(kind=LaunchSemanticComponentKind.AFFILIATE_DECISION_RECORD, artifact_sha256=affiliate_hash),),
        affiliate_hash,
        affiliate_bundle.bundle_sha256 if affiliate_bundle else affiliate_hash,
        affiliate_reasons,
        affiliate_expiry,
    )
    append(
        LaunchSemanticGate.QUALIFIED_DEMAND,
        (LaunchSemanticComponent(kind=LaunchSemanticComponentKind.QUALIFIED_DEMAND_RECORD, artifact_sha256=_scoped_hash("qualified-demand", measurement_hash)),),
        _scoped_hash("qualified-demand-identity", measurement_hash),
        hash_signed_artifact(p12.report),
        demand_reasons,
        measurement_expiry,
    )
    append(
        LaunchSemanticGate.SHADOW_OPERATIONS,
        (LaunchSemanticComponent(kind=LaunchSemanticComponentKind.SHADOW_OPERATIONS_RECORD, artifact_sha256=_scoped_hash("shadow-operations", measurement_hash)),),
        _scoped_hash("shadow-operations-identity", measurement_hash),
        hash_signed_artifact(p12.operations_batch),
        operations_reasons,
        measurement_expiry,
    )
    append(
        LaunchSemanticGate.GOLD_SET_SOURCE_READINESS,
        (LaunchSemanticComponent(kind=LaunchSemanticComponentKind.GOLD_SOURCE_READINESS_RECORD, artifact_sha256=gold_hash),),
        gold_hash,
        item.gold.report.report_sha256,
        gold_reasons,
        gold_expiry,
    )
    append(
        LaunchSemanticGate.PRODUCTION_INTEGRATION_READINESS,
        (
            LaunchSemanticComponent(kind=LaunchSemanticComponentKind.P15_READINESS_REPORT, artifact_sha256=hash_production_readiness_report(p15.report)),
            LaunchSemanticComponent(kind=LaunchSemanticComponentKind.P15_TCO_QA_ATTESTATION, artifact_sha256=hash_production_tco_qa_attestation(p15.tco_qa_attestation)),
        ),
        production_hash,
        p15.plan.plan_sha256,
        production_reasons,
        production_expiry,
    )
    append(
        LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS,
        (
            LaunchSemanticComponent(kind=LaunchSemanticComponentKind.P10_LOCAL_ASSURANCE_REPORT, artifact_sha256=hash_local_assurance_report(p10.local_assurance_report)),
            LaunchSemanticComponent(kind=LaunchSemanticComponentKind.DEPLOYMENT_READINESS_RECORD, artifact_sha256=p10.deployment.record_sha256),
            LaunchSemanticComponent(kind=LaunchSemanticComponentKind.PUBLICATION_READINESS_RECORD, artifact_sha256=p10.publication.record_sha256),
        ),
        deployment_hash,
        p10.deployment.record_sha256,
        deployment_reasons,
        deployment_expiry,
    )

    passed = all(result.passed for result in results)
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "packet_sha256": item.packet_sha256,
        "authority_pins_sha256": pinned.pins_sha256,
        "evaluated_at": at,
        "gates": tuple(results),
        "passed": passed,
        "expires_at": min(result.expires_at for result in results) if passed else at,
        "authority_effect": "none",
        "authorizes_external_mutation": False,
    }
    provisional = LaunchSemanticEvaluation.model_construct(
        **values, evaluation_sha256="0" * 64
    )
    return LaunchSemanticEvaluation(
        **values, evaluation_sha256=hash_launch_semantic_evaluation(provisional)
    )


def _production_scope_matches(
    scope: LaunchSemanticScope, plan: ProductionIntegrationPlan
) -> bool:
    return (
        plan.property_record_sha256 == scope.property_record_sha256
        and plan.environment_identity_sha256 == scope.environment_identity_sha256
        and plan.release_manifest_sha256 == scope.release_manifest_sha256
        and plan.release_artifact_sha256 == scope.release_artifact_sha256
        and plan.deployment_candidate_sha256 == scope.deployment_candidate_sha256
        and plan.provider_target_sha256 == scope.provider_target_sha256
        and plan.expected_pre_state_sha256 == scope.expected_pre_state_sha256
    )


def _deployment_matches_scope(
    record: DeploymentReadinessRecord,
    scope: LaunchSemanticScope,
    production: ProductionSemanticPacket,
    at: datetime,
) -> bool:
    try:
        readback = _unique_production_evidence(
            production.evidence_bundle,
            ProductionIntegrationCheck.INDEPENDENT_READBACK,
        )
        rollback = _unique_production_evidence(
            production.evidence_bundle,
            ProductionIntegrationCheck.ROLLBACK_DISABLE,
        )
        readback_facts = readback.facts
        rollback_facts = rollback.facts
        facts = record.facts
        return (
            facts.property_record_sha256 == scope.property_record_sha256
            and facts.environment_identity_sha256
            == scope.environment_identity_sha256
            and facts.release_identity_sha256 == scope.release_identity_sha256
            and facts.release_manifest_sha256 == scope.release_manifest_sha256
            and facts.release_artifact_sha256 == scope.release_artifact_sha256
            and facts.deployment_candidate_sha256
            == scope.deployment_candidate_sha256
            and facts.production_integration_plan_sha256
            == production.plan.plan_sha256
            and facts.provider_target_sha256 == scope.provider_target_sha256
            and facts.expected_pre_state_sha256
            == scope.expected_pre_state_sha256
            and facts.independent_readback_evidence_sha256
            == hash_production_integration_evidence(readback)
            and facts.rollback_disable_evidence_sha256
            == hash_production_integration_evidence(rollback)
            and facts.staged_expected_state_sha256
            == readback_facts.expected_state_sha256
            == scope.expected_post_state_sha256
            and facts.staged_observed_state_sha256
            == readback_facts.observed_state_sha256
            == scope.expected_post_state_sha256
            and facts.rollback_active_state_sha256
            == rollback_facts.active_state_sha256
            == scope.expected_post_state_sha256
            and facts.rollback_expected_state_sha256
            == rollback_facts.disabled_state_sha256
            == scope.rollback_state_sha256
            and facts.rollback_observed_state_sha256
            == rollback_facts.final_observed_state_sha256
            == scope.rollback_state_sha256
            and rollback_facts.disable_policy_sha256
            == production.plan.p11_policy_sha256
            and rollback_facts.p11_disable_authority_sha256
            == production.plan.p11_policy_sha256
            and record.provenance
            is ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT
            and _verify_readiness_record(
                record,
                production.trust_store.independent_probe,
                hash_deployment_readiness_record,
                at=at,
                maximum_ttl_seconds=(
                    production.policy.maximum_live_control_ttl_seconds
                ),
            )
            and record.observed_at >= max(readback.observed_at, rollback.observed_at)
            and record.expires_at
            <= min(
                readback.expires_at,
                rollback.expires_at,
                production.plan.expires_at,
                production.report.expires_at,
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _publication_matches(
    record: PublicationReadinessRecord,
    deployment: DeploymentReadinessRecord,
    scope: LaunchSemanticScope,
    rights_bundle: Any,
    affiliate_bundle: Any,
    production: ProductionSemanticPacket,
    at: datetime,
) -> bool:
    try:
        facts = record.facts
        content = facts.content_readback
        indexability = facts.indexability_readback
        disclosure = facts.disclosure_readback
        readback_times = (
            content.observed_at,
            indexability.observed_at,
            disclosure.observed_at,
        )
        return (
            rights_bundle is not None
            and affiliate_bundle is not None
            and facts.property_record_sha256 == scope.property_record_sha256
            and facts.environment_identity_sha256
            == scope.environment_identity_sha256
            and facts.release_identity_sha256 == scope.release_identity_sha256
            and facts.release_manifest_sha256 == scope.release_manifest_sha256
            and facts.release_artifact_sha256 == scope.release_artifact_sha256
            and facts.deployment_candidate_sha256
            == scope.deployment_candidate_sha256
            and facts.deployment_readiness_record_sha256
            == deployment.record_sha256
            and facts.rights_bundle_sha256 == rights_bundle.bundle_sha256
            and facts.affiliate_bundle_sha256 == affiliate_bundle.bundle_sha256
            and facts.approved_partner_ids
            == affiliate_bundle.approved_partner_ids
            and content.expected_release_manifest_sha256
            == content.observed_release_manifest_sha256
            == scope.release_manifest_sha256
            and content.expected_release_artifact_sha256
            == content.observed_release_artifact_sha256
            == scope.release_artifact_sha256
            and disclosure.expected_legal_pages_sha256
            == disclosure.observed_legal_pages_sha256
            == scope.legal_pages_sha256
            and disclosure.expected_disclosure_sha256
            == disclosure.observed_disclosure_sha256
            == scope.affiliate_disclosure_sha256
            and record.provenance
            is ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT
            and _verify_readiness_record(
                record,
                production.trust_store.independent_probe,
                hash_publication_readiness_record,
                at=at,
                maximum_ttl_seconds=(
                    production.policy.maximum_live_control_ttl_seconds
                ),
            )
            and record.expires_at
            <= min(production.plan.expires_at, production.report.expires_at)
            and all(
                deployment.observed_at <= observed_at <= at
                and at - observed_at
                <= timedelta(
                    seconds=production.policy.maximum_live_control_ttl_seconds
                )
                for observed_at in readback_times
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _unique_production_evidence(
    bundle: ProductionIntegrationEvidenceBundle,
    check: ProductionIntegrationCheck,
) -> Any:
    matches = tuple(item for item in bundle.evidence if item.check is check)
    if len(matches) != 1:
        raise ValueError(f"expected one {check.value} evidence row")
    return matches[0]


def _readiness_signature_values(
    facts: DeploymentReadinessFacts | PublicationReadinessFacts,
    signing_key: Ed25519PrivateKey,
    verifier: Ed25519VerificationKey,
    *,
    provenance: ProductionEvidenceProvenance,
    observed_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    if type(facts) not in {DeploymentReadinessFacts, PublicationReadinessFacts}:
        raise TypeError("readiness facts must use an exact supported type")
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise TypeError("readiness signer must be an Ed25519 private key")
    selected_verifier = _copy(verifier, Ed25519VerificationKey)
    if selected_verifier.role is not SigningRole.PROVIDER_PROBE:
        raise LaunchSemanticInputError("readiness signer must use the provider-probe role")
    public_bytes = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if (
        hashlib.sha256(public_bytes).hexdigest()
        != selected_verifier.key_id_sha256
        or base64.urlsafe_b64encode(public_bytes).decode("ascii").rstrip("=")
        != selected_verifier.public_key_base64url
    ):
        raise LaunchSemanticInputError("readiness signing key does not match verifier")
    _require_utc(observed_at, "readiness observation timestamp")
    _require_utc(expires_at, "readiness expiry timestamp")
    if expires_at <= observed_at:
        raise LaunchSemanticInputError("readiness expiry must follow observation")
    return {
        "schema_version": "2.0",
        "facts": facts,
        "provenance": provenance,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "issuer": selected_verifier.issuer,
        "key_id_sha256": selected_verifier.key_id_sha256,
        "signer_role": SigningRole.PROVIDER_PROBE,
    }


def _sign_digest(signing_key: Ed25519PrivateKey, digest: str) -> str:
    return base64.urlsafe_b64encode(
        signing_key.sign(digest.encode("ascii"))
    ).decode("ascii").rstrip("=")


def _verify_readiness_record(
    record: DeploymentReadinessRecord | PublicationReadinessRecord,
    verifier: Ed25519VerificationKey,
    hash_function: Any,
    *,
    at: datetime,
    maximum_ttl_seconds: int,
) -> bool:
    try:
        selected_verifier = _copy(verifier, Ed25519VerificationKey)
        if (
            selected_verifier.role is not SigningRole.PROVIDER_PROBE
            or record.issuer != selected_verifier.issuer
            or record.key_id_sha256 != selected_verifier.key_id_sha256
            or record.signer_role is not SigningRole.PROVIDER_PROBE
            or record.provenance
            is not ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT
            or hash_function(record) != record.record_sha256
            or not record.observed_at <= at < record.expires_at
            or record.expires_at - record.observed_at
            > timedelta(seconds=maximum_ttl_seconds)
        ):
            return False
        signature = _decode_base64url(record.signature_base64url, expected_length=64)
        selected_verifier.public_key().verify(
            signature, record.record_sha256.encode("ascii")
        )
        return True
    except (InvalidSignature, AttributeError, TypeError, ValueError):
        return False


def _decode_base64url(value: str, *, expected_length: int) -> bytes:
    if not isinstance(value, str) or "=" in value:
        raise ValueError("base64url value must be unpadded text")
    padding = "=" * ((4 - len(value) % 4) % 4)
    decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != expected_length or canonical != value:
        raise ValueError("base64url value is not canonical")
    return decoded


def _scoped_hash(label: str, digest: str) -> str:
    return _canonical_sha256({"scope": label, "packet_sha256": digest})


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _hash_model(value: StrictModel, *, excluded: set[str] | None = None) -> str:
    return _canonical_sha256(value.model_dump(mode="json", exclude=excluded or set()))


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _copy(value: Any, expected_type: Any) -> Any:
    if type(value) is not expected_type:
        raise TypeError(f"expected exact {expected_type.__name__}")
    return expected_type.model_validate(value.model_dump())


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_utc(value: datetime, label: str) -> None:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


__all__ = [
    "AffiliateSemanticPacket",
    "DeploymentPublicationSemanticPacket",
    "DeploymentReadinessFacts",
    "DeploymentReadinessRecord",
    "GoldSemanticPacket",
    "LaunchSemanticAuthorityPins",
    "LaunchSemanticComponent",
    "LaunchSemanticComponentKind",
    "LaunchSemanticEvaluation",
    "LaunchSemanticGate",
    "LaunchSemanticGateEvaluation",
    "LaunchSemanticInputError",
    "LaunchSemanticPacket",
    "LaunchSemanticReason",
    "LaunchSemanticScope",
    "MeasurementSemanticPacket",
    "ProductionSemanticPacket",
    "PublicationContentReadback",
    "PublicationDisclosureReadback",
    "PublicationIndexabilityReadback",
    "PublicationReadinessFacts",
    "PublicationReadinessRecord",
    "REQUIRED_LAUNCH_SEMANTIC_GATES",
    "RightsSemanticPacket",
    "build_launch_semantic_authority_pins",
    "evaluate_launch_semantics",
    "hash_affiliate_semantic_packet",
    "hash_deployment_publication_semantic_packet",
    "hash_deployment_readiness_record",
    "hash_gold_semantic_packet",
    "hash_launch_semantic_authority_pins",
    "hash_launch_semantic_evaluation",
    "hash_launch_semantic_packet",
    "hash_measurement_semantic_packet",
    "hash_production_semantic_packet",
    "hash_publication_readiness_record",
    "hash_rights_semantic_packet",
    "sign_deployment_readiness_record",
    "sign_publication_readiness_record",
]
