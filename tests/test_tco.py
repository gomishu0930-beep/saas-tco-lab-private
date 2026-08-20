from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from saas_preflight.tco import (
    BillingPeriod,
    CurrencyMismatchError,
    MissingUsagePricingError,
    PriceBasis,
    PricingQuote,
    RecurringCharge,
    ServerPlanPriceStatus,
    ServerPlanReviewStatus,
    ServerTcoTerms,
    ServerUseCase,
    ServerZeroInputPlan,
    TaxInformationError,
    TaxPolicy,
    TaxTreatment,
    TcoError,
    UnsupportedProrationError,
    UsageCharge,
    UsageScenario,
    UsageUnitMismatchError,
    calculate_server_tco,
    calculate_server_zero_input_table,
    calculate_tco,
    calculate_vendor_plan_tco,
    constant_usage_scenario,
)


def _scenario(
    *, seats: int = 1, usage: Decimal = Decimal(0), unit: str | None = None
) -> UsageScenario:
    return constant_usage_scenario(
        months=12, seats=seats, monthly_usage=usage, usage_unit=unit
    )


def _quote(
    *,
    amount: Decimal = Decimal("1000"),
    billing_period: BillingPeriod = BillingPeriod.MONTHLY,
    price_basis: PriceBasis = PriceBasis.FLAT,
    minimum_seats: int = 1,
    included_seats: int = 0,
    maximum_seats: int | None = None,
    addons: tuple[RecurringCharge, ...] = (),
    usage: UsageCharge | None = None,
    tax: TaxPolicy = TaxPolicy(TaxTreatment.NOT_APPLICABLE),
    currency: str = "JPY",
    digits: int = 0,
    commitment: int = 1,
) -> PricingQuote:
    return PricingQuote(
        currency=currency,
        minor_unit_digits=digits,
        minimum_commitment_months=commitment,
        base=RecurringCharge(
            name="base",
            amount=amount,
            currency=currency,
            billing_period=billing_period,
            price_basis=price_basis,
            minimum_seats=minimum_seats,
            included_seats=included_seats,
            maximum_seats=maximum_seats,
        ),
        addons=addons,
        usage=usage,
        tax=tax,
    )


def test_flat_monthly_twelve_month_tco() -> None:
    result = calculate_tco(_quote(), _scenario())

    assert result.total_minor == 12_000
    assert result.months == 12
    assert result.line_items[0].billed_occurrences == 12


def test_server_zero_input_table_keeps_two_vendors_as_confirmed_list() -> None:
    plans = (
        ServerZeroInputPlan(
            vendor_id="alpha",
            plan_id="basic",
            display_name="Alpha Basic",
            price_status=ServerPlanPriceStatus.KNOWN,
            review_status=ServerPlanReviewStatus.APPROVED,
            eligible_use_cases=(ServerUseCase.SMALL_SITE,),
            quote=_quote(amount=Decimal("1000")),
            server_terms=ServerTcoTerms(),
        ),
        ServerZeroInputPlan(
            vendor_id="beta",
            plan_id="business",
            display_name="Beta Business",
            price_status=ServerPlanPriceStatus.KNOWN,
            review_status=ServerPlanReviewStatus.APPROVED,
            eligible_use_cases=(ServerUseCase.SMALL_SITE, ServerUseCase.CORPORATE_SITE),
            quote=_quote(amount=Decimal("1500")),
            server_terms=ServerTcoTerms(),
        ),
        ServerZeroInputPlan(
            vendor_id="gamma",
            plan_id="unknown",
            display_name="Gamma 未確認プラン",
            price_status=ServerPlanPriceStatus.UNKNOWN,
            review_status=ServerPlanReviewStatus.UNREVIEWED,
            eligible_use_cases=(),
            unknown_reason="更新料が未確認",
        ),
    )

    table = calculate_server_zero_input_table(
        plans,
        months=24,
        use_case=ServerUseCase.SMALL_SITE,
        article_review_approved=True,
    )

    assert [row.total_minor for row in table.rows] == [24_000, 36_000, None]
    assert table.comparison_mode == "confirmed_list"
    assert table.confirmed_vendor_count == 2
    assert [row.rank for row in table.rows] == [None, None, None]
    assert [row.difference_from_lowest_minor for row in table.rows] == [None, None, None]
    assert [row.status for row in table.rows] == ["confirmed_unranked", "confirmed_unranked", "unconfirmed"]
    assert table.rows[0].reason == "確認済みvendorが3社未満のため順位なし"
    assert table.rows[2].reason == "更新料が未確認"


