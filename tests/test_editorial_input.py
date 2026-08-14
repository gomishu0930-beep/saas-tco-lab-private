from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from saas_preflight.editorial_input import (
    CategoryExpansionInput,
    EditorialArticleInput,
    EditorialBillingPeriod,
    EditorialBillingToggleState,
    EditorialCurrencyStatus,
    EditorialObservedPriceBasis,
    EditorialSaleBannerState,
    EditorialScopeKind,
    EditorialTaxTreatment,
    EditorialValueKind,
    EditorialValueStatus,
    HumanEditorialNumericField,
    ExpansionCategory,
    expansion_field_kinds,
)


ROOT = Path(__file__).resolve().parents[1]


def _price(**changes: object) -> HumanEditorialNumericField:
    values: dict[str, object] = {
        "scope_kind": EditorialScopeKind.VENDOR_PLAN,
        "vendor_id": "mangools",
        "plan_id": "basic",
        "field": "pricing.base.amount",
        "value_kind": EditorialValueKind.PRICE,
        "value_status": EditorialValueStatus.KNOWN,
        "value": Decimal("1200"),
        "unit": "per seat",
        "currency_status": EditorialCurrencyStatus.KNOWN,
        "currency": "JPY",
        "billing_period": EditorialBillingPeriod.MONTHLY,
        "tax_treatment": EditorialTaxTreatment.UNKNOWN,
        "billing_toggle_state": EditorialBillingToggleState.MONTHLY_SELECTED,
        "sale_banner_state": EditorialSaleBannerState.NONE,
        "observed_price_basis": EditorialObservedPriceBasis.DISPLAYED_PRICE,
        "derived_monthly_value": None,
        "derived_monthly_unit": None,
        "derivation_method": None,
        "source_url": "https://vendor.example/pricing?currency=JPY",
        "observed_on": date(2026, 7, 28),
        "next_review_on": date(2026, 8, 28),
        "acquisition_method": "manual_public_page",
    }
    values.update(changes)
    return HumanEditorialNumericField.model_validate(values)


def test_human_editorial_price_requires_complete_observation() -> None:
    field = _price()
    article = EditorialArticleInput(
        article_id="P01",
        slug="pricing-calculator",
        title="料金計算",
        numeric_fields=(field,),
    )

    assert field.entered_by == "human"
    assert field.rights_path == "human_editorial"
    assert field.tax_treatment is EditorialTaxTreatment.UNKNOWN
    assert article.numeric_fields == (field,)


@pytest.mark.parametrize("missing", ["currency", "billing_period", "tax_treatment"])
def test_price_never_infers_currency_period_or_tax(missing: str) -> None:
    with pytest.raises(ValidationError):
        _price(**{missing: None})


@pytest.mark.parametrize("missing", ["billing_toggle_state", "sale_banner_state"])
def test_vendor_observation_requires_explicit_screen_state(missing: str) -> None:
    with pytest.raises(ValidationError, match="billing toggle and sale banner state"):
        _price(**{missing: None})


@pytest.mark.parametrize(
    "state",
    [
        EditorialSaleBannerState.NONE,
        EditorialSaleBannerState.ANNUAL_DISCOUNT_PERMANENT,
        EditorialSaleBannerState.TIME_LIMITED_PROMO,
        EditorialSaleBannerState.UNKNOWN,
    ],
)
def test_sale_banner_state_v23_accepts_only_the_four_explicit_classes(
    state: EditorialSaleBannerState,
) -> None:
    assert _price(sale_banner_state=state).sale_banner_state is state

    for legacy_state in ("present", "absent"):
        with pytest.raises(ValidationError):
            _price(sale_banner_state=legacy_state)


@pytest.mark.parametrize(
    "source_url",
    [
        "http://vendor.example/pricing",
        "https://vendor.example/pricing?utm_source=affiliate",
        "https://vendor.example/pricing?ref=secret",
        "https://user:pass@vendor.example/pricing",
        "https://localhost/pricing",
    ],
)
def test_source_url_rejects_tracking_credentials_and_private_hosts(source_url: str) -> None:
    with pytest.raises(ValidationError):
        _price(source_url=source_url)


