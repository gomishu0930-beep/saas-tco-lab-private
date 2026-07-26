from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import saas_preflight.repository_acceptance as acceptance_module
from saas_preflight.cli import run as run_cli
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.repository_acceptance import (
    REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS,
    REQUIRED_REPOSITORY_VERIFICATION_CHECKS,
    HumanRepositoryDecision,
    RepositoryAcceptanceAuthorityPins,
    RepositoryAcceptanceAuthorityBundle,
    RepositoryAcceptanceDecision,
    RepositoryAcceptanceInputError,
    RepositoryAcceptancePolicy,
    RepositoryAcceptanceReason,
    RepositoryAcceptanceTrustStore,
    RepositoryCandidateManifest,
    RepositoryFileDigest,
    RepositoryRestartGate,
    RepositoryRequiredInput,
    RepositoryVerificationFact,
    RepositoryVerificationNetworkMode,
    RepositoryVerificationProvenance,
    RepositoryVerificationRequirement,
    build_repository_candidate_manifest,
    build_repository_acceptance_authority_bundle,
    build_repository_inventory,
    build_repository_verification_bundle,
    build_repository_verification_from_verified_runner_evidence,
    evaluate_repository_acceptance,
    evaluate_repository_acceptance_authority_bundle,
    hash_repository_acceptance_authority_bundle,
    hash_repository_acceptance_policy,
    hash_repository_acceptance_authority_pins,
    hash_repository_acceptance_trust_store,
    hash_repository_verification_authority,
    hash_repository_tree,
    hash_repository_verification_command,
    run_repository_verification,
    sign_human_repository_acceptance,
    sign_repository_verification_attestation,
)
from verified_runner_support import build_verified_runner_context


AT = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
HUMAN_PRIVATE = Ed25519PrivateKey.generate()
INTEGRATION_PRIVATE = Ed25519PrivateKey.generate()
TCO_PRIVATE = Ed25519PrivateKey.generate()
TEST_SCOPE_PATHS_SHA256 = (
    "1197f1b4c22e020f0772d8504f979dd1153e2fb9647dc2c37f61a88402363cae"
)


@pytest.fixture(autouse=True)
def _use_exact_synthetic_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        acceptance_module,
        "_SCOPE_PATHS_BY_PROFILE",
        {acceptance_module.SCOPE_PROFILE: TEST_SCOPE_PATHS_SHA256},
    )


def _digest(index: int) -> str:
    return f"{index:064x}"


def _seed_repository(root: Path) -> None:
    root.mkdir()
    for index, relative in enumerate(acceptance_module._SCOPE_ROOT_FILES, 1):
        selected = root / relative
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_text(f"root-file-{index}\n", encoding="utf-8")
    for index, relative in enumerate(
        acceptance_module._SCOPE_ROOT_DIRECTORIES, 1
    ):
        selected = root / relative
        selected.mkdir(parents=True, exist_ok=True)
        (selected / f"scope-{index}.txt").write_text(
            f"scope-directory-{index}\n", encoding="utf-8"
        )
    previous = root / acceptance_module.PREVIOUS_CANDIDATE_RECORD
    previous.parent.mkdir(parents=True, exist_ok=True)
    previous.write_text("decision: PENDING\n", encoding="utf-8")


def _trust_store() -> RepositoryAcceptanceTrustStore:
    return RepositoryAcceptanceTrustStore(
        human_approver=create_verification_key(
            HUMAN_PRIVATE.public_key(),
            issuer="p18-human",
            role=SigningRole.HUMAN_APPROVER,
        ),
        integration_evidence_runner=create_verification_key(
            INTEGRATION_PRIVATE.public_key(),
            issuer="p18-integration",
            role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        ),
        tco_qa=create_verification_key(
            TCO_PRIVATE.public_key(),
            issuer="p18-tco-qa",
            role=SigningRole.TCO_QA,
        ),
    )


def _facts(
    tree_sha256: str,
    *,
    provenance: RepositoryVerificationProvenance = (
        RepositoryVerificationProvenance.VERIFIED_LOCAL_RUN
    ),
    command_offset: int = 100,
) -> tuple[RepositoryVerificationFact, ...]:
    return tuple(
        RepositoryVerificationFact(
            check=check,
            subject_tree_sha256=tree_sha256,
            command_argv=("p18-tool", "verify", check.value),
            working_directory="repository-root",
            environment_sha256=_digest(command_offset + 50),
            network_mode=RepositoryVerificationNetworkMode.DISABLED,
            interpreter_sha256=_digest(command_offset + 51),
            import_closure_sha256=_digest(command_offset + 52),
            command_sha256=hash_repository_verification_command(
                command_argv=("p18-tool", "verify", check.value),
                working_directory="repository-root",
                environment_sha256=_digest(command_offset + 50),
                network_mode=RepositoryVerificationNetworkMode.DISABLED,
                interpreter_sha256=_digest(command_offset + 51),
                import_closure_sha256=_digest(command_offset + 52),
            ),
            tool_name=f"p18-tool-{index}",
            tool_version="1.0.0",
            provenance=provenance,
            executed_at=AT - timedelta(hours=2),
            not_after=AT + timedelta(days=2),
            assertions_executed=(
                acceptance_module.REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[
                    check
                ]
            ),
            failures=0,
            skipped=0,
            exit_code=0,
            output_sha256=_digest(300 + index),
        )
        for index, check in enumerate(
            REQUIRED_REPOSITORY_VERIFICATION_CHECKS, 1
        )
    )


