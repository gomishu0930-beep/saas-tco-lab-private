from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from saas_preflight.economics import Decision, GateStatus, RollbackTestStatus
from saas_preflight.preflight import (
    ArtifactExpiries,
    BusinessDossier,
    CohortInput,
    CommissionInput,
    DemandInput,
    DossierProvenance,
    ScenarioInputs,
    evaluate_business_dossier,
)


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def _demand(volume: str, outbound: str) -> DemandInput:
    return DemandInput(
        deduplicated_search_volume=Decimal(volume),
        organic_visibility=Decimal("0.5"),
        rank_ctr=Decimal("0.2"),
        qualified_rate=Decimal("0.5"),
        outbound_click_rate=Decimal(outbound),
        volume_is_deduplicated=True,
    )


def _dossier(**overrides: object) -> BusinessDossier:
    values: dict[str, object] = {
        "evidence_version": "synthetic-v1",
        "provenance": DossierProvenance(
            property_domain="example.test",
            rights_bundle_sha256="1" * 64,
            affiliate_bundle_sha256="2" * 64,
            demand_source_sha256="3" * 64,
            cohort_source_sha256="4" * 64,
            operations_source_sha256="5" * 64,
            assembled_at=NOW,
        ),
        "as_of": NOW,
        "expires_at": ArtifactExpiries(
            rights=NOW + timedelta(days=30),
            affiliate=NOW + timedelta(days=30),
            demand=NOW + timedelta(days=30),
            operations=NOW + timedelta(days=30),
            cohort=NOW + timedelta(days=30),
        ),
        "approved_affiliate_ids": ("partner-a", "partner-b", "partner-c"),
        "rights_approved": True,
        "scenarios": ScenarioInputs(
            bear=_demand("1000000", "0.10"),
            base=_demand("1200000", "0.12"),
            bull=_demand("1500000", "0.15"),
        ),
        "cohort": CohortInput(
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
        "human_hours_per_month": Decimal("12"),
        "automation_rate": Decimal("0.80"),
        "major_misstatements": 0,
        "shadow_observation_days": 30,
        "job_runs_total": 100,
        "job_runs_succeeded": 99,
        "exceptions_total": 24,
        "rollback_test_status": RollbackTestStatus.PASSED,
    }
    values.update(overrides)
    return BusinessDossier(**values)


def test_fresh_complete_dossier_reaches_calculated_go() -> None:
    result = evaluate_business_dossier(_dossier(), at=NOW + timedelta(days=1))

    assert result.decision is Decision.GO
    assert result.economics is not None
    assert all(check.status is GateStatus.PASS for check in result.freshness_checks)


def test_expired_artifact_stops_before_economics() -> None:
    dossier = _dossier(
        provenance=DossierProvenance(
            property_domain="example.test",
            rights_bundle_sha256="1" * 64,
            affiliate_bundle_sha256="2" * 64,
            demand_source_sha256="3" * 64,
            cohort_source_sha256="4" * 64,
            operations_source_sha256="5" * 64,
            assembled_at=NOW,
        ),
        expires_at=ArtifactExpiries(
            rights=NOW + timedelta(hours=1),
            affiliate=NOW + timedelta(days=30),
            demand=NOW + timedelta(days=30),
            operations=NOW + timedelta(days=30),
            cohort=NOW + timedelta(days=30),
        )
    )
    result = evaluate_business_dossier(dossier, at=NOW + timedelta(hours=1))

    assert result.decision is Decision.STOP
    assert result.economics is None
    rights = next(check for check in result.freshness_checks if check.name == "rights_freshness")
    assert rights.status is GateStatus.FAIL


def test_future_artifact_stops_before_economics() -> None:
    result = evaluate_business_dossier(_dossier(), at=NOW - timedelta(seconds=1))

    assert result.decision is Decision.STOP
    assert result.economics is None


def test_current_real_state_is_stop_not_false_go() -> None:
    empty = CommissionInput(
        pending=Decimal(0),
        rejected=Decimal(0),
        confirmed=Decimal(0),
        paid=Decimal(0),
    )
    dossier = _dossier(
        approved_affiliate_ids=(),
        rights_approved=False,
        scenarios=ScenarioInputs(
            bear=_demand("0", "0"),
            base=_demand("0", "0"),
            bull=_demand("0", "0"),
        ),
        cohort=CohortInput(
            currency="JPY", valid_clicks=0, age_days=0, commissions=empty
        ),
        human_hours_per_month=Decimal(0),
        automation_rate=Decimal(0),
    )

    result = evaluate_business_dossier(dossier, at=NOW)
    assert result.decision is Decision.STOP
    assert result.economics is not None
    failed = {
        check.name
        for check in result.economics.checks
        if check.status is GateStatus.FAIL
    }
    assert {"rights", "affiliate_partners", "automation_rate"} <= failed