def test_server_zero_input_table_ranks_three_vendors_and_derives_first_place_difference() -> None:
    plans = tuple(
        ServerZeroInputPlan(
            vendor_id=vendor_id,
            plan_id="business",
            display_name=display_name,
            price_status=ServerPlanPriceStatus.KNOWN,
            review_status=ServerPlanReviewStatus.APPROVED,
            eligible_use_cases=(ServerUseCase.CORPORATE_SITE,),
            quote=_quote(amount=amount),
            server_terms=ServerTcoTerms(),
        )
        for vendor_id, display_name, amount in (
            ("alpha", "Alpha", Decimal("1000")),
            ("beta", "Beta", Decimal("1500")),
            ("gamma", "Gamma", Decimal("1250")),
        )
    )

    table = calculate_server_zero_input_table(
        plans,
        months=12,
        use_case=ServerUseCase.CORPORATE_SITE,
        article_review_approved=True,
    )

    assert table.comparison_mode == "ranked_comparison"
    assert table.confirmed_vendor_count == 3
    assert [row.rank for row in table.rows] == [1, 3, 2]
    assert [row.difference_from_lowest_minor for row in table.rows] == [0, 6_000, 3_000]


def test_server_zero_input_table_filters_use_case_and_article_review() -> None:
    plan = ServerZeroInputPlan(
        vendor_id="alpha",
        plan_id="basic",
        display_name="Alpha Basic",
        price_status=ServerPlanPriceStatus.KNOWN,
        review_status=ServerPlanReviewStatus.APPROVED,
        eligible_use_cases=(ServerUseCase.SMALL_SITE,),
        quote=_quote(),
        server_terms=ServerTcoTerms(),
    )

    ineligible = calculate_server_zero_input_table(
        (plan,),
        months=12,
        use_case=ServerUseCase.ECOMMERCE,
        article_review_approved=True,
    )
    assert ineligible.rows[0].status == "ineligible"
    assert ineligible.rows[0].rank is None

    unreviewed = calculate_server_zero_input_table(
        (plan,),
        months=12,
        use_case=ServerUseCase.SMALL_SITE,
        article_review_approved=False,
    )
    assert unreviewed.rows[0].status == "unconfirmed"
    assert unreviewed.rows[0].total_minor is None


@pytest.mark.parametrize(("months", "expected"), [(12, 12_000), (24, 24_000), (36, 36_000)])
def test_server_zero_input_table_uses_canonical_horizons(months: int, expected: int) -> None:
    plan = ServerZeroInputPlan(
        vendor_id="alpha",
        plan_id="basic",
        display_name="Alpha Basic",
        price_status=ServerPlanPriceStatus.KNOWN,
        review_status=ServerPlanReviewStatus.APPROVED,
        eligible_use_cases=(ServerUseCase.CORPORATE_SITE,),
        quote=_quote(),
        server_terms=ServerTcoTerms(),
    )
    table = calculate_server_zero_input_table(
        (plan,),
        months=months,
        use_case=ServerUseCase.CORPORATE_SITE,
        article_review_approved=True,
    )
    assert table.rows[0].total_minor == expected
    assert table.rows[0].rank is None
    assert table.rows[0].difference_from_lowest_minor is None


def test_server_zero_input_table_holds_beyond_human_confirmed_horizon() -> None:
    plan = ServerZeroInputPlan(
        vendor_id="alpha",
        plan_id="annual-first-year",
        display_name="Alpha 12か月確認済み",
        price_status=ServerPlanPriceStatus.KNOWN,
        review_status=ServerPlanReviewStatus.APPROVED,
        eligible_use_cases=(ServerUseCase.SMALL_SITE,),
        quote=_quote(amount=Decimal("12000"), billing_period=BillingPeriod.ANNUAL),
        server_terms=ServerTcoTerms(initial_fee=Decimal("1000")),
        confirmed_through_months=12,
        horizon_unknown_reason="更新時請求総額が未確認のため24か月・36か月は計算しません",
    )

    first_year = calculate_server_zero_input_table(
        (plan,),
        months=12,
        use_case=ServerUseCase.SMALL_SITE,
        article_review_approved=True,
    )
    second_year = calculate_server_zero_input_table(
        (plan,),
        months=24,
        use_case=ServerUseCase.SMALL_SITE,
        article_review_approved=True,
    )

    assert first_year.rows[0].total_minor == 13_000
    assert second_year.rows[0].total_minor is None
    assert second_year.rows[0].status == "unconfirmed"
    assert second_year.rows[0].reason == plan.horizon_unknown_reason


