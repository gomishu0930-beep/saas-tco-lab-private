from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import test_measurement_integrity as measurement_fixtures
import test_launch_handoff as p16_fixtures
import test_production_readiness as p15_fixtures
import test_release_assurance as assurance_fixtures
import test_goldset as gold_fixtures
import saas_preflight.production_consumer as production_consumer_module
from saas_preflight.control_cycle import (
    LeaseScope,
    SigningRole,
    _build_lease,
    create_verification_key,
    sign_gold_report_attestation,
)
from saas_preflight.goldset import evaluate_goldset
from saas_preflight.external_actions import (
    ActionEnvironment,
    ActionExecutionClaim,
    ActionResult,
    ExternalAction,
    ExternalActionAuthority,
    ExternalActionExecutionGuard,
    ExternalActionInputError,
    ExternalActionPolicy,
    ExternalActionRuntime,
    ExternalActionTargetRule,
    ExternalActionTrustStore,
    build_external_action_request,
    hash_external_action_policy,
    hash_action_execution_claim,
    hash_external_action_trust_store,
    issue_controller_execution_grant,
    revoke_execution_grant,
    sign_action_receipt,
    sign_human_execution_approval,
)
from saas_preflight.measurement_integrity import (
    MeasurementAuthorityPins,
    MeasurementBoundDossier,
    MeasurementDataset,
    MeasurementIntegrityRuntime,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    sign_measurement_bundle_index,
    sign_measurement_run_plan,
    sign_producer_attestation,
)
from saas_preflight.launch_handoff import (
    LaunchArtifactComponent,
    LaunchArtifactComponentKind,
    LaunchHandoffGate,
    LaunchHandoffRequirement,
    hash_launch_artifact_components,
    hash_launch_handoff_authority,
)
from saas_preflight.launch_semantics import (
    AffiliateSemanticPacket,
    DeploymentPublicationSemanticPacket,
    DeploymentReadinessFacts,
    DeploymentReadinessRecord,
    GoldSemanticPacket,
    LaunchSemanticPacket,
    LaunchSemanticScope,
    MeasurementSemanticPacket,
    ProductionSemanticPacket,
    PublicationContentReadback,
    PublicationDisclosureReadback,
    PublicationIndexabilityReadback,
    PublicationReadinessFacts,
    PublicationReadinessRecord,
    RightsSemanticPacket,
    build_launch_semantic_authority_pins,
    evaluate_launch_semantics,
    hash_launch_semantic_authority_pins,
    hash_launch_semantic_packet,
    sign_deployment_readiness_record,
    sign_publication_readiness_record,
)
from saas_preflight.production_consumer import (
    ConsumptionState,
    GlobalStopStore,
    ProductionConsumer,
    ProductionConsumptionResult,
    ProductionConsumerClockRequest,
    ProductionAuthorityRootRequest,
    ProductionConsumerError,
    ProductionConsumerPolicy,
    ProductionConsumerRuntime,
    ProductionConsumerTrustStore,
    ProductionSignatureScope,
    ProviderOperation,
    ProviderOutcome,
    ProviderDispatchToken,
    ProviderProbeReceipt,
    ProviderResultReceipt,
    ProviderTargetRule,
    SubprocessProviderAdapter,
    _ISOLATED_ADAPTER_LAUNCHER,
    _file_sha256,
    _build_signed_model,
    _canonical_json_bytes,
    _canonical_sha256,
    build_production_consumption_request,
    hash_measurement_authority_pins,
    hash_adapter_dependency_closure,
    hash_production_consumer_policy,
    hash_production_consumer_trust_store,
    production_adapter_dependency_paths,
    sign_global_stop_reset,
    sign_production_consumer_clock_attestation,
    sign_production_authority_roots,
    write_raw_ed25519_private_key,
    write_verification_key,
)
from saas_preflight.production_readiness import (
    EnvironmentApprovalDecision,
    P13TerminalState,
    ProductionEvidenceProvenance,
    ProductionIntegrationCheck,
    ProductionReconciliationLedger,
    ProductionReadinessAuthorityPins,
    ProviderObservedState,
    REQUIRED_PRODUCTION_INTEGRATION_CHECKS,
    ReadinessAttestationDecision,
    authorize_production_bootstrap,
    build_production_integration_bundle,
    evaluate_production_reconciliation,
    hash_production_bootstrap_authorization,
    hash_production_integration_policy,
    hash_production_integration_evidence,
    hash_production_integration_trust_store,
    hash_production_readiness_report,
    hash_production_tco_qa_attestation,
    sign_production_human_environment_approval,
    sign_production_reconciliation_facts,
    sign_production_tco_qa_attestation,
)
from saas_preflight.readiness_builder import (
    AffiliateDecisionBatch,
    AffiliateProgramDecision,
    AffiliateReviewDecision,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)
from saas_preflight.release import ApprovalDecision
from saas_preflight.release_assurance import (
    evaluate_local_assurance,
    evaluate_public_release_assurance,
    hash_assurance_policy,
)
from saas_preflight.traction_control import P12AuthorityPacket


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "saas_preflight" / "synthetic_provider_adapter.py"
PROBE_SCRIPT = ROOT / "src" / "saas_preflight" / "synthetic_provider_probe.py"
POSTCONDITION_SCHEMA = (
    ROOT / "examples" / "synthetic-provider-postcondition.schema.json"
)
PYTHON_EXECUTABLE = Path(sys.executable).resolve()
AT = assurance_fixtures.AT + timedelta(minutes=4)
STATE_KEY = b"synthetic-production-state-authentication-key"
STORE_ID = "d" * 64
TARGET = "3" * 64
PRE_STATE = "6" * 64
POST_STATE = "7" * 64
DISABLED_STATE = "8" * 64


def _retarget_measurement_bundle(bundle: dict) -> None:
    release_identity_sha256 = measurement_fixtures._sha("release-p10")
    deployment_candidate_sha256 = hashlib.sha256(
        POSTCONDITION_SCHEMA.read_bytes()
    ).hexdigest()
    definition = bundle["plan"].definition.model_copy(
        update={
            "fault_target_release_sha256": release_identity_sha256,
            "fault_target_artifact_sha256": "a" * 64,
            "fault_target_schema_sha256": deployment_candidate_sha256,
        }
    )
    plan = sign_measurement_run_plan(
        definition,
        bundle["keys"]["human"],
        issuer=bundle["plan"].issuer,
        issued_at=bundle["plan"].issued_at,
        expires_at=bundle["plan"].expires_at,
    )
    operations = bundle["operations"].model_copy(
        update={
            "fault_exercises": tuple(
                row.model_copy(
                    update={
                        "target_release_sha256": release_identity_sha256,
                        "target_artifact_sha256": "a" * 64,
                        "target_schema_sha256": deployment_candidate_sha256,
                    }
                )
                for row in bundle["operations"].fault_exercises
            )
        }
    )
    issued_at = measurement_fixtures.END_UTC + timedelta(hours=2)
    expires_at = measurement_fixtures.AT + timedelta(days=7)
    attestations = {}
    for dataset, label, offset in (
        (MeasurementDataset.DEMAND, "demand", 0),
        (MeasurementDataset.COHORT, "cohort", 1),
        (MeasurementDataset.OPERATIONS, "operations", 2),
    ):
        batch = operations if label == "operations" else bundle[label]
        attestations[label] = sign_producer_attestation(
            plan,
            dataset,
            batch,
            measurement_fixtures._coverage(batch, label),
            bundle["keys"][label],
            issuer=f"{label}-producer",
            issued_at=issued_at + timedelta(minutes=offset),
            expires_at=expires_at,
        )
    index = sign_measurement_bundle_index(
        plan,
        bundle["demand"],
        bundle["cohort"],
        operations,
        attestations["demand"],
        attestations["cohort"],
        attestations["operations"],
        bundle["keys"]["indexer"],
        issuer="measurement-indexer",
        captured_at=measurement_fixtures.END_UTC,
        issued_at=measurement_fixtures.END_UTC + timedelta(hours=3),
        expires_at=expires_at,
    )
    pins = MeasurementAuthorityPins(
        expected_policy_sha256=hash_measurement_policy(bundle["policy"]),
        expected_trust_store_sha256=hash_measurement_trust_store(bundle["trust"]),
        expected_run_id=plan.definition.run_id,
        expected_bundle_index_sha256=hash_signed_artifact(index),
    )
    bundle.update(
        {
            "plan": plan,
            "operations": operations,
            "demand_attestation": attestations["demand"],
            "cohort_attestation": attestations["cohort"],
            "operations_attestation": attestations["operations"],
            "index": index,
            "pins": pins,
            "runtime": MeasurementIntegrityRuntime(
                bundle["policy"], bundle["trust"], bundle["keys"]["qa"], pins
            ),
        }
    )


def _consumer_clock_attest(case, clock):
    def attest(request: ProductionConsumerClockRequest):
        observed_at = clock()
        return sign_production_consumer_clock_attestation(
            request,
            case["p15"]["trust"],
            p15_fixtures.TIME_PRIVATE,
            observed_at=observed_at,
            issued_at=observed_at,
            expires_at=observed_at + timedelta(seconds=30),
        )

    return attest


def _current_authority_roots(case, *, revision: int = 1, at=AT):
    def resolve(request: ProductionAuthorityRootRequest):
        return sign_production_authority_roots(
            request,
            case["p15"]["trust"],
            p15_fixtures.STORAGE_PRIVATE,
            revision=revision,
            repository_acceptance_authority_sha256=(
                case["p16"]["repository_authority_root"]
            ),
            launch_handoff_authority_sha256=case["p16"]["authority_root"],
            launch_semantic_authority_sha256=(
                case["p16"]["semantic_authority_root"]
            ),
            observed_at=at,
            issued_at=at,
            expires_at=at + timedelta(seconds=30),
        )

    return resolve


def _measurement(monkeypatch):
    measurement_at = assurance_fixtures.AT + timedelta(minutes=3)
    end = measurement_at.astimezone(measurement_fixtures.TOKYO).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_utc = end.astimezone(measurement_fixtures.timezone.utc)
    start = end - timedelta(days=30)
    monkeypatch.setattr(measurement_fixtures, "START", start)
    monkeypatch.setattr(measurement_fixtures, "END", end)
    monkeypatch.setattr(measurement_fixtures, "START_UTC", start.astimezone(measurement_fixtures.timezone.utc))
    monkeypatch.setattr(measurement_fixtures, "END_UTC", end_utc)
    monkeypatch.setattr(measurement_fixtures, "AT", measurement_at)
    original_demand = measurement_fixtures._demand

    def production_scale_demand():
        demand = original_demand()
        summary_values = demand.summary.model_dump()
        summary_values["clusters"] = tuple(
            row.__class__(
                **{
                    **row.model_dump(),
                    "deduplicated_monthly_volume": (
                        row.deduplicated_monthly_volume * Decimal("10000")
                    ),
                }
            )
            for row in demand.summary.clusters
        )
        return demand.__class__(
            **{
                **demand.model_dump(exclude={"summary"}),
                "summary": demand.summary.__class__(**summary_values),
            }
        )

    monkeypatch.setattr(measurement_fixtures, "_demand", production_scale_demand)
    bundle = measurement_fixtures._bundle()
    _retarget_measurement_bundle(bundle)
    cohort = bundle["cohort"]
    extra_sessions = tuple(
        measurement_fixtures.QualifiedSession(
            session_id_sha256=measurement_fixtures._sha(f"session:{number}"),
            qualified_at=start.astimezone(measurement_fixtures.timezone.utc)
            + timedelta(days=1, minutes=number),
        )
        for number in range(4, 1000)
    )
    extra_outbound = tuple(
        measurement_fixtures.ValidOutboundClick(
            click_id_sha256=measurement_fixtures._sha(f"outbound:{number}"),
            session_id_sha256=measurement_fixtures._sha(f"session:{number}"),
            partner_id=("partner-a", "partner-b", "partner-c")[number % 3],
            clicked_at=start.astimezone(measurement_fixtures.timezone.utc)
            + timedelta(days=2, minutes=number),
        )
        for number in range(4, 1000)
    )
    transactions = tuple(
        row.__class__(**{**row.model_dump(), "amount": row.amount * Decimal("1000")})
        for row in cohort.transactions
    )
    payout_rows = tuple(
        row.__class__(**{**row.model_dump(), "amount": row.amount * Decimal("1000")})
        for row in cohort.payout_rows
    )
    statement = cohort.payout_statement.__class__(
        **{
            **cohort.payout_statement.model_dump(),
            "gross_amount": cohort.payout_statement.gross_amount * Decimal("1000"),
            "net_amount": cohort.payout_statement.net_amount * Decimal("1000"),
        }
    )
    cohort = cohort.__class__(
        **{
            **cohort.model_dump(
                exclude={
                    "qualified_sessions",
                    "valid_outbound_clicks",
                    "transactions",
                    "payout_rows",
                    "payout_statement",
                }
            ),
            "qualified_sessions": cohort.qualified_sessions + extra_sessions,
            "valid_outbound_clicks": cohort.valid_outbound_clicks + extra_outbound,
            "transactions": transactions,
            "payout_rows": payout_rows,
            "payout_statement": statement,
        }
    )
    measurement_fixtures._replace_cohort(
        bundle, cohort, measurement_fixtures._coverage(cohort, "cohort")
    )
    report = measurement_fixtures._evaluate(bundle)
    goldset, candidates, raw_plans = gold_fixtures.full_fixture()
    plans = tuple(
        sorted(
            raw_plans,
            key=lambda item: (
                item.vendor_slug,
                item.plan_slug,
                str(item.snapshot_id),
            ),
        )
    )
    candidates = candidates.__class__.model_validate(
        candidates.model_copy(
            update={
                "plans": tuple(
                    sorted(
                        candidates.plans,
                        key=lambda item: (
                            item.plan.vendor_slug,
                            item.plan.plan_slug,
                            str(item.plan.snapshot_id),
                        ),
                    )
                )
            }
        ).model_dump()
    )
    decisions = tuple(
        AffiliateProgramDecision(
            partner_id=f"partner-{suffix}",
            vendor_slug=f"vendor-{suffix}",
            property_domain="synthetic.invalid",
            territory="JP",
            decision=AffiliateReviewDecision.APPROVED,
            reviewed_at=measurement_at - timedelta(days=1),
            review_due_at=measurement_at + timedelta(days=30),
            reviewed_by="p13-semantic-human",
            decision_record_sha256=measurement_fixtures._sha(
                f"affiliate:{suffix}"
            ),
            program_id=f"program-{suffix}",
            destination_sha256=measurement_fixtures._sha(
                f"destination:{suffix}"
            ),
            disclosure_sha256=measurement_fixtures._sha(
                f"disclosure:{suffix}"
            ),
        )
        for suffix in ("a", "b", "c")
    )
    dossier = build_business_dossier(
        plans=plans,
        affiliate_decisions=decisions,
        property_domain="synthetic.invalid",
        demand=report.demand,
        cohort=report.cohort,
        operations=report.operations,
        at=measurement_at,
    )
    bound = MeasurementBoundDossier(
        report=report,
        dossier=dossier,
        dossier_sha256=hash_signed_artifact(dossier),
    )
    return bundle, bound, {
        "plans": plans,
        "decisions": decisions,
        "goldset": goldset,
        "candidates": candidates,
    }


def _public_release(bound: MeasurementBoundDossier):
    dossier = bound.dossier
    sources = tuple(
        sorted(
            (
                dossier.provenance.demand_source_sha256,
                dossier.provenance.cohort_source_sha256,
                dossier.provenance.operations_source_sha256,
            )
        )
    )
    manifest = assurance_fixtures.manifest(
        data_snapshot_sha256s=sources,
        rights_bundle_sha256=dossier.provenance.rights_bundle_sha256,
        affiliate_bundle_sha256=dossier.provenance.affiliate_bundle_sha256,
        schema_sha256=hashlib.sha256(POSTCONDITION_SCHEMA.read_bytes()).hexdigest(),
    )
    local = assurance_fixtures.local_report(manifest)
    tco, human = assurance_fixtures.attestations(local, dossier, manifest)
    public = evaluate_public_release_assurance(
        local,
        dossier,
        manifest,
        assurance_fixtures.AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=assurance_fixtures.AT + timedelta(minutes=3),
    )
    assert public.authorization is not None, public.reasons
    return manifest, public


