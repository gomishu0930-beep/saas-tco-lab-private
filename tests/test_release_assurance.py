from __future__ import annotations

import pickle
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from saas_preflight.control_cycle import (
    ControlTrustStore,
    SigningRole,
    create_verification_key,
    hash_control_trust_store,
)
from saas_preflight.economics import Decision
from saas_preflight.preflight import DossierProvenance
from saas_preflight.release import (
    AffiliateCta,
    ApprovalDecision,
    CtaDecision,
    ReleaseManifest,
)
from saas_preflight.release_assurance import (
    AssuranceCheck,
    AssuranceInputError,
    AssurancePolicy,
    AssuranceRequirement,
    DeterminismFacts,
    EvidenceFactsKind,
    IntegrityFacts,
    LocalAssuranceDecision,
    LocalAssuranceReason,
    LocalAssuranceReport,
    PublicReleaseDecision,
    PublicReleaseReason,
    REQUIRED_LOCAL_CHECKS,
    ReleaseAssuranceAuthority,
    ReleaseAssuranceReport,
    ReleaseAssuranceRuntime,
    ReleaseAssuranceVerifier,
    ReviewFacts,
    RouteAssuranceFacts,
    ScanFacts,
    TestSuiteFacts as SuiteFacts,
    build_assurance_bundle,
    build_assurance_evidence,
    evaluate_local_assurance,
    evaluate_public_release_assurance,
    hash_assurance_policy,
    sign_local_assurance_report,
    sign_public_release_approval,
    verify_release_assurance_report,
)

from test_preflight import NOW, _dossier


ROOT = Path(__file__).resolve().parents[1]
AT = NOW + timedelta(hours=1)

FACTS_KIND = {
    AssuranceCheck.PYTHON_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.WEB_LOCAL_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.WEB_PRODUCTION_TESTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.ROLLBACK_FAULTS: EvidenceFactsKind.TEST_SUITE,
    AssuranceCheck.SCHEMA_DETERMINISM: EvidenceFactsKind.DETERMINISM,
    AssuranceCheck.SBOM_CURRENT: EvidenceFactsKind.DETERMINISM,
    AssuranceCheck.LOCK_INTEGRITY: EvidenceFactsKind.INTEGRITY,
    AssuranceCheck.SECRET_SCAN: EvidenceFactsKind.SCAN,
    AssuranceCheck.DEPENDENCY_AUDIT: EvidenceFactsKind.SCAN,
    AssuranceCheck.THREAT_MODEL_REVIEW: EvidenceFactsKind.REVIEW,
    AssuranceCheck.ACCESSIBILITY: EvidenceFactsKind.ROUTE_ASSURANCE,
    AssuranceCheck.MOBILE_REFLOW: EvidenceFactsKind.ROUTE_ASSURANCE,
    AssuranceCheck.SEO_POLICY: EvidenceFactsKind.ROUTE_ASSURANCE,
}

CONTROLLER_PRIVATE = Ed25519PrivateKey.generate()
TCO_PRIVATE = Ed25519PrivateKey.generate()
HUMAN_PRIVATE = Ed25519PrivateKey.generate()
CONTROLLER_KEY = create_verification_key(
    CONTROLLER_PRIVATE.public_key(), issuer="controller", role=SigningRole.CONTROLLER
)
TCO_KEY = create_verification_key(
    TCO_PRIVATE.public_key(), issuer="tco-qa", role=SigningRole.TCO_QA
)
HUMAN_KEY = create_verification_key(
    HUMAN_PRIVATE.public_key(), issuer="human", role=SigningRole.HUMAN_APPROVER
)
TRUST = ControlTrustStore(
    controller=CONTROLLER_KEY, gold_tco_qa=TCO_KEY, release_human=HUMAN_KEY
)


def requirement(check: AssuranceCheck) -> AssuranceRequirement:
    index = REQUIRED_LOCAL_CHECKS.index(check) + 1
    return AssuranceRequirement(
        check=check,
        facts_kind=FACTS_KIND[check],
        tool_name=f"pinned-{check.value}",
        tool_version="1.0.0",
        command_sha256=f"{100 + index:064x}",
        subject_sha256=f"{200 + index:064x}",
    )


