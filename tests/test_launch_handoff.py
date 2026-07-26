from __future__ import annotations

import base64
import json
import random
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from saas_preflight.cli import run as run_cli
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.launch_handoff import (
    REQUIRED_LAUNCH_HANDOFF_GATES,
    LaunchArtifactComponent,
    LaunchArtifactComponentKind,
    LaunchGateReceipt,
    LaunchHandoffBundle,
    LaunchHandoffDecision,
    LaunchHandoffGate,
    LaunchHandoffInputError,
    LaunchHandoffPlan,
    LaunchHandoffPolicy,
    LaunchHandoffProvenance,
    LaunchHandoffReason,
    LaunchHandoffRequirement,
    LaunchHandoffTrustStore,
    build_launch_handoff_bundle,
    evaluate_launch_handoff,
    hash_launch_artifact_components,
    hash_launch_gate_receipt,
    hash_launch_handoff_authority,
    hash_launch_handoff_plan,
    hash_launch_handoff_policy,
    hash_launch_handoff_trust_store,
    sign_launch_gate_receipt,
)
from saas_preflight.launch_semantics import (
    evaluate_launch_semantics,
    hash_launch_semantic_authority_pins,
)
from saas_preflight.repository_acceptance import (
    REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS,
    REQUIRED_REPOSITORY_VERIFICATION_CHECKS,
    REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS,
    HumanRepositoryDecision,
    RepositoryAcceptanceAuthorityPins,
    RepositoryAcceptancePolicy,
    RepositoryAcceptanceTrustStore,
    RepositoryVerificationFact,
    RepositoryVerificationNetworkMode,
    RepositoryVerificationProvenance,
    RepositoryVerificationRequirement,
    build_repository_acceptance_authority_bundle,
    build_repository_candidate_manifest,
    build_repository_inventory,
    build_repository_verification_bundle,
    build_repository_verification_from_verified_runner_evidence,
    hash_repository_acceptance_authority_pins,
    hash_repository_acceptance_policy,
    hash_repository_acceptance_trust_store,
    hash_repository_verification_authority,
    hash_repository_tree,
    hash_repository_verification_command,
    sign_human_repository_acceptance,
    sign_repository_verification_attestation,
)
from verified_runner_support import build_verified_runner_context
from launch_semantic_support import build_semantic_context


AT = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
HUMAN_PRIVATE = Ed25519PrivateKey.generate()
TCO_PRIVATE = Ed25519PrivateKey.generate()


def _digest(index: int) -> str:
    return f"{index:064x}"


TRUST = LaunchHandoffTrustStore(
    human_approver=create_verification_key(
        HUMAN_PRIVATE.public_key(),
        issuer="p16-human",
        role=SigningRole.HUMAN_APPROVER,
    ),
    tco_qa=create_verification_key(
        TCO_PRIVATE.public_key(), issuer="p16-tco", role=SigningRole.TCO_QA
    ),
)

POLICY = LaunchHandoffPolicy(
    policy_id="p16-launch-handoff-v1",
    trust_store_sha256=hash_launch_handoff_trust_store(TRUST),
    maximum_plan_ttl_seconds=86_400,
    maximum_evidence_ttl_seconds=86_400,
    maximum_live_gate_ttl_seconds=600,
    maximum_report_ttl_seconds=300,
)


def _accepted_repository_bundle(*, at: datetime = AT):
    human_private = Ed25519PrivateKey.generate()
    integration_private = Ed25519PrivateKey.generate()
    tco_private = Ed25519PrivateKey.generate()
    trust = RepositoryAcceptanceTrustStore(
        human_approver=create_verification_key(
            human_private.public_key(),
            issuer="p18-human",
            role=SigningRole.HUMAN_APPROVER,
        ),
        integration_evidence_runner=create_verification_key(
            integration_private.public_key(),
            issuer="p18-integration",
            role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        ),
        tco_qa=create_verification_key(
            tco_private.public_key(),
            issuer="p18-tco",
            role=SigningRole.TCO_QA,
        ),
    )
    files = build_repository_inventory(ROOT)
    tree_sha256 = hash_repository_tree(files)
    runner = build_verified_runner_context(
        tree_sha256, at=at - timedelta(hours=2)
    )
    verification = build_repository_verification_from_verified_runner_evidence(
        runner["evidence"],
        consumption_receipt=runner["consumption_receipt"],
    )
    facts = verification.facts
    integration = sign_repository_verification_attestation(
        verification,
        integration_private,
        attestation_id="p18-integration",
        signer_role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        signer_issuer="p18-integration",
        issued_at=at - timedelta(hours=2, minutes=50),
        expires_at=at + timedelta(hours=6),
        verified_runner_evidence=runner["evidence"],
        verified_runner_authority_sha256=runner["authority_sha256"],
    )
    tco = sign_repository_verification_attestation(
        verification,
        tco_private,
        attestation_id="p18-tco",
        signer_role=SigningRole.TCO_QA,
        signer_issuer="p18-tco",
        issued_at=at - timedelta(hours=2, minutes=50),
        expires_at=at + timedelta(hours=6),
        verified_runner_evidence=runner["evidence"],
        verified_runner_authority_sha256=runner["authority_sha256"],
    )
    manifest = build_repository_candidate_manifest(
        ROOT,
        verification,
        candidate_id="p11-p18-local-candidate",
        assembled_at=at - timedelta(hours=2, minutes=45),
        expires_at=at + timedelta(hours=6),
        integration_verification=integration,
        tco_qa_verification=tco,
        verified_runner_evidence=runner["evidence"],
        verified_runner_policy=runner["policy"],
        verified_runner_trust_store=runner["trust_store"],
        verified_runner_authority_pins=runner["authority_pins"],
    )
    policy = RepositoryAcceptancePolicy(
        policy_id="p18-local-acceptance-v1",
        scope_paths_sha256=manifest.scope_paths_sha256,
        expected_previous_candidate_record_sha256=(
            manifest.previous_candidate_record_sha256
        ),
        human_approver_key_id_sha256=trust.human_approver.key_id_sha256,
        integration_evidence_runner_key_id_sha256=(
            trust.integration_evidence_runner.key_id_sha256
        ),
        tco_qa_key_id_sha256=trust.tco_qa.key_id_sha256,
        verification_requirements=tuple(
            RepositoryVerificationRequirement(
                check=fact.check,
                command_sha256=fact.command_sha256,
                tool_name=fact.tool_name,
                tool_version=fact.tool_version,
                minimum_assertions=fact.assertions_executed,
            )
            for fact in facts
        ),
        required_authority_exclusions=(
            REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS
        ),
        maximum_manifest_ttl_seconds=86_400,
        maximum_verification_age_seconds=86_400,
        maximum_verification_attestation_ttl_seconds=86_400,
        maximum_acceptance_ttl_seconds=86_400,
    )
    receipt = sign_human_repository_acceptance(
        manifest,
        policy,
        trust,
        human_private,
        receipt_id="p18-human-go",
        revision=1,
        predecessor_receipt_sha256="0" * 64,
        decision=HumanRepositoryDecision.GO,
        issued_at=at - timedelta(hours=2, minutes=30),
        expires_at=at + timedelta(hours=6),
    )
    pins = RepositoryAcceptanceAuthorityPins(
        expected_manifest_sha256=manifest.manifest_sha256,
        expected_policy_sha256=hash_repository_acceptance_policy(policy),
        expected_trust_store_sha256=hash_repository_acceptance_trust_store(
            trust
        ),
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(policy, trust)
        ),
        expected_verified_runner_authority_sha256=runner["authority_sha256"],
        expected_current_receipt_sha256=receipt.receipt_sha256,
        expected_current_revision=1,
    )
    return build_repository_acceptance_authority_bundle(
        manifest, policy, trust, pins, receipt
    )


