from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from saas_preflight.goldset import (
    CandidateBatch,
    CandidateParseFailure,
    CandidatePlan,
    GoldFieldLabel,
    GoldPlan,
    GoldTcoExpectation,
    HumanGoldSet,
    ParseFailureCode,
    QuarantineReason,
    evaluate_goldset,
    hash_material_field_value,
    hash_rights_manifest,
    hash_tco_result,
    hash_vendor_plan,
)
from saas_preflight.models import FieldEvidence, PolicyDecision, VendorPlan
from saas_preflight.tco import calculate_vendor_plan_tco, constant_usage_scenario

from test_models import NOW, SOURCE_HASH, make_plan, make_policy


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate(plan: VendorPlan, *, suffix: str | None = None) -> CandidatePlan:
    key = suffix or f"{plan.vendor_slug}-{plan.plan_slug}"
    return CandidatePlan(
        input_id_sha256=digest(f"input:{key}"),
        plan_sha256=hash_vendor_plan(plan),
        plan=plan,
    )


def expectation(plan: VendorPlan, *, suffix: str = "default") -> GoldTcoExpectation:
    scenario = constant_usage_scenario(
        months=12,
        seats=1,
        monthly_usage=Decimal("0"),
        usage_unit=None,
    )
    result = calculate_vendor_plan_tco(plan, scenario)
    return GoldTcoExpectation(
        scenario_id_sha256=digest(f"scenario:{plan.vendor_slug}:{plan.plan_slug}:{suffix}"),
        human_label_receipt_sha256=digest(
            f"tco-receipt:{plan.vendor_slug}:{plan.plan_slug}:{suffix}"
        ),
        labeled_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=10),
        seats=1,
        monthly_usage=Decimal("0"),
        usage_unit=None,
        selected_addon_codes=(),
        expected_tco_sha256=hash_tco_result(result),
        expected_total_minor=result.total_minor,
        expected_currency=result.currency,
    )


def label(plan: VendorPlan, field_path: str) -> GoldFieldLabel:
    key = f"{plan.vendor_slug}:{plan.plan_slug}:{field_path}"
    evidence = next(item for item in plan.field_evidence if item.field == field_path)
    return GoldFieldLabel(
        label_id_sha256=digest(f"label:{key}"),
        field_path=field_path,
        expected_value_sha256=hash_material_field_value(plan, field_path),
        evidence_source_sha256s=tuple(
            sorted({pointer.sha256 for pointer in evidence.pointers})
        ),
        human_label_receipt_sha256=digest(f"receipt:{key}"),
        labeled_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=10),
    )


def gold_plan(plan: VendorPlan) -> GoldPlan:
    return GoldPlan(
        vendor_slug=plan.vendor_slug,
        plan_slug=plan.plan_slug,
        labels=tuple(label(plan, field) for field in sorted(plan.material_fields())),
        tco_expectations=(expectation(plan),),
    )


def synthetic_plans() -> tuple[VendorPlan, ...]:
    return tuple(
        make_plan(
            snapshot_id=uuid4(),
            vendor_slug=f"vendor-{vendor}",
            vendor_name=f"Vendor {vendor.upper()}",
            plan_slug=f"plan-{index}",
            plan_name=f"Plan {index}",
        )
        for vendor in ("a", "b", "c")
        for index in range(1, 7)
    )


def full_fixture() -> tuple[HumanGoldSet, CandidateBatch, tuple[VendorPlan, ...]]:
    plans = synthetic_plans()
    goldset = HumanGoldSet(
        goldset_id_sha256=digest("goldset-full"),
        rights_bundle_sha256=hash_rights_manifest(plans),
        created_at=NOW,
        expires_at=NOW + timedelta(days=10),
        plans=tuple(gold_plan(plan) for plan in plans),
    )
    batch = CandidateBatch(
        source_receipt_sha256=digest("candidate-source"),
        parser_sha256=digest("parser"),
        parser_version="1.0.0",
        captured_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=5),
        plans=tuple(candidate(plan) for plan in plans),
        failures=(),
    )
    return goldset, batch, plans


