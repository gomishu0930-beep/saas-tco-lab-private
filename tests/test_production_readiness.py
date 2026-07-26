from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import socket
import sqlite3
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.cli import run as run_cli
from saas_preflight.production_readiness import (
    BackupRestoreFacts,
    EgressAllowlistFacts,
    EnvironmentApprovalDecision,
    ExternalMonotonicAnchorFacts,
    IndependentReadbackFacts,
    KmsIdentitySeparationFacts,
    P13TerminalState,
    ProductionEvidenceProvenance,
    ProductionFactsKind,
    ProductionHumanEnvironmentApproval,
    ProductionIntegrationCheck,
    ProductionIntegrationEvidence,
    ProductionIntegrationEvidenceBundle,
    ProductionIntegrationPlan,
    ProductionIntegrationPolicy,
    ProductionIntegrationRequirement,
    ProductionIntegrationTrustStore,
    ProductionReadinessAuthorityPins,
    ProductionReadinessDecision,
    ProductionReadinessInputError,
    ProductionReadinessReason,
    ProductionReconciliationAction,
    ProductionReconciliationFacts,
    ProductionReconciliationLedger,
    ProductionReconciliationReason,
    ProductionTcoQaAttestation,
    ProviderConditionalMutationFacts,
    ProviderIdempotencyRetentionFacts,
    ProviderObservedState,
    ProviderReceiptLookupFacts,
    REQUIRED_PRODUCTION_INTEGRATION_CHECKS,
    ReadinessAttestationDecision,
    RollbackDisableFacts,
    SharedDurableStoreFencingFacts,
    TrustedClockFacts,
    authorize_production_bootstrap,
    build_production_integration_bundle,
    evaluate_production_integration_readiness,
    evaluate_production_reconciliation,
    hash_production_bootstrap_authorization,
    hash_production_integration_plan,
    hash_production_integration_policy,
    hash_production_integration_trust_store,
    sign_production_human_environment_approval,
    sign_production_integration_evidence,
    sign_production_reconciliation_facts,
    sign_production_tco_qa_attestation,
    verify_production_bootstrap_authorization,
    verify_production_tco_qa_attestation,
)


AT = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]

CONTROLLER_PRIVATE = Ed25519PrivateKey.generate()
PROVIDER_PRIVATE = Ed25519PrivateKey.generate()
PROBE_PRIVATE = Ed25519PrivateKey.generate()
SECURITY_PRIVATE = Ed25519PrivateKey.generate()
STORAGE_PRIVATE = Ed25519PrivateKey.generate()
TIME_PRIVATE = Ed25519PrivateKey.generate()
NETWORK_PRIVATE = Ed25519PrivateKey.generate()
RECOVERY_PRIVATE = Ed25519PrivateKey.generate()
TCO_PRIVATE = Ed25519PrivateKey.generate()
HUMAN_PRIVATE = Ed25519PrivateKey.generate()

TRUST = ProductionIntegrationTrustStore(
    controller=create_verification_key(
        CONTROLLER_PRIVATE.public_key(), issuer="p15-controller", role=SigningRole.CONTROLLER
    ),
    provider_conformance=create_verification_key(
        PROVIDER_PRIVATE.public_key(),
        issuer="provider-conformance",
        role=SigningRole.PROVIDER_CONFORMANCE,
    ),
    independent_probe=create_verification_key(
        PROBE_PRIVATE.public_key(), issuer="independent-probe", role=SigningRole.PROVIDER_PROBE
    ),
    security_auditor=create_verification_key(
        SECURITY_PRIVATE.public_key(), issuer="security-auditor", role=SigningRole.SECURITY_AUDITOR
    ),
    storage_auditor=create_verification_key(
        STORAGE_PRIVATE.public_key(), issuer="storage-auditor", role=SigningRole.STORAGE_AUDITOR
    ),
    time_auditor=create_verification_key(
        TIME_PRIVATE.public_key(), issuer="time-auditor", role=SigningRole.TIME_AUDITOR
    ),
    network_auditor=create_verification_key(
        NETWORK_PRIVATE.public_key(), issuer="network-auditor", role=SigningRole.NETWORK_AUDITOR
    ),
    recovery_auditor=create_verification_key(
        RECOVERY_PRIVATE.public_key(), issuer="recovery-auditor", role=SigningRole.RECOVERY_AUDITOR
    ),
    tco_qa=create_verification_key(
        TCO_PRIVATE.public_key(), issuer="p15-tco", role=SigningRole.TCO_QA
    ),
    environment_human=create_verification_key(
        HUMAN_PRIVATE.public_key(), issuer="p15-human", role=SigningRole.HUMAN_APPROVER
    ),
)


def _digest(index: int) -> str:
    return f"{index:064x}"


