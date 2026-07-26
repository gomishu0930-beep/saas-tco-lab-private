"""Strict, versioned contracts for lawful SaaS-pricing evidence.

Pydantic models in this module are the sole schema authority.  JSON Schema is a
generated artifact; it must never be maintained by hand.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    ),
]
FieldPath = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
NonNegativeMoney = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=24, decimal_places=8)]
NonNegativeQuantity = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=30, decimal_places=8)]
TaxRate = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"), decimal_places=8)]


class StrictModel(BaseModel):
    """Common no-coercion/no-extra-fields boundary."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PolicyDecision(str, Enum):
    """An explicit decision.  Missing review is never equivalent to approval."""

    APPROVED = "approved"
    PROHIBITED = "prohibited"
    UNREVIEWED = "unreviewed"


class PolicyAction(str, Enum):
    FETCH = "fetch"
    STORE_RAW = "store_raw"
    SEND_TO_AI = "send_to_ai"
    DERIVE = "derive"
    PUBLISH = "publish"
    RETAIN_HISTORY = "retain_history"
    QUOTE = "quote"


class AcquisitionMethod(str, Enum):
    OFFICIAL_API = "official_api"
    VENDOR_FEED = "vendor_feed"
    DIRECT_HTTP = "direct_http"
    BROWSER = "browser"
    MANUAL = "manual"


class EvidenceKind(str, Enum):
    FACT = "fact"
    PARAPHRASE = "paraphrase"
    QUOTE = "quote"


