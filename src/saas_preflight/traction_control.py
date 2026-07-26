"""Credential-free P17 traction and scale-review control.

The module consumes a complete P12 authority packet at ingestion, derives a
minimal signed 30-day observation, and evaluates only non-authoritative Human
review recommendations.  It performs no network, publication, spend, affiliate
or production mutation.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import queue
import sqlite3
import stat
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock, Thread, current_thread
from typing import Any, Literal, Protocol, Self
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from pydantic import Field, field_validator, model_validator

from .control_cycle import (
    Ed25519VerificationKey,
    SigningRole,
    create_verification_key,
)
from .economics import calculate_demand
from .measurement_integrity import (
    AcquisitionClass,
    CohortIntegrityBatch,
    DemandIntegrityBatch,
    MeasurementAuthorityPins,
    MeasurementBundleIndex,
    MeasurementIntegrityReport,
    MeasurementIntegrityRuntime,
    MeasurementPolicy,
    MeasurementTrustStore,
    OperationsIntegrityBatch,
    ProducerAttestation,
    SignedMeasurementRunPlan,
    TransactionStatus,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    verify_measurement_integrity_report,
)
from .models import Sha256, Slug, StrictModel
from .operations_activity import (
    DerivedOperationsActivitySummary,
    OperationalCostPolicy,
    OperationsActivityBatch,
    derive_operations_activity,
    hash_operational_cost_policy,
    hash_operations_activity_batch,
)
from .settlement_amendment import (
    OriginalSettlementBinding,
    SettlementAmendmentAuthorityPins,
    SettlementAmendmentPolicy,
    SettlementAmendmentTrustStore,
    SettlementCompletenessAttestation,
    SignedSettlementAmendment,
    evaluate_settlement_amendments,
    hash_settlement_policy,
    hash_settlement_trust_store,
)


_TOKYO = ZoneInfo("Asia/Tokyo")
_ZERO_SHA256 = "0" * 64
_CLOCK_WORKERS: dict[str, Thread] = {}
_FORK_CLEANUP_FDS: dict[int, list[int | None]] = {}
_CLOCK_WORKERS_LOCK = RLock()
_STORE_COORDINATION_TIMEOUT_SECONDS = 5
_STORE_LOCK_POLL_SECONDS = 0.01


def _prepare_clock_fork() -> None:
    _CLOCK_WORKERS_LOCK.acquire()


def _finish_clock_fork_in_parent() -> None:
    _CLOCK_WORKERS_LOCK.release()


def _clear_inherited_clock_workers() -> None:
    """Drop fork-child FD copies without unlocking the parent's descriptions."""

    global _CLOCK_WORKERS, _FORK_CLEANUP_FDS, _CLOCK_WORKERS_LOCK
    for descriptor, owner in tuple(_FORK_CLEANUP_FDS.items()):
        owner[0] = None
        try:
            os.close(descriptor)
        except OSError:
            pass
    _CLOCK_WORKERS = {}
    _FORK_CLEANUP_FDS = {}
    _CLOCK_WORKERS_LOCK = RLock()


def _track_fork_descriptor(descriptor: int) -> list[int | None]:
    owner: list[int | None] | None = None
    try:
        owner = [descriptor]
        _FORK_CLEANUP_FDS[descriptor] = owner
        return owner
    except BaseException:
        # os.open() already succeeded.  Registration is therefore part of the
        # resource-acquisition boundary and must not leave an untracked FD if
        # owner allocation or dict growth fails (for example, MemoryError).
        if owner is not None:
            owner[0] = None
            try:
                if _FORK_CLEANUP_FDS.get(descriptor) is owner:
                    _FORK_CLEANUP_FDS.pop(descriptor, None)
            except BaseException:
                pass
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _release_fork_descriptor(
    owner: list[int | None], *, unlock: bool
) -> None:
    with _CLOCK_WORKERS_LOCK:
        descriptor = owner[0]
        if descriptor is None:
            return
        owner[0] = None
        if _FORK_CLEANUP_FDS.get(descriptor) is owner:
            _FORK_CLEANUP_FDS.pop(descriptor, None)
        if unlock:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(descriptor)
        except OSError:
            pass


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_prepare_clock_fork,
        after_in_parent=_finish_clock_fork_in_parent,
        after_in_child=_clear_inherited_clock_workers,
    )


class TractionInputError(ValueError):
    """A P17 input is incomplete, conflicting, stale, or non-authoritative."""


