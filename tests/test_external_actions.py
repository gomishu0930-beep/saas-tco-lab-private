from __future__ import annotations

import pickle
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import saas_preflight.external_actions as external_actions_module
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.external_actions import (
    ActionEnvironment,
    ActionExecutionClaim,
    ActionJournalEntry,
    ActionReceipt,
    ActionResult,
    ControllerExecutionGrant,
    ExternalAction,
    ExternalActionAuthority,
    ExternalActionExecutionGuard,
    ExternalActionInputError,
    ExternalActionPolicy,
    ExternalActionRequest,
    ExternalActionRuntime,
    ExternalActionTargetRule,
    ExternalActionTrustStore,
    JournalEventKind,
    JournalAuthorityState,
    JournalOutcomeState,
    append_action_journal_entry,
    build_external_action_request,
    fold_action_journal,
    hash_external_action_policy,
    hash_external_action_trust_store,
    issue_controller_execution_grant,
    revoke_execution_grant,
    sign_action_receipt,
    sign_human_execution_approval,
    verify_action_receipt,
)
from saas_preflight.release import ApprovalDecision

from test_release_assurance import AT, RUNTIME as PUBLIC_RUNTIME, public_go


CONTROLLER_PRIVATE = Ed25519PrivateKey.generate()
HUMAN_PRIVATE = Ed25519PrivateKey.generate()
EXECUTOR_PRIVATE = Ed25519PrivateKey.generate()
CONTROLLER_KEY = create_verification_key(
    CONTROLLER_PRIVATE.public_key(),
    issuer="action-controller",
    role=SigningRole.CONTROLLER,
)
HUMAN_KEY = create_verification_key(
    HUMAN_PRIVATE.public_key(),
    issuer="action-human",
    role=SigningRole.HUMAN_APPROVER,
)
EXECUTOR_KEY = create_verification_key(
    EXECUTOR_PRIVATE.public_key(),
    issuer="action-executor",
    role=SigningRole.EXECUTOR,
)
TRUST = ExternalActionTrustStore(
    controller=CONTROLLER_KEY,
    human=HUMAN_KEY,
    executor=EXECUTOR_KEY,
)
TARGET_RULES = tuple(
    ExternalActionTargetRule(
        action=action,
        environment=(
            ActionEnvironment.VENDOR_CONTACT
            if action
            in {
                ExternalAction.SEND_RIGHTS_INQUIRY,
                ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
            }
            else ActionEnvironment.PRODUCTION
        ),
        environment_sha256="1" * 64,
        vendor_slug=(
            "vendor-a"
            if action
            in {
                ExternalAction.SEND_RIGHTS_INQUIRY,
                ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
            }
            else None
        ),
        property_record_sha256="2" * 64,
        target_sha256="3" * 64,
    )
    for action in sorted(ExternalAction, key=lambda item: item.value)
)
POLICY = ExternalActionPolicy(
    policy_id="external-actions-v1",
    trust_store_sha256=hash_external_action_trust_store(TRUST),
    controller_key_id_sha256=CONTROLLER_KEY.key_id_sha256,
    human_key_id_sha256=HUMAN_KEY.key_id_sha256,
    executor_key_id_sha256=EXECUTOR_KEY.key_id_sha256,
    target_rules=TARGET_RULES,
    maximum_request_ttl_seconds=86_400,
    maximum_approval_ttl_seconds=43_200,
    maximum_grant_ttl_seconds=600,
)
POLICY_SHA = hash_external_action_policy(POLICY)
AUTHORITY = ExternalActionAuthority(POLICY, TRUST, CONTROLLER_PRIVATE)
RUNTIME = ExternalActionRuntime(
    POLICY,
    TRUST,
    release_assurance_runtime=PUBLIC_RUNTIME,
)
ACTION_AT = AT + timedelta(minutes=4)
ROOT = Path(__file__).resolve().parents[1]
STATE_STORE_ID = "d" * 64
STATE_AUTHENTICATION_KEY = b"synthetic-local-state-auth-key!!"
GUARD_CLOCKS: dict[ExternalActionExecutionGuard, list] = {}
STATE_ANCHOR_PINS: dict[str, tuple[int, str]] = {}


def request(
    action: ExternalAction = ExternalAction.SEND_RIGHTS_INQUIRY,
    **updates: object,
):
    contact = action in {
        ExternalAction.SEND_RIGHTS_INQUIRY,
        ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
    }
    values: dict[str, object] = {
        "request_id": f"request-{action.value.replace('_', '-')}",
        "requester_id": "integration-release",
        "action": action,
        "environment": (
            ActionEnvironment.VENDOR_CONTACT
            if contact
            else ActionEnvironment.PRODUCTION
        ),
        "environment_sha256": "1" * 64,
        "external_action_policy_sha256": POLICY_SHA,
        "vendor_slug": "vendor-a" if contact else None,
        "property_record_sha256": "2" * 64,
        "target_sha256": "3" * 64,
        "payload_sha256": "4" * 64,
        "idempotency_key_sha256": "5" * 64,
        "expected_pre_state_sha256": "6" * 64,
        "expected_post_state_sha256": "7" * 64,
        "release_id": "release-p10" if not contact else None,
        "manifest_sha256": "8" * 64 if not contact else None,
        "artifact_sha256": "9" * 64 if not contact else None,
        "public_release_report_sha256": None,
        "public_release_authorization_sha256": None,
        "requested_at": AT,
        "not_before": AT,
        "expires_at": AT + timedelta(hours=8),
    }
    if action is ExternalAction.ACTIVATE_PUBLIC_RELEASE:
        _, _, _, _, _, report = public_go()
        assert report.authorization is not None
        values.update(
            release_id=report.release_id,
            manifest_sha256=report.manifest_sha256,
            artifact_sha256=report.artifact_sha256,
            public_release_report_sha256=report.report_sha256,
            public_release_authorization_sha256=report.authorization.payload_sha256,
        )
    values.update(updates)
    return build_external_action_request(**values)