def _p11(
    tmp_path: Path,
    bound: MeasurementBoundDossier,
    public,
    *,
    action: ExternalAction = ExternalAction.ACTIVATE_PUBLIC_RELEASE,
):
    controller_private = Ed25519PrivateKey.generate()
    human_private = Ed25519PrivateKey.generate()
    executor_private = Ed25519PrivateKey.generate()
    controller = create_verification_key(
        controller_private.public_key(), issuer="p11-controller", role=SigningRole.CONTROLLER
    )
    human = create_verification_key(
        human_private.public_key(), issuer="p11-human", role=SigningRole.HUMAN_APPROVER
    )
    executor = create_verification_key(
        executor_private.public_key(), issuer="p13-dispatcher", role=SigningRole.EXECUTOR
    )
    trust = ExternalActionTrustStore(controller=controller, human=human, executor=executor)
    rules = tuple(
        ExternalActionTargetRule(
            action=item,
            environment=(
                ActionEnvironment.VENDOR_CONTACT
                if item in {
                    ExternalAction.SEND_RIGHTS_INQUIRY,
                    ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
                }
                else ActionEnvironment.PRODUCTION
            ),
            environment_sha256="1" * 64,
            vendor_slug=(
                "vendor-a"
                if item in {
                    ExternalAction.SEND_RIGHTS_INQUIRY,
                    ExternalAction.SUBMIT_AFFILIATE_APPLICATION,
                }
                else None
            ),
            property_record_sha256=bound.report.property_record_sha256,
            target_sha256=TARGET,
        )
        for item in sorted(ExternalAction, key=lambda value: value.value)
    )
    policy = ExternalActionPolicy(
        policy_id="p11-production-test",
        trust_store_sha256=hash_external_action_trust_store(trust),
        controller_key_id_sha256=controller.key_id_sha256,
        human_key_id_sha256=human.key_id_sha256,
        executor_key_id_sha256=executor.key_id_sha256,
        target_rules=rules,
        maximum_request_ttl_seconds=86_400,
        maximum_approval_ttl_seconds=43_200,
        maximum_grant_ttl_seconds=600,
    )
    policy_sha = hash_external_action_policy(policy)
    activation = action is ExternalAction.ACTIVATE_PUBLIC_RELEASE
    request = build_external_action_request(
        request_id=f"p11-{action.value.replace('_', '-')}",
        requester_id="p13-consumer",
        action=action,
        environment=ActionEnvironment.PRODUCTION,
        environment_sha256="1" * 64,
        external_action_policy_sha256=policy_sha,
        vendor_slug=None,
        property_record_sha256=bound.report.property_record_sha256,
        target_sha256=TARGET,
        payload_sha256="4" * 64,
        idempotency_key_sha256=("5" if activation else "8") * 64,
        expected_pre_state_sha256=PRE_STATE,
        expected_post_state_sha256=POST_STATE,
        release_id=public.release_id,
        manifest_sha256=public.manifest_sha256,
        artifact_sha256=public.artifact_sha256,
        public_release_report_sha256=public.report_sha256 if activation else None,
        public_release_authorization_sha256=(
            public.authorization.payload_sha256 if activation else None
        ),
        requested_at=assurance_fixtures.AT,
        not_before=assurance_fixtures.AT,
        expires_at=assurance_fixtures.AT + timedelta(hours=2),
    )
    approval = sign_human_execution_approval(
        request,
        human_private,
        issuer=human.issuer,
        decision=ApprovalDecision.GO,
        decision_record_sha256="a" * 64,
        issued_at=assurance_fixtures.AT + timedelta(minutes=1),
        expires_at=assurance_fixtures.AT + timedelta(hours=1),
    )
    authority = ExternalActionAuthority(policy, trust, controller_private)
    grant = issue_controller_execution_grant(
        request,
        approval,
        authority,
        at=AT,
        public_report=public if activation else None,
        public_runtime=assurance_fixtures.RUNTIME if activation else None,
    )
    runtime = ExternalActionRuntime(
        policy,
        trust,
        release_assurance_runtime=assurance_fixtures.RUNTIME,
    )
    anchors: dict[str, tuple[int, str]] = {}

    def anchor_commit(revision: int, digest: str) -> None:
        previous = anchors.get("p11")
        if previous is not None and revision <= previous[0] and digest != previous[1]:
            raise ValueError("non-monotonic P11 anchor")
        anchors["p11"] = (revision, digest)

    def anchor_read() -> str:
        return anchors["p11"][1]

    guard = ExternalActionExecutionGuard.create(
        runtime,
        tmp_path / f"{action.value}.sqlite",
        store_id_sha256="c" * 64,
        state_authentication_key=b"p11-synthetic-state-authentication-key",
        anchor_commit=anchor_commit,
        anchor_read=anchor_read,
        clock=lambda: AT,
    )
    claim = guard.claim(
        request,
        approval,
        grant,
        observed_pre_state_sha256=PRE_STATE,
        public_report=public if activation else None,
    )
    return {
        "controller_private": controller_private,
        "human_private": human_private,
        "private": executor_private,
        "trust": trust,
        "policy": policy,
        "runtime": runtime,
        "guard": guard,
        "request": request,
        "approval": approval,
        "grant": grant,
        "claim": claim,
    }


def _anchor_callbacks():
    pins: dict[str, tuple[int, str]] = {}

    def commit(revision: int, digest: str) -> None:
        previous = pins.get("p13")
        if previous is not None and (
            revision < previous[0]
            or (revision == previous[0] and digest != previous[1])
        ):
            raise ProductionConsumerError("non-monotonic P13 anchor")
        pins["p13"] = (revision, digest)

    def read() -> str:
        return pins["p13"][1]

    return pins, commit, read


