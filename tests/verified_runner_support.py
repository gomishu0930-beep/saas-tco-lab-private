"""Credential-free P19 V2 evidence factory used only by tests."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.verified_runner import (
    REQUIRED_VERIFIED_RUNNER_CHECKS,
    VERIFIED_RUNNER_MINIMUM_ASSERTIONS,
    VerifiedCheckRecord,
    VerifiedCheckResult,
    VerifiedCheckSpec,
    VerifiedRunnerAuthorityPins,
    VerifiedRunnerChallenge,
    VerifiedRunnerConsumerClockRequest,
    VerifiedRunnerImageIdentity,
    VerifiedRunnerNetworkMode,
    VerifiedRunnerPolicy,
    VerifiedRunnerRequirement,
    VerifiedRunnerRuntime,
    VerifiedRunnerTrustStore,
    VerifiedTerminationReason,
    build_verified_runner_evidence_bundle,
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
)


def _digest(index: int) -> str:
    return f"{index:064x}"


def build_verified_runner_context(
    tree_sha256: str,
    *,
    at: datetime,
    runner_private: Ed25519PrivateKey | None = None,
) -> dict[str, object]:
    runner_private = runner_private or Ed25519PrivateKey.generate()
    advisory_private = Ed25519PrivateKey.generate()
    image_private = Ed25519PrivateKey.generate()
    time_private = Ed25519PrivateKey.generate()
    storage_private = Ed25519PrivateKey.generate()
    consumer_store_id = _digest(10_000)
    challenge_values = {
        "challenge_id": "p19-test-run",
        "sequence": 1,
        "nonce_sha256": _digest(10_001),
        "subject_tree_sha256": tree_sha256,
        "consumer_store_id_sha256": consumer_store_id,
        "previous_evidence_head_sha256": "0" * 64,
        "issued_at": at - timedelta(hours=3),
        "not_before": at - timedelta(hours=2),
        "expires_at": at + timedelta(days=2),
    }
    challenge_provisional = VerifiedRunnerChallenge.model_construct(
        **challenge_values,
        schema_version="2.0",
        challenge_sha256="0" * 64,
    )
    challenge = VerifiedRunnerChallenge(
        **challenge_values,
        challenge_sha256=hash_verified_runner_challenge(
            challenge_provisional
        ),
    )
    image_values = {
        "runtime": VerifiedRunnerRuntime.READ_ONLY_MICROVM,
        "runtime_name": "p19-test-microvm",
        "runtime_version": "1.0.0",
        "platform": "linux/arm64",
        "subject_tree_sha256": tree_sha256,
        "image_manifest_sha256": _digest(10_002),
        "rootfs_sha256": _digest(10_003),
        "boot_measurement_sha256": _digest(10_004),
        "runner_binary_sha256": _digest(10_005),
        "parser_bundle_sha256": _digest(10_006),
        "dependency_lock_sha256": _digest(10_007),
        "seccomp_profile_sha256": _digest(10_008),
        "node_id_sha256": _digest(10_009),
        "built_at": at - timedelta(hours=4),
    }
    image_provisional = VerifiedRunnerImageIdentity.model_construct(
        **image_values,
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
    image = VerifiedRunnerImageIdentity(
        **image_values,
        identity_sha256=hash_verified_runner_image(image_provisional),
    )
    advisory = sign_advisory_snapshot(
        signing_key=advisory_private,
        issuer="p19-test-advisory",
        snapshot_id="p19-test-advisory",
        source_set_sha256=_digest(10_010),
        database_sha256=_digest(10_011),
        record_count=1_000,
        generated_at=at - timedelta(hours=5),
        not_after=at + timedelta(days=2),
    )
    records: list[VerifiedCheckRecord] = []
    empty_hash = hashlib.sha256(b"").hexdigest()
    for index, check in enumerate(REQUIRED_VERIFIED_RUNNER_CHECKS, 1):
        spec_values = {
            "check": check,
            "challenge_sha256": challenge.challenge_sha256,
            "subject_tree_sha256": tree_sha256,
            "image_identity_sha256": image.identity_sha256,
            "advisory_snapshot_sha256": advisory.snapshot_sha256,
            "node_id_sha256": image.node_id_sha256,
            "command_argv": ("p19-test", check.value),
            "environment_sha256": _digest(11_000 + index),
            "network_mode": (
                VerifiedRunnerNetworkMode.LOOPBACK_ONLY
                if check.value == "web_tests"
                else VerifiedRunnerNetworkMode.DISABLED
            ),
            "interpreter_sha256": _digest(12_000 + index),
            "import_closure_sha256": _digest(13_000 + index),
            "parser_name": f"p19-test-parser-{index}",
            "parser_version": "2.0.0",
            "parser_binary_sha256": _digest(14_000 + index),
            "tool_name": f"p19-test-tool-{index}",
            "tool_version": "1.0.0",
            "minimum_assertions": VERIFIED_RUNNER_MINIMUM_ASSERTIONS[check],
            "timeout_seconds": 600,
            "maximum_stdout_bytes": 1_048_576,
            "maximum_stderr_bytes": 1_048_576,
        }
        spec_provisional = VerifiedCheckSpec.model_construct(
            **spec_values,
            schema_version="2.0",
            working_directory="/workspace/repository",
            spec_sha256="0" * 64,
        )
        spec = VerifiedCheckSpec(
            **spec_values,
            spec_sha256=hash_verified_check_spec(spec_provisional),
        )
        started_at = at - timedelta(minutes=90) + timedelta(seconds=index * 2)
        ended_at = started_at + timedelta(seconds=1)
        uses_advisory = check.value == "dependency_audit"
        result_values = {
            "check": check,
            "challenge_sha256": challenge.challenge_sha256,
            "spec_sha256": spec.spec_sha256,
            "subject_tree_sha256": tree_sha256,
            "image_identity_sha256": image.identity_sha256,
            "advisory_snapshot_sha256": advisory.snapshot_sha256,
            "node_id_sha256": image.node_id_sha256,
            "started_at": started_at,
            "ended_at": ended_at,
            "not_after": at + timedelta(days=2),
            "duration_milliseconds": 1_000,
            "monotonic_duration_nanoseconds": 1_000_000_000,
            "termination_reason": VerifiedTerminationReason.EXITED,
            "exit_code": 0,
            "signal_number": None,
            "stdout_sha256": empty_hash,
            "stdout_bytes": 0,
            "stdout_truncated": False,
            "stderr_sha256": empty_hash,
            "stderr_bytes": 0,
            "stderr_truncated": False,
            "parser_name": spec.parser_name,
            "parser_version": spec.parser_version,
            "parser_binary_sha256": spec.parser_binary_sha256,
            "parser_output_sha256": _digest(15_000 + index),
            "parser_output_bytes": 512,
            "parser_output_complete": True,
            "advisory_database_sha256": (
                advisory.database_sha256 if uses_advisory else "0" * 64
            ),
            "advisory_file_identity_sha256": (
                _digest(16_000 + index) if uses_advisory else "0" * 64
            ),
            "advisory_bytes_read": 10_000 if uses_advisory else 0,
            "advisory_input_complete": uses_advisory,
            "tool_name": spec.tool_name,
            "tool_version": spec.tool_version,
            "assertions_executed": spec.minimum_assertions,
            "failures": 0,
            "skipped": 0,
        }
        result_provisional = VerifiedCheckResult.model_construct(
            **result_values,
            schema_version="2.0",
            result_sha256="0" * 64,
        )
        result = VerifiedCheckResult(
            **result_values,
            result_sha256=hash_verified_check_result(result_provisional),
        )
        records.append(VerifiedCheckRecord(spec=spec, result=result))
    record_tuple = tuple(records)
    trust = VerifiedRunnerTrustStore(
        runner=create_verification_key(
            runner_private.public_key(),
            issuer="p19-test-runner",
            role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        ),
        advisory_auditor=create_verification_key(
            advisory_private.public_key(),
            issuer="p19-test-advisory",
            role=SigningRole.SECURITY_AUDITOR,
        ),
        image_builder=create_verification_key(
            image_private.public_key(),
            issuer="p19-test-image",
            role=SigningRole.PROVIDER_CONFORMANCE,
        ),
        time_auditor=create_verification_key(
            time_private.public_key(),
            issuer="p19-test-time",
            role=SigningRole.TIME_AUDITOR,
        ),
        storage_auditor=create_verification_key(
            storage_private.public_key(),
            issuer="p19-test-storage",
            role=SigningRole.STORAGE_AUDITOR,
        ),
    )
    image_attestation = sign_runner_image_attestation(
        image=image,
        challenge=challenge,
        records=record_tuple,
        signing_key=image_private,
        issuer="p19-test-image",
        platform_quote_sha256=_digest(10_012),
        isolation_measurement_sha256=_digest(10_013),
        issued_at=at - timedelta(minutes=80),
        expires_at=at + timedelta(days=2),
    )
    clock = sign_verified_run_clock_attestation(
        challenge=challenge,
        records=record_tuple,
        node_id_sha256=image.node_id_sha256,
        signing_key=time_private,
        issuer="p19-test-time",
        observed_at=at - timedelta(minutes=79),
        issued_at=at - timedelta(minutes=78),
        expires_at=at + timedelta(days=2),
    )
    policy = VerifiedRunnerPolicy(
        policy_id="p19-test-policy",
        trust_store_sha256=hash_verified_runner_trust_store(trust),
        challenge_sha256=challenge.challenge_sha256,
        image_identity_sha256=image.identity_sha256,
        advisory_snapshot_sha256=advisory.snapshot_sha256,
        requirements=tuple(
            VerifiedRunnerRequirement(
                check=item.spec.check,
                spec_sha256=item.spec.spec_sha256,
                minimum_assertions=item.spec.minimum_assertions,
            )
            for item in record_tuple
        ),
        maximum_advisory_age_seconds=86_400,
        maximum_advisory_ttl_seconds=259_200,
        maximum_result_age_seconds=86_400,
        maximum_result_ttl_seconds=259_200,
        maximum_attestation_ttl_seconds=259_200,
        maximum_challenge_ttl_seconds=259_200,
        maximum_clock_attestation_ttl_seconds=259_200,
        maximum_clock_observation_lag_seconds=5,
        clock_response_timeout_seconds=5,
        maximum_image_attestation_ttl_seconds=259_200,
    )
    evidence_sha256 = hash_verified_runner_evidence_payload(
        subject_tree_sha256=tree_sha256,
        challenge=challenge,
        image=image,
        image_attestation=image_attestation,
        advisory_snapshot=advisory,
        records=record_tuple,
        clock_attestation=clock,
    )
    runner_attestation = sign_verified_runner_attestation(
        evidence_sha256=evidence_sha256,
        challenge_sha256=challenge.challenge_sha256,
        clock_attestation_sha256=clock.attestation_sha256,
        subject_tree_sha256=tree_sha256,
        image_identity_sha256=image.identity_sha256,
        advisory_snapshot_sha256=advisory.snapshot_sha256,
        policy=policy,
        trust_store=trust,
        signing_key=runner_private,
        issuer="p19-test-runner",
        issued_at=at - timedelta(minutes=77),
        expires_at=at + timedelta(days=2),
    )
    evidence = build_verified_runner_evidence_bundle(
        subject_tree_sha256=tree_sha256,
        challenge=challenge,
        image=image,
        image_attestation=image_attestation,
        advisory_snapshot=advisory,
        records=record_tuple,
        clock_attestation=clock,
        runner_attestation=runner_attestation,
    )
    pins = VerifiedRunnerAuthorityPins(
        expected_subject_tree_sha256=tree_sha256,
        expected_consumer_store_id_sha256=consumer_store_id,
        expected_challenge_sha256=challenge.challenge_sha256,
        expected_sequence=1,
        expected_previous_evidence_head_sha256="0" * 64,
        expected_policy_sha256=hash_verified_runner_policy(policy),
        expected_trust_store_sha256=hash_verified_runner_trust_store(trust),
        expected_image_identity_sha256=image.identity_sha256,
        expected_advisory_snapshot_sha256=advisory.snapshot_sha256,
    )
    authority_sha256 = hash_verified_runner_authority(policy, trust, pins)
    consumption_at = at - timedelta(minutes=70)
    clock_request_values = {
        "store_id_sha256": consumer_store_id,
        "expected_sequence": 1,
        "expected_previous_evidence_head_sha256": "0" * 64,
        "challenge_sha256": challenge.challenge_sha256,
        "evidence_bundle_sha256": evidence.bundle_sha256,
        "authority_sha256": authority_sha256,
        "request_nonce_sha256": _digest(17_000),
    }
    clock_request_provisional = VerifiedRunnerConsumerClockRequest.model_construct(
        **clock_request_values,
        schema_version="1.0",
        request_sha256="0" * 64,
    )
    clock_request = VerifiedRunnerConsumerClockRequest(
        **clock_request_values,
        request_sha256=hash_verified_runner_consumer_clock_request(
            clock_request_provisional
        ),
    )
    consumption_clock = sign_verified_runner_consumer_clock_attestation(
        clock_request,
        trust,
        time_private,
        observed_at=consumption_at,
        issued_at=consumption_at + timedelta(seconds=1),
        expires_at=at + timedelta(minutes=10),
    )
    consumption_receipt = sign_verified_runner_consumption_receipt(
        values={
            "store_id_sha256": consumer_store_id,
            "sequence": 1,
            "previous_evidence_head_sha256": "0" * 64,
            "evidence_head_sha256": evidence.bundle_sha256,
            "challenge_sha256": challenge.challenge_sha256,
            "evidence_bundle_sha256": evidence.bundle_sha256,
            "authority_sha256": authority_sha256,
            "clock_request": clock_request,
            "clock_attestation": consumption_clock,
            "clock_request_sha256": clock_request.request_sha256,
            "clock_attestation_sha256": consumption_clock.attestation_sha256,
            "consumed_at": consumption_at,
        },
        trust_store=trust,
        signing_key=storage_private,
    )

    def clock_attest(request):
        return sign_verified_runner_consumer_clock_attestation(
            request,
            trust,
            time_private,
            observed_at=at,
            issued_at=at + timedelta(seconds=1),
            expires_at=at + timedelta(minutes=10),
        )

    return {
        "evidence": evidence,
        "policy": policy,
        "trust_store": trust,
        "authority_pins": pins,
        "authority_sha256": authority_sha256,
        "consumer_store_id_sha256": consumer_store_id,
        "consumer_clock_attest": clock_attest,
        "consumption_signing_key": storage_private,
        "consumption_receipt": consumption_receipt,
    }