def _bounded_store_callback(
    callback: Callable[..., Any],
    *args: object,
    label: str,
    coordination_path: Path,
) -> Any:
    """Run an external store callback without granting it an unlimited wait."""

    output: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
    with _CLOCK_WORKERS_LOCK:
        descriptor = os.open(
            coordination_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        descriptor_owner = _track_fork_descriptor(descriptor)
    deadline = time.monotonic() + _STORE_COORDINATION_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError as error:
            if time.monotonic() >= deadline:
                _release_fork_descriptor(descriptor_owner, unlock=False)
                raise TractionInputError(
                    "traction anchor coordination lock timed out"
                ) from error
            time.sleep(_STORE_LOCK_POLL_SECONDS)

    def invoke() -> None:
        try:
            output.put((True, callback(*args)), block=False)
        except BaseException as error:
            try:
                output.put((False, error), block=False)
            except BaseException:
                pass
        finally:
            _release_fork_descriptor(descriptor_owner, unlock=True)

    worker = threading.Thread(
        target=invoke,
        name=f"saas-preflight-{label}",
        daemon=True,
    )
    try:
        worker.start()
    except BaseException:
        _release_fork_descriptor(descriptor_owner, unlock=True)
        raise
    try:
        succeeded, value = output.get(
            timeout=_STORE_COORDINATION_TIMEOUT_SECONDS
        )
    except queue.Empty as error:
        raise TractionInputError(f"{label} timed out") from error
    if not succeeded:
        if isinstance(value, BaseException):
            raise TractionInputError(f"{label} failed") from value
        raise TractionInputError(f"{label} failed")
    return value


class TractionDecision(str, Enum):
    STOP = "stop"
    CONTINUE_OBSERVATION = "continue_observation"
    READY_FOR_SCALE_REVIEW = "ready_for_scale_review"


class TractionFinalizationOutcome(str, Enum):
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class TractionProvenance(str, Enum):
    VERIFIED_P12 = "verified_p12"
    SYNTHETIC_CONTRACT = "synthetic_contract"


class TractionCheckStatus(str, Enum):
    PASS = "pass"
    WAIT = "wait"
    FAIL = "fail"


class TractionClockPurpose(str, Enum):
    APPEND_OBSERVATION = "append_observation"
    APPEND_SETTLEMENT = "append_settlement"
    EVALUATE = "evaluate"
    FINALIZE_EVENT = "finalize_event"


class TractionTrustStore(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_human: Ed25519VerificationKey
    observation_tco_qa: Ed25519VerificationKey
    clock_auditor: Ed25519VerificationKey

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        if (
            self.plan_human.role is not SigningRole.HUMAN_APPROVER
            or self.observation_tco_qa.role is not SigningRole.TCO_QA
            or self.clock_auditor.role is not SigningRole.TIME_AUDITOR
            or len(
                {
                    self.plan_human.key_id_sha256,
                    self.observation_tco_qa.key_id_sha256,
                    self.clock_auditor.key_id_sha256,
                }
            )
            != 3
        ):
            raise ValueError("traction signing roles must be exact and distinct")
        return self


class TractionPolicy(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    trust_store_sha256: Sha256
    ledger_store_id_sha256: Sha256
    p12_policy_sha256: Sha256
    p12_trust_store_sha256: Sha256
    settlement_policy_sha256: Sha256
    settlement_trust_store_sha256: Sha256
    identity_hmac_key_id_sha256: Sha256
    objective_basis: Literal["net_operating_profit"] = "net_operating_profit"
    target_monthly_net_profit: Decimal = Field(default=Decimal("200000"), ge=0)
    minimum_settled_epc: Decimal = Field(default=Decimal("60"), ge=0)
    maturity_valid_clicks: Literal[1000] = 1000
    maturity_days: Literal[180] = 180
    observation_days: Literal[30] = 30
    settlement_lag_days: Literal[30] = 30
    minimum_partner_count: Literal[3] = 3
    maximum_partner_revenue_share: Decimal = Field(default=Decimal("0.40"), ge=0, le=1)
    minimum_outbound_ctr: Decimal = Field(default=Decimal("0.10"), ge=0, le=1)
    minimum_automation_rate: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    maximum_human_minutes: Literal[720] = 720
    minimum_job_success_rate: Decimal = Field(default=Decimal("0.99"), ge=0, le=1)
    maximum_major_misstatements: Literal[0] = 0
    maximum_exceptions: Literal[24] = 24
    required_fault_count: Literal[8] = 8
    maximum_plan_ttl_seconds: int = Field(ge=15552000, le=34560000)
    maximum_observation_ttl_seconds: int = Field(ge=1, le=2678400)
    clock_response_timeout_seconds: int = Field(default=5, ge=1, le=30)
    empty_ledger_action: Literal[TractionDecision.STOP] = TractionDecision.STOP

    @model_validator(mode="after")
    def freeze_economic_thresholds(self) -> Self:
        expected = {
            "target_monthly_net_profit": Decimal("200000"),
            "minimum_settled_epc": Decimal("60"),
            "maximum_partner_revenue_share": Decimal("0.40"),
            "minimum_outbound_ctr": Decimal("0.10"),
            "minimum_automation_rate": Decimal("0.80"),
            "minimum_job_success_rate": Decimal("0.99"),
        }
        if any(getattr(self, name) != value for name, value in expected.items()):
            raise ValueError("traction economic thresholds are fixed")
        return self


class TractionAuthorityPins(StrictModel):
    """Consumer-owned pins; never derive them from the supplied bundle."""

    schema_version: Literal["1.0"] = "1.0"
    expected_policy_sha256: Sha256
    expected_trust_store_sha256: Sha256
    expected_plan_sha256: Sha256
    expected_ledger_store_id_sha256: Sha256
    expected_property_record_sha256: Sha256
    expected_property_domain_sha256: Sha256
    expected_release_sha256: Sha256
    expected_artifact_sha256: Sha256
    expected_schema_sha256: Sha256
    expected_partner_set_sha256: Sha256
    expected_p12_policy_sha256: Sha256
    expected_p12_trust_store_sha256: Sha256
    expected_settlement_policy_sha256: Sha256
    expected_settlement_trust_store_sha256: Sha256


class SignedTractionPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.HUMAN_APPROVER]
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    ledger_store_id_sha256: Sha256
    property_record_sha256: Sha256
    property_domain_sha256: Sha256
    measured_release_sha256: Sha256
    measured_artifact_sha256: Sha256
    measured_schema_sha256: Sha256
    partner_ids: tuple[Slug, ...] = Field(min_length=3)
    partner_set_sha256: Sha256
    rights_evidence_sha256: Sha256
    rights_expires_at: datetime
    affiliate_evidence_sha256: Sha256
    affiliate_expires_at: datetime
    p12_policy_sha256: Sha256
    p12_trust_store_sha256: Sha256
    settlement_policy_sha256: Sha256
    settlement_trust_store_sha256: Sha256
    experiment_started_at: datetime
    experiment_ended_at: datetime
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator(
        "rights_expires_at",
        "affiliate_expires_at",
        "experiment_started_at",
        "experiment_ended_at",
        "issued_at",
        "expires_at",
    )
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return _aware(value, "traction plan timestamp")

    @field_validator("partner_ids")
    @classmethod
    def canonical_partners(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("traction plan partner IDs must be distinct")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.partner_set_sha256 != _canonical_sha256(self.partner_ids):
            raise ValueError("traction partner-set hash mismatch")
        if not (
            self.issued_at <= self.experiment_started_at
            and self.issued_at < self.expires_at
            and self.experiment_started_at < self.experiment_ended_at
            and self.experiment_ended_at - self.experiment_started_at
            == timedelta(days=180)
            and self.experiment_started_at.astimezone(_TOKYO).time().isoformat()
            == "00:00:00"
            and self.experiment_ended_at.astimezone(_TOKYO).time().isoformat()
            == "00:00:00"
            and self.expires_at
            >= self.experiment_ended_at + timedelta(days=30)
            and self.expires_at <= self.rights_expires_at
            and self.expires_at <= self.affiliate_expires_at
        ):
            raise ValueError("invalid traction plan time boundary")
        _validate_payload_hash(self)
        return self


class P12AuthorityPacket(StrictModel):
    """The complete P12 packet required for a fresh ingestion-time rerun."""

    schema_version: Literal["1.0"] = "1.0"
    policy: MeasurementPolicy
    trust_store: MeasurementTrustStore
    authority_pins: MeasurementAuthorityPins
    plan: SignedMeasurementRunPlan
    demand_batch: DemandIntegrityBatch
    cohort_batch: CohortIntegrityBatch
    operations_batch: OperationsIntegrityBatch
    demand_attestation: ProducerAttestation
    cohort_attestation: ProducerAttestation
    operations_attestation: ProducerAttestation
    bundle_index: MeasurementBundleIndex
    report: MeasurementIntegrityReport


class PartnerTractionFacts(StrictModel):
    partner_id: Slug
    settled_amount: Decimal = Field(ge=0, max_digits=30, decimal_places=8)


class TractionObservation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TCO_QA]
    provenance: TractionProvenance
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    plan_sha256: Sha256
    ledger_store_id_sha256: Sha256
    ordinal: int = Field(ge=1, le=6)
    predecessor_sha256: Sha256
    run_id: Slug
    cohort_id: Slug
    p12_report_sha256: Sha256
    p12_plan_sha256: Sha256
    p12_bundle_index_sha256: Sha256
    p12_demand_batch_sha256: Sha256
    p12_cohort_batch_sha256: Sha256
    p12_operations_batch_sha256: Sha256
    p12_demand_attestation_sha256: Sha256
    p12_cohort_attestation_sha256: Sha256
    p12_operations_attestation_sha256: Sha256
    p12_policy_sha256: Sha256
    p12_trust_store_sha256: Sha256
    operations_activity_batch: OperationsActivityBatch
    operational_cost_policy: OperationalCostPolicy
    operations_activity: DerivedOperationsActivitySummary
    property_record_sha256: Sha256
    property_domain_sha256: Sha256
    measured_release_sha256: Sha256
    measured_artifact_sha256: Sha256
    measured_schema_sha256: Sha256
    partner_set_sha256: Sha256
    observation_started_at: datetime
    observation_ended_at: datetime
    ingested_at: datetime
    qualified_sessions: int = Field(ge=0)
    valid_outbound_clicks: int = Field(ge=0)
    settled_amount_at_window_end: Decimal = Field(ge=0, max_digits=30, decimal_places=8)
    partner_facts: tuple[PartnerTractionFacts, ...] = Field(min_length=3)
    bear_qualified_sessions: Decimal = Field(ge=0)
    bear_outbound_click_rate: Decimal = Field(ge=0, le=1)
    human_minutes: int = Field(ge=0)
    routine_tasks_total: int = Field(ge=0)
    routine_tasks_automated: int = Field(ge=0)
    job_runs_total: int = Field(ge=0)
    job_runs_succeeded: int = Field(ge=0)
    major_misstatements: int = Field(ge=0)
    exceptions_total: int = Field(ge=0)
    exact_faults_passed: int = Field(ge=0, le=8)
    click_identity_tokens: tuple[Sha256, ...] = ()
    transaction_identity_tokens: tuple[Sha256, ...] = ()
    issued_at: datetime
    expires_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator(
        "observation_started_at",
        "observation_ended_at",
        "ingested_at",
        "issued_at",
        "expires_at",
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "traction observation timestamp")

    @field_validator("partner_facts")
    @classmethod
    def canonical_partner_facts(
        cls, values: tuple[PartnerTractionFacts, ...]
    ) -> tuple[PartnerTractionFacts, ...]:
        if len({item.partner_id for item in values}) != len(values):
            raise ValueError("traction partner rows must be distinct")
        return tuple(sorted(values, key=lambda item: item.partner_id))

    @field_validator("click_identity_tokens", "transaction_identity_tokens")
    @classmethod
    def canonical_tokens(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("traction identity tokens must be distinct")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if not (
            self.observation_started_at < self.observation_ended_at
            and self.observation_ended_at - self.observation_started_at
            == timedelta(days=30)
            and self.observation_started_at.astimezone(_TOKYO).time().isoformat()
            == "00:00:00"
            and self.observation_ended_at.astimezone(_TOKYO).time().isoformat()
            == "00:00:00"
            and self.observation_ended_at <= self.ingested_at
            and self.ingested_at == self.issued_at
            and self.issued_at < self.expires_at
            and self.routine_tasks_automated <= self.routine_tasks_total
            and self.job_runs_succeeded <= self.job_runs_total
            and len(self.click_identity_tokens) == self.valid_outbound_clicks
        ):
            raise ValueError("invalid traction observation boundary")
        if _canonical_sha256(tuple(row.partner_id for row in self.partner_facts)) != (
            self.partner_set_sha256
        ):
            raise ValueError("observation partner-set hash mismatch")
        if _exact_sum(row.settled_amount for row in self.partner_facts) != (
            self.settled_amount_at_window_end
        ):
            raise ValueError("observation partner revenue does not reconcile")
        try:
            derived = derive_operations_activity(
                self.operations_activity_batch,
                self.operational_cost_policy,
                gross_settled_revenue_jpy=self.settled_amount_at_window_end,
                at=self.ingested_at,
            )
        except ValueError as exc:
            raise ValueError("observation operations activity is invalid") from exc
        daily = derived.daily
        if (
            derived != self.operations_activity
            or self.operations_activity_batch.source_operations_batch_sha256
            != self.p12_operations_batch_sha256
            or hash_operations_activity_batch(self.operations_activity_batch)
            != self.operations_activity_batch.batch_sha256
            or hash_operational_cost_policy(self.operational_cost_policy)
            != self.operational_cost_policy.policy_sha256
            or derived.observation_started_at != self.observation_started_at
            or derived.observation_ended_at != self.observation_ended_at
            or self.human_minutes != sum(item.human_minutes for item in daily)
            or self.routine_tasks_total
            != sum(item.routine_tasks_total for item in daily)
            or self.routine_tasks_automated
            != sum(item.routine_tasks_automated for item in daily)
            or self.job_runs_total != sum(item.job_runs_total for item in daily)
            or self.job_runs_succeeded
            != sum(item.job_runs_succeeded for item in daily)
            or self.major_misstatements
            != sum(item.major_misstatements for item in daily)
            or self.exceptions_total != sum(item.exceptions_total for item in daily)
        ):
            raise ValueError("observation operations aggregates are not reconstructable")
        _validate_payload_hash(self)
        return self


class TractionSettlementEvidence(StrictModel):
    """One window's signed post-P12 settlement packet.

    Policy, trust and per-window authority pins are deliberately not accepted
    here; the consumer derives them from the signed traction scope.
    """

    schema_version: Literal["1.0"] = "1.0"
    observation_sha256: Sha256
    original_binding: OriginalSettlementBinding
    cohort_batch: CohortIntegrityBatch
    amendments: tuple[SignedSettlementAmendment, ...] = Field(min_length=1)
    completeness_attestations: tuple[SettlementCompletenessAttestation, ...] = (
        Field(min_length=1)
    )

    @field_validator("amendments")
    @classmethod
    def canonical_amendments(
        cls, values: tuple[SignedSettlementAmendment, ...]
    ) -> tuple[SignedSettlementAmendment, ...]:
        by_id: dict[str, SignedSettlementAmendment] = {}
        for item in values:
            prior = by_id.setdefault(item.amendment_id_sha256, item)
            if hash_signed_artifact(prior) != hash_signed_artifact(item):
                raise ValueError("conflicting settlement amendment identity")
        return tuple(by_id[key] for key in sorted(by_id))

    @field_validator("completeness_attestations")
    @classmethod
    def canonical_completeness(
        cls, values: tuple[SettlementCompletenessAttestation, ...]
    ) -> tuple[SettlementCompletenessAttestation, ...]:
        by_amendment: dict[str, SettlementCompletenessAttestation] = {}
        for item in values:
            prior = by_amendment.setdefault(item.amendment_sha256, item)
            if hash_signed_artifact(prior) != hash_signed_artifact(item):
                raise ValueError(
                    "multiple completeness attestations for one amendment"
                )
        return tuple(by_amendment[key] for key in sorted(by_amendment))

    @model_validator(mode="after")
    def require_exact_completeness_set(self) -> Self:
        amendment_hashes = {
            hash_signed_artifact(item) for item in self.amendments
        }
        completeness_hashes = {
            item.amendment_sha256 for item in self.completeness_attestations
        }
        if amendment_hashes != completeness_hashes:
            raise ValueError("settlement completeness set must match amendments")
        return self


class TractionClockRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    purpose: TractionClockPurpose
    ledger_store_id_sha256: Sha256
    plan_sha256: Sha256
    event_revision: int = Field(ge=0)
    event_head_sha256: Sha256
    subject_sha256: Sha256
    request_nonce_sha256: Sha256


class SignedTractionClockAttestation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    issuer: Slug
    key_id_sha256: Sha256
    signer_role: Literal[SigningRole.TIME_AUDITOR]
    request_sha256: Sha256
    observed_at: datetime
    payload_sha256: Sha256
    signature_base64url: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "traction trusted-clock timestamp")

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        _validate_payload_hash(self)
        return self


class TractionEvaluationBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    observations: tuple[TractionObservation, ...] = ()
    settlement_evidence: tuple[TractionSettlementEvidence, ...] = ()


class TractionCheck(StrictModel):
    name: Slug
    status: TractionCheckStatus
    observed: str = Field(min_length=1, max_length=160)
    requirement: str = Field(min_length=1, max_length=240)


class TractionReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    decision: TractionDecision
    authority: Literal["none"] = "none"
    purpose: Literal["human_scale_review_input_only"] = (
        "human_scale_review_input_only"
    )
    external_mutation_authorized: Literal[False] = False
    policy_sha256: Sha256
    trust_store_sha256: Sha256
    plan_sha256: Sha256
    ledger_store_id_sha256: Sha256
    evaluated_at: datetime
    observation_count: int = Field(ge=0, le=6)
    covered_days: int = Field(ge=0, le=180)
    cumulative_valid_clicks: int = Field(ge=0)
    cumulative_qualified_sessions: int = Field(ge=0)
    cumulative_settled_amount: Decimal = Field(ge=0)
    cumulative_settled_epc: Decimal | None
    traction_mature: bool
    ledger_authenticated: bool
    settlement_complete: bool
    latest_revenue: Decimal | None
    latest_operating_tco: Decimal | None
    latest_net_operating_profit: Decimal | None
    latest_outbound_ctr: Decimal | None
    latest_max_partner_share: Decimal | None
    latest_automation_rate: Decimal | None
    latest_job_success_rate: Decimal | None
    required_clicks_exact: Decimal | None
    required_qualified_sessions_exact: Decimal | None
    checks: tuple[TractionCheck, ...]
    observation_head_sha256: Sha256
    settlement_evidence_sha256s: tuple[Sha256, ...]
    ledger_event_revision: int = Field(ge=0)
    ledger_event_head_sha256: Sha256
    trusted_clock_attestation_sha256: Sha256
    report_sha256: Sha256

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "traction report timestamp")

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = _canonical_sha256(
            self.model_copy(update={"report_sha256": _ZERO_SHA256}).model_dump(
                mode="python"
            )
        )
        if self.report_sha256 != expected:
            raise ValueError("traction report hash mismatch")
        return self


def hash_traction_trust_store(value: TractionTrustStore) -> str:
    return _canonical_sha256(
        TractionTrustStore.model_validate(value.model_dump()).model_dump(mode="python")
    )


def hash_traction_policy(value: TractionPolicy) -> str:
    return _canonical_sha256(
        TractionPolicy.model_validate(value.model_dump()).model_dump(mode="python")
    )


def hash_traction_artifact(value: StrictModel) -> str:
    return _canonical_sha256(value.model_dump(mode="python"))


def sign_traction_clock_attestation(
    request: TractionClockRequest,
    trust_store: TractionTrustStore,
    signing_key: Ed25519PrivateKey,
    *,
    observed_at: datetime,
) -> SignedTractionClockAttestation:
    """Sign a ledger-state-bound time reading with the distinct time key."""

    _utc(observed_at, "traction trusted-clock timestamp")
    request = TractionClockRequest.model_validate(request.model_dump())
    trust_store = TractionTrustStore.model_validate(trust_store.model_dump())
    key = create_verification_key(
        signing_key.public_key(),
        issuer=trust_store.clock_auditor.issuer,
        role=SigningRole.TIME_AUDITOR,
    )
    if key != trust_store.clock_auditor:
        raise TractionInputError("traction trusted-clock signing key mismatch")
    return _sign_model(
        SignedTractionClockAttestation,
        {
            "issuer": key.issuer,
            "key_id_sha256": key.key_id_sha256,
            "signer_role": SigningRole.TIME_AUDITOR,
            "request_sha256": hash_traction_artifact(request),
            "observed_at": observed_at,
        },
        signing_key,
    )


def verify_traction_clock_attestation(
    attestation: SignedTractionClockAttestation,
    request: TractionClockRequest,
    trust_store: TractionTrustStore,
) -> bool:
    try:
        attestation = SignedTractionClockAttestation.model_validate(
            attestation.model_dump()
        )
        request = TractionClockRequest.model_validate(request.model_dump())
        trust_store = TractionTrustStore.model_validate(trust_store.model_dump())
        return (
            attestation.request_sha256 == hash_traction_artifact(request)
            and attestation.issuer == trust_store.clock_auditor.issuer
            and attestation.key_id_sha256
            == trust_store.clock_auditor.key_id_sha256
            and _verify_signature(attestation, trust_store.clock_auditor)
        )
    except (InvalidSignature, TypeError, ValueError):
        return False


def sign_traction_plan(
    *,
    policy: TractionPolicy,
    trust_store: TractionTrustStore,
    signing_key: Ed25519PrivateKey,
    issuer: str,
    property_record_sha256: str,
    property_domain_sha256: str,
    measured_release_sha256: str,
    measured_artifact_sha256: str,
    measured_schema_sha256: str,
    partner_ids: tuple[str, ...],
    rights_evidence_sha256: str,
    rights_expires_at: datetime,
    affiliate_evidence_sha256: str,
    affiliate_expires_at: datetime,
    experiment_started_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
) -> SignedTractionPlan:
    key = create_verification_key(
        signing_key.public_key(), issuer=issuer, role=SigningRole.HUMAN_APPROVER
    )
    if key != trust_store.plan_human:
        raise TractionInputError("traction plan signing key mismatch")
    values: dict[str, Any] = {
        "issuer": key.issuer,
        "key_id_sha256": key.key_id_sha256,
        "signer_role": SigningRole.HUMAN_APPROVER,
        "policy_sha256": hash_traction_policy(policy),
        "trust_store_sha256": hash_traction_trust_store(trust_store),
        "ledger_store_id_sha256": policy.ledger_store_id_sha256,
        "property_record_sha256": property_record_sha256,
        "property_domain_sha256": property_domain_sha256,
        "measured_release_sha256": measured_release_sha256,
        "measured_artifact_sha256": measured_artifact_sha256,
        "measured_schema_sha256": measured_schema_sha256,
        "partner_ids": tuple(sorted(partner_ids)),
        "partner_set_sha256": _canonical_sha256(tuple(sorted(partner_ids))),
        "rights_evidence_sha256": rights_evidence_sha256,
        "rights_expires_at": rights_expires_at,
        "affiliate_evidence_sha256": affiliate_evidence_sha256,
        "affiliate_expires_at": affiliate_expires_at,
        "p12_policy_sha256": policy.p12_policy_sha256,
        "p12_trust_store_sha256": policy.p12_trust_store_sha256,
        "settlement_policy_sha256": policy.settlement_policy_sha256,
        "settlement_trust_store_sha256": policy.settlement_trust_store_sha256,
        "experiment_started_at": experiment_started_at,
        "experiment_ended_at": experiment_started_at + timedelta(days=180),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    return _sign_model(SignedTractionPlan, values, signing_key)


def verify_traction_plan(
    plan: SignedTractionPlan,
    policy: TractionPolicy,
    trust_store: TractionTrustStore,
    authority_pins: TractionAuthorityPins,
    *,
    at: datetime,
) -> bool:
    try:
        _utc(at, "traction plan verification time")
        plan = SignedTractionPlan.model_validate(plan.model_dump())
        policy = TractionPolicy.model_validate(policy.model_dump())
        trust_store = TractionTrustStore.model_validate(trust_store.model_dump())
        pins = TractionAuthorityPins.model_validate(authority_pins.model_dump())
        return (
            pins.expected_policy_sha256 == hash_traction_policy(policy)
            and pins.expected_trust_store_sha256
            == hash_traction_trust_store(trust_store)
            and pins.expected_plan_sha256 == hash_traction_artifact(plan)
            and pins.expected_ledger_store_id_sha256
            == policy.ledger_store_id_sha256
            == plan.ledger_store_id_sha256
            and pins.expected_property_record_sha256
            == plan.property_record_sha256
            and pins.expected_property_domain_sha256
            == plan.property_domain_sha256
            and pins.expected_release_sha256 == plan.measured_release_sha256
            and pins.expected_artifact_sha256 == plan.measured_artifact_sha256
            and pins.expected_schema_sha256 == plan.measured_schema_sha256
            and pins.expected_partner_set_sha256 == plan.partner_set_sha256
            and pins.expected_p12_policy_sha256
            == policy.p12_policy_sha256
            == plan.p12_policy_sha256
            and pins.expected_p12_trust_store_sha256
            == policy.p12_trust_store_sha256
            == plan.p12_trust_store_sha256
            and pins.expected_settlement_policy_sha256
            == policy.settlement_policy_sha256
            == plan.settlement_policy_sha256
            and pins.expected_settlement_trust_store_sha256
            == policy.settlement_trust_store_sha256
            == plan.settlement_trust_store_sha256
            and policy.trust_store_sha256 == hash_traction_trust_store(trust_store)
            and plan.policy_sha256 == hash_traction_policy(policy)
            and plan.trust_store_sha256 == hash_traction_trust_store(trust_store)
            and plan.issuer == trust_store.plan_human.issuer
            and plan.key_id_sha256 == trust_store.plan_human.key_id_sha256
            and plan.issued_at <= at < plan.expires_at
            and at < plan.rights_expires_at
            and at < plan.affiliate_expires_at
            and plan.expires_at - plan.issued_at
            <= timedelta(seconds=policy.maximum_plan_ttl_seconds)
            and _verify_signature(plan, trust_store.plan_human)
        )
    except (InvalidSignature, TypeError, ValueError):
        return False


def build_traction_observation(
    packet: P12AuthorityPacket,
    runtime: MeasurementIntegrityRuntime,
    *,
    traction_plan: SignedTractionPlan,
    traction_policy: TractionPolicy,
    traction_trust_store: TractionTrustStore,
    authority_pins: TractionAuthorityPins,
    observation_signing_key: Ed25519PrivateKey,
    identity_hmac_key: bytes,
    operations_activity_batch: OperationsActivityBatch,
    operational_cost_policy: OperationalCostPolicy,
    ordinal: int,
    predecessor_sha256: str,
    at: datetime,
    provenance: TractionProvenance = TractionProvenance.VERIFIED_P12,
) -> TractionObservation:
    """Rerun P12 and derive a minimized signed P17 observation."""

    _utc(at, "traction ingestion time")
    if not verify_traction_plan(
        traction_plan,
        traction_policy,
        traction_trust_store,
        authority_pins,
        at=at,
    ):
        raise TractionInputError("traction plan verification failed")
    if type(runtime) is not MeasurementIntegrityRuntime:
        raise TypeError("runtime must be MeasurementIntegrityRuntime")
    packet = P12AuthorityPacket.model_validate(packet.model_dump())
    if (
        hashlib.sha256(identity_hmac_key).hexdigest()
        != traction_policy.identity_hmac_key_id_sha256
        or len(identity_hmac_key) < 32
    ):
        raise TractionInputError("identity HMAC key mismatch")
    if at != packet.report.issued_at:
        raise TractionInputError("P12 report must be freshly issued at ingestion")
    expected_report = runtime.evaluate(
        packet.plan,
        packet.demand_batch,
        packet.cohort_batch,
        packet.operations_batch,
        packet.demand_attestation,
        packet.cohort_attestation,
        packet.operations_attestation,
        packet.bundle_index,
        at=at,
    )
    if expected_report != packet.report:
        raise TractionInputError("fresh P12 rerun does not equal supplied report")
    if not verify_measurement_integrity_report(
        packet.report,
        packet.policy,
        packet.trust_store,
        packet.authority_pins,
        at=at,
    ):
        raise TractionInputError("P12 report authority verification failed")
    if (
        hash_measurement_policy(packet.policy) != traction_plan.p12_policy_sha256
        or hash_measurement_trust_store(packet.trust_store)
        != traction_plan.p12_trust_store_sha256
        or packet.report.property_record_sha256
        != traction_plan.property_record_sha256
        or packet.report.property_domain_sha256
        != traction_plan.property_domain_sha256
        or packet.report.partner_ids != traction_plan.partner_ids
        or packet.plan.definition.fault_target_release_sha256
        != traction_plan.measured_release_sha256
        or packet.plan.definition.fault_target_artifact_sha256
        != traction_plan.measured_artifact_sha256
        or packet.plan.definition.fault_target_schema_sha256
        != traction_plan.measured_schema_sha256
        or packet.report.observation_started_at
        != traction_plan.experiment_started_at + timedelta(days=30 * (ordinal - 1))
        or packet.report.observation_ended_at
        != traction_plan.experiment_started_at + timedelta(days=30 * ordinal)
        or packet.report.observation_ended_at > traction_plan.experiment_ended_at
        or packet.authority_pins.expected_policy_sha256
        != hash_measurement_policy(packet.policy)
        or packet.authority_pins.expected_trust_store_sha256
        != hash_measurement_trust_store(packet.trust_store)
    ):
        raise TractionInputError("P12 packet is outside the frozen traction scope")
    cohort = packet.cohort_batch
    operations = packet.operations_batch
    reversed_ids = {item.transaction_id_sha256 for item in cohort.payout_adjustments}
    settled_by_partner = {partner: Decimal(0) for partner in cohort.partner_ids}
    eligible_transactions = []
    for transaction in cohort.transactions:
        if (
            transaction.acquisition_class is AcquisitionClass.NEW
            and transaction.current_status
            in (TransactionStatus.CONFIRMED, TransactionStatus.PAID)
            and transaction.transaction_id_sha256 not in reversed_ids
        ):
            settled_by_partner[transaction.partner_id] = _exact_sum(
                (settled_by_partner[transaction.partner_id], transaction.amount)
            )
            eligible_transactions.append(transaction)
    settled = _exact_sum(settled_by_partner.values())
    if settled != packet.report.reconciliation.settled_new_acquisition_amount:
        raise TractionInputError("derived partner settlement does not match P12")
    daily = operations.summary.daily_summaries
    activity = derive_operations_activity(
        operations_activity_batch,
        operational_cost_policy,
        gross_settled_revenue_jpy=settled,
        at=at,
    )
    if (
        activity.source_operations_batch_sha256 != hash_signed_artifact(operations)
        or activity.observation_started_at != packet.report.observation_started_at
        or activity.observation_ended_at != packet.report.observation_ended_at
        or tuple(
            (
                item.local_date,
                item.human_minutes,
                item.routine_tasks_total,
                item.routine_tasks_automated,
                item.job_runs_total,
                item.job_runs_succeeded,
                item.exceptions_total,
                item.major_misstatements,
            )
            for item in activity.daily
        )
        != tuple(
            (
                item.local_date,
                item.human_minutes,
                item.routine_tasks_total,
                item.routine_tasks_automated,
                item.job_runs_total,
                item.job_runs_succeeded,
                item.exceptions_total,
                item.major_misstatements,
            )
            for item in daily
        )
    ):
        raise TractionInputError(
            "operations activity does not reconstruct the signed P12 operations batch"
        )
    bear = calculate_demand(packet.report.demand.scenarios.bear.to_domain())
    key = create_verification_key(
        observation_signing_key.public_key(),
        issuer=traction_trust_store.observation_tco_qa.issuer,
        role=SigningRole.TCO_QA,
    )
    if key != traction_trust_store.observation_tco_qa:
        raise TractionInputError("traction observation signing key mismatch")
    values: dict[str, Any] = {
        "issuer": key.issuer,
        "key_id_sha256": key.key_id_sha256,
        "signer_role": SigningRole.TCO_QA,
        "provenance": provenance,
        "policy_sha256": hash_traction_policy(traction_policy),
        "trust_store_sha256": hash_traction_trust_store(traction_trust_store),
        "plan_sha256": hash_traction_artifact(traction_plan),
        "ledger_store_id_sha256": traction_policy.ledger_store_id_sha256,
        "ordinal": ordinal,
        "predecessor_sha256": predecessor_sha256,
        "run_id": packet.report.run_id,
        "cohort_id": cohort.cohort_id,
        "p12_report_sha256": hash_signed_artifact(packet.report),
        "p12_plan_sha256": hash_signed_artifact(packet.plan),
        "p12_bundle_index_sha256": hash_signed_artifact(packet.bundle_index),
        "p12_demand_batch_sha256": hash_signed_artifact(packet.demand_batch),
        "p12_cohort_batch_sha256": hash_signed_artifact(cohort),
        "p12_operations_batch_sha256": hash_signed_artifact(operations),
        "p12_demand_attestation_sha256": hash_signed_artifact(
            packet.demand_attestation
        ),
        "p12_cohort_attestation_sha256": hash_signed_artifact(
            packet.cohort_attestation
        ),
        "p12_operations_attestation_sha256": hash_signed_artifact(
            packet.operations_attestation
        ),
        "p12_policy_sha256": hash_measurement_policy(packet.policy),
        "p12_trust_store_sha256": hash_measurement_trust_store(packet.trust_store),
        "operations_activity_batch": operations_activity_batch,
        "operational_cost_policy": operational_cost_policy,
        "operations_activity": activity,
        "property_record_sha256": packet.report.property_record_sha256,
        "property_domain_sha256": packet.report.property_domain_sha256,
        "measured_release_sha256": packet.plan.definition.fault_target_release_sha256,
        "measured_artifact_sha256": packet.plan.definition.fault_target_artifact_sha256,
        "measured_schema_sha256": packet.plan.definition.fault_target_schema_sha256,
        "partner_set_sha256": traction_plan.partner_set_sha256,
        "observation_started_at": packet.report.observation_started_at,
        "observation_ended_at": packet.report.observation_ended_at,
        "ingested_at": at,
        "qualified_sessions": len(cohort.qualified_sessions),
        "valid_outbound_clicks": len(cohort.valid_outbound_clicks),
        "settled_amount_at_window_end": settled,
        "partner_facts": tuple(
            PartnerTractionFacts(partner_id=partner, settled_amount=amount)
            for partner, amount in sorted(settled_by_partner.items())
        ),
        "bear_qualified_sessions": bear.qualified_sessions,
        "bear_outbound_click_rate": packet.report.demand.scenarios.bear.outbound_click_rate,
        "human_minutes": sum(item.human_minutes for item in daily),
        "routine_tasks_total": sum(item.routine_tasks_total for item in daily),
        "routine_tasks_automated": sum(
            item.routine_tasks_automated for item in daily
        ),
        "job_runs_total": len(operations.logical_job_runs),
        "job_runs_succeeded": sum(item.succeeded for item in operations.logical_job_runs),
        "major_misstatements": sum(item.major_misstatements for item in daily),
        "exceptions_total": sum(item.exceptions_total for item in daily),
        "exact_faults_passed": sum(item.passed for item in operations.fault_exercises),
        "click_identity_tokens": tuple(
            sorted(
                _identity_token(identity_hmac_key, "click", item.click_id_sha256)
                for item in cohort.valid_outbound_clicks
            )
        ),
        "transaction_identity_tokens": tuple(
            sorted(
                _identity_token(
                    identity_hmac_key, "transaction", item.transaction_id_sha256
                )
                for item in cohort.transactions
            )
        ),
        "issued_at": at,
        "expires_at": min(
            traction_plan.expires_at,
            at + timedelta(seconds=traction_policy.maximum_observation_ttl_seconds),
        ),
    }
    return _sign_model(TractionObservation, values, observation_signing_key)


def verify_traction_observation(
    observation: TractionObservation,
    *,
    plan: SignedTractionPlan,
    policy: TractionPolicy,
    trust_store: TractionTrustStore,
    authority_pins: TractionAuthorityPins,
    at: datetime,
    require_current: bool,
) -> bool:
    try:
        _utc(at, "traction observation verification time")
        observation = TractionObservation.model_validate(observation.model_dump())
        if not verify_traction_plan(
            plan, policy, trust_store, authority_pins, at=at
        ):
            return False
        return (
            observation.policy_sha256 == hash_traction_policy(policy)
            and observation.trust_store_sha256
            == hash_traction_trust_store(trust_store)
            and observation.plan_sha256 == hash_traction_artifact(plan)
            and observation.ledger_store_id_sha256 == policy.ledger_store_id_sha256
            and observation.property_record_sha256 == plan.property_record_sha256
            and observation.property_domain_sha256 == plan.property_domain_sha256
            and observation.measured_release_sha256 == plan.measured_release_sha256
            and observation.measured_artifact_sha256 == plan.measured_artifact_sha256
            and observation.measured_schema_sha256 == plan.measured_schema_sha256
            and observation.partner_set_sha256 == plan.partner_set_sha256
            and observation.p12_policy_sha256 == plan.p12_policy_sha256
            and observation.p12_trust_store_sha256 == plan.p12_trust_store_sha256
            and observation.issuer == trust_store.observation_tco_qa.issuer
            and observation.key_id_sha256
            == trust_store.observation_tco_qa.key_id_sha256
            and observation.issued_at <= at
            and (not require_current or at < observation.expires_at)
            and observation.expires_at - observation.issued_at
            <= timedelta(seconds=policy.maximum_observation_ttl_seconds)
            and _verify_signature(observation, trust_store.observation_tco_qa)
        )
    except (InvalidSignature, TypeError, ValueError):
        return False


def _evaluate_traction(
    observations: Sequence[TractionObservation],
    *,
    plan: SignedTractionPlan,
    policy: TractionPolicy,
    trust_store: TractionTrustStore,
    authority_pins: TractionAuthorityPins,
    at: datetime,
    settlement_evidence: Sequence[TractionSettlementEvidence] = (),
    settlement_policy: SettlementAmendmentPolicy | None = None,
    settlement_trust_store: SettlementAmendmentTrustStore | None = None,
) -> TractionReport:
    """Pure diagnostic evaluator; it is structurally unable to return READY."""

    _utc(at, "traction evaluation time")
    if not verify_traction_plan(plan, policy, trust_store, authority_pins, at=at):
        raise TractionInputError("traction authority verification failed")
    items = tuple(observations)
    previous = _ZERO_SHA256
    seen_clicks: set[str] = set()
    seen_transactions: set[str] = set()
    for expected_ordinal, item in enumerate(items, 1):
        if (
            not verify_traction_observation(
                item,
                plan=plan,
                policy=policy,
                trust_store=trust_store,
                authority_pins=authority_pins,
                at=at,
                require_current=False,
            )
            or item.ordinal != expected_ordinal
            or item.predecessor_sha256 != previous
            or item.observation_started_at
            != plan.experiment_started_at + timedelta(days=30 * (expected_ordinal - 1))
            or item.observation_ended_at
            != plan.experiment_started_at + timedelta(days=30 * expected_ordinal)
            or seen_clicks.intersection(item.click_identity_tokens)
            or seen_transactions.intersection(item.transaction_identity_tokens)
        ):
            raise TractionInputError("traction observation chain is invalid")
        seen_clicks.update(item.click_identity_tokens)
        seen_transactions.update(item.transaction_identity_tokens)
        previous = hash_traction_artifact(item)
    settlement_items = tuple(
        TractionSettlementEvidence.model_validate(item.model_dump())
        for item in settlement_evidence
    )
    adjustments_by_observation: dict[str, Decimal] = {}
    partner_amounts_by_observation: dict[str, tuple[Decimal, ...]] = {}
    if settlement_items:
        if settlement_policy is None or settlement_trust_store is None:
            raise TractionInputError("signed settlement policy and trust are required")
        settlement_policy = SettlementAmendmentPolicy.model_validate(
            settlement_policy.model_dump()
        )
        settlement_trust_store = SettlementAmendmentTrustStore.model_validate(
            settlement_trust_store.model_dump()
        )
        if (
            hash_settlement_policy(settlement_policy)
            != policy.settlement_policy_sha256
            or hash_settlement_trust_store(settlement_trust_store)
            != policy.settlement_trust_store_sha256
        ):
            raise TractionInputError("settlement authority is outside traction pins")
        for evidence in settlement_items:
            if evidence.observation_sha256 in adjustments_by_observation:
                raise TractionInputError("duplicate settlement evidence for observation")
            observation = next(
                (
                    item
                    for item in items
                    if hash_traction_artifact(item) == evidence.observation_sha256
                ),
                None,
            )
            binding = evidence.original_binding
            if (
                observation is None
                or binding.p12_report_sha256 != observation.p12_report_sha256
                or binding.p12_plan_sha256 != observation.p12_plan_sha256
                or binding.p12_bundle_index_sha256
                != observation.p12_bundle_index_sha256
                or binding.p12_cohort_batch_sha256
                != observation.p12_cohort_batch_sha256
                or binding.p12_cohort_attestation_sha256
                != observation.p12_cohort_attestation_sha256
                or binding.run_id != observation.run_id
                or binding.cohort_id != observation.cohort_id
                or binding.property_record_sha256
                != observation.property_record_sha256
                or binding.original_verified_at != observation.ingested_at
                or binding.snapshot_as_of != observation.observation_ended_at
                or _canonical_sha256(binding.partner_ids)
                != observation.partner_set_sha256
                or hash_signed_artifact(evidence.cohort_batch)
                != observation.p12_cohort_batch_sha256
                or any(
                    attestation.observed_through_at
                    < observation.observation_ended_at
                    + timedelta(days=policy.settlement_lag_days)
                    for attestation in evidence.completeness_attestations
                )
            ):
                raise TractionInputError("settlement evidence does not bind observation")
            settlement_pins = SettlementAmendmentAuthorityPins(
                expected_policy_sha256=policy.settlement_policy_sha256,
                expected_trust_store_sha256=policy.settlement_trust_store_sha256,
                expected_p12_report_sha256=observation.p12_report_sha256,
                expected_p12_plan_sha256=observation.p12_plan_sha256,
                expected_p12_bundle_index_sha256=observation.p12_bundle_index_sha256,
                expected_p12_cohort_batch_sha256=observation.p12_cohort_batch_sha256,
                expected_p12_cohort_attestation_sha256=observation.p12_cohort_attestation_sha256,
                expected_run_id=observation.run_id,
                expected_cohort_id=observation.cohort_id,
            )
            result = evaluate_settlement_amendments(
                binding,
                evidence.cohort_batch,
                evidence.amendments,
                evidence.completeness_attestations,
                settlement_policy,
                settlement_trust_store,
                settlement_pins,
                at=at,
            )
            if result.original_settled_amount != observation.settled_amount_at_window_end:
                raise TractionInputError("settlement original amount mismatches observation")
            if tuple(
                (row.partner_id, row.original_settled_amount)
                for row in result.partner_settlements
            ) != tuple(
                (row.partner_id, row.settled_amount)
                for row in observation.partner_facts
            ):
                raise TractionInputError(
                    "settlement partner originals mismatch observation"
                )
            adjustments_by_observation[evidence.observation_sha256] = (
                result.settled_delta
            )
            partner_amounts_by_observation[evidence.observation_sha256] = tuple(
                row.amended_settled_amount for row in result.partner_settlements
            )
    settlement_complete = bool(items) and len(adjustments_by_observation) == len(items)
    adjustments = tuple(
        adjustments_by_observation.get(hash_traction_artifact(item), Decimal(0))
        for item in items
    )
    count = len(items)
    clicks = sum(item.valid_outbound_clicks for item in items)
    qualified = sum(item.qualified_sessions for item in items)
    covered_days = count * 30
    settled_windows = tuple(
        _exact_sum((item.settled_amount_at_window_end, adjustment))
        for item, adjustment in zip(items, adjustments, strict=True)
    )
    if any(value < 0 for value in settled_windows):
        raise TractionInputError("amended window settlement cannot be negative")
    settled = _exact_sum(settled_windows)
    epc = None if clicks == 0 else _exact_ratio(settled, Decimal(clicks))
    mature = clicks >= policy.maturity_valid_clicks or covered_days >= policy.maturity_days
    latest = items[-1] if items else None
    latest_revenue = settled_windows[-1] if items else None
    latest_operating_tco = (
        None
        if latest is None
        else latest.operations_activity.operating_tco.total_operating_tco_jpy
    )
    latest_net_operating_profit = (
        None
        if latest_revenue is None or latest_operating_tco is None
        else latest_revenue - latest_operating_tco
    )
    ctr = (
        None
        if latest is None or latest.qualified_sessions == 0
        else _exact_ratio(
            Decimal(latest.valid_outbound_clicks),
            Decimal(latest.qualified_sessions),
        )
    )
    latest_digest = None if latest is None else hash_traction_artifact(latest)
    latest_partner_amounts = (
        ()
        if latest is None
        else partner_amounts_by_observation.get(
            latest_digest,
            tuple(row.settled_amount for row in latest.partner_facts),
        )
    )
    latest_partner_total = (
        None if latest is None else _exact_sum(latest_partner_amounts)
    )
    partner_share = (
        None
        if latest is None or not latest_partner_total
        else _exact_ratio(max(latest_partner_amounts), latest_partner_total)
    )
    automation = (
        None
        if latest is None
        else (
            Decimal(0)
            if latest.routine_tasks_total == 0
            else _exact_ratio(
                Decimal(latest.routine_tasks_automated),
                Decimal(latest.routine_tasks_total),
            )
        )
    )
    jobs = (
        None
        if latest is None or latest.job_runs_total == 0
        else _exact_ratio(
            Decimal(latest.job_runs_succeeded), Decimal(latest.job_runs_total)
        )
    )
    required_clicks_exact = None
    required_qualified_sessions_exact = None
    capacity_pass = False
    if latest is not None and epc is not None and epc > 0 and latest.bear_outbound_click_rate > 0:
        assert latest_operating_tco is not None
        gross_revenue_required = _exact_sum(
            (policy.target_monthly_net_profit, latest_operating_tco)
        )
        target_click_numerator = _exact_product(
            (gross_revenue_required, Decimal(clicks))
        )
        required_clicks_exact = _exact_ratio(
            target_click_numerator, settled
        )
        required_qualified_sessions_exact = _exact_ratio(
            target_click_numerator,
            _exact_product((settled, latest.bear_outbound_click_rate)),
        )
        capacity_pass = (
            _exact_product(
                (
                    latest.bear_qualified_sessions,
                    settled,
                    latest.bear_outbound_click_rate,
                )
            )
            >= target_click_numerator
        )
    checks: list[TractionCheck] = []

    def check(name: str, passed: bool, observed: object, requirement: str) -> None:
        checks.append(
            TractionCheck(
                name=name,
                status=(TractionCheckStatus.PASS if passed else TractionCheckStatus.FAIL),
                observed=str(observed),
                requirement=requirement,
            )
        )

    check("observations", bool(items), count, ">= 1 contiguous signed observation")
    check(
        "ledger",
        False,
        "unverified",
        "authenticated append-only ledger and current external anchor",
    )
    check("settlement", settlement_complete, settlement_complete, "complete signed settlement coverage")
    check("provenance", bool(items) and all(item.provenance is TractionProvenance.VERIFIED_P12 for item in items), "verified" if items and all(item.provenance is TractionProvenance.VERIFIED_P12 for item in items) else "synthetic-or-empty", "all observations verified P12")
    if not mature:
        checks.append(TractionCheck(name="maturity", status=TractionCheckStatus.WAIT, observed=f"clicks={clicks},days={covered_days}", requirement="clicks >= 1000 OR contiguous days >= 180"))
    else:
        check("maturity", True, f"clicks={clicks},days={covered_days}", "clicks >= 1000 OR contiguous days >= 180")
    check("epc", clicks > 0 and settled >= _exact_product((policy.minimum_settled_epc, Decimal(clicks))), epc if epc is not None else "undefined", ">= JPY 60 cumulative settled EPC")
    check(
        "revenue",
        latest_net_operating_profit is not None
        and latest_net_operating_profit >= policy.target_monthly_net_profit,
        (
            latest_net_operating_profit
            if latest_net_operating_profit is not None
            else "undefined"
        ),
        ">= JPY 200000 latest 30-day net operating profit",
    )
    check("capacity", capacity_pass, latest.bear_qualified_sessions if latest else "undefined", ">= exact bear qualified-session requirement")
    check("ctr", latest is not None and latest.qualified_sessions > 0 and Decimal(latest.valid_outbound_clicks) >= _exact_product((policy.minimum_outbound_ctr, Decimal(latest.qualified_sessions))), ctr if ctr is not None else "undefined", ">= 0.10 latest 30-day outbound CTR")
    check("partners", latest is not None and len(latest.partner_facts) >= policy.minimum_partner_count, len(latest.partner_facts) if latest else 0, ">= 3 frozen partners")
    check("concentration", latest_partner_total is not None and latest_partner_total > 0 and max(latest_partner_amounts) <= _exact_product((policy.maximum_partner_revenue_share, latest_partner_total)), partner_share if partner_share is not None else "undefined", "<= 0.40 latest partner revenue share")
    check("automation", latest is not None and latest.routine_tasks_total > 0 and Decimal(latest.routine_tasks_automated) >= _exact_product((policy.minimum_automation_rate, Decimal(latest.routine_tasks_total))), automation if automation is not None else "undefined", ">= 0.80 latest automation rate")
    check("human", latest is not None and latest.human_minutes <= policy.maximum_human_minutes, latest.human_minutes if latest else "undefined", "<= 720 minutes latest 30 days")
    check("jobs", latest is not None and latest.job_runs_total > 0 and Decimal(latest.job_runs_succeeded) >= _exact_product((policy.minimum_job_success_rate, Decimal(latest.job_runs_total))), jobs if jobs is not None else "undefined", ">= 0.99 latest logical-job success rate")
    check("quality", latest is not None and latest.major_misstatements == 0 and latest.exceptions_total <= policy.maximum_exceptions and latest.exact_faults_passed == policy.required_fault_count, "undefined" if latest is None else f"major={latest.major_misstatements},exceptions={latest.exceptions_total},faults={latest.exact_faults_passed}", "major=0, exceptions<=24, faults=8")
    synthetic_or_empty = not items or any(
        item.provenance is not TractionProvenance.VERIFIED_P12 for item in items
    )
    if not items:
        decision = policy.empty_ledger_action
    elif synthetic_or_empty:
        decision = TractionDecision.STOP
    elif not mature:
        hard_fail_names = {
            "observations",
            "provenance",
            "partners",
            "automation",
            "human",
            "jobs",
            "quality",
        }
        decision = (
            TractionDecision.STOP
            if any(
                item.status is TractionCheckStatus.FAIL and item.name in hard_fail_names
                for item in checks
            )
            else TractionDecision.CONTINUE_OBSERVATION
        )
    else:
        decision = (
            TractionDecision.READY_FOR_SCALE_REVIEW
            if all(item.status is TractionCheckStatus.PASS for item in checks)
            else TractionDecision.STOP
        )
    values: dict[str, Any] = {
        "decision": decision,
        "policy_sha256": hash_traction_policy(policy),
        "trust_store_sha256": hash_traction_trust_store(trust_store),
        "plan_sha256": hash_traction_artifact(plan),
        "ledger_store_id_sha256": policy.ledger_store_id_sha256,
        "evaluated_at": at,
        "observation_count": count,
        "covered_days": covered_days,
        "cumulative_valid_clicks": clicks,
        "cumulative_qualified_sessions": qualified,
        "cumulative_settled_amount": settled,
        "cumulative_settled_epc": epc,
        "traction_mature": mature,
        "ledger_authenticated": False,
        "settlement_complete": settlement_complete,
        "latest_revenue": latest_revenue,
        "latest_operating_tco": latest_operating_tco,
        "latest_net_operating_profit": latest_net_operating_profit,
        "latest_outbound_ctr": ctr,
        "latest_max_partner_share": partner_share,
        "latest_automation_rate": automation,
        "latest_job_success_rate": jobs,
        "required_clicks_exact": required_clicks_exact,
        "required_qualified_sessions_exact": required_qualified_sessions_exact,
        "checks": tuple(checks),
        "observation_head_sha256": previous,
        "settlement_evidence_sha256s": tuple(
            hash_traction_artifact(item) for item in settlement_items
        ),
        "ledger_event_revision": 0,
        "ledger_event_head_sha256": _ZERO_SHA256,
        "trusted_clock_attestation_sha256": _ZERO_SHA256,
    }
    provisional = TractionReport.model_construct(
        **values, report_sha256=_ZERO_SHA256
    )
    return TractionReport(
        **values,
        report_sha256=_canonical_sha256(provisional.model_dump(mode="python")),
    )


def evaluate_traction(
    observations: Sequence[TractionObservation],
    *,
    plan: SignedTractionPlan,
    policy: TractionPolicy,
    trust_store: TractionTrustStore,
    authority_pins: TractionAuthorityPins,
    at: datetime,
    settlement_evidence: Sequence[TractionSettlementEvidence] = (),
    settlement_policy: SettlementAmendmentPolicy | None = None,
    settlement_trust_store: SettlementAmendmentTrustStore | None = None,
) -> TractionReport:
    """Evaluate unpersisted evidence for diagnostics, never for scale readiness.

    Only :meth:`TractionLedger.evaluate` can set the authenticated-ledger gate,
    after verifying the database MAC, immutable chain and external anchor.
    """

    return _evaluate_traction(
        observations,
        plan=plan,
        policy=policy,
        trust_store=trust_store,
        authority_pins=authority_pins,
        at=at,
        settlement_evidence=settlement_evidence,
        settlement_policy=settlement_policy,
        settlement_trust_store=settlement_trust_store,
    )


_TRACTION_LEDGER_SCHEMA = """
CREATE TABLE traction_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE traction_observations (
    ordinal INTEGER PRIMARY KEY,
    event_revision INTEGER NOT NULL UNIQUE,
    event_predecessor_sha256 TEXT NOT NULL,
    event_head_sha256 TEXT NOT NULL UNIQUE,
    artifact_sha256 TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL UNIQUE,
    p12_report_sha256 TEXT NOT NULL UNIQUE,
    observation_json TEXT NOT NULL,
    clock_request_json TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
) STRICT;
CREATE TABLE traction_settlements (
    observation_sha256 TEXT NOT NULL,
    settlement_ordinal INTEGER NOT NULL,
    event_revision INTEGER NOT NULL UNIQUE,
    event_predecessor_sha256 TEXT NOT NULL,
    event_head_sha256 TEXT NOT NULL UNIQUE,
    artifact_sha256 TEXT NOT NULL UNIQUE,
    evidence_json TEXT NOT NULL,
    clock_request_json TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (observation_sha256, settlement_ordinal)
) STRICT;
CREATE TABLE traction_evaluations (
    evaluation_ordinal INTEGER PRIMARY KEY,
    event_revision INTEGER NOT NULL UNIQUE,
    event_predecessor_sha256 TEXT NOT NULL,
    event_head_sha256 TEXT NOT NULL UNIQUE,
    artifact_sha256 TEXT NOT NULL UNIQUE,
    report_json TEXT NOT NULL,
    clock_request_json TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
) STRICT;
CREATE TABLE traction_finalizations (
    target_event_revision INTEGER PRIMARY KEY,
    target_event_head_sha256 TEXT NOT NULL UNIQUE,
    target_artifact_sha256 TEXT NOT NULL,
    target_not_after TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('accepted','expired')),
    event_revision INTEGER NOT NULL UNIQUE,
    event_predecessor_sha256 TEXT NOT NULL,
    event_head_sha256 TEXT NOT NULL UNIQUE,
    artifact_sha256 TEXT NOT NULL UNIQUE,
    clock_request_json TEXT NOT NULL,
    clock_attestation_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER traction_observations_no_update BEFORE UPDATE ON traction_observations BEGIN
    SELECT RAISE(ABORT, 'traction observations are immutable');
END;
CREATE TRIGGER traction_observations_no_delete BEFORE DELETE ON traction_observations BEGIN
    SELECT RAISE(ABORT, 'traction observations are immutable');
END;
CREATE TRIGGER traction_settlements_no_update BEFORE UPDATE ON traction_settlements BEGIN
    SELECT RAISE(ABORT, 'traction settlements are immutable');
END;
CREATE TRIGGER traction_settlements_no_delete BEFORE DELETE ON traction_settlements BEGIN
    SELECT RAISE(ABORT, 'traction settlements are immutable');
END;
CREATE TRIGGER traction_evaluations_no_update BEFORE UPDATE ON traction_evaluations BEGIN
    SELECT RAISE(ABORT, 'traction evaluations are immutable');
END;
CREATE TRIGGER traction_evaluations_no_delete BEFORE DELETE ON traction_evaluations BEGIN
    SELECT RAISE(ABORT, 'traction evaluations are immutable');
END;
CREATE TRIGGER traction_finalizations_no_update BEFORE UPDATE ON traction_finalizations BEGIN
    SELECT RAISE(ABORT, 'traction finalizations are immutable');
END;
CREATE TRIGGER traction_finalizations_no_delete BEFORE DELETE ON traction_finalizations BEGIN
    SELECT RAISE(ABORT, 'traction finalizations are immutable');
END;
"""


class TractionLedger:
    """Authenticated append-only observation ledger with an external anchor."""

    __slots__ = (
        "_path", "_lock_path", "_anchor_lock_path", "_clock_lock_path", "_db_identity", "_store_id", "_plan", "_plan_sha256", "_trust",
        "_policy", "_pins", "_auth_key", "_anchor_commit", "_anchor_read",
        "_clock_attest", "_clock_thread", "_lock"
    )

    def __init__(
        self,
        path: str | Path,
        *,
        plan: SignedTractionPlan,
        policy: TractionPolicy,
        trust_store: TractionTrustStore,
        authority_pins: TractionAuthorityPins,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock_attest: Callable[
            [TractionClockRequest], SignedTractionClockAttestation
        ],
    ) -> None:
        self._path = Path(path).resolve()
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        self._anchor_lock_path = self._path.with_suffix(
            self._path.suffix + ".anchor.lock"
        )
        self._store_id = policy.ledger_store_id_sha256
        self._plan = SignedTractionPlan.model_validate(plan.model_dump())
        self._plan_sha256 = hash_traction_artifact(self._plan)
        self._trust = TractionTrustStore.model_validate(trust_store.model_dump())
        self._policy = TractionPolicy.model_validate(policy.model_dump())
        self._pins = TractionAuthorityPins.model_validate(authority_pins.model_dump())
        self._auth_key = _require_auth_key(state_authentication_key)
        if not callable(anchor_commit) or not callable(anchor_read) or not callable(clock_attest):
            raise TypeError("traction anchor and online clock callbacks are required")
        self._anchor_commit = anchor_commit
        self._anchor_read = anchor_read
        self._clock_attest = clock_attest
        self._clock_thread: Thread | None = None
        self._lock = RLock()
        if not self._path.is_file() or self._path.stat().st_mode & 0o077:
            raise TractionInputError("traction ledger is missing or unsafe")
        database_stat = self._path.stat()
        self._db_identity = (database_stat.st_dev, database_stat.st_ino)
        self._clock_lock_path = Path(self._path.anchor)
        with self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            self._assert_integrity(connection, recover_anchor=True)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        plan: SignedTractionPlan,
        policy: TractionPolicy,
        trust_store: TractionTrustStore,
        authority_pins: TractionAuthorityPins,
        state_authentication_key: bytes,
        anchor_commit: Callable[[int, str], None],
        anchor_read: Callable[[], str],
        clock_attest: Callable[
            [TractionClockRequest], SignedTractionClockAttestation
        ],
    ) -> TractionLedger:
        selected = Path(path).resolve()
        if selected.exists():
            raise FileExistsError("traction ledger already exists")
        if authority_pins.expected_plan_sha256 != hash_traction_artifact(plan):
            raise TractionInputError("traction ledger plan pin mismatch")
        selected.parent.mkdir(parents=True, exist_ok=True)
        auth_key = _require_auth_key(state_authentication_key)
        with sqlite3.connect(selected) as connection:
            connection.executescript(_TRACTION_LEDGER_SCHEMA)
            meta = {
                "schema_version": "1.0",
                "store_id_sha256": policy.ledger_store_id_sha256,
                "plan_sha256": hash_traction_artifact(plan),
                "policy_sha256": hash_traction_policy(policy),
                "trust_store_sha256": hash_traction_trust_store(trust_store),
                "event_revision": "0",
                "event_head_sha256": _ZERO_SHA256,
                "observation_count": "0",
                "observation_head_sha256": _ZERO_SHA256,
                "previous_anchor_sha256": _ZERO_SHA256,
                "state_mac_sha256": _ZERO_SHA256,
            }
            connection.executemany(
                "INSERT INTO traction_meta(key,value) VALUES (?,?)", tuple(meta.items())
            )
            mac = cls._state_mac(connection, auth_key)
            connection.execute("UPDATE traction_meta SET value=? WHERE key='state_mac_sha256'", (mac,))
        selected.chmod(0o600)
        anchor = cls._anchor_hash(
            policy.ledger_store_id_sha256, 0, _ZERO_SHA256, mac
        )
        anchor_lock_path = selected.with_suffix(selected.suffix + ".anchor.lock")
        _bounded_store_callback(
            anchor_commit,
            0,
            anchor,
            label="traction-anchor-commit",
            coordination_path=anchor_lock_path,
        )
        if (
            _bounded_store_callback(
                anchor_read,
                label="traction-anchor-read",
                coordination_path=anchor_lock_path,
            )
            != anchor
        ):
            raise TractionInputError("traction anchor initialization was not durable")
        return cls(selected, plan=plan, policy=policy, trust_store=trust_store, authority_pins=authority_pins, state_authentication_key=auth_key, anchor_commit=anchor_commit, anchor_read=anchor_read, clock_attest=clock_attest)

    def append(
        self,
        observation: TractionObservation,
    ) -> TractionObservation:
        item = TractionObservation.model_validate(observation.model_dump())
        digest = hash_traction_artifact(item)
        with self._lock, self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection, recover_anchor=True)
                expired_observation = connection.execute(
                    "SELECT 1 FROM traction_observations o JOIN traction_finalizations f ON f.target_event_revision=o.event_revision WHERE f.outcome='expired' LIMIT 1"
                ).fetchone()
                if expired_observation is not None:
                    raise TractionInputError(
                        "traction ledger has an expired observation; start a new store"
                    )
                existing = connection.execute("SELECT observation_json FROM traction_observations WHERE p12_report_sha256=?", (item.p12_report_sha256,)).fetchone()
                if existing is not None:
                    existing_revision = connection.execute(
                        "SELECT event_revision FROM traction_observations WHERE p12_report_sha256=?",
                        (item.p12_report_sha256,),
                    ).fetchone()[0]
                    if self._is_expired_target(connection, int(existing_revision)):
                        raise TractionInputError(
                            "P12 report belongs to an expired finalized event"
                        )
                    stored = TractionObservation.model_validate_json(existing["observation_json"])
                    if stored != item:
                        raise TractionInputError("P12 report conflicts with traction ledger")
                    connection.rollback()
                    return stored
                request = self._clock_request_from_meta(
                    meta, TractionClockPurpose.APPEND_OBSERVATION, digest
                )
                clock_attestation = self._obtain_clock_attestation(request)
                recorded_at = clock_attestation.observed_at
                last_event_at = self._last_event_at(connection)
                if last_event_at is not None and recorded_at < last_event_at:
                    raise TractionInputError("trusted clock cannot move backward")
                if not verify_traction_observation(
                    item,
                    plan=self._plan,
                    policy=self._policy,
                    trust_store=self._trust,
                    authority_pins=self._pins,
                    at=recorded_at,
                    require_current=True,
                ):
                    raise TractionInputError("traction observation is not authoritative")
                expected_ordinal = int(meta["observation_count"]) + 1
                if item.ordinal != expected_ordinal or item.predecessor_sha256 != meta["observation_head_sha256"]:
                    raise TractionInputError("traction append is not the exact tail")
                previous = connection.execute("SELECT observation_json FROM traction_observations ORDER BY ordinal DESC LIMIT 1").fetchone()
                if previous is not None:
                    prior = TractionObservation.model_validate_json(previous["observation_json"])
                    if prior.observation_ended_at != item.observation_started_at or set(prior.click_identity_tokens).intersection(item.click_identity_tokens) or set(prior.transaction_identity_tokens).intersection(item.transaction_identity_tokens):
                        raise TractionInputError("traction chronology or identity overlap")
                revision = int(meta["event_revision"]) + 1
                event_head = self._event_hash(
                    "observation", revision, meta["event_head_sha256"], digest
                )
                connection.execute(
                    "INSERT INTO traction_observations(ordinal,event_revision,event_predecessor_sha256,event_head_sha256,artifact_sha256,run_id,p12_report_sha256,observation_json,clock_request_json,clock_attestation_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.ordinal,
                        revision,
                        meta["event_head_sha256"],
                        event_head,
                        digest,
                        item.run_id,
                        item.p12_report_sha256,
                        item.model_dump_json(),
                        request.model_dump_json(),
                        clock_attestation.model_dump_json(),
                        recorded_at.isoformat(),
                    ),
                )
                self._commit_state(
                    connection,
                    meta,
                    revision=revision,
                    event_head=event_head,
                    observation_count=item.ordinal,
                    observation_head=digest,
                )
                finalized = self._finalize_event(
                    connection,
                    target_revision=revision,
                    target_head=event_head,
                    target_artifact=digest,
                    target_not_after=item.expires_at,
                    target_recorded_at=recorded_at,
                )
                if not finalized:
                    raise TractionInputError(
                        "traction event was not finalized before evidence expiry"
                    )
                return item
            except Exception:
                connection.rollback()
                raise

    def append_settlement(
        self,
        evidence: TractionSettlementEvidence,
        *,
        settlement_policy: SettlementAmendmentPolicy,
        settlement_trust_store: SettlementAmendmentTrustStore,
    ) -> TractionSettlementEvidence:
        """Validate and immutably anchor a current settlement snapshot."""

        item = TractionSettlementEvidence.model_validate(evidence.model_dump())
        digest = hash_traction_artifact(item)
        with self._lock, self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection, recover_anchor=True)
                exact = connection.execute(
                    "SELECT s.evidence_json,f.outcome FROM traction_settlements s LEFT JOIN traction_finalizations f ON f.target_event_revision=s.event_revision WHERE s.artifact_sha256=?",
                    (digest,),
                ).fetchone()
                if exact is not None:
                    if exact["outcome"] != TractionFinalizationOutcome.ACCEPTED.value:
                        raise TractionInputError(
                            "settlement snapshot belongs to an expired finalized event"
                        )
                    connection.rollback()
                    return TractionSettlementEvidence.model_validate_json(
                        exact["evidence_json"]
                    )
                observation_row = connection.execute(
                    "SELECT observation_json,event_revision FROM traction_observations WHERE artifact_sha256=?",
                    (item.observation_sha256,),
                ).fetchone()
                if observation_row is None:
                    raise TractionInputError("settlement observation is not in ledger")
                if self._is_expired_target(
                    connection, int(observation_row["event_revision"])
                ):
                    raise TractionInputError(
                        "settlement observation was not timely finalized"
                    )
                request = self._clock_request_from_meta(
                    meta, TractionClockPurpose.APPEND_SETTLEMENT, digest
                )
                clock_attestation = self._obtain_clock_attestation(request)
                last_event_at = self._last_event_at(connection)
                if (
                    last_event_at is not None
                    and clock_attestation.observed_at < last_event_at
                ):
                    raise TractionInputError("trusted clock cannot move backward")
                observations = self._read_observations(connection)
                _evaluate_traction(
                    observations,
                    plan=self._plan,
                    policy=self._policy,
                    trust_store=self._trust,
                    authority_pins=self._pins,
                    at=clock_attestation.observed_at,
                    settlement_evidence=(item,),
                    settlement_policy=settlement_policy,
                    settlement_trust_store=settlement_trust_store,
                )
                prior_rows = connection.execute(
                    "SELECT s.evidence_json FROM traction_settlements s JOIN traction_finalizations f ON f.target_event_revision=s.event_revision WHERE s.observation_sha256=? AND f.outcome='accepted' ORDER BY s.settlement_ordinal",
                    (item.observation_sha256,),
                ).fetchall()
                if prior_rows:
                    previous = TractionSettlementEvidence.model_validate_json(
                        prior_rows[-1]["evidence_json"]
                    )
                    old_events = self._settlement_event_map(previous)
                    new_events = self._settlement_event_map(item)
                    if any(new_events.get(key) != value for key, value in old_events.items()):
                        raise TractionInputError("settlement snapshot rewrites prior events")
                    old_event_coverage = self._settlement_event_coverage_map(previous)
                    new_event_coverage = self._settlement_event_coverage_map(item)
                    if any(
                        new_event_coverage.get(key, datetime.min.replace(tzinfo=timezone.utc))
                        < value
                        for key, value in old_event_coverage.items()
                    ):
                        raise TractionInputError(
                            "settlement event coverage cannot regress"
                        )
                    old_coverage = max(
                        attestation.observed_through_at
                        for attestation in previous.completeness_attestations
                    )
                    new_coverage = max(
                        attestation.observed_through_at
                        for attestation in item.completeness_attestations
                    )
                    if new_coverage < old_coverage:
                        raise TractionInputError("settlement coverage cannot regress")
                settlement_ordinal = connection.execute(
                    "SELECT COALESCE(MAX(settlement_ordinal),0)+1 FROM traction_settlements WHERE observation_sha256=?",
                    (item.observation_sha256,),
                ).fetchone()[0]
                revision = int(meta["event_revision"]) + 1
                event_head = self._event_hash(
                    "settlement", revision, meta["event_head_sha256"], digest
                )
                connection.execute(
                    "INSERT INTO traction_settlements(observation_sha256,settlement_ordinal,event_revision,event_predecessor_sha256,event_head_sha256,artifact_sha256,evidence_json,clock_request_json,clock_attestation_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.observation_sha256,
                        settlement_ordinal,
                        revision,
                        meta["event_head_sha256"],
                        event_head,
                        digest,
                        item.model_dump_json(),
                        request.model_dump_json(),
                        clock_attestation.model_dump_json(),
                        clock_attestation.observed_at.isoformat(),
                    ),
                )
                self._commit_state(
                    connection,
                    meta,
                    revision=revision,
                    event_head=event_head,
                    observation_count=int(meta["observation_count"]),
                    observation_head=meta["observation_head_sha256"],
                )
                finalized = self._finalize_event(
                    connection,
                    target_revision=revision,
                    target_head=event_head,
                    target_artifact=digest,
                    target_not_after=self._settlement_not_after((item,)),
                    target_recorded_at=clock_attestation.observed_at,
                )
                if not finalized:
                    raise TractionInputError(
                        "traction event was not finalized before evidence expiry"
                    )
                return item
            except Exception:
                connection.rollback()
                raise

    def observations(self) -> tuple[TractionObservation, ...]:
        with self._lock, self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            self._assert_integrity(connection, recover_anchor=True)
            return self._read_observations(connection)

    def reports(self) -> tuple[TractionReport, ...]:
        """Return previously anchored evaluation reports for audit/replay."""

        with self._lock, self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            self._assert_integrity(connection, recover_anchor=True)
            rows = connection.execute(
                "SELECT e.report_json FROM traction_evaluations e LEFT JOIN traction_finalizations f ON f.target_event_revision=e.event_revision WHERE COALESCE(f.outcome,'')!='expired' ORDER BY e.evaluation_ordinal"
            ).fetchall()
            return tuple(
                TractionReport.model_validate_json(row["report_json"]) for row in rows
            )

    def evaluate(
        self,
        *,
        settlement_policy: SettlementAmendmentPolicy | None = None,
        settlement_trust_store: SettlementAmendmentTrustStore | None = None,
    ) -> TractionReport:
        """Evaluate the exact authenticated ledger head for Human review only."""

        with self._lock, self._file_lock(), self._connect() as connection:
            self._recover_pending_finalization(connection)
            connection.execute("BEGIN IMMEDIATE")
            meta = self._assert_integrity(connection, recover_anchor=True)
            observations = self._read_observations(connection)
            settlement_evidence = self._latest_settlements(connection)
            request = self._clock_request_from_meta(
                meta,
                TractionClockPurpose.EVALUATE,
                self._evaluation_subject(
                    meta, observations, settlement_evidence
                ),
            )
            clock_attestation = self._obtain_clock_attestation(request)
            last_event_at = self._last_event_at(connection)
            if (
                last_event_at is not None
                and clock_attestation.observed_at < last_event_at
            ):
                connection.rollback()
                raise TractionInputError("trusted clock cannot move backward")
            diagnostic = _evaluate_traction(
                observations,
                plan=self._plan,
                policy=self._policy,
                trust_store=self._trust,
                authority_pins=self._pins,
                at=clock_attestation.observed_at,
                settlement_evidence=settlement_evidence,
                settlement_policy=settlement_policy,
                settlement_trust_store=settlement_trust_store,
            )
            checks = tuple(
                item.model_copy(
                    update={"status": TractionCheckStatus.PASS, "observed": "authenticated"}
                )
                if item.name == "ledger"
                else item
                for item in diagnostic.checks
            )
            if diagnostic.traction_mature:
                decision = (
                    TractionDecision.READY_FOR_SCALE_REVIEW
                    if all(item.status is TractionCheckStatus.PASS for item in checks)
                    else TractionDecision.STOP
                )
            else:
                decision = diagnostic.decision
            values = diagnostic.model_dump(
                mode="python", exclude={"report_sha256"}
            )
            values.update(
                {
                    "decision": decision,
                    "ledger_authenticated": True,
                    "checks": checks,
                    "ledger_event_revision": int(meta["event_revision"]),
                    "ledger_event_head_sha256": meta["event_head_sha256"],
                    "trusted_clock_attestation_sha256": hash_traction_artifact(
                        clock_attestation
                    ),
                }
            )
            provisional = TractionReport.model_construct(
                **values, report_sha256=_ZERO_SHA256
            )
            report = TractionReport(
                **values,
                report_sha256=_canonical_sha256(
                    provisional.model_dump(mode="python")
                ),
            )
            digest = hash_traction_artifact(report)
            revision = int(meta["event_revision"]) + 1
            event_head = self._event_hash(
                "evaluation", revision, meta["event_head_sha256"], digest
            )
            evaluation_ordinal = connection.execute(
                "SELECT COUNT(*) FROM traction_evaluations"
            ).fetchone()[0] + 1
            connection.execute(
                "INSERT INTO traction_evaluations(evaluation_ordinal,event_revision,event_predecessor_sha256,event_head_sha256,artifact_sha256,report_json,clock_request_json,clock_attestation_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    evaluation_ordinal,
                    revision,
                    meta["event_head_sha256"],
                    event_head,
                    digest,
                    report.model_dump_json(),
                    request.model_dump_json(),
                    clock_attestation.model_dump_json(),
                    clock_attestation.observed_at.isoformat(),
                ),
            )
            self._commit_state(
                connection,
                meta,
                revision=revision,
                event_head=event_head,
                observation_count=int(meta["observation_count"]),
                observation_head=meta["observation_head_sha256"],
            )
            finalized = self._finalize_event(
                connection,
                target_revision=revision,
                target_head=event_head,
                target_artifact=digest,
                target_not_after=min(
                    self._plan.expires_at,
                    self._settlement_not_after(settlement_evidence),
                ),
                target_recorded_at=clock_attestation.observed_at,
            )
            if not finalized:
                raise TractionInputError(
                    "traction event was not finalized before evidence expiry"
                )
            return report

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        with _CLOCK_WORKERS_LOCK:
            descriptor = os.open(
                self._lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            descriptor_owner = _track_fork_descriptor(descriptor)
        try:
            deadline = (
                time.monotonic() + _STORE_COORDINATION_TIMEOUT_SECONDS
            )
            while True:
                try:
                    fcntl.flock(
                        descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                    break
                except BlockingIOError as error:
                    if time.monotonic() >= deadline:
                        raise TractionInputError(
                            "traction ledger lock timed out"
                        ) from error
                    time.sleep(_STORE_LOCK_POLL_SECONDS)
            yield
        finally:
            _release_fork_descriptor(descriptor_owner, unlock=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _assert_integrity(
        self,
        connection: sqlite3.Connection,
        *,
        recover_anchor: bool,
        allow_unfinalized_tail: bool = False,
    ) -> dict[str, str]:
        if self._schema_descriptor(connection) != self._expected_schema_descriptor():
            raise TractionInputError("traction ledger schema mismatch")
        meta = {row["key"]: row["value"] for row in connection.execute("SELECT key,value FROM traction_meta ORDER BY key")}
        expected_keys = {"schema_version","store_id_sha256","plan_sha256","policy_sha256","trust_store_sha256","event_revision","event_head_sha256","observation_count","observation_head_sha256","previous_anchor_sha256","state_mac_sha256"}
        if set(meta) != expected_keys or meta["schema_version"] != "1.0" or meta["store_id_sha256"] != self._store_id or meta["plan_sha256"] != self._plan_sha256 or meta["policy_sha256"] != hash_traction_policy(self._policy) or meta["trust_store_sha256"] != hash_traction_trust_store(self._trust):
            raise TractionInputError("traction ledger metadata mismatch")
        observation_rows = connection.execute(
            "SELECT * FROM traction_observations ORDER BY ordinal"
        ).fetchall()
        previous = _ZERO_SHA256
        seen_clicks: set[str] = set()
        seen_transactions: set[str] = set()
        events: list[tuple[int, str, str, str, str, datetime]] = []
        observation_digests: set[str] = set()
        clock_nonces: set[str] = set()
        for ordinal, row in enumerate(observation_rows, 1):
            item = TractionObservation.model_validate_json(row["observation_json"])
            digest = hash_traction_artifact(item)
            try:
                recorded_at = datetime.fromisoformat(row["recorded_at"])
                _utc(recorded_at, "traction recorded_at")
            except (TypeError, ValueError) as exc:
                raise TractionInputError("traction recorded_at is invalid") from exc
            request = TractionClockRequest.model_validate_json(
                row["clock_request_json"]
            )
            attestation = SignedTractionClockAttestation.model_validate_json(
                row["clock_attestation_json"]
            )
            if int(row["ordinal"]) != ordinal or item.ordinal != ordinal or item.predecessor_sha256 != previous or row["artifact_sha256"] != digest or row["run_id"] != item.run_id or row["p12_report_sha256"] != item.p12_report_sha256 or request.ledger_store_id_sha256 != self._store_id or request.plan_sha256 != self._plan_sha256 or request.request_nonce_sha256 in clock_nonces or request.purpose is not TractionClockPurpose.APPEND_OBSERVATION or request.subject_sha256 != digest or request.event_revision != int(row["event_revision"]) - 1 or request.event_head_sha256 != row["event_predecessor_sha256"] or attestation.observed_at != recorded_at or not verify_traction_clock_attestation(attestation, request, self._trust) or not verify_traction_observation(item, plan=self._plan, policy=self._policy, trust_store=self._trust, authority_pins=self._pins, at=recorded_at, require_current=True) or seen_clicks.intersection(item.click_identity_tokens) or seen_transactions.intersection(item.transaction_identity_tokens):
                raise TractionInputError("traction ledger record mismatch")
            clock_nonces.add(request.request_nonce_sha256)
            seen_clicks.update(item.click_identity_tokens)
            seen_transactions.update(item.transaction_identity_tokens)
            previous = digest
            observation_digests.add(digest)
            events.append(
                (
                    int(row["event_revision"]),
                    "observation",
                    row["event_predecessor_sha256"],
                    row["event_head_sha256"],
                    digest,
                    recorded_at,
                )
            )
        settlement_counts: dict[str, int] = {}
        settlement_rows = connection.execute(
            "SELECT * FROM traction_settlements ORDER BY event_revision"
        ).fetchall()
        for row in settlement_rows:
            item = TractionSettlementEvidence.model_validate_json(row["evidence_json"])
            digest = hash_traction_artifact(item)
            request = TractionClockRequest.model_validate_json(row["clock_request_json"])
            attestation = SignedTractionClockAttestation.model_validate_json(row["clock_attestation_json"])
            recorded_at = datetime.fromisoformat(row["recorded_at"])
            _utc(recorded_at, "traction settlement recorded_at")
            expected_ordinal = settlement_counts.get(item.observation_sha256, 0) + 1
            if item.observation_sha256 not in observation_digests or row["observation_sha256"] != item.observation_sha256 or int(row["settlement_ordinal"]) != expected_ordinal or row["artifact_sha256"] != digest or request.ledger_store_id_sha256 != self._store_id or request.plan_sha256 != self._plan_sha256 or request.request_nonce_sha256 in clock_nonces or request.purpose is not TractionClockPurpose.APPEND_SETTLEMENT or request.subject_sha256 != digest or request.event_revision != int(row["event_revision"]) - 1 or request.event_head_sha256 != row["event_predecessor_sha256"] or attestation.observed_at != recorded_at or not verify_traction_clock_attestation(attestation, request, self._trust):
                raise TractionInputError("traction settlement ledger record mismatch")
            clock_nonces.add(request.request_nonce_sha256)
            settlement_counts[item.observation_sha256] = expected_ordinal
            events.append((int(row["event_revision"]),"settlement",row["event_predecessor_sha256"],row["event_head_sha256"],digest,recorded_at))
        evaluation_rows = connection.execute(
            "SELECT * FROM traction_evaluations ORDER BY evaluation_ordinal"
        ).fetchall()
        for expected_ordinal, row in enumerate(evaluation_rows, 1):
            report = TractionReport.model_validate_json(row["report_json"])
            digest = hash_traction_artifact(report)
            request = TractionClockRequest.model_validate_json(row["clock_request_json"])
            attestation = SignedTractionClockAttestation.model_validate_json(row["clock_attestation_json"])
            recorded_at = datetime.fromisoformat(row["recorded_at"])
            _utc(recorded_at, "traction evaluation recorded_at")
            subject = self._evaluation_subject_values(
                report.ledger_event_revision,
                report.ledger_event_head_sha256,
                report.observation_head_sha256,
                report.settlement_evidence_sha256s,
            )
            if int(row["evaluation_ordinal"]) != expected_ordinal or row["artifact_sha256"] != digest or request.ledger_store_id_sha256 != self._store_id or request.plan_sha256 != self._plan_sha256 or request.request_nonce_sha256 in clock_nonces or request.purpose is not TractionClockPurpose.EVALUATE or request.subject_sha256 != subject or request.event_revision != report.ledger_event_revision or request.event_head_sha256 != report.ledger_event_head_sha256 or request.event_revision != int(row["event_revision"]) - 1 or request.event_head_sha256 != row["event_predecessor_sha256"] or attestation.observed_at != recorded_at or report.evaluated_at != recorded_at or report.trusted_clock_attestation_sha256 != hash_traction_artifact(attestation) or not verify_traction_clock_attestation(attestation, request, self._trust):
                raise TractionInputError("traction evaluation ledger record mismatch")
            clock_nonces.add(request.request_nonce_sha256)
            events.append((int(row["event_revision"]),"evaluation",row["event_predecessor_sha256"],row["event_head_sha256"],digest,recorded_at))
        target_events = {
            revision: (head, digest, recorded_at)
            for revision, kind, _predecessor, head, digest, recorded_at in events
            if kind in {"observation", "settlement", "evaluation"}
        }
        finalized_targets: set[int] = set()
        finalization_rows = connection.execute(
            "SELECT * FROM traction_finalizations ORDER BY target_event_revision"
        ).fetchall()
        for row in finalization_rows:
            target_revision = int(row["target_event_revision"])
            target = target_events.get(target_revision)
            target_not_after = datetime.fromisoformat(row["target_not_after"])
            _utc(target_not_after, "traction finalization deadline")
            request = TractionClockRequest.model_validate_json(
                row["clock_request_json"]
            )
            attestation = SignedTractionClockAttestation.model_validate_json(
                row["clock_attestation_json"]
            )
            recorded_at = datetime.fromisoformat(row["recorded_at"])
            _utc(recorded_at, "traction finalization recorded_at")
            outcome = TractionFinalizationOutcome(row["outcome"])
            subject = self._finalization_subject(
                target_revision,
                row["target_event_head_sha256"],
                row["target_artifact_sha256"],
                target_not_after,
            )
            artifact = _canonical_sha256(
                {
                    "target_event_revision": target_revision,
                    "target_event_head_sha256": row["target_event_head_sha256"],
                    "target_artifact_sha256": row["target_artifact_sha256"],
                    "target_not_after": target_not_after,
                    "outcome": outcome,
                    "clock_request_sha256": hash_traction_artifact(request),
                    "clock_attestation_sha256": hash_traction_artifact(attestation),
                }
            )
            timing_valid = (
                outcome is TractionFinalizationOutcome.ACCEPTED
                and target is not None
                and target[2] <= recorded_at < target_not_after
            ) or (
                outcome is TractionFinalizationOutcome.EXPIRED
                and target is not None
                and recorded_at >= target_not_after
            )
            if target is None or target_revision in finalized_targets or target[0] != row["target_event_head_sha256"] or target[1] != row["target_artifact_sha256"] or int(row["event_revision"]) != target_revision + 1 or row["event_predecessor_sha256"] != target[0] or row["artifact_sha256"] != artifact or request.ledger_store_id_sha256 != self._store_id or request.plan_sha256 != self._plan_sha256 or request.request_nonce_sha256 in clock_nonces or request.purpose is not TractionClockPurpose.FINALIZE_EVENT or request.subject_sha256 != subject or request.event_revision != target_revision or request.event_head_sha256 != target[0] or attestation.observed_at != recorded_at or not timing_valid or not verify_traction_clock_attestation(attestation, request, self._trust):
                raise TractionInputError("traction finalization record mismatch")
            finalized_targets.add(target_revision)
            clock_nonces.add(request.request_nonce_sha256)
            events.append((int(row["event_revision"]),"finalization",row["event_predecessor_sha256"],row["event_head_sha256"],artifact,recorded_at))
        unfinalized_targets = set(target_events) - finalized_targets
        if unfinalized_targets and (
            not allow_unfinalized_tail or len(unfinalized_targets) != 1
        ):
            raise TractionInputError("traction ledger contains unfinalized events")
        event_head = _ZERO_SHA256
        last_time: datetime | None = None
        for expected_revision, event in enumerate(sorted(events), 1):
            revision, kind, predecessor, actual_head, digest, recorded_at = event
            if revision != expected_revision or predecessor != event_head or actual_head != self._event_hash(kind, revision, predecessor, digest) or (last_time is not None and recorded_at < last_time):
                raise TractionInputError("traction global event chain mismatch")
            event_head = actual_head
            last_time = recorded_at
        if int(meta["event_revision"]) != len(events) or meta["event_head_sha256"] != event_head or int(meta["observation_count"]) != len(observation_rows) or meta["observation_head_sha256"] != previous:
            raise TractionInputError("traction ledger head mismatch")
        if unfinalized_targets:
            pending_revision = next(iter(unfinalized_targets))
            pending = target_events[pending_revision]
            if (
                pending_revision != int(meta["event_revision"])
                or pending[0] != meta["event_head_sha256"]
            ):
                raise TractionInputError(
                    "traction unfinalized event is not the exact ledger tail"
                )
        mac = self._state_mac(connection, self._auth_key)
        if not hmac.compare_digest(mac, meta["state_mac_sha256"]):
            raise TractionInputError("traction ledger authentication mismatch")
        anchor = self._anchor_hash(self._store_id, int(meta["event_revision"]), event_head, meta["state_mac_sha256"])
        observed = _bounded_store_callback(
            self._anchor_read,
            label="traction-anchor-read",
            coordination_path=self._anchor_lock_path,
        )
        if observed != anchor:
            if not recover_anchor or observed != meta["previous_anchor_sha256"]:
                raise TractionInputError("traction ledger anchor mismatch")
            _bounded_store_callback(
                self._anchor_commit,
                int(meta["event_revision"]),
                anchor,
                label="traction-anchor-commit",
                coordination_path=self._anchor_lock_path,
            )
            if (
                _bounded_store_callback(
                    self._anchor_read,
                    label="traction-anchor-read",
                    coordination_path=self._anchor_lock_path,
                )
                != anchor
            ):
                raise TractionInputError("traction anchor recovery failed")
        return meta

    def _commit_state(
        self,
        connection: sqlite3.Connection,
        meta: dict[str, str],
        *,
        revision: int,
        event_head: str,
        observation_count: int,
        observation_head: str,
    ) -> None:
        prior_anchor = _bounded_store_callback(
            self._anchor_read,
            label="traction-anchor-read",
            coordination_path=self._anchor_lock_path,
        )
        updates = {
            "event_revision": str(revision),
            "event_head_sha256": event_head,
            "observation_count": str(observation_count),
            "observation_head_sha256": observation_head,
            "previous_anchor_sha256": prior_anchor,
        }
        connection.executemany(
            "UPDATE traction_meta SET value=? WHERE key=?",
            tuple((value, key) for key, value in updates.items()),
        )
        mac = self._state_mac(connection, self._auth_key)
        connection.execute(
            "UPDATE traction_meta SET value=? WHERE key='state_mac_sha256'", (mac,)
        )
        connection.commit()
        anchor = self._anchor_hash(self._store_id, revision, event_head, mac)
        _bounded_store_callback(
            self._anchor_commit,
            revision,
            anchor,
            label="traction-anchor-commit",
            coordination_path=self._anchor_lock_path,
        )
        if (
            _bounded_store_callback(
                self._anchor_read,
                label="traction-anchor-read",
                coordination_path=self._anchor_lock_path,
            )
            != anchor
        ):
            raise TractionInputError("traction anchor commit was not durable")

    def _recover_pending_finalization(
        self, connection: sqlite3.Connection
    ) -> None:
        """Resume the sole anchored operational tail after a crash/timeout."""

        self._assert_integrity(
            connection,
            recover_anchor=True,
            allow_unfinalized_tail=True,
        )
        row = connection.execute(
            "SELECT operational.kind,operational.event_revision,operational.event_head_sha256,operational.artifact_sha256,operational.recorded_at,operational.payload_json FROM (SELECT 'observation' AS kind,event_revision,event_head_sha256,artifact_sha256,recorded_at,observation_json AS payload_json FROM traction_observations UNION ALL SELECT 'settlement' AS kind,event_revision,event_head_sha256,artifact_sha256,recorded_at,evidence_json AS payload_json FROM traction_settlements UNION ALL SELECT 'evaluation' AS kind,event_revision,event_head_sha256,artifact_sha256,recorded_at,report_json AS payload_json FROM traction_evaluations) operational LEFT JOIN traction_finalizations finalization ON finalization.target_event_revision=operational.event_revision WHERE finalization.target_event_revision IS NULL ORDER BY operational.event_revision"
        ).fetchall()
        if not row:
            return
        if len(row) != 1:
            raise TractionInputError("traction ledger has multiple pending events")
        pending = row[0]
        target_recorded_at = datetime.fromisoformat(pending["recorded_at"])
        _utc(target_recorded_at, "traction pending recorded_at")
        if pending["kind"] == "observation":
            target_not_after = TractionObservation.model_validate_json(
                pending["payload_json"]
            ).expires_at
        elif pending["kind"] == "settlement":
            target_not_after = self._settlement_not_after(
                (
                    TractionSettlementEvidence.model_validate_json(
                        pending["payload_json"]
                    ),
                )
            )
        else:
            report = TractionReport.model_validate_json(pending["payload_json"])
            evidence_rows = connection.execute(
                "SELECT artifact_sha256,evidence_json FROM traction_settlements"
            ).fetchall()
            evidence_by_hash = {
                item["artifact_sha256"]: TractionSettlementEvidence.model_validate_json(
                    item["evidence_json"]
                )
                for item in evidence_rows
            }
            try:
                report_evidence = tuple(
                    evidence_by_hash[digest]
                    for digest in report.settlement_evidence_sha256s
                )
            except KeyError as exc:
                raise TractionInputError(
                    "pending evaluation settlement evidence is missing"
                ) from exc
            target_not_after = min(
                self._plan.expires_at,
                self._settlement_not_after(report_evidence),
            )
        self._finalize_event(
            connection,
            target_revision=int(pending["event_revision"]),
            target_head=pending["event_head_sha256"],
            target_artifact=pending["artifact_sha256"],
            target_not_after=target_not_after,
            target_recorded_at=target_recorded_at,
        )
        self._assert_integrity(connection, recover_anchor=True)

    def _finalize_event(
        self,
        connection: sqlite3.Connection,
        *,
        target_revision: int,
        target_head: str,
        target_artifact: str,
        target_not_after: datetime,
        target_recorded_at: datetime,
    ) -> bool:
        """Timestamp an already durable+anchored event, then anchor that proof."""

        connection.execute("BEGIN IMMEDIATE")
        meta = {
            row["key"]: row["value"]
            for row in connection.execute(
                "SELECT key,value FROM traction_meta ORDER BY key"
            )
        }
        if (
            int(meta["event_revision"]) != target_revision
            or meta["event_head_sha256"] != target_head
        ):
            raise TractionInputError("traction finalization target moved")
        expected_anchor = self._anchor_hash(
            self._store_id,
            target_revision,
            target_head,
            meta["state_mac_sha256"],
        )
        if (
            _bounded_store_callback(
                self._anchor_read,
                label="traction-anchor-read",
                coordination_path=self._anchor_lock_path,
            )
            != expected_anchor
        ):
            raise TractionInputError("traction target was not durably anchored")
        subject = self._finalization_subject(
            target_revision, target_head, target_artifact, target_not_after
        )
        request = self._clock_request_from_meta(
            meta, TractionClockPurpose.FINALIZE_EVENT, subject
        )
        attestation = self._obtain_clock_attestation(request)
        if attestation.observed_at < target_recorded_at:
            raise TractionInputError("trusted clock cannot move backward")
        outcome = (
            TractionFinalizationOutcome.ACCEPTED
            if attestation.observed_at < target_not_after
            else TractionFinalizationOutcome.EXPIRED
        )
        artifact = _canonical_sha256(
            {
                "target_event_revision": target_revision,
                "target_event_head_sha256": target_head,
                "target_artifact_sha256": target_artifact,
                "target_not_after": target_not_after,
                "outcome": outcome,
                "clock_request_sha256": hash_traction_artifact(request),
                "clock_attestation_sha256": hash_traction_artifact(attestation),
            }
        )
        revision = target_revision + 1
        event_head = self._event_hash(
            "finalization", revision, target_head, artifact
        )
        connection.execute(
            "INSERT INTO traction_finalizations(target_event_revision,target_event_head_sha256,target_artifact_sha256,target_not_after,outcome,event_revision,event_predecessor_sha256,event_head_sha256,artifact_sha256,clock_request_json,clock_attestation_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                target_revision,
                target_head,
                target_artifact,
                target_not_after.isoformat(),
                outcome.value,
                revision,
                target_head,
                event_head,
                artifact,
                request.model_dump_json(),
                attestation.model_dump_json(),
                attestation.observed_at.isoformat(),
            ),
        )
        self._commit_state(
            connection,
            meta,
            revision=revision,
            event_head=event_head,
            observation_count=int(meta["observation_count"]),
            observation_head=meta["observation_head_sha256"],
        )
        return outcome is TractionFinalizationOutcome.ACCEPTED

    def _clock_request_from_meta(
        self,
        meta: dict[str, str],
        purpose: TractionClockPurpose,
        subject_sha256: str,
    ) -> TractionClockRequest:
        return TractionClockRequest(
            purpose=purpose,
            ledger_store_id_sha256=self._store_id,
            plan_sha256=self._plan_sha256,
            event_revision=int(meta["event_revision"]),
            event_head_sha256=meta["event_head_sha256"],
            subject_sha256=subject_sha256,
            request_nonce_sha256=hashlib.sha256(os.urandom(32)).hexdigest(),
        )

    def _obtain_clock_attestation(
        self, request: TractionClockRequest
    ) -> SignedTractionClockAttestation:
        database_stat = self._path.stat()
        if (database_stat.st_dev, database_stat.st_ino) != self._db_identity:
            raise TractionInputError("traction ledger identity changed")
        worker_key = str(self._clock_lock_path)
        with _CLOCK_WORKERS_LOCK:
            prior_worker = _CLOCK_WORKERS.get(worker_key)
            if prior_worker is not None and prior_worker.is_alive():
                self._clock_thread = prior_worker
                raise TractionInputError(
                    "previous online trusted-clock request is still running"
                )
            _CLOCK_WORKERS.pop(worker_key, None)
            self._clock_thread = None
        lock_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            lock_flags |= os.O_DIRECTORY
        with _CLOCK_WORKERS_LOCK:
            worker_lock_fd = os.open(self._clock_lock_path, lock_flags)
            worker_fd_owner = _track_fork_descriptor(worker_lock_fd)
        worker: Thread | None = None
        try:
            lock_stat = os.fstat(worker_lock_fd)
            if not stat.S_ISDIR(lock_stat.st_mode):
                raise TractionInputError("traction host clock lock is unsafe")
            fcntl.flock(worker_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result: Queue[tuple[bool, Any]] = Queue(maxsize=1)
            ownership_started = Event()

            def invoke() -> None:
                try:
                    ownership_started.set()
                    result.put((True, self._clock_attest(request)))
                except BaseException as exc:  # callback boundary, relayed below
                    result.put((False, exc))
                finally:
                    _release_fork_descriptor(worker_fd_owner, unlock=True)
                    with _CLOCK_WORKERS_LOCK:
                        if _CLOCK_WORKERS.get(worker_key) is current_thread():
                            _CLOCK_WORKERS.pop(worker_key, None)

            worker = Thread(target=invoke, name="traction-clock", daemon=True)
            self._clock_thread = worker
            with _CLOCK_WORKERS_LOCK:
                _CLOCK_WORKERS[worker_key] = worker
        except BaseException as exc:
            _release_fork_descriptor(worker_fd_owner, unlock=True)
            with _CLOCK_WORKERS_LOCK:
                if worker is not None and _CLOCK_WORKERS.get(worker_key) is worker:
                    _CLOCK_WORKERS.pop(worker_key, None)
            self._clock_thread = None
            if isinstance(exc, BlockingIOError):
                raise TractionInputError(
                    "previous online trusted-clock request is still running"
                ) from exc
            raise
        assert worker is not None
        try:
            worker.start()
        except BaseException:
            # Thread.start() can be wrapped by an implementation which raises
            # after the OS thread was launched.  In that case only the worker
            # may release the one-shot descriptor lease; caller cleanup could
            # otherwise close a newly reused descriptor while the callback runs.
            worker_owns_descriptor = ownership_started.wait(
                timeout=min(
                    1.0,
                    float(self._policy.clock_response_timeout_seconds),
                )
            ) or worker.ident is not None
            if not worker_owns_descriptor:
                _release_fork_descriptor(worker_fd_owner, unlock=True)
                with _CLOCK_WORKERS_LOCK:
                    if _CLOCK_WORKERS.get(worker_key) is worker:
                        _CLOCK_WORKERS.pop(worker_key, None)
                self._clock_thread = None
            elif not worker.is_alive():
                self._clock_thread = None
            raise
        try:
            ok, value = result.get(
                timeout=self._policy.clock_response_timeout_seconds
            )
        except Empty as exc:
            raise TractionInputError(
                "online trusted-clock response timed out"
            ) from exc
        worker.join(timeout=0.1)
        if not worker.is_alive():
            self._clock_thread = None
        if not ok:
            raise TractionInputError(
                "online trusted-clock callback failed"
            ) from value
        try:
            attestation = SignedTractionClockAttestation.model_validate(
                value.model_dump()
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise TractionInputError("online trusted-clock response is invalid") from exc
        if not verify_traction_clock_attestation(
            attestation, request, self._trust
        ):
            raise TractionInputError("online trusted-clock response is untrusted")
        return attestation

    @staticmethod
    def _settlement_event_map(
        evidence: TractionSettlementEvidence,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for amendment in evidence.amendments:
            for event in amendment.events:
                digest = hash_traction_artifact(event)
                previous = result.setdefault(event.event_id_sha256, digest)
                if previous != digest:
                    raise TractionInputError("conflicting settlement event identity")
        return result

    @staticmethod
    def _settlement_event_coverage_map(
        evidence: TractionSettlementEvidence,
    ) -> dict[str, datetime]:
        completeness = {
            item.amendment_sha256: item
            for item in evidence.completeness_attestations
        }
        result: dict[str, datetime] = {}
        for amendment in evidence.amendments:
            coverage = completeness[hash_signed_artifact(amendment)].observed_through_at
            for event in amendment.events:
                prior = result.get(event.event_id_sha256)
                if prior is None or coverage > prior:
                    result[event.event_id_sha256] = coverage
        return result

    def _settlement_not_after(
        self, evidence: Sequence[TractionSettlementEvidence]
    ) -> datetime:
        expiries = [self._plan.expires_at]
        for item in evidence:
            expiries.extend(amendment.expires_at for amendment in item.amendments)
            expiries.extend(
                attestation.expires_at
                for attestation in item.completeness_attestations
            )
        return min(expiries)

    @staticmethod
    def _finalization_subject(
        target_revision: int,
        target_head: str,
        target_artifact: str,
        target_not_after: datetime,
    ) -> str:
        return _canonical_sha256(
            {
                "target_event_revision": target_revision,
                "target_event_head_sha256": target_head,
                "target_artifact_sha256": target_artifact,
                "target_not_after": target_not_after,
            }
        )

    @staticmethod
    def _evaluation_subject_values(
        event_revision: int,
        event_head_sha256: str,
        observation_head_sha256: str,
        evidence_sha256s: Sequence[str],
    ) -> str:
        return _canonical_sha256(
            {
                "event_revision": event_revision,
                "event_head_sha256": event_head_sha256,
                "observation_head_sha256": observation_head_sha256,
                "settlement_evidence_sha256s": tuple(evidence_sha256s),
            }
        )

    def _evaluation_subject(
        self,
        meta: dict[str, str],
        observations: Sequence[TractionObservation],
        evidence: Sequence[TractionSettlementEvidence],
    ) -> str:
        return self._evaluation_subject_values(
            int(meta["event_revision"]),
            meta["event_head_sha256"],
            (
                hash_traction_artifact(observations[-1])
                if observations
                else _ZERO_SHA256
            ),
            tuple(hash_traction_artifact(item) for item in evidence),
        )

    @staticmethod
    def _event_hash(kind: str, revision: int, predecessor: str, artifact: str) -> str:
        return _canonical_sha256(
            {
                "kind": kind,
                "revision": revision,
                "predecessor_sha256": predecessor,
                "artifact_sha256": artifact,
            }
        )

    @staticmethod
    def _read_observations(connection: sqlite3.Connection) -> tuple[TractionObservation, ...]:
        rows = connection.execute(
            "SELECT o.observation_json FROM traction_observations o LEFT JOIN traction_finalizations f ON f.target_event_revision=o.event_revision WHERE COALESCE(f.outcome,'')!='expired' ORDER BY o.ordinal"
        ).fetchall()
        return tuple(
            TractionObservation.model_validate_json(row["observation_json"])
            for row in rows
        )

    @staticmethod
    def _latest_settlements(connection: sqlite3.Connection) -> tuple[TractionSettlementEvidence, ...]:
        rows = connection.execute(
            "SELECT s.evidence_json FROM traction_settlements s JOIN (SELECT observation_sha256,MAX(settlement_ordinal) AS latest FROM traction_settlements GROUP BY observation_sha256) x ON x.observation_sha256=s.observation_sha256 AND x.latest=s.settlement_ordinal JOIN traction_finalizations settlement_finalized ON settlement_finalized.target_event_revision=s.event_revision AND settlement_finalized.outcome='accepted' JOIN traction_observations o ON o.artifact_sha256=s.observation_sha256 JOIN traction_finalizations observation_finalized ON observation_finalized.target_event_revision=o.event_revision AND observation_finalized.outcome='accepted' ORDER BY o.ordinal"
        ).fetchall()
        return tuple(
            TractionSettlementEvidence.model_validate_json(row["evidence_json"])
            for row in rows
        )

    @staticmethod
    def _is_expired_target(
        connection: sqlite3.Connection, event_revision: int
    ) -> bool:
        row = connection.execute(
            "SELECT outcome FROM traction_finalizations WHERE target_event_revision=?",
            (event_revision,),
        ).fetchone()
        return row is not None and row["outcome"] == TractionFinalizationOutcome.EXPIRED.value

    @staticmethod
    def _last_event_at(connection: sqlite3.Connection) -> datetime | None:
        row = connection.execute(
            "SELECT recorded_at FROM (SELECT event_revision,recorded_at FROM traction_observations UNION ALL SELECT event_revision,recorded_at FROM traction_settlements UNION ALL SELECT event_revision,recorded_at FROM traction_evaluations UNION ALL SELECT event_revision,recorded_at FROM traction_finalizations) ORDER BY event_revision DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        value = datetime.fromisoformat(row["recorded_at"])
        _utc(value, "traction last-event time")
        return value

    @staticmethod
    def _state_mac(connection: sqlite3.Connection, key: bytes) -> str:
        meta = [tuple(row) for row in connection.execute("SELECT key,value FROM traction_meta WHERE key!='state_mac_sha256' ORDER BY key")]
        observations = [tuple(row) for row in connection.execute("SELECT * FROM traction_observations ORDER BY ordinal")]
        settlements = [tuple(row) for row in connection.execute("SELECT * FROM traction_settlements ORDER BY event_revision")]
        evaluations = [tuple(row) for row in connection.execute("SELECT * FROM traction_evaluations ORDER BY evaluation_ordinal")]
        finalizations = [tuple(row) for row in connection.execute("SELECT * FROM traction_finalizations ORDER BY target_event_revision")]
        return hmac.new(key, json.dumps({"meta":meta,"observations":observations,"settlements":settlements,"evaluations":evaluations,"finalizations":finalizations},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _anchor_hash(store_id: str, revision: int, head: str, mac: str) -> str:
        return _canonical_sha256({"ledger_store_id_sha256":store_id,"revision":revision,"head_sha256":head,"state_mac_sha256":mac})

    @staticmethod
    def _schema_descriptor(connection: sqlite3.Connection) -> str:
        rows = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND NOT (type='index' AND sql IS NULL) ORDER BY type,name").fetchall()
        return _canonical_sha256([tuple(row) for row in rows])

    @classmethod
    def _expected_schema_descriptor(cls) -> str:
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(_TRACTION_LEDGER_SCHEMA)
            return cls._schema_descriptor(connection)


class TractionLedgerBootstrap(Protocol):
    """Secret-owning boundary used only to open one authenticated ledger."""

    def open_traction_ledger(self) -> TractionLedger: ...


class TractionRuntimeBroker:
    """Credential-blind P17 operations port over a provisioned ledger.

    No broker operation accepts a state-MAC key, signer, trusted-clock callback,
    or external-anchor callback.  A separately controlled bootstrap component
    owns those dependencies and returns only a fully initialized ledger.
    """

    __slots__ = ("_ledger",)

    def __init__(self, bootstrap: TractionLedgerBootstrap) -> None:
        if not callable(getattr(bootstrap, "open_traction_ledger", None)):
            raise TypeError("traction runtime requires a ledger bootstrap port")
        ledger = bootstrap.open_traction_ledger()
        if type(ledger) is not TractionLedger:
            raise TypeError("bootstrap must return an exact TractionLedger")
        self._ledger = ledger

    def append_observation(
        self, observation: TractionObservation
    ) -> TractionObservation:
        return self._ledger.append(observation)

    def append_settlement(
        self,
        evidence: TractionSettlementEvidence,
        *,
        settlement_policy: SettlementAmendmentPolicy,
        settlement_trust_store: SettlementAmendmentTrustStore,
    ) -> TractionSettlementEvidence:
        return self._ledger.append_settlement(
            evidence,
            settlement_policy=settlement_policy,
            settlement_trust_store=settlement_trust_store,
        )

    def evaluate(
        self,
        *,
        settlement_policy: SettlementAmendmentPolicy | None = None,
        settlement_trust_store: SettlementAmendmentTrustStore | None = None,
    ) -> TractionReport:
        return self._ledger.evaluate(
            settlement_policy=settlement_policy,
            settlement_trust_store=settlement_trust_store,
        )

    def observations(self) -> tuple[TractionObservation, ...]:
        return self._ledger.observations()

    def reports(self) -> tuple[TractionReport, ...]:
        return self._ledger.reports()


def _sign_model(model_type: type[StrictModel], values: dict[str, Any], key: Ed25519PrivateKey) -> Any:
    signed_values = {"schema_version": "1.0", **values}
    payload = _canonical_sha256(signed_values)
    signature = _encode_base64url(key.sign(bytes.fromhex(payload)))
    return model_type(
        **signed_values,
        payload_sha256=payload,
        signature_base64url=signature,
    )


def _validate_payload_hash(model: StrictModel) -> None:
    values = model.model_dump(mode="python", exclude={"payload_sha256", "signature_base64url"})
    if getattr(model, "payload_sha256") != _canonical_sha256(values):
        raise ValueError("signed traction payload hash mismatch")


def _verify_signature(model: StrictModel, key: Ed25519VerificationKey) -> bool:
    if getattr(model, "issuer") != key.issuer or getattr(model, "key_id_sha256") != key.key_id_sha256:
        return False
    key.public_key().verify(_decode_base64url(getattr(model, "signature_base64url"), 64), bytes.fromhex(getattr(model, "payload_sha256")))
    return True


def _identity_token(key: bytes, kind: str, value: str) -> str:
    return hmac.new(key, f"p17:{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def _require_auth_key(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        raise TractionInputError("state authentication key must contain at least 32 bytes")
    return value


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _utc(value: datetime, label: str) -> datetime:
    _aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value


def _decimal_work_precision(values: Sequence[Decimal]) -> int:
    return max(
        80,
        sum(
            len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
            for value in values
        )
        + 32,
    )


def _exact_sum(values: Sequence[Decimal] | Iterator[Decimal]) -> Decimal:
    items = tuple(values)
    if not items:
        return Decimal(0)
    with localcontext() as context:
        context.prec = _decimal_work_precision(items)
        return sum(items, Decimal(0))


def _exact_product(values: Sequence[Decimal]) -> Decimal:
    items = tuple(values)
    with localcontext() as context:
        context.prec = _decimal_work_precision(items)
        result = Decimal(1)
        for value in items:
            result *= value
        return result


def _exact_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        raise ZeroDivisionError("exact display ratio denominator is zero")
    with localcontext() as context:
        context.prec = _decimal_work_precision((numerator, denominator))
        return numerator / denominator


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite Decimal cannot be canonicalized")
    if value == 0:
        return "0"
    sign, digits, exponent = value.as_tuple()
    characters = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        rendered = characters + ("0" * exponent)
    else:
        point = len(characters) + exponent
        rendered = (
            characters[:point] + "." + characters[point:]
            if point > 0
            else "0." + ("0" * (-point)) + characters
        )
        rendered = rendered.rstrip("0").rstrip(".")
    return ("-" if sign else "") + rendered


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(_canonical_value(value),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, datetime):
        _aware(value, "canonical datetime")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, StrictModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [_canonical_value(item) for item in value]
    if value is None or type(value) in (str,int,bool):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_base64url(value: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid canonical base64url") from exc
    if len(decoded) != length or _encode_base64url(decoded) != value:
        raise ValueError("invalid canonical base64url length or encoding")
    return decoded


__all__ = [
    "P12AuthorityPacket", "PartnerTractionFacts", "SignedTractionPlan",
    "SignedTractionClockAttestation", "TractionAuthorityPins", "TractionCheck",
    "TractionCheckStatus", "TractionClockPurpose", "TractionClockRequest",
    "TractionDecision", "TractionInputError", "TractionLedger",
    "TractionObservation", "TractionPolicy", "TractionProvenance",
    "TractionEvaluationBundle", "TractionSettlementEvidence",
    "TractionReport", "TractionTrustStore", "build_traction_observation",
    "evaluate_traction", "hash_traction_artifact", "hash_traction_policy",
    "hash_traction_trust_store", "sign_traction_plan",
    "sign_traction_clock_attestation", "verify_traction_clock_attestation",
    "verify_traction_observation", "verify_traction_plan",
]
