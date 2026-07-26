from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from saas_preflight.models import BillingPeriod
from saas_preflight.preview import (
    FitStatus,
    PreviewPage,
    PreviewPlan,
    cta_visible,
    data_visible,
    render_preview,
)


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def _plan(**overrides: object) -> PreviewPlan:
    values: dict[str, object] = {
        "vendor_slug": "sample-vendor",
        "vendor_name": "Sample <Vendor>",
        "plan_slug": "basic",
        "plan_name": "Basic",
        "scenario_name": "10 seats & 12 months",
        "region": "JP",
        "tax_note": "tax included",
        "currency": "JPY",
        "billing_period": BillingPeriod.MONTHLY,
        "commitment_months": 12,
        "minor_unit_digits": 0,
        "total_minor": 13200,
        "fit_status": FitStatus.FIT,
        "fit_reason": "The synthetic scenario is within the fixture limits.",
        "evidence_url": "https://example.com/pricing?x=1&y=2",
        "evidence_retrieved_at": NOW - timedelta(days=1),
        "data_expires_at": NOW + timedelta(days=7),
        "rights_expires_at": NOW + timedelta(days=30),
        "affiliate_expires_at": NOW + timedelta(days=10),
        "affiliate_url": "https://example.com/go?ref=safe",
        "affiliate_active": True,
    }
    values.update(overrides)
    return PreviewPlan(**values)


def _page(plan: PreviewPlan) -> PreviewPage:
    return PreviewPage(
        title="SaaS <比較>",
        methodology="Canonical Python TCO only.",
        rendered_at=NOW,
        plans=(plan,),
    )


def test_preview_is_noindex_escaped_and_sponsored() -> None:
    rendered = render_preview(_page(_plan()), at=NOW)

    assert 'content="noindex,nofollow,noarchive"' in rendered
    assert "SaaS &lt;比較&gt;" in rendered
    assert "Sample &lt;Vendor&gt;" in rendered
    assert "JPY 13,200" in rendered
    assert "tax included" in rendered
    assert "The synthetic scenario is within the fixture limits." in rendered
    assert "<main>" in rendered
    assert 'type="application/ld+json"' in rendered
    assert 'rel="sponsored nofollow noopener noreferrer"' in rendered
    assert "?x=1&amp;y=2" in rendered


def test_expired_rights_hide_numbers_and_cta() -> None:
    plan = _plan(rights_expires_at=NOW)

    assert data_visible(plan, at=NOW) is False
    assert cta_visible(plan, at=NOW) is False
    rendered = render_preview(_page(plan), at=NOW)
    assert "JPY 13,200" not in rendered
    assert "データまたは利用権の期限切れ" in rendered
    assert "公式サイトへ" not in rendered


def test_expired_affiliate_only_hides_cta() -> None:
    plan = _plan(affiliate_expires_at=NOW)

    assert data_visible(plan, at=NOW) is True
    assert cta_visible(plan, at=NOW) is False
    rendered = render_preview(_page(plan), at=NOW)
    assert "JPY 13,200" in rendered
    assert "公式サイトへ" not in rendered


def test_inactive_affiliate_cannot_retain_tracking_values() -> None:
    with pytest.raises(ValidationError, match="inactive affiliate"):
        _plan(affiliate_active=False)


def test_duplicate_preview_rows_fail_closed() -> None:
    plan = _plan()
    with pytest.raises(ValidationError, match="must be unique"):
        PreviewPage(
            title="Duplicate",
            methodology="Test",
            rendered_at=NOW,
            plans=(plan, plan),
        )


def test_old_input_timestamp_cannot_bypass_current_expiry() -> None:
    plan = _plan(data_expires_at=NOW + timedelta(hours=1))
    rendered = render_preview(_page(plan), at=NOW + timedelta(hours=1))

    assert "JPY 13,200" not in rendered
    assert "データまたは利用権の期限切れ" in rendered
