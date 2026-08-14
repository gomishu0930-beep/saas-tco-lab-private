"""Human-entered editorial observations for rights model v2.

This contract is deliberately network-free and is not a pricing database.  It
keeps vendor-plan observations separate from Human scenario inputs, represents
unknowns without guessing, and never grants automated fetch, raw storage,
history, calculation eligibility, or publication authority.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Literal, Self
from urllib.parse import parse_qsl

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from .models import CurrencyCode, FieldPath, Slug, StrictModel


class EditorialValueKind(str, Enum):
    PRICE = "price"
    QUOTA = "quota"
    SEAT_COUNT = "seat_count"
    TAX_RATE = "tax_rate"
    EXCHANGE_RATE = "exchange_rate"
    DURATION = "duration"
    USAGE = "usage"
    PERCENTAGE = "percentage"
    OTHER = "other"


class EditorialBillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"
    PER_USAGE = "per_usage"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class EditorialTaxTreatment(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class EditorialReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class EditorialScopeKind(str, Enum):
    VENDOR_PLAN = "vendor_plan"
    HUMAN_SCENARIO = "human_scenario"


class EditorialValueStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EditorialCurrencyStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EditorialBillingToggleState(str, Enum):
    ANNUAL_SELECTED = "annual_selected"
    MONTHLY_SELECTED = "monthly_selected"
    NOT_PRESENT = "not_present"
    UNKNOWN = "unknown"


class EditorialSaleBannerState(str, Enum):
    NONE = "none"
    ANNUAL_DISCOUNT_PERMANENT = "annual_discount_permanent"
    TIME_LIMITED_PROMO = "time_limited_promo"
    UNKNOWN = "unknown"


class EditorialObservedPriceBasis(str, Enum):
    CHECKOUT_BILLED_TOTAL = "checkout_billed_total"
    DISPLAYED_PRICE = "displayed_price"
    HUMAN_SCENARIO = "human_scenario"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


_SAFE_QUERY_KEYS = frozenset(
    {"billing", "country", "currency", "edition", "lang", "locale", "period", "plan", "region"}
)
_TRACKING_QUERY_MARKERS = (
    "affiliate",
    "aff",
    "clickid",
    "partner",
    "ref",
    "subid",
    "tracking",
    "utm_",
)

_ZERO_MINOR_UNIT_CURRENCIES = frozenset(
    {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF"}
)
_THREE_MINOR_UNIT_CURRENCIES = frozenset(
    {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}
)
_FOUR_MINOR_UNIT_CURRENCIES = frozenset({"CLF", "UYW"})


def _currency_minor_unit_digits(currency: CurrencyCode | None) -> int | None:
    if currency is None:
        return None
    if currency in _ZERO_MINOR_UNIT_CURRENCIES:
        return 0
    if currency in _THREE_MINOR_UNIT_CURRENCIES:
        return 3
    if currency in _FOUR_MINOR_UNIT_CURRENCIES:
        return 4
    return 2


def _exact_annual_monthly_equivalent(
    annual_total: Decimal, currency: CurrencyCode | None
) -> Decimal | None:
    """Return a monthly value only when the annual total divides into exact minor units."""

    digits = _currency_minor_unit_digits(currency)
    if digits is None:
        return None
    scale = Decimal(10) ** digits
    minor_units = annual_total * scale
    integral_minor_units = minor_units.to_integral_value()
    if minor_units != integral_minor_units:
        return None
    minor_units_integer = int(integral_minor_units)
    if minor_units_integer % 12 != 0:
        return None
    return (Decimal(minor_units_integer // 12) / scale).normalize()


def _rounded_annual_discount_percent(
    annual_total: Decimal, monthly_reference: Decimal
) -> Decimal | None:
    """Return the nearest whole discount percent for a same-plan monthly reference."""

    if monthly_reference <= 0 or annual_total < 0:
        return None
    monthly_twelve_month_total = monthly_reference * Decimal(12)
    if annual_total >= monthly_twelve_month_total:
        return None
    return (
        (Decimal(1) - annual_total / monthly_twelve_month_total) * Decimal(100)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class HumanEditorialNumericField(StrictModel):
    """One Human-reviewed field for one vendor-plan or Human scenario."""

    schema_version: Literal["2.3"] = "2.3"
    scope_kind: EditorialScopeKind
    vendor_id: Slug | None = None
    plan_id: Slug | None = None
    field: FieldPath
    value_kind: EditorialValueKind
    value_status: EditorialValueStatus = EditorialValueStatus.KNOWN
    value: Decimal | None = Field(default=None, max_digits=30, decimal_places=8)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    unknown_reason: str | None = Field(default=None, min_length=1, max_length=300)
    currency_status: EditorialCurrencyStatus = EditorialCurrencyStatus.NOT_APPLICABLE
    currency: CurrencyCode | None = None
    currency_display: str | None = Field(default=None, min_length=1, max_length=20)
    currency_unknown_reason: str | None = Field(default=None, min_length=1, max_length=300)
    billing_period: EditorialBillingPeriod | None = None
    tax_treatment: EditorialTaxTreatment | None = None
    billing_toggle_state: EditorialBillingToggleState | None
    sale_banner_state: EditorialSaleBannerState | None
    observed_price_basis: EditorialObservedPriceBasis | None
    derived_monthly_value: Decimal | None = Field(max_digits=30, decimal_places=8)
    derived_monthly_unit: Literal["/ mo"] | None
    derivation_method: Literal["annual_checkout_total_divided_by_12"] | None
    monthly_reference_value: Decimal | None = Field(
        default=None, max_digits=30, decimal_places=8
    )
    monthly_reference_unit: Literal["/ mo"] | None = None
    derived_annual_discount_percent: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=2
    )
    discount_derivation_method: Literal[
        "one_minus_annual_total_divided_by_monthly_price_times_12"
    ] | None = None
    source_url: AnyHttpUrl | None = None
    scenario_basis: str | None = Field(default=None, min_length=1, max_length=300)
    observed_on: date
    next_review_on: date
    entered_by: Literal["human"] = "human"
    acquisition_method: Literal[
        "manual_public_page", "manual_checkout_review", "human_scenario_input"
    ]
    rights_path: Literal["human_editorial"] = "human_editorial"
    review_status: EditorialReviewStatus = EditorialReviewStatus.UNREVIEWED

    @field_validator(
        "value", "derived_monthly_value", "monthly_reference_value", "derived_annual_discount_percent"
    )
    @classmethod
    def require_finite_value(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not math.isfinite(float(value)):
            raise ValueError("editorial numeric value must be finite")
        return value

    @field_validator(
        "unit",
        "unknown_reason",
        "currency_display",
        "currency_unknown_reason",
        "scenario_basis",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("editorial text cannot be blank")
        return normalized

    @field_validator("source_url")
    @classmethod
    def require_safe_public_source(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is None:
            return None
        if value.scheme != "https":
            raise ValueError("editorial source URL must use HTTPS")
        if value.username or value.password or value.fragment:
            raise ValueError("editorial source URL cannot contain credentials or fragments")
        host = (value.host or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise ValueError("editorial source URL must be public")
        for key, raw_value in parse_qsl(value.query or "", keep_blank_values=True):
            normalized_key = key.lower()
            if normalized_key not in _SAFE_QUERY_KEYS or any(
                marker in normalized_key for marker in _TRACKING_QUERY_MARKERS
            ):
                raise ValueError("editorial source URL contains an unapproved query parameter")
            if not raw_value or len(raw_value) > 80:
                raise ValueError("editorial source URL query value is invalid")
        return value

    @model_validator(mode="after")
    def validate_editorial_observation(self) -> Self:
        if self.next_review_on <= self.observed_on:
            raise ValueError("next_review_on must be later than observed_on")
        if self.next_review_on > self.observed_on + timedelta(days=180):
            raise ValueError("editorial review interval cannot exceed 180 days")

        if self.scope_kind is EditorialScopeKind.VENDOR_PLAN:
            if self.vendor_id is None or self.plan_id is None:
                raise ValueError("vendor_plan scope requires vendor_id and plan_id")
            if self.source_url is None:
                raise ValueError("vendor_plan scope requires a public source_url")
            if self.scenario_basis is not None:
                raise ValueError("scenario_basis is only valid for human_scenario scope")
            if self.acquisition_method not in {"manual_public_page", "manual_checkout_review"}:
                raise ValueError("vendor_plan scope requires an approved manual acquisition method")
            if self.billing_toggle_state is None or self.sale_banner_state is None:
                raise ValueError("vendor_plan scope requires billing toggle and sale banner state")
        else:
            if self.vendor_id is not None or self.plan_id is not None:
                raise ValueError("human_scenario scope cannot carry vendor_id or plan_id")
            if self.source_url is not None:
                raise ValueError("human_scenario scope cannot use a vendor source_url")
            if self.scenario_basis is None:
                raise ValueError("human_scenario scope requires scenario_basis")
            if self.acquisition_method != "human_scenario_input":
                raise ValueError("human_scenario scope requires human_scenario_input acquisition")
            if self.billing_toggle_state is not None or self.sale_banner_state is not None:
                raise ValueError("human_scenario scope cannot carry vendor screen state")

        if self.value_status is EditorialValueStatus.KNOWN:
            if self.value is None or self.unit is None:
                raise ValueError("known editorial values require value and unit")
            if self.unknown_reason is not None:
                raise ValueError("unknown_reason is only valid for unknown or not_applicable values")
        else:
            if self.value is not None:
                raise ValueError("unknown or not_applicable values cannot carry a numeric value")
            if self.unknown_reason is None:
                raise ValueError("unknown or not_applicable values require unknown_reason")

        if self.value_kind is EditorialValueKind.PRICE:
            if self.scope_kind is EditorialScopeKind.HUMAN_SCENARIO:
                if self.observed_price_basis is not EditorialObservedPriceBasis.HUMAN_SCENARIO:
                    raise ValueError("human scenario price requires human_scenario price basis")
            elif self.value_status is EditorialValueStatus.NOT_APPLICABLE:
                if self.observed_price_basis is not EditorialObservedPriceBasis.NOT_APPLICABLE:
                    raise ValueError("not_applicable price requires not_applicable price basis")
            elif self.value_status is EditorialValueStatus.UNKNOWN:
                if self.observed_price_basis is not EditorialObservedPriceBasis.UNKNOWN:
                    raise ValueError("unknown price requires unknown price basis")
            elif self.billing_period is EditorialBillingPeriod.ANNUAL:
                if self.observed_price_basis is not EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL:
                    raise ValueError("annual price must use checkout billed total as the primary observation")
            elif self.observed_price_basis not in {
                EditorialObservedPriceBasis.DISPLAYED_PRICE,
                EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL,
            }:
                raise ValueError("known vendor price requires an observed price basis")

            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.observed_price_basis is EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL
                and self.acquisition_method != "manual_checkout_review"
            ):
                raise ValueError("checkout billed total requires manual_checkout_review acquisition")
            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.observed_price_basis is not EditorialObservedPriceBasis.CHECKOUT_BILLED_TOTAL
                and self.acquisition_method != "manual_public_page"
            ):
                raise ValueError("non-checkout vendor observation requires manual_public_page acquisition")

            if self.value_status is EditorialValueStatus.NOT_APPLICABLE:
                if self.currency_status is not EditorialCurrencyStatus.NOT_APPLICABLE:
                    raise ValueError("not_applicable price requires not_applicable currency_status")
                if self.billing_period is not EditorialBillingPeriod.NOT_APPLICABLE:
                    raise ValueError("not_applicable price requires not_applicable billing_period")
                if self.tax_treatment is not EditorialTaxTreatment.NOT_APPLICABLE:
                    raise ValueError("not_applicable price requires not_applicable tax_treatment")
            elif self.currency_status is EditorialCurrencyStatus.KNOWN:
                if self.currency is None:
                    raise ValueError("known price currency requires an explicit ISO currency code")
                if self.currency_unknown_reason is not None:
                    raise ValueError("currency_unknown_reason is only valid for unknown currency")
            elif self.currency_status is EditorialCurrencyStatus.UNKNOWN:
                if self.currency is not None:
                    raise ValueError("unknown currency cannot carry an inferred ISO currency code")
                if self.currency_unknown_reason is None:
                    raise ValueError("unknown currency requires a reason")
                if (
                    self.value_status is EditorialValueStatus.KNOWN
                    and self.currency_display is None
                ):
                    raise ValueError("known price with unknown currency requires display text")
            else:
                raise ValueError("price requires known, unknown, or valid not_applicable currency status")
            if self.billing_period is None:
                raise ValueError("price requires an explicit billing_period, including unknown")
            if self.tax_treatment is None:
                raise ValueError("price requires an explicit tax_treatment, including unknown")

            derived_items = (
                self.derived_monthly_value,
                self.derived_monthly_unit,
                self.derivation_method,
            )
            discount_items = (
                self.monthly_reference_value,
                self.monthly_reference_unit,
                self.derived_annual_discount_percent,
                self.discount_derivation_method,
            )
            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.value_status is EditorialValueStatus.KNOWN
                and self.billing_period is EditorialBillingPeriod.ANNUAL
            ):
                assert self.value is not None
                expected = _exact_annual_monthly_equivalent(self.value, self.currency)
                if expected is None:
                    if any(item is not None for item in derived_items):
                        raise ValueError(
                            "annual monthly equivalent must be omitted when the checkout total "
                            "does not divide exactly into currency minor units"
                        )
                else:
                    if self.derived_monthly_value != expected:
                        raise ValueError("annual monthly equivalent must equal exact checkout total divided by 12")
                    if self.derived_monthly_unit != "/ mo":
                        raise ValueError("annual monthly equivalent requires / mo unit")
                    if self.derivation_method != "annual_checkout_total_divided_by_12":
                        raise ValueError("annual monthly equivalent requires the fixed derivation method")
                if self.billing_toggle_state is not EditorialBillingToggleState.ANNUAL_SELECTED:
                    raise ValueError("annual checkout total requires annual_selected billing toggle")
            elif any(item is not None for item in derived_items):
                raise ValueError("monthly equivalent is only valid for a known annual checkout total")

            requires_discount_evidence = (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.value_status is EditorialValueStatus.KNOWN
                and self.billing_period is EditorialBillingPeriod.ANNUAL
                and self.sale_banner_state
                is EditorialSaleBannerState.ANNUAL_DISCOUNT_PERMANENT
            )
            if requires_discount_evidence:
                if any(item is None for item in discount_items):
                    raise ValueError(
                        "known permanent annual discount requires monthly reference and derived percent"
                    )
                assert self.value is not None
                assert self.monthly_reference_value is not None
                expected_discount = _rounded_annual_discount_percent(
                    self.value, self.monthly_reference_value
                )
                if expected_discount is None:
                    raise ValueError(
                        "annual checkout total must be lower than the positive monthly reference times 12"
                    )
                if self.monthly_reference_unit != "/ mo":
                    raise ValueError("monthly discount reference requires / mo unit")
                if self.derived_annual_discount_percent != expected_discount:
                    raise ValueError(
                        "annual discount percent must match the fixed Human-evidence derivation"
                    )
                if self.discount_derivation_method != (
                    "one_minus_annual_total_divided_by_monthly_price_times_12"
                ):
                    raise ValueError("annual discount requires the fixed derivation method")
            elif any(item is not None for item in discount_items):
                raise ValueError(
                    "annual discount evidence is only valid for a known permanent annual discount"
                )

            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.billing_period is EditorialBillingPeriod.MONTHLY
                and self.billing_toggle_state is EditorialBillingToggleState.ANNUAL_SELECTED
            ):
                raise ValueError("monthly price cannot use annual_selected billing toggle")
            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.billing_period is EditorialBillingPeriod.ANNUAL
                and self.billing_toggle_state is EditorialBillingToggleState.MONTHLY_SELECTED
            ):
                raise ValueError("annual price cannot use monthly_selected billing toggle")
        else:
            if (
                self.scope_kind is EditorialScopeKind.VENDOR_PLAN
                and self.acquisition_method != "manual_public_page"
            ):
                raise ValueError("non-price vendor observation requires manual_public_page acquisition")
            if self.currency_status is not EditorialCurrencyStatus.NOT_APPLICABLE:
                raise ValueError("currency_status is only applicable to price values")
            if any(
                item is not None
                for item in (
                    self.currency,
                    self.currency_display,
                    self.currency_unknown_reason,
                    self.billing_period,
                    self.tax_treatment,
                    self.observed_price_basis,
                    self.derived_monthly_value,
                    self.derived_monthly_unit,
                    self.derivation_method,
                    self.monthly_reference_value,
                    self.monthly_reference_unit,
                    self.derived_annual_discount_percent,
                    self.discount_derivation_method,
                )
            ):
                raise ValueError("currency and billing metadata are only valid for price values")
        return self


class EditorialArticleInput(StrictModel):
    """Human-reviewable input slate for one P01–P12 article template."""

    schema_version: Literal["2.3"] = "2.3"
    article_id: str = Field(pattern=r"^P(?:0[1-9]|1[0-2])$")
    slug: Slug
    title: str = Field(min_length=1, max_length=180)
    disclosure_version: Literal["pr-affiliate-v1"] = "pr-affiliate-v1"
    numeric_fields: tuple[HumanEditorialNumericField, ...] = ()
    article_review_status: EditorialReviewStatus = EditorialReviewStatus.UNREVIEWED

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @model_validator(mode="after")
    def require_unique_fields(self) -> Self:
        identities = [
            (item.scope_kind, item.vendor_id, item.plan_id, item.field)
            for item in self.numeric_fields
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("editorial numeric field identities must be unique")
        return self


class ExpansionCategory(str, Enum):
    ACCOUNTING = "accounting"
    CRM = "crm"
    FORMS = "forms"
    EMAIL_MARKETING = "email_marketing"
    SERVERS = "servers"


_EXPANSION_FIELD_KINDS: dict[ExpansionCategory, dict[str, EditorialValueKind]] = {
    ExpansionCategory.ACCOUNTING: {
        "pricing.base_price": EditorialValueKind.PRICE,
        "pricing.minimum_seats": EditorialValueKind.SEAT_COUNT,
        "accounting.entity_count": EditorialValueKind.QUOTA,
        "accounting.monthly_transactions": EditorialValueKind.QUOTA,
    },
    ExpansionCategory.CRM: {
        "pricing.base_price": EditorialValueKind.PRICE,
        "pricing.minimum_seats": EditorialValueKind.SEAT_COUNT,
        "crm.contact_count": EditorialValueKind.QUOTA,
        "crm.automation_addon_price": EditorialValueKind.PRICE,
    },
    ExpansionCategory.FORMS: {
        "pricing.base_price": EditorialValueKind.PRICE,
        "forms.monthly_responses": EditorialValueKind.QUOTA,
        "forms.storage_quota": EditorialValueKind.QUOTA,
        "forms.payment_fee": EditorialValueKind.PERCENTAGE,
    },
    ExpansionCategory.EMAIL_MARKETING: {
        "pricing.base_price": EditorialValueKind.PRICE,
        "email.contact_count": EditorialValueKind.QUOTA,
        "email.monthly_sends": EditorialValueKind.QUOTA,
        "email.overage_price": EditorialValueKind.PRICE,
    },
    ExpansionCategory.SERVERS: {
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
    },
}


def expansion_field_kinds(category: ExpansionCategory) -> dict[str, EditorialValueKind]:
    """Return a copy of the candidate-only field catalog for one expansion category."""

    return dict(_EXPANSION_FIELD_KINDS[category])


class CategoryExpansionInput(StrictModel):
    """Candidate-only editorial input for a future scope expansion.

    This is not a publication, index, Affiliate, or scope-expansion authority.
    Numeric observations reuse the rights-model-v2 Human field contract.
    """

    schema_version: Literal["1.0"] = "1.0"
    category_id: ExpansionCategory
    template_kind: Literal["pricing_tco"] = "pricing_tco"
    state: Literal["candidate_only"] = "candidate_only"
    numeric_fields: tuple[HumanEditorialNumericField, ...] = Field(
        default=(),
        json_schema_extra={
            "x-category-field-catalog": {
                category.value: {
                    field: kind.value for field, kind in fields.items()
                }
                for category, fields in _EXPANSION_FIELD_KINDS.items()
            }
        },
    )

    @model_validator(mode="after")
    def validate_category_fields(self) -> Self:
        if not self.numeric_fields:
            return self
        if any(item.scope_kind is not EditorialScopeKind.VENDOR_PLAN for item in self.numeric_fields):
            raise ValueError("category expansion input currently accepts vendor_plan fields only")

        expected = expansion_field_kinds(self.category_id)
        grouped: dict[tuple[Slug, Slug], list[HumanEditorialNumericField]] = {}
        for item in self.numeric_fields:
            assert item.vendor_id is not None and item.plan_id is not None
            grouped.setdefault((item.vendor_id, item.plan_id), []).append(item)
        for identity, fields in grouped.items():
            actual = {str(item.field): item.value_kind for item in fields}
            if actual != expected:
                raise ValueError(
                    f"category expansion fields do not match {self.category_id.value} catalog for "
                    f"{identity[0]}/{identity[1]}"
                )
        return self
