from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from saas_preflight.economics import (
    AffiliateCohort,
    CommissionBuckets,
    Decision,
    DemandAssumptions,
    EconomicsError,
    GateCriteria,
    GateStatus,
    GoStopInputs,
    RollbackTestStatus,
    ScenarioSet,
    calculate_confirmed_epc,
    calculate_demand,
    calculate_required_traffic,
    evaluate_go_stop,
    project_scenarios,
    traction_mature,
)


def _demand(
    volume: Decimal = Decimal("1000000"),
    *,
    visibility: Decimal = Decimal("0.50"),
    rank_ctr: Decimal = Decimal("0.20"),
    qualified_rate: Decimal = Decimal("0.50"),
    outbound_rate: Decimal = Decimal("0.10"),
    deduplicated: bool = True,
) -> DemandAssumptions:
    return DemandAssumptions(
        deduplicated_search_volume=volume,
        organic_visibility=visibility,
        rank_ctr=rank_ctr,
        qualified_rate=qualified_rate,
        outbound_click_rate=outbound_rate,
        volume_is_deduplicated=deduplicated,
    )


def _scenarios(*, bear: DemandAssumptions | None = None) -> ScenarioSet:
    return ScenarioSet(
        bear=bear or _demand(),
        base=_demand(
            Decimal("1200000"),
            visibility=Decimal("0.55"),
            rank_ctr=Decimal("0.22"),
            qualified_rate=Decimal("0.55"),
            outbound_rate=Decimal("0.12"),
        ),
        bull=_demand(
            Decimal("1500000"),
            visibility=Decimal("0.60"),
            rank_ctr=Decimal("0.25"),
            qualified_rate=Decimal("0.60"),
            outbound_rate=Decimal("0.15"),
        ),
    )


def _cohort(
    *,
    clicks: int = 1000,
    days: int = 30,
    pending: Decimal = Decimal(0),
    rejected: Decimal = Decimal(0),
    confirmed: Decimal = Decimal("30000"),
    paid: Decimal = Decimal("30000"),
    currency: str = "JPY",
) -> AffiliateCohort:
    return AffiliateCohort(
        currency=currency,
        valid_clicks=clicks,
        age_days=days,
        commissions=CommissionBuckets(
            pending=pending,
            rejected=rejected,
            confirmed=confirmed,
            paid=paid,
        ),
    )


