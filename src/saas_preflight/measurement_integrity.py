"""Signed, offline measurement boundary for Phase 3 evidence.

The module deliberately separates the Human pre-run freeze from the post-run
bundle index.  It accepts no URLs, credentials, free-form notes, or network
clients.  Only a fixed runtime holding the verifier key can turn the signed
artifacts into readiness evidence.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
)
from .measurement import (
    DemandSummaryBatch,
    OperationsSummaryBatch,
    build_demand_evidence,
    build_operations_evidence,
)
from .models import CurrencyCode, Sha256, Slug, StrictModel, VendorPlan
from .preflight import CohortInput, CommissionInput
from .readiness_builder import (
    AffiliateProgramDecision,
    CohortEvidence,
    DemandEvidence,
    OperationsEvidence,
    build_business_dossier,
)
from .preflight import BusinessDossier


_TOKYO = ZoneInfo("Asia/Tokyo")


class MeasurementInputError(ValueError):
    """A signed measurement artifact is invalid or cannot be reconciled."""


class MeasurementDataset(str, Enum):
    DEMAND = "demand"
    COHORT = "cohort"
    OPERATIONS = "operations"


class CoveragePartitionKind(str, Enum):
    DEMAND_CLUSTER = "demand_cluster"
    QUALIFIED_SESSION = "qualified_session"
    VALID_OUTBOUND_CLICK = "valid_outbound_click"
    AFFILIATE_ACCEPTED_CLICK = "affiliate_accepted_click"
    TRANSACTION = "transaction"
    STATUS_EVENT = "status_event"
    PAYOUT_ROW = "payout_row"
    PAYOUT_ADJUSTMENT = "payout_adjustment"
    OPERATION_DAY = "operation_day"
    LOGICAL_JOB_RUN = "logical_job_run"
    FAULT_EXERCISE = "fault_exercise"


class RunFreezeDecision(str, Enum):
    GO = "go"
    HOLD = "hold"
    STOP = "stop"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    PAID = "paid"
    REFUNDED = "refunded"
    CHARGED_BACK = "charged_back"


class AcquisitionClass(str, Enum):
    NEW = "new"
    EXISTING = "existing"
    UNKNOWN = "unknown"


class PayoutAdjustmentKind(str, Enum):
    REFUND = "refund"
    CHARGEBACK = "chargeback"


class FaultId(str, Enum):
    PRICE_CHANGE = "fi-01-price-change"
    PLAN_RENAME = "fi-02-plan-rename"
    BILLING_PERIOD_CHANGE = "fi-03-billing-period-change"
    CURRENCY_CHANGE = "fi-04-currency-change"
    QUOTA_OVERAGE_CHANGE = "fi-05-quota-overage-change"
    SOURCE_CONFLICT = "fi-06-source-conflict"
    AFFILIATE_EXPIRY = "fi-07-affiliate-expiry"
    FETCH_FAILURE_DUPLICATE_DELIVERY = (
        "fi-08-fetch-failure-duplicate-delivery"
    )


REQUIRED_FAULT_IDS = tuple(FaultId)


class MeasurementTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_human: Ed25519VerificationKey
    demand_producer: Ed25519VerificationKey
    cohort_producer: Ed25519VerificationKey
    operations_producer: Ed25519VerificationKey
    bundle_indexer: Ed25519VerificationKey
    measurement_verifier: Ed25519VerificationKey

    @model_validator(mode="after")
    def validate_roles_and_separation(self) -> Self:
        expected = (
            (self.run_human, SigningRole.MEASUREMENT_HUMAN),
            (self.demand_producer, SigningRole.DEMAND_PRODUCER),
            (self.cohort_producer, SigningRole.COHORT_PRODUCER),
            (self.operations_producer, SigningRole.OPERATIONS_PRODUCER),
            (self.bundle_indexer, SigningRole.MEASUREMENT_INDEXER),
            (self.measurement_verifier, SigningRole.TCO_QA),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("measurement trust-store role mismatch")
        if len({key.key_id_sha256 for key, _ in expected}) != len(expected):
            raise ValueError("every measurement signing role requires a distinct key")
        return self


class MeasurementPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    trust_store_sha256: Sha256
    property_record_sha256: Sha256
    property_domain_sha256: Sha256
    approved_rule_pins_sha256: Sha256
    approved_source_authorities_sha256: Sha256
    approved_fault_requirements_sha256: Sha256
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    currency: Literal["JPY"] = "JPY"
    business_timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    observation_days: Literal[30] = 30
    required_fault_ids: tuple[FaultId, ...] = Field(
        min_length=8, max_length=8
    )
    maximum_plan_ttl_seconds: int = Field(ge=1, le=7776000)
    maximum_producer_ttl_seconds: int = Field(ge=1, le=2678400)
    maximum_index_ttl_seconds: int = Field(ge=1, le=2678400)
    maximum_report_ttl_seconds: int = Field(ge=1, le=604800)

    @field_validator("required_fault_ids")
    @classmethod
    def require_exact_fault_catalog(
        cls, values: tuple[FaultId, ...]
    ) -> tuple[FaultId, ...]:
        if values != REQUIRED_FAULT_IDS:
            raise ValueError("required_fault_ids must equal the canonical eight")
        return values


class MeasurementAuthorityPins(StrictModel):
    """Consumer-owned bootstrap values; never derive these from an input bundle."""

    schema_version: Literal["1.0"] = "1.0"
    expected_policy_sha256: Sha256
    expected_trust_store_sha256: Sha256
    expected_run_id: Slug
    expected_bundle_index_sha256: Sha256


class MeasurementRulePins(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    qualification_sha256: Sha256
    session_identity_sha256: Sha256
    demand_deduplication_sha256: Sha256
    valid_outbound_filter_sha256: Sha256
    event_deduplication_sha256: Sha256
    attribution_sha256: Sha256
    transaction_deduplication_sha256: Sha256
    status_transition_sha256: Sha256
    refund_chargeback_sha256: Sha256
    new_acquisition_sha256: Sha256
    payout_reconciliation_sha256: Sha256
    routine_inventory_sha256: Sha256
    job_schedule_sha256: Sha256
    job_status_mapping_sha256: Sha256
    retry_identity_sha256: Sha256
    exception_deduplication_sha256: Sha256
    human_time_union_sha256: Sha256
    qa_policy_sha256: Sha256
    fault_catalog_sha256: Sha256
    privacy_minimization_sha256: Sha256
    coverage_completeness_sha256: Sha256


class FaultRequirement(StrictModel):
    fault_id: FaultId
    definition_sha256: Sha256


class MeasurementRunDefinition(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: Slug
    decision: RunFreezeDecision
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    property_record_sha256: Sha256
    property_domain_sha256: Sha256
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    currency: Literal["JPY"] = "JPY"
    business_timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    source_month: str = Field(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
    observation_started_at: datetime
    observation_ended_at: datetime
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    demand_measurement_version: Slug
    cohort_measurement_version: Slug
    operations_measurement_version: Slug
    demand_authority_record_sha256: Sha256
    cohort_authority_record_sha256: Sha256
    operations_authority_record_sha256: Sha256
    planned_logical_job_count: int = Field(ge=1)
    planned_logical_job_set_sha256: Sha256
    fault_target_release_sha256: Sha256
    fault_target_artifact_sha256: Sha256
    fault_target_schema_sha256: Sha256
    rules: MeasurementRulePins
    fault_requirements: tuple[FaultRequirement, ...] = Field(
        min_length=8, max_length=8
    )

    @field_validator("observation_started_at", "observation_ended_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "measurement observation timestamp")

    @field_validator("partner_ids")
    @classmethod
    def canonicalize_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("partner_ids must be unique")
        return tuple(sorted(values))

    @field_validator("fault_requirements")
    @classmethod
    def canonicalize_faults(
        cls, values: tuple[FaultRequirement, ...]
    ) -> tuple[FaultRequirement, ...]:
        if len({item.fault_id for item in values}) != len(values):
            raise ValueError("fault requirements must be unique")
        ordered = tuple(
            sorted(values, key=lambda item: REQUIRED_FAULT_IDS.index(item.fault_id))
        )
        if tuple(item.fault_id for item in ordered) != REQUIRED_FAULT_IDS:
            raise ValueError("fault requirements must cover the canonical eight")
        return ordered

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.observation_ended_at - self.observation_started_at != timedelta(
            days=30
        ):
            raise ValueError("measurement observation window must be exactly 30 days")
        local_start = self.observation_started_at.astimezone(_TOKYO)
        local_end = self.observation_ended_at.astimezone(_TOKYO)
        if any(
            (
                local_start.hour,
                local_start.minute,
                local_start.second,
                local_start.microsecond,
                local_end.hour,
                local_end.minute,
                local_end.second,
                local_end.microsecond,
            )
        ):
            raise ValueError("measurement window must use Asia/Tokyo midnight bounds")
        return self


class SignedMeasurementRunPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    definition: MeasurementRunDefinition
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.MEASUREMENT_HUMAN]
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "measurement plan timestamp")

    @model_validator(mode="after")
    def validate_signed_plan(self) -> Self:
        _validate_signed(self, "measurement plan")
        if self.issued_at >= self.definition.observation_started_at:
            raise ValueError("measurement plan must be signed before the run starts")
        if self.expires_at <= self.definition.observation_ended_at:
            raise ValueError("measurement plan must remain current through the run")
        return self


class CoveragePartition(StrictModel):
    kind: CoveragePartitionKind
    input_records: int = Field(ge=0)
    accepted_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    duplicate_records: int = Field(ge=0)
    conflict_records: int = Field(ge=0)
    unknown_records: int = Field(ge=0)
    output_records: int = Field(ge=0)
    identity_set_sha256: Sha256

    @model_validator(mode="after")
    def reconcile_partition(self) -> Self:
        if self.input_records != (
            self.accepted_records
            + self.rejected_records
            + self.duplicate_records
            + self.conflict_records
            + self.unknown_records
        ):
            raise ValueError("coverage partition input counts do not reconcile")
        if self.output_records != self.accepted_records:
            raise ValueError("coverage partition output must equal accepted records")
        return self


class ProducerCoverage(StrictModel):
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
    partitions: tuple[CoveragePartition, ...] = Field(min_length=1)
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
            raise ValueError("producer input coverage counts do not reconcile")
        if self.output_records != self.accepted_records:
            raise ValueError("producer output count must equal accepted count")
        if len({item.kind for item in self.partitions}) != len(self.partitions):
            raise ValueError("producer coverage partitions must be distinct")
        ordered = tuple(sorted(self.partitions, key=lambda item: item.kind.value))
        if self.partitions != ordered:
            raise ValueError("producer coverage partitions must be canonically sorted")
        totals = {
            "raw_records": "input_records",
            "accepted_records": "accepted_records",
            "rejected_records": "rejected_records",
            "duplicate_records": "duplicate_records",
            "conflict_records": "conflict_records",
            "unknown_records": "unknown_records",
            "output_records": "output_records",
        }
        for aggregate_field, partition_field in totals.items():
            if getattr(self, aggregate_field) != sum(
                getattr(item, partition_field) for item in self.partitions
            ):
                raise ValueError("producer aggregate counts must equal partitions")
        return self


class ProducerAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset: MeasurementDataset
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: SigningRole
    run_id: Slug
    policy_sha256: Sha256
    plan_sha256: Sha256
    property_record_sha256: Sha256
    source_authority_record_sha256: Sha256
    measurement_version: Slug
    batch_sha256: Sha256
    coverage: ProducerCoverage
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "producer attestation timestamp")

    @model_validator(mode="after")
    def validate_signed_attestation(self) -> Self:
        _validate_signed(self, "producer attestation")
        expected = {
            MeasurementDataset.DEMAND: SigningRole.DEMAND_PRODUCER,
            MeasurementDataset.COHORT: SigningRole.COHORT_PRODUCER,
            MeasurementDataset.OPERATIONS: SigningRole.OPERATIONS_PRODUCER,
        }[self.dataset]
        if self.signer_role is not expected:
            raise ValueError("producer signer role does not match dataset")
        return self


class DemandIntegrityBatch(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    summary: DemandSummaryBatch
    qualification_sha256: Sha256
    session_identity_sha256: Sha256
    valid_outbound_filter_sha256: Sha256
    privacy_minimization_sha256: Sha256


class QualifiedSession(StrictModel):
    session_id_sha256: Sha256
    qualified_at: datetime

    @field_validator("qualified_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "qualified session timestamp")


class ValidOutboundClick(StrictModel):
    click_id_sha256: Sha256
    session_id_sha256: Sha256
    partner_id: Slug
    clicked_at: datetime

    @field_validator("clicked_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "outbound click timestamp")


class AffiliateAcceptedClick(StrictModel):
    affiliate_click_id_sha256: Sha256
    outbound_click_id_sha256: Sha256
    partner_id: Slug
    accepted_at: datetime

    @field_validator("accepted_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "affiliate click timestamp")


class TransactionStatusEvent(StrictModel):
    status: TransactionStatus
    effective_at: datetime
    source_row_sha256: Sha256

    @field_validator("effective_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "transaction status timestamp")


class CurrentTransaction(StrictModel):
    transaction_id_sha256: Sha256
    affiliate_click_id_sha256: Sha256
    partner_id: Slug
    cohort_id: Slug
    currency: CurrencyCode
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    acquisition_class: AcquisitionClass
    acquisition_evidence_sha256: Sha256
    attributed_at: datetime
    current_status: TransactionStatus
    status_events: tuple[TransactionStatusEvent, ...] = Field(min_length=1)

    @field_validator("attributed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "transaction attribution timestamp")

    @field_validator("status_events")
    @classmethod
    def validate_status_history(
        cls, values: tuple[TransactionStatusEvent, ...]
    ) -> tuple[TransactionStatusEvent, ...]:
        if len({item.source_row_sha256 for item in values}) != len(values):
            raise ValueError("transaction status event receipts must be distinct")
        values = tuple(
            sorted(values, key=lambda item: (item.effective_at, item.source_row_sha256))
        )
        if len({item.effective_at for item in values}) != len(values):
            raise ValueError("transaction status event times must be distinct")
        allowed = {
            TransactionStatus.PENDING: {
                TransactionStatus.CONFIRMED,
                TransactionStatus.REJECTED,
            },
            TransactionStatus.CONFIRMED: {
                TransactionStatus.PAID,
                TransactionStatus.REFUNDED,
                TransactionStatus.CHARGED_BACK,
            },
            TransactionStatus.REJECTED: set(),
            TransactionStatus.PAID: set(),
            TransactionStatus.REFUNDED: set(),
            TransactionStatus.CHARGED_BACK: set(),
        }
        for previous, current in zip(values, values[1:], strict=False):
            if current.status not in allowed[previous.status]:
                raise ValueError("invalid or regressive transaction status transition")
        return values

    @model_validator(mode="after")
    def validate_current_state(self) -> Self:
        if self.current_status is not self.status_events[-1].status:
            raise ValueError("current_status must equal the last status event")
        if self.status_events[0].effective_at < self.attributed_at:
            raise ValueError("status history cannot predate attribution")
        return self


class PayoutRow(StrictModel):
    payout_row_sha256: Sha256
    transaction_id_sha256: Sha256
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    currency: CurrencyCode
    paid_at: datetime

    @field_validator("paid_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "payout row timestamp")


class PayoutAdjustment(StrictModel):
    adjustment_id_sha256: Sha256
    transaction_id_sha256: Sha256
    kind: PayoutAdjustmentKind
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    currency: CurrencyCode
    source_row_sha256: Sha256
    adjusted_at: datetime

    @field_validator("adjusted_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "payout adjustment timestamp")


class PayoutStatement(StrictModel):
    statement_sha256: Sha256
    payout_id_sha256: Sha256
    currency: CurrencyCode
    gross_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    reversal_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    fees_tax_withholding: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    net_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    paid_transaction_set_sha256: Sha256
    period_started_at: datetime
    period_ended_at: datetime
    snapshot_as_of: datetime

    @field_validator("period_started_at", "period_ended_at", "snapshot_as_of")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "payout statement timestamp")

    @model_validator(mode="after")
    def reconcile_statement(self) -> Self:
        if self.net_amount != (
            self.gross_amount
            - self.reversal_amount
            - self.fees_tax_withholding
        ):
            raise ValueError("payout statement net amount does not reconcile")
        if not self.period_started_at < self.period_ended_at <= self.snapshot_as_of:
            raise ValueError("payout statement period is invalid")
        return self


class CohortIntegrityBatch(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    measurement_version: Slug
    property_record_sha256: Sha256
    source_authority_record_sha256: Sha256
    source_receipt_sha256: Sha256
    currency: Literal["JPY"] = "JPY"
    cohort_id: Slug
    cohort_started_at: datetime
    cohort_ended_at: datetime
    snapshot_as_of: datetime
    captured_at: datetime
    expires_at: datetime
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    click_deduplication_sha256: Sha256
    status_mapping_sha256: Sha256
    transaction_deduplication_sha256: Sha256
    acquisition_mapping_sha256: Sha256
    payout_mapping_sha256: Sha256
    qualification_sha256: Sha256
    session_identity_sha256: Sha256
    valid_outbound_filter_sha256: Sha256
    attribution_sha256: Sha256
    refund_chargeback_sha256: Sha256
    privacy_minimization_sha256: Sha256
    qualified_sessions: tuple[QualifiedSession, ...] = ()
    valid_outbound_clicks: tuple[ValidOutboundClick, ...] = ()
    affiliate_accepted_clicks: tuple[AffiliateAcceptedClick, ...] = ()
    transactions: tuple[CurrentTransaction, ...] = ()
    payout_rows: tuple[PayoutRow, ...] = ()
    payout_adjustments: tuple[PayoutAdjustment, ...] = ()
    payout_statement: PayoutStatement

    @field_validator(
        "cohort_started_at",
        "cohort_ended_at",
        "snapshot_as_of",
        "captured_at",
        "expires_at",
    )
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "cohort integrity timestamp")

    @field_validator("partner_ids")
    @classmethod
    def canonicalize_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("cohort partner IDs must be unique")
        return tuple(sorted(values))

    @field_validator("qualified_sessions")
    @classmethod
    def canonicalize_sessions(
        cls, values: tuple[QualifiedSession, ...]
    ) -> tuple[QualifiedSession, ...]:
        return tuple(sorted(values, key=lambda item: item.session_id_sha256))

    @field_validator("valid_outbound_clicks")
    @classmethod
    def canonicalize_outbound(
        cls, values: tuple[ValidOutboundClick, ...]
    ) -> tuple[ValidOutboundClick, ...]:
        return tuple(sorted(values, key=lambda item: item.click_id_sha256))

    @field_validator("affiliate_accepted_clicks")
    @classmethod
    def canonicalize_affiliate_clicks(
        cls, values: tuple[AffiliateAcceptedClick, ...]
    ) -> tuple[AffiliateAcceptedClick, ...]:
        return tuple(
            sorted(values, key=lambda item: item.affiliate_click_id_sha256)
        )

    @field_validator("transactions")
    @classmethod
    def canonicalize_transactions(
        cls, values: tuple[CurrentTransaction, ...]
    ) -> tuple[CurrentTransaction, ...]:
        return tuple(sorted(values, key=lambda item: item.transaction_id_sha256))

    @field_validator("payout_rows")
    @classmethod
    def canonicalize_payout_rows(
        cls, values: tuple[PayoutRow, ...]
    ) -> tuple[PayoutRow, ...]:
        return tuple(sorted(values, key=lambda item: item.transaction_id_sha256))

    @field_validator("payout_adjustments")
    @classmethod
    def canonicalize_adjustments(
        cls, values: tuple[PayoutAdjustment, ...]
    ) -> tuple[PayoutAdjustment, ...]:
        return tuple(sorted(values, key=lambda item: item.transaction_id_sha256))

    @model_validator(mode="after")
    def reconcile_ledger(self) -> Self:
        if not (
            self.cohort_started_at
            < self.cohort_ended_at
            <= self.snapshot_as_of
            <= self.captured_at
            < self.expires_at
        ):
            raise ValueError("invalid cohort capture or expiry window")
        sessions = _unique_map(
            self.qualified_sessions,
            "session_id_sha256",
            "qualified session IDs",
        )
        outbound = _unique_map(
            self.valid_outbound_clicks,
            "click_id_sha256",
            "outbound click IDs",
        )
        affiliate = _unique_map(
            self.affiliate_accepted_clicks,
            "affiliate_click_id_sha256",
            "affiliate click IDs",
        )
        transactions = _unique_map(
            self.transactions,
            "transaction_id_sha256",
            "transaction IDs",
        )
        _require_unique_attr(
            self.valid_outbound_clicks,
            "session_id_sha256",
            "outbound session membership",
        )
        _require_unique_attr(
            self.affiliate_accepted_clicks,
            "outbound_click_id_sha256",
            "affiliate outbound membership",
        )
        _require_unique_attr(
            self.transactions,
            "affiliate_click_id_sha256",
            "transaction click membership",
        )
        partners = set(self.partner_ids)
        for row in self.qualified_sessions:
            _inside(row.qualified_at, self.cohort_started_at, self.cohort_ended_at)
        for row in self.valid_outbound_clicks:
            parent = sessions.get(row.session_id_sha256)
            if parent is None or row.partner_id not in partners:
                raise ValueError("outbound click has unknown session or partner")
            _inside(row.clicked_at, self.cohort_started_at, self.cohort_ended_at)
            if parent.qualified_at > row.clicked_at:
                raise ValueError("outbound click cannot predate qualification")
        for row in self.affiliate_accepted_clicks:
            parent = outbound.get(row.outbound_click_id_sha256)
            if parent is None or parent.partner_id != row.partner_id:
                raise ValueError("affiliate click has unknown or mismatched parent")
            _inside(row.accepted_at, self.cohort_started_at, self.cohort_ended_at)
            if parent.clicked_at > row.accepted_at:
                raise ValueError("affiliate acceptance cannot predate outbound click")
        for row in self.transactions:
            parent = affiliate.get(row.affiliate_click_id_sha256)
            if (
                parent is None
                or parent.partner_id != row.partner_id
                or row.partner_id not in partners
                or row.cohort_id != self.cohort_id
                or row.currency != self.currency
                or not self.cohort_started_at
                <= row.attributed_at
                < self.cohort_ended_at
                or parent.accepted_at > row.attributed_at
                or row.attributed_at > self.snapshot_as_of
                or row.status_events[-1].effective_at > self.snapshot_as_of
            ):
                raise ValueError("transaction is outside the frozen cohort")

        status_receipts = [
            event.source_row_sha256
            for row in self.transactions
            for event in row.status_events
        ]
        if len(status_receipts) != len(set(status_receipts)):
            raise ValueError("status event receipts must be globally distinct")
        acquisition_receipts = [
            row.acquisition_evidence_sha256 for row in self.transactions
        ]
        if len(acquisition_receipts) != len(set(acquisition_receipts)):
            raise ValueError("acquisition evidence receipts must be globally distinct")

        paid = {
            key: row
            for key, row in transactions.items()
            if row.current_status is TransactionStatus.PAID
        }
        payout_rows = _unique_map(
            self.payout_rows, "transaction_id_sha256", "payout transaction IDs"
        )
        _require_unique_attr(self.payout_rows, "payout_row_sha256", "payout row IDs")
        if set(payout_rows) != set(paid):
            raise ValueError("payout rows must cover exactly current paid transactions")
        for transaction_id, payout in payout_rows.items():
            transaction = paid[transaction_id]
            if payout.currency != self.currency or payout.amount != transaction.amount:
                raise ValueError("payout row amount or currency mismatch")
            if not (
                transaction.status_events[-1].effective_at
                <= payout.paid_at
                <= self.snapshot_as_of
            ):
                raise ValueError("payout time is outside the current snapshot")

        adjustments = _unique_map(
            self.payout_adjustments,
            "transaction_id_sha256",
            "payout adjustment transactions",
        )
        _require_unique_attr(
            self.payout_adjustments, "adjustment_id_sha256", "payout adjustment IDs"
        )
        _require_unique_attr(
            self.payout_adjustments,
            "source_row_sha256",
            "payout adjustment source receipts",
        )
        for transaction_id, adjustment in adjustments.items():
            transaction = paid.get(transaction_id)
            if (
                transaction is None
                or adjustment.currency != self.currency
                or adjustment.amount != transaction.amount
                or not payout_rows[transaction_id].paid_at
                <= adjustment.adjusted_at
                <= self.snapshot_as_of
            ):
                raise ValueError("adjustment must fully reverse one paid transaction")

        gross = sum((row.amount for row in self.payout_rows), Decimal(0))
        reversal = sum(
            (row.amount for row in self.payout_adjustments), Decimal(0)
        )
        statement = self.payout_statement
        expected_set_hash = _canonical_sha256(sorted(paid))
        if (
            statement.currency != self.currency
            or statement.gross_amount != gross
            or statement.reversal_amount != reversal
            or statement.paid_transaction_set_sha256 != expected_set_hash
            or statement.period_started_at != self.cohort_started_at
            or statement.period_ended_at != self.cohort_ended_at
            or statement.snapshot_as_of != self.snapshot_as_of
        ):
            raise ValueError("payout statement does not match paid transaction ledger")
        return self


class FaultExercise(StrictModel):
    fault_id: FaultId
    definition_sha256: Sha256
    run_sha256: Sha256
    injected_at: datetime
    restored_at: datetime
    pre_state_sha256: Sha256
    fault_state_sha256: Sha256
    restored_state_sha256: Sha256
    validation_receipt_sha256: Sha256
    target_release_sha256: Sha256
    target_artifact_sha256: Sha256
    target_schema_sha256: Sha256
    detected_at: datetime
    stop_receipt_sha256: Sha256
    restore_started_at: datetime
    passed: bool

    @field_validator(
        "injected_at", "detected_at", "restore_started_at", "restored_at"
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "fault exercise timestamp")

    @model_validator(mode="after")
    def validate_restore(self) -> Self:
        if not (
            self.injected_at
            <= self.detected_at
            <= self.restore_started_at
            <= self.restored_at
        ):
            raise ValueError("fault detection and restore chronology is invalid")
        if self.fault_state_sha256 == self.pre_state_sha256:
            raise ValueError("fault injection must materially change state")
        if self.passed and self.restored_state_sha256 != self.pre_state_sha256:
            raise ValueError("passed fault exercise must restore the prior state")
        return self


class LogicalJobRun(StrictModel):
    run_key_sha256: Sha256
    scheduled_for: datetime
    attempt_receipt_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    succeeded: bool
    completed_at: datetime

    @field_validator("scheduled_for", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "logical job run timestamp")

    @field_validator("attempt_receipt_sha256s")
    @classmethod
    def require_distinct_attempts(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("job attempt receipts must be distinct")
        return values

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        if self.completed_at < self.scheduled_for:
            raise ValueError("logical job completion cannot predate schedule")
        return self


class OperationsIntegrityBatch(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    summary: OperationsSummaryBatch
    retry_identity_sha256: Sha256
    human_time_union_sha256: Sha256
    privacy_minimization_sha256: Sha256
    logical_job_runs: tuple[LogicalJobRun, ...] = ()
    fault_exercises: tuple[FaultExercise, ...] = Field(
        min_length=8, max_length=8
    )

    @field_validator("fault_exercises")
    @classmethod
    def canonicalize_faults(
        cls, values: tuple[FaultExercise, ...]
    ) -> tuple[FaultExercise, ...]:
        if len({item.fault_id for item in values}) != len(values):
            raise ValueError("fault ledger identities must be unique")
        values = tuple(
            sorted(values, key=lambda item: REQUIRED_FAULT_IDS.index(item.fault_id))
        )
        if tuple(item.fault_id for item in values) != REQUIRED_FAULT_IDS:
            raise ValueError("fault ledger must contain the canonical eight once each")
        if len({item.run_sha256 for item in values}) != len(values):
            raise ValueError("fault exercise run identities must be distinct")
        if len({item.validation_receipt_sha256 for item in values}) != len(values):
            raise ValueError("fault validation receipts must be distinct")
        if len({item.stop_receipt_sha256 for item in values}) != len(values):
            raise ValueError("fault stop receipts must be distinct")
        return values

    @field_validator("logical_job_runs")
    @classmethod
    def canonicalize_logical_runs(
        cls, values: tuple[LogicalJobRun, ...]
    ) -> tuple[LogicalJobRun, ...]:
        if len({item.run_key_sha256 for item in values}) != len(values):
            raise ValueError("logical job run keys must be distinct")
        return tuple(sorted(values, key=lambda item: item.run_key_sha256))

    @model_validator(mode="after")
    def reconcile_fault_counts(self) -> Self:
        total = sum(item.rollback_tests_total for item in self.summary.daily_summaries)
        passed = sum(
            item.rollback_tests_passed for item in self.summary.daily_summaries
        )
        job_total = sum(item.job_runs_total for item in self.summary.daily_summaries)
        job_succeeded = sum(
            item.job_runs_succeeded for item in self.summary.daily_summaries
        )
        if job_total != len(self.logical_job_runs) or job_succeeded != sum(
            item.succeeded for item in self.logical_job_runs
        ):
            raise ValueError("daily job counts must equal the unique logical run ledger")
        jobs_by_day: dict[date, list[LogicalJobRun]] = {}
        for item in self.logical_job_runs:
            jobs_by_day.setdefault(
                item.scheduled_for.astimezone(_TOKYO).date(), []
            ).append(item)
        for day in self.summary.daily_summaries:
            logical = jobs_by_day.get(day.local_date, [])
            if day.job_runs_total != len(logical) or day.job_runs_succeeded != sum(
                item.succeeded for item in logical
            ):
                raise ValueError("daily job counts must reconcile by Asia/Tokyo date")
        attempts = [
            receipt
            for item in self.logical_job_runs
            for receipt in item.attempt_receipt_sha256s
        ]
        if len(attempts) != len(set(attempts)):
            raise ValueError("job attempt receipts must be globally distinct")
        if total != len(self.fault_exercises):
            raise ValueError("rollback count must equal the exact fault ledger")
        if passed != sum(item.passed for item in self.fault_exercises):
            raise ValueError("rollback pass count must equal the fault ledger")
        for item in self.fault_exercises:
            if not (
                self.summary.observation_started_at
                <= item.injected_at
                <= item.restored_at
                <= self.summary.captured_at
            ):
                raise ValueError("fault exercise is outside the observation window")
        for item in self.logical_job_runs:
            if not (
                self.summary.observation_started_at
                <= item.scheduled_for
                <= item.completed_at
                <= self.summary.captured_at
            ):
                raise ValueError("logical job run is outside the observation window")
        return self


class MeasurementBundleIndex(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.MEASUREMENT_INDEXER]
    run_id: Slug
    policy_sha256: Sha256
    plan_sha256: Sha256
    property_record_sha256: Sha256
    demand_batch_sha256: Sha256
    cohort_batch_sha256: Sha256
    operations_batch_sha256: Sha256
    demand_attestation_sha256: Sha256
    cohort_attestation_sha256: Sha256
    operations_attestation_sha256: Sha256
    captured_at: datetime
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("captured_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "measurement bundle index timestamp")

    @model_validator(mode="after")
    def validate_index(self) -> Self:
        _validate_signed(self, "measurement bundle index")
        if not self.captured_at <= self.issued_at < self.expires_at:
            raise ValueError("invalid bundle index time window")
        return self


class MeasurementReconciliationFacts(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    qualified_sessions: int = Field(ge=0)
    valid_outbound_clicks: int = Field(ge=0)
    affiliate_accepted_clicks: int = Field(ge=0)
    current_transactions: int = Field(ge=0)
    new_acquisition_transactions: int = Field(ge=0)
    gross_paid_transactions: int = Field(ge=0)
    reversed_paid_transactions: int = Field(ge=0)
    net_paid_transactions: int = Field(ge=0)
    settled_new_acquisition_amount: Decimal = Field(ge=0)
    gross_payout_amount: Decimal = Field(ge=0)
    net_payout_amount: Decimal = Field(ge=0)
    confirmed_epc: Decimal | None
    net_payout_epc: Decimal | None
    exact_faults_passed: int = Field(ge=0, le=8)


class MeasurementIntegrityReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA]
    run_id: Slug
    property_record_sha256: Sha256
    property_domain_sha256: Sha256
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    currency: Literal["JPY"] = "JPY"
    observation_started_at: datetime
    observation_ended_at: datetime
    partner_ids: tuple[Slug, ...] = Field(min_length=1)
    policy_sha256: Sha256
    plan_sha256: Sha256
    bundle_index_sha256: Sha256
    demand_attestation_sha256: Sha256
    cohort_attestation_sha256: Sha256
    operations_attestation_sha256: Sha256
    demand: DemandEvidence
    cohort: CohortEvidence
    operations: OperationsEvidence
    reconciliation: MeasurementReconciliationFacts
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator(
        "observation_started_at", "observation_ended_at", "issued_at", "expires_at"
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "measurement integrity report timestamp")

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        _validate_signed(self, "measurement integrity report")
        return self


class MeasurementBoundDossier(StrictModel):
    """A dossier whose measurement fields remain attached to a signed report."""

    schema_version: Literal["1.0"] = "1.0"
    report: MeasurementIntegrityReport
    dossier: BusinessDossier
    dossier_sha256: Sha256

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        _validate_dossier_binding(self.dossier, self.report)
        expected = hash_signed_artifact(self.dossier)
        if self.dossier_sha256 != expected:
            raise ValueError("measurement-bound dossier hash mismatch")
        return self


class MeasurementIntegrityRuntime:
    """Pinned downstream verifier; it performs no external operation."""

    __slots__ = (
        "__authority_pins",
        "__policy",
        "__trust_store",
        "__verifier_signing_key",
    )

    def __init__(
        self,
        policy: MeasurementPolicy,
        trust_store: MeasurementTrustStore,
        verifier_signing_key: Ed25519PrivateKey,
        authority_pins: MeasurementAuthorityPins,
    ) -> None:
        if type(policy) is not MeasurementPolicy:
            raise TypeError("policy must be MeasurementPolicy")
        if type(trust_store) is not MeasurementTrustStore:
            raise TypeError("trust_store must be MeasurementTrustStore")
        validated_policy = MeasurementPolicy.model_validate(policy.model_dump())
        validated_trust = MeasurementTrustStore.model_validate(trust_store.model_dump())
        if type(authority_pins) is not MeasurementAuthorityPins:
            raise TypeError("authority_pins must be MeasurementAuthorityPins")
        validated_pins = MeasurementAuthorityPins.model_validate(
            authority_pins.model_dump()
        )
        if (
            validated_pins.expected_policy_sha256
            != hash_measurement_policy(validated_policy)
            or validated_pins.expected_trust_store_sha256
            != hash_measurement_trust_store(validated_trust)
        ):
            raise MeasurementInputError("consumer measurement authority pin mismatch")
        if validated_policy.trust_store_sha256 != hash_measurement_trust_store(
            validated_trust
        ):
            raise MeasurementInputError("measurement trust-store pin mismatch")
        if not _signing_key_matches(
            verifier_signing_key, validated_trust.measurement_verifier
        ):
            raise MeasurementInputError("measurement verifier signing key mismatch")
        self.__policy = validated_policy
        self.__trust_store = validated_trust
        self.__verifier_signing_key = verifier_signing_key
        self.__authority_pins = validated_pins

    def evaluate(
        self,
        plan: SignedMeasurementRunPlan,
        demand_batch: DemandIntegrityBatch,
        cohort_batch: CohortIntegrityBatch,
        operations_batch: OperationsIntegrityBatch,
        demand_attestation: ProducerAttestation,
        cohort_attestation: ProducerAttestation,
        operations_attestation: ProducerAttestation,
        bundle_index: MeasurementBundleIndex,
        *,
        at: datetime,
    ) -> MeasurementIntegrityReport:
        values = self._derive_report_values(
            plan,
            demand_batch,
            cohort_batch,
            operations_batch,
            demand_attestation,
            cohort_attestation,
            operations_attestation,
            bundle_index,
            at=at,
        )
        return _build_signed(
            MeasurementIntegrityReport, values, self.__verifier_signing_key
        )

    def verify(
        self,
        report: MeasurementIntegrityReport,
        plan: SignedMeasurementRunPlan,
        demand_batch: DemandIntegrityBatch,
        cohort_batch: CohortIntegrityBatch,
        operations_batch: OperationsIntegrityBatch,
        demand_attestation: ProducerAttestation,
        cohort_attestation: ProducerAttestation,
        operations_attestation: ProducerAttestation,
        bundle_index: MeasurementBundleIndex,
        *,
        at: datetime,
    ) -> bool:
        """Re-derive and verify an existing report without issuing a signature."""

        _utc(at, "measurement report verification timestamp")
        if type(report) is not MeasurementIntegrityReport:
            return False
        try:
            supplied = MeasurementIntegrityReport.model_validate(
                report.model_dump()
            )
            values = self._derive_report_values(
                plan,
                demand_batch,
                cohort_batch,
                operations_batch,
                demand_attestation,
                cohort_attestation,
                operations_attestation,
                bundle_index,
                at=supplied.issued_at,
            )
            provisional = MeasurementIntegrityReport.model_construct(
                **values,
                payload_sha256="0" * 64,
                signature_base64url="A" * 86,
            )
            expected_payload_sha256 = _signed_payload_hash(provisional)
            expected_unsigned = provisional.model_dump(
                mode="python",
                exclude={"payload_sha256", "signature_base64url"},
            )
            supplied_unsigned = supplied.model_dump(
                mode="python",
                exclude={"payload_sha256", "signature_base64url"},
            )
            return (
                supplied_unsigned == expected_unsigned
                and supplied.payload_sha256 == expected_payload_sha256
                and verify_measurement_integrity_report(
                    supplied,
                    self.__policy,
                    self.__trust_store,
                    self.__authority_pins,
                    at=at,
                )
            )
        except (MeasurementInputError, TypeError, ValueError):
            return False

    def _derive_report_values(
        self,
        plan: SignedMeasurementRunPlan,
        demand_batch: DemandIntegrityBatch,
        cohort_batch: CohortIntegrityBatch,
        operations_batch: OperationsIntegrityBatch,
        demand_attestation: ProducerAttestation,
        cohort_attestation: ProducerAttestation,
        operations_attestation: ProducerAttestation,
        bundle_index: MeasurementBundleIndex,
        *,
        at: datetime,
    ) -> dict[str, Any]:
        _utc(at, "measurement evaluation timestamp")
        artifacts = (
            (plan, SignedMeasurementRunPlan),
            (demand_batch, DemandIntegrityBatch),
            (cohort_batch, CohortIntegrityBatch),
            (operations_batch, OperationsIntegrityBatch),
            (demand_attestation, ProducerAttestation),
            (cohort_attestation, ProducerAttestation),
            (operations_attestation, ProducerAttestation),
            (bundle_index, MeasurementBundleIndex),
        )
        for value, expected_type in artifacts:
            if type(value) is not expected_type:
                raise TypeError(f"measurement input must be {expected_type.__name__}")
        plan = SignedMeasurementRunPlan.model_validate(plan.model_dump())
        demand_batch = DemandIntegrityBatch.model_validate(demand_batch.model_dump())
        cohort_batch = CohortIntegrityBatch.model_validate(cohort_batch.model_dump())
        operations_batch = OperationsIntegrityBatch.model_validate(
            operations_batch.model_dump()
        )
        demand_attestation = ProducerAttestation.model_validate(
            demand_attestation.model_dump()
        )
        cohort_attestation = ProducerAttestation.model_validate(
            cohort_attestation.model_dump()
        )
        operations_attestation = ProducerAttestation.model_validate(
            operations_attestation.model_dump()
        )
        bundle_index = MeasurementBundleIndex.model_validate(bundle_index.model_dump())

        self._verify_plan(plan, at)
        definition = plan.definition
        plan_hash = hash_signed_artifact(plan)
        policy_hash = hash_measurement_policy(self.__policy)
        batch_hashes = {
            MeasurementDataset.DEMAND: hash_signed_artifact(demand_batch),
            MeasurementDataset.COHORT: hash_signed_artifact(cohort_batch),
            MeasurementDataset.OPERATIONS: hash_signed_artifact(operations_batch),
        }
        attestations = {
            MeasurementDataset.DEMAND: demand_attestation,
            MeasurementDataset.COHORT: cohort_attestation,
            MeasurementDataset.OPERATIONS: operations_attestation,
        }
        batches = {
            MeasurementDataset.DEMAND: demand_batch,
            MeasurementDataset.COHORT: cohort_batch,
            MeasurementDataset.OPERATIONS: operations_batch,
        }
        for dataset, attestation in attestations.items():
            self._verify_producer(
                dataset,
                attestation,
                batches[dataset],
                batch_hashes[dataset],
                plan,
                plan_hash,
                at,
            )
        self._verify_index(
            bundle_index,
            plan,
            plan_hash,
            policy_hash,
            batch_hashes,
            attestations,
            batches,
            at,
        )
        self._verify_cross_batch_rules(
            definition, demand_batch, cohort_batch, operations_batch
        )
        if any(not item.passed for item in operations_batch.fault_exercises):
            raise MeasurementInputError("all eight fault restores must pass")
        if any(
            item.acquisition_class is AcquisitionClass.UNKNOWN
            for item in cohort_batch.transactions
        ):
            raise MeasurementInputError(
                "unknown acquisition rows cannot enter readiness evidence"
            )
        _current_batch(cohort_batch.captured_at, cohort_batch.expires_at, at)

        demand = build_demand_evidence(demand_batch.summary, at=at)
        demand = self._bind_evidence(
            demand, plan_hash, bundle_index, demand_attestation, demand_batch
        )
        cohort, facts = _build_cohort_evidence(
            cohort_batch,
            plan_hash=plan_hash,
            bundle_index=bundle_index,
            attestation=cohort_attestation,
        )
        operations = build_operations_evidence(operations_batch.summary, at=at)
        operations = self._bind_evidence(
            operations,
            plan_hash,
            bundle_index,
            operations_attestation,
            operations_batch,
        )
        facts = facts.model_copy(
            update={
                "exact_faults_passed": sum(
                    item.passed for item in operations_batch.fault_exercises
                )
            }
        )
        expires_at = min(
            plan.expires_at,
            demand_attestation.expires_at,
            cohort_attestation.expires_at,
            operations_attestation.expires_at,
            bundle_index.expires_at,
            demand.expires_at,
            cohort.expires_at,
            operations.expires_at,
            at + timedelta(seconds=self.__policy.maximum_report_ttl_seconds),
        )
        values = {
            "issuer": self.__trust_store.measurement_verifier.issuer,
            "key_id_sha256": self.__trust_store.measurement_verifier.key_id_sha256,
            "signer_role": SigningRole.TCO_QA,
            "run_id": definition.run_id,
            "property_record_sha256": definition.property_record_sha256,
            "property_domain_sha256": definition.property_domain_sha256,
            "country": definition.country,
            "language": definition.language,
            "currency": definition.currency,
            "observation_started_at": definition.observation_started_at.astimezone(
                timezone.utc
            ),
            "observation_ended_at": definition.observation_ended_at.astimezone(
                timezone.utc
            ),
            "partner_ids": definition.partner_ids,
            "policy_sha256": policy_hash,
            "plan_sha256": plan_hash,
            "bundle_index_sha256": hash_signed_artifact(bundle_index),
            "demand_attestation_sha256": hash_signed_artifact(demand_attestation),
            "cohort_attestation_sha256": hash_signed_artifact(cohort_attestation),
            "operations_attestation_sha256": hash_signed_artifact(
                operations_attestation
            ),
            "demand": demand,
            "cohort": cohort,
            "operations": operations,
            "reconciliation": facts,
            "issued_at": at,
            "expires_at": expires_at,
        }
        return values

    def _verify_plan(self, plan: SignedMeasurementRunPlan, at: datetime) -> None:
        definition = plan.definition
        policy = self.__policy
        key = self.__trust_store.run_human
        if (
            definition.decision is not RunFreezeDecision.GO
            or definition.policy_sha256 != hash_measurement_policy(policy)
            or definition.trust_store_sha256 != policy.trust_store_sha256
            or definition.property_record_sha256 != policy.property_record_sha256
            or definition.property_domain_sha256 != policy.property_domain_sha256
            or definition.country != policy.country
            or definition.language != policy.language
            or definition.currency != policy.currency
            or definition.business_timezone != policy.business_timezone
            or hash_signed_artifact(definition.rules)
            != policy.approved_rule_pins_sha256
            or _canonical_sha256(
                {
                    "demand": definition.demand_authority_record_sha256,
                    "cohort": definition.cohort_authority_record_sha256,
                    "operations": definition.operations_authority_record_sha256,
                }
            )
            != policy.approved_source_authorities_sha256
            or _canonical_sha256(
                [item.model_dump(mode="json") for item in definition.fault_requirements]
            )
            != policy.approved_fault_requirements_sha256
            or tuple(item.fault_id for item in definition.fault_requirements)
            != policy.required_fault_ids
            or plan.issuer != key.issuer
            or plan.key_id_sha256 != key.key_id_sha256
            or not _current_signed(
                plan, key, at, policy.maximum_plan_ttl_seconds
            )
        ):
            raise MeasurementInputError("measurement run plan verification failed")

    def _verify_producer(
        self,
        dataset: MeasurementDataset,
        attestation: ProducerAttestation,
        batch: StrictModel,
        batch_hash: str,
        plan: SignedMeasurementRunPlan,
        plan_hash: str,
        at: datetime,
    ) -> None:
        definition = plan.definition
        key = {
            MeasurementDataset.DEMAND: self.__trust_store.demand_producer,
            MeasurementDataset.COHORT: self.__trust_store.cohort_producer,
            MeasurementDataset.OPERATIONS: self.__trust_store.operations_producer,
        }[dataset]
        versions = {
            MeasurementDataset.DEMAND: definition.demand_measurement_version,
            MeasurementDataset.COHORT: definition.cohort_measurement_version,
            MeasurementDataset.OPERATIONS: definition.operations_measurement_version,
        }
        authorities = {
            MeasurementDataset.DEMAND: definition.demand_authority_record_sha256,
            MeasurementDataset.COHORT: definition.cohort_authority_record_sha256,
            MeasurementDataset.OPERATIONS: definition.operations_authority_record_sha256,
        }
        expected_coverage = _expected_coverage(batch)
        output_count = sum(len(values) for values in expected_coverage.values())
        captured_at = measurement_batch_captured_at(batch)
        retrieved_at = measurement_batch_retrieved_at(batch)
        if (
            attestation.dataset is not dataset
            or attestation.issuer != key.issuer
            or attestation.key_id_sha256 != key.key_id_sha256
            or attestation.run_id != definition.run_id
            or attestation.policy_sha256 != definition.policy_sha256
            or attestation.plan_sha256 != plan_hash
            or attestation.property_record_sha256
            != definition.property_record_sha256
            or attestation.source_authority_record_sha256 != authorities[dataset]
            or attestation.measurement_version != versions[dataset]
            or attestation.batch_sha256 != batch_hash
            or attestation.coverage.output_records != output_count
            or attestation.coverage.coverage_rule_sha256
            != definition.rules.coverage_completeness_sha256
            or attestation.coverage.source_export_sha256
            != measurement_batch_source_receipt_sha256(batch)
            or attestation.coverage.conflict_records != 0
            or attestation.coverage.unknown_records != 0
            or not _coverage_matches_batch(
                attestation.coverage, batch, expected_coverage=expected_coverage
            )
            or attestation.issued_at < captured_at
            or attestation.issued_at < retrieved_at
            or attestation.issued_at < plan.issued_at
            or not _current_signed(
                attestation,
                key,
                at,
                self.__policy.maximum_producer_ttl_seconds,
            )
        ):
            raise MeasurementInputError(f"{dataset.value} producer verification failed")

    def _verify_index(
        self,
        index: MeasurementBundleIndex,
        plan: SignedMeasurementRunPlan,
        plan_hash: str,
        policy_hash: str,
        batch_hashes: dict[MeasurementDataset, str],
        attestations: dict[MeasurementDataset, ProducerAttestation],
        batches: dict[MeasurementDataset, StrictModel],
        at: datetime,
    ) -> None:
        definition = plan.definition
        key = self.__trust_store.bundle_indexer
        expected_attestations = {
            dataset: hash_signed_artifact(attestation)
            for dataset, attestation in attestations.items()
        }
        expected_captured_at = max(
            measurement_batch_captured_at(item) for item in batches.values()
        )
        latest_attestation_at = max(item.issued_at for item in attestations.values())
        if (
            index.issuer != key.issuer
            or index.key_id_sha256 != key.key_id_sha256
            or index.run_id != definition.run_id
            or index.run_id != self.__authority_pins.expected_run_id
            or hash_signed_artifact(index)
            != self.__authority_pins.expected_bundle_index_sha256
            or index.policy_sha256 != policy_hash
            or index.plan_sha256 != plan_hash
            or index.property_record_sha256 != definition.property_record_sha256
            or index.demand_batch_sha256
            != batch_hashes[MeasurementDataset.DEMAND]
            or index.cohort_batch_sha256
            != batch_hashes[MeasurementDataset.COHORT]
            or index.operations_batch_sha256
            != batch_hashes[MeasurementDataset.OPERATIONS]
            or index.demand_attestation_sha256
            != expected_attestations[MeasurementDataset.DEMAND]
            or index.cohort_attestation_sha256
            != expected_attestations[MeasurementDataset.COHORT]
            or index.operations_attestation_sha256
            != expected_attestations[MeasurementDataset.OPERATIONS]
            or index.captured_at != expected_captured_at
            or index.issued_at < latest_attestation_at
            or not _current_signed(
                index, key, at, self.__policy.maximum_index_ttl_seconds
            )
        ):
            raise MeasurementInputError("measurement bundle index verification failed")

    def _verify_cross_batch_rules(
        self,
        definition: MeasurementRunDefinition,
        demand: DemandIntegrityBatch,
        cohort: CohortIntegrityBatch,
        operations: OperationsIntegrityBatch,
    ) -> None:
        rules = definition.rules
        fault_definitions = {
            item.fault_id: item.definition_sha256
            for item in definition.fault_requirements
        }
        if (
            demand.summary.country != definition.country
            or demand.summary.language != definition.language
            or demand.summary.source_timezone != definition.business_timezone
            or demand.summary.source_month != definition.source_month
            or demand.summary.measurement_version
            != definition.demand_measurement_version
            or demand.summary.deduplication_sha256
            != rules.demand_deduplication_sha256
            or demand.summary.receipt.authority_record_sha256
            != definition.demand_authority_record_sha256
            or demand.qualification_sha256 != rules.qualification_sha256
            or demand.session_identity_sha256 != rules.session_identity_sha256
            or demand.valid_outbound_filter_sha256
            != rules.valid_outbound_filter_sha256
            or demand.privacy_minimization_sha256
            != rules.privacy_minimization_sha256
            or cohort.property_record_sha256 != definition.property_record_sha256
            or cohort.source_authority_record_sha256
            != definition.cohort_authority_record_sha256
            or cohort.currency != definition.currency
            or cohort.partner_ids != definition.partner_ids
            or cohort.cohort_started_at != definition.observation_started_at
            or cohort.cohort_ended_at != definition.observation_ended_at
            or cohort.measurement_version != definition.cohort_measurement_version
            or cohort.click_deduplication_sha256
            != rules.event_deduplication_sha256
            or cohort.status_mapping_sha256 != rules.status_transition_sha256
            or cohort.transaction_deduplication_sha256
            != rules.transaction_deduplication_sha256
            or cohort.acquisition_mapping_sha256
            != rules.new_acquisition_sha256
            or cohort.payout_mapping_sha256
            != rules.payout_reconciliation_sha256
            or cohort.qualification_sha256 != rules.qualification_sha256
            or cohort.session_identity_sha256 != rules.session_identity_sha256
            or cohort.valid_outbound_filter_sha256
            != rules.valid_outbound_filter_sha256
            or cohort.attribution_sha256 != rules.attribution_sha256
            or cohort.refund_chargeback_sha256
            != rules.refund_chargeback_sha256
            or cohort.privacy_minimization_sha256
            != rules.privacy_minimization_sha256
            or cohort.snapshot_as_of != definition.observation_ended_at
            or cohort.captured_at != definition.observation_ended_at
            or operations.summary.property_record_sha256
            != definition.property_record_sha256
            or operations.summary.observation_started_at
            != definition.observation_started_at
            or operations.summary.captured_at != definition.observation_ended_at
            or operations.summary.measurement_version
            != definition.operations_measurement_version
            or operations.summary.receipt.authority_record_sha256
            != definition.operations_authority_record_sha256
            or operations.summary.routine_inventory_sha256
            != rules.routine_inventory_sha256
            or operations.summary.job_schedule_sha256
            != rules.job_schedule_sha256
            or operations.summary.job_status_mapping_sha256
            != rules.job_status_mapping_sha256
            or operations.summary.exception_deduplication_sha256
            != rules.exception_deduplication_sha256
            or operations.summary.qa_policy_sha256 != rules.qa_policy_sha256
            or operations.summary.rollback_catalog_sha256
            != rules.fault_catalog_sha256
            or operations.retry_identity_sha256 != rules.retry_identity_sha256
            or operations.human_time_union_sha256
            != rules.human_time_union_sha256
            or operations.privacy_minimization_sha256
            != rules.privacy_minimization_sha256
            or len(operations.logical_job_runs)
            != definition.planned_logical_job_count
            or _identity_set_sha256(
                item.run_key_sha256 for item in operations.logical_job_runs
            )
            != definition.planned_logical_job_set_sha256
            or any(
                item.definition_sha256 != fault_definitions[item.fault_id]
                or item.target_release_sha256
                != definition.fault_target_release_sha256
                or item.target_artifact_sha256
                != definition.fault_target_artifact_sha256
                or item.target_schema_sha256
                != definition.fault_target_schema_sha256
                for item in operations.fault_exercises
            )
        ):
            raise MeasurementInputError("measurement batch rule binding failed")

    @staticmethod
    def _bind_evidence(
        evidence: DemandEvidence | OperationsEvidence,
        plan_hash: str,
        index: MeasurementBundleIndex,
        attestation: ProducerAttestation,
        batch: StrictModel,
    ) -> DemandEvidence | OperationsEvidence:
        digest = _canonical_sha256(
            {
                "plan_sha256": plan_hash,
                "index_sha256": hash_signed_artifact(index),
                "attestation_sha256": hash_signed_artifact(attestation),
                "batch_sha256": hash_signed_artifact(batch),
            }
        )
        return evidence.model_copy(
            update={"evidence_version": f"sha256:{digest}", "source_sha256": digest}
        )


class MeasurementIntegrityVerifier:
    """Credential-blind P12 verifier that owns only policy and public keys."""

    __slots__ = ("__runtime",)

    def __init__(
        self,
        policy: MeasurementPolicy,
        trust_store: MeasurementTrustStore,
        authority_pins: MeasurementAuthorityPins,
    ) -> None:
        if type(policy) is not MeasurementPolicy:
            raise TypeError("policy must be MeasurementPolicy")
        if type(trust_store) is not MeasurementTrustStore:
            raise TypeError("trust_store must be MeasurementTrustStore")
        if type(authority_pins) is not MeasurementAuthorityPins:
            raise TypeError("authority_pins must be MeasurementAuthorityPins")
        validated_policy = MeasurementPolicy.model_validate(policy.model_dump())
        validated_trust = MeasurementTrustStore.model_validate(
            trust_store.model_dump()
        )
        validated_pins = MeasurementAuthorityPins.model_validate(
            authority_pins.model_dump()
        )
        if (
            validated_pins.expected_policy_sha256
            != hash_measurement_policy(validated_policy)
            or validated_pins.expected_trust_store_sha256
            != hash_measurement_trust_store(validated_trust)
            or validated_policy.trust_store_sha256
            != hash_measurement_trust_store(validated_trust)
        ):
            raise MeasurementInputError(
                "consumer measurement authority pin mismatch"
            )
        runtime = object.__new__(MeasurementIntegrityRuntime)
        runtime._MeasurementIntegrityRuntime__policy = validated_policy
        runtime._MeasurementIntegrityRuntime__trust_store = validated_trust
        runtime._MeasurementIntegrityRuntime__authority_pins = validated_pins
        runtime._MeasurementIntegrityRuntime__verifier_signing_key = None
        self.__runtime = runtime

    def verify(
        self,
        report: MeasurementIntegrityReport,
        plan: SignedMeasurementRunPlan,
        demand_batch: DemandIntegrityBatch,
        cohort_batch: CohortIntegrityBatch,
        operations_batch: OperationsIntegrityBatch,
        demand_attestation: ProducerAttestation,
        cohort_attestation: ProducerAttestation,
        operations_attestation: ProducerAttestation,
        bundle_index: MeasurementBundleIndex,
        *,
        at: datetime,
    ) -> bool:
        return self.__runtime.verify(
            report,
            plan,
            demand_batch,
            cohort_batch,
            operations_batch,
            demand_attestation,
            cohort_attestation,
            operations_attestation,
            bundle_index,
            at=at,
        )


def sign_measurement_run_plan(
    definition: MeasurementRunDefinition,
    signing_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedMeasurementRunPlan:
    if type(definition) is not MeasurementRunDefinition:
        raise TypeError("definition must be MeasurementRunDefinition")
    key = create_verification_key(
        signing_key.public_key(), issuer=issuer, role=SigningRole.MEASUREMENT_HUMAN
    )
    return _build_signed(
        SignedMeasurementRunPlan,
        {
            "definition": MeasurementRunDefinition.model_validate(
                definition.model_dump()
            ),
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.MEASUREMENT_HUMAN,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        signing_key,
    )


def sign_producer_attestation(
    plan: SignedMeasurementRunPlan,
    dataset: MeasurementDataset,
    batch: StrictModel,
    coverage: ProducerCoverage,
    signing_key: Ed25519PrivateKey,
    *,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> ProducerAttestation:
    expected_type: dict[MeasurementDataset, type[StrictModel]] = {
        MeasurementDataset.DEMAND: DemandIntegrityBatch,
        MeasurementDataset.COHORT: CohortIntegrityBatch,
        MeasurementDataset.OPERATIONS: OperationsIntegrityBatch,
    }
    if type(batch) is not expected_type[dataset]:
        raise TypeError("producer batch type does not match dataset")
    roles = {
        MeasurementDataset.DEMAND: SigningRole.DEMAND_PRODUCER,
        MeasurementDataset.COHORT: SigningRole.COHORT_PRODUCER,
        MeasurementDataset.OPERATIONS: SigningRole.OPERATIONS_PRODUCER,
    }
    definition = plan.definition
    versions = {
        MeasurementDataset.DEMAND: definition.demand_measurement_version,
        MeasurementDataset.COHORT: definition.cohort_measurement_version,
        MeasurementDataset.OPERATIONS: definition.operations_measurement_version,
    }
    authorities = {
        MeasurementDataset.DEMAND: definition.demand_authority_record_sha256,
        MeasurementDataset.COHORT: definition.cohort_authority_record_sha256,
        MeasurementDataset.OPERATIONS: definition.operations_authority_record_sha256,
    }
    key = create_verification_key(
        signing_key.public_key(), issuer=issuer, role=roles[dataset]
    )
    return _build_signed(
        ProducerAttestation,
        {
            "dataset": dataset,
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": roles[dataset],
            "run_id": definition.run_id,
            "policy_sha256": definition.policy_sha256,
            "plan_sha256": hash_signed_artifact(plan),
            "property_record_sha256": definition.property_record_sha256,
            "source_authority_record_sha256": authorities[dataset],
            "measurement_version": versions[dataset],
            "batch_sha256": hash_signed_artifact(batch),
            "coverage": coverage,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        signing_key,
    )


def sign_measurement_bundle_index(
    plan: SignedMeasurementRunPlan,
    demand_batch: DemandIntegrityBatch,
    cohort_batch: CohortIntegrityBatch,
    operations_batch: OperationsIntegrityBatch,
    demand_attestation: ProducerAttestation,
    cohort_attestation: ProducerAttestation,
    operations_attestation: ProducerAttestation,
    signing_key: Ed25519PrivateKey,
    *,
    issuer: str,
    captured_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> MeasurementBundleIndex:
    key = create_verification_key(
        signing_key.public_key(),
        issuer=issuer,
        role=SigningRole.MEASUREMENT_INDEXER,
    )
    definition = plan.definition
    return _build_signed(
        MeasurementBundleIndex,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.MEASUREMENT_INDEXER,
            "run_id": definition.run_id,
            "policy_sha256": definition.policy_sha256,
            "plan_sha256": hash_signed_artifact(plan),
            "property_record_sha256": definition.property_record_sha256,
            "demand_batch_sha256": hash_signed_artifact(demand_batch),
            "cohort_batch_sha256": hash_signed_artifact(cohort_batch),
            "operations_batch_sha256": hash_signed_artifact(operations_batch),
            "demand_attestation_sha256": hash_signed_artifact(demand_attestation),
            "cohort_attestation_sha256": hash_signed_artifact(cohort_attestation),
            "operations_attestation_sha256": hash_signed_artifact(
                operations_attestation
            ),
            "captured_at": captured_at,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
        signing_key,
    )


def verify_measurement_integrity_report(
    report: MeasurementIntegrityReport,
    policy: MeasurementPolicy,
    trust_store: MeasurementTrustStore,
    authority_pins: MeasurementAuthorityPins,
    *,
    at: datetime,
) -> bool:
    _utc(at, "report verification timestamp")
    if (
        type(report) is not MeasurementIntegrityReport
        or type(policy) is not MeasurementPolicy
        or type(trust_store) is not MeasurementTrustStore
        or type(authority_pins) is not MeasurementAuthorityPins
    ):
        return False
    try:
        report = MeasurementIntegrityReport.model_validate(report.model_dump())
        policy = MeasurementPolicy.model_validate(policy.model_dump())
        trust_store = MeasurementTrustStore.model_validate(trust_store.model_dump())
        authority_pins = MeasurementAuthorityPins.model_validate(
            authority_pins.model_dump()
        )
    except (TypeError, ValueError):
        return False
    key = trust_store.measurement_verifier
    return (
        authority_pins.expected_policy_sha256 == hash_measurement_policy(policy)
        and authority_pins.expected_trust_store_sha256
        == hash_measurement_trust_store(trust_store)
        and policy.trust_store_sha256 == hash_measurement_trust_store(trust_store)
        and report.policy_sha256 == hash_measurement_policy(policy)
        and report.run_id == authority_pins.expected_run_id
        and report.bundle_index_sha256
        == authority_pins.expected_bundle_index_sha256
        and report.property_record_sha256 == policy.property_record_sha256
        and report.property_domain_sha256 == policy.property_domain_sha256
        and report.country == policy.country
        and report.language == policy.language
        and report.currency == policy.currency
        and report.issuer == key.issuer
        and report.key_id_sha256 == key.key_id_sha256
        and _current_signed(
            report, key, at, policy.maximum_report_ttl_seconds
        )
    )


def assemble_measurement_bound_dossier(
    report: MeasurementIntegrityReport,
    policy: MeasurementPolicy,
    trust_store: MeasurementTrustStore,
    authority_pins: MeasurementAuthorityPins,
    *,
    plans: tuple[VendorPlan, ...] | list[VendorPlan],
    affiliate_decisions: tuple[AffiliateProgramDecision, ...]
    | list[AffiliateProgramDecision],
    property_domain: str,
    at: datetime,
) -> MeasurementBoundDossier:
    """Build the production-authority measurement path from one verified report."""

    if not verify_measurement_integrity_report(
        report, policy, trust_store, authority_pins, at=at
    ):
        raise MeasurementInputError("measurement integrity report verification failed")
    dossier = build_business_dossier(
        plans=plans,
        affiliate_decisions=affiliate_decisions,
        property_domain=property_domain,
        demand=report.demand,
        cohort=report.cohort,
        operations=report.operations,
        at=at,
    )
    return MeasurementBoundDossier(
        report=report,
        dossier=dossier,
        dossier_sha256=hash_signed_artifact(dossier),
    )


def verify_measurement_bound_dossier(
    bundle: MeasurementBoundDossier,
    policy: MeasurementPolicy,
    trust_store: MeasurementTrustStore,
    authority_pins: MeasurementAuthorityPins,
    *,
    at: datetime,
) -> bool:
    if type(bundle) is not MeasurementBoundDossier:
        return False
    try:
        bundle = MeasurementBoundDossier.model_validate(bundle.model_dump())
    except (TypeError, ValueError):
        return False
    return verify_measurement_integrity_report(
        bundle.report, policy, trust_store, authority_pins, at=at
    )


def hash_measurement_trust_store(trust_store: MeasurementTrustStore) -> str:
    if type(trust_store) is not MeasurementTrustStore:
        raise TypeError("trust_store must be MeasurementTrustStore")
    return hash_signed_artifact(
        MeasurementTrustStore.model_validate(trust_store.model_dump())
    )


def hash_measurement_policy(policy: MeasurementPolicy) -> str:
    if type(policy) is not MeasurementPolicy:
        raise TypeError("policy must be MeasurementPolicy")
    return hash_signed_artifact(MeasurementPolicy.model_validate(policy.model_dump()))


def hash_signed_artifact(model: StrictModel) -> str:
    if not isinstance(model, StrictModel):
        raise TypeError("artifact must be a StrictModel")
    return _canonical_sha256(model.model_dump(mode="python"))


def _build_cohort_evidence(
    batch: CohortIntegrityBatch,
    *,
    plan_hash: str,
    bundle_index: MeasurementBundleIndex,
    attestation: ProducerAttestation,
) -> tuple[CohortEvidence, MeasurementReconciliationFacts]:
    reversed_ids = {
        item.transaction_id_sha256 for item in batch.payout_adjustments
    }
    eligible = [
        row
        for row in batch.transactions
        if row.acquisition_class is AcquisitionClass.NEW
        and row.current_status in (TransactionStatus.CONFIRMED, TransactionStatus.PAID)
        and row.transaction_id_sha256 not in reversed_ids
    ]
    confirmed = sum(
        (
            row.amount
            for row in eligible
            if row.current_status is TransactionStatus.CONFIRMED
        ),
        Decimal(0),
    )
    paid = sum(
        (
            row.amount
            for row in eligible
            if row.current_status is TransactionStatus.PAID
        ),
        Decimal(0),
    )
    pending = sum(
        (
            row.amount
            for row in batch.transactions
            if row.current_status is TransactionStatus.PENDING
        ),
        Decimal(0),
    )
    rejected = sum(
        (
            row.amount
            for row in batch.transactions
            if row.current_status
            in (
                TransactionStatus.REJECTED,
                TransactionStatus.REFUNDED,
                TransactionStatus.CHARGED_BACK,
            )
            or row.transaction_id_sha256 in reversed_ids
        ),
        Decimal(0),
    )
    denominator = len(batch.valid_outbound_clicks)
    settled = confirmed + paid
    confirmed_epc = None if denominator == 0 else settled / Decimal(denominator)
    net_payout_epc = (
        None
        if denominator == 0
        else batch.payout_statement.net_amount / Decimal(denominator)
    )
    digest = _canonical_sha256(
        {
            "plan_sha256": plan_hash,
            "index_sha256": hash_signed_artifact(bundle_index),
            "attestation_sha256": hash_signed_artifact(attestation),
            "batch_sha256": hash_signed_artifact(batch),
        }
    )
    evidence = CohortEvidence(
        evidence_version=f"sha256:{digest}",
        source_sha256=digest,
        status_mapping_sha256=batch.status_mapping_sha256,
        captured_at=batch.captured_at,
        expires_at=batch.expires_at,
        cohort=CohortInput(
            currency=batch.currency,
            valid_clicks=denominator,
            age_days=(batch.snapshot_as_of - batch.cohort_started_at).days,
            commissions=CommissionInput(
                pending=pending,
                rejected=rejected,
                confirmed=confirmed,
                paid=paid,
            ),
        ),
    )
    facts = MeasurementReconciliationFacts(
        qualified_sessions=len(batch.qualified_sessions),
        valid_outbound_clicks=denominator,
        affiliate_accepted_clicks=len(batch.affiliate_accepted_clicks),
        current_transactions=len(batch.transactions),
        new_acquisition_transactions=sum(
            row.acquisition_class is AcquisitionClass.NEW
            for row in batch.transactions
        ),
        gross_paid_transactions=sum(
            row.current_status is TransactionStatus.PAID
            for row in batch.transactions
        ),
        reversed_paid_transactions=len(reversed_ids),
        net_paid_transactions=sum(
            row.current_status is TransactionStatus.PAID
            and row.transaction_id_sha256 not in reversed_ids
            for row in batch.transactions
        ),
        settled_new_acquisition_amount=settled,
        gross_payout_amount=batch.payout_statement.gross_amount,
        net_payout_amount=batch.payout_statement.net_amount,
        confirmed_epc=confirmed_epc,
        net_payout_epc=net_payout_epc,
        exact_faults_passed=0,
    )
    return evidence, facts


def _validate_dossier_binding(
    dossier: BusinessDossier, report: MeasurementIntegrityReport
) -> None:
    operations = report.operations
    if (
        hashlib.sha256(
            dossier.provenance.property_domain.strip().lower().encode("utf-8")
        ).hexdigest()
        != report.property_domain_sha256
        or dossier.approved_affiliate_ids != report.partner_ids
        or dossier.provenance.demand_source_sha256
        != report.demand.source_sha256
        or dossier.provenance.cohort_source_sha256 != report.cohort.source_sha256
        or dossier.provenance.operations_source_sha256
        != operations.source_sha256
        or dossier.scenarios != report.demand.scenarios
        or dossier.cohort != report.cohort.cohort
        or dossier.expires_at.demand != report.demand.expires_at
        or dossier.expires_at.cohort != report.cohort.expires_at
        or dossier.expires_at.operations != operations.expires_at
        or dossier.human_hours_per_month != operations.human_hours()
        or dossier.automation_rate != operations.automation_rate()
        or dossier.major_misstatements != operations.major_misstatements
        or dossier.shadow_observation_days != operations.shadow_observation_days()
        or dossier.job_runs_total != operations.job_runs_total
        or dossier.job_runs_succeeded != operations.job_runs_succeeded
        or dossier.exceptions_total != operations.exceptions_total
        or dossier.rollback_test_status is not operations.rollback_test_status
    ):
        raise ValueError("dossier measurement fields do not match signed report")


def demand_batch_clusters(batch: StrictModel) -> tuple[Any, ...]:
    if type(batch) is not DemandIntegrityBatch:
        raise TypeError("demand batch type mismatch")
    return batch.summary.clusters


def cohort_batch_transactions(batch: StrictModel) -> tuple[Any, ...]:
    if type(batch) is not CohortIntegrityBatch:
        raise TypeError("cohort batch type mismatch")
    return batch.transactions


def operations_batch_days(batch: StrictModel) -> tuple[Any, ...]:
    if type(batch) is not OperationsIntegrityBatch:
        raise TypeError("operations batch type mismatch")
    return batch.summary.daily_summaries


def operations_batch_logical_runs(batch: StrictModel) -> tuple[Any, ...]:
    if type(batch) is not OperationsIntegrityBatch:
        raise TypeError("operations batch type mismatch")
    return batch.logical_job_runs


def measurement_batch_captured_at(batch: StrictModel) -> datetime:
    if type(batch) is DemandIntegrityBatch:
        return batch.summary.captured_at
    if type(batch) is CohortIntegrityBatch:
        return batch.captured_at
    if type(batch) is OperationsIntegrityBatch:
        return batch.summary.captured_at
    raise TypeError("unsupported measurement batch type")


def measurement_batch_retrieved_at(batch: StrictModel) -> datetime:
    if type(batch) is DemandIntegrityBatch:
        return batch.summary.receipt.retrieved_at
    if type(batch) is CohortIntegrityBatch:
        return batch.captured_at
    if type(batch) is OperationsIntegrityBatch:
        return batch.summary.receipt.retrieved_at
    raise TypeError("unsupported measurement batch type")


def measurement_batch_source_receipt_sha256(batch: StrictModel) -> str:
    if type(batch) is DemandIntegrityBatch:
        return batch.summary.receipt.source_receipt_sha256
    if type(batch) is CohortIntegrityBatch:
        return batch.source_receipt_sha256
    if type(batch) is OperationsIntegrityBatch:
        return batch.summary.receipt.source_receipt_sha256
    raise TypeError("unsupported measurement batch type")


def _expected_coverage(
    batch: StrictModel,
) -> dict[CoveragePartitionKind, tuple[str, ...]]:
    if type(batch) is DemandIntegrityBatch:
        return {
            CoveragePartitionKind.DEMAND_CLUSTER: tuple(
                item.cluster_receipt_sha256 for item in batch.summary.clusters
            )
        }
    if type(batch) is CohortIntegrityBatch:
        return {
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
    if type(batch) is OperationsIntegrityBatch:
        return {
            CoveragePartitionKind.OPERATION_DAY: tuple(
                item.summary_id_sha256 for item in batch.summary.daily_summaries
            ),
            CoveragePartitionKind.LOGICAL_JOB_RUN: tuple(
                item.run_key_sha256 for item in batch.logical_job_runs
            ),
            CoveragePartitionKind.FAULT_EXERCISE: tuple(
                item.run_sha256 for item in batch.fault_exercises
            ),
        }
    raise TypeError("unsupported measurement batch type")


def _coverage_matches_batch(
    coverage: ProducerCoverage,
    batch: StrictModel,
    *,
    expected_coverage: dict[CoveragePartitionKind, tuple[str, ...]] | None = None,
) -> bool:
    expected = expected_coverage or _expected_coverage(batch)
    observed = {item.kind: item for item in coverage.partitions}
    if set(observed) != set(expected):
        return False
    return all(
        observed[kind].output_records == len(identities)
        and observed[kind].identity_set_sha256
        == _identity_set_sha256(identities)
        for kind, identities in expected.items()
    )


def _identity_set_sha256(values: Any) -> str:
    normalized = tuple(sorted(values))
    if len(normalized) != len(set(normalized)):
        raise ValueError("identity set members must be distinct")
    return _canonical_sha256(normalized)


def _build_signed(
    model_type: type[StrictModel],
    values: dict[str, Any],
    signing_key: Ed25519PrivateKey,
) -> Any:
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise TypeError("signing_key must be Ed25519PrivateKey")
    provisional = model_type.model_construct(
        **values,
        payload_sha256="0" * 64,
        signature_base64url="A" * 86,
    )
    values = dict(values)
    values["payload_sha256"] = _signed_payload_hash(provisional)
    with_payload = model_type.model_construct(
        **values, signature_base64url="A" * 86
    )
    values["signature_base64url"] = _encode_base64url(
        signing_key.sign(_signature_message(with_payload))
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
    signing_key: Ed25519PrivateKey,
    verification_key: Ed25519VerificationKey,
) -> bool:
    if not isinstance(signing_key, Ed25519PrivateKey):
        return False
    candidate = create_verification_key(
        signing_key.public_key(),
        issuer=verification_key.issuer,
        role=verification_key.role,
    )
    return candidate == verification_key


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
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid canonical base64url value") from exc
    if len(decoded) != expected_length or _encode_base64url(decoded) != value:
        raise ValueError("invalid canonical base64url length or encoding")
    return decoded


def _unique_map(
    values: tuple[Any, ...], attribute: str, label: str
) -> dict[str, Any]:
    result = {getattr(item, attribute): item for item in values}
    if len(result) != len(values):
        raise ValueError(f"{label} must be distinct")
    return result


def _require_unique_attr(
    values: tuple[Any, ...], attribute: str, label: str
) -> None:
    if len({getattr(item, attribute) for item in values}) != len(values):
        raise ValueError(f"{label} must be distinct")


def _inside(value: datetime, start: datetime, end: datetime) -> None:
    if not start <= value < end:
        raise ValueError("funnel event is outside the cohort window")


def _current_batch(captured_at: datetime, expires_at: datetime, at: datetime) -> None:
    if captured_at > at or expires_at <= at:
        raise MeasurementInputError("measurement batch is future or expired")


def _aware(value: datetime, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value


__all__ = [
    "AcquisitionClass",
    "AffiliateAcceptedClick",
    "CohortIntegrityBatch",
    "CoveragePartition",
    "CoveragePartitionKind",
    "CurrentTransaction",
    "DemandIntegrityBatch",
    "FaultExercise",
    "FaultId",
    "FaultRequirement",
    "MeasurementBundleIndex",
    "MeasurementBoundDossier",
    "MeasurementAuthorityPins",
    "MeasurementDataset",
    "MeasurementInputError",
    "MeasurementIntegrityReport",
    "MeasurementIntegrityRuntime",
    "MeasurementIntegrityVerifier",
    "MeasurementPolicy",
    "MeasurementReconciliationFacts",
    "MeasurementRulePins",
    "MeasurementRunDefinition",
    "MeasurementTrustStore",
    "LogicalJobRun",
    "OperationsIntegrityBatch",
    "PayoutAdjustment",
    "PayoutAdjustmentKind",
    "PayoutRow",
    "PayoutStatement",
    "ProducerAttestation",
    "ProducerCoverage",
    "QualifiedSession",
    "REQUIRED_FAULT_IDS",
    "RunFreezeDecision",
    "SignedMeasurementRunPlan",
    "TransactionStatus",
    "TransactionStatusEvent",
    "ValidOutboundClick",
    "assemble_measurement_bound_dossier",
    "hash_measurement_policy",
    "hash_measurement_trust_store",
    "hash_signed_artifact",
    "sign_measurement_bundle_index",
    "sign_measurement_run_plan",
    "sign_producer_attestation",
    "verify_measurement_integrity_report",
    "verify_measurement_bound_dossier",
]
