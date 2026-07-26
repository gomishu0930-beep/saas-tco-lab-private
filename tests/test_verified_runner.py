from __future__ import annotations

import hashlib
import inspect
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import saas_preflight.verified_runner as verified_runner_module
from saas_preflight.cli import run as run_cli
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.repository_acceptance import (
    RepositoryVerificationEvidenceBundle,
    RepositoryVerificationProvenance,
    build_repository_verification_from_verified_runner_evidence,
)
from saas_preflight.verified_runner import (
    REQUIRED_VERIFIED_RUNNER_CHECKS,
    VERIFIED_RUNNER_MINIMUM_ASSERTIONS,
    SignedAdvisorySnapshot,
    VerifiedCheckRecord,
    VerifiedCheckResult,
    VerifiedCheckSpec,
    VerifiedRunnerAuthorityPins,
    VerifiedRunnerChallenge,
    VerifiedRunnerConsumerClockRequest,
    VerifiedRunnerEvidenceBundle,
    VerifiedRunnerImageIdentity,
    VerifiedRunnerInputError,
    VerifiedRunnerNetworkMode,
    VerifiedRunnerPolicy,
    VerifiedRunnerReplayStore,
    VerifiedRunnerRequirement,
    VerifiedRunnerRuntime,
    VerifiedRunnerTrustStore,
    VerifiedTerminationReason,
    build_verified_runner_evidence_bundle,
    hash_advisory_snapshot,
    hash_verified_check_result,
    hash_verified_check_spec,
    hash_verified_runner_authority,
    hash_verified_runner_challenge,
    hash_verified_runner_consumer_clock_request,
    hash_verified_runner_evidence_payload,
    hash_verified_runner_image,
    hash_verified_runner_policy,
    hash_verified_runner_trust_store,
    sign_advisory_snapshot,
    sign_runner_image_attestation,
    sign_verified_run_clock_attestation,
    sign_verified_runner_consumer_clock_attestation,
    sign_verified_runner_consumption_receipt,
    sign_verified_runner_attestation,
    verify_verified_runner_consumption_receipt,
    verify_verified_runner_evidence,
)


AT = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
TREE = "11" * 32
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
RUNNER_PRIVATE = Ed25519PrivateKey.generate()
ADVISORY_PRIVATE = Ed25519PrivateKey.generate()
IMAGE_PRIVATE = Ed25519PrivateKey.generate()
TIME_PRIVATE = Ed25519PrivateKey.generate()
STORAGE_PRIVATE = Ed25519PrivateKey.generate()


def _digest(index: int) -> str:
    return f"{index:064x}"


CONSUMER_STORE_ID = _digest(8000)


def _challenge(**updates) -> VerifiedRunnerChallenge:
    values = {
        "challenge_id": "p19-run-1",
        "sequence": 1,
        "nonce_sha256": _digest(1),
        "subject_tree_sha256": TREE,
        "consumer_store_id_sha256": CONSUMER_STORE_ID,
        "previous_evidence_head_sha256": "0" * 64,
        "issued_at": AT - timedelta(hours=2),
        "not_before": AT - timedelta(minutes=90),
        "expires_at": AT + timedelta(hours=1),
    }
    values.update(updates)
    provisional = VerifiedRunnerChallenge.model_construct(
        **values, schema_version="2.0", challenge_sha256="0" * 64
    )
    return VerifiedRunnerChallenge(
        **values,
        challenge_sha256=hash_verified_runner_challenge(provisional),
    )


