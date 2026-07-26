from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from saas_preflight.cli import run as run_cli
from saas_preflight.growth_system import (
    ActivationDecision,
    ActivationKind,
    ClaimEvidenceLink,
    ContentBrief,
    ContentIntent,
    CtaDecision,
    CtaHealthInput,
    ConditionalActivationInput,
    DraftVoice,
    EditorialDecision,
    EditorialDraft,
    EditorialPackage,
    EvidenceMode,
    FeedbackBatch,
    FunnelEvent,
    FunnelStage,
    GoldDomain,
    GrowthIdentity,
    GrowthSystemError,
    HumanPolicyDecisionReceipt,
    InitiativePortfolio,
    InitiativeProposal,
    LearningGoldCase,
    LearningGoldSet,
    LinkStatus,
    MetricDefinition,
    MetricUnit,
    OperationsKpiInput,
    PageType,
    PromptModelRun,
    PromptRunLedger,
    ProposalLane,
    PolicyDecisionOutcome,
    SemanticFact,
    SemanticSnapshot,
    StrategyPosture,
    build_kpi_scorecard,
    build_policy_memo,
    evaluate_cta_health,
    evaluate_conditional_activation,
    evaluate_editorial_package,
)


AT = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _identity(suffix: str = "one") -> GrowthIdentity:
    return GrowthIdentity(
        property_id_sha256=_h(f"property:{suffix}"),
        content_id_sha256=_h(f"content:{suffix}"),
        query_cluster_id_sha256=_h(f"query:{suffix}"),
        campaign_id_sha256=_h(f"campaign:{suffix}"),
        cta_id_sha256=_h(f"cta:{suffix}"),
        cohort_id_sha256=_h(f"cohort:{suffix}"),
    )


def test_semantic_snapshot_separates_modeled_and_observed_facts() -> None:
    definition = MetricDefinition(
        metric_key="qualified-sessions",
        metric_version="1.0",
        unit=MetricUnit.COUNT,
        description_sha256=_h("definition"),
    )
    observed = SemanticFact(
        fact_id_sha256=_h("a-observed"),
        identity=_identity(),
        metric_key=definition.metric_key,
        metric_version=definition.metric_version,
        value=Decimal("12"),
        evidence_mode=EvidenceMode.OBSERVED,
        source_artifact_sha256=_h("gsc-export"),
        captured_at=AT,
        expires_at=AT + timedelta(days=7),
    )
    snapshot = SemanticSnapshot(
        created_at=AT,
        definitions=(definition,),
        facts=(observed,),
    )
    assert snapshot.facts[0].evidence_mode is EvidenceMode.OBSERVED

    with pytest.raises(ValidationError, match="observed fact requires source artifact"):
        SemanticFact(
            **observed.model_dump(exclude={"source_artifact_sha256"}),
            source_artifact_sha256=None,
        )

    modeled = observed.model_copy(
        update={
            "fact_id_sha256": _h("b-modeled"),
            "evidence_mode": EvidenceMode.MODELED,
            "source_artifact_sha256": None,
            "scenario_sha256": _h("bear-scenario"),
        }
    )
    with pytest.raises(ValidationError, match="duplicate identity metric fact"):
        SemanticSnapshot(
            created_at=AT,
            definitions=(definition,),
            facts=tuple(sorted((observed, modeled), key=lambda item: item.fact_id_sha256)),
        )


def test_learning_gold_set_requires_all_five_domains_and_current_labels() -> None:
    cases = tuple(
        sorted(
            (
                LearningGoldCase(
                    case_id_sha256=_h(domain.value),
                    domain=domain,
                    input_artifact_sha256=_h(f"input:{domain.value}"),
                    expected_artifact_sha256=_h(f"expected:{domain.value}"),
                    human_label_receipt_sha256=_h(f"human:{domain.value}"),
                    synthetic=True,
                    labeled_at=AT,
                    expires_at=AT + timedelta(days=30),
                )
                for domain in GoldDomain
            ),
            key=lambda item: item.case_id_sha256,
        )
    )
    goldset = LearningGoldSet(
        goldset_id_sha256=_h("learning-goldset"),
        created_at=AT,
        expires_at=AT + timedelta(days=30),
        cases=cases,
    )
    assert {case.domain for case in goldset.cases} == set(GoldDomain)

    with pytest.raises(ValidationError, match="at least 5 items"):
        LearningGoldSet(
            goldset_id_sha256=_h("partial"),
            created_at=AT,
            expires_at=AT + timedelta(days=30),
            cases=cases[:-1],
        )


