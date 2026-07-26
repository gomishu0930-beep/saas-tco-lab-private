from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from saas_preflight.operations import (
    BudgetError,
    BudgetExhaustedError,
    BudgetFrozenError,
    BudgetStatus,
    ClaimConflictError,
    ExceptionQueue,
    ExceptionStateError,
    ExceptionStatus,
    ExpiredClaimError,
    MonthlyHumanBudget,
    OperatingRole,
    OperationalException,
    RoleBudgetExceededError,
    RunKey,
    RunLedger,
    RunStateError,
    Severity,
    TimeEntry,
    WorkClass,
    acknowledge_exception,
    claim_run,
    complete_run,
    enqueue_exception,
    fail_run,
    record_time,
    resolve_exception,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
H1 = "1" * 64
H2 = "2" * 64


def run_key() -> RunKey:
    return RunKey(job_name="daily-release-check", scheduled_for=NOW, input_sha256=H1)


def time_entry(
    reference: str,
    role: OperatingRole,
    minutes: int,
    *,
    work_class: WorkClass = WorkClass.ESSENTIAL_OPERATIONS,
) -> TimeEntry:
    return TimeEntry(
        reference=reference,
        role=role,
        work_class=work_class,
        minutes=minutes,
        occurred_at=NOW,
    )


def test_run_key_is_deterministic_strict_utc_and_frozen() -> None:
    first = run_key()
    assert first.value == run_key().value
    with pytest.raises(ValueError, match="UTC"):
        RunKey(
            job_name="daily-release-check",
            scheduled_for=NOW.replace(tzinfo=None),
            input_sha256=H1,
        )
    with pytest.raises(FrozenInstanceError):
        first.job_name = "changed"  # type: ignore[misc]


def test_claim_is_idempotent_for_same_owner_and_rejects_another_owner() -> None:
    key = run_key()
    acquired = claim_run(
        RunLedger(), key, owner="integration", at=NOW, lease_minutes=30
    )
    retry = claim_run(
        acquired.ledger,
        key,
        owner="integration",
        at=NOW + timedelta(minutes=1),
        lease_minutes=60,
    )

    assert acquired.acquired is True
    assert retry.acquired is False
    assert retry.ledger is acquired.ledger
    assert retry.claim.lease_expires_at == NOW + timedelta(minutes=30)
    with pytest.raises(ClaimConflictError, match="another operator"):
        claim_run(
            acquired.ledger,
            key,
            owner="human",
            at=NOW + timedelta(minutes=1),
            lease_minutes=30,
        )


def test_run_cannot_be_claimed_before_schedule() -> None:
    with pytest.raises(ValueError, match="before its scheduled"):
        claim_run(
            RunLedger(),
            run_key(),
            owner="integration",
            at=NOW - timedelta(seconds=1),
            lease_minutes=30,
        )


def test_completion_is_idempotent_and_conflicting_output_is_rejected() -> None:
    key = run_key()
    ledger = claim_run(
        RunLedger(), key, owner="integration", at=NOW, lease_minutes=30
    ).ledger
    completed = complete_run(ledger, key, output_sha256=H2, at=NOW + timedelta(minutes=1))

    assert complete_run(
        completed, key, output_sha256=H2, at=NOW + timedelta(minutes=2)
    ) is completed
    with pytest.raises(ClaimConflictError, match="different output"):
        complete_run(completed, key, output_sha256=H1, at=NOW + timedelta(minutes=2))
    with pytest.raises(RunStateError, match="successful"):
        fail_run(
            completed,
            key,
            failure_code="late-failure",
            at=NOW + timedelta(minutes=2),
        )


def test_expired_claim_cannot_complete() -> None:
    key = run_key()
    ledger = claim_run(
        RunLedger(), key, owner="integration", at=NOW, lease_minutes=1
    ).ledger

    with pytest.raises(ExpiredClaimError):
        complete_run(ledger, key, output_sha256=H2, at=NOW + timedelta(minutes=1))


def test_failure_is_idempotent_but_cannot_change_code() -> None:
    key = run_key()
    ledger = claim_run(
        RunLedger(), key, owner="integration", at=NOW, lease_minutes=30
    ).ledger
    failed = fail_run(
        ledger, key, failure_code="source-expired", at=NOW + timedelta(minutes=1)
    )

    assert fail_run(
        failed, key, failure_code="source-expired", at=NOW + timedelta(minutes=2)
    ) is failed
    with pytest.raises(ClaimConflictError, match="different failure"):
        fail_run(failed, key, failure_code="other-fault", at=NOW + timedelta(minutes=2))


def test_exception_queue_deduplicates_and_requires_ack_before_resolution() -> None:
    item = OperationalException(
        exception_key="pricing-expired-vendor-a",
        severity=Severity.SEV1,
        category="pricing-expired",
        resource_id="vendor-a",
        summary="Pricing evidence expired; release remains hidden.",
        detected_at=NOW,
    )
    queue = enqueue_exception(ExceptionQueue(), item)
    duplicate = OperationalException(
        exception_key=item.exception_key,
        severity=item.severity,
        category=item.category,
        resource_id=item.resource_id,
        summary=item.summary,
        detected_at=NOW + timedelta(minutes=1),
    )
    assert enqueue_exception(queue, duplicate) is queue
    with pytest.raises(ExceptionStateError, match="acknowledged"):
        resolve_exception(
            queue,
            item.exception_key,
            resolution_sha256=H2,
            at=NOW + timedelta(minutes=2),
        )

    acknowledged = acknowledge_exception(
        queue,
        item.exception_key,
        owner="integration",
        at=NOW + timedelta(minutes=1),
    )
    resolved = resolve_exception(
        acknowledged,
        item.exception_key,
        resolution_sha256=H2,
        at=NOW + timedelta(minutes=2),
    )
    assert resolved.get(item.exception_key).status is ExceptionStatus.RESOLVED
    assert resolve_exception(
        resolved,
        item.exception_key,
        resolution_sha256=H2,
        at=NOW + timedelta(minutes=3),
    ) is resolved


def test_exception_key_cannot_be_reused_for_different_fault() -> None:
    first = OperationalException(
        exception_key="fault-1",
        severity=Severity.SEV2,
        category="parser-failure",
        resource_id="vendor-a",
        summary="Parser failed without storing source content.",
        detected_at=NOW,
    )
    different = OperationalException(
        exception_key="fault-1",
        severity=Severity.SEV1,
        category="rights-expired",
        resource_id="vendor-a",
        summary="Rights expired.",
        detected_at=NOW,
    )
    with pytest.raises(ExceptionStateError, match="reused"):
        enqueue_exception(enqueue_exception(ExceptionQueue(), first), different)


def test_budget_freezes_at_576_and_exhausts_at_720() -> None:
    budget = MonthlyHumanBudget(month="2026-07")
    for entry in (
        time_entry("evidence-180", OperatingRole.EVIDENCE, 180),
        time_entry("contract-90", OperatingRole.CONTRACT, 90),
        time_entry("tco-120", OperatingRole.TCO, 120),
        time_entry("integration-186", OperatingRole.INTEGRATION, 186),
    ):
        budget = record_time(budget, entry)

    assert budget.used_minutes == 576
    assert budget.status is BudgetStatus.FROZEN
    with pytest.raises(BudgetFrozenError):
        record_time(
            budget,
            time_entry(
                "new-source",
                OperatingRole.HUMAN,
                1,
                work_class=WorkClass.NEW_SOURCE,
            ),
        )

    budget = record_time(
        budget, time_entry("integration-24", OperatingRole.INTEGRATION, 24)
    )
    budget = record_time(budget, time_entry("human-120", OperatingRole.HUMAN, 120))
    assert budget.used_minutes == 720
    assert budget.remaining_minutes == 0
    assert budget.status is BudgetStatus.EXHAUSTED
    with pytest.raises(BudgetExhaustedError):
        record_time(
            budget,
            time_entry("normal-after-cap", OperatingRole.EVIDENCE, 1),
        )

    emergency = time_entry(
        "sev0-stop",
        OperatingRole.HUMAN,
        5,
        work_class=WorkClass.SEV0_SAFETY_STOP,
    )
    after_emergency = record_time(budget, emergency)
    assert after_emergency.used_minutes == 725
    assert record_time(after_emergency, emergency) is after_emergency


def test_new_source_cannot_cross_freeze_boundary_from_below() -> None:
    budget = MonthlyHumanBudget(
        month="2026-07",
        entries=(
            time_entry("evidence-180", OperatingRole.EVIDENCE, 180),
            time_entry("contract-90", OperatingRole.CONTRACT, 90),
            time_entry("tco-120", OperatingRole.TCO, 120),
            time_entry("integration-185", OperatingRole.INTEGRATION, 185),
        ),
    )
    assert budget.used_minutes == 575
    with pytest.raises(BudgetFrozenError, match="cross"):
        record_time(
            budget,
            time_entry(
                "new-source-crossing",
                OperatingRole.INTEGRATION,
                2,
                work_class=WorkClass.NEW_SOURCE,
            ),
        )


def test_budget_rejects_role_overage_conflicting_duplicate_and_wrong_month() -> None:
    budget = MonthlyHumanBudget(month="2026-07")
    with pytest.raises(RoleBudgetExceededError):
        record_time(
            budget,
            time_entry("evidence-over", OperatingRole.EVIDENCE, 181),
        )

    first = time_entry("same-reference", OperatingRole.CONTRACT, 10)
    budget = record_time(budget, first)
    assert record_time(budget, first) is budget
    with pytest.raises(BudgetError, match="reference was reused"):
        record_time(
            budget,
            time_entry("same-reference", OperatingRole.CONTRACT, 11),
        )

    august = TimeEntry(
        reference="august-work",
        role=OperatingRole.CONTRACT,
        work_class=WorkClass.ESSENTIAL_OPERATIONS,
        minutes=1,
        occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(BudgetError, match="outside"):
        record_time(budget, august)
