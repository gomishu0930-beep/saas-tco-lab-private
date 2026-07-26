from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from saas_preflight.economics import Decision, RollbackTestStatus
from saas_preflight.models import FieldEvidence, PolicyDecision
from saas_preflight.preflight import (
    CohortInput,
    CommissionInput,
    ScenarioInputs,
    evaluate_business_dossier,
)
from saas_preflight.readiness_builder import (
    AffiliateProgramDecision,
    AffiliateReviewDecision,
    CohortEvidence,
    DemandEvidence,
    OperationsEvidence,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)

from test_models import NOW, make_plan, make_policy
from test_preflight import _demand


def _affiliate(
    partner_id: str = "partner-a",
    vendor_slug: str = "example",
    **overrides: object,
) -> AffiliateProgramDecision:
    values: dict[str, object] = {
        "partner_id": partner_id,
        "vendor_slug": vendor_slug,
        "property_domain": "example.test",
        "territory": "JP",
        "decision": AffiliateReviewDecision.APPROVED,
        "reviewed_at": NOW - timedelta(days=1),
        "review_due_at": NOW + timedelta(days=30),
        "reviewed_by": "human-owner",
        "decision_record_sha256": "a" * 64,
        "program_id": f"program-{partner_id}",
        "destination_sha256": "b" * 64,
        "disclosure_sha256": "c" * 64,
    }
    values.update(overrides)
    return AffiliateProgramDecision(**values)


def _scenarios() -> ScenarioInputs:
    return ScenarioInputs(
        bear=_demand("1000000", "0.10"),
        base=_demand("1200000", "0.12"),
        bull=_demand("1500000", "0.15"),
    )


def _demand_evidence() -> DemandEvidence:
    return DemandEvidence(
        evidence_version="demand-v1",
        source_sha256="d" * 64,
        captured_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        scenarios=_scenarios(),
    )


def _cohort_evidence() -> CohortEvidence:
    return CohortEvidence(
        evidence_version="cohort-v1",
        source_sha256="e" * 64,
        status_mapping_sha256="f" * 64,
        captured_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        cohort=CohortInput(
            currency="JPY",
            valid_clicks=1000,
            age_days=30,
            commissions=CommissionInput(
                pending=Decimal(0),
                rejected=Decimal(0),
                confirmed=Decimal("30000"),
                paid=Decimal("30000"),
            ),
        ),
    )


def _operations_evidence(**overrides: object) -> OperationsEvidence:
    values: dict[str, object] = {
        "evidence_version": "operations-v1",
        "source_sha256": "1" * 64,
        "observation_started_at": NOW - timedelta(days=31),
        "captured_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(days=7),
        "human_minutes_per_month": 720,
        "routine_tasks_total": 100,
        "routine_tasks_automated": 80,
        "major_misstatements": 0,
        "job_runs_total": 100,
        "job_runs_succeeded": 99,
        "exceptions_total": 24,
        "rollback_test_status": RollbackTestStatus.PASSED,
    }
    values.update(overrides)
    return OperationsEvidence(**values)


def _plans() -> tuple:
    return tuple(
        make_plan(
            snapshot_id=uuid4(),
            vendor_slug=vendor,
            vendor_name=vendor.title(),
        )
        for vendor in ("vendor-a", "vendor-b", "vendor-c")
    )


def _affiliates() -> tuple[AffiliateProgramDecision, ...]:
    return tuple(
        _affiliate(partner_id=f"partner-{suffix}", vendor_slug=f"vendor-{suffix}")
        for suffix in ("a", "b", "c")
    )


def test_rights_bundle_is_derived_from_every_field_policy() -> None:
    bundle = build_rights_bundle([make_plan()], at=NOW)

    assert bundle.approved is True
    assert bundle.eligible_vendor_slugs == ("example",)
    assert len(bundle.bundle_sha256) == 64


def test_one_prohibited_publish_policy_makes_rights_fail() -> None:
    plan = make_plan()
    changed: list[FieldEvidence] = []
    for item in plan.field_evidence:
        if item.field == "base_price":
            pointer = item.pointers[0]
            policy = make_policy(
                field=item.field,
                publish=PolicyDecision.PROHIBITED,
            )
            item = item.model_copy(
                update={
                    "pointers": (
                        pointer.model_copy(update={"source_policy": policy}),
                    )
                }
            )
        changed.append(item)
    denied_plan = plan.model_copy(update={"field_evidence": tuple(changed)})

    bundle = build_rights_bundle([denied_plan], at=NOW)
    assert bundle.approved is False
    assert bundle.eligible_vendor_slugs == ()
    assert "example.basic.base_price:publish" in bundle.denied_fields


