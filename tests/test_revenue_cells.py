from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from saas_preflight.revenue_cells import (
    EvidenceStatus,
    EvidenceText,
    MoneyEvidence,
    MerchantEvidenceMatrix,
    RevenueAnalyticsContract,
    RevenueCellDailyAggregate,
    RevenueCellId,
    RevenueChannel,
    RevenueEnvironment,
    RevenueMediumClass,
    RevenueSourceClass,
    RevenueTrafficScope,
    summarize_revenue_cell,
)


ROOT = Path(__file__).resolve().parents[1]


def row(**changes: object) -> RevenueCellDailyAggregate:
    values: dict[str, object] = {
        "schema_version": "1.1",
        "observed_on": date(2026, 8, 20),
        "article_id": "SVR01",
        "revenue_cell_id": RevenueCellId.CELL_A,
        "revenue_cell_version": "v2",
        "vendor_id": "xserver-business",
        "cta_position": "primary",
        "cta_type": "affiliate_comparison",
        "channel": RevenueChannel.NOTE,
        "source_class": RevenueSourceClass.NOTE,
        "medium_class": RevenueMediumClass.REFERRAL,
        "campaign_id": "svr01-audit-v2",
        "environment": RevenueEnvironment.PRODUCTION,
        "traffic_scope": RevenueTrafficScope.EXTERNAL,
        "test_flag": False,
        "calculator_result_views": 10,
        "cta_views": 8,
        "cta_view_sessions": 6,
        "eligible_sessions": 6,
        "outbound_clicks": 2,
        "unique_outbound_sessions": 2,
        "asp_clicks": None,
        "pending_conversions": None,
        "confirmed_conversions": None,
        "rejected_conversions": None,
        "matured_eligible_sessions": None,
        "confirmed_commission_minor": None,
    }
    values.update(changes)
    return RevenueCellDailyAggregate.model_validate(values)


def test_unknown_evidence_requires_reason_and_never_retains_value() -> None:
    with pytest.raises(ValidationError):
        EvidenceText(status=EvidenceStatus.UNKNOWN, value="推測値", reason=None)
    unknown = EvidenceText(
        status=EvidenceStatus.UNKNOWN,
        value=None,
        reason="Human確認記録がないため",
    )
    assert unknown.value is None


def test_known_money_requires_currency_tax_and_billing_cycle() -> None:
    with pytest.raises(ValidationError):
        MoneyEvidence(
            status=EvidenceStatus.KNOWN,
            amount=Decimal("1000"),
            currency="JPY",
            tax_treatment="unknown",
            billing_cycle="annual",
            reason=None,
        )


def test_revenue_aggregate_excludes_internal_test_and_non_production() -> None:
    summary = summarize_revenue_cell((
        row(),
        row(traffic_scope=RevenueTrafficScope.INTERNAL),
        row(test_flag=True),
        row(environment=RevenueEnvironment.LOCAL),
    ))
    assert summary.included_rows == 1
    assert summary.decision_ready is True
    assert summary.excluded_rows == 3
    assert summary.eligible_sessions == 6
    assert summary.outbound_clicks == 2
    assert summary.unique_outbound_sessions == 2
    assert summary.outbound_ctr_percent == Decimal("33.33")
    assert summary.confirmed_rpes_minor is None


def test_confirmed_rpes_requires_every_included_row_to_be_mature() -> None:
    unknown = summarize_revenue_cell((row(),))
    assert unknown.confirmed_commission_minor is None
    assert unknown.matured_eligible_sessions is None
    assert unknown.confirmed_rpes_minor is None

    known = summarize_revenue_cell((row(
        matured_eligible_sessions=4,
        confirmed_conversions=1,
        confirmed_commission_minor=Decimal("10000"),
    ),))
    assert known.confirmed_rpes_minor == Decimal("2500.00")