@pytest.fixture
def production_case(tmp_path, monkeypatch):
    measurement, bound, semantic_sources = _measurement(monkeypatch)
    manifest, public = _public_release(bound)
    p11 = _p11(tmp_path, bound, public)
    reset_private = Ed25519PrivateKey.generate()
    p9_private = Ed25519PrivateKey.generate()
    provider_private = Ed25519PrivateKey.generate()
    probe_private = Ed25519PrivateKey.generate()
    reset_key = create_verification_key(
        reset_private.public_key(), issuer="p13-reset-human", role=SigningRole.HUMAN_APPROVER
    )
    provider_key = create_verification_key(
        provider_private.public_key(),
        issuer="synthetic-provider-adapter",
        role=SigningRole.PROVIDER_ADAPTER,
    )
    probe_key = create_verification_key(
        probe_private.public_key(),
        issuer="synthetic-provider-probe",
        role=SigningRole.PROVIDER_PROBE,
    )
    p9_key = create_verification_key(
        p9_private.public_key(), issuer="p9-serving-controller", role=SigningRole.CONTROLLER
    )
    trust = ProductionConsumerTrustStore(
        p10_release_controller=assurance_fixtures.CONTROLLER_KEY,
        p9_lease_controller=p9_key,
        reset_human=reset_key,
        dispatcher=p11["trust"].executor,
        provider_adapter=provider_key,
        provider_probe=probe_key,
    )
    executable_sha = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    probe_executable_sha = hashlib.sha256(PROBE_SCRIPT.read_bytes()).hexdigest()
    python_executable_sha = hashlib.sha256(PYTHON_EXECUTABLE.read_bytes()).hexdigest()
    dependency_paths = production_adapter_dependency_paths()
    dependency_sha = hash_adapter_dependency_closure(dependency_paths)
    postcondition_sha = hashlib.sha256(POSTCONDITION_SCHEMA.read_bytes()).hexdigest()

    def transition(operation):
        return (
            (PRE_STATE, POST_STATE)
            if operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
            else (POST_STATE, DISABLED_STATE)
        )

    allowlist = {
        "schema_version": "1.0",
        "entries": [
            {
                "operation": operation.value,
                "adapter_id": "synthetic-adapter",
                "store_id_sha256": STORE_ID,
                "target_sha256": TARGET,
                "expected_pre_state_sha256": transition(operation)[0],
                "expected_post_state_sha256": transition(operation)[1],
                "adapter_executable_sha256": executable_sha,
                "probe_executable_sha256": probe_executable_sha,
                "python_executable_sha256": python_executable_sha,
                "adapter_dependency_closure_sha256": dependency_sha,
                "postcondition_schema_sha256": postcondition_sha,
            }
            for operation in sorted(ProviderOperation, key=lambda item: item.value)
        ],
    }
    allowlist_sha = _canonical_sha256(allowlist)
    rules = tuple(
        ProviderTargetRule(
            operation=operation,
            external_action={
                ProviderOperation.ACTIVATE_PUBLIC_RELEASE:
                    ExternalAction.ACTIVATE_PUBLIC_RELEASE,
                ProviderOperation.DISABLE_PUBLIC_RELEASE:
                    ExternalAction.DISABLE_PUBLIC_RELEASE,
            }[operation],
            property_record_sha256=bound.report.property_record_sha256,
            target_sha256=TARGET,
            expected_pre_state_sha256=transition(operation)[0],
            expected_post_state_sha256=transition(operation)[1],
            adapter_id="synthetic-adapter",
            adapter_executable_sha256=executable_sha,
            probe_executable_sha256=probe_executable_sha,
            python_executable_sha256=python_executable_sha,
            adapter_dependency_closure_sha256=dependency_sha,
            provider_allowlist_sha256=allowlist_sha,
            postcondition_schema_sha256=postcondition_sha,
        )
        for operation in sorted(ProviderOperation, key=lambda item: item.value)
    )
    policy = ProductionConsumerPolicy(
        policy_id="p13-production-consumer",
        trust_store_sha256=hash_production_consumer_trust_store(trust),
        store_id_sha256=STORE_ID,
        external_action_policy_sha256=hash_external_action_policy(p11["policy"]),
        release_assurance_policy_sha256=hash_assurance_policy(assurance_fixtures.POLICY),
        measurement_policy_sha256=hash_measurement_policy(measurement["policy"]),
        measurement_trust_store_sha256=hash_measurement_trust_store(measurement["trust"]),
        measurement_authority_pins_sha256=hash_measurement_authority_pins(measurement["pins"]),
        production_integration_policy_sha256=hash_production_integration_policy(
            p15_fixtures.POLICY
        ),
        production_integration_trust_store_sha256=hash_production_integration_trust_store(
            p15_fixtures.TRUST
        ),
        production_reconciliation_ledger_store_sha256="9" * 64,
        serving_lease_issuer=p9_key.issuer,
        serving_controller_key_id_sha256=p9_key.key_id_sha256,
        release_assurance_controller_key_id_sha256=(
            assurance_fixtures.CONTROLLER_KEY.key_id_sha256
        ),
        maximum_serving_lease_ttl_seconds=600,
        maximum_request_ttl_seconds=600,
        maximum_dispatch_ttl_seconds=300,
        maximum_reset_ttl_seconds=600,
        maximum_provider_receipt_delay_seconds=60,
        minimum_provider_authority_margin_seconds=60,
        maximum_clock_attestation_ttl_seconds=60,
        maximum_clock_observation_lag_seconds=5,
        clock_response_timeout_seconds=2,
        maximum_authority_root_ttl_seconds=60,
        maximum_authority_root_observation_lag_seconds=5,
        authority_root_response_timeout_seconds=2,
        target_rules=rules,
    )
    p15_plan = p15_fixtures._plan(
        property_record_sha256=bound.report.property_record_sha256,
        environment_identity_sha256=p11["request"].environment_sha256,
        p11_policy_sha256=hash_external_action_policy(p11["policy"]),
        p11_store_identity_sha256=p11["guard"].state_store_id_sha256,
        p13_policy_sha256=hash_production_consumer_policy(policy),
        reconciliation_ledger_store_sha256="9" * 64,
        p13_store_identity_sha256=STORE_ID,
        release_artifact_sha256=public.artifact_sha256,
        release_manifest_sha256=public.manifest_sha256,
        adapter_closure_sha256=_canonical_sha256(
            {
                "adapter_id": "synthetic-adapter",
                "adapter_executable_sha256": executable_sha,
                "python_executable_sha256": python_executable_sha,
                "dependency_closure_sha256": dependency_sha,
            }
        ),
        probe_closure_sha256=_canonical_sha256(
            {
                "adapter_id": "synthetic-adapter",
                "probe_executable_sha256": probe_executable_sha,
                "python_executable_sha256": python_executable_sha,
                "dependency_closure_sha256": dependency_sha,
            }
        ),
        provider_capability_profile_sha256=allowlist_sha,
        deployment_candidate_sha256=postcondition_sha,
        provider_target_sha256=TARGET,
        expected_pre_state_sha256=PRE_STATE,
        issued_at=AT - timedelta(hours=1),
        not_before=AT - timedelta(minutes=1),
        expires_at=AT + timedelta(hours=1),
    )
    p15_evidence = []
    for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
        facts = p15_fixtures._facts(check)
        if check is ProductionIntegrationCheck.INDEPENDENT_READBACK:
            facts = facts.model_copy(
                update={
                    "expected_state_sha256": POST_STATE,
                    "observed_state_sha256": POST_STATE,
                }
            )
        elif check is ProductionIntegrationCheck.ROLLBACK_DISABLE:
            facts = facts.model_copy(
                update={
                    "disable_policy_sha256": p15_plan.p11_policy_sha256,
                    "p11_disable_authority_sha256": p15_plan.p11_policy_sha256,
                    "active_state_sha256": POST_STATE,
                    "disabled_state_sha256": DISABLED_STATE,
                    "final_observed_state_sha256": DISABLED_STATE,
                }
            )
        p15_evidence.append(
            p15_fixtures._evidence(
                check,
                plan=p15_plan,
                observed_at=(
                    AT
                    if check
                    in {
                        ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR,
                        ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING,
                        ProductionIntegrationCheck.TRUSTED_CLOCK,
                    }
                    else AT - timedelta(minutes=1)
                ),
                facts_override=facts,
            )
        )
    p15_bundle = build_production_integration_bundle(
        p15_plan, p15_fixtures.POLICY, tuple(p15_evidence)
    )
    p15_report = p15_fixtures._report(p15_bundle, plan=p15_plan, at=AT)
    p15_tco = sign_production_tco_qa_attestation(
        p15_report,
        p15_fixtures.TCO_PRIVATE,
        issuer=p15_fixtures.TRUST.tco_qa.issuer,
        decision=ReadinessAttestationDecision.ACCEPT,
        issued_at=AT,
        expires_at=AT + timedelta(minutes=30),
    )
    p15_human = sign_production_human_environment_approval(
        p15_report,
        p15_plan,
        p15_fixtures.HUMAN_PRIVATE,
        issuer=p15_fixtures.TRUST.environment_human.issuer,
        decision=EnvironmentApprovalDecision.APPROVE,
        decision_record_sha256="e" * 64,
        issued_at=AT,
        expires_at=AT + timedelta(minutes=30),
    )
    p15_authorization = authorize_production_bootstrap(
        p15_report,
        p15_bundle,
        p15_plan,
        p15_fixtures.POLICY,
        p15_fixtures.TRUST,
        p15_tco,
        p15_human,
        p15_fixtures.CONTROLLER_PRIVATE,
        issuer=p15_fixtures.TRUST.controller.issuer,
        issued_at=AT,
        expires_at=AT + timedelta(minutes=3),
    )
    p15_pins = ProductionReadinessAuthorityPins(
        expected_trust_store_sha256=hash_production_integration_trust_store(
            p15_fixtures.TRUST
        ),
        expected_integration_policy_sha256=hash_production_integration_policy(
            p15_fixtures.POLICY
        ),
        expected_plan_sha256=p15_plan.plan_sha256,
        expected_report_sha256=p15_report.report_sha256,
        expected_authorization_sha256=hash_production_bootstrap_authorization(
            p15_authorization
        ),
    )
    anchors, anchor_commit, anchor_read = _anchor_callbacks()
    store = GlobalStopStore.create(
        tmp_path / "production.sqlite",
        store_id_sha256=STORE_ID,
        policy_sha256=hash_production_consumer_policy(policy),
        initial_stop_reason_sha256="f" * 64,
        created_at=AT - timedelta(minutes=1),
        state_authentication_key=STATE_KEY,
        anchor_commit=anchor_commit,
        anchor_read=anchor_read,
    )
    reconciliation_anchors: dict[str, tuple[int, str]] = {}

    def reconciliation_anchor_commit(revision: int, digest: str) -> None:
        current = reconciliation_anchors.get("p15-reconciliation")
        if current is not None and (
            revision < current[0]
            or (revision == current[0] and digest != current[1])
        ):
            raise ValueError("non-monotonic P15 reconciliation anchor")
        reconciliation_anchors["p15-reconciliation"] = (revision, digest)

    def reconciliation_anchor_read() -> str:
        return reconciliation_anchors["p15-reconciliation"][1]

    reconciliation_ledger = ProductionReconciliationLedger.create(
        tmp_path / "production-reconciliation.sqlite",
        store_id_sha256="9" * 64,
        plan_sha256=p15_plan.plan_sha256,
        trust_store=p15_fixtures.TRUST,
        state_authentication_key=b"p15-p13-reconciliation-auth-key-32bytes",
        anchor_commit=reconciliation_anchor_commit,
        anchor_read=reconciliation_anchor_read,
    )
    initial_stop = store.snapshot()
    initial_reconciliation_facts = sign_production_reconciliation_facts(
        p15_fixtures.RECOVERY_PRIVATE,
        issuer=p15_fixtures.TRUST.recovery_auditor.issuer,
        plan_sha256=p15_plan.plan_sha256,
        p13_store_identity_sha256=STORE_ID,
        p13_result_sha256=_canonical_sha256(
            {"kind": "initial-stop", "head": initial_stop.head_sha256}
        ),
        p13_terminal_state=P13TerminalState.STOP,
        stopped_revision=initial_stop.revision,
        stopped_head_sha256=initial_stop.head_sha256,
        stop_reason_sha256=initial_stop.stop_reason_sha256,
        provider_observed_state=ProviderObservedState.NOT_APPLIED,
        provider_result_receipt_sha256="1" * 64,
        journaled_provider_receipt_sha256="2" * 64,
        provider_probe_receipt_sha256="3" * 64,
        receipt_lookup_evidence_sha256="4" * 64,
        independent_readback_evidence_sha256="5" * 64,
        observed_at=AT - timedelta(seconds=30),
        expires_at=AT + timedelta(minutes=30),
    )
    initial_reconciliation_report = evaluate_production_reconciliation(
        initial_reconciliation_facts, at=AT - timedelta(seconds=20)
    )
    initial_reconciliation_record = reconciliation_ledger.append(
        initial_reconciliation_facts,
        initial_reconciliation_report,
        at=AT - timedelta(seconds=20),
    )
    p18_acceptance = p16_fixtures._accepted_repository_bundle(at=AT)
    p18_authority_root = p16_fixtures.hash_repository_acceptance_authority_pins(
        p18_acceptance.authority_pins
    )
    p12_packet = P12AuthorityPacket(
        policy=measurement["policy"],
        trust_store=measurement["trust"],
        authority_pins=measurement["pins"],
        plan=measurement["plan"],
        demand_batch=measurement["demand"],
        cohort_batch=measurement["cohort"],
        operations_batch=measurement["operations"],
        demand_attestation=measurement["demand_attestation"],
        cohort_attestation=measurement["cohort_attestation"],
        operations_attestation=measurement["operations_attestation"],
        bundle_index=measurement["index"],
        report=bound.report,
    )
    local_assurance_bundle = assurance_fixtures.evidence_bundle(manifest)
    local_assurance_report = evaluate_local_assurance(
        local_assurance_bundle,
        assurance_fixtures.AUTHORITY,
        at=assurance_fixtures.AT,
    )
    assert local_assurance_report.report_sha256 == public.local_report_sha256
    rights_bundle = build_rights_bundle(semantic_sources["plans"], at=AT)
    affiliate_bundle = build_affiliate_bundle(
        semantic_sources["decisions"],
        property_domain="synthetic.invalid",
        at=AT,
    )
    gold_report = evaluate_goldset(
        semantic_sources["goldset"], semantic_sources["candidates"], at=AT
    )
    gold_private = Ed25519PrivateKey.generate()
    gold_key = create_verification_key(
        gold_private.public_key(),
        issuer="p13-semantic-gold",
        role=SigningRole.TCO_QA,
    )
    gold_attestation = sign_gold_report_attestation(
        gold_report,
        gold_private,
        issuer=gold_key.issuer,
        issued_at=AT,
        expires_at=AT + timedelta(minutes=10),
    )
    semantic_scope = LaunchSemanticScope(
        candidate_manifest_sha256=p18_acceptance.manifest.manifest_sha256,
        property_record_sha256=bound.report.property_record_sha256,
        environment_identity_sha256=p11["request"].environment_sha256,
        release_identity_sha256=hashlib.sha256(
            public.release_id.strip().lower().encode("utf-8")
        ).hexdigest(),
        release_manifest_sha256=public.manifest_sha256,
        release_artifact_sha256=public.artifact_sha256,
        deployment_candidate_sha256=postcondition_sha,
        provider_target_sha256=TARGET,
        expected_pre_state_sha256=PRE_STATE,
        expected_post_state_sha256=POST_STATE,
        rollback_state_sha256=DISABLED_STATE,
        legal_pages_sha256="a" * 64,
        affiliate_disclosure_sha256="b" * 64,
    )
    readback_evidence = next(
        row
        for row in p15_bundle.evidence
        if row.check is ProductionIntegrationCheck.INDEPENDENT_READBACK
    )
    rollback_evidence = next(
        row
        for row in p15_bundle.evidence
        if row.check is ProductionIntegrationCheck.ROLLBACK_DISABLE
    )
    deployment_record = sign_deployment_readiness_record(
        DeploymentReadinessFacts(
            property_record_sha256=semantic_scope.property_record_sha256,
            environment_identity_sha256=semantic_scope.environment_identity_sha256,
            release_identity_sha256=semantic_scope.release_identity_sha256,
            release_manifest_sha256=semantic_scope.release_manifest_sha256,
            release_artifact_sha256=semantic_scope.release_artifact_sha256,
            deployment_candidate_sha256=semantic_scope.deployment_candidate_sha256,
            production_integration_plan_sha256=p15_plan.plan_sha256,
            provider_target_sha256=TARGET,
            expected_pre_state_sha256=PRE_STATE,
            independent_readback_evidence_sha256=(
                hash_production_integration_evidence(readback_evidence)
            ),
            rollback_disable_evidence_sha256=(
                hash_production_integration_evidence(rollback_evidence)
            ),
            staged_expected_state_sha256=POST_STATE,
            staged_observed_state_sha256=POST_STATE,
            rollback_active_state_sha256=POST_STATE,
            rollback_expected_state_sha256=DISABLED_STATE,
            rollback_observed_state_sha256=DISABLED_STATE,
        ),
        p15_fixtures.PROBE_PRIVATE,
        p15_fixtures.TRUST.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=AT,
        expires_at=AT + timedelta(minutes=5),
    )
    publication_record = sign_publication_readiness_record(
        PublicationReadinessFacts(
            property_record_sha256=semantic_scope.property_record_sha256,
            environment_identity_sha256=semantic_scope.environment_identity_sha256,
            release_identity_sha256=semantic_scope.release_identity_sha256,
            release_manifest_sha256=semantic_scope.release_manifest_sha256,
            release_artifact_sha256=semantic_scope.release_artifact_sha256,
            deployment_candidate_sha256=semantic_scope.deployment_candidate_sha256,
            deployment_readiness_record_sha256=deployment_record.record_sha256,
            rights_bundle_sha256=rights_bundle.bundle_sha256,
            affiliate_bundle_sha256=affiliate_bundle.bundle_sha256,
            approved_partner_ids=affiliate_bundle.approved_partner_ids,
            content_readback=PublicationContentReadback(
                expected_release_manifest_sha256=public.manifest_sha256,
                observed_release_manifest_sha256=public.manifest_sha256,
                expected_release_artifact_sha256=public.artifact_sha256,
                observed_release_artifact_sha256=public.artifact_sha256,
                response_receipt_sha256="c" * 64,
                observed_at=AT,
            ),
            indexability_readback=PublicationIndexabilityReadback(
                response_receipt_sha256="d" * 64,
                observed_at=AT,
            ),
            disclosure_readback=PublicationDisclosureReadback(
                expected_legal_pages_sha256="a" * 64,
                observed_legal_pages_sha256="a" * 64,
                expected_disclosure_sha256="b" * 64,
                observed_disclosure_sha256="b" * 64,
                response_receipt_sha256="e" * 64,
                observed_at=AT,
            ),
        ),
        p15_fixtures.PROBE_PRIVATE,
        p15_fixtures.TRUST.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=AT,
        expires_at=AT + timedelta(minutes=5),
    )
    semantic_values = {
        "schema_version": "1.0",
        "scope": semantic_scope,
        "rights": RightsSemanticPacket(plans=semantic_sources["plans"]),
        "affiliate": AffiliateSemanticPacket(
            property_domain="synthetic.invalid",
            decisions=AffiliateDecisionBatch(
                decisions=semantic_sources["decisions"]
            ),
        ),
        "measurement": MeasurementSemanticPacket(
            authority_packet=p12_packet, bound_dossier=bound
        ),
        "gold": GoldSemanticPacket(
            goldset=semantic_sources["goldset"],
            candidates=semantic_sources["candidates"],
            report=gold_report,
            attestation=gold_attestation,
            tco_qa_verifier=gold_key,
        ),
        "production": ProductionSemanticPacket(
            plan=p15_plan,
            policy=p15_fixtures.POLICY,
            trust_store=p15_fixtures.TRUST,
            evidence_bundle=p15_bundle,
            report=p15_report,
            tco_qa_attestation=p15_tco,
        ),
        "deployment_publication": DeploymentPublicationSemanticPacket(
            assurance_policy=assurance_fixtures.POLICY,
            assurance_trust_store=assurance_fixtures.TRUST,
            assurance_bundle=local_assurance_bundle,
            local_assurance_report=local_assurance_report,
            deployment=deployment_record,
            publication=publication_record,
        ),
    }
    semantic_provisional = LaunchSemanticPacket.model_construct(
        **semantic_values, packet_sha256="0" * 64
    )
    semantic_packet = LaunchSemanticPacket(
        **semantic_values,
        packet_sha256=hash_launch_semantic_packet(semantic_provisional),
    )
    semantic_pins = build_launch_semantic_authority_pins(semantic_packet)
    semantic_authority_root = hash_launch_semantic_authority_pins(semantic_pins)
    semantic_evaluation = evaluate_launch_semantics(
        semantic_packet,
        semantic_pins,
        at=AT,
        expected_authority_pins_sha256=semantic_authority_root,
    )
    assert semantic_evaluation.passed, semantic_evaluation.gates
    p16_requirements = p16_fixtures._requirements(
        repository_acceptance=p18_acceptance,
        semantic_evaluation=semantic_evaluation,
    )
    p16_plan = p16_fixtures._plan(
        requirements=p16_requirements,
        repository_acceptance=p18_acceptance,
        launch_semantic_authority_pins_sha256=semantic_authority_root,
        candidate_manifest_sha256=semantic_scope.candidate_manifest_sha256,
        property_record_sha256=bound.report.property_record_sha256,
        environment_identity_sha256=p11["request"].environment_sha256,
        release_identity_sha256=semantic_scope.release_identity_sha256,
        release_manifest_sha256=semantic_scope.release_manifest_sha256,
        release_artifact_sha256=public.artifact_sha256,
        deployment_candidate_sha256=postcondition_sha,
        provider_target_sha256=TARGET,
        expected_pre_state_sha256=PRE_STATE,
        expected_post_state_sha256=POST_STATE,
        rollback_state_sha256=DISABLED_STATE,
        legal_pages_sha256=semantic_scope.legal_pages_sha256,
        affiliate_disclosure_sha256=(
            semantic_scope.affiliate_disclosure_sha256
        ),
        issued_at=AT - timedelta(hours=2),
        not_before=AT - timedelta(hours=1),
        expires_at=AT + timedelta(hours=6),
    )
    p16_observed = {
        gate: (
            AT - timedelta(minutes=30) + timedelta(seconds=index)
            if index < 6
            else AT - timedelta(minutes=2) + timedelta(seconds=index - 6)
        )
        for index, gate in enumerate(p16_fixtures.REQUIRED_LAUNCH_HANDOFF_GATES)
    }
    p16_expires = {
        gate: (
            AT + timedelta(minutes=3)
            if gate is LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS
            else (
                AT + timedelta(minutes=5)
                if gate
                in {
                    LaunchHandoffGate.GOLD_SET_SOURCE_READINESS,
                    LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS,
                }
                else AT + timedelta(hours=6)
            )
        )
        for index, gate in enumerate(p16_fixtures.REQUIRED_LAUNCH_HANDOFF_GATES)
    }
    p16_receipts = p16_fixtures._receipts(
        plan=p16_plan,
        observed_overrides=p16_observed,
        expires_overrides=p16_expires,
    )
    p16_bundle = p16_fixtures._bundle(
        p16_receipts,
        plan=p16_plan,
        repository_acceptance=p18_acceptance,
        launch_semantics=semantic_packet,
    )
    p16_authority_root = hash_launch_handoff_authority(
        p16_plan, p16_fixtures.POLICY, p16_fixtures.TRUST
    )

    def runtime_clock_attest(request: ProductionConsumerClockRequest):
        return sign_production_consumer_clock_attestation(
            request,
            p15_fixtures.TRUST,
            p15_fixtures.TIME_PRIVATE,
            observed_at=AT,
            issued_at=AT,
            expires_at=AT + timedelta(seconds=30),
        )

    def runtime_authority_roots(request: ProductionAuthorityRootRequest):
        return sign_production_authority_roots(
            request,
            p15_fixtures.TRUST,
            p15_fixtures.STORAGE_PRIVATE,
            revision=1,
            repository_acceptance_authority_sha256=p18_authority_root,
            launch_handoff_authority_sha256=p16_authority_root,
            launch_semantic_authority_sha256=semantic_authority_root,
            observed_at=AT,
            issued_at=AT,
            expires_at=AT + timedelta(seconds=30),
        )

    runtime = ProductionConsumerRuntime(
        policy,
        trust,
        external_runtime=p11["runtime"],
        external_guard=p11["guard"],
        release_runtime=assurance_fixtures.RUNTIME,
        measurement_policy=measurement["policy"],
        measurement_trust_store=measurement["trust"],
        measurement_authority_pins=measurement["pins"],
        production_integration_plan=p15_plan,
        production_integration_policy=p15_fixtures.POLICY,
        production_integration_trust_store=p15_fixtures.TRUST,
        production_integration_bundle=p15_bundle,
        production_readiness_report=p15_report,
        production_tco_qa_attestation=p15_tco,
        production_human_environment_approval=p15_human,
        production_bootstrap_authorization=p15_authorization,
        production_readiness_authority_pins=p15_pins,
        production_reconciliation_ledger=reconciliation_ledger,
        launch_handoff_bundle=p16_bundle,
        launch_handoff_plan=p16_plan,
        launch_handoff_policy=p16_fixtures.POLICY,
        launch_handoff_trust_store=p16_fixtures.TRUST,
        launch_semantic_packet=semantic_packet,
        launch_semantic_authority_pins=semantic_pins,
        expected_repository_acceptance_authority_pins_sha256=(
            p18_authority_root
        ),
        expected_launch_handoff_authority_sha256=p16_authority_root,
        expected_launch_semantic_authority_pins_sha256=(
            semantic_authority_root
        ),
        clock_attest=runtime_clock_attest,
        current_authority_roots=runtime_authority_roots,
    )
    lease = _build_lease(
        private_key=p9_private,
        issuer=p9_key.issuer,
        controller_key_id_sha256=p9_key.key_id_sha256,
        scope=LeaseScope.SERVE_PROTECTED_CONTENT,
        control_input_sha256="9" * 64,
        release_id=public.release_id,
        manifest_sha256=public.manifest_sha256,
        artifact_sha256=public.artifact_sha256,
        issued_at=assurance_fixtures.AT + timedelta(minutes=3, seconds=30),
        expires_at=AT + timedelta(minutes=5),
    )
    request = build_production_consumption_request(
        request_id="p13-activation",
        operation=ProviderOperation.ACTIVATE_PUBLIC_RELEASE,
        external_request=p11["request"],
        human_approval=p11["approval"],
        controller_grant=p11["grant"],
        execution_claim=p11["claim"],
        release_report=public,
        serving_lease=lease,
        measurement_bundle=bound,
        property_domain_sha256=bound.report.property_domain_sha256,
        measurement_run_id=bound.report.run_id,
        measurement_bundle_index_sha256=bound.report.bundle_index_sha256,
        affiliate_partner_ids_sha256=_canonical_sha256(bound.report.partner_ids),
        production_integration_plan_sha256=p15_plan.plan_sha256,
        production_readiness_authorization_sha256=(
            hash_production_bootstrap_authorization(p15_authorization)
        ),
        repository_acceptance_authority_pins_sha256=(
            p18_authority_root
        ),
        launch_handoff_authority_sha256=p16_authority_root,
        launch_handoff_plan_sha256=p16_plan.plan_sha256,
        launch_handoff_bundle_sha256=p16_bundle.bundle_sha256,
        launch_semantic_authority_sha256=semantic_authority_root,
        launch_semantic_packet_sha256=semantic_packet.packet_sha256,
        adapter_id="synthetic-adapter",
        adapter_executable_sha256=executable_sha,
        probe_executable_sha256=probe_executable_sha,
        python_executable_sha256=python_executable_sha,
        adapter_dependency_closure_sha256=dependency_sha,
        provider_allowlist_sha256=allowlist_sha,
        postcondition_schema_sha256=postcondition_sha,
        requested_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=4),
    )
    provider_state = tmp_path / "provider-state.json"
    provider_state.write_bytes(
        _canonical_json_bytes(
            {
                "schema_version": "1.0",
                "targets": {TARGET: PRE_STATE},
                "operations": {},
                "call_count": 0,
            }
        )
    )
    provider_state.chmod(0o600)
    provider_key_path = tmp_path / "provider.key"
    probe_key_path = tmp_path / "probe.key"
    dispatcher_key_path = tmp_path / "dispatcher.json"
    allowlist_path = tmp_path / "allowlist.json"
    write_raw_ed25519_private_key(provider_key_path, provider_private)
    write_raw_ed25519_private_key(probe_key_path, probe_private)
    write_verification_key(dispatcher_key_path, trust.dispatcher)
    allowlist_path.write_bytes(_canonical_json_bytes(allowlist))
    allowlist_path.chmod(0o600)
    adapter = SubprocessProviderAdapter(
        execute_script_path=SCRIPT,
        expected_execute_executable_sha256=executable_sha,
        probe_script_path=PROBE_SCRIPT,
        expected_probe_executable_sha256=probe_executable_sha,
        python_executable_path=PYTHON_EXECUTABLE,
        expected_python_executable_sha256=python_executable_sha,
        dependency_paths=dependency_paths,
        expected_dependency_closure_sha256=dependency_sha,
        state_path=provider_state,
        provider_private_key_path=provider_key_path,
        probe_private_key_path=probe_key_path,
        dispatcher_verification_key_path=dispatcher_key_path,
        allowlist_path=allowlist_path,
        postcondition_schema_path=POSTCONDITION_SCHEMA,
        adapter_id="synthetic-adapter",
    )
    return {
        "measurement": measurement,
        "bound": bound,
        "manifest": manifest,
        "public": public,
        "p11": p11,
        "p15": {
            "plan": p15_plan,
            "policy": p15_fixtures.POLICY,
            "trust": p15_fixtures.TRUST,
            "bundle": p15_bundle,
            "report": p15_report,
            "tco": p15_tco,
            "human": p15_human,
            "authorization": p15_authorization,
            "pins": p15_pins,
            "reconciliation_ledger": reconciliation_ledger,
            "initial_reconciliation_record": initial_reconciliation_record,
        },
        "p16": {
            "plan": p16_plan,
            "policy": p16_fixtures.POLICY,
            "trust": p16_fixtures.TRUST,
            "bundle": p16_bundle,
            "repository_authority_root": p18_authority_root,
            "authority_root": p16_authority_root,
            "semantic_packet": semantic_packet,
            "semantic_pins": semantic_pins,
            "semantic_authority_root": semantic_authority_root,
        },
        "reset_private": reset_private,
        "probe_private": probe_private,
        "provider_private": provider_private,
        "p9_private": p9_private,
        "policy": policy,
        "trust": trust,
        "runtime": runtime,
        "runtime_clock_attest": runtime_clock_attest,
        "runtime_authority_roots": runtime_authority_roots,
        "store": store,
        "request": request,
        "adapter": adapter,
        "provider_state": provider_state,
        "anchors": anchors,
        "anchor_commit": anchor_commit,
        "anchor_read": anchor_read,
    }


