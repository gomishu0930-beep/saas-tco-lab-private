"""Immutable local operations state for idempotency, exceptions, and budgets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$")
_MONTH_RE = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")

MONTHLY_FREEZE_MINUTES = 576
MONTHLY_LIMIT_MINUTES = 720


class OperationsError(ValueError):
    """Base class for rejected local operations transitions."""


class ClaimConflictError(OperationsError):
    pass


class ExpiredClaimError(OperationsError):
    pass


class RunStateError(OperationsError):
    pass


class ExceptionStateError(OperationsError):
    pass


class BudgetError(OperationsError):
    pass


class BudgetFrozenError(BudgetError):
    pass


class BudgetExhaustedError(BudgetError):
    pass


class RoleBudgetExceededError(BudgetError):
    pass


class RunStatus(str, Enum):
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Severity(str, Enum):
    SEV0 = "sev0"
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"


class ExceptionStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class OperatingRole(str, Enum):
    EVIDENCE = "evidence"
    CONTRACT = "contract"
    TCO = "tco"
    INTEGRATION = "integration"
    HUMAN = "human"


ROLE_LIMIT_MINUTES = {
    OperatingRole.EVIDENCE: 180,
    OperatingRole.CONTRACT: 90,
    OperatingRole.TCO: 120,
    OperatingRole.INTEGRATION: 210,
    OperatingRole.HUMAN: 120,
}


class WorkClass(str, Enum):
    ESSENTIAL_OPERATIONS = "essential_operations"
    NEW_SOURCE = "new_source"
    NONCRITICAL_IMPROVEMENT = "noncritical_improvement"
    RELEASE_GATE = "release_gate"
    SEV0_SAFETY_STOP = "sev0_safety_stop"
    STOP_DECISION = "stop_decision"


class BudgetStatus(str, Enum):
    NORMAL = "normal"
    FROZEN = "frozen"
    EXHAUSTED = "exhausted"


_EMERGENCY_WORK = frozenset({WorkClass.SEV0_SAFETY_STOP, WorkClass.STOP_DECISION})
_FROZEN_WORK = frozenset({WorkClass.NEW_SOURCE, WorkClass.NONCRITICAL_IMPROVEMENT})


def _require_string(value: object, field_name: str, *, max_length: int = 200) -> str:
    if type(value) is not str or not value or len(value) > max_length:
        raise TypeError(f"{field_name} must be a non-empty string up to {max_length} characters")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    text = _require_string(value, field_name, max_length=120)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a lowercase stable identifier")
    return text


def _require_sha256(value: object, field_name: str) -> str:
    text = _require_string(value, field_name, max_length=64)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _require_utc(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RunKey:
    job_name: str
    scheduled_for: datetime
    input_sha256: str
    value: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.job_name, "job_name")
        _require_utc(self.scheduled_for, "scheduled_for")
        _require_sha256(self.input_sha256, "input_sha256")
        object.__setattr__(
            self,
            "value",
            _canonical_sha256(
                {
                    "job_name": self.job_name,
                    "scheduled_for": _utc_text(self.scheduled_for),
                    "input_sha256": self.input_sha256,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class RunClaim:
    run_key: RunKey
    owner: str
    claimed_at: datetime
    lease_expires_at: datetime
    status: RunStatus = RunStatus.CLAIMED
    finished_at: datetime | None = None
    output_sha256: str | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if type(self.run_key) is not RunKey:
            raise TypeError("run_key must be RunKey")
        _require_identifier(self.owner, "owner")
        _require_utc(self.claimed_at, "claimed_at")
        _require_utc(self.lease_expires_at, "lease_expires_at")
        if self.lease_expires_at <= self.claimed_at:
            raise ValueError("lease_expires_at must be later than claimed_at")
        if type(self.status) is not RunStatus:
            raise TypeError("status must be RunStatus")
        if self.status is RunStatus.CLAIMED:
            if any(
                value is not None
                for value in (self.finished_at, self.output_sha256, self.failure_code)
            ):
                raise ValueError("active claim cannot contain completion data")
        elif self.status is RunStatus.SUCCEEDED:
            _require_utc(self.finished_at, "finished_at")
            _require_sha256(self.output_sha256, "output_sha256")
            if self.failure_code is not None:
                raise ValueError("successful claim cannot have a failure code")
        else:
            _require_utc(self.finished_at, "finished_at")
            _require_identifier(self.failure_code, "failure_code")
            if self.output_sha256 is not None:
                raise ValueError("failed claim cannot have an output digest")
        if self.finished_at is not None and self.finished_at < self.claimed_at:
            raise ValueError("finished_at cannot be before claimed_at")
        if (
            self.status is RunStatus.SUCCEEDED
            and self.finished_at is not None
            and self.finished_at >= self.lease_expires_at
        ):
            raise ValueError("successful run must finish before lease expiry")


@dataclass(frozen=True, slots=True)
class RunLedger:
    claims: tuple[RunClaim, ...] = ()

    def __post_init__(self) -> None:
        if type(self.claims) is not tuple:
            raise TypeError("claims must be a tuple")
        if any(type(claim) is not RunClaim for claim in self.claims):
            raise TypeError("claims must contain RunClaim values")
        values = [claim.run_key.value for claim in self.claims]
        if len(values) != len(set(values)):
            raise ValueError("ledger contains duplicate run keys")

    def get(self, run_key: RunKey) -> RunClaim:
        if type(run_key) is not RunKey:
            raise TypeError("run_key must be RunKey")
        for claim in self.claims:
            if claim.run_key.value == run_key.value:
                if claim.run_key != run_key:
                    raise ClaimConflictError("run-key digest collision")
                return claim
        raise KeyError(f"unknown run key: {run_key.value}")


@dataclass(frozen=True, slots=True)
class ClaimResult:
    ledger: RunLedger
    claim: RunClaim
    acquired: bool


def claim_run(
    ledger: RunLedger,
    run_key: RunKey,
    *,
    owner: str,
    at: datetime,
    lease_minutes: int,
) -> ClaimResult:
    """Claim once; an exact retry by the same owner returns the original claim."""

    if type(ledger) is not RunLedger or type(run_key) is not RunKey:
        raise TypeError("claim_run requires RunLedger and RunKey")
    owner_id = _require_identifier(owner, "owner")
    instant = _require_utc(at, "at")
    if type(lease_minutes) is not int or not 1 <= lease_minutes <= 1440:
        raise ValueError("lease_minutes must be an integer from 1 through 1440")
    if instant < run_key.scheduled_for:
        raise ValueError("run cannot be claimed before its scheduled time")
    try:
        existing = ledger.get(run_key)
    except KeyError:
        claim = RunClaim(
            run_key=run_key,
            owner=owner_id,
            claimed_at=instant,
            lease_expires_at=instant + timedelta(minutes=lease_minutes),
        )
        new_ledger = RunLedger(claims=ledger.claims + (claim,))
        return ClaimResult(ledger=new_ledger, claim=claim, acquired=True)
    if existing.owner != owner_id:
        raise ClaimConflictError("run key is already owned by another operator")
    return ClaimResult(ledger=ledger, claim=existing, acquired=False)


def complete_run(
    ledger: RunLedger,
    run_key: RunKey,
    *,
    output_sha256: str,
    at: datetime,
) -> RunLedger:
    digest = _require_sha256(output_sha256, "output_sha256")
    instant = _require_utc(at, "at")
    claim = ledger.get(run_key)
    if claim.status is RunStatus.SUCCEEDED:
        if claim.output_sha256 == digest:
            return ledger
        raise ClaimConflictError("completed run cannot be assigned a different output")
    if claim.status is RunStatus.FAILED:
        raise RunStateError("failed run cannot be completed under the same run key")
    if instant >= claim.lease_expires_at:
        raise ExpiredClaimError("run lease expired before completion")
    completed = replace(
        claim,
        status=RunStatus.SUCCEEDED,
        finished_at=instant,
        output_sha256=digest,
    )
    return _replace_claim(ledger, completed)


def fail_run(
    ledger: RunLedger,
    run_key: RunKey,
    *,
    failure_code: str,
    at: datetime,
) -> RunLedger:
    code = _require_identifier(failure_code, "failure_code")
    instant = _require_utc(at, "at")
    claim = ledger.get(run_key)
    if claim.status is RunStatus.FAILED:
        if claim.failure_code == code:
            return ledger
        raise ClaimConflictError("failed run cannot be assigned a different failure code")
    if claim.status is RunStatus.SUCCEEDED:
        raise RunStateError("successful run cannot be failed")
    failed = replace(
        claim,
        status=RunStatus.FAILED,
        finished_at=instant,
        failure_code=code,
    )
    return _replace_claim(ledger, failed)


def _replace_claim(ledger: RunLedger, replacement: RunClaim) -> RunLedger:
    return RunLedger(
        claims=tuple(
            replacement if claim.run_key.value == replacement.run_key.value else claim
            for claim in ledger.claims
        )
    )


@dataclass(frozen=True, slots=True)
class OperationalException:
    exception_key: str
    severity: Severity
    category: str
    resource_id: str
    summary: str
    detected_at: datetime
    status: ExceptionStatus = ExceptionStatus.OPEN
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    resolution_sha256: str | None = None
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.exception_key, "exception_key")
        if type(self.severity) is not Severity:
            raise TypeError("severity must be Severity")
        category = _require_identifier(self.category, "category")
        resource = _require_identifier(self.resource_id, "resource_id")
        summary = _require_string(self.summary, "summary", max_length=300)
        if "\n" in summary or "\r" in summary:
            raise ValueError("summary must be a single line without raw content")
        _require_utc(self.detected_at, "detected_at")
        if type(self.status) is not ExceptionStatus:
            raise TypeError("status must be ExceptionStatus")

        if self.status is ExceptionStatus.OPEN:
            if any(
                value is not None
                for value in (
                    self.acknowledged_at,
                    self.acknowledged_by,
                    self.resolved_at,
                    self.resolution_sha256,
                )
            ):
                raise ValueError("open exception cannot contain acknowledgement or resolution")
        else:
            _require_utc(self.acknowledged_at, "acknowledged_at")
            _require_identifier(self.acknowledged_by, "acknowledged_by")
            if self.acknowledged_at < self.detected_at:
                raise ValueError("acknowledgement cannot predate detection")
            if self.status is ExceptionStatus.ACKNOWLEDGED:
                if self.resolved_at is not None or self.resolution_sha256 is not None:
                    raise ValueError("acknowledged exception cannot contain resolution")
            else:
                _require_utc(self.resolved_at, "resolved_at")
                _require_sha256(self.resolution_sha256, "resolution_sha256")
                if self.resolved_at < self.acknowledged_at:
                    raise ValueError("resolution cannot predate acknowledgement")
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "exception_key": self.exception_key,
                    "severity": self.severity.value,
                    "category": category,
                    "resource_id": resource,
                    "summary": summary,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ExceptionQueue:
    items: tuple[OperationalException, ...] = ()

    def __post_init__(self) -> None:
        if type(self.items) is not tuple:
            raise TypeError("items must be a tuple")
        if any(type(item) is not OperationalException for item in self.items):
            raise TypeError("items must contain OperationalException values")
        keys = [item.exception_key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("exception queue contains duplicate keys")

    def get(self, exception_key: str) -> OperationalException:
        for item in self.items:
            if item.exception_key == exception_key:
                return item
        raise KeyError(f"unknown exception: {exception_key}")


def enqueue_exception(
    queue: ExceptionQueue,
    item: OperationalException,
) -> ExceptionQueue:
    for existing in queue.items:
        if existing.exception_key != item.exception_key:
            continue
        if existing.fingerprint_sha256 == item.fingerprint_sha256:
            return queue
        raise ExceptionStateError("exception key was reused for a different fault")
    return ExceptionQueue(items=queue.items + (item,))


def acknowledge_exception(
    queue: ExceptionQueue,
    exception_key: str,
    *,
    owner: str,
    at: datetime,
) -> ExceptionQueue:
    item = queue.get(_require_identifier(exception_key, "exception_key"))
    if item.status is ExceptionStatus.RESOLVED:
        raise ExceptionStateError("resolved exception cannot be acknowledged again")
    if item.status is ExceptionStatus.ACKNOWLEDGED:
        return queue
    acknowledged = replace(
        item,
        status=ExceptionStatus.ACKNOWLEDGED,
        acknowledged_at=_require_utc(at, "at"),
        acknowledged_by=_require_identifier(owner, "owner"),
    )
    return _replace_exception(queue, acknowledged)


def resolve_exception(
    queue: ExceptionQueue,
    exception_key: str,
    *,
    resolution_sha256: str,
    at: datetime,
) -> ExceptionQueue:
    item = queue.get(_require_identifier(exception_key, "exception_key"))
    digest = _require_sha256(resolution_sha256, "resolution_sha256")
    instant = _require_utc(at, "at")
    if item.status is ExceptionStatus.OPEN:
        raise ExceptionStateError("exception must be acknowledged before resolution")
    if item.status is ExceptionStatus.RESOLVED:
        if item.resolution_sha256 == digest:
            return queue
        raise ExceptionStateError("resolved exception cannot change resolution artifact")
    resolved = replace(
        item,
        status=ExceptionStatus.RESOLVED,
        resolved_at=instant,
        resolution_sha256=digest,
    )
    return _replace_exception(queue, resolved)


def _replace_exception(
    queue: ExceptionQueue,
    replacement: OperationalException,
) -> ExceptionQueue:
    return ExceptionQueue(
        items=tuple(
            replacement if item.exception_key == replacement.exception_key else item
            for item in queue.items
        )
    )


@dataclass(frozen=True, slots=True)
class TimeEntry:
    reference: str
    role: OperatingRole
    work_class: WorkClass
    minutes: int
    occurred_at: datetime
    entry_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.reference, "reference")
        if type(self.role) is not OperatingRole:
            raise TypeError("role must be OperatingRole")
        if type(self.work_class) is not WorkClass:
            raise TypeError("work_class must be WorkClass")
        if type(self.minutes) is not int or not 1 <= self.minutes <= 720:
            raise ValueError("minutes must be an integer from 1 through 720")
        _require_utc(self.occurred_at, "occurred_at")
        object.__setattr__(
            self,
            "entry_sha256",
            _canonical_sha256(
                {
                    "reference": self.reference,
                    "role": self.role.value,
                    "work_class": self.work_class.value,
                    "minutes": self.minutes,
                    "occurred_at": _utc_text(self.occurred_at),
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class MonthlyHumanBudget:
    month: str
    entries: tuple[TimeEntry, ...] = ()

    def __post_init__(self) -> None:
        if type(self.month) is not str or _MONTH_RE.fullmatch(self.month) is None:
            raise ValueError("month must use YYYY-MM")
        if type(self.entries) is not tuple:
            raise TypeError("entries must be a tuple")
        if any(type(entry) is not TimeEntry for entry in self.entries):
            raise TypeError("entries must contain TimeEntry values")
        references = [entry.reference for entry in self.entries]
        if len(references) != len(set(references)):
            raise ValueError("budget contains duplicate entry references")
        if any(_utc_text(entry.occurred_at)[:7] != self.month for entry in self.entries):
            raise ValueError("every entry must occur within the budget month")
        used = 0
        role_used = {role: 0 for role in OperatingRole}
        previous_time: datetime | None = None
        for entry in self.entries:
            if previous_time is not None and entry.occurred_at < previous_time:
                raise ValueError("time entries must be in UTC chronological order")
            previous_time = entry.occurred_at
            emergency = entry.work_class in _EMERGENCY_WORK
            if used >= MONTHLY_LIMIT_MINUTES and not emergency:
                raise BudgetExhaustedError("budget contains normal work after exhaustion")
            if used >= MONTHLY_FREEZE_MINUTES and entry.work_class in _FROZEN_WORK:
                raise BudgetFrozenError("budget contains frozen work after 576 minutes")
            if (
                entry.work_class in _FROZEN_WORK
                and used + entry.minutes > MONTHLY_FREEZE_MINUTES
            ):
                raise BudgetFrozenError("frozen work cannot cross the 576-minute boundary")
            if used + entry.minutes > MONTHLY_LIMIT_MINUTES and not emergency:
                raise BudgetExhaustedError("budget entries exceed the monthly limit")
            if (
                role_used[entry.role] + entry.minutes > ROLE_LIMIT_MINUTES[entry.role]
                and not emergency
            ):
                raise RoleBudgetExceededError(
                    f"budget entries exceed {entry.role.value} role allocation"
                )
            used += entry.minutes
            role_used[entry.role] += entry.minutes

    @property
    def used_minutes(self) -> int:
        return sum(entry.minutes for entry in self.entries)

    @property
    def remaining_minutes(self) -> int:
        return max(0, MONTHLY_LIMIT_MINUTES - self.used_minutes)

    @property
    def status(self) -> BudgetStatus:
        if self.used_minutes >= MONTHLY_LIMIT_MINUTES:
            return BudgetStatus.EXHAUSTED
        if self.used_minutes >= MONTHLY_FREEZE_MINUTES:
            return BudgetStatus.FROZEN
        return BudgetStatus.NORMAL

    def role_minutes(self, role: OperatingRole) -> int:
        return sum(entry.minutes for entry in self.entries if entry.role is role)


def record_time(budget: MonthlyHumanBudget, entry: TimeEntry) -> MonthlyHumanBudget:
    """Record once while enforcing 576 freeze, 720 cap, and role allocation."""

    if type(budget) is not MonthlyHumanBudget or type(entry) is not TimeEntry:
        raise TypeError("record_time requires MonthlyHumanBudget and TimeEntry")
    if _utc_text(entry.occurred_at)[:7] != budget.month:
        raise BudgetError("time entry is outside the budget month")
    if budget.entries and entry.occurred_at < budget.entries[-1].occurred_at:
        raise BudgetError("time entries must be recorded in UTC chronological order")
    for existing in budget.entries:
        if existing.reference != entry.reference:
            continue
        if existing.entry_sha256 == entry.entry_sha256:
            return budget
        raise BudgetError("time-entry reference was reused for different work")

    emergency = entry.work_class in _EMERGENCY_WORK
    if budget.status is BudgetStatus.EXHAUSTED and not emergency:
        raise BudgetExhaustedError(
            "720-minute budget is exhausted; only SEV0 stop or STOP decision is allowed"
        )
    if budget.status is BudgetStatus.FROZEN and entry.work_class in _FROZEN_WORK:
        raise BudgetFrozenError(
            "576-minute freeze blocks new sources and noncritical improvement"
        )
    projected = budget.used_minutes + entry.minutes
    if entry.work_class in _FROZEN_WORK and projected > MONTHLY_FREEZE_MINUTES:
        raise BudgetFrozenError("frozen work cannot cross the 576-minute boundary")
    if projected > MONTHLY_LIMIT_MINUTES and not emergency:
        raise BudgetExhaustedError("time entry would exceed the 720-minute monthly limit")
    role_projected = budget.role_minutes(entry.role) + entry.minutes
    if role_projected > ROLE_LIMIT_MINUTES[entry.role] and not emergency:
        raise RoleBudgetExceededError(
            f"{entry.role.value} allocation would exceed "
            f"{ROLE_LIMIT_MINUTES[entry.role]} minutes"
        )
    return MonthlyHumanBudget(month=budget.month, entries=budget.entries + (entry,))


__all__ = [
    "BudgetError",
    "BudgetExhaustedError",
    "BudgetFrozenError",
    "BudgetStatus",
    "ClaimConflictError",
    "ClaimResult",
    "ExceptionQueue",
    "ExceptionStateError",
    "ExceptionStatus",
    "ExpiredClaimError",
    "MONTHLY_FREEZE_MINUTES",
    "MONTHLY_LIMIT_MINUTES",
    "MonthlyHumanBudget",
    "OperatingRole",
    "OperationalException",
    "OperationsError",
    "ROLE_LIMIT_MINUTES",
    "RoleBudgetExceededError",
    "RunClaim",
    "RunKey",
    "RunLedger",
    "RunStateError",
    "RunStatus",
    "Severity",
    "TimeEntry",
    "WorkClass",
    "acknowledge_exception",
    "claim_run",
    "complete_run",
    "enqueue_exception",
    "fail_run",
    "record_time",
    "resolve_exception",
]