def test_affiliate_duplicates_cannot_inflate_partner_count() -> None:
    duplicate = _affiliate()
    with pytest.raises(ValueError, match="partner IDs must be distinct"):
        build_affiliate_bundle(
            [duplicate, duplicate], property_domain="example.test", at=NOW
        )


def test_two_approved_programs_for_one_vendor_are_rejected() -> None:
    with pytest.raises(ValueError, match="one current approved"):
        build_affiliate_bundle(
            [_affiliate("partner-a"), _affiliate("partner-b")],
            property_domain="example.test",
            at=NOW,
        )


def test_nonapproved_decision_cannot_smuggle_cta_data() -> None:
    with pytest.raises(ValidationError, match="cannot carry program or CTA data"):
        _affiliate(decision=AffiliateReviewDecision.UNREVIEWED)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _affiliate(affiliate_url="https://example.test/secret")


def test_expired_rights_and_evidence_are_rejected() -> None:
    expired_plan = make_plan(captured_at=NOW - timedelta(days=400))
    with pytest.raises(ValueError, match="retention window has expired"):
        build_rights_bundle([expired_plan], at=NOW)

    with pytest.raises(ValueError, match="demand evidence is expired"):
        build_business_dossier(
            plans=_plans(),
            affiliate_decisions=_affiliates(),
            property_domain="example.test",
            demand=_demand_evidence().model_copy(
                update={"expires_at": NOW}
            ),
            cohort=_cohort_evidence(),
            operations=_operations_evidence(),
            at=NOW,
        )


def test_zero_routine_denominator_derives_zero_not_a_false_go() -> None:
    operations = _operations_evidence(
        routine_tasks_total=0, routine_tasks_automated=0
    )
    dossier = build_business_dossier(
        plans=_plans(),
        affiliate_decisions=_affiliates(),
        property_domain="example.test",
        demand=_demand_evidence(),
        cohort=_cohort_evidence(),
        operations=operations,
        at=NOW,
    )

    assert dossier.automation_rate == Decimal(0)
    assert evaluate_business_dossier(dossier, at=NOW).decision is Decision.STOP


def test_provenance_assembler_reaches_go_with_complete_synthetic_evidence() -> None:
    dossier = build_business_dossier(
        plans=_plans(),
        affiliate_decisions=_affiliates(),
        property_domain="Example.Test.",
        demand=_demand_evidence(),
        cohort=_cohort_evidence(),
        operations=_operations_evidence(),
        at=NOW,
    )

    assert dossier.schema_version == "3.0"
    assert dossier.provenance.property_domain == "example.test"
    assert dossier.rights_approved is True
    assert dossier.approved_affiliate_ids == (
        "partner-a",
        "partner-b",
        "partner-c",
    )
    assert dossier.human_hours_per_month == Decimal(12)
    assert dossier.automation_rate == Decimal("0.8")
    assert dossier.shadow_observation_days == 30
    assert dossier.job_runs_total == 100
    assert dossier.job_runs_succeeded == 99
    assert dossier.exceptions_total == 24
    assert dossier.rollback_test_status is RollbackTestStatus.PASSED
    assert evaluate_business_dossier(dossier, at=NOW).decision is Decision.GO


def test_evidence_version_binds_derived_operations_payload() -> None:
    common = {
        "plans": _plans(),
        "affiliate_decisions": _affiliates(),
        "property_domain": "example.test",
        "demand": _demand_evidence(),
        "cohort": _cohort_evidence(),
        "at": NOW,
    }
    first = build_business_dossier(
        **common, operations=_operations_evidence(human_minutes_per_month=60)
    )
    second = build_business_dossier(
        **common, operations=_operations_evidence(human_minutes_per_month=120)
    )

    assert first.evidence_version != second.evidence_version


def test_operations_evidence_rejects_impossible_run_and_time_counts() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        _operations_evidence(job_runs_total=1, job_runs_succeeded=2)
    with pytest.raises(ValidationError, match="cannot be after"):
        _operations_evidence(observation_started_at=NOW)


def test_approved_affiliate_requires_a_corresponding_plan() -> None:
    with pytest.raises(ValueError, match="lack VendorPlan evidence"):
        build_business_dossier(
            plans=[make_plan()],
            affiliate_decisions=[_affiliate(vendor_slug="missing-vendor")],
            property_domain="example.test",
            demand=_demand_evidence(),
            cohort=_cohort_evidence(),
            operations=_operations_evidence(),
            at=NOW,
        )
