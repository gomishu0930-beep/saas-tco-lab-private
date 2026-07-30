"""Human-entered editorial observations for rights model v2.

This contract is deliberately network-free and is not a pricing database.  It
keeps vendor-plan observations separate from Human scenario inputs, represents
unknowns without guessing, and never grants automated fetch, raw storage,
history, calculation eligibility, or publication authority.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
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


class HumanEditorialNumericField(StrictModel):
    """One Human-reviewed field for one vendor-plan or Human scenario."""

    schema_version: Literal["2.1"] = "2.1"
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
    source_url: AnyHttpUrl | None = None
    scenario_basis: str | None = Field(default=None, min_length=1, max_length=300)
    observed_on: date
    next_review_on: date
    entered_by: Literal["human"] = "human"
    acquisition_method: Literal["manual_public_page", "human_scenario_input"]
    rights_path: Literal["human_editorial"] = "human_editorial"
    review_status: EditorialReviewStatus = EditorialReviewStatus.UNREVIEWED

    @field_validator("value")
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
            if self.acquisition_method != "manual_public_page":
                raise ValueError("vendor_plan scope requires manual_public_page acquisition")
        else:
            if self.vendor_id is not None or self.plan_id is not None:
                raise ValueError("human_scenario scope cannot carry vendor_id or plan_id")
            if self.source_url is not None:
                raise ValueError("human_scenario scope cannot use a vendor source_url")
            if self.scenario_basis is None:
                raise ValueError("human_scenario scope requires scenario_basis")
            if self.acquisition_method != "human_scenario_input":
                raise ValueError("human_scenario scope requires human_scenario_input acquisition")

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
        else:
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
                )
            ):
                raise ValueError("currency and billing metadata are only valid for price values")
        return self


class EditorialArticleInput(StrictModel):
    """Human-reviewable input slate for one P01–P12 article template."""

    schema_version: Literal["2.1"] = "2.1"
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
        "pricing.base_price": EditorialValueKind.PRICE,
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
    numeric_fields: tuple[HumanEditorialNumericField, ...] = ()

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