def _inputs(**overrides: object) -> GoStopInputs:
    values: dict[str, object] = {
        "approved_affiliate_ids": ("partner-a", "partner-b", "partner-c"),
        "rights_approved": True,
        "scenarios": _scenarios(),
        "cohort": _cohort(),
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
    return GoStopInputs(**values)  # type: ignore[arg-type]


def _check(evaluation, name: str):
    return next(check for check in evaluation.checks if check.name == name)


def test_search_demand_formula_uses_deduplicated_volume() -> None:
    result = calculate_demand(_demand())

    assert result.organic_sessions == Decimal("100000")
    assert result.qualified_sessions == Decimal("50000")
    assert result.outbound_clicks == Decimal("5000")


def test_search_volume_must_be_explicitly_deduplicated() -> None:
    with pytest.raises(EconomicsError, match="explicitly deduplicated"):
        calculate_demand(_demand(deduplicated=False))


@pytest.mark.parametrize(
    "assumptions",
    [
        _demand(Decimal("-1")),
        _demand(visibility=Decimal("1.01")),
        _demand(rank_ctr=Decimal("NaN")),
        _demand(qualified_rate=Decimal("-0.1")),
        _demand(outbound_rate=Decimal("1.1")),
    ],
)
def test_invalid_demand_inputs_fail_closed(assumptions: DemandAssumptions) -> None:
    with pytest.raises(EconomicsError):
        calculate_demand(assumptions)


def test_required_traffic_for_200k_at_epc_60() -> None:
    result = calculate_required_traffic(
        Decimal("200000"), Decimal("60"), Decimal("0.10")
    )

    assert result.required_clicks_exact == Decimal("200000") / Decimal("60")
    assert result.required_clicks == 3334
    assert result.required_qualified_sessions_exact == (
        Decimal("200000") / Decimal("60") / Decimal("0.10")
    )
    assert result.required_qualified_sessions == 33334


@pytest.mark.parametrize(
    ("target", "epc", "rate"),
    [
        (Decimal(0), Decimal("60"), Decimal("0.1")),
        (Decimal("200000"), Decimal(0), Decimal("0.1")),
        (Decimal("200000"), Decimal("60"), Decimal(0)),
        (Decimal("200000"), Decimal("60"), Decimal("1.1")),
    ],
)
def test_zero_or_invalid_traffic_denominators_fail_closed(
    target: Decimal, epc: Decimal, rate: Decimal
) -> None:
    with pytest.raises(EconomicsError):
        calculate_required_traffic(target, epc, rate)


def test_confirmed_epc_uses_confirmed_and_paid_only() -> None:
    cohort = _cohort(
        clicks=1000,
        pending=Decimal("1000000"),
        rejected=Decimal("500000"),
        confirmed=Decimal("20000"),
        paid=Decimal("40000"),
    )

    assert calculate_confirmed_epc(cohort) == Decimal("60")


def test_confirmed_epc_rejects_zero_click_denominator() -> None:
    with pytest.raises(EconomicsError, match="zero valid clicks"):
        calculate_confirmed_epc(
            _cohort(clicks=0, confirmed=Decimal(0), paid=Decimal(0))
        )


@pytest.mark.parametrize(
    ("clicks", "days", "expected"),
    [(999, 179, False), (1000, 0, True), (0, 180, True)],
)
def test_traction_is_1000_clicks_or_180_days(
    clicks: int, days: int, expected: bool
) -> None:
    cohort = _cohort(
        clicks=clicks,
        days=days,
        confirmed=Decimal(0),
        paid=Decimal(0),
    )

    assert traction_mature(cohort) is expected


def test_mislabeled_scenario_order_fails_closed() -> None:
    scenarios = ScenarioSet(
        bear=_demand(Decimal("1500000")),
        base=_demand(Decimal("1000000")),
        bull=_demand(Decimal("2000000")),
    )

    with pytest.raises(EconomicsError, match="bear <= base <= bull"):
        project_scenarios(scenarios, Decimal("60"))


def test_go_at_all_default_boundaries() -> None:
    result = evaluate_go_stop(_inputs())

    assert result.decision is Decision.GO
    assert result.confirmed_epc == Decimal("60")
    assert result.traffic_requirement is not None
    assert result.traffic_requirement.required_clicks == 3334
    assert all(check.status is GateStatus.PASS for check in result.checks)


def test_immature_cohort_continues_instead_of_using_provisional_epc() -> None:
    result = evaluate_go_stop(
        _inputs(
            cohort=_cohort(
                clicks=999,
                days=179,
                confirmed=Decimal("29970"),
                paid=Decimal("29970"),
            )
        )
    )

    assert result.confirmed_epc == Decimal("60")
    assert result.decision is Decision.CONTINUE
    assert _check(result, "confirmed_epc").status is GateStatus.WAIT
    assert result.traffic_requirement is None


def test_mature_low_confirmed_epc_stops() -> None:
    result = evaluate_go_stop(
        _inputs(cohort=_cohort(confirmed=Decimal("25000"), paid=Decimal("25000")))
    )

    assert result.confirmed_epc == Decimal("50")
    assert result.decision is Decision.STOP
    assert _check(result, "confirmed_epc").status is GateStatus.FAIL


def test_pending_commission_cannot_create_a_false_go() -> None:
    result = evaluate_go_stop(
        _inputs(
            cohort=_cohort(
                pending=Decimal("1000000"),
                confirmed=Decimal(0),
                paid=Decimal(0),
            )
        )
    )

    assert result.confirmed_epc == 0
    assert result.decision is Decision.STOP


def test_bear_capacity_controls_even_when_base_and_bull_pass() -> None:
    weak_bear = _demand(Decimal("100000"))
    result = evaluate_go_stop(_inputs(scenarios=_scenarios(bear=weak_bear)))

    assert result.projections.base.confirmed_revenue > Decimal("200000")
    assert result.decision is Decision.STOP
    assert _check(result, "bear_target_capacity").status is GateStatus.FAIL


def test_duplicate_affiliate_ids_do_not_satisfy_three_partner_gate() -> None:
    result = evaluate_go_stop(
        _inputs(approved_affiliate_ids=("partner-a", "partner-b", "partner-b"))
    )

    assert result.approved_affiliate_count == 2
    assert result.decision is Decision.STOP


def test_human_hours_boundary_passes_and_excess_stops() -> None:
    assert evaluate_go_stop(_inputs(human_hours_per_month=Decimal("12"))).decision is Decision.GO

    excess = evaluate_go_stop(_inputs(human_hours_per_month=Decimal("12.01")))
    assert excess.decision is Decision.STOP
    assert _check(excess, "human_hours").status is GateStatus.FAIL


def test_automation_boundary_passes_and_shortfall_stops() -> None:
    assert evaluate_go_stop(_inputs(automation_rate=Decimal("0.80"))).decision is Decision.GO

    shortfall = evaluate_go_stop(_inputs(automation_rate=Decimal("0.799")))
    assert shortfall.decision is Decision.STOP
    assert _check(shortfall, "automation_rate").status is GateStatus.FAIL


def test_shadow_operations_boundaries_are_hard_go_requirements() -> None:
    result = evaluate_go_stop(_inputs())
    assert result.job_success_rate == Decimal("0.99")
    assert _check(result, "shadow_observation").status is GateStatus.PASS
    assert _check(result, "job_success_rate").status is GateStatus.PASS
    assert _check(result, "monthly_exceptions").status is GateStatus.PASS
    assert _check(result, "rollback_test").status is GateStatus.PASS


def test_incomplete_shadow_window_continues_instead_of_go() -> None:
    result = evaluate_go_stop(
        _inputs(
            shadow_observation_days=29,
            job_runs_total=0,
            job_runs_succeeded=0,
            exceptions_total=0,
            rollback_test_status=RollbackTestStatus.NOT_RUN,
        )
    )

    assert result.decision is Decision.CONTINUE
    assert result.job_success_rate is None
    assert _check(result, "shadow_observation").status is GateStatus.WAIT
    assert _check(result, "job_success_rate").status is GateStatus.WAIT
    assert _check(result, "monthly_exceptions").status is GateStatus.WAIT
    assert _check(result, "rollback_test").status is GateStatus.WAIT


@pytest.mark.parametrize(
    "overrides",
    [
        {"job_runs_total": 100, "job_runs_succeeded": 98},
        {"exceptions_total": 25},
        {"rollback_test_status": RollbackTestStatus.FAILED},
    ],
)
def test_mature_shadow_failures_stop(overrides: dict[str, object]) -> None:
    assert evaluate_go_stop(_inputs(**overrides)).decision is Decision.STOP


def test_job_success_count_cannot_exceed_denominator() -> None:
    with pytest.raises(EconomicsError, match="cannot exceed"):
        evaluate_go_stop(_inputs(job_runs_total=1, job_runs_succeeded=2))


@pytest.mark.parametrize(
    "overrides",
    [
        {"rights_approved": False},
        {"major_misstatements": 1},
        {"approved_affiliate_ids": ("partner-a", "partner-b")},
    ],
)
def test_hard_preflight_failures_stop(overrides: dict[str, object]) -> None:
    assert evaluate_go_stop(_inputs(**overrides)).decision is Decision.STOP


def test_180_day_maturity_with_zero_clicks_stops_without_dividing() -> None:
    result = evaluate_go_stop(
        _inputs(
            cohort=_cohort(
                clicks=0, days=180, confirmed=Decimal(0), paid=Decimal(0)
            )
        )
    )

    assert result.traction_is_mature is True
    assert result.confirmed_epc is None
    assert result.decision is Decision.STOP


def test_currency_mismatch_is_not_converted() -> None:
    with pytest.raises(EconomicsError, match="conversion is disabled"):
        evaluate_go_stop(_inputs(cohort=_cohort(currency="USD")))


def test_binary_float_is_rejected() -> None:
    assumptions = _demand()
    unsafe = DemandAssumptions(
        deduplicated_search_volume=assumptions.deduplicated_search_volume,
        organic_visibility=0.5,  # type: ignore[arg-type]
        rank_ctr=assumptions.rank_ctr,
        qualified_rate=assumptions.qualified_rate,
        outbound_click_rate=assumptions.outbound_click_rate,
        volume_is_deduplicated=True,
    )

    with pytest.raises(EconomicsError, match="Decimal"):
        calculate_demand(unsafe)


@given(
    low=st.integers(min_value=0, max_value=10**9),
    high=st.integers(min_value=0, max_value=10**9),
)
def test_demand_is_monotonic_in_deduplicated_volume(low: int, high: int) -> None:
    lower, upper = sorted((low, high))

    low_result = calculate_demand(_demand(Decimal(lower)))
    high_result = calculate_demand(_demand(Decimal(upper)))

    assert high_result.qualified_sessions >= low_result.qualified_sessions
    assert high_result.outbound_clicks >= low_result.outbound_clicks


@given(
    low_epc=st.integers(min_value=1, max_value=100_000),
    high_epc=st.integers(min_value=1, max_value=100_000),
)
def test_required_traffic_is_nonincreasing_in_epc(
    low_epc: int, high_epc: int
) -> None:
    lower, upper = sorted((low_epc, high_epc))

    low_result = calculate_required_traffic(
        Decimal("200000"), Decimal(lower), Decimal("0.1")
    )
    high_result = calculate_required_traffic(
        Decimal("200000"), Decimal(upper), Decimal("0.1")
    )

    assert high_result.required_clicks <= low_result.required_clicks
    assert high_result.required_qualified_sessions <= low_result.required_qualified_sessions


@given(
    pending_a=st.integers(min_value=0, max_value=10**9),
    pending_b=st.integers(min_value=0, max_value=10**9),
    rejected_a=st.integers(min_value=0, max_value=10**9),
    rejected_b=st.integers(min_value=0, max_value=10**9),
)
def test_pending_and_rejected_amounts_never_change_confirmed_epc(
    pending_a: int, pending_b: int, rejected_a: int, rejected_b: int
) -> None:
    first = _cohort(
        pending=Decimal(pending_a),
        rejected=Decimal(rejected_a),
        confirmed=Decimal("30000"),
        paid=Decimal("30000"),
    )
    second = _cohort(
        pending=Decimal(pending_b),
        rejected=Decimal(rejected_b),
        confirmed=Decimal("30000"),
        paid=Decimal("30000"),
    )

    assert calculate_confirmed_epc(first) == calculate_confirmed_epc(second)


@given(
    lower=st.integers(min_value=0, max_value=10**9),
    delta=st.integers(min_value=0, max_value=10**9),
)
def test_confirmed_epc_is_monotonic_in_settled_commission(
    lower: int, delta: int
) -> None:
    low = _cohort(confirmed=Decimal(lower), paid=Decimal(0))
    high = _cohort(confirmed=Decimal(lower + delta), paid=Decimal(0))

    assert calculate_confirmed_epc(high) >= calculate_confirmed_epc(low)