POLICY = ProductionIntegrationPolicy(
    policy_id="p15-production-integration-v1",
    trust_store_sha256=hash_production_integration_trust_store(TRUST),
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


def _requirement(check: ProductionIntegrationCheck) -> ProductionIntegrationRequirement:
    index = REQUIRED_PRODUCTION_INTEGRATION_CHECKS.index(check) + 1
    role = {
        ProductionIntegrationCheck.PROVIDER_CONDITIONAL_MUTATION: SigningRole.PROVIDER_CONFORMANCE,
        ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION: SigningRole.PROVIDER_CONFORMANCE,
        ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP: SigningRole.PROVIDER_CONFORMANCE,
        ProductionIntegrationCheck.INDEPENDENT_READBACK: SigningRole.PROVIDER_PROBE,
        ProductionIntegrationCheck.KMS_IDENTITY_SEPARATION: SigningRole.SECURITY_AUDITOR,
        ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR: SigningRole.STORAGE_AUDITOR,
        ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING: SigningRole.STORAGE_AUDITOR,
        ProductionIntegrationCheck.TRUSTED_CLOCK: SigningRole.TIME_AUDITOR,
        ProductionIntegrationCheck.EGRESS_ALLOWLIST: SigningRole.NETWORK_AUDITOR,
        ProductionIntegrationCheck.BACKUP_RESTORE: SigningRole.RECOVERY_AUDITOR,
        ProductionIntegrationCheck.ROLLBACK_DISABLE: SigningRole.RECOVERY_AUDITOR,
    }[check]
    key = {
        SigningRole.PROVIDER_CONFORMANCE: TRUST.provider_conformance,
        SigningRole.PROVIDER_PROBE: TRUST.independent_probe,
        SigningRole.SECURITY_AUDITOR: TRUST.security_auditor,
        SigningRole.STORAGE_AUDITOR: TRUST.storage_auditor,
        SigningRole.TIME_AUDITOR: TRUST.time_auditor,
        SigningRole.NETWORK_AUDITOR: TRUST.network_auditor,
        SigningRole.RECOVERY_AUDITOR: TRUST.recovery_auditor,
    }[role]
    return ProductionIntegrationRequirement(
        check=check,
        facts_kind=ProductionFactsKind(check.value),
        evidence_identity_sha256=_digest(100 + index),
        signer_role=role,
        signer_key_id_sha256=key.key_id_sha256,
        subject_sha256=_digest(200 + index),
        command_sha256=_digest(300 + index),
        tool_name=f"p15-{check.value.replace('_', '-')}",
        tool_version="1.0.0",
    )


REQUIREMENTS = tuple(_requirement(check) for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS)


def _plan(**updates: object) -> ProductionIntegrationPlan:
    values: dict[str, object] = {
        "schema_version": "2.0",
        "plan_id": "p15-real-environment-candidate",
        "integration_policy_sha256": hash_production_integration_policy(POLICY),
        "trust_store_sha256": hash_production_integration_trust_store(TRUST),
        "property_record_sha256": _digest(401),
        "environment_identity_sha256": _digest(402),
        "provider_account_sha256": _digest(410),
        "p11_policy_sha256": _digest(411),
        "p11_store_identity_sha256": _digest(412),
        "p13_policy_sha256": _digest(403),
        "p13_store_identity_sha256": _digest(404),
        "reconciliation_ledger_store_sha256": _digest(414),
        "release_artifact_sha256": _digest(405),
        "release_manifest_sha256": _digest(413),
        "adapter_closure_sha256": _digest(406),
        "probe_closure_sha256": _digest(407),
        "provider_capability_profile_sha256": _digest(408),
        "deployment_candidate_sha256": _digest(409),
        "provider_target_sha256": _digest(415),
        "expected_pre_state_sha256": _digest(416),
        "issued_at": AT - timedelta(hours=1),
        "not_before": AT - timedelta(minutes=30),
        "expires_at": AT + timedelta(hours=12),
        "requirements": REQUIREMENTS,
    }
    values.update(updates)
    provisional = ProductionIntegrationPlan.model_construct(**values, plan_sha256="0" * 64)
    return ProductionIntegrationPlan(
        **values, plan_sha256=hash_production_integration_plan(provisional)
    )


PLAN = _plan()


def _facts(check: ProductionIntegrationCheck, *, success: bool = True):
    digest = _digest(500 + REQUIRED_PRODUCTION_INTEGRATION_CHECKS.index(check))
    if check is ProductionIntegrationCheck.PROVIDER_CONDITIONAL_MUTATION:
        return ProviderConditionalMutationFacts(
            matching_precondition_case_sha256=_digest(1001),
            stale_precondition_case_sha256=_digest(1002),
            lower_fence_case_sha256=_digest(1003),
            concurrent_precondition_case_sha256=_digest(1004),
            scenarios_executed=4,
            accepted_writes=1,
            stale_precondition_rejections=1,
            lower_fence_rejections=1,
            concurrent_winners=1,
            replay_receipt_matches=1,
            duplicate_side_effects=0 if success else 1,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION:
        return ProviderIdempotencyRetentionFacts(
            idempotency_key_sha256=_digest(1010),
            initial_request_sha256=_digest(1011),
            replay_request_sha256=_digest(1011),
            conflicting_request_sha256=_digest(1014),
            conflict_case_sha256=_digest(1015),
            initial_receipt_sha256=_digest(1012),
            replay_receipt_sha256=_digest(1012),
            initial_audit_sha256=_digest(1013),
            replay_audit_sha256=_digest(1013),
            observed_retention_seconds=2_592_000 if success else 2_591_999,
            replay_attempts=2,
            matching_receipts=2,
            duplicate_side_effects=0,
            conflicting_request_rejections=1,
            conflicting_request_side_effects=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP:
        return ProviderReceiptLookupFacts(
            known_query_sha256=_digest(1021),
            expected_receipt_sha256=_digest(1022),
            observed_receipt_sha256=_digest(1022),
            unknown_query_sha256=_digest(1023),
            unknown_result_sha256=_digest(1024),
            lookup_attempts=2,
            receipts_found=1,
            receipt_mismatches=0 if success else 1,
            unauthorized_receipts_returned=0,
            known_lookup_lag_milliseconds=60_000,
            unknown_lookup_mutation_effects=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.INDEPENDENT_READBACK:
        return IndependentReadbackFacts(
            adapter_identity_sha256=_digest(601),
            reader_identity_sha256=_digest(602),
            reader_acl_sha256=_digest(1031),
            provider_receipt_sha256=_digest(1032),
            journal_record_sha256=_digest(1033),
            expected_state_sha256=_digest(1034),
            observed_state_sha256=_digest(1034),
            readbacks_attempted=2,
            readbacks_matched=2 if success else 1,
            readback_mismatches=0 if success else 1,
            readback_lag_milliseconds=60_000,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.KMS_IDENTITY_SEPARATION:
        return KmsIdentitySeparationFacts(
            provider_identity_sha256=_digest(611),
            probe_identity_sha256=_digest(612),
            controller_identity_sha256=_digest(613),
            runner_identity_sha256=_digest(614),
            pairwise_assertions_checked=6,
            separation_violations=0 if success else 1,
            provider_permission_profile_sha256=_digest(1041),
            probe_permission_profile_sha256=_digest(1042),
            controller_permission_profile_sha256=_digest(1043),
            runner_permission_profile_sha256=_digest(1044),
            key_policy_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR:
        return ExternalMonotonicAnchorFacts(
            anchor_identity_sha256=_digest(621),
            store_identity_sha256=_digest(1051),
            advance_case_sha256=_digest(1052),
            rollback_reject_case_sha256=_digest(1053),
            equivocation_reject_case_sha256=_digest(1054),
            authoritative_readback_case_sha256=_digest(1055),
            revision_before=10,
            revision_after=11,
            samples_observed=3,
            strictly_advanced_transitions=2 if success else 1,
            regressions=0,
            replay_rejections=1,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.TRUSTED_CLOCK:
        return TrustedClockFacts(
            clock_source_identity_sha256s=(_digest(1061), _digest(1062), _digest(1063)),
            failure_domain_sha256s=(_digest(1064), _digest(1065)),
            signed_sample_sequence_sha256=_digest(1066),
            rollback_reject_case_sha256=_digest(1067),
            future_reject_case_sha256=_digest(1068),
            samples_observed=3,
            maximum_absolute_offset_milliseconds=750 if success else 751,
            maximum_uncertainty_milliseconds=250,
            backward_steps=0,
            out_of_bound_samples=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING:
        return SharedDurableStoreFencingFacts(
            store_identity_sha256=_digest(641),
            worker_identity_sha256s=tuple(_digest(1070 + index) for index in range(8)),
            failure_domain_sha256s=(_digest(1081), _digest(1082), _digest(1083)),
            lower_fence_reject_case_sha256=_digest(1084),
            old_owner_reject_case_sha256=_digest(1085),
            owner_death_reopen_case_sha256=_digest(1086),
            concurrent_workers=8,
            claim_contenders=8,
            winning_claims=1 if success else 2,
            stale_writer_rejections=7,
            unfenced_successful_writes=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.EGRESS_ALLOWLIST:
        return EgressAllowlistFacts(
            allowlist_policy_sha256=_digest(651),
            approved_destination_sha256s=(_digest(652), _digest(653)),
            observed_destination_sha256s=(
                (_digest(652), _digest(653)) if success else (_digest(652),)
            ),
            method_policy_sha256=_digest(1091),
            tls_profile_sha256=_digest(1092),
            deny_dns_case_sha256=_digest(1093),
            deny_private_range_case_sha256=_digest(1094),
            deny_metadata_case_sha256=_digest(1095),
            deny_wildcard_case_sha256=_digest(1096),
            approved_attempts=2,
            blocked_unapproved_attempts=3,
            successful_unapproved_attempts=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.BACKUP_RESTORE:
        return BackupRestoreFacts(
            source_snapshot_sha256=_digest(661),
            restored_snapshot_sha256=_digest(661) if success else _digest(662),
            source_head_sha256=_digest(1101),
            restored_head_sha256=_digest(1101),
            source_journal_set_sha256=_digest(1102),
            restored_journal_set_sha256=_digest(1102),
            source_anchor_sha256=_digest(1103),
            restored_anchor_sha256=_digest(1103),
            isolated_restore_target_sha256=_digest(1104),
            production_store_identity_sha256=_digest(1105),
            production_pointer_before_sha256=_digest(1106),
            production_pointer_after_sha256=_digest(1106),
            tampered_backup_reject_case_sha256=_digest(1107),
            older_backup_reject_case_sha256=_digest(1108),
            restore_attempts=2,
            successful_restores=2,
            integrity_mismatches=0,
            corrupt_backup_rejections=1,
            observed_rpo_seconds=900,
            observed_rto_seconds=3_600,
            backup_age_seconds=900,
            restore_drill_age_seconds=604_800,
            authoritative_resume_event_gap=0,
            result_artifact_sha256=digest,
        )
    if check is ProductionIntegrationCheck.ROLLBACK_DISABLE:
        return RollbackDisableFacts(
            disable_policy_sha256=_digest(671),
            active_state_sha256=_digest(1111),
            disabled_state_sha256=_digest(1112),
            final_observed_state_sha256=_digest(1112),
            p11_disable_authority_sha256=_digest(1113),
            provider_disable_receipt_sha256=_digest(1114),
            independent_probe_receipt_sha256=_digest(1115),
            running_lane_case_sha256=_digest(1116),
            stop_lane_case_sha256=_digest(1117),
            fault_exercises=2,
            completed_disables=2,
            maximum_disable_latency_milliseconds=300_000 if success else 300_001,
            post_disable_mutation_attempts=2,
            successful_post_disable_mutations=0,
            activation_events_emitted=0,
            retry_events_emitted=0,
            final_state_artifact_sha256=digest,
        )
    raise AssertionError(check)


def _evidence(
    check: ProductionIntegrationCheck,
    *,
    plan: ProductionIntegrationPlan = PLAN,
    success: bool = True,
    provenance: ProductionEvidenceProvenance = ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
    observed_at: datetime | None = None,
    expires_at: datetime | None = None,
    signer: Ed25519PrivateKey | None = None,
    issuer: str | None = None,
    evidence_id: str | None = None,
    facts_override: object | None = None,
) -> ProductionIntegrationEvidence:
    active_observed_at = observed_at or (AT - timedelta(minutes=1))
    role = REQUIREMENTS[REQUIRED_PRODUCTION_INTEGRATION_CHECKS.index(check)].signer_role
    default_private, default_issuer = {
        SigningRole.PROVIDER_CONFORMANCE: (PROVIDER_PRIVATE, "provider-conformance"),
        SigningRole.PROVIDER_PROBE: (PROBE_PRIVATE, "independent-probe"),
        SigningRole.SECURITY_AUDITOR: (SECURITY_PRIVATE, "security-auditor"),
        SigningRole.STORAGE_AUDITOR: (STORAGE_PRIVATE, "storage-auditor"),
        SigningRole.TIME_AUDITOR: (TIME_PRIVATE, "time-auditor"),
        SigningRole.NETWORK_AUDITOR: (NETWORK_PRIVATE, "network-auditor"),
        SigningRole.RECOVERY_AUDITOR: (RECOVERY_PRIVATE, "recovery-auditor"),
    }[role]
    default_expiry = (
        active_observed_at + timedelta(seconds=300)
        if check
        in {
            ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR,
            ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING,
            ProductionIntegrationCheck.TRUSTED_CLOCK,
        }
        else active_observed_at + timedelta(hours=1)
    )
    return sign_production_integration_evidence(
        plan,
        POLICY,
        REQUIREMENTS[REQUIRED_PRODUCTION_INTEGRATION_CHECKS.index(check)],
        facts_override if facts_override is not None else _facts(check, success=success),
        signer or default_private,
        evidence_id=evidence_id or f"evidence-{check.value.replace('_', '-')}",
        issuer=issuer or default_issuer,
        provenance=provenance,
        observed_at=active_observed_at,
        expires_at=expires_at or default_expiry,
    )


def _bundle(
    *,
    plan: ProductionIntegrationPlan = PLAN,
    at: datetime = AT,
    provenance: ProductionEvidenceProvenance = ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
) -> ProductionIntegrationEvidenceBundle:
    return build_production_integration_bundle(
        plan,
        POLICY,
        tuple(
            _evidence(
                check,
                plan=plan,
                provenance=provenance,
                observed_at=at - timedelta(minutes=1),
            )
            for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS
        ),
    )


def _report(
    bundle: ProductionIntegrationEvidenceBundle | None = None,
    *,
    plan: ProductionIntegrationPlan = PLAN,
    at: datetime = AT,
):
    return evaluate_production_integration_readiness(
        bundle or _bundle(plan=plan, at=at), plan, POLICY, TRUST, at=at
    )


def test_plan_hash_binds_every_production_identity() -> None:
    fields = (
        "integration_policy_sha256",
        "trust_store_sha256",
        "property_record_sha256",
        "environment_identity_sha256",
        "provider_account_sha256",
        "p11_policy_sha256",
        "p11_store_identity_sha256",
        "p13_policy_sha256",
        "p13_store_identity_sha256",
        "reconciliation_ledger_store_sha256",
        "release_artifact_sha256",
        "release_manifest_sha256",
        "adapter_closure_sha256",
        "probe_closure_sha256",
        "provider_capability_profile_sha256",
        "deployment_candidate_sha256",
        "provider_target_sha256",
        "expected_pre_state_sha256",
    )
    assert all(
        _plan(**{field: _digest(900 + index)}).plan_sha256 != PLAN.plan_sha256
        for index, field in enumerate(fields)
    )
    changed_requirement = REQUIREMENTS[0].model_copy(
        update={"command_sha256": _digest(930)}
    )
    assert _plan(plan_id="changed-plan").plan_sha256 != PLAN.plan_sha256
    assert (
        _plan(requirements=(changed_requirement, *REQUIREMENTS[1:])).plan_sha256
        != PLAN.plan_sha256
    )
    assert (
        _plan(
            issued_at=PLAN.issued_at - timedelta(seconds=1),
            not_before=PLAN.not_before,
            expires_at=PLAN.expires_at,
        ).plan_sha256
        != PLAN.plan_sha256
    )


def test_plan_rejects_duplicate_or_missing_evidence_identities() -> None:
    duplicate = REQUIREMENTS[1].model_copy(
        update={"evidence_identity_sha256": REQUIREMENTS[0].evidence_identity_sha256}
    )
    values = PLAN.model_dump(exclude={"plan_sha256"})
    values["requirements"] = (REQUIREMENTS[0], duplicate, *REQUIREMENTS[2:])
    provisional = ProductionIntegrationPlan.model_construct(**values, plan_sha256="0" * 64)
    with pytest.raises(ValidationError, match="evidence identity"):
        ProductionIntegrationPlan(
            **values, plan_sha256=hash_production_integration_plan(provisional)
        )
    with pytest.raises(ValidationError, match="at least 11 items"):
        ProductionIntegrationPlan(**{**values, "requirements": REQUIREMENTS[:-1], "plan_sha256": "0" * 64})


def test_blocked_fixture_reports_all_eleven_missing_checks() -> None:
    empty = build_production_integration_bundle(PLAN, POLICY, ())
    report = _report(empty)
    assert report.decision is ProductionReadinessDecision.STOP
    assert report.failed_checks == REQUIRED_PRODUCTION_INTEGRATION_CHECKS
    assert tuple(item.reason for item in report.findings) == (
        ProductionReadinessReason.MISSING_EVIDENCE,
    ) * 11


def test_checked_in_blocked_fixture_is_current_and_explicit() -> None:
    fixture = ROOT / "examples" / "p15" / "blocked"
    bundle = ProductionIntegrationEvidenceBundle.model_validate_json(
        (fixture / "evidence-bundle.json").read_text(encoding="utf-8")
    )
    plan = ProductionIntegrationPlan.model_validate_json(
        (fixture / "plan.json").read_text(encoding="utf-8")
    )
    policy = ProductionIntegrationPolicy.model_validate_json(
        (fixture / "policy.json").read_text(encoding="utf-8")
    )
    trust = ProductionIntegrationTrustStore.model_validate_json(
        (fixture / "trust-store.json").read_text(encoding="utf-8")
    )
    report = evaluate_production_integration_readiness(
        bundle, plan, policy, trust, at=AT
    )
    expected = json.loads(
        (fixture / "expected-stop-report.json").read_text(encoding="utf-8")
    )
    assert report.model_dump(mode="json") == expected
    assert report.decision is ProductionReadinessDecision.STOP


def test_complete_synthetic_fixture_stops_and_is_never_authority() -> None:
    report = _report(_bundle(provenance=ProductionEvidenceProvenance.SYNTHETIC_CONTRACT))
    assert report.decision is ProductionReadinessDecision.STOP
    assert len(report.findings) == 11
    assert {item.reason for item in report.findings} == {
        ProductionReadinessReason.SYNTHETIC_EVIDENCE
    }
    assert report.synthetic_evidence_is_not_production_authority is True


def test_complete_production_shaped_fixture_is_ready_only_for_human_gate() -> None:
    report = _report()
    assert report.decision is ProductionReadinessDecision.READY_FOR_HUMAN_GATE
    assert report.findings == ()
    assert report.passed_checks == REQUIRED_PRODUCTION_INTEGRATION_CHECKS
    assert "authorization" not in report.model_dump_json()


@pytest.mark.parametrize(
    ("plan", "reason"),
    [
        (
            _plan(
                issued_at=AT - timedelta(hours=1),
                not_before=AT + timedelta(microseconds=1),
                expires_at=AT + timedelta(hours=1),
            ),
            ProductionReadinessReason.PLAN_FUTURE,
        ),
        (
            _plan(
                issued_at=AT - timedelta(hours=2),
                not_before=AT - timedelta(hours=1),
                expires_at=AT,
            ),
            ProductionReadinessReason.PLAN_EXPIRED,
        ),
    ],
)
def test_plan_future_or_exact_expiry_stops(
    plan: ProductionIntegrationPlan, reason: ProductionReadinessReason
) -> None:
    bundle = _bundle(plan=plan, at=AT)
    report = _report(bundle, plan=plan, at=AT)
    assert report.decision is ProductionReadinessDecision.STOP
    assert {item.reason for item in report.findings} == {reason}


def test_report_and_authorization_are_clipped_to_plan_expiry() -> None:
    plan = _plan(expires_at=AT + timedelta(minutes=2))
    bundle = _bundle(plan=plan, at=AT)
    report = _report(bundle, plan=plan, at=AT)
    assert report.expires_at == plan.expires_at
    _, _, tco, human = _signed_gate(report, bundle, plan=plan, at=AT)
    with pytest.raises(
        ProductionReadinessInputError, match="expire before every input"
    ):
        authorize_production_bootstrap(
            report,
            bundle,
            plan,
            POLICY,
            TRUST,
            tco,
            human,
            CONTROLLER_PRIVATE,
            issuer="p15-controller",
            issued_at=AT,
            expires_at=plan.expires_at + timedelta(microseconds=1),
        )


def test_future_evaluated_report_cannot_be_authorized_from_earlier_attestations() -> None:
    future = AT + timedelta(minutes=10)
    bundle = _bundle(plan=PLAN, at=future)
    report = _report(bundle, plan=PLAN, at=future)
    _, _, tco, human = _signed_gate(report, bundle, plan=PLAN, at=AT)
    with pytest.raises(ProductionReadinessInputError, match="must postdate the report"):
        authorize_production_bootstrap(
            report,
            bundle,
            PLAN,
            POLICY,
            TRUST,
            tco,
            human,
            CONTROLLER_PRIVATE,
            issuer="p15-controller",
            issued_at=AT,
            expires_at=AT + timedelta(minutes=1),
        )


@pytest.mark.parametrize("check", REQUIRED_PRODUCTION_INTEGRATION_CHECKS)
def test_each_semantically_failed_check_stops(check: ProductionIntegrationCheck) -> None:
    evidence = [item for item in _bundle().evidence if item.check is not check]
    evidence.append(_evidence(check, success=False))
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert report.decision is ProductionReadinessDecision.STOP
    assert check in report.failed_checks
    assert ProductionReadinessReason.CHECK_FAILED in {
        item.reason for item in report.findings if item.check is check
    }


@pytest.mark.parametrize(
    ("check", "updates"),
    (
        (ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION, {"replay_attempts": 1, "matching_receipts": 1}),
        (ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION, {"conflicting_request_rejections": 0}),
        (ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION, {"conflicting_request_side_effects": 1}),
        (ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP, {"lookup_attempts": 1}),
        (ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP, {"known_lookup_lag_milliseconds": 60_001}),
        (ProductionIntegrationCheck.INDEPENDENT_READBACK, {"readbacks_attempted": 1, "readbacks_matched": 1}),
        (ProductionIntegrationCheck.INDEPENDENT_READBACK, {"readback_lag_milliseconds": 60_001}),
        (ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR, {"samples_observed": 2, "strictly_advanced_transitions": 1}),
        (ProductionIntegrationCheck.TRUSTED_CLOCK, {"clock_source_identity_sha256s": (_digest(1061), _digest(1062))}),
        (ProductionIntegrationCheck.TRUSTED_CLOCK, {"failure_domain_sha256s": (_digest(1064),)}),
        (
            ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING,
            {
                "worker_identity_sha256s": tuple(_digest(1070 + index) for index in range(7)),
                "concurrent_workers": 7,
                "claim_contenders": 7,
                "stale_writer_rejections": 6,
            },
        ),
        (ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING, {"failure_domain_sha256s": (_digest(1081), _digest(1082))}),
        (ProductionIntegrationCheck.EGRESS_ALLOWLIST, {"blocked_unapproved_attempts": 2}),
        (ProductionIntegrationCheck.BACKUP_RESTORE, {"restore_attempts": 1, "successful_restores": 1}),
        (ProductionIntegrationCheck.BACKUP_RESTORE, {"observed_rpo_seconds": 901}),
        (ProductionIntegrationCheck.BACKUP_RESTORE, {"observed_rto_seconds": 3_601}),
        (ProductionIntegrationCheck.BACKUP_RESTORE, {"backup_age_seconds": 901}),
        (ProductionIntegrationCheck.BACKUP_RESTORE, {"restore_drill_age_seconds": 604_801}),
        (ProductionIntegrationCheck.ROLLBACK_DISABLE, {"fault_exercises": 1, "completed_disables": 1}),
    ),
)
def test_each_policy_threshold_one_unit_outside_stops(
    check: ProductionIntegrationCheck, updates: dict[str, object]
) -> None:
    altered = _facts(check).model_copy(update=updates)
    evidence = [item for item in _bundle().evidence if item.check is not check]
    evidence.append(_evidence(check, facts_override=altered))
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert report.decision is ProductionReadinessDecision.STOP
    assert ProductionReadinessReason.CHECK_FAILED in {
        finding.reason for finding in report.findings if finding.check is check
    }


@pytest.mark.parametrize(
    ("check", "maximum_ttl"),
    (
        (ProductionIntegrationCheck.PROVIDER_IDEMPOTENCY_RETENTION, POLICY.maximum_evidence_ttl_seconds),
        (ProductionIntegrationCheck.TRUSTED_CLOCK, POLICY.maximum_live_control_ttl_seconds),
        (ProductionIntegrationCheck.BACKUP_RESTORE, POLICY.maximum_recovery_evidence_ttl_seconds),
    ),
)
def test_evidence_ttl_exact_boundary_passes_and_one_second_outside_stops(
    check: ProductionIntegrationCheck, maximum_ttl: int
) -> None:
    expiry = AT + timedelta(seconds=1)
    exact = _evidence(
        check,
        observed_at=expiry - timedelta(seconds=maximum_ttl),
        expires_at=expiry,
    )
    outside = _evidence(
        check,
        observed_at=expiry - timedelta(seconds=maximum_ttl + 1),
        expires_at=expiry,
    )
    base = tuple(item for item in _bundle().evidence if item.check is not check)
    assert _report(build_production_integration_bundle(PLAN, POLICY, (*base, exact))).decision is ProductionReadinessDecision.READY_FOR_HUMAN_GATE
    report = _report(build_production_integration_bundle(PLAN, POLICY, (*base, outside)))
    assert ProductionReadinessReason.EVIDENCE_TTL_EXCEEDED in {
        finding.reason for finding in report.findings if finding.check is check
    }


def test_lookup_and_disable_semantics_reject_noop_counterexamples() -> None:
    lookup = _facts(ProductionIntegrationCheck.PROVIDER_RECEIPT_LOOKUP)
    with pytest.raises(ValidationError, match="unknown query"):
        ProviderReceiptLookupFacts.model_validate(
            {**lookup.model_dump(), "unknown_query_sha256": lookup.known_query_sha256}
        )
    with pytest.raises(ValidationError, match="must not return"):
        ProviderReceiptLookupFacts.model_validate(
            {**lookup.model_dump(), "unknown_result_sha256": lookup.expected_receipt_sha256}
        )
    disable = _facts(ProductionIntegrationCheck.ROLLBACK_DISABLE)
    with pytest.raises(ValidationError, match="must change"):
        RollbackDisableFacts.model_validate(
            {**disable.model_dump(), "active_state_sha256": disable.disabled_state_sha256}
        )


@pytest.mark.parametrize("check", REQUIRED_PRODUCTION_INTEGRATION_CHECKS)
def test_each_missing_check_stops(check: ProductionIntegrationCheck) -> None:
    evidence = tuple(item for item in _bundle().evidence if item.check is not check)
    report = _report(build_production_integration_bundle(PLAN, POLICY, evidence))
    assert report.failed_checks == (check,)
    assert report.findings[0].reason is ProductionReadinessReason.MISSING_EVIDENCE


@pytest.mark.parametrize("check", REQUIRED_PRODUCTION_INTEGRATION_CHECKS)
def test_each_exact_duplicate_check_stops_without_deduplication(
    check: ProductionIntegrationCheck,
) -> None:
    evidence = (*_bundle().evidence, _evidence(check, evidence_id=f"duplicate-{check.value.replace('_', '-')}"))
    report = _report(build_production_integration_bundle(PLAN, POLICY, evidence))
    assert check in report.failed_checks
    reasons = {item.reason for item in report.findings if item.check is check}
    assert ProductionReadinessReason.DUPLICATE_EVIDENCE in reasons


def test_conflicting_duplicate_and_cross_check_duplicate_id_stop() -> None:
    first, second = REQUIRED_PRODUCTION_INTEGRATION_CHECKS[:2]
    evidence = list(_bundle().evidence)
    evidence.append(_evidence(first, success=False, evidence_id="conflicting-first"))
    evidence[evidence.index(next(item for item in evidence if item.check is second))] = _evidence(
        second, evidence_id=evidence[0].evidence_id
    )
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert ProductionReadinessReason.CONFLICTING_EVIDENCE in {
        item.reason for item in report.findings if item.check is first
    }
    assert first in report.failed_checks and second in report.failed_checks


def test_conflicting_duplicate_input_order_cannot_change_bundle_or_report_hash() -> None:
    check = ProductionIntegrationCheck.PROVIDER_CONDITIONAL_MUTATION
    base = tuple(item for item in _bundle().evidence if item.check is not check)
    passing = _evidence(check, evidence_id="duplicate-a")
    failing = _evidence(check, success=False, evidence_id="duplicate-b")
    forward = build_production_integration_bundle(
        PLAN, POLICY, (*base, passing, failing)
    )
    reverse = build_production_integration_bundle(
        PLAN, POLICY, (*base, failing, passing)
    )
    assert forward == reverse
    assert forward.bundle_sha256 == reverse.bundle_sha256
    assert _report(forward) == _report(reverse)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"observed_at": AT + timedelta(microseconds=1), "expires_at": AT + timedelta(hours=1)}, ProductionReadinessReason.EVIDENCE_FUTURE),
        ({"observed_at": AT - timedelta(hours=1), "expires_at": AT}, ProductionReadinessReason.EVIDENCE_EXPIRED),
        ({"observed_at": AT - timedelta(days=2), "expires_at": AT + timedelta(seconds=1)}, ProductionReadinessReason.EVIDENCE_TTL_EXCEEDED),
    ],
)
def test_future_expired_and_excessive_ttl_stop(
    kwargs: dict[str, datetime], reason: ProductionReadinessReason
) -> None:
    check = ProductionIntegrationCheck.TRUSTED_CLOCK
    evidence = [item for item in _bundle().evidence if item.check is not check]
    evidence.append(_evidence(check, **kwargs))
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert reason in {item.reason for item in report.findings if item.check is check}


@pytest.mark.parametrize("check", REQUIRED_PRODUCTION_INTEGRATION_CHECKS)
def test_wrong_runner_key_stops_for_each_check(
    check: ProductionIntegrationCheck,
) -> None:
    attacker = Ed25519PrivateKey.generate()
    evidence = [item for item in _bundle().evidence if item.check is not check]
    evidence.append(_evidence(check, signer=attacker))
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert ProductionReadinessReason.EVIDENCE_SIGNATURE_INVALID in {
        item.reason for item in report.findings if item.check is check
    }


def test_wrong_runner_issuer_stops() -> None:
    check = ProductionIntegrationCheck.TRUSTED_CLOCK
    evidence = [item for item in _bundle().evidence if item.check is not check]
    evidence.append(_evidence(check, issuer="wrong-runner"))
    report = _report(build_production_integration_bundle(PLAN, POLICY, tuple(evidence)))
    assert ProductionReadinessReason.EVIDENCE_SIGNATURE_INVALID in {
        item.reason for item in report.findings if item.check is check
    }


def test_strict_models_reject_urls_credentials_notes_and_self_approval() -> None:
    values = _facts(ProductionIntegrationCheck.TRUSTED_CLOCK).model_dump()
    for field, value in (
        ("url", "https://provider.invalid"),
        ("credential", "secret"),
        ("notes", "trust me"),
        ("approved", True),
        ("waiver_reason", "accepted risk"),
    ):
        with pytest.raises(ValidationError):
            TrustedClockFacts.model_validate({**values, field: value})


def _signed_gate(report=None, bundle=None, *, plan: ProductionIntegrationPlan = PLAN, at: datetime = AT):
    active_bundle = bundle or _bundle(plan=plan, at=at)
    active_report = report or _report(active_bundle, plan=plan, at=at)
    tco = sign_production_tco_qa_attestation(
        active_report,
        TCO_PRIVATE,
        issuer="p15-tco",
        decision=ReadinessAttestationDecision.ACCEPT,
        issued_at=at,
        expires_at=at + timedelta(minutes=30),
    )
    human = sign_production_human_environment_approval(
        active_report,
        plan,
        HUMAN_PRIVATE,
        issuer="p15-human",
        decision=EnvironmentApprovalDecision.APPROVE,
        decision_record_sha256=_digest(801),
        issued_at=at,
        expires_at=at + timedelta(minutes=20),
    )
    return active_report, active_bundle, tco, human


def test_credential_blind_tco_attestation_verifier() -> None:
    report, _, tco, _ = _signed_gate()
    assert verify_production_tco_qa_attestation(
        tco, report, POLICY, TRUST, at=AT
    )
    assert not verify_production_tco_qa_attestation(
        tco, report, POLICY, TRUST, at=tco.expires_at
    )

    rejected = sign_production_tco_qa_attestation(
        report,
        TCO_PRIVATE,
        issuer="p15-tco",
        decision=ReadinessAttestationDecision.REJECT,
        issued_at=AT,
        expires_at=AT + timedelta(minutes=30),
    )
    assert not verify_production_tco_qa_attestation(
        rejected, report, POLICY, TRUST, at=AT
    )

    other_tco_private = Ed25519PrivateKey.generate()
    substituted_trust = TRUST.model_copy(
        update={
            "tco_qa": create_verification_key(
                other_tco_private.public_key(),
                issuer="substituted-p15-tco",
                role=SigningRole.TCO_QA,
            )
        }
    )
    assert not verify_production_tco_qa_attestation(
        tco, report, POLICY, substituted_trust, at=AT
    )


def test_qa_human_controller_signatures_are_distinct_and_cross_bound() -> None:
    report, bundle, tco, human = _signed_gate()
    authorization = authorize_production_bootstrap(
        report,
        bundle,
        PLAN,
        POLICY,
        TRUST,
        tco,
        human,
        CONTROLLER_PRIVATE,
        issuer="p15-controller",
        issued_at=AT,
        expires_at=AT + timedelta(minutes=3),
    )
    assert len(
        {
            TRUST.controller.key_id_sha256,
            TRUST.provider_conformance.key_id_sha256,
            TRUST.independent_probe.key_id_sha256,
            TRUST.security_auditor.key_id_sha256,
            TRUST.storage_auditor.key_id_sha256,
            TRUST.time_auditor.key_id_sha256,
            TRUST.network_auditor.key_id_sha256,
            TRUST.recovery_auditor.key_id_sha256,
            TRUST.tco_qa.key_id_sha256,
            TRUST.environment_human.key_id_sha256,
        }
    ) == 10
    pins = ProductionReadinessAuthorityPins(
        expected_trust_store_sha256=hash_production_integration_trust_store(TRUST),
        expected_integration_policy_sha256=hash_production_integration_policy(POLICY),
        expected_plan_sha256=PLAN.plan_sha256,
        expected_report_sha256=report.report_sha256,
        expected_authorization_sha256=hash_production_bootstrap_authorization(authorization),
    )
    assert verify_production_bootstrap_authorization(
        authorization,
        report,
        bundle,
        PLAN,
        POLICY,
        TRUST,
        tco,
        human,
        pins,
        at=AT + timedelta(minutes=1),
    )
    assert not verify_production_bootstrap_authorization(
        authorization,
        report,
        bundle,
        PLAN,
        POLICY,
        TRUST,
        tco,
        human,
        pins.model_copy(update={"expected_plan_sha256": _digest(999)}),
        at=AT + timedelta(minutes=1),
    )


def test_human_approval_cannot_override_stop_or_expiry() -> None:
    stop_bundle = build_production_integration_bundle(PLAN, POLICY, ())
    stop_report, _, tco, human = _signed_gate(_report(stop_bundle), stop_bundle)
    with pytest.raises(ProductionReadinessInputError, match="READY_FOR_HUMAN_GATE"):
        authorize_production_bootstrap(
            stop_report,
            stop_bundle,
            PLAN,
            POLICY,
            TRUST,
            tco,
            human,
            CONTROLLER_PRIVATE,
            issuer="p15-controller",
            issued_at=AT,
            expires_at=AT + timedelta(minutes=1),
        )
    report, bundle, tco, human = _signed_gate()
    with pytest.raises(ProductionReadinessInputError, match="expire before every input"):
        authorize_production_bootstrap(
            report,
            bundle,
            PLAN,
            POLICY,
            TRUST,
            tco,
            human,
            CONTROLLER_PRIVATE,
            issuer="p15-controller",
            issued_at=AT,
            expires_at=AT + timedelta(minutes=21),
        )


def _reconciliation_facts(
    terminal: P13TerminalState,
    observed: ProviderObservedState,
    *,
    p13_result_sha256: str | None = None,
) -> ProductionReconciliationFacts:
    return sign_production_reconciliation_facts(
        RECOVERY_PRIVATE,
        issuer=TRUST.recovery_auditor.issuer,
        plan_sha256=PLAN.plan_sha256,
        p13_store_identity_sha256=_digest(906),
        p13_result_sha256=p13_result_sha256 or _digest(901),
        p13_terminal_state=terminal,
        stopped_revision=3,
        stopped_head_sha256=_digest(907),
        stop_reason_sha256=_digest(908),
        provider_observed_state=observed,
        provider_result_receipt_sha256=_digest(902),
        journaled_provider_receipt_sha256=_digest(902),
        provider_probe_receipt_sha256=_digest(903),
        receipt_lookup_evidence_sha256=_digest(904),
        independent_readback_evidence_sha256=_digest(905),
        observed_at=AT,
        expires_at=AT + timedelta(hours=1),
    )


@pytest.mark.parametrize(
    ("terminal", "observed", "action", "reason"),
    [
        (P13TerminalState.UNKNOWN, ProviderObservedState.APPLIED, ProductionReconciliationAction.REQUEST_HUMAN_DISABLE, ProductionReconciliationReason.UNKNOWN_NOT_PROMOTED),
        (P13TerminalState.STOP, ProviderObservedState.APPLIED, ProductionReconciliationAction.KEEP_STOP, ProductionReconciliationReason.EXISTING_STOP_PRESERVED),
        (P13TerminalState.UNKNOWN, ProviderObservedState.NOT_APPLIED, ProductionReconciliationAction.KEEP_STOP, ProductionReconciliationReason.NON_APPLIED_FACT_PRESERVED),
        (P13TerminalState.UNKNOWN, ProviderObservedState.AMBIGUOUS, ProductionReconciliationAction.MANUAL_REMEDIATION, ProductionReconciliationReason.AMBIGUOUS_PROVIDER_STATE),
    ],
)
def test_reconciliation_never_promotes_unknown(
    terminal: P13TerminalState,
    observed: ProviderObservedState,
    action: ProductionReconciliationAction,
    reason: ProductionReconciliationReason,
) -> None:
    report = evaluate_production_reconciliation(
        _reconciliation_facts(terminal, observed), at=AT
    )
    assert report.action is action
    assert report.reason is reason
    assert report.decision is ProductionReadinessDecision.STOP


def test_applied_reconciliation_requires_exact_journal_receipt() -> None:
    values = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.APPLIED
    ).model_dump()
    values["journaled_provider_receipt_sha256"] = _digest(999)
    values["facts_sha256"] = _digest(998)
    with pytest.raises(ValidationError, match="exact journaled receipt"):
        ProductionReconciliationFacts.model_validate(values)


def _ledger(tmp_path: Path):
    anchors: dict[str, tuple[int, str]] = {}

    def commit(revision: int, digest: str) -> None:
        current = anchors.get("ledger")
        if current is not None and (
            revision < current[0]
            or (revision == current[0] and digest != current[1])
        ):
            raise ValueError("non-monotonic reconciliation anchor")
        anchors["ledger"] = (revision, digest)

    def read() -> str:
        return anchors["ledger"][1]

    ledger = ProductionReconciliationLedger.create(
        tmp_path / "reconciliation.sqlite",
        store_id_sha256=_digest(950),
        plan_sha256=PLAN.plan_sha256,
        trust_store=TRUST,
        state_authentication_key=b"p15-reconciliation-test-auth-key-32bytes",
        anchor_commit=commit,
        anchor_read=read,
    )
    return ledger, anchors, commit, read


def test_reconciliation_ledger_is_append_only_duplicate_neutral_and_reset_bound(
    tmp_path: Path,
) -> None:
    ledger, anchors, _, _ = _ledger(tmp_path)
    facts = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.NOT_APPLIED
    )
    report = evaluate_production_reconciliation(facts, at=AT)
    record = ledger.append(facts, report, at=AT)
    anchor_after = anchors["ledger"]
    assert ledger.append(facts, report, at=AT) == record
    assert anchors["ledger"] == anchor_after
    assert ledger.verifies_for_reset(
        record.record_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=facts.stopped_head_sha256,
        stop_reason_sha256=facts.stop_reason_sha256,
        at=AT,
    )
    assert not ledger.verifies_for_reset(
        record.record_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=_digest(999),
        stop_reason_sha256=facts.stop_reason_sha256,
        at=AT,
    )


@pytest.mark.parametrize(
    "observed",
    (ProviderObservedState.APPLIED, ProviderObservedState.AMBIGUOUS),
)
def test_reconciliation_ledger_blocks_reset_until_inactive_readback(
    tmp_path: Path, observed: ProviderObservedState
) -> None:
    ledger, _, _, _ = _ledger(tmp_path)
    facts = _reconciliation_facts(P13TerminalState.UNKNOWN, observed)
    report = evaluate_production_reconciliation(facts, at=AT)
    record = ledger.append(facts, report, at=AT)
    assert not ledger.verifies_for_reset(
        record.record_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=facts.stopped_head_sha256,
        stop_reason_sha256=facts.stop_reason_sha256,
        at=AT,
    )
    with sqlite3.connect(tmp_path / "reconciliation.sqlite") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE reconciliation_records SET report_sha256=?",
                (_digest(999),),
            )


def test_reconciliation_ledger_rejects_conflict_wrong_key_and_expiry(
    tmp_path: Path,
) -> None:
    ledger, _, _, _ = _ledger(tmp_path)
    facts = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.NOT_APPLIED
    )
    report = evaluate_production_reconciliation(facts, at=AT)
    ledger.append(facts, report, at=AT)
    attacker = Ed25519PrivateKey.generate()
    conflicting = sign_production_reconciliation_facts(
        attacker,
        issuer=TRUST.recovery_auditor.issuer,
        plan_sha256=PLAN.plan_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        p13_result_sha256=facts.p13_result_sha256,
        p13_terminal_state=P13TerminalState.UNKNOWN,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=facts.stopped_head_sha256,
        stop_reason_sha256=facts.stop_reason_sha256,
        provider_observed_state=ProviderObservedState.AMBIGUOUS,
        provider_result_receipt_sha256=_digest(960),
        journaled_provider_receipt_sha256=_digest(961),
        provider_probe_receipt_sha256=_digest(962),
        receipt_lookup_evidence_sha256=_digest(963),
        independent_readback_evidence_sha256=_digest(964),
        observed_at=AT,
        expires_at=AT + timedelta(hours=1),
    )
    conflicting_report = evaluate_production_reconciliation(conflicting, at=AT)
    with pytest.raises(ProductionReadinessInputError, match="authoritative"):
        ledger.append(conflicting, conflicting_report, at=AT)
    with sqlite3.connect(tmp_path / "reconciliation.sqlite") as connection:
        record_sha256 = connection.execute(
            "SELECT record_sha256 FROM reconciliation_records"
        ).fetchone()[0]
    assert not ledger.verifies_for_reset(
        record_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=facts.stopped_head_sha256,
        stop_reason_sha256=facts.stop_reason_sha256,
        at=facts.expires_at,
    )


def test_reconciliation_ledger_rejects_correctly_signed_conflicting_fact(
    tmp_path: Path,
) -> None:
    ledger, _, _, _ = _ledger(tmp_path)
    original = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.NOT_APPLIED
    )
    ledger.append(original, evaluate_production_reconciliation(original, at=AT), at=AT)
    conflict = sign_production_reconciliation_facts(
        RECOVERY_PRIVATE,
        issuer=TRUST.recovery_auditor.issuer,
        plan_sha256=PLAN.plan_sha256,
        p13_store_identity_sha256=original.p13_store_identity_sha256,
        p13_result_sha256=original.p13_result_sha256,
        p13_terminal_state=P13TerminalState.UNKNOWN,
        stopped_revision=original.stopped_revision,
        stopped_head_sha256=original.stopped_head_sha256,
        stop_reason_sha256=original.stop_reason_sha256,
        provider_observed_state=ProviderObservedState.AMBIGUOUS,
        provider_result_receipt_sha256=_digest(980),
        journaled_provider_receipt_sha256=_digest(981),
        provider_probe_receipt_sha256=_digest(982),
        receipt_lookup_evidence_sha256=_digest(983),
        independent_readback_evidence_sha256=_digest(984),
        observed_at=AT,
        expires_at=AT + timedelta(hours=1),
    )
    with pytest.raises(ProductionReadinessInputError, match="cannot have conflicting"):
        ledger.append(
            conflict,
            evaluate_production_reconciliation(conflict, at=AT),
            at=AT,
        )


def test_reconciliation_ledger_rejects_direct_state_tamper(tmp_path: Path) -> None:
    ledger, _, _, _ = _ledger(tmp_path)
    facts = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.NOT_APPLIED
    )
    record = ledger.append(
        facts, evaluate_production_reconciliation(facts, at=AT), at=AT
    )
    with sqlite3.connect(tmp_path / "reconciliation.sqlite") as connection:
        connection.execute(
            "UPDATE reconciliation_meta SET value=? WHERE key='state_mac_sha256'",
            (_digest(985),),
        )
        connection.commit()
    assert not ledger.verifies_for_reset(
        record.record_sha256,
        p13_store_identity_sha256=facts.p13_store_identity_sha256,
        stopped_revision=facts.stopped_revision,
        stopped_head_sha256=facts.stopped_head_sha256,
        stop_reason_sha256=facts.stop_reason_sha256,
        at=AT,
    )