def _requirements(
    facts: tuple[RepositoryVerificationFact, ...],
) -> tuple[RepositoryVerificationRequirement, ...]:
    return tuple(
        RepositoryVerificationRequirement(
            check=fact.check,
            command_sha256=fact.command_sha256,
            tool_name=fact.tool_name,
            tool_version=fact.tool_version,
            minimum_assertions=fact.assertions_executed,
        )
        for fact in facts
    )


def _context(
    root: Path,
    *,
    with_attestations: bool = True,
    provenance: RepositoryVerificationProvenance = (
        RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
    ),
    integration_private: Ed25519PrivateKey = INTEGRATION_PRIVATE,
    runner_private: Ed25519PrivateKey | None = None,
):
    entries = build_repository_inventory(root)
    tree_hash = hash_repository_tree(entries)
    runner = None
    if provenance is RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2:
        runner = build_verified_runner_context(
            tree_hash, at=AT, runner_private=runner_private
        )
        verification = build_repository_verification_from_verified_runner_evidence(
            runner["evidence"],
            consumption_receipt=runner["consumption_receipt"],
        )
        facts = verification.facts
    else:
        facts = _facts(tree_hash, provenance=provenance)
        verification = build_repository_verification_bundle(tree_hash, facts)
    integration = sign_repository_verification_attestation(
        verification,
        integration_private,
        attestation_id="p18-integration-verification",
        signer_role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        signer_issuer="p18-integration",
        issued_at=AT - timedelta(hours=1),
        expires_at=AT + timedelta(days=1),
        verified_runner_evidence=(None if runner is None else runner["evidence"]),
        verified_runner_authority_sha256=(
            "0" * 64 if runner is None else runner["authority_sha256"]
        ),
    )
    tco = sign_repository_verification_attestation(
        verification,
        TCO_PRIVATE,
        attestation_id="p18-tco-verification",
        signer_role=SigningRole.TCO_QA,
        signer_issuer="p18-tco-qa",
        issued_at=AT - timedelta(hours=1),
        expires_at=AT + timedelta(days=1),
        verified_runner_evidence=(None if runner is None else runner["evidence"]),
        verified_runner_authority_sha256=(
            "0" * 64 if runner is None else runner["authority_sha256"]
        ),
    )
    manifest = build_repository_candidate_manifest(
        root,
        verification,
        candidate_id="p11-p18-local-candidate",
        assembled_at=AT,
        expires_at=AT + timedelta(days=1),
        integration_verification=integration if with_attestations else None,
        tco_qa_verification=tco if with_attestations else None,
        verified_runner_evidence=(None if runner is None else runner["evidence"]),
        verified_runner_policy=(None if runner is None else runner["policy"]),
        verified_runner_trust_store=(
            None if runner is None else runner["trust_store"]
        ),
        verified_runner_authority_pins=(
            None if runner is None else runner["authority_pins"]
        ),
    )
    trust = _trust_store()
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
        verification_requirements=_requirements(facts),
        required_authority_exclusions=(
            REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS
        ),
        maximum_manifest_ttl_seconds=2 * 86400,
        maximum_verification_age_seconds=86400,
        maximum_verification_attestation_ttl_seconds=2 * 86400,
        maximum_acceptance_ttl_seconds=86400,
    )
    return {
        "entries": entries,
        "facts": facts,
        "verification": verification,
        "manifest": manifest,
        "trust": trust,
        "policy": policy,
        "runner": runner,
    }


def _authority(context, decision=HumanRepositoryDecision.GO, condition_ids=()):
    receipt = sign_human_repository_acceptance(
        context["manifest"],
        context["policy"],
        context["trust"],
        HUMAN_PRIVATE,
        receipt_id="p18-human-repository-acceptance",
        revision=1,
        predecessor_receipt_sha256="0" * 64,
        decision=decision,
        condition_ids=condition_ids,
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(hours=12),
    )
    pins = RepositoryAcceptanceAuthorityPins(
        expected_manifest_sha256=context["manifest"].manifest_sha256,
        expected_policy_sha256=hash_repository_acceptance_policy(
            context["policy"]
        ),
        expected_trust_store_sha256=hash_repository_acceptance_trust_store(
            context["trust"]
        ),
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                context["policy"], context["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            "0" * 64
            if context["runner"] is None
            else context["runner"]["authority_sha256"]
        ),
        expected_current_receipt_sha256=receipt.receipt_sha256,
        expected_current_revision=receipt.revision,
    )
    return receipt, pins