class SourcePolicy(StrictModel):
    """Field-level permission record for one source and one review window.

    Every capability defaults to ``unreviewed``.  Callers must use ``permits``
    instead of testing enum truthiness; enum members are intentionally never
    booleans.
    """

    policy_id: UUID = Field(default_factory=uuid4)
    field: FieldPath
    source_url: AnyHttpUrl
    acquisition_method: AcquisitionMethod
    fetch: PolicyDecision = PolicyDecision.UNREVIEWED
    store_raw: PolicyDecision = PolicyDecision.UNREVIEWED
    send_to_ai: PolicyDecision = PolicyDecision.UNREVIEWED
    derive: PolicyDecision = PolicyDecision.UNREVIEWED
    publish: PolicyDecision = PolicyDecision.UNREVIEWED
    retain_history: PolicyDecision = PolicyDecision.UNREVIEWED
    quote: PolicyDecision = PolicyDecision.UNREVIEWED
    attribution_required: bool | None = None
    attribution_text: str | None = Field(default=None, min_length=1, max_length=500)
    max_quote_chars: int | None = Field(default=None, ge=1, le=500)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    reviewed_at: datetime
    review_due_at: datetime
    reviewed_by: str = Field(min_length=1, max_length=120)
    basis: str = Field(min_length=1, max_length=500)
    basis_url: AnyHttpUrl | None = None

    @field_validator("source_url", "basis_url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("policy URLs must use HTTPS")
        return value

    @field_validator("reviewed_at", "review_due_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("policy timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_permission_dependencies(self) -> Self:
        if self.review_due_at <= self.reviewed_at:
            raise ValueError("review_due_at must be later than reviewed_at")

        downstream = (
            self.store_raw,
            self.send_to_ai,
            self.derive,
            self.publish,
            self.retain_history,
            self.quote,
        )
        if PolicyDecision.APPROVED in downstream and self.fetch is not PolicyDecision.APPROVED:
            raise ValueError("downstream approval requires explicitly approved fetch")

        if self.publish is PolicyDecision.APPROVED or self.quote is PolicyDecision.APPROVED:
            if self.attribution_required is None:
                raise ValueError("publish/quote approval requires an explicit attribution decision")
        if self.attribution_required is True and not self.attribution_text:
            raise ValueError("attribution_text is required when attribution is required")
        if self.attribution_required is not True and self.attribution_text is not None:
            raise ValueError("attribution_text is only valid when attribution_required is true")

        if self.quote is PolicyDecision.APPROVED and self.max_quote_chars is None:
            raise ValueError("approved quote policy requires max_quote_chars")
        if self.quote is not PolicyDecision.APPROVED and self.max_quote_chars is not None:
            raise ValueError("max_quote_chars is only valid for an approved quote policy")

        retained = (
            self.store_raw is PolicyDecision.APPROVED
            or self.retain_history is PolicyDecision.APPROVED
        )
        if retained and self.retention_days is None:
            raise ValueError("raw/history approval requires retention_days")
        if not retained and self.retention_days is not None:
            raise ValueError("retention_days is only valid for approved raw/history storage")
        return self

    def decision_for(self, action: PolicyAction) -> PolicyDecision:
        field_name = {
            PolicyAction.FETCH: "fetch",
            PolicyAction.STORE_RAW: "store_raw",
            PolicyAction.SEND_TO_AI: "send_to_ai",
            PolicyAction.DERIVE: "derive",
            PolicyAction.PUBLISH: "publish",
            PolicyAction.RETAIN_HISTORY: "retain_history",
            PolicyAction.QUOTE: "quote",
        }[action]
        return getattr(self, field_name)

    def permits(self, action: PolicyAction, *, at: datetime | None = None) -> bool:
        """Return true only for explicit, currently-effective approval."""

        instant = at or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("permission checks require a timezone-aware timestamp")
        return (
            self.reviewed_at <= instant < self.review_due_at
            and self.decision_for(action) is PolicyDecision.APPROVED
        )


class RawArchivePointer(StrictModel):
    """Metadata pointer only; raw source bytes never enter the pricing record."""

    relative_path: str = Field(min_length=1, max_length=500)
    sha256: Sha256
    captured_at: datetime
    delete_after: datetime

    @field_validator("relative_path")
    @classmethod
    def require_safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or value in {".", ".."}
            or value.endswith("/")
            or "\\" in value
            or "\x00" in value
        ):
            raise ValueError("archive path must be a safe relative file path")
        return value

    @field_validator("captured_at", "delete_after")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("archive timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_positive_retention_window(self) -> Self:
        if self.delete_after <= self.captured_at:
            raise ValueError("delete_after must be later than captured_at")
        return self


class EvidencePointer(StrictModel):
    """Minimal, attributable evidence for a single normalized field."""

    url: AnyHttpUrl
    retrieved_at: datetime
    sha256: Sha256
    evidence_kind: EvidenceKind
    excerpt: str = Field(min_length=1, max_length=500)
    source_policy: SourcePolicy
    raw_archive: RawArchivePointer | None = None

    @field_validator("url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("evidence URL must use HTTPS")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @field_validator("excerpt")
    @classmethod
    def normalize_excerpt(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("excerpt must contain evidence")
        return normalized

    @model_validator(mode="after")
    def enforce_policy(self) -> Self:
        if str(self.url) != str(self.source_policy.source_url):
            raise ValueError("evidence URL must match its source policy URL")
        if not self.source_policy.permits(PolicyAction.FETCH, at=self.retrieved_at):
            raise ValueError("evidence cannot be recorded without approved fetch at retrieval time")

        if self.evidence_kind is EvidenceKind.PARAPHRASE and not self.source_policy.permits(
            PolicyAction.DERIVE, at=self.retrieved_at
        ):
            raise ValueError("paraphrased evidence requires approved derivation")
        if self.evidence_kind is EvidenceKind.QUOTE:
            if not self.source_policy.permits(PolicyAction.QUOTE, at=self.retrieved_at):
                raise ValueError("quoted evidence requires approved quotation")
            assert self.source_policy.max_quote_chars is not None
            if len(self.excerpt) > self.source_policy.max_quote_chars:
                raise ValueError("quoted evidence exceeds the approved character limit")

        if self.raw_archive is not None:
            if not self.source_policy.permits(
                PolicyAction.STORE_RAW, at=self.raw_archive.captured_at
            ):
                raise ValueError("raw archive pointer requires approved raw storage")
            if self.raw_archive.sha256 != self.sha256:
                raise ValueError("archive hash must match the evidence source hash")
            assert self.source_policy.retention_days is not None
            retention_limit = self.raw_archive.captured_at + timedelta(
                days=self.source_policy.retention_days
            )
            if self.raw_archive.delete_after > retention_limit:
                raise ValueError("archive retention exceeds the approved retention_days")
        return self


class FieldEvidence(StrictModel):
    field: FieldPath
    pointers: tuple[EvidencePointer, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_matching_field_policy(self) -> Self:
        mismatched = [
            pointer.source_policy.field
            for pointer in self.pointers
            if pointer.source_policy.field != self.field
        ]
        if mismatched:
            raise ValueError("every evidence policy must name the containing field")
        return self


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class PricingModel(str, Enum):
    FLAT = "flat"
    PER_SEAT = "per_seat"
    PER_USAGE = "per_usage"


class TaxTreatment(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"


class TaxSpec(StrictModel):
    treatment: TaxTreatment
    rate: TaxRate | None = None

    @model_validator(mode="after")
    def validate_rate(self) -> Self:
        if self.treatment is TaxTreatment.EXCLUDED and self.rate is None:
            raise ValueError("excluded tax requires an explicit rate")
        if self.treatment is TaxTreatment.NOT_APPLICABLE and self.rate is not None:
            raise ValueError("not-applicable tax cannot have a rate")
        return self


class SeatPricing(StrictModel):
    """Price for each billable seat.

    Phase 1 intentionally excludes hybrid platform-fee/included-seat products:
    ``included_seats`` is fixed to zero and VendorPlan validates that the unit
    price equals its advertised ``base_price``.
    """

    unit_price: NonNegativeMoney = Field(
        description="Advertised per-seat price for one billing period"
    )
    minimum_seats: int = Field(ge=1, le=1_000_000)
    included_seats: int = Field(default=0, ge=0, le=1_000_000)
    maximum_seats: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_seat_bounds(self) -> Self:
        if self.maximum_seats is not None and self.maximum_seats < self.minimum_seats:
            raise ValueError("maximum_seats cannot be below minimum_seats")
        return self


class UsageAllowance(StrictModel):
    unit_name: str = Field(min_length=1, max_length=80)
    billing_period: BillingPeriod
    included_quantity: NonNegativeQuantity
    overage_unit_price: NonNegativeMoney | None = None


class AddonPrice(StrictModel):
    code: Slug
    name: str = Field(min_length=1, max_length=120)
    required: bool
    unit_price: NonNegativeMoney
    billing_period: BillingPeriod
    pricing_model: PricingModel
    unit_name: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_usage_unit(self) -> Self:
        if self.pricing_model is PricingModel.PER_USAGE and self.unit_name is None:
            raise ValueError("per-usage addon requires unit_name")
        if self.pricing_model is not PricingModel.PER_USAGE and self.unit_name is not None:
            raise ValueError("unit_name is only valid for a per-usage addon")
        return self


class VendorPlan(StrictModel):
    """Immutable price snapshot with evidence for every material input.

    For ``flat`` pricing, ``base_price`` is the fixed charge per billing period.
    For ``per_seat`` pricing, it is the advertised one-seat price and must equal
    ``seat_pricing.unit_price``.  Hybrid platform-fee/included-seat products are
    deferred to a future schema version so Phase 1 TCO cannot double-count them.
    """

    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: UUID = Field(default_factory=uuid4)
    vendor_slug: Slug
    vendor_name: str = Field(min_length=1, max_length=160)
    plan_slug: Slug
    plan_name: str = Field(min_length=1, max_length=160)
    captured_at: datetime
    effective_at: datetime
    currency: CurrencyCode
    minor_unit_digits: int = Field(ge=0, le=6)
    billing_period: BillingPeriod
    commitment_months: int = Field(ge=1, le=120)
    pricing_model: PricingModel
    base_price: NonNegativeMoney = Field(
        description="Flat period charge, or advertised one-seat price for per-seat plans"
    )
    seat_pricing: SeatPricing | None = None
    usage_allowance: UsageAllowance | None = None
    addons: tuple[AddonPrice, ...] = ()
    tax: TaxSpec
    field_evidence: tuple[FieldEvidence, ...] = Field(min_length=1)

    @field_validator("captured_at", "effective_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("plan timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_pricing_and_evidence(self) -> Self:
        if self.pricing_model is PricingModel.PER_USAGE:
            raise ValueError("plan pricing_model supports flat or per_seat; usage is an allowance")
        if self.pricing_model is PricingModel.PER_SEAT and self.seat_pricing is None:
            raise ValueError("per-seat plan requires seat_pricing")
        if self.pricing_model is PricingModel.FLAT and self.seat_pricing is not None:
            raise ValueError("flat plan cannot define seat_pricing")
        if self.pricing_model is PricingModel.PER_SEAT:
            assert self.seat_pricing is not None
            if self.seat_pricing.unit_price != self.base_price:
                raise ValueError("per-seat unit_price must equal advertised base_price")
            if self.seat_pricing.included_seats != 0:
                raise ValueError("Phase 1 per-seat pricing requires included_seats=0")

        addon_codes = [addon.code for addon in self.addons]
        if len(addon_codes) != len(set(addon_codes)):
            raise ValueError("addon codes must be unique")

        evidence_fields = [item.field for item in self.field_evidence]
        if len(evidence_fields) != len(set(evidence_fields)):
            raise ValueError("field evidence paths must be unique")
        missing = self.material_fields() - set(evidence_fields)
        if missing:
            raise ValueError(f"missing evidence for material fields: {', '.join(sorted(missing))}")
        return self

    def material_fields(self) -> set[str]:
        fields = {
            "vendor_name",
            "plan_name",
            "currency",
            "minor_unit_digits",
            "billing_period",
            "commitment_months",
            "pricing_model",
            "base_price",
            "tax.treatment",
        }
        if self.tax.rate is not None:
            fields.add("tax.rate")
        if self.seat_pricing is not None:
            fields.update(
                {
                    "seat_pricing.unit_price",
                    "seat_pricing.minimum_seats",
                    "seat_pricing.included_seats",
                }
            )
            if self.seat_pricing.maximum_seats is not None:
                fields.add("seat_pricing.maximum_seats")
        if self.usage_allowance is not None:
            fields.update(
                {
                    "usage_allowance.unit_name",
                    "usage_allowance.billing_period",
                    "usage_allowance.included_quantity",
                }
            )
            if self.usage_allowance.overage_unit_price is not None:
                fields.add("usage_allowance.overage_unit_price")
        for addon in self.addons:
            prefix = f"addons.{addon.code}"
            fields.update(
                {
                    f"{prefix}.unit_price",
                    f"{prefix}.required",
                    f"{prefix}.billing_period",
                    f"{prefix}.pricing_model",
                }
            )
            if addon.unit_name is not None:
                fields.add(f"{prefix}.unit_name")
        return fields

    def is_publishable(self, *, at: datetime | None = None) -> bool:
        instant = at or datetime.now(timezone.utc)
        return all(
            pointer.source_policy.permits(PolicyAction.PUBLISH, at=instant)
            for item in self.field_evidence
            for pointer in item.pointers
        )


__all__ = [
    "AcquisitionMethod",
    "AddonPrice",
    "BillingPeriod",
    "EvidenceKind",
    "EvidencePointer",
    "FieldEvidence",
    "PolicyAction",
    "PolicyDecision",
    "PricingModel",
    "RawArchivePointer",
    "SeatPricing",
    "SourcePolicy",
    "TaxSpec",
    "TaxTreatment",
    "UsageAllowance",
    "VendorPlan",
]
