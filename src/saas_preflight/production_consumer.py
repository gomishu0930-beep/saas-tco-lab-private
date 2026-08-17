"""Fail-closed local consumer for signed production authority.

The module proves the authority splice and process boundary with synthetic local
state only.  It has no provider endpoint, credential discovery, network client,
deployment, publication, application, email, source-fetch or payment code.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import selectors
import signal
import sqlite3
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import weakref
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from functools import cache
from importlib import metadata
from pathlib import Path
from queue import Empty, Queue
from threading import RLock, Thread
from typing import Any, Callable, Iterator, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    LeaseScope,
    ServingLease,
    SigningRole,
    create_verification_key,
    verify_serving_lease,
)
from .external_actions import (
    ActionEnvironment,
    ActionExecutionClaim,
    ActionReceipt,
    ActionResult,
    ControllerExecutionGrant,
    ExternalAction,
    ExternalActionExecutionGuard,
    ExternalActionInputError,
    ExternalActionRequest,
    ExternalActionRuntime,
    HumanExecutionApproval,
    hash_external_action_policy,
    sign_action_receipt,
    verify_action_receipt,
)
from .launch_handoff import (
    LaunchArtifactComponentKind,
    LaunchHandoffBundle,
    LaunchHandoffDecision,
    LaunchHandoffGate,
    LaunchHandoffPlan,
    LaunchHandoffPolicy,
    LaunchHandoffTrustStore,
    evaluate_launch_handoff,
    hash_launch_handoff_authority,
    hash_launch_handoff_policy,
    hash_launch_handoff_trust_store,
)
from .launch_semantics import (
    LaunchSemanticAuthorityPins,
    LaunchSemanticPacket,
    evaluate_launch_semantics,
    hash_launch_semantic_authority_pins,
)
from .measurement_integrity import (
    MeasurementAuthorityPins,
    MeasurementBoundDossier,
    MeasurementPolicy,
    MeasurementTrustStore,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    verify_measurement_bound_dossier,
)
from .models import Sha256, Slug, StrictModel
from .production_readiness import (
    ProductionBootstrapAuthorization,
    ProductionHumanEnvironmentApproval,
    ProductionIntegrationEvidenceBundle,
    ProductionIntegrationPlan,
    ProductionIntegrationPolicy,
    ProductionIntegrationTrustStore,
    ProductionReadinessAuthorityPins,
    ProductionReadinessReport,
    ProductionReconciliationLedger,
    ProductionTcoQaAttestation,
    hash_production_bootstrap_authorization,
    hash_production_integration_policy,
    hash_production_integration_trust_store,
    hash_production_readiness_report,
    hash_production_tco_qa_attestation,
    verify_production_bootstrap_authorization,
)
from .release_assurance import (
    ReleaseAssuranceReport,
    ReleaseAssuranceRuntime,
    hash_business_dossier,
    verify_release_assurance_report,
)


_PRODUCTION_CONSUMER_RUNTIME_SEAL = object()


_ISOLATED_ADAPTER_LAUNCHER = """
import hashlib,json,os,sys
manifest_fd=int(sys.argv.pop(1))
manifest=json.loads(os.read(manifest_fd,16777217))
paths=json.loads(sys.argv.pop(1))
script=sys.argv.pop(1)
sys.path.extend(path for path in paths if path not in sys.path)
bootstrap=__import__('_frozen_importlib_external')
PathFinder=bootstrap.PathFinder
ExtensionFileLoader=bootstrap.ExtensionFileLoader
pinned_extension_fds=[]

def under(path,root):
    try:
        return os.path.commonpath((path,root)) == root
    except ValueError:
        return False

def pinned_bytes(origin):
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    descriptor=os.open(origin,flags)
    before=os.fstat(descriptor)
    try:
        chunks=[]
        while chunk := os.read(descriptor,1048576):
            chunks.append(chunk)
        after=os.fstat(descriptor)
        identity=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if identity(before) != identity(after) or before.st_nlink != 1:
            raise ImportError('module changed while opening the pinned adapter closure')
        return descriptor,b''.join(chunks)
    except Exception:
        os.close(descriptor)
        raise

class PinnedSourceLoader:
    def __init__(self,fullname,origin,source):
        self.fullname=fullname
        self.origin=origin
        self.source=source
    def create_module(self,spec):
        return None
    def exec_module(self,module):
        exec(compile(self.source,self.origin,'exec'),module.__dict__)

class ClosureGuard:
    def find_spec(self,fullname,path=None,target=None):
        spec=PathFinder.find_spec(fullname,path)
        if spec is None or spec.origin in (None,'built-in','frozen'):
            if spec is not None and spec.origin is None and spec.submodule_search_locations:
                locations=tuple(os.path.abspath(item) for item in spec.submodule_search_locations)
                if any(
                    not any(under(allowed,location) for allowed in manifest)
                    for location in locations
                ):
                    raise ImportError('namespace package is outside the pinned adapter closure')
            return spec
        origin=os.path.abspath(spec.origin)
        expected=manifest.get(origin)
        if expected is None:
            raise ImportError('module is outside the pinned adapter closure: '+fullname+':'+origin)
        descriptor,content=pinned_bytes(origin)
        if hashlib.sha256(content).hexdigest() != expected:
            os.close(descriptor)
            raise ImportError('module changed after adapter closure verification')
        if origin.endswith('.py'):
            os.close(descriptor)
            spec.loader=PinnedSourceLoader(fullname,origin,content)
        else:
            os.lseek(descriptor,0,os.SEEK_SET)
            pinned_extension_fds.append(descriptor)
            descriptor_path='/dev/fd/'+str(descriptor)
            spec.origin=descriptor_path
            spec.loader=ExtensionFileLoader(fullname,descriptor_path)
        return spec