def test_review_window_is_positive_and_bounded() -> None:
    with pytest.raises(ValidationError, match="later"):
        _price(next_review_on=date(2026, 7, 28))
    with pytest.raises(ValidationError, match="180"):
        _price(next_review_on=date(2027, 1, 25))


def test_duplicate_article_fields_fail_closed() -> None:
    field = _price()
    with pytest.raises(ValidationError, match="unique"):
        EditorialArticleInput(
            article_id="P01",
            slug="pricing-calculator",
            title="料金計算",
            numeric_fields=(field, field),
        )


def test_same_field_is_allowed_for_distinct_vendor_plan_rows() -> None:
    basic = _price()
    premium = _price(plan_id="premium", value=Decimal("2200"))

    article = EditorialArticleInput(
        article_id="P02",
        slug="plan-comparison",
        title="プラン比較",
        numeric_fields=(basic, premium),
    )

    assert [item.plan_id for item in article.numeric_fields] == ["basic", "premium"]


def test_ambiguous_dollar_currency_is_preserved_without_inference() -> None:
    field = _price(
        currency_status=EditorialCurrencyStatus.UNKNOWN,
        currency=None,
        currency_display="$",
        currency_unknown_reason="official page shows only a dollar symbol",
    )

    assert field.value == Decimal("1200")
    assert field.currency is None
    assert field.currency_display == "$"


def test_explicit_unknown_value_is_structural_evidence_not_zero() -> None:
    field = _price(
        value_status=EditorialValueStatus.UNKNOWN,
        value=None,
        unit=None,
        unknown_reason="official page does not state an overage price",
        currency_status=EditorialCurrencyStatus.UNKNOWN,
        currency=None,
        currency_display=None,
        currency_unknown_reason="no overage price or currency is displayed",
        observed_price_basis=EditorialObservedPriceBasis.UNKNOWN,
    )

    assert field.value is None
    assert field.value_status is EditorialValueStatus.UNKNOWN
    assert field.currency_display is None


def test_human_scenario_is_separate_from_vendor_evidence() -> None:
    field = HumanEditorialNumericField.model_validate(
        {
            "scope_kind": EditorialScopeKind.HUMAN_SCENARIO,
            "field": "scenario.seat_count",
            "value_kind": EditorialValueKind.SEAT_COUNT,
            "value_status": EditorialValueStatus.KNOWN,
            "value": Decimal("5"),
            "unit": "seats",
            "currency_status": EditorialCurrencyStatus.NOT_APPLICABLE,
            "billing_toggle_state": None,
            "sale_banner_state": None,
            "observed_price_basis": None,
            "derived_monthly_value": None,
            "derived_monthly_unit": None,
            "derivation_method": None,
            "scenario_basis": "Human-selected calculator scenario",
            "observed_on": date(2026, 7, 29),
            "next_review_on": date(2026, 8, 29),
            "acquisition_method": "human_scenario_input",
        }
    )

    assert field.source_url is None
    assert field.vendor_id is None
    assert field.acquisition_method == "human_scenario_input"


def test_human_scenario_rejects_vendor_source_identity() -> None:
    with pytest.raises(ValidationError, match="cannot carry vendor_id"):
        HumanEditorialNumericField.model_validate(
            {
                "scope_kind": EditorialScopeKind.HUMAN_SCENARIO,
                "vendor_id": "mangools",
                "plan_id": "basic",
                "field": "scenario.seat_count",
                "value_kind": EditorialValueKind.SEAT_COUNT,
                "value_status": EditorialValueStatus.KNOWN,
                "value": Decimal("5"),
                "unit": "seats",
                "currency_status": EditorialCurrencyStatus.NOT_APPLICABLE,
                "billing_toggle_state": None,
                "sale_banner_state": None,
                "observed_price_basis": None,
                "derived_monthly_value": None,
                "derived_monthly_unit": None,
                "derivation_method": None,
                "scenario_basis": "Human-selected calculator scenario",
                "observed_on": date(2026, 7, 29),
                "next_review_on": date(2026, 8, 29),
                "acquisition_method": "human_scenario_input",
            }
        )


