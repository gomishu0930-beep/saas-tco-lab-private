from __future__ import annotations

import inspect
import pickle
from datetime import timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from saas_preflight.control_cycle import (
    AttestationScope,
    ControlConfig,
    ControllerAuthority,
    ControlDecision,
    ControlInputError,
    ControlReason,
    ControlTrustStore,
    GoldReportAttestation,
    LeaseScope,
    ReleaseDecisionAttestation,
    SchedulerHeartbeat,
    ServingLease,
    SigningRole,
    create_verification_key,
    evaluate_control_cycle,
    hash_control_trust_store,
    sign_gold_report_attestation,
    sign_release_decision_attestation,
    verify_gold_report_attestation,
)
from saas_preflight.control_cycle import _signed_payload_hash
from saas_preflight.economics import RollbackTestStatus
from saas_preflight.goldset import GoldSetReport, evaluate_goldset, hash_goldset_report
from saas_preflight import mvp as mvp_module
from saas_preflight.mvp import ControlledMvpRuntime, build_mvp_artifact
from saas_preflight.operations import (
    BudgetStatus,
    ExceptionQueue,
    ExceptionStatus,
    MonthlyHumanBudget,
    OperatingRole,
    OperationalException,
    Severity,
    TimeEntry,
    WorkClass,
)
from saas_preflight.preflight import DossierProvenance
from saas_preflight.release import (
    AffiliateCta,
    ApprovalDecision,
    ApprovalScope,
    CtaDecision,
    HumanApproval,
    ReleaseManifest,
    ReleaseState,
    prepare_release,
    promote_release,
)

from test_goldset import full_fixture
from test_mvp import page
from test_preflight import NOW, _dossier


AT = NOW + timedelta(minutes=5)
AFFILIATE = "a" * 64
CONTROLLER_ISSUER = "production-controller"
GOLD_ISSUER = "tco-qa"
HUMAN_ISSUER = "human-release"
CONTROLLER_PRIVATE = Ed25519PrivateKey.generate()
GOLD_PRIVATE = Ed25519PrivateKey.generate()
HUMAN_PRIVATE = Ed25519PrivateKey.generate()
CONTROLLER_KEY = create_verification_key(
    CONTROLLER_PRIVATE.public_key(),
    issuer=CONTROLLER_ISSUER,
    role=SigningRole.CONTROLLER,
)
GOLD_KEY = create_verification_key(
    GOLD_PRIVATE.public_key(), issuer=GOLD_ISSUER, role=SigningRole.TCO_QA
)
HUMAN_KEY = create_verification_key(
    HUMAN_PRIVATE.public_key(),
    issuer=HUMAN_ISSUER,
    role=SigningRole.HUMAN_APPROVER,
)
TRUST_STORE = ControlTrustStore(
    controller=CONTROLLER_KEY,
    gold_tco_qa=GOLD_KEY,
    release_human=HUMAN_KEY,
)
_UNSET = object()


def config() -> ControlConfig:
    return ControlConfig(
        controller_issuer=CONTROLLER_ISSUER,
        controller_key_id_sha256=CONTROLLER_KEY.key_id_sha256,
        trust_store_sha256=hash_control_trust_store(TRUST_STORE),
        lease_seconds=120,
        heartbeat_ttl_seconds=300,
        gold_report_ttl_seconds=3600,
        schedule_grace_seconds=60,
        maximum_schedule_interval_seconds=600,
    )


AUTHORITY = ControllerAuthority(config(), TRUST_STORE, CONTROLLER_PRIVATE)


def heartbeat(**updates: object) -> SchedulerHeartbeat:
    values: dict[str, object] = {
        "scheduler_id_sha256": "d" * 64,
        "run_receipt_sha256": "e" * 64,
        "observed_at": AT - timedelta(minutes=1),
        "next_run_at": AT + timedelta(minutes=4),
    }
    values.update(updates)
    return SchedulerHeartbeat(**values)


