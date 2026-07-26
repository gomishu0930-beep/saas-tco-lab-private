"""Credential-free model routing policy for evaluated, pinned AI candidates.

This module selects only a candidate for a later controller/Human gate. It has
no API client, credential handling, billing mutation, or network operation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .models import CurrencyCode, Sha256, Slug, StrictModel


class ModelTask(str, Enum):
    BULK = "bulk"
    DRAFT = "draft"
    POLICY_QA = "policy_qa"


class ModelTier(str, Enum):
    LUNA = "luna"
    TERRA = "terra"
    SOL = "sol"


class ModelRouteDecision(str, Enum):
    READY_FOR_CONTROLLER_GATE = "ready_for_controller_gate"
    STOP = "stop"


_EXPECTED_TIER = {
    ModelTask.BULK: ModelTier.LUNA,
    ModelTask.DRAFT: ModelTier.TERRA,
    ModelTask.POLICY_QA: ModelTier.SOL,
}


class EvaluatedModelRoute(StrictModel):
    route_id_sha256: Sha256
    task: ModelTask
    tier: ModelTier
    provider: Slug
    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    model_snapshot: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    goldset_id_sha256: Sha256
    evaluated_at: datetime
    evaluation_expires_at: datetime
    evaluation_passed: bool
    quality_score: Decimal = Field(ge=0, le=1)
    predicted_cost_minor: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)

    @field_validator("evaluated_at", "evaluation_expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "model route timestamp")

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.evaluation_expires_at <= self.evaluated_at:
            raise ValueError("model evaluation expiry must be later than evaluation")
        if self.tier is not _EXPECTED_TIER[self.task]:
            raise ValueError("model task must use its fixed Luna/Terra/Sol tier")
        snapshot = self.model_snapshot.lower()
        if snapshot.endswith("latest") or snapshot in {"latest", "preview"}:
            raise ValueError("model snapshot must be pinned, not latest or preview")
        return self


class ModelRouterPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id_sha256: Sha256
    currency: CurrencyCode
    monthly_budget_minor: int = Field(gt=0)
    minimum_quality_score: Decimal = Field(ge=0, le=1)
    created_at: datetime
    expires_at: datetime
    budget_approved: bool = False
    budget_approval_receipt_sha256: Sha256 | None = None
    routes: tuple[EvaluatedModelRoute, ...] = Field(min_length=3, max_length=3)

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "model router policy timestamp")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("model router policy expiry must be later than creation")
        if self.budget_approved != (self.budget_approval_receipt_sha256 is not None):
            raise ValueError("budget approval and receipt hash must appear together")
        tasks = [route.task for route in self.routes]
        if set(tasks) != set(ModelTask) or len(tasks) != len(set(tasks)):
            raise ValueError("router requires exactly one route for each model task")
        route_ids = [route.route_id_sha256 for route in self.routes]
        if route_ids != sorted(route_ids) or len(route_ids) != len(set(route_ids)):
            raise ValueError("model routes must have unique canonically sorted IDs")
        return self


class ModelRoutingRequest(StrictModel):
    request_id_sha256: Sha256
    task: ModelTask
    goldset_id_sha256: Sha256
    prompt_sha256: Sha256
    input_artifact_sha256: Sha256
    requested_at: datetime
    projected_monthly_spend_minor: int = Field(ge=0)
    contains_sensitive_data: Literal[False] = False

    @field_validator("requested_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "model routing request timestamp")


class ModelRoutingEvaluation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id_sha256: Sha256
    evaluated_at: datetime
    decision: ModelRouteDecision
    selected_route_id_sha256: Sha256 | None
    reasons: tuple[str, ...]
    authority: Literal["none"] = "none"

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "model routing evaluation timestamp")

    @model_validator(mode="after")
    def validate_evaluation(self) -> Self:
        selected = self.selected_route_id_sha256 is not None
        if selected != (self.decision is ModelRouteDecision.READY_FOR_CONTROLLER_GATE):
            raise ValueError("only a ready routing evaluation may select a route")
        return self


def evaluate_model_route(
    request: ModelRoutingRequest,
    policy: ModelRouterPolicy,
    *,
    at: datetime,
) -> ModelRoutingEvaluation:
    instant = _utc(at, "model routing evaluation time")
    route = next(item for item in policy.routes if item.task is request.task)
    reasons: list[str] = []
    if instant < request.requested_at:
        reasons.append("future_request")
    if instant < policy.created_at:
        reasons.append("future_policy")
    if instant >= policy.expires_at:
        reasons.append("policy_expired")
    if instant < route.evaluated_at:
        reasons.append("future_evaluation")
    if instant >= route.evaluation_expires_at:
        reasons.append("model_evaluation_expired")
    if not policy.budget_approved:
        reasons.append("budget_not_approved")
    if not route.evaluation_passed:
        reasons.append("goldset_evaluation_failed")
    if route.quality_score < policy.minimum_quality_score:
        reasons.append("quality_below_policy")
    if request.goldset_id_sha256 != route.goldset_id_sha256:
        reasons.append("goldset_mismatch")
    if request.projected_monthly_spend_minor + route.predicted_cost_minor > policy.monthly_budget_minor:
        reasons.append("monthly_budget_exceeded")
    return ModelRoutingEvaluation(
        request_id_sha256=request.request_id_sha256,
        evaluated_at=instant,
        decision=(ModelRouteDecision.STOP if reasons else ModelRouteDecision.READY_FOR_CONTROLLER_GATE),
        selected_route_id_sha256=None if reasons else route.route_id_sha256,
        reasons=tuple(sorted(reasons)),
    )


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value


__all__ = [
    "EvaluatedModelRoute",
    "ModelRouteDecision",
    "ModelRouterPolicy",
    "ModelRoutingEvaluation",
    "ModelRoutingRequest",
    "ModelTask",
    "ModelTier",
    "evaluate_model_route",
]