def _reset(case):
    snapshot = case["store"].snapshot()
    reset = sign_global_stop_reset(
        snapshot,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="1" * 64,
        reconciliation_record_sha256=(
            case["p15"]["initial_reconciliation_record"].record_sha256
        ),
        nonce_sha256="3" * 64,
        issued_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=5),
    )
    return case["store"].apply_reset(reset, case["runtime"], at=AT)


def test_duck_typed_runtime_cannot_apply_an_expired_reset(production_case) -> None:
    case = production_case
    before = case["store"].snapshot()
    reset = sign_global_stop_reset(
        before,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="1" * 64,
        reconciliation_record_sha256=(
            case["p15"]["initial_reconciliation_record"].record_sha256
        ),
        nonce_sha256="4" * 64,
        issued_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(seconds=1),
    )

    class DuckRuntime:
        policy = case["policy"]
        policy_sha256 = hash_production_consumer_policy(case["policy"])

        def authoritative_phase(self, **_kwargs):
            raise AssertionError("duck runtime authority must never be called")

    with pytest.raises(TypeError, match="exact ProductionConsumerRuntime"):
        case["store"].apply_reset(
            reset,
            DuckRuntime(),
            at=AT + timedelta(days=365),
        )
    assert case["store"].snapshot() == before


def _runtime_from_case(case, **overrides):
    values = {
        "external_runtime": case["p11"]["runtime"],
        "external_guard": case["p11"]["guard"],
        "release_runtime": assurance_fixtures.RUNTIME,
        "measurement_policy": case["measurement"]["policy"],
        "measurement_trust_store": case["measurement"]["trust"],
        "measurement_authority_pins": case["measurement"]["pins"],
        "production_integration_plan": case["p15"]["plan"],
        "production_integration_policy": case["p15"]["policy"],
        "production_integration_trust_store": case["p15"]["trust"],
        "production_integration_bundle": case["p15"]["bundle"],
        "production_readiness_report": case["p15"]["report"],
        "production_tco_qa_attestation": case["p15"]["tco"],
        "production_human_environment_approval": case["p15"]["human"],
        "production_bootstrap_authorization": case["p15"]["authorization"],
        "production_readiness_authority_pins": case["p15"]["pins"],
        "production_reconciliation_ledger": case["p15"]["reconciliation_ledger"],
        "launch_handoff_bundle": case["p16"]["bundle"],
        "launch_handoff_plan": case["p16"]["plan"],
        "launch_handoff_policy": case["p16"]["policy"],
        "launch_handoff_trust_store": case["p16"]["trust"],
        "launch_semantic_packet": case["p16"]["semantic_packet"],
        "launch_semantic_authority_pins": case["p16"]["semantic_pins"],
        "expected_repository_acceptance_authority_pins_sha256": (
            case["p16"]["repository_authority_root"]
        ),
        "expected_launch_handoff_authority_sha256": case["p16"]["authority_root"],
        "expected_launch_semantic_authority_pins_sha256": (
            case["p16"]["semantic_authority_root"]
        ),
        "clock_attest": case["runtime_clock_attest"],
        "current_authority_roots": case["runtime_authority_roots"],
    }
    values.update(overrides)
    return ProductionConsumerRuntime(case["policy"], case["trust"], **values)


def _runtime_at(case, at):
    return _runtime_from_case(
        case,
        clock_attest=_consumer_clock_attest(case, lambda: at),
        current_authority_roots=_current_authority_roots(case, at=at),
    )


def _disable_request(case):
    p11 = case["p11"]
    public = case["public"]
    external = build_external_action_request(
        request_id="p11-disable-public-release",
        requester_id="p13-consumer",
        action=ExternalAction.DISABLE_PUBLIC_RELEASE,
        environment=ActionEnvironment.PRODUCTION,
        environment_sha256="1" * 64,
        external_action_policy_sha256=hash_external_action_policy(p11["policy"]),
        vendor_slug=None,
        property_record_sha256=case["bound"].report.property_record_sha256,
        target_sha256=TARGET,
        payload_sha256="b" * 64,
        idempotency_key_sha256="8" * 64,
        expected_pre_state_sha256=POST_STATE,
        expected_post_state_sha256=DISABLED_STATE,
        release_id=public.release_id,
        manifest_sha256=public.manifest_sha256,
        artifact_sha256=public.artifact_sha256,
        public_release_report_sha256=None,
        public_release_authorization_sha256=None,
        requested_at=assurance_fixtures.AT,
        not_before=assurance_fixtures.AT,
        expires_at=assurance_fixtures.AT + timedelta(hours=2),
    )
    approval = sign_human_execution_approval(
        external,
        p11["human_private"],
        issuer=p11["trust"].human.issuer,
        decision=ApprovalDecision.GO,
        decision_record_sha256="c" * 64,
        issued_at=assurance_fixtures.AT + timedelta(minutes=1),
        expires_at=assurance_fixtures.AT + timedelta(hours=1),
    )
    authority = ExternalActionAuthority(
        p11["policy"], p11["trust"], p11["controller_private"]
    )
    grant = issue_controller_execution_grant(
        external, approval, authority, at=AT
    )
    claim = p11["guard"].claim(
        external,
        approval,
        grant,
        observed_pre_state_sha256=POST_STATE,
    )
    return build_production_consumption_request(
        request_id="p13-disable",
        operation=ProviderOperation.DISABLE_PUBLIC_RELEASE,
        external_request=external,
        human_approval=approval,
        controller_grant=grant,
        execution_claim=claim,
        release_report=None,
        serving_lease=None,
        measurement_bundle=None,
        property_domain_sha256=None,
        measurement_run_id=None,
        measurement_bundle_index_sha256=None,
        affiliate_partner_ids_sha256=None,
        adapter_id=case["request"].adapter_id,
        adapter_executable_sha256=case["request"].adapter_executable_sha256,
        probe_executable_sha256=case["request"].probe_executable_sha256,
        python_executable_sha256=case["request"].python_executable_sha256,
        adapter_dependency_closure_sha256=(
            case["request"].adapter_dependency_closure_sha256
        ),
        provider_allowlist_sha256=case["request"].provider_allowlist_sha256,
        postcondition_schema_sha256=case["request"].postcondition_schema_sha256,
        requested_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=4),
    )


def test_signed_two_stage_subprocess_flow_is_idempotent(production_case) -> None:
    case = production_case
    assert case["store"].snapshot().stopped is True
    with pytest.raises(ProductionConsumerError, match="STOP blocks activation"):
        case["store"].claim(
            case["request"], case["runtime"], case["p11"]["private"], at=AT
        )

    running = _reset(case)
    assert running.stopped is False and running.epoch == 1
    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=_current_authority_roots(case),
    )
    first = consumer.execute(case["request"], case["adapter"])
    second = consumer.execute(case["request"], case["adapter"])

    assert first == second
    assert first.state is ConsumptionState.SUCCEEDED
    assert first.provider_receipt is not None
    assert first.probe_receipt is not None
    assert first.action_receipt is not None
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1
    assert case["store"].snapshot().stopped is False


def test_runtime_rejects_swapped_p18_or_p16_packet_external_root(
    production_case,
) -> None:
    case = production_case
    with pytest.raises(
        ProductionConsumerError, match="P16/P18 execution authority pin mismatch"
    ):
        _runtime_from_case(
            case,
            expected_launch_handoff_authority_sha256="0" * 64,
        )
    with pytest.raises(
        ProductionConsumerError, match="P16/P18 execution authority pin mismatch"
    ):
        _runtime_from_case(
            case,
            expected_repository_acceptance_authority_pins_sha256="0" * 64,
        )
    with pytest.raises(
        ProductionConsumerError, match="P16/P18 execution authority pin mismatch"
    ):
        _runtime_from_case(
            case,
            expected_launch_semantic_authority_pins_sha256="0" * 64,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_request_cannot_substitute_launch_semantic_packet_or_root(
    production_case,
) -> None:
    case = production_case
    values = {
        field: getattr(case["request"], field)
        for field in type(case["request"]).model_fields
        if field != "request_sha256"
    }
    values["launch_semantic_packet_sha256"] = "f" * 64
    packet_substitution = build_production_consumption_request(**values)
    assert case["runtime"].verifies(packet_substitution, at=AT) is False

    values = {
        field: getattr(case["request"], field)
        for field in type(case["request"]).model_fields
        if field != "request_sha256"
    }
    values["launch_semantic_authority_sha256"] = "e" * 64
    root_substitution = build_production_consumption_request(**values)
    assert case["runtime"].verifies(root_substitution, at=AT) is False
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_execution_boundary_rejects_a_different_measurement_dossier(
    production_case,
) -> None:
    case = production_case
    request = case["request"]
    assert request.measurement_bundle is not None
    assert case["runtime"].verifies_execution_boundary(request, at=AT) is True
    foreign_dossier = request.measurement_bundle.dossier.model_copy(
        update={"evidence_version": "foreign-valid-envelope"}
    )
    foreign_bundle = MeasurementBoundDossier(
        report=request.measurement_bundle.report,
        dossier=foreign_dossier,
        dossier_sha256=hash_signed_artifact(foreign_dossier),
    )
    values = {
        field: getattr(request, field)
        for field in type(request).model_fields
        if field != "request_sha256"
    }
    values["measurement_bundle"] = foreign_bundle
    attacked = build_production_consumption_request(**values)

    assert case["runtime"].verifies_execution_boundary(attacked, at=AT) is False


def test_execution_boundary_rejects_a_rehashed_provider_target_splice(
    production_case,
) -> None:
    case = production_case
    request = case["request"]
    external_values = request.external_request.model_dump(
        exclude={"request_sha256"}
    )
    external_values["target_sha256"] = "f" * 64
    changed_external = build_external_action_request(**external_values)
    values = {
        field: getattr(request, field)
        for field in type(request).model_fields
        if field != "request_sha256"
    }
    values["external_request"] = changed_external
    attacked = build_production_consumption_request(**values)

    assert case["runtime"].verifies_execution_boundary(attacked, at=AT) is False


def test_backdated_signed_clock_persists_stop_before_provider(production_case) -> None:
    case = production_case
    _reset(case)

    def backdated(request):
        return sign_production_consumer_clock_attestation(
            request,
            case["p15"]["trust"],
            p15_fixtures.TIME_PRIVATE,
            observed_at=AT - timedelta(hours=1),
            issued_at=AT,
            expires_at=AT + timedelta(seconds=30),
        )

    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=backdated,
        current_authority_roots=_current_authority_roots(case),
    )
    with pytest.raises(ProductionConsumerError, match="persistent STOP"):
        consumer.execute(case["request"], case["adapter"])
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_current_root_change_persists_stop_before_provider(production_case) -> None:
    case = production_case
    _reset(case)

    def replaced(request):
        return sign_production_authority_roots(
            request,
            case["p15"]["trust"],
            p15_fixtures.STORAGE_PRIVATE,
            revision=2,
            repository_acceptance_authority_sha256="f" * 64,
            launch_handoff_authority_sha256=case["p16"]["authority_root"],
            launch_semantic_authority_sha256=(
                case["p16"]["semantic_authority_root"]
            ),
            observed_at=AT,
            issued_at=AT,
            expires_at=AT + timedelta(seconds=30),
        )

    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=replaced,
    )
    with pytest.raises(ProductionConsumerError, match="persistent STOP"):
        consumer.execute(case["request"], case["adapter"])
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_current_semantic_root_change_persists_stop_before_provider(
    production_case,
) -> None:
    case = production_case
    _reset(case)

    def replaced(request):
        return sign_production_authority_roots(
            request,
            case["p15"]["trust"],
            p15_fixtures.STORAGE_PRIVATE,
            revision=2,
            repository_acceptance_authority_sha256=(
                case["p16"]["repository_authority_root"]
            ),
            launch_handoff_authority_sha256=case["p16"]["authority_root"],
            launch_semantic_authority_sha256="f" * 64,
            observed_at=AT,
            issued_at=AT,
            expires_at=AT + timedelta(seconds=30),
        )

    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=replaced,
    )
    with pytest.raises(ProductionConsumerError, match="persistent STOP"):
        consumer.execute(case["request"], case["adapter"])
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_authority_root_revision_cannot_roll_back_after_store_reopen(
    production_case,
) -> None:
    case = production_case
    _reset(case)
    revision_two = _runtime_from_case(
        case,
        current_authority_roots=_current_authority_roots(case, revision=2),
    )
    case["store"].claim(
        case["request"], revision_two, case["p11"]["private"], at=AT
    )
    path = case["store"].path
    case["store"].close()
    reopened = GlobalStopStore(
        path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    with pytest.raises(ProductionConsumerError, match="persistent STOP"):
        reopened.claim(
            case["request"], case["runtime"], case["p11"]["private"], at=AT
        )
    assert reopened.snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_post_provider_clock_timeout_commits_unknown_without_deadlock(
    production_case,
) -> None:
    case = production_case
    _reset(case)
    calls = 0

    def clock(request):
        nonlocal calls
        calls += 1
        if calls == 4:
            time.sleep(case["policy"].clock_response_timeout_seconds + 1)
        return _consumer_clock_attest(case, lambda: AT)(request)

    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=clock,
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(case["request"], case["adapter"])
    assert result.state is ConsumptionState.UNKNOWN
    # The provider's signed fact was already durably verified by the store's
    # independent POST_PROVIDER authority phase before the wrapper clock failed.
    assert result.provider_receipt is not None
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_store_post_provider_clock_failure_retains_signed_provider_fact(
    production_case,
) -> None:
    case = production_case
    _reset(case)

    def clock(request):
        if request.purpose.value == "post_provider":
            time.sleep(case["policy"].clock_response_timeout_seconds + 1)
        return _consumer_clock_attest(case, lambda: AT)(request)

    runtime = _runtime_from_case(case, clock_attest=clock)
    consumer = ProductionConsumer(
        runtime,
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(case["request"], case["adapter"])
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is not None
    assert result.provider_receipt.observed_post_state_sha256 == POST_STATE
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_dispatch_token_is_clipped_to_effective_p16_expiry(production_case) -> None:
    case = production_case
    observations = {
        receipt.gate: receipt.observed_at
        for receipt in case["p16"]["bundle"].receipts
    }
    expiries = {
        receipt.gate: receipt.expires_at
        for receipt in case["p16"]["bundle"].receipts
    }
    expiries[LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS] = (
        AT + timedelta(seconds=30)
    )
    receipts = p16_fixtures._receipts(
        plan=case["p16"]["plan"],
        policy=case["p16"]["policy"],
        observed_overrides=observations,
        expires_overrides=expiries,
    )
    short_bundle = p16_fixtures._bundle(
        receipts,
        plan=case["p16"]["plan"],
        policy=case["p16"]["policy"],
        repository_acceptance=case["p16"]["bundle"].repository_acceptance,
        launch_semantics=case["p16"]["semantic_packet"],
    )
    runtime = _runtime_from_case(case, launch_handoff_bundle=short_bundle)
    values = {
        name: getattr(case["request"], name)
        for name in type(case["request"]).model_fields
        if name != "request_sha256"
    }
    values["launch_handoff_bundle_sha256"] = short_bundle.bundle_sha256
    request = build_production_consumption_request(**values)
    _reset(case)
    token = case["store"].claim(
        request, runtime, case["p11"]["private"], at=AT
    )
    assert isinstance(token, ProviderDispatchToken)
    assert token.expires_at == AT + timedelta(seconds=30)


def test_incomplete_p16_bundle_stops_before_claim_or_provider(production_case) -> None:
    case = production_case
    incomplete = p16_fixtures._bundle(
        case["p16"]["bundle"].receipts[:-1],
        plan=case["p16"]["plan"],
        policy=case["p16"]["policy"],
        repository_acceptance=case["p16"]["bundle"].repository_acceptance,
        launch_semantics=case["p16"]["semantic_packet"],
    )
    runtime = _runtime_from_case(case, launch_handoff_bundle=incomplete)
    values = {
        name: getattr(case["request"], name)
        for name in type(case["request"]).model_fields
        if name != "request_sha256"
    }
    values["launch_handoff_bundle_sha256"] = incomplete.bundle_sha256
    request = build_production_consumption_request(**values)
    _reset(case)
    before = case["store"].snapshot()
    with pytest.raises(
        ProductionConsumerError, match="production authority verification failed"
    ):
        case["store"].claim(request, runtime, case["p11"]["private"], at=AT)
    after = case["store"].snapshot()
    assert (after.revision, after.epoch, after.head_sha256) == (
        before.revision,
        before.epoch,
        before.head_sha256,
    )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_p16_expiry_between_claim_and_dispatch_never_calls_provider(
    production_case,
) -> None:
    case = production_case
    observations = {
        receipt.gate: receipt.observed_at
        for receipt in case["p16"]["bundle"].receipts
    }
    expiries = {
        receipt.gate: receipt.expires_at
        for receipt in case["p16"]["bundle"].receipts
    }
    expiries[LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS] = (
        AT + timedelta(seconds=30)
    )
    receipts = p16_fixtures._receipts(
        plan=case["p16"]["plan"],
        policy=case["p16"]["policy"],
        observed_overrides=observations,
        expires_overrides=expiries,
    )
    short_bundle = p16_fixtures._bundle(
        receipts,
        plan=case["p16"]["plan"],
        policy=case["p16"]["policy"],
        repository_acceptance=case["p16"]["bundle"].repository_acceptance,
        launch_semantics=case["p16"]["semantic_packet"],
    )
    runtime = _runtime_from_case(case, launch_handoff_bundle=short_bundle)
    values = {
        name: getattr(case["request"], name)
        for name in type(case["request"]).model_fields
        if name != "request_sha256"
    }
    values["launch_handoff_bundle_sha256"] = short_bundle.bundle_sha256
    request = build_production_consumption_request(**values)
    _reset(case)
    clock_values = iter((AT, AT, AT + timedelta(seconds=30), AT + timedelta(seconds=30)))
    consumer = ProductionConsumer(
        runtime,
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: next(clock_values)),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(request, case["adapter"])
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is None
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_naked_or_detached_authority_cannot_dispatch(production_case) -> None:
    case = production_case
    naked_values = {
        name: getattr(case["request"], name)
        for name in case["request"].__class__.model_fields
        if name
        not in {
            "request_sha256",
            "release_report",
            "serving_lease",
            "measurement_bundle",
        }
    }
    with pytest.raises(ValidationError):
        build_production_consumption_request(**naked_values)
    _reset(case)
    claim_values = case["request"].execution_claim.model_dump(
        exclude={"claim_sha256"}
    )
    claim_values["claimed_at"] = AT + timedelta(seconds=1)
    provisional = ActionExecutionClaim.model_construct(
        **claim_values, claim_sha256="0" * 64
    )
    detached = ActionExecutionClaim(
        **claim_values, claim_sha256=hash_action_execution_claim(provisional)
    )
    request_values = {
        name: getattr(case["request"], name)
        for name in case["request"].__class__.model_fields
        if name != "request_sha256"
    }
    request_values["execution_claim"] = detached
    copied = build_production_consumption_request(**request_values)
    assert case["runtime"].verifies(copied, at=AT) is False


def test_wrong_measurement_run_and_exact_expiry_reject(production_case) -> None:
    case = production_case
    values = {
        name: getattr(case["request"], name)
        for name in case["request"].__class__.model_fields
        if name != "request_sha256"
    }
    values["measurement_run_id"] = "wrong-run"
    wrong = build_production_consumption_request(
        **values
    )
    assert case["runtime"].verifies(wrong, at=AT) is False
    assert case["runtime"].verifies(case["request"], at=case["request"].expires_at) is False


def test_provider_prestate_failure_sticks_stop_and_consumes_epoch(production_case) -> None:
    case = production_case
    _reset(case)
    state = json.loads(case["provider_state"].read_text())
    state["targets"][TARGET] = "a" * 64
    case["provider_state"].write_bytes(_canonical_json_bytes(state))
    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(case["request"], case["adapter"])
    snapshot = case["store"].snapshot()
    assert result.state is ConsumptionState.FAILED
    assert result.provider_receipt is not None
    assert snapshot.stopped is True and snapshot.epoch == 2
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_safety_disable_is_allowed_during_stop_and_never_clears_it(production_case) -> None:
    case = production_case
    disable = _disable_request(case)
    state = json.loads(case["provider_state"].read_text())
    state["targets"][TARGET] = POST_STATE
    case["provider_state"].write_bytes(_canonical_json_bytes(state))
    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(disable, case["adapter"])
    assert result.state is ConsumptionState.SUCCEEDED
    assert case["store"].snapshot().stopped is True


def test_reset_is_bound_to_current_stop_head_and_exact_expiry(production_case) -> None:
    case = production_case
    snapshot = case["store"].snapshot()
    reset = sign_global_stop_reset(
        snapshot,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="1" * 64,
        reconciliation_record_sha256=(
            case["p15"]["initial_reconciliation_record"].record_sha256
        ),
        nonce_sha256="4" * 64,
        issued_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=1),
    )
    with pytest.raises(ProductionConsumerError, match="reset is invalid"):
        case["store"].apply_reset(
            reset.model_copy(update={"stop_reason_sha256": "a" * 64}),
            case["runtime"],
            at=AT,
        )
    expired_runtime = _runtime_from_case(
        case,
        clock_attest=_consumer_clock_attest(case, lambda: reset.expires_at),
    )
    with pytest.raises(ProductionConsumerError, match="reset is invalid"):
        case["store"].apply_reset(
            reset,
            expired_runtime,
            # A forged/backdated caller value cannot override signed time.
            at=AT,
        )


def test_reset_rejects_nonexistent_or_stale_reconciliation_record(
    production_case,
) -> None:
    case = production_case
    snapshot = case["store"].snapshot()
    nonexistent = sign_global_stop_reset(
        snapshot,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="1" * 64,
        reconciliation_record_sha256="a" * 64,
        nonce_sha256="b" * 64,
        issued_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=1),
    )
    before = case["store"].snapshot()
    with pytest.raises(ProductionConsumerError, match="reset is invalid"):
        case["store"].apply_reset(nonexistent, case["runtime"], at=AT)
    assert case["store"].snapshot() == before

    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    expired_at = case["p15"]["authorization"].expires_at
    expired_runtime = _runtime_from_case(
        case,
        clock_attest=_consumer_clock_attest(case, lambda: expired_at),
        current_authority_roots=_current_authority_roots(case, at=expired_at),
    )
    stopped = case["store"].redeem(
        case["request"], token, expired_runtime, at=AT
    )
    assert stopped is not None and stopped.state is ConsumptionState.UNKNOWN
    current = case["store"].snapshot()
    stale = sign_global_stop_reset(
        current,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="2" * 64,
        reconciliation_record_sha256=(
            case["p15"]["initial_reconciliation_record"].record_sha256
        ),
        nonce_sha256="c" * 64,
        issued_at=expired_at,
        not_before=expired_at,
        expires_at=expired_at + timedelta(minutes=1),
    )
    with pytest.raises(ProductionConsumerError, match="reset is invalid"):
        case["store"].apply_reset(stale, expired_runtime, at=AT)


