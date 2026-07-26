#!/usr/bin/env python3
"""Generate the deterministic, credential-free P15 STOP fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.production_readiness import (
    ProductionFactsKind,
    ProductionIntegrationPlan,
    ProductionIntegrationPolicy,
    ProductionIntegrationRequirement,
    ProductionIntegrationTrustStore,
    REQUIRED_PRODUCTION_INTEGRATION_CHECKS,
    build_production_integration_bundle,
    evaluate_production_integration_readiness,
    hash_production_integration_plan,
    hash_production_integration_policy,
    hash_production_integration_trust_store,
)


AT = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)


def digest(index: int) -> str:
    return f"{index:064x}"


def key(index: int, issuer: str, role: SigningRole):
    public_key = Ed25519PublicKey.from_public_bytes(bytes([index]) * 32)
    return create_verification_key(public_key, issuer=issuer, role=role)


def build_models():
    trust = ProductionIntegrationTrustStore(
        controller=key(1, "fixture-controller", SigningRole.CONTROLLER),
        provider_conformance=key(
            2, "fixture-provider-conformance", SigningRole.PROVIDER_CONFORMANCE
        ),
        independent_probe=key(3, "fixture-probe", SigningRole.PROVIDER_PROBE),
        security_auditor=key(4, "fixture-security", SigningRole.SECURITY_AUDITOR),
        storage_auditor=key(5, "fixture-storage", SigningRole.STORAGE_AUDITOR),
        time_auditor=key(6, "fixture-time", SigningRole.TIME_AUDITOR),
        network_auditor=key(7, "fixture-network", SigningRole.NETWORK_AUDITOR),
        recovery_auditor=key(8, "fixture-recovery", SigningRole.RECOVERY_AUDITOR),
        tco_qa=key(9, "fixture-tco", SigningRole.TCO_QA),
        environment_human=key(10, "fixture-human", SigningRole.HUMAN_APPROVER),
    )
    policy = ProductionIntegrationPolicy(
        policy_id="p15-blocked-fixture-v1",
        trust_store_sha256=hash_production_integration_trust_store(trust),
        maximum_evidence_ttl_seconds=86_400,
        maximum_live_control_ttl_seconds=300,
        maximum_recovery_evidence_ttl_seconds=86_400,
        maximum_report_ttl_seconds=900,
        maximum_tco_attestation_ttl_seconds=3_600,
        maximum_human_approval_ttl_seconds=3_600,
        maximum_authorization_ttl_seconds=900,
        minimum_idempotency_retention_seconds=2_592_000,
        minimum_replay_attempts=2,
        minimum_receipt_lookup_attempts=2,
        maximum_receipt_lookup_lag_milliseconds=60_000,
        minimum_independent_readbacks=2,
        maximum_independent_readback_lag_milliseconds=60_000,
        minimum_anchor_samples=3,
        maximum_clock_offset_milliseconds=1_000,
        minimum_clock_sources=3,
        minimum_clock_failure_domains=2,
        minimum_fencing_workers=8,
        minimum_fencing_failure_domains=3,
        minimum_unapproved_egress_attempts=3,
        minimum_restore_attempts=2,
        maximum_rpo_seconds=900,
        maximum_rto_seconds=3_600,
        maximum_backup_age_seconds=900,
        maximum_restore_drill_age_seconds=604_800,
        minimum_rollback_exercises=2,
        maximum_disable_latency_milliseconds=300_000,
    )
    role_keys = {
        SigningRole.PROVIDER_CONFORMANCE: trust.provider_conformance,
        SigningRole.PROVIDER_PROBE: trust.independent_probe,
        SigningRole.SECURITY_AUDITOR: trust.security_auditor,
        SigningRole.STORAGE_AUDITOR: trust.storage_auditor,
        SigningRole.TIME_AUDITOR: trust.time_auditor,
        SigningRole.NETWORK_AUDITOR: trust.network_auditor,
        SigningRole.RECOVERY_AUDITOR: trust.recovery_auditor,
    }
    roles = {
        "provider_conditional_mutation": SigningRole.PROVIDER_CONFORMANCE,
        "provider_idempotency_retention": SigningRole.PROVIDER_CONFORMANCE,
        "provider_receipt_lookup": SigningRole.PROVIDER_CONFORMANCE,
        "independent_readback": SigningRole.PROVIDER_PROBE,
        "kms_identity_separation": SigningRole.SECURITY_AUDITOR,
        "external_monotonic_anchor": SigningRole.STORAGE_AUDITOR,
        "shared_durable_store_fencing": SigningRole.STORAGE_AUDITOR,
        "trusted_clock": SigningRole.TIME_AUDITOR,
        "egress_allowlist": SigningRole.NETWORK_AUDITOR,
        "backup_restore": SigningRole.RECOVERY_AUDITOR,
        "rollback_disable": SigningRole.RECOVERY_AUDITOR,
    }
    requirements = tuple(
        ProductionIntegrationRequirement(
            check=check,
            facts_kind=ProductionFactsKind(check.value),
            evidence_identity_sha256=digest(100 + index),
            signer_role=roles[check.value],
            signer_key_id_sha256=role_keys[roles[check.value]].key_id_sha256,
            subject_sha256=digest(200 + index),
            command_sha256=digest(300 + index),
            tool_name=f"fixture-{check.value.replace('_', '-')}",
            tool_version="1.0.0",
        )
        for index, check in enumerate(REQUIRED_PRODUCTION_INTEGRATION_CHECKS, 1)
    )
    plan_values = {
        "schema_version": "2.0",
        "plan_id": "p15-blocked-fixture",
        "integration_policy_sha256": hash_production_integration_policy(policy),
        "trust_store_sha256": hash_production_integration_trust_store(trust),
        "property_record_sha256": digest(401),
        "environment_identity_sha256": digest(402),
        "provider_account_sha256": digest(403),
        "p11_policy_sha256": digest(404),
        "p11_store_identity_sha256": digest(405),
        "p13_policy_sha256": digest(406),
        "p13_store_identity_sha256": digest(407),
        "reconciliation_ledger_store_sha256": digest(414),
        "release_artifact_sha256": digest(408),
        "release_manifest_sha256": digest(409),
        "adapter_closure_sha256": digest(410),
        "probe_closure_sha256": digest(411),
        "provider_capability_profile_sha256": digest(412),
        "deployment_candidate_sha256": digest(413),
        "provider_target_sha256": digest(414),
        "expected_pre_state_sha256": digest(415),
        "issued_at": AT - timedelta(hours=1),
        "not_before": AT - timedelta(minutes=30),
        "expires_at": AT + timedelta(hours=12),
        "requirements": requirements,
    }
    provisional = ProductionIntegrationPlan.model_construct(
        **plan_values, plan_sha256="0" * 64
    )
    plan = ProductionIntegrationPlan(
        **plan_values, plan_sha256=hash_production_integration_plan(provisional)
    )
    bundle = build_production_integration_bundle(plan, policy, ())
    report = evaluate_production_integration_readiness(
        bundle, plan, policy, trust, at=AT
    )
    return trust, policy, plan, bundle, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("examples/p15/blocked")
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