def inputs(*, release_id: str = "release-1", report_at=NOW) -> tuple[object, ...]:
    goldset, batch, _ = full_fixture()
    gold_report = evaluate_goldset(goldset, batch, at=report_at)
    dossier = _dossier(
        provenance=DossierProvenance(
            property_domain="example.test",
            rights_bundle_sha256=gold_report.rights_bundle_sha256,
            affiliate_bundle_sha256=AFFILIATE,
            demand_source_sha256="3" * 64,
            cohort_source_sha256="4" * 64,
            operations_source_sha256="5" * 64,
            assembled_at=NOW,
        )
    )
    artifact = build_mvp_artifact(page(), at=NOW)
    manifest = ReleaseManifest(
        release_id=release_id,
        prepared_at=NOW,
        artifact_sha256=artifact.artifact_sha256,
        schema_sha256="6" * 64,
        data_snapshot_sha256s=(gold_report.candidate_batch_sha256,),
        rights_bundle_sha256=gold_report.rights_bundle_sha256,
        affiliate_bundle_sha256=AFFILIATE,
        data_expires_at=NOW + timedelta(days=5),
        rights_expires_at=NOW + timedelta(days=6),
        affiliate_expires_at=NOW + timedelta(days=7),
        cta=AffiliateCta(
            decision=CtaDecision.APPROVED,
            program_id="synthetic-program",
            destination_sha256=artifact.destination_bundle_sha256,
            disclosure_sha256=artifact.disclosure_sha256,
        ),
    )
    prepared = prepare_release(ReleaseState(), manifest)
    state = promote_release(
        prepared,
        release_id,
        HumanApproval(
            release_id=release_id,
            scope=ApprovalScope.PROMOTE,
            decision=ApprovalDecision.GO,
            approved_by="human-approver",
            approved_at=NOW,
            expires_at=NOW + timedelta(days=1),
            decision_record_sha256="7" * 64,
        ),
        at=NOW + timedelta(seconds=1),
    )
    return dossier, gold_report, artifact, state