def test_prompt_run_ledger_is_hash_only_ordered_and_sensitive_data_free() -> None:
    run = PromptModelRun(
        run_id_sha256=_h("run"),
        provider="openai",
        model="gpt-5.6-terra",
        model_snapshot="gpt-5.6-terra-2026-07-01",
        prompt_sha256=_h("prompt"),
        input_artifact_sha256=_h("input"),
        output_artifact_sha256=_h("output"),
        started_at=AT,
        completed_at=AT + timedelta(seconds=2),
        input_tokens=100,
        output_tokens=50,
        cost_minor=3,
        cost_currency="USD",
        evaluation_case_ids=(_h("case"),),
        evaluation_passed=True,
    )
    ledger = PromptRunLedger(ledger_id_sha256=_h("ledger"), runs=(run,))
    assert ledger.runs[0].contains_sensitive_data is False

    with pytest.raises(ValidationError, match="False"):
        PromptModelRun(**run.model_dump(exclude={"contains_sensitive_data"}), contains_sensitive_data=True)


def _proposal(
    posture: StrategyPosture,
    suffix: str,
    *,
    impact: int,
    rights: bool = True,
) -> InitiativeProposal:
    return InitiativeProposal(
        proposal_id_sha256=_h(suffix),
        posture=posture,
        title=f"Proposal {suffix}",
        evidence_artifact_sha256s=(_h(f"evidence:{suffix}"),),
        expected_impact_low_minor=impact,
        expected_impact_high_minor=impact,
        confidence=Decimal("1"),
        cost_minor=100,
        time_to_signal_days=10,
        reversibility=Decimal("1"),
        kill_condition="Stop when the frozen signal threshold fails.",
        owner_lane=ProposalLane.SHARED,
        rights_gate_passed=rights,
        legal_gate_passed=True,
        security_gate_passed=True,
    )


def test_policy_memo_keeps_hard_gates_outside_evi_and_ranks_eligible_options() -> None:
    proposals = tuple(
        sorted(
            (
                _proposal(StrategyPosture.CONSERVATIVE, "conservative", impact=100),
                _proposal(StrategyPosture.BALANCED, "balanced", impact=300),
                _proposal(StrategyPosture.AGGRESSIVE, "aggressive", impact=1000, rights=False),
            ),
            key=lambda item: item.proposal_id_sha256,
        )
    )
    memo = build_policy_memo(
        InitiativePortfolio(currency="JPY", as_of=AT, proposals=proposals)
    )
    assert memo.recommended_proposal_id_sha256 == _h("balanced")
    aggressive = next(item for item in memo.assessments if item.posture is StrategyPosture.AGGRESSIVE)
    assert aggressive.eligible is False
    assert aggressive.expected_value_of_information is None
    assert aggressive.hard_gate_failures == ("rights",)

    receipt = HumanPolicyDecisionReceipt(
        memo_sha256=_h("memo"),
        outcome=PolicyDecisionOutcome.APPROVE_EXPERIMENT,
        selected_proposal_id_sha256=memo.recommended_proposal_id_sha256,
        decided_by_sha256=_h("human"),
        decision_artifact_sha256=_h("decision"),
        basis_artifact_sha256s=(_h("basis"),),
        decided_at=AT,
        expires_at=AT + timedelta(days=7),
    )
    assert receipt.grants_external_action is False


