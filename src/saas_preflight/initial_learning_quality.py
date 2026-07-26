"""Fail-closed quality gate for the first owned learning data.

The gate does not fetch, persist, publish, or train a model.  It verifies that
sanitized source profiles and Human labels are current, complete, non-synthetic,
and independently attested before they may be considered for a controlled
learning run.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from .growth_system import GoldDomain, LearningGoldSet
from .models import CurrencyCode, Sha256, Slug, StrictModel


class InitialLearningSourceKind(str, Enum):
    FIELD_EVIDENCE = "field_evidence"
    KEYWORD_DEMAND = "keyword_demand"
    SEARCH_CONSOLE = "search_console"
    ANALYTICS = "analytics"
    AFFILIATE = "affiliate"
    OPERATIONS = "operations"


class InitialLearningAttestationRole(str, Enum):
    SOURCE_STEWARD = "source_steward"
    HUMAN_LABELER = "human_labeler"
    TCO_QA = "tco_qa"


class InitialLearningQualityDecision(str, Enum):
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    STOP = "stop"


class InitialLearningQualityReason(str, Enum):
    POLICY_MISMATCH = "policy_mismatch"
    POLICY_NOT_CURRENT = "policy_not_current"
    AUTHORITY_ROOT_MISMATCH = "authority_root_mismatch"
    REQUIRED_SOURCE_MISSING = "required_source_missing"
    SOURCE_NOT_CURRENT = "source_not_current"
    SOURCE_CAPTURE_STALE = "source_capture_stale"
    SOURCE_REPORTING_LAG_EXCEEDED = "source_reporting_lag_exceeded"
    SOURCE_CONTRACT_INVALID = "source_contract_invalid"
    SOURCE_ATTESTATION_INVALID = "source_attestation_invalid"
    DUPLICATE_RATE_EXCEEDED = "duplicate_rate_exceeded"
    QUARANTINE_RATE_EXCEEDED = "quarantine_rate_exceeded"
    MISSING_RATE_EXCEEDED = "missing_rate_exceeded"
    ORPHAN_ROWS_PRESENT = "orphan_rows_present"
    JOIN_COVERAGE_INSUFFICIENT = "join_coverage_insufficient"
    SCHEMA_DRIFT = "schema_drift"
    SENSITIVE_DATA_PRESENT = "sensitive_data_present"
    SYNTHETIC_SOURCE = "synthetic_source"
    MODELED_SOURCE = "modeled_source"
    TARGET_SCOPE_MISMATCH = "target_scope_mismatch"
    GOLDSET_NOT_CURRENT = "goldset_not_current"
    GOLDSET_SYNTHETIC = "goldset_synthetic"
    GOLDSET_DOMAIN_COVERAGE = "goldset_domain_coverage"
    HUMAN_LABEL_ATTESTATION_INVALID = "human_label_attestation_invalid"
    QA_ATTESTATION_INVALID = "qa_attestation_invalid"


class InitialLearningVerificationKey(StrictModel):
    issuer: Slug
    key_id_sha256: Sha256
    public_key_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")

    @field_validator("public_key_base64url")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _decode_base64url(value, expected_length=32)
        return value

    @model_validator(mode="after")
    def validate_key_id(self) -> Self:
        public_bytes = _decode_base64url(
            self.public_key_base64url, expected_length=32
        )
        if hashlib.sha256(public_bytes).hexdigest() != self.key_id_sha256:
            raise ValueError("initial-learning key ID must hash the public key")
        return self

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(
            _decode_base64url(self.public_key_base64url, expected_length=32)
        )


class InitialLearningTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_steward: InitialLearningVerificationKey
    human_labeler: InitialLearningVerificationKey
    tco_qa: InitialLearningVerificationKey

    @model_validator(mode="after")
    def require_distinct_keys(self) -> Self:
        ids = (
            self.source_steward.key_id_sha256,
            self.human_labeler.key_id_sha256,
            self.tco_qa.key_id_sha256,
        )
        if len(ids) != len(set(ids)):
            raise ValueError("initial-learning trust roles require distinct keys")
        return self

    def key_for(self, role: InitialLearningAttestationRole) -> InitialLearningVerificationKey:
        return {
            InitialLearningAttestationRole.SOURCE_STEWARD: self.source_steward,
            InitialLearningAttestationRole.HUMAN_LABELER: self.human_labeler,
            InitialLearningAttestationRole.TCO_QA: self.tco_qa,
        }[role]


class InitialLearningQualityPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id_sha256: Sha256
    created_at: datetime
    expires_at: datetime
    required_source_kinds: tuple[InitialLearningSourceKind, ...] = Field(min_length=1)
    join_required_kinds: tuple[InitialLearningSourceKind, ...] = ()
    minimum_cases_per_domain: int = Field(default=3, ge=1, le=1000)
    maximum_duplicate_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    maximum_quarantine_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    maximum_missing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    minimum_join_coverage: Decimal = Field(default=Decimal("0.99"), ge=0, le=1)
    maximum_capture_age_seconds: int = Field(default=604_800, ge=1, le=31_536_000)
    maximum_reporting_lag_seconds: int = Field(default=86_400, ge=0, le=2_592_000)
    maximum_attestation_age_seconds: int = Field(default=86_400, ge=1, le=2_592_000)

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "initial-learning policy timestamp")

    @field_validator("required_source_kinds", "join_required_kinds")
    @classmethod
    def canonicalize_kinds(
        cls, values: tuple[InitialLearningSourceKind, ...]
    ) -> tuple[InitialLearningSourceKind, ...]:
        if len(values) != len(set(values)):
            raise ValueError("initial-learning source kinds must be unique")
        return tuple(sorted(values, key=lambda item: item.value))

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("initial-learning policy expiry must follow creation")
        if not set(self.join_required_kinds) <= set(self.required_source_kinds):
            raise ValueError("join-required source kinds must also be required")
        return self


class InitialLearningDatasetProfile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id_sha256: Sha256
    kind: InitialLearningSourceKind
    raw_export_receipt_sha256: Sha256
    safe_summary_sha256: Sha256
    authority_record_sha256: Sha256
    schema_sha256: Sha256
    mapping_version_sha256: Sha256
    extraction_spec_sha256: Sha256
    coverage_manifest_sha256: Sha256
    expected_grain_sha256: Sha256
    candidate_key_sha256: Sha256
    reporting_period_start: datetime
    reporting_period_end: datetime
    captured_at: datetime
    expires_at: datetime
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    source_timezone: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_+:/-]+$")
    canonical_timezone: Literal["UTC"] = "UTC"
    currency: CurrencyCode | None = None
    rows_received: int = Field(gt=0)
    rows_accepted: int = Field(gt=0)
    duplicate_rows: int = Field(ge=0)
    quarantined_rows: int = Field(ge=0)
    required_values_total: int = Field(gt=0)
    required_values_missing: int = Field(ge=0)
    orphan_rows: int = Field(ge=0)
    join_parent_rows: int = Field(ge=0)
    join_matched_rows: int = Field(ge=0)
    schema_drift_detected: bool = False
    duplicate_headers_detected: bool = False
    mixed_currency_detected: bool = False
    ambiguous_timestamps_detected: bool = False
    unknown_state_rows: int = Field(default=0, ge=0)
    contains_sensitive_data: bool = False
    synthetic: bool = False
    modeled: bool = False

    @field_validator(
        "reporting_period_start", "reporting_period_end", "captured_at", "expires_at"
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "initial-learning dataset timestamp")

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.reporting_period_end <= self.reporting_period_start:
            raise ValueError("reporting period end must follow start")
        if self.captured_at < self.reporting_period_end:
            raise ValueError("dataset capture cannot predate reporting period end")
        if self.expires_at <= self.captured_at:
            raise ValueError("dataset expiry must follow capture")
        if self.rows_received != (
            self.rows_accepted + self.duplicate_rows + self.quarantined_rows
        ):
            raise ValueError("dataset row accounting must be exact")
        if self.required_values_missing > self.required_values_total:
            raise ValueError("missing required values cannot exceed total required values")
        if self.join_matched_rows > self.join_parent_rows:
            raise ValueError("matched join rows cannot exceed parent rows")
        if self.join_parent_rows == 0 and self.join_matched_rows != 0:
            raise ValueError("zero-parent join must have zero matched rows")
        if self.kind is InitialLearningSourceKind.AFFILIATE and self.currency != "JPY":
            raise ValueError("initial affiliate learning profile must use JPY")
        return self

    @property
    def duplicate_rate(self) -> Decimal:
        return Decimal(self.duplicate_rows) / Decimal(self.rows_received)

    @property
    def quarantine_rate(self) -> Decimal:
        return Decimal(self.quarantined_rows) / Decimal(self.rows_received)

    @property
    def missing_rate(self) -> Decimal:
        return Decimal(self.required_values_missing) / Decimal(self.required_values_total)

    @property
    def join_coverage(self) -> Decimal | None:
        if self.join_parent_rows == 0:
            return None
        return Decimal(self.join_matched_rows) / Decimal(self.join_parent_rows)


class InitialLearningAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    role: InitialLearningAttestationRole
    issuer: Slug
    key_id_sha256: Sha256
    subject_sha256: Sha256
    policy_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "initial-learning attestation timestamp")

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("initial-learning attestation expiry must follow issue")
        if self.payload_sha256 != initial_learning_attestation_payload_sha256(self):
            raise ValueError("initial-learning attestation payload hash mismatch")
        _decode_base64url(self.signature_base64url, expected_length=64)
        return self


class InitialLearningQualityBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    bundle_id_sha256: Sha256
    policy_sha256: Sha256
    datasets: tuple[InitialLearningDatasetProfile, ...]
    learning_gold_set: LearningGoldSet
    source_and_label_attestations: tuple[InitialLearningAttestation, ...]
    input_root_sha256: Sha256
    qa_attestation: InitialLearningAttestation

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        ordering = [(item.kind.value, item.dataset_id_sha256) for item in self.datasets]
        if ordering != sorted(ordering) or len(ordering) != len(set(ordering)):
            raise ValueError("initial-learning datasets must be unique and canonically sorted")
        attestation_order = [
            (item.role.value, item.subject_sha256, item.payload_sha256)
            for item in self.source_and_label_attestations
        ]
        if attestation_order != sorted(attestation_order) or len(attestation_order) != len(
            set(attestation_order)
        ):
            raise ValueError("initial-learning attestations must be unique and canonically sorted")
        subject_roles = [
            (item.subject_sha256, item.role)
            for item in self.source_and_label_attestations
        ]
        if len(subject_roles) != len(set(subject_roles)):
            raise ValueError("initial-learning subject/role attestations must be unambiguous")
        expected_subject_roles = {
            (
                hash_initial_learning_artifact(dataset),
                InitialLearningAttestationRole.SOURCE_STEWARD,
            )
            for dataset in self.datasets
        }
        expected_subject_roles.add(
            (
                hash_initial_learning_artifact(self.learning_gold_set),
                InitialLearningAttestationRole.HUMAN_LABELER,
            )
        )
        if set(subject_roles) != expected_subject_roles:
            raise ValueError(
                "initial-learning bundle requires exactly one source attestation "
                "per dataset and one Human label attestation"
            )
        expected_root = initial_learning_input_root_sha256(
            bundle_id_sha256=self.bundle_id_sha256,
            policy_sha256=self.policy_sha256,
            datasets=self.datasets,
            learning_gold_set=self.learning_gold_set,
            source_and_label_attestations=self.source_and_label_attestations,
        )
        if self.input_root_sha256 != expected_root:
            raise ValueError("initial-learning input root mismatch")
        if self.qa_attestation.role is not InitialLearningAttestationRole.TCO_QA:
            raise ValueError("initial-learning QA attestation requires TCO/QA role")
        if self.qa_attestation.subject_sha256 != self.input_root_sha256:
            raise ValueError("initial-learning QA attestation must bind the input root")
        if self.qa_attestation.policy_sha256 != self.policy_sha256:
            raise ValueError("initial-learning QA attestation must bind the policy")
        return self


class InitialLearningQualityCheck(StrictModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_.:-]+$")
    passed: bool
    subject_sha256: Sha256 | None = None
    observed: str = Field(min_length=1, max_length=160)
    requirement: str = Field(min_length=1, max_length=160)


class InitialLearningQualityReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    bundle_id_sha256: Sha256
    input_root_sha256: Sha256
    evaluated_at: datetime
    decision: InitialLearningQualityDecision
    checks: tuple[InitialLearningQualityCheck, ...]
    reasons: tuple[InitialLearningQualityReason, ...]
    authority: Literal["none"] = "none"

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "initial-learning evaluation timestamp")

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        names = [item.name for item in self.checks]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("initial-learning checks must be unique and canonically sorted")
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise ValueError("initial-learning reasons must be unique and canonically sorted")
        expected = (
            InitialLearningQualityDecision.READY_FOR_HUMAN_REVIEW
            if all(item.passed for item in self.checks)
            else InitialLearningQualityDecision.STOP
        )
        if self.decision is not expected:
            raise ValueError("initial-learning decision does not match checks")
        return self


def evaluate_initial_learning_quality(
    bundle: InitialLearningQualityBundle,
    policy: InitialLearningQualityPolicy,
    trust_store: InitialLearningTrustStore,
    *,
    expected_authority_sha256: str,
    at: datetime,
) -> InitialLearningQualityReport:
    """Evaluate data and label quality; never grants learning or publication authority."""

    instant = _utc(at, "initial-learning evaluation timestamp")
    policy_sha256 = hash_initial_learning_artifact(policy)
    checks: list[InitialLearningQualityCheck] = []
    reasons: set[InitialLearningQualityReason] = set()

    def add(
        name: str,
        passed: bool,
        observed: str,
        requirement: str,
        reason: InitialLearningQualityReason,
        subject_sha256: str | None = None,
    ) -> None:
        checks.append(
            InitialLearningQualityCheck(
                name=name,
                passed=passed,
                subject_sha256=subject_sha256,
                observed=observed,
                requirement=requirement,
            )
        )
        if not passed:
            reasons.add(reason)

    policy_matches = bundle.policy_sha256 == policy_sha256
    add(
        "authority.policy_binding",
        policy_matches,
        "match" if policy_matches else "mismatch",
        "bundle binds exact policy",
        InitialLearningQualityReason.POLICY_MISMATCH,
        policy_sha256,
    )
    policy_current = policy.created_at <= instant < policy.expires_at
    add(
        "authority.policy_current",
        policy_current,
        "current" if policy_current else "not_current",
        "created_at <= evaluation < expires_at",
        InitialLearningQualityReason.POLICY_NOT_CURRENT,
        policy_sha256,
    )
    authority_sha256 = initial_learning_authority_sha256(policy, trust_store)
    authority_matches = authority_sha256 == expected_authority_sha256
    add(
        "authority.root",
        authority_matches,
        "match" if authority_matches else "mismatch",
        "consumer-pinned policy and trust root",
        InitialLearningQualityReason.AUTHORITY_ROOT_MISMATCH,
        authority_sha256,
    )

    kinds = {item.kind for item in bundle.datasets}
    missing_kinds = set(policy.required_source_kinds) - kinds
    add(
        "coverage.required_sources",
        not missing_kinds,
        (
            "complete"
            if not missing_kinds
            else "missing:" + ",".join(sorted(x.value for x in missing_kinds))
        ),
        "all policy-required source kinds present",
        InitialLearningQualityReason.REQUIRED_SOURCE_MISSING,
    )

    attestation_by_subject_role = {
        (item.subject_sha256, item.role): item
        for item in bundle.source_and_label_attestations
    }
    for dataset in bundle.datasets:
        subject = hash_initial_learning_artifact(dataset)
        prefix = f"dataset.{dataset.kind.value}.{dataset.dataset_id_sha256[:12]}"
        current = (
            dataset.reporting_period_end <= dataset.captured_at <= instant < dataset.expires_at
        )
        add(
            f"{prefix}.current",
            current,
            "current" if current else "not_current",
            "period_end <= captured_at <= evaluation < expires_at",
            InitialLearningQualityReason.SOURCE_NOT_CURRENT,
            subject,
        )
        capture_age = instant - dataset.captured_at
        capture_fresh = timedelta(0) <= capture_age <= timedelta(
            seconds=policy.maximum_capture_age_seconds
        )
        add(
            f"{prefix}.capture_freshness",
            capture_fresh,
            str(int(capture_age.total_seconds())),
            f"0..{policy.maximum_capture_age_seconds} seconds",
            InitialLearningQualityReason.SOURCE_CAPTURE_STALE,
            subject,
        )
        reporting_lag = dataset.captured_at - dataset.reporting_period_end
        reporting_lag_ok = reporting_lag <= timedelta(
            seconds=policy.maximum_reporting_lag_seconds
        )
        add(
            f"{prefix}.reporting_lag",
            reporting_lag_ok,
            str(int(reporting_lag.total_seconds())),
            f"<= {policy.maximum_reporting_lag_seconds} seconds",
            InitialLearningQualityReason.SOURCE_REPORTING_LAG_EXCEEDED,
            subject,
        )
        source_contract_ok = not (
            dataset.duplicate_headers_detected
            or dataset.mixed_currency_detected
            or dataset.ambiguous_timestamps_detected
            or dataset.unknown_state_rows
        )
        add(
            f"{prefix}.source_contract",
            source_contract_ok,
            (
                "valid"
                if source_contract_ok
                else "duplicate_headers="
                f"{str(dataset.duplicate_headers_detected).lower()},"
                f"mixed_currency={str(dataset.mixed_currency_detected).lower()},"
                f"ambiguous_timestamps={str(dataset.ambiguous_timestamps_detected).lower()},"
                f"unknown_state_rows={dataset.unknown_state_rows}"
            ),
            "no duplicate headers, mixed currency, ambiguous timestamps, or unknown states",
            InitialLearningQualityReason.SOURCE_CONTRACT_INVALID,
            subject,
        )
        source_attestation = attestation_by_subject_role.get(
            (subject, InitialLearningAttestationRole.SOURCE_STEWARD)
        )
        signature_ok = source_attestation is not None and _verify_attestation(
            source_attestation,
            trust_store.key_for(InitialLearningAttestationRole.SOURCE_STEWARD),
            expected_role=InitialLearningAttestationRole.SOURCE_STEWARD,
            expected_policy_sha256=policy_sha256,
            expected_subject_sha256=subject,
            maximum_age_seconds=policy.maximum_attestation_age_seconds,
            at=instant,
        )
        add(
            f"{prefix}.source_attestation",
            signature_ok,
            "verified" if signature_ok else "invalid_or_missing",
            "current source-steward signature over exact profile",
            InitialLearningQualityReason.SOURCE_ATTESTATION_INVALID,
            subject,
        )
        add(
            f"{prefix}.duplicates",
            dataset.duplicate_rate <= policy.maximum_duplicate_rate,
            str(dataset.duplicate_rate),
            f"<= {policy.maximum_duplicate_rate}",
            InitialLearningQualityReason.DUPLICATE_RATE_EXCEEDED,
            subject,
        )
        add(
            f"{prefix}.quarantine",
            dataset.quarantine_rate <= policy.maximum_quarantine_rate,
            str(dataset.quarantine_rate),
            f"<= {policy.maximum_quarantine_rate}",
            InitialLearningQualityReason.QUARANTINE_RATE_EXCEEDED,
            subject,
        )
        add(
            f"{prefix}.missing",
            dataset.missing_rate <= policy.maximum_missing_rate,
            str(dataset.missing_rate),
            f"<= {policy.maximum_missing_rate}",
            InitialLearningQualityReason.MISSING_RATE_EXCEEDED,
            subject,
        )
        add(
            f"{prefix}.orphans",
            dataset.orphan_rows == 0,
            str(dataset.orphan_rows),
            "0",
            InitialLearningQualityReason.ORPHAN_ROWS_PRESENT,
            subject,
        )
        if dataset.kind in policy.join_required_kinds:
            join_coverage = dataset.join_coverage
            join_ok = join_coverage is not None and join_coverage >= policy.minimum_join_coverage
            add(
                f"{prefix}.join_coverage",
                join_ok,
                "undefined" if join_coverage is None else str(join_coverage),
                f">= {policy.minimum_join_coverage}",
                InitialLearningQualityReason.JOIN_COVERAGE_INSUFFICIENT,
                subject,
            )
        add(
            f"{prefix}.schema",
            not dataset.schema_drift_detected,
            "stable" if not dataset.schema_drift_detected else "drift",
            "no unreviewed schema drift",
            InitialLearningQualityReason.SCHEMA_DRIFT,
            subject,
        )
        add(
            f"{prefix}.sensitive_data",
            not dataset.contains_sensitive_data,
            "absent" if not dataset.contains_sensitive_data else "present",
            "no sensitive data",
            InitialLearningQualityReason.SENSITIVE_DATA_PRESENT,
            subject,
        )
        add(
            f"{prefix}.synthetic",
            not dataset.synthetic,
            str(dataset.synthetic).lower(),
            "false",
            InitialLearningQualityReason.SYNTHETIC_SOURCE,
            subject,
        )
        add(
            f"{prefix}.modeled",
            not dataset.modeled,
            str(dataset.modeled).lower(),
            "false",
            InitialLearningQualityReason.MODELED_SOURCE,
            subject,
        )
        scope_ok = dataset.country == "JP" and dataset.language == "ja"
        add(
            f"{prefix}.scope",
            scope_ok,
            f"{dataset.country}/{dataset.language}",
            "JP/ja",
            InitialLearningQualityReason.TARGET_SCOPE_MISMATCH,
            subject,
        )

    cases_by_domain = {
        domain: [item for item in bundle.learning_gold_set.cases if item.domain is domain]
        for domain in GoldDomain
    }
    gold_current = (
        bundle.learning_gold_set.created_at
        <= instant
        < bundle.learning_gold_set.expires_at
    )
    add(
        "goldset.current",
        gold_current,
        "current" if gold_current else "not_current",
        "created_at <= evaluation < expires_at",
        InitialLearningQualityReason.GOLDSET_NOT_CURRENT,
        hash_initial_learning_artifact(bundle.learning_gold_set),
    )
    gold_non_synthetic = all(not item.synthetic for item in bundle.learning_gold_set.cases)
    add(
        "goldset.non_synthetic",
        gold_non_synthetic,
        "all_real" if gold_non_synthetic else "contains_synthetic",
        "all Human gold cases are non-synthetic",
        InitialLearningQualityReason.GOLDSET_SYNTHETIC,
        hash_initial_learning_artifact(bundle.learning_gold_set),
    )
    domain_coverage_ok = all(
        len(cases) >= policy.minimum_cases_per_domain for cases in cases_by_domain.values()
    )
    add(
        "goldset.domain_coverage",
        domain_coverage_ok,
        ",".join(f"{domain.value}:{len(cases_by_domain[domain])}" for domain in GoldDomain),
        f">= {policy.minimum_cases_per_domain} per domain",
        InitialLearningQualityReason.GOLDSET_DOMAIN_COVERAGE,
        hash_initial_learning_artifact(bundle.learning_gold_set),
    )
    gold_subject = hash_initial_learning_artifact(bundle.learning_gold_set)
    label_attestation = attestation_by_subject_role.get(
        (gold_subject, InitialLearningAttestationRole.HUMAN_LABELER)
    )
    label_signature_ok = label_attestation is not None and _verify_attestation(
        label_attestation,
        trust_store.key_for(InitialLearningAttestationRole.HUMAN_LABELER),
        expected_role=InitialLearningAttestationRole.HUMAN_LABELER,
        expected_policy_sha256=policy_sha256,
        expected_subject_sha256=gold_subject,
        maximum_age_seconds=policy.maximum_attestation_age_seconds,
        at=instant,
    )
    add(
        "goldset.human_attestation",
        label_signature_ok,
        "verified" if label_signature_ok else "invalid_or_missing",
        "current Human-labeler signature over exact gold set",
        InitialLearningQualityReason.HUMAN_LABEL_ATTESTATION_INVALID,
        gold_subject,
    )

    qa_ok = _verify_attestation(
        bundle.qa_attestation,
        trust_store.key_for(InitialLearningAttestationRole.TCO_QA),
        expected_role=InitialLearningAttestationRole.TCO_QA,
        expected_policy_sha256=policy_sha256,
        expected_subject_sha256=bundle.input_root_sha256,
        maximum_age_seconds=policy.maximum_attestation_age_seconds,
        at=instant,
    )
    add(
        "quality.qa_attestation",
        qa_ok,
        "verified" if qa_ok else "invalid",
        "current independent QA signature over exact input root",
        InitialLearningQualityReason.QA_ATTESTATION_INVALID,
        bundle.input_root_sha256,
    )

    ordered_checks = tuple(sorted(checks, key=lambda item: item.name))
    ordered_reasons = tuple(sorted(reasons, key=lambda item: item.value))
    return InitialLearningQualityReport(
        bundle_id_sha256=bundle.bundle_id_sha256,
        input_root_sha256=bundle.input_root_sha256,
        evaluated_at=instant,
        decision=(
            InitialLearningQualityDecision.READY_FOR_HUMAN_REVIEW
            if all(item.passed for item in ordered_checks)
            else InitialLearningQualityDecision.STOP
        ),
        checks=ordered_checks,
        reasons=ordered_reasons,
    )


def hash_initial_learning_artifact(value: StrictModel) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def initial_learning_attestation_payload_sha256(
    value: InitialLearningAttestation,
) -> str:
    return _canonical_sha256(
        value.model_dump(
            mode="json", exclude={"payload_sha256", "signature_base64url"}
        )
    )


def initial_learning_input_root_sha256(
    *,
    bundle_id_sha256: str,
    policy_sha256: str,
    datasets: tuple[InitialLearningDatasetProfile, ...],
    learning_gold_set: LearningGoldSet,
    source_and_label_attestations: tuple[InitialLearningAttestation, ...],
) -> str:
    return _canonical_sha256(
        {
            "bundle_id_sha256": bundle_id_sha256,
            "policy_sha256": policy_sha256,
            "dataset_sha256s": [hash_initial_learning_artifact(item) for item in datasets],
            "learning_gold_set_sha256": hash_initial_learning_artifact(learning_gold_set),
            "attestation_sha256s": [
                hash_initial_learning_artifact(item)
                for item in source_and_label_attestations
            ],
        }
    )


def initial_learning_authority_sha256(
    policy: InitialLearningQualityPolicy, trust_store: InitialLearningTrustStore
) -> str:
    return _canonical_sha256(
        {
            "policy_sha256": hash_initial_learning_artifact(policy),
            "trust_store_sha256": hash_initial_learning_artifact(trust_store),
        }
    )


def build_initial_learning_verification_key(
    public_key: Ed25519PublicKey, *, issuer: str
) -> InitialLearningVerificationKey:
    """Build a public, repository-safe key record; never persists private key data."""

    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("initial-learning verification key must be Ed25519")
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return InitialLearningVerificationKey(
        issuer=issuer,
        key_id_sha256=hashlib.sha256(public_bytes).hexdigest(),
        public_key_base64url=base64.urlsafe_b64encode(public_bytes)
        .decode("ascii")
        .rstrip("="),
    )


def sign_initial_learning_attestation(
    private_key: Ed25519PrivateKey,
    verification_key: InitialLearningVerificationKey,
    *,
    role: InitialLearningAttestationRole,
    subject_sha256: str,
    policy_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
) -> InitialLearningAttestation:
    """Sign one bounded attestation without writing or returning private key bytes."""

    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("initial-learning signer must be Ed25519")
    derived_key = build_initial_learning_verification_key(
        private_key.public_key(), issuer=verification_key.issuer
    )
    if derived_key != verification_key:
        raise ValueError("initial-learning signer does not match verification key")
    unsigned = InitialLearningAttestation.model_construct(
        schema_version="1.0",
        role=role,
        issuer=verification_key.issuer,
        key_id_sha256=verification_key.key_id_sha256,
        subject_sha256=subject_sha256,
        policy_sha256=policy_sha256,
        issued_at=issued_at,
        expires_at=expires_at,
        payload_sha256="0" * 64,
        signature_base64url="A" * 86,
    )
    payload_sha256 = initial_learning_attestation_payload_sha256(unsigned)
    signature = private_key.sign(bytes.fromhex(payload_sha256))
    return InitialLearningAttestation(
        **unsigned.model_dump(exclude={"payload_sha256", "signature_base64url"}),
        payload_sha256=payload_sha256,
        signature_base64url=base64.urlsafe_b64encode(signature)
        .decode("ascii")
        .rstrip("="),
    )


def _verify_attestation(
    value: InitialLearningAttestation,
    key: InitialLearningVerificationKey,
    *,
    expected_role: InitialLearningAttestationRole,
    expected_policy_sha256: str,
    expected_subject_sha256: str,
    maximum_age_seconds: int,
    at: datetime,
) -> bool:
    if (
        value.role is not expected_role
        or value.issuer != key.issuer
        or value.key_id_sha256 != key.key_id_sha256
        or value.policy_sha256 != expected_policy_sha256
        or value.subject_sha256 != expected_subject_sha256
        or value.issued_at > at
        or value.expires_at <= at
        or at - value.issued_at > timedelta(seconds=maximum_age_seconds)
    ):
        return False
    try:
        key.public_key().verify(
            _decode_base64url(value.signature_base64url, expected_length=64),
            bytes.fromhex(value.payload_sha256),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _decode_base64url(value: str, *, expected_length: int) -> bytes:
    try:
        result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url value") from exc
    if len(result) != expected_length:
        raise ValueError("invalid base64url decoded length")
    return result


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value


__all__ = [
    "InitialLearningAttestation",
    "InitialLearningAttestationRole",
    "InitialLearningDatasetProfile",
    "InitialLearningQualityBundle",
    "InitialLearningQualityCheck",
    "InitialLearningQualityDecision",
    "InitialLearningQualityPolicy",
    "InitialLearningQualityReason",
    "InitialLearningQualityReport",
    "InitialLearningSourceKind",
    "InitialLearningTrustStore",
    "InitialLearningVerificationKey",
    "build_initial_learning_verification_key",
    "evaluate_initial_learning_quality",
    "hash_initial_learning_artifact",
    "initial_learning_attestation_payload_sha256",
    "initial_learning_authority_sha256",
    "initial_learning_input_root_sha256",
    "sign_initial_learning_attestation",
]