sys.meta_path.insert(0,ClosureGuard())
sys.argv[0]=script
scope={'__name__':'__main__','__file__':script,'__package__':None,'__cached__':None}
exec(compile(open(script,'rb').read(),script,'exec'),scope)
"""

_ADAPTER_RUNTIME_DISTRIBUTIONS = (
    "annotated-types",
    "cffi",
    "cryptography",
    "pydantic",
    "pydantic-core",
    "pycparser",
    "typing-extensions",
    "typing-inspection",
)

_STORE_COORDINATION_TIMEOUT_SECONDS = 5
_STORE_LOCK_POLL_SECONDS = 0.01


class ProductionConsumerError(ValueError):
    """Production authority or durable state failed closed."""


class ProviderOperation(str, Enum):
    ACTIVATE_PUBLIC_RELEASE = "activate_public_release"
    DISABLE_PUBLIC_RELEASE = "disable_public_release"


class ProviderOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ConsumptionState(str, Enum):
    CLAIMED = "claimed"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ProductionSignatureScope(str, Enum):
    GLOBAL_STOP_RESET = "global_stop_reset"
    PROVIDER_DISPATCH = "provider_dispatch"
    PROVIDER_RESULT = "provider_result"
    PROVIDER_PROBE = "provider_probe"


class ProductionClockPurpose(str, Enum):
    RESET = "reset"
    CLAIM = "claim"
    REDEEM = "redeem"
    PRE_PROVIDER = "pre_provider"
    POST_PROVIDER = "post_provider"
    PRE_PROBE = "pre_probe"
    POST_PROBE = "post_probe"
    TERMINAL = "terminal"


class ProductionConsumerClockRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    store_id_sha256: Sha256
    policy_sha256: Sha256
    production_request_sha256: Sha256
    purpose: ProductionClockPurpose
    nonce_sha256: Sha256
    request_sha256: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.request_sha256 != hash_production_consumer_clock_request(self):
            raise ValueError("production clock request hash mismatch")
        return self


class SignedProductionConsumerClockAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_sha256: Sha256
    observed_at: datetime
    issued_at: datetime
    expires_at: datetime
    issuer: str = Field(min_length=1, max_length=120)
    signer_role: Literal[SigningRole.TIME_AUDITOR] = SigningRole.TIME_AUDITOR
    key_id_sha256: Sha256
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production clock timestamp")
        return value

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        if not self.observed_at <= self.issued_at < self.expires_at:
            raise ValueError("production clock timestamps are not ordered")
        _validate_signed_hash(self, "production clock attestation")
        return self


class ProductionAuthorityRootRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    store_id_sha256: Sha256
    policy_sha256: Sha256
    production_request_sha256: Sha256
    purpose: ProductionClockPurpose
    nonce_sha256: Sha256
    request_sha256: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.request_sha256 != hash_production_authority_root_request(self):
            raise ValueError("production authority-root request hash mismatch")
        return self


class SignedProductionAuthorityRoots(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    request_sha256: Sha256
    revision: int = Field(ge=1, le=1_000_000_000)
    repository_acceptance_authority_sha256: Sha256
    launch_handoff_authority_sha256: Sha256
    launch_semantic_authority_sha256: Sha256
    observed_at: datetime
    issued_at: datetime
    expires_at: datetime
    issuer: str = Field(min_length=1, max_length=120)
    signer_role: Literal[SigningRole.STORAGE_AUDITOR] = SigningRole.STORAGE_AUDITOR
    key_id_sha256: Sha256
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at", "issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production authority-root timestamp")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if not self.observed_at <= self.issued_at < self.expires_at:
            raise ValueError("production authority-root timestamps are not ordered")
        _validate_signed_hash(self, "production authority-root snapshot")
        return self


class ProductionConsumerTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    p10_release_controller: Ed25519VerificationKey
    p9_lease_controller: Ed25519VerificationKey
    reset_human: Ed25519VerificationKey
    dispatcher: Ed25519VerificationKey
    provider_adapter: Ed25519VerificationKey
    provider_probe: Ed25519VerificationKey

    @model_validator(mode="after")
    def require_roles_and_separation(self) -> Self:
        expected = (
            (self.p10_release_controller, SigningRole.CONTROLLER),
            (self.p9_lease_controller, SigningRole.CONTROLLER),
            (self.reset_human, SigningRole.HUMAN_APPROVER),
            (self.dispatcher, SigningRole.EXECUTOR),
            (self.provider_adapter, SigningRole.PROVIDER_ADAPTER),
            (self.provider_probe, SigningRole.PROVIDER_PROBE),
        )
        if any(key.role is not role for key, role in expected):
            raise ValueError("production consumer trust-store role mismatch")
        if len({key.key_id_sha256 for key, _ in expected}) != len(expected):
            raise ValueError("production consumer roles require distinct keys")
        return self


class ProviderTargetRule(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    operation: ProviderOperation
    external_action: ExternalAction
    property_record_sha256: Sha256
    target_sha256: Sha256
    expected_pre_state_sha256: Sha256
    expected_post_state_sha256: Sha256
    adapter_id: Slug
    adapter_executable_sha256: Sha256
    probe_executable_sha256: Sha256
    python_executable_sha256: Sha256
    adapter_dependency_closure_sha256: Sha256
    provider_allowlist_sha256: Sha256
    postcondition_schema_sha256: Sha256

    @model_validator(mode="after")
    def require_operation_mapping(self) -> Self:
        expected = {
            ProviderOperation.ACTIVATE_PUBLIC_RELEASE:
                ExternalAction.ACTIVATE_PUBLIC_RELEASE,
            ProviderOperation.DISABLE_PUBLIC_RELEASE:
                ExternalAction.DISABLE_PUBLIC_RELEASE,
        }[self.operation]
        if self.external_action is not expected:
            raise ValueError("provider operation and external action do not match")
        if self.expected_pre_state_sha256 == self.expected_post_state_sha256:
            raise ValueError("provider transition cannot be a no-op")
        return self


class ProductionConsumerPolicy(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    policy_id: Slug
    trust_store_sha256: Sha256
    store_id_sha256: Sha256
    external_action_policy_sha256: Sha256
    release_assurance_policy_sha256: Sha256
    measurement_policy_sha256: Sha256
    measurement_trust_store_sha256: Sha256
    measurement_authority_pins_sha256: Sha256
    production_integration_policy_sha256: Sha256
    production_integration_trust_store_sha256: Sha256
    production_reconciliation_ledger_store_sha256: Sha256
    serving_lease_issuer: Slug
    serving_controller_key_id_sha256: Sha256
    release_assurance_controller_key_id_sha256: Sha256
    maximum_serving_lease_ttl_seconds: int = Field(ge=1, le=3_600)
    maximum_request_ttl_seconds: int = Field(ge=1, le=3_600)
    maximum_dispatch_ttl_seconds: int = Field(ge=1, le=300)
    maximum_reset_ttl_seconds: int = Field(ge=1, le=3_600)
    maximum_provider_receipt_delay_seconds: int = Field(ge=1, le=3_600)
    minimum_provider_authority_margin_seconds: int = Field(ge=1, le=300)
    maximum_clock_attestation_ttl_seconds: int = Field(ge=1, le=300)
    maximum_clock_observation_lag_seconds: int = Field(ge=0, le=60)
    clock_response_timeout_seconds: int = Field(ge=1, le=60)
    maximum_authority_root_ttl_seconds: int = Field(ge=1, le=300)
    maximum_authority_root_observation_lag_seconds: int = Field(ge=0, le=60)
    authority_root_response_timeout_seconds: int = Field(ge=1, le=60)
    target_rules: tuple[ProviderTargetRule, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_canonical_rules(self) -> Self:
        canonical = tuple(sorted(self.target_rules, key=lambda item: item.operation.value))
        if self.target_rules != canonical or len(set(canonical)) != len(canonical):
            raise ValueError("provider target rules must be canonical and unique")
        if {item.operation for item in canonical} != set(ProviderOperation):
            raise ValueError("provider target rules must cover activate and disable")
        activation = next(
            item
            for item in canonical
            if item.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
        )
        disable = next(
            item
            for item in canonical
            if item.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE
        )
        if (
            disable.expected_pre_state_sha256
            != activation.expected_post_state_sha256
            or disable.expected_post_state_sha256
            == activation.expected_post_state_sha256
        ):
            raise ValueError(
                "disable must start at the active state and reach a distinct state"
            )
        shared_target = (
            "property_record_sha256",
            "target_sha256",
            "adapter_id",
            "adapter_executable_sha256",
            "probe_executable_sha256",
            "python_executable_sha256",
            "adapter_dependency_closure_sha256",
            "provider_allowlist_sha256",
            "postcondition_schema_sha256",
        )
        if any(
            getattr(activation, field) != getattr(disable, field)
            for field in shared_target
        ):
            raise ValueError(
                "activate and disable must share one exact provider target contract"
            )
        return self


class ProductionConsumptionRequest(StrictModel):
    schema_version: Literal["4.0"] = "4.0"
    request_id: Slug
    operation: ProviderOperation
    external_request: ExternalActionRequest
    human_approval: HumanExecutionApproval
    controller_grant: ControllerExecutionGrant
    execution_claim: ActionExecutionClaim
    release_report: ReleaseAssuranceReport | None = None
    serving_lease: ServingLease | None = None
    measurement_bundle: MeasurementBoundDossier | None = None
    property_domain_sha256: Sha256 | None = None
    measurement_run_id: Slug | None = None
    measurement_bundle_index_sha256: Sha256 | None = None
    affiliate_partner_ids_sha256: Sha256 | None = None
    production_integration_plan_sha256: Sha256 | None = None
    production_readiness_authorization_sha256: Sha256 | None = None
    repository_acceptance_authority_pins_sha256: Sha256 | None = None
    launch_handoff_authority_sha256: Sha256 | None = None
    launch_handoff_plan_sha256: Sha256 | None = None
    launch_handoff_bundle_sha256: Sha256 | None = None
    launch_semantic_authority_sha256: Sha256 | None = None
    launch_semantic_packet_sha256: Sha256 | None = None
    adapter_id: Slug
    adapter_executable_sha256: Sha256
    probe_executable_sha256: Sha256
    python_executable_sha256: Sha256
    adapter_dependency_closure_sha256: Sha256
    provider_allowlist_sha256: Sha256
    postcondition_schema_sha256: Sha256
    requested_at: datetime
    not_before: datetime
    expires_at: datetime
    request_sha256: Sha256

    @field_validator("requested_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production consumption request time")
        return value

    @model_validator(mode="after")
    def require_complete_action_shape(self) -> Self:
        if not self.requested_at <= self.not_before < self.expires_at:
            raise ValueError("request times must satisfy requested <= not-before < expiry")
        activation = self.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
        gated = (
            self.release_report,
            self.serving_lease,
            self.measurement_bundle,
            self.property_domain_sha256,
            self.measurement_run_id,
            self.measurement_bundle_index_sha256,
            self.affiliate_partner_ids_sha256,
            self.production_integration_plan_sha256,
            self.production_readiness_authorization_sha256,
            self.repository_acceptance_authority_pins_sha256,
            self.launch_handoff_authority_sha256,
            self.launch_handoff_plan_sha256,
            self.launch_handoff_bundle_sha256,
            self.launch_semantic_authority_sha256,
            self.launch_semantic_packet_sha256,
        )
        if activation and any(item is None for item in gated):
            raise ValueError("activation requires P9, P10, P12, and P15 authority")
        if not activation and any(item is not None for item in gated):
            raise ValueError("safety disable cannot carry activation authority")
        expected_action = {
            ProviderOperation.ACTIVATE_PUBLIC_RELEASE:
                ExternalAction.ACTIVATE_PUBLIC_RELEASE,
            ProviderOperation.DISABLE_PUBLIC_RELEASE:
                ExternalAction.DISABLE_PUBLIC_RELEASE,
        }[self.operation]
        if (
            self.external_request.action is not expected_action
            or self.external_request.environment is not ActionEnvironment.PRODUCTION
        ):
            raise ValueError("request operation is not bound to the P11 action")
        expected = hash_production_consumption_request(self)
        if self.request_sha256 != expected:
            raise ValueError("production request hash mismatch")
        return self


class GlobalStopSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    store_id_sha256: Sha256
    policy_sha256: Sha256
    stopped: bool
    epoch: int = Field(ge=0)
    revision: int = Field(ge=0)
    head_sha256: Sha256
    stop_reason_sha256: Sha256
    stopped_at: datetime
    anchor_sha256: Sha256

    @field_validator("stopped_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "global STOP time")
        return value


class HumanGlobalStopReset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER] = SigningRole.HUMAN_APPROVER
    scope: Literal[ProductionSignatureScope.GLOBAL_STOP_RESET] = (
        ProductionSignatureScope.GLOBAL_STOP_RESET
    )
    store_id_sha256: Sha256
    policy_sha256: Sha256
    stopped_epoch: int = Field(ge=0)
    stopped_revision: int = Field(ge=0)
    stopped_head_sha256: Sha256
    stop_reason_sha256: Sha256
    remediation_record_sha256: Sha256
    reconciliation_record_sha256: Sha256
    nonce_sha256: Sha256
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "global STOP reset time")
        return value

    @model_validator(mode="after")
    def validate_reset(self) -> Self:
        if not self.issued_at <= self.not_before < self.expires_at:
            raise ValueError("reset times must satisfy issued <= not-before < expiry")
        _validate_signed_hash(self, "global STOP reset")
        return self


class ProviderDispatchToken(StrictModel):
    schema_version: Literal["4.0"] = "4.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.EXECUTOR] = SigningRole.EXECUTOR
    scope: Literal[ProductionSignatureScope.PROVIDER_DISPATCH] = (
        ProductionSignatureScope.PROVIDER_DISPATCH
    )
    store_id_sha256: Sha256
    policy_sha256: Sha256
    request_sha256: Sha256
    p11_claim_sha256: Sha256
    production_integration_plan_sha256: Sha256 | None = None
    production_readiness_authorization_sha256: Sha256 | None = None
    repository_acceptance_authority_pins_sha256: Sha256 | None = None
    launch_handoff_authority_sha256: Sha256 | None = None
    launch_handoff_plan_sha256: Sha256 | None = None
    launch_handoff_bundle_sha256: Sha256 | None = None
    launch_semantic_authority_sha256: Sha256 | None = None
    launch_semantic_packet_sha256: Sha256 | None = None
    epoch: int = Field(ge=0)
    fencing_token: int = Field(ge=1)
    operation: ProviderOperation
    adapter_id: Slug
    adapter_executable_sha256: Sha256
    probe_executable_sha256: Sha256
    python_executable_sha256: Sha256
    adapter_dependency_closure_sha256: Sha256
    provider_allowlist_sha256: Sha256
    postcondition_schema_sha256: Sha256
    target_sha256: Sha256
    idempotency_key_sha256: Sha256
    expected_pre_state_sha256: Sha256
    expected_post_state_sha256: Sha256
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "provider dispatch time")
        return value

    @model_validator(mode="after")
    def validate_token(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("dispatch expiry must follow issuance")
        readiness = (
            self.production_integration_plan_sha256,
            self.production_readiness_authorization_sha256,
            self.repository_acceptance_authority_pins_sha256,
            self.launch_handoff_authority_sha256,
            self.launch_handoff_plan_sha256,
            self.launch_handoff_bundle_sha256,
            self.launch_semantic_authority_sha256,
            self.launch_semantic_packet_sha256,
        )
        activation = self.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
        if activation and any(item is None for item in readiness):
            raise ValueError("activation dispatch requires P15 readiness authority")
        if not activation and any(item is not None for item in readiness):
            raise ValueError("safety disable cannot carry P15 activation authority")
        _validate_signed_hash(self, "provider dispatch")
        return self


class ProviderResultReceipt(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.PROVIDER_ADAPTER] = SigningRole.PROVIDER_ADAPTER
    scope: Literal[ProductionSignatureScope.PROVIDER_RESULT] = (
        ProductionSignatureScope.PROVIDER_RESULT
    )
    dispatch_payload_sha256: Sha256
    store_id_sha256: Sha256
    epoch: int = Field(ge=0)
    fencing_token: int = Field(ge=1)
    operation: ProviderOperation
    adapter_id: Slug
    target_sha256: Sha256
    idempotency_key_sha256: Sha256
    outcome: ProviderOutcome
    observed_pre_state_sha256: Sha256
    observed_post_state_sha256: Sha256
    provider_audit_receipt_sha256: Sha256
    started_at: datetime
    completed_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "provider result time")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("provider result cannot complete before it starts")
        _validate_signed_hash(self, "provider result")
        return self


class ProviderProbeReceipt(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.PROVIDER_PROBE] = SigningRole.PROVIDER_PROBE
    scope: Literal[ProductionSignatureScope.PROVIDER_PROBE] = (
        ProductionSignatureScope.PROVIDER_PROBE
    )
    dispatch_payload_sha256: Sha256
    store_id_sha256: Sha256
    epoch: int = Field(ge=0)
    fencing_token: int = Field(ge=1)
    operation: ProviderOperation
    adapter_id: Slug
    target_sha256: Sha256
    observed_post_state_sha256: Sha256
    probed_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("probed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "provider probe time")
        return value

    @model_validator(mode="after")
    def validate_probe(self) -> Self:
        _validate_signed_hash(self, "provider probe")
        return self


class ProductionConsumptionResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_sha256: Sha256
    dispatch_payload_sha256: Sha256
    epoch: int = Field(ge=0)
    fencing_token: int = Field(ge=1)
    state: ConsumptionState
    provider_receipt: ProviderResultReceipt | None = None
    probe_receipt: ProviderProbeReceipt | None = None
    action_receipt: ActionReceipt | None = None
    terminal_at: datetime
    result_sha256: Sha256

    @field_validator("terminal_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "production result time")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        success = self.state is ConsumptionState.SUCCEEDED
        artifacts = (self.provider_receipt, self.probe_receipt, self.action_receipt)
        if success and not all(item is not None for item in artifacts):
            raise ValueError("exact success requires all terminal receipts")
        if not success and (
            self.probe_receipt is not None or self.action_receipt is not None
        ):
            raise ValueError("non-success cannot carry success-only receipts")
        expected = hash_production_result(self)
        if self.result_sha256 != expected:
            raise ValueError("production result hash mismatch")
        return self


def hash_production_consumer_trust_store(store: ProductionConsumerTrustStore) -> str:
    return _canonical_sha256(ProductionConsumerTrustStore.model_validate(store.model_dump()))


def hash_production_consumer_policy(policy: ProductionConsumerPolicy) -> str:
    return _canonical_sha256(ProductionConsumerPolicy.model_validate(policy.model_dump()))


def hash_production_consumer_clock_request(
    request: ProductionConsumerClockRequest,
) -> str:
    return _hash_without(request, {"request_sha256"})


def sign_production_consumer_clock_attestation(
    request: ProductionConsumerClockRequest,
    trust_store: ProductionIntegrationTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    observed_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedProductionConsumerClockAttestation:
    selected = ProductionConsumerClockRequest.model_validate(request.model_dump())
    trust = ProductionIntegrationTrustStore.model_validate(trust_store.model_dump())
    if not _private_key_matches(signing_key, trust.time_auditor):
        raise ProductionConsumerError("production clock signing key mismatch")
    return _build_signed_model(
        SignedProductionConsumerClockAttestation,
        {
            "schema_version": "1.0",
            "request_sha256": selected.request_sha256,
            "observed_at": observed_at,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "issuer": trust.time_auditor.issuer,
            "signer_role": SigningRole.TIME_AUDITOR,
        },
        signing_key,
        issuer=trust.time_auditor.issuer,
        role=SigningRole.TIME_AUDITOR,
    )


def hash_production_authority_root_request(
    request: ProductionAuthorityRootRequest,
) -> str:
    return _hash_without(request, {"request_sha256"})


def sign_production_authority_roots(
    request: ProductionAuthorityRootRequest,
    trust_store: ProductionIntegrationTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    revision: int,
    repository_acceptance_authority_sha256: str,
    launch_handoff_authority_sha256: str,
    launch_semantic_authority_sha256: str,
    observed_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedProductionAuthorityRoots:
    selected = ProductionAuthorityRootRequest.model_validate(request.model_dump())
    trust = ProductionIntegrationTrustStore.model_validate(trust_store.model_dump())
    if not _private_key_matches(signing_key, trust.storage_auditor):
        raise ProductionConsumerError("production authority-root signing key mismatch")
    return _build_signed_model(
        SignedProductionAuthorityRoots,
        {
            "schema_version": "2.0",
            "request_sha256": selected.request_sha256,
            "revision": revision,
            "repository_acceptance_authority_sha256": (
                repository_acceptance_authority_sha256
            ),
            "launch_handoff_authority_sha256": launch_handoff_authority_sha256,
            "launch_semantic_authority_sha256": launch_semantic_authority_sha256,
            "observed_at": observed_at,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "issuer": trust.storage_auditor.issuer,
            "signer_role": SigningRole.STORAGE_AUDITOR,
        },
        signing_key,
        issuer=trust.storage_auditor.issuer,
        role=SigningRole.STORAGE_AUDITOR,
    )


def hash_measurement_authority_pins(pins: MeasurementAuthorityPins) -> str:
    return hash_signed_artifact(MeasurementAuthorityPins.model_validate(pins.model_dump()))


def hash_production_consumption_request(request: ProductionConsumptionRequest) -> str:
    return _hash_without(request, {"request_sha256"})


def hash_production_result(result: ProductionConsumptionResult) -> str:
    return _hash_without(result, {"result_sha256"})


def hash_production_adapter_readiness_closure(
    request: ProductionConsumptionRequest,
) -> str:
    return _production_adapter_readiness_closure(request)


def hash_production_probe_readiness_closure(
    request: ProductionConsumptionRequest,
) -> str:
    return _production_probe_readiness_closure(request)


def _production_adapter_readiness_closure(
    request: ProductionConsumptionRequest,
) -> str:
    return _canonical_sha256(
        {
            "adapter_id": request.adapter_id,
            "adapter_executable_sha256": request.adapter_executable_sha256,
            "python_executable_sha256": request.python_executable_sha256,
            "dependency_closure_sha256": request.adapter_dependency_closure_sha256,
        }
    )


def _production_probe_readiness_closure(
    request: ProductionConsumptionRequest,
) -> str:
    return _canonical_sha256(
        {
            "adapter_id": request.adapter_id,
            "probe_executable_sha256": request.probe_executable_sha256,
            "python_executable_sha256": request.python_executable_sha256,
            "dependency_closure_sha256": request.adapter_dependency_closure_sha256,
        }
    )


def _file_sha256(
    path: str | Path,
    *,
    absolute_deadline: float | None = None,
) -> str:
    selected = Path(os.path.abspath(os.fspath(path)))
    if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
        raise ProductionConsumerError(
            "adapter subprocess execution deadline is exhausted"
        )
    try:
        descriptor, before = _open_regular_file_no_follow(selected)
    except OSError as exc:
        raise ProductionConsumerError(f"pinned file is unavailable: {selected.name}") from exc
    digest = hashlib.sha256()
    try:
        while chunk := os.read(descriptor, 1_048_576):
            digest.update(chunk)
            if (
                absolute_deadline is not None
                and time.monotonic() >= absolute_deadline
            ):
                raise ProductionConsumerError(
                    "adapter subprocess execution deadline is exhausted"
                )
        _require_unchanged_file(descriptor, before, selected.name)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _open_regular_file_no_follow(path: Path) -> tuple[int, os.stat_result]:
    """Open an absolute regular file without following any path component."""

    selected = Path(os.path.abspath(os.fspath(path)))
    if not selected.is_absolute() or selected.name in {"", ".", ".."}:
        raise OSError("invalid pinned file path")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(selected.anchor, directory_flags)
    try:
        for component in selected.parts[1:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(
            selected.name,
            file_flags,
            dir_fd=descriptor,
        )
    finally:
        os.close(descriptor)
    before = os.fstat(file_descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        os.close(file_descriptor)
        raise OSError("pinned path is not one unlinked regular file")
    return file_descriptor, before


def _require_unchanged_file(
    descriptor: int,
    before: os.stat_result,
    label: str,
) -> None:
    after = os.fstat(descriptor)
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if identity(before) != identity(after):
        raise ProductionConsumerError(f"pinned file changed while open: {label}")


def _read_pinned_bytes(path: Path) -> bytes:
    try:
        descriptor, before = _open_regular_file_no_follow(path)
    except OSError as exc:
        raise ProductionConsumerError(
            f"pinned file is unavailable: {path.name}"
        ) from exc
    chunks: list[bytes] = []
    try:
        while chunk := os.read(descriptor, 1_048_576):
            chunks.append(chunk)
        _require_unchanged_file(descriptor, before, path.name)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def hash_adapter_dependency_closure(paths: tuple[str | Path, ...]) -> str:
    """Hash every importable file in the fixed adapter closure."""

    selected = tuple(Path(path).absolute() for path in paths)
    return _hash_adapter_dependency_manifest(
        selected, _adapter_dependency_manifest(selected)
    )


def production_adapter_dependency_paths() -> tuple[Path, ...]:
    """Return source plus exact third-party import files for the P13 fixture."""

    package = Path(__file__).resolve().parent
    selected = {path.absolute() for path in package.glob("*.py")}
    runtime_roots = {
        Path(
            sysconfig.get_path(
                name,
                vars={"base": sys.base_prefix, "platbase": sys.base_prefix},
            )
        ).resolve()
        for name in ("stdlib", "platstdlib")
    }
    for runtime_root in runtime_roots:
        for located in runtime_root.rglob("*"):
            if (
                located.is_file()
                and located.suffix in {".py", ".so", ".pyd"}
                and "site-packages" not in located.parts
                and "__pycache__" not in located.parts
            ):
                selected.add(located.absolute())
    for distribution_name in _ADAPTER_RUNTIME_DISTRIBUTIONS:
        try:
            distribution = metadata.distribution(distribution_name)
        except metadata.PackageNotFoundError as exc:
            raise ProductionConsumerError(
                f"required adapter distribution is missing: {distribution_name}"
            ) from exc
        for relative in distribution.files or ():
            if not str(relative).endswith((".py", ".so", ".pyd")):
                continue
            located = Path(distribution.locate_file(relative)).absolute()
            if located.is_file():
                selected.add(located)
    return tuple(sorted(selected, key=_adapter_dependency_label))


@cache
def _adapter_dependency_roots() -> tuple[tuple[str, Path], ...]:
    """Return immutable interpreter roots without recomputing sysconfig per file."""

    return (
        ("source", Path(__file__).resolve().parents[1]),
        ("purelib", Path(sysconfig.get_path("purelib")).absolute()),
        ("platlib", Path(sysconfig.get_path("platlib")).absolute()),
        (
            "stdlib",
            Path(
                sysconfig.get_path(
                    "stdlib",
                    vars={
                        "base": sys.base_prefix,
                        "platbase": sys.base_prefix,
                    },
                )
            ).resolve(),
        ),
    )


def _adapter_dependency_label(path: Path) -> str:
    selected = path.absolute()
    roots = _adapter_dependency_roots()
    for prefix, root in roots:
        try:
            relative = selected.relative_to(root)
        except ValueError:
            continue
        return f"{prefix}/{relative.as_posix()}"
    raise ProductionConsumerError("adapter dependency is outside fixed runtime roots")


def _adapter_dependency_manifest(
    paths: tuple[Path, ...],
    *,
    absolute_deadline: float | None = None,
) -> dict[str, str]:
    manifest = {
        str(path.absolute()): _file_sha256(
            path,
            absolute_deadline=absolute_deadline,
        )
        for path in paths
    }
    if len(manifest) != len(paths):
        raise ProductionConsumerError("adapter dependency closure is ambiguous")
    return manifest


def _hash_adapter_dependency_manifest(
    paths: tuple[Path, ...], manifest: dict[str, str]
) -> str:
    entries = sorted(
        (_adapter_dependency_label(path), manifest[str(path.absolute())])
        for path in paths
    )
    if (
        not entries
        or len(entries) != len(manifest)
        or len({name for name, _ in entries}) != len(entries)
    ):
        raise ProductionConsumerError(
            "adapter dependency closure is empty or ambiguous"
        )
    return _canonical_sha256(entries)


def build_production_consumption_request(**values: Any) -> ProductionConsumptionRequest:
    provisional = ProductionConsumptionRequest.model_construct(
        **values, request_sha256="0" * 64
    )
    return ProductionConsumptionRequest(
        **values, request_sha256=hash_production_consumption_request(provisional)
    )


def sign_global_stop_reset(
    snapshot: GlobalStopSnapshot,
    policy: ProductionConsumerPolicy,
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    remediation_record_sha256: str,
    reconciliation_record_sha256: str,
    nonce_sha256: str,
    issued_at: datetime,
    not_before: datetime,
    expires_at: datetime,
) -> HumanGlobalStopReset:
    return _build_signed_model(
        HumanGlobalStopReset,
        {
            "issuer": issuer,
            "signer_role": SigningRole.HUMAN_APPROVER,
            "scope": ProductionSignatureScope.GLOBAL_STOP_RESET,
            "store_id_sha256": snapshot.store_id_sha256,
            "policy_sha256": hash_production_consumer_policy(policy),
            "stopped_epoch": snapshot.epoch,
            "stopped_revision": snapshot.revision,
            "stopped_head_sha256": snapshot.head_sha256,
            "stop_reason_sha256": snapshot.stop_reason_sha256,
            "remediation_record_sha256": remediation_record_sha256,
            "reconciliation_record_sha256": reconciliation_record_sha256,
            "nonce_sha256": nonce_sha256,
            "issued_at": issued_at,
            "not_before": not_before,
            "expires_at": expires_at,
        },
        private_key,
        issuer=issuer,
        role=SigningRole.HUMAN_APPROVER,
    )


class ProductionConsumerRuntime:
    """Read-only verifier whose pins are supplied only at bootstrap."""

    __slots__ = (
        "policy", "policy_sha256", "trust", "external_runtime", "external_guard",
        "release_runtime", "measurement_policy", "measurement_trust",
        "measurement_pins", "integration_plan", "integration_policy",
        "integration_trust", "integration_bundle", "integration_report",
        "integration_tco", "integration_human", "integration_authorization",
        "integration_pins", "integration_authorization_sha256",
        "reconciliation_ledger", "launch_bundle", "launch_plan",
        "launch_policy", "launch_trust", "repository_authority_root_sha256",
        "launch_authority_root_sha256", "launch_semantic_packet",
        "launch_semantic_pins", "launch_semantic_authority_root_sha256",
        "_clock_attest",
        "_current_authority_roots",
        "_runtime_seal",
    )

    def __init__(
        self,
        policy: ProductionConsumerPolicy,
        trust_store: ProductionConsumerTrustStore,
        *,
        external_runtime: ExternalActionRuntime,
        external_guard: ExternalActionExecutionGuard,
        release_runtime: ReleaseAssuranceRuntime,
        measurement_policy: MeasurementPolicy,
        measurement_trust_store: MeasurementTrustStore,
        measurement_authority_pins: MeasurementAuthorityPins,
        production_integration_plan: ProductionIntegrationPlan,
        production_integration_policy: ProductionIntegrationPolicy,
        production_integration_trust_store: ProductionIntegrationTrustStore,
        production_integration_bundle: ProductionIntegrationEvidenceBundle,
        production_readiness_report: ProductionReadinessReport,
        production_tco_qa_attestation: ProductionTcoQaAttestation,
        production_human_environment_approval: ProductionHumanEnvironmentApproval,
        production_bootstrap_authorization: ProductionBootstrapAuthorization,
        production_readiness_authority_pins: ProductionReadinessAuthorityPins,
        production_reconciliation_ledger: ProductionReconciliationLedger,
        launch_handoff_bundle: LaunchHandoffBundle,
        launch_handoff_plan: LaunchHandoffPlan,
        launch_handoff_policy: LaunchHandoffPolicy,
        launch_handoff_trust_store: LaunchHandoffTrustStore,
        launch_semantic_packet: LaunchSemanticPacket,
        launch_semantic_authority_pins: LaunchSemanticAuthorityPins,
        expected_repository_acceptance_authority_pins_sha256: str,
        expected_launch_handoff_authority_sha256: str,
        expected_launch_semantic_authority_pins_sha256: str,
        clock_attest: Callable[
            [ProductionConsumerClockRequest],
            SignedProductionConsumerClockAttestation,
        ],
        current_authority_roots: Callable[
            [ProductionAuthorityRootRequest],
            SignedProductionAuthorityRoots,
        ],
    ) -> None:
        self.policy = ProductionConsumerPolicy.model_validate(policy.model_dump())
        self.trust = ProductionConsumerTrustStore.model_validate(trust_store.model_dump())
        self.policy_sha256 = hash_production_consumer_policy(self.policy)
        if self.policy.trust_store_sha256 != hash_production_consumer_trust_store(self.trust):
            raise ProductionConsumerError("production trust-store pin mismatch")
        if type(external_runtime) is not ExternalActionRuntime or type(
            external_guard
        ) is not ExternalActionExecutionGuard:
            raise TypeError("P11 runtime and durable guard are required")
        if external_guard.runtime is not external_runtime:
            raise ProductionConsumerError("P11 guard/runtime identity mismatch")
        if (
            self.policy.external_action_policy_sha256
            != hash_external_action_policy(external_runtime.policy)
            or self.trust.dispatcher.key_id_sha256
            != external_runtime.trust_store.executor.key_id_sha256
            or self.trust.reset_human.key_id_sha256
            in {
                external_runtime.trust_store.human.key_id_sha256,
                external_runtime.trust_store.controller.key_id_sha256,
            }
        ):
            raise ProductionConsumerError("P11 authority splice pin mismatch")
        if type(release_runtime) is not ReleaseAssuranceRuntime:
            raise TypeError("P10 release runtime is required")
        self.release_runtime = release_runtime
        self.external_runtime = external_runtime
        self.external_guard = external_guard
        self.measurement_policy = MeasurementPolicy.model_validate(
            measurement_policy.model_dump()
        )
        self.measurement_trust = MeasurementTrustStore.model_validate(
            measurement_trust_store.model_dump()
        )
        self.measurement_pins = MeasurementAuthorityPins.model_validate(
            measurement_authority_pins.model_dump()
        )
        self.integration_plan = ProductionIntegrationPlan.model_validate(
            production_integration_plan.model_dump()
        )
        self.integration_policy = ProductionIntegrationPolicy.model_validate(
            production_integration_policy.model_dump()
        )
        self.integration_trust = ProductionIntegrationTrustStore.model_validate(
            production_integration_trust_store.model_dump()
        )
        self.integration_bundle = ProductionIntegrationEvidenceBundle.model_validate(
            production_integration_bundle.model_dump()
        )
        self.integration_report = ProductionReadinessReport.model_validate(
            production_readiness_report.model_dump()
        )
        self.integration_tco = ProductionTcoQaAttestation.model_validate(
            production_tco_qa_attestation.model_dump()
        )
        self.integration_human = ProductionHumanEnvironmentApproval.model_validate(
            production_human_environment_approval.model_dump()
        )
        self.integration_authorization = ProductionBootstrapAuthorization.model_validate(
            production_bootstrap_authorization.model_dump()
        )
        self.integration_pins = ProductionReadinessAuthorityPins.model_validate(
            production_readiness_authority_pins.model_dump()
        )
        self.integration_authorization_sha256 = hash_production_bootstrap_authorization(
            self.integration_authorization
        )
        self.launch_bundle = LaunchHandoffBundle.model_validate(
            launch_handoff_bundle.model_dump()
        )
        self.launch_plan = LaunchHandoffPlan.model_validate(
            launch_handoff_plan.model_dump()
        )
        self.launch_policy = LaunchHandoffPolicy.model_validate(
            launch_handoff_policy.model_dump()
        )
        self.launch_trust = LaunchHandoffTrustStore.model_validate(
            launch_handoff_trust_store.model_dump()
        )
        self.launch_semantic_packet = LaunchSemanticPacket.model_validate(
            launch_semantic_packet.model_dump()
        )
        self.launch_semantic_pins = LaunchSemanticAuthorityPins.model_validate(
            launch_semantic_authority_pins.model_dump()
        )
        if not _is_sha256(expected_repository_acceptance_authority_pins_sha256):
            raise ProductionConsumerError("P18 authority root is invalid")
        if not _is_sha256(expected_launch_handoff_authority_sha256):
            raise ProductionConsumerError("P16 authority root is invalid")
        if not _is_sha256(expected_launch_semantic_authority_pins_sha256):
            raise ProductionConsumerError("launch semantic authority root is invalid")
        self.repository_authority_root_sha256 = (
            expected_repository_acceptance_authority_pins_sha256
        )
        self.launch_authority_root_sha256 = expected_launch_handoff_authority_sha256
        self.launch_semantic_authority_root_sha256 = (
            expected_launch_semantic_authority_pins_sha256
        )
        if not callable(clock_attest) or not callable(current_authority_roots):
            raise TypeError("production authority service callbacks are required")
        self._clock_attest = clock_attest
        self._current_authority_roots = current_authority_roots
        if (
            self.launch_plan.handoff_policy_sha256
            != hash_launch_handoff_policy(self.launch_policy)
            or self.launch_plan.trust_store_sha256
            != hash_launch_handoff_trust_store(self.launch_trust)
            or self.launch_bundle.plan_sha256 != self.launch_plan.plan_sha256
            or self.launch_bundle.bundle_sha256 == "0" * 64
            or self.launch_plan.repository_acceptance_authority_pins_sha256
            != self.repository_authority_root_sha256
            or hash_launch_handoff_authority(
                self.launch_plan, self.launch_policy, self.launch_trust
            )
            != self.launch_authority_root_sha256
            or self.launch_bundle.launch_semantics != self.launch_semantic_packet
            or self.launch_semantic_packet.packet_sha256
            != self.launch_semantic_pins.expected_packet_sha256
            or hash_launch_semantic_authority_pins(self.launch_semantic_pins)
            != self.launch_semantic_authority_root_sha256
            or self.launch_plan.launch_semantic_authority_pins_sha256
            != self.launch_semantic_authority_root_sha256
        ):
            raise ProductionConsumerError("P16/P18 execution authority pin mismatch")
        if type(production_reconciliation_ledger) is not ProductionReconciliationLedger:
            raise TypeError("authenticated P15 reconciliation ledger is required")
        self.reconciliation_ledger = production_reconciliation_ledger
        measurement_key_ids = {
            key.key_id_sha256
            for key in (
                self.measurement_trust.run_human,
                self.measurement_trust.demand_producer,
                self.measurement_trust.cohort_producer,
                self.measurement_trust.operations_producer,
                self.measurement_trust.bundle_indexer,
                self.measurement_trust.measurement_verifier,
            )
        }
        p11_non_dispatch_ids = {
            external_runtime.trust_store.controller.key_id_sha256,
            external_runtime.trust_store.human.key_id_sha256,
        }
        consumer_key_ids = {
            self.trust.p10_release_controller.key_id_sha256,
            self.trust.p9_lease_controller.key_id_sha256,
            self.trust.reset_human.key_id_sha256,
            self.trust.dispatcher.key_id_sha256,
            self.trust.provider_adapter.key_id_sha256,
            self.trust.provider_probe.key_id_sha256,
        }
        integration_key_ids = {
            key.key_id_sha256
            for key in (
                self.integration_trust.controller,
                self.integration_trust.provider_conformance,
                self.integration_trust.independent_probe,
                self.integration_trust.security_auditor,
                self.integration_trust.storage_auditor,
                self.integration_trust.time_auditor,
                self.integration_trust.network_auditor,
                self.integration_trust.recovery_auditor,
                self.integration_trust.tco_qa,
                self.integration_trust.environment_human,
            )
        }
        launch_key_ids = {
            self.launch_trust.human_approver.key_id_sha256,
            self.launch_trust.tco_qa.key_id_sha256,
        }
        if (
            self.policy.measurement_policy_sha256
            != hash_measurement_policy(self.measurement_policy)
            or self.policy.measurement_trust_store_sha256
            != hash_measurement_trust_store(self.measurement_trust)
            or self.policy.measurement_authority_pins_sha256
            != hash_measurement_authority_pins(self.measurement_pins)
            or self.policy.release_assurance_policy_sha256
            != release_runtime.assurance_policy_sha256
            or release_runtime.controller_key != self.trust.p10_release_controller
            or self.policy.release_assurance_controller_key_id_sha256
            != self.trust.p10_release_controller.key_id_sha256
            or self.policy.serving_controller_key_id_sha256
            != self.trust.p9_lease_controller.key_id_sha256
            or consumer_key_ids & measurement_key_ids
            or consumer_key_ids & p11_non_dispatch_ids
            or measurement_key_ids & p11_non_dispatch_ids
            or external_runtime.trust_store.executor.key_id_sha256
            in measurement_key_ids
            or self.policy.production_integration_policy_sha256
            != hash_production_integration_policy(self.integration_policy)
            or self.policy.production_integration_trust_store_sha256
            != hash_production_integration_trust_store(self.integration_trust)
            or self.integration_policy.trust_store_sha256
            != self.policy.production_integration_trust_store_sha256
            or self.integration_plan.p13_policy_sha256 != self.policy_sha256
            or self.integration_plan.p13_store_identity_sha256
            != self.policy.store_id_sha256
            or self.integration_plan.p11_policy_sha256
            != self.policy.external_action_policy_sha256
            or self.integration_plan.p11_store_identity_sha256
            != external_guard.state_store_id_sha256
            or self.reconciliation_ledger.plan_sha256
            != self.integration_plan.plan_sha256
            or self.integration_plan.reconciliation_ledger_store_sha256
            != self.policy.production_reconciliation_ledger_store_sha256
            or self.reconciliation_ledger.store_id_sha256
            != self.policy.production_reconciliation_ledger_store_sha256
            or self.reconciliation_ledger.trust_store_sha256
            != self.policy.production_integration_trust_store_sha256
            or integration_key_ids
            & (consumer_key_ids | measurement_key_ids | p11_non_dispatch_ids)
            or launch_key_ids
            & (
                consumer_key_ids
                | measurement_key_ids
                | p11_non_dispatch_ids
                | integration_key_ids
            )
        ):
            raise ProductionConsumerError("P9/P10/P12/P15/P16 consumer pin mismatch")
        self._runtime_seal = _PRODUCTION_CONSUMER_RUNTIME_SEAL

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_runtime_seal", None) is _PRODUCTION_CONSUMER_RUNTIME_SEAL:
            raise AttributeError("production runtime is sealed")
        object.__setattr__(self, name, value)

    def assert_sealed(self) -> None:
        """Reject duck-typed, partially initialized, or mutated authority runtimes."""

        if (
            type(self) is not ProductionConsumerRuntime
            or getattr(self, "_runtime_seal", None)
            is not _PRODUCTION_CONSUMER_RUNTIME_SEAL
            or self.policy_sha256 != hash_production_consumer_policy(self.policy)
            or self.policy.trust_store_sha256
            != hash_production_consumer_trust_store(self.trust)
            or self.policy.production_integration_policy_sha256
            != hash_production_integration_policy(self.integration_policy)
            or self.policy.production_integration_trust_store_sha256
            != hash_production_integration_trust_store(self.integration_trust)
        ):
            raise ProductionConsumerError("production runtime seal is invalid")

    def authoritative_phase(
        self,
        *,
        subject_sha256: str,
        purpose: ProductionClockPurpose,
        require_current_roots: bool,
        minimum_observed_at: datetime,
        minimum_root_revision: int,
    ) -> tuple[
        datetime,
        SignedProductionConsumerClockAttestation,
        SignedProductionAuthorityRoots | None,
    ]:
        """Obtain fresh signed time/root facts for every mutation-capable API."""

        _require_utc(minimum_observed_at, "minimum production authority time")
        request_values = {
            "store_id_sha256": self.policy.store_id_sha256,
            "policy_sha256": self.policy_sha256,
            "production_request_sha256": subject_sha256,
            "purpose": purpose,
            "nonce_sha256": hashlib.sha256(os.urandom(32)).hexdigest(),
        }
        provisional = ProductionConsumerClockRequest.model_construct(
            **request_values, schema_version="1.0", request_sha256="0" * 64
        )
        clock_request = ProductionConsumerClockRequest(
            **request_values,
            request_sha256=hash_production_consumer_clock_request(provisional),
        )
        clock = _invoke_authority_callback(
            self._clock_attest,
            clock_request,
            SignedProductionConsumerClockAttestation,
            timeout_seconds=self.policy.clock_response_timeout_seconds,
            label="production trusted clock",
        )
        if (
            clock.request_sha256 != clock_request.request_sha256
            or not _verify_signed(clock, self.integration_trust.time_auditor)
            or clock.expires_at - clock.issued_at
            > timedelta(seconds=self.policy.maximum_clock_attestation_ttl_seconds)
            or clock.issued_at - clock.observed_at
            > timedelta(seconds=self.policy.maximum_clock_observation_lag_seconds)
            or clock.observed_at < minimum_observed_at
        ):
            raise ProductionConsumerError(
                "production trusted clock attestation is invalid"
            )
        roots: SignedProductionAuthorityRoots | None = None
        if require_current_roots:
            root_values = {
                "store_id_sha256": self.policy.store_id_sha256,
                "policy_sha256": self.policy_sha256,
                "production_request_sha256": subject_sha256,
                "purpose": purpose,
                "nonce_sha256": hashlib.sha256(os.urandom(32)).hexdigest(),
            }
            root_provisional = ProductionAuthorityRootRequest.model_construct(
                **root_values, schema_version="1.0", request_sha256="0" * 64
            )
            root_request = ProductionAuthorityRootRequest(
                **root_values,
                request_sha256=hash_production_authority_root_request(
                    root_provisional
                ),
            )
            roots = _invoke_authority_callback(
                self._current_authority_roots,
                root_request,
                SignedProductionAuthorityRoots,
                timeout_seconds=self.policy.authority_root_response_timeout_seconds,
                label="production authority-root resolver",
            )
            if (
                roots.request_sha256 != root_request.request_sha256
                or not _verify_signed(
                    roots, self.integration_trust.storage_auditor
                )
                or roots.repository_acceptance_authority_sha256
                != self.repository_authority_root_sha256
                or roots.launch_handoff_authority_sha256
                != self.launch_authority_root_sha256
                or roots.launch_semantic_authority_sha256
                != self.launch_semantic_authority_root_sha256
                or not roots.observed_at <= clock.observed_at < roots.expires_at
                or roots.expires_at - roots.issued_at
                > timedelta(seconds=self.policy.maximum_authority_root_ttl_seconds)
                or roots.issued_at - roots.observed_at
                > timedelta(
                    seconds=(
                        self.policy.maximum_authority_root_observation_lag_seconds
                    )
                )
                or roots.revision < minimum_root_revision
            ):
                raise ProductionConsumerError(
                    "current production authority roots are invalid"
                )
        return clock.observed_at, clock, roots

    def verifies(self, request: ProductionConsumptionRequest, *, at: datetime) -> bool:
        try:
            _require_utc(at, "production consumer time")
            item = ProductionConsumptionRequest.model_validate(request.model_dump())
        except (TypeError, ValueError):
            return False
        rule = next(
            (rule for rule in self.policy.target_rules if rule.operation is item.operation),
            None,
        )
        ext = item.external_request
        if (
            rule is None
            or item.expires_at - item.requested_at
            > timedelta(seconds=self.policy.maximum_request_ttl_seconds)
            or not item.not_before <= at < item.expires_at
            or ext.property_record_sha256 != rule.property_record_sha256
            or ext.target_sha256 != rule.target_sha256
            or (
                item.adapter_id,
                item.adapter_executable_sha256,
                item.probe_executable_sha256,
                item.python_executable_sha256,
                item.adapter_dependency_closure_sha256,
                item.provider_allowlist_sha256,
                item.postcondition_schema_sha256,
                ext.expected_pre_state_sha256,
                ext.expected_post_state_sha256,
            )
            != (
                rule.adapter_id,
                rule.adapter_executable_sha256,
                rule.probe_executable_sha256,
                rule.python_executable_sha256,
                rule.adapter_dependency_closure_sha256,
                rule.provider_allowlist_sha256,
                rule.postcondition_schema_sha256,
                rule.expected_pre_state_sha256,
                rule.expected_post_state_sha256,
            )
            or item.execution_claim.claim_sha256 == "0" * 64
            or not self.external_guard.verifies_claim(
                ext,
                item.human_approval,
                item.controller_grant,
                item.execution_claim,
                at=at,
            )
            or not self.external_runtime.verifies_artifacts(
                ext,
                item.human_approval,
                item.controller_grant,
                at=at,
                observed_pre_state_sha256=ext.expected_pre_state_sha256,
                public_report=item.release_report,
            )
        ):
            return False
        if item.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE:
            return True
        report = item.release_report
        lease = item.serving_lease
        bundle = item.measurement_bundle
        if report is None or lease is None or bundle is None:
            return False
        required_snapshots = {
            bundle.dossier.provenance.demand_source_sha256,
            bundle.dossier.provenance.cohort_source_sha256,
            bundle.dossier.provenance.operations_source_sha256,
        }
        release_dossier_sha256 = hash_business_dossier(bundle.dossier)
        earliest_expiry = min(
            item.expires_at,
            report.expires_at,
            lease.expires_at,
            bundle.report.expires_at,
            bundle.dossier.expires_at.rights,
            bundle.dossier.expires_at.affiliate,
            bundle.dossier.expires_at.demand,
            bundle.dossier.expires_at.cohort,
            bundle.dossier.expires_at.operations,
        )
        return (
            verify_release_assurance_report(report, self.release_runtime, at=at)
            and verify_serving_lease(
                lease,
                self.trust.p9_lease_controller,
                expected_issuer=self.policy.serving_lease_issuer,
                expected_scope=LeaseScope.SERVE_PROTECTED_CONTENT,
                maximum_ttl_seconds=self.policy.maximum_serving_lease_ttl_seconds,
                at=at,
            )
            and verify_measurement_bound_dossier(
                bundle,
                self.measurement_policy,
                self.measurement_trust,
                self.measurement_pins,
                at=at,
            )
            and item.expires_at <= earliest_expiry
            and report.authorization is not None
            and report.business_dossier_sha256 == release_dossier_sha256
            and report.authorization.business_dossier_sha256
            == release_dossier_sha256
            and required_snapshots.issubset(report.approved_data_snapshot_sha256s)
            and (
                report.release_id,
                report.manifest_sha256,
                report.artifact_sha256,
            )
            == (lease.release_id, lease.manifest_sha256, lease.artifact_sha256)
            == (ext.release_id, ext.manifest_sha256, ext.artifact_sha256)
            and lease.issued_at >= report.authorization.issued_at
            and item.property_domain_sha256 == bundle.report.property_domain_sha256
            and item.measurement_run_id == bundle.report.run_id
            and item.measurement_bundle_index_sha256
            == bundle.report.bundle_index_sha256
            and item.affiliate_partner_ids_sha256
            == _canonical_sha256(bundle.report.partner_ids)
            and ext.property_record_sha256 == bundle.report.property_record_sha256
            and item.production_integration_plan_sha256
            == self.integration_plan.plan_sha256
            and item.production_readiness_authorization_sha256
            == self.integration_authorization_sha256
            and self.integration_plan.property_record_sha256
            == ext.property_record_sha256
            and self.integration_plan.environment_identity_sha256
            == ext.environment_sha256
            and self.integration_plan.release_artifact_sha256
            == report.artifact_sha256
            and self.integration_plan.release_manifest_sha256
            == report.manifest_sha256
            and self.integration_plan.adapter_closure_sha256
            == _production_adapter_readiness_closure(item)
            and self.integration_plan.probe_closure_sha256
            == _production_probe_readiness_closure(item)
            and self.integration_plan.provider_capability_profile_sha256
            == item.provider_allowlist_sha256
            and self.integration_plan.deployment_candidate_sha256
            == item.postcondition_schema_sha256
            and verify_production_bootstrap_authorization(
                self.integration_authorization,
                self.integration_report,
                self.integration_bundle,
                self.integration_plan,
                self.integration_policy,
                self.integration_trust,
                self.integration_tco,
                self.integration_human,
                self.integration_pins,
                at=at,
            )
            and self.verifies_execution_boundary(item, at=at)
        )

    def verifies_execution_boundary(
        self, request: ProductionConsumptionRequest, *, at: datetime
    ) -> bool:
        """Revalidate packet-external P18/P16 authority at the mutation boundary."""

        try:
            _require_utc(at, "P16 execution-boundary verification time")
            item = ProductionConsumptionRequest.model_validate(request.model_dump())
        except (TypeError, ValueError):
            return False
        if item.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE:
            return True
        report = item.release_report
        if report is None:
            return False
        try:
            handoff = evaluate_launch_handoff(
                self.launch_bundle,
                self.launch_plan,
                self.launch_policy,
                self.launch_trust,
                at=at,
                expected_repository_acceptance_authority_pins_sha256=(
                    self.repository_authority_root_sha256
                ),
                expected_launch_handoff_authority_sha256=(
                    self.launch_authority_root_sha256
                ),
                launch_semantic_authority_pins=self.launch_semantic_pins,
                expected_launch_semantic_authority_pins_sha256=(
                    self.launch_semantic_authority_root_sha256
                ),
            )
        except (TypeError, ValueError):
            return False
        requirements = {item.gate: item for item in self.launch_plan.requirements}
        readiness = requirements.get(
            LaunchHandoffGate.PRODUCTION_INTEGRATION_READINESS
        )
        deployment = requirements.get(
            LaunchHandoffGate.DEPLOYMENT_PUBLICATION_READINESS
        )
        if readiness is None or deployment is None:
            return False
        disable_rule = next(
            (
                rule
                for rule in self.policy.target_rules
                if rule.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE
            ),
            None,
        )
        if disable_rule is None or item.measurement_bundle is None:
            return False
        semantic_scope = self.launch_semantic_packet.scope
        readiness_components = tuple(
            (component.kind, component.artifact_sha256)
            for component in readiness.artifact_components
        )
        deployment_components = tuple(
            (component.kind, component.artifact_sha256)
            for component in deployment.artifact_components
        )
        return (
            handoff.decision
            is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
            and at < handoff.expires_at
            and handoff.evidence_bundle_sha256 == self.launch_bundle.bundle_sha256
            and handoff.launch_authority_sha256
            == self.launch_authority_root_sha256
            and item.repository_acceptance_authority_pins_sha256
            == self.repository_authority_root_sha256
            and item.launch_handoff_authority_sha256
            == self.launch_authority_root_sha256
            and item.launch_handoff_plan_sha256 == self.launch_plan.plan_sha256
            and item.launch_handoff_bundle_sha256 == self.launch_bundle.bundle_sha256
            and item.launch_semantic_authority_sha256
            == self.launch_semantic_authority_root_sha256
            and item.launch_semantic_packet_sha256
            == self.launch_semantic_packet.packet_sha256
            and self.launch_plan.property_record_sha256
            == item.external_request.property_record_sha256
            and self.launch_plan.environment_identity_sha256
            == item.external_request.environment_sha256
            and self.launch_plan.release_identity_sha256
            == semantic_scope.release_identity_sha256
            == hashlib.sha256(
                report.release_id.strip().lower().encode("utf-8")
            ).hexdigest()
            and self.launch_plan.release_manifest_sha256
            == semantic_scope.release_manifest_sha256
            == report.manifest_sha256
            and self.launch_plan.release_artifact_sha256 == report.artifact_sha256
            and self.launch_plan.release_artifact_sha256
            == semantic_scope.release_artifact_sha256
            and self.launch_plan.deployment_candidate_sha256
            == item.postcondition_schema_sha256
            and self.launch_plan.deployment_candidate_sha256
            == semantic_scope.deployment_candidate_sha256
            and self.launch_plan.provider_target_sha256
            == semantic_scope.provider_target_sha256
            == item.external_request.target_sha256
            and self.launch_plan.expected_pre_state_sha256
            == semantic_scope.expected_pre_state_sha256
            == item.external_request.expected_pre_state_sha256
            and self.launch_plan.expected_post_state_sha256
            == semantic_scope.expected_post_state_sha256
            == item.external_request.expected_post_state_sha256
            and self.launch_plan.rollback_state_sha256
            == semantic_scope.rollback_state_sha256
            == disable_rule.expected_post_state_sha256
            and self.launch_plan.legal_pages_sha256
            == semantic_scope.legal_pages_sha256
            and self.launch_plan.affiliate_disclosure_sha256
            == semantic_scope.affiliate_disclosure_sha256
            and item.measurement_bundle
            == self.launch_semantic_packet.measurement.bound_dossier
            and readiness_components
            == (
                (
                    LaunchArtifactComponentKind.P15_READINESS_REPORT,
                    hash_production_readiness_report(self.integration_report),
                ),
                (
                    LaunchArtifactComponentKind.P15_TCO_QA_ATTESTATION,
                    hash_production_tco_qa_attestation(self.integration_tco),
                ),
            )
            and deployment_components[0]
            == (
                LaunchArtifactComponentKind.P10_LOCAL_ASSURANCE_REPORT,
                report.local_report_sha256,
            )
        )

    def execution_boundary_expires_at(
        self, request: ProductionConsumptionRequest, *, at: datetime
    ) -> datetime | None:
        """Return the effective signed P16/P18 expiry used by dispatch."""

        if request.operation is ProviderOperation.DISABLE_PUBLIC_RELEASE:
            return None
        if not self.verifies_execution_boundary(request, at=at):
            return None
        try:
            report = evaluate_launch_handoff(
                self.launch_bundle,
                self.launch_plan,
                self.launch_policy,
                self.launch_trust,
                at=at,
                expected_repository_acceptance_authority_pins_sha256=(
                    self.repository_authority_root_sha256
                ),
                expected_launch_handoff_authority_sha256=(
                    self.launch_authority_root_sha256
                ),
                launch_semantic_authority_pins=self.launch_semantic_pins,
                expected_launch_semantic_authority_pins_sha256=(
                    self.launch_semantic_authority_root_sha256
                ),
            )
        except (TypeError, ValueError):
            return None
        return report.expires_at

    def verifies_provider_result(
        self,
        token: ProviderDispatchToken,
        receipt: ProviderResultReceipt,
        *,
        at: datetime,
    ) -> bool:
        try:
            _require_utc(at, "provider result verification time")
            item = ProviderResultReceipt.model_validate(receipt.model_dump())
        except (TypeError, ValueError):
            return False
        return (
            _verify_signed(token, self.trust.dispatcher)
            and token.store_id_sha256 == self.policy.store_id_sha256
            and token.policy_sha256 == self.policy_sha256
            and token.issued_at <= at
            and _verify_signed(item, self.trust.provider_adapter)
            and item.dispatch_payload_sha256 == token.payload_sha256
            and (
                item.store_id_sha256,
                item.epoch,
                item.fencing_token,
                item.operation,
                item.adapter_id,
                item.target_sha256,
                item.idempotency_key_sha256,
            )
            == (
                token.store_id_sha256,
                token.epoch,
                token.fencing_token,
                token.operation,
                token.adapter_id,
                token.target_sha256,
                token.idempotency_key_sha256,
            )
            and (
                item.outcome is not ProviderOutcome.SUCCEEDED
                or item.observed_pre_state_sha256
                == token.expected_pre_state_sha256
            )
            and token.issued_at <= item.started_at <= item.completed_at <= at
            and item.completed_at - item.started_at
            <= timedelta(seconds=self.policy.maximum_provider_receipt_delay_seconds)
            and item.completed_at < token.expires_at
        )

    def verifies_probe(
        self,
        token: ProviderDispatchToken,
        provider_receipt: ProviderResultReceipt,
        probe: ProviderProbeReceipt,
        *,
        at: datetime,
    ) -> bool:
        try:
            _require_utc(at, "provider probe verification time")
            item = ProviderProbeReceipt.model_validate(probe.model_dump())
        except (TypeError, ValueError):
            return False
        return (
            self.verifies_provider_result(token, provider_receipt, at=at)
            and _verify_signed(item, self.trust.provider_probe)
            and item.dispatch_payload_sha256 == token.payload_sha256
            and (
                item.store_id_sha256,
                item.epoch,
                item.fencing_token,
                item.operation,
                item.adapter_id,
                item.target_sha256,
            )
            == (
                token.store_id_sha256,
                token.epoch,
                token.fencing_token,
                token.operation,
                token.adapter_id,
                token.target_sha256,
            )
            and item.observed_post_state_sha256
            == token.expected_post_state_sha256
            and token.issued_at
            <= provider_receipt.completed_at
            <= item.probed_at
            <= at
            < token.expires_at
        )

    def verifies_terminal_result(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        *,
        state: ConsumptionState,
        terminal_at: datetime,
        provider_receipt: ProviderResultReceipt | None,
        probe_receipt: ProviderProbeReceipt | None,
        action_receipt: ActionReceipt | None,
    ) -> bool:
        try:
            _require_utc(terminal_at, "terminal result verification time")
        except (TypeError, ValueError):
            return False
        if (
            token.request_sha256 != request.request_sha256
            or token.p11_claim_sha256 != request.execution_claim.claim_sha256
            or token.production_integration_plan_sha256
            != request.production_integration_plan_sha256
            or token.production_readiness_authorization_sha256
            != request.production_readiness_authorization_sha256
            or token.repository_acceptance_authority_pins_sha256
            != request.repository_acceptance_authority_pins_sha256
            or token.launch_handoff_authority_sha256
            != request.launch_handoff_authority_sha256
            or token.launch_handoff_plan_sha256
            != request.launch_handoff_plan_sha256
            or token.launch_handoff_bundle_sha256
            != request.launch_handoff_bundle_sha256
            or token.launch_semantic_authority_sha256
            != request.launch_semantic_authority_sha256
            or token.launch_semantic_packet_sha256
            != request.launch_semantic_packet_sha256
            or token.policy_sha256 != self.policy_sha256
            or token.store_id_sha256 != self.policy.store_id_sha256
            or not token.issued_at <= terminal_at
            or not _verify_signed(token, self.trust.dispatcher)
        ):
            return False
        if state is ConsumptionState.SUCCEEDED:
            return (
                provider_receipt is not None
                and probe_receipt is not None
                and action_receipt is not None
                and self.verifies(request, at=terminal_at)
                and terminal_at < token.expires_at
                and provider_receipt.outcome is ProviderOutcome.SUCCEEDED
                and provider_receipt.observed_post_state_sha256
                == token.expected_post_state_sha256
                and self.verifies_probe(
                    token, provider_receipt, probe_receipt, at=terminal_at
                )
                and action_receipt.provider_operation_sha256
                == provider_receipt.payload_sha256
                and action_receipt.provider_audit_receipt_sha256
                == provider_receipt.provider_audit_receipt_sha256
                and verify_action_receipt(
                    request.external_request,
                    request.human_approval,
                    request.controller_grant,
                    request.execution_claim,
                    action_receipt,
                    self.external_guard,
                    at=terminal_at,
                    require_success=True,
                )
            )
        if probe_receipt is not None or action_receipt is not None:
            return False
        if provider_receipt is None:
            return state is ConsumptionState.UNKNOWN
        expected_state = {
            ProviderOutcome.FAILED: ConsumptionState.FAILED,
            ProviderOutcome.PARTIAL: ConsumptionState.PARTIAL,
            ProviderOutcome.UNKNOWN: ConsumptionState.UNKNOWN,
            ProviderOutcome.SUCCEEDED: ConsumptionState.UNKNOWN,
        }[provider_receipt.outcome]
        return (
            state in {expected_state, ConsumptionState.UNKNOWN}
            and self.verifies_provider_result(token, provider_receipt, at=terminal_at)
        )


class _ProviderInvocationCapability:
    """One-shot store-issued authority for exactly one adapter subprocess call."""

    __slots__ = (
        "_store_seal",
        "_dispatch_payload_sha256",
        "_command",
        "_authoritative_at",
        "_used",
    )

    def __init__(
        self,
        store_seal: object,
        token: ProviderDispatchToken,
        command: Literal["execute", "probe"],
        authoritative_at: datetime,
    ) -> None:
        self._store_seal = store_seal
        self._dispatch_payload_sha256 = token.payload_sha256
        self._command = command
        self._authoritative_at = authoritative_at
        self._used = False

    def consume(
        self,
        *,
        token: ProviderDispatchToken,
        command: Literal["execute", "probe"],
    ) -> datetime:
        with _PROVIDER_CAPABILITY_LOCK:
            registered = _ACTIVE_PROVIDER_CAPABILITIES.pop(id(self), None)
            store_reference = _PROVIDER_CAPABILITY_STORES.get(self._store_seal)
            store = store_reference() if store_reference is not None else None
            if (
                type(self) is not _ProviderInvocationCapability
                or registered is not self
                or store is None
                or self._used
                or self._dispatch_payload_sha256 != token.payload_sha256
                or self._command != command
            ):
                raise ProductionConsumerError(
                    "adapter subprocess capability is stale or invalid"
                )
        store._validate_provider_invocation_capability(
            token,
            command=command,
            authoritative_at=self._authoritative_at,
        )
        self._used = True
        return self._authoritative_at


_PROVIDER_CAPABILITY_LOCK = RLock()
_ACTIVE_PROVIDER_CAPABILITIES: dict[int, _ProviderInvocationCapability] = {}
_PROVIDER_CAPABILITY_STORES: dict[object, weakref.ReferenceType[GlobalStopStore]] = {}
_PROVIDER_CAPABILITY_PERMITS: dict[object, object] = {}


def _issue_provider_invocation_capability(
    store_seal: object,
    permit: object,
    token: ProviderDispatchToken,
    command: Literal["execute", "probe"],
    authoritative_at: datetime,
) -> _ProviderInvocationCapability:
    with _PROVIDER_CAPABILITY_LOCK:
        store_reference = _PROVIDER_CAPABILITY_STORES.get(store_seal)
        store = store_reference() if store_reference is not None else None
        if (
            type(store) is not GlobalStopStore
            or store._provider_capability_quarantined
            or _PROVIDER_CAPABILITY_PERMITS.pop(store_seal, None) is not permit
        ):
            raise ProductionConsumerError(
                "adapter subprocess capability issuer is invalid"
            )
        capability = _ProviderInvocationCapability(
            store_seal, token, command, authoritative_at
        )
        _ACTIVE_PROVIDER_CAPABILITIES[id(capability)] = capability
    return capability


def _revoke_provider_invocation_capability(
    capability: _ProviderInvocationCapability,
) -> None:
    with _PROVIDER_CAPABILITY_LOCK:
        _ACTIVE_PROVIDER_CAPABILITIES.pop(id(capability), None)


_SUBPROCESS_PROVIDER_EXECUTION_PORT_SEAL = object()


class _SubprocessProviderExecutionPort:
    """Exact one-shot binding to the pinned, deadline-bounded subprocess path."""

    __slots__ = (
        "_seal",
        "_adapter",
        "_request_sha256",
        "_token_sha256",
        "_profile_sha256",
        "_timeout_seconds",
        "_used",
    )

    def __init__(
        self,
        seal: object,
        adapter: SubprocessProviderAdapter,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
    ) -> None:
        if seal is not _SUBPROCESS_PROVIDER_EXECUTION_PORT_SEAL:
            raise ProductionConsumerError("provider execution port issuer is invalid")
        object.__setattr__(self, "_seal", seal)
        object.__setattr__(self, "_adapter", adapter)
        object.__setattr__(self, "_request_sha256", request.request_sha256)
        object.__setattr__(self, "_token_sha256", token.payload_sha256)
        object.__setattr__(self, "_profile_sha256", adapter._execution_profile_sha256())
        object.__setattr__(self, "_timeout_seconds", adapter._timeout)
        object.__setattr__(self, "_used", False)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("provider execution port is immutable")

    def validates(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
    ) -> bool:
        return (
            type(self) is _SubprocessProviderExecutionPort
            and self._seal is _SUBPROCESS_PROVIDER_EXECUTION_PORT_SEAL
            and type(self._adapter) is SubprocessProviderAdapter
            and not self._used
            and self._request_sha256 == request.request_sha256
            and self._token_sha256 == token.payload_sha256
            and self._profile_sha256 == self._adapter._execution_profile_sha256()
            and self._timeout_seconds == self._adapter._timeout
            and self._timeout_seconds
            < runtime.policy.minimum_provider_authority_margin_seconds
            and self._adapter.matches(request)
        )

    def execute(
        self,
        token: ProviderDispatchToken,
        capability: _ProviderInvocationCapability,
        *,
        absolute_deadline: float,
    ) -> ProviderResultReceipt:
        if self._used:
            raise ProductionConsumerError("provider execution port was already consumed")
        object.__setattr__(self, "_used", True)
        return ProviderResultReceipt.model_validate_json(
            _canonical_json_bytes(
                self._adapter._invoke(
                    "execute",
                    token,
                    capability=capability,
                    absolute_deadline=absolute_deadline,
                )
            )
        )


_STORE_SCHEMA = """
CREATE TABLE production_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE production_dispatches (
    request_sha256 TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    idempotency_key_sha256 TEXT NOT NULL UNIQUE,
    epoch INTEGER NOT NULL,
    fencing_token INTEGER NOT NULL UNIQUE,
    request_json TEXT NOT NULL,
    token_json TEXT NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT
) STRICT;
CREATE TABLE production_provider_receipts (
    request_sha256 TEXT PRIMARY KEY REFERENCES production_dispatches(request_sha256),
    dispatch_payload_sha256 TEXT NOT NULL UNIQUE,
    receipt_payload_sha256 TEXT NOT NULL UNIQUE,
    provider_audit_receipt_sha256 TEXT NOT NULL UNIQUE,
    receipt_json TEXT NOT NULL,
    verified_at TEXT NOT NULL
) STRICT;
CREATE TABLE production_provider_attempt_intents (
    request_sha256 TEXT PRIMARY KEY REFERENCES production_dispatches(request_sha256),
    dispatch_payload_sha256 TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    authority_roots_json TEXT
) STRICT;
CREATE TRIGGER production_provider_attempt_intents_no_update
BEFORE UPDATE ON production_provider_attempt_intents BEGIN
    SELECT RAISE(ABORT, 'provider attempt intents are immutable');