def test_revenue_row_rejects_unsafe_campaign_and_impossible_click_count() -> None:
    with pytest.raises(ValidationError):
        row(campaign_id="raw query=value")
    with pytest.raises(ValidationError):
        row(campaign_id="a" * 65)
    with pytest.raises(ValidationError):
        row(cta_views=1, outbound_clicks=2)
    with pytest.raises(ValidationError):
        row(unique_outbound_sessions=7)
    with pytest.raises(ValidationError):
        row(cta_views=1, cta_view_sessions=2)
    with pytest.raises(ValidationError):
        row(cta_view_sessions=1, eligible_sessions=2)
    with pytest.raises(ValidationError):
        row(cta_view_sessions=1, unique_outbound_sessions=2)
    with pytest.raises(ValidationError):
        row(pending_conversions=0, pending_commission_minor=Decimal("1"))
    with pytest.raises(ValidationError):
        row(confirmed_conversions=0, confirmed_commission_minor=Decimal("1"))
    assert row(pending_conversions=0, pending_commission_minor=Decimal("0"))
    assert row(confirmed_conversions=0, confirmed_commission_minor=Decimal("0"))


def test_revenue_summary_is_not_decision_ready_without_clean_rows() -> None:
    summary = summarize_revenue_cell((
        row(traffic_scope=RevenueTrafficScope.UNKNOWN),
        row(traffic_scope=RevenueTrafficScope.INTERNAL),
        row(test_flag=True),
    ))
    assert summary.decision_ready is False
    assert summary.included_rows == 0
    assert summary.outbound_ctr_percent is None


def test_revenue_summary_uses_unique_outbound_sessions_not_event_count() -> None:
    summary = summarize_revenue_cell((
        row(outbound_clicks=5, unique_outbound_sessions=2),
    ))
    assert summary.outbound_clicks == 5
    assert summary.unique_outbound_sessions == 2
    assert summary.outbound_ctr_percent == Decimal("33.33")


def test_cell_b_v3_is_separate_from_the_prechange_v2_group() -> None:
    v3 = row(
        article_id="SVR04",
        revenue_cell_id=RevenueCellId.CELL_B,
        revenue_cell_version="v3",
        cta_position="single",
        cta_type="affiliate_single",
    )
    assert summarize_revenue_cell((v3,)).revenue_cell_version == "v3"
    with pytest.raises(ValueError, match="must share article"):
        summarize_revenue_cell((row(), v3))


def test_revenue_summary_rejects_mixed_cell_or_acquisition_groups() -> None:
    with pytest.raises(ValueError, match="must share article"):
        summarize_revenue_cell((
            row(),
            row(
                article_id="SVR04",
                revenue_cell_id=RevenueCellId.CELL_B,
                cta_position="single",
                cta_type="affiliate_single",
            ),
        ))
    with pytest.raises(ValueError, match="must share article"):
        summarize_revenue_cell((
            row(),
            row(
                channel=RevenueChannel.ORGANIC,
                source_class=RevenueSourceClass.SEARCH,
                medium_class=RevenueMediumClass.ORGANIC,
            ),
        ))


def test_repository_revenue_contracts_validate_and_keep_unknowns_explicit() -> None:
    matrix = MerchantEvidenceMatrix.model_validate_json(
        (ROOT / "artifacts/revenue-cells/merchant-evidence-matrix-v2-2026-08-20.json").read_text()
    )
    assert matrix.affiliate_urls_saved is False
    assert matrix.tracking_ids_saved is False
    assert [entry.vendor_id for entry in matrix.entries] == [
        "conoha-wing", "kagoya", "xserver-business",
    ]
    kagoya = matrix.entries[1]
    assert kagoya.current_cta_eligibility.value == "hold"
    assert kagoya.affiliate_approval_status == "unknown"
    assert kagoya.scorecard is None
    for entry in (matrix.entries[0], matrix.entries[2]):
        assert entry.current_cta_eligibility.value == "eligible"
        assert entry.scorecard is not None
        assert entry.scorecard.total is None
        assert entry.confirmation_period.status is EvidenceStatus.UNKNOWN
        assert entry.deep_link_permission.status is EvidenceStatus.UNKNOWN

    analytics = RevenueAnalyticsContract.model_validate_json(
        (ROOT / "artifacts/revenue-cells/revenue-analytics-contract-v1.json").read_text()
    )
    assert "affiliate_url" in analytics.prohibited_dimensions
    assert "campaign_id" in analytics.allowed_dimensions
    assert "revenue_cell_version" in analytics.allowed_dimensions
    assert "source_class" in analytics.allowed_dimensions
    assert "medium_class" in analytics.allowed_dimensions
