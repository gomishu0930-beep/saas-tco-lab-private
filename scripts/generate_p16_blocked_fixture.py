#!/usr/bin/env python3
"""Generate the deterministic, credential-free P16 STOP fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.launch_handoff import (
    REQUIRED_LAUNCH_HANDOFF_GATES,
    LaunchArtifactComponent,
    LaunchArtifactComponentKind,
    LaunchHandoffPlan,
    LaunchHandoffPolicy,
    LaunchHandoffRequirement,
    LaunchHandoffTrustStore,
    build_launch_handoff_bundle,
    evaluate_launch_handoff,
    hash_launch_handoff_authority,
    hash_launch_handoff_plan,
    hash_launch_handoff_policy,
    hash_launch_handoff_trust_store,
    hash_launch_artifact_components,
)


AT = datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc)


def digest(index: int) -> str:
    return f"{index:064x}"


def key(index: int, issuer: str, role: SigningRole):
    public_key = Ed25519PublicKey.from_public_bytes(bytes([index]) * 32)
    return create_verification_key(public_key, issuer=issuer, role=role)


def build_models():
    trust = LaunchHandoffTrustStore(
        human_approver=key(21, "fixture-human", SigningRole.HUMAN_APPROVER),
        tco_qa=key(22, "fixture-tco", SigningRole.TCO_QA),
    )
    policy = LaunchHandoffPolicy(
        policy_id="p16-blocked-fixture-v1",
        trust_store_sha256=hash_launch_handoff_trust_store(trust),
        maximum_plan_ttl_seconds=86_400,
        maximum_evidence_ttl_seconds=86_400,
        maximum_live_gate_ttl_seconds=600,
        maximum_report_ttl_seconds=300,
    )
    role_keys = {
        SigningRole.HUMAN_APPROVER: trust.human_approver,
        SigningRole.TCO_QA: trust.tco_qa,
    }
    human_gates = {
        REQUIRED_LAUNCH_HANDOFF_GATES[0],
        REQUIRED_LAUNCH_HANDOFF_GATES[1],
        REQUIRED_LAUNCH_HANDOFF_GATES[2],
        REQUIRED_LAUNCH_HANDOFF_GATES[7],
    }
    component_kinds = {
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
    components = {
        gate: tuple(
            LaunchArtifactComponent(kind=kind, artifact_sha256=digest(600 + index * 10 + part))
            for part, kind in enumerate(component_kinds[gate], 1)
        )
        for index, gate in enumerate(REQUIRED_LAUNCH_HANDOFF_GATES, 1)
    }
    requirements = tuple(
        LaunchHandoffRequirement(
            gate=gate,
            evidence_identity_sha256=digest(100 + index),
            artifact_components=components[gate],
            expected_artifact_sha256=hash_launch_artifact_components(components[gate]),
            subject_sha256=digest(300 + index),
            signer_role=(
                SigningRole.HUMAN_APPROVER
                if gate in human_gates
                else SigningRole.TCO_QA
            ),
            signer_key_id_sha256=role_keys[
                SigningRole.HUMAN_APPROVER
                if gate in human_gates
                else SigningRole.TCO_QA
            ].key_id_sha256,
            command_sha256=digest(400 + index),
            tool_name=f"fixture-{gate.value.replace('_', '-')}",
            tool_version="1.0.0",
        )
        for index, gate in enumerate(REQUIRED_LAUNCH_HANDOFF_GATES, 1)
    )
    values = {
        "schema_version": "3.0",
        "plan_id": "p16-blocked-fixture",
        "handoff_policy_sha256": hash_launch_handoff_policy(policy),
        "trust_store_sha256": hash_launch_handoff_trust_store(trust),
        "repository_acceptance_authority_pins_sha256": digest(500),
        "launch_semantic_authority_pins_sha256": digest(506),
        "candidate_manifest_sha256": digest(501),
        "property_record_sha256": digest(502),
        "environment_identity_sha256": digest(503),
        "release_identity_sha256": digest(507),
        "release_manifest_sha256": digest(508),
        "release_artifact_sha256": digest(504),
        "deployment_candidate_sha256": digest(505),
        "provider_target_sha256": digest(509),
        "expected_pre_state_sha256": digest(510),
        "expected_post_state_sha256": digest(511),
        "rollback_state_sha256": digest(512),
        "legal_pages_sha256": digest(513),
        "affiliate_disclosure_sha256": digest(514),
        "issued_at": AT - timedelta(hours=2),
        "not_before": AT - timedelta(hours=1),
        "expires_at": AT + timedelta(hours=6),
        "requirements": requirements,
    }
    provisional = LaunchHandoffPlan.model_construct(**values, plan_sha256="0" * 64)
    plan = LaunchHandoffPlan(
        **values, plan_sha256=hash_launch_handoff_plan(provisional)
    )
    bundle = build_launch_handoff_bundle(plan, policy, ())
    report = evaluate_launch_handoff(
        bundle,
        plan,
        policy,
        trust,
        at=AT,
        expected_repository_acceptance_authority_pins_sha256=digest(500),
        expected_launch_handoff_authority_sha256=(
            hash_launch_handoff_authority(plan, policy, trust)
        ),
    )
    return trust, policy, plan, bundle, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("examples/p16/blocked")
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = (
        "trust-store.json",
        "policy.json",
        "plan.json",
        "evidence-bundle.json",
        "expected-stop-report.json",
    )
    for name, model in zip(names, build_models(), strict=True):
        (args.output_dir / name).write_text(
            json.dumps(
                model.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