def _editorial_package() -> EditorialPackage:
    evidence = _h("approved-evidence")
    claim = _h("claim")
    brief = ContentBrief(
        brief_id_sha256=_h("brief"),
        page_type=PageType.COMPARISON,
        query_cluster_id_sha256=_h("query-cluster"),
        intent=ContentIntent.COMPARE,
        audience="Japanese buyer comparing approved SaaS plans",
        comparison_unit_sha256=_h("comparison-unit"),
        approved_evidence_sha256s=(evidence,),
        cta_eligible=False,
        created_at=AT,
        source_valid_until=AT + timedelta(days=7),
    )
    drafts = tuple(
        EditorialDraft(
            voice=voice,
            content_sha256=_h(f"draft:{voice.value}"),
            claim_id_sha256s=(claim,),
        )
        for voice in DraftVoice
    )
    return EditorialPackage(
        brief=brief,
        drafts=drafts,
        claims=(
            ClaimEvidenceLink(
                claim_id_sha256=claim,
                material=True,
                evidence_sha256s=(evidence,),
                citation_id_sha256=_h("citation"),
            ),
        ),
        synthesized_content_sha256=_h("article"),
        synthesized_claim_id_sha256s=(claim,),
    )


def test_editorial_package_requires_three_voices_and_stops_when_evidence_expires() -> None:
    package = _editorial_package()
    ready = evaluate_editorial_package(package, at=AT + timedelta(days=1))
    assert ready.decision is EditorialDecision.READY_FOR_HUMAN_REVIEW
    expired = evaluate_editorial_package(package, at=AT + timedelta(days=7))
    assert expired.decision is EditorialDecision.STOP
    assert expired.reasons == ("source_expired",)

    with pytest.raises(ValidationError, match="analyst, editor and skeptical buyer"):
        EditorialPackage(
            **package.model_dump(exclude={"drafts"}),
            drafts=(package.drafts[0], package.drafts[0], package.drafts[1]),
        )


def _feedback_batch() -> FeedbackBatch:
    identity = _identity()
    events: list[FunnelEvent] = []
    parent = None
    for index, stage in enumerate(FunnelStage):
        event_id = _h(f"event:{index}")
        monetary = stage in {FunnelStage.PENDING, FunnelStage.CONFIRMED, FunnelStage.PAID}
        events.append(
            FunnelEvent(
                event_id_sha256=event_id,
                parent_event_id_sha256=parent,
                identity=identity,
                stage=stage,
                occurred_at=AT + timedelta(minutes=index),
                source_artifact_sha256=_h(f"source:{index}"),
                transaction_id_sha256=_h("transaction") if monetary else None,
                amount_minor=(100 if stage is FunnelStage.PENDING else 120) if monetary else 0,
                currency="JPY" if monetary else None,
            )
        )
        parent = event_id
    return FeedbackBatch(
        batch_id_sha256=_h("batch"),
        metric_version="1.0",
        captured_at=AT + timedelta(minutes=10),
        expires_at=AT + timedelta(days=1),
        events=tuple(events),
    )


def test_feedback_and_scorecard_preserve_causality_and_latest_settlement_state() -> None:
    batch = _feedback_batch()
    scorecard = build_kpi_scorecard(
        batch,
        OperationsKpiInput(
            human_minutes=30,
            routine_tasks_total=10,
            routine_tasks_automated=8,
            jobs_total=100,
            jobs_succeeded=99,
            major_misstatements=0,
            operating_cost_minor=20,
        ),
        at=AT + timedelta(hours=1),
    )
    assert scorecard.search_impressions == 1
    assert scorecard.qualified_sessions == 1
    assert scorecard.valid_outbound_clicks == 1
    assert scorecard.confirmed_revenue_minor == 120
    assert scorecard.confirmed_epc_minor == Decimal("120")
    assert scorecard.net_operating_profit_minor == 100
    assert scorecard.automation_rate == Decimal("0.8")
    assert scorecard.job_success_rate == Decimal("0.99")

    broken = list(batch.events)
    broken[2] = broken[2].model_copy(update={"parent_event_id_sha256": _h("missing")})
    with pytest.raises(ValidationError, match="parent is missing"):
        FeedbackBatch(
            batch_id_sha256=batch.batch_id_sha256,
            metric_version=batch.metric_version,
            captured_at=batch.captured_at,
            expires_at=batch.expires_at,
            events=tuple(broken),
        )

    with pytest.raises(GrowthSystemError, match="expired"):
        build_kpi_scorecard(
            batch,
            OperationsKpiInput(
                human_minutes=0,
                routine_tasks_total=0,
                routine_tasks_automated=0,
                jobs_total=0,
                jobs_succeeded=0,
                major_misstatements=0,
                operating_cost_minor=0,
            ),
            at=batch.expires_at,
        )


