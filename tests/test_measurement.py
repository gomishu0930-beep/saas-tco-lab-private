from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from saas_preflight.economics import RollbackTestStatus
from saas_preflight.measurement import (
    CohortSummaryBatch,
    DailyOperationsSummary,
    DemandClusterSummary,
    DemandSummaryBatch,
    EvidenceReceipt,
    OperationsSummaryBatch,
    PartnerCohortSummary,
    ScenarioRates,
    build_cohort_evidence,
    build_demand_evidence,
    build_operations_evidence,
)
from saas_preflight.preflight import CommissionInput


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
TOKYO = ZoneInfo("Asia/Tokyo")
OBSERVATION_START = datetime(2026, 6, 1, tzinfo=TOKYO)
OBSERVATION_END = OBSERVATION_START + timedelta(days=30)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _receipt(captured_at: datetime = NOW) -> EvidenceReceipt:
    return EvidenceReceipt(
        authority="synthetic-owned-export",
        authority_record_sha256=_sha("authority"),
        source_receipt_sha256=_sha("source"),
        retrieved_at=captured_at + timedelta(hours=1),
    )


def _rates(value: str) -> ScenarioRates:
    return ScenarioRates(
        organic_visibility=Decimal(value),
        rank_ctr=Decimal("0.2"),
        qualified_rate=Decimal("0.5"),
        outbound_click_rate=Decimal("0.1"),
    )


def _cluster(name: str, volume: str) -> DemandClusterSummary:
    return DemandClusterSummary(
        cluster_id=name,
        cluster_receipt_sha256=_sha(f"cluster:{name}"),
        deduplicated_monthly_volume=Decimal(volume),
    )


def _demand_batch(
    *, clusters: tuple[DemandClusterSummary, ...] | None = None
) -> DemandSummaryBatch:
    return DemandSummaryBatch(
        measurement_version="demand-method-v1",
        receipt=_receipt(),
        source_month="2026-06",
        deduplication_sha256=_sha("demand-dedup-v1"),
        volume_is_deduplicated=True,
        captured_at=NOW,
        expires_at=NOW + timedelta(days=30),
        clusters=clusters or (_cluster("pricing", "100"), _cluster("compare", "200")),
        bear=_rates("0.2"),
        base=_rates("0.3"),
        bull=_rates("0.4"),
    )


def _partner(
    partner: str,
    *,
    clicks: int,
    confirmed: str = "0",
    paid: str = "0",
) -> PartnerCohortSummary:
    return PartnerCohortSummary(
        summary_id_sha256=_sha(f"summary:{partner}"),
        partner_id=partner,
        valid_clicks=clicks,
        commissions=CommissionInput(
            pending=Decimal(0),
            rejected=Decimal(0),
            confirmed=Decimal(confirmed),
            paid=Decimal(paid),
        ),
    )


def _cohort_batch(
    *, summaries: tuple[PartnerCohortSummary, ...] | None = None
) -> CohortSummaryBatch:
    return CohortSummaryBatch(
        measurement_version="cohort-method-v1",
        receipt=_receipt(),
        property_record_sha256=_sha("property"),
        currency="JPY",
        cohort_id="june-2026",
        cohort_started_at=NOW - timedelta(days=30),
        cohort_ended_at=NOW - timedelta(days=1),
        captured_at=NOW,
        expires_at=NOW + timedelta(days=30),
        click_deduplication_sha256=_sha("click-dedup-v1"),
        status_mapping_sha256=_sha("status-map-v1"),
        summaries=summaries
        or (
            _partner("partner-a", clicks=600, confirmed="20000"),
            _partner("partner-b", clicks=400, paid="40000"),
        ),
    )


