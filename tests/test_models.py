from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from saas_preflight.models import (
    AcquisitionMethod,
    AddonPrice,
    BillingPeriod,
    EvidenceKind,
    EvidencePointer,
    FieldEvidence,
    PolicyAction,
    PolicyDecision,
    PricingModel,
    RawArchivePointer,
    SeatPricing,
    SourcePolicy,
    TaxSpec,
    TaxTreatment,
    UsageAllowance,
    VendorPlan,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://example.com/pricing"
SOURCE_HASH = "a" * 64


def make_policy(*, field: str = "base_price", **overrides: object) -> SourcePolicy:
    values: dict[str, object] = {
        "field": field,
        "source_url": SOURCE_URL,
        "acquisition_method": AcquisitionMethod.MANUAL,
        "fetch": PolicyDecision.APPROVED,
        "derive": PolicyDecision.APPROVED,
        "publish": PolicyDecision.APPROVED,
        "retain_history": PolicyDecision.APPROVED,
        "attribution_required": True,
        "attribution_text": "Example pricing page",
        "retention_days": 365,
        "reviewed_at": NOW - timedelta(days=1),
        "review_due_at": NOW + timedelta(days=30),
        "reviewed_by": "human-owner",
        "basis": "Terms and pricing page reviewed manually",
    }
    values.update(overrides)
    return SourcePolicy(**values)


def make_pointer(*, field: str = "base_price", **overrides: object) -> EvidencePointer:
    values: dict[str, object] = {
        "url": SOURCE_URL,
        "retrieved_at": NOW,
        "sha256": SOURCE_HASH,
        "evidence_kind": EvidenceKind.FACT,
        "excerpt": "Plan price is 1,000 JPY per month.",
        "source_policy": make_policy(field=field),
    }
    values.update(overrides)
    return EvidencePointer(**values)


def make_plan(**overrides: object) -> VendorPlan:
    material_fields = (
        "vendor_name",
        "plan_name",
        "currency",
        "minor_unit_digits",
        "billing_period",
        "commitment_months",
        "pricing_model",
        "base_price",
        "tax.treatment",
        "tax.rate",
    )
    values: dict[str, object] = {
        "vendor_slug": "example",
        "vendor_name": "Example",
        "plan_slug": "basic",
        "plan_name": "Basic",
        "captured_at": NOW,
        "effective_at": NOW,
        "currency": "JPY",
        "minor_unit_digits": 0,
        "billing_period": BillingPeriod.MONTHLY,
        "commitment_months": 1,
        "pricing_model": PricingModel.FLAT,
        "base_price": Decimal("1000"),
        "tax": TaxSpec(treatment=TaxTreatment.EXCLUDED, rate=Decimal("0.10")),
        "field_evidence": tuple(
            FieldEvidence(field=field, pointers=(make_pointer(field=field),))
            for field in material_fields
        ),
    }
    values.update(overrides)
    return VendorPlan(**values)


def test_unreviewed_policy_is_fail_closed() -> None:
    policy = SourcePolicy(
        field="base_price",
        source_url=SOURCE_URL,
        acquisition_method=AcquisitionMethod.MANUAL,
        reviewed_at=NOW - timedelta(days=1),
        review_due_at=NOW + timedelta(days=1),
        reviewed_by="human-owner",
        basis="Not reviewed yet",
    )

    assert policy.decision_for(PolicyAction.FETCH) is PolicyDecision.UNREVIEWED
    assert policy.permits(PolicyAction.FETCH, at=NOW) is False
    assert policy.permits(PolicyAction.PUBLISH, at=NOW) is False


def test_expired_approval_is_not_permission() -> None:
    policy = make_policy(review_due_at=NOW + timedelta(minutes=1))

    assert policy.permits(PolicyAction.PUBLISH, at=NOW) is True
    assert policy.permits(PolicyAction.PUBLISH, at=NOW + timedelta(minutes=1)) is False


def test_downstream_approval_without_fetch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="downstream approval requires"):
        make_policy(fetch=PolicyDecision.UNREVIEWED)


def test_history_or_raw_approval_requires_explicit_retention() -> None:
    with pytest.raises(ValidationError, match="requires retention_days"):
        make_policy(retention_days=None)
    with pytest.raises(ValidationError, match="only valid"):
        make_policy(
            retain_history=PolicyDecision.UNREVIEWED,
            retention_days=30,
        )


def test_policy_urls_and_timestamps_are_strict() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        make_policy(source_url="http://example.com/pricing")
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_policy(reviewed_at=NOW.replace(tzinfo=None))


def test_evidence_requires_matching_https_source_and_fetch_permission() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        make_pointer(url="http://example.com/pricing")
    with pytest.raises(ValidationError, match="must match"):
        make_pointer(url="https://other.example/pricing")


def test_field_evidence_requires_matching_field_level_policy() -> None:
    with pytest.raises(ValidationError, match="containing field"):
        FieldEvidence(field="plan_name", pointers=(make_pointer(field="base_price"),))


def test_quote_must_be_approved_and_within_limit() -> None:
    quote_policy = make_policy(
        quote=PolicyDecision.APPROVED,
        max_quote_chars=10,
    )
    with pytest.raises(ValidationError, match="character limit"):
        make_pointer(
            evidence_kind=EvidenceKind.QUOTE,
            excerpt="this quote is too long",
            source_policy=quote_policy,
        )