def reasons(report: object) -> set[QuarantineReason]:
    return {item.reason for item in report.quarantines}  # type: ignore[attr-defined]


def test_full_three_by_six_and_sixty_labels_per_vendor_is_ready() -> None:
    goldset, batch, _ = full_fixture()

    report = evaluate_goldset(goldset, batch, at=NOW)

    assert report.full_goldset_coverage is True
    assert report.gold_vendor_count == 3
    assert report.gold_plan_count == 18
    assert report.gold_label_count == 180
    assert report.ready_for_release is True
    assert report.quarantines == ()


def test_partial_goldset_is_valid_contract_but_never_release_ready() -> None:
    goldset, batch, _ = full_fixture()
    partial = HumanGoldSet(
        goldset_id_sha256=digest("partial"),
        rights_bundle_sha256=goldset.rights_bundle_sha256,
        created_at=goldset.created_at,
        expires_at=goldset.expires_at,
        plans=(goldset.plans[0],),
    )
    partial_batch = batch.model_copy(update={"plans": (batch.plans[0],)})

    report = evaluate_goldset(partial, partial_batch, at=NOW)
    assert report.full_goldset_coverage is False
    assert report.ready_for_release is False
    assert QuarantineReason.PARTIAL_GOLDSET in reasons(report)


def test_more_than_150_labels_for_one_vendor_is_not_full_coverage() -> None:
    goldset, batch, _ = full_fixture()
    first = goldset.plans[0]
    extras = tuple(
        GoldFieldLabel(
            label_id_sha256=digest(f"over-label-{index}"),
            field_path=f"synthetic.extra{index:03d}",
            expected_value_sha256=digest(f"over-value-{index}"),
            evidence_source_sha256s=(SOURCE_HASH,),
            human_label_receipt_sha256=digest(f"over-receipt-{index}"),
            labeled_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(days=1),
        )
        for index in range(91)
    )
    oversized = GoldPlan(
        vendor_slug=first.vendor_slug,
        plan_slug=first.plan_slug,
        labels=first.labels + extras,
        tco_expectations=first.tco_expectations,
    )
    changed = HumanGoldSet(
        goldset_id_sha256=goldset.goldset_id_sha256,
        rights_bundle_sha256=goldset.rights_bundle_sha256,
        created_at=goldset.created_at,
        expires_at=goldset.expires_at,
        plans=(oversized,) + goldset.plans[1:],
    )

    report = evaluate_goldset(changed, batch, at=NOW)
    assert report.full_goldset_coverage is False
    assert report.ready_for_release is False
    assert QuarantineReason.PARTIAL_GOLDSET in reasons(report)


def test_more_than_three_vendors_and_six_plans_can_be_ready() -> None:
    _, _, base_plans = full_fixture()
    extra_plans = tuple(
        make_plan(
            snapshot_id=uuid4(),
            vendor_slug="vendor-d",
            vendor_name="Vendor D",
            plan_slug=f"plan-{index}",
            plan_name=f"Plan {index}",
        )
        for index in range(1, 7)
    )
    plans = base_plans + extra_plans
    goldset = HumanGoldSet(
        goldset_id_sha256=digest("goldset-overcoverage"),
        rights_bundle_sha256=hash_rights_manifest(plans),
        created_at=NOW,
        expires_at=NOW + timedelta(days=10),
        plans=tuple(gold_plan(plan) for plan in plans),
    )
    batch = CandidateBatch(
        source_receipt_sha256=digest("overcoverage-source"),
        parser_sha256=digest("overcoverage-parser"),
        parser_version="1.0.0",
        captured_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=5),
        plans=tuple(candidate(plan) for plan in plans),
        failures=(),
    )

    report = evaluate_goldset(goldset, batch, at=NOW)
    assert report.gold_vendor_count == 4
    assert report.gold_plan_count == 24
    assert report.full_goldset_coverage is True
    assert report.ready_for_release is True