def test_inventory_is_deterministic_and_content_mode_bound(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    first = build_repository_inventory(root)
    assert build_repository_inventory(root) == first
    selected = root / "src" / "scope-10.txt"
    selected.write_text("changed\n", encoding="utf-8")
    changed = build_repository_inventory(root)
    assert hash_repository_tree(changed) != hash_repository_tree(first)
    selected.chmod(0o755)
    executable = build_repository_inventory(root)
    assert hash_repository_tree(executable) != hash_repository_tree(changed)


def test_inventory_rejects_symlink_hardlink_secret_and_unknown_top_level(
    tmp_path,
) -> None:
    for attack in ("symlink", "hardlink", "secret", "unknown"):
        root = tmp_path / attack
        _seed_repository(root)
        source = root / "src" / "scope-10.txt"
        if attack == "symlink":
            source.unlink()
            source.symlink_to(root / "README.md")
        elif attack == "hardlink":
            os.link(source, root / "src" / "shadow.txt")
        elif attack == "secret":
            (root / "site" / ".env.production").write_text(
                "SECRET=do-not-hash\n", encoding="utf-8"
            )
        else:
            (root / "shadow.py").write_text("raise SystemExit\n", encoding="utf-8")
        with pytest.raises(RepositoryAcceptanceInputError):
            build_repository_inventory(root)


def test_inventory_rejects_root_symlink_and_path_collision_model(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    alias = tmp_path / "repo-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(RepositoryAcceptanceInputError, match="root and every ancestor"):
        build_repository_inventory(alias)
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RepositoryAcceptanceInputError, match="root and every ancestor"):
        build_repository_inventory(parent_alias / "repo")
    for invalid_path in ("../escape.py", ".", "./README.md", "src//file.py"):
        with pytest.raises(ValidationError):
            RepositoryFileDigest(
                path=invalid_path,
                size_bytes=1,
                executable=False,
                sha256=_digest(1),
            )

    context = _context(root)
    manifest_values = context["manifest"].model_dump()
    colliding = RepositoryFileDigest(
        path="README.MD",
        size_bytes=1,
        executable=False,
        sha256=_digest(999),
    )
    manifest_values["files"] = tuple(
        sorted((*context["manifest"].files, colliding), key=lambda item: item.path)
    )
    with pytest.raises(ValidationError, match="Unicode/case-colliding"):
        RepositoryCandidateManifest.model_validate(manifest_values)

    fabricated = context["manifest"].model_dump()
    fabricated["files"] = (context["manifest"].files[0],)
    with pytest.raises(ValidationError, match="exact fixed scope"):
        RepositoryCandidateManifest.model_validate(fabricated)


def test_attestations_must_follow_execution_and_precede_manifest(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    entries = build_repository_inventory(root)
    tree_hash = hash_repository_tree(entries)
    evidence = build_repository_verification_bundle(tree_hash, _facts(tree_hash))
    late_integration = sign_repository_verification_attestation(
        evidence,
        INTEGRATION_PRIVATE,
        attestation_id="late-integration",
        signer_role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        signer_issuer="p18-integration",
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(days=2),
    )
    late_tco = sign_repository_verification_attestation(
        evidence,
        TCO_PRIVATE,
        attestation_id="late-tco",
        signer_role=SigningRole.TCO_QA,
        signer_issuer="p18-tco-qa",
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(days=2),
    )
    with pytest.raises(ValidationError, match="precede assembly"):
        build_repository_candidate_manifest(
            root,
            evidence,
            candidate_id="late-attestations",
            assembled_at=AT,
            expires_at=AT + timedelta(days=1),
            integration_verification=late_integration,
            tco_qa_verification=late_tco,
        )


def test_v2_attestations_cannot_predate_consumption_receipt_clock_issue(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    runner = context["runner"]
    receipt = runner["consumption_receipt"]
    issued_at = receipt.clock_attestation.issued_at - timedelta(microseconds=1)
    attestations = (
        sign_repository_verification_attestation(
            context["verification"],
            private_key,
            attestation_id=attestation_id,
            signer_role=role,
            signer_issuer=issuer,
            issued_at=issued_at,
            expires_at=AT + timedelta(days=1),
            verified_runner_evidence=runner["evidence"],
            verified_runner_authority_sha256=runner["authority_sha256"],
        )
        for private_key, attestation_id, role, issuer in (
            (
                INTEGRATION_PRIVATE,
                "predated-consumption-integration",
                SigningRole.INTEGRATION_EVIDENCE_RUNNER,
                "p18-integration",
            ),
            (
                TCO_PRIVATE,
                "predated-consumption-tco",
                SigningRole.TCO_QA,
                "p18-tco-qa",
            ),
        )
    )
    integration, tco = attestations
    with pytest.raises(ValidationError, match="follow execution"):
        build_repository_candidate_manifest(
            root,
            context["verification"],
            candidate_id="predated-consumption-receipt",
            assembled_at=AT,
            expires_at=AT + timedelta(days=1),
            integration_verification=integration,
            tco_qa_verification=tco,
            verified_runner_evidence=runner["evidence"],
            verified_runner_policy=runner["policy"],
            verified_runner_trust_store=runner["trust_store"],
            verified_runner_authority_pins=runner["authority_pins"],
        )


def test_missing_verifier_trust_stops_before_human_gate(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    report = evaluate_repository_acceptance(
        context["manifest"], root, at=AT + timedelta(hours=1)
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert report.next_gate is RepositoryRestartGate.LOCAL_VERIFICATION
    assert RepositoryAcceptanceReason.VERIFICATION_TRUST_MISSING in report.reasons
    assert RepositoryAcceptanceReason.RECEIPT_MISSING in report.reasons


def test_wrong_attestation_key_stops_without_human_receipt(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root, integration_private=Ed25519PrivateKey.generate())
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        policy=context["policy"],
        trust_store=context["trust"],
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                context["policy"], context["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            context["runner"]["authority_sha256"]
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert report.next_gate is RepositoryRestartGate.LOCAL_VERIFICATION
    assert (
        RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID
        in report.reasons
    )


def test_signed_verification_without_receipt_is_pending_and_names_gate(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        policy=context["policy"],
        trust_store=context["trust"],
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                context["policy"], context["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            context["runner"]["authority_sha256"]
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.PENDING
    assert report.reasons == (RepositoryAcceptanceReason.RECEIPT_MISSING,)
    assert report.next_gate is RepositoryRestartGate.REPOSITORY_ACCEPTANCE
    assert report.first_external_gate is RepositoryRestartGate.RIGHTS_EVIDENCE
    assert report.authority == "none"
    assert report.external_mutation_authorized is False
    assert report.public_release_authorized is False
    assert report.production_write_authorized is False
    assert report.scale_authorized is False

    mismatched_root = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        policy=context["policy"],
        trust_store=context["trust"],
        expected_verification_authority_sha256=_digest(9999),
    )
    assert mismatched_root.decision is RepositoryAcceptanceDecision.STOP
    assert mismatched_root.next_gate is RepositoryRestartGate.LOCAL_VERIFICATION
    assert (
        RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH
        in mismatched_root.reasons
    )


def test_exact_human_go_accepts_local_integration_only(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.ACCEPTED
    assert report.local_integration_accepted is True
    assert report.next_gate is RepositoryRestartGate.RIGHTS_EVIDENCE
    assert report.external_mutation_authorized is False


def test_fully_signed_legacy_verified_local_run_permanently_stops(tmp_path) -> None:
    root = tmp_path / "repo-legacy"
    _seed_repository(root)
    context = _context(
        root,
        provenance=RepositoryVerificationProvenance.VERIFIED_LOCAL_RUN,
    )
    receipt, pins = _authority(context)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert report.next_gate is RepositoryRestartGate.LOCAL_VERIFICATION
    assert RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC in report.reasons


def test_p18_and_p19_signing_key_reuse_stops_even_when_signatures_are_valid(
    tmp_path,
) -> None:
    root = tmp_path / "repo-key-reuse"
    _seed_repository(root)
    context = _context(root, runner_private=INTEGRATION_PRIVATE)
    receipt, pins = _authority(context)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH in report.reasons
    )


@pytest.mark.parametrize(
    ("decision", "conditions", "expected"),
    (
        (
            HumanRepositoryDecision.CONDITIONAL,
            ("review-again",),
            RepositoryAcceptanceDecision.CONDITIONAL_PENDING,
        ),
        (HumanRepositoryDecision.STOP, (), RepositoryAcceptanceDecision.REJECTED),
    ),
)
def test_conditional_and_stop_never_accept(tmp_path, decision, conditions, expected) -> None:
    root = tmp_path / f"repo-{decision.value}"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context, decision, conditions)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert report.decision is expected
    assert report.local_integration_accepted is False


def test_unsigned_or_fabricated_verification_cannot_accept(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root, with_attestations=False)
    receipt, pins = _authority(context)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_MISSING in report.reasons

    signed = _context(root)
    wrong_requirements = list(signed["policy"].verification_requirements)
    wrong_requirements[0] = wrong_requirements[0].model_copy(
        update={"command_sha256": _digest(999)}
    )
    wrong_policy = signed["policy"].model_copy(
        update={"verification_requirements": tuple(wrong_requirements)}
    )
    wrong_receipt = sign_human_repository_acceptance(
        signed["manifest"],
        wrong_policy,
        signed["trust"],
        HUMAN_PRIVATE,
        receipt_id="p18-wrong-command-acceptance",
        revision=1,
        predecessor_receipt_sha256="0" * 64,
        decision=HumanRepositoryDecision.GO,
        issued_at=AT + timedelta(minutes=1),
        expires_at=AT + timedelta(hours=12),
    )
    wrong_pins = RepositoryAcceptanceAuthorityPins(
        expected_manifest_sha256=signed["manifest"].manifest_sha256,
        expected_policy_sha256=hash_repository_acceptance_policy(wrong_policy),
        expected_trust_store_sha256=hash_repository_acceptance_trust_store(
            signed["trust"]
        ),
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                wrong_policy, signed["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            signed["runner"]["authority_sha256"]
        ),
        expected_current_receipt_sha256=wrong_receipt.receipt_sha256,
        expected_current_revision=1,
    )
    wrong_report = evaluate_repository_acceptance(
        signed["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=wrong_receipt,
        policy=wrong_policy,
        trust_store=signed["trust"],
        authority_pins=wrong_pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            wrong_pins
        ),
    )
    assert wrong_report.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.VERIFICATION_REQUIREMENT_MISMATCH
        in wrong_report.reasons
    )


def test_signed_low_assertion_policy_cannot_bypass_code_defined_floors(
    tmp_path,
) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    baseline = _context(root)
    low_facts = tuple(
        fact.model_copy(update={"assertions_executed": 1})
        for fact in baseline["facts"]
    )
    low_verification = build_repository_verification_bundle(
        baseline["manifest"].tree_sha256,
        low_facts,
        verified_runner_consumption_receipt=(
            baseline["manifest"].verification
            .verified_runner_consumption_receipt
        ),
    )
    integration = sign_repository_verification_attestation(
        low_verification,
        INTEGRATION_PRIVATE,
        attestation_id="p18-low-assertion-integration",
        signer_role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        signer_issuer="p18-integration",
        issued_at=AT - timedelta(hours=1),
        expires_at=AT + timedelta(days=1),
    )
    tco = sign_repository_verification_attestation(
        low_verification,
        TCO_PRIVATE,
        attestation_id="p18-low-assertion-tco",
        signer_role=SigningRole.TCO_QA,
        signer_issuer="p18-tco-qa",
        issued_at=AT - timedelta(hours=1),
        expires_at=AT + timedelta(days=1),
    )
    with pytest.raises(
        ValidationError, match="verified v2 facts require retained runner evidence"
    ):
        build_repository_candidate_manifest(
            root,
            low_verification,
            candidate_id="p18-low-assertion-candidate",
            assembled_at=AT,
            expires_at=AT + timedelta(days=1),
            integration_verification=integration,
            tco_qa_verification=tco,
        )
    manifest = baseline["manifest"]
    low_requirements = tuple(
        requirement.model_copy(update={"minimum_assertions": 1})
        for requirement in baseline["policy"].verification_requirements
    )
    policy_values = baseline["policy"].model_dump()
    policy_values["verification_requirements"] = low_requirements
    with pytest.raises(
        ValidationError,
        match="code-defined repository assertion floors",
    ):
        RepositoryAcceptancePolicy.model_validate(policy_values)

    # model_copy deliberately bypasses validation; every signing/evaluation boundary
    # must revalidate the policy before it can become acceptance authority.
    bypass_policy = baseline["policy"].model_copy(
        update={"verification_requirements": low_requirements}
    )
    with pytest.raises(RepositoryAcceptanceInputError):
        sign_human_repository_acceptance(
            manifest,
            bypass_policy,
            baseline["trust"],
            HUMAN_PRIVATE,
            receipt_id="p18-low-assertion-human",
            revision=1,
            predecessor_receipt_sha256="0" * 64,
            decision=HumanRepositoryDecision.GO,
            issued_at=AT + timedelta(minutes=1),
            expires_at=AT + timedelta(hours=12),
        )
    with pytest.raises(RepositoryAcceptanceInputError):
        evaluate_repository_acceptance(
            manifest,
            root,
            at=AT + timedelta(hours=1),
            policy=bypass_policy,
            trust_store=baseline["trust"],
            expected_verification_authority_sha256=(
                hash_repository_verification_authority(
                    baseline["policy"], baseline["trust"]
                )
            ),
        )


def test_synthetic_verification_expiry_signature_and_tree_drift_stop(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)

    bad_signature = receipt.model_copy(update={"signature_base64url": "A" * 86})
    signature_report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=bad_signature,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=hash_repository_acceptance_authority_pins(
            pins
        ),
    )
    assert RepositoryAcceptanceReason.RECEIPT_SIGNATURE_INVALID in signature_report.reasons

    (root / "README.md").write_text("drift\n", encoding="utf-8")
    drift_report = evaluate_repository_acceptance(
        context["manifest"], root, at=AT + timedelta(hours=1)
    )
    assert drift_report.decision is RepositoryAcceptanceDecision.STOP
    assert RepositoryAcceptanceReason.MANIFEST_DRIFT in drift_report.reasons


def test_synthetic_verification_is_an_actual_local_verification_stop(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(
        root,
        provenance=RepositoryVerificationProvenance.SYNTHETIC_CONTRACT,
    )
    receipt, pins = _authority(context)
    report = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert report.next_gate is RepositoryRestartGate.LOCAL_VERIFICATION
    assert RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC in report.reasons


def test_authority_root_is_required_and_exact(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)
    common = {
        "receipt": receipt,
        "policy": context["policy"],
        "trust_store": context["trust"],
        "authority_pins": pins,
    }
    missing = evaluate_repository_acceptance(
        context["manifest"], root, at=AT + timedelta(hours=1), **common
    )
    assert missing.decision is RepositoryAcceptanceDecision.STOP
    assert RepositoryAcceptanceReason.AUTHORITY_ROOT_MISSING in missing.reasons
    assert missing.next_gate is RepositoryRestartGate.REPOSITORY_ACCEPTANCE
    assert missing.required_inputs == (
        RepositoryRequiredInput.CURRENT_PINNED_ACCEPTANCE_CHAIN,
    )

    mismatched = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        expected_authority_pins_sha256=_digest(4242),
        **common,
    )
    assert mismatched.decision is RepositoryAcceptanceDecision.STOP
    assert RepositoryAcceptanceReason.AUTHORITY_ROOT_MISMATCH in mismatched.reasons

    verifier_mismatch = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
        expected_verification_authority_sha256=_digest(4243),
        **common,
    )
    assert verifier_mismatch.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH
        in verifier_mismatch.reasons
    )


def test_new_stop_head_prevents_replay_of_old_go(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    old_go, _ = _authority(context)
    current_stop = sign_human_repository_acceptance(
        context["manifest"],
        context["policy"],
        context["trust"],
        HUMAN_PRIVATE,
        receipt_id="p18-human-repository-stop",
        revision=2,
        predecessor_receipt_sha256=old_go.receipt_sha256,
        decision=HumanRepositoryDecision.STOP,
        issued_at=AT + timedelta(minutes=2),
        expires_at=AT + timedelta(hours=12),
    )
    current_pins = RepositoryAcceptanceAuthorityPins(
        expected_manifest_sha256=context["manifest"].manifest_sha256,
        expected_policy_sha256=hash_repository_acceptance_policy(
            context["policy"]
        ),
        expected_trust_store_sha256=hash_repository_acceptance_trust_store(
            context["trust"]
        ),
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                context["policy"], context["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            context["runner"]["authority_sha256"]
        ),
        expected_current_receipt_sha256=current_stop.receipt_sha256,
        expected_current_revision=2,
    )
    expected_root = hash_repository_acceptance_authority_pins(current_pins)
    replay = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=old_go,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=current_pins,
        expected_authority_pins_sha256=expected_root,
    )
    assert replay.decision is RepositoryAcceptanceDecision.STOP
    assert RepositoryAcceptanceReason.RECEIPT_NOT_CURRENT in replay.reasons

    stopped = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=current_stop,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=current_pins,
        receipt_chain=(old_go,),
        expected_authority_pins_sha256=expected_root,
    )
    assert stopped.decision is RepositoryAcceptanceDecision.REJECTED
    assert stopped.reasons == (RepositoryAcceptanceReason.HUMAN_STOP,)


def test_revision_two_requires_complete_valid_receipt_history(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    old_go, _ = _authority(context)
    current_stop = sign_human_repository_acceptance(
        context["manifest"],
        context["policy"],
        context["trust"],
        HUMAN_PRIVATE,
        receipt_id="p18-revision-two-stop",
        revision=2,
        predecessor_receipt_sha256=old_go.receipt_sha256,
        decision=HumanRepositoryDecision.STOP,
        issued_at=AT + timedelta(minutes=2),
        expires_at=AT + timedelta(hours=12),
    )
    pins = RepositoryAcceptanceAuthorityPins(
        expected_manifest_sha256=context["manifest"].manifest_sha256,
        expected_policy_sha256=hash_repository_acceptance_policy(
            context["policy"]
        ),
        expected_trust_store_sha256=hash_repository_acceptance_trust_store(
            context["trust"]
        ),
        expected_verification_authority_sha256=(
            hash_repository_verification_authority(
                context["policy"], context["trust"]
            )
        ),
        expected_verified_runner_authority_sha256=(
            context["runner"]["authority_sha256"]
        ),
        expected_current_receipt_sha256=current_stop.receipt_sha256,
        expected_current_revision=2,
    )
    common = {
        "receipt": current_stop,
        "policy": context["policy"],
        "trust_store": context["trust"],
        "authority_pins": pins,
        "expected_authority_pins_sha256": (
            hash_repository_acceptance_authority_pins(pins)
        ),
    }
    missing_history = evaluate_repository_acceptance(
        context["manifest"], root, at=AT + timedelta(hours=1), **common
    )
    assert missing_history.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.RECEIPT_CHAIN_INVALID
        in missing_history.reasons
    )

    tampered_history = old_go.model_copy(
        update={"signature_base64url": "A" * 86}
    )
    invalid_signature = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt_chain=(tampered_history,),
        **common,
    )
    assert invalid_signature.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.RECEIPT_SIGNATURE_INVALID
        in invalid_signature.reasons
    )

    valid_chain = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt_chain=(old_go,),
        **common,
    )
    assert valid_chain.decision is RepositoryAcceptanceDecision.REJECTED
    assert valid_chain.reasons == (RepositoryAcceptanceReason.HUMAN_STOP,)

    with pytest.raises(ValidationError, match="receipt revisions"):
        build_repository_acceptance_authority_bundle(
            context["manifest"],
            context["policy"],
            context["trust"],
            pins,
            current_stop,
        )
    bundle = build_repository_acceptance_authority_bundle(
        context["manifest"],
        context["policy"],
        context["trust"],
        pins,
        current_stop,
        receipt_chain=(old_go,),
    )
    bundle_report = evaluate_repository_acceptance_authority_bundle(
        bundle,
        at=AT + timedelta(hours=1),
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
    )
    assert bundle_report.decision is RepositoryAcceptanceDecision.REJECTED
    assert bundle_report.reasons == (RepositoryAcceptanceReason.HUMAN_STOP,)


