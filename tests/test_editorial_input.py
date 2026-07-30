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
    EditorialCurrencyStatus,
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
                "scenario_basis": "Human-selected calculator scenario",
                "observed_on": date(2026, 7, 29),
                "next_review_on": date(2026, 8, 29),
                "acquisition_method": "human_scenario_input",
            }
        )


def test_imported_first_batch_contracts_pass_authoritative_validation() -> None:
    expected_counts = {"P01": 5, "P02": 15, "P03": 12}
    for article_id, expected_count in expected_counts.items():
        path = ROOT / "artifacts" / "editorial-inputs" / f"{article_id}-editorial-input.json"
        contract = EditorialArticleInput.model_validate_json(path.read_text(encoding="utf-8"))
        assert contract.article_id == article_id
        assert len(contract.numeric_fields) == expected_count
        assert contract.article_review_status.value == "unreviewed"
        assert all(field.entered_by == "human" for field in contract.numeric_fields)
        assert all(field.rights_path == "human_editorial" for field in contract.numeric_fields)


def test_category_expansion_contract_is_candidate_only_and_has_fixed_catalogs() -> None:
    candidate = CategoryExpansionInput(category_id=ExpansionCategory.ACCOUNTING)

    assert candidate.state == "candidate_only"
    assert candidate.numeric_fields == ()
    assert expansion_field_kinds(ExpansionCategory.SERVERS) == {
        "pricing.base_price": EditorialValueKind.PRICE,
        "servers.compute_hours": EditorialValueKind.USAGE,
        "servers.storage_gb": EditorialValueKind.QUOTA,
        "servers.data_transfer_gb": EditorialValueKind.QUOTA,
        "servers.backup_price": EditorialValueKind.PRICE,
    }


def test_category_expansion_rejects_partial_or_cross_category_rows() -> None:
    with pytest.raises(ValidationError, match="do not match accounting catalog"):
        CategoryExpansionInput(
            category_id=ExpansionCategory.ACCOUNTING,
            numeric_fields=(_price(field="pricing.base_price"),),
        )