def _image() -> VerifiedRunnerImageIdentity:
    values = {
        "runtime": VerifiedRunnerRuntime.READ_ONLY_MICROVM,
        "runtime_name": "p19-microvm",
        "runtime_version": "1.0.0",
        "platform": "linux/arm64",
        "subject_tree_sha256": TREE,
        "image_manifest_sha256": _digest(2),
        "rootfs_sha256": _digest(3),
        "boot_measurement_sha256": _digest(4),
        "runner_binary_sha256": _digest(5),
        "parser_bundle_sha256": _digest(6),
        "dependency_lock_sha256": _digest(7),
        "seccomp_profile_sha256": _digest(8),
        "node_id_sha256": _digest(9),
        "built_at": AT - timedelta(hours=3),
    }
    provisional = VerifiedRunnerImageIdentity.model_construct(
        **values,
        schema_version="2.0",
        rootfs_read_only=True,
        subject_embedded_read_only=True,
        host_mounts=(),
        host_network=False,
        external_network=False,
        privileged=False,
        linux_capabilities=(),
        identity_sha256="0" * 64,
    )
    return VerifiedRunnerImageIdentity(
        **values,
        identity_sha256=hash_verified_runner_image(provisional),
    )


def _trust() -> VerifiedRunnerTrustStore:
    return VerifiedRunnerTrustStore(
        runner=create_verification_key(
            RUNNER_PRIVATE.public_key(),
            issuer="p19-runner",
            role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        ),
        advisory_auditor=create_verification_key(
            ADVISORY_PRIVATE.public_key(),
            issuer="p19-advisory",
            role=SigningRole.SECURITY_AUDITOR,
        ),
        image_builder=create_verification_key(
            IMAGE_PRIVATE.public_key(),
            issuer="p19-image",
            role=SigningRole.PROVIDER_CONFORMANCE,
        ),
        time_auditor=create_verification_key(
            TIME_PRIVATE.public_key(),
            issuer="p19-time",
            role=SigningRole.TIME_AUDITOR,
        ),
        storage_auditor=create_verification_key(
            STORAGE_PRIVATE.public_key(),
            issuer="p19-storage",
            role=SigningRole.STORAGE_AUDITOR,
        ),
    )


def _spec(check, index, challenge, image, advisory) -> VerifiedCheckSpec:
    values = {
        "check": check,
        "challenge_sha256": challenge.challenge_sha256,
        "subject_tree_sha256": TREE,
        "image_identity_sha256": image.identity_sha256,
        "advisory_snapshot_sha256": advisory.snapshot_sha256,
        "node_id_sha256": image.node_id_sha256,
        "command_argv": ("p19-verify", check.value),
        "environment_sha256": _digest(100 + index),
        "network_mode": (
            VerifiedRunnerNetworkMode.LOOPBACK_ONLY
            if check.value == "web_tests"
            else VerifiedRunnerNetworkMode.DISABLED
        ),
        "interpreter_sha256": _digest(200 + index),
        "import_closure_sha256": _digest(300 + index),
        "parser_name": f"p19-parser-{index}",
        "parser_version": "2.0.0",
        "parser_binary_sha256": _digest(400 + index),
        "tool_name": f"p19-tool-{index}",
        "tool_version": "1.0.0",
        "minimum_assertions": VERIFIED_RUNNER_MINIMUM_ASSERTIONS[check],
        "timeout_seconds": 600,
        "maximum_stdout_bytes": 1_048_576,
        "maximum_stderr_bytes": 1_048_576,
    }
    provisional = VerifiedCheckSpec.model_construct(
        **values,
        schema_version="2.0",
        working_directory="/workspace/repository",
        spec_sha256="0" * 64,
    )
    return VerifiedCheckSpec(
        **values,
        spec_sha256=hash_verified_check_spec(provisional),
    )


