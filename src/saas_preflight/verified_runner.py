"""Typed authority boundary for a future immutable P19 verification runner.

This module does not run containers, fetch advisories, hold production keys, or
grant publication authority.  It verifies externally produced, independently
pinned runner evidence.  P18 may consume this typed result only after this
verification succeeds.  The current host diagnostic runner cannot call this
boundary without a trusted image, signed advisory snapshot, runner signature,
and packet-external authority root.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import RLock, Thread
from typing import Any, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
)
from .models import Sha256, Slug, StrictModel
_ZERO_SHA256 = "0" * 64
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$"
_STORE_COORDINATION_TIMEOUT_SECONDS = 5
_STORE_LOCK_POLL_SECONDS = 0.01


def _bounded_store_callback(
    callback: Callable[..., Any],
    *args: Any,
    label: str,
) -> Any:
    output: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, callback(*args)), block=False)
        except BaseException as exc:
            try:
                output.put((False, exc), block=False)
            except BaseException:
                pass

    Thread(target=invoke, name=f"{label}-{os.urandom(6).hex()}", daemon=True).start()
    try:
        succeeded, value = output.get(timeout=_STORE_COORDINATION_TIMEOUT_SECONDS)
    except Empty as exc:
        raise VerifiedRunnerInputError(f"{label} timed out") from exc
    if not succeeded:
        raise VerifiedRunnerInputError(f"{label} failed") from (
            value if isinstance(value, BaseException) else None
        )
    return value


class VerifiedRunnerCheck(str, Enum):
    PYTHON_BASE = "python_base"
    PYTHON_TRACTION = "python_traction"
    PYTHON_PRODUCTION_CONSUMER = "python_production_consumer"
    SCHEMA_DETERMINISM = "schema_determinism"
    BLOCKED_FIXTURE_DETERMINISM = "blocked_fixture_determinism"
    UV_LOCK = "uv_lock"
    COMPILEALL = "compileall"
    SECRET_SCAN = "secret_scan"
    WEB_TESTS = "web_tests"
    WEB_LINT = "web_lint"
    DEPENDENCY_AUDIT = "dependency_audit"
    WORKFLOW_VERIFIER = "workflow_verifier"
    CONTRACT_STORAGE_AUDIT = "contract_storage_audit"
    TCO_QA_AUDIT = "tco_qa_audit"


REQUIRED_VERIFIED_RUNNER_CHECKS: tuple[VerifiedRunnerCheck, ...] = tuple(
    VerifiedRunnerCheck
)

VERIFIED_RUNNER_MINIMUM_ASSERTIONS = {
    VerifiedRunnerCheck.PYTHON_BASE: 524,
    VerifiedRunnerCheck.PYTHON_TRACTION: 57,
    VerifiedRunnerCheck.PYTHON_PRODUCTION_CONSUMER: 81,
    VerifiedRunnerCheck.SCHEMA_DETERMINISM: 197,
    VerifiedRunnerCheck.BLOCKED_FIXTURE_DETERMINISM: 8,
    VerifiedRunnerCheck.UV_LOCK: 1,
    VerifiedRunnerCheck.COMPILEALL: 1,
    VerifiedRunnerCheck.SECRET_SCAN: 1,
    VerifiedRunnerCheck.WEB_TESTS: 13,
    VerifiedRunnerCheck.WEB_LINT: 1,
    VerifiedRunnerCheck.DEPENDENCY_AUDIT: 1,
    VerifiedRunnerCheck.WORKFLOW_VERIFIER: 1,
    VerifiedRunnerCheck.CONTRACT_STORAGE_AUDIT: 28,
    VerifiedRunnerCheck.TCO_QA_AUDIT: 51,
}


class VerifiedRunnerNetworkMode(str, Enum):
    DISABLED = "disabled"
    LOOPBACK_ONLY = "loopback_only"
    NOT_APPLICABLE = "not_applicable"


class VerifiedRunnerInputError(ValueError):
    """Externally produced runner evidence is invalid or outside trusted pins."""


class VerifiedRunnerRuntime(str, Enum):
    READ_ONLY_OCI = "read_only_oci"
    READ_ONLY_MICROVM = "read_only_microvm"


class VerifiedTerminationReason(str, Enum):
    EXITED = "exited"
    SIGNALLED = "signalled"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    LAUNCH_ERROR = "launch_error"


class VerifiedRunnerChallenge(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    challenge_id: Slug
    sequence: int = Field(ge=1, le=1_000_000_000)
    nonce_sha256: Sha256
    subject_tree_sha256: Sha256
    consumer_store_id_sha256: Sha256
    previous_evidence_head_sha256: Sha256
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    challenge_sha256: Sha256

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "runner challenge timestamp")
        return value

    @model_validator(mode="after")
    def validate_challenge(self) -> Self:
        if not self.issued_at <= self.not_before < self.expires_at:
            raise ValueError("runner challenge timestamps are not ordered")
        if self.sequence == 1 and self.previous_evidence_head_sha256 != _ZERO_SHA256:
            raise ValueError("first runner challenge must use the zero predecessor")
        if self.sequence > 1 and self.previous_evidence_head_sha256 == _ZERO_SHA256:
            raise ValueError("later runner challenge must bind an evidence predecessor")
        if self.challenge_sha256 != hash_verified_runner_challenge(self):
            raise ValueError("runner challenge hash mismatch")
        return self


def _utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")


def _canonical_sha256(value: Any) -> str:
    if isinstance(value, StrictModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _domain_sha256(domain: str, value: Any) -> str:
    return _canonical_sha256(
        {"hash_domain": f"saas-preflight/p19/{domain}/v2", "payload": value}
    )


def _hash_without(domain: str, value: StrictModel, *fields: str) -> str:
    payload = value.model_dump(mode="json")
    for field in fields:
        payload.pop(field, None)
    return _domain_sha256(domain, payload)


def _signature(private_key: Ed25519PrivateKey, digest: str) -> str:
    return base64.urlsafe_b64encode(
        private_key.sign(bytes.fromhex(digest))
    ).decode("ascii").rstrip("=")


def _verify_signature(
    key: Ed25519VerificationKey, digest: str, signature_base64url: str
) -> bool:
    try:
        signature = base64.urlsafe_b64decode(signature_base64url + "==")
        key.public_key().verify(signature, bytes.fromhex(digest))
        return True
    except (InvalidSignature, TypeError, ValueError):
        return False


class VerifiedRunnerImageIdentity(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    runtime: VerifiedRunnerRuntime
    runtime_name: Slug
    runtime_version: str = Field(pattern=_SEMVER)
    platform: Literal["linux/amd64", "linux/arm64"]
    subject_tree_sha256: Sha256
    image_manifest_sha256: Sha256
    rootfs_sha256: Sha256
    boot_measurement_sha256: Sha256
    runner_binary_sha256: Sha256
    parser_bundle_sha256: Sha256
    dependency_lock_sha256: Sha256
    seccomp_profile_sha256: Sha256
    node_id_sha256: Sha256
    built_at: datetime
    rootfs_read_only: Literal[True] = True
    subject_embedded_read_only: Literal[True] = True
    host_mounts: tuple[()] = ()
    host_network: Literal[False] = False
    external_network: Literal[False] = False
    privileged: Literal[False] = False
    linux_capabilities: tuple[()] = ()
    identity_sha256: Sha256

    @field_validator("built_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "runner image build time")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.identity_sha256 != hash_verified_runner_image(self):
            raise ValueError("verified runner image identity hash mismatch")
        return self


class SignedRunnerImageAttestation(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    image_identity_sha256: Sha256
    subject_tree_sha256: Sha256
    challenge_sha256: Sha256
    challenge_nonce_sha256: Sha256
    record_set_sha256: Sha256
    platform_quote_sha256: Sha256
    isolation_measurement_sha256: Sha256
    signer_role: Literal[SigningRole.PROVIDER_CONFORMANCE] = (
        SigningRole.PROVIDER_CONFORMANCE
    )
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    attestation_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "image attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("image attestation expiry must follow issuance")
        if self.attestation_sha256 != hash_runner_image_attestation(self):
            raise ValueError("image attestation hash mismatch")
        return self


class SignedAdvisorySnapshot(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: Slug
    ecosystem: Literal["npm"] = "npm"
    source_set_sha256: Sha256
    database_sha256: Sha256
    record_count: int = Field(ge=1, le=1_000_000_000)
    generated_at: datetime
    not_after: datetime
    signer_role: Literal[SigningRole.SECURITY_AUDITOR] = (
        SigningRole.SECURITY_AUDITOR
    )
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    snapshot_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("generated_at", "not_after")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "advisory snapshot timestamp")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.not_after <= self.generated_at:
            raise ValueError("advisory snapshot expiry must follow generation")
        if self.snapshot_sha256 != hash_advisory_snapshot(self):
            raise ValueError("advisory snapshot hash mismatch")
        return self


class VerifiedCheckSpec(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    check: VerifiedRunnerCheck
    challenge_sha256: Sha256
    subject_tree_sha256: Sha256
    image_identity_sha256: Sha256
    advisory_snapshot_sha256: Sha256
    node_id_sha256: Sha256
    command_argv: tuple[str, ...] = Field(min_length=1, max_length=40)
    working_directory: Literal["/workspace/repository"] = "/workspace/repository"
    environment_sha256: Sha256
    network_mode: VerifiedRunnerNetworkMode
    interpreter_sha256: Sha256
    import_closure_sha256: Sha256
    parser_name: Slug
    parser_version: str = Field(pattern=_SEMVER)
    parser_binary_sha256: Sha256
    tool_name: Slug
    tool_version: str = Field(pattern=_SEMVER)
    minimum_assertions: int = Field(ge=1, le=100_000_000)
    timeout_seconds: int = Field(ge=1, le=3_600)
    maximum_stdout_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    maximum_stderr_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    spec_sha256: Sha256

    @model_validator(mode="after")
    def validate_spec(self) -> Self:
        if any(
            not item or "\x00" in item or len(item) > 1_024
            for item in self.command_argv
        ):
            raise ValueError("verified check argv contains an invalid argument")
        expected_network = (
            VerifiedRunnerNetworkMode.LOOPBACK_ONLY
            if self.check is VerifiedRunnerCheck.WEB_TESTS
            else VerifiedRunnerNetworkMode.DISABLED
        )
        if self.network_mode is not expected_network:
            raise ValueError("verified check has an invalid network mode")
        if (
            self.minimum_assertions
            != VERIFIED_RUNNER_MINIMUM_ASSERTIONS[self.check]
        ):
            raise ValueError("verified check assertion floor differs from code registry")
        if self.spec_sha256 != hash_verified_check_spec(self):
            raise ValueError("verified check spec hash mismatch")
        return self


class VerifiedCheckResult(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    check: VerifiedRunnerCheck
    challenge_sha256: Sha256
    spec_sha256: Sha256
    subject_tree_sha256: Sha256
    image_identity_sha256: Sha256
    advisory_snapshot_sha256: Sha256
    node_id_sha256: Sha256
    started_at: datetime
    ended_at: datetime
    not_after: datetime
    duration_milliseconds: int = Field(ge=0, le=3_600_000)
    monotonic_duration_nanoseconds: int = Field(ge=0, le=3_600_000_000_000)
    termination_reason: VerifiedTerminationReason
    exit_code: int | None = Field(default=None, ge=0, le=255)
    signal_number: int | None = Field(default=None, ge=1, le=64)
    stdout_sha256: Sha256
    stdout_bytes: int = Field(ge=0, le=64 * 1024 * 1024)
    stdout_truncated: bool
    stderr_sha256: Sha256
    stderr_bytes: int = Field(ge=0, le=64 * 1024 * 1024)
    stderr_truncated: bool
    parser_name: Slug
    parser_version: str = Field(pattern=_SEMVER)
    parser_binary_sha256: Sha256
    parser_output_sha256: Sha256
    parser_output_bytes: int = Field(ge=1, le=64 * 1024 * 1024)
    parser_output_complete: Literal[True] = True
    advisory_database_sha256: Sha256 = _ZERO_SHA256
    advisory_file_identity_sha256: Sha256 = _ZERO_SHA256
    advisory_bytes_read: int = Field(default=0, ge=0, le=4_000_000_000)
    advisory_input_complete: bool = False
    tool_name: Slug
    tool_version: str = Field(pattern=_SEMVER)
    assertions_executed: int = Field(ge=1, le=100_000_000)
    failures: int = Field(ge=0, le=100_000_000)
    skipped: int = Field(ge=0, le=100_000_000)
    result_sha256: Sha256

    @field_validator("started_at", "ended_at", "not_after")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "verified result timestamp")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if not self.started_at <= self.ended_at < self.not_after:
            raise ValueError("verified result timestamps are not ordered")
        expected_duration = int(
            (self.ended_at - self.started_at).total_seconds() * 1_000
        )
        if self.duration_milliseconds != expected_duration:
            raise ValueError("verified result wall duration mismatch")
        monotonic_milliseconds = self.monotonic_duration_nanoseconds // 1_000_000
        if abs(monotonic_milliseconds - self.duration_milliseconds) > 100:
            raise ValueError("verified result wall/monotonic duration mismatch")
        if (self.stdout_bytes == 0) != (self.stdout_sha256 == _EMPTY_SHA256):
            raise ValueError("empty stdout or stdout content hash is inconsistent")
        if (self.stderr_bytes == 0) != (self.stderr_sha256 == _EMPTY_SHA256):
            raise ValueError("empty stderr or stderr content hash is inconsistent")
        if self.parser_output_sha256 == _EMPTY_SHA256:
            raise ValueError("parser output must bind non-empty complete bytes")
        if self.failures + self.skipped > self.assertions_executed:
            raise ValueError("verified result counts are inconsistent")
        if self.termination_reason is VerifiedTerminationReason.EXITED:
            if self.exit_code is None or self.signal_number is not None:
                raise ValueError("exited result must bind only an exit code")
        elif self.termination_reason is VerifiedTerminationReason.SIGNALLED:
            if self.exit_code is not None or self.signal_number is None:
                raise ValueError("signalled result must bind only a signal")
        elif self.exit_code is not None or self.signal_number is not None:
            raise ValueError("non-process termination cannot bind exit or signal")
        if (
            (self.stdout_truncated or self.stderr_truncated)
            and self.termination_reason
            is not VerifiedTerminationReason.OUTPUT_LIMIT
        ):
            raise ValueError("truncation must be reported as an output limit")
        has_advisory_input = self.check is VerifiedRunnerCheck.DEPENDENCY_AUDIT
        if has_advisory_input:
            if (
                self.advisory_database_sha256 == _ZERO_SHA256
                or self.advisory_file_identity_sha256 == _ZERO_SHA256
                or self.advisory_bytes_read == 0
                or not self.advisory_input_complete
            ):
                raise ValueError("dependency audit must bind complete advisory bytes")
        elif (
            self.advisory_database_sha256 != _ZERO_SHA256
            or self.advisory_file_identity_sha256 != _ZERO_SHA256
            or self.advisory_bytes_read != 0
            or self.advisory_input_complete
        ):
            raise ValueError("non-advisory check cannot claim advisory input")
        if self.result_sha256 != hash_verified_check_result(self):
            raise ValueError("verified check result hash mismatch")
        return self


class VerifiedCheckRecord(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    spec: VerifiedCheckSpec
    result: VerifiedCheckResult

    @model_validator(mode="after")
    def bind_spec_and_result(self) -> Self:
        if (
            self.result.check is not self.spec.check
            or self.result.spec_sha256 != self.spec.spec_sha256
        ):
            raise ValueError("verified result does not bind its check spec")
        return self


class SignedVerifiedRunClockAttestation(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    challenge_sha256: Sha256
    record_set_sha256: Sha256
    node_id_sha256: Sha256
    observed_at: datetime
    signer_role: Literal[SigningRole.TIME_AUDITOR] = SigningRole.TIME_AUDITOR
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    attestation_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "verified run clock timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if not self.observed_at <= self.issued_at < self.expires_at:
            raise ValueError("verified run clock timestamps are not ordered")
        if self.attestation_sha256 != hash_verified_run_clock_attestation(self):
            raise ValueError("verified run clock attestation hash mismatch")
        return self


class VerifiedRunnerRequirement(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    check: VerifiedRunnerCheck
    spec_sha256: Sha256
    minimum_assertions: int = Field(ge=1, le=100_000_000)


class VerifiedRunnerTrustStore(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    runner: Ed25519VerificationKey
    advisory_auditor: Ed25519VerificationKey
    image_builder: Ed25519VerificationKey
    time_auditor: Ed25519VerificationKey
    storage_auditor: Ed25519VerificationKey

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        if (
            self.runner.role is not SigningRole.INTEGRATION_EVIDENCE_RUNNER
            or self.advisory_auditor.role is not SigningRole.SECURITY_AUDITOR
            or self.image_builder.role is not SigningRole.PROVIDER_CONFORMANCE
            or self.time_auditor.role is not SigningRole.TIME_AUDITOR
            or self.storage_auditor.role is not SigningRole.STORAGE_AUDITOR
        ):
            raise ValueError("verified runner trust-store role mismatch")
        keys = (
            self.runner,
            self.advisory_auditor,
            self.image_builder,
            self.time_auditor,
            self.storage_auditor,
        )
        if len({item.key_id_sha256 for item in keys}) != len(keys):
            raise ValueError("verified runner role keys must be distinct")
        return self


class VerifiedRunnerPolicy(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    policy_id: Slug
    trust_store_sha256: Sha256
    challenge_sha256: Sha256
    image_identity_sha256: Sha256
    advisory_snapshot_sha256: Sha256
    requirements: tuple[VerifiedRunnerRequirement, ...] = Field(
        min_length=14, max_length=14
    )
    maximum_advisory_age_seconds: int = Field(ge=1, le=2_592_000)
    maximum_advisory_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_result_age_seconds: int = Field(ge=1, le=2_592_000)
    maximum_result_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_attestation_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_challenge_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_clock_attestation_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_clock_observation_lag_seconds: int = Field(ge=0, le=300)
    clock_response_timeout_seconds: int = Field(ge=1, le=60)
    maximum_image_attestation_ttl_seconds: int = Field(ge=1, le=2_592_000)

    @model_validator(mode="after")
    def validate_requirements(self) -> Self:
        if tuple(item.check for item in self.requirements) != (
            REQUIRED_VERIFIED_RUNNER_CHECKS
        ):
            raise ValueError("runner policy must contain the exact ordered checks")
        if tuple(item.minimum_assertions for item in self.requirements) != tuple(
            VERIFIED_RUNNER_MINIMUM_ASSERTIONS[check]
            for check in REQUIRED_VERIFIED_RUNNER_CHECKS
        ):
            raise ValueError("runner policy assertion floors differ from code registry")
        if len({item.spec_sha256 for item in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("runner policy spec hashes must be distinct")
        return self


class VerifiedRunnerAuthorityPins(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    expected_subject_tree_sha256: Sha256
    expected_consumer_store_id_sha256: Sha256
    expected_challenge_sha256: Sha256
    expected_sequence: int = Field(ge=1, le=1_000_000_000)
    expected_previous_evidence_head_sha256: Sha256
    expected_policy_sha256: Sha256
    expected_trust_store_sha256: Sha256
    expected_image_identity_sha256: Sha256
    expected_advisory_snapshot_sha256: Sha256


class VerifiedRunnerAttestation(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    evidence_sha256: Sha256
    challenge_sha256: Sha256
    clock_attestation_sha256: Sha256
    subject_tree_sha256: Sha256
    image_identity_sha256: Sha256
    advisory_snapshot_sha256: Sha256
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    signer_role: Literal[SigningRole.INTEGRATION_EVIDENCE_RUNNER] = (
        SigningRole.INTEGRATION_EVIDENCE_RUNNER
    )
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    attestation_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "runner attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("runner attestation expiry must follow issuance")
        if self.attestation_sha256 != hash_verified_runner_attestation(self):
            raise ValueError("runner attestation hash mismatch")
        return self


class VerifiedRunnerEvidenceBundle(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    subject_tree_sha256: Sha256
    challenge: VerifiedRunnerChallenge
    image: VerifiedRunnerImageIdentity
    image_attestation: SignedRunnerImageAttestation
    advisory_snapshot: SignedAdvisorySnapshot
    records: tuple[VerifiedCheckRecord, ...] = Field(min_length=14, max_length=14)
    clock_attestation: SignedVerifiedRunClockAttestation
    evidence_sha256: Sha256
    runner_attestation: VerifiedRunnerAttestation
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if tuple(item.spec.check for item in self.records) != (
            REQUIRED_VERIFIED_RUNNER_CHECKS
        ):
            raise ValueError("runner evidence must contain the exact ordered checks")
        if (
            self.challenge.subject_tree_sha256 != self.subject_tree_sha256
            or self.image_attestation.image_identity_sha256
            != self.image.identity_sha256
            or self.image_attestation.subject_tree_sha256
            != self.subject_tree_sha256
            or self.image_attestation.challenge_sha256
            != self.challenge.challenge_sha256
            or self.image_attestation.challenge_nonce_sha256
            != self.challenge.nonce_sha256
            or self.image_attestation.record_set_sha256
            != hash_verified_record_set(self.records)
        ):
            raise ValueError("runner challenge/image attestation binding mismatch")
        if self.image.subject_tree_sha256 != self.subject_tree_sha256:
            raise ValueError("runner image does not embed the evidence tree")
        for record in self.records:
            if (
                record.spec.subject_tree_sha256 != self.subject_tree_sha256
                or record.result.subject_tree_sha256 != self.subject_tree_sha256
                or record.spec.image_identity_sha256 != self.image.identity_sha256
                or record.result.image_identity_sha256
                != self.image.identity_sha256
                or record.spec.advisory_snapshot_sha256
                != self.advisory_snapshot.snapshot_sha256
                or record.result.advisory_snapshot_sha256
                != self.advisory_snapshot.snapshot_sha256
                or record.spec.node_id_sha256 != self.image.node_id_sha256
                or record.result.node_id_sha256 != self.image.node_id_sha256
                or record.spec.challenge_sha256
                != self.challenge.challenge_sha256
                or record.result.challenge_sha256
                != self.challenge.challenge_sha256
            ):
                raise ValueError("runner evidence record binding mismatch")
        record_set_sha256 = hash_verified_record_set(self.records)
        if (
            self.clock_attestation.challenge_sha256
            != self.challenge.challenge_sha256
            or self.clock_attestation.record_set_sha256 != record_set_sha256
            or self.clock_attestation.node_id_sha256 != self.image.node_id_sha256
        ):
            raise ValueError("runner clock attestation binding mismatch")
        if self.evidence_sha256 != hash_verified_runner_evidence_content(self):
            raise ValueError("runner evidence content hash mismatch")
        if (
            self.runner_attestation.evidence_sha256 != self.evidence_sha256
            or self.runner_attestation.challenge_sha256
            != self.challenge.challenge_sha256
            or self.runner_attestation.clock_attestation_sha256
            != self.clock_attestation.attestation_sha256
            or self.runner_attestation.subject_tree_sha256
            != self.subject_tree_sha256
            or self.runner_attestation.image_identity_sha256
            != self.image.identity_sha256
            or self.runner_attestation.advisory_snapshot_sha256
            != self.advisory_snapshot.snapshot_sha256
        ):
            raise ValueError("runner attestation does not bind the evidence")
        if self.bundle_sha256 != hash_verified_runner_bundle(self):
            raise ValueError("runner evidence bundle hash mismatch")
        return self


def hash_verified_runner_challenge(value: VerifiedRunnerChallenge) -> str:
    return _hash_without("runner-challenge", value, "challenge_sha256")


def hash_verified_runner_image(value: VerifiedRunnerImageIdentity) -> str:
    return _hash_without("runner-image", value, "identity_sha256")


def hash_runner_image_attestation(value: SignedRunnerImageAttestation) -> str:
    return _hash_without(
        "runner-image-attestation",
        value,
        "attestation_sha256",
        "signature_base64url",
    )


def hash_advisory_snapshot(value: SignedAdvisorySnapshot) -> str:
    return _hash_without(
        "advisory-snapshot", value, "snapshot_sha256", "signature_base64url"
    )


def hash_verified_check_spec(value: VerifiedCheckSpec) -> str:
    return _hash_without("check-spec", value, "spec_sha256")


def hash_verified_check_result(value: VerifiedCheckResult) -> str:
    return _hash_without("check-result", value, "result_sha256")


def hash_verified_record_set(
    records: tuple[VerifiedCheckRecord, ...],
) -> str:
    return _domain_sha256(
        "record-set",
        tuple(
            {
                "spec_sha256": item.spec.spec_sha256,
                "result_sha256": item.result.result_sha256,
            }
            for item in records
        )
    )


def hash_verified_run_clock_attestation(
    value: SignedVerifiedRunClockAttestation,
) -> str:
    return _hash_without(
        "clock-attestation", value, "attestation_sha256", "signature_base64url"
    )


def hash_verified_runner_trust_store(value: VerifiedRunnerTrustStore) -> str:
    return _domain_sha256("trust-store", value.model_dump(mode="json"))


def hash_verified_runner_policy(value: VerifiedRunnerPolicy) -> str:
    return _domain_sha256("policy", value.model_dump(mode="json"))


def hash_verified_runner_authority(
    policy: VerifiedRunnerPolicy,
    trust_store: VerifiedRunnerTrustStore,
    pins: VerifiedRunnerAuthorityPins,
) -> str:
    return _domain_sha256(
        "authority",
        {
            "schema_version": "2.0",
            "policy_sha256": hash_verified_runner_policy(policy),
            "trust_store_sha256": hash_verified_runner_trust_store(trust_store),
            "pins": pins.model_dump(mode="json"),
        }
    )


def hash_verified_runner_attestation(value: VerifiedRunnerAttestation) -> str:
    return _hash_without(
        "runner-attestation", value, "attestation_sha256", "signature_base64url"
    )


def hash_verified_runner_evidence_content(
    value: VerifiedRunnerEvidenceBundle,
) -> str:
    return hash_verified_runner_evidence_payload(
        subject_tree_sha256=value.subject_tree_sha256,
        challenge=value.challenge,
        image=value.image,
        image_attestation=value.image_attestation,
        advisory_snapshot=value.advisory_snapshot,
        records=value.records,
        clock_attestation=value.clock_attestation,
    )


def hash_verified_runner_evidence_payload(
    *,
    subject_tree_sha256: str,
    challenge: VerifiedRunnerChallenge,
    image: VerifiedRunnerImageIdentity,
    image_attestation: SignedRunnerImageAttestation,
    advisory_snapshot: SignedAdvisorySnapshot,
    records: tuple[VerifiedCheckRecord, ...],
    clock_attestation: SignedVerifiedRunClockAttestation,
) -> str:
    return _domain_sha256(
        "evidence-content",
        {
            "schema_version": "2.0",
            "subject_tree_sha256": subject_tree_sha256,
            "challenge": challenge.model_dump(mode="json"),
            "image": image.model_dump(mode="json"),
            "image_attestation": image_attestation.model_dump(mode="json"),
            "advisory_snapshot": advisory_snapshot.model_dump(mode="json"),
            "records": tuple(
                item.model_dump(mode="json") for item in records
            ),
            "clock_attestation": clock_attestation.model_dump(mode="json"),
        }
    )


def hash_verified_runner_bundle(value: VerifiedRunnerEvidenceBundle) -> str:
    return _hash_without("evidence-bundle", value, "bundle_sha256")


def hash_verified_check_output(value: VerifiedCheckResult) -> str:
    return _domain_sha256(
        "check-output",
        {
            "stdout_sha256": value.stdout_sha256,
            "stdout_bytes": value.stdout_bytes,
            "stderr_sha256": value.stderr_sha256,
            "stderr_bytes": value.stderr_bytes,
            "parser_output_sha256": value.parser_output_sha256,
            "result_sha256": value.result_sha256,
        }
    )


def sign_advisory_snapshot(
    *,
    signing_key: Ed25519PrivateKey,
    issuer: str,
    snapshot_id: str,
    source_set_sha256: str,
    database_sha256: str,
    record_count: int,
    generated_at: datetime,
    not_after: datetime,
) -> SignedAdvisorySnapshot:
    key = create_verification_key(
        signing_key.public_key(), issuer=issuer, role=SigningRole.SECURITY_AUDITOR
    )
    values: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "source_set_sha256": source_set_sha256,
        "database_sha256": database_sha256,
        "record_count": record_count,
        "generated_at": generated_at,
        "not_after": not_after,
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
    }
    provisional = SignedAdvisorySnapshot.model_construct(
        **values,
        schema_version="2.0",
        ecosystem="npm",
        signer_role=SigningRole.SECURITY_AUDITOR,
        snapshot_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_advisory_snapshot(provisional)
    return SignedAdvisorySnapshot(
        **values,
        snapshot_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def sign_runner_image_attestation(
    *,
    image: VerifiedRunnerImageIdentity,
    challenge: VerifiedRunnerChallenge,
    records: tuple[VerifiedCheckRecord, ...],
    signing_key: Ed25519PrivateKey,
    issuer: str,
    platform_quote_sha256: str,
    isolation_measurement_sha256: str,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedRunnerImageAttestation:
    key = create_verification_key(
        signing_key.public_key(),
        issuer=issuer,
        role=SigningRole.PROVIDER_CONFORMANCE,
    )
    values: dict[str, Any] = {
        "image_identity_sha256": image.identity_sha256,
        "subject_tree_sha256": image.subject_tree_sha256,
        "challenge_sha256": challenge.challenge_sha256,
        "challenge_nonce_sha256": challenge.nonce_sha256,
        "record_set_sha256": hash_verified_record_set(records),
        "platform_quote_sha256": platform_quote_sha256,
        "isolation_measurement_sha256": isolation_measurement_sha256,
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    provisional = SignedRunnerImageAttestation.model_construct(
        **values,
        schema_version="2.0",
        signer_role=SigningRole.PROVIDER_CONFORMANCE,
        attestation_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_runner_image_attestation(provisional)
    return SignedRunnerImageAttestation(
        **values,
        attestation_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def sign_verified_run_clock_attestation(
    *,
    challenge: VerifiedRunnerChallenge,
    records: tuple[VerifiedCheckRecord, ...],
    node_id_sha256: str,
    signing_key: Ed25519PrivateKey,
    issuer: str,
    observed_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedVerifiedRunClockAttestation:
    key = create_verification_key(
        signing_key.public_key(), issuer=issuer, role=SigningRole.TIME_AUDITOR
    )
    values: dict[str, Any] = {
        "challenge_sha256": challenge.challenge_sha256,
        "record_set_sha256": hash_verified_record_set(records),
        "node_id_sha256": node_id_sha256,
        "observed_at": observed_at,
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    provisional = SignedVerifiedRunClockAttestation.model_construct(
        **values,
        schema_version="2.0",
        signer_role=SigningRole.TIME_AUDITOR,
        attestation_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_verified_run_clock_attestation(provisional)
    return SignedVerifiedRunClockAttestation(
        **values,
        attestation_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def sign_verified_runner_attestation(
    *,
    evidence_sha256: str,
    challenge_sha256: str,
    clock_attestation_sha256: str,
    subject_tree_sha256: str,
    image_identity_sha256: str,
    advisory_snapshot_sha256: str,
    policy: VerifiedRunnerPolicy,
    trust_store: VerifiedRunnerTrustStore,
    signing_key: Ed25519PrivateKey,
    issuer: str,
    issued_at: datetime,
    expires_at: datetime,
) -> VerifiedRunnerAttestation:
    key = create_verification_key(
        signing_key.public_key(),
        issuer=issuer,
        role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
    )
    if key != trust_store.runner:
        raise VerifiedRunnerInputError("runner signing key does not match trust store")
    values: dict[str, Any] = {
        "evidence_sha256": evidence_sha256,
        "challenge_sha256": challenge_sha256,
        "clock_attestation_sha256": clock_attestation_sha256,
        "subject_tree_sha256": subject_tree_sha256,
        "image_identity_sha256": image_identity_sha256,
        "advisory_snapshot_sha256": advisory_snapshot_sha256,
        "policy_sha256": hash_verified_runner_policy(policy),
        "trust_store_sha256": hash_verified_runner_trust_store(trust_store),
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    provisional = VerifiedRunnerAttestation.model_construct(
        **values,
        schema_version="2.0",
        signer_role=SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        attestation_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_verified_runner_attestation(provisional)
    return VerifiedRunnerAttestation(
        **values,
        attestation_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def build_verified_runner_evidence_bundle(
    *,
    subject_tree_sha256: str,
    challenge: VerifiedRunnerChallenge,
    image: VerifiedRunnerImageIdentity,
    image_attestation: SignedRunnerImageAttestation,
    advisory_snapshot: SignedAdvisorySnapshot,
    records: tuple[VerifiedCheckRecord, ...],
    clock_attestation: SignedVerifiedRunClockAttestation,
    runner_attestation: VerifiedRunnerAttestation,
) -> VerifiedRunnerEvidenceBundle:
    evidence_sha256 = hash_verified_runner_evidence_payload(
        subject_tree_sha256=subject_tree_sha256,
        challenge=challenge,
        image=image,
        image_attestation=image_attestation,
        advisory_snapshot=advisory_snapshot,
        records=records,
        clock_attestation=clock_attestation,
    )
    values: dict[str, Any] = {
        "subject_tree_sha256": subject_tree_sha256,
        "challenge": challenge,
        "image": image,
        "image_attestation": image_attestation,
        "advisory_snapshot": advisory_snapshot,
        "records": records,
        "clock_attestation": clock_attestation,
        "evidence_sha256": evidence_sha256,
        "runner_attestation": runner_attestation,
    }
    provisional = VerifiedRunnerEvidenceBundle.model_construct(
        **values,
        schema_version="2.0",
        bundle_sha256=_ZERO_SHA256,
    )
    return VerifiedRunnerEvidenceBundle(
        **values,
        bundle_sha256=hash_verified_runner_bundle(provisional),
    )


def verify_verified_runner_evidence(
    evidence: VerifiedRunnerEvidenceBundle,
    *,
    policy: VerifiedRunnerPolicy,
    trust_store: VerifiedRunnerTrustStore,
    authority_pins: VerifiedRunnerAuthorityPins,
    expected_authority_sha256: str,
    at: datetime,
) -> VerifiedRunnerEvidenceBundle:
    """Verify immutable external runner evidence against packet-external pins."""

    try:
        _utc(at, "verified runner evaluation time")
        evidence = VerifiedRunnerEvidenceBundle.model_validate(
            evidence.model_dump()
        )
        policy = VerifiedRunnerPolicy.model_validate(policy.model_dump())
        trust_store = VerifiedRunnerTrustStore.model_validate(
            trust_store.model_dump()
        )
        pins = VerifiedRunnerAuthorityPins.model_validate(
            authority_pins.model_dump()
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise VerifiedRunnerInputError("invalid verified runner input") from exc

    policy_hash = hash_verified_runner_policy(policy)
    trust_hash = hash_verified_runner_trust_store(trust_store)
    authority_hash = hash_verified_runner_authority(policy, trust_store, pins)
    if not expected_authority_sha256 or expected_authority_sha256 != authority_hash:
        raise VerifiedRunnerInputError("verified runner authority root mismatch")
    if (
        pins.expected_subject_tree_sha256 != evidence.subject_tree_sha256
        or pins.expected_consumer_store_id_sha256
        != evidence.challenge.consumer_store_id_sha256
        or pins.expected_challenge_sha256
        != evidence.challenge.challenge_sha256
        or pins.expected_sequence != evidence.challenge.sequence
        or pins.expected_previous_evidence_head_sha256
        != evidence.challenge.previous_evidence_head_sha256
        or pins.expected_policy_sha256 != policy_hash
        or pins.expected_trust_store_sha256 != trust_hash
        or pins.expected_image_identity_sha256 != evidence.image.identity_sha256
        or pins.expected_advisory_snapshot_sha256
        != evidence.advisory_snapshot.snapshot_sha256
        or policy.trust_store_sha256 != trust_hash
        or policy.challenge_sha256 != evidence.challenge.challenge_sha256
        or policy.image_identity_sha256 != evidence.image.identity_sha256
        or policy.advisory_snapshot_sha256
        != evidence.advisory_snapshot.snapshot_sha256
    ):
        raise VerifiedRunnerInputError("verified runner pins do not bind evidence")

    challenge = evidence.challenge
    if (
        not challenge.not_before <= at < challenge.expires_at
        or challenge.expires_at - challenge.issued_at
        > timedelta(seconds=policy.maximum_challenge_ttl_seconds)
    ):
        raise VerifiedRunnerInputError("verified runner challenge is not current")

    image_attestation = evidence.image_attestation
    if (
        image_attestation.signer_issuer != trust_store.image_builder.issuer
        or image_attestation.signer_key_id_sha256
        != trust_store.image_builder.key_id_sha256
        or not _verify_signature(
            trust_store.image_builder,
            image_attestation.attestation_sha256,
            image_attestation.signature_base64url,
        )
        or not challenge.not_before
        <= image_attestation.issued_at
        <= at
        < image_attestation.expires_at
        or image_attestation.expires_at - image_attestation.issued_at
        > timedelta(seconds=policy.maximum_image_attestation_ttl_seconds)
    ):
        raise VerifiedRunnerInputError("runner image attestation is not authoritative")

    advisory = evidence.advisory_snapshot
    if (
        advisory.signer_issuer != trust_store.advisory_auditor.issuer
        or advisory.signer_key_id_sha256
        != trust_store.advisory_auditor.key_id_sha256
        or not _verify_signature(
            trust_store.advisory_auditor,
            advisory.snapshot_sha256,
            advisory.signature_base64url,
        )
        or not advisory.generated_at <= at < advisory.not_after
        or at - advisory.generated_at
        > timedelta(seconds=policy.maximum_advisory_age_seconds)
        or advisory.not_after - advisory.generated_at
        > timedelta(seconds=policy.maximum_advisory_ttl_seconds)
    ):
        raise VerifiedRunnerInputError("signed advisory snapshot is not current")

    attestation = evidence.runner_attestation
    clock_attestation = evidence.clock_attestation
    if (
        clock_attestation.signer_issuer != trust_store.time_auditor.issuer
        or clock_attestation.signer_key_id_sha256
        != trust_store.time_auditor.key_id_sha256
        or not _verify_signature(
            trust_store.time_auditor,
            clock_attestation.attestation_sha256,
            clock_attestation.signature_base64url,
        )
        or not clock_attestation.issued_at <= at < clock_attestation.expires_at
        or clock_attestation.expires_at - clock_attestation.issued_at
        > timedelta(seconds=policy.maximum_clock_attestation_ttl_seconds)
    ):
        raise VerifiedRunnerInputError("verified run clock is not authoritative")
    if (
        attestation.policy_sha256 != policy_hash
        or attestation.trust_store_sha256 != trust_hash
        or attestation.signer_issuer != trust_store.runner.issuer
        or attestation.signer_key_id_sha256 != trust_store.runner.key_id_sha256
        or not _verify_signature(
            trust_store.runner,
            attestation.attestation_sha256,
            attestation.signature_base64url,
        )
        or not attestation.issued_at <= at < attestation.expires_at
        or attestation.expires_at - attestation.issued_at
        > timedelta(seconds=policy.maximum_attestation_ttl_seconds)
    ):
        raise VerifiedRunnerInputError("runner attestation is not authoritative")
    latest_end = max(item.result.ended_at for item in evidence.records)
    earliest_start = min(item.result.started_at for item in evidence.records)
    if (
        earliest_start < challenge.not_before
        or latest_end > image_attestation.issued_at
        or image_attestation.issued_at > clock_attestation.observed_at
        or clock_attestation.observed_at > clock_attestation.issued_at
        or attestation.issued_at < clock_attestation.issued_at
    ):
        raise VerifiedRunnerInputError("runner attestation predates check completion")

    for record, requirement in zip(
        evidence.records, policy.requirements, strict=True
    ):
        spec = record.spec
        result = record.result
        if (
            requirement.check is not spec.check
            or requirement.spec_sha256 != spec.spec_sha256
            or requirement.minimum_assertions != spec.minimum_assertions
            or result.parser_name != spec.parser_name
            or result.parser_version != spec.parser_version
            or result.parser_binary_sha256 != spec.parser_binary_sha256
            or result.tool_name != spec.tool_name
            or result.tool_version != spec.tool_version
            or result.started_at < evidence.image.built_at
            or result.ended_at > attestation.issued_at
            or at - result.ended_at
            > timedelta(seconds=policy.maximum_result_age_seconds)
            or result.not_after - result.ended_at
            > timedelta(seconds=policy.maximum_result_ttl_seconds)
            or result.not_after <= at
            or result.duration_milliseconds > spec.timeout_seconds * 1_000
            or result.monotonic_duration_nanoseconds
            > spec.timeout_seconds * 1_000_000_000
            or result.stdout_bytes > spec.maximum_stdout_bytes
            or result.stderr_bytes > spec.maximum_stderr_bytes
            or result.stdout_truncated
            or result.stderr_truncated
            or (
                spec.check is VerifiedRunnerCheck.DEPENDENCY_AUDIT
                and result.advisory_database_sha256
                != advisory.database_sha256
            )
            or result.termination_reason is not VerifiedTerminationReason.EXITED
            or result.exit_code != 0
            or result.failures != 0
            or result.skipped != 0
            or result.assertions_executed < requirement.minimum_assertions
        ):
            raise VerifiedRunnerInputError(
                f"verified check failed: {spec.check.value}"
            )
    return evidence


class VerifiedRunnerConsumerClockRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    store_id_sha256: Sha256
    expected_sequence: int = Field(ge=1, le=1_000_000_000)
    expected_previous_evidence_head_sha256: Sha256
    challenge_sha256: Sha256
    evidence_bundle_sha256: Sha256
    authority_sha256: Sha256
    request_nonce_sha256: Sha256
    request_sha256: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.request_sha256 != hash_verified_runner_consumer_clock_request(self):
            raise ValueError("runner consumer clock request hash mismatch")
        return self


class SignedVerifiedRunnerConsumerClockAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_sha256: Sha256
    store_id_sha256: Sha256
    observed_sequence: int = Field(ge=0, le=1_000_000_000)
    observed_evidence_head_sha256: Sha256
    observed_at: datetime
    issued_at: datetime
    expires_at: datetime
    signer_role: Literal[SigningRole.TIME_AUDITOR] = SigningRole.TIME_AUDITOR
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    attestation_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "runner consumer clock timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if not self.observed_at <= self.issued_at < self.expires_at:
            raise ValueError("runner consumer clock timestamps are not ordered")
        if self.attestation_sha256 != hash_verified_runner_consumer_clock_attestation(
            self
        ):
            raise ValueError("runner consumer clock attestation hash mismatch")
        return self


class VerifiedRunnerConsumptionReceipt(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    store_id_sha256: Sha256
    sequence: int = Field(ge=1, le=1_000_000_000)
    previous_evidence_head_sha256: Sha256
    evidence_head_sha256: Sha256
    challenge_sha256: Sha256
    evidence_bundle_sha256: Sha256
    authority_sha256: Sha256
    clock_request: VerifiedRunnerConsumerClockRequest
    clock_attestation: SignedVerifiedRunnerConsumerClockAttestation
    clock_request_sha256: Sha256
    clock_attestation_sha256: Sha256
    consumed_at: datetime
    signer_role: Literal[SigningRole.STORAGE_AUDITOR] = SigningRole.STORAGE_AUDITOR
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    receipt_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("consumed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _utc(value, "runner consumption timestamp")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.evidence_head_sha256 != self.evidence_bundle_sha256:
            raise ValueError("runner evidence head must equal the consumed bundle hash")
        if (
            self.clock_request_sha256 != self.clock_request.request_sha256
            or self.clock_attestation_sha256
            != self.clock_attestation.attestation_sha256
            or self.clock_request.store_id_sha256 != self.store_id_sha256
            or self.clock_request.expected_sequence != self.sequence
            or self.clock_request.expected_previous_evidence_head_sha256
            != self.previous_evidence_head_sha256
            or self.clock_request.challenge_sha256 != self.challenge_sha256
            or self.clock_request.evidence_bundle_sha256
            != self.evidence_bundle_sha256
            or self.clock_request.authority_sha256 != self.authority_sha256
            or self.clock_attestation.request_sha256
            != self.clock_request.request_sha256
            or self.clock_attestation.store_id_sha256 != self.store_id_sha256
            or self.clock_attestation.observed_sequence != self.sequence - 1
            or self.clock_attestation.observed_evidence_head_sha256
            != self.previous_evidence_head_sha256
            or self.clock_attestation.observed_at != self.consumed_at
        ):
            raise ValueError("runner consumption clock artifacts are not bound")
        expected = hash_verified_runner_consumption_receipt(self)
        if self.receipt_sha256 != expected:
            raise ValueError(
                "runner consumption receipt hash mismatch: "
                f"expected {expected}"
            )
        return self


def hash_verified_runner_consumer_clock_request(
    value: VerifiedRunnerConsumerClockRequest,
) -> str:
    return _hash_without("consumer-clock-request", value, "request_sha256")


def hash_verified_runner_consumer_clock_attestation(
    value: SignedVerifiedRunnerConsumerClockAttestation,
) -> str:
    return _hash_without(
        "consumer-clock-attestation",
        value,
        "attestation_sha256",
        "signature_base64url",
    )


def hash_verified_runner_consumption_receipt(
    value: VerifiedRunnerConsumptionReceipt,
) -> str:
    return _domain_sha256(
        "consumption-receipt",
        {
            "schema_version": value.schema_version,
            "store_id_sha256": value.store_id_sha256,
            "sequence": value.sequence,
            "previous_evidence_head_sha256": (
                value.previous_evidence_head_sha256
            ),
            "evidence_head_sha256": value.evidence_head_sha256,
            "challenge_sha256": value.challenge_sha256,
            "evidence_bundle_sha256": value.evidence_bundle_sha256,
            "authority_sha256": value.authority_sha256,
            "clock_request": value.clock_request.model_dump(mode="json"),
            "clock_attestation": value.clock_attestation.model_dump(mode="json"),
            "clock_request_sha256": value.clock_request_sha256,
            "clock_attestation_sha256": value.clock_attestation_sha256,
            "consumed_at": value.consumed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "signer_role": value.signer_role.value,
            "signer_issuer": value.signer_issuer,
            "signer_key_id_sha256": value.signer_key_id_sha256,
        },
    )


def sign_verified_runner_consumer_clock_attestation(
    request: VerifiedRunnerConsumerClockRequest,
    trust_store: VerifiedRunnerTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    observed_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedVerifiedRunnerConsumerClockAttestation:
    selected = VerifiedRunnerConsumerClockRequest.model_validate(
        request.model_dump()
    )
    trust = VerifiedRunnerTrustStore.model_validate(trust_store.model_dump())
    key = create_verification_key(
        signing_key.public_key(),
        issuer=trust.time_auditor.issuer,
        role=SigningRole.TIME_AUDITOR,
    )
    if key != trust.time_auditor:
        raise VerifiedRunnerInputError("runner consumer clock key mismatch")
    values: dict[str, Any] = {
        "request_sha256": selected.request_sha256,
        "store_id_sha256": selected.store_id_sha256,
        "observed_sequence": selected.expected_sequence - 1,
        "observed_evidence_head_sha256": (
            selected.expected_previous_evidence_head_sha256
        ),
        "observed_at": observed_at,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
    }
    provisional = SignedVerifiedRunnerConsumerClockAttestation.model_construct(
        **values,
        schema_version="1.0",
        signer_role=SigningRole.TIME_AUDITOR,
        attestation_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_verified_runner_consumer_clock_attestation(provisional)
    return SignedVerifiedRunnerConsumerClockAttestation(
        **values,
        attestation_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def sign_verified_runner_consumption_receipt(
    *,
    values: dict[str, Any],
    trust_store: VerifiedRunnerTrustStore,
    signing_key: Ed25519PrivateKey,
) -> VerifiedRunnerConsumptionReceipt:
    """Sign the durable one-shot consumption result with the storage role."""

    trust = VerifiedRunnerTrustStore.model_validate(trust_store.model_dump())
    key = create_verification_key(
        signing_key.public_key(),
        issuer=trust.storage_auditor.issuer,
        role=SigningRole.STORAGE_AUDITOR,
    )
    if key != trust.storage_auditor:
        raise VerifiedRunnerInputError("runner consumption signing key mismatch")
    signed_values = {
        **values,
        "signer_issuer": key.issuer,
        "signer_key_id_sha256": key.key_id_sha256,
    }
    provisional = VerifiedRunnerConsumptionReceipt.model_construct(
        **signed_values,
        schema_version="2.0",
        signer_role=SigningRole.STORAGE_AUDITOR,
        receipt_sha256=_ZERO_SHA256,
        signature_base64url="A" * 86,
    )
    digest = hash_verified_runner_consumption_receipt(provisional)
    return VerifiedRunnerConsumptionReceipt(
        **signed_values,
        receipt_sha256=digest,
        signature_base64url=_signature(signing_key, digest),
    )


def verify_verified_runner_consumption_receipt(
    receipt: VerifiedRunnerConsumptionReceipt,
    evidence: VerifiedRunnerEvidenceBundle,
    *,
    trust_store: VerifiedRunnerTrustStore,
    policy: VerifiedRunnerPolicy,
    authority_pins: VerifiedRunnerAuthorityPins,
    expected_authority_sha256: str,
    at: datetime,
) -> VerifiedRunnerConsumptionReceipt:
    """Authenticate a consumed P19 bundle before any P18 authority is granted."""

    _utc(at, "runner consumption verification time")
    try:
        selected = VerifiedRunnerConsumptionReceipt.model_validate(
            receipt.model_dump()
        )
        evidence = VerifiedRunnerEvidenceBundle.model_validate(evidence.model_dump())
        trust = VerifiedRunnerTrustStore.model_validate(trust_store.model_dump())
        policy = VerifiedRunnerPolicy.model_validate(policy.model_dump())
        pins = VerifiedRunnerAuthorityPins.model_validate(authority_pins.model_dump())
    except (AttributeError, TypeError, ValueError) as exc:
        raise VerifiedRunnerInputError("invalid runner consumption contract") from exc
    if (
        selected.store_id_sha256 != pins.expected_consumer_store_id_sha256
        or evidence.challenge.consumer_store_id_sha256 != selected.store_id_sha256
        or selected.sequence != pins.expected_sequence
        or selected.previous_evidence_head_sha256
        != pins.expected_previous_evidence_head_sha256
        or selected.evidence_head_sha256 != evidence.bundle_sha256
        or selected.challenge_sha256 != evidence.challenge.challenge_sha256
        or selected.evidence_bundle_sha256 != evidence.bundle_sha256
        or selected.authority_sha256 != expected_authority_sha256
        or selected.signer_issuer != trust.storage_auditor.issuer
        or selected.signer_key_id_sha256 != trust.storage_auditor.key_id_sha256
        or selected.clock_attestation.signer_issuer != trust.time_auditor.issuer
        or selected.clock_attestation.signer_key_id_sha256
        != trust.time_auditor.key_id_sha256
        or not _verify_signature(
            trust.time_auditor,
            selected.clock_attestation.attestation_sha256,
            selected.clock_attestation.signature_base64url,
        )
        or selected.clock_attestation.expires_at
        - selected.clock_attestation.issued_at
        > timedelta(seconds=policy.maximum_clock_attestation_ttl_seconds)
        or selected.clock_attestation.issued_at
        - selected.clock_attestation.observed_at
        > timedelta(seconds=policy.maximum_clock_observation_lag_seconds)
        or not _verify_signature(
            trust.storage_auditor,
            selected.receipt_sha256,
            selected.signature_base64url,
        )
        or selected.consumed_at
        < max(
            evidence.runner_attestation.issued_at,
            *(record.result.ended_at for record in evidence.records),
        )
        or selected.consumed_at > at
    ):
        raise VerifiedRunnerInputError("runner consumption receipt is not authoritative")
    return selected


_VERIFIED_RUNNER_CONSUMER_SCHEMA = """
CREATE TABLE verified_runner_consumer_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE verified_runner_consumptions (
    sequence INTEGER PRIMARY KEY,
    previous_evidence_head_sha256 TEXT NOT NULL,
    evidence_head_sha256 TEXT NOT NULL UNIQUE,
    challenge_sha256 TEXT NOT NULL UNIQUE,
    evidence_bundle_sha256 TEXT NOT NULL UNIQUE,
    authority_sha256 TEXT NOT NULL,
    clock_request_json TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    consumed_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER verified_runner_consumptions_no_update
BEFORE UPDATE ON verified_runner_consumptions BEGIN
    SELECT RAISE(ABORT, 'verified runner consumptions are immutable');
END;
CREATE TRIGGER verified_runner_consumptions_no_delete
BEFORE DELETE ON verified_runner_consumptions BEGIN
    SELECT RAISE(ABORT, 'verified runner consumptions are immutable');
END;
"""


class VerifiedRunnerReplayStore:
    """Authenticated one-shot P19 challenge consumer with an external anchor.

    Authentication keys and clock authority are runtime-only constructor inputs;
    no CLI accepts them.  The external anchor callback must enforce monotonic
    revisions.  A database one revision ahead of that anchor is recoverable,
    covering a crash after SQLite commit and before anchor commit.
    """

    __slots__ = (
        "_path",
        "_lock_path",
        "_identity",
        "_store_id",
        "_auth_key",
        "_anchor_commit",
        "_anchor_read",
        "_clock_attest",
        "_consumption_signing_key",
        "_clock_failed",
        "_lock",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        expected_store_id_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock_attest: Callable[
            [VerifiedRunnerConsumerClockRequest],
            SignedVerifiedRunnerConsumerClockAttestation,
        ],
        consumption_signing_key: Ed25519PrivateKey,
    ) -> None:
        self._configure(
            path,
            store_id_sha256=expected_store_id_sha256,
            state_authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
            clock_attest=clock_attest,
            consumption_signing_key=consumption_signing_key,
        )
        if not self._path.is_file() or self._path.stat().st_mode & 0o077:
            raise VerifiedRunnerInputError("runner replay store is missing or unsafe")
        observed = self._path.stat()
        self._identity = (observed.st_dev, observed.st_ino)
        with self._file_lock(), self._connect() as connection:
            self._assert_integrity(connection, recover_anchor=True)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock_attest: Callable[
            [VerifiedRunnerConsumerClockRequest],
            SignedVerifiedRunnerConsumerClockAttestation,
        ],
        consumption_signing_key: Ed25519PrivateKey,
    ) -> VerifiedRunnerReplayStore:
        store = object.__new__(cls)
        store._configure(
            path,
            store_id_sha256=store_id_sha256,
            state_authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
            clock_attest=clock_attest,
            consumption_signing_key=consumption_signing_key,
        )
        if store._path.exists():
            raise VerifiedRunnerInputError("runner replay store already exists")
        store._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(store._path) as connection:
            connection.row_factory = sqlite3.Row
            connection.executescript(_VERIFIED_RUNNER_CONSUMER_SCHEMA)
            meta = {
                "schema_version": "1.0",
                "store_id_sha256": store_id_sha256,
                "revision": "0",
                "anchor_revision": "0",
                "clock_frozen": "0",
                "evidence_head_sha256": _ZERO_SHA256,
                "previous_anchor_sha256": _ZERO_SHA256,
                "state_mac_sha256": _ZERO_SHA256,
            }
            connection.executemany(
                "INSERT INTO verified_runner_consumer_meta(key,value) VALUES (?,?)",
                tuple(meta.items()),
            )
            mac = store._state_mac(connection)
            connection.execute(
                "UPDATE verified_runner_consumer_meta SET value=? "
                "WHERE key='state_mac_sha256'",
                (mac,),
            )
        store._path.chmod(0o600)
        anchor = store._anchor_hash(0, _ZERO_SHA256, mac, _ZERO_SHA256)
        _bounded_store_callback(anchor_commit, 0, anchor, label="runner-anchor-commit")
        if _bounded_store_callback(anchor_read, label="runner-anchor-read") != anchor:
            raise VerifiedRunnerInputError("runner replay anchor was not durable")
        return cls(
            store._path,
            expected_store_id_sha256=store_id_sha256,
            state_authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
            clock_attest=clock_attest,
            consumption_signing_key=consumption_signing_key,
        )

    def _configure(
        self,
        path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock_attest: Callable[
            [VerifiedRunnerConsumerClockRequest],
            SignedVerifiedRunnerConsumerClockAttestation,
        ],
        consumption_signing_key: Ed25519PrivateKey,
    ) -> None:
        if not isinstance(path, (str, Path)):
            raise TypeError("runner replay store path must be a string or Path")
        selected = Path(path)
        if str(selected) in {"", ":memory:"} or selected.is_symlink():
            raise ValueError("runner replay store requires a durable real path")
        if not isinstance(store_id_sha256, str) or len(store_id_sha256) != 64:
            raise ValueError("runner replay store ID must be SHA-256")
        try:
            bytes.fromhex(store_id_sha256)
        except ValueError as exc:
            raise ValueError("runner replay store ID must be SHA-256") from exc
        if type(state_authentication_key) is not bytes or len(
            state_authentication_key
        ) < 32:
            raise ValueError("runner replay authentication key is too short")
        if not all(callable(item) for item in (anchor_commit, anchor_read, clock_attest)):
            raise TypeError("runner replay runtime callbacks are required")
        if not isinstance(consumption_signing_key, Ed25519PrivateKey):
            raise TypeError("runner replay consumption signing key is required")
        self._path = selected.resolve()
        self._lock_path = self._path.with_name(f"{self._path.name}.lock")
        self._identity = (0, 0)
        self._store_id = store_id_sha256
        self._auth_key = state_authentication_key
        self._anchor_commit = anchor_commit
        self._anchor_read = anchor_read
        self._clock_attest = clock_attest
        self._consumption_signing_key = consumption_signing_key
        self._clock_failed = False
        self._lock = RLock()

    def _obtain_clock_attestation(
        self,
        request: VerifiedRunnerConsumerClockRequest,
        *,
        timeout_seconds: int,
    ) -> SignedVerifiedRunnerConsumerClockAttestation:
        if self._clock_failed:
            raise VerifiedRunnerInputError(
                "runner consumer clock runtime is frozen after failure"
            )
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                output.put((True, self._clock_attest(request)), block=False)
            except BaseException as exc:  # callback boundary must fail closed
                try:
                    output.put((False, exc), block=False)
                except BaseException:
                    pass

        worker = Thread(
            target=invoke,
            name=f"verified-runner-clock-{request.request_nonce_sha256[:12]}",
            daemon=True,
        )
        worker.start()
        try:
            succeeded, value = output.get(timeout=timeout_seconds)
        except Empty as exc:
            self._clock_failed = True
            raise VerifiedRunnerInputError(
                "runner consumer clock response timed out; runtime frozen"
            ) from exc
        if not succeeded:
            self._clock_failed = True
            raise VerifiedRunnerInputError(
                "runner consumer clock callback failed; runtime frozen"
            ) from value if isinstance(value, BaseException) else None
        try:
            return SignedVerifiedRunnerConsumerClockAttestation.model_validate(
                value.model_dump()  # type: ignore[union-attr]
            )
        except (AttributeError, TypeError, ValueError) as exc:
            self._clock_failed = True
            raise VerifiedRunnerInputError(
                "runner consumer clock returned an invalid attestation"
            ) from exc

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        descriptor = os.open(
            self._lock_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            deadline = time.monotonic() + _STORE_COORDINATION_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise VerifiedRunnerInputError(
                            "runner replay store lock timed out"
                        ) from exc
                    time.sleep(_STORE_LOCK_POLL_SECONDS)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        observed = self._path.stat()
        if self._identity != (observed.st_dev, observed.st_ino):
            raise VerifiedRunnerInputError("runner replay store identity changed")
        connection = sqlite3.connect(self._path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _schema_sha256(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        return _domain_sha256(
            "consumer-store-schema",
            tuple(tuple(row) for row in rows),
        )

    @classmethod
    def _expected_schema_sha256(cls) -> str:
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(_VERIFIED_RUNNER_CONSUMER_SCHEMA)
            return cls._schema_sha256(connection)

    def _meta(self, connection: sqlite3.Connection) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in connection.execute(
                "SELECT key,value FROM verified_runner_consumer_meta ORDER BY key"
            )
        }

    def _state_mac(self, connection: sqlite3.Connection) -> str:
        meta = self._meta(connection)
        meta["state_mac_sha256"] = _ZERO_SHA256
        rows = tuple(
            dict(row)
            for row in connection.execute(
                "SELECT * FROM verified_runner_consumptions ORDER BY sequence"
            )
        )
        payload = json.dumps(
            {"meta": meta, "rows": rows},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(self._auth_key, payload, hashlib.sha256).hexdigest()

    def _anchor_hash(
        self,
        revision: int,
        evidence_head: str,
        state_mac: str,
        previous_anchor: str,
    ) -> str:
        return _domain_sha256(
            "consumer-store-anchor",
            {
                "store_id_sha256": self._store_id,
                "revision": revision,
                "evidence_head_sha256": evidence_head,
                "state_mac_sha256": state_mac,
                "previous_anchor_sha256": previous_anchor,
            },
        )

    def _assert_integrity(
        self, connection: sqlite3.Connection, *, recover_anchor: bool
    ) -> dict[str, str]:
        if self._schema_sha256(connection) != self._expected_schema_sha256():
            raise VerifiedRunnerInputError("runner replay store schema changed")
        meta = self._meta(connection)
        expected_keys = {
            "schema_version",
            "store_id_sha256",
            "revision",
            "anchor_revision",
            "clock_frozen",
            "evidence_head_sha256",
            "previous_anchor_sha256",
            "state_mac_sha256",
        }
        if (
            set(meta) != expected_keys
            or meta["schema_version"] != "1.0"
            or meta["store_id_sha256"] != self._store_id
            or meta["state_mac_sha256"] != self._state_mac(connection)
        ):
            raise VerifiedRunnerInputError("runner replay store authentication failed")
        revision = int(meta["revision"])
        anchor_revision = int(meta["anchor_revision"])
        if anchor_revision < revision or meta["clock_frozen"] not in {"0", "1"}:
            raise VerifiedRunnerInputError("runner replay control state changed")
        rows = connection.execute(
            "SELECT sequence,evidence_head_sha256,receipt_json FROM "
            "verified_runner_consumptions ORDER BY sequence"
        ).fetchall()
        if tuple(row["sequence"] for row in rows) != tuple(
            range(1, revision + 1)
        ) or len(rows) != revision:
            raise VerifiedRunnerInputError("runner replay sequence is not contiguous")
        if rows:
            receipts = tuple(
                VerifiedRunnerConsumptionReceipt.model_validate_json(
                    row["receipt_json"]
                )
                for row in rows
            )
            previous = _ZERO_SHA256
            for row, receipt in zip(rows, receipts, strict=True):
                if (
                    receipt.sequence != row["sequence"]
                    or receipt.previous_evidence_head_sha256 != previous
                    or receipt.evidence_head_sha256 != row["evidence_head_sha256"]
                ):
                    raise VerifiedRunnerInputError("runner replay receipt chain changed")
                previous = receipt.evidence_head_sha256
            if previous != meta["evidence_head_sha256"]:
                raise VerifiedRunnerInputError("runner replay head changed")
        elif meta["evidence_head_sha256"] != _ZERO_SHA256:
            raise VerifiedRunnerInputError("empty runner replay store has a head")
        anchor = self._anchor_hash(
            anchor_revision,
            meta["evidence_head_sha256"],
            meta["state_mac_sha256"],
            meta["previous_anchor_sha256"],
        )
        observed_anchor = _bounded_store_callback(
            self._anchor_read, label="runner-anchor-read"
        )
        if observed_anchor != anchor:
            if not recover_anchor or observed_anchor != meta["previous_anchor_sha256"]:
                raise VerifiedRunnerInputError("runner replay external anchor mismatch")
            _bounded_store_callback(
                self._anchor_commit,
                anchor_revision,
                anchor,
                label="runner-anchor-recovery",
            )
            if _bounded_store_callback(
                self._anchor_read, label="runner-anchor-read"
            ) != anchor:
                raise VerifiedRunnerInputError("runner replay anchor recovery failed")
        return meta

    def _persist_clock_freeze(self, connection: sqlite3.Connection) -> None:
        """Durably freeze after any untrusted clock-service response."""

        self._clock_failed = True
        if connection.in_transaction:
            connection.rollback()
        connection.execute("BEGIN IMMEDIATE")
        frozen_meta = self._assert_integrity(connection, recover_anchor=True)
        if frozen_meta["clock_frozen"] == "1":
            connection.rollback()
            return
        previous_anchor = _bounded_store_callback(
            self._anchor_read, label="runner-anchor-read"
        )
        anchor_revision = int(frozen_meta["anchor_revision"]) + 1
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value='1' "
            "WHERE key='clock_frozen'"
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='anchor_revision'",
            (str(anchor_revision),),
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='previous_anchor_sha256'",
            (previous_anchor,),
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='state_mac_sha256'",
            (_ZERO_SHA256,),
        )
        frozen_mac = self._state_mac(connection)
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='state_mac_sha256'",
            (frozen_mac,),
        )
        connection.commit()
        frozen_anchor = self._anchor_hash(
            anchor_revision,
            frozen_meta["evidence_head_sha256"],
            frozen_mac,
            previous_anchor,
        )
        _bounded_store_callback(
            self._anchor_commit,
            anchor_revision,
            frozen_anchor,
            label="runner-freeze-anchor-commit",
        )
        if _bounded_store_callback(
            self._anchor_read, label="runner-anchor-read"
        ) != frozen_anchor:
            raise VerifiedRunnerInputError(
                "runner clock freeze anchor was not durable"
            )

    def _arm_clock_freeze(self, connection: sqlite3.Connection) -> None:
        """Commit fail-closed intent before asking an external clock service."""

        if connection.in_transaction:
            connection.rollback()
        connection.execute("BEGIN IMMEDIATE")
        meta = self._assert_integrity(connection, recover_anchor=True)
        if meta["clock_frozen"] == "1":
            connection.rollback()
            raise VerifiedRunnerInputError(
                "runner consumer clock store is persistently frozen"
            )
        previous_anchor = _bounded_store_callback(
            self._anchor_read, label="runner-anchor-read"
        )
        anchor_revision = int(meta["anchor_revision"]) + 1
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value='1' "
            "WHERE key='clock_frozen'"
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='anchor_revision'",
            (str(anchor_revision),),
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='previous_anchor_sha256'",
            (previous_anchor,),
        )
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='state_mac_sha256'",
            (_ZERO_SHA256,),
        )
        state_mac = self._state_mac(connection)
        connection.execute(
            "UPDATE verified_runner_consumer_meta SET value=? "
            "WHERE key='state_mac_sha256'",
            (state_mac,),
        )
        connection.commit()
        anchor = self._anchor_hash(
            anchor_revision,
            meta["evidence_head_sha256"],
            state_mac,
            previous_anchor,
        )
        _bounded_store_callback(
            self._anchor_commit,
            anchor_revision,
            anchor,
            label="runner-clock-intent-anchor-commit",
        )
        if _bounded_store_callback(
            self._anchor_read, label="runner-anchor-read"
        ) != anchor:
            raise VerifiedRunnerInputError(
                "runner clock intent anchor was not durable"
            )

    def consume(
        self,
        evidence: VerifiedRunnerEvidenceBundle,
        *,
        policy: VerifiedRunnerPolicy,
        trust_store: VerifiedRunnerTrustStore,
        authority_pins: VerifiedRunnerAuthorityPins,
        expected_authority_sha256: str,
    ) -> VerifiedRunnerConsumptionReceipt:
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection, recover_anchor=True)
                if meta["clock_frozen"] == "1":
                    raise VerifiedRunnerInputError(
                        "runner consumer clock store is persistently frozen"
                    )
                try:
                    evidence = VerifiedRunnerEvidenceBundle.model_validate(
                        evidence.model_dump()
                    )
                    policy = VerifiedRunnerPolicy.model_validate(policy.model_dump())
                    trust_store = VerifiedRunnerTrustStore.model_validate(
                        trust_store.model_dump()
                    )
                    authority_pins = VerifiedRunnerAuthorityPins.model_validate(
                        authority_pins.model_dump()
                    )
                except (AttributeError, TypeError, ValueError) as exc:
                    raise VerifiedRunnerInputError(
                        "invalid runner replay consumption contract"
                    ) from exc
                if (
                    authority_pins.expected_consumer_store_id_sha256
                    != self._store_id
                    or evidence.challenge.consumer_store_id_sha256 != self._store_id
                    or hash_verified_runner_authority(
                        policy, trust_store, authority_pins
                    )
                    != expected_authority_sha256
                ):
                    raise VerifiedRunnerInputError(
                        "runner replay store or authority binding mismatch"
                    )
                storage_key = create_verification_key(
                    self._consumption_signing_key.public_key(),
                    issuer=trust_store.storage_auditor.issuer,
                    role=SigningRole.STORAGE_AUDITOR,
                )
                if storage_key != trust_store.storage_auditor:
                    raise VerifiedRunnerInputError(
                        "runner consumption signing key mismatch"
                    )
                revision = int(meta["revision"])
                expected_sequence = revision + 1
                if (
                    authority_pins.expected_sequence != expected_sequence
                    or authority_pins.expected_previous_evidence_head_sha256
                    != meta["evidence_head_sha256"]
                    or evidence.challenge.sequence != expected_sequence
                    or evidence.challenge.previous_evidence_head_sha256
                    != meta["evidence_head_sha256"]
                ):
                    raise VerifiedRunnerInputError(
                        "runner challenge is not the exact unused store tail"
                    )
                request_values = {
                    "store_id_sha256": self._store_id,
                    "expected_sequence": expected_sequence,
                    "expected_previous_evidence_head_sha256": (
                        meta["evidence_head_sha256"]
                    ),
                    "challenge_sha256": evidence.challenge.challenge_sha256,
                    "evidence_bundle_sha256": evidence.bundle_sha256,
                    "authority_sha256": expected_authority_sha256,
                    "request_nonce_sha256": hashlib.sha256(
                        os.urandom(32)
                    ).hexdigest(),
                }
                request_provisional = VerifiedRunnerConsumerClockRequest.model_construct(
                    **request_values,
                    schema_version="1.0",
                    request_sha256=_ZERO_SHA256,
                )
                request = VerifiedRunnerConsumerClockRequest(
                    **request_values,
                    request_sha256=hash_verified_runner_consumer_clock_request(
                        request_provisional
                    ),
                )
                self._arm_clock_freeze(connection)
                connection.execute("BEGIN IMMEDIATE")
                meta = self._assert_integrity(connection, recover_anchor=True)
                if meta["clock_frozen"] != "1":
                    raise VerifiedRunnerInputError(
                        "runner clock intent was not durably armed"
                    )
                try:
                    clock = self._obtain_clock_attestation(
                        request,
                        timeout_seconds=policy.clock_response_timeout_seconds,
                    )
                except VerifiedRunnerInputError:
                    self._persist_clock_freeze(connection)
                    raise
                if (
                    clock.request_sha256 != request.request_sha256
                    or clock.store_id_sha256 != self._store_id
                    or clock.observed_sequence != revision
                    or clock.observed_evidence_head_sha256
                    != meta["evidence_head_sha256"]
                    or clock.signer_issuer != trust_store.time_auditor.issuer
                    or clock.signer_key_id_sha256
                    != trust_store.time_auditor.key_id_sha256
                    or not _verify_signature(
                        trust_store.time_auditor,
                        clock.attestation_sha256,
                        clock.signature_base64url,
                    )
                    or clock.expires_at - clock.issued_at
                    > timedelta(
                        seconds=policy.maximum_clock_attestation_ttl_seconds
                    )
                    or clock.issued_at - clock.observed_at
                    > timedelta(
                        seconds=policy.maximum_clock_observation_lag_seconds
                    )
                ):
                    self._persist_clock_freeze(connection)
                    raise VerifiedRunnerInputError(
                        "runner consumer clock is not authoritative"
                    )
                verified = verify_verified_runner_evidence(
                    evidence,
                    policy=policy,
                    trust_store=trust_store,
                    authority_pins=authority_pins,
                    expected_authority_sha256=expected_authority_sha256,
                    at=clock.observed_at,
                )
                existing = connection.execute(
                    "SELECT 1 FROM verified_runner_consumptions WHERE "
                    "challenge_sha256=? OR evidence_bundle_sha256=?",
                    (
                        verified.challenge.challenge_sha256,
                        verified.bundle_sha256,
                    ),
                ).fetchone()
                if existing is not None:
                    raise VerifiedRunnerInputError(
                        "runner challenge or evidence was already consumed"
                    )
                receipt_values = {
                    "store_id_sha256": self._store_id,
                    "sequence": expected_sequence,
                    "previous_evidence_head_sha256": meta[
                        "evidence_head_sha256"
                    ],
                    "evidence_head_sha256": verified.bundle_sha256,
                    "challenge_sha256": verified.challenge.challenge_sha256,
                    "evidence_bundle_sha256": verified.bundle_sha256,
                    "authority_sha256": expected_authority_sha256,
                    "clock_request": request,
                    "clock_attestation": clock,
                    "clock_request_sha256": request.request_sha256,
                    "clock_attestation_sha256": clock.attestation_sha256,
                    "consumed_at": clock.observed_at,
                }
                receipt = sign_verified_runner_consumption_receipt(
                    values=receipt_values,
                    trust_store=trust_store,
                    signing_key=self._consumption_signing_key,
                )
                connection.execute(
                    "INSERT INTO verified_runner_consumptions("
                    "sequence,previous_evidence_head_sha256,evidence_head_sha256,"
                    "challenge_sha256,evidence_bundle_sha256,authority_sha256,"
                    "clock_request_json,clock_attestation_json,receipt_json,consumed_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        expected_sequence,
                        meta["evidence_head_sha256"],
                        verified.bundle_sha256,
                        verified.challenge.challenge_sha256,
                        verified.bundle_sha256,
                        expected_authority_sha256,
                        request.model_dump_json(),
                        clock.model_dump_json(),
                        receipt.model_dump_json(),
                        clock.observed_at.isoformat(),
                    ),
                )
                previous_anchor = _bounded_store_callback(
                    self._anchor_read, label="runner-anchor-read"
                )
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='revision'",
                    (str(expected_sequence),),
                )
                anchor_revision = int(meta["anchor_revision"]) + 1
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='anchor_revision'",
                    (str(anchor_revision),),
                )
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='evidence_head_sha256'",
                    (verified.bundle_sha256,),
                )
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='previous_anchor_sha256'",
                    (previous_anchor,),
                )
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value='0' "
                    "WHERE key='clock_frozen'"
                )
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='state_mac_sha256'",
                    (_ZERO_SHA256,),
                )
                state_mac = self._state_mac(connection)
                connection.execute(
                    "UPDATE verified_runner_consumer_meta SET value=? "
                    "WHERE key='state_mac_sha256'",
                    (state_mac,),
                )
                connection.commit()
                anchor = self._anchor_hash(
                    anchor_revision,
                    verified.bundle_sha256,
                    state_mac,
                    previous_anchor,
                )
                _bounded_store_callback(
                    self._anchor_commit,
                    anchor_revision,
                    anchor,
                    label="runner-anchor-commit",
                )
                if _bounded_store_callback(
                    self._anchor_read, label="runner-anchor-read"
                ) != anchor:
                    raise VerifiedRunnerInputError(
                        "runner replay anchor commit was not durable"
                    )
                return receipt
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def receipts(self) -> tuple[VerifiedRunnerConsumptionReceipt, ...]:
        with self._lock, self._file_lock(), self._connect() as connection:
            self._assert_integrity(connection, recover_anchor=True)
            return tuple(
                VerifiedRunnerConsumptionReceipt.model_validate_json(
                    row["receipt_json"]
                )
                for row in connection.execute(
                    "SELECT receipt_json FROM verified_runner_consumptions "
                    "ORDER BY sequence"
                )
            )
