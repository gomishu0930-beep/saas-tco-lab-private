"""Signed, append-only settlement amendments for a complete P12 cohort.

The boundary is deliberately narrow.  It accepts only later transaction status
events and full payout reversals.  Every event is content-bound to the original
P12 transaction, while consumer-owned pins bind the complete original
report/plan/index/cohort-batch/cohort-attestation set.  No network, URL,
credential, account identifier, or external side effect is accepted here.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
)
from .measurement_integrity import (
    AcquisitionClass,
    CohortIntegrityBatch,
    CoveragePartitionKind,
    MeasurementAuthorityPins,
    MeasurementBundleIndex,
    MeasurementDataset,
    MeasurementIntegrityReport,
    MeasurementPolicy,
    MeasurementTrustStore,
    PayoutAdjustmentKind,
    ProducerAttestation,
    RunFreezeDecision,
    SignedMeasurementRunPlan,
    TransactionStatus,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    verify_measurement_integrity_report,
)
from .models import CurrencyCode, Sha256, Slug, StrictModel


class SettlementAmendmentError(ValueError):
    """A settlement amendment cannot be trusted or reconciled."""


class SettlementEventKind(str, Enum):
    STATUS_CHANGE = "status_change"
    PAYOUT_ADJUSTMENT = "payout_adjustment"


class SettlementCompletenessDecision(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class SettlementAmendmentTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    amendment_producer: Ed25519VerificationKey
    completeness_verifier: Ed25519VerificationKey

    @model_validator(mode="after")
    def validate_roles_and_separation(self) -> Self:
        if self.amendment_producer.role is not SigningRole.COHORT_PRODUCER:
            raise ValueError("amendment producer must use the cohort producer role")
        if self.completeness_verifier.role is not SigningRole.TCO_QA:
            raise ValueError("completeness verifier must use the TCO/QA role")
        if (
            self.amendment_producer.key_id_sha256
            == self.completeness_verifier.key_id_sha256
        ):
            raise ValueError("amendment and completeness roles require distinct keys")
        return self


class SettlementAmendmentPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    trust_store_sha256: Sha256
    p12_policy_sha256: Sha256
    p12_trust_store_sha256: Sha256
    completeness_rule_sha256: Sha256
    maximum_amendment_ttl_seconds: int = Field(ge=1, le=2678400)
    maximum_completeness_ttl_seconds: int = Field(ge=1, le=604800)


class SettlementAmendmentAuthorityPins(StrictModel):
    """Consumer-owned bootstrap values; never derive these from an amendment."""

    schema_version: Literal["1.0"] = "1.0"
    expected_policy_sha256: Sha256
    expected_trust_store_sha256: Sha256
    expected_p12_report_sha256: Sha256
    expected_p12_plan_sha256: Sha256
    expected_p12_bundle_index_sha256: Sha256
    expected_p12_cohort_batch_sha256: Sha256
    expected_p12_cohort_attestation_sha256: Sha256
    expected_run_id: Slug
    expected_cohort_id: Slug


class OriginalSettlementBinding(StrictModel):
    """Canonical commitment to the complete original P12 cohort evidence set."""

    schema_version: Literal["1.0"] = "1.0"
    p12_report_sha256: Sha256
    p12_policy_sha256: Sha256
    p12_trust_store_sha256: Sha256
    p12_authority_pins_sha256: Sha256
    p12_plan_sha256: Sha256
    p12_bundle_index_sha256: Sha256
    p12_cohort_batch_sha256: Sha256
    p12_cohort_attestation_sha256: Sha256
    run_id: Slug
    cohort_id: Slug
    property_record_sha256: Sha256
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    currency: CurrencyCode
    snapshot_as_of: datetime
    original_verified_at: datetime
    original_transaction_set_sha256: Sha256
    original_payout_adjustment_set_sha256: Sha256

    @field_validator("partner_ids")
    @classmethod
    def canonicalize_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("original partner IDs must be unique")
        return tuple(sorted(values))

    @field_validator("snapshot_as_of", "original_verified_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "original settlement binding timestamp")


class SettlementStatusChange(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal[SettlementEventKind.STATUS_CHANGE] = (
        SettlementEventKind.STATUS_CHANGE
    )
    event_id_sha256: Sha256
    transaction_id_sha256: Sha256
    original_transaction_sha256: Sha256
    previous_status: TransactionStatus
    current_status: TransactionStatus
    source_row_sha256: Sha256
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "settlement status change timestamp")

    @model_validator(mode="after")
    def require_forward_transition(self) -> Self:
        if self.current_status not in _ALLOWED_TRANSITIONS[self.previous_status]:
            raise ValueError("settlement status change must be a forward transition")
        return self


class SettlementPayoutAdjustment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal[SettlementEventKind.PAYOUT_ADJUSTMENT] = (
        SettlementEventKind.PAYOUT_ADJUSTMENT
    )
    event_id_sha256: Sha256
    transaction_id_sha256: Sha256
    original_transaction_sha256: Sha256
    adjustment_id_sha256: Sha256
    adjustment_kind: PayoutAdjustmentKind
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    currency: CurrencyCode
    source_row_sha256: Sha256
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "settlement payout adjustment timestamp")


SettlementEvent = Annotated[
    SettlementStatusChange | SettlementPayoutAdjustment,
    Field(discriminator="kind"),
]


class SignedSettlementAmendment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.COHORT_PRODUCER]
    amendment_id_sha256: Sha256
    policy_sha256: Sha256
    original_binding_sha256: Sha256
    run_id: Slug
    cohort_id: Slug
    property_record_sha256: Sha256
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    currency: CurrencyCode
    events: tuple[SettlementEvent, ...] = ()
    event_root_sha256: Sha256
    observed_through_at: datetime
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("partner_ids")
    @classmethod
    def canonicalize_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("amendment partner IDs must be unique")
        return tuple(sorted(values))

    @field_validator("events")
    @classmethod
    def canonicalize_events(
        cls, values: tuple[SettlementEvent, ...]
    ) -> tuple[SettlementEvent, ...]:
        ordered = tuple(
            sorted(values, key=lambda item: (item.effective_at, item.event_id_sha256))
        )
        if len({item.event_id_sha256 for item in ordered}) != len(ordered):
            raise ValueError("amendment event IDs must be unique")
        if len({item.source_row_sha256 for item in ordered}) != len(ordered):
            raise ValueError("amendment source receipts must be unique")
        return ordered

    @field_validator("observed_through_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "settlement amendment timestamp")

    @model_validator(mode="after")
    def validate_signed_amendment(self) -> Self:
        _validate_signed(self, "settlement amendment")
        if self.events and not max(
            item.effective_at for item in self.events
        ) <= self.observed_through_at:
            raise ValueError("observed_through_at must cover every amendment event")
        if not self.observed_through_at <= self.issued_at < self.expires_at:
            raise ValueError("invalid amendment issue or expiry window")
        if self.event_root_sha256 != _event_root(self.events):
            raise ValueError("settlement amendment event root mismatch")
        return self


class SettlementCompletenessCoverage(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_export_sha256: Sha256
    complete_export_receipt_sha256: Sha256
    coverage_rule_sha256: Sha256
    raw_records: int = Field(ge=0)
    accepted_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    duplicate_records: int = Field(ge=0)
    conflict_records: int = Field(ge=0)
    unknown_records: int = Field(ge=0)
    output_records: int = Field(ge=0)
    event_id_set_sha256: Sha256
    privacy_scan_sha256: Sha256
    privacy_scan_passed: Literal[True]

    @model_validator(mode="after")
    def reconcile_counts(self) -> Self:
        if self.raw_records != (
            self.accepted_records
            + self.rejected_records
            + self.duplicate_records
            + self.conflict_records
            + self.unknown_records
        ):
            raise ValueError("settlement completeness counts do not reconcile")
        if self.output_records != self.accepted_records:
            raise ValueError("settlement completeness output must equal accepted count")
        return self


class SettlementCompletenessAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA]
    decision: SettlementCompletenessDecision
    policy_sha256: Sha256
    original_binding_sha256: Sha256
    amendment_sha256: Sha256
    event_root_sha256: Sha256
    observed_through_at: datetime
    coverage: SettlementCompletenessCoverage
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_through_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "settlement completeness timestamp")

    @model_validator(mode="after")
    def validate_signed_attestation(self) -> Self:
        _validate_signed(self, "settlement completeness attestation")
        if not self.observed_through_at <= self.issued_at < self.expires_at:
            raise ValueError("invalid completeness issue or expiry window")
        return self


class PartnerSettlementAmount(StrictModel):
    """One frozen partner's original and amended settled contribution."""

    partner_id: Slug
    original_settled_amount: Decimal = Field(
        ge=0, max_digits=24, decimal_places=8
    )
    amended_settled_amount: Decimal = Field(
        ge=0, max_digits=24, decimal_places=8
    )
    settled_delta: Decimal = Field(max_digits=24, decimal_places=8)

    @model_validator(mode="after")
    def reconcile_delta(self) -> Self:
        if self.settled_delta != (
            self.amended_settled_amount - self.original_settled_amount
        ):
            raise ValueError("partner settlement delta does not reconcile")
        return self