def test_restart_with_inflight_claim_becomes_unknown_stop(production_case) -> None:
    case = production_case
    _reset(case)
    case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    case["store"].close()
    reopened = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    snapshot = reopened.snapshot()
    assert snapshot.stopped is True and snapshot.epoch == 2
    result = reopened.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert result.state is ConsumptionState.UNKNOWN
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_live_owner_is_not_recovered_by_late_store_opener(production_case) -> None:
    case = production_case
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    before = case["store"].snapshot()
    late = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    observed = late.snapshot()
    assert (
        observed.stopped,
        observed.epoch,
        observed.revision,
        observed.head_sha256,
    ) == (
        before.stopped,
        before.epoch,
        before.revision,
        before.head_sha256,
    )
    with pytest.raises(ProductionConsumerError, match="not owned"):
        late.redeem(case["request"], token, case["runtime"], at=AT)
    with pytest.raises(ProductionConsumerError, match="not owned"):
        late.commit_result(
            case["request"],
            token,
            case["runtime"],
            state=ConsumptionState.UNKNOWN,
            terminal_at=AT,
        )
    assert case["store"].redeem(
        case["request"], token, case["runtime"], at=AT
    ) is None
    terminal = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert terminal.state is ConsumptionState.UNKNOWN
    late.close()


def test_forked_child_cannot_inherit_parent_dispatch_ownership(
    production_case,
) -> None:
    case = production_case
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    context = multiprocessing.get_context("fork")
    outcomes = context.Queue()

    def child_attempt() -> None:
        try:
            case["store"].redeem(
                case["request"], token, case["runtime"], at=AT
            )
            outcomes.put("redeem-accepted")
        except ProductionConsumerError as exc:
            outcomes.put(str(exc))
        try:
            case["store"].commit_result(
                case["request"],
                token,
                case["runtime"],
                state=ConsumptionState.UNKNOWN,
                terminal_at=AT,
            )
            outcomes.put("commit-accepted")
        except ProductionConsumerError as exc:
            outcomes.put(str(exc))

    child = context.Process(target=child_attempt)
    child.start()
    child.join(timeout=15)
    assert child.exitcode == 0
    child_results = [outcomes.get(timeout=5), outcomes.get(timeout=5)]
    assert all("not owned" in outcome for outcome in child_results)
    assert case["store"].redeem(
        case["request"], token, case["runtime"], at=AT
    ) is None
    result = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert result.state is ConsumptionState.UNKNOWN


def test_owner_death_is_recoverable_while_forked_child_stays_alive(
    production_case, tmp_path
) -> None:
    case = production_case
    _reset(case)
    context = multiprocessing.get_context("fork")
    anchor_path = tmp_path / "fork-owner-anchor.json"
    anchor_revision, anchor_digest = case["anchors"]["p13"]
    anchor_path.write_text(
        json.dumps({"revision": anchor_revision, "digest": anchor_digest}),
        encoding="utf-8",
    )
    owner_marker = tmp_path / "fork-owner-claimed"
    helper_marker = tmp_path / "fork-helper-alive"
    helper_done = tmp_path / "fork-helper-done"
    release_read, release_write = os.pipe()

    def owner_then_exit() -> None:
        os.close(release_write)

        def read_anchor() -> str:
            return json.loads(anchor_path.read_text(encoding="utf-8"))["digest"]

        def commit_anchor(revision: int, digest: str) -> None:
            current = json.loads(anchor_path.read_text(encoding="utf-8"))
            if revision < current["revision"] or (
                revision == current["revision"] and digest != current["digest"]
            ):
                raise ProductionConsumerError("non-monotonic fork anchor")
            anchor_path.write_text(
                json.dumps({"revision": revision, "digest": digest}),
                encoding="utf-8",
            )

        owner_store = GlobalStopStore(
            case["store"].path,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=read_anchor(),
            state_authentication_key=STATE_KEY,
            anchor_commit=commit_anchor,
            anchor_read=read_anchor,
        )
        owner_store.claim(
            case["request"], case["runtime"], case["p11"]["private"], at=AT
        )
        owner_marker.write_text("claimed", encoding="utf-8")
        helper_pid = os.fork()
        if helper_pid == 0:
            helper_marker.write_text("alive", encoding="utf-8")
            os.read(release_read, 1)
            helper_done.write_text("done", encoding="utf-8")
            os._exit(0)
        os.close(release_read)

    owner = context.Process(target=owner_then_exit)
    owner.start()
    os.close(release_read)
    deadline = time.monotonic() + 15
    while (
        not owner_marker.exists() or not helper_marker.exists()
    ) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert owner_marker.exists() and helper_marker.exists()
    deadline = time.monotonic() + 5
    while owner.exitcode is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert owner.exitcode == 0

    child_anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    case["anchors"]["p13"] = (
        child_anchor["revision"],
        child_anchor["digest"],
    )
    try:
        recovered = GlobalStopStore(
            case["store"].path,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=case["anchor_read"](),
            state_authentication_key=STATE_KEY,
            anchor_commit=case["anchor_commit"],
            anchor_read=case["anchor_read"],
        )
        result = recovered.claim(
            case["request"], case["runtime"], case["p11"]["private"], at=AT
        )
        assert result.state is ConsumptionState.UNKNOWN
        assert recovered.snapshot().stopped is True
    finally:
        os.write(release_write, b"x")
        os.close(release_write)
    deadline = time.monotonic() + 5
    while not helper_done.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert helper_done.exists()
    owner.join(timeout=5)