def test_rights_manifest_ignores_snapshot_observation_but_binds_policy() -> None:
    plan = make_plan()
    first_evidence = plan.field_evidence[0]
    changed_pointer = first_evidence.pointers[0].model_copy(
        update={
            "retrieved_at": NOW + timedelta(minutes=1),
            "sha256": digest("new-source-body"),
        }
    )
    observed = plan.model_copy(
        update={
            "snapshot_id": uuid4(),
            "captured_at": NOW + timedelta(minutes=1),
            "effective_at": NOW + timedelta(minutes=1),
            "field_evidence": (
                first_evidence.model_copy(update={"pointers": (changed_pointer,)}),
            )
            + plan.field_evidence[1:],
        }
    )
    assert hash_rights_manifest((plan,)) == hash_rights_manifest((observed,))

    duplicate_pointer_plan = plan.model_copy(
        update={
            "field_evidence": (
                first_evidence.model_copy(
                    update={
                        "pointers": (
                            first_evidence.pointers[0],
                            first_evidence.pointers[0],
                        )
                    }
                ),
            )
            + plan.field_evidence[1:]
        }
    )
    assert hash_rights_manifest((plan,)) == hash_rights_manifest(
        (duplicate_pointer_plan,)
    )

    policy_values = first_evidence.pointers[0].source_policy.model_dump()
    policy_values["source_url"] = "https://policy-change.example/pricing"
    changed_policy = type(first_evidence.pointers[0].source_policy)(**policy_values)
    policy_changed_pointer = first_evidence.pointers[0].model_copy(
        update={"source_policy": changed_policy}
    )
    policy_changed = plan.model_copy(
        update={
            "field_evidence": (
                first_evidence.model_copy(
                    update={"pointers": (policy_changed_pointer,)}
                ),
            )
            + plan.field_evidence[1:]
        }
    )
    assert hash_rights_manifest((plan,)) != hash_rights_manifest((policy_changed,))


def test_duplicate_labels_plans_and_candidate_inputs_are_rejected() -> None:
    goldset, batch, _ = full_fixture()
    first = goldset.plans[1]
    with pytest.raises(ValidationError, match="label IDs must be distinct"):
        GoldPlan(
            vendor_slug=first.vendor_slug,
            plan_slug=first.plan_slug,
            labels=first.labels + (first.labels[0],),
            tco_expectations=first.tco_expectations,
        )
    with pytest.raises(ValidationError, match="gold plan keys must be distinct"):
        HumanGoldSet(
            goldset_id_sha256=digest("duplicate-plan"),
            rights_bundle_sha256=goldset.rights_bundle_sha256,
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            plans=(first, first),
        )
    failure = CandidateParseFailure(
        input_id_sha256=batch.plans[0].input_id_sha256,
        expected_vendor_slug="vendor-a",
        expected_plan_slug="plan-1",
        code=ParseFailureCode.PARSE_ERROR,
        error_sha256=digest("error"),
    )
    with pytest.raises(ValidationError, match="candidate input IDs must be distinct"):
        CandidateBatch(
            source_receipt_sha256=batch.source_receipt_sha256,
            parser_sha256=batch.parser_sha256,
            parser_version=batch.parser_version,
            captured_at=batch.captured_at,
            expires_at=batch.expires_at,
            plans=(batch.plans[0],),
            failures=(failure,),
        )


def test_candidate_plan_hash_mismatch_is_rejected() -> None:
    plan = make_plan()
    with pytest.raises(ValidationError, match="does not match"):
        CandidatePlan(
            input_id_sha256=digest("input"),
            plan_sha256=digest("wrong"),
            plan=plan,
        )