def test_credential_blind_gold_attestation_verifier() -> None:
    _, report, _, _ = inputs()
    assert type(report) is GoldSetReport
    attestation = sign_gold_report_attestation(
        report,
        GOLD_PRIVATE,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    assert verify_gold_report_attestation(
        attestation, report, GOLD_KEY, at=AT
    )
    assert not verify_gold_report_attestation(
        attestation, report, GOLD_KEY, at=attestation.expires_at
    )
    assert not verify_gold_report_attestation(
        attestation,
        report,
        create_verification_key(
            Ed25519PrivateKey.generate().public_key(),
            issuer=GOLD_ISSUER,
            role=SigningRole.TCO_QA,
        ),
        at=AT,
    )


def cycle(
    *,
    authority: object = AUTHORITY,
    dossier: object | None = None,
    gold_report: object | None = None,
    state: ReleaseState | None = None,
    beat: SchedulerHeartbeat | None = None,
    queue: ExceptionQueue | None = None,
    budget: MonthlyHumanBudget | None = None,
    gold_attestation: GoldReportAttestation | None | object = _UNSET,
    release_attestation: ReleaseDecisionAttestation | None | object = _UNSET,
    at=AT,
):
    default_dossier, default_report, _, default_state = inputs()
    selected_report = gold_report or default_report
    selected_state = default_state if state is None else state
    if gold_attestation is _UNSET:
        try:
            selected_gold_attestation = sign_gold_report_attestation(
                selected_report,  # type: ignore[arg-type]
                GOLD_PRIVATE,
                issuer=GOLD_ISSUER,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
        except (TypeError, ValueError):
            selected_gold_attestation = sign_gold_report_attestation(
                default_report,
                GOLD_PRIVATE,
                issuer=GOLD_ISSUER,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
    else:
        selected_gold_attestation = gold_attestation
    if release_attestation is _UNSET:
        selected_release_attestation = (
            None
            if selected_state.current_release_id is None
            else sign_release_decision_attestation(
                selected_state,
                HUMAN_PRIVATE,
                issuer=HUMAN_ISSUER,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
        )
    else:
        selected_release_attestation = release_attestation
    return evaluate_control_cycle(
        authority,  # type: ignore[arg-type]
        dossier or default_dossier,  # type: ignore[arg-type]
        gold_report or default_report,  # type: ignore[arg-type]
        selected_state,
        beat or heartbeat(),
        queue or ExceptionQueue(),
        budget or MonthlyHumanBudget(month="2026-07"),
        gold_attestation=selected_gold_attestation,  # type: ignore[arg-type]
        release_attestation=selected_release_attestation,  # type: ignore[arg-type]
        at=at,
    )


def controlled_runtime(
    artifact,
    state: ReleaseState,
    lease: ServingLease | None,
    *,
    key=CONTROLLER_KEY,
    issuer: str = CONTROLLER_ISSUER,
    scope: LeaseScope = LeaseScope.SERVE_PROTECTED_CONTENT,
    maximum_ttl_seconds: int = 120,
) -> ControlledMvpRuntime:
    return ControlledMvpRuntime(
        artifact,
        state,
        lease,
        controller_verification_key=key,
        expected_issuer=issuer,
        expected_scope=scope,
        maximum_ttl_seconds=maximum_ttl_seconds,
    )


def test_passing_current_release_gets_deterministic_bounded_lease() -> None:
    dossier, report, artifact, state = inputs()
    first = cycle(dossier=dossier, gold_report=report, state=state)
    second = cycle(dossier=dossier, gold_report=report, state=state)

    assert first.decision is ControlDecision.MAINTAIN_CURRENT
    assert first.reasons == ()
    assert first.input_sha256 == second.input_sha256
    assert first.report_sha256 == second.report_sha256
    assert first.serving_lease == second.serving_lease
    assert first.serving_lease is not None
    assert first.serving_lease.expires_at == AT + timedelta(minutes=2)
    response = controlled_runtime(artifact, state, first.serving_lease).handle(
        "/comparison/", at=AT
    )
    assert response.status == 200
    assert "JPY 13,200" in response.body
    serialized = first.model_dump_json()
    assert "https://" not in serialized
    assert "synthetic-affiliate" not in serialized


def test_ready_candidate_without_current_requires_human_and_never_promotes() -> None:
    dossier, report, _, _ = inputs()
    result = cycle(dossier=dossier, gold_report=report, state=ReleaseState())

    assert result.decision is ControlDecision.HUMAN_APPROVAL_REQUIRED
    assert result.reasons == (ControlReason.NO_CURRENT_RELEASE,)
    assert result.serving_lease is None
    assert result.current_release_id is None


def test_exact_freshness_boundaries_and_future_inputs_hold() -> None:
    stale_beat = heartbeat(observed_at=AT - timedelta(minutes=5))
    assert cycle(beat=stale_beat).decision is ControlDecision.HOLD
    assert ControlReason.HEARTBEAT_STALE in cycle(beat=stale_beat).reasons

    schedule_boundary = heartbeat(
        observed_at=AT - timedelta(minutes=6),
        next_run_at=AT - timedelta(minutes=1),
    )
    scheduled = cycle(beat=schedule_boundary)
    assert ControlReason.SCHEDULER_LAG in scheduled.reasons

    future_beat = heartbeat(observed_at=AT + timedelta(seconds=1), next_run_at=AT + timedelta(minutes=2))
    assert ControlReason.HEARTBEAT_FUTURE in cycle(beat=future_beat).reasons

    dossier, report, _, state = inputs()
    future_dossier, future_report, _, future_state = inputs(
        report_at=AT + timedelta(seconds=1)
    )
    future = cycle(
        dossier=future_dossier,
        gold_report=future_report,
        state=future_state,
    )
    assert future.decision is ControlDecision.HOLD
    assert ControlReason.GOLD_REPORT_FUTURE in future.reasons

    exact_stale_at = report.evaluated_at + timedelta(seconds=config().gold_report_ttl_seconds)
    stale = cycle(dossier=dossier, gold_report=report, state=state, at=exact_stale_at)
    assert ControlReason.GOLD_REPORT_STALE in stale.reasons


def test_release_and_report_hash_substitutions_stop() -> None:
    dossier, report, artifact, _ = inputs()
    changed_report = report.model_copy(update={"rights_bundle_sha256": "f" * 64})
    report_result = cycle(dossier=dossier, gold_report=changed_report)
    assert report_result.decision is ControlDecision.STOP
    assert ControlReason.GOLD_REPORT_INVALID in report_result.reasons
    assert ControlReason.RIGHTS_BINDING_MISMATCH in report_result.reasons

    def substituted_state(**changes: object) -> ReleaseState:
        _, _, _, original = inputs()
        manifest = original.get("release-1")
        values = {
            "release_id": manifest.release_id,
            "prepared_at": manifest.prepared_at,
            "artifact_sha256": manifest.artifact_sha256,
            "schema_sha256": manifest.schema_sha256,
            "data_snapshot_sha256s": manifest.data_snapshot_sha256s,
            "rights_bundle_sha256": manifest.rights_bundle_sha256,
            "affiliate_bundle_sha256": manifest.affiliate_bundle_sha256,
            "data_expires_at": manifest.data_expires_at,
            "rights_expires_at": manifest.rights_expires_at,
            "affiliate_expires_at": manifest.affiliate_expires_at,
            "cta": manifest.cta,
        }
        values.update(changes)
        replacement = ReleaseManifest(**values)
        prepared = prepare_release(ReleaseState(), replacement)
        return promote_release(
            prepared,
            replacement.release_id,
            HumanApproval(
                release_id=replacement.release_id,
                scope=ApprovalScope.PROMOTE,
                decision=ApprovalDecision.GO,
                approved_by="human-approver",
                approved_at=NOW,
                expires_at=NOW + timedelta(days=1),
                decision_record_sha256="7" * 64,
            ),
            at=NOW + timedelta(seconds=1),
        )

    affiliate = cycle(
        dossier=dossier,
        gold_report=report,
        state=substituted_state(affiliate_bundle_sha256="b" * 64),
    )
    assert ControlReason.AFFILIATE_BINDING_MISMATCH in affiliate.reasons
    candidate = cycle(
        dossier=dossier,
        gold_report=report,
        state=substituted_state(data_snapshot_sha256s=("8" * 64,)),
    )
    assert ControlReason.CANDIDATE_BINDING_MISMATCH in candidate.reasons
    rights = cycle(
        dossier=dossier,
        gold_report=report,
        state=substituted_state(rights_bundle_sha256="9" * 64),
    )
    assert ControlReason.RIGHTS_BINDING_MISMATCH in rights.reasons
    assert artifact.artifact_sha256 == inputs()[2].artifact_sha256


def test_open_severity_faults_fail_closed_but_resolved_and_order_are_stable() -> None:
    sev0 = OperationalException(
        exception_key="safety-stop",
        severity=Severity.SEV0,
        category="rights-fault",
        resource_id="release-1",
        summary="Synthetic safety fault without raw source content.",
        detected_at=NOW,
    )
    sev1 = OperationalException(
        exception_key="tco-regression",
        severity=Severity.SEV1,
        category="tco-fault",
        resource_id="release-1",
        summary="Synthetic TCO fault without raw source content.",
        detected_at=NOW,
    )
    dossier, report, _, state = inputs()
    first = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        queue=ExceptionQueue(items=(sev0, sev1)),
    )
    second = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        queue=ExceptionQueue(items=(sev1, sev0)),
    )
    assert first.decision is ControlDecision.STOP
    assert first.input_sha256 == second.input_sha256
    assert first.report_sha256 == second.report_sha256
    assert first.unresolved_sev0_count == 1
    assert first.unresolved_sev1_count == 1
    assert "Synthetic safety" not in first.model_dump_json()

    resolved = tuple(
        item.__class__(
            exception_key=item.exception_key,
            severity=item.severity,
            category=item.category,
            resource_id=item.resource_id,
            summary=item.summary,
            detected_at=item.detected_at,
            status=ExceptionStatus.RESOLVED,
            acknowledged_at=NOW + timedelta(seconds=1),
            acknowledged_by="integration",
            resolved_at=NOW + timedelta(seconds=2),
            resolution_sha256="1" * 64,
        )
        for item in (sev0, sev1)
    )
    assert cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        queue=ExceptionQueue(items=resolved),
    ).decision is ControlDecision.MAINTAIN_CURRENT


def _budget(minutes: int) -> MonthlyHumanBudget:
    allocations = (
        (OperatingRole.EVIDENCE, 180),
        (OperatingRole.CONTRACT, 90),
        (OperatingRole.TCO, 120),
        (OperatingRole.INTEGRATION, 210),
        (OperatingRole.HUMAN, 120),
    )
    remaining = minutes
    entries = []
    for index, (role, limit) in enumerate(allocations):
        used = min(remaining, limit)
        if used:
            entries.append(
                TimeEntry(
                    reference=f"budget-{index}",
                    role=role,
                    work_class=WorkClass.ESSENTIAL_OPERATIONS,
                    minutes=used,
                    occurred_at=NOW,
                )
            )
            remaining -= used
    assert remaining == 0
    return MonthlyHumanBudget(month="2026-07", entries=tuple(entries))


def test_budget_freeze_maintains_current_but_wrong_month_and_exhaustion_fail_closed() -> None:
    frozen = cycle(budget=_budget(576))
    assert frozen.decision is ControlDecision.MAINTAIN_CURRENT
    assert frozen.budget_status is BudgetStatus.FROZEN

    wrong = cycle(budget=MonthlyHumanBudget(month="2026-06"))
    assert wrong.decision is ControlDecision.HOLD
    assert ControlReason.BUDGET_MONTH_MISMATCH in wrong.reasons

    exhausted = cycle(budget=_budget(720))
    assert exhausted.decision is ControlDecision.STOP
    assert ControlReason.BUDGET_EXHAUSTED in exhausted.reasons


def test_business_stop_and_continue_override_ready_gold() -> None:
    dossier, report, _, state = inputs()
    stopped_dossier = dossier.model_copy(update={"rights_approved": False})
    stopped = cycle(dossier=stopped_dossier, gold_report=report, state=state)
    assert stopped.decision is ControlDecision.STOP
    assert ControlReason.BUSINESS_STOP in stopped.reasons

    continued_dossier = dossier.model_copy(
        update={
            "shadow_observation_days": 29,
            "job_runs_total": 0,
            "job_runs_succeeded": 0,
            "exceptions_total": 0,
            "rollback_test_status": RollbackTestStatus.NOT_RUN,
        }
    )
    continued = cycle(dossier=continued_dossier, gold_report=report, state=state)
    assert continued.decision is ControlDecision.HOLD
    assert ControlReason.BUSINESS_CONTINUE in continued.reasons


def test_controlled_runtime_denies_missing_future_expired_and_copied_lease() -> None:
    dossier, report, artifact, state = inputs()
    result = cycle(dossier=dossier, gold_report=report, state=state)
    assert result.serving_lease is not None

    missing = controlled_runtime(artifact, state, None)
    denied = missing.handle("/comparison/", at=AT)
    assert denied.status == 503
    assert "13,200" not in denied.body
    assert missing.handle("/healthz", at=AT).body == "ok\n"
    assert missing.handle("/robots.txt", at=AT).body == "User-agent: *\nDisallow: /\n"

    assert controlled_runtime(artifact, state, result.serving_lease).handle(
        "/", at=result.serving_lease.expires_at
    ).status == 503
    assert controlled_runtime(artifact, state, result.serving_lease).handle(
        "/", at=result.serving_lease.issued_at - timedelta(microseconds=1)
    ).status == 503

    other_dossier, other_report, _, other_state = inputs(release_id="release-2")
    other_result = cycle(
        dossier=other_dossier,
        gold_report=other_report,
        state=other_state,
    )
    assert other_result.serving_lease is not None
    copied = controlled_runtime(artifact, state, other_result.serving_lease).handle(
        "/comparison/", at=AT
    )
    assert copied.status == 503
    assert "13,200" not in copied.body


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provenance", None),
        ("expires_at", None),
    ],
)
def test_bypassed_invalid_dossier_is_a_typed_stop_without_a_lease(
    field: str, value: object
) -> None:
    dossier, report, _, state = inputs()
    invalid = dossier.model_copy(update={field: value})

    result = cycle(dossier=invalid, gold_report=report, state=state)

    assert result.decision is ControlDecision.STOP
    assert ControlReason.DOSSIER_INVALID in result.reasons
    assert result.serving_lease is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("report_sha256", None),
        ("expires_at", None),
        ("rights_bundle_sha256", None),
    ],
)
def test_bypassed_invalid_gold_report_is_a_typed_stop_without_a_lease(
    field: str, value: object
) -> None:
    dossier, report, _, state = inputs()
    invalid = report.model_copy(update={field: value})

    result = cycle(dossier=dossier, gold_report=invalid, state=state)

    assert result.decision is ControlDecision.STOP
    assert ControlReason.GOLD_REPORT_INVALID in result.reasons
    assert result.serving_lease is None
    assert len(result.gold_report_sha256) == 64