def test_restart_after_provider_journal_preserves_fact_and_stops(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    before = case["store"].snapshot()
    case["store"].close()
    reopened = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    result = reopened.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    after = reopened.snapshot()
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt == provider
    assert result.probe_receipt is None and result.action_receipt is None
    assert after.stopped is True and after.epoch == before.epoch + 1
    assert after.revision == before.revision + 1
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_restart_before_provider_journal_does_not_invent_fact(
    production_case,
) -> None:
    case = production_case
    _claim_and_redeem(case)
    case["store"].close()
    reopened = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    result = reopened.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is None
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_process_crash_after_provider_call_before_journal_never_retries(
    production_case, tmp_path, monkeypatch
) -> None:
    case = production_case
    _reset(case)
    context = multiprocessing.get_context("fork")
    anchor_path = tmp_path / "prejournal-crash-anchor.json"
    anchor_revision, anchor_digest = case["anchors"]["p13"]
    anchor_path.write_text(
        json.dumps({"revision": anchor_revision, "digest": anchor_digest}),
        encoding="utf-8",
    )
    original_invoke = SubprocessProviderAdapter._invoke

    def invoke_then_exit(
        adapter,
        command,
        token,
        *,
        capability,
        absolute_deadline,
    ):
        original_invoke(
            adapter,
            command,
            token,
            capability=capability,
            absolute_deadline=absolute_deadline,
        )
        os._exit(23)

    monkeypatch.setattr(SubprocessProviderAdapter, "_invoke", invoke_then_exit)

    def crash_after_call() -> None:
        def read_anchor() -> str:
            return json.loads(anchor_path.read_text(encoding="utf-8"))["digest"]

        def commit_anchor(revision: int, digest: str) -> None:
            current = json.loads(anchor_path.read_text(encoding="utf-8"))
            if revision < current["revision"] or (
                revision == current["revision"] and digest != current["digest"]
            ):
                raise ProductionConsumerError("non-monotonic crash anchor")
            anchor_path.write_text(
                json.dumps({"revision": revision, "digest": digest}),
                encoding="utf-8",
            )

        owner_store = GlobalStopStore(
            case["store"].path,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=read_anchor(),
            state_authentication_key=STATE_KEY,
            anchor_commit=commit_anchor,
            anchor_read=read_anchor,
        )
        token = owner_store.claim(
            case["request"], case["runtime"], case["p11"]["private"], at=AT
        )
        assert owner_store.redeem(
            case["request"], token, case["runtime"], at=AT
        ) is None

        case["adapter"].execute(
            case["request"],
            token,
            owner_store,
            case["runtime"],
            at=AT,
        )

    owner = context.Process(target=crash_after_call)
    owner.start()
    owner.join(timeout=15)
    assert owner.exitcode == 23
    child_anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    case["anchors"]["p13"] = (
        child_anchor["revision"],
        child_anchor["digest"],
    )
    recovered = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    result = recovered.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is None
    assert recovered.snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_provider_exception_after_side_effect_cannot_retry_in_same_process(
    production_case, monkeypatch,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    side_effects = 0

    def disconnect_after_side_effect(_adapter, _command, _token, **_kwargs):
        nonlocal side_effects
        side_effects += 1
        raise RuntimeError("synthetic disconnect after mutation")

    monkeypatch.setattr(
        SubprocessProviderAdapter, "_invoke", disconnect_after_side_effect
    )

    with pytest.raises(RuntimeError, match="disconnect after mutation"):
        case["adapter"].execute(
            case["request"],
            token,
            case["store"],
            case["runtime"],
            at=AT,
        )
    with pytest.raises(ProductionConsumerError, match="stale|replay"):
        case["adapter"].execute(
            case["request"],
            token,
            case["store"],
            case["runtime"],
            at=AT,
        )
    assert side_effects == 1
    result = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert result.state is ConsumptionState.UNKNOWN


def test_provider_base_exception_is_closed_to_unknown_stop(
    production_case, monkeypatch
) -> None:
    case = production_case
    token = _claim_and_redeem(case)

    class ProviderAbort(BaseException):
        pass

    def abort(_adapter, _command, _token, **_kwargs):
        raise ProviderAbort("synthetic provider abort")

    monkeypatch.setattr(SubprocessProviderAdapter, "_invoke", abort)

    with pytest.raises(ProviderAbort, match="provider abort"):
        case["adapter"].execute(
            case["request"],
            token,
            case["store"],
            case["runtime"],
            at=AT,
        )
    snapshot = case["store"].snapshot()
    assert snapshot.stopped is True and snapshot.epoch == token.epoch + 1
    with sqlite3.connect(case["store"].path) as connection:
        row = connection.execute(
            "SELECT state, result_json FROM production_dispatches "
            "WHERE request_sha256=?",
            (case["request"].request_sha256,),
        ).fetchone()
    assert row[0] == ConsumptionState.UNKNOWN.value
    assert ProductionConsumptionResult.model_validate_json(row[1]).state is ConsumptionState.UNKNOWN


def test_callback_and_anchor_double_fault_quarantines_launch_until_recovery(
    production_case, monkeypatch,
) -> None:
    case = production_case
    _reset(case)
    case["store"].close()
    anchor_available = True

    def flaky_read() -> str:
        if not anchor_available:
            raise RuntimeError("synthetic close-time anchor outage")
        return case["anchor_read"]()

    store = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=flaky_read,
    )
    case["store"] = store
    token = store.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert store.redeem(
        case["request"], token, case["runtime"], at=AT
    ) is None

    def disconnect_after_anchor_loss(_adapter, _command, _token, **_kwargs):
        nonlocal anchor_available
        anchor_available = False
        raise RuntimeError("synthetic provider disconnect")

    monkeypatch.setattr(
        SubprocessProviderAdapter, "_invoke", disconnect_after_anchor_loss
    )

    with pytest.raises(
        ProductionConsumerError,
        match=r"UNKNOWN\+STOP could not be committed",
    ):
        case["adapter"].execute(
            case["request"],
            token,
            store,
            case["runtime"],
            at=AT,
        )
    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            "SELECT state, result_json FROM production_dispatches "
            "WHERE request_sha256=?",
            (case["request"].request_sha256,),
        ).fetchone()
    assert row == (ConsumptionState.DISPATCHED.value, None)

    seal = store._provider_capability_seal
    production_consumer_module._PROVIDER_CAPABILITY_STORES[seal] = (
        production_consumer_module.weakref.ref(store)
    )
    assert store._acquire_inflight_owner() is False
    permit = object()
    production_consumer_module._PROVIDER_CAPABILITY_PERMITS[seal] = permit
    with pytest.raises(ProductionConsumerError, match="issuer is invalid"):
        production_consumer_module._issue_provider_invocation_capability(
            seal,
            permit,
            token,
            "execute",
            AT,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0

    anchor_available = True
    recovered = GlobalStopStore(
        store.path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    result = recovered.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert result.state is ConsumptionState.UNKNOWN
    assert recovered.snapshot().stopped is True


def test_raw_adapter_invocation_requires_a_store_issued_capability(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    with pytest.raises(
        ProductionConsumerError, match="store-issued capability"
    ):
        case["adapter"]._invoke(
            "execute",
            token,
            capability=object(),
            absolute_deadline=time.monotonic() + 1,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )


def test_store_rejects_arbitrary_provider_callback_before_attempt_intent(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    before = case["store"].snapshot()

    class StructuralFakePort:
        def validates(self, *_args):
            return True

    assert not hasattr(case["store"], "invoke_and_record_provider")
    with pytest.raises(
        ProductionConsumerError, match="exact subprocess provider execution port"
    ):
        case["store"]._invoke_and_record_provider(
            case["request"],
            token,
            case["runtime"],
            StructuralFakePort(),
            at=AT,
        )
    after = case["store"].snapshot()
    assert (after.revision, after.head_sha256, after.epoch) == (
        before.revision,
        before.head_sha256,
        before.epoch,
    )
    with sqlite3.connect(case["store"].path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM production_provider_attempt_intents"
        ).fetchone()[0] == 0
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )


def test_forged_internal_permit_cannot_cross_authenticated_stop_state(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert case["store"].snapshot().stopped is True
    seal = case["store"]._provider_capability_seal
    permit = object()
    production_consumer_module._PROVIDER_CAPABILITY_PERMITS[seal] = permit
    capability = (
        production_consumer_module._issue_provider_invocation_capability(
            seal,
            permit,
            token,
            "execute",
            AT,
        )
    )
    with pytest.raises(ProductionConsumerError, match="durable authority"):
        case["adapter"]._invoke(
            "execute",
            token,
            capability=capability,
            absolute_deadline=time.monotonic() + 1,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


@pytest.mark.parametrize("invalid_kind", ("wrong-key", "wrong-dispatch"))
def test_wrong_key_and_dispatch_provider_receipts_never_become_verified_facts(
    production_case, invalid_kind: str, monkeypatch,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)

    def receipt(private_key, *, dispatch_sha: str) -> ProviderResultReceipt:
        return _build_signed_model(
            ProviderResultReceipt,
            {
                "issuer": case["trust"].provider_adapter.issuer,
                "signer_role": SigningRole.PROVIDER_ADAPTER,
                "scope": ProductionSignatureScope.PROVIDER_RESULT,
                "dispatch_payload_sha256": dispatch_sha,
                "store_id_sha256": token.store_id_sha256,
                "epoch": token.epoch,
                "fencing_token": token.fencing_token,
                "operation": token.operation,
                "adapter_id": token.adapter_id,
                "target_sha256": token.target_sha256,
                "idempotency_key_sha256": token.idempotency_key_sha256,
                "outcome": ProviderOutcome.UNKNOWN,
                "observed_pre_state_sha256": token.expected_pre_state_sha256,
                "observed_post_state_sha256": token.expected_pre_state_sha256,
                "provider_audit_receipt_sha256": "e" * 64,
                "started_at": AT,
                "completed_at": AT,
            },
            private_key,
            issuer=case["trust"].provider_adapter.issuer,
            role=SigningRole.PROVIDER_ADAPTER,
        )

    token_values = token.model_dump(
        exclude={"key_id_sha256", "payload_sha256", "signature_base64url"}
    )
    token_values["policy_sha256"] = "b" * 64
    alternate_policy_token = _build_signed_model(
        ProviderDispatchToken,
        token_values,
        case["p11"]["private"],
        issuer=case["trust"].dispatcher.issuer,
        role=SigningRole.EXECUTOR,
    )
    invalid = {
        "wrong-key": receipt(
            Ed25519PrivateKey.generate(), dispatch_sha=token.payload_sha256
        ),
        "wrong-dispatch": receipt(
            case["provider_private"],
            dispatch_sha=alternate_policy_token.payload_sha256,
        ),
    }[invalid_kind]
    monkeypatch.setattr(
        SubprocessProviderAdapter,
        "_invoke",
        lambda *_args, **_kwargs: invalid.model_dump(mode="json"),
    )
    before = case["store"].snapshot()
    with pytest.raises(ProductionConsumerError, match="unauthoritative receipt"):
        case["adapter"].execute(
            case["request"],
            token,
            case["store"],
            case["runtime"],
            at=AT,
        )
    current = case["store"].snapshot()
    assert current.revision == before.revision + 2
    assert current.epoch == before.epoch + 1
    assert current.stopped is True
    with sqlite3.connect(case["store"].path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM production_provider_receipts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM production_provider_attempt_intents"
        ).fetchone()[0] == 1
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0
    stopped = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert stopped.provider_receipt is None


def test_duplicate_provider_invocation_is_revision_neutral(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    first = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    before = case["store"].snapshot()
    second = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    after = case["store"].snapshot()
    assert second == first
    assert after.revision == before.revision
    assert after.head_sha256 == before.head_sha256
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        provider_receipt=first,
        terminal_at=AT,
    )


def test_unjournaled_provider_fact_cannot_enter_terminal_result(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = _signed_provider_receipt(case, token)
    with pytest.raises(ProductionConsumerError, match="must be journaled"):
        case["store"].commit_result(
            case["request"],
            token,
            case["runtime"],
            state=ConsumptionState.UNKNOWN,
            provider_receipt=provider,
            terminal_at=AT,
        )
    stopped = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert stopped.provider_receipt is None


def test_provider_journal_rows_are_append_only(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    with sqlite3.connect(case["store"].path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE production_provider_receipts SET verified_at=? "
                "WHERE request_sha256=?",
                ((AT + timedelta(seconds=1)).isoformat(), case["request"].request_sha256),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM production_provider_receipts WHERE request_sha256=?",
                (case["request"].request_sha256,),
            )
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        provider_receipt=provider,
        terminal_at=AT,
    )


def test_anchor_outage_after_provider_journal_preserves_fact_as_unknown(
    production_case,
) -> None:
    case = production_case
    base = _reset(case)
    failed = False

    def flaky_commit(revision: int, digest: str) -> None:
        nonlocal failed
        if revision == base.revision + 4 and not failed:
            failed = True
            raise RuntimeError("synthetic provider-journal anchor outage")
        case["anchor_commit"](revision, digest)

    store = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=flaky_commit,
        anchor_read=case["anchor_read"],
    )
    consumer = ProductionConsumer(
        case["runtime"],
        store,
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: AT),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(case["request"], case["adapter"])
    assert failed is True
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is not None
    assert result.provider_receipt.observed_post_state_sha256 == POST_STATE
    assert store.snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_probe_cannot_use_backdated_time_after_provider_journal_commit(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"],
        token,
        case["store"],
        _runtime_at(case, AT + timedelta(seconds=1)),
        at=AT,
    )
    assert provider.completed_at == AT + timedelta(seconds=1)
    with pytest.raises(ProductionConsumerError, match="persistent STOP"):
        case["adapter"].probe(
            case["request"], token, case["store"], case["runtime"], at=AT
        )
    assert case["store"].snapshot().stopped is True


def test_conflicting_idempotency_has_one_claim_winner(production_case) -> None:
    case = production_case
    _reset(case)
    first = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    values = {
        name: getattr(case["request"], name)
        for name in case["request"].__class__.model_fields
        if name != "request_sha256"
    }
    values["request_id"] = "p13-activation-conflict"
    conflicting = build_production_consumption_request(**values)
    with pytest.raises(ProductionConsumerError, match="idempotency reuse"):
        case["store"].claim(
            conflicting, case["runtime"], case["p11"]["private"], at=AT
        )
    assert first.request_sha256 == case["request"].request_sha256


def test_db_rollback_and_executable_swap_fail_closed(production_case, tmp_path) -> None:
    case = production_case
    old_db = tmp_path / "old.sqlite"
    shutil.copy2(case["store"].path, old_db)
    _reset(case)
    shutil.copy2(old_db, case["store"].path)
    with pytest.raises(ProductionConsumerError, match="anchor mismatch"):
        GlobalStopStore(
            case["store"].path,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=case["anchor_read"](),
            state_authentication_key=STATE_KEY,
            anchor_commit=case["anchor_commit"],
            anchor_read=case["anchor_read"],
        )
    altered = tmp_path / "adapter.py"
    altered.write_text("raise SystemExit(0)\n", encoding="utf-8")
    with pytest.raises(ProductionConsumerError, match="digest mismatch"):
        SubprocessProviderAdapter(
            execute_script_path=altered,
            expected_execute_executable_sha256=(
                case["request"].adapter_executable_sha256
            ),
            probe_script_path=PROBE_SCRIPT,
            expected_probe_executable_sha256=(
                case["request"].probe_executable_sha256
            ),
            python_executable_path=PYTHON_EXECUTABLE,
            expected_python_executable_sha256=(
                case["request"].python_executable_sha256
            ),
            dependency_paths=production_adapter_dependency_paths(),
            expected_dependency_closure_sha256=(
                case["request"].adapter_dependency_closure_sha256
            ),
            state_path=case["provider_state"],
            provider_private_key_path=tmp_path / "missing-provider",
            probe_private_key_path=tmp_path / "missing-probe",
            dispatcher_verification_key_path=tmp_path / "missing-dispatcher",
            allowlist_path=tmp_path / "missing-allowlist",
            postcondition_schema_path=POSTCONDITION_SCHEMA,
            adapter_id="synthetic-adapter",
        )


def _claim_and_redeem(case):
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert case["store"].redeem(
        case["request"], token, case["runtime"], at=AT
    ) is None
    return token


def _signed_provider_receipt(case, token) -> ProviderResultReceipt:
    return _build_signed_model(
        ProviderResultReceipt,
        {
            "issuer": case["trust"].provider_adapter.issuer,
            "signer_role": SigningRole.PROVIDER_ADAPTER,
            "scope": ProductionSignatureScope.PROVIDER_RESULT,
            "dispatch_payload_sha256": token.payload_sha256,
            "store_id_sha256": token.store_id_sha256,
            "epoch": token.epoch,
            "fencing_token": token.fencing_token,
            "operation": token.operation,
            "adapter_id": token.adapter_id,
            "target_sha256": token.target_sha256,
            "idempotency_key_sha256": token.idempotency_key_sha256,
            "outcome": ProviderOutcome.SUCCEEDED,
            "observed_pre_state_sha256": token.expected_pre_state_sha256,
            "observed_post_state_sha256": token.expected_post_state_sha256,
            "provider_audit_receipt_sha256": "e" * 64,
            "started_at": AT,
            "completed_at": AT,
        },
        case["provider_private"],
        issuer=case["trust"].provider_adapter.issuer,
        role=SigningRole.PROVIDER_ADAPTER,
    )


def _invoke_execute_through_store(case, token, adapter=None):
    selected = adapter or case["adapter"]
    return selected.execute(
        case["request"],
        token,
        case["store"],
        case["runtime"],
        at=AT,
    )


def _valid_terminal_receipts(case, token):
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    probe = case["adapter"].probe(
        case["request"], token, case["store"], case["runtime"], at=AT
    )
    action = sign_action_receipt(
        case["request"].external_request,
        case["request"].human_approval,
        case["request"].controller_grant,
        case["request"].execution_claim,
        case["p11"]["guard"],
        case["p11"]["private"],
        issuer=case["trust"].dispatcher.issuer,
        result=ActionResult.SUCCEEDED,
        observed_pre_state_sha256=token.expected_pre_state_sha256,
        observed_post_state_sha256=token.expected_post_state_sha256,
        provider_operation_sha256=provider.payload_sha256,
        provider_audit_receipt_sha256=provider.provider_audit_receipt_sha256,
    )
    return provider, probe, action


def test_activation_request_requires_p15_plan_and_authorization(production_case) -> None:
    excluded = {
        "request_sha256",
        "production_integration_plan_sha256",
        "production_readiness_authorization_sha256",
    }
    values = {
        name: getattr(production_case["request"], name)
        for name in production_case["request"].__class__.model_fields
        if name not in excluded
    }
    with pytest.raises(ValidationError, match="P15 authority"):
        build_production_consumption_request(**values)


@pytest.mark.parametrize(
    "field",
    (
        "production_integration_plan_sha256",
        "production_readiness_authorization_sha256",
    ),
)
def test_p15_plan_or_authorization_splice_is_rejected_before_claim(
    production_case, field: str
) -> None:
    case = production_case
    _reset(case)
    values = {
        name: getattr(case["request"], name)
        for name in case["request"].__class__.model_fields
        if name != "request_sha256"
    }
    values[field] = "0" * 64
    spliced = build_production_consumption_request(**values)
    before = case["store"].snapshot()
    provider_before = json.loads(case["provider_state"].read_text())
    with pytest.raises(ProductionConsumerError, match="authority verification"):
        case["store"].claim(
            spliced, case["runtime"], case["p11"]["private"], at=AT
        )
    after = case["store"].snapshot()
    assert (after.revision, after.epoch, after.head_sha256) == (
        before.revision,
        before.epoch,
        before.head_sha256,
    )
    assert json.loads(case["provider_state"].read_text()) == provider_before


def test_p15_exact_expiry_after_claim_redeems_to_unknown_stop(production_case) -> None:
    case = production_case
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    expired_at = case["p15"]["authorization"].expires_at
    assert expired_at == token.expires_at
    result = case["store"].redeem(
        case["request"], token, _runtime_at(case, expired_at), at=AT
    )
    assert result is not None and result.state is ConsumptionState.UNKNOWN
    assert case["store"].snapshot().stopped is True
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_p15_expiry_blocks_provider_probe_and_terminal_success(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider, probe, action = _valid_terminal_receipts(case, token)
    expired_at = case["p15"]["authorization"].expires_at
    with pytest.raises(ProductionConsumerError, match="receipts or authority"):
        case["store"].commit_result(
            case["request"],
            token,
            _runtime_at(case, expired_at),
            state=ConsumptionState.SUCCEEDED,
            provider_receipt=provider,
            probe_receipt=probe,
            action_receipt=action,
            terminal_at=expired_at,
        )


def test_p15_exact_expiry_blocks_provider_before_external_mutation(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    expired_at = case["p15"]["authorization"].expires_at
    before = json.loads(case["provider_state"].read_text())
    with pytest.raises(ProductionConsumerError, match="dispatch fence is stale or invalid"):
        case["adapter"].execute(
            case["request"], token, case["store"], _runtime_at(case, expired_at), at=AT,
        )
    assert json.loads(case["provider_state"].read_text()) == before


def test_p15_exact_expiry_blocks_probe_before_child_launch(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    expired_at = case["p15"]["authorization"].expires_at
    with pytest.raises(ProductionConsumerError, match="dispatch fence is stale or invalid"):
        case["adapter"].probe(
            case["request"], token, case["store"], _runtime_at(case, expired_at), at=AT
        )


def test_p15_expiry_does_not_block_human_approved_safety_disable(
    production_case,
) -> None:
    case = production_case
    disable = _disable_request(case)
    state = json.loads(case["provider_state"].read_text())
    state["targets"][TARGET] = POST_STATE
    case["provider_state"].write_bytes(_canonical_json_bytes(state))
    expired_at = case["p15"]["authorization"].expires_at
    runtime = _runtime_at(case, expired_at)
    consumer = ProductionConsumer(
        runtime,
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, lambda: expired_at),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(disable, case["adapter"])
    assert result.state is ConsumptionState.SUCCEEDED
    assert case["store"].snapshot().stopped is True


def test_revocation_after_claim_redeems_to_atomic_unknown_stop(production_case) -> None:
    case = production_case
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    authority = ExternalActionAuthority(
        case["p11"]["policy"],
        case["p11"]["trust"],
        case["p11"]["controller_private"],
    )
    revoke_execution_grant(
        case["request"].external_request,
        case["request"].controller_grant,
        authority,
        case["p11"]["guard"],
        reason_record_sha256="9" * 64,
        issued_at=AT,
        effective_at=AT,
    )

    result = case["store"].redeem(
        case["request"], token, case["runtime"], at=AT
    )
    snapshot = case["store"].snapshot()
    assert result is not None and result.state is ConsumptionState.UNKNOWN
    assert snapshot.stopped is True and snapshot.epoch == 2
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_p11_revocation_writer_is_fenced_during_external_mutation(
    production_case,
) -> None:
    case = production_case
    authority = ExternalActionAuthority(
        case["p11"]["policy"],
        case["p11"]["trust"],
        case["p11"]["controller_private"],
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with case["p11"]["guard"].dispatch_fence(
            case["request"].external_request,
            case["request"].human_approval,
            case["request"].controller_grant,
            case["request"].execution_claim,
            at=AT,
            not_after=AT + timedelta(seconds=1),
        ):
            future = pool.submit(
                revoke_execution_grant,
                case["request"].external_request,
                case["request"].controller_grant,
                authority,
                case["p11"]["guard"],
                reason_record_sha256="a" * 64,
                issued_at=AT,
                effective_at=AT,
            )
            time.sleep(0.1)
            assert future.done() is False
        assert future.result(timeout=2) is not None


def test_future_effective_revocation_blocks_the_whole_provider_window(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    authority = ExternalActionAuthority(
        case["p11"]["policy"],
        case["p11"]["trust"],
        case["p11"]["controller_private"],
    )
    revoke_execution_grant(
        case["request"].external_request,
        case["request"].controller_grant,
        authority,
        case["p11"]["guard"],
        reason_record_sha256="b" * 64,
        issued_at=AT,
        effective_at=AT + timedelta(seconds=1),
    )
    with pytest.raises(ExternalActionInputError, match="revoked"):
        case["adapter"].execute(
            case["request"],
            token,
            case["store"],
            case["runtime"],
            at=AT,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0
    case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )


def test_revocation_after_provider_preserves_factual_receipt_and_stops(production_case) -> None:
    case = production_case
    _reset(case)
    authority = ExternalActionAuthority(
        case["p11"]["policy"],
        case["p11"]["trust"],
        case["p11"]["controller_private"],
    )
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 5:
            revoke_execution_grant(
                case["request"].external_request,
                case["request"].controller_grant,
                authority,
                case["p11"]["guard"],
                reason_record_sha256="a" * 64,
                issued_at=AT,
                effective_at=AT,
            )
        return AT

    consumer = ProductionConsumer(
        case["runtime"],
        case["store"],
        case["p11"]["private"],
        clock_attest=_consumer_clock_attest(case, clock),
        current_authority_roots=_current_authority_roots(case),
    )
    result = consumer.execute(case["request"], case["adapter"])
    snapshot = case["store"].snapshot()
    assert result.state is ConsumptionState.UNKNOWN
    assert result.provider_receipt is not None
    assert result.provider_receipt.observed_post_state_sha256 == POST_STATE
    assert result.probe_receipt is None and result.action_receipt is None
    assert snapshot.stopped is True and snapshot.epoch == 2
    assert json.loads(case["provider_state"].read_text())["call_count"] == 1


def test_exact_dispatch_expiry_redeems_to_unknown_stop(production_case) -> None:
    case = production_case
    _reset(case)
    token = case["store"].claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    result = case["store"].redeem(
        case["request"], token, _runtime_at(case, token.expires_at), at=AT
    )
    snapshot = case["store"].snapshot()
    assert result is not None and result.state is ConsumptionState.UNKNOWN
    assert snapshot.stopped is True and snapshot.epoch == 2
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_old_token_cannot_cross_adapter_fence_after_stop(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    stopped = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        terminal_at=AT,
    )
    assert stopped.state is ConsumptionState.UNKNOWN
    with pytest.raises(ProductionConsumerError, match="dispatch fence"):
        case["adapter"].execute(
            case["request"], token, case["store"], case["runtime"], at=AT,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_direct_success_commit_rejects_forged_provider_receipt(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider, probe, action = _valid_terminal_receipts(case, token)
    forged = provider.model_copy(update={"signature_base64url": "A" * 86})
    with pytest.raises(ProductionConsumerError, match="immutable journal"):
        case["store"].commit_result(
            case["request"],
            token,
            case["runtime"],
            state=ConsumptionState.SUCCEEDED,
            terminal_at=AT,
            provider_receipt=forged,
            probe_receipt=probe,
            action_receipt=action,
        )
    assert case["store"].snapshot().stopped is False


def test_valid_conflicting_provider_receipt_cannot_replace_journal(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    values = provider.model_dump(
        exclude={"key_id_sha256", "payload_sha256", "signature_base64url"}
    )
    values["provider_audit_receipt_sha256"] = "d" * 64
    conflicting = _build_signed_model(
        ProviderResultReceipt,
        values,
        case["provider_private"],
        issuer=case["trust"].provider_adapter.issuer,
        role=SigningRole.PROVIDER_ADAPTER,
    )
    assert conflicting != provider
    assert case["runtime"].verifies_provider_result(
        token, conflicting, at=AT
    )
    before = case["store"].snapshot()
    with pytest.raises(ProductionConsumerError, match="immutable journal"):
        case["store"].commit_result(
            case["request"],
            token,
            case["runtime"],
            state=ConsumptionState.UNKNOWN,
            provider_receipt=conflicting,
            terminal_at=AT,
        )
    after = case["store"].snapshot()
    assert after.revision == before.revision
    result = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        provider_receipt=provider,
        terminal_at=AT,
    )
    assert result.provider_receipt == provider


def test_success_rejects_authoritative_p11_receipt_for_other_provider_facts(
    production_case,
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    probe = case["adapter"].probe(
        case["request"], token, case["store"], case["runtime"], at=AT
    )
    unrelated = sign_action_receipt(
        case["request"].external_request,
        case["request"].human_approval,
        case["request"].controller_grant,
        case["request"].execution_claim,
        case["p11"]["guard"],
        case["p11"]["private"],
        issuer=case["trust"].dispatcher.issuer,
        result=ActionResult.SUCCEEDED,
        observed_pre_state_sha256=token.expected_pre_state_sha256,
        observed_post_state_sha256=token.expected_post_state_sha256,
        provider_operation_sha256="1" * 64,
        provider_audit_receipt_sha256="2" * 64,
    )
    with pytest.raises(ProductionConsumerError, match="receipts or authority"):
        case["store"].commit_result(
            case["request"],
            token,
            case["runtime"],
            state=ConsumptionState.SUCCEEDED,
            terminal_at=AT,
            provider_receipt=provider,
            probe_receipt=probe,
            action_receipt=unrelated,
        )


def test_store_rejects_alternate_runtime_policy_before_replay(production_case) -> None:
    case = production_case
    alternate_policy = ProductionConsumerPolicy(
        **{
            **case["policy"].model_dump(),
            "policy_id": "p13-alternate-policy",
        }
    )
    before = case["store"].snapshot()
    with pytest.raises(ProductionConsumerError, match="consumer pin mismatch"):
        ProductionConsumerRuntime(
            alternate_policy,
            case["trust"],
            external_runtime=case["p11"]["runtime"],
            external_guard=case["p11"]["guard"],
            release_runtime=assurance_fixtures.RUNTIME,
            measurement_policy=case["measurement"]["policy"],
            measurement_trust_store=case["measurement"]["trust"],
            measurement_authority_pins=case["measurement"]["pins"],
            production_integration_plan=case["p15"]["plan"],
            production_integration_policy=case["p15"]["policy"],
            production_integration_trust_store=case["p15"]["trust"],
            production_integration_bundle=case["p15"]["bundle"],
            production_readiness_report=case["p15"]["report"],
            production_tco_qa_attestation=case["p15"]["tco"],
            production_human_environment_approval=case["p15"]["human"],
            production_bootstrap_authorization=case["p15"]["authorization"],
            production_readiness_authority_pins=case["p15"]["pins"],
            production_reconciliation_ledger=case["p15"]["reconciliation_ledger"],
            launch_handoff_bundle=case["p16"]["bundle"],
            launch_handoff_plan=case["p16"]["plan"],
                launch_handoff_policy=case["p16"]["policy"],
                launch_handoff_trust_store=case["p16"]["trust"],
                launch_semantic_packet=case["p16"]["semantic_packet"],
                launch_semantic_authority_pins=case["p16"]["semantic_pins"],
                expected_repository_acceptance_authority_pins_sha256=(
                    case["p16"]["repository_authority_root"]
                ),
                expected_launch_handoff_authority_sha256=case["p16"]["authority_root"],
                expected_launch_semantic_authority_pins_sha256=(
                    case["p16"]["semantic_authority_root"]
                ),
            clock_attest=case["runtime_clock_attest"],
            current_authority_roots=case["runtime_authority_roots"],
        )
    after = case["store"].snapshot()
    assert (before.revision, before.epoch, before.head_sha256) == (
        after.revision,
        after.epoch,
        after.head_sha256,
    )


def test_runtime_rejects_reconciliation_ledger_store_or_trust_splice(
    production_case, tmp_path
) -> None:
    case = production_case

    def build_ledger(name: str, store_id: str, trust_store):
        _, commit, read = _anchor_callbacks()
        return ProductionReconciliationLedger.create(
            tmp_path / f"{name}.sqlite",
            store_id_sha256=store_id,
            plan_sha256=case["p15"]["plan"].plan_sha256,
            trust_store=trust_store,
            state_authentication_key=b"synthetic-hostile-ledger-auth-material",
            anchor_commit=commit,
            anchor_read=read,
        )

    attacker = Ed25519PrivateKey.generate()
    hostile_trust = case["p15"]["trust"].model_copy(
        update={
            "recovery_auditor": create_verification_key(
                attacker.public_key(),
                issuer="hostile-recovery-auditor",
                role=SigningRole.RECOVERY_AUDITOR,
            )
        }
    )
    ledgers = (
        build_ledger("wrong-store", "a" * 64, case["p15"]["trust"]),
        build_ledger("wrong-trust", "9" * 64, hostile_trust),
    )
    for ledger in ledgers:
        with pytest.raises(ProductionConsumerError, match="consumer pin mismatch"):
            ProductionConsumerRuntime(
                case["policy"],
                case["trust"],
                external_runtime=case["p11"]["runtime"],
                external_guard=case["p11"]["guard"],
                release_runtime=assurance_fixtures.RUNTIME,
                measurement_policy=case["measurement"]["policy"],
                measurement_trust_store=case["measurement"]["trust"],
                measurement_authority_pins=case["measurement"]["pins"],
                production_integration_plan=case["p15"]["plan"],
                production_integration_policy=case["p15"]["policy"],
                production_integration_trust_store=case["p15"]["trust"],
                production_integration_bundle=case["p15"]["bundle"],
                production_readiness_report=case["p15"]["report"],
                production_tco_qa_attestation=case["p15"]["tco"],
                production_human_environment_approval=case["p15"]["human"],
                production_bootstrap_authorization=case["p15"]["authorization"],
                production_readiness_authority_pins=case["p15"]["pins"],
                production_reconciliation_ledger=ledger,
                launch_handoff_bundle=case["p16"]["bundle"],
                launch_handoff_plan=case["p16"]["plan"],
                    launch_handoff_policy=case["p16"]["policy"],
                    launch_handoff_trust_store=case["p16"]["trust"],
                    launch_semantic_packet=case["p16"]["semantic_packet"],
                    launch_semantic_authority_pins=case["p16"]["semantic_pins"],
                    expected_repository_acceptance_authority_pins_sha256=(
                        case["p16"]["repository_authority_root"]
                    ),
                    expected_launch_handoff_authority_sha256=(
                        case["p16"]["authority_root"]
                    ),
                    expected_launch_semantic_authority_pins_sha256=(
                        case["p16"]["semantic_authority_root"]
                    ),
                clock_attest=case["runtime_clock_attest"],
                current_authority_roots=case["runtime_authority_roots"],
            )


def test_valid_p9_and_p10_artifact_swaps_reject_without_claim(
    production_case,
) -> None:
    case = production_case
    _reset(case)
    original = case["request"]
    alternate_lease = _build_lease(
        private_key=case["p9_private"],
        issuer=case["trust"].p9_lease_controller.issuer,
        controller_key_id_sha256=(
            case["trust"].p9_lease_controller.key_id_sha256
        ),
        scope=LeaseScope.SERVE_PROTECTED_CONTENT,
        control_input_sha256="7" * 64,
        release_id="release-p10-alternate",
        manifest_sha256=original.serving_lease.manifest_sha256,
        artifact_sha256=original.serving_lease.artifact_sha256,
        issued_at=original.serving_lease.issued_at,
        expires_at=original.serving_lease.expires_at,
    )
    request_values = {
        name: getattr(original, name)
        for name in original.__class__.model_fields
        if name != "request_sha256"
    }
    request_values["serving_lease"] = alternate_lease
    p9_swapped = build_production_consumption_request(**request_values)

    sources = tuple(
        sorted(
            (
                case["bound"].dossier.provenance.demand_source_sha256,
                case["bound"].dossier.provenance.cohort_source_sha256,
                case["bound"].dossier.provenance.operations_source_sha256,
            )
        )
    )
    alternate_manifest = assurance_fixtures.manifest(
        release_id="release-p10-alternate",
        data_snapshot_sha256s=sources,
        rights_bundle_sha256=(
            case["bound"].dossier.provenance.rights_bundle_sha256
        ),
        affiliate_bundle_sha256=(
            case["bound"].dossier.provenance.affiliate_bundle_sha256
        ),
    )
    local = assurance_fixtures.local_report(alternate_manifest)
    tco, human = assurance_fixtures.attestations(
        local, case["bound"].dossier, alternate_manifest
    )
    alternate_public = evaluate_public_release_assurance(
        local,
        case["bound"].dossier,
        alternate_manifest,
        assurance_fixtures.AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=assurance_fixtures.AT + timedelta(minutes=3),
    )
    assert alternate_public.authorization is not None
    request_values["serving_lease"] = original.serving_lease
    request_values["release_report"] = alternate_public
    p10_swapped = build_production_consumption_request(**request_values)

    before = case["store"].snapshot()
    for swapped in (p9_swapped, p10_swapped):
        with pytest.raises(
            ProductionConsumerError, match="authority verification failed"
        ):
            case["store"].claim(
                swapped, case["runtime"], case["p11"]["private"], at=AT
            )
        after = case["store"].snapshot()
        assert (
            after.revision,
            after.epoch,
            after.head_sha256,
        ) == (
            before.revision,
            before.epoch,
            before.head_sha256,
        )
    assert json.loads(case["provider_state"].read_text())["call_count"] == 0


def test_success_commit_at_exact_token_expiry_is_rejected(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider, probe, action = _valid_terminal_receipts(case, token)
    with pytest.raises(ProductionConsumerError, match="receipts or authority"):
        case["store"].commit_result(
            case["request"],
            token,
            _runtime_at(case, token.expires_at),
            state=ConsumptionState.SUCCEEDED,
            terminal_at=token.expires_at,
            provider_receipt=provider,
            probe_receipt=probe,
            action_receipt=action,
        )


def test_signed_probe_cannot_predate_provider_completion(production_case) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    early = _build_signed_model(
        ProviderProbeReceipt,
        {
            "issuer": case["trust"].provider_probe.issuer,
            "signer_role": SigningRole.PROVIDER_PROBE,
            "scope": ProductionSignatureScope.PROVIDER_PROBE,
            "dispatch_payload_sha256": token.payload_sha256,
            "store_id_sha256": token.store_id_sha256,
            "epoch": token.epoch,
            "fencing_token": token.fencing_token,
            "operation": token.operation,
            "adapter_id": token.adapter_id,
            "target_sha256": token.target_sha256,
            "observed_post_state_sha256": token.expected_post_state_sha256,
            "probed_at": AT - timedelta(microseconds=1),
        },
        case["probe_private"],
        issuer=case["trust"].provider_probe.issuer,
        role=SigningRole.PROVIDER_PROBE,
    )
    assert case["runtime"].verifies_probe(token, provider, early, at=AT) is False


def test_noop_and_wrong_direction_disable_rules_are_rejected(production_case) -> None:
    case = production_case
    disable = next(
        rule
        for rule in case["policy"].target_rules
        if rule.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE
    )
    with pytest.raises(ValidationError, match="no-op"):
        ProviderTargetRule(
            **{
                **disable.model_dump(),
                "expected_post_state_sha256": disable.expected_pre_state_sha256,
            }
        )
    wrong_disable = ProviderTargetRule(
        **{
            **disable.model_dump(),
            "expected_pre_state_sha256": PRE_STATE,
        }
    )
    rules = tuple(
        wrong_disable if rule.operation is disable.operation else rule
        for rule in case["policy"].target_rules
    )
    with pytest.raises(ValidationError, match="disable must start"):
        ProductionConsumerPolicy(
            **{**case["policy"].model_dump(), "target_rules": rules}
        )
    wrong_target_disable = ProviderTargetRule(
        **{
            **disable.model_dump(),
            "target_sha256": "f" * 64,
        }
    )
    target_spliced_rules = tuple(
        wrong_target_disable if rule.operation is disable.operation else rule
        for rule in case["policy"].target_rules
    )
    with pytest.raises(ValidationError, match="exact provider target contract"):
        ProductionConsumerPolicy(
            **{
                **case["policy"].model_dump(),
                "target_rules": target_spliced_rules,
            }
        )


def test_execute_and_probe_parsers_reject_the_other_role_key(tmp_path) -> None:
    common = [
        "--state", str(tmp_path / "state"),
        "--dispatcher-key", str(tmp_path / "dispatcher"),
        "--allowlist", str(tmp_path / "allowlist"),
        "--postcondition-schema", str(tmp_path / "schema"),
    ]
    execute = subprocess.run(
        [
            str(Path(sys.executable).absolute()), str(SCRIPT), *common,
            "--provider-key", str(tmp_path / "provider"),
            "--probe-key", str(tmp_path / "probe"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    probe = subprocess.run(
        [
            str(Path(sys.executable).absolute()), str(PROBE_SCRIPT), *common,
            "--probe-key", str(tmp_path / "probe"),
            "--provider-key", str(tmp_path / "provider"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert execute.returncode == 2 and b"unrecognized arguments: --probe-key" in execute.stderr
    assert probe.returncode == 2 and b"unrecognized arguments: --provider-key" in probe.stderr


def test_concurrent_identical_claim_has_one_owner(production_case) -> None:
    case = production_case
    _reset(case)

    def attempt():
        try:
            return case["store"].claim(
                case["request"], case["runtime"], case["p11"]["private"], at=AT
            )
        except ProductionConsumerError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sum(not isinstance(item, str) for item in outcomes) == 1
    assert sum("already in progress" in item for item in outcomes if isinstance(item, str)) == 1


def test_four_process_claims_have_one_live_owner(production_case, tmp_path) -> None:
    case = production_case
    _reset(case)
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        pytest.skip("multiprocess ownership test requires fork")

    anchor_path = tmp_path / "multiprocess-anchor.json"
    anchor_revision, anchor_digest = case["anchors"]["p13"]
    anchor_path.write_text(
        json.dumps({"revision": anchor_revision, "digest": anchor_digest}),
        encoding="utf-8",
    )
    ready = context.Queue()
    outcomes = context.Queue()
    start = context.Event()
    release = context.Event()

    def attempt_claim() -> None:
        def read_anchor() -> str:
            return json.loads(anchor_path.read_text(encoding="utf-8"))["digest"]

        def commit_anchor(revision: int, digest: str) -> None:
            current = json.loads(anchor_path.read_text(encoding="utf-8"))
            if revision < current["revision"] or (
                revision == current["revision"] and digest != current["digest"]
            ):
                raise ProductionConsumerError("non-monotonic process anchor")
            anchor_path.write_text(
                json.dumps({"revision": revision, "digest": digest}),
                encoding="utf-8",
            )

        store = GlobalStopStore(
            case["store"].path,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=read_anchor(),
            state_authentication_key=STATE_KEY,
            anchor_commit=commit_anchor,
            anchor_read=read_anchor,
        )
        ready.put(True)
        start.wait(10)
        try:
            store.claim(
                case["request"],
                case["runtime"],
                case["p11"]["private"],
                at=AT,
            )
            outcomes.put("owner")
        except ProductionConsumerError as exc:
            outcomes.put(str(exc))
        release.wait(10)
        store.close()

    processes = [context.Process(target=attempt_claim) for _ in range(4)]
    for process in processes:
        process.start()
    for _ in processes:
        assert ready.get(timeout=15) is True
    start.set()
    results = [outcomes.get(timeout=15) for _ in processes]
    assert results.count("owner") == 1
    assert sum("already in progress" in item for item in results) == 3
    release.set()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    child_anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    case["anchors"]["p13"] = (
        child_anchor["revision"],
        child_anchor["digest"],
    )
    recovered = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    result = recovered.claim(
        case["request"], case["runtime"], case["p11"]["private"], at=AT
    )
    assert result.state is ConsumptionState.UNKNOWN


def test_schema_mutation_after_provider_fact_blocks_probe(
    production_case, tmp_path
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    schema = tmp_path / "postcondition.schema.json"
    shutil.copy2(POSTCONDITION_SCHEMA, schema)
    case["adapter"]._schema = schema
    case["adapter"]._schema_digest = hashlib.sha256(schema.read_bytes()).hexdigest()
    provider = case["adapter"].execute(
        case["request"], token, case["store"], case["runtime"], at=AT,
    )
    schema.write_text('{"type":"null"}', encoding="utf-8")
    with pytest.raises(ProductionConsumerError, match="policy file digest"):
        case["adapter"].probe(
            case["request"], token, case["store"], case["runtime"], at=AT
        )
    result = case["store"].commit_result(
        case["request"],
        token,
        case["runtime"],
        state=ConsumptionState.UNKNOWN,
        provider_receipt=provider,
        terminal_at=AT,
    )
    assert result.state is ConsumptionState.UNKNOWN


def test_legacy_store_is_not_implicitly_migrated(production_case, tmp_path) -> None:
    case = production_case
    legacy = tmp_path / "legacy-v1.sqlite"
    with sqlite3.connect(legacy) as connection:
        connection.executescript(
            "CREATE TABLE production_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;"
            "CREATE TABLE production_dispatches ("
            "request_sha256 TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, "
            "idempotency_key_sha256 TEXT NOT NULL UNIQUE, epoch INTEGER NOT NULL, "
            "fencing_token INTEGER NOT NULL UNIQUE, request_json TEXT NOT NULL, "
            "token_json TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT) STRICT;"
            "CREATE TABLE production_events (revision INTEGER PRIMARY KEY, "
            "previous_head_sha256 TEXT NOT NULL, event_json TEXT NOT NULL, "
            "event_sha256 TEXT NOT NULL UNIQUE) STRICT;"
        )
    with pytest.raises(ProductionConsumerError, match="schema mismatch"):
        GlobalStopStore(
            legacy,
            expected_store_id_sha256=STORE_ID,
            expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
            expected_anchor_sha256=case["anchor_read"](),
            state_authentication_key=STATE_KEY,
            anchor_commit=case["anchor_commit"],
            anchor_read=case["anchor_read"],
        )


def test_rogue_trigger_is_part_of_schema_integrity(production_case) -> None:
    case = production_case
    with sqlite3.connect(case["store"].path) as connection:
        connection.execute(
            "CREATE TRIGGER rogue_event_trigger AFTER INSERT ON production_events "
            "BEGIN SELECT 1; END"
        )
    with pytest.raises(ProductionConsumerError, match="schema mismatch"):
        case["store"].snapshot()


def test_one_revision_ahead_sqlite_recovers_external_anchor_once(production_case) -> None:
    case = production_case
    failed = False

    def flaky_commit(revision: int, digest: str) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("synthetic anchor outage")
        case["anchor_commit"](revision, digest)

    flaky = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=flaky_commit,
        anchor_read=case["anchor_read"],
    )
    snapshot = flaky.snapshot()
    reset = sign_global_stop_reset(
        snapshot,
        case["policy"],
        case["reset_private"],
        issuer=case["trust"].reset_human.issuer,
        remediation_record_sha256="1" * 64,
        reconciliation_record_sha256=(
            case["p15"]["initial_reconciliation_record"].record_sha256
        ),
        nonce_sha256="a" * 64,
        issued_at=AT,
        not_before=AT,
        expires_at=AT + timedelta(minutes=5),
    )
    with pytest.raises(ProductionConsumerError, match="anchor commit failed"):
        flaky.apply_reset(reset, case["runtime"], at=AT)

    recovered = GlobalStopStore(
        case["store"].path,
        expected_store_id_sha256=STORE_ID,
        expected_policy_sha256=hash_production_consumer_policy(case["policy"]),
        expected_anchor_sha256=case["anchor_read"](),
        state_authentication_key=STATE_KEY,
        anchor_commit=case["anchor_commit"],
        anchor_read=case["anchor_read"],
    )
    current = recovered.snapshot()
    assert current.stopped is False and current.revision == snapshot.revision + 1


def test_timeout_kills_the_entire_adapter_process_group(
    production_case, tmp_path, monkeypatch
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    marker = tmp_path / "fork-survived"
    script = tmp_path / "forking-adapter.py"
    script.write_text(
        "import os, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    time.sleep(2)\n"
        f"    open({str(marker)!r}, 'w').write('survived')\n"
        "    raise SystemExit(0)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    adapter = case["adapter"]
    real_verified_script = SubprocessProviderAdapter._verified_script

    @contextmanager
    def substitute_execute_descriptor(self, path, expected):
        selected_path = script.resolve() if path == self._execute_script else path
        selected_digest = (
            hashlib.sha256(script.read_bytes()).hexdigest()
            if path == self._execute_script
            else expected
        )
        with real_verified_script(self, selected_path, selected_digest) as descriptor:
            yield descriptor

    monkeypatch.setattr(
        SubprocessProviderAdapter,
        "_verified_script",
        substitute_execute_descriptor,
    )
    real_wait = subprocess.Popen.wait
    release_unbounded_wait = Event()

    def delay_unbounded_wait(process, timeout=None):
        if timeout is None:
            release_unbounded_wait.wait()
        return real_wait(process, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", delay_unbounded_wait)
    adapter._timeout = 1
    completed = Event()
    outcomes: list[BaseException | None] = []

    def invoke() -> None:
        try:
            _invoke_execute_through_store(case, token, adapter)
        except BaseException as exc:
            outcomes.append(exc)
        else:
            outcomes.append(None)
        finally:
            completed.set()

    worker = Thread(target=invoke, daemon=True)
    worker.start()
    try:
        # The adapter has a one-second deadline.  A generous completion bound
        # keeps scheduler jitter out of the assertion while the unreleased
        # Event makes any unbounded Popen.wait deterministically fail it.
        assert completed.wait(timeout=2.5)
    finally:
        release_unbounded_wait.set()
    worker.join(timeout=3)
    assert worker.is_alive() is False
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], ProductionConsumerError)
    assert (
        "timed out" in str(outcomes[0])
        or "deadline is exhausted" in str(outcomes[0])
    )
    time.sleep(2.2)
    assert marker.exists() is False


def test_verified_script_descriptor_fails_closed_on_path_swap(
    production_case, tmp_path
) -> None:
    case = production_case
    script = tmp_path / "swappable-adapter.py"
    script.write_text("print('{\"source\":\"verified\"}')\n", encoding="utf-8")
    adapter = case["adapter"]
    expected = hashlib.sha256(script.read_bytes()).hexdigest()
    replacement = script.with_suffix(".replacement")
    replacement.write_text("print('{\"source\":\"swapped\"}')\n", encoding="utf-8")
    with pytest.raises(ProductionConsumerError, match="changed while open"):
        with adapter._verified_script(script.resolve(), expected):
            replacement.replace(script)


def test_pinned_hash_rejects_file_and_parent_symlinks(tmp_path) -> None:
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    target = real_directory / "adapter.py"
    target.write_text("print('safe')\n", encoding="utf-8")
    direct_alias = tmp_path / "adapter-alias.py"
    direct_alias.symlink_to(target)
    directory_alias = tmp_path / "directory-alias"
    directory_alias.symlink_to(real_directory, target_is_directory=True)

    with pytest.raises(ProductionConsumerError, match="unavailable"):
        _file_sha256(direct_alias)
    with pytest.raises(ProductionConsumerError, match="unavailable"):
        _file_sha256(directory_alias / target.name)


def test_isolated_adapter_ignores_pythonpath_and_sitecustomize(
    production_case, tmp_path, monkeypatch
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    injection = tmp_path / "external-import"
    injection.mkdir()
    marker = tmp_path / "sitecustomize-ran"
    (injection / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(injection))
    monkeypatch.syspath_prepend(str(injection))

    result = _invoke_execute_through_store(case, token)
    assert result.outcome is ProviderOutcome.SUCCEEDED
    assert marker.exists() is False


def test_isolated_launcher_rejects_unpinned_module_on_an_import_path(
    tmp_path,
) -> None:
    injected = tmp_path / "injected_module.py"
    injected.write_text("VALUE = 'untrusted'\n", encoding="utf-8")
    script = tmp_path / "adapter.py"
    script.write_text("import injected_module\n", encoding="utf-8")
    with tempfile.TemporaryFile() as manifest:
        manifest.write(b"{}")
        manifest.flush()
        manifest.seek(0)
        result = subprocess.run(
            (
                str(PYTHON_EXECUTABLE),
                "-I",
                "-S",
                "-B",
                "-c",
                _ISOLATED_ADAPTER_LAUNCHER,
                str(manifest.fileno()),
                json.dumps((str(tmp_path),), separators=(",", ":")),
                str(script),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(manifest.fileno(),),
            check=False,
        )
    assert result.returncode != 0
    assert b"outside the pinned adapter closure" in result.stderr

    script.write_text("import pytest\n", encoding="utf-8")
    purelib = str(Path(sysconfig.get_path("purelib")).resolve())
    with tempfile.TemporaryFile() as manifest:
        manifest.write(b"{}")
        manifest.flush()
        manifest.seek(0)
        site_packages_shadow = subprocess.run(
            (
                str(PYTHON_EXECUTABLE),
                "-I",
                "-S",
                "-B",
                "-c",
                _ISOLATED_ADAPTER_LAUNCHER,
                str(manifest.fileno()),
                json.dumps((purelib,), separators=(",", ":")),
                str(script),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(manifest.fileno(),),
            check=False,
        )
    assert site_packages_shadow.returncode != 0
    assert b"outside the pinned adapter closure: pytest:" in site_packages_shadow.stderr


def test_isolated_launcher_executes_verified_source_bytes_during_path_swap(
    tmp_path,
) -> None:
    marker = tmp_path / "malicious-ran"
    module = tmp_path / "race_module.py"
    safe_bytes = b"VALUE = 'safe'\n" + b"#" * (16 * 1024 * 1024)
    module.write_bytes(safe_bytes)
    replacement = tmp_path / "replacement.py"
    replacement.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "VALUE = 'malicious'\n",
        encoding="utf-8",
    )
    script = tmp_path / "adapter.py"
    script.write_text("import race_module\nprint(race_module.VALUE)\n", encoding="utf-8")
    expected = hashlib.sha256(safe_bytes).hexdigest()
    with tempfile.TemporaryFile() as manifest:
        manifest.write(
            json.dumps(
                {str(module): expected}, separators=(",", ":")
            ).encode("utf-8")
        )
        manifest.flush()
        manifest.seek(0)
        process = subprocess.Popen(
            (
                str(PYTHON_EXECUTABLE),
                "-I",
                "-S",
                "-B",
                "-c",
                _ISOLATED_ADAPTER_LAUNCHER,
                str(manifest.fileno()),
                json.dumps((str(tmp_path),), separators=(",", ":")),
                str(script),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(manifest.fileno(),),
        )
        time.sleep(0.02)
        replacement.replace(module)
        stdout, _ = process.communicate(timeout=10)
    assert marker.exists() is False
    assert process.returncode != 0 or stdout.strip() == b"safe"


def test_adapter_closure_binds_the_base_standard_library() -> None:
    paths = production_adapter_dependency_paths()
    argparse_path = Path(__import__("argparse").__file__).resolve()
    assert argparse_path in paths


def test_subprocess_output_limit_kills_the_child(
    production_case, tmp_path, monkeypatch
) -> None:
    case = production_case
    token = _claim_and_redeem(case)
    script = tmp_path / "output-flood.py"
    script.write_text(
        "import os,time\nos.write(1,b'x'*1048576)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    adapter = case["adapter"]
    real_verified_script = SubprocessProviderAdapter._verified_script

    @contextmanager
    def substitute_execute_descriptor(self, path, expected):
        selected_path = script.resolve() if path == self._execute_script else path
        selected_digest = (
            hashlib.sha256(script.read_bytes()).hexdigest()
            if path == self._execute_script
            else expected
        )
        with real_verified_script(self, selected_path, selected_digest) as descriptor:
            yield descriptor

    monkeypatch.setattr(
        SubprocessProviderAdapter,
        "_verified_script",
        substitute_execute_descriptor,
    )
    adapter._max_output = 1024
    with pytest.raises(ProductionConsumerError, match="output limit"):
        _invoke_execute_through_store(case, token, adapter)