def approval(
    selected,
    *,
    decision: ApprovalDecision = ApprovalDecision.GO,
    private_key=HUMAN_PRIVATE,
    issuer: str = "action-human",
    issued_at=AT + timedelta(minutes=1),
    expires_at=AT + timedelta(hours=2),
):
    return sign_human_execution_approval(
        selected,
        private_key,
        issuer=issuer,
        decision=decision,
        decision_record_sha256="a" * 64,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def grant(selected=None, selected_approval=None):
    selected = selected or request()
    selected_approval = selected_approval or approval(selected)
    return issue_controller_execution_grant(
        selected, selected_approval, AUTHORITY, at=ACTION_AT
    )


def activation_grant():
    selected = request(ExternalAction.ACTIVATE_PUBLIC_RELEASE)
    selected_approval = approval(selected)
    _, _, _, _, _, report = public_go()
    issued = issue_controller_execution_grant(
        selected,
        selected_approval,
        AUTHORITY,
        at=ACTION_AT,
        public_report=report,
        public_runtime=PUBLIC_RUNTIME,
    )
    return selected, selected_approval, issued, report


@pytest.fixture
def guard_factory(tmp_path):
    sequence = 0

    def make(
        *, at=ACTION_AT, path=None, clock_fn=None
    ) -> ExternalActionExecutionGuard:
        nonlocal sequence
        sequence += 1
        selected_path = path or tmp_path / f"external-actions-{sequence}.sqlite"
        runtime = ExternalActionRuntime(
            POLICY,
            TRUST,
            release_assurance_runtime=PUBLIC_RUNTIME,
        )
        clock = [at]
        clock_callback = clock_fn or (lambda: clock[0])
        anchor_key = str(selected_path.resolve())

        def commit_anchor(revision: int, anchor_sha256: str) -> None:
            previous = STATE_ANCHOR_PINS.get(anchor_key)
            if previous is not None and (
                revision < previous[0]
                or (revision == previous[0] and anchor_sha256 != previous[1])
            ):
                raise ExternalActionInputError(
                    "external state anchor is not monotonic"
                )
            STATE_ANCHOR_PINS[anchor_key] = (revision, anchor_sha256)

        def read_anchor() -> str:
            return STATE_ANCHOR_PINS[anchor_key][1]

        if selected_path.exists():
            expected_anchor_sha256 = STATE_ANCHOR_PINS[anchor_key][1]
            guard = ExternalActionExecutionGuard.open(
                runtime,
                selected_path,
                expected_store_id_sha256=STATE_STORE_ID,
                expected_anchor_sha256=expected_anchor_sha256,
                state_authentication_key=STATE_AUTHENTICATION_KEY,
                anchor_commit=commit_anchor,
                anchor_read=read_anchor,
                clock=clock_callback,
            )
        else:
            guard = ExternalActionExecutionGuard.create(
                runtime,
                selected_path,
                store_id_sha256=STATE_STORE_ID,
                state_authentication_key=STATE_AUTHENTICATION_KEY,
                anchor_commit=commit_anchor,
                anchor_read=read_anchor,
                clock=clock_callback,
            )
        GUARD_CLOCKS[guard] = clock
        return guard

    return make


def execution_claim(
    selected,
    selected_approval,
    issued,
    guard,
    *,
    public_report=None,
) -> ActionExecutionClaim:
    return guard.claim(
        selected,
        selected_approval,
        issued,
        observed_pre_state_sha256=selected.expected_pre_state_sha256,
        public_report=public_report,
    )


def receipt(selected, selected_approval, issued, selected_claim, guard, **updates: object):
    values: dict[str, object] = {
        "issuer": "action-executor",
        "result": ActionResult.SUCCEEDED,
        "observed_pre_state_sha256": selected.expected_pre_state_sha256,
        "observed_post_state_sha256": selected.expected_post_state_sha256,
        "provider_operation_sha256": "b" * 64,
        "provider_audit_receipt_sha256": "c" * 64,
    }
    completed_at = updates.pop(
        "completed_at", max(selected_claim.claimed_at, ACTION_AT) + timedelta(minutes=2)
    )
    GUARD_CLOCKS[guard][0] = completed_at
    values.update(updates)
    return sign_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        guard,
        EXECUTOR_PRIVATE,
        **values,
    )


@pytest.mark.parametrize(
    "action",
    (
        ExternalAction.SEND_RIGHTS_INQUIRY,
        ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
        ExternalAction.ACTIVATE_PUBLIC_RELEASE,
        ExternalAction.DISABLE_PUBLIC_RELEASE,
    ),
)
def test_request_is_strict_content_bound_for_all_four_actions(action) -> None:
    selected = request(action)
    assert selected.request_sha256
    copied = selected.model_copy(update={"target_sha256": "f" * 64})
    with pytest.raises(ValidationError):
        type(selected).model_validate(copied.model_dump())


def test_action_specific_fields_cannot_widen_scope() -> None:
    with pytest.raises(ValidationError, match="vendor action cannot carry"):
        request(release_id="release-x")
    with pytest.raises(ValidationError, match="requires vendor_slug"):
        request(vendor_slug=None)
    with pytest.raises(ValidationError, match="disable must not depend"):
        request(
            ExternalAction.DISABLE_PUBLIC_RELEASE,
            public_release_report_sha256="a" * 64,
        )
    with pytest.raises(ValidationError, match="requires P10"):
        request(
            ExternalAction.ACTIVATE_PUBLIC_RELEASE,
            public_release_report_sha256=None,
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"environment_sha256": "a" * 64},
        {"vendor_slug": "vendor-b"},
        {"property_record_sha256": "b" * 64},
        {"target_sha256": "c" * 64},
    ),
)
def test_fixed_policy_rejects_unapproved_environment_vendor_property_target(
    updates,
) -> None:
    selected = request(**updates)

    with pytest.raises(ExternalActionInputError, match="target is not allowed"):
        grant(selected, approval(selected))