def test_annual_price_requires_checkout_total_and_records_fixed_monthly_derivation() -> None:
    field = _price(
        value=Decimal("732"),
        unit="annual checkout total",
        billing_period=EditorialBillingPeriod.ANNUAL,
        billing_toggle_state=EditorialBillingToggleState.ANNUAL_SELECTED,
        observed_price_basis=EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
        derived_monthly_value=Decimal("61"),
        derived_monthly_unit="/ mo",
        derivation_method="annual_checkout_total_divided_by_12",
        acquisition_method="manual_checkout_review",
    )

    assert field.value == Decimal("732")
    assert field.derived_monthly_value == Decimal("61")


def test_permanent_annual_discount_requires_same_plan_monthly_reference() -> None:
    field = _price(
        value=Decimal("452.40"),
        unit="annual checkout total",
        currency="USD",
        billing_period=EditorialBillingPeriod.ANNUAL,
        billing_toggle_state=EditorialBillingToggleState.ANNUAL_SELECTED,
        sale_banner_state=EditorialSaleBannerState.ANNUAL_DISCOUNT_PERMANENT,
        observed_price_basis=EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
        derived_monthly_value=Decimal("37.70"),
        derived_monthly_unit="/ mo",
        derivation_method="annual_checkout_total_divided_by_12",
        monthly_reference_value=Decimal("61.00"),
        monthly_reference_unit="/ mo",
        derived_annual_discount_percent=Decimal("38"),
        discount_derivation_method=(
            "one_minus_annual_total_divided_by_monthly_price_times_12"
        ),
        acquisition_method="manual_checkout_review",
    )

    assert field.derived_annual_discount_percent == Decimal("38")

    with pytest.raises(ValidationError, match="monthly reference"):
        _price(
            value=Decimal("452.40"),
            unit="annual checkout total",
            currency="USD",
            billing_period=EditorialBillingPeriod.ANNUAL,
            billing_toggle_state=EditorialBillingToggleState.ANNUAL_SELECTED,
            sale_banner_state=EditorialSaleBannerState.ANNUAL_DISCOUNT_PERMANENT,
            observed_price_basis=EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
            derived_monthly_value=Decimal("37.70"),
            derived_monthly_unit="/ mo",
            derivation_method="annual_checkout_total_divided_by_12",
            acquisition_method="manual_checkout_review",
        )


def test_nondivisible_annual_total_keeps_primary_value_and_omits_monthly_derivation() -> None:
    field = _price(
        value=Decimal("733"),
        unit="annual checkout total",
        billing_period=EditorialBillingPeriod.ANNUAL,
        billing_toggle_state=EditorialBillingToggleState.ANNUAL_SELECTED,
        observed_price_basis=EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
        derived_monthly_value=None,
        derived_monthly_unit=None,
        derivation_method=None,
        acquisition_method="manual_checkout_review",
    )

    assert field.value == Decimal("733")
    assert field.derived_monthly_value is None

    with pytest.raises(ValidationError, match="must be omitted"):
        _price(
            value=Decimal("733"),
            unit="annual checkout total",
            billing_period=EditorialBillingPeriod.ANNUAL,
            billing_toggle_state=EditorialBillingToggleState.ANNUAL_SELECTED,
            observed_price_basis=EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
            derived_monthly_value=Decimal("61.08333333"),
            derived_monthly_unit="/ mo",
            derivation_method="annual_checkout_total_divided_by_12",
            acquisition_method="manual_checkout_review",
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"observed_price_basis": EditorialObservedPriceBasis.DISPLAYED_PRICE}, "checkout billed total"),
        ({"derived_monthly_value": Decimal("60")}, "divided by 12"),
        ({"billing_toggle_state": EditorialBillingToggleState.MONTHLY_SELECTED}, "annual_selected"),
    ],
)
def test_annual_price_rejects_monthly_display_or_inconsistent_derivation(
    change: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "value": Decimal("732"),
        "unit": "annual checkout total",
        "billing_period": EditorialBillingPeriod.ANNUAL,
        "billing_toggle_state": EditorialBillingToggleState.ANNUAL_SELECTED,
        "observed_price_basis": EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
        "derived_monthly_value": Decimal("61"),
        "derived_monthly_unit": "/ mo",
        "derivation_method": "annual_checkout_total_divided_by_12",
        "acquisition_method": "manual_checkout_review",
    }
    values.update(change)
    with pytest.raises(ValidationError, match=message):
        _price(**values)