class SettlementAmendmentEvaluation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_sha256: Sha256
    original_binding_sha256: Sha256
    run_id: Slug
    cohort_id: Slug
    currency: CurrencyCode
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    amendment_sha256s: tuple[Sha256, ...]
    completeness_attestation_sha256s: tuple[Sha256, ...]
    applied_event_root_sha256: Sha256
    final_transaction_state_root_sha256: Sha256
    applied_event_count: int = Field(ge=0)
    replayed_amendment_occurrences: int = Field(ge=0)
    replayed_event_occurrences: int = Field(ge=0)
    original_settled_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    amended_settled_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    settled_delta: Decimal = Field(max_digits=24, decimal_places=8)
    positive_settled_delta: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    negative_settled_delta: Decimal = Field(le=0, max_digits=24, decimal_places=8)
    partner_settlements: tuple[PartnerSettlementAmount, ...] = Field(min_length=1)
    evaluated_at: datetime

    @field_validator("partner_ids")
    @classmethod
    def canonicalize_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("evaluation partner IDs must be unique")
        return tuple(sorted(values))

    @field_validator("partner_settlements")
    @classmethod
    def canonicalize_partner_settlements(
        cls, values: tuple[PartnerSettlementAmount, ...]
    ) -> tuple[PartnerSettlementAmount, ...]:
        if len({item.partner_id for item in values}) != len(values):
            raise ValueError("partner settlement rows must be unique")
        return tuple(sorted(values, key=lambda item: item.partner_id))

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "settlement evaluation timestamp")

    @model_validator(mode="after")
    def reconcile_delta(self) -> Self:
        if self.settled_delta != self.amended_settled_amount - self.original_settled_amount:
            raise ValueError("settlement delta does not reconcile")
        if self.positive_settled_delta != max(self.settled_delta, Decimal(0)):
            raise ValueError("positive settlement delta does not reconcile")
        if self.negative_settled_delta != min(self.settled_delta, Decimal(0)):
            raise ValueError("negative settlement delta does not reconcile")
        if tuple(item.partner_id for item in self.partner_settlements) != (
            self.partner_ids
        ):
            raise ValueError(
                "partner settlement rows must cover the exact frozen partner set"
            )
        if sum(
            (item.original_settled_amount for item in self.partner_settlements),
            Decimal(0),
        ) != self.original_settled_amount:
            raise ValueError("partner original settlement amounts do not reconcile")
        if sum(
            (item.amended_settled_amount for item in self.partner_settlements),
            Decimal(0),
        ) != self.amended_settled_amount:
            raise ValueError("partner amended settlement amounts do not reconcile")
        if sum(
            (item.settled_delta for item in self.partner_settlements), Decimal(0)
        ) != self.settled_delta:
            raise ValueError("partner settlement deltas do not reconcile")
        return self


_ALLOWED_TRANSITIONS: dict[TransactionStatus, frozenset[TransactionStatus]] = {
    TransactionStatus.PENDING: frozenset(
        (TransactionStatus.CONFIRMED, TransactionStatus.REJECTED)
    ),
    TransactionStatus.CONFIRMED: frozenset(
        (
            TransactionStatus.PAID,
            TransactionStatus.REFUNDED,
            TransactionStatus.CHARGED_BACK,
        )
    ),
    TransactionStatus.REJECTED: frozenset(),
    TransactionStatus.PAID: frozenset(),
    TransactionStatus.REFUNDED: frozenset(),
    TransactionStatus.CHARGED_BACK: frozenset(),
}


def hash_settlement_trust_store(trust_store: SettlementAmendmentTrustStore) -> str:
    if type(trust_store) is not SettlementAmendmentTrustStore:
        raise TypeError("trust_store must be SettlementAmendmentTrustStore")
    return _canonical_sha256(
        SettlementAmendmentTrustStore.model_validate(
            trust_store.model_dump()
        ).model_dump(mode="python")
    )


def hash_settlement_policy(policy: SettlementAmendmentPolicy) -> str:
    if type(policy) is not SettlementAmendmentPolicy:
        raise TypeError("policy must be SettlementAmendmentPolicy")
    return _canonical_sha256(
        SettlementAmendmentPolicy.model_validate(
            policy.model_dump()
        ).model_dump(mode="python")
    )


def hash_original_settlement_binding(binding: OriginalSettlementBinding) -> str:
    if type(binding) is not OriginalSettlementBinding:
        raise TypeError("binding must be OriginalSettlementBinding")
    return _canonical_sha256(
        OriginalSettlementBinding.model_validate(
            binding.model_dump()
        ).model_dump(mode="python")
    )


def hash_settlement_event(event: SettlementEvent) -> str:
    if type(event) not in (SettlementStatusChange, SettlementPayoutAdjustment):
        raise TypeError("event must be a settlement event")
    return _canonical_sha256(event.model_dump(mode="python"))


def hash_settlement_artifact(artifact: StrictModel) -> str:
    if not isinstance(artifact, StrictModel):
        raise TypeError("artifact must be a StrictModel")
    return _canonical_sha256(artifact.model_dump(mode="python"))