def _result(spec, index, advisory, **updates) -> VerifiedCheckResult:
    started_at = AT - timedelta(minutes=60) + timedelta(seconds=index * 2)
    ended_at = started_at + timedelta(seconds=1)
    advisory_input = spec.check.value == "dependency_audit"
    values = {
        "check": spec.check,
        "challenge_sha256": spec.challenge_sha256,
        "spec_sha256": spec.spec_sha256,
        "subject_tree_sha256": spec.subject_tree_sha256,
        "image_identity_sha256": spec.image_identity_sha256,
        "advisory_snapshot_sha256": spec.advisory_snapshot_sha256,
        "node_id_sha256": spec.node_id_sha256,
        "started_at": started_at,
        "ended_at": ended_at,
        "not_after": AT + timedelta(hours=1),
        "duration_milliseconds": 1_000,
        "monotonic_duration_nanoseconds": 1_000_000_000,
        "termination_reason": VerifiedTerminationReason.EXITED,
        "exit_code": 0,
        "signal_number": None,
        "stdout_sha256": EMPTY_SHA256,
        "stdout_bytes": 0,
        "stdout_truncated": False,
        "stderr_sha256": EMPTY_SHA256,
        "stderr_bytes": 0,
        "stderr_truncated": False,
        "parser_name": spec.parser_name,
        "parser_version": spec.parser_version,
        "parser_binary_sha256": spec.parser_binary_sha256,
        "parser_output_sha256": _digest(500 + index),
        "parser_output_bytes": 512,
        "parser_output_complete": True,
        "advisory_database_sha256": (
            advisory.database_sha256 if advisory_input else "0" * 64
        ),
        "advisory_file_identity_sha256": (
            _digest(600 + index) if advisory_input else "0" * 64
        ),
        "advisory_bytes_read": 10_000 if advisory_input else 0,
        "advisory_input_complete": advisory_input,
        "tool_name": spec.tool_name,
        "tool_version": spec.tool_version,
        "assertions_executed": spec.minimum_assertions,
        "failures": 0,
        "skipped": 0,
    }
    values.update(updates)
    provisional = VerifiedCheckResult.model_construct(
        **values, schema_version="2.0", result_sha256="0" * 64
    )
    return VerifiedCheckResult(
        **values,
        result_sha256=hash_verified_check_result(provisional),
    )