def _day(offset: int, **overrides: int) -> DailyOperationsSummary:
    values = {
        "human_minutes": 0,
        "routine_tasks_total": 0,
        "routine_tasks_automated": 0,
        "job_runs_total": 0,
        "job_runs_succeeded": 0,
        "exceptions_total": 0,
        "major_misstatements": 0,
        "rollback_tests_total": 0,
        "rollback_tests_passed": 0,
    }
    values.update(overrides)
    return DailyOperationsSummary(
        summary_id_sha256=_sha(f"day:{offset}"),
        local_date=(OBSERVATION_START + timedelta(days=offset)).date(),
        **values,
    )


def _operation_days() -> tuple[DailyOperationsSummary, ...]:
    return (
        _day(
            0,
            human_minutes=720,
            routine_tasks_total=100,
            routine_tasks_automated=80,
            job_runs_total=100,
            job_runs_succeeded=99,
            exceptions_total=24,
            rollback_tests_total=1,
            rollback_tests_passed=1,
        ),
        *(_day(offset) for offset in range(1, 30)),
    )


def _operations_batch(
    *, days: tuple[DailyOperationsSummary, ...] | None = None
) -> OperationsSummaryBatch:
    return OperationsSummaryBatch(
        measurement_version="operations-method-v1",
        receipt=_receipt(OBSERVATION_END),
        property_record_sha256=_sha("property"),
        observation_started_at=OBSERVATION_START,
        captured_at=OBSERVATION_END,
        expires_at=OBSERVATION_END + timedelta(days=30),
        routine_inventory_sha256=_sha("routine-inventory"),
        job_schedule_sha256=_sha("job-schedule"),
        job_status_mapping_sha256=_sha("job-status"),
        exception_deduplication_sha256=_sha("exception-dedup"),
        qa_policy_sha256=_sha("qa-policy"),
        rollback_catalog_sha256=_sha("rollback-catalog"),
        daily_summaries=days if days is not None else _operation_days(),
    )


def test_demand_clusters_are_summed_into_exact_decimal_scenarios() -> None:
    evidence = build_demand_evidence(
        _demand_batch(), at=NOW + timedelta(hours=2)
    )

    assert evidence.scenarios.bear.deduplicated_search_volume == Decimal("300")
    assert evidence.scenarios.base.deduplicated_search_volume == Decimal("300")
    assert evidence.scenarios.bull.deduplicated_search_volume == Decimal("300")
    assert evidence.source_sha256 in evidence.evidence_version


def test_demand_order_is_canonical_but_duplicate_identity_is_rejected() -> None:
    first = build_demand_evidence(
        _demand_batch(
            clusters=(_cluster("pricing", "100"), _cluster("compare", "200"))
        ),
        at=NOW + timedelta(hours=2),
    )
    second = build_demand_evidence(
        _demand_batch(
            clusters=(_cluster("compare", "200"), _cluster("pricing", "100"))
        ),
        at=NOW + timedelta(hours=2),
    )
    assert first == second

    with pytest.raises(ValidationError, match="cluster IDs must be distinct"):
        _demand_batch(clusters=(_cluster("pricing", "100"), _cluster("pricing", "100")))


def test_demand_rejects_float_and_mislabeled_scenario_order() -> None:
    with pytest.raises(ValidationError):
        ScenarioRates(
            organic_visibility=0.2,
            rank_ctr=Decimal("0.2"),
            qualified_rate=Decimal("0.5"),
            outbound_click_rate=Decimal("0.1"),
        )
    batch = _demand_batch().model_copy(
        update={"bear": _rates("0.5"), "base": _rates("0.3")}
    )
    with pytest.raises(ValueError, match="bear <= base <= bull"):
        build_demand_evidence(batch, at=NOW + timedelta(hours=2))


def test_cohort_aggregates_partner_summaries_without_pending_inference() -> None:
    evidence = build_cohort_evidence(
        _cohort_batch(), at=NOW + timedelta(hours=2)
    )

    assert evidence.cohort.valid_clicks == 1000
    assert evidence.cohort.age_days == 30
    assert evidence.cohort.commissions.confirmed == Decimal("20000")
    assert evidence.cohort.commissions.paid == Decimal("40000")