@pytest.mark.parametrize("field", ["observed_at", "next_run_at"])
def test_bypassed_invalid_heartbeat_is_a_typed_hold_without_a_lease(field: str) -> None:
    invalid = heartbeat().model_copy(update={field: None})

    result = cycle(beat=invalid)

    assert result.decision is ControlDecision.HOLD
    assert ControlReason.HEARTBEAT_INVALID in result.reasons
    assert result.serving_lease is None


@pytest.mark.parametrize(
    "field",
    [
        "lease_seconds",
        "heartbeat_ttl_seconds",
        "gold_report_ttl_seconds",
        "controller_key_id_sha256",
        "trust_store_sha256",
    ],
)
def test_bypassed_invalid_config_is_rejected_at_authority_bootstrap(field: str) -> None:
    invalid = config().model_copy(update={field: None})

    with pytest.raises((ControlInputError, ValueError)):
        ControllerAuthority(invalid, TRUST_STORE, CONTROLLER_PRIVATE)


def test_runtime_rejects_valid_lease_from_an_unexpected_controller() -> None:
    dossier, report, artifact, state = inputs()
    other_private = Ed25519PrivateKey.generate()
    other_key = create_verification_key(
        other_private.public_key(),
        issuer="other-controller",
        role=SigningRole.CONTROLLER,
    )
    other_trust = ControlTrustStore(
        controller=other_key,
        gold_tco_qa=GOLD_KEY,
        release_human=HUMAN_KEY,
    )
    other_config = config().model_copy(
        update={
            "controller_issuer": other_key.issuer,
            "controller_key_id_sha256": other_key.key_id_sha256,
            "trust_store_sha256": hash_control_trust_store(other_trust),
        }
    )
    other_authority = ControllerAuthority(other_config, other_trust, other_private)
    other = cycle(
        authority=other_authority,
        dossier=dossier,
        gold_report=report,
        state=state,
    )
    assert other.serving_lease is not None

    denied = controlled_runtime(artifact, state, other.serving_lease).handle(
        "/comparison/", at=AT
    )

    assert denied.status == 503
    assert "13,200" not in denied.body


