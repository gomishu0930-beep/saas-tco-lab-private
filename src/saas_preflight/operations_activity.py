"""Reconstructable P17 routine-operations activity and net-profit evidence.

The contract contains no names, free-form logs, credentials, or URLs.  It
binds a 30-day schedule to one execution receipt per occurrence, minimized
actor tokens to exact minute intervals, and resource usage to JPY unit costs.
Aggregates are always derived; callers cannot supply automation, human-time,
TCO, or net-profit totals directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from enum import Enum
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from .models import Sha256, Slug, StrictModel


_TOKYO = ZoneInfo("Asia/Tokyo")


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value


def _canonical_sha256(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {
            "hash_domain": f"saas-preflight/operations-activity/{domain}/v1",
            "payload": value,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _model_hash(domain: str, value: StrictModel, excluded: str) -> str:
    payload = value.model_dump(mode="json")
    payload.pop(excluded, None)
    return _canonical_sha256(domain, payload)


def _exact_sum(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as context:
        context.prec = 60
        return sum(values, start=Decimal(0))


class RoutineTaskMode(str, Enum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class RoutineExecutionOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RoutineTaskDefinition(StrictModel):
    task_id: Slug
    definition_sha256: Sha256
    mode: RoutineTaskMode


class ScheduledRoutineTask(StrictModel):
    occurrence_id_sha256: Sha256
    task_id: Slug
    definition_sha256: Sha256
    local_date: date
    scheduled_for: datetime

    @field_validator("scheduled_for")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "routine task schedule")

    @model_validator(mode="after")
    def bind_local_date(self) -> Self:
        if self.scheduled_for.astimezone(_TOKYO).date() != self.local_date:
            raise ValueError("routine task local date differs from schedule")
        return self


class RoutineTaskExecution(StrictModel):
    occurrence_id_sha256: Sha256
    execution_receipt_sha256: Sha256
    mode: RoutineTaskMode
    started_at: datetime
    completed_at: datetime
    outcome: RoutineExecutionOutcome
    exception_count: int = Field(ge=0, le=1_000_000)
    major_misstatement_count: int = Field(ge=0, le=1_000_000)

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "routine task execution")

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.completed_at <= self.started_at:
            raise ValueError("routine task execution must have positive duration")
        return self


class HumanActivityEvent(StrictModel):
    activity_id_sha256: Sha256
    actor_identity_token_sha256: Sha256
    role_id: Slug
    occurrence_id_sha256: Sha256
    source_receipt_sha256: Sha256
    started_at: datetime
    ended_at: datetime

    @field_validator("started_at", "ended_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "human activity")

    @model_validator(mode="after")
    def require_exact_minutes(self) -> Self:
        if self.ended_at <= self.started_at:
            raise ValueError("human activity must have positive duration")
        if any(
            (
                self.started_at.second,
                self.started_at.microsecond,
                self.ended_at.second,
                self.ended_at.microsecond,
            )
        ):
            raise ValueError("human activity boundaries must be exact minutes")
        return self


class ResourceUsageEvent(StrictModel):
    usage_id_sha256: Sha256
    resource_class: Slug
    source_receipt_sha256: Sha256
    occurred_at: datetime
    quantity: Decimal = Field(ge=0, max_digits=30, decimal_places=8)
    unit_cost_jpy: Decimal = Field(ge=0, max_digits=30, decimal_places=8)

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "resource usage")


class RoleLaborRate(StrictModel):
    role_id: Slug
    hourly_cost_jpy: Decimal = Field(ge=0, max_digits=30, decimal_places=8)


class OperationalCostPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: Slug
    objective_basis: Literal["net_operating_profit"] = "net_operating_profit"
    target_monthly_net_profit_jpy: Decimal = Field(
        default=Decimal("200000"), ge=0, max_digits=30, decimal_places=8
    )
    role_labor_rates: tuple[RoleLaborRate, ...] = Field(min_length=1, max_length=100)
    maximum_evidence_ttl_seconds: int = Field(ge=1, le=2_678_400)
    policy_sha256: Sha256

    @field_validator("role_labor_rates")
    @classmethod
    def canonicalize_rates(
        cls, values: tuple[RoleLaborRate, ...]
    ) -> tuple[RoleLaborRate, ...]:
        if len({item.role_id for item in values}) != len(values):
            raise ValueError("labor roles must be distinct")
        return tuple(sorted(values, key=lambda item: item.role_id))

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.target_monthly_net_profit_jpy != Decimal("200000"):
            raise ValueError("monthly net-profit target is fixed at JPY 200000")
        if self.policy_sha256 != hash_operational_cost_policy(self):
            raise ValueError("operational cost policy hash mismatch")
        return self


class OperationsActivityBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    batch_id: Slug
    source_operations_batch_sha256: Sha256
    source_timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    observation_started_at: datetime
    observation_ended_at: datetime
    captured_at: datetime
    expires_at: datetime
    definitions: tuple[RoutineTaskDefinition, ...] = Field(min_length=1, max_length=1_000)
    schedules: tuple[ScheduledRoutineTask, ...] = Field(default=(), max_length=1_000_000)
    executions: tuple[RoutineTaskExecution, ...] = Field(default=(), max_length=1_000_000)
    human_activities: tuple[HumanActivityEvent, ...] = Field(default=(), max_length=1_000_000)
    resource_usage: tuple[ResourceUsageEvent, ...] = Field(default=(), max_length=1_000_000)
    batch_sha256: Sha256

    @field_validator(
        "observation_started_at", "observation_ended_at", "captured_at", "expires_at"
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "operations activity timestamp")

    @field_validator("definitions")
    @classmethod
    def canonicalize_definitions(
        cls, values: tuple[RoutineTaskDefinition, ...]
    ) -> tuple[RoutineTaskDefinition, ...]:
        if len({item.task_id for item in values}) != len(values):
            raise ValueError("routine task definitions must be distinct")
        return tuple(sorted(values, key=lambda item: item.task_id))

    @field_validator("schedules")
    @classmethod
    def canonicalize_schedules(
        cls, values: tuple[ScheduledRoutineTask, ...]
    ) -> tuple[ScheduledRoutineTask, ...]:
        if len({item.occurrence_id_sha256 for item in values}) != len(values):
            raise ValueError("routine task schedules must be distinct")
        return tuple(sorted(values, key=lambda item: item.occurrence_id_sha256))

    @field_validator("executions")
    @classmethod
    def canonicalize_executions(
        cls, values: tuple[RoutineTaskExecution, ...]
    ) -> tuple[RoutineTaskExecution, ...]:
        if len({item.occurrence_id_sha256 for item in values}) != len(values):
            raise ValueError("routine task executions must be distinct")
        if len({item.execution_receipt_sha256 for item in values}) != len(values):
            raise ValueError("execution receipts must be distinct")
        return tuple(sorted(values, key=lambda item: item.occurrence_id_sha256))

    @field_validator("human_activities")
    @classmethod
    def canonicalize_activities(
        cls, values: tuple[HumanActivityEvent, ...]
    ) -> tuple[HumanActivityEvent, ...]:
        if len({item.activity_id_sha256 for item in values}) != len(values):
            raise ValueError("human activity IDs must be distinct")
        if len({item.source_receipt_sha256 for item in values}) != len(values):
            raise ValueError("human activity receipts must be distinct")
        return tuple(sorted(values, key=lambda item: item.activity_id_sha256))

    @field_validator("resource_usage")
    @classmethod
    def canonicalize_usage(
        cls, values: tuple[ResourceUsageEvent, ...]
    ) -> tuple[ResourceUsageEvent, ...]:
        if len({item.usage_id_sha256 for item in values}) != len(values):
            raise ValueError("resource usage IDs must be distinct")
        if len({item.source_receipt_sha256 for item in values}) != len(values):
            raise ValueError("resource usage receipts must be distinct")
        return tuple(sorted(values, key=lambda item: item.usage_id_sha256))

    @model_validator(mode="after")
    def reconcile_activity(self) -> Self:
        if not (
            self.observation_started_at
            < self.observation_ended_at
            <= self.captured_at
            < self.expires_at
        ):
            raise ValueError("operations activity window is invalid")
        start_local = self.observation_started_at.astimezone(_TOKYO)
        end_local = self.observation_ended_at.astimezone(_TOKYO)
        if any(
            (
                start_local.hour,
                start_local.minute,
                start_local.second,
                start_local.microsecond,
                end_local.hour,
                end_local.minute,
                end_local.second,
                end_local.microsecond,
            )
        ) or (end_local.date() - start_local.date()).days != 30:
            raise ValueError("operations activity must cover exactly 30 Tokyo days")
        definitions = {item.task_id: item for item in self.definitions}
        schedule = {item.occurrence_id_sha256: item for item in self.schedules}
        execution = {item.occurrence_id_sha256: item for item in self.executions}
        if schedule.keys() != execution.keys():
            raise ValueError("every scheduled task must have exactly one execution")
        for occurrence, planned in schedule.items():
            definition = definitions.get(planned.task_id)
            actual = execution[occurrence]
            if (
                definition is None
                or planned.definition_sha256 != definition.definition_sha256
                or actual.mode is not definition.mode
                or not self.observation_started_at
                <= planned.scheduled_for
                < self.observation_ended_at
                or actual.started_at < planned.scheduled_for
                or actual.completed_at > self.captured_at
            ):
                raise ValueError("routine task schedule/execution binding is invalid")
        actors: dict[str, tuple[str, datetime]] = {}
        activities_by_occurrence: set[str] = set()
        for item in sorted(
            self.human_activities,
            key=lambda value: (value.actor_identity_token_sha256, value.started_at),
        ):
            actual = execution.get(item.occurrence_id_sha256)
            prior = actors.get(item.actor_identity_token_sha256)
            if (
                actual is None
                or item.started_at < actual.started_at
                or item.ended_at > actual.completed_at
                or prior is not None
                and (prior[0] != item.role_id or item.started_at < prior[1])
            ):
                raise ValueError("human activity does not reconcile to execution")
            actors[item.actor_identity_token_sha256] = (item.role_id, item.ended_at)
            activities_by_occurrence.add(item.occurrence_id_sha256)
        if any(
            definition.mode is RoutineTaskMode.MANUAL
            and occurrence not in activities_by_occurrence
            for occurrence, planned in schedule.items()
            for definition in (definitions[planned.task_id],)
        ):
            raise ValueError("manual routine task is missing human activity")
        if any(
            not self.observation_started_at <= item.occurred_at < self.observation_ended_at
            for item in self.resource_usage
        ):
            raise ValueError("resource usage is outside the observation window")
        if self.batch_sha256 != hash_operations_activity_batch(self):
            raise ValueError("operations activity batch hash mismatch")
        return self


class DailyDerivedOperations(StrictModel):
    local_date: date
    human_minutes: int = Field(ge=0)
    routine_tasks_total: int = Field(ge=0)
    routine_tasks_automated: int = Field(ge=0)
    job_runs_total: int = Field(ge=0)
    job_runs_succeeded: int = Field(ge=0)
    exceptions_total: int = Field(ge=0)
    major_misstatements: int = Field(ge=0)


class TaskActivityCoverage(StrictModel):
    scheduled_occurrences: int = Field(ge=0)
    executed_occurrences: int = Field(ge=0)
    execution_receipts: int = Field(ge=0)
    manual_occurrences: int = Field(ge=0)
    manual_occurrences_with_activity: int = Field(ge=0)
    human_activity_receipts: int = Field(ge=0)
    resource_usage_receipts: int = Field(ge=0)
    complete: bool


class MonthlyOperatingTco(StrictModel):
    objective_basis: Literal["net_operating_profit"] = "net_operating_profit"
    target_monthly_net_profit_jpy: Decimal = Field(ge=0)
    gross_settled_revenue_jpy: Decimal = Field(ge=0)
    human_minutes: int = Field(ge=0)
    labor_cost_jpy: Decimal = Field(ge=0)
    resource_cost_jpy: Decimal = Field(ge=0)
    total_operating_tco_jpy: Decimal = Field(ge=0)
    net_operating_profit_jpy: Decimal
    target_achieved: bool

    @model_validator(mode="after")
    def reconcile_tco(self) -> Self:
        if self.total_operating_tco_jpy != _exact_sum(
            (self.labor_cost_jpy, self.resource_cost_jpy)
        ) or self.net_operating_profit_jpy != (
            self.gross_settled_revenue_jpy - self.total_operating_tco_jpy
        ):
            raise ValueError("monthly operating TCO does not reconcile")
        if self.target_achieved != (
            self.net_operating_profit_jpy >= self.target_monthly_net_profit_jpy
        ):
            raise ValueError("net-profit target result does not reconcile")
        return self


class DerivedOperationsActivitySummary(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_batch_sha256: Sha256
    source_operations_batch_sha256: Sha256
    policy_sha256: Sha256
    observation_started_at: datetime
    observation_ended_at: datetime
    captured_at: datetime
    expires_at: datetime
    daily: tuple[DailyDerivedOperations, ...] = Field(min_length=30, max_length=30)
    coverage: TaskActivityCoverage
    operating_tco: MonthlyOperatingTco
    summary_sha256: Sha256

    @field_validator(
        "observation_started_at", "observation_ended_at", "captured_at", "expires_at"
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "derived operations timestamp")

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        expected_dates = tuple(
            self.observation_started_at.astimezone(_TOKYO).date()
            + timedelta(days=index)
            for index in range(30)
        )
        if tuple(item.local_date for item in self.daily) != expected_dates:
            raise ValueError("derived operations days are not contiguous")
        if not self.coverage.complete:
            raise ValueError("derived operations coverage must be complete")
        if self.summary_sha256 != hash_derived_operations_activity(self):
            raise ValueError("derived operations summary hash mismatch")
        return self


def hash_operational_cost_policy(value: OperationalCostPolicy) -> str:
    return _model_hash("cost-policy", value, "policy_sha256")


def hash_operations_activity_batch(value: OperationsActivityBatch) -> str:
    return _model_hash("activity-batch", value, "batch_sha256")


def hash_derived_operations_activity(value: DerivedOperationsActivitySummary) -> str:
    return _model_hash("derived-summary", value, "summary_sha256")


def derive_operations_activity(
    batch: OperationsActivityBatch,
    policy: OperationalCostPolicy,
    *,
    gross_settled_revenue_jpy: Decimal,
    at: datetime,
) -> DerivedOperationsActivitySummary:
    """Derive 30-day operating metrics from complete task/activity receipts."""

    _utc(at, "operations derivation time")
    selected = OperationsActivityBatch.model_validate(batch.model_dump())
    selected_policy = OperationalCostPolicy.model_validate(policy.model_dump())
    if not selected.captured_at <= at < selected.expires_at:
        raise ValueError("operations activity batch is not current")
    if selected.expires_at - selected.captured_at > timedelta(
        seconds=selected_policy.maximum_evidence_ttl_seconds
    ):
        raise ValueError("operations activity batch TTL exceeds policy")
    rates = {
        item.role_id: item.hourly_cost_jpy
        for item in selected_policy.role_labor_rates
    }
    if any(item.role_id not in rates for item in selected.human_activities):
        raise ValueError("human activity role has no labor rate")
    definitions = {item.task_id: item for item in selected.definitions}
    schedules = {
        item.occurrence_id_sha256: item for item in selected.schedules
    }
    executions = {
        item.occurrence_id_sha256: item for item in selected.executions
    }
    human_by_day: dict[date, int] = {}
    minutes_by_role: dict[str, int] = {}
    for item in selected.human_activities:
        minutes = int((item.ended_at - item.started_at).total_seconds() // 60)
        local_date = item.started_at.astimezone(_TOKYO).date()
        if item.ended_at.astimezone(_TOKYO).date() != local_date:
            raise ValueError("human activity cannot cross a Tokyo calendar day")
        human_by_day[local_date] = human_by_day.get(local_date, 0) + minutes
        minutes_by_role[item.role_id] = (
            minutes_by_role.get(item.role_id, 0) + minutes
        )
    daily: list[DailyDerivedOperations] = []
    start_date = selected.observation_started_at.astimezone(_TOKYO).date()
    for offset in range(30):
        local_date = start_date + timedelta(days=offset)
        occurrences = tuple(
            item for item in selected.schedules if item.local_date == local_date
        )
        results = tuple(executions[item.occurrence_id_sha256] for item in occurrences)
        daily.append(
            DailyDerivedOperations(
                local_date=local_date,
                human_minutes=human_by_day.get(local_date, 0),
                routine_tasks_total=len(occurrences),
                routine_tasks_automated=sum(
                    definitions[item.task_id].mode is RoutineTaskMode.AUTOMATED
                    for item in occurrences
                ),
                job_runs_total=len(results),
                job_runs_succeeded=sum(
                    item.outcome is RoutineExecutionOutcome.SUCCEEDED
                    for item in results
                ),
                exceptions_total=sum(item.exception_count for item in results),
                major_misstatements=sum(
                    item.major_misstatement_count for item in results
                ),
            )
        )
    manual = {
        occurrence
        for occurrence, planned in schedules.items()
        if definitions[planned.task_id].mode is RoutineTaskMode.MANUAL
    }
    manual_with_activity = {
        item.occurrence_id_sha256 for item in selected.human_activities
    }.intersection(manual)
    coverage = TaskActivityCoverage(
        scheduled_occurrences=len(schedules),
        executed_occurrences=len(executions),
        execution_receipts=len(
            {item.execution_receipt_sha256 for item in selected.executions}
        ),
        manual_occurrences=len(manual),
        manual_occurrences_with_activity=len(manual_with_activity),
        human_activity_receipts=len(
            {item.source_receipt_sha256 for item in selected.human_activities}
        ),
        resource_usage_receipts=len(
            {item.source_receipt_sha256 for item in selected.resource_usage}
        ),
        complete=(
            len(schedules) == len(executions)
            == len({item.execution_receipt_sha256 for item in selected.executions})
            and manual == manual_with_activity
        ),
    )
    labor_cost = _exact_sum(
        tuple(
            rates[role] * Decimal(minutes) / Decimal(60)
            for role, minutes in sorted(minutes_by_role.items())
        )
    )
    resource_cost = _exact_sum(
        tuple(item.quantity * item.unit_cost_jpy for item in selected.resource_usage)
    )
    total_tco = _exact_sum((labor_cost, resource_cost))
    net_profit = gross_settled_revenue_jpy - total_tco
    tco = MonthlyOperatingTco(
        target_monthly_net_profit_jpy=(
            selected_policy.target_monthly_net_profit_jpy
        ),
        gross_settled_revenue_jpy=gross_settled_revenue_jpy,
        human_minutes=sum(item.human_minutes for item in daily),
        labor_cost_jpy=labor_cost,
        resource_cost_jpy=resource_cost,
        total_operating_tco_jpy=total_tco,
        net_operating_profit_jpy=net_profit,
        target_achieved=(
            net_profit >= selected_policy.target_monthly_net_profit_jpy
        ),
    )
    values = {
        "source_batch_sha256": selected.batch_sha256,
        "source_operations_batch_sha256": selected.source_operations_batch_sha256,
        "policy_sha256": selected_policy.policy_sha256,
        "observation_started_at": selected.observation_started_at,
        "observation_ended_at": selected.observation_ended_at,
        "captured_at": selected.captured_at,
        "expires_at": selected.expires_at,
        "daily": tuple(daily),
        "coverage": coverage,
        "operating_tco": tco,
    }
    provisional = DerivedOperationsActivitySummary.model_construct(
        **values, schema_version="1.0", summary_sha256="0" * 64
    )
    return DerivedOperationsActivitySummary(
        **values,
        summary_sha256=hash_derived_operations_activity(provisional),
    )