REQUIREMENTS = tuple(requirement(check) for check in REQUIRED_LOCAL_CHECKS)
POLICY = AssurancePolicy(
    policy_id="prepublication-v2",
    trust_store_sha256=hash_control_trust_store(TRUST),
    tco_qa_key_id_sha256=TCO_KEY.key_id_sha256,
    human_key_id_sha256=HUMAN_KEY.key_id_sha256,
    assurance_runner_key_id_sha256=CONTROLLER_KEY.key_id_sha256,
    requirements=REQUIREMENTS,
    maximum_evidence_ttl_seconds=2 * 86400,
    maximum_attestation_ttl_seconds=86400,
)
AUTHORITY = ReleaseAssuranceAuthority(POLICY, TRUST, CONTROLLER_PRIVATE)
POLICY_HASH = hash_assurance_policy(POLICY)
RUNTIME = ReleaseAssuranceRuntime(
    CONTROLLER_KEY,
    assurance_policy_sha256=POLICY_HASH,
    maximum_authorization_ttl_seconds=86400,
)


def manifest(**updates: object) -> ReleaseManifest:
    values: dict[str, object] = {
        "release_id": "release-p10",
        "prepared_at": NOW,
        "artifact_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "data_snapshot_sha256s": ("3" * 64, "4" * 64, "5" * 64),
        "rights_bundle_sha256": "1" * 64,
        "affiliate_bundle_sha256": "2" * 64,
        "data_expires_at": NOW + timedelta(days=20),
        "rights_expires_at": NOW + timedelta(days=20),
        "affiliate_expires_at": NOW + timedelta(days=20),
        "cta": AffiliateCta(
            decision=CtaDecision.APPROVED,
            program_id="synthetic-program",
            destination_sha256="d" * 64,
            disclosure_sha256="e" * 64,
        ),
    }
    values.update(updates)
    return ReleaseManifest(**values)  # type: ignore[arg-type]


def facts(check: AssuranceCheck, *, success: bool = True):
    digest = f"{300 + REQUIRED_LOCAL_CHECKS.index(check):064x}"
    kind = FACTS_KIND[check]
    if kind is EvidenceFactsKind.TEST_SUITE:
        return SuiteFacts(
            collected=2,
            passed=2 if success else 1,
            failed=0 if success else 1,
            skipped=0,
            exit_code=0 if success else 1,
            output_sha256=digest,
        )
    if kind is EvidenceFactsKind.DETERMINISM:
        return DeterminismFacts(
            generated_items=30,
            first_sha256=digest,
            second_sha256=digest if success else "8" * 64,
            committed_sha256=digest,
            exit_code=0,
        )
    if kind is EvidenceFactsKind.INTEGRITY:
        return IntegrityFacts(
            checked_items=24,
            invalid_items=0 if success else 1,
            drift_items=0,
            output_sha256=digest,
            exit_code=0,
        )
    if kind is EvidenceFactsKind.SCAN:
        return ScanFacts(
            scanned_items=649,
            findings=0 if success else 1,
            unresolved_findings=0 if success else 1,
            output_sha256=digest,
            exit_code=0,
        )
    if kind is EvidenceFactsKind.REVIEW:
        return ReviewFacts(
            requirements_total=24,
            requirements_met=24 if success else 23,
            release_blockers=0 if success else 1,
            review_artifact_sha256=digest,
            exit_code=0,
        )
    return RouteAssuranceFacts(
        routes_checked=5 if success else 4,
        assertions_executed=20,
        violations=0 if success else 1,
        output_sha256=digest,
        exit_code=0,
    )


def evidence_bundle(
    release: ReleaseManifest | None = None,
    *,
    failed_check: AssuranceCheck | None = None,
    observed_at=NOW,
    expires_at=NOW + timedelta(days=1),
    policy: AssurancePolicy = POLICY,
    runner_private: Ed25519PrivateKey = CONTROLLER_PRIVATE,
    runner_issuer: str | None = None,
    subject_override: tuple[AssuranceCheck, str] | None = None,
):
    selected = release or manifest()
    policy_hash = hash_assurance_policy(policy)
    requirements = {item.check: item for item in policy.requirements}
    items = []
    for check in REQUIRED_LOCAL_CHECKS:
        pinned = requirements[check]
        subject = (
            subject_override[1]
            if subject_override is not None and subject_override[0] is check
            else pinned.subject_sha256
        )
        items.append(
            build_assurance_evidence(
                runner_private,
                runner_issuer=(
                    runner_issuer
                    or ("controller" if runner_private is CONTROLLER_PRIVATE else "attacker")
                ),
                evidence_id=f"{check.value}-run-1",
                check=check,
                release_id=selected.release_id,
                manifest_sha256=selected.manifest_sha256,
                artifact_sha256=selected.artifact_sha256,
                assurance_policy_sha256=policy_hash,
                subject_sha256=subject,
                command_sha256=pinned.command_sha256,
                tool_name=pinned.tool_name,
                tool_version=pinned.tool_version,
                facts=facts(check, success=check is not failed_check),
                observed_at=observed_at,
                expires_at=expires_at,
            )
        )
    return build_assurance_bundle(
        release_id=selected.release_id,
        manifest_sha256=selected.manifest_sha256,
        artifact_sha256=selected.artifact_sha256,
        assurance_policy_sha256=policy_hash,
        evidence=tuple(reversed(items)),
    )