def test_missing_or_wrong_controller_signer_is_rejected_at_bootstrap() -> None:
    with pytest.raises(TypeError):
        ControllerAuthority(config(), TRUST_STORE, None)  # type: ignore[arg-type]
    with pytest.raises(ControlInputError):
        ControllerAuthority(config(), TRUST_STORE, Ed25519PrivateKey.generate())


def test_zero_count_rehashed_report_without_matching_tco_qa_attestation_stops() -> None:
    dossier, report, _, state = inputs()
    valid_attestation = sign_gold_report_attestation(
        report,
        GOLD_PRIVATE,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    forged = report.model_copy(
        update={
            "gold_vendor_count": 0,
            "gold_plan_count": 0,
            "gold_label_count": 0,
            "candidate_plan_count": 0,
        }
    )
    forged = forged.model_copy(
        update={"report_sha256": hash_goldset_report(forged)}
    )
    GoldSetReport.model_validate(forged.model_dump())

    result = cycle(
        dossier=dossier,
        gold_report=forged,
        state=state,
        gold_attestation=valid_attestation,
    )

    assert result.decision is ControlDecision.STOP
    assert ControlReason.GOLD_ATTESTATION_INVALID in result.reasons
    assert result.serving_lease is None


def test_pinned_trust_store_rejects_attacker_gold_and_human_keys() -> None:
    dossier, report, _, state = inputs()
    forged = report.model_copy(
        update={
            "gold_vendor_count": 0,
            "gold_plan_count": 0,
            "gold_label_count": 0,
            "candidate_plan_count": 0,
        }
    )
    forged = forged.model_copy(
        update={"report_sha256": hash_goldset_report(forged)}
    )
    attack_gold_private = Ed25519PrivateKey.generate()
    attack_human_private = Ed25519PrivateKey.generate()
    attack_gold_key = create_verification_key(
        attack_gold_private.public_key(),
        issuer="attacker-tco",
        role=SigningRole.TCO_QA,
    )
    attack_human_key = create_verification_key(
        attack_human_private.public_key(),
        issuer="attacker-human",
        role=SigningRole.HUMAN_APPROVER,
    )
    attack_trust = ControlTrustStore(
        controller=CONTROLLER_KEY,
        gold_tco_qa=attack_gold_key,
        release_human=attack_human_key,
    )
    assert hash_control_trust_store(attack_trust) != AUTHORITY.config.trust_store_sha256
    forged_gold_attestation = sign_gold_report_attestation(
        forged,
        attack_gold_private,
        issuer=attack_gold_key.issuer,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    forged_release_attestation = sign_release_decision_attestation(
        state,
        attack_human_private,
        issuer=attack_human_key.issuer,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )

    result = cycle(
        dossier=dossier,
        gold_report=forged,
        state=state,
        gold_attestation=forged_gold_attestation,
        release_attestation=forged_release_attestation,
    )

    assert result.decision is ControlDecision.STOP
    assert ControlReason.GOLD_ATTESTATION_INVALID in result.reasons
    assert ControlReason.RELEASE_ATTESTATION_INVALID in result.reasons
    assert result.serving_lease is None
    parameters = inspect.signature(evaluate_control_cycle).parameters
    assert "authority" in parameters
    assert "config" not in parameters
    assert "trust_store" not in parameters
    assert "controller_signer" not in parameters


def test_missing_or_wrong_gold_and_human_attestations_never_issue_a_lease() -> None:
    dossier, report, _, state = inputs()
    missing_gold = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=None,
    )
    assert ControlReason.GOLD_ATTESTATION_INVALID in missing_gold.reasons
    assert missing_gold.serving_lease is None

    wrong_gold_private = Ed25519PrivateKey.generate()
    wrong_gold = sign_gold_report_attestation(
        report,
        wrong_gold_private,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    rejected_gold = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=wrong_gold,
    )
    assert ControlReason.GOLD_ATTESTATION_INVALID in rejected_gold.reasons
    assert rejected_gold.serving_lease is None

    unsigned_human_event = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        release_attestation=None,
    )
    assert ControlReason.RELEASE_ATTESTATION_INVALID in unsigned_human_event.reasons
    assert unsigned_human_event.serving_lease is None

    wrong_human = sign_release_decision_attestation(
        state,
        Ed25519PrivateKey.generate(),
        issuer=HUMAN_ISSUER,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    forged_human_event = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        release_attestation=wrong_human,
    )
    assert ControlReason.RELEASE_ATTESTATION_INVALID in forged_human_event.reasons
    assert forged_human_event.serving_lease is None