END;
CREATE TRIGGER production_provider_attempt_intents_no_delete
BEFORE DELETE ON production_provider_attempt_intents BEGIN
    SELECT RAISE(ABORT, 'provider attempt intents are immutable');
END;
CREATE TABLE production_provider_attempts (
    request_sha256 TEXT PRIMARY KEY REFERENCES production_dispatches(request_sha256),
    dispatch_payload_sha256 TEXT NOT NULL UNIQUE,
    receipt_payload_sha256 TEXT NOT NULL UNIQUE,
    receipt_json TEXT NOT NULL
) STRICT;
CREATE TRIGGER production_provider_attempts_no_update
BEFORE UPDATE ON production_provider_attempts BEGIN
    SELECT RAISE(ABORT, 'provider attempts are immutable');
END;
CREATE TRIGGER production_provider_attempts_no_delete
BEFORE DELETE ON production_provider_attempts BEGIN
    SELECT RAISE(ABORT, 'provider attempts are immutable');
END;
CREATE TRIGGER production_provider_receipts_no_update
BEFORE UPDATE ON production_provider_receipts BEGIN
    SELECT RAISE(ABORT, 'provider receipts are immutable');
END;
CREATE TRIGGER production_provider_receipts_no_delete
BEFORE DELETE ON production_provider_receipts BEGIN
    SELECT RAISE(ABORT, 'provider receipts are immutable');