def test_cta_health_enables_only_exact_current_approved_state() -> None:
    value = CtaHealthInput(
        identity=_identity(),
        affiliate_approved=True,
        rights_current=True,
        link_status=LinkStatus.HEALTHY,
        expected_destination_sha256=_h("destination"),
        observed_destination_sha256=_h("destination"),
        expected_disclosure_sha256=_h("disclosure"),
        observed_disclosure_sha256=_h("disclosure"),
        checked_at=AT,
        expires_at=AT + timedelta(hours=1),
    )
    assert evaluate_cta_health(value, at=AT).decision is CtaDecision.ENABLED

    mismatch = value.model_copy(update={"observed_disclosure_sha256": _h("wrong")})
    result = evaluate_cta_health(mismatch, at=AT)
    assert result.decision is CtaDecision.DISABLED
    assert result.reasons == ("disclosure_mismatch",)


def test_conditional_activation_stops_until_evidence_and_human_gates_exist() -> None:
    stopped_input = ConditionalActivationInput(
        activation_id_sha256=_h("challenger-activation"),
        kind=ActivationKind.CHALLENGER_MODEL,
        captured_at=AT,
        expires_at=AT + timedelta(days=7),
        evidence_artifact_sha256s=(_h("benchmark-evidence"),),
    )
    stopped = evaluate_conditional_activation(stopped_input, at=AT)
    assert stopped.decision is ActivationDecision.STOP
    assert stopped.authority == "none"
    assert set(stopped.reasons) == {
        "budget_not_approved",
        "fewer_than_100_evaluated_runs",
        "promotion_threshold_not_met",
        "retention_not_approved",
        "single_provider_not_selected",
        "upstream_not_ready",
    }

    ready_for_human_gate = evaluate_conditional_activation(
        stopped_input.model_copy(
            update={
                "upstream_ready": True,
                "evaluated_runs": 100,
                "quality_gain_percent": Decimal("5"),
                "single_provider_candidate": True,
                "retention_approved": True,
                "budget_approved": True,
                "approval_receipt_sha256s": (_h("human-approval"),),
            }
        ),
        at=AT,
    )
    assert ready_for_human_gate.decision is ActivationDecision.READY_FOR_HUMAN_GATE
    assert ready_for_human_gate.authority == "none"
    assert ready_for_human_gate.reasons == ()