def test_attestation_signature_payload_scope_and_expiry_are_verified() -> None:
    dossier, report, _, state = inputs()
    gold_attestation = sign_gold_report_attestation(
        report,
        GOLD_PRIVATE,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    bad_signature = gold_attestation.model_copy(
        update={"signature_base64url": "A" * 86}
    )
    assert ControlReason.GOLD_ATTESTATION_INVALID in cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=bad_signature,
    ).reasons

    changed_scope = gold_attestation.model_copy(
        update={"scope": AttestationScope.CURRENT_RELEASE_DECISION}
    )
    assert ControlReason.GOLD_ATTESTATION_INVALID in cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=changed_scope,
    ).reasons

    expired = sign_gold_report_attestation(
        report,
        GOLD_PRIVATE,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=AT,
    )
    boundary = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=expired,
    )
    assert ControlReason.GOLD_ATTESTATION_INVALID in boundary.reasons
    assert boundary.serving_lease is None

    short = sign_gold_report_attestation(
        report,
        GOLD_PRIVATE,
        issuer=GOLD_ISSUER,
        issued_at=NOW,
        expires_at=AT + timedelta(seconds=30),
    )
    bounded = cycle(
        dossier=dossier,
        gold_report=report,
        state=state,
        gold_attestation=short,
    )
    assert bounded.serving_lease is not None
    assert bounded.serving_lease.expires_at == AT + timedelta(seconds=30)