def test_reconciliation_ledger_rejects_anchor_rollback_beyond_one_revision(
    tmp_path: Path,
) -> None:
    ledger, anchors, _, _ = _ledger(tmp_path)
    initial_anchor = anchors["ledger"]
    first = _reconciliation_facts(
        P13TerminalState.UNKNOWN,
        ProviderObservedState.NOT_APPLIED,
        p13_result_sha256=_digest(986),
    )
    ledger.append(first, evaluate_production_reconciliation(first, at=AT), at=AT)
    second = _reconciliation_facts(
        P13TerminalState.UNKNOWN,
        ProviderObservedState.AMBIGUOUS,
        p13_result_sha256=_digest(987),
    )
    second_record = ledger.append(
        second, evaluate_production_reconciliation(second, at=AT), at=AT
    )
    anchors["ledger"] = initial_anchor
    assert not ledger.verifies_for_reset(
        second_record.record_sha256,
        p13_store_identity_sha256=second.p13_store_identity_sha256,
        stopped_revision=second.stopped_revision,
        stopped_head_sha256=second.stopped_head_sha256,
        stop_reason_sha256=second.stop_reason_sha256,
        at=AT,
    )


def test_reconciliation_ledger_recovers_exact_one_ahead_anchor(tmp_path: Path) -> None:
    anchors: dict[str, tuple[int, str]] = {}
    fail_revision_one = True

    def commit(revision: int, digest: str) -> None:
        nonlocal fail_revision_one
        if revision == 1 and fail_revision_one:
            fail_revision_one = False
            raise RuntimeError("synthetic anchor outage")
        anchors["ledger"] = (revision, digest)

    def read() -> str:
        return anchors["ledger"][1]

    path = tmp_path / "one-ahead.sqlite"
    key = b"p15-reconciliation-test-auth-key-32bytes"
    ledger = ProductionReconciliationLedger.create(
        path,
        store_id_sha256=_digest(970),
        plan_sha256=PLAN.plan_sha256,
        trust_store=TRUST,
        state_authentication_key=key,
        anchor_commit=commit,
        anchor_read=read,
    )
    facts = _reconciliation_facts(
        P13TerminalState.UNKNOWN, ProviderObservedState.AMBIGUOUS
    )
    report = evaluate_production_reconciliation(facts, at=AT)
    with pytest.raises(RuntimeError, match="anchor outage"):
        ledger.append(facts, report, at=AT)
    reopened = ProductionReconciliationLedger(
        path,
        expected_store_id_sha256=_digest(970),
        expected_plan_sha256=PLAN.plan_sha256,
        trust_store=TRUST,
        state_authentication_key=key,
        anchor_commit=commit,
        anchor_read=read,
    )
    record = reopened.append(facts, report, at=AT)
    assert record.revision == 1
    assert anchors["ledger"][0] == 1