def _context(
    *,
    challenge=None,
    result_update=None,
    result_update_check=None,
    clock_response_timeout_seconds=5,
):
    challenge = challenge or _challenge()
    image = _image()
    advisory = sign_advisory_snapshot(
        signing_key=ADVISORY_PRIVATE,
        issuer="p19-advisory",
        snapshot_id="p19-advisory-1",
        source_set_sha256=_digest(10),
        database_sha256=_digest(11),
        record_count=1_000,
        generated_at=AT - timedelta(hours=4),
        not_after=AT + timedelta(hours=2),
    )
    records = []
    for index, check in enumerate(REQUIRED_VERIFIED_RUNNER_CHECKS, 1):
        spec = _spec(check, index, challenge, image, advisory)
        updates = (
            result_update or {}
            if result_update_check is None or check.value == result_update_check
            else {}
        )
        result = _result(spec, index, advisory, **updates)
        records.append(VerifiedCheckRecord(spec=spec, result=result))
    records = tuple(records)
    trust = _trust()
    image_attestation = sign_runner_image_attestation(
        image=image,
        challenge=challenge,
        records=records,
        signing_key=IMAGE_PRIVATE,
        issuer="p19-image",
        platform_quote_sha256=_digest(12),
        isolation_measurement_sha256=_digest(13),
        issued_at=AT - timedelta(minutes=50),
        expires_at=AT + timedelta(hours=1),
    )
    clock = sign_verified_run_clock_attestation(
        challenge=challenge,
        records=records,
        node_id_sha256=image.node_id_sha256,
        signing_key=TIME_PRIVATE,
        issuer="p19-time",
        observed_at=AT - timedelta(minutes=49),
        issued_at=AT - timedelta(minutes=48),
        expires_at=AT + timedelta(hours=1),
    )
    requirements = tuple(
        VerifiedRunnerRequirement(
            check=item.spec.check,
            spec_sha256=item.spec.spec_sha256,
            minimum_assertions=item.spec.minimum_assertions,
        )
        for item in records
    )
    policy = VerifiedRunnerPolicy(
        policy_id="p19-runner-policy",
        trust_store_sha256=hash_verified_runner_trust_store(trust),
        challenge_sha256=challenge.challenge_sha256,
        image_identity_sha256=image.identity_sha256,
        advisory_snapshot_sha256=advisory.snapshot_sha256,
        requirements=requirements,
        maximum_advisory_age_seconds=86_400,
        maximum_advisory_ttl_seconds=86_400,
        maximum_result_age_seconds=86_400,
        maximum_result_ttl_seconds=86_400,
        maximum_attestation_ttl_seconds=86_400,
        maximum_challenge_ttl_seconds=14_400,
        maximum_clock_attestation_ttl_seconds=7_200,
        maximum_clock_observation_lag_seconds=5,
        clock_response_timeout_seconds=clock_response_timeout_seconds,
        maximum_image_attestation_ttl_seconds=7_200,
    )
    evidence_sha256 = hash_verified_runner_evidence_payload(
        subject_tree_sha256=TREE,
        challenge=challenge,
        image=image,
        image_attestation=image_attestation,
        advisory_snapshot=advisory,
        records=records,
        clock_attestation=clock,
    )
    runner_attestation = sign_verified_runner_attestation(
        evidence_sha256=evidence_sha256,
        challenge_sha256=challenge.challenge_sha256,
        clock_attestation_sha256=clock.attestation_sha256,
        subject_tree_sha256=TREE,
        image_identity_sha256=image.identity_sha256,
        advisory_snapshot_sha256=advisory.snapshot_sha256,
        policy=policy,
        trust_store=trust,
        signing_key=RUNNER_PRIVATE,
        issuer="p19-runner",
        issued_at=AT - timedelta(minutes=47),
        expires_at=AT + timedelta(hours=1),
    )
    evidence = build_verified_runner_evidence_bundle(
        subject_tree_sha256=TREE,
        challenge=challenge,
        image=image,
        image_attestation=image_attestation,
        advisory_snapshot=advisory,
        records=records,
        clock_attestation=clock,
        runner_attestation=runner_attestation,
    )
    pins = VerifiedRunnerAuthorityPins(
        expected_subject_tree_sha256=TREE,
        expected_consumer_store_id_sha256=challenge.consumer_store_id_sha256,
        expected_challenge_sha256=challenge.challenge_sha256,
        expected_sequence=challenge.sequence,
        expected_previous_evidence_head_sha256=(
            challenge.previous_evidence_head_sha256
        ),
        expected_policy_sha256=hash_verified_runner_policy(policy),
        expected_trust_store_sha256=hash_verified_runner_trust_store(trust),
        expected_image_identity_sha256=image.identity_sha256,
        expected_advisory_snapshot_sha256=advisory.snapshot_sha256,
    )
    authority = hash_verified_runner_authority(policy, trust, pins)
    request_values = {
        "store_id_sha256": challenge.consumer_store_id_sha256,
        "expected_sequence": challenge.sequence,
        "expected_previous_evidence_head_sha256": (
            challenge.previous_evidence_head_sha256
        ),
        "challenge_sha256": challenge.challenge_sha256,
        "evidence_bundle_sha256": evidence.bundle_sha256,
        "authority_sha256": authority,
        "request_nonce_sha256": _digest(700),
    }
    request_provisional = VerifiedRunnerConsumerClockRequest.model_construct(
        **request_values, schema_version="1.0", request_sha256="0" * 64
    )
    consumer_clock_request = VerifiedRunnerConsumerClockRequest(
        **request_values,
        request_sha256=hash_verified_runner_consumer_clock_request(
            request_provisional
        ),
    )
    consumer_clock = sign_verified_runner_consumer_clock_attestation(
        consumer_clock_request,
        trust,
        TIME_PRIVATE,
        observed_at=AT,
        issued_at=AT + timedelta(seconds=1),
        expires_at=AT + timedelta(minutes=10),
    )
    receipt = sign_verified_runner_consumption_receipt(
        values={
            "store_id_sha256": challenge.consumer_store_id_sha256,
            "sequence": challenge.sequence,
            "previous_evidence_head_sha256": (
                challenge.previous_evidence_head_sha256
            ),
            "evidence_head_sha256": evidence.bundle_sha256,
            "challenge_sha256": challenge.challenge_sha256,
            "evidence_bundle_sha256": evidence.bundle_sha256,
            "authority_sha256": authority,
            "clock_request": consumer_clock_request,
            "clock_attestation": consumer_clock,
            "clock_request_sha256": consumer_clock_request.request_sha256,
            "clock_attestation_sha256": consumer_clock.attestation_sha256,
            "consumed_at": AT,
        },
        trust_store=trust,
        signing_key=STORAGE_PRIVATE,
    )
    return {
        "evidence": evidence,
        "policy": policy,
        "trust": trust,
        "pins": pins,
        "authority": authority,
        "consumption_receipt": receipt,
    }