def build_original_settlement_binding(
    report: MeasurementIntegrityReport,
    p12_policy: MeasurementPolicy,
    p12_trust_store: MeasurementTrustStore,
    p12_authority_pins: MeasurementAuthorityPins,
    plan: SignedMeasurementRunPlan,
    bundle_index: MeasurementBundleIndex,
    cohort_batch: CohortIntegrityBatch,
    cohort_attestation: ProducerAttestation,
    *,
    original_verified_at: datetime,
) -> OriginalSettlementBinding:
    """Verify and bind the complete original P12 cohort evidence slice."""

    values = _canonicalize_original_inputs(
        report,
        p12_policy,
        p12_trust_store,
        p12_authority_pins,
        plan,
        bundle_index,
        cohort_batch,
        cohort_attestation,
    )
    _utc(original_verified_at, "original verification timestamp")
    _verify_original_artifacts(*values, original_verified_at=original_verified_at)
    (
        report,
        p12_policy,
        p12_trust_store,
        p12_authority_pins,
        plan,
        bundle_index,
        cohort_batch,
        cohort_attestation,
    ) = values
    del cohort_attestation
    return OriginalSettlementBinding(
        p12_report_sha256=hash_signed_artifact(report),
        p12_policy_sha256=hash_measurement_policy(p12_policy),
        p12_trust_store_sha256=hash_measurement_trust_store(p12_trust_store),
        p12_authority_pins_sha256=hash_signed_artifact(p12_authority_pins),
        p12_plan_sha256=hash_signed_artifact(plan),
        p12_bundle_index_sha256=hash_signed_artifact(bundle_index),
        p12_cohort_batch_sha256=hash_signed_artifact(cohort_batch),
        p12_cohort_attestation_sha256=bundle_index.cohort_attestation_sha256,
        run_id=plan.definition.run_id,
        cohort_id=cohort_batch.cohort_id,
        property_record_sha256=cohort_batch.property_record_sha256,
        partner_ids=cohort_batch.partner_ids,
        currency=cohort_batch.currency,
        snapshot_as_of=cohort_batch.snapshot_as_of.astimezone(timezone.utc),
        original_verified_at=original_verified_at,
        original_transaction_set_sha256=_transaction_set_root(cohort_batch),
        original_payout_adjustment_set_sha256=_original_adjustment_set_root(
            cohort_batch
        ),
    )