def test_no_model_serialization_contains_url_or_credential() -> None:
    serialized = "".join(
        (
            PLAN.model_dump_json(),
            POLICY.model_dump_json(),
            TRUST.model_dump_json(),
            _bundle().model_dump_json(),
            _report().model_dump_json(),
        )
    ).lower()
    assert "https://" not in serialized
    assert "credential" not in serialized
    assert "password" not in serialized
    assert "private_key" not in serialized


def test_p15_schemas_expose_no_url_secret_waiver_or_self_approval_field() -> None:
    prohibited = {
        "url",
        "uri",
        "endpoint",
        "credential",
        "api_key",
        "token",
        "password",
        "cookie",
        "oauth",
        "private_key",
        "notes",
        "waiver",
        "approved",
        "ready",
        "production_go",
    }
    selected = tuple((ROOT / "schemas").glob("*production*.schema.json"))
    selected = selected + tuple((ROOT / "schemas").glob("*readiness*.schema.json"))
    selected = selected + tuple((ROOT / "schemas").glob("*reconciliation*.schema.json"))
    assert selected

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

    for path in set(selected):
        inspect(json.loads(path.read_text(encoding="utf-8")))


def _write_cli_inputs(
    directory: Path, bundle: ProductionIntegrationEvidenceBundle
) -> tuple[Path, Path, Path, Path]:
    paths = tuple(directory / name for name in ("bundle.json", "plan.json", "policy.json", "trust.json"))
    for path, model in zip(paths, (bundle, PLAN, POLICY, TRUST), strict=True):
        path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return paths  # type: ignore[return-value]


