from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from saas_preflight.cli import run as run_cli
from saas_preflight.operations_activity import (
    DerivedOperationsActivitySummary,
    HumanActivityEvent,
    OperationalCostPolicy,
    OperationsActivityBatch,
    ResourceUsageEvent,
    RoleLaborRate,
    RoutineExecutionOutcome,
    RoutineTaskDefinition,
    RoutineTaskExecution,
    RoutineTaskMode,
    ScheduledRoutineTask,
    derive_operations_activity,
    hash_operational_cost_policy,
    hash_operations_activity_batch,
)


START = datetime(2026, 5, 31, 15, 0, tzinfo=timezone.utc)
END = START + timedelta(days=30)
AT = END + timedelta(hours=1)


def _digest(index: int) -> str:
    return f"{index:064x}"


def _policy(*, role_id: str = "operator") -> OperationalCostPolicy:
    values = {
        "policy_id": "p17-operating-cost",
        "role_labor_rates": (
            RoleLaborRate(role_id=role_id, hourly_cost_jpy=Decimal("5000")),
        ),
        "maximum_evidence_ttl_seconds": 172_800,
    }
    provisional = OperationalCostPolicy.model_construct(
        **values,
        schema_version="1.0",
        objective_basis="net_operating_profit",
        target_monthly_net_profit_jpy=Decimal("200000"),
        policy_sha256="0" * 64,
    )
    return OperationalCostPolicy(
        **values,
        policy_sha256=hash_operational_cost_policy(provisional),
    )


def _batch(**updates) -> OperationsActivityBatch:
    definitions = (
        RoutineTaskDefinition(
            task_id="automated-refresh",
            definition_sha256=_digest(1),
            mode=RoutineTaskMode.AUTOMATED,
        ),
        RoutineTaskDefinition(
            task_id="manual-review",
            definition_sha256=_digest(2),
            mode=RoutineTaskMode.MANUAL,
        ),
    )
    schedules = []
    executions = []
    activities = []
    usage = []
    for day in range(30):
        for task_index, definition in enumerate(definitions):
            occurrence = _digest(1000 + day * 2 + task_index)
            scheduled = START + timedelta(days=day, hours=1 + task_index)
            schedules.append(
                ScheduledRoutineTask(
                    occurrence_id_sha256=occurrence,
                    task_id=definition.task_id,
                    definition_sha256=definition.definition_sha256,
                    local_date=scheduled.astimezone(ZoneInfo("Asia/Tokyo")).date(),
                    scheduled_for=scheduled,
                )
            )
            executions.append(
                RoutineTaskExecution(
                    occurrence_id_sha256=occurrence,
                    execution_receipt_sha256=_digest(2000 + day * 2 + task_index),
                    mode=definition.mode,
                    started_at=scheduled,
                    completed_at=scheduled + timedelta(minutes=20),
                    outcome=RoutineExecutionOutcome.SUCCEEDED,
                    exception_count=0,
                    major_misstatement_count=0,
                )
            )
            if definition.mode is RoutineTaskMode.MANUAL:
                activities.append(
                    HumanActivityEvent(
                        activity_id_sha256=_digest(3000 + day),
                        actor_identity_token_sha256=_digest(4000),
                        role_id="operator",
                        occurrence_id_sha256=occurrence,
                        source_receipt_sha256=_digest(5000 + day),
                        started_at=scheduled + timedelta(minutes=2),
                        ended_at=scheduled + timedelta(minutes=12),
                    )
                )
        usage.append(
            ResourceUsageEvent(
                usage_id_sha256=_digest(6000 + day),
                resource_class="compute",
                source_receipt_sha256=_digest(7000 + day),
                occurred_at=START + timedelta(days=day, hours=6),
                quantity=Decimal("1"),
                unit_cost_jpy=Decimal("100"),
            )
        )
    values = {
        "batch_id": "p17-operations-activity",
        "source_operations_batch_sha256": _digest(8),
        "observation_started_at": START,
        "observation_ended_at": END,
        "captured_at": END,
        "expires_at": END + timedelta(days=1),
        "definitions": definitions,
        "schedules": tuple(schedules),
        "executions": tuple(executions),
        "human_activities": tuple(activities),
        "resource_usage": tuple(usage),
    }
    values.update(updates)
    provisional = OperationsActivityBatch.model_construct(
        **values,
        schema_version="1.0",
        source_timezone="Asia/Tokyo",
        batch_sha256="0" * 64,
    )
    return OperationsActivityBatch(
        **values,
        batch_sha256=hash_operations_activity_batch(provisional),
    )