def verify_original_settlement_binding(
    binding: OriginalSettlementBinding,
    report: MeasurementIntegrityReport,
    p12_policy: MeasurementPolicy,
    p12_trust_store: MeasurementTrustStore,
    p12_authority_pins: MeasurementAuthorityPins,
    plan: SignedMeasurementRunPlan,
    bundle_index: MeasurementBundleIndex,
    cohort_batch: CohortIntegrityBatch,
    cohort_attestation: ProducerAttestation,
) -> bool:
    """Return whether a supplied binding is exactly derivable from valid P12 input."""

    if type(binding) is not OriginalSettlementBinding:
        return False
    try:
        binding = OriginalSettlementBinding.model_validate(binding.model_dump())
        rebuilt = build_original_settlement_binding(
            report,
            p12_policy,
            p12_trust_store,
            p12_authority_pins,
            plan,
            bundle_index,
            cohort_batch,
            cohort_attestation,
            original_verified_at=binding.original_verified_at,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return binding == rebuilt


def sign_settlement_amendment(
    binding: OriginalSettlementBinding,
    events: tuple[SettlementEvent, ...] | list[SettlementEvent],
    policy: SettlementAmendmentPolicy,
    trust_store: SettlementAmendmentTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    amendment_id_sha256: str,
    observed_through_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedSettlementAmendment:
    """Create an amendment using only the pinned cohort-producer key."""

    binding = _require_exact(binding, OriginalSettlementBinding, "binding")
    policy = _require_exact(policy, SettlementAmendmentPolicy, "policy")
    trust_store = _require_exact(
        trust_store, SettlementAmendmentTrustStore, "trust_store"
    )
    if policy.trust_store_sha256 != hash_settlement_trust_store(trust_store):
        raise SettlementAmendmentError("settlement policy trust-store mismatch")
    if not _signing_key_matches(signing_key, trust_store.amendment_producer):
        raise SettlementAmendmentError("amendment signing key is not pinned")
    canonical_events = tuple(
        sorted(
            (_require_event(item) for item in events),
            key=lambda item: (item.effective_at, item.event_id_sha256),
        )
    )
    key = trust_store.amendment_producer
    return _build_signed(
        SignedSettlementAmendment,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.COHORT_PRODUCER,
            "amendment_id_sha256": amendment_id_sha256,
            "policy_sha256": hash_settlement_policy(policy),
            "original_binding_sha256": hash_original_settlement_binding(binding),
            "run_id": binding.run_id,
            "cohort_id": binding.cohort_id,
            "property_record_sha256": binding.property_record_sha256,
            "partner_ids": binding.partner_ids,
            "currency": binding.currency,
            "events": canonical_events,
            "event_root_sha256": _event_root(canonical_events),
            "observed_through_at": observed_through_at,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        signing_key,
    )


def sign_settlement_completeness_attestation(
    amendment: SignedSettlementAmendment,
    binding: OriginalSettlementBinding,
    coverage: SettlementCompletenessCoverage,
    policy: SettlementAmendmentPolicy,
    trust_store: SettlementAmendmentTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    decision: SettlementCompletenessDecision,
    issued_at: datetime,
    expires_at: datetime,
) -> SettlementCompletenessAttestation:
    """Sign the required independent completeness decision for one amendment."""

    amendment = _require_exact(
        amendment, SignedSettlementAmendment, "amendment"
    )
    binding = _require_exact(binding, OriginalSettlementBinding, "binding")
    coverage = _require_exact(
        coverage, SettlementCompletenessCoverage, "coverage"
    )
    policy = _require_exact(policy, SettlementAmendmentPolicy, "policy")
    trust_store = _require_exact(
        trust_store, SettlementAmendmentTrustStore, "trust_store"
    )
    if policy.trust_store_sha256 != hash_settlement_trust_store(trust_store):
        raise SettlementAmendmentError("settlement policy trust-store mismatch")
    if not _signing_key_matches(signing_key, trust_store.completeness_verifier):
        raise SettlementAmendmentError("completeness signing key is not pinned")
    key = trust_store.completeness_verifier
    return _build_signed(
        SettlementCompletenessAttestation,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.TCO_QA,
            "decision": decision,
            "policy_sha256": hash_settlement_policy(policy),
            "original_binding_sha256": hash_original_settlement_binding(binding),
            "amendment_sha256": hash_settlement_artifact(amendment),
            "event_root_sha256": amendment.event_root_sha256,
            "observed_through_at": amendment.observed_through_at,
            "coverage": coverage,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        signing_key,
    )


def verify_settlement_amendment(
    amendment: SignedSettlementAmendment,
    completeness: SettlementCompletenessAttestation,
    binding: OriginalSettlementBinding,
    cohort_batch: CohortIntegrityBatch,
    policy: SettlementAmendmentPolicy,
    trust_store: SettlementAmendmentTrustStore,
    authority_pins: SettlementAmendmentAuthorityPins,
    *,
    at: datetime,
) -> bool:
    """Verify one standalone amendment through deterministic state application."""

    try:
        amendment = _require_exact(
            amendment, SignedSettlementAmendment, "amendment"
        )
        completeness = _require_exact(
            completeness, SettlementCompletenessAttestation, "completeness"
        )
        binding = _require_exact(binding, OriginalSettlementBinding, "binding")
        cohort_batch = _require_exact(
            cohort_batch, CohortIntegrityBatch, "cohort_batch"
        )
        policy = _require_exact(policy, SettlementAmendmentPolicy, "policy")
        trust_store = _require_exact(
            trust_store, SettlementAmendmentTrustStore, "trust_store"
        )
        authority_pins = _require_exact(
            authority_pins,
            SettlementAmendmentAuthorityPins,
            "authority_pins",
        )
        _utc(at, "settlement amendment verification timestamp")
        _verify_amendment_boundary(
            amendment,
            completeness,
            binding,
            cohort_batch,
            policy,
            trust_store,
            authority_pins,
            at=at,
        )
        _apply_events_once(cohort_batch, amendment.events)
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def evaluate_settlement_amendments(
    binding: OriginalSettlementBinding,
    cohort_batch: CohortIntegrityBatch,
    amendments: tuple[SignedSettlementAmendment, ...]
    | list[SignedSettlementAmendment],
    completeness_attestations: tuple[SettlementCompletenessAttestation, ...]
    | list[SettlementCompletenessAttestation],
    policy: SettlementAmendmentPolicy,
    trust_store: SettlementAmendmentTrustStore,
    authority_pins: SettlementAmendmentAuthorityPins,
    *,
    at: datetime,
) -> SettlementAmendmentEvaluation:
    """Apply a set of signed events once, independent of delivery order/replay."""

    binding = _require_exact(binding, OriginalSettlementBinding, "binding")
    cohort_batch = _require_exact(
        cohort_batch, CohortIntegrityBatch, "cohort_batch"
    )
    policy = _require_exact(policy, SettlementAmendmentPolicy, "policy")
    trust_store = _require_exact(
        trust_store, SettlementAmendmentTrustStore, "trust_store"
    )
    authority_pins = _require_exact(
        authority_pins,
        SettlementAmendmentAuthorityPins,
        "authority_pins",
    )
    _utc(at, "settlement amendment evaluation timestamp")
    if not amendments:
        raise SettlementAmendmentError("at least one settlement amendment is required")

    for item in amendments:
        if type(item) is not SignedSettlementAmendment:
            raise TypeError("every amendment must be SignedSettlementAmendment")
    for item in completeness_attestations:
        if type(item) is not SettlementCompletenessAttestation:
            raise TypeError(
                "every completeness item must be SettlementCompletenessAttestation"
            )

    unique_amendments, replayed_amendments = _deduplicate_artifacts(
        tuple(amendments), "amendment_id_sha256", "amendment"
    )
    unique_completeness, _ = _deduplicate_artifacts(
        tuple(completeness_attestations),
        "amendment_sha256",
        "completeness attestation",
    )
    completeness_by_amendment = {
        item.amendment_sha256: item for item in unique_completeness
    }
    amendment_hashes = {
        hash_settlement_artifact(item): item for item in unique_amendments
    }
    if set(completeness_by_amendment) != set(amendment_hashes):
        raise SettlementAmendmentError(
            "every unique amendment requires exactly one completeness attestation"
        )
    for amendment_hash, amendment in amendment_hashes.items():
        _verify_amendment_boundary(
            amendment,
            completeness_by_amendment[amendment_hash],
            binding,
            cohort_batch,
            policy,
            trust_store,
            authority_pins,
            at=at,
        )

    event_occurrences = [
        event for amendment in unique_amendments for event in amendment.events
    ]
    unique_events, replayed_events = _deduplicate_artifacts(
        tuple(event_occurrences), "event_id_sha256", "settlement event"
    )
    events = tuple(
        sorted(
            unique_events,
            key=lambda item: (item.effective_at, item.event_id_sha256),
        )
    )
    (
        original_amount,
        amended_amount,
        partner_settlements,
        final_root,
    ) = _apply_events_once(cohort_batch, events)
    delta = amended_amount - original_amount
    return SettlementAmendmentEvaluation(
        policy_sha256=hash_settlement_policy(policy),
        original_binding_sha256=hash_original_settlement_binding(binding),
        run_id=binding.run_id,
        cohort_id=binding.cohort_id,
        currency=binding.currency,
        partner_ids=binding.partner_ids,
        amendment_sha256s=tuple(sorted(amendment_hashes)),
        completeness_attestation_sha256s=tuple(
            sorted(hash_settlement_artifact(item) for item in unique_completeness)
        ),
        applied_event_root_sha256=_event_root(events),
        final_transaction_state_root_sha256=final_root,
        applied_event_count=len(events),
        replayed_amendment_occurrences=replayed_amendments,
        replayed_event_occurrences=replayed_events,
        original_settled_amount=original_amount,
        amended_settled_amount=amended_amount,
        settled_delta=delta,
        positive_settled_delta=max(delta, Decimal(0)),
        negative_settled_delta=min(delta, Decimal(0)),
        partner_settlements=partner_settlements,
        evaluated_at=at,
    )


def _canonicalize_original_inputs(
    report: MeasurementIntegrityReport,
    p12_policy: MeasurementPolicy,
    p12_trust_store: MeasurementTrustStore,
    p12_authority_pins: MeasurementAuthorityPins,
    plan: SignedMeasurementRunPlan,
    bundle_index: MeasurementBundleIndex,
    cohort_batch: CohortIntegrityBatch,
    cohort_attestation: ProducerAttestation,
) -> tuple[
    MeasurementIntegrityReport,
    MeasurementPolicy,
    MeasurementTrustStore,
    MeasurementAuthorityPins,
    SignedMeasurementRunPlan,
    MeasurementBundleIndex,
    CohortIntegrityBatch,
    ProducerAttestation,
]:
    values = (
        (report, MeasurementIntegrityReport, "report"),
        (p12_policy, MeasurementPolicy, "p12_policy"),
        (p12_trust_store, MeasurementTrustStore, "p12_trust_store"),
        (p12_authority_pins, MeasurementAuthorityPins, "p12_authority_pins"),
        (plan, SignedMeasurementRunPlan, "plan"),
        (bundle_index, MeasurementBundleIndex, "bundle_index"),
        (cohort_batch, CohortIntegrityBatch, "cohort_batch"),
        (cohort_attestation, ProducerAttestation, "cohort_attestation"),
    )
    return tuple(_require_exact(*item) for item in values)  # type: ignore[return-value]


def _verify_original_artifacts(
    report: MeasurementIntegrityReport,
    p12_policy: MeasurementPolicy,
    p12_trust_store: MeasurementTrustStore,
    p12_authority_pins: MeasurementAuthorityPins,
    plan: SignedMeasurementRunPlan,
    bundle_index: MeasurementBundleIndex,
    cohort_batch: CohortIntegrityBatch,
    cohort_attestation: ProducerAttestation,
    *,
    original_verified_at: datetime,
) -> None:
    if not verify_measurement_integrity_report(
        report,
        p12_policy,
        p12_trust_store,
        p12_authority_pins,
        at=original_verified_at,
    ):
        raise SettlementAmendmentError("original P12 report verification failed")
    definition = plan.definition
    policy_hash = hash_measurement_policy(p12_policy)
    trust_hash = hash_measurement_trust_store(p12_trust_store)
    plan_hash = hash_signed_artifact(plan)
    index_hash = hash_signed_artifact(bundle_index)
    batch_hash = hash_signed_artifact(cohort_batch)
    attestation_hash = hash_signed_artifact(cohort_attestation)

    plan_key = p12_trust_store.run_human
    if (
        definition.decision is not RunFreezeDecision.GO
        or definition.policy_sha256 != policy_hash
        or definition.trust_store_sha256 != trust_hash
        or p12_policy.trust_store_sha256 != trust_hash
        or definition.property_record_sha256 != p12_policy.property_record_sha256
        or definition.property_domain_sha256 != p12_policy.property_domain_sha256
        or definition.country != p12_policy.country
        or definition.language != p12_policy.language
        or definition.currency != p12_policy.currency
        or definition.business_timezone != p12_policy.business_timezone
        or hash_signed_artifact(definition.rules)
        != p12_policy.approved_rule_pins_sha256
        or _canonical_sha256(
            {
                "demand": definition.demand_authority_record_sha256,
                "cohort": definition.cohort_authority_record_sha256,
                "operations": definition.operations_authority_record_sha256,
            }
        )
        != p12_policy.approved_source_authorities_sha256
        or _canonical_sha256(
            tuple(
                item.model_dump(mode="json")
                for item in definition.fault_requirements
            )
        )
        != p12_policy.approved_fault_requirements_sha256
        or tuple(item.fault_id for item in definition.fault_requirements)
        != p12_policy.required_fault_ids
        or plan.issuer != plan_key.issuer
        or plan.key_id_sha256 != plan_key.key_id_sha256
        or not _current_signed(
            plan,
            plan_key,
            original_verified_at,
            p12_policy.maximum_plan_ttl_seconds,
        )
    ):
        raise SettlementAmendmentError("original P12 run plan verification failed")

    index_key = p12_trust_store.bundle_indexer
    if (
        p12_authority_pins.expected_policy_sha256 != policy_hash
        or p12_authority_pins.expected_trust_store_sha256 != trust_hash
        or p12_authority_pins.expected_run_id != definition.run_id
        or p12_authority_pins.expected_bundle_index_sha256 != index_hash
        or bundle_index.issuer != index_key.issuer
        or bundle_index.key_id_sha256 != index_key.key_id_sha256
        or bundle_index.run_id != definition.run_id
        or bundle_index.policy_sha256 != policy_hash
        or bundle_index.plan_sha256 != plan_hash
        or bundle_index.property_record_sha256
        != definition.property_record_sha256
        or bundle_index.cohort_batch_sha256 != batch_hash
        or bundle_index.cohort_attestation_sha256 != attestation_hash
        or not _current_signed(
            bundle_index,
            index_key,
            original_verified_at,
            p12_policy.maximum_index_ttl_seconds,
        )
    ):
        raise SettlementAmendmentError("original P12 bundle index verification failed")

    cohort_key = p12_trust_store.cohort_producer
    coverage = cohort_attestation.coverage
    if (
        cohort_attestation.dataset is not MeasurementDataset.COHORT
        or cohort_attestation.issuer != cohort_key.issuer
        or cohort_attestation.key_id_sha256 != cohort_key.key_id_sha256
        or cohort_attestation.run_id != definition.run_id
        or cohort_attestation.policy_sha256 != policy_hash
        or cohort_attestation.plan_sha256 != plan_hash
        or cohort_attestation.property_record_sha256
        != definition.property_record_sha256
        or cohort_attestation.source_authority_record_sha256
        != definition.cohort_authority_record_sha256
        or cohort_attestation.measurement_version
        != definition.cohort_measurement_version
        or cohort_attestation.batch_sha256 != batch_hash
        or cohort_attestation.issued_at < cohort_batch.captured_at
        or coverage.source_export_sha256 != cohort_batch.source_receipt_sha256
        or coverage.coverage_rule_sha256
        != definition.rules.coverage_completeness_sha256
        or coverage.conflict_records != 0
        or coverage.unknown_records != 0
        or not _cohort_coverage_matches(cohort_batch, cohort_attestation)
        or not _current_signed(
            cohort_attestation,
            cohort_key,
            original_verified_at,
            p12_policy.maximum_producer_ttl_seconds,
        )
    ):
        raise SettlementAmendmentError(
            "original P12 cohort attestation verification failed"
        )

    rules = definition.rules
    if (
        cohort_batch.property_record_sha256 != definition.property_record_sha256
        or cohort_batch.source_authority_record_sha256
        != definition.cohort_authority_record_sha256
        or cohort_batch.currency != definition.currency
        or cohort_batch.partner_ids != definition.partner_ids
        or cohort_batch.cohort_started_at != definition.observation_started_at
        or cohort_batch.cohort_ended_at != definition.observation_ended_at
        or cohort_batch.measurement_version
        != definition.cohort_measurement_version
        or cohort_batch.click_deduplication_sha256
        != rules.event_deduplication_sha256
        or cohort_batch.status_mapping_sha256 != rules.status_transition_sha256
        or cohort_batch.transaction_deduplication_sha256
        != rules.transaction_deduplication_sha256
        or cohort_batch.acquisition_mapping_sha256
        != rules.new_acquisition_sha256
        or cohort_batch.payout_mapping_sha256
        != rules.payout_reconciliation_sha256
        or cohort_batch.qualification_sha256 != rules.qualification_sha256
        or cohort_batch.session_identity_sha256 != rules.session_identity_sha256
        or cohort_batch.valid_outbound_filter_sha256
        != rules.valid_outbound_filter_sha256
        or cohort_batch.attribution_sha256 != rules.attribution_sha256
        or cohort_batch.refund_chargeback_sha256
        != rules.refund_chargeback_sha256
        or cohort_batch.privacy_minimization_sha256
        != rules.privacy_minimization_sha256
        or cohort_batch.snapshot_as_of != definition.observation_ended_at
        or cohort_batch.captured_at != definition.observation_ended_at
    ):
        raise SettlementAmendmentError("original P12 cohort rule binding failed")

    original_amount = _settled_amount(cohort_batch)
    confirmed, paid, pending, rejected = _cohort_commissions(cohort_batch)
    expected_evidence_hash = _canonical_sha256(
        {
            "plan_sha256": plan_hash,
            "index_sha256": index_hash,
            "attestation_sha256": attestation_hash,
            "batch_sha256": batch_hash,
        }
    )
    if (
        report.run_id != definition.run_id
        or report.plan_sha256 != plan_hash
        or report.bundle_index_sha256 != index_hash
        or report.cohort_attestation_sha256 != attestation_hash
        or report.property_record_sha256 != definition.property_record_sha256
        or report.partner_ids != definition.partner_ids
        or report.currency != definition.currency
        or report.observation_started_at
        != definition.observation_started_at.astimezone(timezone.utc)
        or report.observation_ended_at
        != definition.observation_ended_at.astimezone(timezone.utc)
        or report.cohort.source_sha256 != expected_evidence_hash
        or report.cohort.evidence_version != f"sha256:{expected_evidence_hash}"
        or report.cohort.status_mapping_sha256 != cohort_batch.status_mapping_sha256
        or report.cohort.captured_at
        != cohort_batch.captured_at.astimezone(timezone.utc)
        or report.cohort.expires_at
        != cohort_batch.expires_at.astimezone(timezone.utc)
        or report.cohort.cohort.currency != cohort_batch.currency
        or report.cohort.cohort.valid_clicks
        != len(cohort_batch.valid_outbound_clicks)
        or report.cohort.cohort.commissions.confirmed != confirmed
        or report.cohort.cohort.commissions.paid != paid
        or report.cohort.cohort.commissions.pending != pending
        or report.cohort.cohort.commissions.rejected != rejected
        or report.reconciliation.current_transactions
        != len(cohort_batch.transactions)
        or report.reconciliation.new_acquisition_transactions
        != sum(
            item.acquisition_class is AcquisitionClass.NEW
            for item in cohort_batch.transactions
        )
        or report.reconciliation.gross_paid_transactions
        != sum(
            item.current_status is TransactionStatus.PAID
            for item in cohort_batch.transactions
        )
        or report.reconciliation.reversed_paid_transactions
        != len(cohort_batch.payout_adjustments)
        or report.reconciliation.net_paid_transactions
        != sum(
            item.current_status is TransactionStatus.PAID
            and item.transaction_id_sha256
            not in {
                adjustment.transaction_id_sha256
                for adjustment in cohort_batch.payout_adjustments
            }
            for item in cohort_batch.transactions
        )
        or report.reconciliation.settled_new_acquisition_amount != original_amount
        or report.reconciliation.gross_payout_amount
        != cohort_batch.payout_statement.gross_amount
        or report.reconciliation.net_payout_amount
        != cohort_batch.payout_statement.net_amount
    ):
        raise SettlementAmendmentError("original P12 report cohort binding failed")


def _verify_amendment_boundary(
    amendment: SignedSettlementAmendment,
    completeness: SettlementCompletenessAttestation,
    binding: OriginalSettlementBinding,
    cohort_batch: CohortIntegrityBatch,
    policy: SettlementAmendmentPolicy,
    trust_store: SettlementAmendmentTrustStore,
    authority_pins: SettlementAmendmentAuthorityPins,
    *,
    at: datetime,
) -> None:
    policy_hash = hash_settlement_policy(policy)
    trust_hash = hash_settlement_trust_store(trust_store)
    binding_hash = hash_original_settlement_binding(binding)
    amendment_hash = hash_settlement_artifact(amendment)
    producer_key = trust_store.amendment_producer
    completeness_key = trust_store.completeness_verifier
    if (
        authority_pins.expected_policy_sha256 != policy_hash
        or authority_pins.expected_trust_store_sha256 != trust_hash
        or policy.trust_store_sha256 != trust_hash
        or policy.p12_policy_sha256 != binding.p12_policy_sha256
        or policy.p12_trust_store_sha256 != binding.p12_trust_store_sha256
        or authority_pins.expected_p12_report_sha256
        != binding.p12_report_sha256
        or authority_pins.expected_p12_plan_sha256 != binding.p12_plan_sha256
        or authority_pins.expected_p12_bundle_index_sha256
        != binding.p12_bundle_index_sha256
        or authority_pins.expected_p12_cohort_batch_sha256
        != binding.p12_cohort_batch_sha256
        or authority_pins.expected_p12_cohort_attestation_sha256
        != binding.p12_cohort_attestation_sha256
        or authority_pins.expected_run_id != binding.run_id
        or authority_pins.expected_cohort_id != binding.cohort_id
        or not _binding_matches_batch(binding, cohort_batch)
        or amendment.issuer != producer_key.issuer
        or amendment.key_id_sha256 != producer_key.key_id_sha256
        or amendment.policy_sha256 != policy_hash
        or amendment.original_binding_sha256 != binding_hash
        or amendment.run_id != binding.run_id
        or amendment.cohort_id != binding.cohort_id
        or amendment.property_record_sha256 != binding.property_record_sha256
        or amendment.partner_ids != binding.partner_ids
        or amendment.currency != binding.currency
        or amendment.observed_through_at <= binding.snapshot_as_of
        or not _current_signed(
            amendment,
            producer_key,
            at,
            policy.maximum_amendment_ttl_seconds,
        )
        or completeness.issuer != completeness_key.issuer
        or completeness.key_id_sha256 != completeness_key.key_id_sha256
        or completeness.decision is not SettlementCompletenessDecision.COMPLETE
        or completeness.policy_sha256 != policy_hash
        or completeness.original_binding_sha256 != binding_hash
        or completeness.amendment_sha256 != amendment_hash
        or completeness.event_root_sha256 != amendment.event_root_sha256
        or completeness.observed_through_at != amendment.observed_through_at
        or not _complete_coverage_matches(amendment, completeness, policy)
        or not _current_signed(
            completeness,
            completeness_key,
            at,
            policy.maximum_completeness_ttl_seconds,
        )
    ):
        raise SettlementAmendmentError(
            "settlement amendment signature, pins, or completeness verification failed"
        )
    transactions = {
        item.transaction_id_sha256: item for item in cohort_batch.transactions
    }
    for event in amendment.events:
        transaction = transactions.get(event.transaction_id_sha256)
        if (
            transaction is None
            or event.original_transaction_sha256
            != hash_signed_artifact(transaction)
            or event.effective_at <= binding.snapshot_as_of
        ):
            raise SettlementAmendmentError(
                "amendment event does not bind a later original transaction"
            )
        if type(event) is SettlementPayoutAdjustment and (
            event.amount != transaction.amount
            or event.currency != transaction.currency
        ):
            raise SettlementAmendmentError(
                "payout adjustment changed original amount or currency"
            )


def _apply_events_once(
    cohort_batch: CohortIntegrityBatch,
    events: tuple[SettlementEvent, ...],
) -> tuple[Decimal, Decimal, tuple[PartnerSettlementAmount, ...], str]:
    transactions = {
        item.transaction_id_sha256: item for item in cohort_batch.transactions
    }
    statuses = {
        key: item.current_status for key, item in transactions.items()
    }
    latest_times = {
        key: item.status_events[-1].effective_at for key, item in transactions.items()
    }
    adjusted = {
        item.transaction_id_sha256 for item in cohort_batch.payout_adjustments
    }
    original_adjusted = frozenset(adjusted)
    adjustment_ids = {
        item.adjustment_id_sha256 for item in cohort_batch.payout_adjustments
    }
    source_receipts = {
        item.source_row_sha256 for item in cohort_batch.payout_adjustments
    } | {
        event.source_row_sha256
        for item in cohort_batch.transactions
        for event in item.status_events
    }
    payout_times = {
        item.transaction_id_sha256: item.paid_at for item in cohort_batch.payout_rows
    }
    for event in events:
        transaction = transactions[event.transaction_id_sha256]
        if event.source_row_sha256 in source_receipts:
            raise SettlementAmendmentError("source receipt replays original evidence")
        source_receipts.add(event.source_row_sha256)
        if event.effective_at <= cohort_batch.snapshot_as_of:
            raise SettlementAmendmentError("settlement event is not later than P12")
        if type(event) is SettlementStatusChange:
            if (
                event.previous_status is not statuses[event.transaction_id_sha256]
                or event.current_status
                not in _ALLOWED_TRANSITIONS[event.previous_status]
                or event.effective_at <= latest_times[event.transaction_id_sha256]
            ):
                raise SettlementAmendmentError(
                    "settlement status events are conflicting or out of sequence"
                )
            statuses[event.transaction_id_sha256] = event.current_status
            latest_times[event.transaction_id_sha256] = event.effective_at
        else:
            if (
                statuses[event.transaction_id_sha256] is not TransactionStatus.PAID
                or event.transaction_id_sha256 in adjusted
                or event.adjustment_id_sha256 in adjustment_ids
                or event.amount != transaction.amount
                or event.currency != transaction.currency
                or event.transaction_id_sha256 not in payout_times
                or event.effective_at <= payout_times[event.transaction_id_sha256]
                or event.effective_at <= latest_times[event.transaction_id_sha256]
            ):
                raise SettlementAmendmentError(
                    "payout adjustment is not one later full paid reversal"
                )
            adjusted.add(event.transaction_id_sha256)
            adjustment_ids.add(event.adjustment_id_sha256)

    original_by_partner = {
        partner_id: Decimal(0) for partner_id in cohort_batch.partner_ids
    }
    amended_by_partner = {
        partner_id: Decimal(0) for partner_id in cohort_batch.partner_ids
    }
    for transaction_id, item in transactions.items():
        if item.acquisition_class is not AcquisitionClass.NEW:
            continue
        if (
            item.current_status
            in (TransactionStatus.CONFIRMED, TransactionStatus.PAID)
            and transaction_id not in original_adjusted
        ):
            original_by_partner[item.partner_id] += item.amount
        if (
            statuses[transaction_id]
            in (TransactionStatus.CONFIRMED, TransactionStatus.PAID)
            and transaction_id not in adjusted
        ):
            amended_by_partner[item.partner_id] += item.amount
    partner_settlements = tuple(
        PartnerSettlementAmount(
            partner_id=partner_id,
            original_settled_amount=original_by_partner[partner_id],
            amended_settled_amount=amended_by_partner[partner_id],
            settled_delta=(
                amended_by_partner[partner_id] - original_by_partner[partner_id]
            ),
        )
        for partner_id in sorted(cohort_batch.partner_ids)
    )
    original_amount = sum(original_by_partner.values(), Decimal(0))
    amended_amount = sum(amended_by_partner.values(), Decimal(0))
    state_root = _canonical_sha256(
        tuple(
            {
                "transaction_id_sha256": transaction_id,
                "original_transaction_sha256": hash_signed_artifact(
                    transactions[transaction_id]
                ),
                "current_status": statuses[transaction_id],
                "is_payout_adjusted": transaction_id in adjusted,
            }
            for transaction_id in sorted(transactions)
        )
    )
    return original_amount, amended_amount, partner_settlements, state_root


def _binding_matches_batch(
    binding: OriginalSettlementBinding, cohort_batch: CohortIntegrityBatch
) -> bool:
    return (
        binding.p12_cohort_batch_sha256 == hash_signed_artifact(cohort_batch)
        and binding.cohort_id == cohort_batch.cohort_id
        and binding.property_record_sha256 == cohort_batch.property_record_sha256
        and binding.partner_ids == cohort_batch.partner_ids
        and binding.currency == cohort_batch.currency
        and binding.snapshot_as_of
        == cohort_batch.snapshot_as_of.astimezone(timezone.utc)
        and binding.original_transaction_set_sha256
        == _transaction_set_root(cohort_batch)
        and binding.original_payout_adjustment_set_sha256
        == _original_adjustment_set_root(cohort_batch)
    )


def _cohort_coverage_matches(
    batch: CohortIntegrityBatch, attestation: ProducerAttestation
) -> bool:
    expected = {
        CoveragePartitionKind.QUALIFIED_SESSION: tuple(
            item.session_id_sha256 for item in batch.qualified_sessions
        ),
        CoveragePartitionKind.VALID_OUTBOUND_CLICK: tuple(
            item.click_id_sha256 for item in batch.valid_outbound_clicks
        ),
        CoveragePartitionKind.AFFILIATE_ACCEPTED_CLICK: tuple(
            item.affiliate_click_id_sha256
            for item in batch.affiliate_accepted_clicks
        ),
        CoveragePartitionKind.TRANSACTION: tuple(
            item.transaction_id_sha256 for item in batch.transactions
        ),
        CoveragePartitionKind.STATUS_EVENT: tuple(
            event.source_row_sha256
            for item in batch.transactions
            for event in item.status_events
        ),
        CoveragePartitionKind.PAYOUT_ROW: tuple(
            item.payout_row_sha256 for item in batch.payout_rows
        ),
        CoveragePartitionKind.PAYOUT_ADJUSTMENT: tuple(
            item.adjustment_id_sha256 for item in batch.payout_adjustments
        ),
    }
    observed = {item.kind: item for item in attestation.coverage.partitions}
    if set(observed) != set(expected):
        return False
    output_count = sum(len(values) for values in expected.values())
    return (
        attestation.coverage.output_records == output_count
        and all(
            observed[kind].output_records == len(identities)
            and observed[kind].identity_set_sha256
            == _identity_set_root(identities)
            for kind, identities in expected.items()
        )
    )


def _complete_coverage_matches(
    amendment: SignedSettlementAmendment,
    completeness: SettlementCompletenessAttestation,
    policy: SettlementAmendmentPolicy,
) -> bool:
    coverage = completeness.coverage
    event_ids = tuple(item.event_id_sha256 for item in amendment.events)
    return (
        coverage.coverage_rule_sha256 == policy.completeness_rule_sha256
        and coverage.accepted_records == len(event_ids)
        and coverage.output_records == len(event_ids)
        and coverage.rejected_records == 0
        and coverage.conflict_records == 0
        and coverage.unknown_records == 0
        and coverage.event_id_set_sha256 == _identity_set_root(event_ids)
        and coverage.privacy_scan_passed is True
        and (
            bool(event_ids)
            or (coverage.raw_records == 0 and coverage.duplicate_records == 0)
        )
    )


def _cohort_commissions(
    batch: CohortIntegrityBatch,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    reversed_ids = {
        item.transaction_id_sha256 for item in batch.payout_adjustments
    }
    eligible = tuple(
        item
        for item in batch.transactions
        if item.acquisition_class is AcquisitionClass.NEW
        and item.current_status in (TransactionStatus.CONFIRMED, TransactionStatus.PAID)
        and item.transaction_id_sha256 not in reversed_ids
    )
    confirmed = sum(
        (
            item.amount
            for item in eligible
            if item.current_status is TransactionStatus.CONFIRMED
        ),
        Decimal(0),
    )
    paid = sum(
        (
            item.amount
            for item in eligible
            if item.current_status is TransactionStatus.PAID
        ),
        Decimal(0),
    )
    pending = sum(
        (
            item.amount
            for item in batch.transactions
            if item.current_status is TransactionStatus.PENDING
        ),
        Decimal(0),
    )
    rejected = sum(
        (
            item.amount
            for item in batch.transactions
            if item.current_status
            in (
                TransactionStatus.REJECTED,
                TransactionStatus.REFUNDED,
                TransactionStatus.CHARGED_BACK,
            )
            or item.transaction_id_sha256 in reversed_ids
        ),
        Decimal(0),
    )
    return confirmed, paid, pending, rejected


def _settled_amount(batch: CohortIntegrityBatch) -> Decimal:
    confirmed, paid, _, _ = _cohort_commissions(batch)
    return confirmed + paid


def _transaction_set_root(batch: CohortIntegrityBatch) -> str:
    return _canonical_sha256(
        tuple(
            hash_signed_artifact(item)
            for item in sorted(
                batch.transactions, key=lambda row: row.transaction_id_sha256
            )
        )
    )


def _original_adjustment_set_root(batch: CohortIntegrityBatch) -> str:
    return _canonical_sha256(
        tuple(
            hash_signed_artifact(item)
            for item in sorted(
                batch.payout_adjustments,
                key=lambda row: row.adjustment_id_sha256,
            )
        )
    )


def _identity_set_root(values: tuple[str, ...]) -> str:
    ordered = tuple(sorted(values))
    if len(ordered) != len(set(ordered)):
        raise SettlementAmendmentError("identity set contains duplicate members")
    return _canonical_sha256(ordered)


def _event_root(events: tuple[SettlementEvent, ...] | list[SettlementEvent]) -> str:
    ordered = tuple(
        sorted(events, key=lambda item: (item.effective_at, item.event_id_sha256))
    )
    return _canonical_sha256(tuple(hash_settlement_event(item) for item in ordered))


def _deduplicate_artifacts(
    values: tuple[Any, ...], identity_field: str, label: str
) -> tuple[tuple[Any, ...], int]:
    by_identity: dict[str, tuple[str, Any]] = {}
    replayed = 0
    for value in values:
        artifact_hash = hash_settlement_artifact(value)
        identity = getattr(value, identity_field)
        previous = by_identity.get(identity)
        if previous is None:
            by_identity[identity] = (artifact_hash, value)
        elif previous[0] == artifact_hash:
            replayed += 1
        else:
            raise SettlementAmendmentError(f"conflicting {label} identity")
    ordered = tuple(
        item[1] for item in sorted(by_identity.values(), key=lambda pair: pair[0])
    )
    return ordered, replayed


def _require_exact(value: Any, model_type: type[Any], label: str) -> Any:
    if type(value) is not model_type:
        raise TypeError(f"{label} must be {model_type.__name__}")
    return model_type.model_validate(value.model_dump())


def _require_event(value: Any) -> SettlementEvent:
    if type(value) not in (SettlementStatusChange, SettlementPayoutAdjustment):
        raise TypeError("event must be a settlement event")
    return type(value).model_validate(value.model_dump())


def _build_signed(
    model_type: type[StrictModel], values: dict[str, Any], signer: Ed25519PrivateKey
) -> Any:
    if not isinstance(signer, Ed25519PrivateKey):
        raise TypeError("signing_key must be Ed25519PrivateKey")
    provisional = model_type.model_construct(
        **values, payload_sha256="0" * 64, signature_base64url="A" * 86
    )
    values = dict(values)
    values["payload_sha256"] = _signed_payload_hash(provisional)
    with_payload = model_type.model_construct(
        **values, signature_base64url="A" * 86
    )
    values["signature_base64url"] = _encode_base64url(
        signer.sign(_signature_message(with_payload))
    )
    return model_type(**values)


def _validate_signed(model: StrictModel, label: str) -> None:
    if model.expires_at <= model.issued_at:  # type: ignore[attr-defined]
        raise ValueError(f"{label} expires_at must be after issued_at")
    _decode_base64url(model.signature_base64url, 64)  # type: ignore[attr-defined]
    if model.payload_sha256 != _signed_payload_hash(model):  # type: ignore[attr-defined]
        raise ValueError(f"{label} payload hash mismatch")


def _current_signed(
    model: StrictModel,
    key: Ed25519VerificationKey,
    at: datetime,
    maximum_ttl_seconds: int,
) -> bool:
    try:
        return (
            model.issued_at <= at < model.expires_at  # type: ignore[attr-defined]
            and model.expires_at - model.issued_at  # type: ignore[attr-defined]
            <= timedelta(seconds=maximum_ttl_seconds)
            and _verify_signature(model, key)
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _verify_signature(model: StrictModel, key: Ed25519VerificationKey) -> bool:
    try:
        key.public_key().verify(
            _decode_base64url(model.signature_base64url, 64),  # type: ignore[attr-defined]
            _signature_message(model),
        )
    except (AttributeError, InvalidSignature, TypeError, ValueError):
        return False
    return True


def _signing_key_matches(
    signer: Ed25519PrivateKey, verifier: Ed25519VerificationKey
) -> bool:
    if not isinstance(signer, Ed25519PrivateKey):
        return False
    candidate = create_verification_key(
        signer.public_key(),
        issuer=verifier.issuer,
        role=verifier.role,
    )
    return candidate == verifier


def _signed_payload_hash(model: StrictModel) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            model.model_dump(
                mode="python", exclude={"payload_sha256", "signature_base64url"}
            )
        )
    ).hexdigest()


def _signature_message(model: StrictModel) -> bytes:
    return _canonical_json_bytes(
        model.model_dump(mode="python", exclude={"signature_base64url"})
    )


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
        _aware(value, "canonical datetime")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str, expected_length: int) -> bytes:
    if type(value) is not str:
        raise TypeError("base64url value must be a string")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url value") from exc
    if len(decoded) != expected_length or _encode_base64url(decoded) != value:
        raise ValueError("invalid or non-canonical base64url value")
    return decoded


def _utc(value: datetime, label: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value


def _aware(value: datetime, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


__all__ = [
    "OriginalSettlementBinding",
    "PartnerSettlementAmount",
    "SettlementAmendmentAuthorityPins",
    "SettlementAmendmentError",
    "SettlementAmendmentEvaluation",
    "SettlementAmendmentPolicy",
    "SettlementAmendmentTrustStore",
    "SettlementCompletenessAttestation",
    "SettlementCompletenessCoverage",
    "SettlementCompletenessDecision",
    "SettlementEvent",
    "SettlementEventKind",
    "SettlementPayoutAdjustment",
    "SettlementStatusChange",
    "SignedSettlementAmendment",
    "build_original_settlement_binding",
    "evaluate_settlement_amendments",
    "hash_original_settlement_binding",
    "hash_settlement_artifact",
    "hash_settlement_event",
    "hash_settlement_policy",
    "hash_settlement_trust_store",
    "sign_settlement_amendment",
    "sign_settlement_completeness_attestation",
    "verify_original_settlement_binding",
    "verify_settlement_amendment",
]