def test_cli_is_offline_and_uses_stop_exit_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_path, plan_path, policy_path, trust_path = _write_cli_inputs(
        tmp_path, build_production_integration_bundle(PLAN, POLICY, ())
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("P15 CLI attempted an external operation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    result = run_cli(
        [
            "evaluate-production-readiness",
            str(bundle_path),
            "--plan",
            str(plan_path),
            "--policy",
            str(policy_path),
            "--trust-store",
            str(trust_path),
            "--at",
            AT.isoformat(),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 3
    assert output["decision"] == "stop"
    assert len(output["failed_checks"]) == 11


def test_reconciliation_cli_is_offline_and_always_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    facts_path = tmp_path / "reconciliation-facts.json"
    facts_path.write_text(
        _reconciliation_facts(
            P13TerminalState.UNKNOWN, ProviderObservedState.AMBIGUOUS
        ).model_dump_json(indent=2)
        + "\n",
        encoding="utf-8",
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("P15 reconciliation CLI attempted an external operation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    result = run_cli(
        [
            "evaluate-production-reconciliation",
            str(facts_path),
            "--at",
            AT.isoformat(),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 3
    assert output["decision"] == "stop"
    assert output["action"] == "manual_remediation"


def test_cli_ready_exit_zero_and_duplicate_json_key_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_path, plan_path, policy_path, trust_path = _write_cli_inputs(tmp_path, _bundle())
    arguments = [
        "evaluate-production-readiness",
        str(bundle_path),
        "--plan",
        str(plan_path),
        "--policy",
        str(policy_path),
        "--trust-store",
        str(trust_path),
        "--at",
        AT.isoformat(),
    ]
    assert run_cli(arguments) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "ready_for_human_gate"
    bundle_path.write_text('{"schema_version":"1.0","schema_version":"1.0"}\n', encoding="utf-8")
    assert run_cli(arguments) == 2
    captured = capsys.readouterr()
    assert "duplicate JSON key: schema_version" in captured.err


def test_cli_help_has_no_external_mutation_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        run_cli(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    for forbidden in ("provider-url", "credential", "oauth", "billing", "publish", "deploy"):
        assert forbidden not in help_text