def test_activity_derives_reconstructable_automation_tco_and_net_profit() -> None:
    summary = derive_operations_activity(
        _batch(),
        _policy(),
        gross_settled_revenue_jpy=Decimal("230000"),
        at=AT,
    )
    assert len(summary.daily) == 30
    assert sum(item.routine_tasks_total for item in summary.daily) == 60
    assert sum(item.routine_tasks_automated for item in summary.daily) == 30
    assert sum(item.human_minutes for item in summary.daily) == 300
    assert summary.coverage.complete is True
    assert summary.operating_tco.labor_cost_jpy == Decimal("25000")
    assert summary.operating_tco.resource_cost_jpy == Decimal("3000")
    assert summary.operating_tco.total_operating_tco_jpy == Decimal("28000")
    assert summary.operating_tco.net_operating_profit_jpy == Decimal("202000")
    assert summary.operating_tco.target_achieved is True


def test_activity_rejects_missing_or_extra_execution() -> None:
    batch = _batch()
    with pytest.raises(ValidationError, match="every scheduled task"):
        OperationsActivityBatch.model_validate(
            {**batch.model_dump(), "executions": batch.executions[:-1]}
        )


def test_activity_rejects_execution_mode_substitution() -> None:
    batch = _batch()
    changed = batch.executions[0].model_copy(
        update={"mode": RoutineTaskMode.MANUAL}
    )
    with pytest.raises(ValidationError, match="schedule/execution"):
        OperationsActivityBatch.model_validate(
            {**batch.model_dump(), "executions": (changed, *batch.executions[1:])}
        )


def test_activity_rejects_manual_claim_without_human_receipt() -> None:
    batch = _batch()
    with pytest.raises(ValidationError, match="missing human activity"):
        OperationsActivityBatch.model_validate(
            {**batch.model_dump(), "human_activities": batch.human_activities[1:]}
        )


def test_activity_rejects_overlapping_actor_time() -> None:
    batch = _batch()
    original = batch.human_activities[0]
    overlap = original.model_copy(
        update={
            "activity_id_sha256": _digest(9000),
            "source_receipt_sha256": _digest(9001),
        }
    )
    with pytest.raises(ValidationError, match="does not reconcile"):
        OperationsActivityBatch.model_validate(
            {
                **batch.model_dump(),
                "human_activities": (*batch.human_activities, overlap),
            }
        )


def test_derivation_rejects_unpriced_role_and_expired_batch() -> None:
    batch = _batch()
    with pytest.raises(ValueError, match="no labor rate"):
        derive_operations_activity(
            batch,
            _policy(role_id="reviewer"),
            gross_settled_revenue_jpy=Decimal("230000"),
            at=AT,
        )
    with pytest.raises(ValueError, match="not current"):
        derive_operations_activity(
            batch,
            _policy(),
            gross_settled_revenue_jpy=Decimal("230000"),
            at=batch.expires_at,
        )


def test_net_profit_goal_does_not_pass_on_gross_revenue_alone() -> None:
    summary = derive_operations_activity(
        _batch(),
        _policy(),
        gross_settled_revenue_jpy=Decimal("220000"),
        at=AT,
    )
    assert summary.operating_tco.gross_settled_revenue_jpy >= Decimal("200000")
    assert summary.operating_tco.net_operating_profit_jpy == Decimal("192000")
    assert summary.operating_tco.target_achieved is False


def test_operations_activity_cli_writes_one_credential_free_result(
    tmp_path, capsys
) -> None:
    batch_path = tmp_path / "batch.json"
    policy_path = tmp_path / "policy.json"
    output = tmp_path / "summary.json"
    batch_path.write_text(_batch().model_dump_json(indent=2), encoding="utf-8")
    policy_path.write_text(_policy().model_dump_json(indent=2), encoding="utf-8")
    result = run_cli(
        (
            "derive-operations-activity",
            str(batch_path),
            "--cost-policy",
            str(policy_path),
            "--gross-settled-revenue-jpy",
            "230000",
            "--at",
            AT.isoformat(),
            "--output",
            str(output),
        )
    )
    assert result == 0
    assert '"authority": "none"' in capsys.readouterr().out
    summary = DerivedOperationsActivitySummary.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert summary.operating_tco.net_operating_profit_jpy == Decimal("202000")
