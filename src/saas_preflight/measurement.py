"""Offline Phase 3 safe-summary aggregation.

The contracts in this module start at the L2 boundary described in the Phase 3
runbook.  Raw exports, URLs, credentials, keyword text, customer identifiers,
and free-form logs are deliberately outside the schema.  Builders normalize
row order, reject conflicting/duplicate identities, and emit the existing L3
readiness evidence contracts.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from .economics import RollbackTestStatus, project_scenarios
from .models import CurrencyCode, Sha256, Slug, StrictModel
from .preflight import CohortInput, CommissionInput, DemandInput, ScenarioInputs
from .readiness_builder import CohortEvidence, DemandEvidence, OperationsEvidence


_MONTH_RE = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
_TOKYO = ZoneInfo("Asia/Tokyo")


class EvidenceReceipt(StrictModel):
    """Shared hash-only provenance for an already-sanitized L2 summary."""

    authority: Slug
    authority_record_sha256: Sha256
    source_receipt_sha256: Sha256
    retrieved_at: datetime

    @field_validator("retrieved_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "retrieved_at")


class ScenarioRates(StrictModel):
    organic_visibility: Decimal = Field(ge=0, le=1)
    rank_ctr: Decimal = Field(ge=0, le=1)
    qualified_rate: Decimal = Field(ge=0, le=1)
    outbound_click_rate: Decimal = Field(ge=0, le=1)


class DemandClusterSummary(StrictModel):
    cluster_id: Slug
    cluster_receipt_sha256: Sha256
    deduplicated_monthly_volume: Decimal = Field(ge=0)


class DemandSummaryBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    measurement_version: Slug
    receipt: EvidenceReceipt
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    period_unit: Literal["monthly"] = "monthly"
    source_month: str
    source_timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    deduplication_sha256: Sha256
    volume_is_deduplicated: Literal[True]
    captured_at: datetime
    expires_at: datetime
    clusters: tuple[DemandClusterSummary, ...] = Field(min_length=1)
    bear: ScenarioRates
    base: ScenarioRates
    bull: ScenarioRates

    @field_validator("source_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        if _MONTH_RE.fullmatch(value) is None:
            raise ValueError("source_month must use YYYY-MM")
        return value

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "demand timestamp")

    @field_validator("clusters")
    @classmethod
    def canonicalize_clusters(
        cls, values: tuple[DemandClusterSummary, ...]
    ) -> tuple[DemandClusterSummary, ...]:
        _require_distinct(
            [item.cluster_id for item in values], "demand cluster IDs"
        )
        _require_distinct(
            [item.cluster_receipt_sha256 for item in values],
            "demand cluster receipts",
        )
        return tuple(sorted(values, key=lambda item: item.cluster_id))

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        _positive_window(self.captured_at, self.expires_at)
        if self.receipt.retrieved_at < self.captured_at:
            raise ValueError("retrieved_at cannot predate captured_at")
        captured_month = self.captured_at.astimezone(_TOKYO).strftime("%Y-%m")
        if self.source_month > captured_month:
            raise ValueError("source_month cannot be later than captured_at")
        return self


class PartnerCohortSummary(StrictModel):
    summary_id_sha256: Sha256
    partner_id: Slug
    valid_clicks: int = Field(ge=0)
    commissions: CommissionInput


class CohortSummaryBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    measurement_version: Slug
    receipt: EvidenceReceipt
    property_record_sha256: Sha256
    territory: Literal["JP"] = "JP"
    currency: CurrencyCode
    cohort_id: Slug
    cohort_started_at: datetime
    cohort_ended_at: datetime
    captured_at: datetime
    expires_at: datetime
    click_deduplication_sha256: Sha256
    status_mapping_sha256: Sha256
    summaries: tuple[PartnerCohortSummary, ...] = Field(min_length=1)

    @field_validator(
        "cohort_started_at", "cohort_ended_at", "captured_at", "expires_at"
    )
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "cohort timestamp")

    @field_validator("summaries")
    @classmethod
    def canonicalize_summaries(
        cls, values: tuple[PartnerCohortSummary, ...]
    ) -> tuple[PartnerCohortSummary, ...]:
        _require_distinct(
            [item.summary_id_sha256 for item in values],
            "cohort summary IDs",
        )
        _require_distinct(
            [item.partner_id for item in values], "cohort partner IDs"
        )
        return tuple(sorted(values, key=lambda item: item.partner_id))

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.cohort_ended_at <= self.cohort_started_at:
            raise ValueError("cohort_ended_at must be later than cohort_started_at")
        if self.captured_at < self.cohort_ended_at:
            raise ValueError("captured_at cannot predate cohort_ended_at")
        _positive_window(self.captured_at, self.expires_at)
        if self.receipt.retrieved_at < self.captured_at:
            raise ValueError("retrieved_at cannot predate captured_at")
        return self


class DailyOperationsSummary(StrictModel):
    summary_id_sha256: Sha256
    local_date: date
    human_minutes: int = Field(ge=0)
    routine_tasks_total: int = Field(ge=0)
    routine_tasks_automated: int = Field(ge=0)
    job_runs_total: int = Field(ge=0)
    job_runs_succeeded: int = Field(ge=0)
    exceptions_total: int = Field(ge=0)
    major_misstatements: int = Field(ge=0)
    rollback_tests_total: int = Field(ge=0)
    rollback_tests_passed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.routine_tasks_automated > self.routine_tasks_total:
            raise ValueError("routine_tasks_automated cannot exceed total")
        if self.job_runs_succeeded > self.job_runs_total:
            raise ValueError("job_runs_succeeded cannot exceed total")
        if self.rollback_tests_passed > self.rollback_tests_total:
            raise ValueError("rollback_tests_passed cannot exceed total")
        return self


class OperationsSummaryBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    measurement_version: Slug
    receipt: EvidenceReceipt
    property_record_sha256: Sha256
    source_timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    observation_started_at: datetime
    captured_at: datetime
    expires_at: datetime
    routine_inventory_sha256: Sha256
    job_schedule_sha256: Sha256
    job_status_mapping_sha256: Sha256
    exception_deduplication_sha256: Sha256
    qa_policy_sha256: Sha256
    rollback_catalog_sha256: Sha256
    daily_summaries: tuple[DailyOperationsSummary, ...] = ()

    @field_validator("observation_started_at", "captured_at", "expires_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "operations timestamp")

    @field_validator("daily_summaries")
    @classmethod
    def canonicalize_days(
        cls, values: tuple[DailyOperationsSummary, ...]
    ) -> tuple[DailyOperationsSummary, ...]:
        _require_distinct(
            [item.summary_id_sha256 for item in values],
            "daily summary IDs",
        )
        _require_distinct(
            [item.local_date.isoformat() for item in values],
            "daily summary dates",
        )
        return tuple(sorted(values, key=lambda item: item.local_date))

    @model_validator(mode="after")
    def validate_window_and_dates(self) -> Self:
        if self.observation_started_at > self.captured_at:
            raise ValueError("observation_started_at cannot be after captured_at")
        _positive_window(self.captured_at, self.expires_at)
        if self.receipt.retrieved_at < self.captured_at:
            raise ValueError("retrieved_at cannot predate captured_at")

        start_local = self.observation_started_at.astimezone(_TOKYO)
        if any(
            (start_local.hour, start_local.minute, start_local.second, start_local.microsecond)
        ):
            raise ValueError("observation_started_at must be midnight Asia/Tokyo")
        complete_days = (self.captured_at - self.observation_started_at).days
        expected = {
            start_local.date() + timedelta(days=offset)
            for offset in range(complete_days)
        }
        observed = {item.local_date for item in self.daily_summaries}
        if observed != expected:
            raise ValueError(
                "daily_summaries must cover every complete observation day exactly once"
            )
        return self


def build_demand_evidence(
    batch: DemandSummaryBatch, *, at: datetime | None = None
) -> DemandEvidence:
    instant = at or datetime.now(timezone.utc)
    _current(batch.captured_at, batch.expires_at, instant, "demand")
    _retrieval_is_current(batch.receipt.retrieved_at, instant, "demand")
    volume = sum(
        (item.deduplicated_monthly_volume for item in batch.clusters),
        start=Decimal(0),
    )

    def scenario(rates: ScenarioRates) -> DemandInput:
        return DemandInput(
            deduplicated_search_volume=volume,
            organic_visibility=rates.organic_visibility,
            rank_ctr=rates.rank_ctr,
            qualified_rate=rates.qualified_rate,
            outbound_click_rate=rates.outbound_click_rate,
            volume_is_deduplicated=True,
        )

    scenarios = ScenarioInputs(
        bear=scenario(batch.bear),
        base=scenario(batch.base),
        bull=scenario(batch.bull),
    )
    project_scenarios(scenarios.to_domain(), None)
    digest = _canonical_model_sha256(batch)
    return DemandEvidence(
        evidence_version=f"sha256:{digest}",
        source_sha256=digest,
        captured_at=batch.captured_at,
        expires_at=batch.expires_at,
        scenarios=scenarios,
    )


def build_cohort_evidence(
    batch: CohortSummaryBatch, *, at: datetime | None = None
) -> CohortEvidence:
    instant = at or datetime.now(timezone.utc)
    _current(batch.captured_at, batch.expires_at, instant, "cohort")
    _retrieval_is_current(batch.receipt.retrieved_at, instant, "cohort")
    valid_clicks = sum(item.valid_clicks for item in batch.summaries)
    commissions = CommissionInput(
        pending=sum(
            (item.commissions.pending for item in batch.summaries), Decimal(0)
        ),
        rejected=sum(
            (item.commissions.rejected for item in batch.summaries), Decimal(0)
        ),
        confirmed=sum(
            (item.commissions.confirmed for item in batch.summaries), Decimal(0)
        ),
        paid=sum((item.commissions.paid for item in batch.summaries), Decimal(0)),
    )
    digest = _canonical_model_sha256(batch)
    return CohortEvidence(
        evidence_version=f"sha256:{digest}",
        source_sha256=digest,
        status_mapping_sha256=batch.status_mapping_sha256,
        captured_at=batch.captured_at,
        expires_at=batch.expires_at,
        cohort=CohortInput(
            currency=batch.currency,
            valid_clicks=valid_clicks,
            age_days=(batch.captured_at - batch.cohort_started_at).days,
            commissions=commissions,
        ),
    )


def build_operations_evidence(
    batch: OperationsSummaryBatch, *, at: datetime | None = None
) -> OperationsEvidence:
    instant = at or datetime.now(timezone.utc)
    _current(batch.captured_at, batch.expires_at, instant, "operations")
    _retrieval_is_current(batch.receipt.retrieved_at, instant, "operations")
    rows = batch.daily_summaries
    rollback_total = sum(item.rollback_tests_total for item in rows)
    rollback_passed = sum(item.rollback_tests_passed for item in rows)
    if rollback_total == 0:
        rollback_status = RollbackTestStatus.NOT_RUN
    elif rollback_passed == rollback_total:
        rollback_status = RollbackTestStatus.PASSED
    else:
        rollback_status = RollbackTestStatus.FAILED
    digest = _canonical_model_sha256(batch)
    return OperationsEvidence(
        evidence_version=f"sha256:{digest}",
        source_sha256=digest,
        observation_started_at=batch.observation_started_at,
        captured_at=batch.captured_at,
        expires_at=batch.expires_at,
        human_minutes_per_month=sum(item.human_minutes for item in rows),
        routine_tasks_total=sum(item.routine_tasks_total for item in rows),
        routine_tasks_automated=sum(
            item.routine_tasks_automated for item in rows
        ),
        major_misstatements=sum(item.major_misstatements for item in rows),
        job_runs_total=sum(item.job_runs_total for item in rows),
        job_runs_succeeded=sum(item.job_runs_succeeded for item in rows),
        exceptions_total=sum(item.exceptions_total for item in rows),
        rollback_test_status=rollback_status,
    )


def _canonical_model_sha256(model: StrictModel) -> str:
    payload = model.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_distinct(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be distinct")


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _positive_window(captured_at: datetime, expires_at: datetime) -> None:
    if expires_at <= captured_at:
        raise ValueError("expires_at must be later than captured_at")


def _current(
    captured_at: datetime, expires_at: datetime, at: datetime, label: str
) -> None:
    _aware(at, "aggregation time")
    if captured_at > at:
        raise ValueError(f"{label} summary was captured in the future")
    if expires_at <= at:
        raise ValueError(f"{label} summary is expired")


def _retrieval_is_current(retrieved_at: datetime, at: datetime, label: str) -> None:
    if retrieved_at > at:
        raise ValueError(f"{label} summary was retrieved in the future")


__all__ = [
    "CohortSummaryBatch",
    "DailyOperationsSummary",
    "DemandClusterSummary",
    "DemandSummaryBatch",
    "EvidenceReceipt",
    "OperationsSummaryBatch",
    "PartnerCohortSummary",
    "ScenarioRates",
    "build_cohort_evidence",
    "build_demand_evidence",
    "build_operations_evidence",
]
