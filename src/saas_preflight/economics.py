"""Deterministic demand, affiliate-cohort, and GO/STOP economics.

This module performs no network access and contains no market estimates. Every
volume, rate, commission, and approval state must be supplied by the caller from
versioned evidence. Decimal arithmetic is used throughout; binary floats are
rejected at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from enum import Enum
from typing import Iterable


class EconomicsError(ValueError):
    """Raised when an economic input is incomplete, ambiguous, or invalid."""


class Decision(str, Enum):
    GO = "go"
    CONTINUE = "continue"
    STOP = "stop"


class GateStatus(str, Enum):
    PASS = "pass"
    WAIT = "wait"
    FAIL = "fail"


class ScenarioName(str, Enum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


class RollbackTestStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DemandAssumptions:
    """One monthly, deduplicated Japanese-search demand scenario.

    All rates are decimal fractions in the closed interval [0, 1]. The
    ``volume_is_deduplicated`` assertion is explicit so raw keyword volumes
    cannot accidentally enter the capacity calculation.
    """

    deduplicated_search_volume: Decimal
    organic_visibility: Decimal
    rank_ctr: Decimal
    qualified_rate: Decimal
    outbound_click_rate: Decimal
    volume_is_deduplicated: bool


@dataclass(frozen=True, slots=True)
class DemandProjection:
    deduplicated_search_volume: Decimal
    organic_sessions: Decimal
    qualified_sessions: Decimal
    outbound_clicks: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioSet:
    bear: DemandAssumptions
    base: DemandAssumptions
    bull: DemandAssumptions


@dataclass(frozen=True, slots=True)
class ScenarioProjection:
    name: ScenarioName
    demand: DemandProjection
    confirmed_revenue: Decimal | None


@dataclass(frozen=True, slots=True)
class ScenarioProjectionSet:
    bear: ScenarioProjection
    base: ScenarioProjection
    bull: ScenarioProjection


@dataclass(frozen=True, slots=True)
class CommissionBuckets:
    """Mutually exclusive commission-status amounts at one snapshot.

    ``paid`` represents amounts whose current status is paid; it must not also
    remain in ``confirmed``. Pending and rejected amounts are reported but never
    enter confirmed EPC.
    """

    pending: Decimal
    rejected: Decimal
    confirmed: Decimal
    paid: Decimal


@dataclass(frozen=True, slots=True)
class AffiliateCohort:
    currency: str
    valid_clicks: int
    age_days: int
    commissions: CommissionBuckets


@dataclass(frozen=True, slots=True)
class TrafficRequirement:
    target_monthly_revenue: Decimal
    confirmed_epc: Decimal
    outbound_click_rate: Decimal
    required_clicks_exact: Decimal
    required_clicks: int
    required_qualified_sessions_exact: Decimal
    required_qualified_sessions: int


@dataclass(frozen=True, slots=True)
class GateCriteria:
    currency: str = "JPY"
    target_monthly_revenue: Decimal = Decimal("200000")
    minimum_affiliate_partners: int = 3
    minimum_confirmed_epc: Decimal = Decimal("60")
    traction_valid_clicks: int = 1000
    traction_days: int = 180
    maximum_human_hours_per_month: Decimal = Decimal("12")
    minimum_automation_rate: Decimal = Decimal("0.80")
    maximum_major_misstatements: int = 0
    minimum_shadow_observation_days: int = 30
    minimum_job_success_rate: Decimal = Decimal("0.99")
    maximum_monthly_exceptions: int = 24


@dataclass(frozen=True, slots=True)
class GoStopInputs:
    approved_affiliate_ids: tuple[str, ...]
    rights_approved: bool
    scenarios: ScenarioSet
    cohort: AffiliateCohort
    human_hours_per_month: Decimal
    automation_rate: Decimal
    major_misstatements: int
    shadow_observation_days: int
    job_runs_total: int
    job_runs_succeeded: int
    exceptions_total: int
    rollback_test_status: RollbackTestStatus


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    status: GateStatus
    observed: str
    requirement: str


@dataclass(frozen=True, slots=True)
class GoStopEvaluation:
    decision: Decision
    checks: tuple[GateCheck, ...]
    approved_affiliate_count: int
    traction_is_mature: bool
    confirmed_epc: Decimal | None
    traffic_requirement: TrafficRequirement | None
    projections: ScenarioProjectionSet
    job_success_rate: Decimal | None


DEFAULT_GATE_CRITERIA = GateCriteria()


def calculate_demand(assumptions: DemandAssumptions) -> DemandProjection:
    """Project monthly qualified sessions and outbound clicks without rounding."""

    if assumptions.volume_is_deduplicated is not True:
        raise EconomicsError("search volume must be explicitly deduplicated")
    volume = _non_negative_decimal(
        assumptions.deduplicated_search_volume, "deduplicated_search_volume"
    )
    visibility = _ratio(assumptions.organic_visibility, "organic_visibility")
    rank_ctr = _ratio(assumptions.rank_ctr, "rank_ctr")
    qualified_rate = _ratio(assumptions.qualified_rate, "qualified_rate")
    outbound_rate = _ratio(
        assumptions.outbound_click_rate, "outbound_click_rate"
    )
    organic_sessions = volume * visibility * rank_ctr
    qualified_sessions = organic_sessions * qualified_rate
    return DemandProjection(
        deduplicated_search_volume=volume,
        organic_sessions=organic_sessions,
        qualified_sessions=qualified_sessions,
        outbound_clicks=qualified_sessions * outbound_rate,
    )


def calculate_confirmed_epc(cohort: AffiliateCohort) -> Decimal:
    """Return settled commission per all valid cohort clicks.

    Confirmed and paid are mutually exclusive settled status buckets. Pending
    and rejected commission never enter the numerator, while their cohort's
    valid clicks remain in the denominator.
    """

    _validate_cohort(cohort)
    if cohort.valid_clicks == 0:
        raise EconomicsError("confirmed EPC is undefined for zero valid clicks")
    settled = (
        _non_negative_decimal(cohort.commissions.confirmed, "commissions.confirmed")
        + _non_negative_decimal(cohort.commissions.paid, "commissions.paid")
    )
    return settled / Decimal(cohort.valid_clicks)


def calculate_required_traffic(
    target_monthly_revenue: Decimal,
    confirmed_epc: Decimal,
    outbound_click_rate: Decimal,
) -> TrafficRequirement:
    """Reverse a revenue target into confirmed clicks and qualified sessions.

    Exact expectations are retained. Integer requirements independently round
    the exact click and exact session expectations upward, so a rounded click
    count is not cascaded into a second, artificially inflated rounding step.
    """

    target = _positive_decimal(target_monthly_revenue, "target_monthly_revenue")
    epc = _positive_decimal(confirmed_epc, "confirmed_epc")
    outbound_rate = _positive_ratio(outbound_click_rate, "outbound_click_rate")
    exact_clicks = target / epc
    exact_sessions = exact_clicks / outbound_rate
    return TrafficRequirement(
        target_monthly_revenue=target,
        confirmed_epc=epc,
        outbound_click_rate=outbound_rate,
        required_clicks_exact=exact_clicks,
        required_clicks=_ceiling(exact_clicks),
        required_qualified_sessions_exact=exact_sessions,
        required_qualified_sessions=_ceiling(exact_sessions),
    )


def traction_mature(
    cohort: AffiliateCohort, criteria: GateCriteria = DEFAULT_GATE_CRITERIA
) -> bool:
    """Mature at 1,000 valid clicks OR 180 elapsed days by default."""

    _validate_cohort(cohort)
    _validate_criteria(criteria)
    return (
        cohort.valid_clicks >= criteria.traction_valid_clicks
        or cohort.age_days >= criteria.traction_days
    )


def project_scenarios(
    scenarios: ScenarioSet, confirmed_epc: Decimal | None
) -> ScenarioProjectionSet:
    """Calculate bear/base/bull projections and reject mislabeled ordering."""

    epc = (
        None
        if confirmed_epc is None
        else _non_negative_decimal(confirmed_epc, "confirmed_epc")
    )
    results: list[ScenarioProjection] = []
    for name, assumptions in (
        (ScenarioName.BEAR, scenarios.bear),
        (ScenarioName.BASE, scenarios.base),
        (ScenarioName.BULL, scenarios.bull),
    ):
        demand = calculate_demand(assumptions)
        results.append(
            ScenarioProjection(
                name=name,
                demand=demand,
                confirmed_revenue=(None if epc is None else demand.outbound_clicks * epc),
            )
        )

    for metric in ("qualified_sessions", "outbound_clicks"):
        values = [getattr(result.demand, metric) for result in results]
        if values != sorted(values):
            raise EconomicsError(
                f"scenario ordering must satisfy bear <= base <= bull for {metric}"
            )
    return ScenarioProjectionSet(*results)


def evaluate_go_stop(
    inputs: GoStopInputs, criteria: GateCriteria = DEFAULT_GATE_CRITERIA
) -> GoStopEvaluation:
    """Evaluate preflight and mature traction gates without inventing evidence."""

    _validate_criteria(criteria)
    _validate_cohort(inputs.cohort)
    expected_currency = _currency(criteria.currency, "criteria.currency")
    cohort_currency = _currency(inputs.cohort.currency, "cohort.currency")
    if cohort_currency != expected_currency:
        raise EconomicsError(
            f"cohort currency {cohort_currency} does not match target currency "
            f"{expected_currency}; conversion is disabled"
        )
    if not isinstance(inputs.rights_approved, bool):
        raise EconomicsError("rights_approved must be boolean")
    human_hours = _non_negative_decimal(
        inputs.human_hours_per_month, "human_hours_per_month"
    )
    automation_rate = _ratio(inputs.automation_rate, "automation_rate")
    major_misstatements = _non_negative_integer(
        inputs.major_misstatements, "major_misstatements"
    )
    shadow_days = _non_negative_integer(
        inputs.shadow_observation_days, "shadow_observation_days"
    )
    job_runs_total = _non_negative_integer(inputs.job_runs_total, "job_runs_total")
    job_runs_succeeded = _non_negative_integer(
        inputs.job_runs_succeeded, "job_runs_succeeded"
    )
    if job_runs_succeeded > job_runs_total:
        raise EconomicsError("job_runs_succeeded cannot exceed job_runs_total")
    exceptions_total = _non_negative_integer(
        inputs.exceptions_total, "exceptions_total"
    )
    if type(inputs.rollback_test_status) is not RollbackTestStatus:
        raise EconomicsError("rollback_test_status must be RollbackTestStatus")
    job_success_rate = (
        None
        if job_runs_total == 0
        else Decimal(job_runs_succeeded) / Decimal(job_runs_total)
    )
    affiliate_ids = _normalise_affiliate_ids(inputs.approved_affiliate_ids)
    affiliate_count = len(set(affiliate_ids))
    mature = traction_mature(inputs.cohort, criteria)

    current_epc: Decimal | None = None
    if inputs.cohort.valid_clicks > 0:
        current_epc = calculate_confirmed_epc(inputs.cohort)
    projections = project_scenarios(inputs.scenarios, current_epc)
    bear = projections.bear

    checks: list[GateCheck] = [
        _boolean_check(
            "rights",
            inputs.rights_approved,
            observed="approved" if inputs.rights_approved else "not approved",
            requirement="approved field-level rights",
        ),
        _threshold_check(
            "affiliate_partners",
            affiliate_count >= criteria.minimum_affiliate_partners,
            observed=str(affiliate_count),
            requirement=f">= {criteria.minimum_affiliate_partners} distinct approved partners",
        ),
        _threshold_check(
            "major_misstatements",
            major_misstatements <= criteria.maximum_major_misstatements,
            observed=str(major_misstatements),
            requirement=f"<= {criteria.maximum_major_misstatements}",
        ),
        _threshold_check(
            "human_hours",
            human_hours <= criteria.maximum_human_hours_per_month,
            observed=str(human_hours),
            requirement=f"<= {criteria.maximum_human_hours_per_month} hours/month",
        ),
        _threshold_check(
            "automation_rate",
            automation_rate >= criteria.minimum_automation_rate,
            observed=str(automation_rate),
            requirement=f">= {criteria.minimum_automation_rate}",
        ),
        _threshold_check(
            "bear_qualified_demand",
            bear.demand.qualified_sessions > 0 and bear.demand.outbound_clicks > 0,
            observed=(
                f"qualified_sessions={bear.demand.qualified_sessions}, "
                f"outbound_clicks={bear.demand.outbound_clicks}"
            ),
            requirement="positive conservative qualified sessions and outbound clicks",
        ),
        GateCheck(
            name="shadow_observation",
            status=(
                GateStatus.PASS
                if shadow_days >= criteria.minimum_shadow_observation_days
                else GateStatus.WAIT
            ),
            observed=f"{shadow_days} days",
            requirement=f">= {criteria.minimum_shadow_observation_days} days",
        ),
        GateCheck(
            name="job_success_rate",
            status=(
                GateStatus.WAIT
                if shadow_days < criteria.minimum_shadow_observation_days
                else (
                    GateStatus.PASS
                    if job_success_rate is not None
                    and job_success_rate >= criteria.minimum_job_success_rate
                    else GateStatus.FAIL
                )
            ),
            observed=("undefined" if job_success_rate is None else str(job_success_rate)),
            requirement=f">= {criteria.minimum_job_success_rate}",
        ),
        GateCheck(
            name="monthly_exceptions",
            status=(
                GateStatus.FAIL
                if exceptions_total > criteria.maximum_monthly_exceptions
                else (
                    GateStatus.PASS
                    if shadow_days >= criteria.minimum_shadow_observation_days
                    else GateStatus.WAIT
                )
            ),
            observed=str(exceptions_total),
            requirement=f"<= {criteria.maximum_monthly_exceptions}",
        ),
        GateCheck(
            name="rollback_test",
            status={
                RollbackTestStatus.NOT_RUN: GateStatus.WAIT,
                RollbackTestStatus.PASSED: GateStatus.PASS,
                RollbackTestStatus.FAILED: GateStatus.FAIL,
            }[inputs.rollback_test_status],
            observed=inputs.rollback_test_status.value,
            requirement=RollbackTestStatus.PASSED.value,
        ),
        GateCheck(
            name="traction_maturity",
            status=GateStatus.PASS if mature else GateStatus.WAIT,
            observed=(
                f"valid_clicks={inputs.cohort.valid_clicks}, age_days={inputs.cohort.age_days}"
            ),
            requirement=(
                f">= {criteria.traction_valid_clicks} valid clicks OR "
                f">= {criteria.traction_days} days"
            ),
        ),
    ]

    requirement: TrafficRequirement | None = None
    if not mature:
        checks.extend(
            (
                GateCheck(
                    name="confirmed_epc",
                    status=GateStatus.WAIT,
                    observed="provisional" if current_epc is not None else "undefined",
                    requirement=f">= {criteria.minimum_confirmed_epc} after maturity",
                ),
                GateCheck(
                    name="bear_target_capacity",
                    status=GateStatus.WAIT,
                    observed="not evaluated before traction maturity",
                    requirement=f">= {criteria.target_monthly_revenue} {expected_currency}/month",
                ),
            )
        )
    elif current_epc is None:
        checks.extend(
            (
                GateCheck(
                    name="confirmed_epc",
                    status=GateStatus.FAIL,
                    observed="undefined: zero valid clicks",
                    requirement=f">= {criteria.minimum_confirmed_epc}",
                ),
                GateCheck(
                    name="bear_target_capacity",
                    status=GateStatus.FAIL,
                    observed="undefined: zero valid clicks",
                    requirement=f">= {criteria.target_monthly_revenue} {expected_currency}/month",
                ),
            )
        )
    else:
        epc_passes = current_epc >= criteria.minimum_confirmed_epc
        checks.append(
            _threshold_check(
                "confirmed_epc",
                epc_passes,
                observed=str(current_epc),
                requirement=f">= {criteria.minimum_confirmed_epc} {expected_currency}/valid click",
            )
        )
        if current_epc > 0:
            requirement = calculate_required_traffic(
                criteria.target_monthly_revenue,
                current_epc,
                scenarios_outbound_rate(inputs.scenarios.bear),
            )
            capacity_passes = (
                bear.demand.qualified_sessions
                >= requirement.required_qualified_sessions_exact
            )
            checks.append(
                _threshold_check(
                    "bear_target_capacity",
                    capacity_passes,
                    observed=(
                        f"qualified_sessions={bear.demand.qualified_sessions}, "
                        f"required={requirement.required_qualified_sessions_exact}, "
                        f"confirmed_revenue={bear.confirmed_revenue}"
                    ),
                    requirement=f">= {criteria.target_monthly_revenue} {expected_currency}/month",
                )
            )
        else:
            checks.append(
                GateCheck(
                    name="bear_target_capacity",
                    status=GateStatus.FAIL,
                    observed="confirmed EPC is zero",
                    requirement=f">= {criteria.target_monthly_revenue} {expected_currency}/month",
                )
            )

    statuses = {check.status for check in checks}
    if GateStatus.FAIL in statuses:
        decision = Decision.STOP
    elif GateStatus.WAIT in statuses:
        decision = Decision.CONTINUE
    else:
        decision = Decision.GO
    return GoStopEvaluation(
        decision=decision,
        checks=tuple(checks),
        approved_affiliate_count=affiliate_count,
        traction_is_mature=mature,
        confirmed_epc=current_epc,
        traffic_requirement=requirement,
        projections=projections,
        job_success_rate=job_success_rate,
    )


def scenarios_outbound_rate(assumptions: DemandAssumptions) -> Decimal:
    """Return a validated scenario outbound click rate."""

    return _positive_ratio(assumptions.outbound_click_rate, "outbound_click_rate")


def _validate_cohort(cohort: AffiliateCohort) -> None:
    _currency(cohort.currency, "cohort.currency")
    _non_negative_integer(cohort.valid_clicks, "valid_clicks")
    _non_negative_integer(cohort.age_days, "age_days")
    _non_negative_decimal(cohort.commissions.pending, "commissions.pending")
    _non_negative_decimal(cohort.commissions.rejected, "commissions.rejected")
    _non_negative_decimal(cohort.commissions.confirmed, "commissions.confirmed")
    _non_negative_decimal(cohort.commissions.paid, "commissions.paid")


def _validate_criteria(criteria: GateCriteria) -> None:
    _currency(criteria.currency, "criteria.currency")
    _positive_decimal(criteria.target_monthly_revenue, "target_monthly_revenue")
    _positive_integer(
        criteria.minimum_affiliate_partners, "minimum_affiliate_partners"
    )
    _positive_decimal(criteria.minimum_confirmed_epc, "minimum_confirmed_epc")
    _positive_integer(criteria.traction_valid_clicks, "traction_valid_clicks")
    _positive_integer(criteria.traction_days, "traction_days")
    _non_negative_decimal(
        criteria.maximum_human_hours_per_month, "maximum_human_hours_per_month"
    )
    _ratio(criteria.minimum_automation_rate, "minimum_automation_rate")
    _non_negative_integer(
        criteria.maximum_major_misstatements, "maximum_major_misstatements"
    )
    _positive_integer(
        criteria.minimum_shadow_observation_days,
        "minimum_shadow_observation_days",
    )
    _ratio(criteria.minimum_job_success_rate, "minimum_job_success_rate")
    if criteria.minimum_job_success_rate == 0:
        raise EconomicsError("minimum_job_success_rate must be positive")
    _non_negative_integer(
        criteria.maximum_monthly_exceptions, "maximum_monthly_exceptions"
    )


def _normalise_affiliate_ids(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EconomicsError("approved_affiliate_ids must be an iterable of IDs")
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise EconomicsError(
                f"approved_affiliate_ids[{index}] must be a non-empty string"
            )
        result.append(value.strip())
    return tuple(result)


def _boolean_check(
    name: str, passed: bool, *, observed: str, requirement: str
) -> GateCheck:
    return _threshold_check(name, passed, observed=observed, requirement=requirement)


def _threshold_check(
    name: str, passed: bool, *, observed: str, requirement: str
) -> GateCheck:
    return GateCheck(
        name=name,
        status=GateStatus.PASS if passed else GateStatus.FAIL,
        observed=observed,
        requirement=requirement,
    )


def _ceiling(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _positive_integer(value: int, field: str) -> int:
    result = _non_negative_integer(value, field)
    if result == 0:
        raise EconomicsError(f"{field} must be positive")
    return result


def _non_negative_integer(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EconomicsError(f"{field} must be a non-negative integer")
    return value


def _positive_ratio(value: Decimal, field: str) -> Decimal:
    result = _ratio(value, field)
    if result == 0:
        raise EconomicsError(f"{field} must be greater than zero")
    return result


def _ratio(value: Decimal, field: str) -> Decimal:
    result = _non_negative_decimal(value, field)
    if result > 1:
        raise EconomicsError(f"{field} must be between 0 and 1")
    return result


def _positive_decimal(value: Decimal, field: str) -> Decimal:
    result = _non_negative_decimal(value, field)
    if result == 0:
        raise EconomicsError(f"{field} must be greater than zero")
    return result


def _non_negative_decimal(value: Decimal, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise EconomicsError(f"{field} must use Decimal, not bool/float")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EconomicsError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise EconomicsError(f"{field} must be finite and non-negative")
    return result


def _currency(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isascii()
        or not value.isalpha()
        or value != value.upper()
    ):
        raise EconomicsError(f"{field} must be an uppercase three-letter currency code")
    return value