END;
CREATE TABLE production_events (
    revision INTEGER PRIMARY KEY,
    previous_head_sha256 TEXT NOT NULL,
    event_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE
) STRICT;
"""


_FORK_AWARE_STORES: weakref.WeakSet[GlobalStopStore] = weakref.WeakSet()


def _reset_forked_store_handles() -> None:
    """Drop inherited owner descriptors without unlocking the parent lease."""

    for store in tuple(_FORK_AWARE_STORES):
        store._after_fork_child()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_forked_store_handles)


class GlobalStopStore:
    """Authenticated SQLite state with a caller-owned monotonic anchor.

    A missing, rolled-back or modified database is not repaired.  It becomes an
    unavailable effective STOP until a Human follows the recovery procedure.
    """

    __slots__ = (
        "_path", "_lock_path", "_inflight_lock_path", "_inflight_handle",
        "_inflight_pid",
        "_store_id", "_policy_sha", "_auth_key", "_anchor_commit",
        "_anchor_read", "_lock", "_provider_capability_seal",
        "_provider_capability_quarantined", "__weakref__",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        expected_store_id_sha256: str,
        expected_policy_sha256: str,
        expected_anchor_sha256: str,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> None:
        self._path = Path(path).resolve()
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        self._inflight_lock_path = self._path.with_suffix(
            self._path.suffix + ".inflight.lock"
        )
        self._inflight_handle: Any | None = None
        self._inflight_pid: int | None = None
        self._store_id = expected_store_id_sha256
        self._policy_sha = expected_policy_sha256
        self._auth_key = _validate_state_key(state_authentication_key)
        self._anchor_commit = anchor_commit
        self._anchor_read = anchor_read
        self._lock = RLock()
        self._provider_capability_seal = object()
        self._provider_capability_quarantined = False
        _FORK_AWARE_STORES.add(self)
        if not self._path.is_file():
            raise ProductionConsumerError("global STOP store is missing")
        with self._file_lock(), self._connect() as connection:
            self._assert_integrity(connection, expected_anchor_sha256)
            if self._has_inflight(connection) and self._acquire_inflight_owner():
                try:
                    self._recover_inflight(connection)
                finally:
                    self._release_inflight_owner()
        with _PROVIDER_CAPABILITY_LOCK:
            _PROVIDER_CAPABILITY_STORES[self._provider_capability_seal] = weakref.ref(self)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_provider_capability_seal" and hasattr(
            self, "_provider_capability_seal"
        ):
            raise AttributeError("provider capability issuer seal is immutable")
        if name == "_provider_capability_quarantined" and hasattr(self, name):
            current = object.__getattribute__(self, name)
            if current or value is not True:
                raise AttributeError("provider capability quarantine is irreversible")
        object.__setattr__(self, name, value)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        store_id_sha256: str,
        policy_sha256: str,
        initial_stop_reason_sha256: str,
        created_at: datetime,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
    ) -> GlobalStopStore:
        _require_utc(created_at, "global STOP store creation time")
        selected = Path(path).resolve()
        if selected.exists():
            raise ProductionConsumerError("refusing to overwrite global STOP store")
        selected.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(selected)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(_STORE_SCHEMA)
            head = _canonical_sha256(
                {
                    "store_id_sha256": store_id_sha256,
                    "policy_sha256": policy_sha256,
                    "initial_stop_reason_sha256": initial_stop_reason_sha256,
                    "created_at": created_at,
                }
            )
            meta = {
                "schema_version": "4",
                "store_id_sha256": store_id_sha256,
                "policy_sha256": policy_sha256,
                "revision": "0",
                "epoch": "0",
                "stopped": "1",
                "head_sha256": head,
                "previous_anchor_sha256": "0" * 64,
                "stop_reason_sha256": initial_stop_reason_sha256,
                "stopped_at": created_at.isoformat(),
                "last_trusted_at": created_at.isoformat(),
                "authority_root_revision": "0",
            }
            connection.executemany(
                "INSERT INTO production_meta(key, value) VALUES (?, ?)",
                tuple(meta.items()),
            )
            connection.execute(
                "INSERT INTO production_meta(key, value) VALUES ('state_mac_sha256', ?)",
                ("0" * 64,),
            )
            auth_key = _validate_state_key(state_authentication_key)
            state_mac = cls._calculate_state_mac(connection, auth_key)
            connection.execute(
                "UPDATE production_meta SET value=? WHERE key='state_mac_sha256'",
                (state_mac,),
            )
            connection.commit()
            os.chmod(selected, 0o600)
            anchor = cls._anchor_hash(store_id_sha256, 0, head, state_mac)
            _invoke_bounded_operation(
                anchor_commit,
                0,
                anchor,
                timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
                label="global STOP anchor commit",
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return cls(
            selected,
            expected_store_id_sha256=store_id_sha256,
            expected_policy_sha256=policy_sha256,
            expected_anchor_sha256=_invoke_bounded_operation(
                anchor_read,
                timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
                label="global STOP anchor read",
            ),
            state_authentication_key=state_authentication_key,
            anchor_commit=anchor_commit,
            anchor_read=anchor_read,
        )

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        self._lock_path.touch(mode=0o600, exist_ok=True)
        with self._lock_path.open("rb") as handle:
            deadline = time.monotonic() + _STORE_COORDINATION_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ProductionConsumerError(
                            "global STOP store lock timed out"
                        ) from exc
                    time.sleep(_STORE_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _shared_file_lock(self) -> Iterator[None]:
        """Hold the store fence while a provider subprocess is in flight.

        State transitions take the exclusive form of this same OS lock, so a
        STOP/epoch change is ordered either before the provider mutation or
        after the subprocess has returned.
        """

        self._lock_path.touch(mode=0o600, exist_ok=True)
        with self._lock_path.open("rb") as handle:
            deadline = time.monotonic() + _STORE_COORDINATION_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ProductionConsumerError(
                            "global STOP shared store lock timed out"
                        ) from exc
                    time.sleep(_STORE_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _acquire_inflight_owner(self) -> bool:
        if self._provider_capability_quarantined:
            return False
        if self._inflight_handle is not None:
            return self._inflight_pid == os.getpid()
        self._inflight_lock_path.touch(mode=0o600, exist_ok=True)
        handle = self._inflight_lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._inflight_handle = handle
        self._inflight_pid = os.getpid()
        return True

    def _owns_inflight(self) -> bool:
        return (
            not self._provider_capability_quarantined
            and self._inflight_handle is not None
            and self._inflight_pid == os.getpid()
        )

    def _after_fork_child(self) -> None:
        """Make an inherited store a non-owner in the child process."""

        handle = self._inflight_handle
        self._inflight_handle = None
        self._inflight_pid = None
        self._lock = RLock()
        if handle is not None:
            # Do not call LOCK_UN: the inherited descriptor refers to the
            # parent's locked open-file description.  Closing only the child
            # copy prevents both authority inheritance and stale retention.
            handle.close()

    def _release_inflight_owner(self) -> None:
        handle = self._inflight_handle
        if handle is None:
            return
        self._inflight_handle = None
        owner_pid = self._inflight_pid
        self._inflight_pid = None
        try:
            if owner_pid == os.getpid():
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def close(self) -> None:
        """Relinquish this process's live-dispatch lease.

        Closing with an in-flight row deliberately models owner loss.  A later
        opener will recover that row to UNKNOWN+STOP; it never resumes it.
        """

        with self._lock:
            self._quarantine_provider_invocation_authority()

    def _quarantine_provider_invocation_authority(self) -> None:
        """Fail closed locally when the durable UNKNOWN+STOP close also fails.

        The SQLite in-flight intent remains recoverable by the next store opener,
        but this live object must no longer be able to issue or validate a provider
        launch in the interval before that recovery completes.
        """

        if not self._provider_capability_quarantined:
            self._provider_capability_quarantined = True
        self._release_inflight_owner()
        with _PROVIDER_CAPABILITY_LOCK:
            _PROVIDER_CAPABILITY_STORES.pop(
                self._provider_capability_seal, None
            )
            _PROVIDER_CAPABILITY_PERMITS.pop(
                self._provider_capability_seal, None
            )
            stale = [
                capability_id
                for capability_id, capability in _ACTIVE_PROVIDER_CAPABILITIES.items()
                if capability._store_seal is self._provider_capability_seal
            ]
            for capability_id in stale:
                _ACTIVE_PROVIDER_CAPABILITIES.pop(capability_id, None)

    def _validate_provider_invocation_capability(
        self,
        token: ProviderDispatchToken,
        *,
        command: Literal["execute", "probe"],
        authoritative_at: datetime,
    ) -> None:
        """Recheck authenticated durable state at the subprocess boundary."""

        with self._lock, self._connect() as connection:
            meta = self._assert_integrity(connection)
            row = connection.execute(
                "SELECT d.state, d.result_json, p.receipt_json, "
                "a.receipt_json AS attempt_receipt_json, "
                "i.request_sha256 AS intent_request_sha256 "
                "FROM production_dispatches AS d "
                "LEFT JOIN production_provider_receipts AS p "
                "ON p.request_sha256=d.request_sha256 "
                "LEFT JOIN production_provider_attempts AS a "
                "ON a.request_sha256=d.request_sha256 "
                "LEFT JOIN production_provider_attempt_intents AS i "
                "ON i.request_sha256=d.request_sha256 "
                "WHERE d.request_sha256=?",
                (token.request_sha256,),
            ).fetchone()
            activation_stopped = (
                token.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                and meta["stopped"] == "1"
            )
            common = (
                row is not None
                and not self._provider_capability_quarantined
                and self._owns_inflight()
                and row["result_json"] is None
                and token.store_id_sha256 == self._store_id
                and token.policy_sha256 == self._policy_sha
                and token.epoch == int(meta["epoch"])
                and token.issued_at <= authoritative_at < token.expires_at
                and datetime.fromisoformat(meta["last_trusted_at"])
                == authoritative_at
                and not activation_stopped
            )
            if command == "execute":
                valid = (
                    common
                    and row["state"] == ConsumptionState.DISPATCHED.value
                    and row["receipt_json"] is None
                    and row["attempt_receipt_json"] is None
                    and row["intent_request_sha256"] is not None
                    and token.fencing_token + 2 == int(meta["revision"])
                )
            else:
                latest = connection.execute(
                    "SELECT event_json FROM production_events "
                    "ORDER BY revision DESC LIMIT 1"
                ).fetchone()
                try:
                    latest_event = json.loads(latest["event_json"])
                except (TypeError, json.JSONDecodeError):
                    latest_event = None
                valid = (
                    common
                    and row["state"] == "provider_recorded"
                    and row["receipt_json"] is not None
                    and row["attempt_receipt_json"] is not None
                    and token.fencing_token + 5 == int(meta["revision"])
                    and isinstance(latest_event, dict)
                    and latest_event.get("kind")
                    == "provider_probe_intent_recorded"
                    and latest_event.get("request_sha256") == token.request_sha256
                )
            if not valid:
                raise ProductionConsumerError(
                    "adapter subprocess durable authority is stale or invalid"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    @staticmethod
    def _schema_descriptor(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        return _canonical_sha256([tuple(row) for row in rows])

    @classmethod
    def _expected_schema_descriptor(cls) -> str:
        memory = sqlite3.connect(":memory:")
        try:
            memory.executescript(_STORE_SCHEMA)
            return cls._schema_descriptor(memory)
        finally:
            memory.close()

    @staticmethod
    def _meta(connection: sqlite3.Connection) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in connection.execute(
                "SELECT key, value FROM production_meta ORDER BY key"
            )
        }

    @staticmethod
    def _assert_provider_journal_integrity(connection: sqlite3.Connection) -> None:
        orphan = connection.execute(
            "SELECT 1 FROM production_provider_receipts AS p "
            "LEFT JOIN production_dispatches AS d "
            "ON d.request_sha256=p.request_sha256 "
            "WHERE d.request_sha256 IS NULL LIMIT 1"
        ).fetchone()
        if orphan is not None:
            raise ProductionConsumerError("provider journal has an orphan receipt")
        orphan_attempt = connection.execute(
            "SELECT 1 FROM production_provider_attempts AS a "
            "LEFT JOIN production_dispatches AS d "
            "ON d.request_sha256=a.request_sha256 "
            "WHERE d.request_sha256 IS NULL LIMIT 1"
        ).fetchone()
        if orphan_attempt is not None:
            raise ProductionConsumerError("provider journal has an orphan attempt")
        orphan_intent = connection.execute(
            "SELECT 1 FROM production_provider_attempt_intents AS i "
            "LEFT JOIN production_dispatches AS d "
            "ON d.request_sha256=i.request_sha256 "
            "WHERE d.request_sha256 IS NULL LIMIT 1"
        ).fetchone()
        if orphan_intent is not None:
            raise ProductionConsumerError("provider journal has an orphan attempt intent")
        rows = connection.execute(
            "SELECT d.request_sha256, d.token_json, d.state, d.result_json, "
            "p.dispatch_payload_sha256, p.receipt_payload_sha256, "
            "p.provider_audit_receipt_sha256, p.receipt_json, p.verified_at, "
            "a.dispatch_payload_sha256 AS attempt_dispatch_payload_sha256, "
            "a.receipt_payload_sha256 AS attempt_receipt_payload_sha256, "
            "a.receipt_json AS attempt_receipt_json, "
            "i.dispatch_payload_sha256 AS intent_dispatch_payload_sha256, "
            "i.started_at AS intent_started_at, "
            "i.clock_attestation_json AS intent_clock_attestation_json, "
            "i.authority_roots_json AS intent_authority_roots_json "
            "FROM production_dispatches AS d "
            "LEFT JOIN production_provider_receipts AS p "
            "ON p.request_sha256=d.request_sha256 "
            "LEFT JOIN production_provider_attempts AS a "
            "ON a.request_sha256=d.request_sha256 "
            "LEFT JOIN production_provider_attempt_intents AS i "
            "ON i.request_sha256=d.request_sha256 ORDER BY d.request_sha256"
        ).fetchall()
        terminal_states = {
            ConsumptionState.SUCCEEDED.value,
            ConsumptionState.FAILED.value,
            ConsumptionState.PARTIAL.value,
            ConsumptionState.UNKNOWN.value,
        }
        for row in rows:
            try:
                token = ProviderDispatchToken.model_validate_json(row["token_json"])
                receipt = (
                    ProviderResultReceipt.model_validate_json(row["receipt_json"])
                    if row["receipt_json"] is not None
                    else None
                )
                attempt = (
                    ProviderResultReceipt.model_validate_json(
                        row["attempt_receipt_json"]
                    )
                    if row["attempt_receipt_json"] is not None
                    else None
                )
                intent_clock = (
                    SignedProductionConsumerClockAttestation.model_validate_json(
                        row["intent_clock_attestation_json"]
                    )
                    if row["intent_clock_attestation_json"] is not None
                    else None
                )
                intent_roots = (
                    SignedProductionAuthorityRoots.model_validate_json(
                        row["intent_authority_roots_json"]
                    )
                    if row["intent_authority_roots_json"] is not None
                    else None
                )
                intent_started_at = (
                    datetime.fromisoformat(row["intent_started_at"])
                    if row["intent_started_at"] is not None
                    else None
                )
                if intent_started_at is not None:
                    _require_utc(intent_started_at, "provider attempt start time")
                result = (
                    ProductionConsumptionResult.model_validate_json(row["result_json"])
                    if row["result_json"] is not None
                    else None
                )
                if receipt is not None:
                    verified_at = datetime.fromisoformat(row["verified_at"])
                    _require_utc(verified_at, "provider journal verification time")
            except (TypeError, ValueError) as exc:
                raise ProductionConsumerError(
                    "provider journal contains an invalid artifact"
                ) from exc
            if receipt is None:
                if any(
                    row[name] is not None
                    for name in (
                        "dispatch_payload_sha256",
                        "receipt_payload_sha256",
                        "provider_audit_receipt_sha256",
                        "verified_at",
                    )
                ):
                    raise ProductionConsumerError("provider journal is incomplete")
            elif (
                row["dispatch_payload_sha256"] != token.payload_sha256
                or row["receipt_payload_sha256"] != receipt.payload_sha256
                or row["provider_audit_receipt_sha256"]
                != receipt.provider_audit_receipt_sha256
                or receipt.dispatch_payload_sha256 != token.payload_sha256
                or receipt.completed_at > verified_at
                or (
                    receipt.store_id_sha256,
                    receipt.epoch,
                    receipt.fencing_token,
                    receipt.operation,
                    receipt.adapter_id,
                    receipt.target_sha256,
                    receipt.idempotency_key_sha256,
                )
                != (
                    token.store_id_sha256,
                    token.epoch,
                    token.fencing_token,
                    token.operation,
                    token.adapter_id,
                    token.target_sha256,
                    token.idempotency_key_sha256,
                )
            ):
                raise ProductionConsumerError("provider journal/token binding mismatch")
            if attempt is not None and (
                row["attempt_dispatch_payload_sha256"] != token.payload_sha256
                or row["attempt_receipt_payload_sha256"]
                != attempt.payload_sha256
                or attempt.dispatch_payload_sha256 != token.payload_sha256
                or (receipt is not None and receipt != attempt)
            ):
                raise ProductionConsumerError("provider attempt/token binding mismatch")
            if attempt is None and any(
                row[name] is not None
                for name in (
                    "attempt_dispatch_payload_sha256",
                    "attempt_receipt_payload_sha256",
                    "attempt_receipt_json",
                )
            ):
                raise ProductionConsumerError("provider attempt journal is incomplete")
            has_intent = intent_clock is not None
            if has_intent:
                if (
                    row["intent_dispatch_payload_sha256"] != token.payload_sha256
                    or intent_started_at != intent_clock.observed_at
                    or (
                        token.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    )
                    != (intent_roots is not None)
                ):
                    raise ProductionConsumerError(
                        "provider attempt intent/token binding mismatch"
                    )
            elif any(
                row[name] is not None
                for name in (
                    "intent_dispatch_payload_sha256",
                    "intent_started_at",
                    "intent_clock_attestation_json",
                    "intent_authority_roots_json",
                )
            ):
                raise ProductionConsumerError("provider attempt intent is incomplete")
            if attempt is not None and not has_intent:
                raise ProductionConsumerError("provider attempt has no durable intent")
            if row["state"] in {
                ConsumptionState.CLAIMED.value,
            }:
                valid_shape = (
                    receipt is None
                    and attempt is None
                    and not has_intent
                    and result is None
                )
            elif row["state"] == ConsumptionState.DISPATCHED.value:
                valid_shape = receipt is None and result is None
            elif row["state"] == "provider_recorded":
                valid_shape = (
                    receipt is not None
                    and attempt == receipt
                    and has_intent
                    and result is None
                )
            elif row["state"] in terminal_states:
                valid_shape = (
                    result is not None
                    and result.state.value == row["state"]
                    and result.request_sha256 == row["request_sha256"]
                    and result.dispatch_payload_sha256 == token.payload_sha256
                    and result.epoch == token.epoch
                    and result.fencing_token == token.fencing_token
                    and result.provider_receipt == (receipt or attempt)
                )
            else:
                valid_shape = False
            if not valid_shape:
                raise ProductionConsumerError("provider journal state shape mismatch")

    @staticmethod
    def _calculate_state_mac(connection: sqlite3.Connection, key: bytes) -> str:
        meta = GlobalStopStore._meta(connection)
        meta.pop("state_mac_sha256", None)
        dispatches = [
            tuple(row)
            for row in connection.execute(
                "SELECT request_sha256, request_id, idempotency_key_sha256, epoch, "
                "fencing_token, request_json, token_json, state, result_json "
                "FROM production_dispatches ORDER BY request_sha256"
            )
        ]
        provider_receipts = [
            tuple(row)
            for row in connection.execute(
                "SELECT request_sha256, dispatch_payload_sha256, "
                "receipt_payload_sha256, provider_audit_receipt_sha256, "
                "receipt_json, verified_at FROM production_provider_receipts "
                "ORDER BY request_sha256"
            )
        ]
        provider_attempts = [
            tuple(row)
            for row in connection.execute(
                "SELECT request_sha256, dispatch_payload_sha256, "
                "receipt_payload_sha256, receipt_json "
                "FROM production_provider_attempts ORDER BY request_sha256"
            )
        ]
        provider_attempt_intents = [
            tuple(row)
            for row in connection.execute(
                "SELECT request_sha256, dispatch_payload_sha256, started_at, "
                "clock_attestation_json, authority_roots_json "
                "FROM production_provider_attempt_intents ORDER BY request_sha256"
            )
        ]
        events = [
            tuple(row)
            for row in connection.execute(
                "SELECT revision, previous_head_sha256, event_json, event_sha256 "
                "FROM production_events ORDER BY revision"
            )
        ]
        return hmac.new(
            key,
            _canonical_json_bytes(
                {
                    "meta": meta,
                    "dispatches": dispatches,
                    "provider_receipts": provider_receipts,
                    "provider_attempts": provider_attempts,
                    "provider_attempt_intents": provider_attempt_intents,
                    "events": events,
                }
            ),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _anchor_hash(store_id: str, revision: int, head: str, state_mac: str) -> str:
        return _canonical_sha256(
            {
                "store_id_sha256": store_id,
                "revision": revision,
                "head_sha256": head,
                "state_mac_sha256": state_mac,
            }
        )

    def _assert_integrity(
        self, connection: sqlite3.Connection, expected_anchor: str | None = None
    ) -> dict[str, str]:
        if self._schema_descriptor(connection) != self._expected_schema_descriptor():
            raise ProductionConsumerError("global STOP store schema mismatch")
        meta = self._meta(connection)
        required = {
            "schema_version", "store_id_sha256", "policy_sha256", "revision",
            "epoch", "stopped", "head_sha256", "stop_reason_sha256",
            "stopped_at", "state_mac_sha256", "previous_anchor_sha256",
            "last_trusted_at", "authority_root_revision",
        }
        if (
            set(meta) != required
            or meta["store_id_sha256"] != self._store_id
            or meta["policy_sha256"] != self._policy_sha
            or meta["schema_version"] != "4"
            or meta["stopped"] not in {"0", "1"}
            or not hmac.compare_digest(
                meta["state_mac_sha256"],
                self._calculate_state_mac(connection, self._auth_key),
            )
        ):
            raise ProductionConsumerError("global STOP store integrity mismatch")
        self._assert_provider_journal_integrity(connection)
        revision = int(meta["revision"])
        anchor = self._anchor_hash(
            self._store_id, revision, meta["head_sha256"], meta["state_mac_sha256"]
        )
        external = _invoke_bounded_operation(
            self._anchor_read,
            timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
            label="global STOP anchor read",
        )
        if expected_anchor is not None and expected_anchor != external:
            raise ProductionConsumerError("expected global STOP anchor mismatch")
        if external != anchor:
            if revision < 1 or external != meta["previous_anchor_sha256"]:
                raise ProductionConsumerError("global STOP external anchor mismatch")
            _invoke_bounded_operation(
                self._anchor_commit,
                revision,
                anchor,
                timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
                label="global STOP anchor recovery",
            )
            if _invoke_bounded_operation(
                self._anchor_read,
                timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
                label="global STOP anchor read",
            ) != anchor:
                raise ProductionConsumerError(
                    "global STOP pending anchor recovery failed"
                )
        return meta

    @staticmethod
    def _has_inflight(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM production_dispatches "
            "WHERE state IN ('claimed','dispatched','provider_recorded') LIMIT 1"
        ).fetchone()
        return row is not None

    def _recover_inflight(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            meta = self._assert_integrity(connection)
            now = datetime.now(timezone.utc)
            rows = connection.execute(
                "SELECT d.request_sha256, d.token_json, "
                "COALESCE(p.receipt_json, a.receipt_json) AS receipt_json "
                "FROM production_dispatches AS d "
                "LEFT JOIN production_provider_receipts AS p "
                "ON p.request_sha256=d.request_sha256 "
                "LEFT JOIN production_provider_attempts AS a "
                "ON a.request_sha256=d.request_sha256 "
                "WHERE d.state IN ('claimed','dispatched','provider_recorded') "
                "ORDER BY d.request_sha256"
            ).fetchall()
            for row in rows:
                token = ProviderDispatchToken.model_validate_json(row["token_json"])
                provider = (
                    ProviderResultReceipt.model_validate_json(row["receipt_json"])
                    if row["receipt_json"] is not None
                    else None
                )
                result = _build_result(
                    token,
                    ConsumptionState.UNKNOWN,
                    terminal_at=now,
                    provider_receipt=provider,
                )
                connection.execute(
                    "UPDATE production_dispatches SET state='unknown', result_json=? "
                    "WHERE request_sha256=?",
                    (result.model_dump_json(), row["request_sha256"]),
                )
            reason = _canonical_sha256(
                {"reason": "restart-with-inflight", "requests": [row[0] for row in rows]}
            )
            self._advance(
                connection,
                meta,
                event={"kind": "recovery_stop", "reason_sha256": reason, "at": now},
                updates={
                    "stopped": "1",
                    "epoch": str(int(meta["epoch"]) + 1),
                    "stop_reason_sha256": reason,
                    "stopped_at": now.isoformat(),
                },
            )
        except Exception:
            connection.rollback()
            raise

    def _advance(
        self,
        connection: sqlite3.Connection,
        meta: dict[str, str],
        *,
        event: dict[str, Any],
        updates: dict[str, str] | None = None,
    ) -> str:
        prior_anchor = self._anchor_hash(
            self._store_id,
            int(meta["revision"]),
            meta["head_sha256"],
            meta["state_mac_sha256"],
        )
        if _invoke_bounded_operation(
            self._anchor_read,
            timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
            label="global STOP anchor read",
        ) != prior_anchor:
            raise ProductionConsumerError("global STOP anchor changed before state advance")
        revision = int(meta["revision"]) + 1
        event_json = _canonical_json_bytes(event).decode("utf-8")
        event_sha = _canonical_sha256(
            {
                "revision": revision,
                "previous_head_sha256": meta["head_sha256"],
                "event": event,
            }
        )
        connection.execute(
            "INSERT INTO production_events VALUES (?, ?, ?, ?)",
            (revision, meta["head_sha256"], event_json, event_sha),
        )
        values = {"revision": str(revision), "head_sha256": event_sha}
        values["previous_anchor_sha256"] = prior_anchor
        values.update(updates or {})
        connection.executemany(
            "UPDATE production_meta SET value=? WHERE key=?",
            tuple((value, key) for key, value in values.items()),
        )
        state_mac = self._calculate_state_mac(connection, self._auth_key)
        connection.execute(
            "UPDATE production_meta SET value=? WHERE key='state_mac_sha256'",
            (state_mac,),
        )
        connection.commit()
        anchor = self._anchor_hash(self._store_id, revision, event_sha, state_mac)
        _invoke_bounded_operation(
            self._anchor_commit,
            revision,
            anchor,
            timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
            label="global STOP anchor commit",
        )
        if _invoke_bounded_operation(
            self._anchor_read,
            timeout_seconds=_STORE_COORDINATION_TIMEOUT_SECONDS,
            label="global STOP anchor read",
        ) != anchor:
            raise ProductionConsumerError("global STOP anchor commit was not durable")
        return anchor

    def _require_authority(
        self,
        connection: sqlite3.Connection,
        meta: dict[str, str],
        runtime: ProductionConsumerRuntime,
        *,
        subject_sha256: str,
        purpose: ProductionClockPurpose,
        require_current_roots: bool,
    ) -> tuple[
        datetime,
        SignedProductionConsumerClockAttestation,
        SignedProductionAuthorityRoots | None,
        dict[str, str],
    ]:
        """Make signed authority an invariant of every store-facing operation."""

        if type(runtime) is not ProductionConsumerRuntime:
            raise TypeError("exact ProductionConsumerRuntime is required")
        runtime.assert_sealed()
        if (
            runtime.policy_sha256 != self._policy_sha
            or runtime.policy.store_id_sha256 != self._store_id
        ):
            raise ProductionConsumerError("production runtime/store policy mismatch")
        last_trusted_at = datetime.fromisoformat(meta["last_trusted_at"])
        minimum_revision = int(meta["authority_root_revision"])
        try:
            at, clock, roots = runtime.authoritative_phase(
                subject_sha256=subject_sha256,
                purpose=purpose,
                require_current_roots=require_current_roots,
                minimum_observed_at=last_trusted_at,
                minimum_root_revision=minimum_revision,
            )
        except (TypeError, ValueError, ProductionConsumerError) as exc:
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            reason = _canonical_sha256(
                {
                    "kind": "production-store-authority-failure",
                    "exception_type": type(exc).__name__,
                    "subject_sha256": subject_sha256,
                    "purpose": purpose,
                }
            )
            self._advance(
                connection,
                meta,
                event={
                    "kind": "production_store_authority_failure_stop",
                    "reason_sha256": reason,
                    "last_trusted_at": last_trusted_at,
                    "purpose": purpose,
                },
                updates={
                    "stopped": "1",
                    "epoch": str(int(meta["epoch"]) + 1),
                    "stop_reason_sha256": reason,
                    "stopped_at": last_trusted_at.isoformat(),
                },
            )
            raise ProductionConsumerError(
                "production store authority failed; persistent STOP committed"
            ) from exc
        updates = {"last_trusted_at": at.isoformat()}
        if roots is not None:
            updates["authority_root_revision"] = str(roots.revision)
        return at, clock, roots, updates

    @staticmethod
    def _authority_event(
        clock: SignedProductionConsumerClockAttestation,
        roots: SignedProductionAuthorityRoots | None,
    ) -> dict[str, Any]:
        return {
            "clock_attestation": clock.model_dump(mode="json"),
            "authority_roots": (
                roots.model_dump(mode="json") if roots is not None else None
            ),
        }

    def _close_uncertain_provider_attempt(
        self,
        connection: sqlite3.Connection,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        *,
        terminal_at: datetime,
        clock: SignedProductionConsumerClockAttestation,
        roots: SignedProductionAuthorityRoots | None,
    ) -> ProductionConsumptionResult:
        """Atomically make any escaped/invalid provider callback non-retryable."""

        if connection.in_transaction:
            connection.rollback()
        connection.execute("BEGIN IMMEDIATE")
        try:
            meta = self._assert_integrity(connection)
            row = connection.execute(
                "SELECT state, result_json FROM production_dispatches "
                "WHERE request_sha256=?",
                (request.request_sha256,),
            ).fetchone()
            if row is None:
                raise ProductionConsumerError(
                    "uncertain provider attempt has no durable dispatch"
                )
            if row["result_json"] is not None:
                connection.rollback()
                return ProductionConsumptionResult.model_validate_json(
                    row["result_json"]
                )
            if row["state"] != ConsumptionState.DISPATCHED.value:
                raise ProductionConsumerError(
                    "uncertain provider attempt state is not closable"
                )
            result = _build_result(
                token,
                ConsumptionState.UNKNOWN,
                terminal_at=terminal_at,
            )
            reason = _canonical_sha256(
                {
                    "reason": "provider-callback-escaped-without-authoritative-fact",
                    "request_sha256": request.request_sha256,
                    "dispatch_payload_sha256": token.payload_sha256,
                }
            )
            connection.execute(
                "UPDATE production_dispatches SET state='unknown', result_json=? "
                "WHERE request_sha256=?",
                (result.model_dump_json(), request.request_sha256),
            )
            self._advance(
                connection,
                meta,
                event={
                    "kind": "provider_callback_uncertain_stop",
                    "request_sha256": request.request_sha256,
                    "result_sha256": result.result_sha256,
                    "at": terminal_at,
                    **self._authority_event(clock, roots),
                },
                updates={
                    "stopped": "1",
                    "epoch": str(int(meta["epoch"]) + 1),
                    "stop_reason_sha256": reason,
                    "stopped_at": terminal_at.isoformat(),
                },
            )
            self._release_inflight_owner()
            return result
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def snapshot(self) -> GlobalStopSnapshot:
        with self._lock, self._file_lock(), self._connect() as connection:
            meta = self._assert_integrity(connection)
            anchor = self._anchor_hash(
                self._store_id,
                int(meta["revision"]),
                meta["head_sha256"],
                meta["state_mac_sha256"],
            )
            return GlobalStopSnapshot(
                store_id_sha256=self._store_id,
                policy_sha256=self._policy_sha,
                stopped=meta["stopped"] == "1",
                epoch=int(meta["epoch"]),
                revision=int(meta["revision"]),
                head_sha256=meta["head_sha256"],
                stop_reason_sha256=meta["stop_reason_sha256"],
                stopped_at=datetime.fromisoformat(meta["stopped_at"]),
                anchor_sha256=anchor,
            )

    def freeze_after_clock_failure(
        self, *, reason_sha256: str, last_trusted_at: datetime | None
    ) -> GlobalStopSnapshot:
        """Persist a fencing STOP when authoritative time becomes unavailable."""

        stopped_at = last_trusted_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        _require_utc(stopped_at, "clock failure last trusted time")
        if not isinstance(reason_sha256, str) or len(reason_sha256) != 64:
            raise ProductionConsumerError("clock failure reason must be SHA-256")
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "trusted_clock_failure_stop",
                        "reason_sha256": reason_sha256,
                        "last_trusted_at": stopped_at,
                    },
                    updates={
                        "stopped": "1",
                        "epoch": str(int(meta["epoch"]) + 1),
                        "stop_reason_sha256": reason_sha256,
                        "stopped_at": stopped_at.isoformat(),
                    },
                )
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return self.snapshot()

    @contextmanager
    def dispatch_fence(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> Iterator[tuple[_ProviderInvocationCapability, datetime]]:
        """Fence the independent probe after the provider fact is durable."""

        _require_utc(at, "provider dispatch fence time")
        if (
            runtime.policy_sha256 != self._policy_sha
            or runtime.policy.store_id_sha256 != self._store_id
        ):
            raise ProductionConsumerError("dispatch fence runtime/store policy mismatch")
        with self._lock, self._file_lock(), self._connect() as connection:
            meta = self._assert_integrity(connection)
            at, clock, roots, authority_updates = self._require_authority(
                connection,
                meta,
                runtime,
                subject_sha256=request.request_sha256,
                purpose=ProductionClockPurpose.PRE_PROBE,
                require_current_roots=(
                    request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                ),
            )
            row = connection.execute(
                "SELECT d.request_json, d.token_json, d.state, p.receipt_json "
                "FROM production_dispatches AS d "
                "LEFT JOIN production_provider_receipts AS p "
                "ON p.request_sha256=d.request_sha256 "
                "WHERE d.request_sha256=?",
                (request.request_sha256,),
            ).fetchone()
            if (
                row is None
                or not self._owns_inflight()
                or row["state"] != "provider_recorded"
                or row["receipt_json"] is None
                or row["request_json"] != _canonical_model_json(request)
                or ProviderDispatchToken.model_validate_json(row["token_json"]) != token
                or token.store_id_sha256 != self._store_id
                or token.policy_sha256 != self._policy_sha
                or token.epoch != int(meta["epoch"])
                or token.fencing_token + 4 != int(meta["revision"])
                or not token.issued_at <= at < token.expires_at
                or not _verify_signed(token, runtime.trust.dispatcher)
                or not runtime.verifies(request, at=at)
                or (
                    request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    and meta["stopped"] == "1"
                )
            ):
                raise ProductionConsumerError("dispatch fence is stale or invalid")
            connection.execute("BEGIN IMMEDIATE")
            self._advance(
                connection,
                meta,
                event={
                    "kind": "provider_probe_intent_recorded",
                    "request_sha256": request.request_sha256,
                    "dispatch_payload_sha256": token.payload_sha256,
                    "at": at,
                    **self._authority_event(clock, roots),
                },
                updates=authority_updates,
            )
            permit = object()
            with _PROVIDER_CAPABILITY_LOCK:
                _PROVIDER_CAPABILITY_PERMITS[
                    self._provider_capability_seal
                ] = permit
            try:
                capability = _issue_provider_invocation_capability(
                    self._provider_capability_seal,
                    permit,
                    token,
                    "probe",
                    at,
                )
            finally:
                with _PROVIDER_CAPABILITY_LOCK:
                    _PROVIDER_CAPABILITY_PERMITS.pop(
                        self._provider_capability_seal, None
                    )
            try:
                yield capability, at
            finally:
                _revoke_provider_invocation_capability(capability)

    def apply_reset(
        self,
        reset: HumanGlobalStopReset,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> GlobalStopSnapshot:
        _require_utc(at, "global STOP reset application time")
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                if (
                    runtime.policy_sha256 != self._policy_sha
                    or runtime.policy.store_id_sha256 != self._store_id
                ):
                    raise ProductionConsumerError(
                        "reset runtime/store policy mismatch"
                    )
                try:
                    item = HumanGlobalStopReset.model_validate(reset.model_dump())
                except (TypeError, ValueError) as exc:
                    raise ProductionConsumerError(
                        "Human global STOP reset is invalid"
                    ) from exc
                at, clock, roots, authority_updates = self._require_authority(
                    connection,
                    meta,
                    runtime,
                    subject_sha256=item.payload_sha256,
                    purpose=ProductionClockPurpose.RESET,
                    require_current_roots=False,
                )
                if (
                    meta["stopped"] != "1"
                    or item.store_id_sha256 != self._store_id
                    or item.policy_sha256 != self._policy_sha
                    or item.stopped_epoch != int(meta["epoch"])
                    or item.stopped_revision != int(meta["revision"])
                    or item.stopped_head_sha256 != meta["head_sha256"]
                    or item.stop_reason_sha256 != meta["stop_reason_sha256"]
                    or item.issued_at < datetime.fromisoformat(meta["stopped_at"])
                    or not item.not_before <= at < item.expires_at
                    or item.expires_at - item.issued_at
                    > timedelta(seconds=runtime.policy.maximum_reset_ttl_seconds)
                    or not _verify_signed(item, runtime.trust.reset_human)
                    or not runtime.reconciliation_ledger.verifies_for_reset(
                        item.reconciliation_record_sha256,
                        p13_store_identity_sha256=self._store_id,
                        stopped_revision=int(meta["revision"]),
                        stopped_head_sha256=meta["head_sha256"],
                        stop_reason_sha256=meta["stop_reason_sha256"],
                        at=at,
                    )
                    or self._has_inflight(connection)
                ):
                    raise ProductionConsumerError("Human global STOP reset is invalid")
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "human_reset",
                        "reset_payload_sha256": item.payload_sha256,
                        "at": at,
                        **self._authority_event(clock, roots),
                    },
                    updates={
                        "stopped": "0",
                        "epoch": str(int(meta["epoch"]) + 1),
                        **authority_updates,
                    },
                )
            except Exception:
                connection.rollback()
                raise
        return self.snapshot()

    def claim(
        self,
        request: ProductionConsumptionRequest,
        runtime: ProductionConsumerRuntime,
        dispatcher_private_key: Ed25519PrivateKey,
        *,
        at: datetime,
    ) -> ProviderDispatchToken | ProductionConsumptionResult:
        return _GlobalStopStoreOperations.claim(
            self, request, runtime, dispatcher_private_key, at=at
        )

    def redeem(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> ProductionConsumptionResult | None:
        return _GlobalStopStoreOperations.redeem(
            self, request, token, runtime, at=at
        )

    def _invoke_and_record_provider(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        port: _SubprocessProviderExecutionPort,
        *,
        at: datetime,
    ) -> ProviderResultReceipt:
        if (
            type(port) is not _SubprocessProviderExecutionPort
            or not port.validates(request, token, runtime)
        ):
            raise ProductionConsumerError(
                "exact subprocess provider execution port is required"
            )
        return _GlobalStopStoreOperations._invoke_and_record_provider(
            self,
            request,
            token,
            runtime,
            port,
            at=at,
        )

    def commit_result(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        *,
        state: ConsumptionState,
        terminal_at: datetime,
        provider_receipt: ProviderResultReceipt | None = None,
        probe_receipt: ProviderProbeReceipt | None = None,
        action_receipt: ActionReceipt | None = None,
        stop_reason_sha256: str | None = None,
    ) -> ProductionConsumptionResult:
        return _GlobalStopStoreOperations.commit_result(
            self,
            request,
            token,
            runtime,
            state=state,
            terminal_at=terminal_at,
            provider_receipt=provider_receipt,
            probe_receipt=probe_receipt,
            action_receipt=action_receipt,
            stop_reason_sha256=stop_reason_sha256,
        )


class ProductionConsumer:
    """Coordinates one durable P11 claim and one provider subprocess boundary."""

    __slots__ = (
        "runtime",
        "store",
        "_dispatcher_key",
        "_clock_attest",
        "_clock_failed",
        "_last_observed_at",
        "_authority_root_resolver",
        "_authority_failed",
        "_last_authority_revision",
        "_has_claimed",
        "_lock",
    )

    def __init__(
        self,
        runtime: ProductionConsumerRuntime,
        store: GlobalStopStore,
        dispatcher_private_key: Ed25519PrivateKey,
        *,
        clock_attest: Callable[
            [ProductionConsumerClockRequest],
            SignedProductionConsumerClockAttestation,
        ],
        current_authority_roots: Callable[
            [ProductionAuthorityRootRequest],
            SignedProductionAuthorityRoots,
        ],
    ) -> None:
        if type(runtime) is not ProductionConsumerRuntime:
            raise TypeError("runtime must be ProductionConsumerRuntime")
        if type(store) is not GlobalStopStore:
            raise TypeError("store must be GlobalStopStore")
        if not _private_key_matches(dispatcher_private_key, runtime.trust.dispatcher):
            raise ProductionConsumerError("dispatcher private key mismatch")
        if not callable(clock_attest):
            raise TypeError("authoritative production clock callback is required")
        if not callable(current_authority_roots):
            raise TypeError("current production authority-root callback is required")
        store_snapshot = store.snapshot()
        if (
            store_snapshot.store_id_sha256 != runtime.policy.store_id_sha256
            or store_snapshot.policy_sha256 != runtime.policy_sha256
        ):
            raise ProductionConsumerError("consumer store pin mismatch")
        self.runtime = runtime
        self.store = store
        self._dispatcher_key = dispatcher_private_key
        self._clock_attest = clock_attest
        self._clock_failed = False
        self._last_observed_at: datetime | None = None
        self._authority_root_resolver = current_authority_roots
        self._authority_failed = False
        self._last_authority_revision = 0
        self._has_claimed = False
        self._lock = RLock()

    def execute(
        self,
        request: ProductionConsumptionRequest,
        adapter: SubprocessProviderAdapter,
    ) -> ProductionConsumptionResult:
        """Run the synthetic adapter path; every ambiguity becomes sticky STOP."""

        with self._lock:
            if type(adapter) is not SubprocessProviderAdapter or not adapter.matches(request):
                raise ProductionConsumerError(
                    "provider adapter bootstrap does not match the pinned request"
                )
            now = self._now(request, ProductionClockPurpose.CLAIM)
            claimed = self.store.claim(
                request,
                self.runtime,
                self._dispatcher_key,
                at=now,
            )
            if isinstance(claimed, ProductionConsumptionResult):
                return claimed
            token = claimed
            self._has_claimed = True
            verified_provider: ProviderResultReceipt | None = None
            try:
                redemption = self.store.redeem(
                    request,
                    token,
                    self.runtime,
                    at=self._now(request, ProductionClockPurpose.REDEEM),
                )
                if redemption is not None:
                    self._has_claimed = False
                    return redemption
                if not self.runtime.verifies_execution_boundary(
                    request,
                    at=self._now(request, ProductionClockPurpose.PRE_PROVIDER),
                ):
                    raise ProductionConsumerError(
                        "P16/P18 execution-boundary authority is stale or invalid"
                    )
                provider = adapter.execute(
                    request,
                    token,
                    self.store,
                    self.runtime,
                    at=self._last_observed_at or now,
                )
                verified_provider = provider
                after_provider = self._last_observed_at or now
                if not self._valid_provider_result(token, provider, at=after_provider):
                    raise ProductionConsumerError("provider result receipt is invalid")
                if (
                    provider.outcome is not ProviderOutcome.SUCCEEDED
                    or provider.observed_post_state_sha256
                    != token.expected_post_state_sha256
                ):
                    state = {
                        ProviderOutcome.FAILED: ConsumptionState.FAILED,
                        ProviderOutcome.PARTIAL: ConsumptionState.PARTIAL,
                        ProviderOutcome.UNKNOWN: ConsumptionState.UNKNOWN,
                        ProviderOutcome.SUCCEEDED: ConsumptionState.UNKNOWN,
                    }[provider.outcome]
                    result = self.store.commit_result(
                        request,
                        token,
                        self.runtime,
                        state=state,
                        provider_receipt=provider,
                        terminal_at=after_provider,
                    )
                    self._has_claimed = False
                    return result
                if not self.runtime.verifies(request, at=after_provider):
                    raise ProductionConsumerError("authority expired before independent probe")
                probe = adapter.probe(
                    request,
                    token,
                    self.store,
                    self.runtime,
                    at=self._now(request, ProductionClockPurpose.PRE_PROBE),
                )
                after_probe = self._now(request, ProductionClockPurpose.POST_PROBE)
                if not self._valid_probe(
                    token, provider, probe, at=after_probe
                ):
                    raise ProductionConsumerError("independent postcondition probe is invalid")
                action_receipt = sign_action_receipt(
                    request.external_request,
                    request.human_approval,
                    request.controller_grant,
                    request.execution_claim,
                    self.runtime.external_guard,
                    self._dispatcher_key,
                    issuer=self.runtime.trust.dispatcher.issuer,
                    result=ActionResult.SUCCEEDED,
                    observed_pre_state_sha256=token.expected_pre_state_sha256,
                    observed_post_state_sha256=token.expected_post_state_sha256,
                    provider_operation_sha256=provider.payload_sha256,
                    provider_audit_receipt_sha256=provider.provider_audit_receipt_sha256,
                )
                terminal_at = self._now(request, ProductionClockPurpose.TERMINAL)
                result = self.store.commit_result(
                    request,
                    token,
                    self.runtime,
                    state=ConsumptionState.SUCCEEDED,
                    provider_receipt=provider,
                    probe_receipt=probe,
                    action_receipt=action_receipt,
                    terminal_at=terminal_at,
                )
                self._has_claimed = False
                return result
            except Exception as exc:
                terminal_at = self._last_observed_at or datetime(
                    1970, 1, 1, tzinfo=timezone.utc
                )
                reason = _canonical_sha256(
                    {
                        "kind": "provider-boundary-failure",
                        "exception_type": type(exc).__name__,
                        "request_sha256": request.request_sha256,
                    }
                )
                try:
                    result = self.store.commit_result(
                        request,
                        token,
                        self.runtime,
                        state=ConsumptionState.UNKNOWN,
                        provider_receipt=verified_provider,
                        terminal_at=terminal_at,
                        stop_reason_sha256=reason,
                    )
                    self._has_claimed = False
                    return result
                except ProductionConsumerError:
                    raise ProductionConsumerError(
                        "provider boundary failed and terminal STOP could not be committed"
                    ) from exc

    def _now(
        self,
        request: ProductionConsumptionRequest,
        purpose: ProductionClockPurpose,
    ) -> datetime:
        if self._clock_failed:
            raise ProductionConsumerError(
                "production trusted clock is frozen after failure"
            )
        request_values = {
            "store_id_sha256": self.runtime.policy.store_id_sha256,
            "policy_sha256": self.runtime.policy_sha256,
            "production_request_sha256": request.request_sha256,
            "purpose": purpose,
            "nonce_sha256": hashlib.sha256(os.urandom(32)).hexdigest(),
        }
        provisional = ProductionConsumerClockRequest.model_construct(
            **request_values, schema_version="1.0", request_sha256="0" * 64
        )
        clock_request = ProductionConsumerClockRequest(
            **request_values,
            request_sha256=hash_production_consumer_clock_request(provisional),
        )
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                output.put((True, self._clock_attest(clock_request)), block=False)
            except BaseException as exc:
                try:
                    output.put((False, exc), block=False)
                except BaseException:
                    pass

        Thread(
            target=invoke,
            name=f"production-clock-{clock_request.nonce_sha256[:12]}",
            daemon=True,
        ).start()
        try:
            succeeded, value = output.get(
                timeout=self.runtime.policy.clock_response_timeout_seconds
            )
            if not succeeded:
                raise ProductionConsumerError(
                    "production trusted clock callback failed"
                ) from value if isinstance(value, BaseException) else None
            clock = SignedProductionConsumerClockAttestation.model_validate(
                value.model_dump()  # type: ignore[union-attr]
            )
            if (
                clock.request_sha256 != clock_request.request_sha256
                or not _verify_signed(
                    clock, self.runtime.integration_trust.time_auditor
                )
                or clock.expires_at - clock.issued_at
                > timedelta(
                    seconds=(
                        self.runtime.policy.maximum_clock_attestation_ttl_seconds
                    )
                )
                or clock.issued_at - clock.observed_at
                > timedelta(
                    seconds=(
                        self.runtime.policy.maximum_clock_observation_lag_seconds
                    )
                )
                or (
                    self._last_observed_at is not None
                    and clock.observed_at < self._last_observed_at
                )
            ):
                raise ProductionConsumerError(
                    "production trusted clock attestation is invalid"
                )
        except (Empty, AttributeError, TypeError, ValueError, ProductionConsumerError) as exc:
            self._clock_failed = True
            reason = _canonical_sha256(
                {
                    "kind": "production-trusted-clock-failure",
                    "exception_type": type(exc).__name__,
                    "request_sha256": request.request_sha256,
                    "purpose": purpose.value,
                }
            )
            if not self._has_claimed:
                self.store.freeze_after_clock_failure(
                    reason_sha256=reason,
                    last_trusted_at=self._last_observed_at,
                )
            raise ProductionConsumerError(
                "production trusted clock failed; persistent STOP committed"
            ) from exc
        self._last_observed_at = clock.observed_at
        if request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE:
            self._verify_current_authority_roots(
                request, purpose=purpose, at=clock.observed_at
            )
        return clock.observed_at

    def _verify_current_authority_roots(
        self,
        request: ProductionConsumptionRequest,
        *,
        purpose: ProductionClockPurpose,
        at: datetime,
    ) -> None:
        if self._authority_failed:
            raise ProductionConsumerError(
                "production authority-root resolver is frozen after failure"
            )
        values = {
            "store_id_sha256": self.runtime.policy.store_id_sha256,
            "policy_sha256": self.runtime.policy_sha256,
            "production_request_sha256": request.request_sha256,
            "purpose": purpose,
            "nonce_sha256": hashlib.sha256(os.urandom(32)).hexdigest(),
        }
        provisional = ProductionAuthorityRootRequest.model_construct(
            **values, schema_version="1.0", request_sha256="0" * 64
        )
        root_request = ProductionAuthorityRootRequest(
            **values,
            request_sha256=hash_production_authority_root_request(provisional),
        )
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                output.put(
                    (True, self._authority_root_resolver(root_request)),
                    block=False,
                )
            except BaseException as exc:
                try:
                    output.put((False, exc), block=False)
                except BaseException:
                    pass

        Thread(
            target=invoke,
            name=f"production-authority-root-{root_request.nonce_sha256[:12]}",
            daemon=True,
        ).start()
        try:
            succeeded, value = output.get(
                timeout=(
                    self.runtime.policy.authority_root_response_timeout_seconds
                )
            )
            if not succeeded:
                raise ProductionConsumerError(
                    "production authority-root callback failed"
                ) from value if isinstance(value, BaseException) else None
            snapshot = SignedProductionAuthorityRoots.model_validate(
                value.model_dump()  # type: ignore[union-attr]
            )
            if (
                snapshot.request_sha256 != root_request.request_sha256
                or not _verify_signed(
                    snapshot, self.runtime.integration_trust.storage_auditor
                )
                or snapshot.repository_acceptance_authority_sha256
                != self.runtime.repository_authority_root_sha256
                or snapshot.launch_handoff_authority_sha256
                != self.runtime.launch_authority_root_sha256
                or snapshot.launch_semantic_authority_sha256
                != self.runtime.launch_semantic_authority_root_sha256
                or not snapshot.observed_at <= at < snapshot.expires_at
                or snapshot.expires_at - snapshot.issued_at
                > timedelta(
                    seconds=self.runtime.policy.maximum_authority_root_ttl_seconds
                )
                or snapshot.issued_at - snapshot.observed_at
                > timedelta(
                    seconds=(
                        self.runtime.policy
                        .maximum_authority_root_observation_lag_seconds
                    )
                )
                or snapshot.revision < self._last_authority_revision
            ):
                raise ProductionConsumerError(
                    "current production authority roots are invalid"
                )
        except (Empty, AttributeError, TypeError, ValueError, ProductionConsumerError) as exc:
            self._authority_failed = True
            reason = _canonical_sha256(
                {
                    "kind": "production-authority-root-failure",
                    "exception_type": type(exc).__name__,
                    "request_sha256": request.request_sha256,
                    "purpose": purpose.value,
                }
            )
            if not self._has_claimed:
                self.store.freeze_after_clock_failure(
                    reason_sha256=reason,
                    last_trusted_at=at,
                )
            raise ProductionConsumerError(
                "current production authority roots failed; persistent STOP committed"
            ) from exc
        self._last_authority_revision = snapshot.revision

    def _valid_provider_result(
        self,
        token: ProviderDispatchToken,
        receipt: ProviderResultReceipt,
        *,
        at: datetime,
    ) -> bool:
        return self.runtime.verifies_provider_result(token, receipt, at=at)

    def _valid_probe(
        self,
        token: ProviderDispatchToken,
        provider_receipt: ProviderResultReceipt,
        probe: ProviderProbeReceipt,
        *,
        at: datetime,
    ) -> bool:
        return self.runtime.verifies_probe(
            token, provider_receipt, probe, at=at
        )


def _communicate_bounded(
    process: subprocess.Popen[bytes],
    payload: bytes,
    *,
    timeout_seconds: int,
    absolute_deadline: float,
    maximum_output_bytes: int,
) -> tuple[bytes, bytes]:
    """Exchange one frame without allowing child output to grow unbounded."""

    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise ProductionConsumerError("adapter subprocess pipes are unavailable")
    selector = selectors.DefaultSelector()
    streams = {
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    buffers = {name: bytearray() for name in streams}
    input_offset = 0
    for name, stream in streams.items():
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    os.set_blocking(process.stdin.fileno(), False)
    selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    deadline = min(time.monotonic() + timeout_seconds, absolute_deadline)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProductionConsumerError(
                    "adapter subprocess failed or timed out"
                )
            events = selector.select(remaining)
            if not events:
                raise ProductionConsumerError(
                    "adapter subprocess failed or timed out"
                )
            for key, _ in events:
                stream = key.fileobj
                name = key.data
                if name == "stdin":
                    try:
                        written = os.write(
                            stream.fileno(), payload[input_offset:]
                        )
                    except BrokenPipeError:
                        written = 0
                        input_offset = len(payload)
                    else:
                        input_offset += written
                    if input_offset >= len(payload):
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                buffers[name].extend(chunk)
                if len(buffers[name]) > maximum_output_bytes:
                    raise ProductionConsumerError(
                        "adapter subprocess exceeded the output limit"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProductionConsumerError(
                "adapter subprocess failed or timed out"
            )
        process.wait(timeout=remaining)
    except (OSError, subprocess.TimeoutExpired, ProductionConsumerError) as exc:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=0)
        except subprocess.TimeoutExpired:
            def reap_after_authority_release() -> None:
                try:
                    # Keep cleanup off the authority-critical path without an
                    # unbounded Popen.wait().  poll() performs non-blocking
                    # waitpid checks and still reaps the killed child once the
                    # kernel publishes its terminal status.
                    while process.poll() is None:
                        time.sleep(0.01)
                except BaseException:
                    pass

            try:
                Thread(
                    target=reap_after_authority_release,
                    name="saas-preflight-provider-reaper",
                    daemon=True,
                ).start()
            except BaseException:
                # Reaping is availability cleanup only.  It must never extend
                # the mutation authority deadline or retain the store locks.
                pass
        if isinstance(exc, ProductionConsumerError):
            raise
        raise ProductionConsumerError(
            "adapter subprocess failed or timed out"
        ) from exc
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    return bytes(buffers["stdout"]), bytes(buffers["stderr"])


class SubprocessProviderAdapter:
    """Pinned, fenced launchers for the synthetic provider and independent probe.

    Execute and probe are distinct programs and receive only their own 0600
    signing key.  A current GlobalStopStore dispatch fence is held for the full
    subprocess lifetime; direct replay of a stopped or old-epoch token fails
    before either child is started.
    """

    __slots__ = (
        "_execute_script", "_execute_digest", "_probe_script", "_probe_digest",
        "_python", "_python_digest", "_dependencies", "_dependency_digest",
        "_state", "_provider_key", "_probe_key", "_dispatcher_key",
        "_allowlist", "_allowlist_digest", "_adapter_id", "_schema",
        "_schema_digest", "_timeout", "_max_output",
        "_provider_key_digest", "_probe_key_digest",
        "_dispatcher_key_digest", "_allowlist_file_digest",
    )

    def __init__(
        self,
        *,
        execute_script_path: str | Path,
        expected_execute_executable_sha256: str,
        probe_script_path: str | Path,
        expected_probe_executable_sha256: str,
        python_executable_path: str | Path,
        expected_python_executable_sha256: str,
        dependency_paths: tuple[str | Path, ...],
        expected_dependency_closure_sha256: str,
        state_path: str | Path,
        provider_private_key_path: str | Path,
        probe_private_key_path: str | Path,
        dispatcher_verification_key_path: str | Path,
        allowlist_path: str | Path,
        postcondition_schema_path: str | Path,
        adapter_id: str,
        timeout_seconds: int = 5,
        maximum_output_bytes: int = 262_144,
    ) -> None:
        self._execute_script = Path(execute_script_path).absolute()
        self._execute_digest = expected_execute_executable_sha256
        self._probe_script = Path(probe_script_path).absolute()
        self._probe_digest = expected_probe_executable_sha256
        self._python = Path(python_executable_path).absolute()
        self._python_digest = expected_python_executable_sha256
        self._dependencies = tuple(Path(path).absolute() for path in dependency_paths)
        if self._dependencies != production_adapter_dependency_paths():
            raise ProductionConsumerError(
                "adapter dependency closure does not match the fixed manifest"
            )
        self._dependency_digest = expected_dependency_closure_sha256
        self._state = Path(state_path).absolute()
        self._provider_key = Path(provider_private_key_path).absolute()
        self._probe_key = Path(probe_private_key_path).absolute()
        self._dispatcher_key = Path(dispatcher_verification_key_path).absolute()
        self._allowlist = Path(allowlist_path).absolute()
        self._schema = Path(postcondition_schema_path).absolute()
        self._adapter_id = adapter_id
        self._timeout = timeout_seconds
        self._max_output = maximum_output_bytes
        if not 1 <= timeout_seconds <= 60 or not 1024 <= maximum_output_bytes <= 1_048_576:
            raise ValueError("subprocess adapter limits are out of bounds")
        self._verify_files()
        initial_manifest = _adapter_dependency_manifest(self._dependencies)
        if (
            _hash_adapter_dependency_manifest(
                self._dependencies, initial_manifest
            )
            != self._dependency_digest
        ):
            raise ProductionConsumerError(
                "adapter dependency closure digest mismatch"
            )
        self._provider_key_digest = _file_sha256(self._provider_key)
        self._probe_key_digest = _file_sha256(self._probe_key)
        self._dispatcher_key_digest = _file_sha256(self._dispatcher_key)
        self._allowlist_file_digest = _file_sha256(self._allowlist)
        self._allowlist_digest = _canonical_sha256(
            json.loads(_read_pinned_bytes(self._allowlist).decode("utf-8"))
        )
        self._schema_digest = _file_sha256(self._schema)

    def matches(self, request: ProductionConsumptionRequest) -> bool:
        return (
            request.adapter_id == self._adapter_id
            and request.adapter_executable_sha256 == self._execute_digest
            and request.probe_executable_sha256 == self._probe_digest
            and request.python_executable_sha256 == self._python_digest
            and request.adapter_dependency_closure_sha256
            == self._dependency_digest
            and request.provider_allowlist_sha256 == self._allowlist_digest
            and request.postcondition_schema_sha256 == self._schema_digest
        )

    def _execution_profile_sha256(self) -> str:
        return _canonical_sha256(
            {
                "adapter_id": self._adapter_id,
                "execute_sha256": self._execute_digest,
                "probe_sha256": self._probe_digest,
                "python_sha256": self._python_digest,
                "dependency_sha256": self._dependency_digest,
                "allowlist_sha256": self._allowlist_digest,
                "schema_sha256": self._schema_digest,
                "timeout_seconds": self._timeout,
                "maximum_output_bytes": self._max_output,
            }
        )

    def _bind_execute(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
    ) -> _SubprocessProviderExecutionPort:
        if type(self) is not SubprocessProviderAdapter or not self.matches(request):
            raise ProductionConsumerError(
                "provider adapter bootstrap does not match the pinned request"
            )
        if self._timeout >= runtime.policy.minimum_provider_authority_margin_seconds:
            raise ProductionConsumerError(
                "adapter timeout must fit inside provider authority margin"
            )
        return _SubprocessProviderExecutionPort(
            _SUBPROCESS_PROVIDER_EXECUTION_PORT_SEAL,
            self,
            request,
            token,
        )

    def execute(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        store: GlobalStopStore,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> ProviderResultReceipt:
        port = self._bind_execute(request, token, runtime)
        return store._invoke_and_record_provider(
            request,
            token,
            runtime,
            port,
            at=at,
        )

    def probe(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        store: GlobalStopStore,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> ProviderProbeReceipt:
        if self._timeout >= runtime.policy.minimum_provider_authority_margin_seconds:
            raise ProductionConsumerError(
                "probe timeout must fit inside provider authority margin"
            )
        with store.dispatch_fence(request, token, runtime, at=at) as (
            capability,
            _,
        ):
            data = self._invoke(
                "probe",
                token,
                capability=capability,
                absolute_deadline=time.monotonic() + self._timeout,
            )
        return ProviderProbeReceipt.model_validate_json(_canonical_json_bytes(data))

    def _verify_files(self) -> None:
        if _file_sha256(self._execute_script) != self._execute_digest:
            raise ProductionConsumerError("adapter executable digest mismatch")
        if _file_sha256(self._probe_script) != self._probe_digest:
            raise ProductionConsumerError("probe executable digest mismatch")
        if _file_sha256(self._python) != self._python_digest:
            raise ProductionConsumerError("Python executable digest mismatch")
        if hasattr(self, "_provider_key_digest") and (
            _file_sha256(self._provider_key) != self._provider_key_digest
            or _file_sha256(self._probe_key) != self._probe_key_digest
            or _file_sha256(self._dispatcher_key)
            != self._dispatcher_key_digest
            or _file_sha256(self._allowlist)
            != self._allowlist_file_digest
        ):
            raise ProductionConsumerError("adapter bootstrap file digest mismatch")
        for secret in (self._provider_key, self._probe_key):
            try:
                descriptor, metadata = _open_regular_file_no_follow(secret)
            except OSError as exc:
                raise ProductionConsumerError(
                    "adapter-owned signing key permissions are unsafe"
                ) from exc
            os.close(descriptor)
            if metadata.st_mode & 0o077:
                raise ProductionConsumerError("adapter-owned signing key permissions are unsafe")
        for public in (self._dispatcher_key, self._allowlist, self._schema):
            try:
                descriptor, _ = _open_regular_file_no_follow(public)
            except OSError as exc:
                raise ProductionConsumerError(
                    "adapter bootstrap file is missing"
                ) from exc
            else:
                os.close(descriptor)
        try:
            current_allowlist = json.loads(
                _read_pinned_bytes(self._allowlist).decode("utf-8")
            )
            current_schema = json.loads(
                _read_pinned_bytes(self._schema).decode("utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionConsumerError("adapter policy file is invalid") from exc
        if type(current_allowlist) is not dict or type(current_schema) is not dict:
            raise ProductionConsumerError("adapter policy file must be one object")
        if hasattr(self, "_allowlist_digest") and (
            _canonical_sha256(current_allowlist) != self._allowlist_digest
            or _file_sha256(self._schema) != self._schema_digest
        ):
            raise ProductionConsumerError("adapter policy file digest mismatch")

    @contextmanager
    def _verified_script(self, path: Path, expected_sha256: str) -> Iterator[int]:
        try:
            descriptor, before = _open_regular_file_no_follow(path)
        except OSError as exc:
            raise ProductionConsumerError("adapter executable could not be opened") from exc
        try:
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1_048_576):
                digest.update(chunk)
            if digest.hexdigest() != expected_sha256:
                raise ProductionConsumerError("adapter executable digest mismatch")
            _require_unchanged_file(descriptor, before, path.name)
            os.lseek(descriptor, 0, os.SEEK_SET)
            yield descriptor
            _require_unchanged_file(descriptor, before, path.name)
        finally:
            os.close(descriptor)

    def _invoke(
        self,
        command: Literal["execute", "probe"],
        token: ProviderDispatchToken,
        *,
        capability: _ProviderInvocationCapability,
        absolute_deadline: float,
    ) -> dict[str, Any]:
        if type(capability) is not _ProviderInvocationCapability:
            raise ProductionConsumerError(
                "adapter subprocess requires store-issued capability"
            )
        if (
            not isinstance(absolute_deadline, float)
            or not absolute_deadline > time.monotonic()
        ):
            raise ProductionConsumerError(
                "adapter subprocess execution deadline is exhausted"
            )
        at = capability.consume(token=token, command=command)
        _require_utc(at, "subprocess adapter invocation time")
        self._verify_files()
        if time.monotonic() >= absolute_deadline:
            raise ProductionConsumerError(
                "adapter subprocess execution deadline is exhausted"
            )
        script = self._execute_script if command == "execute" else self._probe_script
        expected = self._execute_digest if command == "execute" else self._probe_digest
        secret_flag = "--provider-key" if command == "execute" else "--probe-key"
        secret = self._provider_key if command == "execute" else self._probe_key
        payload = _canonical_json_bytes(
            {"token": token.model_dump(mode="json"), "at": at}
        )
        isolated_import_paths = tuple(
            dict.fromkeys(
                str(Path(value).absolute())
                for value in (
                    Path(__file__).resolve().parents[1],
                    sysconfig.get_path("purelib"),
                    sysconfig.get_path("platlib"),
                )
            )
        )
        dependency_manifest = _adapter_dependency_manifest(
            self._dependencies,
            absolute_deadline=absolute_deadline,
        )
        if (
            _hash_adapter_dependency_manifest(
                self._dependencies, dependency_manifest
            )
            != self._dependency_digest
        ):
            raise ProductionConsumerError(
                "adapter dependency closure digest mismatch"
            )
        if time.monotonic() >= absolute_deadline:
            raise ProductionConsumerError(
                "adapter subprocess execution deadline is exhausted"
            )
        manifest_payload = json.dumps(
            dependency_manifest, separators=(",", ":")
        ).encode("utf-8")
        secret_digest = (
            self._provider_key_digest
            if command == "execute"
            else self._probe_key_digest
        )
        with ExitStack() as stack:
            descriptor = stack.enter_context(
                self._verified_script(script, expected)
            )
            secret_descriptor = stack.enter_context(
                self._verified_script(secret, secret_digest)
            )
            dispatcher_descriptor = stack.enter_context(
                self._verified_script(
                    self._dispatcher_key, self._dispatcher_key_digest
                )
            )
            allowlist_descriptor = stack.enter_context(
                self._verified_script(
                    self._allowlist, self._allowlist_file_digest
                )
            )
            schema_descriptor = stack.enter_context(
                self._verified_script(self._schema, self._schema_digest)
            )
            manifest_file = stack.enter_context(tempfile.TemporaryFile())
            manifest_file.write(manifest_payload)
            manifest_file.flush()
            manifest_file.seek(0)
            argv = (
                str(self._python),
                "-I",
                "-S",
                "-B",
                "-c",
                _ISOLATED_ADAPTER_LAUNCHER,
                str(manifest_file.fileno()),
                json.dumps(isolated_import_paths, separators=(",", ":")),
                f"/dev/fd/{descriptor}",
                "--state",
                str(self._state),
                secret_flag,
                f"/dev/fd/{secret_descriptor}",
                "--dispatcher-key",
                f"/dev/fd/{dispatcher_descriptor}",
                "--allowlist",
                f"/dev/fd/{allowlist_descriptor}",
                "--postcondition-schema",
                f"/dev/fd/{schema_descriptor}",
            )
            try:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    close_fds=True,
                    pass_fds=(
                        descriptor,
                        manifest_file.fileno(),
                        secret_descriptor,
                        dispatcher_descriptor,
                        allowlist_descriptor,
                        schema_descriptor,
                    ),
                    cwd="/",
                    env={
                        "LANG": "C",
                        "LC_ALL": "C",
                        "PATH": "/usr/bin:/bin",
                        "PYTHONHASHSEED": "0",
                        "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    start_new_session=True,
                )
                stdout, stderr = _communicate_bounded(
                    process,
                    payload,
                    timeout_seconds=self._timeout,
                    absolute_deadline=absolute_deadline,
                    maximum_output_bytes=self._max_output,
                )
            except OSError as exc:
                raise ProductionConsumerError(
                    "adapter subprocess failed or timed out"
                ) from exc
        if (
            process.returncode != 0
            or not stdout
            or len(stdout) > self._max_output
            or len(stderr) > self._max_output
        ):
            raise ProductionConsumerError("adapter subprocess returned an invalid frame")
        try:
            value = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionConsumerError("adapter subprocess output is not strict JSON") from exc
        if type(value) is not dict:
            raise ProductionConsumerError("adapter subprocess output must be one object")
        return value


def write_raw_ed25519_private_key(path: str | Path, key: Ed25519PrivateKey) -> None:
    """Write a synthetic adapter-owned key for tests; never a production KMS key."""

    selected = Path(path)
    if selected.exists():
        raise ProductionConsumerError("refusing to overwrite adapter key")
    raw = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_verification_key(path: str | Path, key: Ed25519VerificationKey) -> None:
    selected = Path(path)
    if selected.exists():
        raise ProductionConsumerError("refusing to overwrite verification key")
    descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, _canonical_json_bytes(key.model_dump(mode="json")))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _build_result(
    token: ProviderDispatchToken,
    state: ConsumptionState,
    *,
    terminal_at: datetime,
    provider_receipt: ProviderResultReceipt | None = None,
    probe_receipt: ProviderProbeReceipt | None = None,
    action_receipt: ActionReceipt | None = None,
) -> ProductionConsumptionResult:
    values = {
        "request_sha256": token.request_sha256,
        "dispatch_payload_sha256": token.payload_sha256,
        "epoch": token.epoch,
        "fencing_token": token.fencing_token,
        "state": state,
        "provider_receipt": provider_receipt,
        "probe_receipt": probe_receipt,
        "action_receipt": action_receipt,
        "terminal_at": terminal_at,
    }
    provisional = ProductionConsumptionResult.model_construct(
        **values, result_sha256="0" * 64
    )
    return ProductionConsumptionResult(
        **values, result_sha256=hash_production_result(provisional)
    )


def _build_signed_model(
    model_type: type[StrictModel],
    values: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    issuer: str,
    role: SigningRole,
) -> Any:
    key = create_verification_key(private_key.public_key(), issuer=issuer, role=role)
    unsigned = dict(values)
    unsigned.setdefault("schema_version", "1.0")
    unsigned["key_id_sha256"] = key.key_id_sha256
    payload_sha = _canonical_sha256(unsigned)
    signed_values = {**unsigned, "payload_sha256": payload_sha}
    signature = private_key.sign(_canonical_json_bytes(signed_values))
    return model_type(
        **signed_values,
        signature_base64url=_encode_base64url(signature),
    )


def _validate_signed_hash(model: StrictModel, label: str) -> None:
    expected = _hash_without(model, {"payload_sha256", "signature_base64url"})
    if getattr(model, "payload_sha256", None) != expected:
        raise ValueError(f"{label} payload hash mismatch")


def _verify_signed(model: StrictModel, key: Ed25519VerificationKey) -> bool:
    try:
        if (
            getattr(model, "issuer") != key.issuer
            or getattr(model, "key_id_sha256") != key.key_id_sha256
            or getattr(model, "signer_role") is not key.role
        ):
            return False
        signature = _decode_base64url(getattr(model, "signature_base64url"), 64)
        message = _canonical_json_bytes(
            model.model_dump(mode="json", exclude={"signature_base64url"})
        )
        key.public_key().verify(signature, message)
    except (AttributeError, TypeError, ValueError, InvalidSignature):
        return False
    return True


def _private_key_matches(
    private_key: Ed25519PrivateKey, public_verifier: Ed25519VerificationKey
) -> bool:
    if not isinstance(private_key, Ed25519PrivateKey):
        return False
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    expected = public_verifier.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return hmac.compare_digest(raw, expected)


def _invoke_authority_callback(
    callback: Callable[[Any], Any],
    request: StrictModel,
    model_type: type[StrictModel],
    *,
    timeout_seconds: int,
    label: str,
) -> Any:
    """Run an authority service behind a strict, daemonized deadline."""

    output: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, callback(request)), block=False)
        except BaseException as exc:
            try:
                output.put((False, exc), block=False)
            except BaseException:
                pass

    Thread(
        target=invoke,
        name=f"{label.replace(' ', '-')}-{os.urandom(6).hex()}",
        daemon=True,
    ).start()
    try:
        succeeded, value = output.get(timeout=timeout_seconds)
    except Empty as exc:
        raise ProductionConsumerError(f"{label} timed out") from exc
    if not succeeded:
        raise ProductionConsumerError(f"{label} failed") from (
            value if isinstance(value, BaseException) else None
        )
    try:
        return model_type.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProductionConsumerError(f"{label} returned an invalid artifact") from exc


def _invoke_bounded_operation(
    callback: Callable[..., Any],
    *args: Any,
    timeout_seconds: int,
    label: str,
) -> Any:
    """Bound filesystem-anchor service calls so an outage cannot deadlock STOP."""

    output: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, callback(*args)), block=False)
        except BaseException as exc:
            try:
                output.put((False, exc), block=False)
            except BaseException:
                pass

    Thread(
        target=invoke,
        name=f"{label.replace(' ', '-')}-{os.urandom(6).hex()}",
        daemon=True,
    ).start()
    try:
        succeeded, value = output.get(timeout=timeout_seconds)
    except Empty as exc:
        raise ProductionConsumerError(f"{label} timed out") from exc
    if not succeeded:
        raise ProductionConsumerError(f"{label} failed") from (
            value if isinstance(value, BaseException) else None
        )
    return value


def _validate_state_key(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        raise ValueError("state authentication key must be at least 32 bytes")
    return bytes(value)


def _hash_without(model: StrictModel, excluded: set[str]) -> str:
    return _canonical_sha256(model.model_dump(mode="python", exclude=excluded))


def _canonical_model_json(model: StrictModel) -> str:
    return _canonical_json_bytes(model.model_dump(mode="python")).decode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    if isinstance(value, StrictModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetime must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical decimal must be finite")
        return format(value, "f")
    return value


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str, expected_length: int) -> bytes:
    if not isinstance(value, str):
        raise TypeError("base64url value must be a string")
    padding = "=" * ((4 - len(value) % 4) % 4)
    decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    if len(decoded) != expected_length:
        raise ValueError("base64url value has the wrong length")
    return decoded


class _GlobalStopStoreOperations:

    def claim(
        self,
        request: ProductionConsumptionRequest,
        runtime: ProductionConsumerRuntime,
        dispatcher_private_key: Ed25519PrivateKey,
        *,
        at: datetime,
    ) -> ProviderDispatchToken | ProductionConsumptionResult:
        _require_utc(at, "production claim time")
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                if (
                    runtime.policy_sha256 != self._policy_sha
                    or runtime.policy.store_id_sha256 != self._store_id
                ):
                    raise ProductionConsumerError(
                        "claim runtime/store policy mismatch"
                    )
                at, clock, roots, authority_updates = self._require_authority(
                    connection,
                    meta,
                    runtime,
                    subject_sha256=request.request_sha256,
                    purpose=ProductionClockPurpose.CLAIM,
                    require_current_roots=(
                        request.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    ),
                )
                existing = connection.execute(
                    "SELECT request_json, token_json, result_json FROM production_dispatches "
                    "WHERE request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                if existing is not None:
                    if existing["request_json"] != _canonical_model_json(request):
                        raise ProductionConsumerError("request hash collision or conflict")
                    if existing["result_json"] is not None:
                        connection.rollback()
                        return ProductionConsumptionResult.model_validate_json(
                            existing["result_json"]
                        )
                    raise ProductionConsumerError(
                        "production request is already in progress"
                    )
                conflict = connection.execute(
                    "SELECT request_sha256 FROM production_dispatches "
                    "WHERE idempotency_key_sha256=?",
                    (request.external_request.idempotency_key_sha256,),
                ).fetchone()
                if conflict is not None:
                    raise ProductionConsumerError("conflicting idempotency reuse")
                if self._has_inflight(connection):
                    raise ProductionConsumerError(
                        "another production request is already in progress"
                    )
                if (
                    request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    and meta["stopped"] == "1"
                ):
                    raise ProductionConsumerError("global STOP blocks activation")
                if not runtime.verifies(request, at=at):
                    raise ProductionConsumerError("production authority verification failed")
                execution_boundary_expiry = (
                    runtime.execution_boundary_expires_at(request, at=at)
                    if request.operation
                    is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    else None
                )
                if (
                    request.operation
                    is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    and execution_boundary_expiry is None
                ):
                    raise ProductionConsumerError(
                        "P16/P18 execution boundary is unavailable"
                    )
                if not self._acquire_inflight_owner():
                    raise ProductionConsumerError(
                        "another process owns the production request"
                    )
                expires_at = min(
                    request.expires_at,
                    at + timedelta(seconds=runtime.policy.maximum_dispatch_ttl_seconds),
                    *(
                        (
                            runtime.integration_authorization.expires_at,
                            runtime.integration_report.expires_at,
                            execution_boundary_expiry,
                        )
                        if request.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                        else ()
                    ),
                )
                token = _build_signed_model(
                    ProviderDispatchToken,
                    {
                        "schema_version": "4.0",
                        "issuer": runtime.trust.dispatcher.issuer,
                        "signer_role": SigningRole.EXECUTOR,
                        "scope": ProductionSignatureScope.PROVIDER_DISPATCH,
                        "store_id_sha256": self._store_id,
                        "policy_sha256": self._policy_sha,
                        "request_sha256": request.request_sha256,
                        "p11_claim_sha256": request.execution_claim.claim_sha256,
                        "production_integration_plan_sha256":
                            request.production_integration_plan_sha256,
                        "production_readiness_authorization_sha256":
                            request.production_readiness_authorization_sha256,
                        "repository_acceptance_authority_pins_sha256":
                            request.repository_acceptance_authority_pins_sha256,
                        "launch_handoff_authority_sha256":
                            request.launch_handoff_authority_sha256,
                        "launch_handoff_plan_sha256":
                            request.launch_handoff_plan_sha256,
                        "launch_handoff_bundle_sha256":
                            request.launch_handoff_bundle_sha256,
                        "launch_semantic_authority_sha256":
                            request.launch_semantic_authority_sha256,
                        "launch_semantic_packet_sha256":
                            request.launch_semantic_packet_sha256,
                        "epoch": int(meta["epoch"]),
                        "fencing_token": int(meta["revision"]) + 1,
                        "operation": request.operation,
                        "adapter_id": request.adapter_id,
                        "adapter_executable_sha256": request.adapter_executable_sha256,
                        "probe_executable_sha256": request.probe_executable_sha256,
                        "python_executable_sha256": request.python_executable_sha256,
                        "adapter_dependency_closure_sha256":
                            request.adapter_dependency_closure_sha256,
                        "provider_allowlist_sha256": request.provider_allowlist_sha256,
                        "postcondition_schema_sha256": request.postcondition_schema_sha256,
                        "target_sha256": request.external_request.target_sha256,
                        "idempotency_key_sha256": request.external_request.idempotency_key_sha256,
                        "expected_pre_state_sha256": request.external_request.expected_pre_state_sha256,
                        "expected_post_state_sha256": request.external_request.expected_post_state_sha256,
                        "issued_at": at,
                        "expires_at": expires_at,
                    },
                    dispatcher_private_key,
                    issuer=runtime.trust.dispatcher.issuer,
                    role=SigningRole.EXECUTOR,
                )
                connection.execute(
                    "INSERT INTO production_dispatches "
                    "(request_sha256, request_id, idempotency_key_sha256, epoch, "
                    "fencing_token, request_json, token_json, state, result_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        request.request_sha256,
                        request.request_id,
                        request.external_request.idempotency_key_sha256,
                        token.epoch,
                        token.fencing_token,
                        _canonical_model_json(request),
                        _canonical_model_json(token),
                        ConsumptionState.CLAIMED.value,
                    ),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "claim",
                        "request_sha256": request.request_sha256,
                        "token_payload_sha256": token.payload_sha256,
                        "epoch": token.epoch,
                        "fencing_token": token.fencing_token,
                        **self._authority_event(clock, roots),
                    },
                    updates=authority_updates,
                )
                return token
            except Exception:
                connection.rollback()
                if not self._has_inflight(connection):
                    self._release_inflight_owner()
                raise

    def redeem(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        *,
        at: datetime,
    ) -> ProductionConsumptionResult | None:
        _require_utc(at, "dispatch redemption time")
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                if (
                    runtime.policy_sha256 != self._policy_sha
                    or runtime.policy.store_id_sha256 != self._store_id
                ):
                    raise ProductionConsumerError(
                        "redemption runtime/store policy mismatch"
                    )
                at, clock, roots, authority_updates = self._require_authority(
                    connection,
                    meta,
                    runtime,
                    subject_sha256=request.request_sha256,
                    purpose=ProductionClockPurpose.REDEEM,
                    require_current_roots=(
                        request.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    ),
                )
                row = connection.execute(
                    "SELECT request_json, token_json, state, result_json "
                    "FROM production_dispatches WHERE request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                authoritative = (
                    row is not None
                    and row["request_json"] == _canonical_model_json(request)
                    and ProviderDispatchToken.model_validate_json(row["token_json"])
                    == token
                )
                if not authoritative:
                    raise ProductionConsumerError("dispatch token is stale or invalid")
                if row["result_json"] is not None:
                    connection.rollback()
                    return ProductionConsumptionResult.model_validate_json(
                        row["result_json"]
                    )
                if not self._owns_inflight():
                    raise ProductionConsumerError(
                        "dispatch redemption is not owned by this process"
                    )
                if row["state"] != ConsumptionState.CLAIMED.value:
                    raise ProductionConsumerError("dispatch token is stale or invalid")
                valid = (
                    token.store_id_sha256 == self._store_id
                    and token.policy_sha256 == self._policy_sha
                    and token.epoch == int(meta["epoch"])
                    and token.fencing_token == int(meta["revision"])
                    and token.issued_at <= at < token.expires_at
                    and _verify_signed(token, runtime.trust.dispatcher)
                    and runtime.verifies(request, at=at)
                    and not (
                        request.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                        and meta["stopped"] == "1"
                    )
                )
                if not valid:
                    result = _build_result(
                        token,
                        ConsumptionState.UNKNOWN,
                        terminal_at=at,
                    )
                    reason = _canonical_sha256(
                        {
                            "reason": "authoritative-dispatch-redemption-failed",
                            "request_sha256": request.request_sha256,
                            "epoch": token.epoch,
                            "fencing_token": token.fencing_token,
                            "at": at,
                        }
                    )
                    connection.execute(
                        "UPDATE production_dispatches SET state='unknown', result_json=? "
                        "WHERE request_sha256=?",
                        (result.model_dump_json(), request.request_sha256),
                    )
                    self._advance(
                        connection,
                        meta,
                        event={
                            "kind": "redemption_failure_stop",
                            "request_sha256": request.request_sha256,
                            "result_sha256": result.result_sha256,
                            "at": at,
                            **self._authority_event(clock, roots),
                        },
                        updates={
                            "stopped": "1",
                            "epoch": str(int(meta["epoch"]) + 1),
                            "stop_reason_sha256": reason,
                            "stopped_at": at.isoformat(),
                            **authority_updates,
                        },
                    )
                    self._release_inflight_owner()
                    return result
                connection.execute(
                    "UPDATE production_dispatches SET state='dispatched' WHERE request_sha256=?",
                    (request.request_sha256,),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "dispatch_redeemed",
                        "request_sha256": request.request_sha256,
                        "token_payload_sha256": token.payload_sha256,
                        "at": at,
                        **self._authority_event(clock, roots),
                    },
                    updates=authority_updates,
                )
            except Exception:
                connection.rollback()
                if not self._has_inflight(connection):
                    self._release_inflight_owner()
                raise

    def _invoke_and_record_provider(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        port: _SubprocessProviderExecutionPort,
        *,
        at: datetime,
    ) -> ProviderResultReceipt:
        """Invoke once and durably journal the verified provider fact.

        The cooperative store lock remains exclusive from the final authority
        check until the immutable receipt is committed.  A receipt is evidence
        only: it does not itself authorize a successful terminal result.
        """

        if (
            type(port) is not _SubprocessProviderExecutionPort
            or not port.validates(request, token, runtime)
        ):
            raise ProductionConsumerError(
                "exact subprocess provider execution port is required"
            )
        operation_deadline = time.monotonic() + port._timeout_seconds
        _require_utc(at, "provider result verification time")
        if (
            runtime.policy_sha256 != self._policy_sha
            or runtime.policy.store_id_sha256 != self._store_id
        ):
            raise ProductionConsumerError(
                "provider invocation runtime/store policy mismatch"
            )
        with self._lock, self._file_lock(), self._connect() as connection:
            meta = self._assert_integrity(connection)
            at, pre_clock, pre_roots, pre_authority_updates = self._require_authority(
                connection,
                meta,
                runtime,
                subject_sha256=request.request_sha256,
                purpose=ProductionClockPurpose.PRE_PROVIDER,
                require_current_roots=(
                    request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                ),
            )
            row = connection.execute(
                "SELECT d.request_json, d.token_json, d.state, d.result_json, "
                "p.receipt_json, a.receipt_json AS attempt_receipt_json, "
                "i.request_sha256 AS intent_request_sha256 "
                "FROM production_dispatches AS d "
                "LEFT JOIN production_provider_receipts AS p "
                "ON p.request_sha256=d.request_sha256 "
                "LEFT JOIN production_provider_attempts AS a "
                "ON a.request_sha256=d.request_sha256 "
                "LEFT JOIN production_provider_attempt_intents AS i "
                "ON i.request_sha256=d.request_sha256 "
                "WHERE d.request_sha256=?",
                (request.request_sha256,),
            ).fetchone()
            authoritative = (
                row is not None
                and row["request_json"] == _canonical_model_json(request)
                and ProviderDispatchToken.model_validate_json(row["token_json"])
                == token
            )
            if not authoritative or not self._owns_inflight():
                raise ProductionConsumerError(
                    "provider dispatch fence is stale or invalid"
                )
            if row["state"] == "provider_recorded":
                if row["result_json"] is not None or row["receipt_json"] is None:
                    raise ProductionConsumerError(
                        "provider journal state is inconsistent"
                    )
                return ProviderResultReceipt.model_validate_json(
                    row["receipt_json"]
                )
            if (
                row["intent_request_sha256"] is not None
                or row["attempt_receipt_json"] is not None
            ):
                raise ProductionConsumerError(
                    "provider attempt is already durable; replay is forbidden"
                )
            valid = (
                row["state"] == ConsumptionState.DISPATCHED.value
                and row["result_json"] is None
                and row["receipt_json"] is None
                and token.store_id_sha256 == self._store_id
                and token.policy_sha256 == self._policy_sha
                and token.epoch == int(meta["epoch"])
                and token.fencing_token + 1 == int(meta["revision"])
                and token.issued_at <= at < token.expires_at
                and at
                + timedelta(
                    seconds=runtime.policy.minimum_provider_authority_margin_seconds
                )
                <= token.expires_at
                and _verify_signed(token, runtime.trust.dispatcher)
                and runtime.verifies(request, at=at)
                and not (
                    request.operation
                    is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    and meta["stopped"] == "1"
                )
            )
            if not valid:
                raise ProductionConsumerError(
                    "provider dispatch fence is stale or invalid"
                )

            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                current = connection.execute(
                    "SELECT d.state, d.result_json, p.receipt_json, "
                    "a.receipt_json AS attempt_receipt_json, "
                    "i.request_sha256 AS intent_request_sha256 "
                    "FROM production_dispatches AS d "
                    "LEFT JOIN production_provider_receipts AS p "
                    "ON p.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempts AS a "
                    "ON a.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempt_intents AS i "
                    "ON i.request_sha256=d.request_sha256 "
                    "WHERE d.request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                if (
                    current is None
                    or current["state"] != ConsumptionState.DISPATCHED.value
                    or current["result_json"] is not None
                    or current["receipt_json"] is not None
                    or current["attempt_receipt_json"] is not None
                    or current["intent_request_sha256"] is not None
                    or token.epoch != int(meta["epoch"])
                    or token.fencing_token + 1 != int(meta["revision"])
                ):
                    raise ProductionConsumerError(
                        "provider authority changed before attempt intent"
                    )
                connection.execute(
                    "INSERT INTO production_provider_attempt_intents "
                    "(request_sha256, dispatch_payload_sha256, started_at, "
                    "clock_attestation_json, authority_roots_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        request.request_sha256,
                        token.payload_sha256,
                        at.isoformat(),
                        _canonical_model_json(pre_clock),
                        (
                            _canonical_model_json(pre_roots)
                            if pre_roots is not None
                            else None
                        ),
                    ),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "provider_attempt_intent_recorded",
                        "request_sha256": request.request_sha256,
                        "dispatch_payload_sha256": token.payload_sha256,
                        "at": at,
                        "pre_provider_authority": self._authority_event(
                            pre_clock, pre_roots
                        ),
                    },
                    updates=pre_authority_updates,
                )
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

            try:
                with runtime.external_guard.dispatch_fence(
                    request.external_request,
                    request.human_approval,
                    request.controller_grant,
                    request.execution_claim,
                    at=at,
                    not_after=token.expires_at,
                ):
                    permit = object()
                    with _PROVIDER_CAPABILITY_LOCK:
                        _PROVIDER_CAPABILITY_PERMITS[
                            self._provider_capability_seal
                        ] = permit
                    try:
                        capability = _issue_provider_invocation_capability(
                            self._provider_capability_seal,
                            permit,
                            token,
                            "execute",
                            at,
                        )
                    finally:
                        with _PROVIDER_CAPABILITY_LOCK:
                            _PROVIDER_CAPABILITY_PERMITS.pop(
                                self._provider_capability_seal, None
                            )
                    try:
                        receipt = ProviderResultReceipt.model_validate(
                            port.execute(
                                token,
                                capability,
                                absolute_deadline=operation_deadline,
                            ).model_dump(mode="python")
                        )
                    finally:
                        _revoke_provider_invocation_capability(capability)
                if not runtime.verifies_provider_result(
                    token, receipt, at=receipt.completed_at
                ):
                    raise ProductionConsumerError(
                        "provider invocation returned an unauthoritative receipt"
                    )
            except BaseException as exc:
                try:
                    self._close_uncertain_provider_attempt(
                        connection,
                        request,
                        token,
                        terminal_at=at,
                        clock=pre_clock,
                        roots=pre_roots,
                    )
                except BaseException as close_exc:
                    self._quarantine_provider_invocation_authority()
                    raise ProductionConsumerError(
                        "provider callback failed and UNKNOWN+STOP could not be committed"
                    ) from close_exc
                if isinstance(
                    exc, (ExternalActionInputError, ProductionConsumerError)
                ):
                    raise
                if isinstance(exc, (AttributeError, TypeError, ValueError)):
                    raise ProductionConsumerError(
                        "provider invocation returned an invalid receipt"
                    ) from exc
                raise

            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                current = connection.execute(
                    "SELECT d.state, d.result_json, p.receipt_json, "
                    "a.receipt_json AS attempt_receipt_json "
                    "FROM production_dispatches AS d "
                    "LEFT JOIN production_provider_receipts AS p "
                    "ON p.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempts AS a "
                    "ON a.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempt_intents AS i "
                    "ON i.request_sha256=d.request_sha256 "
                    "WHERE d.request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                if (
                    current is None
                    or current["state"] != ConsumptionState.DISPATCHED.value
                    or current["result_json"] is not None
                    or current["receipt_json"] is not None
                    or current["attempt_receipt_json"] is not None
                    or token.epoch != int(meta["epoch"])
                    or token.fencing_token + 2 != int(meta["revision"])
                ):
                    raise ProductionConsumerError(
                        "provider authority changed before attempt journaling"
                    )
                connection.execute(
                    "INSERT INTO production_provider_attempts "
                    "(request_sha256, dispatch_payload_sha256, "
                    "receipt_payload_sha256, receipt_json) VALUES (?, ?, ?, ?)",
                    (
                        request.request_sha256,
                        token.payload_sha256,
                        receipt.payload_sha256,
                        _canonical_model_json(receipt),
                    ),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "provider_attempt_recorded",
                        "request_sha256": request.request_sha256,
                        "dispatch_payload_sha256": token.payload_sha256,
                        "receipt_payload_sha256": receipt.payload_sha256,
                        "provider_audit_receipt_sha256": (
                            receipt.provider_audit_receipt_sha256
                        ),
                        "provider_completed_at": receipt.completed_at,
                        "pre_provider_authority": self._authority_event(
                            pre_clock, pre_roots
                        ),
                    },
                )
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

            meta = self._assert_integrity(connection)
            verification_at, post_clock, post_roots, authority_updates = (
                self._require_authority(
                    connection,
                    meta,
                    runtime,
                    subject_sha256=request.request_sha256,
                    purpose=ProductionClockPurpose.POST_PROVIDER,
                    require_current_roots=(
                        request.operation
                        is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    ),
                )
            )
            if not runtime.verifies_provider_result(
                token, receipt, at=verification_at
            ):
                raise ProductionConsumerError(
                    "provider invocation returned an unauthoritative receipt"
                )

            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                current = connection.execute(
                    "SELECT d.request_json, d.token_json, d.state, d.result_json, "
                    "p.receipt_json, a.receipt_json AS attempt_receipt_json "
                    "FROM production_dispatches AS d "
                    "LEFT JOIN production_provider_receipts AS p "
                    "ON p.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempts AS a "
                    "ON a.request_sha256=d.request_sha256 "
                    "WHERE d.request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                if (
                    current is None
                    or current["request_json"] != _canonical_model_json(request)
                    or ProviderDispatchToken.model_validate_json(
                        current["token_json"]
                    ) != token
                    or current["state"] != ConsumptionState.DISPATCHED.value
                    or current["result_json"] is not None
                    or current["receipt_json"] is not None
                    or current["attempt_receipt_json"]
                    != _canonical_model_json(receipt)
                    or token.epoch != int(meta["epoch"])
                    or token.fencing_token + 3 != int(meta["revision"])
                ):
                    raise ProductionConsumerError(
                        "provider authority changed before receipt journaling"
                    )
                connection.execute(
                    "INSERT INTO production_provider_receipts "
                    "(request_sha256, dispatch_payload_sha256, "
                    "receipt_payload_sha256, provider_audit_receipt_sha256, "
                    "receipt_json, verified_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        request.request_sha256,
                        token.payload_sha256,
                        receipt.payload_sha256,
                        receipt.provider_audit_receipt_sha256,
                        _canonical_model_json(receipt),
                        verification_at.isoformat(),
                    ),
                )
                connection.execute(
                    "UPDATE production_dispatches SET state='provider_recorded' "
                    "WHERE request_sha256=?",
                    (request.request_sha256,),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "provider_receipt_recorded",
                        "request_sha256": request.request_sha256,
                        "dispatch_payload_sha256": token.payload_sha256,
                        "receipt_payload_sha256": receipt.payload_sha256,
                        "provider_audit_receipt_sha256": (
                            receipt.provider_audit_receipt_sha256
                        ),
                        "verified_at": verification_at,
                        "pre_provider_authority": self._authority_event(
                            pre_clock, pre_roots
                        ),
                        "post_provider_authority": self._authority_event(
                            post_clock, post_roots
                        ),
                    },
                    updates=authority_updates,
                )
                return receipt
            except Exception:
                connection.rollback()
                raise

    def commit_result(
        self,
        request: ProductionConsumptionRequest,
        token: ProviderDispatchToken,
        runtime: ProductionConsumerRuntime,
        *,
        state: ConsumptionState,
        terminal_at: datetime,
        provider_receipt: ProviderResultReceipt | None = None,
        probe_receipt: ProviderProbeReceipt | None = None,
        action_receipt: ActionReceipt | None = None,
        stop_reason_sha256: str | None = None,
    ) -> ProductionConsumptionResult:
        _require_utc(terminal_at, "production result commit time")
        if state in {ConsumptionState.CLAIMED, ConsumptionState.DISPATCHED}:
            raise ProductionConsumerError("production result must be terminal")
        with self._lock, self._file_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection)
                if (
                    runtime.policy_sha256 != self._policy_sha
                    or runtime.policy.store_id_sha256 != self._store_id
                ):
                    raise ProductionConsumerError(
                        "terminal runtime/store policy mismatch"
                    )
                terminal_at, clock, roots, authority_updates = (
                    self._require_authority(
                        connection,
                        meta,
                        runtime,
                        subject_sha256=request.request_sha256,
                        purpose=ProductionClockPurpose.TERMINAL,
                        require_current_roots=(
                            request.operation
                            is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                        ),
                    )
                )
                row = connection.execute(
                    "SELECT d.token_json, d.state, d.result_json, p.receipt_json, "
                    "p.verified_at, a.receipt_json AS attempt_receipt_json, "
                    "i.request_sha256 AS intent_request_sha256 "
                    "FROM production_dispatches AS d "
                    "LEFT JOIN production_provider_receipts AS p "
                    "ON p.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempts AS a "
                    "ON a.request_sha256=d.request_sha256 "
                    "LEFT JOIN production_provider_attempt_intents AS i "
                    "ON i.request_sha256=d.request_sha256 "
                    "WHERE d.request_sha256=?",
                    (request.request_sha256,),
                ).fetchone()
                if row is None or ProviderDispatchToken.model_validate_json(row["token_json"]) != token:
                    raise ProductionConsumerError("production dispatch is not authoritative")
                journaled_provider = (
                    ProviderResultReceipt.model_validate_json(row["receipt_json"])
                    if row["receipt_json"] is not None
                    else None
                )
                attempted_provider = (
                    ProviderResultReceipt.model_validate_json(
                        row["attempt_receipt_json"]
                    )
                    if row["attempt_receipt_json"] is not None
                    else None
                )
                if journaled_provider is None:
                    if provider_receipt is not None and provider_receipt != attempted_provider:
                        raise ProductionConsumerError(
                            "provider receipt must be journaled before terminal commit"
                        )
                    effective_provider = attempted_provider
                else:
                    if (
                        provider_receipt is not None
                        and provider_receipt != journaled_provider
                    ):
                        raise ProductionConsumerError(
                            "provider receipt conflicts with immutable journal"
                        )
                    effective_provider = journaled_provider
                journal_verified_at = (
                    datetime.fromisoformat(row["verified_at"])
                    if row["verified_at"] is not None
                    else None
                )
                result = _build_result(
                    token,
                    state,
                    terminal_at=terminal_at,
                    provider_receipt=effective_provider,
                    probe_receipt=probe_receipt,
                    action_receipt=action_receipt,
                )
                if row["result_json"] is not None:
                    stored = ProductionConsumptionResult.model_validate_json(row["result_json"])
                    if stored != result:
                        raise ProductionConsumerError("terminal production result is immutable")
                    connection.rollback()
                    return stored
                if not self._owns_inflight():
                    raise ProductionConsumerError(
                        "terminal commit is not owned by this process"
                    )
                if row["state"] not in (
                    {"provider_recorded"}
                    if state is ConsumptionState.SUCCEEDED
                    else {
                        ConsumptionState.CLAIMED.value,
                        ConsumptionState.DISPATCHED.value,
                        "provider_recorded",
                    }
                ):
                    raise ProductionConsumerError("dispatch was not redeemed exactly once")
                if state is ConsumptionState.SUCCEEDED and journaled_provider is None:
                    raise ProductionConsumerError(
                        "successful provider receipt lacks post-authority verification"
                    )
                has_attempt_intent = row["intent_request_sha256"] is not None
                expected_revision = token.fencing_token + {
                    ConsumptionState.CLAIMED.value: 0,
                    ConsumptionState.DISPATCHED.value: (
                        3
                        if attempted_provider is not None
                        else 2 if has_attempt_intent else 1
                    ),
                    "provider_recorded": 4,
                }[row["state"]]
                authority_failure_stop = (
                    state is ConsumptionState.UNKNOWN
                    and attempted_provider is not None
                    and row["state"] == ConsumptionState.DISPATCHED.value
                    and meta["stopped"] == "1"
                    and token.epoch + 1 == int(meta["epoch"])
                )
                if authority_failure_stop:
                    expected_revision += 1
                if token.epoch != int(meta["epoch"]) and not authority_failure_stop:
                    raise ProductionConsumerError("old epoch result cannot commit")
                allowed_revisions = {expected_revision}
                if row["state"] == "provider_recorded":
                    # A one-shot probe authorization is itself a durable event.
                    # Failed probes therefore leave the same +1 fence as successful
                    # probes, while success must carry the corresponding receipt.
                    allowed_revisions.add(expected_revision + 1)
                    if state is ConsumptionState.SUCCEEDED:
                        allowed_revisions = {expected_revision + 1}
                if int(meta["revision"]) not in allowed_revisions:
                    raise ProductionConsumerError(
                        "terminal result phase fence is stale"
                    )
                if not runtime.verifies_terminal_result(
                    request,
                    token,
                    state=state,
                    terminal_at=terminal_at,
                    provider_receipt=effective_provider,
                    probe_receipt=probe_receipt,
                    action_receipt=action_receipt,
                ):
                    raise ProductionConsumerError(
                        "terminal receipts or authority are invalid"
                    )
                success = state is ConsumptionState.SUCCEEDED
                if success and (
                    journal_verified_at is None
                    or probe_receipt is None
                    or journal_verified_at > probe_receipt.probed_at
                ):
                    raise ProductionConsumerError(
                        "success probe predates provider journal"
                    )
                if success and (
                    request.operation is ProviderOperation.ACTIVATE_PUBLIC_RELEASE
                    and meta["stopped"] == "1"
                ):
                    raise ProductionConsumerError("STOP wins over provider success")
                updates: dict[str, str] = dict(authority_updates)
                if not success:
                    reason = stop_reason_sha256 or _canonical_sha256(
                        {"state": state, "request_sha256": request.request_sha256}
                    )
                    updates = {
                        **updates,
                        "stopped": "1",
                        "epoch": str(int(meta["epoch"]) + 1),
                        "stop_reason_sha256": reason,
                        "stopped_at": terminal_at.isoformat(),
                    }
                connection.execute(
                    "UPDATE production_dispatches SET state=?, result_json=? "
                    "WHERE request_sha256=?",
                    (state.value, result.model_dump_json(), request.request_sha256),
                )
                self._advance(
                    connection,
                    meta,
                    event={
                        "kind": "terminal_result",
                        "request_sha256": request.request_sha256,
                        "state": state,
                        "result_sha256": result.result_sha256,
                        "at": terminal_at,
                        **self._authority_event(clock, roots),
                    },
                    updates=updates,
                )
                self._release_inflight_owner()
                return result
            except Exception:
                connection.rollback()
                if not self._has_inflight(connection):
                    self._release_inflight_owner()
                raise