def test_human_go_issues_short_one_shot_contact_grant() -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)

    assert issued.request_sha256 == selected.request_sha256
    assert issued.human_approval_payload_sha256 == selected_approval.payload_sha256
    assert issued.expires_at == ACTION_AT + timedelta(minutes=10)
    assert RUNTIME.verifies_artifacts(
        selected,
        selected_approval,
        issued,
        at=ACTION_AT,
        observed_pre_state_sha256=selected.expected_pre_state_sha256,
    )


@pytest.mark.parametrize(
    "decision", (ApprovalDecision.STOP, ApprovalDecision.CONDITIONAL)
)
def test_stop_and_conditional_never_issue_a_grant(decision) -> None:
    selected = request()
    with pytest.raises(ExternalActionInputError, match="only Human GO"):
        grant(selected, approval(selected, decision=decision))


def test_wrong_human_key_policy_and_request_copy_are_rejected() -> None:
    selected = request()
    attacker = Ed25519PrivateKey.generate()
    attacker_approval = approval(
        selected, private_key=attacker, issuer="attacker-human"
    )
    with pytest.raises(ExternalActionInputError, match="approval is invalid"):
        grant(selected, attacker_approval)

    copied = selected.model_copy(update={"target_sha256": "d" * 64})
    with pytest.raises(ExternalActionInputError):
        grant(copied, approval(selected))

    alternate_policy = POLICY.model_copy(update={"policy_id": "alternate-actions"})
    alternate_values = selected.model_dump(exclude={"request_sha256"})
    alternate_values["external_action_policy_sha256"] = hash_external_action_policy(
        alternate_policy
    )
    alternate = build_external_action_request(**alternate_values)
    with pytest.raises(ExternalActionInputError, match="policy binding"):
        grant(alternate, approval(alternate))


def test_request_approval_and_grant_time_boundaries_are_half_open() -> None:
    selected = request(expires_at=ACTION_AT)
    with pytest.raises(ExternalActionInputError, match="not currently"):
        grant(selected, approval(selected, expires_at=ACTION_AT + timedelta(minutes=1)))

    future = request(not_before=ACTION_AT + timedelta(microseconds=1))
    with pytest.raises(ExternalActionInputError, match="not currently"):
        grant(future, approval(future))

    overlong = request(expires_at=AT + timedelta(days=1, microseconds=1))
    with pytest.raises(ExternalActionInputError, match="request TTL"):
        grant(overlong, approval(overlong))

    good = request()
    good_approval = approval(good)
    issued = grant(good, good_approval)
    assert not RUNTIME.verifies_artifacts(
        good,
        good_approval,
        issued,
        at=issued.expires_at,
        observed_pre_state_sha256=good.expected_pre_state_sha256,
    )
    assert not RUNTIME.verifies_artifacts(
        good,
        good_approval,
        issued,
        at=ACTION_AT,
        observed_pre_state_sha256="e" * 64,
    )


def test_activation_requires_exact_current_p10_public_go() -> None:
    selected, selected_approval, issued, report = activation_grant()
    assert issued.public_release_report_sha256 == report.report_sha256
    assert RUNTIME.verifies_artifacts(
        selected,
        selected_approval,
        issued,
        at=ACTION_AT,
        observed_pre_state_sha256=selected.expected_pre_state_sha256,
        public_report=report,
    )

    mismatched = request(
        ExternalAction.ACTIVATE_PUBLIC_RELEASE,
        artifact_sha256="f" * 64,
    )
    with pytest.raises(ExternalActionInputError, match="release binding"):
        issue_controller_execution_grant(
            mismatched,
            approval(mismatched),
            AUTHORITY,
            at=ACTION_AT,
            public_report=report,
            public_runtime=PUBLIC_RUNTIME,
        )

    copied_report = report.model_copy(update={"artifact_sha256": "f" * 64})
    with pytest.raises(ExternalActionInputError, match="current P10"):
        issue_controller_execution_grant(
            selected,
            selected_approval,
            AUTHORITY,
            at=ACTION_AT,
            public_report=copied_report,
            public_runtime=PUBLIC_RUNTIME,
        )


def test_runtime_reproves_human_go_and_current_p10_at_consumption() -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    forged_values = issued.model_dump(
        exclude={"payload_sha256", "signature_base64url"}
    )
    forged_values["human_approval_payload_sha256"] = "f" * 64
    forged = AUTHORITY._sign(ControllerExecutionGrant, forged_values)

    assert not RUNTIME.verifies_artifacts(
        selected,
        selected_approval,
        forged,
        at=ACTION_AT,
        observed_pre_state_sha256=selected.expected_pre_state_sha256,
    )

    active, active_approval, active_grant, report = activation_grant()
    assert not RUNTIME.verifies_artifacts(
        active,
        active_approval,
        active_grant,
        at=report.expires_at,
        observed_pre_state_sha256=active.expected_pre_state_sha256,
        public_report=report,
    )