def test_raw_archive_is_metadata_only_and_requires_raw_permission() -> None:
    archive = RawArchivePointer(
        relative_path="example/2026-07-21/source.html.enc",
        sha256=SOURCE_HASH,
        captured_at=NOW,
        delete_after=NOW + timedelta(days=7),
    )
    with pytest.raises(ValidationError, match="approved raw storage"):
        make_pointer(raw_archive=archive)

    pointer = make_pointer(
        source_policy=make_policy(
            store_raw=PolicyDecision.APPROVED,
            retention_days=7,
        ),
        raw_archive=archive,
    )
    dumped = pointer.model_dump()
    assert "raw_archive" in dumped
    assert "html" not in dumped["raw_archive"]
    assert "content" not in dumped["raw_archive"]


def test_raw_archive_rejects_unsafe_path_and_hash_mismatch() -> None:
    with pytest.raises(ValidationError, match="safe relative"):
        RawArchivePointer(
            relative_path="../source.html",
            sha256=SOURCE_HASH,
            captured_at=NOW,
            delete_after=NOW + timedelta(days=1),
        )

    with pytest.raises(ValidationError, match="safe relative"):
        RawArchivePointer(
            relative_path=r"..\source.html",
            sha256=SOURCE_HASH,
            captured_at=NOW,
            delete_after=NOW + timedelta(days=1),
        )

    archive = RawArchivePointer(
        relative_path="example/source.html.enc",
        sha256="b" * 64,
        captured_at=NOW,
        delete_after=NOW + timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="hash must match"):
        make_pointer(
            source_policy=make_policy(
                store_raw=PolicyDecision.APPROVED,
                retention_days=7,
            ),
            raw_archive=archive,
        )


def test_vendor_plan_requires_material_field_evidence() -> None:
    with pytest.raises(ValidationError, match="missing evidence.*base_price"):
        make_plan(
            field_evidence=tuple(
                item for item in make_plan().field_evidence if item.field != "base_price"
            )
        )


def test_vendor_plan_rejects_ambiguous_pricing_shape() -> None:
    with pytest.raises(ValidationError, match="requires seat_pricing"):
        make_plan(pricing_model=PricingModel.PER_SEAT)


def test_phase_one_per_seat_semantics_are_unambiguous() -> None:
    flat = make_plan()
    seat_fields = (
        "seat_pricing.unit_price",
        "seat_pricing.minimum_seats",
        "seat_pricing.included_seats",
    )
    evidence = flat.field_evidence + tuple(
        FieldEvidence(field=field, pointers=(make_pointer(field=field),))
        for field in seat_fields
    )

    plan = make_plan(
        pricing_model=PricingModel.PER_SEAT,
        seat_pricing=SeatPricing(
            unit_price=Decimal("1000"),
            minimum_seats=1,
            included_seats=0,
        ),
        field_evidence=evidence,
    )
    assert plan.base_price == plan.seat_pricing.unit_price

    with pytest.raises(ValidationError, match="must equal advertised base_price"):
        make_plan(
            pricing_model=PricingModel.PER_SEAT,
            seat_pricing=SeatPricing(
                unit_price=Decimal("900"),
                minimum_seats=1,
                included_seats=0,
            ),
            field_evidence=evidence,
        )


def test_usage_reset_period_and_addon_selection_are_evidence_backed() -> None:
    base = make_plan()
    usage = UsageAllowance(
        unit_name="api-call",
        billing_period=BillingPeriod.MONTHLY,
        included_quantity=Decimal("1000"),
        overage_unit_price=Decimal("0.01"),
    )
    addon = AddonPrice(
        code="audit-log",
        name="Audit Log",
        required=False,
        unit_price=Decimal("500"),
        billing_period=BillingPeriod.MONTHLY,
        pricing_model=PricingModel.FLAT,
    )
    extra_fields = (
        "usage_allowance.unit_name",
        "usage_allowance.billing_period",
        "usage_allowance.included_quantity",
        "usage_allowance.overage_unit_price",
        "addons.audit-log.unit_price",
        "addons.audit-log.required",
        "addons.audit-log.billing_period",
        "addons.audit-log.pricing_model",
    )
    evidence = base.field_evidence + tuple(
        FieldEvidence(field=field, pointers=(make_pointer(field=field),))
        for field in extra_fields
    )

    plan = make_plan(usage_allowance=usage, addons=(addon,), field_evidence=evidence)
    assert plan.material_fields().issubset({item.field for item in plan.field_evidence})


def test_vendor_plan_is_publishable_only_during_review_window() -> None:
    plan = make_plan()

    assert plan.is_publishable(at=NOW) is True
    assert plan.is_publishable(at=NOW + timedelta(days=31)) is False


def test_models_are_strict_and_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        make_plan(base_price=1000)
    with pytest.raises(ValidationError, match="Extra inputs"):
        SourcePolicy(
            field="base_price",
            source_url=SOURCE_URL,
            acquisition_method=AcquisitionMethod.MANUAL,
            reviewed_at=NOW,
            review_due_at=NOW + timedelta(days=1),
            reviewed_by="human-owner",
            basis="review",
            can_publish=True,
        )