def test_exact_expiry_boundaries_and_wrong_attestation_key_stop(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)
    receipt_expired = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=receipt.expires_at,
        receipt=receipt,
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
    )
    assert RepositoryAcceptanceReason.RECEIPT_EXPIRED in receipt_expired.reasons

    verification_expired = evaluate_repository_acceptance(
        context["manifest"],
        root,
        at=context["facts"][0].not_after,
    )
    assert (
        RepositoryAcceptanceReason.VERIFICATION_EXPIRED
        in verification_expired.reasons
    )
    assert (
        RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID
        in verification_expired.reasons
    )

    wrong_key_context = _context(
        root, integration_private=Ed25519PrivateKey.generate()
    )
    wrong_receipt, wrong_pins = _authority(wrong_key_context)
    wrong_key = evaluate_repository_acceptance(
        wrong_key_context["manifest"],
        root,
        at=AT + timedelta(hours=1),
        receipt=wrong_receipt,
        policy=wrong_key_context["policy"],
        trust_store=wrong_key_context["trust"],
        authority_pins=wrong_pins,
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(wrong_pins)
        ),
    )
    assert wrong_key.decision is RepositoryAcceptanceDecision.STOP
    assert (
        RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID
        in wrong_key.reasons
    )


def test_authority_bundle_is_hash_bound_and_evaluates_exact_chain(tmp_path) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)
    bundle = build_repository_acceptance_authority_bundle(
        context["manifest"],
        context["policy"],
        context["trust"],
        pins,
        receipt,
    )
    assert isinstance(bundle, RepositoryAcceptanceAuthorityBundle)
    assert bundle.bundle_sha256 == hash_repository_acceptance_authority_bundle(
        bundle
    )
    report = evaluate_repository_acceptance_authority_bundle(
        bundle,
        at=AT + timedelta(hours=1),
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
    )
    assert report.decision is RepositoryAcceptanceDecision.ACCEPTED
    assert report.local_integration_accepted is True