def test_future_and_expired_gold_candidate_plan_and_label_are_quarantined() -> None:
    goldset, batch, _ = full_fixture()
    first_plan = goldset.plans[0]
    future_label = first_plan.labels[0].model_copy(
        update={
            "labeled_at": NOW + timedelta(minutes=1),
            "expires_at": NOW + timedelta(days=1),
        }
    )
    changed_gold_plan = first_plan.model_copy(
        update={"labels": (future_label,) + first_plan.labels[1:]}
    )
    changed_gold = goldset.model_copy(
        update={
            "created_at": NOW + timedelta(minutes=2),
            "plans": (changed_gold_plan,) + goldset.plans[1:],
        }
    )
    future_vendor_plan = batch.plans[0].plan.model_copy(
        update={"effective_at": NOW + timedelta(minutes=1)}
    )
    changed_candidate = candidate(future_vendor_plan, suffix="future")
    changed_batch = batch.model_copy(
        update={
            "captured_at": NOW + timedelta(minutes=1),
            "plans": (changed_candidate,) + batch.plans[1:],
        }
    )

    report = evaluate_goldset(changed_gold, changed_batch, at=NOW)
    assert QuarantineReason.GOLDSET_NOT_CURRENT in reasons(report)
    assert QuarantineReason.CANDIDATE_NOT_CURRENT in reasons(report)
    assert QuarantineReason.LABEL_NOT_CURRENT in reasons(report)


def test_expiry_boundary_and_expired_rights_fail_closed() -> None:
    plan = make_plan()
    item = gold_plan(plan)
    long_labels = tuple(
        label_item.model_copy(update={"expires_at": NOW + timedelta(days=40)})
        for label_item in item.labels
    )
    long_item = item.model_copy(update={"labels": long_labels})
    goldset = HumanGoldSet(
        goldset_id_sha256=digest("rights-expiry"),
        rights_bundle_sha256=digest("rights-bundle-expiry"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=40),
        plans=(long_item,),
    )
    batch = CandidateBatch(
        source_receipt_sha256=digest("expiry-source"),
        parser_sha256=digest("expiry-parser"),
        parser_version="1.0.0",
        captured_at=NOW,
        expires_at=NOW + timedelta(days=40),
        plans=(candidate(plan),),
        failures=(),
    )

    rights_expired = evaluate_goldset(goldset, batch, at=NOW + timedelta(days=31))
    assert QuarantineReason.RIGHTS_INVALID in reasons(rights_expired)

    boundary_gold = goldset.model_copy(update={"expires_at": NOW})
    boundary_batch = batch.model_copy(update={"expires_at": NOW})
    boundary_label = long_item.labels[0].model_copy(update={"expires_at": NOW})
    boundary_item = long_item.model_copy(
        update={"labels": (boundary_label,) + long_item.labels[1:]}
    )
    boundary_gold = boundary_gold.model_copy(update={"plans": (boundary_item,)})
    boundary = evaluate_goldset(boundary_gold, boundary_batch, at=NOW)
    assert QuarantineReason.GOLDSET_NOT_CURRENT in reasons(boundary)
    assert QuarantineReason.CANDIDATE_NOT_CURRENT in reasons(boundary)
    assert QuarantineReason.LABEL_NOT_CURRENT in reasons(boundary)


def test_label_after_goldset_creation_is_rejected_at_contract_boundary() -> None:
    plan = make_plan()
    item = gold_plan(plan)
    later = item.labels[0].model_copy(update={"labeled_at": NOW + timedelta(seconds=1)})
    changed = item.model_copy(update={"labels": (later,) + item.labels[1:]})
    with pytest.raises(ValidationError, match="labels cannot be created after"):
        HumanGoldSet(
            goldset_id_sha256=digest("future-label"),
            rights_bundle_sha256=digest("rights"),
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            plans=(changed,),
        )


