"""Exact, credential-free repository acceptance and restart boundary.

P18 closes the gap between an audited working-tree candidate and a separately
signed Human decision.  It hashes a code-defined local scope, binds structured
verification facts, and reports the next gate.  It never grants publication,
production, affiliate, spend, scale, or other external mutation authority.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self
from xml.etree import ElementTree

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from .control_cycle import Ed25519VerificationKey, SigningRole
from .models import Sha256, Slug, StrictModel
from .verified_runner import (
    REQUIRED_VERIFIED_RUNNER_CHECKS,
    VERIFIED_RUNNER_MINIMUM_ASSERTIONS,
    VerifiedRunnerAuthorityPins,
    VerifiedRunnerCheck,
    VerifiedRunnerConsumptionReceipt,
    VerifiedRunnerEvidenceBundle,
    VerifiedRunnerNetworkMode,
    VerifiedRunnerPolicy,
    VerifiedRunnerTrustStore,
    hash_verified_check_output,
    hash_verified_runner_authority,
    verify_verified_runner_evidence,
    verify_verified_runner_consumption_receipt,
)


class RepositoryAcceptanceInputError(ValueError):
    """An untrusted acceptance artifact or repository scope is invalid."""


RepositoryScopeProfile = Literal[
    "p11-p18-local-candidate-v1",
    "p11-p20-local-candidate-v2",
    "p11-p21-local-candidate-v3",
    "p11-p21-growth-local-candidate-v4",
    "p11-p21-owned-learning-local-candidate-v5",
    "p11-p21-measurement-deploy-ready-local-candidate-v6",
    "p11-p21-launch-track-local-candidate-v7",
    "p11-p21-editorial-contracts-local-candidate-v8",
]
LEGACY_SCOPE_PROFILE: RepositoryScopeProfile = "p11-p18-local-candidate-v1"
P20_SCOPE_PROFILE: RepositoryScopeProfile = "p11-p20-local-candidate-v2"
P21_SCOPE_PROFILE: RepositoryScopeProfile = "p11-p21-local-candidate-v3"
GROWTH_SCOPE_PROFILE: RepositoryScopeProfile = "p11-p21-growth-local-candidate-v4"
OWNED_LEARNING_SCOPE_PROFILE: RepositoryScopeProfile = (
    "p11-p21-owned-learning-local-candidate-v5"
)
SCOPE_PROFILE: RepositoryScopeProfile = (
    "p11-p21-editorial-contracts-local-candidate-v8"
)
PREVIOUS_CANDIDATE_RECORD = "docs/P11_P17_LOCAL_ACCEPTANCE_PENDING.md"
_SCOPE_PATHS_BY_PROFILE = {
    LEGACY_SCOPE_PROFILE: (
        "8cfaac4b1a77e790f467442cab628b53f53769c39ce15390676e3dede2ecb721"
    ),
    P20_SCOPE_PROFILE: (
        "82e256e234b4c3e1fc2106c28acfddf14508d8a9ee305623957eeda7f77f3970"
    ),
    P21_SCOPE_PROFILE: (
        "5a56536ab6f8f6afb59fc42833b9a2584654ea4fac2910f40e0be17592e7daed"
    ),
    GROWTH_SCOPE_PROFILE: (
        "1c93f72ca8bb2d9bd2780c04a02b4eef7db7ff1fcdf160909be85e73a0deed15"
    ),
    OWNED_LEARNING_SCOPE_PROFILE: (
        "e095b623274f1ce14d4b413bccc760bad1238effc4e63d4077a014e64a0f0bc6"
    ),
    "p11-p21-measurement-deploy-ready-local-candidate-v6": (
        "227fe3fcfc83718e17f5e9fb8667cc4c762b6606a6f000319619ff4aaf473d20"
    ),
    "p11-p21-launch-track-local-candidate-v7": (
        "a078f9b367a21890879f0b24445f84d2e95994d32489f9d939964107f2390175"
    ),
    SCOPE_PROFILE: (
        "ac7c4dd0560e23047d22d8c4d01710ce510ebc1e7e72289e888e8583a4ffc75e"
    ),
}

_SCOPE_ROOT_FILES = (
    ".gitignore",
    ".gitleaks.toml",
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "status-dashboard.html",
    "uv.lock",
)
_SCOPE_ROOT_DIRECTORIES = (
    ".github",
    ".workflow/recipes",
    ".workflow/saas-affiliate-production-roadmap",
    "artifacts/editorial-inputs",
    "artifacts/release-assurance",
    "docs",
    "examples",
    "schemas",
    "scripts",
    "site",
    "src",
    "tests",
)
_IGNORED_TOP_LEVEL = frozenset(
    {
        ".codex",
        ".devspace",
        ".git",
        ".hypothesis",
        ".pytest_cache",
        ".venv",
        "outputs",
        "work",
    }
)
_IGNORED_DIRECTORY_NAMES = frozenset({"__pycache__", ".pytest_cache"})
_IGNORED_SITE_DIRECTORY_NAMES = frozenset(
    {".git", ".vinext", ".wrangler", "dist", "node_modules"}
)
_FORBIDDEN_SECRET_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "credentials.json",
        "service-account.json",
    }
)
_FORBIDDEN_SECRET_SUFFIXES = (".key", ".p12", ".pfx", ".pem")

REPOSITORY_VERIFICATION_RUNNER_VERSION = "1.0.0"
_NETWORK_DISABLED_SANDBOX_PROFILE = (
    "(version 1)(allow default)(deny network*)"
)
_LOOPBACK_ONLY_SANDBOX_PROFILE = (
    "(version 1)(allow default)(deny network*)"
    '(allow network-bind (local ip "localhost:*"))'
    '(allow network-inbound (local ip "localhost:*"))'
    '(allow network-outbound (remote ip "localhost:*"))'
)
_VERIFICATION_RUNNER_WORK = Path(
    "artifacts/local-acceptance/p18-verification-work"
)
_VERIFICATION_OUTPUT_LIMIT_BYTES = 4 * 1024 * 1024
_SEMVER_PATTERN = re.compile(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])")
_BASE_TEST_MODULES = frozenset(
    {
        "tests/test_adoption_implementation_status.py",
        "tests/test_ai_routing.py",
        "tests/test_cli.py",
        "tests/test_control_cycle.py",
        "tests/test_economics.py",
        "tests/test_editorial_input.py",
        "tests/test_end_to_end.py",
        "tests/test_external_actions.py",
        "tests/test_goldset.py",
        "tests/test_goldset_cli.py",
        "tests/test_growth_system.py",
        "tests/test_keyword_universe.py",
        "tests/test_launch_semantics.py",
        "tests/test_launch_semantics_security.py",
        "tests/test_mangools_export.py",
        "tests/test_measurement.py",
        "tests/test_measurement_cli.py",
        "tests/test_measurement_integrity.py",
        "tests/test_models.py",
        "tests/test_mvp.py",
        "tests/test_operations.py",
        "tests/test_operations_activity.py",
        "tests/test_preflight.py",
        "tests/test_preflight_cli.py",
        "tests/test_preview.py",
        "tests/test_production_readiness.py",
        "tests/test_readiness_builder.py",
        "tests/test_release.py",
        "tests/test_release_assurance.py",
        "tests/test_sbom.py",
        "tests/test_source_access.py",
        "tests/test_storage.py",
        "tests/test_status_dashboard.py",
        "tests/test_tco.py",
        "tests/test_tco_golden.py",
        "tests/test_verified_runner.py",
    }
)


RepositoryVerificationCheck = VerifiedRunnerCheck


REQUIRED_REPOSITORY_VERIFICATION_CHECKS: tuple[
    RepositoryVerificationCheck, ...
] = REQUIRED_VERIFIED_RUNNER_CHECKS

REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS = VERIFIED_RUNNER_MINIMUM_ASSERTIONS

_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS = {
    RepositoryVerificationCheck.PYTHON_BASE: 900,
    RepositoryVerificationCheck.PYTHON_TRACTION: 300,
    RepositoryVerificationCheck.PYTHON_PRODUCTION_CONSUMER: 900,
    RepositoryVerificationCheck.SCHEMA_DETERMINISM: 180,
    RepositoryVerificationCheck.BLOCKED_FIXTURE_DETERMINISM: 180,
    RepositoryVerificationCheck.UV_LOCK: 60,
    RepositoryVerificationCheck.COMPILEALL: 120,
    RepositoryVerificationCheck.SECRET_SCAN: 180,
    RepositoryVerificationCheck.WEB_TESTS: 300,
    RepositoryVerificationCheck.WEB_LINT: 180,
    RepositoryVerificationCheck.DEPENDENCY_AUDIT: 120,
    RepositoryVerificationCheck.WORKFLOW_VERIFIER: 60,
    RepositoryVerificationCheck.CONTRACT_STORAGE_AUDIT: 180,
    RepositoryVerificationCheck.TCO_QA_AUDIT: 180,
}


class RepositoryVerificationProvenance(str, Enum):
    VERIFIED_LOCAL_RUN = "verified_local_run"
    VERIFIED_IMMUTABLE_RUN_V2 = "verified_immutable_run_v2"
    LOCAL_DIAGNOSTIC_RUN = "local_diagnostic_run"
    SYNTHETIC_CONTRACT = "synthetic_contract"


RepositoryVerificationNetworkMode = VerifiedRunnerNetworkMode


class RepositoryAuthorityExclusion(str, Enum):
    SOURCE_FETCH = "source_fetch"
    OUTREACH_APPLICATION_EMAIL = "outreach_application_email"
    ACCOUNT_CREDENTIAL_BILLING = "account_credential_billing"
    PRODUCTION_WRITE = "production_write"
    DEPLOY_PUBLICATION = "deploy_publication"
    AFFILIATE_LINK_CHANGE = "affiliate_link_change"
    SPEND = "spend"
    SCALE_AUTHORITY = "scale_authority"
    EXTERNAL_MUTATION = "external_mutation"


REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS: tuple[
    RepositoryAuthorityExclusion, ...
] = tuple(RepositoryAuthorityExclusion)


class RepositoryAcceptanceDecision(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CONDITIONAL_PENDING = "conditional_pending"
    REJECTED = "rejected"
    STOP = "stop"


class HumanRepositoryDecision(str, Enum):
    GO = "go"
    CONDITIONAL = "conditional"
    STOP = "stop"


class RepositoryAcceptanceReason(str, Enum):
    SCOPE_PROFILE_OUTDATED = "scope_profile_outdated"
    MANIFEST_DRIFT = "manifest_drift"
    MANIFEST_FUTURE = "manifest_future"
    MANIFEST_EXPIRED = "manifest_expired"
    MANIFEST_TTL_EXCEEDED = "manifest_ttl_exceeded"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_EXPIRED = "verification_expired"
    VERIFICATION_TOO_OLD = "verification_too_old"
    VERIFICATION_SYNTHETIC = "verification_synthetic"
    VERIFICATION_REQUIREMENT_MISMATCH = "verification_requirement_mismatch"
    VERIFICATION_TRUST_MISSING = "verification_trust_missing"
    VERIFICATION_TRUST_MISMATCH = "verification_trust_mismatch"
    VERIFICATION_ATTESTATION_MISSING = "verification_attestation_missing"
    VERIFICATION_ATTESTATION_INVALID = "verification_attestation_invalid"
    RECEIPT_MISSING = "receipt_missing"
    AUTHORITY_MISSING = "authority_missing"
    AUTHORITY_ROOT_MISSING = "authority_root_missing"
    AUTHORITY_ROOT_MISMATCH = "authority_root_mismatch"
    AUTHORITY_PIN_MISMATCH = "authority_pin_mismatch"
    POLICY_MISMATCH = "policy_mismatch"
    TRUST_STORE_MISMATCH = "trust_store_mismatch"
    RECEIPT_BINDING_MISMATCH = "receipt_binding_mismatch"
    RECEIPT_SIGNATURE_INVALID = "receipt_signature_invalid"
    RECEIPT_FUTURE = "receipt_future"
    RECEIPT_EXPIRED = "receipt_expired"
    RECEIPT_TTL_EXCEEDED = "receipt_ttl_exceeded"
    RECEIPT_NOT_CURRENT = "receipt_not_current"
    RECEIPT_CHAIN_INVALID = "receipt_chain_invalid"
    HUMAN_CONDITIONAL = "human_conditional"
    HUMAN_STOP = "human_stop"


class RepositoryRestartGate(str, Enum):
    LOCAL_VERIFICATION = "local_verification"
    REPOSITORY_ACCEPTANCE = "repository_acceptance"
    RIGHTS_EVIDENCE = "rights_evidence"


class RepositoryRequiredInput(str, Enum):
    CURRENT_SIGNED_VERIFICATION_BUNDLE = "current_signed_verification_bundle"
    HUMAN_SIGNED_REPOSITORY_ACCEPTANCE = "human_signed_repository_acceptance"
    CURRENT_PINNED_ACCEPTANCE_CHAIN = "current_pinned_acceptance_chain"
    CURRENT_RIGHTS_DECISION_RECORDS = "current_rights_decision_records"


_LOCAL_VERIFICATION_REASONS = frozenset(
    {
        RepositoryAcceptanceReason.SCOPE_PROFILE_OUTDATED,
        RepositoryAcceptanceReason.MANIFEST_DRIFT,
        RepositoryAcceptanceReason.MANIFEST_FUTURE,
        RepositoryAcceptanceReason.MANIFEST_EXPIRED,
        RepositoryAcceptanceReason.MANIFEST_TTL_EXCEEDED,
        RepositoryAcceptanceReason.VERIFICATION_FAILED,
        RepositoryAcceptanceReason.VERIFICATION_EXPIRED,
        RepositoryAcceptanceReason.VERIFICATION_TOO_OLD,
        RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC,
        RepositoryAcceptanceReason.VERIFICATION_REQUIREMENT_MISMATCH,
        RepositoryAcceptanceReason.VERIFICATION_TRUST_MISSING,
        RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH,
        RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_MISSING,
        RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID,
    }
)

_ACCEPTANCE_CHAIN_REASONS = frozenset(
    {
        RepositoryAcceptanceReason.AUTHORITY_MISSING,
        RepositoryAcceptanceReason.AUTHORITY_ROOT_MISSING,
        RepositoryAcceptanceReason.AUTHORITY_ROOT_MISMATCH,
        RepositoryAcceptanceReason.AUTHORITY_PIN_MISMATCH,
        RepositoryAcceptanceReason.POLICY_MISMATCH,
        RepositoryAcceptanceReason.TRUST_STORE_MISMATCH,
        RepositoryAcceptanceReason.RECEIPT_BINDING_MISMATCH,
        RepositoryAcceptanceReason.RECEIPT_SIGNATURE_INVALID,
        RepositoryAcceptanceReason.RECEIPT_FUTURE,
        RepositoryAcceptanceReason.RECEIPT_EXPIRED,
        RepositoryAcceptanceReason.RECEIPT_TTL_EXCEEDED,
        RepositoryAcceptanceReason.RECEIPT_NOT_CURRENT,
        RepositoryAcceptanceReason.RECEIPT_CHAIN_INVALID,
    }
)


class RepositoryFileDigest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    path: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0, le=1_000_000_000)
    executable: bool
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def require_canonical_relative_path(cls, value: str) -> str:
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError("repository path must be NFC-normalized")
        if "\\" in value or "\x00" in value:
            raise ValueError("repository path contains a forbidden character")
        parsed = PurePosixPath(value)
        if (
            parsed.is_absolute()
            or not parsed.parts
            or parsed.as_posix() != value
            or any(part in {"", ".", ".."} for part in parsed.parts)
        ):
            raise ValueError("repository path must be canonical and relative")
        name = parsed.name.lower()
        if (
            name in _FORBIDDEN_SECRET_NAMES
            or name.startswith(".env.")
            or name.endswith(_FORBIDDEN_SECRET_SUFFIXES)
        ):
            raise ValueError("repository path has a secret-bearing filename")
        return value


class RepositoryVerificationFact(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    check: RepositoryVerificationCheck
    subject_tree_sha256: Sha256
    command_argv: tuple[str, ...] = Field(min_length=1, max_length=40)
    working_directory: Literal["repository-root"] = "repository-root"
    environment_sha256: Sha256
    network_mode: RepositoryVerificationNetworkMode
    interpreter_sha256: Sha256
    import_closure_sha256: Sha256
    command_sha256: Sha256
    tool_name: Slug
    tool_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$",
    )
    provenance: RepositoryVerificationProvenance
    executed_at: datetime
    not_after: datetime
    assertions_executed: int = Field(ge=1, le=100_000_000)
    failures: int = Field(ge=0, le=100_000_000)
    skipped: int = Field(ge=0, le=100_000_000)
    exit_code: int = Field(ge=0, le=255)
    output_sha256: Sha256

    @field_validator("executed_at", "not_after")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "verification timestamp")
        return value

    @model_validator(mode="after")
    def validate_fact(self) -> Self:
        if self.not_after <= self.executed_at:
            raise ValueError("verification expiry must be after execution")
        if self.failures + self.skipped > self.assertions_executed:
            raise ValueError("failed and skipped assertions exceed all assertions")
        if any(
            not item
            or "\x00" in item
            or len(item) > 1_024
            for item in self.command_argv
        ):
            raise ValueError("verification argv contains an invalid argument")
        if self.command_sha256 != hash_repository_verification_command(
            command_argv=self.command_argv,
            working_directory=self.working_directory,
            environment_sha256=self.environment_sha256,
            network_mode=self.network_mode,
            interpreter_sha256=self.interpreter_sha256,
            import_closure_sha256=self.import_closure_sha256,
        ):
            raise ValueError("verification command hash does not bind its context")
        return self

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.failures == 0 and self.skipped == 0


class RepositoryVerificationEvidenceBundle(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    subject_tree_sha256: Sha256
    facts: tuple[RepositoryVerificationFact, ...] = Field(min_length=14, max_length=14)
    verified_runner_consumption_receipt: VerifiedRunnerConsumptionReceipt | None = None
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if tuple(item.check for item in self.facts) != REQUIRED_REPOSITORY_VERIFICATION_CHECKS:
            raise ValueError("verification bundle must contain the exact ordered checks")
        if any(item.subject_tree_sha256 != self.subject_tree_sha256 for item in self.facts):
            raise ValueError("verification fact does not bind the bundle tree")
        uses_v2 = all(
            item.provenance
            is RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
            for item in self.facts
        )
        if uses_v2 != (self.verified_runner_consumption_receipt is not None):
            raise ValueError(
                "verified v2 facts require exactly one signed consumption receipt"
            )
        if self.bundle_sha256 != hash_repository_verification_bundle(self):
            raise ValueError("verification bundle hash mismatch")
        return self


class RepositoryVerificationAttestation(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    attestation_id: Slug
    subject_tree_sha256: Sha256
    verification_bundle_sha256: Sha256
    verified_runner_bundle_sha256: Sha256 = "0" * 64
    verified_runner_authority_sha256: Sha256 = "0" * 64
    signer_role: SigningRole
    signer_issuer: str = Field(min_length=1, max_length=120)
    signer_key_id_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    attestation_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "verification attestation timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if self.signer_role not in {
            SigningRole.INTEGRATION_EVIDENCE_RUNNER,
            SigningRole.TCO_QA,
        }:
            raise ValueError("verification attestation has an invalid signer role")
        if self.expires_at <= self.issued_at:
            raise ValueError("verification attestation expiry must follow issuance")
        if self.attestation_sha256 != hash_repository_verification_attestation(self):
            raise ValueError("verification attestation hash mismatch")
        return self


class RepositoryCandidateManifest(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    candidate_id: Slug
    scope_profile: RepositoryScopeProfile = SCOPE_PROFILE
    scope_paths_sha256: Sha256
    previous_candidate_record_sha256: Sha256
    assembled_at: datetime
    expires_at: datetime
    files: tuple[RepositoryFileDigest, ...] = Field(min_length=1, max_length=10_000)
    tree_sha256: Sha256
    verification: RepositoryVerificationEvidenceBundle
    verified_runner_evidence: VerifiedRunnerEvidenceBundle | None = None
    verified_runner_policy: VerifiedRunnerPolicy | None = None
    verified_runner_trust_store: VerifiedRunnerTrustStore | None = None
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None = None
    integration_verification: RepositoryVerificationAttestation | None = None
    tco_qa_verification: RepositoryVerificationAttestation | None = None
    authority_exclusions: tuple[RepositoryAuthorityExclusion, ...] = Field(
        min_length=9, max_length=9
    )
    authority: Literal["none"] = "none"
    decision: Literal["pending"] = "pending"
    manifest_sha256: Sha256

    @field_validator("assembled_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "candidate manifest timestamp")
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.expires_at <= self.assembled_at:
            raise ValueError("candidate manifest expiry must follow assembly")
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("repository files must be uniquely sorted by path")
        collision_keys = tuple(
            unicodedata.normalize("NFC", item).casefold() for item in paths
        )
        if len(set(collision_keys)) != len(collision_keys):
            raise ValueError(
                "repository files must not contain Unicode/case-colliding paths"
            )
        path_set = set(paths)
        expected_scope_paths = _SCOPE_PATHS_BY_PROFILE.get(self.scope_profile)
        if (
            expected_scope_paths is None
            or self.scope_paths_sha256 != expected_scope_paths
            or _canonical_sha256(paths) != expected_scope_paths
        ):
            raise ValueError("candidate manifest does not contain the exact fixed scope")
        if not set(_SCOPE_ROOT_FILES).issubset(path_set):
            raise ValueError("candidate manifest omits a required repository root file")
        if any(
            not (
                path in _SCOPE_ROOT_FILES
                or any(
                    path.startswith(f"{directory}/")
                    for directory in _SCOPE_ROOT_DIRECTORIES
                )
            )
            for path in paths
        ):
            raise ValueError("candidate manifest contains a path outside fixed scope")
        if any(
            not any(path.startswith(f"{directory}/") for path in paths)
            for directory in _SCOPE_ROOT_DIRECTORIES
        ):
            raise ValueError("candidate manifest omits a required repository directory")
        for path in paths:
            parts = PurePosixPath(path).parts
            if (
                any(part in _IGNORED_DIRECTORY_NAMES for part in parts)
                or path.endswith((".pyc", ".pyo"))
                or (
                    parts[0] == "site"
                    and any(
                        part in _IGNORED_SITE_DIRECTORY_NAMES
                        for part in parts[1:]
                    )
                )
            ):
                raise ValueError("candidate manifest includes a runtime-only path")
        previous_entry = next(
            (
                item
                for item in self.files
                if item.path == PREVIOUS_CANDIDATE_RECORD
            ),
            None,
        )
        if (
            previous_entry is None
            or previous_entry.sha256
            != self.previous_candidate_record_sha256
        ):
            raise ValueError("previous candidate record binding mismatch")
        if self.tree_sha256 != hash_repository_tree(self.files):
            raise ValueError("candidate tree hash mismatch")
        if self.verification.subject_tree_sha256 != self.tree_sha256:
            raise ValueError("verification bundle does not bind the candidate tree")
        provenances = {item.provenance for item in self.verification.facts}
        uses_v2 = provenances == {
            RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
        }
        runner_contract = (
            self.verified_runner_evidence,
            self.verified_runner_policy,
            self.verified_runner_trust_store,
            self.verified_runner_authority_pins,
        )
        if any(item is not None for item in runner_contract) and not all(
            item is not None for item in runner_contract
        ):
            raise ValueError("verified runner contract is incomplete")
        if uses_v2:
            if not all(item is not None for item in runner_contract):
                raise ValueError("verified v2 facts require retained runner evidence")
            assert self.verified_runner_evidence is not None
            assert self.verified_runner_policy is not None
            assert self.verified_runner_trust_store is not None
            assert self.verified_runner_authority_pins is not None
            if (
                self.verified_runner_evidence.subject_tree_sha256
                != self.tree_sha256
                or self.verification
                != build_repository_verification_from_verified_runner_evidence(
                    self.verified_runner_evidence,
                    consumption_receipt=(
                        self.verification.verified_runner_consumption_receipt
                    ),
                )
            ):
                raise ValueError("verified v2 facts do not match retained evidence")
            if (
                hash_verified_runner_authority(
                    self.verified_runner_policy,
                    self.verified_runner_trust_store,
                    self.verified_runner_authority_pins,
                )
                == "0" * 64
            ):
                raise ValueError("verified runner authority cannot be zero")
        elif any(item is not None for item in runner_contract):
            raise ValueError("runner evidence cannot accompany legacy or diagnostic facts")
        if len(provenances) != 1:
            raise ValueError("repository verification provenance cannot be mixed")
        attestations = (self.integration_verification, self.tco_qa_verification)
        if (attestations[0] is None) is not (attestations[1] is None):
            raise ValueError("both verification role attestations are required together")
        if all(item is not None for item in attestations):
            assert self.integration_verification is not None
            assert self.tco_qa_verification is not None
            if (
                self.integration_verification.signer_role
                is not SigningRole.INTEGRATION_EVIDENCE_RUNNER
                or self.tco_qa_verification.signer_role is not SigningRole.TCO_QA
            ):
                raise ValueError("verification attestations occupy the wrong role slots")
            if any(
                item.subject_tree_sha256 != self.tree_sha256
                or item.verification_bundle_sha256 != self.verification.bundle_sha256
                for item in (
                    self.integration_verification,
                    self.tco_qa_verification,
                )
            ):
                raise ValueError("verification attestation binding mismatch")
            expected_runner_bundle = (
                "0" * 64
                if self.verified_runner_evidence is None
                else self.verified_runner_evidence.bundle_sha256
            )
            expected_runner_authority = (
                "0" * 64
                if self.verified_runner_policy is None
                or self.verified_runner_trust_store is None
                or self.verified_runner_authority_pins is None
                else hash_verified_runner_authority(
                    self.verified_runner_policy,
                    self.verified_runner_trust_store,
                    self.verified_runner_authority_pins,
                )
            )
            if any(
                item.verified_runner_bundle_sha256 != expected_runner_bundle
                or item.verified_runner_authority_sha256
                != expected_runner_authority
                for item in (
                    self.integration_verification,
                    self.tco_qa_verification,
                )
            ):
                raise ValueError(
                    "verification attestations do not bind the retained runner contract"
                )
            latest_execution = max(
                item.executed_at for item in self.verification.facts
            )
            if self.verified_runner_evidence is not None:
                consumption_receipt = (
                    self.verification.verified_runner_consumption_receipt
                )
                if consumption_receipt is None:
                    raise ValueError(
                        "verified runner evidence requires its consumption receipt"
                    )
                latest_execution = max(
                    latest_execution,
                    self.verified_runner_evidence.runner_attestation.issued_at,
                    consumption_receipt.consumed_at,
                    consumption_receipt.clock_attestation.issued_at,
                    *(record.result.ended_at for record in self.verified_runner_evidence.records),
                )
            if any(
                item.issued_at < latest_execution
                or item.issued_at > self.assembled_at
                or item.expires_at < self.expires_at
                for item in (
                    self.integration_verification,
                    self.tco_qa_verification,
                )
            ):
                raise ValueError(
                    "verification attestations must follow execution and precede assembly"
                )
        if any(item.executed_at > self.assembled_at for item in self.verification.facts):
            raise ValueError("verification cannot be executed after manifest assembly")
        if any(item.not_after < self.expires_at for item in self.verification.facts):
            raise ValueError("manifest cannot outlive verification evidence")
        if self.authority_exclusions != REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS:
            raise ValueError("candidate manifest must contain the exact authority exclusions")
        if self.manifest_sha256 != hash_repository_candidate_manifest(self):
            raise ValueError("candidate manifest hash mismatch")
        return self


class RepositoryAcceptanceTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    human_approver: Ed25519VerificationKey
    integration_evidence_runner: Ed25519VerificationKey
    tco_qa: Ed25519VerificationKey

    @model_validator(mode="after")
    def require_human_role(self) -> Self:
        expected = (
            (self.human_approver, SigningRole.HUMAN_APPROVER),
            (
                self.integration_evidence_runner,
                SigningRole.INTEGRATION_EVIDENCE_RUNNER,
            ),
            (self.tco_qa, SigningRole.TCO_QA),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("repository acceptance trust-store role mismatch")
        if len({key.key_id_sha256 for key, _ in expected}) != len(expected):
            raise ValueError("repository acceptance role keys must be distinct")
        return self


class RepositoryVerificationRequirement(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    check: RepositoryVerificationCheck
    command_sha256: Sha256
    tool_name: Slug
    tool_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$",
    )
    minimum_assertions: int = Field(ge=1, le=100_000_000)


class RepositoryAcceptancePolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    policy_id: Slug
    scope_profile: RepositoryScopeProfile = SCOPE_PROFILE
    scope_paths_sha256: Sha256
    expected_previous_candidate_record_sha256: Sha256
    human_approver_key_id_sha256: Sha256
    integration_evidence_runner_key_id_sha256: Sha256
    tco_qa_key_id_sha256: Sha256
    verification_requirements: tuple[RepositoryVerificationRequirement, ...] = Field(
        min_length=14, max_length=14
    )
    required_authority_exclusions: tuple[RepositoryAuthorityExclusion, ...] = Field(
        min_length=9, max_length=9
    )
    maximum_manifest_ttl_seconds: int = Field(ge=1, le=2_592_000)
    maximum_verification_age_seconds: int = Field(ge=1, le=2_592_000)
    maximum_verification_attestation_ttl_seconds: int = Field(
        ge=1, le=2_592_000
    )
    maximum_acceptance_ttl_seconds: int = Field(ge=1, le=2_592_000)

    @model_validator(mode="after")
    def require_fixed_contract(self) -> Self:
        if self.scope_paths_sha256 != _SCOPE_PATHS_BY_PROFILE.get(
            self.scope_profile
        ):
            raise ValueError("policy does not bind a registered repository scope")
        if (
            tuple(item.check for item in self.verification_requirements)
            != REQUIRED_REPOSITORY_VERIFICATION_CHECKS
        ):
            raise ValueError("policy must require the exact repository verification checks")
        if tuple(
            item.minimum_assertions for item in self.verification_requirements
        ) != tuple(
            REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[check]
            for check in REQUIRED_REPOSITORY_VERIFICATION_CHECKS
        ):
            raise ValueError(
                "policy must require the code-defined repository assertion floors"
            )
        if self.required_authority_exclusions != REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS:
            raise ValueError("policy must require every repository authority exclusion")
        return self


class RepositoryAcceptanceAuthorityPins(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    expected_manifest_sha256: Sha256
    expected_policy_sha256: Sha256
    expected_trust_store_sha256: Sha256
    expected_verification_authority_sha256: Sha256
    expected_verified_runner_authority_sha256: Sha256 = "0" * 64
    expected_current_receipt_sha256: Sha256
    expected_current_revision: int = Field(ge=1, le=1_000_000_000)


class HumanRepositoryAcceptance(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    receipt_id: Slug
    manifest_sha256: Sha256
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    revision: int = Field(ge=1, le=1_000_000_000)
    predecessor_receipt_sha256: Sha256
    decision: HumanRepositoryDecision
    condition_ids: tuple[Slug, ...] = Field(default=(), max_length=20)
    issued_at: datetime
    expires_at: datetime
    approver_issuer: str = Field(min_length=1, max_length=120)
    approver_key_id_sha256: Sha256
    receipt_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "repository acceptance timestamp")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("repository acceptance expiry must follow issuance")
        if self.revision == 1 and self.predecessor_receipt_sha256 != "0" * 64:
            raise ValueError("the first acceptance receipt must use the zero predecessor")
        if self.revision > 1 and self.predecessor_receipt_sha256 == "0" * 64:
            raise ValueError("a later acceptance receipt must bind its predecessor")
        if tuple(sorted(self.condition_ids)) != self.condition_ids or len(
            set(self.condition_ids)
        ) != len(self.condition_ids):
            raise ValueError("condition IDs must be uniquely sorted")
        if self.decision is HumanRepositoryDecision.GO and self.condition_ids:
            raise ValueError("GO cannot retain unresolved conditions")
        if self.decision is HumanRepositoryDecision.CONDITIONAL and not self.condition_ids:
            raise ValueError("CONDITIONAL requires at least one condition ID")
        if self.receipt_sha256 != hash_human_repository_acceptance(self):
            raise ValueError("repository acceptance receipt hash mismatch")
        return self


class RepositoryAcceptanceReceiptChain(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    receipts: tuple[HumanRepositoryAcceptance, ...] = Field(
        default=(), max_length=999
    )

    @model_validator(mode="after")
    def validate_chain_prefix(self) -> Self:
        if tuple(item.revision for item in self.receipts) != tuple(
            range(1, len(self.receipts) + 1)
        ):
            raise ValueError("repository acceptance receipt revisions are not contiguous")
        if len({item.receipt_id for item in self.receipts}) != len(self.receipts):
            raise ValueError("repository acceptance receipt IDs must be unique")
        for index, item in enumerate(self.receipts):
            expected_predecessor = (
                "0" * 64 if index == 0 else self.receipts[index - 1].receipt_sha256
            )
            if item.predecessor_receipt_sha256 != expected_predecessor or (
                index > 0 and item.issued_at <= self.receipts[index - 1].issued_at
            ):
                raise ValueError("repository acceptance receipt chain is invalid")
        return self


class RepositoryAcceptanceAuthorityBundle(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    manifest: RepositoryCandidateManifest
    policy: RepositoryAcceptancePolicy
    trust_store: RepositoryAcceptanceTrustStore
    authority_pins: RepositoryAcceptanceAuthorityPins
    verified_runner_policy: VerifiedRunnerPolicy | None = None
    verified_runner_trust_store: VerifiedRunnerTrustStore | None = None
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None = None
    receipt_chain: tuple[HumanRepositoryAcceptance, ...] = Field(
        default=(), max_length=1_000
    )
    human_acceptance: HumanRepositoryAcceptance
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        policy_hash = hash_repository_acceptance_policy(self.policy)
        trust_hash = hash_repository_acceptance_trust_store(self.trust_store)
        verification_authority_hash = hash_repository_verification_authority(
            self.policy, self.trust_store
        )
        runner_parts = (
            self.verified_runner_policy,
            self.verified_runner_trust_store,
            self.verified_runner_authority_pins,
        )
        uses_v2 = self.manifest.verified_runner_evidence is not None
        if uses_v2 != all(item is not None for item in runner_parts) or (
            any(item is not None for item in runner_parts)
            and not all(item is not None for item in runner_parts)
        ):
            raise ValueError("repository runner authority packet is incomplete")
        runner_authority_hash = "0" * 64
        if uses_v2:
            assert self.verified_runner_policy is not None
            assert self.verified_runner_trust_store is not None
            assert self.verified_runner_authority_pins is not None
            runner_authority_hash = hash_verified_runner_authority(
                self.verified_runner_policy,
                self.verified_runner_trust_store,
                self.verified_runner_authority_pins,
            )
            if (
                self.verified_runner_policy
                != self.manifest.verified_runner_policy
                or self.verified_runner_trust_store
                != self.manifest.verified_runner_trust_store
                or self.verified_runner_authority_pins
                != self.manifest.verified_runner_authority_pins
            ):
                raise ValueError("runner authority differs from manifest contract")
        if (
            self.authority_pins.expected_manifest_sha256
            != self.manifest.manifest_sha256
            or self.authority_pins.expected_policy_sha256 != policy_hash
            or self.authority_pins.expected_trust_store_sha256 != trust_hash
            or self.authority_pins.expected_verification_authority_sha256
            != verification_authority_hash
            or self.authority_pins.expected_verified_runner_authority_sha256
            != runner_authority_hash
            or self.human_acceptance.manifest_sha256
            != self.manifest.manifest_sha256
            or self.human_acceptance.policy_sha256 != policy_hash
            or self.human_acceptance.trust_store_sha256 != trust_hash
            or self.authority_pins.expected_current_receipt_sha256
            != self.human_acceptance.receipt_sha256
            or self.authority_pins.expected_current_revision
            != self.human_acceptance.revision
        ):
            raise ValueError("repository acceptance authority bundle binding mismatch")
        receipts = (*self.receipt_chain, self.human_acceptance)
        if tuple(item.revision for item in receipts) != tuple(
            range(1, len(receipts) + 1)
        ):
            raise ValueError("repository acceptance receipt revisions are not contiguous")
        if len(receipts) != self.human_acceptance.revision:
            raise ValueError("repository acceptance current revision omits history")
        if len({item.receipt_id for item in receipts}) != len(receipts):
            raise ValueError("repository acceptance receipt IDs must be unique")
        for index, item in enumerate(receipts):
            expected_predecessor = (
                "0" * 64 if index == 0 else receipts[index - 1].receipt_sha256
            )
            if (
                item.predecessor_receipt_sha256 != expected_predecessor
                or item.manifest_sha256 != self.manifest.manifest_sha256
                or item.policy_sha256 != policy_hash
                or item.trust_store_sha256 != trust_hash
                or (
                    index > 0
                    and item.issued_at <= receipts[index - 1].issued_at
                )
            ):
                raise ValueError("repository acceptance receipt chain is invalid")
        if self.bundle_sha256 != hash_repository_acceptance_authority_bundle(self):
            raise ValueError("repository acceptance authority bundle hash mismatch")
        return self


class RepositoryAcceptanceReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evaluated_at: datetime
    manifest_sha256: Sha256
    expected_tree_sha256: Sha256
    observed_tree_sha256: Sha256
    verification_bundle_sha256: Sha256
    decision: RepositoryAcceptanceDecision
    reasons: tuple[RepositoryAcceptanceReason, ...]
    local_integration_accepted: bool
    next_gate: RepositoryRestartGate
    first_external_gate: Literal[RepositoryRestartGate.RIGHTS_EVIDENCE] = (
        RepositoryRestartGate.RIGHTS_EVIDENCE
    )
    required_inputs: tuple[RepositoryRequiredInput, ...] = Field(min_length=1, max_length=1)
    authority: Literal["none"] = "none"
    external_mutation_authorized: Literal[False] = False
    public_release_authorized: Literal[False] = False
    production_write_authorized: Literal[False] = False
    scale_authorized: Literal[False] = False
    report_sha256: Sha256

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "repository acceptance evaluation timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        accepted = self.decision is RepositoryAcceptanceDecision.ACCEPTED
        if self.local_integration_accepted is not accepted:
            raise ValueError("local acceptance flag does not match decision")
        if accepted:
            expected_gate = RepositoryRestartGate.RIGHTS_EVIDENCE
            expected_input = RepositoryRequiredInput.CURRENT_RIGHTS_DECISION_RECORDS
        elif set(self.reasons).intersection(_LOCAL_VERIFICATION_REASONS):
            expected_gate = RepositoryRestartGate.LOCAL_VERIFICATION
            expected_input = (
                RepositoryRequiredInput.CURRENT_SIGNED_VERIFICATION_BUNDLE
            )
        elif set(self.reasons).intersection(_ACCEPTANCE_CHAIN_REASONS):
            expected_gate = RepositoryRestartGate.REPOSITORY_ACCEPTANCE
            expected_input = (
                RepositoryRequiredInput.CURRENT_PINNED_ACCEPTANCE_CHAIN
            )
        else:
            expected_gate = RepositoryRestartGate.REPOSITORY_ACCEPTANCE
            expected_input = (
                RepositoryRequiredInput.HUMAN_SIGNED_REPOSITORY_ACCEPTANCE
            )
        if self.next_gate is not expected_gate or self.required_inputs != (expected_input,):
            raise ValueError("next gate or required input does not match decision")
        if tuple(sorted(set(self.reasons), key=lambda item: item.value)) != self.reasons:
            raise ValueError("repository acceptance reasons must be unique and sorted")
        if self.report_sha256 != hash_repository_acceptance_report(self):
            raise ValueError("repository acceptance report hash mismatch")
        return self


def build_repository_inventory(repo_root: Path) -> tuple[RepositoryFileDigest, ...]:
    """Hash the code-defined candidate scope without following symbolic links."""

    try:
        root, root_descriptor = _open_repository_root_no_follow(repo_root)
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            "repository root and every ancestor must be real directories"
        ) from exc
    try:
        first, first_directories = _collect_repository_inventory(
            root_descriptor
        )
        second, second_directories = _collect_repository_inventory(
            root_descriptor
        )
        if first != second or first_directories != second_directories:
            raise RepositoryAcceptanceInputError(
                "repository scope changed during inventory collection"
            )
        _validate_repository_directories(root_descriptor, second_directories)
        root_before = os.fstat(root_descriptor)
        root_after = os.stat(root, follow_symlinks=False)
        if (root_before.st_dev, root_before.st_ino) != (
            root_after.st_dev,
            root_after.st_ino,
        ):
            raise RepositoryAcceptanceInputError(
                "repository root identity changed during inventory collection"
            )
        return first
    finally:
        os.close(root_descriptor)


def _open_repository_root_no_follow(repo_root: Path) -> tuple[Path, int]:
    root = Path(os.path.abspath(os.fspath(repo_root)))
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root.anchor, flags)
    try:
        for component in root.parts[1:]:
            next_descriptor = os.open(
                component,
                flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return root, descriptor
    except Exception:
        os.close(descriptor)
        raise


def _collect_repository_inventory(
    root_descriptor: int,
) -> tuple[tuple[RepositoryFileDigest, ...], tuple[tuple[str, int, int], ...]]:
    allowed_top_level = {
        PurePosixPath(item).parts[0]
        for item in (*_SCOPE_ROOT_FILES, *_SCOPE_ROOT_DIRECTORIES)
    } | _IGNORED_TOP_LEVEL
    try:
        unexpected = sorted(
            item.name
            for item in os.scandir(root_descriptor)
            if item.name not in allowed_top_level
        )
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            "repository root could not be enumerated safely"
        ) from exc
    if unexpected:
        raise RepositoryAcceptanceInputError(
            "unexpected top-level repository entries: " + ", ".join(unexpected)
        )

    paths: list[str] = []
    directory_identities: dict[str, tuple[int, int]] = {}
    for relative in _SCOPE_ROOT_FILES:
        paths.append(relative)
    for relative in _SCOPE_ROOT_DIRECTORIES:
        before = len(paths)
        paths.extend(
            _walk_repository_directory(
                root_descriptor,
                PurePosixPath(relative),
                ignore_site_runtime=relative == "site",
                identities=directory_identities,
            )
        )
        if len(paths) == before:
            raise RepositoryAcceptanceInputError(
                f"required repository directory is empty: {relative}"
            )

    entries = tuple(
        sorted(
            (_digest_file(root_descriptor, path) for path in paths),
            key=lambda item: item.path,
        )
    )
    entry_paths = tuple(item.path for item in entries)
    if len(entry_paths) != len(set(entry_paths)):
        raise RepositoryAcceptanceInputError("repository scope produced duplicate paths")
    casefold_paths = tuple(item.casefold() for item in entry_paths)
    if len(casefold_paths) != len(set(casefold_paths)):
        raise RepositoryAcceptanceInputError(
            "repository scope contains a Unicode/case-colliding path"
        )
    if PREVIOUS_CANDIDATE_RECORD not in set(entry_paths):
        raise RepositoryAcceptanceInputError("previous candidate record is outside repository scope")
    identities = tuple(
        (path, identity[0], identity[1])
        for path, identity in sorted(directory_identities.items())
    )
    _validate_repository_directories(root_descriptor, identities)
    return entries, identities


def _walk_repository_directory(
    root_descriptor: int,
    relative: PurePosixPath,
    *,
    ignore_site_runtime: bool,
    identities: dict[str, tuple[int, int]],
) -> tuple[str, ...]:
    try:
        descriptor = _open_relative_directory(root_descriptor, relative)
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            f"required repository directory is missing or unsafe: {relative}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        identities[relative.as_posix()] = (metadata.st_dev, metadata.st_ino)
        children = sorted(os.scandir(descriptor), key=lambda item: item.name)
        paths: list[str] = []
        for child in children:
            child_relative = relative / child.name
            ignored_directory = child.name in _IGNORED_DIRECTORY_NAMES or (
                ignore_site_runtime
                and child.name in _IGNORED_SITE_DIRECTORY_NAMES
            )
            if ignored_directory:
                continue
            try:
                child_metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise RepositoryAcceptanceInputError(
                    f"repository scope entry changed: {child_relative}"
                ) from exc
            if stat.S_ISLNK(child_metadata.st_mode):
                raise RepositoryAcceptanceInputError(
                    f"symbolic link is forbidden in repository scope: {child_relative}"
                )
            if stat.S_ISDIR(child_metadata.st_mode):
                paths.extend(
                    _walk_repository_directory(
                        root_descriptor,
                        child_relative,
                        ignore_site_runtime=ignore_site_runtime,
                        identities=identities,
                    )
                )
            elif child.name.endswith((".pyc", ".pyo")):
                continue
            elif stat.S_ISREG(child_metadata.st_mode):
                paths.append(child_relative.as_posix())
            else:
                raise RepositoryAcceptanceInputError(
                    f"repository scope entry is not a regular file: {child_relative}"
                )
        return tuple(paths)
    finally:
        os.close(descriptor)


def _validate_repository_directories(
    root_descriptor: int,
    identities: tuple[tuple[str, int, int], ...],
) -> None:
    for relative, expected_device, expected_inode in identities:
        try:
            descriptor = _open_relative_directory(
                root_descriptor, PurePosixPath(relative)
            )
        except OSError as exc:
            raise RepositoryAcceptanceInputError(
                f"repository directory changed while hashing: {relative}"
            ) from exc
        try:
            observed = os.fstat(descriptor)
            if (observed.st_dev, observed.st_ino) != (
                expected_device,
                expected_inode,
            ):
                raise RepositoryAcceptanceInputError(
                    f"repository directory changed while hashing: {relative}"
                )
        finally:
            os.close(descriptor)


def _open_relative_directory(
    root_descriptor: int, relative: PurePosixPath
) -> int:
    directory_descriptor = os.dup(root_descriptor)
    try:
        for component in relative.parts:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_descriptor = os.open(
                component, flags, dir_fd=directory_descriptor
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return directory_descriptor
    except Exception:
        os.close(directory_descriptor)
        raise


def build_repository_verification_bundle(
    tree_sha256: str,
    facts: tuple[RepositoryVerificationFact, ...],
    *,
    verified_runner_consumption_receipt: (
        VerifiedRunnerConsumptionReceipt | None
    ) = None,
) -> RepositoryVerificationEvidenceBundle:
    validated_facts = tuple(_copy(item, RepositoryVerificationFact) for item in facts)
    values = {
        "schema_version": "2.0",
        "subject_tree_sha256": tree_sha256,
        "facts": validated_facts,
        "verified_runner_consumption_receipt": (
            verified_runner_consumption_receipt
        ),
    }
    provisional = RepositoryVerificationEvidenceBundle.model_construct(
        **values, bundle_sha256="0" * 64
    )
    return RepositoryVerificationEvidenceBundle(
        **values,
        bundle_sha256=hash_repository_verification_bundle(provisional),
    )


def build_repository_verification_from_verified_runner_evidence(
    evidence: VerifiedRunnerEvidenceBundle,
    *,
    consumption_receipt: VerifiedRunnerConsumptionReceipt,
) -> RepositoryVerificationEvidenceBundle:
    """Derive P18 summary facts while retaining the full P19 evidence in manifest.

    This is a structural mapping only.  It does not authenticate the runner,
    image, advisory snapshot, or freshness; P18 evaluation always invokes the
    packet-external P19 authority verifier before accepting these facts.
    """

    try:
        evidence = VerifiedRunnerEvidenceBundle.model_validate(
            evidence.model_dump()
        )
        consumption_receipt = VerifiedRunnerConsumptionReceipt.model_validate(
            consumption_receipt.model_dump()
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise RepositoryAcceptanceInputError(
            "invalid retained verified runner evidence"
        ) from exc
    facts: list[RepositoryVerificationFact] = []
    for record in evidence.records:
        spec = record.spec
        result = record.result
        succeeded = (
            result.termination_reason.value == "exited"
            and result.exit_code == 0
            and result.failures == 0
            and result.skipped == 0
            and not result.stdout_truncated
            and not result.stderr_truncated
        )
        facts.append(
            RepositoryVerificationFact(
                check=RepositoryVerificationCheck(spec.check.value),
                subject_tree_sha256=evidence.subject_tree_sha256,
                command_argv=spec.command_argv,
                working_directory="repository-root",
                environment_sha256=spec.environment_sha256,
                network_mode=RepositoryVerificationNetworkMode(
                    spec.network_mode.value
                ),
                interpreter_sha256=spec.interpreter_sha256,
                import_closure_sha256=spec.import_closure_sha256,
                command_sha256=hash_repository_verification_command(
                    command_argv=spec.command_argv,
                    working_directory="repository-root",
                    environment_sha256=spec.environment_sha256,
                    network_mode=RepositoryVerificationNetworkMode(
                        spec.network_mode.value
                    ),
                    interpreter_sha256=spec.interpreter_sha256,
                    import_closure_sha256=spec.import_closure_sha256,
                ),
                tool_name=result.tool_name,
                tool_version=result.tool_version,
                provenance=(
                    RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
                ),
                executed_at=result.started_at,
                not_after=min(
                    result.not_after,
                    evidence.challenge.expires_at,
                    evidence.image_attestation.expires_at,
                    evidence.advisory_snapshot.not_after,
                    evidence.clock_attestation.expires_at,
                    evidence.runner_attestation.expires_at,
                ),
                assertions_executed=result.assertions_executed,
                failures=(
                    result.failures
                    if result.failures or result.skipped
                    else (0 if succeeded else 1)
                ),
                skipped=result.skipped,
                exit_code=result.exit_code if result.exit_code is not None else 255,
                output_sha256=hash_verified_check_output(result),
            )
        )
    values = {
        "schema_version": "2.0",
        "subject_tree_sha256": evidence.subject_tree_sha256,
        "facts": tuple(facts),
        "verified_runner_consumption_receipt": consumption_receipt,
    }
    provisional = RepositoryVerificationEvidenceBundle.model_construct(
        **values, bundle_sha256="0" * 64
    )
    return RepositoryVerificationEvidenceBundle(
        **values,
        bundle_sha256=hash_repository_verification_bundle(provisional),
    )


def run_repository_verification(
    repo_root: Path,
    *,
    workflow_verifier: Path,
    fact_ttl_seconds: int = 86_400,
    maximum_output_bytes: int = _VERIFICATION_OUTPUT_LIMIT_BYTES,
) -> RepositoryVerificationEvidenceBundle:
    """Run the fixed P18 checks under a network-restricted local sandbox.

    This function creates unsigned verification facts only.  Integration and
    TCO/QA attestations remain separate signing steps, and Human acceptance is
    never created here.
    """

    if sys.platform != "darwin":
        raise RepositoryAcceptanceInputError(
            "verified local execution currently requires macOS sandbox-exec"
        )
    if not 60 <= fact_ttl_seconds <= 604_800:
        raise RepositoryAcceptanceInputError(
            "verification fact TTL must be between 60 and 604800 seconds"
        )
    if not 65_536 <= maximum_output_bytes <= 16 * 1024 * 1024:
        raise RepositoryAcceptanceInputError(
            "verification output limit must be between 65536 and 16777216 bytes"
        )

    root = Path(os.path.abspath(os.fspath(repo_root)))
    workflow = Path(os.path.abspath(os.fspath(workflow_verifier)))
    tools = _repository_verification_tool_paths(workflow)
    initial_files = build_repository_inventory(root)
    tree_sha256 = hash_repository_tree(initial_files)
    work = _prepare_repository_verification_work(root)
    interpreter_sha256 = _repository_verification_interpreter_sha256(tools)

    lock_descriptor = os.open(
        work / "runner.lock",
        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    lock_metadata = os.fstat(lock_descriptor)
    if not stat.S_ISREG(lock_metadata.st_mode) or lock_metadata.st_nlink != 1:
        os.close(lock_descriptor)
        raise RepositoryAcceptanceInputError(
            "verification runner lock is not one regular file"
        )
    run_work: Path | None = None
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RepositoryAcceptanceInputError(
                "another repository verification run is active"
            ) from exc

        run_work = Path(tempfile.mkdtemp(prefix="run-", dir=work))
        os.chmod(run_work, 0o700)
        for name in ("home", "tmp", "cache"):
            selected = run_work / name
            selected.mkdir(mode=0o700)
            os.chmod(selected, 0o700)
        environment = _repository_verification_environment(
            root, run_work, tools
        )
        environment_sha256 = _canonical_sha256(environment)
        runtime_closure_sha256 = _repository_verification_runtime_closure_sha256(
            root, tools
        )
        facts: list[RepositoryVerificationFact] = []
        for check in REQUIRED_REPOSITORY_VERIFICATION_CHECKS:
            network_mode = (
                RepositoryVerificationNetworkMode.LOOPBACK_ONLY
                if check is RepositoryVerificationCheck.WEB_TESTS
                else RepositoryVerificationNetworkMode.DISABLED
            )
            profile = (
                _LOOPBACK_ONLY_SANDBOX_PROFILE
                if network_mode is RepositoryVerificationNetworkMode.LOOPBACK_ONLY
                else _NETWORK_DISABLED_SANDBOX_PROFILE
            )
            command_argv = _repository_verification_check_command(
                check,
                root=root,
                work=run_work,
                tools=tools,
                sandbox_profile=profile,
                maximum_output_bytes=maximum_output_bytes,
            )
            executed_at = datetime.now(timezone.utc)
            stdout, stderr, returncode = _execute_repository_verification_command(
                command_argv,
                cwd=root,
                environment=environment,
                timeout_seconds=(
                    _REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[check] + 30
                ),
                maximum_output_bytes=maximum_output_bytes,
            )
            result = _parse_repository_verification_check_result(
                check,
                stdout=stdout,
                stderr=stderr,
                returncode=returncode,
            )
            assertions = result["assertions_executed"]
            failures = result["failures"]
            minimum = REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[check]
            if assertions < minimum:
                assertions = max(assertions, 1)
                failures = max(failures, 1)
            output_sha256 = hashlib.sha256(
                stdout + b"\x00" + stderr
            ).hexdigest()
            facts.append(
                RepositoryVerificationFact(
                    check=check,
                    subject_tree_sha256=tree_sha256,
                    command_argv=command_argv,
                    working_directory="repository-root",
                    environment_sha256=environment_sha256,
                    network_mode=network_mode,
                    interpreter_sha256=interpreter_sha256,
                    import_closure_sha256=runtime_closure_sha256,
                    command_sha256=hash_repository_verification_command(
                        command_argv=command_argv,
                        working_directory="repository-root",
                        environment_sha256=environment_sha256,
                        network_mode=network_mode,
                        interpreter_sha256=interpreter_sha256,
                        import_closure_sha256=runtime_closure_sha256,
                    ),
                    tool_name=result["tool_name"],
                    tool_version=result["tool_version"],
                    provenance=(
                        RepositoryVerificationProvenance.LOCAL_DIAGNOSTIC_RUN
                    ),
                    executed_at=executed_at,
                    not_after=executed_at + timedelta(seconds=fact_ttl_seconds),
                    assertions_executed=assertions,
                    failures=min(failures, assertions),
                    skipped=min(result["skipped"], assertions - min(failures, assertions)),
                    exit_code=result["exit_code"],
                    output_sha256=output_sha256,
                )
            )

        final_files = build_repository_inventory(root)
        final_runtime_closure = (
            _repository_verification_runtime_closure_sha256(root, tools)
        )
        if final_files != initial_files:
            raise RepositoryAcceptanceInputError(
                "repository scope changed during verification"
            )
        if final_runtime_closure != runtime_closure_sha256:
            raise RepositoryAcceptanceInputError(
                "verification runtime closure changed during execution"
            )
        return build_repository_verification_bundle(
            tree_sha256, tuple(facts)
        )
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)
            if run_work is not None and run_work.parent == work:
                shutil.rmtree(run_work, ignore_errors=True)


def run_repository_verification_check(
    check: RepositoryVerificationCheck,
    repo_root: Path,
    work_dir: Path,
    *,
    python_executable: Path,
    uv_executable: Path,
    gitleaks_executable: Path,
    npm_executable: Path,
    node_executable: Path,
    workflow_verifier: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    """Execute one sandboxed child check and return a hash-only result."""

    root = Path(os.path.abspath(os.fspath(repo_root)))
    work = Path(os.path.abspath(os.fspath(work_dir)))
    expected_work = root / _VERIFICATION_RUNNER_WORK
    try:
        work_metadata = work.lstat()
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            "verification work directory is unavailable"
        ) from exc
    if (
        work.parent != expected_work
        or not work.name.startswith("run-")
        or not stat.S_ISDIR(work_metadata.st_mode)
        or stat.S_ISLNK(work_metadata.st_mode)
        or work_metadata.st_uid != os.geteuid()
        or work_metadata.st_mode & 0o077
    ):
        raise RepositoryAcceptanceInputError(
            "verification work directory is outside the fixed local boundary"
        )
    if not 65_536 <= maximum_output_bytes <= 16 * 1024 * 1024:
        raise RepositoryAcceptanceInputError("invalid verification output limit")
    selected_tools = {
        "python": _require_verification_tool(python_executable),
        "uv": _require_verification_tool(uv_executable),
        "gitleaks": _require_verification_tool(gitleaks_executable),
        "npm": _require_verification_tool(npm_executable),
        "node": _require_verification_tool(node_executable),
        "workflow": _require_verification_tool(workflow_verifier),
    }
    if not os.path.samefile(selected_tools["python"], sys.executable):
        raise RepositoryAcceptanceInputError(
            "internal verification check must use the active interpreter"
        )
    expected_environment = _repository_verification_environment(
        root, work, selected_tools
    )
    observed_environment = dict(os.environ)
    darwin_text_encoding = observed_environment.pop(
        "__CF_USER_TEXT_ENCODING", ""
    )
    if (
        observed_environment != expected_environment
        or not re.fullmatch(
            r"0x[0-9A-F]+:0x[0-9A-F]+:0x[0-9A-F]+",
            darwin_text_encoding,
        )
    ):
        raise RepositoryAcceptanceInputError(
            "internal verification check did not receive the sanitized environment"
        )
    check_work = work / check.value
    if check_work.is_symlink():
        raise RepositoryAcceptanceInputError(
            "verification check work path is a symbolic link"
        )
    if check_work.exists():
        shutil.rmtree(check_work)
    check_work.mkdir(mode=0o700)

    if check in {
        RepositoryVerificationCheck.PYTHON_BASE,
        RepositoryVerificationCheck.PYTHON_TRACTION,
        RepositoryVerificationCheck.PYTHON_PRODUCTION_CONSUMER,
        RepositoryVerificationCheck.CONTRACT_STORAGE_AUDIT,
        RepositoryVerificationCheck.TCO_QA_AUDIT,
    }:
        result = _run_repository_pytest_check(
            check,
            root=root,
            work=check_work,
            python=selected_tools["python"],
            maximum_output_bytes=maximum_output_bytes,
        )
    elif check is RepositoryVerificationCheck.SCHEMA_DETERMINISM:
        result = _run_repository_schema_check(
            root=root,
            work=check_work,
            python=selected_tools["python"],
            maximum_output_bytes=maximum_output_bytes,
        )
    elif check is RepositoryVerificationCheck.BLOCKED_FIXTURE_DETERMINISM:
        result = _run_repository_fixture_check(
            root=root,
            work=check_work,
            python=selected_tools["python"],
            maximum_output_bytes=maximum_output_bytes,
        )
    elif check is RepositoryVerificationCheck.WEB_TESTS:
        result = _run_repository_web_tests_check(
            root=root,
            node=selected_tools["node"],
            maximum_output_bytes=maximum_output_bytes,
        )
    elif check is RepositoryVerificationCheck.WEB_LINT:
        result = _run_repository_web_lint_check(
            root=root,
            node=selected_tools["node"],
            maximum_output_bytes=maximum_output_bytes,
        )
    else:
        command, tool_name, tool_version, assertions = (
            _repository_simple_check_command(
                check, root=root, tools=selected_tools
            )
        )
        stdout, stderr, returncode = _execute_repository_verification_command(
            command,
            cwd=root,
            environment=dict(os.environ),
            timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[check],
            maximum_output_bytes=maximum_output_bytes,
            start_new_session=True,
        )
        failures = int(returncode != 0)
        skipped = 0
        if check is RepositoryVerificationCheck.DEPENDENCY_AUDIT:
            stderr += (
                b"\nunsigned or stale offline advisory cache is not acceptance evidence"
            )
            failures = 1
            returncode = 3
        result = {
            "assertions_executed": max(assertions, 1),
            "failures": failures,
            "skipped": skipped,
            "exit_code": returncode,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "underlying_output_sha256": hashlib.sha256(
                stdout + b"\x00" + stderr
            ).hexdigest(),
        }
    return {"check": check.value, **result}


def _repository_verification_tool_paths(
    workflow_verifier: Path,
) -> dict[str, Path]:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.exists():
        raise RepositoryAcceptanceInputError(
            "sandbox-exec is required for verified local execution"
        )
    located = {
        "sandbox": sandbox,
        "python": Path(sys.executable).absolute(),
        "uv": Path(shutil.which("uv") or ""),
        "gitleaks": Path(shutil.which("gitleaks") or ""),
        "npm": Path(shutil.which("npm") or ""),
        "node": Path(shutil.which("node") or ""),
        "workflow": workflow_verifier,
    }
    return {
        name: _require_verification_tool(path)
        for name, path in located.items()
    }


def _require_verification_tool(path: Path) -> Path:
    selected = Path(os.path.abspath(os.fspath(path)))
    try:
        metadata = selected.stat()
        resolved = selected.resolve(strict=True)
        resolved_metadata = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise RepositoryAcceptanceInputError(
            f"verification tool is unavailable: {selected.name or 'unknown'}"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or not stat.S_ISREG(
        resolved_metadata.st_mode
    ):
        raise RepositoryAcceptanceInputError(
            f"verification tool is not a regular file: {selected.name}"
        )
    return selected


def _prepare_repository_verification_work(root: Path) -> Path:
    selected_root, root_descriptor = _open_repository_root_no_follow(root)
    directory_descriptor = os.dup(root_descriptor)
    os.close(root_descriptor)
    try:
        for component in _VERIFICATION_RUNNER_WORK.parts:
            try:
                os.mkdir(component, mode=0o700, dir_fd=directory_descriptor)
            except FileExistsError:
                pass
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            next_descriptor = os.open(
                component, flags, dir_fd=directory_descriptor
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        metadata = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
        ):
            raise RepositoryAcceptanceInputError(
                "verification work directory has an unsafe owner or type"
            )
        os.fchmod(directory_descriptor, 0o700)
        return selected_root / _VERIFICATION_RUNNER_WORK
    except Exception:
        os.close(directory_descriptor)
        raise
    finally:
        try:
            os.close(directory_descriptor)
        except OSError:
            pass


def _repository_verification_environment(
    root: Path,
    work: Path,
    tools: dict[str, Path],
) -> dict[str, str]:
    path_entries: list[str] = []
    for candidate in (
        tools["python"].parent,
        tools["uv"].parent,
        tools["gitleaks"].parent,
        tools["npm"].parent,
        tools["node"].parent,
        Path("/usr/bin"),
        Path("/bin"),
        root / "site" / "node_modules" / ".bin",
    ):
        serialized = os.fspath(candidate)
        if serialized not in path_entries:
            path_entries.append(serialized)
    return {
        "CI": "1",
        "HOME": os.fspath(work / "home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(path_entries),
        "PIP_NO_INDEX": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONSAFEPATH": "1",
        "TMPDIR": os.fspath(work / "tmp"),
        "TZ": "UTC",
        "UV_OFFLINE": "1",
        "XDG_CACHE_HOME": os.fspath(work / "cache"),
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_offline": "true",
        "npm_config_update_notifier": "false",
    }


def _repository_verification_check_command(
    check: RepositoryVerificationCheck,
    *,
    root: Path,
    work: Path,
    tools: dict[str, Path],
    sandbox_profile: str,
    maximum_output_bytes: int,
) -> tuple[str, ...]:
    return (
        os.fspath(tools["sandbox"]),
        "-p",
        sandbox_profile,
        os.fspath(tools["python"]),
        "-I",
        "-B",
        "-m",
        "saas_preflight.cli",
        "_run-repository-check",
        check.value,
        "--repo-root",
        os.fspath(root),
        "--work-dir",
        os.fspath(work),
        "--python-executable",
        os.fspath(tools["python"]),
        "--uv-executable",
        os.fspath(tools["uv"]),
        "--gitleaks-executable",
        os.fspath(tools["gitleaks"]),
        "--npm-executable",
        os.fspath(tools["npm"]),
        "--node-executable",
        os.fspath(tools["node"]),
        "--workflow-verifier",
        os.fspath(tools["workflow"]),
        "--maximum-output-bytes",
        str(maximum_output_bytes),
    )


def _repository_verification_interpreter_sha256(
    tools: dict[str, Path],
) -> str:
    entries: list[tuple[str, str, str]] = []
    for name in ("sandbox", "python"):
        path = tools[name]
        entries.extend(_runtime_path_commitment(name, path))
    return _canonical_sha256(entries)


def _repository_verification_runtime_closure_sha256(
    root: Path,
    tools: dict[str, Path],
) -> str:
    entries: list[tuple[str, str, str]] = []
    roots = (
        ("python-venv", root / ".venv"),
        (
            "python-stdlib",
            Path(
                sysconfig.get_path(
                    "stdlib",
                    vars={
                        "base": sys.base_prefix,
                        "platbase": sys.base_prefix,
                    },
                )
            ),
        ),
        ("node-modules", root / "site" / "node_modules"),
    )
    for label, selected_root in roots:
        if not selected_root.is_dir():
            raise RepositoryAcceptanceInputError(
                f"verification runtime root is unavailable: {label}"
            )
        entries.extend(_runtime_tree_commitment(label, selected_root))
    for name in (
        "sandbox",
        "python",
        "uv",
        "gitleaks",
        "npm",
        "node",
        "workflow",
    ):
        entries.extend(_runtime_path_commitment(f"tool-{name}", tools[name]))
    entries.extend(
        _runtime_path_commitment("uv-lock", root / "uv.lock")
    )
    entries.extend(
        _runtime_path_commitment(
            "npm-lock", root / "site" / "package-lock.json"
        )
    )
    return _canonical_sha256(sorted(entries))


def _runtime_tree_commitment(
    label: str, root: Path
) -> list[tuple[str, str, str]]:
    selected_root = Path(os.path.abspath(os.fspath(root)))
    entries: list[tuple[str, str, str]] = []
    for directory, directory_names, file_names in os.walk(
        selected_root, topdown=True, followlinks=False
    ):
        directory_names.sort()
        file_names.sort()
        directory_path = Path(directory)
        retained_directories: list[str] = []
        for name in directory_names:
            candidate = directory_path / name
            if label == "python-stdlib" and name == "site-packages":
                continue
            if candidate.is_symlink():
                relative = candidate.relative_to(selected_root).as_posix()
                entries.extend(
                    _runtime_path_commitment(f"{label}/{relative}", candidate)
                )
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            candidate = directory_path / name
            relative = candidate.relative_to(selected_root).as_posix()
            entries.extend(
                _runtime_path_commitment(f"{label}/{relative}", candidate)
            )
    if not entries:
        raise RepositoryAcceptanceInputError(
            f"verification runtime root is empty: {label}"
        )
    return entries


def _runtime_path_commitment(
    label: str, path: Path
) -> list[tuple[str, str, str]]:
    selected = Path(os.path.abspath(os.fspath(path)))
    try:
        before = selected.lstat()
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            f"verification runtime path is unavailable: {label}"
        ) from exc
    if stat.S_ISLNK(before.st_mode):
        target = os.readlink(selected)
        after = selected.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise RepositoryAcceptanceInputError(
                f"verification runtime symlink changed: {label}"
            )
        entries = [
            (label, "symlink", hashlib.sha256(target.encode()).hexdigest())
        ]
        resolved = selected.resolve(strict=True)
        if resolved.is_dir():
            entries.extend(
                _runtime_tree_commitment(f"{label}:target", resolved)
            )
        else:
            entries.extend(_runtime_path_commitment(f"{label}:target", resolved))
        return entries
    if not stat.S_ISREG(before.st_mode):
        raise RepositoryAcceptanceInputError(
            f"verification runtime path is not regular: {label}"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(selected, flags)
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            f"verification runtime path could not be opened: {label}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(opened) != identity(after):
            raise RepositoryAcceptanceInputError(
                f"verification runtime file changed: {label}"
            )
        return [(label, "file", digest.hexdigest())]
    finally:
        os.close(descriptor)


def _execute_repository_verification_command(
    command_argv: tuple[str, ...],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    maximum_output_bytes: int,
    start_new_session: bool = True,
) -> tuple[bytes, bytes, int]:
    try:
        process = subprocess.Popen(
            command_argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=start_new_session,
        )
    except OSError as exc:
        return b"", f"runner launch failed: {type(exc).__name__}".encode(), 126
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    deadline = time.monotonic() + timeout_seconds
    forced_code: int | None = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                forced_code = 124
                break
            events = selector.select(remaining)
            if not events:
                forced_code = 124
                break
            for key, _ in events:
                stream = key.fileobj
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                buffers[key.data].extend(chunk)
                if sum(len(item) for item in buffers.values()) > maximum_output_bytes:
                    forced_code = 125
                    break
            if forced_code is not None:
                break
        if forced_code is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            buffers["stderr"].extend(
                (
                    b"\nverification command timed out"
                    if forced_code == 124
                    else b"\nverification command exceeded output limit"
                )
            )
            return bytes(buffers["stdout"]), bytes(buffers["stderr"]), forced_code
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command_argv, timeout_seconds)
        returncode = process.wait(timeout=remaining)
        normalized = returncode if returncode >= 0 else min(255, 128 - returncode)
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), normalized
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        buffers["stderr"].extend(b"\nverification command timed out")
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), 124
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            if not stream.closed:
                stream.close()


def _parse_repository_verification_check_result(
    check: RepositoryVerificationCheck,
    *,
    stdout: bytes,
    stderr: bytes,
    returncode: int,
) -> dict[str, Any]:
    fallback = {
        "assertions_executed": 1,
        "failures": 1,
        "skipped": 0,
        "exit_code": returncode,
        "tool_name": "p18-local-runner",
        "tool_version": REPOSITORY_VERIFICATION_RUNNER_VERSION,
    }
    try:
        parsed = json.loads(
            stdout.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_verification_keys,
        )
        expected_keys = {
            "check",
            "assertions_executed",
            "failures",
            "skipped",
            "exit_code",
            "tool_name",
            "tool_version",
            "underlying_output_sha256",
        }
        if not isinstance(parsed, dict) or set(parsed) != expected_keys:
            return fallback
        counts = tuple(
            parsed[name]
            for name in (
                "assertions_executed",
                "failures",
                "skipped",
                "exit_code",
            )
        )
        if (
            parsed["check"] != check.value
            or any(type(item) is not int for item in counts)
            or counts[0] < 1
            or counts[1] < 0
            or counts[2] < 0
            or counts[1] + counts[2] > counts[0]
            or not 0 <= counts[3] <= 255
            or counts[3] != returncode
            or not isinstance(parsed["tool_name"], str)
            or not isinstance(parsed["tool_version"], str)
            or not isinstance(parsed["underlying_output_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", parsed["underlying_output_sha256"])
        ):
            return fallback
        return {
            "assertions_executed": counts[0],
            "failures": counts[1],
            "skipped": counts[2],
            "exit_code": counts[3],
            "tool_name": parsed["tool_name"],
            "tool_version": parsed["tool_version"],
        }
    except (UnicodeDecodeError, ValueError, TypeError):
        return fallback


def _reject_duplicate_verification_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate verification result key: {key}")
        result[key] = value
    return result


def _run_repository_pytest_check(
    check: RepositoryVerificationCheck,
    *,
    root: Path,
    work: Path,
    python: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    _verify_repository_test_partition(root)
    junit = work / "pytest.xml"
    arguments: dict[RepositoryVerificationCheck, tuple[str, ...]] = {
        RepositoryVerificationCheck.PYTHON_BASE: (
            "--ignore=tests/test_traction_control.py",
            "--ignore=tests/test_settlement_amendment.py",
            "--ignore=tests/test_production_consumer.py",
            "--ignore=tests/test_launch_handoff.py",
            "--ignore=tests/test_repository_acceptance.py",
        ),
        RepositoryVerificationCheck.PYTHON_TRACTION: (
            "tests/test_traction_control.py",
            "tests/test_settlement_amendment.py",
        ),
        RepositoryVerificationCheck.PYTHON_PRODUCTION_CONSUMER: (
            "tests/test_production_consumer.py",
        ),
        RepositoryVerificationCheck.CONTRACT_STORAGE_AUDIT: (
            "tests/test_repository_acceptance.py",
            "--deselect=tests/test_repository_acceptance.py::test_p18_pending_fixture_is_deterministic_and_stays_stop",
        ),
        RepositoryVerificationCheck.TCO_QA_AUDIT: (
            "tests/test_launch_handoff.py",
            "--deselect=tests/test_launch_handoff.py::test_p16_schema_and_blocked_fixture_generation_are_byte_deterministic",
        ),
    }
    command = (
        os.fspath(python),
        "-m",
        "pytest",
        "-p",
        "_hypothesis_pytestplugin",
        "-q",
        *arguments[check],
        f"--junitxml={junit}",
    )
    stdout, stderr, returncode = _execute_repository_verification_command(
        command,
        cwd=root,
        environment=dict(os.environ),
        timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[check],
        maximum_output_bytes=maximum_output_bytes,
        start_new_session=True,
    )
    assertions, failures, skipped = _parse_pytest_junit(junit, returncode)
    return {
        "assertions_executed": assertions,
        "failures": failures,
        "skipped": skipped,
        "exit_code": returncode,
        "tool_name": "pytest",
        "tool_version": _normalized_semver(importlib.metadata.version("pytest")),
        "underlying_output_sha256": hashlib.sha256(
            stdout + b"\x00" + stderr
        ).hexdigest(),
    }


def _verify_repository_test_partition(root: Path) -> None:
    all_tests = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").glob("test_*.py")
    }
    dedicated = {
        "tests/test_traction_control.py",
        "tests/test_settlement_amendment.py",
        "tests/test_production_consumer.py",
        "tests/test_launch_handoff.py",
        "tests/test_repository_acceptance.py",
    }
    base = set(_BASE_TEST_MODULES)
    partitions = (
        base,
        {
            "tests/test_traction_control.py",
            "tests/test_settlement_amendment.py",
        },
        {"tests/test_production_consumer.py"},
        {"tests/test_launch_handoff.py"},
        {"tests/test_repository_acceptance.py"},
    )
    if set().union(*partitions) != all_tests:
        raise RepositoryAcceptanceInputError(
            "repository test partition does not cover every test module"
        )
    for index, left in enumerate(partitions):
        if any(left.intersection(right) for right in partitions[index + 1 :]):
            raise RepositoryAcceptanceInputError(
                "repository test partitions overlap"
            )


def _parse_pytest_junit(
    path: Path, returncode: int
) -> tuple[int, int, int]:
    try:
        document = ElementTree.parse(path).getroot()
        suites = (
            (document,)
            if document.tag == "testsuite"
            else tuple(document.findall("./testsuite"))
        )
        assertions = sum(int(item.attrib.get("tests", "0")) for item in suites)
        failures = sum(
            int(item.attrib.get("failures", "0"))
            + int(item.attrib.get("errors", "0"))
            for item in suites
        )
        skipped = sum(int(item.attrib.get("skipped", "0")) for item in suites)
    except (OSError, ValueError, ElementTree.ParseError):
        return 1, 1, 0
    assertions = max(assertions, 1)
    if returncode != 0 and failures == 0:
        failures = 1
    return assertions, min(failures, assertions), min(
        skipped, assertions - min(failures, assertions)
    )


def _run_repository_schema_check(
    *,
    root: Path,
    work: Path,
    python: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    outputs: list[bytes] = []
    returncodes: list[int] = []
    generated: list[Path] = []
    for name in ("first", "second"):
        destination = work / name
        generated.append(destination)
        command = (
            os.fspath(python),
            "scripts/export_schemas.py",
            "--output-dir",
            os.fspath(destination),
        )
        stdout, stderr, returncode = _execute_repository_verification_command(
            command,
            cwd=root,
            environment=dict(os.environ),
            timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[
                RepositoryVerificationCheck.SCHEMA_DETERMINISM
            ],
            maximum_output_bytes=maximum_output_bytes,
            start_new_session=True,
        )
        outputs.extend((stdout, stderr))
        returncodes.append(returncode)
    assertions, comparison_failures, comparison = _compare_generated_trees(
        root / "schemas", *generated
    )
    outputs.append(comparison)
    failures = comparison_failures + int(any(returncodes))
    failures = min(max(failures, int(any(returncodes))), assertions)
    exit_code = 0 if failures == 0 else next(
        (item for item in returncodes if item != 0), 1
    )
    return {
        "assertions_executed": assertions,
        "failures": failures,
        "skipped": 0,
        "exit_code": exit_code,
        "tool_name": "python",
        "tool_version": _python_tool_version(),
        "underlying_output_sha256": hashlib.sha256(
            b"\x00".join(outputs)
        ).hexdigest(),
    }


def _run_repository_fixture_check(
    *,
    root: Path,
    work: Path,
    python: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    outputs: list[bytes] = []
    returncodes: list[int] = []
    generated: dict[str, list[Path]] = {"p16": [], "p18": []}
    scripts = {
        "p16": root / "scripts" / "generate_p16_blocked_fixture.py",
        "p18": root / "scripts" / "generate_p18_pending_fixture.py",
    }
    expected = {
        "p16": root / "examples" / "p16" / "blocked",
        "p18": root
        / "artifacts"
        / "local-acceptance"
        / "p18-current-stop",
    }
    for label in ("p16", "p18"):
        for round_name in ("first", "second"):
            destination = work / f"{label}-{round_name}"
            generated[label].append(destination)
            command = (
                os.fspath(python),
                os.fspath(scripts[label]),
                "--output-dir",
                os.fspath(destination),
            )
            if label == "p18":
                command += ("--repo-root", os.fspath(root))
            stdout, stderr, returncode = (
                _execute_repository_verification_command(
                    command,
                    cwd=root,
                    environment=dict(os.environ),
                    timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[
                        RepositoryVerificationCheck.BLOCKED_FIXTURE_DETERMINISM
                    ],
                    maximum_output_bytes=maximum_output_bytes,
                    start_new_session=True,
                )
            )
            outputs.extend((stdout, stderr))
            returncodes.append(returncode)
    assertions = 0
    comparison_failures = 0
    for label in ("p16", "p18"):
        count, failures, comparison = _compare_generated_trees(
            expected[label], *generated[label]
        )
        assertions += count
        comparison_failures += failures
        outputs.append(comparison)
    assertions = max(assertions, 1)
    failures = min(
        comparison_failures + int(any(returncodes)), assertions
    )
    exit_code = 0 if failures == 0 else next(
        (item for item in returncodes if item != 0), 1
    )
    return {
        "assertions_executed": assertions,
        "failures": failures,
        "skipped": 0,
        "exit_code": exit_code,
        "tool_name": "python",
        "tool_version": _python_tool_version(),
        "underlying_output_sha256": hashlib.sha256(
            b"\x00".join(outputs)
        ).hexdigest(),
    }


def _compare_generated_trees(
    expected: Path, first: Path, second: Path
) -> tuple[int, int, bytes]:
    trees = tuple(_directory_digest_map(item) for item in (expected, first, second))
    names = sorted(set().union(*(set(item) for item in trees)))
    failures = sum(
        1
        for name in names
        if not (
            name in trees[0]
            and name in trees[1]
            and name in trees[2]
            and trees[0][name] == trees[1][name] == trees[2][name]
        )
    )
    return (
        max(len(names), 1),
        failures if names else 1,
        json.dumps(
            {"expected": trees[0], "first": trees[1], "second": trees[2]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )


def _directory_digest_map(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _run_repository_web_tests_check(
    *,
    root: Path,
    node: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    site = root / "site"
    vinext = site / "node_modules" / "vinext" / "dist" / "cli.js"
    commands = (
        (
            (os.fspath(node), os.fspath(vinext), "build"),
            {"SAAS_RUNTIME_MODE": "synthetic-local"},
        ),
        (
            (
                os.fspath(node),
                "--test",
                "tests/local-ui.test.mjs",
                "tests/prepublication-assurance.test.mjs",
            ),
            {},
        ),
        (
            (os.fspath(node), "--test", "tests/startup-boundary.test.mjs"),
            {},
        ),
        (
            (os.fspath(node), os.fspath(vinext), "build"),
            {"SAAS_RUNTIME_MODE": "production"},
        ),
        (
            (os.fspath(node), "--test", "tests/production-worker.test.mjs"),
            {"SAAS_RUNTIME_MODE": "production"},
        ),
    )
    outputs: list[bytes] = []
    returncodes: list[int] = []
    for command, overrides in commands:
        environment = dict(os.environ)
        environment.update(overrides)
        environment["WRANGLER_LOG_PATH"] = ".wrangler/wrangler.log"
        stdout, stderr, returncode = _execute_repository_verification_command(
            command,
            cwd=site,
            environment=environment,
            timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[
                RepositoryVerificationCheck.WEB_TESTS
            ],
            maximum_output_bytes=maximum_output_bytes,
            start_new_session=True,
        )
        outputs.extend((stdout, stderr))
        returncodes.append(returncode)
        if returncode != 0:
            break
    combined = b"\n".join(outputs)
    assertions, failures, skipped = _parse_node_test_counts(
        combined, next((item for item in returncodes if item != 0), 0)
    )
    exit_code = next((item for item in returncodes if item != 0), 0)
    return {
        "assertions_executed": assertions,
        "failures": failures,
        "skipped": skipped,
        "exit_code": exit_code,
        "tool_name": "node",
        "tool_version": _read_tool_version(node, ("--version",)),
        "underlying_output_sha256": hashlib.sha256(combined).hexdigest(),
    }


def _run_repository_web_lint_check(
    *,
    root: Path,
    node: Path,
    maximum_output_bytes: int,
) -> dict[str, Any]:
    site = root / "site"
    eslint = site / "node_modules" / "eslint" / "bin" / "eslint.js"
    command = (
        os.fspath(node),
        os.fspath(eslint),
        ".",
        "--ignore-pattern",
        "dist",
        "--ignore-pattern",
        ".next",
    )
    stdout, stderr, returncode = _execute_repository_verification_command(
        command,
        cwd=site,
        environment=dict(os.environ),
        timeout_seconds=_REPOSITORY_VERIFICATION_TIMEOUT_SECONDS[
            RepositoryVerificationCheck.WEB_LINT
        ],
        maximum_output_bytes=maximum_output_bytes,
        start_new_session=True,
    )
    return {
        "assertions_executed": 1,
        "failures": int(returncode != 0),
        "skipped": 0,
        "exit_code": returncode,
        "tool_name": "eslint",
        "tool_version": _read_tool_version(
            node, (os.fspath(eslint), "--version")
        ),
        "underlying_output_sha256": hashlib.sha256(
            stdout + b"\x00" + stderr
        ).hexdigest(),
    }


def _parse_node_test_counts(
    output: bytes, returncode: int
) -> tuple[int, int, int]:
    decoded = output.decode("utf-8", errors="replace")
    tests = [int(item) for item in re.findall(r"(?:#|ℹ)\s*tests\s+(\d+)", decoded)]
    failed = [int(item) for item in re.findall(r"(?:#|ℹ)\s*fail\s+(\d+)", decoded)]
    skipped_values = [
        int(item) for item in re.findall(r"(?:#|ℹ)\s*skipped\s+(\d+)", decoded)
    ]
    assertions = max(sum(tests), 1)
    failures = sum(failed)
    skipped = sum(skipped_values)
    if returncode != 0 and failures == 0:
        failures = 1
    return assertions, min(failures, assertions), min(
        skipped, assertions - min(failures, assertions)
    )


def _repository_simple_check_command(
    check: RepositoryVerificationCheck,
    *,
    root: Path,
    tools: dict[str, Path],
) -> tuple[tuple[str, ...], str, str, int]:
    if check is RepositoryVerificationCheck.UV_LOCK:
        return (
            (os.fspath(tools["uv"]), "lock", "--check", "--offline"),
            "uv",
            _read_tool_version(tools["uv"], ("--version",)),
            1,
        )
    if check is RepositoryVerificationCheck.COMPILEALL:
        assertions = sum(
            1
            for directory in ("src", "scripts", "tests")
            for _ in (root / directory).rglob("*.py")
        )
        return (
            (
                os.fspath(tools["python"]),
                "-m",
                "compileall",
                "-q",
                "src",
                "scripts",
                "tests",
            ),
            "python",
            _python_tool_version(),
            max(assertions, 1),
        )
    if check is RepositoryVerificationCheck.SECRET_SCAN:
        return (
            (
                os.fspath(tools["gitleaks"]),
                "dir",
                ".",
                "--redact",
                "--no-banner",
                "--no-color",
            ),
            "gitleaks",
            _read_tool_version(tools["gitleaks"], ("version",)),
            1,
        )
    if check is RepositoryVerificationCheck.DEPENDENCY_AUDIT:
        return (
            (
                os.fspath(tools["npm"]),
                "--prefix",
                "site",
                "audit",
                "--offline",
                "--audit-level=high",
            ),
            "npm",
            _read_tool_version(tools["npm"], ("--version",)),
            1,
        )
    if check is RepositoryVerificationCheck.WORKFLOW_VERIFIER:
        return (
            (
                os.fspath(tools["python"]),
                os.fspath(tools["workflow"]),
                os.fspath(root / ".workflow" / "saas-affiliate-production-roadmap"),
            ),
            "python",
            _python_tool_version(),
            1,
        )
    raise RepositoryAcceptanceInputError(
        f"repository verification check has no fixed command: {check.value}"
    )


def _read_tool_version(path: Path, arguments: tuple[str, ...]) -> str:
    stdout, stderr, returncode = _execute_repository_verification_command(
        (os.fspath(path), *arguments),
        cwd=Path.cwd(),
        environment=dict(os.environ),
        timeout_seconds=15,
        maximum_output_bytes=65_536,
        start_new_session=True,
    )
    if returncode != 0:
        raise RepositoryAcceptanceInputError(
            f"could not determine verification tool version: {path.name}"
        )
    return _normalized_semver((stdout + b"\n" + stderr).decode(errors="replace"))


def _normalized_semver(value: str) -> str:
    matched = _SEMVER_PATTERN.search(value)
    if matched is None:
        raise RepositoryAcceptanceInputError(
            "verification tool did not report a semantic version"
        )
    return matched.group(1)


def _python_tool_version() -> str:
    return ".".join(str(item) for item in sys.version_info[:3])


def build_repository_candidate_manifest(
    repo_root: Path,
    verification: RepositoryVerificationEvidenceBundle,
    *,
    candidate_id: str,
    assembled_at: datetime,
    expires_at: datetime,
    integration_verification: RepositoryVerificationAttestation | None = None,
    tco_qa_verification: RepositoryVerificationAttestation | None = None,
    verified_runner_evidence: VerifiedRunnerEvidenceBundle | None = None,
    verified_runner_policy: VerifiedRunnerPolicy | None = None,
    verified_runner_trust_store: VerifiedRunnerTrustStore | None = None,
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None = None,
) -> RepositoryCandidateManifest:
    _require_utc(assembled_at, "candidate assembly timestamp")
    _require_utc(expires_at, "candidate expiry timestamp")
    entries = build_repository_inventory(repo_root)
    tree_hash = hash_repository_tree(entries)
    verified = _copy(verification, RepositoryVerificationEvidenceBundle)
    if verified.subject_tree_sha256 != tree_hash:
        raise RepositoryAcceptanceInputError(
            "verification evidence does not bind the current repository tree"
        )
    previous_hash = next(
        item.sha256 for item in entries if item.path == PREVIOUS_CANDIDATE_RECORD
    )
    values: dict[str, Any] = {
        "schema_version": "2.0",
        "candidate_id": candidate_id,
        "scope_profile": SCOPE_PROFILE,
        "scope_paths_sha256": _SCOPE_PATHS_BY_PROFILE[SCOPE_PROFILE],
        "previous_candidate_record_sha256": previous_hash,
        "assembled_at": assembled_at,
        "expires_at": expires_at,
        "files": entries,
        "tree_sha256": tree_hash,
        "verification": verified,
        "verified_runner_evidence": (
            None
            if verified_runner_evidence is None
            else VerifiedRunnerEvidenceBundle.model_validate(
                verified_runner_evidence.model_dump()
            )
        ),
        "verified_runner_policy": verified_runner_policy,
        "verified_runner_trust_store": verified_runner_trust_store,
        "verified_runner_authority_pins": verified_runner_authority_pins,
        "integration_verification": (
            None
            if integration_verification is None
            else _copy(
                integration_verification,
                RepositoryVerificationAttestation,
            )
        ),
        "tco_qa_verification": (
            None
            if tco_qa_verification is None
            else _copy(tco_qa_verification, RepositoryVerificationAttestation)
        ),
        "authority_exclusions": REQUIRED_REPOSITORY_AUTHORITY_EXCLUSIONS,
        "authority": "none",
        "decision": "pending",
    }
    provisional = RepositoryCandidateManifest.model_construct(
        **values, manifest_sha256="0" * 64
    )
    return RepositoryCandidateManifest(
        **values,
        manifest_sha256=hash_repository_candidate_manifest(provisional),
    )


def sign_repository_verification_attestation(
    verification: RepositoryVerificationEvidenceBundle,
    private_key: Ed25519PrivateKey,
    *,
    attestation_id: str,
    signer_role: SigningRole,
    signer_issuer: str,
    issued_at: datetime,
    expires_at: datetime,
    verified_runner_evidence: VerifiedRunnerEvidenceBundle | None = None,
    verified_runner_authority_sha256: str = "0" * 64,
) -> RepositoryVerificationAttestation:
    selected = _copy(verification, RepositoryVerificationEvidenceBundle)
    if signer_role not in {
        SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        SigningRole.TCO_QA,
    }:
        raise RepositoryAcceptanceInputError("invalid verification attestation role")
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    if (verified_runner_evidence is None) is not (
        verified_runner_authority_sha256 == "0" * 64
    ):
        raise RepositoryAcceptanceInputError(
            "runner evidence and its packet-external authority root are required together"
        )
    runner_bundle_sha256 = (
        "0" * 64
        if verified_runner_evidence is None
        else VerifiedRunnerEvidenceBundle.model_validate(
            verified_runner_evidence.model_dump()
        ).bundle_sha256
    )
    values: dict[str, Any] = {
        "schema_version": "2.0",
        "attestation_id": attestation_id,
        "subject_tree_sha256": selected.subject_tree_sha256,
        "verification_bundle_sha256": selected.bundle_sha256,
        "verified_runner_bundle_sha256": runner_bundle_sha256,
        "verified_runner_authority_sha256": verified_runner_authority_sha256,
        "signer_role": signer_role,
        "signer_issuer": signer_issuer,
        "signer_key_id_sha256": _private_key_id(private_key),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    provisional = RepositoryVerificationAttestation.model_construct(
        **values, attestation_sha256="0" * 64, signature_base64url="A" * 86
    )
    attestation_hash = hash_repository_verification_attestation(provisional)
    return RepositoryVerificationAttestation(
        **values,
        attestation_sha256=attestation_hash,
        signature_base64url=_sign(private_key, attestation_hash),
    )


def sign_human_repository_acceptance(
    manifest: RepositoryCandidateManifest,
    policy: RepositoryAcceptancePolicy,
    trust_store: RepositoryAcceptanceTrustStore,
    private_key: Ed25519PrivateKey,
    *,
    receipt_id: str,
    revision: int,
    predecessor_receipt_sha256: str,
    decision: HumanRepositoryDecision,
    condition_ids: tuple[str, ...] = (),
    issued_at: datetime,
    expires_at: datetime,
) -> HumanRepositoryAcceptance:
    candidate = _copy(manifest, RepositoryCandidateManifest)
    selected_policy = _copy(policy, RepositoryAcceptancePolicy)
    trust = _copy(trust_store, RepositoryAcceptanceTrustStore)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    key_id = _private_key_id(private_key)
    if (
        trust.human_approver.key_id_sha256 != key_id
        or selected_policy.human_approver_key_id_sha256 != key_id
    ):
        raise RepositoryAcceptanceInputError("Human signing key is not policy-pinned")
    if (
        selected_policy.scope_profile != candidate.scope_profile
        or selected_policy.scope_paths_sha256 != candidate.scope_paths_sha256
        or selected_policy.expected_previous_candidate_record_sha256
        != candidate.previous_candidate_record_sha256
    ):
        raise RepositoryAcceptanceInputError("policy does not bind the candidate scope")
    if issued_at < candidate.assembled_at or expires_at > candidate.expires_at:
        raise RepositoryAcceptanceInputError(
            "Human acceptance must be issued within the candidate lifetime"
        )
    policy_hash = hash_repository_acceptance_policy(selected_policy)
    trust_hash = hash_repository_acceptance_trust_store(trust)
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_id": receipt_id,
        "manifest_sha256": candidate.manifest_sha256,
        "policy_sha256": policy_hash,
        "trust_store_sha256": trust_hash,
        "revision": revision,
        "predecessor_receipt_sha256": predecessor_receipt_sha256,
        "decision": decision,
        "condition_ids": tuple(sorted(condition_ids)),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "approver_issuer": trust.human_approver.issuer,
        "approver_key_id_sha256": key_id,
    }
    provisional = HumanRepositoryAcceptance.model_construct(
        **values, receipt_sha256="0" * 64, signature_base64url="A" * 86
    )
    receipt_hash = hash_human_repository_acceptance(provisional)
    return HumanRepositoryAcceptance(
        **values,
        receipt_sha256=receipt_hash,
        signature_base64url=_sign(private_key, receipt_hash),
    )


def build_repository_acceptance_authority_bundle(
    manifest: RepositoryCandidateManifest,
    policy: RepositoryAcceptancePolicy,
    trust_store: RepositoryAcceptanceTrustStore,
    authority_pins: RepositoryAcceptanceAuthorityPins,
    human_acceptance: HumanRepositoryAcceptance,
    *,
    receipt_chain: tuple[HumanRepositoryAcceptance, ...] = (),
    verified_runner_policy: VerifiedRunnerPolicy | None = None,
    verified_runner_trust_store: VerifiedRunnerTrustStore | None = None,
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None = None,
) -> RepositoryAcceptanceAuthorityBundle:
    verified_runner_policy = (
        verified_runner_policy or manifest.verified_runner_policy
    )
    verified_runner_trust_store = (
        verified_runner_trust_store or manifest.verified_runner_trust_store
    )
    verified_runner_authority_pins = (
        verified_runner_authority_pins
        or manifest.verified_runner_authority_pins
    )
    values = {
        "schema_version": "2.0",
        "manifest": _copy(manifest, RepositoryCandidateManifest),
        "policy": _copy(policy, RepositoryAcceptancePolicy),
        "trust_store": _copy(trust_store, RepositoryAcceptanceTrustStore),
        "authority_pins": _copy(
            authority_pins, RepositoryAcceptanceAuthorityPins
        ),
        "verified_runner_policy": verified_runner_policy,
        "verified_runner_trust_store": verified_runner_trust_store,
        "verified_runner_authority_pins": verified_runner_authority_pins,
        "receipt_chain": tuple(
            _copy(item, HumanRepositoryAcceptance) for item in receipt_chain
        ),
        "human_acceptance": _copy(
            human_acceptance, HumanRepositoryAcceptance
        ),
    }
    provisional = RepositoryAcceptanceAuthorityBundle.model_construct(
        **values, bundle_sha256="0" * 64
    )
    return RepositoryAcceptanceAuthorityBundle(
        **values,
        bundle_sha256=hash_repository_acceptance_authority_bundle(provisional),
    )


def evaluate_repository_acceptance(
    manifest: RepositoryCandidateManifest,
    repo_root: Path,
    *,
    at: datetime,
    receipt: HumanRepositoryAcceptance | None = None,
    policy: RepositoryAcceptancePolicy | None = None,
    trust_store: RepositoryAcceptanceTrustStore | None = None,
    authority_pins: RepositoryAcceptanceAuthorityPins | None = None,
    expected_verification_authority_sha256: str | None = None,
    verified_runner_policy: VerifiedRunnerPolicy | None = None,
    verified_runner_trust_store: VerifiedRunnerTrustStore | None = None,
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None = None,
    expected_verified_runner_authority_sha256: str | None = None,
    expected_authority_pins_sha256: str | None = None,
    receipt_chain: tuple[HumanRepositoryAcceptance, ...] = (),
) -> RepositoryAcceptanceReport:
    _require_utc(at, "repository acceptance evaluation timestamp")
    candidate = _copy(manifest, RepositoryCandidateManifest)
    observed_files = build_repository_inventory(repo_root)
    observed_tree = hash_repository_tree(observed_files)
    reasons: set[RepositoryAcceptanceReason] = set()

    if candidate.scope_profile != SCOPE_PROFILE:
        reasons.add(RepositoryAcceptanceReason.SCOPE_PROFILE_OUTDATED)
    if observed_files != candidate.files or observed_tree != candidate.tree_sha256:
        reasons.add(RepositoryAcceptanceReason.MANIFEST_DRIFT)
    if candidate.assembled_at > at:
        reasons.add(RepositoryAcceptanceReason.MANIFEST_FUTURE)
    if candidate.expires_at <= at:
        reasons.add(RepositoryAcceptanceReason.MANIFEST_EXPIRED)
    reasons.update(_candidate_local_verification_reasons(candidate, at=at))

    selected_policy: RepositoryAcceptancePolicy | None = None
    trust: RepositoryAcceptanceTrustStore | None = None
    if policy is None or trust_store is None:
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISSING)
        if (policy is None) is not (trust_store is None):
            reasons.add(RepositoryAcceptanceReason.AUTHORITY_MISSING)
    else:
        selected_policy = _copy(policy, RepositoryAcceptancePolicy)
        trust = _copy(trust_store, RepositoryAcceptanceTrustStore)
        verification_root = expected_verification_authority_sha256
        if verification_root is None and authority_pins is not None:
            verification_root = (
                authority_pins.expected_verification_authority_sha256
            )
        runner_root = expected_verified_runner_authority_sha256
        if authority_pins is not None:
            if (
                runner_root is not None
                and runner_root
                != authority_pins.expected_verified_runner_authority_sha256
            ):
                reasons.add(RepositoryAcceptanceReason.AUTHORITY_PIN_MISMATCH)
            runner_root = (
                authority_pins.expected_verified_runner_authority_sha256
            )
        runner_policy = verified_runner_policy or candidate.verified_runner_policy
        runner_trust = (
            verified_runner_trust_store
            or candidate.verified_runner_trust_store
        )
        runner_pins = (
            verified_runner_authority_pins
            or candidate.verified_runner_authority_pins
        )
        if (
            verified_runner_policy is not None
            and verified_runner_policy != candidate.verified_runner_policy
        ) or (
            verified_runner_trust_store is not None
            and verified_runner_trust_store
            != candidate.verified_runner_trust_store
        ) or (
            verified_runner_authority_pins is not None
            and verified_runner_authority_pins
            != candidate.verified_runner_authority_pins
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH)
        reasons.update(
            _repository_verification_authority_reasons(
                candidate,
                selected_policy,
                trust,
                expected_verification_authority_sha256=verification_root,
                verified_runner_policy=runner_policy,
                verified_runner_trust_store=runner_trust,
                verified_runner_authority_pins=runner_pins,
                expected_verified_runner_authority_sha256=runner_root,
                at=at,
            )
        )

    receipt_authority = (receipt, authority_pins)
    if all(item is None for item in receipt_authority):
        reasons.add(RepositoryAcceptanceReason.RECEIPT_MISSING)
        return _acceptance_report(candidate, observed_tree, at, reasons)
    if (
        any(item is None for item in receipt_authority)
        or selected_policy is None
        or trust is None
    ):
        reasons.add(RepositoryAcceptanceReason.AUTHORITY_MISSING)
        return _acceptance_report(candidate, observed_tree, at, reasons)

    assert receipt is not None
    assert authority_pins is not None
    accepted_receipt = _copy(receipt, HumanRepositoryAcceptance)
    reasons.update(
        _repository_receipt_authority_reasons(
            candidate,
            accepted_receipt,
            selected_policy,
            trust,
            _copy(authority_pins, RepositoryAcceptanceAuthorityPins),
            receipt_chain=tuple(
                _copy(item, HumanRepositoryAcceptance)
                for item in receipt_chain
            ),
            expected_authority_pins_sha256=expected_authority_pins_sha256,
            at=at,
        )
    )

    return _acceptance_report(
        candidate,
        observed_tree,
        at,
        reasons,
        human_decision=accepted_receipt.decision,
    )


def evaluate_repository_acceptance_authority_bundle(
    bundle: RepositoryAcceptanceAuthorityBundle,
    *,
    at: datetime,
    expected_authority_pins_sha256: str,
) -> RepositoryAcceptanceReport:
    """Verify the pinned P18 authority chain without claiming a live tree read."""

    _require_utc(at, "repository authority evaluation timestamp")
    selected = _copy(bundle, RepositoryAcceptanceAuthorityBundle)
    candidate = selected.manifest
    reasons: set[RepositoryAcceptanceReason] = set()
    if (
        candidate.scope_profile != SCOPE_PROFILE
        or selected.policy.scope_profile != SCOPE_PROFILE
    ):
        reasons.add(RepositoryAcceptanceReason.SCOPE_PROFILE_OUTDATED)
    if candidate.assembled_at > at:
        reasons.add(RepositoryAcceptanceReason.MANIFEST_FUTURE)
    if candidate.expires_at <= at:
        reasons.add(RepositoryAcceptanceReason.MANIFEST_EXPIRED)
    reasons.update(
        _repository_verification_authority_reasons(
            candidate,
            selected.policy,
            selected.trust_store,
            expected_verification_authority_sha256=(
                selected.authority_pins.expected_verification_authority_sha256
            ),
            verified_runner_policy=selected.verified_runner_policy,
            verified_runner_trust_store=selected.verified_runner_trust_store,
            verified_runner_authority_pins=(
                selected.verified_runner_authority_pins
            ),
            expected_verified_runner_authority_sha256=(
                selected.authority_pins.expected_verified_runner_authority_sha256
            ),
            at=at,
        )
    )
    reasons.update(
        _repository_receipt_authority_reasons(
            candidate,
            selected.human_acceptance,
            selected.policy,
            selected.trust_store,
            selected.authority_pins,
            receipt_chain=selected.receipt_chain,
            expected_authority_pins_sha256=expected_authority_pins_sha256,
            at=at,
        )
    )
    return _acceptance_report(
        candidate,
        candidate.tree_sha256,
        at,
        reasons,
        human_decision=selected.human_acceptance.decision,
    )


def _repository_verification_authority_reasons(
    candidate: RepositoryCandidateManifest,
    selected_policy: RepositoryAcceptancePolicy,
    trust: RepositoryAcceptanceTrustStore,
    *,
    expected_verification_authority_sha256: str | None,
    verified_runner_policy: VerifiedRunnerPolicy | None,
    verified_runner_trust_store: VerifiedRunnerTrustStore | None,
    verified_runner_authority_pins: VerifiedRunnerAuthorityPins | None,
    expected_verified_runner_authority_sha256: str | None,
    at: datetime,
) -> set[RepositoryAcceptanceReason]:
    reasons: set[RepositoryAcceptanceReason] = set()
    verification_authority_hash = hash_repository_verification_authority(
        selected_policy, trust
    )
    if expected_verification_authority_sha256 is None:
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISSING)
    elif expected_verification_authority_sha256 != verification_authority_hash:
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH)
    uses_v2 = all(
        fact.provenance
        is RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
        for fact in candidate.verification.facts
    )
    runner_authority = (
        verified_runner_policy,
        verified_runner_trust_store,
        verified_runner_authority_pins,
        expected_verified_runner_authority_sha256,
    )
    if not uses_v2 or candidate.verified_runner_evidence is None:
        # VERIFIED_LOCAL_RUN is a legacy value and is permanently unsupported.
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC)
    elif any(item is None for item in runner_authority) or (
        expected_verified_runner_authority_sha256 == "0" * 64
    ):
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISSING)
    else:
        assert verified_runner_policy is not None
        assert verified_runner_trust_store is not None
        assert verified_runner_authority_pins is not None
        assert expected_verified_runner_authority_sha256 is not None
        p18_and_p19_keys = (
            trust.human_approver.key_id_sha256,
            trust.integration_evidence_runner.key_id_sha256,
            trust.tco_qa.key_id_sha256,
            verified_runner_trust_store.runner.key_id_sha256,
            verified_runner_trust_store.advisory_auditor.key_id_sha256,
            verified_runner_trust_store.image_builder.key_id_sha256,
            verified_runner_trust_store.time_auditor.key_id_sha256,
            verified_runner_trust_store.storage_auditor.key_id_sha256,
        )
        if len(set(p18_and_p19_keys)) != len(p18_and_p19_keys):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH)
        try:
            verified = verify_verified_runner_evidence(
                candidate.verified_runner_evidence,
                policy=verified_runner_policy,
                trust_store=verified_runner_trust_store,
                authority_pins=verified_runner_authority_pins,
                expected_authority_sha256=(
                    expected_verified_runner_authority_sha256
                ),
                at=at,
            )
            receipt = verify_verified_runner_consumption_receipt(
                candidate.verification.verified_runner_consumption_receipt,
                verified,
                trust_store=verified_runner_trust_store,
                policy=verified_runner_policy,
                authority_pins=verified_runner_authority_pins,
                expected_authority_sha256=(
                    expected_verified_runner_authority_sha256
                ),
                at=at,
            )
            if (
                verified != candidate.verified_runner_evidence
                or build_repository_verification_from_verified_runner_evidence(
                    verified, consumption_receipt=receipt
                )
                != candidate.verification
            ):
                reasons.add(
                    RepositoryAcceptanceReason.VERIFICATION_REQUIREMENT_MISMATCH
                )
        except (TypeError, ValueError):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_TRUST_MISMATCH)
    if (
        selected_policy.scope_profile != candidate.scope_profile
        or selected_policy.scope_paths_sha256 != candidate.scope_paths_sha256
        or selected_policy.expected_previous_candidate_record_sha256
        != candidate.previous_candidate_record_sha256
        or tuple(
            item.check for item in selected_policy.verification_requirements
        )
        != tuple(item.check for item in candidate.verification.facts)
        or tuple(
            item.minimum_assertions
            for item in selected_policy.verification_requirements
        )
        != tuple(
            REPOSITORY_VERIFICATION_MINIMUM_ASSERTIONS[check]
            for check in REQUIRED_REPOSITORY_VERIFICATION_CHECKS
        )
        or selected_policy.required_authority_exclusions
        != candidate.authority_exclusions
    ):
        reasons.add(RepositoryAcceptanceReason.POLICY_MISMATCH)
    if (
        trust.human_approver.key_id_sha256
        != selected_policy.human_approver_key_id_sha256
        or trust.integration_evidence_runner.key_id_sha256
        != selected_policy.integration_evidence_runner_key_id_sha256
        or trust.tco_qa.key_id_sha256 != selected_policy.tco_qa_key_id_sha256
    ):
        reasons.add(RepositoryAcceptanceReason.TRUST_STORE_MISMATCH)
    if candidate.expires_at - candidate.assembled_at > timedelta(
        seconds=selected_policy.maximum_manifest_ttl_seconds
    ):
        reasons.add(RepositoryAcceptanceReason.MANIFEST_TTL_EXCEEDED)
    for fact, requirement in zip(
        candidate.verification.facts,
        selected_policy.verification_requirements,
        strict=True,
    ):
        if not fact.succeeded:
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_FAILED)
        if fact.not_after <= at:
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_EXPIRED)
        if candidate.assembled_at - fact.executed_at > timedelta(
            seconds=selected_policy.maximum_verification_age_seconds
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_TOO_OLD)
        if (
            fact.provenance
            is not RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC)
        if (
            fact.check is not requirement.check
            or fact.command_sha256 != requirement.command_sha256
            or fact.tool_name != requirement.tool_name
            or fact.tool_version != requirement.tool_version
            or fact.assertions_executed < requirement.minimum_assertions
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_REQUIREMENT_MISMATCH)
    attestations = (
        (
            candidate.integration_verification,
            trust.integration_evidence_runner,
            SigningRole.INTEGRATION_EVIDENCE_RUNNER,
        ),
        (candidate.tco_qa_verification, trust.tco_qa, SigningRole.TCO_QA),
    )
    if any(item[0] is None for item in attestations):
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_MISSING)
    else:
        for attestation, key, role in attestations:
            assert attestation is not None
            if (
                attestation.signer_role is not role
                or attestation.signer_key_id_sha256 != key.key_id_sha256
                or attestation.signer_issuer != key.issuer
                or attestation.subject_tree_sha256 != candidate.tree_sha256
                or attestation.verification_bundle_sha256
                != candidate.verification.bundle_sha256
                or attestation.verified_runner_bundle_sha256
                != (
                    "0" * 64
                    if candidate.verified_runner_evidence is None
                    else candidate.verified_runner_evidence.bundle_sha256
                )
                or attestation.verified_runner_authority_sha256
                != (
                    "0" * 64
                    if candidate.verified_runner_policy is None
                    or candidate.verified_runner_trust_store is None
                    or candidate.verified_runner_authority_pins is None
                    else hash_verified_runner_authority(
                        candidate.verified_runner_policy,
                        candidate.verified_runner_trust_store,
                        candidate.verified_runner_authority_pins,
                    )
                )
                or attestation.issued_at > at
                or attestation.expires_at <= at
                or attestation.expires_at - attestation.issued_at
                > timedelta(
                    seconds=selected_policy.maximum_verification_attestation_ttl_seconds
                )
                or not _verify_signature(
                    key,
                    attestation.attestation_sha256,
                    attestation.signature_base64url,
                )
            ):
                reasons.add(
                    RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID
                )
    return reasons


def _repository_receipt_authority_reasons(
    candidate: RepositoryCandidateManifest,
    accepted_receipt: HumanRepositoryAcceptance,
    selected_policy: RepositoryAcceptancePolicy,
    trust: RepositoryAcceptanceTrustStore,
    pins: RepositoryAcceptanceAuthorityPins,
    *,
    receipt_chain: tuple[HumanRepositoryAcceptance, ...],
    at: datetime,
    expected_authority_pins_sha256: str | None,
) -> set[RepositoryAcceptanceReason]:
    reasons: set[RepositoryAcceptanceReason] = set()
    policy_hash = hash_repository_acceptance_policy(selected_policy)
    trust_hash = hash_repository_acceptance_trust_store(trust)
    verification_authority_hash = hash_repository_verification_authority(
        selected_policy, trust
    )
    pins_hash = hash_repository_acceptance_authority_pins(pins)
    if expected_authority_pins_sha256 is None:
        reasons.add(RepositoryAcceptanceReason.AUTHORITY_ROOT_MISSING)
    elif expected_authority_pins_sha256 != pins_hash:
        reasons.add(RepositoryAcceptanceReason.AUTHORITY_ROOT_MISMATCH)
    if (
        pins.expected_manifest_sha256 != candidate.manifest_sha256
        or pins.expected_policy_sha256 != policy_hash
        or pins.expected_trust_store_sha256 != trust_hash
        or pins.expected_verification_authority_sha256
        != verification_authority_hash
    ):
        reasons.add(RepositoryAcceptanceReason.AUTHORITY_PIN_MISMATCH)
    if (
        pins.expected_current_receipt_sha256
        != accepted_receipt.receipt_sha256
        or pins.expected_current_revision != accepted_receipt.revision
    ):
        reasons.add(RepositoryAcceptanceReason.RECEIPT_NOT_CURRENT)
    receipts = (*receipt_chain, accepted_receipt)
    if (
        tuple(item.revision for item in receipts)
        != tuple(range(1, len(receipts) + 1))
        or len(receipts) != accepted_receipt.revision
        or len({item.receipt_id for item in receipts}) != len(receipts)
    ):
        reasons.add(RepositoryAcceptanceReason.RECEIPT_CHAIN_INVALID)
    for index, item in enumerate(receipts):
        expected_predecessor = (
            "0" * 64 if index == 0 else receipts[index - 1].receipt_sha256
        )
        if (
            item.predecessor_receipt_sha256 != expected_predecessor
            or (index > 0 and item.issued_at <= receipts[index - 1].issued_at)
        ):
            reasons.add(RepositoryAcceptanceReason.RECEIPT_CHAIN_INVALID)
        if (
            item.manifest_sha256 != candidate.manifest_sha256
            or item.policy_sha256 != policy_hash
            or item.trust_store_sha256 != trust_hash
            or item.approver_key_id_sha256
            != trust.human_approver.key_id_sha256
            or item.approver_issuer != trust.human_approver.issuer
            or item.issued_at < candidate.assembled_at
            or item.expires_at > candidate.expires_at
        ):
            reason = (
                RepositoryAcceptanceReason.RECEIPT_BINDING_MISMATCH
                if index == len(receipts) - 1
                else RepositoryAcceptanceReason.RECEIPT_CHAIN_INVALID
            )
            reasons.add(reason)
        if not _verify_signature(
            trust.human_approver,
            item.receipt_sha256,
            item.signature_base64url,
        ):
            reasons.add(RepositoryAcceptanceReason.RECEIPT_SIGNATURE_INVALID)
        if item.issued_at > at:
            reasons.add(RepositoryAcceptanceReason.RECEIPT_FUTURE)
        if item.expires_at - item.issued_at > timedelta(
            seconds=selected_policy.maximum_acceptance_ttl_seconds
        ):
            reasons.add(RepositoryAcceptanceReason.RECEIPT_TTL_EXCEEDED)
    if accepted_receipt.expires_at <= at:
        reasons.add(RepositoryAcceptanceReason.RECEIPT_EXPIRED)
    if accepted_receipt.decision is HumanRepositoryDecision.CONDITIONAL:
        reasons.add(RepositoryAcceptanceReason.HUMAN_CONDITIONAL)
    elif accepted_receipt.decision is HumanRepositoryDecision.STOP:
        reasons.add(RepositoryAcceptanceReason.HUMAN_STOP)
    return reasons


def _candidate_local_verification_reasons(
    candidate: RepositoryCandidateManifest,
    *,
    at: datetime,
) -> set[RepositoryAcceptanceReason]:
    reasons: set[RepositoryAcceptanceReason] = set()
    for fact in candidate.verification.facts:
        if not fact.succeeded:
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_FAILED)
        if fact.not_after <= at:
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_EXPIRED)
        if (
            fact.provenance
            is not RepositoryVerificationProvenance.VERIFIED_IMMUTABLE_RUN_V2
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_SYNTHETIC)
    if (
        candidate.integration_verification is None
        or candidate.tco_qa_verification is None
    ):
        reasons.add(RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_MISSING)
    else:
        if (
            candidate.integration_verification.expires_at <= at
            or candidate.tco_qa_verification.expires_at <= at
        ):
            reasons.add(RepositoryAcceptanceReason.VERIFICATION_ATTESTATION_INVALID)
    return reasons


def hash_repository_tree(value: tuple[RepositoryFileDigest, ...]) -> str:
    return _canonical_sha256([item.model_dump(mode="json") for item in value])


def hash_repository_verification_command(
    *,
    command_argv: tuple[str, ...],
    working_directory: str,
    environment_sha256: str,
    network_mode: RepositoryVerificationNetworkMode,
    interpreter_sha256: str,
    import_closure_sha256: str,
) -> str:
    return _canonical_sha256(
        {
            "command_argv": command_argv,
            "working_directory": working_directory,
            "environment_sha256": environment_sha256,
            "network_mode": network_mode.value,
            "interpreter_sha256": interpreter_sha256,
            "import_closure_sha256": import_closure_sha256,
        }
    )


def hash_repository_verification_bundle(
    value: RepositoryVerificationEvidenceBundle,
) -> str:
    return _hash_model(value, excluded={"bundle_sha256"})


def hash_repository_candidate_manifest(value: RepositoryCandidateManifest) -> str:
    return _hash_model(value, excluded={"manifest_sha256"})


def hash_repository_verification_attestation(
    value: RepositoryVerificationAttestation,
) -> str:
    return _hash_model(
        value, excluded={"attestation_sha256", "signature_base64url"}
    )


def hash_repository_acceptance_trust_store(
    value: RepositoryAcceptanceTrustStore,
) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_repository_acceptance_policy(value: RepositoryAcceptancePolicy) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_repository_verification_authority(
    policy: RepositoryAcceptancePolicy,
    trust_store: RepositoryAcceptanceTrustStore,
) -> str:
    return _canonical_sha256(
        {
            "policy_sha256": hash_repository_acceptance_policy(policy),
            "trust_store_sha256": hash_repository_acceptance_trust_store(
                trust_store
            ),
        }
    )


def hash_repository_acceptance_authority_pins(
    value: RepositoryAcceptanceAuthorityPins,
) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def hash_repository_acceptance_authority_bundle(
    value: RepositoryAcceptanceAuthorityBundle,
) -> str:
    return _hash_model(value, excluded={"bundle_sha256"})


def hash_human_repository_acceptance(value: HumanRepositoryAcceptance) -> str:
    return _hash_model(value, excluded={"receipt_sha256", "signature_base64url"})


def hash_repository_acceptance_report(value: RepositoryAcceptanceReport) -> str:
    return _hash_model(value, excluded={"report_sha256"})


def _acceptance_report(
    candidate: RepositoryCandidateManifest,
    observed_tree: str,
    at: datetime,
    reasons: set[RepositoryAcceptanceReason],
    *,
    human_decision: HumanRepositoryDecision | None = None,
) -> RepositoryAcceptanceReport:
    hard_reasons = reasons - {
        RepositoryAcceptanceReason.RECEIPT_MISSING,
        RepositoryAcceptanceReason.HUMAN_CONDITIONAL,
        RepositoryAcceptanceReason.HUMAN_STOP,
    }
    if hard_reasons:
        decision = RepositoryAcceptanceDecision.STOP
    elif human_decision is HumanRepositoryDecision.GO and not reasons:
        decision = RepositoryAcceptanceDecision.ACCEPTED
    elif human_decision is HumanRepositoryDecision.CONDITIONAL:
        decision = RepositoryAcceptanceDecision.CONDITIONAL_PENDING
    elif human_decision is HumanRepositoryDecision.STOP:
        decision = RepositoryAcceptanceDecision.REJECTED
    else:
        decision = RepositoryAcceptanceDecision.PENDING
    accepted = decision is RepositoryAcceptanceDecision.ACCEPTED
    if accepted:
        next_gate = RepositoryRestartGate.RIGHTS_EVIDENCE
        required = RepositoryRequiredInput.CURRENT_RIGHTS_DECISION_RECORDS
    elif reasons.intersection(_LOCAL_VERIFICATION_REASONS):
        next_gate = RepositoryRestartGate.LOCAL_VERIFICATION
        required = RepositoryRequiredInput.CURRENT_SIGNED_VERIFICATION_BUNDLE
    elif reasons.intersection(_ACCEPTANCE_CHAIN_REASONS):
        next_gate = RepositoryRestartGate.REPOSITORY_ACCEPTANCE
        required = RepositoryRequiredInput.CURRENT_PINNED_ACCEPTANCE_CHAIN
    else:
        next_gate = RepositoryRestartGate.REPOSITORY_ACCEPTANCE
        required = RepositoryRequiredInput.HUMAN_SIGNED_REPOSITORY_ACCEPTANCE
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "evaluated_at": at,
        "manifest_sha256": candidate.manifest_sha256,
        "expected_tree_sha256": candidate.tree_sha256,
        "observed_tree_sha256": observed_tree,
        "verification_bundle_sha256": candidate.verification.bundle_sha256,
        "decision": decision,
        "reasons": tuple(sorted(reasons, key=lambda item: item.value)),
        "local_integration_accepted": accepted,
        "next_gate": next_gate,
        "first_external_gate": RepositoryRestartGate.RIGHTS_EVIDENCE,
        "required_inputs": (required,),
        "authority": "none",
        "external_mutation_authorized": False,
        "public_release_authorized": False,
        "production_write_authorized": False,
        "scale_authorized": False,
    }
    provisional = RepositoryAcceptanceReport.model_construct(
        **values, report_sha256="0" * 64
    )
    return RepositoryAcceptanceReport(
        **values,
        report_sha256=hash_repository_acceptance_report(provisional),
    )


def _digest_file(
    root_descriptor: int, relative: str
) -> RepositoryFileDigest:
    name = PurePosixPath(relative).name.lower()
    if name in _FORBIDDEN_SECRET_NAMES or name.startswith(".env.") or name.endswith(
        _FORBIDDEN_SECRET_SUFFIXES
    ):
        raise RepositoryAcceptanceInputError(
            f"secret-bearing filename is forbidden in repository scope: {relative}"
        )
    try:
        descriptor = _open_relative_file(
            root_descriptor, PurePosixPath(relative)
        )
    except OSError as exc:
        raise RepositoryAcceptanceInputError(
            f"repository file is missing or unsafe: {relative}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RepositoryAcceptanceInputError(
                f"repository scope entry is not a regular file: {relative}"
            )
        if before.st_nlink != 1:
            raise RepositoryAcceptanceInputError(
                f"hard-linked file is forbidden in repository scope: {relative}"
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after:
            raise RepositoryAcceptanceInputError(
                f"repository file changed while hashing: {relative}"
            )
        return RepositoryFileDigest(
            path=relative,
            size_bytes=after.st_size,
            executable=bool(after.st_mode & 0o111),
            sha256=digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


def _open_relative_file(root_descriptor: int, relative: PurePosixPath) -> int:
    """Open every path component relative to a stable root dirfd."""

    directory_descriptor = os.dup(root_descriptor)
    try:
        for component in relative.parts[:-1]:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            next_descriptor = os.open(
                component,
                flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        return os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise RepositoryAcceptanceInputError(
            "repository scope escaped the selected root"
        ) from exc
    if unicodedata.normalize("NFC", relative) != relative:
        raise RepositoryAcceptanceInputError("repository path is not NFC-normalized")
    return relative


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _hash_model(value: StrictModel, *, excluded: set[str]) -> str:
    return _canonical_sha256(value.model_dump(mode="json", exclude=excluded))


def _copy(value: Any, model_type: type[StrictModel]) -> Any:
    try:
        return model_type.model_validate(value.model_dump())
    except (AttributeError, TypeError, ValueError) as exc:
        raise RepositoryAcceptanceInputError(
            f"invalid copied {model_type.__name__}"
        ) from exc


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


def _private_key_id(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def _sign(private_key: Ed25519PrivateKey, digest: str) -> str:
    return base64.urlsafe_b64encode(private_key.sign(bytes.fromhex(digest))).decode().rstrip("=")


def _verify_signature(
    key: Ed25519VerificationKey,
    digest: str,
    signature_base64url: str,
) -> bool:
    try:
        signature = base64.urlsafe_b64decode(signature_base64url + "==")
        if len(signature) != 64:
            return False
        key.public_key().verify(signature, bytes.fromhex(digest))
    except (InvalidSignature, ValueError):
        return False
    return True
