from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import test_measurement_integrity as p12
from saas_preflight.measurement_integrity import (
    CohortIntegrityBatch,
    CurrentTransaction,
    PayoutAdjustmentKind,
    TransactionStatus,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
)
from saas_preflight.settlement_amendment import (
    SettlementAmendmentAuthorityPins,
    SettlementAmendmentError,
    SettlementAmendmentPolicy,
    SettlementAmendmentTrustStore,
    SettlementCompletenessCoverage,
    SettlementCompletenessDecision,
    SettlementPayoutAdjustment,
    SettlementStatusChange,
    SignedSettlementAmendment,
    build_original_settlement_binding,
    evaluate_settlement_amendments,
    hash_original_settlement_binding,
    hash_settlement_artifact,
    hash_settlement_policy,
    hash_settlement_trust_store,
    sign_settlement_amendment,
    sign_settlement_completeness_attestation,
    verify_original_settlement_binding,
    verify_settlement_amendment,
)


def _case(*, pending_new: bool = False) -> dict:
    bundle = p12._bundle()
    if pending_new:
        cohort = bundle["cohort"]
        target_id = p12._sha("transaction:confirmed-new")
        target = next(
            item
            for item in cohort.transactions
            if item.transaction_id_sha256 == target_id
        )
        pending = CurrentTransaction.model_validate(
            {
                **target.model_dump(),
                "current_status": TransactionStatus.PENDING,
                "status_events": (
                    p12._event("pending-new", TransactionStatus.PENDING, 0),
                ),
            }
        )
        changed = CohortIntegrityBatch.model_validate(
            {
                **cohort.model_dump(),
                "transactions": tuple(
                    pending if item.transaction_id_sha256 == target_id else item
                    for item in cohort.transactions
                ),
            }
        )
        p12._replace_cohort(bundle, changed, p12._coverage(changed, "cohort"))
    report = p12._evaluate(bundle)
    binding = build_original_settlement_binding(
        report,
        bundle["policy"],
        bundle["trust"],
        bundle["pins"],
        bundle["plan"],
        bundle["index"],
        bundle["cohort"],
        bundle["cohort_attestation"],
        original_verified_at=p12.AT,
    )
    trust = SettlementAmendmentTrustStore(
        amendment_producer=bundle["trust"].cohort_producer,
        completeness_verifier=bundle["trust"].measurement_verifier,
    )
    policy = SettlementAmendmentPolicy(
        trust_store_sha256=hash_settlement_trust_store(trust),
        p12_policy_sha256=hash_measurement_policy(bundle["policy"]),
        p12_trust_store_sha256=hash_measurement_trust_store(bundle["trust"]),
        completeness_rule_sha256=p12._sha("settlement-completeness"),
        maximum_amendment_ttl_seconds=24 * 60 * 60,
        maximum_completeness_ttl_seconds=24 * 60 * 60,
    )
    pins = SettlementAmendmentAuthorityPins(
        expected_policy_sha256=hash_settlement_policy(policy),
        expected_trust_store_sha256=hash_settlement_trust_store(trust),
        expected_p12_report_sha256=hash_signed_artifact(report),
        expected_p12_plan_sha256=hash_signed_artifact(bundle["plan"]),
        expected_p12_bundle_index_sha256=hash_signed_artifact(bundle["index"]),
        expected_p12_cohort_batch_sha256=hash_signed_artifact(bundle["cohort"]),
        expected_p12_cohort_attestation_sha256=hash_signed_artifact(
            bundle["cohort_attestation"]
        ),
        expected_run_id=binding.run_id,
        expected_cohort_id=binding.cohort_id,
    )
    return {
        **bundle,
        "report": report,
        "binding": binding,
        "settlement_trust": trust,
        "settlement_policy": policy,
        "settlement_pins": pins,
        "event_at": p12.AT + timedelta(hours=1),
        "observed_at": p12.AT + timedelta(hours=2),
        "issued_at": p12.AT + timedelta(hours=3),
        "completeness_issued_at": p12.AT + timedelta(hours=3, minutes=30),
        "expires_at": p12.AT + timedelta(hours=12),
        "evaluation_at": p12.AT + timedelta(hours=4),
    }


def _transaction(case: dict, label: str):
    transaction_id = p12._sha(f"transaction:{label}")
    return next(
        item
        for item in case["cohort"].transactions
        if item.transaction_id_sha256 == transaction_id
    )


def _status_event(
    case: dict,
    *,
    label: str,
    previous: TransactionStatus,
    current: TransactionStatus,
    offset_minutes: int = 0,
    event_id_label: str | None = None,
) -> SettlementStatusChange:
    transaction = _transaction(case, label)
    identity = event_id_label or f"event:{label}:{current.value}"
    return SettlementStatusChange(
        event_id_sha256=p12._sha(identity),
        transaction_id_sha256=transaction.transaction_id_sha256,
        original_transaction_sha256=hash_signed_artifact(transaction),
        previous_status=previous,
        current_status=current,
        source_row_sha256=p12._sha(
            f"amendment-source:{label}:{current.value}:{offset_minutes}"
        ),
        effective_at=case["event_at"] + timedelta(minutes=offset_minutes),
    )