def test_tco_label_window_and_goldset_creation_boundary_are_strict() -> None:
    plan = make_plan()
    valid = expectation(plan)
    with pytest.raises(ValidationError, match="later than labeled_at"):
        GoldTcoExpectation(
            **valid.model_dump(exclude={"expires_at"}),
            expires_at=valid.labeled_at,
        )

    future = valid.model_copy(update={"labeled_at": NOW + timedelta(seconds=1)})
    item = gold_plan(plan).model_copy(update={"tco_expectations": (future,)})
    with pytest.raises(ValidationError, match="TCO labels cannot be created after"):
        HumanGoldSet(
            goldset_id_sha256=digest("future-tco-label"),
            rights_bundle_sha256=digest("rights"),
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            plans=(item,),
        )


def test_future_and_expired_tco_labels_are_quarantined() -> None:
    goldset, batch, _ = full_fixture()
    first = goldset.plans[0]
    not_current = first.tco_expectations[0].model_copy(
        update={
            "labeled_at": NOW + timedelta(minutes=1),
            "expires_at": NOW + timedelta(minutes=2),
        }
    )
    changed_plan = first.model_copy(update={"tco_expectations": (not_current,)})
    changed_gold = goldset.model_copy(
        update={"plans": (changed_plan,) + goldset.plans[1:]}
    )
    report = evaluate_goldset(changed_gold, batch, at=NOW)
    assert QuarantineReason.LABEL_NOT_CURRENT in reasons(report)

    expired = first.tco_expectations[0].model_copy(update={"expires_at": NOW})
    expired_plan = first.model_copy(update={"tco_expectations": (expired,)})
    expired_gold = goldset.model_copy(
        update={"plans": (expired_plan,) + goldset.plans[1:]}
    )
    expired_report = evaluate_goldset(expired_gold, batch, at=NOW)
    assert QuarantineReason.LABEL_NOT_CURRENT in reasons(expired_report)


def test_future_evidence_retrieval_is_quarantined() -> None:
    goldset, batch, _ = full_fixture()
    plan = batch.plans[0].plan
    evidence = list(plan.field_evidence)
    first = evidence[0]
    future_pointer = first.pointers[0].model_copy(
        update={"retrieved_at": NOW + timedelta(minutes=1)}
    )
    evidence[0] = first.model_copy(update={"pointers": (future_pointer,)})
    future_plan = plan.model_copy(update={"field_evidence": tuple(evidence)})
    changed_batch = batch.model_copy(
        update={"plans": (candidate(future_plan, suffix="future-evidence"),) + batch.plans[1:]}
    )

    report = evaluate_goldset(goldset, changed_batch, at=NOW)
    assert QuarantineReason.CANDIDATE_NOT_CURRENT in reasons(report)


def test_expired_retention_cohort_is_rights_invalid() -> None:
    plan = make_plan(captured_at=NOW - timedelta(days=2))
    evidence = list(plan.field_evidence)
    first = evidence[0]
    short_policy = make_policy(
        field=first.field,
        retention_days=1,
        review_due_at=NOW + timedelta(days=20),
    )
    evidence[0] = first.model_copy(
        update={
            "pointers": (
                first.pointers[0].model_copy(update={"source_policy": short_policy}),
            )
        }
    )
    expired_plan = plan.model_copy(update={"field_evidence": tuple(evidence)})
    item = gold_plan(expired_plan)
    goldset = HumanGoldSet(
        goldset_id_sha256=digest("expired-retention"),
        rights_bundle_sha256=digest("expired-rights-receipt"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=5),
        plans=(item,),
    )
    batch = CandidateBatch(
        source_receipt_sha256=digest("expired-source"),
        parser_sha256=digest("expired-parser"),
        parser_version="1.0.0",
        captured_at=NOW,
        expires_at=NOW + timedelta(days=5),
        plans=(candidate(expired_plan),),
        failures=(),
    )

    report = evaluate_goldset(goldset, batch, at=NOW)
    assert QuarantineReason.RIGHTS_INVALID in reasons(report)