def test_imported_first_batch_contracts_pass_authoritative_validation() -> None:
    expected_counts = {"P01": 5, "P02": 15, "P03": 12}
    for article_id, expected_count in expected_counts.items():
        path = ROOT / "artifacts" / "editorial-inputs" / f"{article_id}-editorial-input.json"
        contract = EditorialArticleInput.model_validate_json(path.read_text(encoding="utf-8"))
        assert contract.article_id == article_id
        assert len(contract.numeric_fields) == expected_count
        assert contract.article_review_status.value == "approved"
        assert all(field.entered_by == "human" for field in contract.numeric_fields)
        assert all(field.review_status.value == "approved" for field in contract.numeric_fields)
        assert all(field.rights_path == "human_editorial" for field in contract.numeric_fields)


def test_p06_p07_contracts_record_explicit_human_approval() -> None:
    expected_counts = {"P06": 4, "P07": 4}
    for article_id, expected_count in expected_counts.items():
        path = ROOT / "artifacts" / "editorial-inputs" / f"{article_id}-editorial-input.json"
        contract = EditorialArticleInput.model_validate_json(path.read_text(encoding="utf-8"))
        assert contract.article_id == article_id
        assert len(contract.numeric_fields) == expected_count
        assert contract.article_review_status.value == "approved"
        assert all(field.review_status.value == "approved" for field in contract.numeric_fields)
        assert all(field.entered_by == "human" for field in contract.numeric_fields)
        assert all(field.rights_path == "human_editorial" for field in contract.numeric_fields)


def test_category_expansion_contract_is_candidate_only_and_has_fixed_catalogs() -> None:
    candidate = CategoryExpansionInput(category_id=ExpansionCategory.ACCOUNTING)

    assert candidate.state == "candidate_only"
    assert candidate.numeric_fields == ()
    assert expansion_field_kinds(ExpansionCategory.SERVERS) == {
        "pricing.initial_fee": EditorialValueKind.PRICE,
        "pricing.base_price": EditorialValueKind.PRICE,
        "pricing.renewal_fee": EditorialValueKind.PRICE,
        "servers.campaign_price": EditorialValueKind.PRICE,
        "servers.campaign_period_months": EditorialValueKind.DURATION,
        "servers.domain_benefit_amount": EditorialValueKind.PRICE,
        "servers.domain_benefit_period_months": EditorialValueKind.DURATION,
        "servers.compute_hours": EditorialValueKind.USAGE,
        "servers.storage_gb": EditorialValueKind.QUOTA,
        "servers.data_transfer_gb": EditorialValueKind.QUOTA,
        "servers.backup_price": EditorialValueKind.PRICE,
    }
    schema_catalog = CategoryExpansionInput.model_json_schema()["properties"][
        "numeric_fields"
    ]["x-category-field-catalog"]["servers"]
    assert schema_catalog["pricing.initial_fee"] == "price"
    assert schema_catalog["pricing.renewal_fee"] == "price"
    assert schema_catalog["servers.campaign_period_months"] == "duration"
    assert schema_catalog["servers.domain_benefit_amount"] == "price"


def test_category_expansion_rejects_partial_or_cross_category_rows() -> None:
    with pytest.raises(ValidationError, match="do not match accounting catalog"):
        CategoryExpansionInput(
            category_id=ExpansionCategory.ACCOUNTING,
            numeric_fields=(_price(field="pricing.base_price"),),
        )