def _adjustment_event(
    case: dict,
    *,
    amount: str = "200",
    offset_minutes: int = 0,
) -> SettlementPayoutAdjustment:
    transaction = _transaction(case, "paid-new")
    return SettlementPayoutAdjustment(
        event_id_sha256=p12._sha("event:paid-new:refund"),
        transaction_id_sha256=transaction.transaction_id_sha256,
        original_transaction_sha256=hash_signed_artifact(transaction),
        adjustment_id_sha256=p12._sha("adjustment:paid-new:refund"),
        adjustment_kind=PayoutAdjustmentKind.REFUND,
        amount=Decimal(amount),
        currency="JPY",
        source_row_sha256=p12._sha("amendment-source:paid-new:refund"),
        effective_at=case["event_at"] + timedelta(minutes=offset_minutes),
    )


def _signed(
    case: dict,
    events,
    *,
    amendment_label: str = "a1",
    decision: SettlementCompletenessDecision = (
        SettlementCompletenessDecision.COMPLETE
    ),
):
    amendment = sign_settlement_amendment(
        case["binding"],
        tuple(events),
        case["settlement_policy"],
        case["settlement_trust"],
        case["keys"]["cohort"],
        amendment_id_sha256=p12._sha(f"amendment:{amendment_label}"),
        observed_through_at=case["observed_at"],
        issued_at=case["issued_at"],
        expires_at=case["expires_at"],
    )
    coverage = SettlementCompletenessCoverage(
        source_export_sha256=p12._sha(f"source-export:{amendment_label}"),
        complete_export_receipt_sha256=p12._sha(
            f"complete-export:{amendment_label}"
        ),
        coverage_rule_sha256=case[
            "settlement_policy"
        ].completeness_rule_sha256,
        raw_records=len(amendment.events),
        accepted_records=len(amendment.events),
        rejected_records=0,
        duplicate_records=0,
        conflict_records=0,
        unknown_records=0,
        output_records=len(amendment.events),
        event_id_set_sha256=p12._set_hash(
            [item.event_id_sha256 for item in amendment.events]
        ),
        privacy_scan_sha256=p12._sha(f"privacy:{amendment_label}"),
        privacy_scan_passed=True,
    )
    completeness = sign_settlement_completeness_attestation(
        amendment,
        case["binding"],
        coverage,
        case["settlement_policy"],
        case["settlement_trust"],
        case["keys"]["qa"],
        decision=decision,
        issued_at=case["completeness_issued_at"],
        expires_at=case["expires_at"],
    )
    return amendment, completeness


def _evaluate(case: dict, amendments, completeness):
    return evaluate_settlement_amendments(
        case["binding"],
        case["cohort"],
        tuple(amendments),
        tuple(completeness),
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )


def test_positive_settled_delta_from_later_pending_confirmation() -> None:
    case = _case(pending_new=True)
    event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.PENDING,
        current=TransactionStatus.CONFIRMED,
    )
    amendment, completeness = _signed(case, (event,))

    result = _evaluate(case, (amendment,), (completeness,))

    assert result.original_settled_amount == Decimal("200")
    assert result.amended_settled_amount == Decimal("300")
    assert result.settled_delta == Decimal("100")
    assert result.positive_settled_delta == Decimal("100")
    assert result.negative_settled_delta == Decimal("0")
    assert verify_settlement_amendment(
        amendment,
        completeness,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )


def test_signed_zero_event_complete_snapshot_proves_unchanged_settlement() -> None:
    case = _case()
    amendment, completeness = _signed(case, ())

    result = _evaluate(case, (amendment,), (completeness,))

    assert amendment.events == ()
    assert completeness.coverage.raw_records == 0
    assert completeness.coverage.output_records == 0
    assert result.applied_event_count == 0
    assert result.original_settled_amount == Decimal("300")
    assert result.amended_settled_amount == Decimal("300")
    assert result.settled_delta == Decimal("0")
    assert verify_settlement_amendment(
        amendment,
        completeness,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )


def test_zero_event_incomplete_and_missing_signed_snapshot_are_rejected() -> None:
    case = _case()
    amendment, incomplete = _signed(
        case,
        (),
        decision=SettlementCompletenessDecision.INCOMPLETE,
    )

    assert not verify_settlement_amendment(
        amendment,
        incomplete,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )
    with pytest.raises(SettlementAmendmentError, match="completeness"):
        _evaluate(case, (amendment,), (incomplete,))
    with pytest.raises(SettlementAmendmentError, match="at least one"):
        _evaluate(case, (), ())

    inconsistent_coverage = SettlementCompletenessCoverage.model_validate(
        {
            **incomplete.coverage.model_dump(),
            "raw_records": 1,
            "duplicate_records": 1,
        }
    )
    inconsistent_complete = sign_settlement_completeness_attestation(
        amendment,
        case["binding"],
        inconsistent_coverage,
        case["settlement_policy"],
        case["settlement_trust"],
        case["keys"]["qa"],
        decision=SettlementCompletenessDecision.COMPLETE,
        issued_at=case["completeness_issued_at"],
        expires_at=case["expires_at"],
    )
    assert not verify_settlement_amendment(
        amendment,
        inconsistent_complete,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )


def test_partner_positive_and_negative_attribution_covers_frozen_set() -> None:
    case = _case(pending_new=True)
    positive = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.PENDING,
        current=TransactionStatus.CONFIRMED,
        offset_minutes=1,
    )
    negative = _adjustment_event(case, offset_minutes=2)
    amendment, completeness = _signed(case, (negative, positive))

    result = _evaluate(case, (amendment,), (completeness,))
    by_partner = {item.partner_id: item for item in result.partner_settlements}

    assert result.partner_ids == ("partner-a", "partner-b", "partner-c")
    assert tuple(by_partner) == result.partner_ids
    assert (
        by_partner["partner-a"].original_settled_amount,
        by_partner["partner-a"].amended_settled_amount,
        by_partner["partner-a"].settled_delta,
    ) == (Decimal("0"), Decimal("100"), Decimal("100"))
    assert (
        by_partner["partner-b"].original_settled_amount,
        by_partner["partner-b"].amended_settled_amount,
        by_partner["partner-b"].settled_delta,
    ) == (Decimal("200"), Decimal("0"), Decimal("-200"))
    assert (
        by_partner["partner-c"].original_settled_amount,
        by_partner["partner-c"].amended_settled_amount,
        by_partner["partner-c"].settled_delta,
    ) == (Decimal("0"), Decimal("0"), Decimal("0"))
    assert sum(
        (item.original_settled_amount for item in result.partner_settlements),
        Decimal(0),
    ) == result.original_settled_amount
    assert sum(
        (item.amended_settled_amount for item in result.partner_settlements),
        Decimal(0),
    ) == result.amended_settled_amount
    assert sum(
        (item.settled_delta for item in result.partner_settlements), Decimal(0)
    ) == result.settled_delta == Decimal("-100")

    with pytest.raises(ValidationError, match="exact frozen partner set"):
        type(result).model_validate(
            {
                **result.model_dump(),
                "partner_settlements": tuple(
                    item
                    for item in result.partner_settlements
                    if item.partner_id != "partner-c"
                ),
            }
        )


@pytest.mark.parametrize(
    ("event_factory", "expected_delta"),
    (
        (
            lambda case: _status_event(
                case,
                label="confirmed-new",
                previous=TransactionStatus.CONFIRMED,
                current=TransactionStatus.REFUNDED,
            ),
            Decimal("-100"),
        ),
        (lambda case: _adjustment_event(case), Decimal("-200")),
    ),
)
def test_negative_settled_delta_for_status_or_full_payout_reversal(
    event_factory, expected_delta
) -> None:
    case = _case()
    amendment, completeness = _signed(case, (event_factory(case),))

    result = _evaluate(case, (amendment,), (completeness,))

    assert result.settled_delta == expected_delta
    assert result.positive_settled_delta == Decimal("0")
    assert result.negative_settled_delta == expected_delta


def test_original_binding_rejects_cross_run_splice() -> None:
    case = _case()
    other = _case()

    assert verify_original_settlement_binding(
        case["binding"],
        case["report"],
        case["policy"],
        case["trust"],
        case["pins"],
        case["plan"],
        case["index"],
        case["cohort"],
        case["cohort_attestation"],
    )
    assert not verify_original_settlement_binding(
        case["binding"],
        other["report"],
        case["policy"],
        case["trust"],
        case["pins"],
        case["plan"],
        case["index"],
        case["cohort"],
        case["cohort_attestation"],
    )