def local_report(
    release: ReleaseManifest | None = None,
    *,
    authority: ReleaseAssuranceAuthority = AUTHORITY,
    policy: AssurancePolicy = POLICY,
):
    return evaluate_local_assurance(
        evidence_bundle(release, policy=policy), authority, at=AT
    )


def attestations(report, dossier, selected_manifest):
    snapshots = tuple(sorted(selected_manifest.data_snapshot_sha256s))
    return (
        sign_local_assurance_report(
            report,
            TCO_PRIVATE,
            issuer="tco-qa",
            issued_at=AT + timedelta(minutes=1),
            expires_at=AT + timedelta(hours=12),
        ),
        sign_public_release_approval(
            report,
            dossier,
            selected_manifest,
            HUMAN_PRIVATE,
            issuer="human",
            decision=ApprovalDecision.GO,
            decision_record_sha256="f" * 64,
            approved_data_snapshot_sha256s=snapshots,
            issued_at=AT + timedelta(minutes=2),
            expires_at=AT + timedelta(hours=12),
        ),
    )


def public_go(selected: ReleaseManifest | None = None):
    chosen = selected or manifest()
    dossier = _dossier()
    report = local_report(chosen)
    tco, human = attestations(report, dossier, chosen)
    result = evaluate_public_release_assurance(
        report,
        dossier,
        chosen,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )
    return chosen, dossier, report, tco, human, result


def test_local_assurance_recomputes_typed_signed_checks_deterministically() -> None:
    bundle = evidence_bundle()
    report = evaluate_local_assurance(bundle, AUTHORITY, at=AT)
    rebuilt = build_assurance_bundle(
        release_id=bundle.release_id,
        manifest_sha256=bundle.manifest_sha256,
        artifact_sha256=bundle.artifact_sha256,
        assurance_policy_sha256=bundle.assurance_policy_sha256,
        evidence=tuple(reversed(bundle.evidence)),
    )

    assert len(report.passed_checks) == 13
    assert report.decision is LocalAssuranceDecision.READY
    assert rebuilt.bundle_sha256 == bundle.bundle_sha256
    assert evaluate_local_assurance(rebuilt, AUTHORITY, at=AT) == report


def test_credential_blind_local_verifier_rederives_without_controller_key() -> None:
    bundle = evidence_bundle()
    report = evaluate_local_assurance(bundle, AUTHORITY, at=AT)
    verifier = ReleaseAssuranceVerifier(
        POLICY,
        TRUST,
        expected_policy_sha256=POLICY_HASH,
        expected_trust_store_sha256=hash_control_trust_store(TRUST),
    )
    assert verifier.verify_local(bundle, report, at=AT) is True
    assert verifier.verify_local(bundle, report, at=report.expires_at) is False

    other_bundle = evidence_bundle(manifest(artifact_sha256="9" * 64))
    assert verifier.verify_local(other_bundle, report, at=AT) is False


def test_credential_blind_local_verifier_rejects_authority_substitution() -> None:
    with pytest.raises(AssuranceInputError, match="authority pin mismatch"):
        ReleaseAssuranceVerifier(
            POLICY,
            TRUST,
            expected_policy_sha256="9" * 64,
            expected_trust_store_sha256=hash_control_trust_store(TRUST),
        )


def test_failed_typed_facts_stop_their_check() -> None:
    report = evaluate_local_assurance(
        evidence_bundle(failed_check=AssuranceCheck.SBOM_CURRENT), AUTHORITY, at=AT
    )

    assert report.decision is LocalAssuranceDecision.STOP
    assert report.failed_checks == (AssuranceCheck.SBOM_CURRENT,)
    assert LocalAssuranceReason.CHECK_FAILED in report.reasons