def test_attacker_authority_cannot_create_a_grant_for_fixed_runtime() -> None:
    controller = Ed25519PrivateKey.generate()
    human = Ed25519PrivateKey.generate()
    executor = Ed25519PrivateKey.generate()
    trust = ExternalActionTrustStore(
        controller=create_verification_key(
            controller.public_key(), issuer="evil-controller", role=SigningRole.CONTROLLER
        ),
        human=create_verification_key(
            human.public_key(), issuer="evil-human", role=SigningRole.HUMAN_APPROVER
        ),
        executor=create_verification_key(
            executor.public_key(), issuer="evil-executor", role=SigningRole.EXECUTOR
        ),
    )
    policy = ExternalActionPolicy(
        policy_id="evil-actions",
        trust_store_sha256=hash_external_action_trust_store(trust),
        controller_key_id_sha256=trust.controller.key_id_sha256,
        human_key_id_sha256=trust.human.key_id_sha256,
        executor_key_id_sha256=trust.executor.key_id_sha256,
        target_rules=TARGET_RULES,
        maximum_request_ttl_seconds=86_400,
        maximum_approval_ttl_seconds=43_200,
        maximum_grant_ttl_seconds=600,
    )
    authority = ExternalActionAuthority(policy, trust, controller)
    selected = request(
        external_action_policy_sha256=hash_external_action_policy(policy)
    )
    selected_approval = sign_human_execution_approval(
        selected,
        human,
        issuer="evil-human",
        decision=ApprovalDecision.GO,
        decision_record_sha256="a" * 64,
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(hours=2),
    )
    issued = issue_controller_execution_grant(
        selected, selected_approval, authority, at=ACTION_AT
    )

    assert not RUNTIME.verifies_artifacts(
        selected,
        selected_approval,
        issued,
        at=ACTION_AT,
        observed_pre_state_sha256=selected.expected_pre_state_sha256,
    )