def test_original_transaction_amount_currency_and_identity_are_immutable() -> None:
    case = _case()
    bad_amount = _adjustment_event(case, amount="201")
    amendment, completeness = _signed(case, (bad_amount,))

    assert not verify_settlement_amendment(
        amendment,
        completeness,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SettlementStatusChange.model_validate(
            {
                **_status_event(
                    case,
                    label="confirmed-new",
                    previous=TransactionStatus.CONFIRMED,
                    current=TransactionStatus.REFUNDED,
                ).model_dump(),
                "partner_id": "partner-b",
                "cohort_id": "different-cohort",
                "amount": Decimal("999"),
                "currency": "USD",
            }
        )


def test_event_order_is_canonical_and_exact_replay_is_applied_once() -> None:
    case = _case()
    status = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.REFUNDED,
        offset_minutes=2,
    )
    adjustment = _adjustment_event(case, offset_minutes=1)
    first, first_completeness = _signed(case, (status, adjustment))
    second, _ = _signed(case, (adjustment, status))

    assert first.events == second.events
    assert first.event_root_sha256 == second.event_root_sha256
    assert hash_settlement_artifact(first) == hash_settlement_artifact(second)

    result = _evaluate(
        case,
        (first, first),
        (first_completeness, first_completeness),
    )
    assert result.applied_event_count == 2
    assert result.replayed_amendment_occurrences == 1
    assert result.replayed_event_occurrences == 0
    assert result.settled_delta == Decimal("-300")


def test_same_event_identity_with_different_content_is_a_conflict() -> None:
    case = _case()
    first_event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.REFUNDED,
        event_id_label="shared-event-id",
    )
    conflicting_event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.CHARGED_BACK,
        offset_minutes=1,
        event_id_label="shared-event-id",
    )
    first, first_completeness = _signed(case, (first_event,), amendment_label="a1")
    second, second_completeness = _signed(
        case, (conflicting_event,), amendment_label="a2"
    )

    with pytest.raises(SettlementAmendmentError, match="conflicting settlement event"):
        _evaluate(
            case,
            (first, second),
            (first_completeness, second_completeness),
        )


def test_completeness_is_required_independent_current_and_complete() -> None:
    case = _case()
    event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.REFUNDED,
    )
    amendment, completeness = _signed(case, (event,))

    with pytest.raises(SettlementAmendmentError, match="completeness"):
        _evaluate(case, (amendment,), ())
    assert not verify_settlement_amendment(
        amendment,
        completeness.model_copy(
            update={"decision": SettlementCompletenessDecision.INCOMPLETE}
        ),
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["evaluation_at"],
    )
    assert not verify_settlement_amendment(
        amendment,
        completeness,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        case["settlement_pins"],
        at=case["expires_at"],
    )


def test_wrong_keys_pins_payload_and_event_root_fail_closed() -> None:
    case = _case()
    event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.REFUNDED,
    )
    amendment, completeness = _signed(case, (event,))
    wrong_key = Ed25519PrivateKey.generate()
    with pytest.raises(SettlementAmendmentError, match="not pinned"):
        sign_settlement_amendment(
            case["binding"],
            (event,),
            case["settlement_policy"],
            case["settlement_trust"],
            wrong_key,
            amendment_id_sha256=p12._sha("amendment:wrong"),
            observed_through_at=case["observed_at"],
            issued_at=case["issued_at"],
            expires_at=case["expires_at"],
        )

    bad_pins = case["settlement_pins"].model_copy(
        update={"expected_p12_report_sha256": p12._sha("different-report")}
    )
    assert not verify_settlement_amendment(
        amendment,
        completeness,
        case["binding"],
        case["cohort"],
        case["settlement_policy"],
        case["settlement_trust"],
        bad_pins,
        at=case["evaluation_at"],
    )
    with pytest.raises(ValidationError, match="payload hash mismatch"):
        SignedSettlementAmendment.model_validate(
            {
                **amendment.model_dump(),
                "event_root_sha256": p12._sha("wrong-event-root"),
            }
        )


def test_models_expose_no_url_pii_account_or_credential_fields() -> None:
    schemas = (
        SignedSettlementAmendment.model_json_schema(),
        type(_case()["binding"]).model_json_schema(),
        SettlementCompletenessCoverage.model_json_schema(),
    )

    def property_names(value):
        if isinstance(value, dict):
            for name in value.get("properties", {}):
                yield name.lower()
            for nested in value.values():
                yield from property_names(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from property_names(nested)

    names = set(name for schema in schemas for name in property_names(schema))
    for forbidden in (
        "url",
        "source_url",
        "email",
        "credential",
        "raw_account_id",
        "password",
    ):
        assert forbidden not in names


def test_binding_and_artifact_hashes_are_deterministic() -> None:
    case = _case()
    binding_copy = type(case["binding"]).model_validate(
        case["binding"].model_dump()
    )
    event = _status_event(
        case,
        label="confirmed-new",
        previous=TransactionStatus.CONFIRMED,
        current=TransactionStatus.REFUNDED,
    )
    amendment, _ = _signed(case, (event,))
    amendment_copy = SignedSettlementAmendment.model_validate(
        amendment.model_dump()
    )

    assert hash_original_settlement_binding(case["binding"]) == (
        hash_original_settlement_binding(binding_copy)
    )
    assert hash_settlement_artifact(amendment) == hash_settlement_artifact(
        amendment_copy
    )