def test_unsigned_or_attacker_signed_self_reported_facts_cannot_pass() -> None:
    attacker = Ed25519PrivateKey.generate()
    report = evaluate_local_assurance(
        evidence_bundle(runner_private=attacker), AUTHORITY, at=AT
    )

    assert report.decision is LocalAssuranceDecision.STOP
    assert len(report.failed_checks) == 13
    assert LocalAssuranceReason.EVIDENCE_SIGNATURE_INVALID in report.reasons

    sample = evidence_bundle().evidence[0]
    with pytest.raises(ValidationError):
        type(sample)(
            **sample.model_dump(exclude={"signature_base64url"}),
            expected_items=1,
            passed_items=1,
            signature_base64url=sample.signature_base64url,
        )


def test_runner_signed_but_unpinned_subject_is_still_rejected() -> None:
    report = evaluate_local_assurance(
        evidence_bundle(
            subject_override=(AssuranceCheck.PYTHON_TESTS, "0" * 64)
        ),
        AUTHORITY,
        at=AT,
    )

    assert report.failed_checks == (AssuranceCheck.PYTHON_TESTS,)
    assert LocalAssuranceReason.EVIDENCE_REQUIREMENT_MISMATCH in report.reasons


def test_future_expired_and_overlong_evidence_fail_at_exact_boundaries() -> None:
    future = evaluate_local_assurance(
        evidence_bundle(
            observed_at=AT + timedelta(seconds=1),
            expires_at=AT + timedelta(hours=1),
        ),
        AUTHORITY,
        at=AT,
    )
    expired = evaluate_local_assurance(
        evidence_bundle(observed_at=NOW, expires_at=AT), AUTHORITY, at=AT
    )
    too_long = evaluate_local_assurance(
        evidence_bundle(expires_at=NOW + timedelta(days=3)), AUTHORITY, at=AT
    )

    assert LocalAssuranceReason.EVIDENCE_FUTURE in future.reasons
    assert LocalAssuranceReason.EVIDENCE_EXPIRED in expired.reasons
    assert LocalAssuranceReason.EVIDENCE_TTL_EXCEEDED in too_long.reasons


def test_authority_pins_policy_trust_and_private_controller_capability() -> None:
    attacker = Ed25519PrivateKey.generate()
    with pytest.raises(AssuranceInputError):
        ReleaseAssuranceAuthority(POLICY, TRUST, attacker)
    with pytest.raises(TypeError):
        pickle.dumps(AUTHORITY)
    assert "redacted" in repr(AUTHORITY)


def test_runtime_rejects_noncanonical_policy_hash() -> None:
    with pytest.raises(ValueError, match="policy SHA-256"):
        ReleaseAssuranceRuntime(
            CONTROLLER_KEY,
            assurance_policy_sha256="G" * 64,
            maximum_authorization_ttl_seconds=86400,
        )


def test_tampered_bundle_is_rejected() -> None:
    forged = evidence_bundle().model_copy(update={"bundle_sha256": "0" * 64})
    with pytest.raises(AssuranceInputError):
        evaluate_local_assurance(forged, AUTHORITY, at=AT)


def test_signed_public_release_go_has_controller_authorization() -> None:
    _, _, _, _, _, result = public_go()

    assert result.decision is PublicReleaseDecision.GO
    assert result.public_release_ready is True
    assert result.business_decision is Decision.GO
    assert result.authorization is not None
    assert verify_release_assurance_report(
        result, RUNTIME, at=AT + timedelta(minutes=4)
    )


def test_current_real_business_state_stays_stop_despite_local_pass() -> None:
    selected = manifest()
    report = local_report(selected)
    current_stop = _dossier(approved_affiliate_ids=(), rights_approved=False)
    tco, human = attestations(report, current_stop, selected)
    result = evaluate_public_release_assurance(
        report,
        current_stop,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )

    assert result.local_assurance_ready is True
    assert result.public_release_ready is False
    assert result.authorization is None
    assert PublicReleaseReason.BUSINESS_NOT_GO in result.reasons


def test_missing_signatures_are_distinct_fail_closed_reasons() -> None:
    selected = manifest()
    report = local_report(selected)
    result = evaluate_public_release_assurance(
        report,
        _dossier(),
        selected,
        AUTHORITY,
        tco_qa_attestation=None,
        human_approval=None,
        at=AT,
    )

    assert PublicReleaseReason.TCO_QA_ATTESTATION_MISSING in result.reasons
    assert PublicReleaseReason.HUMAN_APPROVAL_MISSING in result.reasons
    assert result.authorization is None


