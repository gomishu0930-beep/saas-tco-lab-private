from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from saas_preflight.ai_routing import (
    EvaluatedModelRoute,
    ModelRouteDecision,
    ModelRouterPolicy,
    ModelRoutingRequest,
    ModelTask,
    ModelTier,
    evaluate_model_route,
)
from saas_preflight.cli import run as run_cli


AT = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _routes() -> tuple[EvaluatedModelRoute, ...]:
    tiers = {
        ModelTask.BULK: ModelTier.LUNA,
        ModelTask.DRAFT: ModelTier.TERRA,
        ModelTask.POLICY_QA: ModelTier.SOL,
    }
    return tuple(
        sorted(
            (
                EvaluatedModelRoute(
                    route_id_sha256=_h(f"route:{task.value}"),
                    task=task,
                    tier=tiers[task],
                    provider="openai",
                    model=f"project-{tier.value}",
                    model_snapshot=f"project-{tier.value}-2026-07-01",
                    goldset_id_sha256=_h("goldset"),
                    evaluated_at=AT,
                    evaluation_expires_at=AT + timedelta(days=30),
                    evaluation_passed=True,
                    quality_score=Decimal("0.95"),
                    predicted_cost_minor=10,
                    p95_latency_ms=1000,
                )
                for task, tier in tiers.items()
            ),
            key=lambda item: item.route_id_sha256,
        )
    )


def _policy(*, approved: bool) -> ModelRouterPolicy:
    return ModelRouterPolicy(
        policy_id_sha256=_h("router-policy"),
        currency="JPY",
        monthly_budget_minor=10_000,
        minimum_quality_score=Decimal("0.9"),
        created_at=AT,
        expires_at=AT + timedelta(days=30),
        budget_approved=approved,
        budget_approval_receipt_sha256=_h("budget-receipt") if approved else None,
        routes=_routes(),
    )


def _request() -> ModelRoutingRequest:
    return ModelRoutingRequest(
        request_id_sha256=_h("request"),
        task=ModelTask.DRAFT,
        goldset_id_sha256=_h("goldset"),
        prompt_sha256=_h("prompt"),
        input_artifact_sha256=_h("input"),
        requested_at=AT,
        projected_monthly_spend_minor=100,
    )


def test_router_is_stopped_without_human_budget_and_selects_no_route() -> None:
    report = evaluate_model_route(_request(), _policy(approved=False), at=AT)
    assert report.decision is ModelRouteDecision.STOP
    assert report.selected_route_id_sha256 is None
    assert report.reasons == ("budget_not_approved",)
    assert report.authority == "none"


def test_router_selects_only_evaluated_pinned_task_tier_for_controller_gate() -> None:
    report = evaluate_model_route(_request(), _policy(approved=True), at=AT)
    expected = next(route for route in _routes() if route.task is ModelTask.DRAFT)
    assert report.decision is ModelRouteDecision.READY_FOR_CONTROLLER_GATE
    assert report.selected_route_id_sha256 == expected.route_id_sha256
    assert report.reasons == ()
    assert report.authority == "none"


def test_route_rejects_unpinned_alias_and_wrong_tier() -> None:
    route = _routes()[0]
    with pytest.raises(ValidationError, match="pinned"):
        EvaluatedModelRoute(
            **route.model_dump(exclude={"model_snapshot"}),
            model_snapshot="latest",
        )
    with pytest.raises(ValidationError, match="fixed Luna/Terra/Sol tier"):
        EvaluatedModelRoute(
            **route.model_dump(exclude={"tier"}),
            tier=(ModelTier.SOL if route.tier is not ModelTier.SOL else ModelTier.LUNA),
        )


def test_router_cli_emits_authority_free_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path = tmp_path / "request.json"
    policy_path = tmp_path / "policy.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    policy_path.write_text(_policy(approved=False).model_dump_json(), encoding="utf-8")
    assert run_cli(
        [
            "evaluate-model-route",
            str(request_path),
            "--policy",
            str(policy_path),
            "--at",
            AT.isoformat(),
        ]
    ) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "stop"
    assert output["authority"] == "none"
    assert output["selected_route_id_sha256"] is None
