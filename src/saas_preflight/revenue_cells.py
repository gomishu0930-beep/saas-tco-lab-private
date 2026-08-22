"""Fail-closed contracts for the two revenue cells and safe aggregates.

These models contain only reviewable evidence and low-cardinality dimensions.
They intentionally cannot store affiliate destinations, click identifiers,
cookies, referrer/search queries, credentials, or free-form visitor data.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from .models import CurrencyCode, Slug, StrictModel


_SAFE_TEXT = re.compile(
    r"^(?!.*(?:https?://|www\.|[^\s@]+@[^\s@]+\.[^\s@]+)).+$",
    re.I,
)
_ARTICLE_ID = re.compile(r"^(?:P(?:0[1-9]|1[0-2])|SVR(?:0[1-9]|1[0-9]|20))$")
_CAMPAIGN_ID = re.compile(r"^(?=.{1,64}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class EvidenceStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    RESTRICTED_DASHBOARD_ONLY = "restricted_dashboard_only"


class GateStatus(str, Enum):
    GO = "go"
    HOLD = "hold"
    UNKNOWN = "unknown"


class CtaEligibility(str, Enum):
    ELIGIBLE = "eligible"
    HOLD = "hold"


class EvidenceText(StrictModel):
    status: EvidenceStatus
    value: str | None = Field(default=None, min_length=1, max_length=800)
    reason: str | None = Field(default=None, min_length=2, max_length=800)

    @field_validator("value", "reason")
    @classmethod
    def keep_text_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not _SAFE_TEXT.fullmatch(normalized):
            raise ValueError("evidence text cannot contain a URL or email address")
        return normalized

    @model_validator(mode="after")
    def require_explicit_state(self) -> Self:
        if self.status is EvidenceStatus.KNOWN:
            if self.value is None or self.reason is not None:
                raise ValueError("known evidence requires a value and no unknown reason")
        elif self.value is not None:
            raise ValueError("unavailable evidence cannot retain a value")
        elif self.reason is None:
            raise ValueError("unavailable evidence requires an explicit reason")
        return self


class MoneyEvidence(StrictModel):
    status: EvidenceStatus
    amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    currency: CurrencyCode | None = None
    tax_treatment: Literal["included", "excluded", "unknown", "not_applicable"]
    billing_cycle: Literal["one_time", "monthly", "annual", "unknown", "not_applicable"]
    reason: str | None = Field(default=None, min_length=2, max_length=800)

    @field_validator("reason")
    @classmethod
    def keep_reason_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not _SAFE_TEXT.fullmatch(normalized):
            raise ValueError("money evidence reason cannot contain a URL or email address")
        return normalized

    @model_validator(mode="after")
    def require_known_money_together(self) -> Self:
        if self.status is EvidenceStatus.KNOWN:
            if self.amount is None or self.currency is None or self.reason is not None:
                raise ValueError("known money requires amount and currency")
            if self.tax_treatment in {"unknown", "not_applicable"}:
                raise ValueError("known money requires a known tax treatment")
            if self.billing_cycle in {"unknown", "not_applicable"}:
                raise ValueError("known money requires a known billing cycle")
        else:
            if self.amount is not None or self.currency is not None:
                raise ValueError("unavailable money cannot retain amount or currency")
            if self.reason is None:
                raise ValueError("unavailable money requires an explicit reason")
        return self


class MerchantScorecard(StrictModel):
    editorial_fit: int | None = Field(default=None, ge=0, le=30)
    destination_continuity: int | None = Field(default=None, ge=0, le=15)
    price_contract_completeness: int | None = Field(default=None, ge=0, le=15)
    confirmed_revenue_expectation: int | None = Field(default=None, ge=0, le=15)
    outcome_rule_clarity: int | None = Field(default=None, ge=0, le=10)
    confirmation_speed: int | None = Field(default=None, ge=0, le=5)
    human_audit_load: int | None = Field(default=None, ge=0, le=10)
    total: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def keep_unknown_axes_out_of_total(self) -> Self:
        axes = (
            self.editorial_fit,
            self.destination_continuity,
            self.price_contract_completeness,
            self.confirmed_revenue_expectation,
            self.outcome_rule_clarity,
            self.confirmation_speed,
            self.human_audit_load,
        )
        if any(value is None for value in axes):
            if self.total is not None:
                raise ValueError("incomplete scorecard total must remain unknown")
        elif self.total != sum(value for value in axes if value is not None):
            raise ValueError("scorecard total must equal its seven axes")
        return self


class MerchantEvidenceEntry(StrictModel):
    vendor_id: Slug
    program_id: EvidenceText
    network: EvidenceText
    affiliate_approval_status: Literal["approved", "pending", "denied", "unknown"]
    runtime_destination_status: GateStatus
    article_go: GateStatus
    channel_scope: Literal["owned_site"] = "owned_site"
    channel_go: GateStatus
    use_case_fit: EvidenceText
    plan_name: EvidenceText
    currency: EvidenceText
    tax_treatment: EvidenceText
    billing_cycle: EvidenceText
    first_invoice_total: MoneyEvidence
    renewal_amount: MoneyEvidence
    minimum_contract_term: EvidenceText
    cancellation_condition: EvidenceText
    promotion_condition: EvidenceText
    promotion_expiry: EvidenceText
    observation_date: date
    next_review_date: date
    source_url_references: tuple[AnyHttpUrl, ...] = Field(min_length=1, max_length=5)
    human_verifier: str = Field(min_length=2, max_length=80)
    success_condition: EvidenceText
    rejection_condition: EvidenceText
    confirmation_period: EvidenceText
    deep_link_permission: EvidenceText
    disclosure_precedes_cta: bool
    required_field_count: int = Field(ge=1, le=100)
    known_required_field_count: int = Field(ge=0, le=100)
    data_completeness_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    unknown_fields: tuple[str, ...]
    confidence: Literal["high", "medium", "low", "insufficient"]
    current_cta_eligibility: CtaEligibility
    hold_reasons: tuple[str, ...]
    scorecard: MerchantScorecard | None = None

    @field_validator("human_verifier")
    @classmethod
    def keep_verifier_non_personal(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", normalized):
            raise ValueError("human verifier must be a non-personal approver handle")
        return normalized

    @field_validator("unknown_fields", "hold_reasons")
    @classmethod
    def require_sorted_safe_lists(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(" ".join(item.strip().split()) for item in values)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("unknown fields and hold reasons must be unique and sorted")
        if any(not item or not _SAFE_TEXT.fullmatch(item) for item in normalized):
            raise ValueError("unknown fields and hold reasons must contain safe text")
        return normalized

    @model_validator(mode="after")
    def enforce_fail_closed_eligibility(self) -> Self:
        expected = (
            Decimal(self.known_required_field_count)
            / Decimal(self.required_field_count)
            * Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if self.data_completeness_percent != expected:
            raise ValueError("data completeness must be derived from required field counts")
        if self.known_required_field_count > self.required_field_count:
            raise ValueError("known required fields cannot exceed required fields")
        if self.next_review_date < self.observation_date:
            raise ValueError("next review date cannot precede observation date")

        hard_gates_pass = all(
            (
                self.affiliate_approval_status == "approved",
                self.runtime_destination_status is GateStatus.GO,
                self.article_go is GateStatus.GO,
                self.channel_go is GateStatus.GO,
                self.use_case_fit.status is EvidenceStatus.KNOWN,
                self.plan_name.status is EvidenceStatus.KNOWN,
                self.first_invoice_total.status is EvidenceStatus.KNOWN,
                self.success_condition.status is EvidenceStatus.KNOWN,
                self.disclosure_precedes_cta,
            )
        )
        if self.current_cta_eligibility is CtaEligibility.ELIGIBLE:
            if not hard_gates_pass or self.hold_reasons:
                raise ValueError("eligible CTA requires every hard gate and no hold reason")
            if self.scorecard is None:
                raise ValueError("eligible merchant requires a scorecard, even when some axes are unknown")
        elif hard_gates_pass and not self.hold_reasons:
            raise ValueError("a merchant with all hard gates must not be silently held")
        return self


class MerchantEvidenceMatrix(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    property_domain: Literal["saastcolab.jp"] = "saastcolab.jp"
    as_of_date: date
    article_id: Literal["SVR01"] = "SVR01"
    selection_basis: Literal[
        "cell_a_primary_and_alternative_plus_non_affiliate_evidence_control"
    ] = "cell_a_primary_and_alternative_plus_non_affiliate_evidence_control"
    affiliate_urls_saved: Literal[False] = False
    tracking_ids_saved: Literal[False] = False
    entries: tuple[MerchantEvidenceEntry, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_top_three_and_fresh_active_entries(self) -> Self:
        vendor_ids = tuple(entry.vendor_id for entry in self.entries)
        if vendor_ids != tuple(sorted(vendor_ids)) or len(set(vendor_ids)) != 3:
            raise ValueError("matrix must contain exactly three unique sorted vendors")
        for entry in self.entries:
            if (
                entry.current_cta_eligibility is CtaEligibility.ELIGIBLE
                and entry.next_review_date < self.as_of_date
            ):
                raise ValueError("expired merchant evidence cannot remain CTA eligible")
            if (
                entry.current_cta_eligibility is CtaEligibility.HOLD
                and not entry.hold_reasons
            ):
                raise ValueError("held merchant requires at least one explicit reason")
        return self


class RevenueEventName(str, Enum):
    CALCULATOR_RESULT_VIEW = "calculator_result_view"
    CTA_VIEW = "cta_view"
    CTA_ELIGIBLE_SESSION = "cta_eligible_session"
    OUTBOUND_CLICK = "outbound_click"


class RevenueCellId(str, Enum):
    CELL_A = "cell-a-comparison"
    CELL_B = "cell-b-single"
    NONE = "none"


class RevenueChannel(str, Enum):
    DIRECT = "direct"
    ORGANIC = "organic"
    REFERRAL = "referral"
    NOTE = "note"
    X = "x"
    PARTNER = "partner"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class RevenueSourceClass(str, Enum):
    DIRECT = "direct"
    SEARCH = "search"
    REFERRAL = "referral"
    NOTE = "note"
    X = "x"
    PARTNER = "partner"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class RevenueMediumClass(str, Enum):
    NONE = "none"
    ORGANIC = "organic"
    REFERRAL = "referral"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class RevenueTrafficScope(str, Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    BOT = "bot"
    UNKNOWN = "unknown"


class RevenueEnvironment(str, Enum):
    PRODUCTION = "production"
    PREVIEW = "preview"
    LOCAL = "local"


class RevenueAnalyticsContract(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    event_names: tuple[RevenueEventName, ...]
    allowed_dimensions: tuple[Literal[
        "article_id",
        "revenue_cell_id",
        "revenue_cell_version",
        "vendor_id",
        "cta_position",
        "cta_type",
        "channel",
        "source_class",
        "medium_class",
        "campaign_id",
        "environment",
        "traffic_scope",
        "test_flag",
    ], ...]
    prohibited_dimensions: tuple[Literal[
        "name",
        "email",
        "ip_address",
        "cookie",
        "credential",
        "affiliate_url",
        "raw_referrer_query",
        "raw_search_query",
        "tracking_parameters",
    ], ...]

    @model_validator(mode="after")
    def require_exact_contract(self) -> Self:
        if set(self.event_names) != set(RevenueEventName):
            raise ValueError("analytics contract must list every revenue event once")
        if len(set(self.event_names)) != len(self.event_names):
            raise ValueError("analytics event names must be unique")
        if len(set(self.allowed_dimensions)) != len(self.allowed_dimensions):
            raise ValueError("allowed dimensions must be unique")
        if len(set(self.prohibited_dimensions)) != len(self.prohibited_dimensions):
            raise ValueError("prohibited dimensions must be unique")
        return self


class RevenueCellDailyAggregate(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    observed_on: date
    article_id: str
    revenue_cell_id: RevenueCellId
    revenue_cell_version: Literal["v2"]
    vendor_id: Slug | Literal["none"]
    cta_position: Literal["primary", "alternative", "single", "article_action", "none"]
    cta_type: Literal["affiliate_comparison", "affiliate_single", "saas_affiliate", "none"]
    channel: RevenueChannel
    source_class: RevenueSourceClass
    medium_class: RevenueMediumClass
    campaign_id: str
    environment: RevenueEnvironment
    traffic_scope: RevenueTrafficScope
    test_flag: bool
    calculator_result_views: int = Field(ge=0)
    cta_views: int = Field(ge=0)
    cta_view_sessions: int = Field(ge=0)
    eligible_sessions: int = Field(ge=0)
    outbound_clicks: int = Field(ge=0)
    unique_outbound_sessions: int = Field(ge=0)
    asp_clicks: int | None = Field(default=None, ge=0)
    pending_conversions: int | None = Field(default=None, ge=0)
    pending_commission_minor: Decimal | None = Field(default=None, ge=0, decimal_places=8)
    confirmed_conversions: int | None = Field(default=None, ge=0)
    rejected_conversions: int | None = Field(default=None, ge=0)
    matured_eligible_sessions: int | None = Field(default=None, ge=0)
    confirmed_commission_minor: Decimal | None = Field(default=None, ge=0, decimal_places=8)

    @field_validator("article_id")
    @classmethod
    def require_article_id(cls, value: str) -> str:
        if not _ARTICLE_ID.fullmatch(value):
            raise ValueError("article ID is outside the published article namespace")
        return value

    @field_validator("campaign_id")
    @classmethod
    def require_safe_campaign_id(cls, value: str) -> str:
        if not _CAMPAIGN_ID.fullmatch(value):
            raise ValueError("campaign ID must be a short safe slug")
        return value

    @model_validator(mode="after")
    def require_consistent_counts(self) -> Self:
        if self.cta_view_sessions > self.cta_views:
            raise ValueError("CTA view sessions cannot exceed CTA view events")
        if self.eligible_sessions > self.cta_view_sessions:
            raise ValueError("eligible sessions cannot exceed CTA view sessions")
        if self.outbound_clicks > self.cta_views:
            raise ValueError("outbound clicks cannot exceed observed CTA views")
        if self.unique_outbound_sessions > self.cta_view_sessions:
            raise ValueError("unique outbound sessions cannot exceed CTA view sessions")
        if self.unique_outbound_sessions > self.eligible_sessions:
            raise ValueError("unique outbound sessions cannot exceed eligible sessions")
        if self.unique_outbound_sessions > self.outbound_clicks:
            raise ValueError("unique outbound sessions cannot exceed outbound click events")
        if self.matured_eligible_sessions is not None and self.matured_eligible_sessions > self.eligible_sessions:
            raise ValueError("matured eligible sessions cannot exceed eligible sessions")
        if self.pending_commission_minor is not None:
            if self.pending_conversions is None:
                raise ValueError("pending commission requires a pending conversion count")
            if self.pending_commission_minor > 0 and self.pending_conversions == 0:
                raise ValueError("positive pending commission requires a positive conversion count")
        if self.confirmed_commission_minor is not None:
            if self.confirmed_conversions is None:
                raise ValueError("confirmed commission requires a confirmed conversion count")
            if self.confirmed_commission_minor > 0 and self.confirmed_conversions == 0:
                raise ValueError("positive confirmed commission requires a positive conversion count")
        return self


class RevenueCellAggregateSummary(StrictModel):
    decision_ready: bool
    article_id: str | None = None
    revenue_cell_id: RevenueCellId | None = None
    revenue_cell_version: Literal["v2"] | None = None
    vendor_id: Slug | Literal["none"] | None = None
    cta_position: Literal["primary", "alternative", "single", "article_action", "none"] | None = None
    cta_type: Literal["affiliate_comparison", "affiliate_single", "saas_affiliate", "none"] | None = None
    channel: RevenueChannel | None = None
    source_class: RevenueSourceClass | None = None
    medium_class: RevenueMediumClass | None = None
    campaign_id: str | None = None
    included_rows: int = Field(ge=0)
    excluded_rows: int = Field(ge=0)
    calculator_result_views: int = Field(ge=0)
    cta_views: int = Field(ge=0)
    cta_view_sessions: int = Field(ge=0)
    eligible_sessions: int = Field(ge=0)
    outbound_clicks: int = Field(ge=0)
    unique_outbound_sessions: int = Field(ge=0)
    asp_clicks: int | None = Field(default=None, ge=0)
    pending_conversions: int | None = Field(default=None, ge=0)
    pending_commission_minor: Decimal | None = Field(default=None, ge=0)
    confirmed_conversions: int | None = Field(default=None, ge=0)
    rejected_conversions: int | None = Field(default=None, ge=0)
    matured_eligible_sessions: int | None = Field(default=None, ge=0)
    confirmed_commission_minor: Decimal | None = Field(default=None, ge=0)
    outbound_ctr_percent: Decimal | None = Field(default=None, ge=0)
    confirmed_rpes_minor: Decimal | None = Field(default=None, ge=0)


def summarize_revenue_cell(
    rows: tuple[RevenueCellDailyAggregate, ...],
) -> RevenueCellAggregateSummary:
    """Aggregate only production, external, non-test rows.

    Missing maturity or commission remains unknown; it is never zero-filled.
    """

    included = tuple(
        row
        for row in rows
        if row.environment is RevenueEnvironment.PRODUCTION
        and row.traffic_scope is RevenueTrafficScope.EXTERNAL
        and not row.test_flag
    )
    grouping_keys = {
        (
            row.article_id,
            row.revenue_cell_id,
            row.revenue_cell_version,
            row.vendor_id,
            row.cta_position,
            row.cta_type,
            row.channel,
            row.source_class,
            row.medium_class,
            row.campaign_id,
        )
        for row in included
    }
    if len(grouping_keys) > 1:
        raise ValueError(
            "safe aggregate rows must share article, cell/version, CTA, channel/source/medium, and campaign"
        )
    grouping_key = next(iter(grouping_keys), None)
    eligible = sum(row.eligible_sessions for row in included)
    outbound_sessions = sum(row.unique_outbound_sessions for row in included)
    matured_values = [row.matured_eligible_sessions for row in included]
    commission_values = [row.confirmed_commission_minor for row in included]
    def complete_sum(field_name: str) -> int | Decimal | None:
        values = [getattr(row, field_name) for row in included]
        if not included or not all(value is not None for value in values):
            return None
        return sum((value for value in values if value is not None), 0)

    matured = (
        sum(value for value in matured_values if value is not None)
        if included and all(value is not None for value in matured_values)
        else None
    )
    commission = (
        sum((value for value in commission_values if value is not None), Decimal(0))
        if included and all(value is not None for value in commission_values)
        else None
    )
    outbound_ctr = (
        (Decimal(outbound_sessions) / Decimal(eligible) * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if eligible > 0
        else None
    )
    confirmed_rpes = (
        (commission / Decimal(matured)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if commission is not None and matured is not None and matured > 0
        else None
    )
    return RevenueCellAggregateSummary(
        decision_ready=bool(included),
        article_id=grouping_key[0] if grouping_key else None,
        revenue_cell_id=grouping_key[1] if grouping_key else None,
        revenue_cell_version=grouping_key[2] if grouping_key else None,
        vendor_id=grouping_key[3] if grouping_key else None,
        cta_position=grouping_key[4] if grouping_key else None,
        cta_type=grouping_key[5] if grouping_key else None,
        channel=grouping_key[6] if grouping_key else None,
        source_class=grouping_key[7] if grouping_key else None,
        medium_class=grouping_key[8] if grouping_key else None,
        campaign_id=grouping_key[9] if grouping_key else None,
        included_rows=len(included),
        excluded_rows=len(rows) - len(included),
        calculator_result_views=sum(row.calculator_result_views for row in included),
        cta_views=sum(row.cta_views for row in included),
        cta_view_sessions=sum(row.cta_view_sessions for row in included),
        eligible_sessions=eligible,
        outbound_clicks=sum(row.outbound_clicks for row in included),
        unique_outbound_sessions=outbound_sessions,
        asp_clicks=complete_sum("asp_clicks"),
        pending_conversions=complete_sum("pending_conversions"),
        pending_commission_minor=complete_sum("pending_commission_minor"),
        confirmed_conversions=complete_sum("confirmed_conversions"),
        rejected_conversions=complete_sum("rejected_conversions"),
        matured_eligible_sessions=matured,
        confirmed_commission_minor=commission,
        outbound_ctr_percent=outbound_ctr,
        confirmed_rpes_minor=confirmed_rpes,
    )
