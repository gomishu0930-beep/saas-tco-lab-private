"""Noindex preview renderer fed only by canonical, precomputed TCO results.

The renderer contains no pricing business logic and performs no network access.
It enforces data/rights/affiliate expiry at render time so a stale static
preview cannot accidentally expose numeric comparisons or an invalid CTA.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from html import escape
import json
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from .models import BillingPeriod, CurrencyCode, StrictModel


class FitStatus(str, Enum):
    FIT = "fit"
    NOT_FIT = "not_fit"
    UNKNOWN = "unknown"


class PreviewPlan(StrictModel):
    vendor_slug: str = Field(min_length=1, max_length=80)
    vendor_name: str = Field(min_length=1, max_length=160)
    plan_slug: str = Field(min_length=1, max_length=80)
    plan_name: str = Field(min_length=1, max_length=160)
    scenario_name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=2, max_length=40)
    tax_note: str = Field(min_length=1, max_length=200)
    currency: CurrencyCode
    billing_period: BillingPeriod
    commitment_months: int = Field(ge=1, le=120)
    minor_unit_digits: int = Field(ge=0, le=6)
    total_minor: int = Field(ge=0)
    fit_status: FitStatus
    fit_reason: str = Field(min_length=1, max_length=500)
    evidence_url: AnyHttpUrl
    evidence_retrieved_at: datetime
    data_expires_at: datetime
    rights_expires_at: datetime
    affiliate_expires_at: datetime | None = None
    affiliate_url: AnyHttpUrl | None = None
    affiliate_active: bool = False

    @field_validator(
        "evidence_retrieved_at",
        "data_expires_at",
        "rights_expires_at",
        "affiliate_expires_at",
    )
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("preview timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_affiliate_state(self) -> Self:
        affiliate_values = (self.affiliate_url, self.affiliate_expires_at)
        if self.affiliate_active and any(value is None for value in affiliate_values):
            raise ValueError(
                "active affiliate CTA requires URL and affiliate expiry"
            )
        if not self.affiliate_active and any(value is not None for value in affiliate_values):
            raise ValueError(
                "inactive affiliate CTA cannot retain URL or affiliate expiry"
            )
        return self


class PreviewPage(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    title: str = Field(min_length=1, max_length=200)
    methodology: str = Field(min_length=1, max_length=1000)
    rendered_at: datetime
    plans: tuple[PreviewPlan, ...] = Field(min_length=1, max_length=100)
    affiliate_disclosure: str = Field(
        default="このページにはアフィリエイトリンクが含まれる場合があります。",
        min_length=1,
        max_length=500,
    )

    @field_validator("rendered_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("rendered_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_unique_rows(self) -> Self:
        keys = [
            (plan.vendor_slug, plan.plan_slug, plan.scenario_name)
            for plan in self.plans
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("preview plan rows must be unique")
        return self


def data_visible(plan: PreviewPlan, *, at: datetime) -> bool:
    _require_aware(at)
    return at < min(plan.data_expires_at, plan.rights_expires_at)


def cta_visible(plan: PreviewPlan, *, at: datetime) -> bool:
    if not data_visible(plan, at=at) or not plan.affiliate_active:
        return False
    assert plan.affiliate_expires_at is not None
    return at < plan.affiliate_expires_at


def format_minor_units(amount: int, digits: int) -> str:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError("amount must be a non-negative integer")
    if isinstance(digits, bool) or not isinstance(digits, int) or not 0 <= digits <= 6:
        raise ValueError("digits must be an integer between 0 and 6")
    value = Decimal(amount) / (Decimal(10) ** digits)
    return f"{value:,.{digits}f}"


def render_preview(page: PreviewPage, *, at: datetime | None = None) -> str:
    """Return a complete escaped HTML page with a mandatory noindex policy."""

    instant = at or datetime.now(timezone.utc)
    _require_aware(instant)
    if page.rendered_at > instant:
        raise ValueError("preview input rendered_at cannot be in the future")
    rows: list[str] = []
    for plan in page.plans:
        identity = f"{escape(plan.vendor_name)} / {escape(plan.plan_name)}"
        source = (
            f'<a href="{escape(str(plan.evidence_url), quote=True)}" '
            'rel="nofollow noopener noreferrer">公式根拠</a>'
        )
        if data_visible(plan, at=instant):
            total = (
                f"{escape(plan.currency)} "
                f"{format_minor_units(plan.total_minor, plan.minor_unit_digits)}"
            )
            status = "検証済み"
        else:
            total = "非表示"
            status = "データまたは利用権の期限切れ"

        fit_labels = {
            FitStatus.FIT: "適合",
            FitStatus.NOT_FIT: "非適合",
            FitStatus.UNKNOWN: "判定不能",
        }
        conditions = (
            f"{escape(plan.region)} / {escape(plan.currency)} / "
            f"{escape(plan.tax_note)} / {escape(plan.billing_period.value)} / "
            f"{plan.commitment_months}か月"
        )
        expiry = (
            f"取得 {escape(plan.evidence_retrieved_at.isoformat())}<br>"
            f"data期限 {escape(plan.data_expires_at.isoformat())}<br>"
            f"rights期限 {escape(plan.rights_expires_at.isoformat())}"
        )

        if cta_visible(plan, at=instant):
            assert plan.affiliate_url is not None
            cta = (
                f'<a href="{escape(str(plan.affiliate_url), quote=True)}" '
                'rel="sponsored nofollow noopener noreferrer">公式サイトへ</a>'
            )
        else:
            cta = "利用不可"

        rows.append(
            "<tr>"
            f"<th scope=\"row\">{identity}</th>"
            f"<td>{conditions}<br><small>{escape(plan.scenario_name)}</small></td>"
            f"<td>{escape(total)}</td>"
            f"<td>{escape(fit_labels[plan.fit_status])}<br>"
            f"<small>{escape(plan.fit_reason)}</small></td>"
            f"<td>{escape(status)}</td>"
            f"<td>{source}<br><small>{expiry}</small></td>"
            f"<td>{cta}</td>"
            "</tr>"
        )

    disclosure = f'<aside class="disclosure" aria-label="広告表示">{escape(page.affiliate_disclosure)}</aside>'
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": page.title,
            "dateModified": instant.isoformat(),
            "isAccessibleForFree": True,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return (
        "<!doctype html>\n"
        '<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow,noarchive">'
        f"<title>{escape(page.title)}</title>"
        f'<script type="application/ld+json">{structured_data}</script>'
        "<style>body{font-family:system-ui,sans-serif;max-width:72rem;margin:auto;padding:1rem;line-height:1.6}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.6rem;text-align:left}"
        ".disclosure{border:2px solid #444;padding:.75rem;font-weight:700}small{color:#555}</style>"
        "</head><body><header><nav aria-label=\"プレビュー\">公開前比較 / NOINDEX</nav></header><main>"
        f"<h1>{escape(page.title)}</h1>{disclosure}"
        f"<p>{escape(page.methodology)}</p>"
        f"<p>生成時刻: <time>{escape(instant.isoformat())}</time></p>"
        "<table><thead><tr><th>サービス / プラン</th><th>条件</th><th>12か月TCO</th>"
        "<th>適合</th><th>状態</th><th>根拠と期限</th><th>広告リンク</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></main><footer>合成fixtureまたは承認済みreleaseのみ</footer></body></html>\n"
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("visibility checks require a timezone-aware timestamp")


__all__ = [
    "FitStatus",
    "PreviewPage",
    "PreviewPlan",
    "cta_visible",
    "data_visible",
    "format_minor_units",
    "render_preview",
]