def test_monthly_and_annual_fixture_are_equivalent() -> None:
    monthly = calculate_tco(_quote(amount=Decimal("1000")), _scenario())
    annual = calculate_tco(
        _quote(amount=Decimal("12000"), billing_period=BillingPeriod.ANNUAL),
        _scenario(),
    )

    assert monthly.total_minor == annual.total_minor == 12_000


def test_per_seat_minimum_and_included_seats() -> None:
    result = calculate_tco(
        _quote(
            amount=Decimal("100"),
            price_basis=PriceBasis.PER_SEAT,
            minimum_seats=5,
            included_seats=2,
        ),
        _scenario(seats=1),
    )

    # max(requested=1, minimum=5) - included=2 => 3 billed seats.
    assert result.total_minor == 3 * 100 * 12


def test_flat_and_per_seat_addons() -> None:
    addons = (
        RecurringCharge(
            name="support",
            amount=Decimal("500"),
            currency="JPY",
            billing_period=BillingPeriod.MONTHLY,
        ),
        RecurringCharge(
            name="audit",
            amount=Decimal("100"),
            currency="JPY",
            billing_period=BillingPeriod.MONTHLY,
            price_basis=PriceBasis.PER_SEAT,
        ),
    )

    result = calculate_tco(_quote(addons=addons), _scenario(seats=3))

    assert result.total_minor == (1000 + 500 + 3 * 100) * 12


def test_monthly_included_usage_and_overage() -> None:
    usage = UsageCharge(
        name="events",
        included_quantity=Decimal("100"),
        overage_unit_price=Decimal("2"),
        currency="JPY",
        unit="event",
    )

    result = calculate_tco(
        _quote(amount=Decimal(0), usage=usage),
        _scenario(usage=Decimal("110"), unit="event"),
    )

    assert result.total_minor == 10 * 2 * 12
    assert result.line_items[-1].billed_occurrences == 12


def test_annual_usage_allowance() -> None:
    usage = UsageCharge(
        name="events",
        included_quantity=Decimal("1200"),
        overage_unit_price=Decimal("2"),
        currency="JPY",
        unit="event",
        billing_period=BillingPeriod.ANNUAL,
    )

    result = calculate_tco(
        _quote(amount=Decimal(0), usage=usage),
        _scenario(usage=Decimal("110"), unit="event"),
    )

    assert result.total_minor == 120 * 2
    assert result.line_items[-1].billed_occurrences == 1


def test_per_seat_included_usage_uses_minimum_seats() -> None:
    usage = UsageCharge(
        name="events",
        included_quantity=Decimal("10"),
        included_basis=PriceBasis.PER_SEAT,
        overage_unit_price=Decimal("1"),
        currency="JPY",
        unit="event",
    )
    quote = _quote(
        amount=Decimal(0),
        price_basis=PriceBasis.PER_SEAT,
        minimum_seats=3,
        usage=usage,
    )

    result = calculate_tco(
        quote, _scenario(seats=1, usage=Decimal("31"), unit="event")
    )

    assert result.total_minor == 12


def test_tax_excluded_is_added_per_invoice() -> None:
    result = calculate_tco(
        _quote(
            amount=Decimal("5"),
            tax=TaxPolicy(TaxTreatment.EXCLUDED, Decimal("0.10")),
        ),
        _scenario(),
    )

    # JPY 0.5 tax rounds half-up to JPY 1 for each monthly invoice.
    assert result.listed_minor == 60
    assert result.added_tax_minor == 12
    assert result.total_minor == 72


def test_tax_included_does_not_require_rate_or_add_tax() -> None:
    result = calculate_tco(
        _quote(tax=TaxPolicy(TaxTreatment.INCLUDED)), _scenario()
    )

    assert result.total_minor == 12_000
    assert result.added_tax_minor == 0


def test_rounding_is_per_invoice_not_at_end() -> None:
    quote = _quote(
        amount=Decimal("0.005"), currency="USD", digits=2
    )
    scenario = constant_usage_scenario(
        months=2, seats=1, monthly_usage=Decimal(0), usage_unit=None
    )

    result = calculate_tco(quote, scenario)

    assert result.total_minor == 2