P18_ACCEPTANCE = _accepted_repository_bundle()
P18_AUTHORITY_ROOT = hash_repository_acceptance_authority_pins(
    P18_ACCEPTANCE.authority_pins
)
SEMANTIC_CONTEXT = build_semantic_context(
    candidate_manifest_sha256=P18_ACCEPTANCE.manifest.manifest_sha256
)
SEMANTIC_PACKET = SEMANTIC_CONTEXT["packet"]
SEMANTIC_PINS = SEMANTIC_CONTEXT["pins"]
SEMANTIC_AUTHORITY_ROOT = hash_launch_semantic_authority_pins(SEMANTIC_PINS)
SEMANTIC_EVALUATION = evaluate_launch_semantics(
    SEMANTIC_PACKET,
    SEMANTIC_PINS,
    at=AT,
    expected_authority_pins_sha256=SEMANTIC_AUTHORITY_ROOT,
)

HUMAN_GATES = {
    LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
    LaunchHandoffGate.RIGHTS_APPROVAL,
    LaunchHandoffGate.AFFILIATE_ACCEPTANCE,
    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS,
}

COMPONENT_KINDS = {
    REQUIRED_LAUNCH_HANDOFF_GATES[0]: (
        LaunchArtifactComponentKind.P18_REPOSITORY_ACCEPTANCE_AUTHORITY_BUNDLE,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[1]: (
        LaunchArtifactComponentKind.RIGHTS_DECISION_RECORD,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[2]: (
        LaunchArtifactComponentKind.AFFILIATE_DECISION_RECORD,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[3]: (
        LaunchArtifactComponentKind.QUALIFIED_DEMAND_RECORD,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[4]: (
        LaunchArtifactComponentKind.SHADOW_OPERATIONS_RECORD,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[5]: (
        LaunchArtifactComponentKind.GOLD_SOURCE_READINESS_RECORD,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[6]: (
        LaunchArtifactComponentKind.P15_READINESS_REPORT,
        LaunchArtifactComponentKind.P15_TCO_QA_ATTESTATION,
    ),
    REQUIRED_LAUNCH_HANDOFF_GATES[7]: (
        LaunchArtifactComponentKind.P10_LOCAL_ASSURANCE_REPORT,
        LaunchArtifactComponentKind.DEPLOYMENT_READINESS_RECORD,
        LaunchArtifactComponentKind.PUBLICATION_READINESS_RECORD,
    ),
}


def _requirements(
    trust: LaunchHandoffTrustStore = TRUST,
    repository_acceptance=P18_ACCEPTANCE,
    semantic_evaluation=SEMANTIC_EVALUATION,
):
    semantic_by_gate = {item.gate.value: item for item in semantic_evaluation.gates}
    result = []
    for index, gate in enumerate(REQUIRED_LAUNCH_HANDOFF_GATES, 1):
        role = (
            SigningRole.HUMAN_APPROVER if gate in HUMAN_GATES else SigningRole.TCO_QA
        )
        key = trust.human_approver if role is SigningRole.HUMAN_APPROVER else trust.tco_qa
        if gate is LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE:
            components = (
                LaunchArtifactComponent(
                    kind=COMPONENT_KINDS[gate][0],
                    artifact_sha256=repository_acceptance.bundle_sha256,
                ),
            )
            evidence_identity = repository_acceptance.human_acceptance.receipt_sha256
            subject = repository_acceptance.manifest.tree_sha256
        else:
            semantic = semantic_by_gate[gate.value]
            components = tuple(
                LaunchArtifactComponent(
                    kind=LaunchArtifactComponentKind(component.kind.value),
                    artifact_sha256=component.artifact_sha256,
                )
                for component in semantic.components
            )
            evidence_identity = semantic.evidence_identity_sha256
            subject = semantic.subject_sha256
        result.append(
            LaunchHandoffRequirement(
                gate=gate,
                evidence_identity_sha256=(
                    evidence_identity
                ),
                artifact_components=components,
                expected_artifact_sha256=hash_launch_artifact_components(components),
                subject_sha256=(
                    subject
                ),
                signer_role=role,
                signer_key_id_sha256=key.key_id_sha256,
                command_sha256=_digest(400 + index),
                tool_name=f"p16-{gate.value.replace('_', '-')}",
                tool_version="1.0.0",
            )
        )
    return tuple(result)


REQUIREMENTS = _requirements()


def _plan(
    *,
    policy: LaunchHandoffPolicy = POLICY,
    trust: LaunchHandoffTrustStore = TRUST,
    requirements: tuple[LaunchHandoffRequirement, ...] = REQUIREMENTS,
    repository_acceptance=P18_ACCEPTANCE,
    **updates: object,
) -> LaunchHandoffPlan:
    values: dict[str, object] = {
        "schema_version": "3.0",
        "plan_id": "p16-real-candidate",
        "handoff_policy_sha256": hash_launch_handoff_policy(policy),
        "trust_store_sha256": hash_launch_handoff_trust_store(trust),
        "repository_acceptance_authority_pins_sha256": (
            hash_repository_acceptance_authority_pins(
                repository_acceptance.authority_pins
            )
        ),
        "launch_semantic_authority_pins_sha256": SEMANTIC_AUTHORITY_ROOT,
        "candidate_manifest_sha256": SEMANTIC_PACKET.scope.candidate_manifest_sha256,
        "property_record_sha256": SEMANTIC_PACKET.scope.property_record_sha256,
        "environment_identity_sha256": SEMANTIC_PACKET.scope.environment_identity_sha256,
        "release_identity_sha256": SEMANTIC_PACKET.scope.release_identity_sha256,
        "release_manifest_sha256": SEMANTIC_PACKET.scope.release_manifest_sha256,
        "release_artifact_sha256": SEMANTIC_PACKET.scope.release_artifact_sha256,
        "deployment_candidate_sha256": SEMANTIC_PACKET.scope.deployment_candidate_sha256,
        "provider_target_sha256": SEMANTIC_PACKET.scope.provider_target_sha256,
        "expected_pre_state_sha256": SEMANTIC_PACKET.scope.expected_pre_state_sha256,
        "expected_post_state_sha256": SEMANTIC_PACKET.scope.expected_post_state_sha256,
        "rollback_state_sha256": SEMANTIC_PACKET.scope.rollback_state_sha256,
        "legal_pages_sha256": SEMANTIC_PACKET.scope.legal_pages_sha256,
        "affiliate_disclosure_sha256": (
            SEMANTIC_PACKET.scope.affiliate_disclosure_sha256
        ),
        "issued_at": AT - timedelta(hours=2),
        "not_before": AT - timedelta(hours=1),
        "expires_at": AT + timedelta(hours=6),
        "requirements": requirements,
    }
    values.update(updates)
    provisional = LaunchHandoffPlan.model_construct(**values, plan_sha256="0" * 64)
    return LaunchHandoffPlan(
        **values, plan_sha256=hash_launch_handoff_plan(provisional)
    )


PLAN = _plan()


def _default_observed(gate: LaunchHandoffGate) -> datetime:
    index = REQUIRED_LAUNCH_HANDOFF_GATES.index(gate)
    if index < 6:
        return AT - timedelta(hours=1) + timedelta(seconds=index)
    return AT - timedelta(minutes=4) + timedelta(seconds=index - 6)


def _default_expires(gate: LaunchHandoffGate) -> datetime:
    if gate is LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS:
        return AT + timedelta(minutes=3)
    if gate is LaunchHandoffGate.GOLD_SET_SOURCE_READINESS:
        return AT + timedelta(hours=1)
    return AT + (timedelta(minutes=5) if gate is LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS else timedelta(hours=12))


def _receipts(
    *,
    plan: LaunchHandoffPlan = PLAN,
    policy: LaunchHandoffPolicy = POLICY,
    provenance: LaunchHandoffProvenance = LaunchHandoffProvenance.VERIFIED_RECORD,
    provenance_overrides: dict[LaunchHandoffGate, LaunchHandoffProvenance] | None = None,
    signer_overrides: dict[LaunchHandoffGate, Ed25519PrivateKey] | None = None,
    observed_overrides: dict[LaunchHandoffGate, datetime] | None = None,
    expires_overrides: dict[LaunchHandoffGate, datetime] | None = None,
) -> tuple[LaunchGateReceipt, ...]:
    items: list[LaunchGateReceipt] = []
    for index, requirement in enumerate(plan.requirements):
        gate = requirement.gate
        default_key = HUMAN_PRIVATE if gate in HUMAN_GATES else TCO_PRIVATE
        key = (signer_overrides or {}).get(gate, default_key)
        issuer = TRUST.human_approver.issuer if gate in HUMAN_GATES else TRUST.tco_qa.issuer
        items.append(
            sign_launch_gate_receipt(
                plan,
                policy,
                requirement,
                key,
                predecessor_receipt=items[index - 1] if index else None,
                receipt_id=f"receipt-{index + 1}",
                reviewer_issuer=issuer,
                provenance=(provenance_overrides or {}).get(gate, provenance),
                observed_at=(observed_overrides or {}).get(gate, _default_observed(gate)),
                expires_at=(expires_overrides or {}).get(gate, _default_expires(gate)),
            )
        )
    return tuple(items)


def _bundle(
    receipts: tuple[LaunchGateReceipt, ...] | None = None,
    *,
    plan: LaunchHandoffPlan = PLAN,
    policy: LaunchHandoffPolicy = POLICY,
    repository_acceptance=P18_ACCEPTANCE,
    launch_semantics=SEMANTIC_PACKET,
) -> LaunchHandoffBundle:
    return build_launch_handoff_bundle(
        plan,
        policy,
        _receipts(plan=plan, policy=policy) if receipts is None else receipts,
        repository_acceptance=repository_acceptance,
        launch_semantics=launch_semantics,
    )


def _report(
    bundle: LaunchHandoffBundle | None = None,
    *,
    plan: LaunchHandoffPlan = PLAN,
    policy: LaunchHandoffPolicy = POLICY,
    trust: LaunchHandoffTrustStore = TRUST,
    at: datetime = AT,
    expected_repository_root: str = P18_AUTHORITY_ROOT,
    expected_launch_root: str | None = None,
    semantic_pins=SEMANTIC_PINS,
    expected_semantic_root: str = SEMANTIC_AUTHORITY_ROOT,
):
    return evaluate_launch_handoff(
        _bundle(plan=plan, policy=policy) if bundle is None else bundle,
        plan,
        policy,
        trust,
        at=at,
        expected_repository_acceptance_authority_pins_sha256=(
            expected_repository_root
        ),
        expected_launch_handoff_authority_sha256=(
            hash_launch_handoff_authority(plan, policy, trust)
            if expected_launch_root is None
            else expected_launch_root
        ),
        launch_semantic_authority_pins=semantic_pins,
        expected_launch_semantic_authority_pins_sha256=expected_semantic_root,
    )


def _resign(
    receipt: LaunchGateReceipt,
    private_key: Ed25519PrivateKey,
    **updates: object,
) -> LaunchGateReceipt:
    values = receipt.model_dump(exclude={"receipt_sha256", "signature_base64url"})
    values.update(updates)
    provisional = LaunchGateReceipt.model_construct(
        **values, receipt_sha256="0" * 64, signature_base64url="A" * 86
    )
    receipt_hash = hash_launch_gate_receipt(provisional)
    signature = base64.urlsafe_b64encode(
        private_key.sign(receipt_hash.encode("ascii"))
    ).rstrip(b"=").decode("ascii")
    return LaunchGateReceipt(
        **values, receipt_sha256=receipt_hash, signature_base64url=signature
    )


def test_exact_eight_gate_order_and_plan_hash_are_enforced() -> None:
    assert REQUIRED_LAUNCH_HANDOFF_GATES == (
        LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
        LaunchHandoffGate.RIGHTS_APPROVAL,
        LaunchHandoffGate.AFFILIATE_ACCEPTANCE,
        LaunchHandoffGate.QUALIFIED_DEMAND,
        LaunchHandoffGate.SHADOW_OPERATIONS,
        LaunchHandoffGate.GOLD_SET_SOURCE_READINESS,
        LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS,
        LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS,
    )
    values = PLAN.model_dump(exclude={"plan_sha256"})
    values["requirements"] = tuple(reversed(REQUIREMENTS))
    with pytest.raises(ValidationError, match="exact ordered P16 gates"):
        LaunchHandoffPlan(**values, plan_sha256="0" * 64)
    with pytest.raises(ValidationError, match="plan_sha256"):
        LaunchHandoffPlan(**PLAN.model_dump() | {"plan_sha256": _digest(999)})


def test_requirement_role_and_trust_key_separation_are_fixed() -> None:
    values = REQUIREMENTS[0].model_dump()
    values["signer_role"] = SigningRole.TCO_QA
    with pytest.raises(ValidationError, match="fixed handoff gate role"):
        LaunchHandoffRequirement(**values)
    values = REQUIREMENTS[-1].model_dump()
    values["artifact_components"] = values["artifact_components"][:-1]
    with pytest.raises(ValidationError, match="fixed gate contract"):
        LaunchHandoffRequirement(**values)
    with pytest.raises(ValidationError, match="Human Approver and TCO/QA"):
        LaunchHandoffTrustStore(
            human_approver=TRUST.human_approver,
            tco_qa=TRUST.human_approver.model_copy(
                update={"role": SigningRole.TCO_QA}
            ),
        )

    local_values = REQUIREMENTS[0].model_dump()
    local_values["artifact_components"] = (
        {
            "schema_version": "1.0",
            "kind": "p11_local_acceptance_record",
            "artifact_sha256": _digest(998),
        },
    )
    local_values["expected_artifact_sha256"] = _digest(996)
    with pytest.raises(ValidationError):
        LaunchHandoffRequirement(**local_values)


def test_complete_verified_packet_is_final_review_only() -> None:
    report = _report()
    assert report.decision is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
    assert report.passed_gates == REQUIRED_LAUNCH_HANDOFF_GATES
    assert report.failed_gates == ()
    assert report.authority_effect == "none"
    assert report.permitted_use == "final_human_review_input_only"
    assert report.does_not_authorize_external_action is True
    assert report.authorizes_external_mutation is False
    assert report.requires_execution_boundary_revalidation is True
    serialized = report.model_dump_json()
    for forbidden in ("bootstrap_authorization", "dispatch_token", "execution_grant", "public_go"):
        assert forbidden not in serialized


def test_p18_authority_bundle_is_mandatory_and_root_pinned() -> None:
    missing = _report(_bundle(repository_acceptance=None))
    assert missing.decision is LaunchHandoffDecision.STOP
    assert (
        LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
        LaunchHandoffReason.REPOSITORY_ACCEPTANCE_MISSING,
    ) in {(item.gate, item.reason) for item in missing.findings}

    with pytest.raises(LaunchHandoffInputError, match="authority root is invalid"):
        _report(expected_repository_root="A" * 64)

    wrong_root_plan = _plan(
        repository_acceptance_authority_pins_sha256=_digest(997)
    )
    wrong_root_bundle = _bundle(
        _receipts(plan=wrong_root_plan), plan=wrong_root_plan
    )
    with pytest.raises(LaunchHandoffInputError, match="binding mismatch"):
        _report(wrong_root_bundle, plan=wrong_root_plan)

    substituted = _accepted_repository_bundle()
    substituted_requirements = _requirements(
        repository_acceptance=substituted
    )
    substituted_plan = _plan(
        requirements=substituted_requirements,
        repository_acceptance=substituted,
    )
    substituted_bundle = _bundle(
        _receipts(plan=substituted_plan),
        plan=substituted_plan,
        repository_acceptance=substituted,
    )
    with pytest.raises(LaunchHandoffInputError, match="binding mismatch"):
        _report(
            substituted_bundle,
            plan=substituted_plan,
            expected_repository_root=P18_AUTHORITY_ROOT,
        )


def test_hash_only_handoff_without_typed_semantics_stops_gates_two_through_eight(
) -> None:
    report = _report(_bundle(launch_semantics=None), semantic_pins=None)
    assert report.decision is LaunchHandoffDecision.STOP
    missing = {
        item.gate
        for item in report.findings
        if item.reason is LaunchHandoffReason.SEMANTIC_EVIDENCE_MISSING
    }
    assert missing == set(REQUIRED_LAUNCH_HANDOFF_GATES[1:])
    assert report.authorizes_external_mutation is False

    for field in ("legal_pages_sha256", "affiliate_disclosure_sha256"):
        mismatched_plan = _plan(**{field: _digest(1600)})
        mismatched = _report(
            _bundle(plan=mismatched_plan),
            plan=mismatched_plan,
        )
        assert mismatched.decision is LaunchHandoffDecision.STOP
        assert LaunchHandoffReason.SEMANTIC_SCOPE_MISMATCH in {
            item.reason for item in mismatched.findings
        }


def test_checked_in_blocked_fixture_stays_stop_and_pending() -> None:
    directory = ROOT / "examples" / "p16" / "blocked"
    report = json.loads((directory / "expected-stop-report.json").read_text(encoding="utf-8"))
    assert report["decision"] == "stop"
    missing = {
        item["gate"]
        for item in report["findings"]
        if item["reason"] == "missing_receipt"
    }
    assert missing == {gate.value for gate in REQUIRED_LAUNCH_HANDOFF_GATES}
    pending = (ROOT / "docs" / "P11_P15_LOCAL_ACCEPTANCE_PENDING.md").read_text(
        encoding="utf-8"
    )
    assert "PENDING" in pending
    assert REQUIRED_LAUNCH_HANDOFF_GATES[0].value in report["failed_gates"]


@pytest.mark.parametrize("gate", REQUIRED_LAUNCH_HANDOFF_GATES)
def test_each_missing_gate_stops_and_blocks_later_gates(gate: LaunchHandoffGate) -> None:
    receipts = tuple(item for item in _receipts() if item.gate is not gate)
    report = _report(_bundle(receipts))
    assert report.decision is LaunchHandoffDecision.STOP
    assert (gate, LaunchHandoffReason.MISSING_RECEIPT) in {
        (item.gate, item.reason) for item in report.findings
    }
    for later in REQUIRED_LAUNCH_HANDOFF_GATES[
        REQUIRED_LAUNCH_HANDOFF_GATES.index(gate) + 1 :
    ]:
        assert (later, LaunchHandoffReason.PREREQUISITE_NOT_MET) in {
            (item.gate, item.reason) for item in report.findings
        }


@pytest.mark.parametrize("gate", REQUIRED_LAUNCH_HANDOFF_GATES)
def test_each_synthetic_gate_stops(gate: LaunchHandoffGate) -> None:
    receipts = _receipts(
        provenance_overrides={gate: LaunchHandoffProvenance.SYNTHETIC_CONTRACT}
    )
    report = _report(_bundle(receipts))
    assert report.decision is LaunchHandoffDecision.STOP
    assert (gate, LaunchHandoffReason.SYNTHETIC_RECEIPT) in {
        (item.gate, item.reason) for item in report.findings
    }


def test_complete_synthetic_packet_never_reaches_review() -> None:
    report = _report(
        _bundle(_receipts(provenance=LaunchHandoffProvenance.SYNTHETIC_CONTRACT))
    )
    assert report.decision is LaunchHandoffDecision.STOP
    assert len(
        [item for item in report.findings if item.reason is LaunchHandoffReason.SYNTHETIC_RECEIPT]
    ) == 8


def test_duplicate_and_conflicting_receipts_are_not_deduplicated() -> None:
    receipts = _receipts()
    exact = _report(_bundle(receipts + (receipts[2],)))
    assert LaunchHandoffReason.DUPLICATE_RECEIPT in {
        item.reason for item in exact.findings
    }
    conflicting = _resign(
        receipts[2], HUMAN_PRIVATE, receipt_id="receipt-3-conflict"
    )
    report = _report(_bundle(receipts + (conflicting,)))
    assert LaunchHandoffReason.CONFLICTING_RECEIPT in {
        item.reason for item in report.findings
    }

    cross_gate_id = list(receipts)
    cross_gate_id[1] = _resign(
        cross_gate_id[1], HUMAN_PRIVATE, receipt_id=receipts[0].receipt_id
    )
    report = _report(_bundle(tuple(cross_gate_id)))
    duplicate_gates = {
        item.gate
        for item in report.findings
        if item.reason is LaunchHandoffReason.DUPLICATE_RECEIPT
    }
    assert duplicate_gates == {
        LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
        LaunchHandoffGate.RIGHTS_APPROVAL,
    }


def test_bundle_and_report_are_permutation_invariant_including_conflicts() -> None:
    receipts = list(_receipts())
    original = _bundle(tuple(receipts))
    shuffled = list(receipts)
    random.Random(1601).shuffle(shuffled)
    assert _bundle(tuple(shuffled)) == original
    assert _report(_bundle(tuple(shuffled))) == _report(original)
    conflict = _resign(receipts[1], HUMAN_PRIVATE, receipt_id="receipt-2-conflict")
    one = _bundle(tuple(receipts) + (conflict,))
    two = _bundle(tuple(reversed(tuple(receipts) + (conflict,))))
    assert one == two
    assert _report(one) == _report(two)


def test_signature_tie_break_and_base64url_canonicality_are_deterministic() -> None:
    receipts = _receipts()
    original = receipts[2]
    invalid_envelope = original.model_copy(update={"signature_base64url": "A" * 86})
    forward = _bundle(receipts + (invalid_envelope,))
    reverse = _bundle(tuple(reversed(receipts + (invalid_envelope,))))
    assert forward == reverse
    assert _report(forward) == _report(reverse)

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    padding = lambda value: value + "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(padding(original.signature_base64url))
    aliases = [
        original.signature_base64url[:-1] + char
        for char in alphabet
        if original.signature_base64url[-1] != char
        and base64.urlsafe_b64decode(
            padding(original.signature_base64url[:-1] + char)
        )
        == decoded
    ]
    assert aliases
    aliased = original.model_copy(update={"signature_base64url": aliases[0]})
    replaced = list(receipts)
    replaced[2] = aliased
    report = _report(_bundle(tuple(replaced)))
    assert LaunchHandoffReason.RECEIPT_SIGNATURE_INVALID in {
        item.reason for item in report.findings
    }


def test_wrong_key_and_corrupt_signature_stop() -> None:
    wrong = Ed25519PrivateKey.generate()
    gate = LaunchHandoffGate.RIGHTS_APPROVAL
    receipts = _receipts(signer_overrides={gate: wrong})
    report = _report(_bundle(receipts))
    reasons = {(item.gate, item.reason) for item in report.findings}
    assert (gate, LaunchHandoffReason.REQUIREMENT_MISMATCH) in reasons
    assert (gate, LaunchHandoffReason.RECEIPT_SIGNATURE_INVALID) in reasons

    valid = list(_receipts())
    valid[0] = valid[0].model_copy(update={"signature_base64url": "A" * 86})
    corrupt = _report(_bundle(tuple(valid)))
    assert LaunchHandoffReason.RECEIPT_SIGNATURE_INVALID in {
        item.reason for item in corrupt.findings
    }

    wrong_issuer = list(_receipts())
    wrong_issuer[0] = _resign(
        wrong_issuer[0], HUMAN_PRIVATE, reviewer_issuer="untrusted-human"
    )
    report = _report(_bundle(tuple(wrong_issuer)))
    assert (
        LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE,
        LaunchHandoffReason.RECEIPT_SIGNATURE_INVALID,
    ) in {(item.gate, item.reason) for item in report.findings}


def test_receipt_ordinal_and_predecessor_shape_are_model_enforced() -> None:
    first = _receipts()[0]
    with pytest.raises(ValidationError, match="gate_ordinal"):
        LaunchGateReceipt(**first.model_dump() | {"gate_ordinal": 2})
    with pytest.raises(LaunchHandoffInputError, match="requires its exact predecessor"):
        sign_launch_gate_receipt(
            PLAN,
            POLICY,
            REQUIREMENTS[1],
            HUMAN_PRIVATE,
            predecessor_receipt=None,
            receipt_id="missing-predecessor",
            reviewer_issuer=TRUST.human_approver.issuer,
            provenance=LaunchHandoffProvenance.VERIFIED_RECORD,
            observed_at=AT - timedelta(minutes=30),
            expires_at=AT + timedelta(minutes=30),
        )


@pytest.mark.parametrize(
    "field",
    (
        "candidate_manifest_sha256",
        "property_record_sha256",
        "environment_identity_sha256",
        "deployment_candidate_sha256",
        "artifact_sha256",
        "subject_sha256",
        "command_sha256",
    ),
)
def test_scope_and_artifact_splices_are_rejected(field: str) -> None:
    receipts = list(_receipts())
    receipts[3] = _resign(receipts[3], TCO_PRIVATE, **{field: _digest(900)})
    report = _report(_bundle(tuple(receipts)))
    assert (
        LaunchHandoffGate.QUALIFIED_DEMAND,
        LaunchHandoffReason.REQUIREMENT_MISMATCH,
    ) in {(item.gate, item.reason) for item in report.findings}


def test_predecessor_chain_and_chronology_cannot_be_repaired_by_sorting() -> None:
    receipts = list(_receipts())
    gate = LaunchHandoffGate.SHADOW_OPERATIONS
    receipts[4] = _resign(
        receipts[4], TCO_PRIVATE, predecessor_receipt_sha256=_digest(901)
    )
    report = _report(_bundle(tuple(reversed(receipts))))
    assert (gate, LaunchHandoffReason.OUT_OF_ORDER_RECEIPT) in {
        (item.gate, item.reason) for item in report.findings
    }

    earlier = _default_observed(LaunchHandoffGate.QUALIFIED_DEMAND) - timedelta(seconds=1)
    chronological = _receipts(
        observed_overrides={LaunchHandoffGate.SHADOW_OPERATIONS: earlier}
    )
    report = _report(_bundle(chronological))
    assert (gate, LaunchHandoffReason.OUT_OF_ORDER_RECEIPT) in {
        (item.gate, item.reason) for item in report.findings
    }


@pytest.mark.parametrize(
    ("observed", "expires", "reason"),
    (
        (AT + timedelta(microseconds=1), AT + timedelta(hours=1), LaunchHandoffReason.RECEIPT_FUTURE),
        (AT - timedelta(hours=1), AT, LaunchHandoffReason.RECEIPT_EXPIRED),
        (
            AT - timedelta(hours=1),
            AT + timedelta(days=1, seconds=1),
            LaunchHandoffReason.RECEIPT_TTL_EXCEEDED,
        ),
    ),
)
def test_receipt_time_boundaries_fail_closed(
    observed: datetime, expires: datetime, reason: LaunchHandoffReason
) -> None:
    gate = LaunchHandoffGate.QUALIFIED_DEMAND
    receipts = _receipts(
        observed_overrides={gate: observed}, expires_overrides={gate: expires}
    )
    report = _report(_bundle(receipts))
    assert (gate, reason) in {(item.gate, item.reason) for item in report.findings}


def test_exact_ttl_boundary_passes_and_plus_one_stops() -> None:
    gate = LaunchHandoffGate.RIGHTS_APPROVAL
    observed = AT - timedelta(hours=1)
    receipts = _receipts(
        observed_overrides={gate: observed},
        expires_overrides={
            gate: observed
            + timedelta(seconds=POLICY.maximum_evidence_ttl_seconds)
        },
    )
    assert _report(_bundle(receipts)).decision is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
    receipts = _receipts(
        observed_overrides={gate: observed},
        expires_overrides={
            gate: observed
            + timedelta(seconds=POLICY.maximum_evidence_ttl_seconds + 1)
        },
    )
    report = _report(_bundle(receipts))
    assert (gate, LaunchHandoffReason.RECEIPT_TTL_EXCEEDED) in {
        (item.gate, item.reason) for item in report.findings
    }


def test_receipt_before_plan_stops() -> None:
    gate = LaunchHandoffGate.LOCAL_CANDIDATE_ACCEPTANCE
    receipts = _receipts(
        observed_overrides={gate: PLAN.issued_at - timedelta(seconds=1)}
    )
    report = _report(_bundle(receipts))
    assert (gate, LaunchHandoffReason.RECEIPT_BEFORE_PLAN) in {
        (item.gate, item.reason) for item in report.findings
    }


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        ({"not_before": AT + timedelta(microseconds=1)}, LaunchHandoffReason.PLAN_FUTURE),
        ({"expires_at": AT}, LaunchHandoffReason.PLAN_EXPIRED),
        (
            {"issued_at": AT - timedelta(days=2)},
            LaunchHandoffReason.PLAN_TTL_EXCEEDED,
        ),
    ),
)
def test_plan_time_boundaries_fail_closed(
    updates: dict[str, datetime], reason: LaunchHandoffReason
) -> None:
    if "not_before" in updates:
        updates["expires_at"] = AT + timedelta(hours=1)
    plan = _plan(**updates)
    report = _report(
        _bundle((), plan=plan), plan=plan
    )
    assert all(gate in report.failed_gates for gate in REQUIRED_LAUNCH_HANDOFF_GATES)
    assert reason in {item.reason for item in report.findings}


def test_ready_report_expiry_is_clipped_to_earliest_input() -> None:
    receipts = _receipts()
    report = _report(_bundle(receipts))
    assert report.expires_at == min(
        PLAN.expires_at,
        *(receipt.expires_at for receipt in receipts),
        *(item.expires_at for item in SEMANTIC_EVALUATION.gates),
        AT + timedelta(seconds=POLICY.maximum_report_ttl_seconds),
    )


def test_full_trust_policy_plan_substitution_is_not_accepted_by_original_root() -> None:
    other_human = Ed25519PrivateKey.generate()
    other_tco = Ed25519PrivateKey.generate()
    other_trust = LaunchHandoffTrustStore(
        human_approver=create_verification_key(
            other_human.public_key(), issuer="other-human", role=SigningRole.HUMAN_APPROVER
        ),
        tco_qa=create_verification_key(
            other_tco.public_key(), issuer="other-tco", role=SigningRole.TCO_QA
        ),
    )
    other_policy = POLICY.model_copy(
        update={"trust_store_sha256": hash_launch_handoff_trust_store(other_trust)}
    )
    other_plan = _plan(
        policy=other_policy,
        trust=other_trust,
        requirements=_requirements(other_trust),
    )
    other_bundle = build_launch_handoff_bundle(other_plan, other_policy, ())
    with pytest.raises(LaunchHandoffInputError, match="trust-store pin mismatch"):
        evaluate_launch_handoff(
            other_bundle,
            other_plan,
            other_policy,
            TRUST,
            at=AT,
            expected_repository_acceptance_authority_pins_sha256=(
                P18_AUTHORITY_ROOT
            ),
            expected_launch_handoff_authority_sha256=(
                hash_launch_handoff_authority(
                    other_plan, other_policy, TRUST
                )
            ),
        )

    with pytest.raises(LaunchHandoffInputError, match="consumer root"):
        evaluate_launch_handoff(
            other_bundle,
            other_plan,
            other_policy,
            other_trust,
            at=AT,
            expected_repository_acceptance_authority_pins_sha256=(
                P18_AUTHORITY_ROOT
            ),
            expected_launch_handoff_authority_sha256=(
                hash_launch_handoff_authority(PLAN, POLICY, TRUST)
            ),
        )


def test_unknown_and_forbidden_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LaunchHandoffPolicy(**POLICY.model_dump(), waiver=True)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LaunchGateReceipt(**_receipts()[0].model_dump(), source_url="https://example.invalid")


def test_p16_schemas_are_strict_and_expose_no_secret_or_waiver_fields() -> None:
    selected = tuple((ROOT / "schemas").glob("*launch*.schema.json"))
    assert len(selected) == 14
    prohibited = {
        "credential",
        "secret",
        "cookie",
        "oauth",
        "waiver",
        "notes",
        "public_go",
        "grant",
        "token",
        "authorization",
    }

    def inspect(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                assert not (set(properties) & prohibited)
                assert value.get("additionalProperties") is False
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    for path in selected:
        inspect(json.loads(path.read_text(encoding="utf-8")))


def test_p16_schema_and_blocked_fixture_generation_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    schema_one = tmp_path / "schema-one"
    schema_two = tmp_path / "schema-two"
    schema_command = [
        sys.executable,
        str(ROOT / "scripts" / "export_schemas.py"),
        "--output-dir",
    ]
    subprocess.run(schema_command + [str(schema_one)], check=True, cwd=ROOT)
    subprocess.run(schema_command + [str(schema_two)], check=True, cwd=ROOT)
    p16_names = sorted(path.name for path in schema_one.glob("*launch*.schema.json"))
    assert len(p16_names) == 14
    for name in p16_names:
        first = (schema_one / name).read_bytes()
        assert first == (schema_two / name).read_bytes()
        assert first == (ROOT / "schemas" / name).read_bytes()

    fixture_one = tmp_path / "fixture-one"
    fixture_two = tmp_path / "fixture-two"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "generate_p16_blocked_fixture.py"),
    ]
    subprocess.run(command + ["--output-dir", str(fixture_one)], check=True, cwd=ROOT)
    subprocess.run(command + ["--output-dir", str(fixture_two)], check=True, cwd=ROOT)
    names = sorted(path.name for path in fixture_one.iterdir())
    assert names == sorted(path.name for path in fixture_two.iterdir())
    for name in names:
        first = (fixture_one / name).read_bytes()
        assert first == (fixture_two / name).read_bytes()
        assert first == (ROOT / "examples" / "p16" / "blocked" / name).read_bytes()


def _write_cli_inputs(
    directory: Path, bundle: LaunchHandoffBundle
) -> tuple[Path, Path, Path, Path, Path]:
    paths = tuple(
        directory / name
        for name in (
            "bundle.json",
            "plan.json",
            "policy.json",
            "trust.json",
            "semantic-pins.json",
        )
    )
    for path, model in zip(
        paths, (bundle, PLAN, POLICY, TRUST, SEMANTIC_PINS), strict=True
    ):
        path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return paths  # type: ignore[return-value]


def _cli_args(paths: tuple[Path, Path, Path, Path, Path]) -> list[str]:
    bundle, plan, policy, trust, semantic_pins = paths
    return [
        "evaluate-launch-handoff",
        str(bundle),
        "--plan",
        str(plan),
        "--policy",
        str(policy),
        "--trust-store",
        str(trust),
        "--expected-repository-acceptance-authority-pins-sha256",
        P18_AUTHORITY_ROOT,
        "--expected-launch-handoff-authority-sha256",
        hash_launch_handoff_authority(PLAN, POLICY, TRUST),
        "--launch-semantic-authority-pins",
        str(semantic_pins),
        "--expected-launch-semantic-authority-pins-sha256",
        SEMANTIC_AUTHORITY_ROOT,
        "--at",
        AT.isoformat(),
    ]


def test_cli_is_offline_and_uses_stop_and_ready_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("P16 CLI attempted an external operation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    stop_paths = _write_cli_inputs(tmp_path, _bundle(()))
    assert run_cli(_cli_args(stop_paths)) == 3
    assert json.loads(capsys.readouterr().out)["decision"] == "stop"
    for path in stop_paths:
        path.unlink()
    ready_paths = _write_cli_inputs(tmp_path, _bundle())
    assert run_cli(_cli_args(ready_paths)) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "ready_for_final_human_review"
    assert output["authorizes_external_mutation"] is False


def test_cli_duplicate_json_key_is_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _write_cli_inputs(tmp_path, _bundle())
    paths[0].write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}\n', encoding="utf-8"
    )
    assert run_cli(_cli_args(paths)) == 2
    assert "duplicate JSON key: schema_version" in capsys.readouterr().err


def test_launch_handoff_cli_help_has_no_external_mutation_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_cli(["evaluate-launch-handoff", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    for forbidden in (
        "provider-url",
        "credential",
        "oauth",
        "billing",
        "--publish",
        "--deploy",
        "--send",
        "--apply",
        "--output",
    ):
        assert forbidden not in help_text