def test_one_guard_atomically_rejects_second_grant_for_same_idempotency(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    first = grant(selected, selected_approval)
    second = issue_controller_execution_grant(
        selected,
        selected_approval,
        AUTHORITY,
        at=ACTION_AT + timedelta(minutes=1),
    )
    guard = guard_factory(at=ACTION_AT + timedelta(minutes=1))
    execution_claim(selected, selected_approval, first, guard)

    with pytest.raises(ExternalActionInputError, match="idempotency key"):
        execution_claim(
            selected,
            selected_approval,
            second,
            guard,
        )


def test_same_request_id_with_different_payload_and_idempotency_conflicts(
    guard_factory,
) -> None:
    first_request = request()
    first_approval = approval(first_request)
    first_grant = grant(first_request, first_approval)
    guard = guard_factory()
    execution_claim(first_request, first_approval, first_grant, guard)
    conflicting_request = request(
        payload_sha256="e" * 64,
        idempotency_key_sha256="f" * 64,
    )
    conflicting_approval = approval(conflicting_request)
    conflicting_grant = grant(conflicting_request, conflicting_approval)

    with pytest.raises(ExternalActionInputError, match="request ID"):
        execution_claim(
            conflicting_request,
            conflicting_approval,
            conflicting_grant,
            guard,
        )


def test_durable_store_rejects_replay_after_guard_restart(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "restart-state.sqlite"
    first_guard = guard_factory(path=state_path)
    selected_claim = execution_claim(
        selected, selected_approval, issued, first_guard
    )
    completed = receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        first_guard,
    )
    restarted_guard = guard_factory(
        path=state_path, at=ACTION_AT + timedelta(minutes=1)
    )

    with pytest.raises(ExternalActionInputError, match="already claimed"):
        execution_claim(
            selected, selected_approval, issued, restarted_guard
        )
    assert verify_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        completed,
        restarted_guard,
        at=completed.completed_at,
    )
    first = append_action_journal_entry(
        journal_id="journal-restart-recovery",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    recovered = fold_action_journal(
        selected,
        selected_approval,
        issued,
        selected_claim,
        (first, second, third),
        restarted_guard,
        receipts=(completed,),
        at=completed.completed_at,
    )

    assert recovered.outcome_state is JournalOutcomeState.SUCCEEDED


def test_missing_configured_store_never_bootstraps_empty_recovery(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "missing-state.sqlite"
    guard = guard_factory(path=state_path)
    execution_claim(selected, selected_approval, issued, guard)
    state_path.replace(tmp_path / "removed-state.sqlite")

    with pytest.raises(ExternalActionInputError, match="already provisioned"):
        guard_factory(path=state_path)


@pytest.mark.parametrize(
    "tamper_sql",
    (
        "DELETE FROM external_action_claims",
        "UPDATE external_action_meta SET value = '999' WHERE key = 'state_revision'",
    ),
)
def test_authenticated_store_rejects_row_deletion_and_metadata_tamper(
    guard_factory, tmp_path, tamper_sql
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / f"tamper-{len(tamper_sql)}.sqlite"
    guard = guard_factory(path=state_path)
    execution_claim(selected, selected_approval, issued, guard)
    with sqlite3.connect(state_path) as connection:
        connection.execute(tamper_sql)

    with pytest.raises(ExternalActionInputError, match="authentication|rollback"):
        guard.authoritative_snapshot(issued)


def test_store_rejects_schema_trigger_substitution_before_claim(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "trigger-state.sqlite"
    guard = guard_factory(path=state_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER ignore_claim BEFORE INSERT ON external_action_claims
            BEGIN SELECT RAISE(IGNORE); END
            """
        )

    with pytest.raises(ExternalActionInputError, match="schema fingerprint"):
        execution_claim(selected, selected_approval, issued, guard)


def test_anchor_rejects_older_authenticated_database_replacement(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "rollback-state.sqlite"
    old_state_path = tmp_path / "old-state.sqlite"
    guard = guard_factory(path=state_path)
    with sqlite3.connect(state_path) as source, sqlite3.connect(
        old_state_path
    ) as destination:
        source.backup(destination)
    execution_claim(selected, selected_approval, issued, guard)
    with sqlite3.connect(state_path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    old_state_path.replace(state_path)

    with pytest.raises(ExternalActionInputError, match="rollback|anchor"):
        guard.authoritative_snapshot(issued)


def test_external_anchor_pin_rejects_database_and_companion_pair_rollback(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "pair-rollback-state.sqlite"
    old_state_path = tmp_path / "pair-old-state.sqlite"
    anchor_path = state_path.with_name(f"{state_path.name}.anchor.json")
    guard = guard_factory(path=state_path)
    with sqlite3.connect(state_path) as source, sqlite3.connect(
        old_state_path
    ) as destination:
        source.backup(destination)
    old_anchor = anchor_path.read_bytes()
    execution_claim(selected, selected_approval, issued, guard)
    with sqlite3.connect(state_path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    old_state_path.replace(state_path)
    anchor_path.write_bytes(old_anchor)

    with pytest.raises(ExternalActionInputError, match="rollback|anchor"):
        guard_factory(path=state_path)


def test_durable_store_claim_is_atomic_across_guard_instances(
    guard_factory, tmp_path
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "concurrent-state.sqlite"
    guards = (
        guard_factory(path=state_path),
        guard_factory(path=state_path),
    )

    def attempt(guard) -> bool:
        try:
            execution_claim(selected, selected_approval, issued, guard)
        except ExternalActionInputError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(attempt, guards))

    assert sum(results) == 1
def test_guard_clock_not_caller_time_controls_expiry(guard_factory) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    expired_guard = guard_factory(at=issued.expires_at)

    with pytest.raises(ExternalActionInputError, match="authority is invalid"):
        execution_claim(
            selected, selected_approval, issued, expired_guard
        )


def test_guard_clock_prevents_backdated_late_receipt(guard_factory) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(
        selected, selected_approval, issued, guard
    )
    GUARD_CLOCKS[guard][0] = selected_claim.claimed_at + timedelta(days=365)

    with pytest.raises(ExternalActionInputError, match="completion time"):
        sign_action_receipt(
            selected,
            selected_approval,
            issued,
            selected_claim,
            guard,
            EXECUTOR_PRIVATE,
            issuer="action-executor",
            result=ActionResult.SUCCEEDED,
            observed_pre_state_sha256=selected.expected_pre_state_sha256,
            observed_post_state_sha256=selected.expected_post_state_sha256,
            provider_operation_sha256="b" * 64,
            provider_audit_receipt_sha256="c" * 64,
        )


def test_claim_samples_clock_after_waiting_for_store_lock(
    guard_factory, tmp_path
) -> None:
    import fcntl

    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "claim-clock-linearization.sqlite"
    guard = guard_factory(
        path=state_path,
        at=issued.expires_at - timedelta(microseconds=1),
    )
    lock_path = state_path.with_name(f"{state_path.name}.lock")
    started = Event()

    def attempt() -> bool:
        started.set()
        try:
            execution_claim(selected, selected_approval, issued, guard)
        except ExternalActionInputError:
            return False
        return True

    with lock_path.open("a+b") as lock_file, ThreadPoolExecutor(
        max_workers=1
    ) as executor:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        future = executor.submit(attempt)
        assert started.wait(timeout=2)
        GUARD_CLOCKS[guard][0] = issued.expires_at + timedelta(seconds=1)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        accepted = future.result(timeout=2)

    assert not accepted
    assert guard.authoritative_snapshot(issued)[0] is None


def test_receipt_samples_clock_after_waiting_for_store_lock(
    guard_factory, tmp_path
) -> None:
    import fcntl

    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    state_path = tmp_path / "receipt-clock-linearization.sqlite"
    clock_value = [ACTION_AT]
    receipt_clock_sampled = Event()
    clock_calls = 0

    def controlled_clock():
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls >= 2:
            receipt_clock_sampled.set()
        return clock_value[0]

    guard = guard_factory(path=state_path, clock_fn=controlled_clock)
    selected_claim = execution_claim(
        selected, selected_approval, issued, guard
    )
    clock_value[0] = selected_claim.claimed_at + timedelta(
        seconds=POLICY.maximum_receipt_delay_seconds
    )
    lock_path = state_path.with_name(f"{state_path.name}.lock")
    started = Event()

    def attempt() -> bool:
        started.set()
        try:
            sign_action_receipt(
                selected,
                selected_approval,
                issued,
                selected_claim,
                guard,
                EXECUTOR_PRIVATE,
                issuer="action-executor",
                result=ActionResult.SUCCEEDED,
                observed_pre_state_sha256=selected.expected_pre_state_sha256,
                observed_post_state_sha256=selected.expected_post_state_sha256,
                provider_operation_sha256="b" * 64,
                provider_audit_receipt_sha256="c" * 64,
            )
        except ExternalActionInputError:
            return False
        return True

    with lock_path.open("a+b") as lock_file, ThreadPoolExecutor(
        max_workers=1
    ) as executor:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        future = executor.submit(attempt)
        assert started.wait(timeout=2)
        assert not receipt_clock_sampled.wait(timeout=0.1)
        clock_value[0] += timedelta(microseconds=1)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        accepted = future.result(timeout=2)

    assert not accepted
    assert guard.authoritative_snapshot(issued)[1] is None


def test_revocation_removes_authority_but_does_not_create_a_disable(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory(at=ACTION_AT + timedelta(minutes=1))
    future = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        guard,
        reason_record_sha256="d" * 64,
        issued_at=ACTION_AT,
        effective_at=ACTION_AT + timedelta(minutes=2),
    )
    before = execution_claim(
        selected,
        selected_approval,
        issued,
        guard,
    )
    assert before.grant_payload_sha256 == issued.payload_sha256

    denied_guard = guard_factory(at=future.effective_at)
    denied_guard.register_revocation(selected, issued, future)
    with pytest.raises(ExternalActionInputError, match="revoked"):
        execution_claim(
            selected,
            selected_approval,
            issued,
            denied_guard,
        )


def test_executor_receipt_is_bound_to_success_and_post_state(guard_factory) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )

    assert verify_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        completed,
        guard,
        at=completed.completed_at,
    )
    assert not verify_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        completed,
        guard,
        at=completed.completed_at - timedelta(microseconds=1),
    )
    failed_guard = guard_factory()
    failed_claim = execution_claim(
        selected, selected_approval, issued, failed_guard
    )
    failed = receipt(
        selected,
        selected_approval,
        issued,
        failed_claim,
        failed_guard,
        result=ActionResult.FAILED,
        observed_post_state_sha256=selected.expected_pre_state_sha256,
    )
    assert verify_action_receipt(
        selected,
        selected_approval,
        issued,
        failed_claim,
        failed,
        failed_guard,
        at=failed.completed_at,
        require_success=False,
    )
    assert not verify_action_receipt(
        selected,
        selected_approval,
        issued,
        failed_claim,
        failed,
        failed_guard,
        at=failed.completed_at,
    )
    wrong_guard = guard_factory()
    wrong_claim = execution_claim(
        selected, selected_approval, issued, wrong_guard
    )
    with pytest.raises(ExternalActionInputError, match="expected post-state"):
        receipt(
            selected,
            selected_approval,
            issued,
            wrong_claim,
            wrong_guard,
            observed_post_state_sha256="f" * 64,
        )

    forged = completed.model_copy(update={"provider_operation_sha256": "e" * 64})
    assert not verify_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        forged,
        guard,
        at=completed.completed_at,
    )


def test_receipt_completion_delay_is_policy_bounded(guard_factory) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    exact_guard = guard_factory()
    exact_claim = execution_claim(
        selected, selected_approval, issued, exact_guard
    )
    exact = receipt(
        selected,
        selected_approval,
        issued,
        exact_claim,
        exact_guard,
        completed_at=(
            exact_claim.claimed_at
            + timedelta(seconds=POLICY.maximum_receipt_delay_seconds)
        ),
    )
    assert verify_action_receipt(
        selected,
        selected_approval,
        issued,
        exact_claim,
        exact,
        exact_guard,
        at=exact.completed_at,
    )

    late_guard = guard_factory()
    late_claim = execution_claim(
        selected, selected_approval, issued, late_guard
    )
    with pytest.raises(ExternalActionInputError, match="completion time"):
        receipt(
            selected,
            selected_approval,
            issued,
            late_claim,
            late_guard,
            completed_at=(
                late_claim.claimed_at
                + timedelta(
                    seconds=POLICY.maximum_receipt_delay_seconds,
                    microseconds=1,
                )
            ),
        )


def test_executor_signed_wrong_poststate_success_is_never_accepted(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    source_guard = guard_factory()
    source_claim = execution_claim(
        selected, selected_approval, issued, source_guard
    )
    failed = receipt(
        selected,
        selected_approval,
        issued,
        source_claim,
        source_guard,
        result=ActionResult.FAILED,
        observed_post_state_sha256=selected.expected_pre_state_sha256,
    )
    forged_values = failed.model_dump(
        exclude={"payload_sha256", "signature_base64url"}
    )
    forged_values["result"] = ActionResult.SUCCEEDED
    forged_values["receipt_id_sha256"] = external_actions_module._canonical_sha256(
        {
            "request_sha256": selected.request_sha256,
            "grant_payload_sha256": issued.payload_sha256,
            "claim_sha256": source_claim.claim_sha256,
            "completed_at": failed.completed_at,
            "result": ActionResult.SUCCEEDED,
        }
    )
    forged = external_actions_module._build_signed_model(
        ActionReceipt,
        forged_values,
        EXECUTOR_PRIVATE,
        issuer="action-executor",
        role=SigningRole.EXECUTOR,
    )
    target_guard = guard_factory()
    target_claim = execution_claim(
        selected, selected_approval, issued, target_guard
    )

    with pytest.raises(ExternalActionInputError, match="expected post-state"):
        target_guard._sign_and_commit_receipt(
            selected,
            selected_approval,
            issued,
            target_claim,
            EXECUTOR_PRIVATE,
            issuer="action-executor",
            result=ActionResult.SUCCEEDED,
            observed_pre_state_sha256=selected.expected_pre_state_sha256,
            observed_post_state_sha256="f" * 64,
            provider_operation_sha256="b" * 64,
            provider_audit_receipt_sha256="c" * 64,
        )


def test_started_action_records_terminal_receipt_after_revocation(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    revoked = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        guard,
        reason_record_sha256="d" * 64,
        issued_at=ACTION_AT + timedelta(seconds=10),
        effective_at=ACTION_AT + timedelta(seconds=30),
    )
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )

    assert revoked.effective_at < completed.completed_at
    assert verify_action_receipt(
        selected,
        selected_approval,
        issued,
        selected_claim,
        completed,
        guard,
        at=completed.completed_at,
    )


def test_receipt_first_does_not_suppress_midflight_revocation(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    revoked = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        guard,
        reason_record_sha256="d" * 64,
        issued_at=selected_claim.claimed_at + timedelta(seconds=10),
        effective_at=selected_claim.claimed_at + timedelta(seconds=30),
    )

    stored_claim, stored_receipt, stored_revocations = (
        guard.authoritative_snapshot(issued)
    )
    assert stored_claim == selected_claim
    assert stored_receipt == completed
    assert stored_revocations == (revoked,)
    first = append_action_journal_entry(
        journal_id="journal-receipt-then-revocation",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    fourth = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second, third),
        event_kind=JournalEventKind.REVOCATION,
        event_payload_sha256=revoked.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at + timedelta(microseconds=1),
    )
    folded = fold_action_journal(
        selected,
        selected_approval,
        issued,
        selected_claim,
        (first, second, third, fourth),
        guard,
        revocations=(revoked,),
        receipts=(completed,),
        at=fourth.recorded_at,
    )

    assert folded.authority_state is JournalAuthorityState.REVOKED
    assert folded.outcome_state is JournalOutcomeState.SUCCEEDED
    assert folded.head_entry_sha256 == fourth.entry_sha256


def test_signed_revocation_delayed_before_persist_is_not_discarded(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    delayed = AUTHORITY._sign(
        external_actions_module.ActionRevocation,
        {
            "issuer": TRUST.controller.issuer,
            "signer_role": SigningRole.CONTROLLER,
            "scope": external_actions_module.ActionSignatureScope.CONTROLLER_GRANT_REVOCATION,
            "request_sha256": selected.request_sha256,
            "grant_payload_sha256": issued.payload_sha256,
            "external_action_policy_sha256": POLICY_SHA,
            "reason_record_sha256": "d" * 64,
            "issued_at": ACTION_AT,
            "effective_at": ACTION_AT,
        },
    )
    guard = guard_factory(at=ACTION_AT)
    selected_claim = execution_claim(
        selected, selected_approval, issued, guard
    )

    guard.register_revocation(selected, issued, delayed)

    stored_claim, _, stored_revocations = guard.authoritative_snapshot(issued)
    assert stored_claim == selected_claim
    assert stored_revocations == (delayed,)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    first = append_action_journal_entry(
        journal_id="journal-midflight-revocation",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second),
        event_kind=JournalEventKind.REVOCATION,
        event_payload_sha256=delayed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=delayed.issued_at,
    )
    fourth = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second, third),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    folded = fold_action_journal(
        selected,
        selected_approval,
        issued,
        selected_claim,
        (first, second, third, fourth),
        guard,
        revocations=(delayed,),
        receipts=(completed,),
        at=completed.completed_at,
    )

    assert folded.authority_state is JournalAuthorityState.REVOKED
    assert folded.outcome_state is JournalOutcomeState.SUCCEEDED


def test_canonical_journal_folds_one_grant_and_one_terminal_receipt(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    entries: tuple[ActionJournalEntry, ...] = ()
    first = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=entries,
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=ACTION_AT,
    )
    entries = (first,)
    second = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=entries,
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    entries = (*entries, second)
    third = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=entries,
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    report = fold_action_journal(
        selected,
        selected_approval,
        issued,
        selected_claim,
        (*entries, third),
        guard,
        receipts=(completed,),
        at=completed.completed_at,
    )

    assert report.authority_state is JournalAuthorityState.CLAIMED
    assert report.outcome_state is JournalOutcomeState.SUCCEEDED
    assert report.entry_count == 3
    assert report.receipt_payload_sha256 == completed.payload_sha256


def test_journal_fold_rejects_revocation_committed_during_evaluation(
    guard_factory, monkeypatch
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    first = append_action_journal_entry(
        journal_id="journal-concurrent-revocation",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    original = ExternalActionExecutionGuard._snapshot_is_current
    injected = False

    def change_before_final_check(self, selected_grant, *, revision, anchor_sha256):
        nonlocal injected
        if not injected:
            injected = True
            revoke_execution_grant(
                selected,
                issued,
                AUTHORITY,
                guard,
                reason_record_sha256="d" * 64,
                issued_at=ACTION_AT + timedelta(seconds=30),
                effective_at=ACTION_AT + timedelta(seconds=30),
            )
        return original(
            self,
            selected_grant,
            revision=revision,
            anchor_sha256=anchor_sha256,
        )

    monkeypatch.setattr(
        ExternalActionExecutionGuard,
        "_snapshot_is_current",
        change_before_final_check,
    )

    with pytest.raises(ExternalActionInputError, match="changed during"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            selected_claim,
            (first, second),
            guard,
            at=ACTION_AT + timedelta(minutes=1),
        )
def test_journal_cannot_omit_durable_claim_receipt_or_revocation(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)

    claim_guard = guard_factory()
    selected_claim = execution_claim(
        selected, selected_approval, issued, claim_guard
    )
    grant_entry = append_action_journal_entry(
        journal_id="journal-claim-omission",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    with pytest.raises(ExternalActionInputError, match="durable authoritative"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            None,
            (grant_entry,),
            claim_guard,
            at=selected_claim.claimed_at,
        )

    receipt_guard = guard_factory()
    receipt_claim = execution_claim(
        selected, selected_approval, issued, receipt_guard
    )
    completed = receipt(
        selected,
        selected_approval,
        issued,
        receipt_claim,
        receipt_guard,
    )
    receipt_grant_entry = append_action_journal_entry(
        journal_id="journal-receipt-omission",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    receipt_claim_entry = append_action_journal_entry(
        journal_id=receipt_grant_entry.journal_id,
        entries=(receipt_grant_entry,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=receipt_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=receipt_claim.claimed_at,
    )
    with pytest.raises(ExternalActionInputError, match="durable authoritative"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            receipt_claim,
            (receipt_grant_entry, receipt_claim_entry),
            receipt_guard,
            at=completed.completed_at,
        )

    revocation_guard = guard_factory()
    revoked = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        revocation_guard,
        reason_record_sha256="d" * 64,
        issued_at=ACTION_AT,
        effective_at=ACTION_AT,
    )
    revocation_grant_entry = append_action_journal_entry(
        journal_id="journal-revocation-omission",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    with pytest.raises(ExternalActionInputError, match="durable authoritative"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            None,
            (revocation_grant_entry,),
            revocation_guard,
            at=revoked.effective_at,
        )


def test_journal_revalidates_exact_stored_revocation_sidecar(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    revoked = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        guard,
        reason_record_sha256="d" * 64,
        issued_at=ACTION_AT,
        effective_at=ACTION_AT,
    )
    first = append_action_journal_entry(
        journal_id="journal-bad-revocation-sidecar",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.REVOCATION,
        event_payload_sha256=revoked.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=revoked.issued_at,
    )
    invalid = revoked.model_copy(update={"signature_base64url": "A" * 86})

    with pytest.raises(ExternalActionInputError, match="durable authoritative"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            None,
            (first, second),
            guard,
            revocations=(invalid,),
            at=revoked.effective_at,
        )


@pytest.mark.parametrize("action", tuple(ExternalAction))
def test_all_four_actions_complete_the_guarded_local_lifecycle(
    action, guard_factory
) -> None:
    if action is ExternalAction.ACTIVATE_PUBLIC_RELEASE:
        selected, selected_approval, issued, report = activation_grant()
    else:
        selected = request(action)
        selected_approval = approval(selected)
        issued = grant(selected, selected_approval)
        report = None
    guard = guard_factory()
    selected_claim = execution_claim(
        selected,
        selected_approval,
        issued,
        guard,
        public_report=report,
    )
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    first = append_action_journal_entry(
        journal_id=f"journal-{action.value.replace('_', '-')}",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )

    folded = fold_action_journal(
        selected,
        selected_approval,
        issued,
        selected_claim,
        (first, second, third),
        guard,
        receipts=(completed,),
        public_report=report,
        at=completed.completed_at,
    )

    assert folded.authority_state is JournalAuthorityState.CLAIMED
    assert folded.outcome_state is JournalOutcomeState.SUCCEEDED


def test_journal_rejects_bad_grant_revocation_future_and_extra_sidecar(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    first = append_action_journal_entry(
        journal_id="external-actions-adversarial",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=issued.issued_at,
    )
    second = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id=first.journal_id,
        entries=(first, second),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    entries = (first, second, third)

    invalid_grant = issued.model_copy(update={"signature_base64url": "A" * 86})
    with pytest.raises(ExternalActionInputError, match="grant authority"):
        fold_action_journal(
            selected,
            selected_approval,
            invalid_grant,
            selected_claim,
            entries,
            guard,
            receipts=(completed,),
            at=completed.completed_at,
        )

    with pytest.raises(ExternalActionInputError, match="chain or binding"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            selected_claim,
            entries,
            guard,
            receipts=(completed,),
            at=selected_claim.claimed_at - timedelta(microseconds=1),
        )

    other_guard = guard_factory()
    other_claim = execution_claim(
        selected, selected_approval, issued, other_guard
    )
    other_receipt = receipt(
        selected,
        selected_approval,
        issued,
        other_claim,
        other_guard,
        result=ActionResult.UNKNOWN,
        observed_post_state_sha256=selected.expected_pre_state_sha256,
    )
    with pytest.raises(
        ExternalActionInputError,
        match="receipts do not match|sidecars are not exact",
    ):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            selected_claim,
            entries,
            guard,
            receipts=(completed, other_receipt),
            at=completed.completed_at,
        )

    revoke_guard = guard_factory()
    valid_revocation = revoke_execution_grant(
        selected,
        issued,
        AUTHORITY,
        revoke_guard,
        reason_record_sha256="d" * 64,
        issued_at=ACTION_AT,
        effective_at=ACTION_AT,
    )
    invalid_revocation = valid_revocation.model_copy(
        update={"signature_base64url": "A" * 86}
    )
    with pytest.raises(ExternalActionInputError, match="signature is invalid"):
        guard_factory().register_revocation(selected, issued, invalid_revocation)


def test_journal_gap_reorder_duplicate_and_conflicting_receipt_fail(
    guard_factory,
) -> None:
    selected = request()
    selected_approval = approval(selected)
    issued = grant(selected, selected_approval)
    guard = guard_factory()
    selected_claim = execution_claim(selected, selected_approval, issued, guard)
    completed = receipt(
        selected, selected_approval, issued, selected_claim, guard
    )
    first = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=(),
        event_kind=JournalEventKind.GRANT,
        event_payload_sha256=issued.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=ACTION_AT,
    )
    second = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=(first,),
        event_kind=JournalEventKind.CLAIM,
        event_payload_sha256=selected_claim.claim_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=selected_claim.claimed_at,
    )
    third = append_action_journal_entry(
        journal_id="external-actions-2026",
        entries=(first, second),
        event_kind=JournalEventKind.RECEIPT,
        event_payload_sha256=completed.payload_sha256,
        request=selected,
        grant=issued,
        authority=AUTHORITY,
        recorded_at=completed.completed_at,
    )
    with pytest.raises(ExternalActionInputError, match="chain or binding"):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            selected_claim,
            (second, first, third),
            guard,
            receipts=(completed,),
            at=completed.completed_at,
        )
    with pytest.raises(
        ExternalActionInputError, match="chain or binding|terminal (receipt|event)"
    ):
        fold_action_journal(
            selected,
            selected_approval,
            issued,
            selected_claim,
            (first, second, third, third),
            guard,
            receipts=(completed,),
            at=completed.completed_at,
        )


def test_authority_is_signer_redacted_and_nonserializable() -> None:
    with pytest.raises(ExternalActionInputError):
        ExternalActionAuthority(POLICY, TRUST, Ed25519PrivateKey.generate())
    with pytest.raises(TypeError):
        pickle.dumps(AUTHORITY)
    assert "redacted" in repr(AUTHORITY)


def test_synthetic_request_fixture_is_valid_but_has_no_authority() -> None:
    selected = ExternalActionRequest.model_validate_json(
        (ROOT / "examples/external-action-request.synthetic-unapproved.json").read_text()
    )
    selected_approval = approval(
        selected,
        issued_at=selected.not_before + timedelta(minutes=1),
        expires_at=selected.not_before + timedelta(hours=2),
    )

    with pytest.raises(ExternalActionInputError, match="policy binding"):
        issue_controller_execution_grant(
            selected,
            selected_approval,
            AUTHORITY,
            at=selected.not_before + timedelta(minutes=2),
        )