def test_cross_policy_report_is_rejected_even_with_same_role_keys() -> None:
    alternate_policy = POLICY.model_copy(update={"policy_id": "alternate-v2"})
    alternate_policy = AssurancePolicy.model_validate(alternate_policy.model_dump())
    alternate_authority = ReleaseAssuranceAuthority(
        alternate_policy, TRUST, CONTROLLER_PRIVATE
    )
    selected = manifest()
    report = local_report(
        selected, authority=alternate_authority, policy=alternate_policy
    )
    dossier = _dossier()
    tco, human = attestations(report, dossier, selected)
    result = evaluate_public_release_assurance(
        report,
        dossier,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )

    assert PublicReleaseReason.ASSURANCE_POLICY_MISMATCH in result.reasons
    assert PublicReleaseReason.LOCAL_ASSURANCE_EXPIRED not in result.reasons
    assert result.authorization is None


def test_attacker_authority_cannot_authorize_the_pinned_runtime() -> None:
    controller = Ed25519PrivateKey.generate()
    tco_private = Ed25519PrivateKey.generate()
    human_private = Ed25519PrivateKey.generate()
    controller_key = create_verification_key(
        controller.public_key(), issuer="evil-controller", role=SigningRole.CONTROLLER
    )
    tco_key = create_verification_key(
        tco_private.public_key(), issuer="evil-tco", role=SigningRole.TCO_QA
    )
    human_key = create_verification_key(
        human_private.public_key(), issuer="evil-human", role=SigningRole.HUMAN_APPROVER
    )
    trust = ControlTrustStore(
        controller=controller_key, gold_tco_qa=tco_key, release_human=human_key
    )
    policy = AssurancePolicy(
        policy_id="evil-v2",
        trust_store_sha256=hash_control_trust_store(trust),
        tco_qa_key_id_sha256=tco_key.key_id_sha256,
        human_key_id_sha256=human_key.key_id_sha256,
        assurance_runner_key_id_sha256=controller_key.key_id_sha256,
        requirements=REQUIREMENTS,
        maximum_evidence_ttl_seconds=2 * 86400,
        maximum_attestation_ttl_seconds=86400,
    )
    authority = ReleaseAssuranceAuthority(policy, trust, controller)
    selected = manifest()
    report = evaluate_local_assurance(
        evidence_bundle(
            selected,
            policy=policy,
            runner_private=controller,
            runner_issuer="evil-controller",
        ),
        authority,
        at=AT,
    )
    dossier = _dossier()
    snapshots = tuple(sorted(selected.data_snapshot_sha256s))
    tco_attestation = sign_local_assurance_report(
        report,
        tco_private,
        issuer="evil-tco",
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(hours=1),
    )
    human_attestation = sign_public_release_approval(
        report,
        dossier,
        selected,
        human_private,
        issuer="evil-human",
        decision=ApprovalDecision.GO,
        decision_record_sha256="f" * 64,
        approved_data_snapshot_sha256s=snapshots,
        issued_at=AT + timedelta(minutes=2),
        expires_at=AT + timedelta(hours=1),
    )
    result = evaluate_public_release_assurance(
        report,
        dossier,
        selected,
        authority,
        tco_qa_attestation=tco_attestation,
        human_approval=human_attestation,
        at=AT + timedelta(minutes=3),
    )

    assert result.decision is PublicReleaseDecision.GO
    assert not verify_release_assurance_report(
        result, RUNTIME, at=AT + timedelta(minutes=4)
    )


def test_current_time_verification_rejects_exact_expiry_and_copied_report() -> None:
    _, _, _, _, _, result = public_go()
    assert verify_release_assurance_report(
        result, RUNTIME, at=result.expires_at - timedelta(microseconds=1)
    )
    assert not verify_release_assurance_report(
        result, RUNTIME, at=result.expires_at
    )
    copied = result.model_copy(update={"artifact_sha256": "9" * 64})
    assert not verify_release_assurance_report(copied, RUNTIME, at=AT)

    duplicated = result.model_dump()
    duplicated["approved_data_snapshot_sha256s"] = (
        *result.approved_data_snapshot_sha256s,
        result.approved_data_snapshot_sha256s[0],
    )
    with pytest.raises(ValidationError, match="canonical and unique"):
        ReleaseAssuranceReport.model_validate(duplicated)


