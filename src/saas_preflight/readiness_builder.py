"""Provenance-backed assembly of the business readiness dossier.

This module is intentionally offline.  It accepts already-reviewed plan,
affiliate, demand, cohort, and operations records and derives every production
GO/STOP input.  It never accepts a caller-supplied ``rights_approved`` flag,
affiliate count, automation rate, or human-hours value.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from .economics import RollbackTestStatus
from .models import PolicyAction, Sha256, StrictModel, VendorPlan
from .preflight import (
    ArtifactExpiries,
    BusinessDossier,
    CohortInput,
    DossierProvenance,
    ScenarioInputs,
)


_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_REQUIRED_RIGHTS = (
    PolicyAction.DERIVE,
    PolicyAction.PUBLISH,
    PolicyAction.RETAIN_HISTORY,
)


class AffiliateReviewDecision(str, Enum):
    APPROVED = "approved"
    PROHIBITED = "prohibited"
    UNREVIEWED = "unreviewed"


class AffiliateProgramDecision(StrictModel):
    """Hash-only affiliate review result for one vendor and web property."""

    schema_version: Literal["1.0"] = "1.0"
    partner_id: str = Field(min_length=1, max_length=120)
    vendor_slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    property_domain: str = Field(min_length=1, max_length=253)
    territory: str = Field(min_length=2, max_length=32)
    decision: AffiliateReviewDecision
    reviewed_at: datetime
    review_due_at: datetime
    reviewed_by: str = Field(min_length=1, max_length=120)
    decision_record_sha256: Sha256
    program_id: str | None = Field(default=None, min_length=1, max_length=160)
    destination_sha256: Sha256 | None = None
    disclosure_sha256: Sha256 | None = None

    @field_validator("property_domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return _normalize_domain(value)

    @field_validator("partner_id", "territory", "reviewed_by", "program_id")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("affiliate decision text must be non-empty")
        return normalized

    @field_validator("reviewed_at", "review_due_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        _require_aware(value, "affiliate review timestamp")
        return value

    @model_validator(mode="after")
    def validate_decision_payload(self) -> Self:
        if self.review_due_at <= self.reviewed_at:
            raise ValueError("review_due_at must be later than reviewed_at")
        approval_fields = (
            self.program_id,
            self.destination_sha256,
            self.disclosure_sha256,
        )
        if self.decision is AffiliateReviewDecision.APPROVED:
            if any(value is None for value in approval_fields):
                raise ValueError(
                    "approved affiliate decision requires program and hash-only CTA records"
                )
        elif any(value is not None for value in approval_fields):
            raise ValueError(
                "non-approved affiliate decision cannot carry program or CTA data"
            )
        return self


class AffiliateDecisionBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decisions: tuple[AffiliateProgramDecision, ...] = Field(min_length=1)


class DemandEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_version: str = Field(min_length=1, max_length=120)
    source_sha256: Sha256
    captured_at: datetime
    expires_at: datetime
    scenarios: ScenarioInputs

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        _require_aware(value, "demand evidence timestamp")
        return value

    @model_validator(mode="after")
    def require_positive_window(self) -> Self:
        _require_positive_window(self.captured_at, self.expires_at)
        return self


class CohortEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_version: str = Field(min_length=1, max_length=120)
    source_sha256: Sha256
    status_mapping_sha256: Sha256
    captured_at: datetime
    expires_at: datetime
    cohort: CohortInput

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        _require_aware(value, "cohort evidence timestamp")
        return value

    @model_validator(mode="after")
    def require_positive_window(self) -> Self:
        _require_positive_window(self.captured_at, self.expires_at)
        return self


class OperationsEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_version: str = Field(min_length=1, max_length=120)
    source_sha256: Sha256
    observation_started_at: datetime
    captured_at: datetime
    expires_at: datetime
    human_minutes_per_month: int = Field(ge=0)
    routine_tasks_total: int = Field(ge=0)
    routine_tasks_automated: int = Field(ge=0)
    major_misstatements: int = Field(ge=0)
    job_runs_total: int = Field(ge=0)
    job_runs_succeeded: int = Field(ge=0)
    exceptions_total: int = Field(ge=0)
    rollback_test_status: RollbackTestStatus

    @field_validator("observation_started_at", "captured_at", "expires_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        _require_aware(value, "operations evidence timestamp")
        return value

    @model_validator(mode="after")
    def validate_operations(self) -> Self:
        _require_positive_window(self.captured_at, self.expires_at)
        if self.observation_started_at > self.captured_at:
            raise ValueError("observation_started_at cannot be after captured_at")
        if self.routine_tasks_automated > self.routine_tasks_total:
            raise ValueError("automated routine tasks cannot exceed total routine tasks")
        if self.job_runs_succeeded > self.job_runs_total:
            raise ValueError("job_runs_succeeded cannot exceed job_runs_total")
        return self

    def human_hours(self) -> Decimal:
        return Decimal(self.human_minutes_per_month) / Decimal(60)

    def automation_rate(self) -> Decimal:
        if self.routine_tasks_total == 0:
            return Decimal(0)
        return Decimal(self.routine_tasks_automated) / Decimal(
            self.routine_tasks_total
        )

    def shadow_observation_days(self) -> int:
        elapsed = self.captured_at - self.observation_started_at
        return elapsed.days


@dataclass(frozen=True, slots=True)
class RightsBundle:
    approved: bool
    eligible_vendor_slugs: tuple[str, ...]
    denied_fields: tuple[str, ...]
    bundle_sha256: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AffiliateBundle:
    approved_partner_ids: tuple[str, ...]
    approved_vendor_slugs: tuple[str, ...]
    bundle_sha256: str
    expires_at: datetime


def build_rights_bundle(
    plans: tuple[VendorPlan, ...] | list[VendorPlan], *, at: datetime | None = None
) -> RightsBundle:
    """Derive current publish/derive/history rights from every evidence pointer."""

    instant = at or datetime.now(timezone.utc)
    _require_aware(instant, "rights bundle time")
    if not plans:
        raise ValueError("at least one VendorPlan is required")

    snapshot_ids = [str(plan.snapshot_id) for plan in plans]
    if len(snapshot_ids) != len(set(snapshot_ids)):
        raise ValueError("VendorPlan snapshot IDs must be distinct")

    denied: set[str] = set()
    expiries: list[datetime] = []
    vendor_allowed: dict[str, bool] = {}
    canonical_plans: list[dict[str, Any]] = []
    for plan in plans:
        if plan.captured_at > instant:
            raise ValueError(f"plan {plan.snapshot_id} was captured in the future")
        vendor_allowed.setdefault(plan.vendor_slug, True)
        plan_denied = False
        canonical_plans.append(plan.model_dump(mode="json"))
        for evidence in plan.field_evidence:
            for pointer in evidence.pointers:
                policy = pointer.source_policy
                if policy.reviewed_at > instant or policy.review_due_at <= instant:
                    raise ValueError(
                        f"rights policy is not current: {plan.vendor_slug}."
                        f"{plan.plan_slug}.{evidence.field}"
                    )
                expiries.append(policy.review_due_at)
                if policy.retention_days is not None:
                    retention_expiry = plan.captured_at + timedelta(
                        days=policy.retention_days
                    )
                    if retention_expiry <= instant:
                        raise ValueError(
                            f"retention window has expired: {plan.vendor_slug}."
                            f"{plan.plan_slug}.{evidence.field}"
                        )
                    expiries.append(retention_expiry)
                for action in _REQUIRED_RIGHTS:
                    if not policy.permits(action, at=instant):
                        denied.add(
                            f"{plan.vendor_slug}.{plan.plan_slug}."
                            f"{evidence.field}:{action.value}"
                        )
                        plan_denied = True
        if plan_denied:
            vendor_allowed[plan.vendor_slug] = False

    if not expiries:
        raise ValueError("rights expiry cannot be determined")
    canonical_plans.sort(key=lambda item: str(item["snapshot_id"]))
    return RightsBundle(
        approved=not denied,
        eligible_vendor_slugs=tuple(
            sorted(vendor for vendor, allowed in vendor_allowed.items() if allowed)
        ),
        denied_fields=tuple(sorted(denied)),
        bundle_sha256=_canonical_sha256(
            {"required_actions": [action.value for action in _REQUIRED_RIGHTS], "plans": canonical_plans}
        ),
        expires_at=min(expiries),
    )


def build_affiliate_bundle(
    decisions: tuple[AffiliateProgramDecision, ...]
    | list[AffiliateProgramDecision],
    *,
    property_domain: str,
    at: datetime | None = None,
) -> AffiliateBundle:
    """Select current approvals without accepting URLs, secrets, or counts."""

    instant = at or datetime.now(timezone.utc)
    _require_aware(instant, "affiliate bundle time")
    expected_domain = _normalize_domain(property_domain)
    if not decisions:
        raise ValueError("at least one affiliate decision is required")

    partner_ids = [decision.partner_id for decision in decisions]
    if len(partner_ids) != len(set(partner_ids)):
        raise ValueError("affiliate partner IDs must be distinct")

    approved: list[AffiliateProgramDecision] = []
    expiries: list[datetime] = []
    for decision in decisions:
        if decision.property_domain != expected_domain:
            raise ValueError(
                f"affiliate decision property mismatch for {decision.partner_id}"
            )
        if decision.reviewed_at > instant or decision.review_due_at <= instant:
            raise ValueError(
                f"affiliate decision is not current: {decision.partner_id}"
            )
        expiries.append(decision.review_due_at)
        if decision.decision is AffiliateReviewDecision.APPROVED:
            approved.append(decision)

    approved_vendors = [decision.vendor_slug for decision in approved]
    if len(approved_vendors) != len(set(approved_vendors)):
        raise ValueError("only one current approved affiliate program per vendor is allowed")
    program_ids = [decision.program_id for decision in approved]
    if len(program_ids) != len(set(program_ids)):
        raise ValueError("approved affiliate program IDs must be distinct")

    canonical_decisions = sorted(
        (decision.model_dump(mode="json") for decision in decisions),
        key=lambda item: (str(item["vendor_slug"]), str(item["partner_id"])),
    )
    return AffiliateBundle(
        approved_partner_ids=tuple(sorted(decision.partner_id for decision in approved)),
        approved_vendor_slugs=tuple(sorted(approved_vendors)),
        bundle_sha256=_canonical_sha256(
            {"property_domain": expected_domain, "decisions": canonical_decisions}
        ),
        expires_at=min(expiries),
    )


def build_business_dossier(
    *,
    plans: tuple[VendorPlan, ...] | list[VendorPlan],
    affiliate_decisions: tuple[AffiliateProgramDecision, ...]
    | list[AffiliateProgramDecision],
    property_domain: str,
    demand: DemandEvidence,
    cohort: CohortEvidence,
    operations: OperationsEvidence,
    at: datetime | None = None,
) -> BusinessDossier:
    """Assemble a v3 dossier from current, versioned evidence only."""

    instant = at or datetime.now(timezone.utc)
    _require_aware(instant, "dossier assembly time")
    domain = _normalize_domain(property_domain)
    _require_current_evidence(demand.captured_at, demand.expires_at, instant, "demand")
    _require_current_evidence(cohort.captured_at, cohort.expires_at, instant, "cohort")
    _require_current_evidence(
        operations.captured_at, operations.expires_at, instant, "operations"
    )

    rights = build_rights_bundle(plans, at=instant)
    affiliate = build_affiliate_bundle(
        affiliate_decisions, property_domain=domain, at=instant
    )
    plan_vendors = {plan.vendor_slug for plan in plans}
    missing_plans = set(affiliate.approved_vendor_slugs) - plan_vendors
    if missing_plans:
        raise ValueError(
            "approved affiliate decisions lack VendorPlan evidence: "
            + ", ".join(sorted(missing_plans))
        )

    combined_evidence_sha = _canonical_sha256(
        {
            "rights": rights.bundle_sha256,
            "affiliate": affiliate.bundle_sha256,
            "demand": demand.model_dump(mode="json"),
            "cohort": cohort.model_dump(mode="json"),
            "operations": operations.model_dump(mode="json"),
        }
    )
    return BusinessDossier(
        evidence_version=f"sha256:{combined_evidence_sha}",
        provenance=DossierProvenance(
            property_domain=domain,
            rights_bundle_sha256=rights.bundle_sha256,
            affiliate_bundle_sha256=affiliate.bundle_sha256,
            demand_source_sha256=demand.source_sha256,
            cohort_source_sha256=cohort.source_sha256,
            operations_source_sha256=operations.source_sha256,
            assembled_at=instant,
        ),
        as_of=instant,
        expires_at=ArtifactExpiries(
            rights=rights.expires_at,
            affiliate=affiliate.expires_at,
            demand=demand.expires_at,
            operations=operations.expires_at,
            cohort=cohort.expires_at,
        ),
        approved_affiliate_ids=affiliate.approved_partner_ids,
        rights_approved=rights.approved,
        scenarios=demand.scenarios,
        cohort=cohort.cohort,
        human_hours_per_month=operations.human_hours(),
        automation_rate=operations.automation_rate(),
        major_misstatements=operations.major_misstatements,
        shadow_observation_days=operations.shadow_observation_days(),
        job_runs_total=operations.job_runs_total,
        job_runs_succeeded=operations.job_runs_succeeded,
        exceptions_total=operations.exceptions_total,
        rollback_test_status=operations.rollback_test_status,
    )


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_domain(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    if not _DOMAIN_PATTERN.fullmatch(normalized):
        raise ValueError("property_domain must be a normalized DNS domain")
    return normalized


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_positive_window(captured_at: datetime, expires_at: datetime) -> None:
    if expires_at <= captured_at:
        raise ValueError("expires_at must be later than captured_at")


def _require_current_evidence(
    captured_at: datetime, expires_at: datetime, at: datetime, label: str
) -> None:
    if captured_at > at:
        raise ValueError(f"{label} evidence was captured in the future")
    if expires_at <= at:
        raise ValueError(f"{label} evidence is expired")


__all__ = [
    "AffiliateBundle",
    "AffiliateDecisionBatch",
    "AffiliateProgramDecision",
    "AffiliateReviewDecision",
    "CohortEvidence",
    "DemandEvidence",
    "OperationsEvidence",
    "RightsBundle",
    "build_affiliate_bundle",
    "build_business_dossier",
    "build_rights_bundle",
]