def test_monthly_billing_with_twelve_month_commitment_is_supported() -> None:
    result = calculate_tco(_quote(commitment=12), _scenario())

    assert result.total_minor == 12_000


def test_commitment_longer_than_twelve_month_horizon_fails_closed() -> None:
    with pytest.raises(UnsupportedProrationError, match="13-month"):
        calculate_tco(_quote(commitment=13), _scenario())


def test_annual_charge_rejects_unspecified_proration() -> None:
    scenario = constant_usage_scenario(
        months=13, seats=1, monthly_usage=Decimal(0), usage_unit=None
    )

    with pytest.raises(UnsupportedProrationError):
        calculate_tco(
            _quote(billing_period=BillingPeriod.ANNUAL), scenario
        )


def test_unknown_and_incomplete_tax_fail_closed() -> None:
    with pytest.raises(TaxInformationError, match="unknown"):
        calculate_tco(
            _quote(tax=TaxPolicy(TaxTreatment.UNKNOWN)), _scenario()
        )
    with pytest.raises(TaxInformationError, match="requires"):
        calculate_tco(
            _quote(tax=TaxPolicy(TaxTreatment.EXCLUDED)), _scenario()
        )
    with pytest.raises(TaxInformationError, match="cannot have"):
        calculate_tco(
            _quote(
                tax=TaxPolicy(TaxTreatment.NOT_APPLICABLE, Decimal("0.10"))
            ),
            _scenario(),
        )


def test_currency_conversion_is_never_implicit() -> None:
    addon = RecurringCharge(
        name="foreign",
        amount=Decimal("10"),
        currency="USD",
        billing_period=BillingPeriod.MONTHLY,
    )

    with pytest.raises(CurrencyMismatchError, match="conversion is disabled"):
        calculate_tco(_quote(addons=(addon,)), _scenario())


def test_usage_unit_mismatch_fails_closed() -> None:
    usage = UsageCharge(
        name="storage",
        included_quantity=Decimal("10"),
        overage_unit_price=Decimal("1"),
        currency="JPY",
        unit="GB",
    )

    with pytest.raises(UsageUnitMismatchError):
        calculate_tco(
            _quote(usage=usage),
            _scenario(usage=Decimal("11"), unit="request"),
        )


def test_unknown_overage_price_only_fails_when_allowance_is_exceeded() -> None:
    usage = UsageCharge(
        name="storage",
        included_quantity=Decimal("10"),
        overage_unit_price=None,
        currency="JPY",
        unit="GB",
    )

    within = calculate_tco(
        _quote(amount=Decimal(0), usage=usage),
        _scenario(usage=Decimal("10"), unit="GB"),
    )
    assert within.total_minor == 0
    with pytest.raises(MissingUsagePricingError):
        calculate_tco(
            _quote(usage=usage),
            _scenario(usage=Decimal("11"), unit="GB"),
        )


def test_usage_without_pricing_fails_closed() -> None:
    with pytest.raises(MissingUsagePricingError):
        calculate_tco(
            _quote(), _scenario(usage=Decimal("1"), unit="event")
        )


def test_maximum_seats_is_enforced() -> None:
    with pytest.raises(TcoError, match="at most 3"):
        calculate_tco(
            _quote(
                price_basis=PriceBasis.PER_SEAT,
                maximum_seats=3,
            ),
            _scenario(seats=4),
        )


def test_server_terms_add_known_initial_renewal_campaign_and_domain_costs() -> None:
    result = calculate_server_tco(
        _quote(),
        _scenario(),
        ServerTcoTerms(
            initial_fee=Decimal("3000"),
            renewal_fee=Decimal("500"),
            renewal_due_month=12,
            campaign_price=Decimal("500"),
            campaign_period_months=3,
            domain_price=Decimal("2400"),
            domain_billing_period=BillingPeriod.ANNUAL,
            domain_included_months=12,
        ),
    )

    assert result.total_minor == 14_000
    assert [item.kind for item in result.line_items] == [
        "server.initial_fee",
        "base.campaign",
        "base.regular",
        "server.renewal_fee",
        "server.domain",
    ]
    assert result.line_items[-1].billed_occurrences == 0