def test_unkeyed_self_hash_and_modified_signed_lease_are_rejected() -> None:
    dossier, report, artifact, state = inputs()
    result = cycle(dossier=dossier, gold_report=report, state=state)
    assert result.serving_lease is not None

    forged = result.serving_lease.model_copy(
        update={
            "control_input_sha256": "f" * 64,
            "signature_base64url": "A" * 86,
        }
    )
    forged = forged.model_copy(
        update={"payload_sha256": _signed_payload_hash(forged)}
    )
    ServingLease.model_validate(forged.model_dump())
    response = controlled_runtime(artifact, state, forged).handle("/comparison/", at=AT)
    assert response.status == 503
    assert "13,200" not in response.body

    changed_payload = result.serving_lease.model_copy(
        update={"control_input_sha256": "e" * 64}
    )
    changed_payload = changed_payload.model_copy(
        update={"payload_sha256": _signed_payload_hash(changed_payload)}
    )
    assert controlled_runtime(artifact, state, changed_payload).handle(
        "/comparison/", at=AT
    ).status == 503

    changed_scope = result.serving_lease.model_copy(update={"scope": "other_scope"})
    assert controlled_runtime(artifact, state, changed_scope).handle(
        "/comparison/", at=AT
    ).status == 503
    assert controlled_runtime(
        artifact,
        state,
        result.serving_lease,
        issuer="unexpected-issuer",
    ).handle("/comparison/", at=AT).status == 503