def test_authority_bundle_cannot_cross_a_current_scope_profile_advance(
    tmp_path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    context = _context(root)
    receipt, pins = _authority(context)
    bundle = build_repository_acceptance_authority_bundle(
        context["manifest"],
        context["policy"],
        context["trust"],
        pins,
        receipt,
    )
    monkeypatch.setattr(
        acceptance_module, "SCOPE_PROFILE", "p11-p22-local-candidate-v4"
    )

    report = evaluate_repository_acceptance_authority_bundle(
        bundle,
        at=AT + timedelta(hours=1),
        expected_authority_pins_sha256=(
            hash_repository_acceptance_authority_pins(pins)
        ),
    )

    assert report.decision is RepositoryAcceptanceDecision.STOP
    assert report.local_integration_accepted is False
    assert (
        RepositoryAcceptanceReason.SCOPE_PROFILE_OUTDATED in report.reasons
    )


def test_cli_builds_authority_free_manifest_and_pending_report(
    tmp_path, capsys
) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    entries = build_repository_inventory(root)
    tree_hash = hash_repository_tree(entries)
    evidence = build_repository_verification_bundle(tree_hash, _facts(tree_hash))
    evidence_path = tmp_path / "verification.json"
    evidence_path.write_text(evidence.model_dump_json(indent=2) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    code = run_cli(
        [
            "build-local-acceptance-manifest",
            "--repo-root",
            str(root),
            "--verification-evidence",
            str(evidence_path),
            "--candidate-id",
            "p18-cli-candidate",
            "--assembled-at",
            AT.isoformat(),
            "--expires-at",
            (AT + timedelta(days=1)).isoformat(),
            "--output",
            str(manifest_path),
        ]
    )
    assert code == 3
    assert RepositoryCandidateManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    ).authority == "none"
    capsys.readouterr()
    code = run_cli(
        [
            "evaluate-local-acceptance",
            str(manifest_path),
            "--repo-root",
            str(root),
            "--at",
            (AT + timedelta(hours=1)).isoformat(),
        ]
    )
    assert code == 3
    output = capsys.readouterr().out
    assert '"decision": "stop"' in output
    assert '"next_gate": "local_verification"' in output


def test_real_verification_runner_builds_all_facts_from_executed_checks(
    tmp_path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    workflow = tmp_path / "workflow.py"
    workflow.write_text("pass\n", encoding="utf-8")
    tools = {
        name: workflow
        for name in (
            "sandbox",
            "python",
            "uv",
            "gitleaks",
            "npm",
            "node",
            "workflow",
        )
    }
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        acceptance_module, "_repository_verification_tool_paths", lambda _: tools
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_environment",
        lambda *_: {"CI": "1"},
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_interpreter_sha256",
        lambda _: _digest(900),
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_runtime_closure_sha256",
        lambda *_: _digest(901),
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_check_command",
        lambda check, **_: ("p18-runner", check.value),
    )

    def execute(command, **_):
        check = acceptance_module.RepositoryVerificationCheck(command[1])
        assertions = acceptance_module.REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[
            check
        ]
        payload = {
            "check": check.value,
            "assertions_executed": assertions,
            "failures": 0,
            "skipped": 0,
            "exit_code": 0,
            "tool_name": "p18-test-runner",
            "tool_version": "1.0.0",
            "underlying_output_sha256": _digest(assertions),
        }
        return (acceptance_module.json.dumps(payload).encode(), b"", 0)

    monkeypatch.setattr(
        acceptance_module, "_execute_repository_verification_command", execute
    )
    bundle = run_repository_verification(
        root,
        workflow_verifier=workflow,
        fact_ttl_seconds=600,
    )
    assert tuple(item.check for item in bundle.facts) == (
        REQUIRED_REPOSITORY_VERIFICATION_CHECKS
    )
    assert all(
        item.provenance
        is RepositoryVerificationProvenance.LOCAL_DIAGNOSTIC_RUN
        and item.succeeded
        for item in bundle.facts
    )
    assert next(
        item
        for item in bundle.facts
        if item.check.value == "web_tests"
    ).network_mode is RepositoryVerificationNetworkMode.LOOPBACK_ONLY
    assert all(
        item.network_mode is RepositoryVerificationNetworkMode.DISABLED
        for item in bundle.facts
        if item.check.value != "web_tests"
    )


def test_real_verification_runner_rejects_runtime_drift(
    tmp_path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    _seed_repository(root)
    workflow = tmp_path / "workflow.py"
    workflow.write_text("pass\n", encoding="utf-8")
    tools = {
        name: workflow
        for name in (
            "sandbox",
            "python",
            "uv",
            "gitleaks",
            "npm",
            "node",
            "workflow",
        )
    }
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        acceptance_module, "_repository_verification_tool_paths", lambda _: tools
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_environment",
        lambda *_: {"CI": "1"},
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_interpreter_sha256",
        lambda _: _digest(902),
    )
    closures = iter((_digest(903), _digest(904)))
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_runtime_closure_sha256",
        lambda *_: next(closures),
    )
    monkeypatch.setattr(
        acceptance_module,
        "_repository_verification_check_command",
        lambda check, **_: ("p18-runner", check.value),
    )

    def execute(command, **_):
        check = acceptance_module.RepositoryVerificationCheck(command[1])
        assertions = acceptance_module.REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[
            check
        ]
        payload = {
            "check": check.value,
            "assertions_executed": assertions,
            "failures": 0,
            "skipped": 0,
            "exit_code": 0,
            "tool_name": "p18-test-runner",
            "tool_version": "1.0.0",
            "underlying_output_sha256": _digest(assertions),
        }
        return (acceptance_module.json.dumps(payload).encode(), b"", 0)

    monkeypatch.setattr(
        acceptance_module, "_execute_repository_verification_command", execute
    )
    with pytest.raises(RepositoryAcceptanceInputError, match="runtime closure changed"):
        run_repository_verification(
            root,
            workflow_verifier=workflow,
            fact_ttl_seconds=600,
        )