def test_server_renewal_and_domain_charge_only_when_horizon_reaches_them() -> None:
    scenario = constant_usage_scenario(
        months=24,
        seats=1,
        monthly_usage=Decimal(0),
        usage_unit=None,
    )
    result = calculate_server_tco(
        _quote(),
        scenario,
        ServerTcoTerms(
            renewal_fee=Decimal("500"),
            renewal_due_month=13,
            domain_price=Decimal("2400"),
            domain_billing_period=BillingPeriod.ANNUAL,
            domain_included_months=12,
        ),
    )

    assert result.total_minor == 24_000 + 500 + 2_400
    assert result.line_items[-2].billed_occurrences == 1
    assert result.line_items[-1].billed_occurrences == 1


@pytest.mark.parametrize(
    ("terms", "message"),
    [
        (ServerTcoTerms(renewal_fee=Decimal("500")), "renewal fee and due month"),
        (ServerTcoTerms(campaign_price=Decimal("500")), "campaign price and period"),
        (
            ServerTcoTerms(
                domain_price=Decimal("2400"),
                domain_billing_period=BillingPeriod.ANNUAL,
            ),
            "domain price, billing period, and included months",
        ),
    ],
)
def test_server_terms_reject_partial_observations(
    terms: ServerTcoTerms,
    message: str,
) -> None:
    with pytest.raises(TcoError, match=message):
        calculate_server_tco(_quote(), _scenario(), terms)


def test_server_campaign_rejects_annual_proration_and_invented_discount() -> None:
    with pytest.raises(UnsupportedProrationError, match="monthly base price"):
        calculate_server_tco(
            _quote(billing_period=BillingPeriod.ANNUAL, amount=Decimal("12000")),
            _scenario(),
            ServerTcoTerms(
                campaign_price=Decimal("6000"),
                campaign_period_months=12,
            ),
        )
    with pytest.raises(TcoError, match="cannot exceed"):
        calculate_server_tco(
            _quote(),
            _scenario(),
            ServerTcoTerms(
                campaign_price=Decimal("1001"),
                campaign_period_months=1,
            ),
        )


def test_vendor_plan_adapter_prices_per_seat_without_fixed_platform_fee() -> None:
    plan = SimpleNamespace(
        base_price=Decimal("200"),
        currency="JPY",
        minor_unit_digits=0,
        billing_period="monthly",
        commitment_months=12,
        pricing_model="per_seat",
        seat_pricing=SimpleNamespace(
            unit_price=Decimal("200"),
            minimum_seats=3,
            included_seats=0,
            maximum_seats=10,
        ),
        usage_allowance=None,
        addons=(),
        tax=SimpleNamespace(treatment="not_applicable", rate=None),
    )

    result = calculate_vendor_plan_tco(
        plan, _scenario(seats=4), minor_unit_digits=0
    )

    # Phase-1 per-seat base_price is the unit price, not a fixed platform fee.
    assert result.total_minor == 4 * 200 * 12


def test_vendor_plan_adapter_uses_contract_usage_reset_period() -> None:
    plan = SimpleNamespace(
        base_price=Decimal(0),
        currency="JPY",
        minor_unit_digits=0,
        billing_period="monthly",
        commitment_months=1,
        pricing_model="flat",
        seat_pricing=None,
        usage_allowance=SimpleNamespace(
            unit_name="event",
            included_quantity=Decimal("100"),
            overage_unit_price=Decimal("1"),
            billing_period="monthly",
        ),
        addons=(),
        tax=SimpleNamespace(treatment="included", rate=None),
    )

    result = calculate_vendor_plan_tco(
        plan,
        _scenario(usage=Decimal("101"), unit="event"),
        minor_unit_digits=0,
    )

    assert result.total_minor == 12


def test_vendor_plan_adapter_always_includes_required_addon() -> None:
    plan = SimpleNamespace(
        base_price=Decimal("1000"),
        currency="JPY",
        minor_unit_digits=0,
        billing_period="monthly",
        commitment_months=1,
        pricing_model="flat",
        seat_pricing=None,
        usage_allowance=None,
        addons=(
            SimpleNamespace(
                code="required-support",
                name="Required support",
                unit_price=Decimal("100"),
                billing_period="monthly",
                pricing_model="flat",
                required=True,
            ),
            SimpleNamespace(
                code="optional-audit",
                name="Optional audit",
                unit_price=Decimal("200"),
                billing_period="monthly",
                pricing_model="flat",
                required=False,
            ),
        ),
        tax=SimpleNamespace(treatment="not_applicable", rate=None),
    )

    result = calculate_vendor_plan_tco(plan, _scenario())

    assert result.total_minor == (1000 + 100) * 12
    assert [item.name for item in result.line_items] == [
        "base price",
        "Required support",
    ]