def test_rights_bundle_must_be_derived_from_candidate_snapshot() -> None:
    goldset, batch, _ = full_fixture()
    wrong_receipt = goldset.model_copy(
        update={"rights_bundle_sha256": digest("unrelated-rights-bundle")}
    )

    report = evaluate_goldset(wrong_receipt, batch, at=NOW)
    assert QuarantineReason.RIGHTS_INVALID in reasons(report)
    assert report.ready_for_release is False


def test_label_source_hash_order_is_canonical() -> None:
    plan = make_plan()
    field_path = sorted(plan.material_fields())[0]
    item = GoldFieldLabel(
        label_id_sha256=digest("source-order-label"),
        field_path=field_path,
        expected_value_sha256=hash_material_field_value(plan, field_path),
        evidence_source_sha256s=(digest("source-z"), digest("source-a")),
        human_label_receipt_sha256=digest("source-order-receipt"),
        labeled_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=1),
    )
    assert item.evidence_source_sha256s == tuple(sorted(item.evidence_source_sha256s))


def test_field_source_and_tco_mismatches_are_separate_quarantines() -> None:
    goldset, batch, _ = full_fixture()
    plan = goldset.plans[0]
    changed_label = plan.labels[0].model_copy(
        update={
            "expected_value_sha256": digest("wrong-value"),
            "evidence_source_sha256s": (digest("wrong-source"),),
        }
    )
    changed_expectation = plan.tco_expectations[0].model_copy(
        update={"expected_total_minor": plan.tco_expectations[0].expected_total_minor + 1}
    )
    changed_plan = plan.model_copy(
        update={
            "labels": (changed_label,) + plan.labels[1:],
            "tco_expectations": (changed_expectation,),
        }
    )
    changed_gold = goldset.model_copy(
        update={"plans": (changed_plan,) + goldset.plans[1:]}
    )

    report = evaluate_goldset(changed_gold, batch, at=NOW)
    assert {
        QuarantineReason.FIELD_MISMATCH,
        QuarantineReason.SOURCE_MISMATCH,
        QuarantineReason.TCO_MISMATCH,
    }.issubset(reasons(report))


def test_missing_and_extra_plans_and_fields_are_quarantined() -> None:
    goldset, batch, _ = full_fixture()
    first = goldset.plans[1]
    extra_label = GoldFieldLabel(
        label_id_sha256=digest("extra-label"),
        field_path="legacy.value",
        expected_value_sha256=digest("legacy-value"),
        evidence_source_sha256s=(SOURCE_HASH,),
        human_label_receipt_sha256=digest("legacy-receipt"),
        labeled_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=1),
    )
    labels = first.labels[1:] + (extra_label,)
    changed_plan = first.model_copy(update={"labels": labels})
    changed_gold = goldset.model_copy(
        update={"plans": (goldset.plans[0], changed_plan) + goldset.plans[2:]}
    )
    extra_vendor = make_plan(
        snapshot_id=uuid4(),
        vendor_slug="vendor-x",
        vendor_name="Vendor X",
        plan_slug="plan-x",
        plan_name="Plan X",
    )
    changed_batch = batch.model_copy(
        update={"plans": batch.plans[1:] + (candidate(extra_vendor),)}
    )

    report = evaluate_goldset(changed_gold, changed_batch, at=NOW)
    assert {
        QuarantineReason.MISSING_PLAN,
        QuarantineReason.EXTRA_PLAN,
        QuarantineReason.MISSING_FIELD,
        QuarantineReason.EXTRA_FIELD,
    }.issubset(reasons(report))