def test_growth_cli_is_local_hash_only_and_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package_path = tmp_path / "editorial-package.json"
    package_path.write_text(_editorial_package().model_dump_json(), encoding="utf-8")
    assert run_cli(
        [
            "evaluate-editorial-package",
            str(package_path),
            "--at",
            (AT + timedelta(days=1)).isoformat(),
        ]
    ) == 0
    editorial = json.loads(capsys.readouterr().out)
    assert editorial["authority"] == "none"
    assert editorial["decision"] == "ready_for_human_review"

    proposals = tuple(
        sorted(
            (
                _proposal(StrategyPosture.CONSERVATIVE, "conservative", impact=100),
                _proposal(StrategyPosture.BALANCED, "balanced", impact=300),
                _proposal(
                    StrategyPosture.AGGRESSIVE,
                    "aggressive",
                    impact=1000,
                    rights=False,
                ),
            ),
            key=lambda item: item.proposal_id_sha256,
        )
    )
    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_text(
        InitiativePortfolio(currency="JPY", as_of=AT, proposals=proposals).model_dump_json(),
        encoding="utf-8",
    )
    assert run_cli(["rank-growth-initiatives", str(portfolio_path)]) == 0
    memo = json.loads(capsys.readouterr().out)
    assert memo["authority"] == "none"
    assert memo["recommended_proposal_id_sha256"] == _h("balanced")

    feedback_path = tmp_path / "feedback.json"
    operations_path = tmp_path / "operations.json"
    scorecard_path = tmp_path / "scorecard.json"
    feedback_path.write_text(_feedback_batch().model_dump_json(), encoding="utf-8")
    operations_path.write_text(
        OperationsKpiInput(
            human_minutes=30,
            routine_tasks_total=10,
            routine_tasks_automated=8,
            jobs_total=100,
            jobs_succeeded=99,
            major_misstatements=0,
            operating_cost_minor=20,
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert run_cli(
        [
            "build-growth-scorecard",
            str(feedback_path),
            "--operations",
            str(operations_path),
            "--at",
            (AT + timedelta(hours=1)).isoformat(),
            "--output",
            str(scorecard_path),
        ]
    ) == 0
    scorecard_receipt = json.loads(capsys.readouterr().out)
    assert scorecard_receipt == {
        "authority": "none",
        "evidence_mode": "observed",
        "metric_version": "1.0",
        "output": str(scorecard_path.resolve()),
        "status": "derived",
    }
    assert json.loads(scorecard_path.read_text(encoding="utf-8"))[
        "net_operating_profit_minor"
    ] == 100

    cta_path = tmp_path / "cta.json"
    cta_path.write_text(
        CtaHealthInput(
            identity=_identity(),
            affiliate_approved=False,
            rights_current=True,
            link_status=LinkStatus.HEALTHY,
            expected_destination_sha256=_h("destination"),
            observed_destination_sha256=_h("destination"),
            expected_disclosure_sha256=_h("disclosure"),
            observed_disclosure_sha256=_h("disclosure"),
            checked_at=AT,
            expires_at=AT + timedelta(hours=1),
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert run_cli(
        ["evaluate-cta-health", str(cta_path), "--at", AT.isoformat()]
    ) == 3
    cta = json.loads(capsys.readouterr().out)
    assert cta["authority"] == "none"
    assert cta["decision"] == "disabled"
    assert cta["reasons"] == ["affiliate_not_approved"]

    activation_path = tmp_path / "activation.json"
    activation_path.write_text(
        ConditionalActivationInput(
            activation_id_sha256=_h("activation"),
            kind=ActivationKind.LLM_OBSERVABILITY,
            captured_at=AT,
            expires_at=AT + timedelta(days=1),
            evidence_artifact_sha256s=(_h("runs"),),
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert run_cli(
        ["evaluate-growth-activation", str(activation_path), "--at", AT.isoformat()]
    ) == 3
    activation = json.loads(capsys.readouterr().out)
    assert activation["authority"] == "none"
    assert activation["decision"] == "stop"


def test_growth_json_schemas_are_exported() -> None:
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    expected = {
        "semantic-snapshot.schema.json",
        "learning-gold-set.schema.json",
        "prompt-run-ledger.schema.json",
        "initiative-portfolio.schema.json",
        "policy-memo.schema.json",
        "human-policy-decision-receipt.schema.json",
        "editorial-package.schema.json",
        "editorial-evaluation.schema.json",
        "derivative-bundle.schema.json",
        "feedback-batch.schema.json",
        "kpi-scorecard.schema.json",
        "cta-health-input.schema.json",
        "cta-health-evaluation.schema.json",
        "conditional-activation-input.schema.json",
        "conditional-activation-evaluation.schema.json",
    }
    assert expected <= {path.name for path in schema_dir.glob("*.schema.json")}
    for filename in expected:
        document = json.loads((schema_dir / filename).read_text(encoding="utf-8"))
        assert document["type"] == "object"
        assert document["additionalProperties"] is False