def test_cohort_zero_click_summary_is_valid_stop_evidence() -> None:
    evidence = build_cohort_evidence(
        _cohort_batch(summaries=(_partner("partner-a", clicks=0),)),
        at=NOW + timedelta(hours=2),
    )
    assert evidence.cohort.valid_clicks == 0


def test_cohort_order_is_canonical_and_partner_duplicates_are_rejected() -> None:
    a = _partner("partner-a", clicks=1)
    b = _partner("partner-b", clicks=2)
    first = build_cohort_evidence(
        _cohort_batch(summaries=(a, b)), at=NOW + timedelta(hours=2)
    )
    second = build_cohort_evidence(
        _cohort_batch(summaries=(b, a)), at=NOW + timedelta(hours=2)
    )
    assert first == second
    with pytest.raises(ValidationError, match="partner IDs must be distinct"):
        _cohort_batch(summaries=(a, a.model_copy(update={"summary_id_sha256": _sha("other")})))


def test_operations_builds_all_gate_d_values() -> None:
    evidence = build_operations_evidence(
        _operations_batch(), at=OBSERVATION_END + timedelta(hours=2)
    )

    assert evidence.shadow_observation_days() == 30
    assert evidence.human_minutes_per_month == 720
    assert evidence.routine_tasks_total == 100
    assert evidence.routine_tasks_automated == 80
    assert evidence.job_runs_total == 100
    assert evidence.job_runs_succeeded == 99
    assert evidence.exceptions_total == 24
    assert evidence.major_misstatements == 0
    assert evidence.rollback_test_status is RollbackTestStatus.PASSED


def test_operations_zero_denominators_and_unrun_rollback_remain_evidence() -> None:
    evidence = build_operations_evidence(
        _operations_batch(days=tuple(_day(offset) for offset in range(30))),
        at=OBSERVATION_END + timedelta(hours=2),
    )

    assert evidence.automation_rate() == Decimal(0)
    assert evidence.job_runs_total == 0
    assert evidence.rollback_test_status is RollbackTestStatus.NOT_RUN


def test_operations_rejects_impossible_counts_duplicate_or_missing_days() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        _day(0, job_runs_total=1, job_runs_succeeded=2)
    with pytest.raises(ValidationError, match="dates must be distinct"):
        _operations_batch(
            days=(
                _day(0),
                _day(0).model_copy(update={"summary_id_sha256": _sha("other-day")}),
            )
        )
    with pytest.raises(ValidationError, match="cover every complete"):
        _operations_batch(days=_operation_days()[:-1])


@pytest.mark.parametrize(
    "builder,batch,at",
    [
        (build_demand_evidence, _demand_batch(), NOW + timedelta(days=31)),
        (build_cohort_evidence, _cohort_batch(), NOW + timedelta(days=31)),
        (
            build_operations_evidence,
            _operations_batch(),
            OBSERVATION_END + timedelta(days=30),
        ),
    ],
)
def test_expired_summary_is_rejected(builder, batch, at: datetime) -> None:
    with pytest.raises(ValueError, match="expired"):
        builder(batch, at=at)


def test_receipt_cannot_claim_retrieval_before_capture() -> None:
    values = _demand_batch().model_dump()
    values["receipt"] = _receipt(NOW - timedelta(hours=2))
    with pytest.raises(ValidationError, match="cannot predate"):
        DemandSummaryBatch(**values)


def test_future_retrieval_and_source_month_are_rejected() -> None:
    with pytest.raises(ValueError, match="retrieved in the future"):
        build_demand_evidence(
            _demand_batch(), at=NOW + timedelta(minutes=30)
        )
    values = _demand_batch().model_dump()
    values["source_month"] = "2026-08"
    with pytest.raises(ValidationError, match="source_month cannot be later"):
        DemandSummaryBatch(**values)
