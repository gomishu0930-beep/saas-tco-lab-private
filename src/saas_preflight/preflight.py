"""Versioned dossier adapter for the deterministic business GO/STOP model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .economics import (
    AffiliateCohort,
    CommissionBuckets,
    Decision,
    DemandAssumptions,
    GateCheck,
    GateStatus,
    GoStopEvaluation,
    GoStopInputs,
    RollbackTestStatus,
    ScenarioSet,
    evaluate_go_stop,
)
from .models import CurrencyCode, Sha256, StrictModel


class DemandInput(StrictModel):
    deduplicated_search_volume: Decimal = Field(ge=0)
    organic_visibility: Decimal = Field(ge=0, le=1)
    rank_ctr: Decimal = Field(ge=0, le=1)
    qualified_rate: Decimal = Field(ge=0, le=1)
    outbound_click_rate: Decimal = Field(ge=0, le=1)
    volume_is_deduplicated: bool

    def to_domain(self) -> DemandAssumptions:
        return DemandAssumptions(**self.model_dump())


class ScenarioInputs(StrictModel):
    bear: DemandInput
    base: DemandInput
    bull: DemandInput

    def to_domain(self) -> ScenarioSet:
        return ScenarioSet(
            bear=self.bear.to_domain(),
            base=self.base.to_domain(),
            bull=self.bull.to_domain(),
        )


class CommissionInput(StrictModel):
    pending: Decimal = Field(ge=0)
    rejected: Decimal = Field(ge=0)
    confirmed: Decimal = Field(ge=0)
    paid: Decimal = Field(ge=0)


class CohortInput(StrictModel):
    currency: CurrencyCode
    valid_clicks: int = Field(ge=0)
    age_days: int = Field(ge=0)
    commissions: CommissionInput

    def to_domain(self) -> AffiliateCohort:
        return AffiliateCohort(
            currency=self.currency,
            valid_clicks=self.valid_clicks,
            age_days=self.age_days,
            commissions=CommissionBuckets(**self.commissions.model_dump()),
        )


class ArtifactExpiries(StrictModel):
    rights: datetime
    affiliate: datetime
    demand: datetime
    operations: datetime
    cohort: datetime

    @field_validator("rights", "affiliate", "demand", "operations", "cohort")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact expiry must be timezone-aware")
        return value

    def items(self) -> tuple[tuple[str, datetime], ...]:
        return (
            ("rights", self.rights),
            ("affiliate", self.affiliate),
            ("demand", self.demand),
            ("operations", self.operations),
            ("cohort", self.cohort),
        )


class DossierProvenance(StrictModel):
    """Hash-only receipts for the inputs used by the production assembler."""

    builder_version: Literal["2.0"] = "2.0"
    property_domain: str = Field(min_length=1, max_length=253)
    rights_bundle_sha256: Sha256
    affiliate_bundle_sha256: Sha256
    demand_source_sha256: Sha256
    cohort_source_sha256: Sha256
    operations_source_sha256: Sha256
    assembled_at: datetime

    @field_validator("assembled_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("assembled_at must be timezone-aware")
        return value


class BusinessDossier(StrictModel):
    """All evidence-backed inputs needed for one reproducible decision."""

    schema_version: Literal["3.0"] = "3.0"
    evidence_version: str = Field(min_length=1, max_length=120)
    provenance: DossierProvenance
    as_of: datetime
    expires_at: ArtifactExpiries
    approved_affiliate_ids: tuple[str, ...]
    rights_approved: bool
    scenarios: ScenarioInputs
    cohort: CohortInput
    human_hours_per_month: Decimal = Field(ge=0)
    automation_rate: Decimal = Field(ge=0, le=1)
    major_misstatements: int = Field(ge=0)
    shadow_observation_days: int = Field(ge=0)
    job_runs_total: int = Field(ge=0)
    job_runs_succeeded: int = Field(ge=0)
    exceptions_total: int = Field(ge=0)
    rollback_test_status: RollbackTestStatus

    @field_validator("as_of")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value

    @field_validator("approved_affiliate_ids")
    @classmethod
    def normalize_partner_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("approved affiliate IDs must be non-empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("approved affiliate IDs must be distinct")
        return normalized

    @model_validator(mode="after")
    def require_expiry_after_observation(self) -> Self:
        if self.as_of != self.provenance.assembled_at:
            raise ValueError("as_of must equal provenance.assembled_at")
        invalid = [name for name, expiry in self.expires_at.items() if expiry <= self.as_of]
        if invalid:
            raise ValueError(
                "artifact expiry must be later than as_of: " + ", ".join(invalid)
            )
        if self.job_runs_succeeded > self.job_runs_total:
            raise ValueError("job_runs_succeeded cannot exceed job_runs_total")
        return self

    def to_domain(self) -> GoStopInputs:
        return GoStopInputs(
            approved_affiliate_ids=self.approved_affiliate_ids,
            rights_approved=self.rights_approved,
            scenarios=self.scenarios.to_domain(),
            cohort=self.cohort.to_domain(),
            human_hours_per_month=self.human_hours_per_month,
            automation_rate=self.automation_rate,
            major_misstatements=self.major_misstatements,
            shadow_observation_days=self.shadow_observation_days,
            job_runs_total=self.job_runs_total,
            job_runs_succeeded=self.job_runs_succeeded,
            exceptions_total=self.exceptions_total,
            rollback_test_status=self.rollback_test_status,
        )


@dataclass(frozen=True, slots=True)
class BusinessDossierEvaluation:
    decision: Decision
    evaluated_at: datetime
    evidence_version: str
    freshness_checks: tuple[GateCheck, ...]
    economics: GoStopEvaluation | None


def evaluate_business_dossier(
    dossier: BusinessDossier, *, at: datetime | None = None
) -> BusinessDossierEvaluation:
    """Fail closed before economics when any input artifact is stale/future."""

    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("evaluation time must be timezone-aware")

    freshness: list[GateCheck] = []
    if dossier.as_of > instant:
        freshness.append(
            GateCheck(
                name="artifact_as_of",
                status=GateStatus.FAIL,
                observed=dossier.as_of.isoformat(),
                requirement=f"<= {instant.isoformat()}",
            )
        )
    else:
        freshness.append(
            GateCheck(
                name="artifact_as_of",
                status=GateStatus.PASS,
                observed=dossier.as_of.isoformat(),
                requirement=f"<= {instant.isoformat()}",
            )
        )
    for name, expiry in dossier.expires_at.items():
        freshness.append(
            GateCheck(
                name=f"{name}_freshness",
                status=GateStatus.PASS if instant < expiry else GateStatus.FAIL,
                observed=expiry.isoformat(),
                requirement=f"> {instant.isoformat()}",
            )
        )

    if any(check.status is GateStatus.FAIL for check in freshness):
        return BusinessDossierEvaluation(
            decision=Decision.STOP,
            evaluated_at=instant,
            evidence_version=dossier.evidence_version,
            freshness_checks=tuple(freshness),
            economics=None,
        )

    economics = evaluate_go_stop(dossier.to_domain())
    return BusinessDossierEvaluation(
        decision=economics.decision,
        evaluated_at=instant,
        evidence_version=dossier.evidence_version,
        freshness_checks=tuple(freshness),
        economics=economics,
    )


__all__ = [
    "ArtifactExpiries",
    "BusinessDossier",
    "BusinessDossierEvaluation",
    "CohortInput",
    "CommissionInput",
    "DemandInput",
    "DossierProvenance",
    "ScenarioInputs",
    "evaluate_business_dossier",
]