def test_expired_or_missing_required_rights_are_quarantined() -> None:
    goldset, batch, _ = full_fixture()
    plan = batch.plans[0].plan
    changed_evidence: list[FieldEvidence] = []
    for item in plan.field_evidence:
        if item.field == "base_price":
            pointer = item.pointers[0]
            policy = make_policy(
                field=item.field,
                publish=PolicyDecision.PROHIBITED,
            )
            item = item.model_copy(
                update={"pointers": (pointer.model_copy(update={"source_policy": policy}),)}
            )
        changed_evidence.append(item)
    denied_plan = plan.model_copy(update={"field_evidence": tuple(changed_evidence)})
    changed_batch = batch.model_copy(
        update={"plans": (candidate(denied_plan, suffix="denied"),) + batch.plans[1:]}
    )

    report = evaluate_goldset(goldset, changed_batch, at=NOW)
    assert QuarantineReason.RIGHTS_INVALID in reasons(report)


def test_unsupported_constant_usage_scenario_is_quarantined_not_guessed() -> None:
    goldset, batch, _ = full_fixture()
    first = goldset.plans[0]
    unsupported = first.tco_expectations[0].model_copy(
        update={"selected_addon_codes": ("unknown-addon",)}
    )
    changed_plan = first.model_copy(update={"tco_expectations": (unsupported,)})
    changed_gold = goldset.model_copy(
        update={"plans": (changed_plan,) + goldset.plans[1:]}
    )

    report = evaluate_goldset(changed_gold, batch, at=NOW)
    assert QuarantineReason.TCO_ERROR in reasons(report)


def test_failure_rate_exact_twenty_percent_does_not_trigger_stop_but_above_does() -> None:
    goldset, batch, _ = full_fixture()
    failure = CandidateParseFailure(
        input_id_sha256=digest("failure-1"),
        expected_vendor_slug="vendor-c",
        expected_plan_slug="plan-6",
        code=ParseFailureCode.AMBIGUOUS,
        error_sha256=digest("ambiguous"),
    )
    exact = batch.model_copy(update={"plans": batch.plans[:4], "failures": (failure,)})
    above = batch.model_copy(update={"plans": batch.plans[:3], "failures": (failure,)})

    exact_report = evaluate_goldset(goldset, exact, at=NOW)
    above_report = evaluate_goldset(goldset, above, at=NOW)
    assert exact_report.parse_failure_rate == Decimal("0.2")
    assert exact_report.parser_failure_stop is False
    assert exact_report.ready_for_release is False
    assert above_report.parse_failure_rate == Decimal("0.25")
    assert above_report.parser_failure_stop is True
    assert QuarantineReason.PARSER_FAILURE_RATE in reasons(above_report)


def test_selected_addons_and_report_hash_are_permutation_invariant() -> None:
    sorted_expectation = GoldTcoExpectation(
        scenario_id_sha256=digest("addons"),
        human_label_receipt_sha256=digest("addons-receipt"),
        labeled_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=1),
        seats=1,
        monthly_usage=Decimal("0"),
        selected_addon_codes=("zeta", "alpha"),
        expected_tco_sha256=digest("tco"),
        expected_total_minor=0,
        expected_currency="JPY",
    )
    assert sorted_expectation.selected_addon_codes == ("alpha", "zeta")

    goldset, batch, _ = full_fixture()
    permuted_gold = goldset.model_copy(
        update={
            "plans": tuple(
                plan.model_copy(update={"labels": tuple(reversed(plan.labels))})
                for plan in reversed(goldset.plans)
            )
        }
    )
    permuted_batch = batch.model_copy(update={"plans": tuple(reversed(batch.plans))})

    first = evaluate_goldset(goldset, batch, at=NOW)
    second = evaluate_goldset(permuted_gold, permuted_batch, at=NOW)
    assert first.goldset_content_sha256 == second.goldset_content_sha256
    assert first.candidate_batch_sha256 == second.candidate_batch_sha256
    assert first.report_sha256 == second.report_sha256


def test_report_is_hash_only_and_contains_no_candidate_evidence_text_or_url() -> None:
    goldset, batch, _ = full_fixture()
    report = evaluate_goldset(goldset, batch, at=NOW)

    serialized = report.model_dump_json()
    assert "https://" not in serialized
    assert "Plan price is" not in serialized
    assert "credential" not in serialized.lower()