def test_human_signature_cannot_be_reused_with_an_unreviewed_dossier() -> None:
    selected, approved, report, tco, human, _ = public_go()
    substituted = _dossier(approved_affiliate_ids=(), rights_approved=False)
    result = evaluate_public_release_assurance(
        report,
        substituted,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )

    assert PublicReleaseReason.HUMAN_APPROVAL_INVALID in result.reasons
    assert PublicReleaseReason.BUSINESS_NOT_GO in result.reasons


def test_unreviewed_snapshot_cannot_be_silently_added_to_human_approval() -> None:
    selected = manifest(
        data_snapshot_sha256s=("3" * 64, "4" * 64, "5" * 64, "6" * 64)
    )
    report = local_report(selected)
    with pytest.raises(ValueError, match="exactly match"):
        sign_public_release_approval(
            report,
            _dossier(),
            selected,
            HUMAN_PRIVATE,
            issuer="human",
            decision=ApprovalDecision.GO,
            decision_record_sha256="f" * 64,
            approved_data_snapshot_sha256s=("3" * 64, "4" * 64, "5" * 64),
            issued_at=AT + timedelta(minutes=2),
            expires_at=AT + timedelta(hours=1),
        )


def test_manifest_must_include_all_dossier_receipts_even_when_human_signs() -> None:
    selected = manifest(data_snapshot_sha256s=("3" * 64, "4" * 64))
    report = local_report(selected)
    dossier = _dossier()
    tco, human = attestations(report, dossier, selected)
    result = evaluate_public_release_assurance(
        report,
        dossier,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )

    assert PublicReleaseReason.DATA_BINDING_MISMATCH in result.reasons


def test_human_stop_is_validly_signed_but_never_public_go() -> None:
    selected = manifest()
    report = local_report(selected)
    dossier = _dossier()
    tco = attestations(report, dossier, selected)[0]
    human_stop = sign_public_release_approval(
        report,
        dossier,
        selected,
        HUMAN_PRIVATE,
        issuer="human",
        decision=ApprovalDecision.STOP,
        decision_record_sha256="f" * 64,
        approved_data_snapshot_sha256s=tuple(sorted(selected.data_snapshot_sha256s)),
        issued_at=AT + timedelta(minutes=2),
        expires_at=AT + timedelta(hours=1),
    )
    result = evaluate_public_release_assurance(
        report,
        dossier,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human_stop,
        at=AT + timedelta(minutes=3),
    )

    assert result.human_decision is ApprovalDecision.STOP
    assert PublicReleaseReason.HUMAN_DECISION_NOT_GO in result.reasons
    assert result.authorization is None


def test_manifest_rights_affiliate_and_cta_bindings_are_fail_closed() -> None:
    selected = manifest(cta=AffiliateCta(decision=CtaDecision.UNREVIEWED))
    report = local_report(selected)
    mismatched = _dossier(
        provenance=DossierProvenance(
            property_domain="example.test",
            rights_bundle_sha256="7" * 64,
            affiliate_bundle_sha256="8" * 64,
            demand_source_sha256="3" * 64,
            cohort_source_sha256="4" * 64,
            operations_source_sha256="5" * 64,
            assembled_at=NOW,
        )
    )
    tco, human = attestations(report, mismatched, selected)
    result = evaluate_public_release_assurance(
        report,
        mismatched,
        selected,
        AUTHORITY,
        tco_qa_attestation=tco,
        human_approval=human,
        at=AT + timedelta(minutes=3),
    )

    assert PublicReleaseReason.RIGHTS_BINDING_MISMATCH in result.reasons
    assert PublicReleaseReason.AFFILIATE_BINDING_MISMATCH in result.reasons
    assert PublicReleaseReason.CTA_NOT_APPROVED in result.reasons


def test_checked_in_examples_are_hash_valid_and_public_stop() -> None:
    local = LocalAssuranceReport.model_validate_json(
        (ROOT / "examples/local-assurance.synthetic-ready.json").read_text()
    )
    public = ReleaseAssuranceReport.model_validate_json(
        (ROOT / "examples/release-assurance.current-stop.json").read_text()
    )

    assert local.decision is LocalAssuranceDecision.READY
    assert public.local_report_sha256 == local.report_sha256
    assert public.decision is PublicReleaseDecision.STOP
    assert public.public_release_ready is False
