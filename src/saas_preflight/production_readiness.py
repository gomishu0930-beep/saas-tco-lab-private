"""Offline production-integration readiness and reconciliation boundary.

The models in this module are intentionally hash-only.  They cannot contain a
provider URL, credential, account identifier, deployment command, or network
client.  A locally passing synthetic bundle proves contract wiring only; it is
never evidence that a real environment is ready.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Annotated, Any, Callable, Iterator, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import Ed25519VerificationKey, SigningRole
from .models import Sha256, Slug, StrictModel


class ProductionReadinessInputError(ValueError):
    """An untrusted P15 artifact failed strict local revalidation."""


class ProductionIntegrationCheck(str, Enum):
    BACKUP_RESTORE = "backup_restore"
    EGRESS_ALLOWLIST = "egress_allowlist"
    EXTERNAL_MONOTONIC_ANCHOR = "external_monotonic_anchor"
    INDEPENDENT_READBACK = "independent_readback"
    KMS_IDENTITY_SEPARATION = "kms_identity_separation"
    PROVIDER_CONDITIONAL_MUTATION = "provider_conditional_mutation"
    PROVIDER_IDEMPOTENCY_RETENTION = "provider_idempotency_retention"
    PROVIDER_RECEIPT_LOOKUP = "provider_receipt_lookup"
    ROLLBACK_DISABLE = "rollback_disable"
    SHARED_DURABLE_STORE_FENCING = "shared_durable_store_fencing"
    TRUSTED_CLOCK = "trusted_clock"


REQUIRED_PRODUCTION_INTEGRATION_CHECKS: tuple[ProductionIntegrationCheck, ...] = tuple(
    sorted(ProductionIntegrationCheck, key=lambda item: item.value)
)


class ProductionFactsKind(str, Enum):
    BACKUP_RESTORE = "backup_restore"
    EGRESS_ALLOWLIST = "egress_allowlist"
    EXTERNAL_MONOTONIC_ANCHOR = "external_monotonic_anchor"
    INDEPENDENT_READBACK = "independent_readback"
    KMS_IDENTITY_SEPARATION = "kms_identity_separation"
    PROVIDER_CONDITIONAL_MUTATION = "provider_conditional_mutation"
    PROVIDER_IDEMPOTENCY_RETENTION = "provider_idempotency_retention"
    PROVIDER_RECEIPT_LOOKUP = "provider_receipt_lookup"
    ROLLBACK_DISABLE = "rollback_disable"
    SHARED_DURABLE_STORE_FENCING = "shared_durable_store_fencing"
    TRUSTED_CLOCK = "trusted_clock"


class ProductionEvidenceProvenance(str, Enum):
    PRODUCTION_ENVIRONMENT = "production_environment"
    SYNTHETIC_CONTRACT = "synthetic_contract"


_EXPECTED_FACTS_KIND: dict[ProductionIntegrationCheck, ProductionFactsKind] = {
    check: ProductionFactsKind(check.value) for check in ProductionIntegrationCheck
}


_EXPECTED_SIGNING_ROLE: dict[ProductionIntegrationCheck, SigningRole] = {
    ProductionIntegrationCheck.PROVIDER_CONDITIONAL_MUTATION: SigningRole.PROVIDER_CONFORMANCE,
    ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION: SigningRole.PROVIDER_CONFORMANCE,
    ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP: SigningRole.PROVIDER_CONFORMANCE,
    ProductionIntegrationCheck.INDEPENDENT_READBACK: SigningRole.PROVIDER_PROBE,
    ProductionIntegrationCheck.KMS_IDENTITY_SEPARATION: SigningRole.SECURITY_AUDITOR,
    ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR: SigningRole.STORAGE_AUDITOR,
    ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING: SigningRole.STORAGE_AUDITOR,
    ProductionIntegrationCheck.TRUSTED_CLOCK: SigningRole.TIME_AUDITOR,
    ProductionIntegrationCheck.EGRESS_ALLOWLIST: SigningRole.NETWORK_AUDITOR,
    ProductionIntegrationCheck.BACKUP_RESTORE: SigningRole.RECOVERY_AUDITOR,
    ProductionIntegrationCheck.ROLLBACK_DISABLE: SigningRole.RECOVERY_AUDITOR,
}


class ProviderConditionalMutationFacts(StrictModel):
    kind: Literal[ProductionFactsKind.PROVIDER_CONDITIONAL_MUTATION] = (
        ProductionFactsKind.PROVIDER_CONDITIONAL_MUTATION
    )
    matching_precondition_case_sha256: Sha256
    stale_precondition_case_sha256: Sha256
    lower_fence_case_sha256: Sha256
    concurrent_precondition_case_sha256: Sha256
    scenarios_expected: Literal[4] = 4
    scenarios_executed: int = Field(ge=0, le=4)
    accepted_writes: int = Field(ge=0, le=4)
    stale_precondition_rejections: int = Field(ge=0, le=4)
    lower_fence_rejections: int = Field(ge=0, le=4)
    concurrent_winners: int = Field(ge=0, le=4)
    replay_receipt_matches: int = Field(ge=0, le=4)
    duplicate_side_effects: int = Field(ge=0, le=4)
    result_artifact_sha256: Sha256


class ProviderIdempotencyRetentionFacts(StrictModel):
    kind: Literal[ProductionFactsKind.PROVIDER_IDEMPOTENCY_RETENTION] = (
        ProductionFactsKind.PROVIDER_IDEMPOTENCY_RETENTION
    )
    idempotency_key_sha256: Sha256
    initial_request_sha256: Sha256
    replay_request_sha256: Sha256
    conflicting_request_sha256: Sha256
    conflict_case_sha256: Sha256
    initial_receipt_sha256: Sha256
    replay_receipt_sha256: Sha256
    initial_audit_sha256: Sha256
    replay_audit_sha256: Sha256
    observed_retention_seconds: int = Field(ge=0, le=31_536_000)
    replay_attempts: int = Field(ge=1, le=10_000)
    matching_receipts: int = Field(ge=0, le=10_000)
    duplicate_side_effects: int = Field(ge=0, le=10_000)
    conflicting_request_rejections: int = Field(ge=0, le=10_000)
    conflicting_request_side_effects: int = Field(ge=0, le=10_000)
    result_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_distinct_conflicting_request(self) -> Self:
        if self.conflicting_request_sha256 == self.initial_request_sha256:
            raise ValueError("conflicting request must differ from the initial request")
        return self


class ProviderReceiptLookupFacts(StrictModel):
    kind: Literal[ProductionFactsKind.PROVIDER_RECEIPT_LOOKUP] = (
        ProductionFactsKind.PROVIDER_RECEIPT_LOOKUP
    )
    known_query_sha256: Sha256
    expected_receipt_sha256: Sha256
    observed_receipt_sha256: Sha256
    unknown_query_sha256: Sha256
    unknown_result_sha256: Sha256
    unknown_result_kind: Literal["not_found"] = "not_found"
    lookup_attempts: int = Field(ge=1, le=10_000)
    receipts_found: int = Field(ge=0, le=10_000)
    receipt_mismatches: int = Field(ge=0, le=10_000)
    unauthorized_receipts_returned: int = Field(ge=0, le=10_000)
    known_lookup_lag_milliseconds: int = Field(ge=0, le=86_400_000)
    unknown_lookup_mutation_effects: int = Field(ge=0, le=10_000)
    result_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_distinct_unknown_lookup(self) -> Self:
        if self.unknown_query_sha256 == self.known_query_sha256:
            raise ValueError("unknown query must differ from the known query")
        if self.unknown_result_sha256 == self.expected_receipt_sha256:
            raise ValueError("unknown lookup must not return the expected receipt")
        return self


class IndependentReadbackFacts(StrictModel):
    kind: Literal[ProductionFactsKind.INDEPENDENT_READBACK] = (
        ProductionFactsKind.INDEPENDENT_READBACK
    )
    adapter_identity_sha256: Sha256
    reader_identity_sha256: Sha256
    reader_acl_sha256: Sha256
    provider_receipt_sha256: Sha256
    journal_record_sha256: Sha256
    expected_state_sha256: Sha256
    observed_state_sha256: Sha256
    readbacks_attempted: int = Field(ge=1, le=10_000)
    readbacks_matched: int = Field(ge=0, le=10_000)
    readback_mismatches: int = Field(ge=0, le=10_000)
    readback_lag_milliseconds: int = Field(ge=0, le=86_400_000)
    result_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_independent_identity(self) -> Self:
        if self.adapter_identity_sha256 == self.reader_identity_sha256:
            raise ValueError("readback identity must be independent from adapter identity")
        return self


class KmsIdentitySeparationFacts(StrictModel):
    kind: Literal[ProductionFactsKind.KMS_IDENTITY_SEPARATION] = (
        ProductionFactsKind.KMS_IDENTITY_SEPARATION
    )
    provider_identity_sha256: Sha256
    probe_identity_sha256: Sha256
    controller_identity_sha256: Sha256
    runner_identity_sha256: Sha256
    pairwise_assertions_expected: Literal[6] = 6
    pairwise_assertions_checked: int = Field(ge=0, le=6)
    separation_violations: int = Field(ge=0, le=6)
    provider_permission_profile_sha256: Sha256
    probe_permission_profile_sha256: Sha256
    controller_permission_profile_sha256: Sha256
    runner_permission_profile_sha256: Sha256
    export_policy: Literal["non_exportable"] = "non_exportable"
    key_policy_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_distinct_identities(self) -> Self:
        identities = {
            self.provider_identity_sha256,
            self.probe_identity_sha256,
            self.controller_identity_sha256,
            self.runner_identity_sha256,
        }
        if len(identities) != 4:
            raise ValueError("provider, probe, controller, and runner identities must differ")
        return self


class ExternalMonotonicAnchorFacts(StrictModel):
    kind: Literal[ProductionFactsKind.EXTERNAL_MONOTONIC_ANCHOR] = (
        ProductionFactsKind.EXTERNAL_MONOTONIC_ANCHOR
    )
    anchor_identity_sha256: Sha256
    store_identity_sha256: Sha256
    advance_case_sha256: Sha256
    rollback_reject_case_sha256: Sha256
    equivocation_reject_case_sha256: Sha256
    authoritative_readback_case_sha256: Sha256
    revision_before: int = Field(ge=0, le=9_223_372_036_854_775_807)
    revision_after: int = Field(ge=1, le=9_223_372_036_854_775_807)
    samples_observed: int = Field(ge=1, le=10_000)
    strictly_advanced_transitions: int = Field(ge=0, le=9_999)
    regressions: int = Field(ge=0, le=10_000)
    replay_rejections: int = Field(ge=0, le=10_000)
    result_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_external_identity(self) -> Self:
        if self.anchor_identity_sha256 == self.store_identity_sha256:
            raise ValueError("anchor identity must be external to the production store")
        return self


class TrustedClockFacts(StrictModel):
    kind: Literal[ProductionFactsKind.TRUSTED_CLOCK] = ProductionFactsKind.TRUSTED_CLOCK
    clock_source_identity_sha256s: tuple[Sha256, ...] = Field(min_length=1, max_length=10)
    failure_domain_sha256s: tuple[Sha256, ...] = Field(min_length=1, max_length=10)
    signed_sample_sequence_sha256: Sha256
    rollback_reject_case_sha256: Sha256
    future_reject_case_sha256: Sha256
    samples_observed: int = Field(ge=1, le=100_000)
    maximum_absolute_offset_milliseconds: int = Field(ge=0, le=86_400_000)
    maximum_uncertainty_milliseconds: int = Field(ge=0, le=86_400_000)
    backward_steps: int = Field(ge=0, le=100_000)
    out_of_bound_samples: int = Field(ge=0, le=100_000)
    result_artifact_sha256: Sha256

    @field_validator("clock_source_identity_sha256s", "failure_domain_sha256s")
    @classmethod
    def require_canonical_clock_identities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("clock identities must be canonical and unique")
        return value


class SharedDurableStoreFencingFacts(StrictModel):
    kind: Literal[ProductionFactsKind.SHARED_DURABLE_STORE_FENCING] = (
        ProductionFactsKind.SHARED_DURABLE_STORE_FENCING
    )
    store_identity_sha256: Sha256
    worker_identity_sha256s: tuple[Sha256, ...] = Field(min_length=2, max_length=100)
    failure_domain_sha256s: tuple[Sha256, ...] = Field(min_length=2, max_length=20)
    lower_fence_reject_case_sha256: Sha256
    old_owner_reject_case_sha256: Sha256
    owner_death_reopen_case_sha256: Sha256
    concurrent_workers: int = Field(ge=1, le=10_000)
    claim_contenders: int = Field(ge=1, le=100_000)
    winning_claims: int = Field(ge=0, le=100_000)
    stale_writer_rejections: int = Field(ge=0, le=100_000)
    unfenced_successful_writes: int = Field(ge=0, le=100_000)
    result_artifact_sha256: Sha256

    @field_validator("worker_identity_sha256s", "failure_domain_sha256s")
    @classmethod
    def require_canonical_store_identities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("store identities must be canonical and unique")
        return value


class EgressAllowlistFacts(StrictModel):
    kind: Literal[ProductionFactsKind.EGRESS_ALLOWLIST] = (
        ProductionFactsKind.EGRESS_ALLOWLIST
    )
    allowlist_policy_sha256: Sha256
    approved_destination_sha256s: tuple[Sha256, ...] = Field(min_length=1, max_length=100)
    observed_destination_sha256s: tuple[Sha256, ...] = Field(min_length=1, max_length=100)
    method_policy_sha256: Sha256
    tls_profile_sha256: Sha256
    deny_dns_case_sha256: Sha256
    deny_private_range_case_sha256: Sha256
    deny_metadata_case_sha256: Sha256
    deny_wildcard_case_sha256: Sha256
    approved_attempts: int = Field(ge=1, le=100_000)
    blocked_unapproved_attempts: int = Field(ge=0, le=100_000)
    successful_unapproved_attempts: int = Field(ge=0, le=100_000)
    result_artifact_sha256: Sha256

    @field_validator("approved_destination_sha256s", "observed_destination_sha256s")
    @classmethod
    def require_canonical_destinations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("destination identities must be canonical and unique")
        return value


class BackupRestoreFacts(StrictModel):
    kind: Literal[ProductionFactsKind.BACKUP_RESTORE] = ProductionFactsKind.BACKUP_RESTORE
    source_snapshot_sha256: Sha256
    restored_snapshot_sha256: Sha256
    source_head_sha256: Sha256
    restored_head_sha256: Sha256
    source_journal_set_sha256: Sha256
    restored_journal_set_sha256: Sha256
    source_anchor_sha256: Sha256
    restored_anchor_sha256: Sha256
    isolated_restore_target_sha256: Sha256
    production_store_identity_sha256: Sha256
    production_pointer_before_sha256: Sha256
    production_pointer_after_sha256: Sha256
    tampered_backup_reject_case_sha256: Sha256
    older_backup_reject_case_sha256: Sha256
    restore_attempts: int = Field(ge=1, le=10_000)
    successful_restores: int = Field(ge=0, le=10_000)
    integrity_mismatches: int = Field(ge=0, le=10_000)
    corrupt_backup_rejections: int = Field(ge=0, le=10_000)
    observed_rpo_seconds: int = Field(ge=0, le=31_536_000)
    observed_rto_seconds: int = Field(ge=0, le=31_536_000)
    backup_age_seconds: int = Field(ge=0, le=31_536_000)
    restore_drill_age_seconds: int = Field(ge=0, le=31_536_000)
    authoritative_resume_event_gap: int = Field(ge=0, le=1_000_000)
    result_artifact_sha256: Sha256


class RollbackDisableFacts(StrictModel):
    kind: Literal[ProductionFactsKind.ROLLBACK_DISABLE] = (
        ProductionFactsKind.ROLLBACK_DISABLE
    )
    disable_policy_sha256: Sha256
    active_state_sha256: Sha256
    disabled_state_sha256: Sha256
    final_observed_state_sha256: Sha256
    p11_disable_authority_sha256: Sha256
    provider_disable_receipt_sha256: Sha256
    independent_probe_receipt_sha256: Sha256
    running_lane_case_sha256: Sha256
    stop_lane_case_sha256: Sha256
    fault_exercises: int = Field(ge=1, le=10_000)
    completed_disables: int = Field(ge=0, le=10_000)
    maximum_disable_latency_milliseconds: int = Field(ge=0, le=86_400_000)
    post_disable_mutation_attempts: int = Field(ge=1, le=100_000)
    successful_post_disable_mutations: int = Field(ge=0, le=100_000)
    activation_events_emitted: int = Field(ge=0, le=100_000)
    retry_events_emitted: int = Field(ge=0, le=100_000)
    final_state_artifact_sha256: Sha256

    @model_validator(mode="after")
    def require_real_disable_transition(self) -> Self:
        if self.active_state_sha256 == self.disabled_state_sha256:
            raise ValueError("disable must change active state to disabled state")
        return self


ProductionIntegrationFacts = Annotated[
    ProviderConditionalMutationFacts
    | ProviderIdempotencyRetentionFacts
    | ProviderReceiptLookupFacts
    | IndependentReadbackFacts
    | KmsIdentitySeparationFacts
    | ExternalMonotonicAnchorFacts
    | TrustedClockFacts
    | SharedDurableStoreFencingFacts
    | EgressAllowlistFacts
    | BackupRestoreFacts
    | RollbackDisableFacts,
    Field(discriminator="kind"),
]


class ProductionIntegrationTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    controller: Ed25519VerificationKey
    provider_conformance: Ed25519VerificationKey
    independent_probe: Ed25519VerificationKey
    security_auditor: Ed25519VerificationKey
    storage_auditor: Ed25519VerificationKey
    time_auditor: Ed25519VerificationKey
    network_auditor: Ed25519VerificationKey
    recovery_auditor: Ed25519VerificationKey
    tco_qa: Ed25519VerificationKey
    environment_human: Ed25519VerificationKey

    @model_validator(mode="after")
    def require_roles_and_separation(self) -> Self:
        expected = (
            (self.controller, SigningRole.CONTROLLER),
            (self.provider_conformance, SigningRole.PROVIDER_CONFORMANCE),
            (self.independent_probe, SigningRole.PROVIDER_PROBE),
            (self.security_auditor, SigningRole.SECURITY_AUDITOR),
            (self.storage_auditor, SigningRole.STORAGE_AUDITOR),
            (self.time_auditor, SigningRole.TIME_AUDITOR),
            (self.network_auditor, SigningRole.NETWORK_AUDITOR),
            (self.recovery_auditor, SigningRole.RECOVERY_AUDITOR),
            (self.tco_qa, SigningRole.TCO_QA),
            (self.environment_human, SigningRole.HUMAN_APPROVER),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("production integration trust-store role mismatch")
        if len({key.key_id_sha256 for key, _ in expected}) != len(expected):
            raise ValueError("every production evidence and approval role requires a distinct key")
        return self


class ProductionIntegrationPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: Slug
    trust_store_sha256: Sha256
    maximum_evidence_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_live_control_ttl_seconds: int = Field(ge=1, le=3_600)
    maximum_recovery_evidence_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_report_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_tco_attestation_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_human_approval_ttl_seconds: int = Field(ge=1, le=604_800)
    maximum_authorization_ttl_seconds: int = Field(ge=1, le=86_400)
    minimum_idempotency_retention_seconds: int = Field(ge=1, le=31_536_000)
    minimum_replay_attempts: int = Field(ge=2, le=10_000)
    minimum_receipt_lookup_attempts: int = Field(ge=2, le=10_000)
    maximum_receipt_lookup_lag_milliseconds: int = Field(ge=1, le=3_600_000)
    minimum_independent_readbacks: int = Field(ge=2, le=10_000)
    maximum_independent_readback_lag_milliseconds: int = Field(ge=1, le=3_600_000)
    minimum_anchor_samples: int = Field(ge=3, le=10_000)
    maximum_clock_offset_milliseconds: int = Field(ge=0, le=60_000)
    minimum_clock_sources: int = Field(ge=3, le=10)
    minimum_clock_failure_domains: int = Field(ge=2, le=10)
    minimum_fencing_workers: int = Field(ge=2, le=10_000)
    minimum_fencing_failure_domains: int = Field(ge=2, le=20)
    minimum_unapproved_egress_attempts: int = Field(ge=1, le=10_000)
    minimum_restore_attempts: int = Field(ge=1, le=10_000)
    maximum_rpo_seconds: int = Field(ge=0, le=2_592_000)
    maximum_rto_seconds: int = Field(ge=1, le=604_800)
    maximum_backup_age_seconds: int = Field(ge=1, le=604_800)
    maximum_restore_drill_age_seconds: int = Field(ge=1, le=2_592_000)
    minimum_rollback_exercises: int = Field(ge=1, le=10_000)
    maximum_disable_latency_milliseconds: int = Field(ge=1, le=86_400_000)


class ProductionIntegrationRequirement(StrictModel):
    check: ProductionIntegrationCheck
    facts_kind: ProductionFactsKind
    evidence_identity_sha256: Sha256
    signer_role: SigningRole
    signer_key_id_sha256: Sha256
    subject_sha256: Sha256
    command_sha256: Sha256
    tool_name: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"
    )
    tool_version: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"
    )

    @model_validator(mode="after")
    def require_check_specific_kind(self) -> Self:
        if self.facts_kind is not _EXPECTED_FACTS_KIND[self.check]:
            raise ValueError("production requirement facts kind does not match check")
        if self.signer_role is not _EXPECTED_SIGNING_ROLE[self.check]:
            raise ValueError("production requirement signer role does not match check")
        return self


class ProductionIntegrationPlan(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    plan_id: Slug
    integration_policy_sha256: Sha256
    trust_store_sha256: Sha256
    property_record_sha256: Sha256
    environment_identity_sha256: Sha256
    provider_account_sha256: Sha256
    p11_policy_sha256: Sha256
    p11_store_identity_sha256: Sha256
    p13_policy_sha256: Sha256
    p13_store_identity_sha256: Sha256
    reconciliation_ledger_store_sha256: Sha256
    release_artifact_sha256: Sha256
    release_manifest_sha256: Sha256
    adapter_closure_sha256: Sha256
    probe_closure_sha256: Sha256
    provider_capability_profile_sha256: Sha256
    deployment_candidate_sha256: Sha256
    provider_target_sha256: Sha256
    expected_pre_state_sha256: Sha256
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    requirements: tuple[ProductionIntegrationRequirement, ...] = Field(
        min_length=11, max_length=11
    )
    plan_sha256: Sha256

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        checks = tuple(requirement.check for requirement in self.requirements)
        if checks != REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
            raise ValueError("plan requirements must equal the canonical P15 check set")
        if len({item.evidence_identity_sha256 for item in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("every evidence identity must be distinct")
        if not (self.issued_at <= self.not_before < self.expires_at):
            raise ValueError("plan times must be issued_at <= not_before < expires_at")
        if self.plan_sha256 != hash_production_integration_plan(self):
            raise ValueError("plan_sha256 does not match canonical plan")
        return self

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production integration plan timestamp")
        return value


class ProductionIntegrationEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_id: Slug
    check: ProductionIntegrationCheck
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    requirement_sha256: Sha256
    evidence_identity_sha256: Sha256
    environment_identity_sha256: Sha256
    subject_sha256: Sha256
    command_sha256: Sha256
    tool_name: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"
    )
    tool_version: str = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"
    )
    provenance: ProductionEvidenceProvenance
    facts: ProductionIntegrationFacts
    observed_at: datetime
    expires_at: datetime
    runner_issuer: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    runner_key_id_sha256: Sha256
    runner_role: SigningRole
    evidence_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production evidence timestamp")
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("production evidence expiry must follow observation")
        if self.facts.kind is not _EXPECTED_FACTS_KIND[self.check]:
            raise ValueError("production evidence facts kind does not match check")
        if self.evidence_sha256 != hash_production_integration_evidence(self):
            raise ValueError("evidence_sha256 does not match canonical evidence")
        return self


class ProductionIntegrationEvidenceBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    evidence: tuple[ProductionIntegrationEvidence, ...] = Field(max_length=22)
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        order_keys = tuple(
            (item.check.value, item.evidence_id, item.evidence_sha256)
            for item in self.evidence
        )
        if order_keys != tuple(sorted(order_keys)):
            raise ValueError("production evidence must be in canonical order")
        binding = (self.plan_sha256, self.integration_policy_sha256)
        if any(
            (item.plan_sha256, item.integration_policy_sha256) != binding
            for item in self.evidence
        ):
            raise ValueError("every evidence item must match the bundle binding")
        if self.bundle_sha256 != hash_production_integration_bundle(self):
            raise ValueError("bundle_sha256 does not match canonical bundle")
        return self


class ProductionReadinessDecision(str, Enum):
    READY_FOR_HUMAN_GATE = "ready_for_human_gate"
    STOP = "stop"


class ProductionReadinessReason(str, Enum):
    CHECK_FAILED = "check_failed"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    EVIDENCE_EXPIRED = "evidence_expired"
    EVIDENCE_FUTURE = "evidence_future"
    EVIDENCE_SIGNATURE_INVALID = "evidence_signature_invalid"
    EVIDENCE_TTL_EXCEEDED = "evidence_ttl_exceeded"
    MISSING_EVIDENCE = "missing_evidence"
    PLAN_EXPIRED = "plan_expired"
    PLAN_FUTURE = "plan_future"
    REQUIREMENT_MISMATCH = "requirement_mismatch"
    SYNTHETIC_EVIDENCE = "synthetic_evidence"


class ProductionReadinessFinding(StrictModel):
    check: ProductionIntegrationCheck
    reason: ProductionReadinessReason


class ProductionReadinessReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: ProductionReadinessDecision
    evaluated_at: datetime
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    trust_store_sha256: Sha256
    evidence_bundle_sha256: Sha256
    findings: tuple[ProductionReadinessFinding, ...]
    passed_checks: tuple[ProductionIntegrationCheck, ...]
    failed_checks: tuple[ProductionIntegrationCheck, ...]
    expires_at: datetime
    synthetic_evidence_is_not_production_authority: Literal[True] = True
    report_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production readiness report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        finding_keys = tuple((item.check.value, item.reason.value) for item in self.findings)
        if finding_keys != tuple(sorted(set(finding_keys))):
            raise ValueError("production readiness findings must be canonical and unique")
        if self.passed_checks != tuple(sorted(set(self.passed_checks), key=lambda x: x.value)):
            raise ValueError("passed checks must be canonical and unique")
        if self.failed_checks != tuple(sorted(set(self.failed_checks), key=lambda x: x.value)):
            raise ValueError("failed checks must be canonical and unique")
        if set(self.passed_checks) | set(self.failed_checks) != set(
            REQUIRED_PRODUCTION_INTEGRATION_CHECKS
        ):
            raise ValueError("report must classify every P15 check")
        if set(self.passed_checks) & set(self.failed_checks):
            raise ValueError("a P15 check cannot both pass and fail")
        expected = (
            ProductionReadinessDecision.READY_FOR_HUMAN_GATE
            if not self.failed_checks and not self.findings
            else ProductionReadinessDecision.STOP
        )
        if self.decision is not expected:
            raise ValueError("production readiness decision does not match findings")
        if self.decision is ProductionReadinessDecision.READY_FOR_HUMAN_GATE and self.expires_at <= self.evaluated_at:
            raise ValueError("ready-for-Human-gate report must expire after evaluation")
        if self.report_sha256 != hash_production_readiness_report(self):
            raise ValueError("report_sha256 does not match canonical report")
        return self


class ReadinessAttestationDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


class EnvironmentApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ProductionAttestationScope(str, Enum):
    TCO_QA_ACCEPTANCE = "production_integration_tco_qa_acceptance"
    HUMAN_ENVIRONMENT_APPROVAL = "production_environment_human_approval"
    CONTROLLER_BOOTSTRAP = "production_adapter_bootstrap"


class ProductionTcoQaAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA] = SigningRole.TCO_QA
    scope: Literal[ProductionAttestationScope.TCO_QA_ACCEPTANCE] = (
        ProductionAttestationScope.TCO_QA_ACCEPTANCE
    )
    decision: ReadinessAttestationDecision
    report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "TCO/QA attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        _validate_signed_payload(self, "TCO/QA attestation")
        return self


class ProductionHumanEnvironmentApproval(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER] = SigningRole.HUMAN_APPROVER
    scope: Literal[ProductionAttestationScope.HUMAN_ENVIRONMENT_APPROVAL] = (
        ProductionAttestationScope.HUMAN_ENVIRONMENT_APPROVAL
    )
    decision: EnvironmentApprovalDecision
    report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    environment_identity_sha256: Sha256
    deployment_candidate_sha256: Sha256
    decision_record_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "Human environment approval timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        _validate_signed_payload(self, "Human environment approval")
        return self


class ProductionBootstrapAuthorization(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    controller_key_id_sha256: Sha256
    signer_role: Literal[SigningRole.CONTROLLER] = SigningRole.CONTROLLER
    scope: Literal[ProductionAttestationScope.CONTROLLER_BOOTSTRAP] = (
        ProductionAttestationScope.CONTROLLER_BOOTSTRAP
    )
    report_sha256: Sha256
    evidence_bundle_sha256: Sha256
    tco_qa_attestation_sha256: Sha256
    human_approval_sha256: Sha256
    plan_sha256: Sha256
    integration_policy_sha256: Sha256
    environment_identity_sha256: Sha256
    deployment_candidate_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "bootstrap authorization timestamp")
        return value

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        _validate_signed_payload(self, "bootstrap authorization")
        return self


class ProductionReadinessAuthorityPins(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    expected_trust_store_sha256: Sha256
    expected_integration_policy_sha256: Sha256
    expected_plan_sha256: Sha256
    expected_report_sha256: Sha256
    expected_authorization_sha256: Sha256


class P13TerminalState(str, Enum):
    STOP = "stop"
    UNKNOWN = "unknown"


class ProviderObservedState(str, Enum):
    APPLIED = "applied"
    NOT_APPLIED = "not_applied"
    AMBIGUOUS = "ambiguous"


class ProductionReconciliationFacts(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_sha256: Sha256
    p13_store_identity_sha256: Sha256
    p13_result_sha256: Sha256
    p13_terminal_state: P13TerminalState
    stopped_revision: int = Field(ge=0, le=9_223_372_036_854_775_807)
    stopped_head_sha256: Sha256
    stop_reason_sha256: Sha256
    provider_observed_state: ProviderObservedState
    provider_result_receipt_sha256: Sha256
    journaled_provider_receipt_sha256: Sha256
    provider_probe_receipt_sha256: Sha256
    receipt_lookup_evidence_sha256: Sha256
    independent_readback_evidence_sha256: Sha256
    observed_at: datetime
    expires_at: datetime
    producer_issuer: Slug
    producer_key_id_sha256: Sha256
    producer_role: Literal[SigningRole.RECOVERY_AUDITOR] = SigningRole.RECOVERY_AUDITOR
    facts_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "reconciliation timestamp")
        return value

    @model_validator(mode="after")
    def validate_facts(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("reconciliation expiry must follow observation")
        if (
            self.provider_observed_state is ProviderObservedState.APPLIED
            and self.provider_result_receipt_sha256
            != self.journaled_provider_receipt_sha256
        ):
            raise ValueError("applied provider state requires the exact journaled receipt")
        if self.facts_sha256 != hash_production_reconciliation_facts(self):
            raise ValueError("facts_sha256 does not match canonical reconciliation facts")
        return self


class ProductionReconciliationAction(str, Enum):
    KEEP_STOP = "keep_stop"
    MANUAL_REMEDIATION = "manual_remediation"
    REQUEST_HUMAN_DISABLE = "request_human_disable"


class ProductionReconciliationReason(str, Enum):
    AMBIGUOUS_PROVIDER_STATE = "ambiguous_provider_state"
    EXISTING_STOP_PRESERVED = "existing_stop_preserved"
    NON_APPLIED_FACT_PRESERVED = "non_applied_fact_preserved"
    UNKNOWN_NOT_PROMOTED = "unknown_not_promoted"


class ProductionReconciliationReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: Literal[ProductionReadinessDecision.STOP] = ProductionReadinessDecision.STOP
    action: ProductionReconciliationAction
    reason: ProductionReconciliationReason
    plan_sha256: Sha256
    p13_result_sha256: Sha256
    reconciliation_facts_sha256: Sha256
    evaluated_at: datetime
    report_sha256: Sha256

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "reconciliation report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.report_sha256 != hash_production_reconciliation_report(self):
            raise ValueError("report_sha256 does not match canonical reconciliation report")
        return self


class ProductionReconciliationRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    ledger_store_id_sha256: Sha256
    plan_sha256: Sha256
    revision: int = Field(ge=1, le=9_223_372_036_854_775_807)
    previous_head_sha256: Sha256
    facts_sha256: Sha256
    report_sha256: Sha256
    p13_result_sha256: Sha256
    recorded_at: datetime
    record_sha256: Sha256

    @field_validator("recorded_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "reconciliation record timestamp")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.record_sha256 != hash_production_reconciliation_record(self):
            raise ValueError("record_sha256 does not match reconciliation record")
        return self


def hash_production_integration_trust_store(
    trust_store: ProductionIntegrationTrustStore,
) -> str:
    return _canonical_sha256(trust_store.model_dump(mode="json"))


def hash_production_integration_policy(policy: ProductionIntegrationPolicy) -> str:
    return _canonical_sha256(policy.model_dump(mode="json"))


def hash_production_integration_requirement(
    requirement: ProductionIntegrationRequirement,
) -> str:
    return _canonical_sha256(requirement.model_dump(mode="json"))


def hash_production_integration_plan(plan: ProductionIntegrationPlan) -> str:
    return _canonical_sha256(plan.model_dump(mode="json", exclude={"plan_sha256"}))


def hash_production_integration_evidence(
    evidence: ProductionIntegrationEvidence,
) -> str:
    return _canonical_sha256(
        evidence.model_dump(
            mode="json", exclude={"evidence_sha256", "signature_base64url"}
        )
    )


def hash_production_integration_bundle(
    bundle: ProductionIntegrationEvidenceBundle,
) -> str:
    return _canonical_sha256(bundle.model_dump(mode="json", exclude={"bundle_sha256"}))


def hash_production_readiness_report(report: ProductionReadinessReport) -> str:
    return _canonical_sha256(report.model_dump(mode="json", exclude={"report_sha256"}))


def hash_production_tco_qa_attestation(attestation: ProductionTcoQaAttestation) -> str:
    return _canonical_sha256(attestation.model_dump(mode="json"))


def verify_production_tco_qa_attestation(
    attestation: ProductionTcoQaAttestation,
    report: ProductionReadinessReport,
    policy: ProductionIntegrationPolicy,
    trust_store: ProductionIntegrationTrustStore,
    *,
    at: datetime,
) -> bool:
    """Verify the P15 TCO/QA gate without a Human or controller secret."""

    try:
        _require_utc(at, "TCO/QA attestation verification timestamp")
        item = _copy(attestation, ProductionTcoQaAttestation)
        report_copy = _copy(report, ProductionReadinessReport)
        policy_copy = _copy(policy, ProductionIntegrationPolicy)
        trust_copy = _copy(trust_store, ProductionIntegrationTrustStore)
    except (TypeError, ValueError):
        return False
    binding = _report_binding(report_copy)
    return (
        policy_copy.trust_store_sha256
        == hash_production_integration_trust_store(trust_copy)
        and report_copy.integration_policy_sha256
        == hash_production_integration_policy(policy_copy)
        and report_copy.decision
        is ProductionReadinessDecision.READY_FOR_HUMAN_GATE
        and item.decision is ReadinessAttestationDecision.ACCEPT
        and all(getattr(item, field) == value for field, value in binding.items())
        and _verify_attestation(item, trust_copy.tco_qa, SigningRole.TCO_QA)
        and report_copy.evaluated_at <= item.issued_at <= at < item.expires_at
        and item.expires_at - item.issued_at
        <= timedelta(seconds=policy_copy.maximum_tco_attestation_ttl_seconds)
    )


def hash_production_human_approval(
    approval: ProductionHumanEnvironmentApproval,
) -> str:
    return _canonical_sha256(approval.model_dump(mode="json"))


def hash_production_bootstrap_authorization(
    authorization: ProductionBootstrapAuthorization,
) -> str:
    return _canonical_sha256(authorization.model_dump(mode="json"))


def hash_production_reconciliation_facts(facts: ProductionReconciliationFacts) -> str:
    return _canonical_sha256(
        facts.model_dump(
            mode="json", exclude={"facts_sha256", "signature_base64url"}
        )
    )


def hash_production_reconciliation_report(report: ProductionReconciliationReport) -> str:
    return _canonical_sha256(report.model_dump(mode="json", exclude={"report_sha256"}))


def hash_production_reconciliation_record(record: ProductionReconciliationRecord) -> str:
    return _canonical_sha256(record.model_dump(mode="json", exclude={"record_sha256"}))


def sign_production_reconciliation_facts(
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    plan_sha256: str,
    p13_store_identity_sha256: str,
    p13_result_sha256: str,
    p13_terminal_state: P13TerminalState,
    stopped_revision: int,
    stopped_head_sha256: str,
    stop_reason_sha256: str,
    provider_observed_state: ProviderObservedState,
    provider_result_receipt_sha256: str,
    journaled_provider_receipt_sha256: str,
    provider_probe_receipt_sha256: str,
    receipt_lookup_evidence_sha256: str,
    independent_readback_evidence_sha256: str,
    observed_at: datetime,
    expires_at: datetime,
) -> ProductionReconciliationFacts:
    values = {
        "schema_version": "1.0",
        "plan_sha256": plan_sha256,
        "p13_store_identity_sha256": p13_store_identity_sha256,
        "p13_result_sha256": p13_result_sha256,
        "p13_terminal_state": p13_terminal_state,
        "stopped_revision": stopped_revision,
        "stopped_head_sha256": stopped_head_sha256,
        "stop_reason_sha256": stop_reason_sha256,
        "provider_observed_state": provider_observed_state,
        "provider_result_receipt_sha256": provider_result_receipt_sha256,
        "journaled_provider_receipt_sha256": journaled_provider_receipt_sha256,
        "provider_probe_receipt_sha256": provider_probe_receipt_sha256,
        "receipt_lookup_evidence_sha256": receipt_lookup_evidence_sha256,
        "independent_readback_evidence_sha256": independent_readback_evidence_sha256,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "producer_issuer": issuer,
        "producer_key_id_sha256": _private_key_id(private_key),
        "producer_role": SigningRole.RECOVERY_AUDITOR,
    }
    provisional = ProductionReconciliationFacts.model_construct(
        **values, facts_sha256="0" * 64, signature_base64url="A" * 86
    )
    facts_sha256 = hash_production_reconciliation_facts(provisional)
    return ProductionReconciliationFacts(
        **values,
        facts_sha256=facts_sha256,
        signature_base64url=_sign(private_key, facts_sha256),
    )


def verify_production_reconciliation_facts(
    facts: ProductionReconciliationFacts,
    trust_store: ProductionIntegrationTrustStore,
    *,
    at: datetime,
) -> bool:
    try:
        _require_utc(at, "reconciliation verification timestamp")
        item = _copy(facts, ProductionReconciliationFacts)
        trust = _copy(trust_store, ProductionIntegrationTrustStore)
        return (
            item.observed_at <= at < item.expires_at
            and _verify_signed_hash(
                item.facts_sha256,
                item.signature_base64url,
                trust.recovery_auditor,
                issuer=item.producer_issuer,
                key_id=item.producer_key_id_sha256,
                role=item.producer_role,
                expected_role=SigningRole.RECOVERY_AUDITOR,
            )
        )
    except (TypeError, ValueError):
        return False


def sign_production_integration_evidence(
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    requirement: ProductionIntegrationRequirement,
    facts: ProductionIntegrationFacts,
    private_key: Ed25519PrivateKey,
    *,
    evidence_id: str,
    issuer: str,
    provenance: ProductionEvidenceProvenance,
    observed_at: datetime,
    expires_at: datetime,
) -> ProductionIntegrationEvidence:
    validated_plan = _copy(plan, ProductionIntegrationPlan)
    validated_policy = _copy(policy, ProductionIntegrationPolicy)
    validated_requirement = _copy(requirement, ProductionIntegrationRequirement)
    if validated_plan.integration_policy_sha256 != hash_production_integration_policy(
        validated_policy
    ):
        raise ProductionReadinessInputError("plan does not bind the supplied policy")
    if validated_requirement not in validated_plan.requirements:
        raise ProductionReadinessInputError("requirement is not part of the exact plan")
    facts_copy = type(facts).model_validate(facts.model_dump())
    if facts_copy.kind is not validated_requirement.facts_kind:
        raise ProductionReadinessInputError("facts kind does not match requirement")
    key_id = _private_key_id(private_key)
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "check": validated_requirement.check,
        "plan_sha256": validated_plan.plan_sha256,
        "integration_policy_sha256": validated_plan.integration_policy_sha256,
        "requirement_sha256": hash_production_integration_requirement(
            validated_requirement
        ),
        "evidence_identity_sha256": validated_requirement.evidence_identity_sha256,
        "environment_identity_sha256": validated_plan.environment_identity_sha256,
        "subject_sha256": validated_requirement.subject_sha256,
        "command_sha256": validated_requirement.command_sha256,
        "tool_name": validated_requirement.tool_name,
        "tool_version": validated_requirement.tool_version,
        "provenance": provenance,
        "facts": facts_copy,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "runner_issuer": issuer,
        "runner_key_id_sha256": key_id,
        "runner_role": validated_requirement.signer_role,
    }
    provisional = ProductionIntegrationEvidence.model_construct(
        **values, evidence_sha256="0" * 64, signature_base64url="A" * 86
    )
    evidence_sha256 = hash_production_integration_evidence(provisional)
    signature = _sign(private_key, evidence_sha256)
    return ProductionIntegrationEvidence(
        **values,
        evidence_sha256=evidence_sha256,
        signature_base64url=signature,
    )


def build_production_integration_bundle(
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    evidence: tuple[ProductionIntegrationEvidence, ...],
) -> ProductionIntegrationEvidenceBundle:
    plan_copy = _copy(plan, ProductionIntegrationPlan)
    policy_copy = _copy(policy, ProductionIntegrationPolicy)
    if plan_copy.integration_policy_sha256 != hash_production_integration_policy(
        policy_copy
    ):
        raise ProductionReadinessInputError("plan does not bind the supplied policy")
    ordered = tuple(
        sorted(
            evidence,
            key=lambda item: (
                item.check.value,
                item.evidence_id,
                item.evidence_sha256,
            ),
        )
    )
    values = {
        "schema_version": "1.0",
        "plan_sha256": plan_copy.plan_sha256,
        "integration_policy_sha256": plan_copy.integration_policy_sha256,
        "evidence": ordered,
    }
    provisional = ProductionIntegrationEvidenceBundle.model_construct(
        **values, bundle_sha256="0" * 64
    )
    return ProductionIntegrationEvidenceBundle(
        **values, bundle_sha256=hash_production_integration_bundle(provisional)
    )


def evaluate_production_integration_readiness(
    bundle: ProductionIntegrationEvidenceBundle,
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    trust_store: ProductionIntegrationTrustStore,
    *,
    at: datetime,
) -> ProductionReadinessReport:
    _require_utc(at, "readiness evaluation timestamp")
    validated_bundle = _copy(bundle, ProductionIntegrationEvidenceBundle)
    validated_plan = _copy(plan, ProductionIntegrationPlan)
    validated_policy = _copy(policy, ProductionIntegrationPolicy)
    validated_trust = _copy(trust_store, ProductionIntegrationTrustStore)
    trust_hash = hash_production_integration_trust_store(validated_trust)
    policy_hash = hash_production_integration_policy(validated_policy)
    if validated_policy.trust_store_sha256 != trust_hash:
        raise ProductionReadinessInputError("policy trust-store pin mismatch")
    if (
        validated_plan.integration_policy_sha256 != policy_hash
        or validated_plan.trust_store_sha256 != trust_hash
        or validated_bundle.plan_sha256 != validated_plan.plan_sha256
        or validated_bundle.integration_policy_sha256 != policy_hash
    ):
        raise ProductionReadinessInputError("plan, policy, trust store, or bundle binding mismatch")

    findings: set[tuple[ProductionIntegrationCheck, ProductionReadinessReason]] = set()
    failed: set[ProductionIntegrationCheck] = set()
    expiries: list[datetime] = []
    evidence_by_check: dict[ProductionIntegrationCheck, list[ProductionIntegrationEvidence]] = {
        check: [] for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS
    }
    for item in validated_bundle.evidence:
        evidence_by_check[item.check].append(item)

    duplicate_ids = {
        item.evidence_id
        for item in validated_bundle.evidence
        if sum(other.evidence_id == item.evidence_id for other in validated_bundle.evidence)
        > 1
    }

    requirements = {item.check: item for item in validated_plan.requirements}
    if validated_plan.not_before > at:
        for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.PLAN_FUTURE))
    if validated_plan.expires_at <= at:
        for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.PLAN_EXPIRED))
    for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
        items = evidence_by_check[check]
        if not items:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.MISSING_EVIDENCE))
            continue
        if len(items) > 1:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.DUPLICATE_EVIDENCE))
            if len({item.evidence_sha256 for item in items}) > 1:
                findings.add((check, ProductionReadinessReason.CONFLICTING_EVIDENCE))
            continue
        item = items[0]
        requirement = requirements[check]
        expiries.append(item.expires_at)
        if item.evidence_id in duplicate_ids:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.DUPLICATE_EVIDENCE))
        if item.provenance is ProductionEvidenceProvenance.SYNTHETIC_CONTRACT:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.SYNTHETIC_EVIDENCE))
        if not _evidence_matches_requirement(
            item, requirement, validated_plan.environment_identity_sha256
        ):
            failed.add(check)
            findings.add((check, ProductionReadinessReason.REQUIREMENT_MISMATCH))
        verification_key = _verification_key_for_check(validated_trust, check)
        if not _verify_signed_hash(
            item.evidence_sha256,
            item.signature_base64url,
            verification_key,
            issuer=item.runner_issuer,
            key_id=item.runner_key_id_sha256,
            role=item.runner_role,
            expected_role=requirement.signer_role,
        ):
            failed.add(check)
            findings.add((check, ProductionReadinessReason.EVIDENCE_SIGNATURE_INVALID))
        if item.observed_at > at:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.EVIDENCE_FUTURE))
        if item.expires_at <= at:
            failed.add(check)
            findings.add((check, ProductionReadinessReason.EVIDENCE_EXPIRED))
        if item.expires_at - item.observed_at > timedelta(
            seconds=_maximum_check_ttl_seconds(check, validated_policy)
        ):
            failed.add(check)
            findings.add((check, ProductionReadinessReason.EVIDENCE_TTL_EXCEEDED))
        if not _facts_pass(item.facts, validated_policy):
            failed.add(check)
            findings.add((check, ProductionReadinessReason.CHECK_FAILED))

    passed = set(REQUIRED_PRODUCTION_INTEGRATION_CHECKS) - failed
    decision = (
        ProductionReadinessDecision.READY_FOR_HUMAN_GATE
        if not failed and not findings
        else ProductionReadinessDecision.STOP
    )
    if decision is ProductionReadinessDecision.READY_FOR_HUMAN_GATE:
        expires_at = min(
            min(expiries),
            validated_plan.expires_at,
            at + timedelta(seconds=validated_policy.maximum_report_ttl_seconds),
        )
    else:
        expires_at = at
    ordered_findings = tuple(
        ProductionReadinessFinding(check=check, reason=reason)
        for check, reason in sorted(findings, key=lambda item: (item[0].value, item[1].value))
    )
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "decision": decision,
        "evaluated_at": at,
        "plan_sha256": validated_plan.plan_sha256,
        "integration_policy_sha256": policy_hash,
        "trust_store_sha256": trust_hash,
        "evidence_bundle_sha256": validated_bundle.bundle_sha256,
        "findings": ordered_findings,
        "passed_checks": tuple(sorted(passed, key=lambda item: item.value)),
        "failed_checks": tuple(sorted(failed, key=lambda item: item.value)),
        "expires_at": expires_at,
        "synthetic_evidence_is_not_production_authority": True,
    }
    provisional = ProductionReadinessReport.model_construct(
        **values, report_sha256="0" * 64
    )
    return ProductionReadinessReport(
        **values, report_sha256=hash_production_readiness_report(provisional)
    )


def sign_production_tco_qa_attestation(
    report: ProductionReadinessReport,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    decision: ReadinessAttestationDecision,
    issued_at: datetime,
    expires_at: datetime,
) -> ProductionTcoQaAttestation:
    validated = _copy(report, ProductionReadinessReport)
    return _build_signed_model(
        ProductionTcoQaAttestation,
        {
            "issuer": issuer,
            "signer_role": SigningRole.TCO_QA,
            "scope": ProductionAttestationScope.TCO_QA_ACCEPTANCE,
            "decision": decision,
            **_report_binding(validated),
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
        key_field="key_id_sha256",
    )


def sign_production_human_environment_approval(
    report: ProductionReadinessReport,
    plan: ProductionIntegrationPlan,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    decision: EnvironmentApprovalDecision,
    decision_record_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
) -> ProductionHumanEnvironmentApproval:
    validated_report = _copy(report, ProductionReadinessReport)
    validated_plan = _copy(plan, ProductionIntegrationPlan)
    if validated_report.plan_sha256 != validated_plan.plan_sha256:
        raise ProductionReadinessInputError("Human approval plan mismatch")
    return _build_signed_model(
        ProductionHumanEnvironmentApproval,
        {
            "issuer": issuer,
            "signer_role": SigningRole.HUMAN_APPROVER,
            "scope": ProductionAttestationScope.HUMAN_ENVIRONMENT_APPROVAL,
            "decision": decision,
            **_report_binding(validated_report),
            "environment_identity_sha256": validated_plan.environment_identity_sha256,
            "deployment_candidate_sha256": validated_plan.deployment_candidate_sha256,
            "decision_record_sha256": decision_record_sha256,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
        key_field="key_id_sha256",
    )


def authorize_production_bootstrap(
    report: ProductionReadinessReport,
    bundle: ProductionIntegrationEvidenceBundle,
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    trust_store: ProductionIntegrationTrustStore,
    tco_qa: ProductionTcoQaAttestation,
    human: ProductionHumanEnvironmentApproval,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> ProductionBootstrapAuthorization:
    validated_report = _copy(report, ProductionReadinessReport)
    validated_bundle = _copy(bundle, ProductionIntegrationEvidenceBundle)
    validated_plan = _copy(plan, ProductionIntegrationPlan)
    validated_policy = _copy(policy, ProductionIntegrationPolicy)
    validated_trust = _copy(trust_store, ProductionIntegrationTrustStore)
    validated_tco = _copy(tco_qa, ProductionTcoQaAttestation)
    validated_human = _copy(human, ProductionHumanEnvironmentApproval)
    _validate_authorization_inputs(
        validated_report,
        validated_bundle,
        validated_plan,
        validated_policy,
        validated_trust,
        validated_tco,
        validated_human,
        at=issued_at,
        requested_expiry=expires_at,
    )
    if issuer != validated_trust.controller.issuer:
        raise ProductionReadinessInputError("controller issuer does not match trust store")
    if not _private_key_matches(private_key, validated_trust.controller):
        raise ProductionReadinessInputError("controller signer does not match trust store")
    return _build_signed_model(
        ProductionBootstrapAuthorization,
        {
            "issuer": issuer,
            "controller_key_id_sha256": validated_trust.controller.key_id_sha256,
            "signer_role": SigningRole.CONTROLLER,
            "scope": ProductionAttestationScope.CONTROLLER_BOOTSTRAP,
            "report_sha256": validated_report.report_sha256,
            "evidence_bundle_sha256": validated_bundle.bundle_sha256,
            "tco_qa_attestation_sha256": hash_production_tco_qa_attestation(
                validated_tco
            ),
            "human_approval_sha256": hash_production_human_approval(validated_human),
            "plan_sha256": validated_plan.plan_sha256,
            "integration_policy_sha256": hash_production_integration_policy(
                validated_policy
            ),
            "environment_identity_sha256": validated_plan.environment_identity_sha256,
            "deployment_candidate_sha256": validated_plan.deployment_candidate_sha256,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        private_key,
        key_field="controller_key_id_sha256",
    )


def verify_production_bootstrap_authorization(
    authorization: ProductionBootstrapAuthorization,
    report: ProductionReadinessReport,
    bundle: ProductionIntegrationEvidenceBundle,
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    trust_store: ProductionIntegrationTrustStore,
    tco_qa: ProductionTcoQaAttestation,
    human: ProductionHumanEnvironmentApproval,
    pins: ProductionReadinessAuthorityPins,
    *,
    at: datetime,
) -> bool:
    try:
        _require_utc(at, "authorization verification timestamp")
        auth = _copy(authorization, ProductionBootstrapAuthorization)
        report_copy = _copy(report, ProductionReadinessReport)
        bundle_copy = _copy(bundle, ProductionIntegrationEvidenceBundle)
        plan_copy = _copy(plan, ProductionIntegrationPlan)
        policy_copy = _copy(policy, ProductionIntegrationPolicy)
        trust_copy = _copy(trust_store, ProductionIntegrationTrustStore)
        tco_copy = _copy(tco_qa, ProductionTcoQaAttestation)
        human_copy = _copy(human, ProductionHumanEnvironmentApproval)
        pins_copy = _copy(pins, ProductionReadinessAuthorityPins)
        if (
            pins_copy.expected_trust_store_sha256
            != hash_production_integration_trust_store(trust_copy)
            or pins_copy.expected_integration_policy_sha256
            != hash_production_integration_policy(policy_copy)
            or pins_copy.expected_plan_sha256 != plan_copy.plan_sha256
            or pins_copy.expected_report_sha256 != report_copy.report_sha256
            or pins_copy.expected_authorization_sha256
            != hash_production_bootstrap_authorization(auth)
        ):
            return False
        _validate_authorization_inputs(
            report_copy,
            bundle_copy,
            plan_copy,
            policy_copy,
            trust_copy,
            tco_copy,
            human_copy,
            at=at,
            requested_expiry=auth.expires_at,
            require_issue_time=auth.issued_at,
        )
        expected = (
            report_copy.report_sha256,
            bundle_copy.bundle_sha256,
            hash_production_tco_qa_attestation(tco_copy),
            hash_production_human_approval(human_copy),
            plan_copy.plan_sha256,
            hash_production_integration_policy(policy_copy),
            plan_copy.environment_identity_sha256,
            plan_copy.deployment_candidate_sha256,
        )
        actual = (
            auth.report_sha256,
            auth.evidence_bundle_sha256,
            auth.tco_qa_attestation_sha256,
            auth.human_approval_sha256,
            auth.plan_sha256,
            auth.integration_policy_sha256,
            auth.environment_identity_sha256,
            auth.deployment_candidate_sha256,
        )
        return actual == expected and auth.issued_at <= at < auth.expires_at and _verify_signed_hash(
            auth.payload_sha256,
            auth.signature_base64url,
            trust_copy.controller,
            issuer=auth.issuer,
            key_id=auth.controller_key_id_sha256,
            role=auth.signer_role,
            expected_role=SigningRole.CONTROLLER,
        )
    except (TypeError, ValueError, ProductionReadinessInputError):
        return False


def evaluate_production_reconciliation(
    facts: ProductionReconciliationFacts, *, at: datetime
) -> ProductionReconciliationReport:
    _require_utc(at, "reconciliation evaluation timestamp")
    validated = _copy(facts, ProductionReconciliationFacts)
    if validated.observed_at > at:
        raise ProductionReadinessInputError("reconciliation observation is in the future")
    if validated.p13_terminal_state is P13TerminalState.STOP:
        action = ProductionReconciliationAction.KEEP_STOP
        reason = ProductionReconciliationReason.EXISTING_STOP_PRESERVED
    elif validated.provider_observed_state is ProviderObservedState.APPLIED:
        action = ProductionReconciliationAction.REQUEST_HUMAN_DISABLE
        reason = ProductionReconciliationReason.UNKNOWN_NOT_PROMOTED
    elif validated.provider_observed_state is ProviderObservedState.NOT_APPLIED:
        action = ProductionReconciliationAction.KEEP_STOP
        reason = ProductionReconciliationReason.NON_APPLIED_FACT_PRESERVED
    elif validated.provider_observed_state is ProviderObservedState.AMBIGUOUS:
        action = ProductionReconciliationAction.MANUAL_REMEDIATION
        reason = ProductionReconciliationReason.AMBIGUOUS_PROVIDER_STATE
    values = {
        "schema_version": "1.0",
        "decision": ProductionReadinessDecision.STOP,
        "action": action,
        "reason": reason,
        "plan_sha256": validated.plan_sha256,
        "p13_result_sha256": validated.p13_result_sha256,
        "reconciliation_facts_sha256": validated.facts_sha256,
        "evaluated_at": at,
    }
    provisional = ProductionReconciliationReport.model_construct(
        **values, report_sha256="0" * 64
    )
    return ProductionReconciliationReport(
        **values, report_sha256=hash_production_reconciliation_report(provisional)
    )


_RECONCILIATION_LEDGER_SCHEMA = """
CREATE TABLE reconciliation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE reconciliation_records (
    revision INTEGER PRIMARY KEY,
    facts_sha256 TEXT NOT NULL UNIQUE,
    report_sha256 TEXT NOT NULL UNIQUE,
    p13_result_sha256 TEXT NOT NULL UNIQUE,
    record_sha256 TEXT NOT NULL UNIQUE,
    facts_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER reconciliation_records_no_update
BEFORE UPDATE ON reconciliation_records BEGIN
    SELECT RAISE(ABORT, 'reconciliation records are immutable');
END;
CREATE TRIGGER reconciliation_records_no_delete
BEFORE DELETE ON reconciliation_records BEGIN
    SELECT RAISE(ABORT, 'reconciliation records are immutable');
END;
"""


class ProductionReconciliationLedger:
    """Authenticated append-only local ledger for post-UNKNOWN provider facts."""

    __slots__ = (
        "_path",
        "_lock_path",
        "_store_id",
        "_plan_sha256",
        "_trust",
        "_auth_key",
        "_anchor_commit",
        "_anchor_read",
        "_lock",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        expected_store_id_sha256: str,
        expected_plan_sha256: str,
        trust_store: ProductionIntegrationTrustStore,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> None:
        self._path = Path(path).resolve()
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        self._store_id = _require_sha256(expected_store_id_sha256, "ledger store")
        self._plan_sha256 = _require_sha256(expected_plan_sha256, "ledger plan")
        self._trust = _copy(trust_store, ProductionIntegrationTrustStore)
        self._auth_key = _require_authentication_key(state_authentication_key)
        if not callable(anchor_commit) or not callable(anchor_read):
            raise TypeError("reconciliation anchor callbacks are required")
        self._anchor_commit = anchor_commit
        self._anchor_read = anchor_read
        self._lock = RLock()
        if not self._path.is_file() or self._path.stat().st_mode & 0o077:
            raise ProductionReadinessInputError(
                "reconciliation ledger is missing or has unsafe permissions"
            )
        with self._file_lock(), self._connect() as connection:
            self._assert_integrity(connection, recover_anchor=True)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        store_id_sha256: str,
        plan_sha256: str,
        trust_store: ProductionIntegrationTrustStore,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> ProductionReconciliationLedger:
        selected = Path(path).resolve()
        if selected.exists():
            raise FileExistsError("reconciliation ledger already exists")
        selected.parent.mkdir(parents=True, exist_ok=True)
        store_id = _require_sha256(store_id_sha256, "ledger store")
        plan_id = _require_sha256(plan_sha256, "ledger plan")
        auth_key = _require_authentication_key(state_authentication_key)
        connection = sqlite3.connect(selected)
        try:
            connection.executescript(_RECONCILIATION_LEDGER_SCHEMA)
            meta = {
                "schema_version": "1.0",
                "store_id_sha256": store_id,
                "plan_sha256": plan_id,
                "revision": "0",
                "head_sha256": "0" * 64,
                "previous_anchor_sha256": "0" * 64,
                "state_mac_sha256": "0" * 64,
            }
            connection.executemany(
                "INSERT INTO reconciliation_meta(key, value) VALUES (?, ?)",
                tuple(meta.items()),
            )
            state_mac = cls._calculate_state_mac_static(connection, auth_key)
            connection.execute(
                "UPDATE reconciliation_meta SET value=? WHERE key='state_mac_sha256'",
                (state_mac,),
            )
            connection.commit()
        finally:
            connection.close()
        selected.chmod(0o600)
        initial_anchor = cls._anchor_hash(store_id, 0, "0" * 64, state_mac)
        anchor_commit(0, initial_anchor)
        if anchor_read() != initial_anchor:
            raise ProductionReadinessInputError(
                "reconciliation anchor initialization was not durable"
            )
        return cls(
            selected,
            expected_store_id_sha256=store_id,
            expected_plan_sha256=plan_id,
            trust_store=trust_store,
            state_authentication_key=auth_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
        )

    @property
    def store_id_sha256(self) -> str:
        return self._store_id

    @property
    def plan_sha256(self) -> str:
        return self._plan_sha256

    @property
    def trust_store_sha256(self) -> str:
        return hash_production_integration_trust_store(self._trust)

    def append(
        self,
        facts: ProductionReconciliationFacts,
        report: ProductionReconciliationReport,
        *,
        at: datetime,
    ) -> ProductionReconciliationRecord:
        _require_utc(at, "reconciliation append timestamp")
        facts_copy = _copy(facts, ProductionReconciliationFacts)
        report_copy = _copy(report, ProductionReconciliationReport)
        expected_report = evaluate_production_reconciliation(
            facts_copy, at=report_copy.evaluated_at
        )
        if (
            report_copy != expected_report
            or facts_copy.plan_sha256 != self._plan_sha256
            or not verify_production_reconciliation_facts(
                facts_copy, self._trust, at=at
            )
            or facts_copy.observed_at > report_copy.evaluated_at
            or report_copy.evaluated_at > at
        ):
            raise ProductionReadinessInputError(
                "reconciliation facts or report are not authoritative"
            )
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection, recover_anchor=True)
                existing = connection.execute(
                    "SELECT facts_json, report_json, record_json "
                    "FROM reconciliation_records WHERE facts_sha256=?",
                    (facts_copy.facts_sha256,),
                ).fetchone()
                if existing is not None:
                    if (
                        ProductionReconciliationFacts.model_validate_json(
                            existing["facts_json"]
                        )
                        != facts_copy
                        or ProductionReconciliationReport.model_validate_json(
                            existing["report_json"]
                        )
                        != report_copy
                    ):
                        raise ProductionReadinessInputError(
                            "reconciliation fact hash conflicts with ledger"
                        )
                    connection.rollback()
                    return ProductionReconciliationRecord.model_validate_json(
                        existing["record_json"]
                    )
                if connection.execute(
                    "SELECT 1 FROM reconciliation_records WHERE p13_result_sha256=?",
                    (facts_copy.p13_result_sha256,),
                ).fetchone() is not None:
                    raise ProductionReadinessInputError(
                        "a P13 result cannot have conflicting reconciliation facts"
                    )
                revision = int(meta["revision"]) + 1
                values = {
                    "schema_version": "1.0",
                    "ledger_store_id_sha256": self._store_id,
                    "plan_sha256": self._plan_sha256,
                    "revision": revision,
                    "previous_head_sha256": meta["head_sha256"],
                    "facts_sha256": facts_copy.facts_sha256,
                    "report_sha256": report_copy.report_sha256,
                    "p13_result_sha256": facts_copy.p13_result_sha256,
                    "recorded_at": at,
                }
                provisional = ProductionReconciliationRecord.model_construct(
                    **values, record_sha256="0" * 64
                )
                record = ProductionReconciliationRecord(
                    **values,
                    record_sha256=hash_production_reconciliation_record(provisional),
                )
                connection.execute(
                    "INSERT INTO reconciliation_records "
                    "(revision, facts_sha256, report_sha256, p13_result_sha256, "
                    "record_sha256, facts_json, report_json, record_json, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        revision,
                        facts_copy.facts_sha256,
                        report_copy.report_sha256,
                        facts_copy.p13_result_sha256,
                        record.record_sha256,
                        facts_copy.model_dump_json(),
                        report_copy.model_dump_json(),
                        record.model_dump_json(),
                        at.isoformat(),
                    ),
                )
                prior_anchor = self._anchor_read()
                connection.execute(
                    "UPDATE reconciliation_meta SET value=? WHERE key='revision'",
                    (str(revision),),
                )
                connection.execute(
                    "UPDATE reconciliation_meta SET value=? WHERE key='head_sha256'",
                    (record.record_sha256,),
                )
                connection.execute(
                    "UPDATE reconciliation_meta SET value=? "
                    "WHERE key='previous_anchor_sha256'",
                    (prior_anchor,),
                )
                state_mac = self._calculate_state_mac_static(
                    connection, self._auth_key
                )
                connection.execute(
                    "UPDATE reconciliation_meta SET value=? "
                    "WHERE key='state_mac_sha256'",
                    (state_mac,),
                )
                connection.commit()
                anchor = self._anchor_hash(
                    self._store_id, revision, record.record_sha256, state_mac
                )
                self._anchor_commit(revision, anchor)
                if self._anchor_read() != anchor:
                    raise ProductionReadinessInputError(
                        "reconciliation anchor commit was not durable"
                    )
                return record
            except Exception:
                connection.rollback()
                raise

    def verifies_for_reset(
        self,
        record_sha256: str,
        *,
        p13_store_identity_sha256: str,
        stopped_revision: int,
        stopped_head_sha256: str,
        stop_reason_sha256: str,
        at: datetime,
    ) -> bool:
        try:
            _require_utc(at, "reconciliation reset verification timestamp")
            with self._lock, self._file_lock(), self._connect() as connection:
                self._assert_integrity(connection, recover_anchor=True)
                row = connection.execute(
                    "SELECT facts_json, report_json, record_json "
                    "FROM reconciliation_records WHERE record_sha256=?",
                    (record_sha256,),
                ).fetchone()
                if row is None:
                    return False
                facts = ProductionReconciliationFacts.model_validate_json(
                    row["facts_json"]
                )
                report = ProductionReconciliationReport.model_validate_json(
                    row["report_json"]
                )
                record = ProductionReconciliationRecord.model_validate_json(
                    row["record_json"]
                )
                return (
                    record.record_sha256 == record_sha256
                    and record.plan_sha256 == self._plan_sha256
                    and report.decision is ProductionReadinessDecision.STOP
                    and report.action is ProductionReconciliationAction.KEEP_STOP
                    and facts.provider_observed_state
                    is ProviderObservedState.NOT_APPLIED
                    and facts.p13_store_identity_sha256
                    == p13_store_identity_sha256
                    and facts.stopped_revision == stopped_revision
                    and facts.stopped_head_sha256 == stopped_head_sha256
                    and facts.stop_reason_sha256 == stop_reason_sha256
                    and verify_production_reconciliation_facts(
                        facts, self._trust, at=at
                    )
                )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        descriptor = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _assert_integrity(
        self, connection: sqlite3.Connection, *, recover_anchor: bool
    ) -> dict[str, str]:
        if self._schema_descriptor(connection) != self._expected_schema_descriptor():
            raise ProductionReadinessInputError(
                "reconciliation ledger schema mismatch"
            )
        rows = connection.execute(
            "SELECT key, value FROM reconciliation_meta ORDER BY key"
        ).fetchall()
        meta = {row["key"]: row["value"] for row in rows}
        expected_keys = {
            "schema_version",
            "store_id_sha256",
            "plan_sha256",
            "revision",
            "head_sha256",
            "previous_anchor_sha256",
            "state_mac_sha256",
        }
        if (
            set(meta) != expected_keys
            or meta["schema_version"] != "1.0"
            or meta["store_id_sha256"] != self._store_id
            or meta["plan_sha256"] != self._plan_sha256
        ):
            raise ProductionReadinessInputError(
                "reconciliation ledger metadata mismatch"
            )
        records = connection.execute(
            "SELECT * FROM reconciliation_records ORDER BY revision"
        ).fetchall()
        previous = "0" * 64
        for expected_revision, row in enumerate(records, 1):
            facts = ProductionReconciliationFacts.model_validate_json(row["facts_json"])
            report = ProductionReconciliationReport.model_validate_json(row["report_json"])
            record = ProductionReconciliationRecord.model_validate_json(row["record_json"])
            if (
                int(row["revision"]) != expected_revision
                or record.revision != expected_revision
                or record.previous_head_sha256 != previous
                or record.record_sha256 != row["record_sha256"]
                or not (
                    record.facts_sha256
                    == facts.facts_sha256
                    == row["facts_sha256"]
                )
                or not (
                    record.report_sha256
                    == report.report_sha256
                    == row["report_sha256"]
                )
                or not (
                    record.p13_result_sha256
                    == facts.p13_result_sha256
                    == row["p13_result_sha256"]
                )
                or report.reconciliation_facts_sha256 != facts.facts_sha256
                or report.plan_sha256 != self._plan_sha256
                or facts.plan_sha256 != self._plan_sha256
                or not _verify_signed_hash(
                    facts.facts_sha256,
                    facts.signature_base64url,
                    self._trust.recovery_auditor,
                    issuer=facts.producer_issuer,
                    key_id=facts.producer_key_id_sha256,
                    role=facts.producer_role,
                    expected_role=SigningRole.RECOVERY_AUDITOR,
                )
            ):
                raise ProductionReadinessInputError(
                    "reconciliation ledger record mismatch"
                )
            previous = record.record_sha256
        if int(meta["revision"]) != len(records) or meta["head_sha256"] != previous:
            raise ProductionReadinessInputError(
                "reconciliation ledger head mismatch"
            )
        expected_mac = self._calculate_state_mac_static(connection, self._auth_key)
        if not hmac.compare_digest(expected_mac, meta["state_mac_sha256"]):
            raise ProductionReadinessInputError(
                "reconciliation ledger authentication mismatch"
            )
        anchor = self._anchor_hash(
            self._store_id,
            int(meta["revision"]),
            meta["head_sha256"],
            meta["state_mac_sha256"],
        )
        observed_anchor = self._anchor_read()
        if observed_anchor != anchor:
            if not recover_anchor or observed_anchor != meta["previous_anchor_sha256"]:
                raise ProductionReadinessInputError(
                    "reconciliation ledger anchor mismatch"
                )
            self._anchor_commit(int(meta["revision"]), anchor)
            if self._anchor_read() != anchor:
                raise ProductionReadinessInputError(
                    "reconciliation ledger anchor recovery failed"
                )
        return meta

    @staticmethod
    def _calculate_state_mac_static(
        connection: sqlite3.Connection, auth_key: bytes
    ) -> str:
        meta_rows = connection.execute(
            "SELECT key, value FROM reconciliation_meta "
            "WHERE key != 'state_mac_sha256' ORDER BY key"
        ).fetchall()
        record_rows = connection.execute(
            "SELECT revision, facts_sha256, report_sha256, p13_result_sha256, "
            "record_sha256, facts_json, report_json, record_json, recorded_at "
            "FROM reconciliation_records ORDER BY revision"
        ).fetchall()
        payload = {
            "meta": [tuple(row) for row in meta_rows],
            "records": [tuple(row) for row in record_rows],
        }
        return hmac.new(
            auth_key,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _anchor_hash(
        store_id_sha256: str, revision: int, head_sha256: str, state_mac_sha256: str
    ) -> str:
        return _canonical_sha256(
            {
                "ledger_store_id_sha256": store_id_sha256,
                "revision": revision,
                "head_sha256": head_sha256,
                "state_mac_sha256": state_mac_sha256,
            }
        )

    @staticmethod
    def _schema_descriptor(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' "
            "AND NOT (type='index' AND sql IS NULL) "
            "ORDER BY type, name"
        ).fetchall()
        return _canonical_sha256([tuple(row) for row in rows])

    @classmethod
    def _expected_schema_descriptor(cls) -> str:
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(_RECONCILIATION_LEDGER_SCHEMA)
            return cls._schema_descriptor(connection)


def _facts_pass(
    facts: ProductionIntegrationFacts, policy: ProductionIntegrationPolicy
) -> bool:
    if isinstance(facts, ProviderConditionalMutationFacts):
        return (
            facts.scenarios_executed == facts.scenarios_expected
            and facts.accepted_writes == 1
            and facts.stale_precondition_rejections == 1
            and facts.lower_fence_rejections == 1
            and facts.concurrent_winners == 1
            and facts.replay_receipt_matches == 1
            and facts.duplicate_side_effects == 0
        )
    if isinstance(facts, ProviderIdempotencyRetentionFacts):
        return (
            facts.observed_retention_seconds
            >= policy.minimum_idempotency_retention_seconds
            and facts.replay_attempts >= policy.minimum_replay_attempts
            and facts.matching_receipts == facts.replay_attempts
            and facts.duplicate_side_effects == 0
            and facts.conflicting_request_sha256 != facts.initial_request_sha256
            and facts.conflicting_request_rejections >= 1
            and facts.conflicting_request_side_effects == 0
            and facts.initial_request_sha256 == facts.replay_request_sha256
            and facts.initial_receipt_sha256 == facts.replay_receipt_sha256
            and facts.initial_audit_sha256 == facts.replay_audit_sha256
        )
    if isinstance(facts, ProviderReceiptLookupFacts):
        return (
            facts.lookup_attempts >= policy.minimum_receipt_lookup_attempts
            and facts.receipts_found == 1
            and facts.receipt_mismatches == 0
            and facts.unauthorized_receipts_returned == 0
            and facts.expected_receipt_sha256 == facts.observed_receipt_sha256
            and facts.unknown_query_sha256 != facts.known_query_sha256
            and facts.unknown_result_sha256 != facts.expected_receipt_sha256
            and facts.known_lookup_lag_milliseconds
            <= policy.maximum_receipt_lookup_lag_milliseconds
            and facts.unknown_lookup_mutation_effects == 0
        )
    if isinstance(facts, IndependentReadbackFacts):
        return (
            facts.readbacks_attempted >= policy.minimum_independent_readbacks
            and facts.readbacks_matched == facts.readbacks_attempted
            and facts.readback_mismatches == 0
            and facts.expected_state_sha256 == facts.observed_state_sha256
            and facts.readback_lag_milliseconds
            <= policy.maximum_independent_readback_lag_milliseconds
        )
    if isinstance(facts, KmsIdentitySeparationFacts):
        return facts.pairwise_assertions_checked == 6 and facts.separation_violations == 0
    if isinstance(facts, ExternalMonotonicAnchorFacts):
        return (
            facts.samples_observed >= policy.minimum_anchor_samples
            and facts.strictly_advanced_transitions == facts.samples_observed - 1
            and facts.revision_after > facts.revision_before
            and facts.regressions == 0
            and facts.replay_rejections >= 1
        )
    if isinstance(facts, TrustedClockFacts):
        return (
            len(facts.clock_source_identity_sha256s) >= policy.minimum_clock_sources
            and len(facts.failure_domain_sha256s)
            >= policy.minimum_clock_failure_domains
            and facts.samples_observed >= policy.minimum_clock_sources
            and facts.maximum_absolute_offset_milliseconds
            + facts.maximum_uncertainty_milliseconds
            <= policy.maximum_clock_offset_milliseconds
            and facts.backward_steps == 0
            and facts.out_of_bound_samples == 0
        )
    if isinstance(facts, SharedDurableStoreFencingFacts):
        return (
            facts.concurrent_workers >= policy.minimum_fencing_workers
            and len(facts.worker_identity_sha256s) == facts.concurrent_workers
            and len(facts.failure_domain_sha256s)
            >= policy.minimum_fencing_failure_domains
            and facts.claim_contenders >= facts.concurrent_workers
            and facts.winning_claims == 1
            and facts.stale_writer_rejections >= facts.concurrent_workers - 1
            and facts.unfenced_successful_writes == 0
        )
    if isinstance(facts, EgressAllowlistFacts):
        return (
            facts.observed_destination_sha256s == facts.approved_destination_sha256s
            and facts.blocked_unapproved_attempts
            >= policy.minimum_unapproved_egress_attempts
            and facts.successful_unapproved_attempts == 0
        )
    if isinstance(facts, BackupRestoreFacts):
        return (
            facts.source_snapshot_sha256 == facts.restored_snapshot_sha256
            and facts.source_head_sha256 == facts.restored_head_sha256
            and facts.source_journal_set_sha256 == facts.restored_journal_set_sha256
            and facts.source_anchor_sha256 == facts.restored_anchor_sha256
            and facts.isolated_restore_target_sha256
            != facts.production_store_identity_sha256
            and facts.production_pointer_before_sha256
            == facts.production_pointer_after_sha256
            and facts.restore_attempts >= policy.minimum_restore_attempts
            and facts.successful_restores == facts.restore_attempts
            and facts.integrity_mismatches == 0
            and facts.corrupt_backup_rejections >= 1
            and facts.observed_rpo_seconds <= policy.maximum_rpo_seconds
            and facts.observed_rto_seconds <= policy.maximum_rto_seconds
            and facts.backup_age_seconds <= policy.maximum_backup_age_seconds
            and facts.restore_drill_age_seconds
            <= policy.maximum_restore_drill_age_seconds
            and facts.authoritative_resume_event_gap == 0
        )
    if isinstance(facts, RollbackDisableFacts):
        return (
            facts.fault_exercises >= policy.minimum_rollback_exercises
            and facts.completed_disables == facts.fault_exercises
            and facts.maximum_disable_latency_milliseconds
            <= policy.maximum_disable_latency_milliseconds
            and facts.successful_post_disable_mutations == 0
            and facts.active_state_sha256 != facts.disabled_state_sha256
            and facts.final_observed_state_sha256 == facts.disabled_state_sha256
            and facts.activation_events_emitted == 0
            and facts.retry_events_emitted == 0
        )
    raise TypeError("unsupported production integration facts")


def _maximum_check_ttl_seconds(
    check: ProductionIntegrationCheck, policy: ProductionIntegrationPolicy
) -> int:
    if check in {
        ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR,
        ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING,
        ProductionIntegrationCheck.TRUSTED_CLOCK,
    }:
        return policy.maximum_live_control_ttl_seconds
    if check in {
        ProductionIntegrationCheck.BACKUP_RESTORE,
        ProductionIntegrationCheck.ROLLBACK_DISABLE,
    }:
        return policy.maximum_recovery_evidence_ttl_seconds
    return policy.maximum_evidence_ttl_seconds


def _evidence_matches_requirement(
    evidence: ProductionIntegrationEvidence,
    requirement: ProductionIntegrationRequirement,
    plan_environment: str,
) -> bool:
    return (
        evidence.check is requirement.check
        and evidence.requirement_sha256
        == hash_production_integration_requirement(requirement)
        and evidence.evidence_identity_sha256 == requirement.evidence_identity_sha256
        and evidence.environment_identity_sha256 == plan_environment
        and evidence.subject_sha256 == requirement.subject_sha256
        and evidence.command_sha256 == requirement.command_sha256
        and evidence.tool_name == requirement.tool_name
        and evidence.tool_version == requirement.tool_version
        and evidence.facts.kind is requirement.facts_kind
        and evidence.runner_role is requirement.signer_role
        and evidence.runner_key_id_sha256 == requirement.signer_key_id_sha256
    )


def _verification_key_for_check(
    trust_store: ProductionIntegrationTrustStore,
    check: ProductionIntegrationCheck,
) -> Ed25519VerificationKey:
    role = _EXPECTED_SIGNING_ROLE[check]
    return {
        SigningRole.PROVIDER_CONFORMANCE: trust_store.provider_conformance,
        SigningRole.PROVIDER_PROBE: trust_store.independent_probe,
        SigningRole.SECURITY_AUDITOR: trust_store.security_auditor,
        SigningRole.STORAGE_AUDITOR: trust_store.storage_auditor,
        SigningRole.TIME_AUDITOR: trust_store.time_auditor,
        SigningRole.NETWORK_AUDITOR: trust_store.network_auditor,
        SigningRole.RECOVERY_AUDITOR: trust_store.recovery_auditor,
    }[role]


def _report_binding(report: ProductionReadinessReport) -> dict[str, Any]:
    return {
        "report_sha256": report.report_sha256,
        "evidence_bundle_sha256": report.evidence_bundle_sha256,
        "plan_sha256": report.plan_sha256,
        "integration_policy_sha256": report.integration_policy_sha256,
    }


def _validate_authorization_inputs(
    report: ProductionReadinessReport,
    bundle: ProductionIntegrationEvidenceBundle,
    plan: ProductionIntegrationPlan,
    policy: ProductionIntegrationPolicy,
    trust_store: ProductionIntegrationTrustStore,
    tco: ProductionTcoQaAttestation,
    human: ProductionHumanEnvironmentApproval,
    *,
    at: datetime,
    requested_expiry: datetime,
    require_issue_time: datetime | None = None,
) -> None:
    _require_utc(at, "authorization evaluation timestamp")
    _require_utc(requested_expiry, "authorization expiry")
    if require_issue_time is not None:
        _require_utc(require_issue_time, "authorization issue timestamp")
    trust_hash = hash_production_integration_trust_store(trust_store)
    policy_hash = hash_production_integration_policy(policy)
    if policy.trust_store_sha256 != trust_hash:
        raise ProductionReadinessInputError("authorization policy trust-store mismatch")
    if not plan.not_before <= at < plan.expires_at:
        raise ProductionReadinessInputError("authorization production plan is not current")
    fresh_report = evaluate_production_integration_readiness(
        bundle, plan, policy, trust_store, at=report.evaluated_at
    )
    if fresh_report != report or report.decision is not ProductionReadinessDecision.READY_FOR_HUMAN_GATE:
        raise ProductionReadinessInputError(
            "authorization requires the exact READY_FOR_HUMAN_GATE report"
        )
    binding = _report_binding(report)
    if any(getattr(tco, field) != value for field, value in binding.items()):
        raise ProductionReadinessInputError("TCO/QA attestation binding mismatch")
    if any(getattr(human, field) != value for field, value in binding.items()):
        raise ProductionReadinessInputError("Human approval binding mismatch")
    if (
        human.environment_identity_sha256 != plan.environment_identity_sha256
        or human.deployment_candidate_sha256 != plan.deployment_candidate_sha256
    ):
        raise ProductionReadinessInputError("Human environment binding mismatch")
    if (
        tco.decision is not ReadinessAttestationDecision.ACCEPT
        or human.decision is not EnvironmentApprovalDecision.APPROVE
    ):
        raise ProductionReadinessInputError("TCO/QA acceptance and Human approval are required")
    if not _verify_attestation(tco, trust_store.tco_qa, SigningRole.TCO_QA):
        raise ProductionReadinessInputError("TCO/QA attestation signature invalid")
    if not _verify_attestation(
        human, trust_store.environment_human, SigningRole.HUMAN_APPROVER
    ):
        raise ProductionReadinessInputError("Human approval signature invalid")
    if not (tco.issued_at <= at < tco.expires_at and human.issued_at <= at < human.expires_at):
        raise ProductionReadinessInputError("TCO/QA or Human approval is not current")
    if tco.expires_at - tco.issued_at > timedelta(
        seconds=policy.maximum_tco_attestation_ttl_seconds
    ):
        raise ProductionReadinessInputError("TCO/QA attestation TTL exceeds policy")
    if human.expires_at - human.issued_at > timedelta(
        seconds=policy.maximum_human_approval_ttl_seconds
    ):
        raise ProductionReadinessInputError("Human approval TTL exceeds policy")
    if require_issue_time is not None and require_issue_time > at:
        raise ProductionReadinessInputError("authorization issue time is in the future")
    issue_time = require_issue_time if require_issue_time is not None else at
    if not (
        report.evaluated_at <= tco.issued_at <= issue_time
        and report.evaluated_at <= human.issued_at <= issue_time
    ):
        raise ProductionReadinessInputError(
            "TCO/QA and Human attestations must postdate the report and predate authorization"
        )
    earliest_expiry = min(
        report.expires_at,
        plan.expires_at,
        tco.expires_at,
        human.expires_at,
    )
    if not (issue_time <= at < requested_expiry <= earliest_expiry):
        raise ProductionReadinessInputError("authorization must expire before every input")
    if requested_expiry - issue_time > timedelta(
        seconds=policy.maximum_authorization_ttl_seconds
    ):
        raise ProductionReadinessInputError("authorization TTL exceeds policy")


def _build_signed_model(
    model_type: Any,
    values: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    key_field: str,
) -> Any:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("signer must be an Ed25519 private key")
    values = {"schema_version": "1.0", **values, key_field: _private_key_id(private_key)}
    provisional = model_type.model_construct(
        **values, payload_sha256="0" * 64, signature_base64url="A" * 86
    )
    payload_sha256 = _canonical_sha256(
        provisional.model_dump(
            mode="json", exclude={"payload_sha256", "signature_base64url"}
        )
    )
    return model_type(
        **values,
        payload_sha256=payload_sha256,
        signature_base64url=_sign(private_key, payload_sha256),
    )


def _validate_signed_payload(model: Any, label: str) -> None:
    if model.expires_at <= model.issued_at:
        raise ValueError(f"{label} expiry must follow issue time")
    expected = _canonical_sha256(
        model.model_dump(mode="json", exclude={"payload_sha256", "signature_base64url"})
    )
    if model.payload_sha256 != expected:
        raise ValueError(f"{label} payload hash mismatch")


def _verify_attestation(
    model: Any, key: Ed25519VerificationKey, role: SigningRole
) -> bool:
    return _verify_signed_hash(
        model.payload_sha256,
        model.signature_base64url,
        key,
        issuer=model.issuer,
        key_id=model.key_id_sha256,
        role=model.signer_role,
        expected_role=role,
    )


def _verify_signed_hash(
    payload_sha256: str,
    signature_base64url: str,
    key: Ed25519VerificationKey,
    *,
    issuer: str,
    key_id: str,
    role: SigningRole,
    expected_role: SigningRole,
) -> bool:
    if (
        key.issuer != issuer
        or key.key_id_sha256 != key_id
        or key.role is not expected_role
        or role is not expected_role
    ):
        return False
    try:
        key.public_key().verify(
            _decode_base64url(signature_base64url, expected_length=64),
            bytes.fromhex(payload_sha256),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _private_key_matches(
    signer: Ed25519PrivateKey, expected_verifier: Ed25519VerificationKey
) -> bool:
    return isinstance(signer, Ed25519PrivateKey) and _private_key_id(
        signer
    ) == expected_verifier.key_id_sha256


def _private_key_id(private_key: Ed25519PrivateKey) -> str:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("signer must be an Ed25519 private key")
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(public_bytes).hexdigest()


def _require_sha256(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} identity must be SHA-256")
    return value


def _require_authentication_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("ledger authentication key must be at least 32 bytes")
    return bytes(value)


def _sign(private_key: Ed25519PrivateKey, payload_sha256: str) -> str:
    return _encode_base64url(private_key.sign(bytes.fromhex(payload_sha256)))


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _copy(value: Any, expected_type: Any) -> Any:
    if type(value) is not expected_type:
        raise TypeError(f"expected exact {expected_type.__name__}")
    return expected_type.model_validate(value.model_dump())


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str, *, expected_length: int) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url encoding") from exc
    if len(decoded) != expected_length:
        raise ValueError("invalid base64url length")
    return decoded
