"""Deterministic total-cost-of-ownership calculations for SaaS quotes.

The module deliberately does not know about persistence or extraction models.  A
caller may pass these frozen dataclasses or any object satisfying the protocols
below.  This keeps the calculation boundary small and makes it possible to
validate extracted data before it reaches the calculator.

Rounding rule
-------------
Each invoice line is first converted from major currency units to integer minor
units with ``ROUND_HALF_UP``.  Excluded tax is then calculated from that rounded
invoice line and is also rounded ``ROUND_HALF_UP`` to a whole minor unit.  The
rounded invoice occurrences are summed; totals are never rounded only once at
the end of the horizon.

No currency conversion or tax inference is performed.  Ambiguous tax,
currencies, billing periods, and usage units fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from enum import Enum
from typing import Iterable, Protocol, Sequence, runtime_checkable


class TcoError(ValueError):
    """Base class for invalid or incomplete TCO inputs."""


class CurrencyMismatchError(TcoError):
    """Raised when a quote would require currency conversion."""


class TaxInformationError(TcoError):
    """Raised when tax treatment or a required rate is unavailable."""


class UsageUnitMismatchError(TcoError):
    """Raised when scenario and quote usage units differ."""


class UnsupportedProrationError(TcoError):
    """Raised when an annual price would require an unspecified proration rule."""


class MissingUsagePricingError(TcoError):
    """Raised when non-zero usage cannot be priced from the quote."""


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class PriceBasis(str, Enum):
    FLAT = "flat"
    PER_SEAT = "per_seat"


class TaxTreatment(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ServerUseCase(str, Enum):
    """Reader-selectable, editorially approved server usage classes."""

    SMALL_SITE = "small_site"
    CORPORATE_SITE = "corporate_site"
    ECOMMERCE = "ecommerce"


class ServerPlanPriceStatus(str, Enum):
    """Whether a server plan has enough approved evidence to calculate."""

    KNOWN = "known"
    UNKNOWN = "unknown"


class ServerPlanReviewStatus(str, Enum):
    """Human review state used by the zero-input projection."""

    UNREVIEWED = "unreviewed"
    APPROVED = "approved"


@runtime_checkable
class TaxPolicyLike(Protocol):
    treatment: TaxTreatment | str
    rate: Decimal | None


@runtime_checkable
class RecurringChargeLike(Protocol):
    name: str
    amount: Decimal
    currency: str
    billing_period: BillingPeriod | str
    price_basis: PriceBasis | str
    minimum_seats: int
    included_seats: int
    maximum_seats: int | None


@runtime_checkable
class UsageChargeLike(Protocol):
    name: str
    included_quantity: Decimal
    included_basis: PriceBasis | str
    overage_unit_price: Decimal | None
    currency: str
    unit: str
    billing_period: BillingPeriod | str


@runtime_checkable
class PricingQuoteLike(Protocol):
    currency: str
    minor_unit_digits: int
    minimum_commitment_months: int
    base: RecurringChargeLike
    addons: Sequence[RecurringChargeLike]
    usage: UsageChargeLike | None
    tax: TaxPolicyLike


@dataclass(frozen=True, slots=True)
class TaxPolicy:
    treatment: TaxTreatment
    rate: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RecurringCharge:
    """A selected base-plan or add-on recurring charge.

    ``amount`` is the listed price for one billing occurrence.  For
    ``PER_SEAT`` it is the listed price for one billable seat per occurrence.
    """

    name: str
    amount: Decimal
    currency: str
    billing_period: BillingPeriod
    price_basis: PriceBasis = PriceBasis.FLAT
    minimum_seats: int = 1
    included_seats: int = 0
    maximum_seats: int | None = None


@dataclass(frozen=True, slots=True)
class UsageCharge:
    """Included usage and deterministic overage pricing.

    ``included_quantity`` applies to each ``billing_period``.  When
    ``included_basis`` is ``PER_SEAT``, the allowance is multiplied by the
    greater of requested seats and the base plan's minimum seats.
    """

    name: str
    included_quantity: Decimal
    overage_unit_price: Decimal | None
    currency: str
    unit: str
    billing_period: BillingPeriod = BillingPeriod.MONTHLY
    included_basis: PriceBasis = PriceBasis.FLAT


@dataclass(frozen=True, slots=True)
class PricingQuote:
    currency: str
    minor_unit_digits: int
    base: RecurringCharge
    tax: TaxPolicy
    minimum_commitment_months: int = 1
    addons: tuple[RecurringCharge, ...] = ()
    usage: UsageCharge | None = None


@dataclass(frozen=True, slots=True)
class UsageScenario:
    """The seats and measured usage for every month in the horizon."""

    seats: int
    monthly_usage: tuple[Decimal, ...]
    usage_unit: str | None = None

    @property
    def months(self) -> int:
        return len(self.monthly_usage)


@dataclass(frozen=True, slots=True)
class ServerTcoTerms:
    """Known server-specific charges layered onto a normal pricing quote.

    ``None`` means the Human-confirmed item is not applicable. Unknown values
    must not be passed to this calculator. Campaign pricing replaces the base
    monthly price for the stated first months. Domain pricing starts only after
    the confirmed included-benefit period. Every amount uses the quote currency
    and tax policy; mixed-currency or mixed-tax components require a separate
    quote and otherwise remain outside the calculation.
    """

    initial_fee: Decimal | None = None
    renewal_fee: Decimal | None = None
    renewal_due_month: int | None = None
    campaign_price: Decimal | None = None
    campaign_period_months: int | None = None
    domain_price: Decimal | None = None
    domain_billing_period: BillingPeriod | None = None
    domain_included_months: int | None = None


@dataclass(frozen=True, slots=True)
class ServerZeroInputPlan:
    """A display projection made only from a Human-reviewed price contract.

    ``quote`` and ``server_terms`` must both be absent for an unknown row.  A
    known row is still ineligible for calculation until its review status is
    approved.  ``eligible_use_cases`` is an explicit Human editorial decision;
    the calculator never infers suitability from price or plan names.
    """

    vendor_id: str
    plan_id: str
    display_name: str
    price_status: ServerPlanPriceStatus
    review_status: ServerPlanReviewStatus
    eligible_use_cases: tuple[ServerUseCase, ...]
    quote: PricingQuote | None = None
    server_terms: ServerTcoTerms | None = None
    unknown_reason: str | None = None
    confirmed_through_months: int | None = None
    horizon_unknown_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ServerZeroInputRow:
    vendor_id: str
    plan_id: str
    display_name: str
    status: str
    total_minor: int | None
    currency: str | None
    minor_unit_digits: int | None
    rank: int | None
    difference_from_lowest_minor: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class ServerZeroInputTable:
    months: int
    use_case: ServerUseCase
    comparison_mode: str
    confirmed_vendor_count: int
    rows: tuple[ServerZeroInputRow, ...]


@dataclass(frozen=True, slots=True)
class TcoLineItem:
    name: str
    kind: str
    listed_minor: int
    added_tax_minor: int
    total_minor: int
    billed_occurrences: int


@dataclass(frozen=True, slots=True)
class TcoResult:
    currency: str
    minor_unit_digits: int
    months: int
    seats: int
    listed_minor: int
    added_tax_minor: int
    total_minor: int
    line_items: tuple[TcoLineItem, ...]


def constant_usage_scenario(
    *, months: int = 12, seats: int, monthly_usage: Decimal, usage_unit: str | None
) -> UsageScenario:
    """Create a scenario with identical measured usage in each month."""

    if not isinstance(months, int) or isinstance(months, bool) or months <= 0:
        raise TcoError("months must be a positive integer")
    return UsageScenario(
        seats=seats,
        monthly_usage=tuple(Decimal(monthly_usage) for _ in range(months)),
        usage_unit=usage_unit,
    )


def calculate_tco(quote: PricingQuoteLike, scenario: UsageScenario) -> TcoResult:
    """Calculate a quote's deterministic gross TCO in integer minor units.

    Annual charges are accepted only for horizons divisible by 12 months.  The
    function refuses to invent an annual proration convention.
    """

    return _calculate_tco(quote, scenario, server_terms=None)


def calculate_server_tco(
    quote: PricingQuoteLike,
    scenario: UsageScenario,
    server_terms: ServerTcoTerms,
) -> TcoResult:
    """Calculate server TCO from explicit, Human-confirmed cost components.

    This function does not infer that a missing initial fee is zero, that a
    campaign continues, or that a free domain has a monetary value. Callers
    must keep any unknown component outside the calculator and HOLD the claim.
    """

    return _calculate_tco(quote, scenario, server_terms=server_terms)


def calculate_server_zero_input_table(
    plans: Sequence[ServerZeroInputPlan],
    *,
    months: int,
    use_case: ServerUseCase,
    article_review_approved: bool,
) -> ServerZeroInputTable:
    """Precompute a server comparison without accepting reader price inputs.

    Only 12/24/36-month horizons are supported. Unknown, unreviewed, or
    explicitly ineligible rows remain visible but are excluded from ranking.
    A ranking and first-place difference are emitted only when at least three
    distinct vendors have comparable, approved prices. Mixed currencies are
    calculated but not ranked because conversion is intentionally outside the
    canonical TCO boundary.
    """

    if months not in {12, 24, 36}:
        raise TcoError("server zero-input horizon must be 12, 24, or 36 months")
    if not isinstance(use_case, ServerUseCase):
        raise TcoError("server zero-input use case is invalid")

    identities = [(plan.vendor_id, plan.plan_id) for plan in plans]
    if len(identities) != len(set(identities)):
        raise TcoError("server zero-input plan identities must be unique")

    pending: list[ServerZeroInputRow] = []
    calculated: list[tuple[ServerZeroInputPlan, TcoResult]] = []
    for plan in plans:
        if not plan.vendor_id.strip() or not plan.plan_id.strip() or not plan.display_name.strip():
            raise TcoError("server zero-input plan identity cannot be blank")
        if plan.price_status is ServerPlanPriceStatus.UNKNOWN:
            if plan.quote is not None or plan.server_terms is not None:
                raise TcoError("unknown server plan cannot carry calculable price terms")
            if not plan.unknown_reason or not plan.unknown_reason.strip():
                raise TcoError("unknown server plan requires a reason")
            pending.append(
                ServerZeroInputRow(
                    vendor_id=plan.vendor_id,
                    plan_id=plan.plan_id,
                    display_name=plan.display_name,
                    status="unconfirmed",
                    total_minor=None,
                    currency=None,
                    minor_unit_digits=None,
                    rank=None,
                    difference_from_lowest_minor=None,
                    reason=plan.unknown_reason.strip(),
                )
            )
            continue
        if plan.quote is None or plan.server_terms is None:
            raise TcoError("known server plan requires quote and server terms")
        if plan.confirmed_through_months is not None:
            if plan.confirmed_through_months not in {12, 24, 36}:
                raise TcoError("confirmed server horizon must be 12, 24, or 36 months")
            if not plan.horizon_unknown_reason or not plan.horizon_unknown_reason.strip():
                raise TcoError("bounded server horizon requires an unknown reason")
            if months > plan.confirmed_through_months:
                pending.append(
                    ServerZeroInputRow(
                        vendor_id=plan.vendor_id,
                        plan_id=plan.plan_id,
                        display_name=plan.display_name,
                        status="unconfirmed",
                        total_minor=None,
                        currency=plan.quote.currency,
                        minor_unit_digits=plan.quote.minor_unit_digits,
                        rank=None,
                        difference_from_lowest_minor=None,
                        reason=plan.horizon_unknown_reason.strip(),
                    )
                )
                continue
        elif plan.horizon_unknown_reason is not None:
            raise TcoError("unbounded server horizon cannot carry an unknown reason")
        if not article_review_approved or plan.review_status is not ServerPlanReviewStatus.APPROVED:
            pending.append(
                ServerZeroInputRow(
                    vendor_id=plan.vendor_id,
                    plan_id=plan.plan_id,
                    display_name=plan.display_name,
                    status="unconfirmed",
                    total_minor=None,
                    currency=None,
                    minor_unit_digits=None,
                    rank=None,
                    difference_from_lowest_minor=None,
                    reason="Human承認前のため計算対象外",
                )
            )
            continue
        if use_case not in plan.eligible_use_cases:
            pending.append(
                ServerZeroInputRow(
                    vendor_id=plan.vendor_id,
                    plan_id=plan.plan_id,
                    display_name=plan.display_name,
                    status="ineligible",
                    total_minor=None,
                    currency=plan.quote.currency,
                    minor_unit_digits=plan.quote.minor_unit_digits,
                    rank=None,
                    difference_from_lowest_minor=None,
                    reason="選択した用途区分の承認対象外",
                )
            )
            continue
        scenario = constant_usage_scenario(
            months=months,
            seats=1,
            monthly_usage=Decimal(0),
            usage_unit=None,
        )
        calculated.append((plan, calculate_server_tco(plan.quote, scenario, plan.server_terms)))

    currencies = {result.currency for _, result in calculated}
    confirmed_vendor_count = len({plan.vendor_id for plan, _ in calculated})
    currencies_comparable = len(currencies) <= 1
    ranking_enabled = currencies_comparable and confirmed_vendor_count >= 3
    rank_by_identity: dict[tuple[str, str], int] = {}
    lowest_total_minor: int | None = None
    if ranking_enabled:
        lowest_total_minor = min(result.total_minor for _, result in calculated)
        for rank, (plan, _) in enumerate(
            sorted(calculated, key=lambda item: (item[1].total_minor, item[0].display_name)),
            start=1,
        ):
            rank_by_identity[(plan.vendor_id, plan.plan_id)] = rank

    calculated_rows = [
        ServerZeroInputRow(
            vendor_id=plan.vendor_id,
            plan_id=plan.plan_id,
            display_name=plan.display_name,
            total_minor=result.total_minor,
            currency=result.currency,
            minor_unit_digits=result.minor_unit_digits,
            rank=rank_by_identity.get((plan.vendor_id, plan.plan_id)),
            difference_from_lowest_minor=(
                result.total_minor - lowest_total_minor
                if ranking_enabled and lowest_total_minor is not None
                else None
            ),
            reason=(
                None
                if ranking_enabled
                else "確認済みvendorが3社未満のため順位なし"
                if currencies_comparable
                else "通貨換算を行わないため順位なし"
            ),
            status=(
                "ranked"
                if ranking_enabled
                else "confirmed_unranked"
                if currencies_comparable
                else "currency_mismatch"
            ),
        )
        for plan, result in calculated
    ]
    rows_by_identity = {
        (row.vendor_id, row.plan_id): row for row in (*calculated_rows, *pending)
    }
    return ServerZeroInputTable(
        months=months,
        use_case=use_case,
        comparison_mode="ranked_comparison" if ranking_enabled else "confirmed_list",
        confirmed_vendor_count=confirmed_vendor_count,
        rows=tuple(rows_by_identity[identity] for identity in identities),
    )


def _calculate_tco(
    quote: PricingQuoteLike,
    scenario: UsageScenario,
    *,
    server_terms: ServerTcoTerms | None,
) -> TcoResult:
    currency = _normalise_currency(quote.currency, field="quote.currency")
    digits = _validate_minor_unit_digits(quote.minor_unit_digits)
    months = scenario.months
    seats = _validate_seats(scenario.seats)
    commitment_months = _validate_commitment_months(
        quote.minimum_commitment_months
    )
    usage_values = tuple(
        _non_negative_decimal(value, f"monthly_usage[{index}]")
        for index, value in enumerate(scenario.monthly_usage)
    )
    if months <= 0:
        raise TcoError("scenario must contain at least one month of usage")
    if months < commitment_months:
        raise UnsupportedProrationError(
            f"{months}-month horizon is shorter than the "
            f"{commitment_months}-month minimum commitment"
        )

    treatment, rate = _validate_tax_policy(quote.tax)
    line_items: list[TcoLineItem] = []
    validated_server_terms = (
        None
        if server_terms is None
        else _validate_server_terms(server_terms, quote=quote)
    )

    if (
        validated_server_terms is not None
        and validated_server_terms.initial_fee is not None
    ):
        line_items.append(
            _price_fixed(
                name="initial fee",
                kind="server.initial_fee",
                amount=validated_server_terms.initial_fee,
                billed=True,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )

    base = quote.base
    base_minimum = _validate_minimum_seats(base.minimum_seats, "base.minimum_seats")
    if (
        validated_server_terms is None
        or validated_server_terms.campaign_price is None
    ):
        line_items.append(
            _price_recurring(
                charge=base,
                kind="base",
                months=months,
                seats=seats,
                quote_currency=currency,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )
    else:
        assert validated_server_terms.campaign_period_months is not None
        campaign_months = min(
            months,
            validated_server_terms.campaign_period_months,
        )
        campaign_charge = RecurringCharge(
            name=f"{base.name} (campaign)",
            amount=validated_server_terms.campaign_price,
            currency=currency,
            billing_period=BillingPeriod.MONTHLY,
            price_basis=_coerce_enum(
                PriceBasis,
                base.price_basis,
                "base.price_basis",
            ),
            minimum_seats=base.minimum_seats,
            included_seats=base.included_seats,
            maximum_seats=base.maximum_seats,
        )
        line_items.append(
            _price_recurring(
                charge=campaign_charge,
                kind="base.campaign",
                months=campaign_months,
                seats=seats,
                quote_currency=currency,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )
        regular_months = months - campaign_months
        if regular_months:
            line_items.append(
                _price_recurring(
                    charge=base,
                    kind="base.regular",
                    months=regular_months,
                    seats=seats,
                    quote_currency=currency,
                    digits=digits,
                    treatment=treatment,
                    tax_rate=rate,
                )
            )

    for index, addon in enumerate(tuple(quote.addons)):
        line_items.append(
            _price_recurring(
                charge=addon,
                kind=f"addon[{index}]",
                months=months,
                seats=seats,
                quote_currency=currency,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )

    if quote.usage is None:
        if any(value != 0 for value in usage_values):
            raise MissingUsagePricingError(
                "scenario contains usage but the quote has no usage pricing"
            )
    else:
        line_items.append(
            _price_usage(
                usage=quote.usage,
                usage_values=usage_values,
                usage_unit=scenario.usage_unit,
                months=months,
                seats=seats,
                base_minimum_seats=base_minimum,
                quote_currency=currency,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )

    if (
        validated_server_terms is not None
        and validated_server_terms.renewal_fee is not None
    ):
        assert validated_server_terms.renewal_due_month is not None
        line_items.append(
            _price_fixed(
                name="renewal fee",
                kind="server.renewal_fee",
                amount=validated_server_terms.renewal_fee,
                billed=validated_server_terms.renewal_due_month <= months,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )

    if (
        validated_server_terms is not None
        and validated_server_terms.domain_price is not None
    ):
        assert validated_server_terms.domain_billing_period is not None
        assert validated_server_terms.domain_included_months is not None
        billable_domain_months = max(
            months - validated_server_terms.domain_included_months,
            0,
        )
        line_items.append(
            _price_recurring(
                charge=RecurringCharge(
                    name="domain after included benefit",
                    amount=validated_server_terms.domain_price,
                    currency=currency,
                    billing_period=validated_server_terms.domain_billing_period,
                ),
                kind="server.domain",
                months=billable_domain_months,
                seats=1,
                quote_currency=currency,
                digits=digits,
                treatment=treatment,
                tax_rate=rate,
            )
        )

    listed_minor = sum(item.listed_minor for item in line_items)
    added_tax_minor = sum(item.added_tax_minor for item in line_items)
    return TcoResult(
        currency=currency,
        minor_unit_digits=digits,
        months=months,
        seats=seats,
        listed_minor=listed_minor,
        added_tax_minor=added_tax_minor,
        total_minor=listed_minor + added_tax_minor,
        line_items=tuple(line_items),
    )


def _validate_server_terms(
    terms: ServerTcoTerms,
    *,
    quote: PricingQuoteLike,
) -> ServerTcoTerms:
    initial_fee = (
        None
        if terms.initial_fee is None
        else _non_negative_decimal(terms.initial_fee, "server.initial_fee")
    )

    renewal_values = (terms.renewal_fee, terms.renewal_due_month)
    if (renewal_values[0] is None) != (renewal_values[1] is None):
        raise TcoError("server renewal fee and due month must be supplied together")
    renewal_fee = (
        None
        if terms.renewal_fee is None
        else _non_negative_decimal(terms.renewal_fee, "server.renewal_fee")
    )
    renewal_due_month = (
        None
        if terms.renewal_due_month is None
        else _validate_positive_month(
            terms.renewal_due_month,
            "server.renewal_due_month",
        )
    )

    campaign_values = (terms.campaign_price, terms.campaign_period_months)
    if (campaign_values[0] is None) != (campaign_values[1] is None):
        raise TcoError("server campaign price and period must be supplied together")
    campaign_price = (
        None
        if terms.campaign_price is None
        else _non_negative_decimal(terms.campaign_price, "server.campaign_price")
    )
    campaign_period_months = (
        None
        if terms.campaign_period_months is None
        else _validate_positive_month(
            terms.campaign_period_months,
            "server.campaign_period_months",
        )
    )
    if campaign_price is not None:
        base_period = _coerce_enum(
            BillingPeriod,
            quote.base.billing_period,
            "base.billing_period",
        )
        if base_period is not BillingPeriod.MONTHLY:
            raise UnsupportedProrationError(
                "server campaign pricing currently requires an observed monthly base price"
            )
        base_amount = _non_negative_decimal(quote.base.amount, "base.amount")
        if campaign_price > base_amount:
            raise TcoError("server campaign price cannot exceed the observed regular price")

    domain_values = (
        terms.domain_price,
        terms.domain_billing_period,
        terms.domain_included_months,
    )
    if any(value is None for value in domain_values) and any(
        value is not None for value in domain_values
    ):
        raise TcoError(
            "server domain price, billing period, and included months must be supplied together"
        )
    domain_price = (
        None
        if terms.domain_price is None
        else _non_negative_decimal(terms.domain_price, "server.domain_price")
    )
    domain_billing_period = (
        None
        if terms.domain_billing_period is None
        else _coerce_enum(
            BillingPeriod,
            terms.domain_billing_period,
            "server.domain_billing_period",
        )
    )
    domain_included_months = (
        None
        if terms.domain_included_months is None
        else _validate_non_negative_month(
            terms.domain_included_months,
            "server.domain_included_months",
        )
    )

    return ServerTcoTerms(
        initial_fee=initial_fee,
        renewal_fee=renewal_fee,
        renewal_due_month=renewal_due_month,
        campaign_price=campaign_price,
        campaign_period_months=campaign_period_months,
        domain_price=domain_price,
        domain_billing_period=domain_billing_period,
        domain_included_months=domain_included_months,
    )


def calculate_vendor_plan_tco(
    plan: object,
    scenario: UsageScenario,
    *,
    minor_unit_digits: int | None = None,
    selected_addon_codes: Iterable[str] = (),
) -> TcoResult:
    """Adapt the storage-layer ``VendorPlan`` shape without importing it.

    The adapter intentionally uses structural attribute access so the storage
    model remains an independent boundary.  A flat plan treats ``base_price`` as
    its fixed recurring price.  For a Phase-1 per-seat plan, ``base_price`` must
    equal ``seat_pricing.unit_price`` and is multiplied by billable seats; it is
    not added again as a platform fee.  Hybrid platform-fee plans are outside the
    Phase-1 schema and fail closed here.

    The storage contract owns the reset period of a usage allowance through
    ``UsageAllowance.billing_period``. Per-usage add-ons are rejected because
    the shared scenario has no add-on-specific quantities; flat and per-seat
    add-ons are supported.
    Required add-ons are always included. Optional add-ons are included only
    when their code is present in ``selected_addon_codes``. Unknown and
    duplicate selections fail closed.
    """

    try:
        currency = getattr(plan, "currency")
        period = getattr(plan, "billing_period")
        pricing_model = getattr(plan, "pricing_model")
        commitment_months = getattr(plan, "commitment_months")
        base_price = getattr(plan, "base_price")
        tax = getattr(plan, "tax")
    except AttributeError as exc:
        raise TcoError(f"VendorPlan-compatible object is missing {exc.name!r}") from exc

    if (
        not isinstance(commitment_months, int)
        or isinstance(commitment_months, bool)
        or commitment_months <= 0
    ):
        raise TcoError("commitment_months must be a positive integer")
    if scenario.months < commitment_months:
        raise UnsupportedProrationError(
            f"{scenario.months}-month horizon is shorter than the "
            f"{commitment_months}-month commitment"
        )

    if minor_unit_digits is None:
        try:
            minor_unit_digits = getattr(plan, "minor_unit_digits")
        except AttributeError as exc:
            raise TcoError(
                "minor_unit_digits must be supplied or present on VendorPlan"
            ) from exc

    recurring: list[RecurringCharge] = []
    model = _coerce_enum(PriceBasis, pricing_model, "plan.pricing_model")
    if model is PriceBasis.PER_SEAT:
        seat_pricing = getattr(plan, "seat_pricing", None)
        if seat_pricing is None:
            raise TcoError("per-seat plan requires seat_pricing")
        unit_price = _non_negative_decimal(
            getattr(seat_pricing, "unit_price"), "seat_pricing.unit_price"
        )
        normalised_base_price = _non_negative_decimal(base_price, "plan.base_price")
        if unit_price != normalised_base_price:
            raise TcoError(
                "Phase-1 per-seat plan requires base_price == seat_pricing.unit_price"
            )
        if getattr(seat_pricing, "included_seats") != 0:
            raise TcoError(
                "Phase-1 per-seat plan requires included_seats == 0; hybrid pricing is unsupported"
            )
        base_charge = RecurringCharge(
            name="base price",
            amount=normalised_base_price,
            currency=currency,
            billing_period=period,
            price_basis=PriceBasis.PER_SEAT,
            minimum_seats=getattr(seat_pricing, "minimum_seats"),
            included_seats=0,
            maximum_seats=getattr(seat_pricing, "maximum_seats"),
        )
    else:
        base_charge = RecurringCharge(
            name="base price",
            amount=base_price,
            currency=currency,
            billing_period=period,
        )

    addons = tuple(getattr(plan, "addons", ()))
    selected_codes = _normalise_selected_addon_codes(selected_addon_codes)
    available_codes: set[str] = set()
    for index, addon in enumerate(addons):
        code = _normalise_addon_code(getattr(addon, "code"), f"addon[{index}].code")
        if code in available_codes:
            raise TcoError(f"duplicate add-on code in plan: {code!r}")
        available_codes.add(code)
    unknown_codes = selected_codes - available_codes
    if unknown_codes:
        rendered = ", ".join(sorted(unknown_codes))
        raise TcoError(f"unknown selected add-on code(s): {rendered}")

    for index, addon in enumerate(addons):
        code = _normalise_addon_code(getattr(addon, "code"), f"addon[{index}].code")
        required = getattr(addon, "required")
        if not isinstance(required, bool):
            raise TcoError(f"addon[{index}].required must be boolean")
        if not required and code not in selected_codes:
            continue
        addon_model_raw = getattr(addon, "pricing_model")
        addon_model_value = (
            addon_model_raw.value if isinstance(addon_model_raw, Enum) else addon_model_raw
        )
        if addon_model_value == "per_usage":
            raise MissingUsagePricingError(
                f"addon[{index}] is per_usage but no add-on-specific quantity was supplied"
            )
        addon_model = _coerce_enum(
            PriceBasis, addon_model_raw, f"addon[{index}].pricing_model"
        )
        recurring.append(
            RecurringCharge(
                name=str(getattr(addon, "name")),
                amount=getattr(addon, "unit_price"),
                currency=currency,
                billing_period=getattr(addon, "billing_period"),
                price_basis=addon_model,
            )
        )

    usage_allowance = getattr(plan, "usage_allowance", None)
    usage_charge: UsageCharge | None = None
    if usage_allowance is not None:
        usage_charge = UsageCharge(
            name="usage overage",
            included_quantity=getattr(usage_allowance, "included_quantity"),
            overage_unit_price=getattr(usage_allowance, "overage_unit_price"),
            currency=currency,
            unit=str(getattr(usage_allowance, "unit_name")),
            billing_period=getattr(usage_allowance, "billing_period"),
        )

    quote = PricingQuote(
        currency=currency,
        minor_unit_digits=minor_unit_digits,
        base=base_charge,
        addons=tuple(recurring),
        usage=usage_charge,
        tax=TaxPolicy(
            treatment=getattr(tax, "treatment"),
            rate=getattr(tax, "rate"),
        ),
        minimum_commitment_months=commitment_months,
    )
    return calculate_tco(quote, scenario)


def _price_recurring(
    *,
    charge: RecurringChargeLike,
    kind: str,
    months: int,
    seats: int,
    quote_currency: str,
    digits: int,
    treatment: TaxTreatment,
    tax_rate: Decimal | None,
) -> TcoLineItem:
    _require_currency(charge.currency, quote_currency, f"{kind}.currency")
    amount = _non_negative_decimal(charge.amount, f"{kind}.amount")
    minimum_seats = _validate_minimum_seats(
        charge.minimum_seats, f"{kind}.minimum_seats"
    )
    included_seats = _validate_included_seats(
        charge.included_seats, f"{kind}.included_seats"
    )
    maximum_seats = _validate_maximum_seats(
        charge.maximum_seats, minimum_seats, f"{kind}.maximum_seats"
    )
    basis = _coerce_enum(PriceBasis, charge.price_basis, f"{kind}.price_basis")
    period = _coerce_enum(
        BillingPeriod, charge.billing_period, f"{kind}.billing_period"
    )
    occurrences = _billing_occurrences(period, months, kind)
    if basis is PriceBasis.PER_SEAT:
        if maximum_seats is not None and seats > maximum_seats:
            raise TcoError(
                f"{kind} supports at most {maximum_seats} seats, got {seats}"
            )
        quantity = max(max(seats, minimum_seats) - included_seats, 0)
    else:
        quantity = 1
    invoice_minor = _major_to_minor(amount * quantity, digits)
    invoice_tax_minor = _added_tax_minor(invoice_minor, treatment, tax_rate)
    listed = invoice_minor * occurrences
    added_tax = invoice_tax_minor * occurrences
    return TcoLineItem(
        name=str(charge.name),
        kind=kind,
        listed_minor=listed,
        added_tax_minor=added_tax,
        total_minor=listed + added_tax,
        billed_occurrences=occurrences,
    )


def _price_fixed(
    *,
    name: str,
    kind: str,
    amount: Decimal,
    billed: bool,
    digits: int,
    treatment: TaxTreatment,
    tax_rate: Decimal | None,
) -> TcoLineItem:
    invoice_minor = _major_to_minor(amount, digits) if billed else 0
    added_tax = _added_tax_minor(invoice_minor, treatment, tax_rate)
    return TcoLineItem(
        name=name,
        kind=kind,
        listed_minor=invoice_minor,
        added_tax_minor=added_tax,
        total_minor=invoice_minor + added_tax,
        billed_occurrences=1 if billed else 0,
    )


def _price_usage(
    *,
    usage: UsageChargeLike,
    usage_values: tuple[Decimal, ...],
    usage_unit: str | None,
    months: int,
    seats: int,
    base_minimum_seats: int,
    quote_currency: str,
    digits: int,
    treatment: TaxTreatment,
    tax_rate: Decimal | None,
) -> TcoLineItem:
    _require_currency(usage.currency, quote_currency, "usage.currency")
    quote_unit = _normalise_unit(usage.unit, "usage.unit")
    scenario_unit = _normalise_unit(usage_unit, "scenario.usage_unit")
    if quote_unit != scenario_unit:
        raise UsageUnitMismatchError(
            f"usage unit mismatch: quote={quote_unit!r}, scenario={scenario_unit!r}"
        )

    included = _non_negative_decimal(
        usage.included_quantity, "usage.included_quantity"
    )
    overage_price = (
        None
        if usage.overage_unit_price is None
        else _non_negative_decimal(usage.overage_unit_price, "usage.overage_unit_price")
    )
    included_basis = _coerce_enum(
        PriceBasis, usage.included_basis, "usage.included_basis"
    )
    if included_basis is PriceBasis.PER_SEAT:
        included *= max(seats, base_minimum_seats)
    period = _coerce_enum(
        BillingPeriod, usage.billing_period, "usage.billing_period"
    )
    windows = _usage_windows(period, usage_values, months)

    listed = 0
    added_tax = 0
    for measured in windows:
        overage_quantity = max(measured - included, Decimal(0))
        if overage_quantity and overage_price is None:
            raise MissingUsagePricingError(
                "usage exceeds the included allowance but no overage unit price is known"
            )
        effective_overage_price = overage_price or Decimal(0)
        invoice_minor = _major_to_minor(
            overage_quantity * effective_overage_price, digits
        )
        listed += invoice_minor
        added_tax += _added_tax_minor(invoice_minor, treatment, tax_rate)
    return TcoLineItem(
        name=str(usage.name),
        kind="usage",
        listed_minor=listed,
        added_tax_minor=added_tax,
        total_minor=listed + added_tax,
        billed_occurrences=len(windows),
    )


def _usage_windows(
    period: BillingPeriod, values: tuple[Decimal, ...], months: int
) -> tuple[Decimal, ...]:
    if period is BillingPeriod.MONTHLY:
        return values
    _billing_occurrences(period, months, "usage")
    return tuple(sum(values[index : index + 12], Decimal(0)) for index in range(0, months, 12))


def _billing_occurrences(period: BillingPeriod, months: int, field: str) -> int:
    if period is BillingPeriod.MONTHLY:
        return months
    if months % 12:
        raise UnsupportedProrationError(
            f"{field} is annual but {months} months would require an unspecified proration rule"
        )
    return months // 12


def _major_to_minor(amount: Decimal, digits: int) -> int:
    multiplier = Decimal(10) ** digits
    with localcontext() as context:
        context.prec = max(50, len(amount.as_tuple().digits) + digits + 10)
        try:
            return int((amount * multiplier).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        except InvalidOperation as exc:
            raise TcoError(f"amount cannot be rounded to minor units: {amount!r}") from exc


def _added_tax_minor(
    invoice_minor: int, treatment: TaxTreatment, tax_rate: Decimal | None
) -> int:
    if treatment in (TaxTreatment.INCLUDED, TaxTreatment.NOT_APPLICABLE):
        return 0
    # Validation guarantees an excluded rate is present.
    assert tax_rate is not None
    return int(
        (Decimal(invoice_minor) * tax_rate).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def _validate_tax_policy(
    policy: TaxPolicyLike,
) -> tuple[TaxTreatment, Decimal | None]:
    treatment = _coerce_enum(TaxTreatment, policy.treatment, "tax.treatment")
    if treatment is TaxTreatment.UNKNOWN:
        raise TaxInformationError("tax treatment is unknown")
    if treatment is TaxTreatment.EXCLUDED and policy.rate is None:
        raise TaxInformationError("tax-excluded pricing requires an explicit tax rate")
    if treatment is TaxTreatment.NOT_APPLICABLE and policy.rate is not None:
        raise TaxInformationError("not-applicable tax cannot have a tax rate")
    if policy.rate is None:
        return treatment, None
    rate = _non_negative_decimal(policy.rate, "tax.rate")
    if rate > 1:
        raise TaxInformationError("tax.rate must be a decimal fraction between 0 and 1")
    return treatment, rate


def _validate_minor_unit_digits(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 6:
        raise TcoError("minor_unit_digits must be an integer between 0 and 6")
    return value


def _validate_commitment_months(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TcoError("minimum_commitment_months must be a positive integer")
    return value


def _validate_seats(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TcoError("seats must be a positive integer")
    return value


def _validate_positive_month(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TcoError(f"{field} must be a positive integer")
    return value


def _validate_non_negative_month(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TcoError(f"{field} must be a non-negative integer")
    return value


def _validate_minimum_seats(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TcoError(f"{field} must be a positive integer")
    return value


def _validate_included_seats(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TcoError(f"{field} must be a non-negative integer")
    return value


def _validate_maximum_seats(
    value: int | None, minimum_seats: int, field: str
) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TcoError(f"{field} must be a positive integer or None")
    if value < minimum_seats:
        raise TcoError(f"{field} cannot be less than minimum_seats")
    return value


def _non_negative_decimal(value: Decimal, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TcoError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise TcoError(f"{field} must be finite and non-negative")
    return result


def _normalise_currency(value: str, *, field: str) -> str:
    if not isinstance(value, str) or len(value.strip()) != 3:
        raise TcoError(f"{field} must be a three-letter currency code")
    return value.strip().upper()


def _require_currency(value: str, expected: str, field: str) -> None:
    actual = _normalise_currency(value, field=field)
    if actual != expected:
        raise CurrencyMismatchError(
            f"currency mismatch: quote={expected!r}, {field}={actual!r}; conversion is disabled"
        )


def _normalise_unit(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UsageUnitMismatchError(f"{field} must be an explicit non-empty unit")
    return value.strip().lower()


def _normalise_selected_addon_codes(values: Iterable[str]) -> set[str]:
    if isinstance(values, (str, bytes)):
        raise TcoError("selected_addon_codes must be an iterable of codes, not a string")
    normalised: list[str] = []
    for index, value in enumerate(values):
        normalised.append(_normalise_addon_code(value, f"selected_addon_codes[{index}]"))
    if len(normalised) != len(set(normalised)):
        raise TcoError("selected_addon_codes contains duplicate codes")
    return set(normalised)


def _normalise_addon_code(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TcoError(f"{field} must be a non-empty string")
    return value.strip()


def _coerce_enum(enum_type: type[Enum], value: object, field: str):
    raw = value.value if isinstance(value, Enum) else value
    try:
        return enum_type(raw)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise TcoError(f"{field} must be one of: {allowed}") from exc