def test_verified_runner_v2_converts_only_after_full_authority_verification() -> None:
    context = _context()
    evidence = verify_verified_runner_evidence(
        context["evidence"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        expected_authority_sha256=context["authority"],
        at=AT,
    )
    bundle = build_repository_verification_from_verified_runner_evidence(
        evidence,
        consumption_receipt=context["consumption_receipt"],
    )
    assert len(bundle.facts) == 14
    assert all(
        item.provenance
        is RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
        and item.succeeded
        for item in bundle.facts
    )


def test_verified_runner_cli_is_pure_and_emits_only_a_structural_summary(
    tmp_path, capsys
) -> None:
    context = _context()
    paths = {}
    for name, value in (
        ("evidence", context["evidence"]),
        ("policy", context["policy"]),
        ("trust", context["trust"]),
        ("pins", context["pins"]),
        ("receipt", context["consumption_receipt"]),
    ):
        selected = tmp_path / f"{name}.json"
        selected.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        paths[name] = selected
    output = tmp_path / "p18-summary.json"
    result = run_cli(
        (
            "verify-immutable-runner-evidence",
            str(paths["evidence"]),
            "--consumption-receipt",
            str(paths["receipt"]),
            "--policy",
            str(paths["policy"]),
            "--trust-store",
            str(paths["trust"]),
            "--authority-pins",
            str(paths["pins"]),
            "--expected-authority-sha256",
            context["authority"],
            "--at",
            AT.isoformat(),
            "--output",
            str(output),
        )
    )
    assert result == 0
    emitted = capsys.readouterr().out
    assert '"mode": "pure-verification-only"' in emitted
    assert '"authority": "none"' in emitted
    summary = RepositoryVerificationEvidenceBundle.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert len(summary.facts) == 14
    assert not (tmp_path / "replay-ledger.json").exists()


def _anchor_runtime(*, fail_revision: int | None = None):
    state = {"revision": -1, "sha256": "0" * 64, "fail_revision": fail_revision}

    def commit(revision: int, digest: str) -> None:
        if state["fail_revision"] == revision:
            raise OSError("simulated anchor outage")
        if revision < state["revision"] or revision > state["revision"] + 1:
            raise ValueError("anchor revision is not monotonic")
        if revision == state["revision"] and digest != state["sha256"]:
            raise ValueError("anchor revision conflicts")
        state["revision"] = revision
        state["sha256"] = digest

    def read() -> str:
        return state["sha256"]

    return state, commit, read


def _consumer_clock(context):
    def attest(request):
        return sign_verified_runner_consumer_clock_attestation(
            request,
            context["trust"],
            TIME_PRIVATE,
            observed_at=AT,
            issued_at=AT + timedelta(seconds=1),
            expires_at=AT + timedelta(minutes=10),
        )

    return attest


def test_replay_store_consumes_a_challenge_once_and_survives_reopen(
    tmp_path,
) -> None:
    context = _context()
    state, commit, read = _anchor_runtime()
    auth_key = b"p19-replay-store-authentication-key" * 2
    path = tmp_path / "p19-replay.sqlite3"
    store = VerifiedRunnerReplayStore.create(
        path,
        store_id_sha256=_digest(8000),
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    receipt = store.consume(
        context["evidence"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        expected_authority_sha256=context["authority"],
    )
    assert receipt.sequence == 1
    assert receipt.evidence_head_sha256 == context["evidence"].bundle_sha256
    assert state["revision"] == 2
    with pytest.raises(VerifiedRunnerInputError, match="exact unused store tail"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    reopened = VerifiedRunnerReplayStore(
        path,
        expected_store_id_sha256=_digest(8000),
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    assert reopened.receipts() == (receipt,)
    assert "state_authentication_key" not in inspect.signature(
        reopened.consume
    ).parameters


def test_replay_store_detects_row_meta_and_anchor_tampering(tmp_path) -> None:
    context = _context()
    state, commit, read = _anchor_runtime()
    path = tmp_path / "p19-tamper.sqlite3"
    store = VerifiedRunnerReplayStore.create(
        path,
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-tamper-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    store.consume(
        context["evidence"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        expected_authority_sha256=context["authority"],
    )
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE verified_runner_consumptions SET authority_sha256=?",
                (_digest(9999),),
            )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='evidence_head_sha256'",
            (_digest(9998),),
        )
    with pytest.raises(VerifiedRunnerInputError, match="authentication failed"):
        store.receipts()

    # Restore the database bytes through a fresh fixture, then prove a foreign
    # external anchor cannot be silently accepted.
    other = tmp_path / "p19-anchor.sqlite3"
    state2, commit2, read2 = _anchor_runtime()
    anchored = VerifiedRunnerReplayStore.create(
        other,
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-anchor-authentication-key" * 2,
        anchor_commit=commit2,
        anchor_read=read2,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    state2["sha256"] = _digest(9997)
    with pytest.raises(VerifiedRunnerInputError, match="external anchor mismatch"):
        anchored.receipts()


def test_replay_store_recovers_only_the_committed_anchor_tail(tmp_path) -> None:
    context = _context()
    state, commit, read = _anchor_runtime(fail_revision=2)
    path = tmp_path / "p19-anchor-recovery.sqlite3"
    auth_key = b"p19-anchor-recovery-authentication-key" * 2
    store = VerifiedRunnerReplayStore.create(
        path,
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="runner-anchor-commit failed"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    assert state["revision"] == 1
    state["fail_revision"] = None
    recovered = VerifiedRunnerReplayStore(
        path,
        expected_store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    assert len(recovered.receipts()) == 1
    assert state["revision"] == 2


def test_replay_store_bounds_clock_callback_and_freezes_runtime(tmp_path) -> None:
    context = _context(clock_response_timeout_seconds=1)
    _state, commit, read = _anchor_runtime()
    release = Event()
    calls = 0

    def hung_clock(request):
        nonlocal calls
        calls += 1
        release.wait(timeout=10)
        return _consumer_clock(context)(request)

    store = VerifiedRunnerReplayStore.create(
        tmp_path / "p19-clock-timeout.sqlite3",
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-clock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=hung_clock,
        consumption_signing_key=STORAGE_PRIVATE,
    )
    started = monotonic()
    with pytest.raises(VerifiedRunnerInputError, match="timed out; runtime frozen"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    assert 0.8 <= monotonic() - started < 3
    with pytest.raises(VerifiedRunnerInputError, match="persistently frozen"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    assert calls == 1
    assert store.receipts() == ()
    reopened = VerifiedRunnerReplayStore(
        tmp_path / "p19-clock-timeout.sqlite3",
        expected_store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-clock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="persistently frozen"):
        reopened.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    release.set()


def test_replay_store_bounds_external_anchor_callback(
    tmp_path, monkeypatch
) -> None:
    context = _context()
    _state, commit, read = _anchor_runtime()
    release = Event()
    entered = Event()
    store = VerifiedRunnerReplayStore.create(
        tmp_path / "p19-anchor-timeout.sqlite3",
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-anchor-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )

    def hung_read() -> str:
        entered.set()
        release.wait(timeout=10)
        return read()

    store._anchor_read = hung_read
    monkeypatch.setattr(
        verified_runner_module, "_STORE_COORDINATION_TIMEOUT_SECONDS", 0.05
    )
    started = monotonic()
    try:
        with pytest.raises(VerifiedRunnerInputError, match="anchor-read timed out"):
            store.receipts()
        assert entered.is_set()
        assert monotonic() - started < 1
    finally:
        release.set()


def test_replay_store_bounds_cross_process_file_lock(
    tmp_path, monkeypatch
) -> None:
    context = _context()
    _state, commit, read = _anchor_runtime()
    store = VerifiedRunnerReplayStore.create(
        tmp_path / "p19-lock-timeout.sqlite3",
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-lock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    holder = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "import fcntl, sys, time; "
                "handle=open(sys.argv[1], 'a+b'); "
                "fcntl.flock(handle.fileno(), fcntl.LOCK_EX); "
                "print('locked', flush=True); time.sleep(10)"
            ),
            str(store._lock_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        monkeypatch.setattr(
            verified_runner_module, "_STORE_COORDINATION_TIMEOUT_SECONDS", 0.05
        )
        started = monotonic()
        with pytest.raises(VerifiedRunnerInputError, match="store lock timed out"):
            store.receipts()
        assert monotonic() - started < 1
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_replay_store_persists_freeze_for_invalid_clock_signature(tmp_path) -> None:
    context = _context()
    _state, commit, read = _anchor_runtime()
    path = tmp_path / "p19-invalid-clock-signature.sqlite3"
    auth_key = b"p19-invalid-clock-signature-auth-key" * 2

    def invalid_signature(request):
        return _consumer_clock(context)(request).model_copy(
            update={"signature_base64url": "A" * 86}
        )

    store = VerifiedRunnerReplayStore.create(
        path,
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=invalid_signature,
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="not authoritative"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    reopened = VerifiedRunnerReplayStore(
        path,
        expected_store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=auth_key,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=_consumer_clock(context),
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="persistently frozen"):
        reopened.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )


def test_replay_store_rejects_evidence_pinned_to_another_store_before_clock(
    tmp_path,
) -> None:
    context = _context()
    _state, commit, read = _anchor_runtime()
    calls = 0

    def clock(request):
        nonlocal calls
        calls += 1
        return _consumer_clock(context)(request)

    store = VerifiedRunnerReplayStore.create(
        tmp_path / "p19-foreign-store.sqlite3",
        store_id_sha256=_digest(8001),
        state_authentication_key=b"p19-foreign-store-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=clock,
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="store or authority"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )
    assert calls == 0


def test_replay_store_rejects_backdated_consumer_clock(tmp_path) -> None:
    context = _context()
    _state, commit, read = _anchor_runtime()

    def backdated(request):
        return sign_verified_runner_consumer_clock_attestation(
            request,
            context["trust"],
            TIME_PRIVATE,
            observed_at=AT - timedelta(minutes=1),
            issued_at=AT,
            expires_at=AT + timedelta(minutes=1),
        )

    store = VerifiedRunnerReplayStore.create(
        tmp_path / "p19-backdated-clock.sqlite3",
        store_id_sha256=CONSUMER_STORE_ID,
        state_authentication_key=b"p19-backdated-clock-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=read,
        clock_attest=backdated,
        consumption_signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="not authoritative"):
        store.consume(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
        )


def test_consumption_receipt_signature_is_required() -> None:
    context = _context()
    receipt = context["consumption_receipt"].model_copy(
        update={"signature_base64url": "B" * 86}
    )
    with pytest.raises(VerifiedRunnerInputError, match="not authoritative"):
        verify_verified_runner_consumption_receipt(
            receipt,
            context["evidence"],
            trust_store=context["trust"],
            policy=context["policy"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
            at=AT,
        )


def test_storage_resign_cannot_hide_a_forged_nested_time_signature() -> None:
    context = _context()
    original = context["consumption_receipt"]
    forged_clock = original.clock_attestation.model_copy(
        update={"signature_base64url": "B" * 86}
    )
    excluded = {
            "schema_version",
            "signer_issuer",
            "signer_role",
            "signer_key_id_sha256",
            "receipt_sha256",
            "signature_base64url",
    }
    values = {
        name: getattr(original, name)
        for name in type(original).model_fields
        if name not in excluded
    }
    values["clock_attestation"] = forged_clock
    resigned = sign_verified_runner_consumption_receipt(
        values=values,
        trust_store=context["trust"],
        signing_key=STORAGE_PRIVATE,
    )
    with pytest.raises(VerifiedRunnerInputError, match="not authoritative"):
        verify_verified_runner_consumption_receipt(
            resigned,
            context["evidence"],
            trust_store=context["trust"],
            policy=context["policy"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
            at=AT,
        )


def test_packet_external_authority_root_rejects_self_consistent_replacement() -> None:
    context = _context()
    with pytest.raises(VerifiedRunnerInputError, match="authority root"):
        verify_verified_runner_evidence(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=_digest(999),
            at=AT,
        )


@pytest.mark.parametrize(
    "updates",
    (
        {
            "termination_reason": VerifiedTerminationReason.TIMEOUT,
            "exit_code": None,
        },
        {"exit_code": 1},
        {"failures": 1},
        {"skipped": 1},
        {"parser_version": "9.9.9"},
        {
            "termination_reason": VerifiedTerminationReason.OUTPUT_LIMIT,
            "exit_code": None,
            "stdout_truncated": True,
        },
    ),
)
def test_signed_failed_or_parser_substituted_results_never_verify(updates) -> None:
    context = _context(result_update=updates)
    with pytest.raises(VerifiedRunnerInputError, match="verified check failed"):
        verify_verified_runner_evidence(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
            at=AT,
        )


def test_dependency_audit_must_bind_the_signed_database_bytes() -> None:
    context = _context(
        result_update={"advisory_database_sha256": _digest(998)},
        result_update_check="dependency_audit",
    )
    with pytest.raises(VerifiedRunnerInputError, match="verified check failed"):
        verify_verified_runner_evidence(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
            at=AT,
        )


def test_empty_advisory_snapshot_and_false_empty_output_are_invalid() -> None:
    with pytest.raises(ValidationError):
        SignedAdvisorySnapshot(
            snapshot_id="empty",
            source_set_sha256=_digest(1),
            database_sha256=_digest(2),
            record_count=0,
            generated_at=AT,
            not_after=AT + timedelta(hours=1),
            signer_issuer="auditor",
            signer_key_id_sha256=_digest(3),
            snapshot_sha256=_digest(4),
            signature_base64url="A" * 86,
        )
    context = _context()
    result = context["evidence"].records[0].result
    values = result.model_dump()
    values["stdout_sha256"] = _digest(1234)
    values["result_sha256"] = _digest(1235)
    with pytest.raises(ValidationError, match="empty stdout"):
        VerifiedCheckResult.model_validate(values)
    values = result.model_dump()
    values["stdout_bytes"] = 1
    values["result_sha256"] = _digest(1236)
    with pytest.raises(ValidationError, match="stdout content hash"):
        VerifiedCheckResult.model_validate(values)


def test_challenge_sequence_and_predecessor_are_consumer_pinned() -> None:
    context = _context()
    wrong = context["pins"].model_copy(update={"expected_sequence": 2})
    wrong_authority = hash_verified_runner_authority(
        context["policy"], context["trust"], wrong
    )
    with pytest.raises(VerifiedRunnerInputError, match="pins do not bind"):
        verify_verified_runner_evidence(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=wrong,
            expected_authority_sha256=wrong_authority,
            at=AT,
        )


def test_expired_challenge_advisory_result_and_attestation_replay_stop() -> None:
    context = _context()
    with pytest.raises(VerifiedRunnerInputError):
        verify_verified_runner_evidence(
            context["evidence"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            expected_authority_sha256=context["authority"],
            at=AT + timedelta(hours=2),
        )


def test_wall_and_monotonic_duration_must_agree() -> None:
    context = _context()
    result = context["evidence"].records[0].result
    values = result.model_dump()
    values["monotonic_duration_nanoseconds"] = 1
    values["result_sha256"] = _digest(777)
    with pytest.raises(ValidationError, match="wall/monotonic"):
        VerifiedCheckResult.model_validate(values)