def test_valid_long_lease_is_rejected_by_runtime_maximum_ttl() -> None:
    dossier, report, artifact, state = inputs()
    long_config = config().model_copy(update={"lease_seconds": 300})
    long_authority = ControllerAuthority(
        long_config,
        TRUST_STORE,
        CONTROLLER_PRIVATE,
    )
    long = cycle(
        authority=long_authority,
        dossier=dossier,
        gold_report=report,
        state=state,
    )
    assert long.serving_lease is not None
    assert long.serving_lease.expires_at - long.serving_lease.issued_at > timedelta(
        seconds=120
    )

    denied = controlled_runtime(
        artifact,
        state,
        long.serving_lease,
        maximum_ttl_seconds=120,
    ).handle("/comparison/", at=AT)
    assert denied.status == 503
    assert "13,200" not in denied.body


def test_private_keys_are_runtime_only_and_local_preview_is_not_exported() -> None:
    dossier, report, _, state = inputs()
    result = cycle(dossier=dossier, gold_report=report, state=state)
    serialized = result.model_dump_json() + TRUST_STORE.model_dump_json()

    assert "private_key" not in serialized
    assert "private_bytes" not in serialized
    assert "<redacted>" in repr(AUTHORITY)
    assert "Ed25519PrivateKey" not in repr(AUTHORITY)
    with pytest.raises(TypeError):
        pickle.dumps(AUTHORITY)
    assert "MvpRuntime" not in vars(mvp_module)
    assert "LocalPreviewRuntime" not in mvp_module.__all__
    assert "ControlledMvpRuntime" in mvp_module.__all__