def test_vendor_plan_adapter_includes_selected_optional_addon() -> None:
    plan = SimpleNamespace(
        base_price=Decimal("1000"),
        currency="JPY",
        minor_unit_digits=0,
        billing_period="monthly",
        commitment_months=1,
        pricing_model="flat",
        seat_pricing=None,
        usage_allowance=None,
        addons=(
            SimpleNamespace(
                code="optional-audit",
                name="Optional audit",
                unit_price=Decimal("200"),
                billing_period="monthly",
                pricing_model="flat",
                required=False,
            ),
        ),
        tax=SimpleNamespace(treatment="not_applicable", rate=None),
    )

    result = calculate_vendor_plan_tco(
        plan, _scenario(), selected_addon_codes=("optional-audit",)
    )

    assert result.total_minor == (1000 + 200) * 12


def test_vendor_plan_adapter_rejects_unknown_addon_selection() -> None:
    plan = SimpleNamespace(
        base_price=Decimal("1000"),
        currency="JPY",
        minor_unit_digits=0,
        billing_period="monthly",
        commitment_months=1,
        pricing_model="flat",
        seat_pricing=None,
        usage_allowance=None,
        addons=(),
        tax=SimpleNamespace(treatment="not_applicable", rate=None),
    )

    with pytest.raises(TcoError, match="unknown selected add-on"):
        calculate_vendor_plan_tco(
            plan, _scenario(), selected_addon_codes=("not-a-real-addon",)
        )


@given(
    amount_minor=st.integers(min_value=0, max_value=10**9),
    seats=st.integers(min_value=1, max_value=10_000),
)
def test_total_is_always_non_negative(amount_minor: int, seats: int) -> None:
    quote = _quote(
        amount=Decimal(amount_minor) / 100,
        currency="USD",
        digits=2,
        price_basis=PriceBasis.PER_SEAT,
    )

    result = calculate_tco(quote, _scenario(seats=seats))

    assert result.listed_minor >= 0
    assert result.added_tax_minor >= 0
    assert result.total_minor >= 0


@given(
    low=st.integers(min_value=1, max_value=999),
    high=st.integers(min_value=1, max_value=1000),
)
def test_tco_is_monotonic_in_seats(low: int, high: int) -> None:
    low_seats, high_seats = sorted((low, high))
    quote = _quote(amount=Decimal("7"), price_basis=PriceBasis.PER_SEAT)

    low_result = calculate_tco(quote, _scenario(seats=low_seats))
    high_result = calculate_tco(quote, _scenario(seats=high_seats))

    assert high_result.total_minor >= low_result.total_minor


@given(
    low=st.integers(min_value=0, max_value=999_999),
    high=st.integers(min_value=0, max_value=1_000_000),
)
def test_tco_is_monotonic_in_usage(low: int, high: int) -> None:
    low_usage, high_usage = sorted((low, high))
    usage = UsageCharge(
        name="events",
        included_quantity=Decimal("100"),
        overage_unit_price=Decimal("0.5"),
        currency="JPY",
        unit="event",
    )
    quote = _quote(amount=Decimal(0), usage=usage)

    low_result = calculate_tco(
        quote, _scenario(usage=Decimal(low_usage), unit="event")
    )
    high_result = calculate_tco(
        quote, _scenario(usage=Decimal(high_usage), unit="event")
    )

    assert high_result.total_minor >= low_result.total_minor


@given(monthly_minor=st.integers(min_value=0, max_value=10**9))
def test_monthly_and_annual_are_equivalent_for_exact_minor_prices(
    monthly_minor: int,
) -> None:
    monthly_amount = Decimal(monthly_minor) / 100
    monthly = calculate_tco(
        _quote(amount=monthly_amount, currency="USD", digits=2), _scenario()
    )
    annual = calculate_tco(
        _quote(
            amount=monthly_amount * 12,
            billing_period=BillingPeriod.ANNUAL,
            currency="USD",
            digits=2,
        ),
        _scenario(),
    )

    assert monthly.total_minor == annual.total_minor