def test_verification_result_parser_fails_closed_on_fabricated_output() -> None:
    result = acceptance_module._parse_repository_verification_check_result(
        acceptance_module.RepositoryVerificationCheck.UV_LOCK,
        stdout=b'{"check":"uv_lock","check":"uv_lock"}',
        stderr=b"",
        returncode=0,
    )
    assert result == {
        "assertions_executed": 1,
        "failures": 1,
        "skipped": 0,
        "exit_code": 0,
        "tool_name": "p18-local-runner",
        "tool_version": "1.0.0",
    }


def test_verification_command_output_is_bounded(tmp_path) -> None:
    stdout, stderr, returncode = (
        acceptance_module._execute_repository_verification_command(
            (sys.executable, "-c", "print('x' * 100000)"),
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout_seconds=10,
            maximum_output_bytes=1024,
        )
    )
    assert returncode == 125
    assert len(stdout) + len(stderr) < 70_000
    assert b"output limit" in stderr


def test_p18_pending_fixture_is_deterministic_and_stays_stop(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = (
        sys.executable,
        str(root / "scripts" / "generate_p18_pending_fixture.py"),
        "--repo-root",
        str(root),
    )
    for output in (first, second):
        result = subprocess.run(
            (*command, "--output-dir", str(output)),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    expected_names = (
        "verification-evidence.synthetic.json",
        "candidate-manifest.pending.json",
        "expected-stop-report.json",
    )
    assert all(
        (first / name).read_bytes() == (second / name).read_bytes()
        for name in expected_names
    )
    checked_in = root / "artifacts" / "local-acceptance" / "p18-current-stop"
    assert all(
        (first / name).read_bytes() == (checked_in / name).read_bytes()
        for name in expected_names
    )
    report = (first / "expected-stop-report.json").read_text(encoding="utf-8")
    assert '"decision": "stop"' in report
    assert '"next_gate": "local_verification"' in report
    assert '"authority": "none"' in report
