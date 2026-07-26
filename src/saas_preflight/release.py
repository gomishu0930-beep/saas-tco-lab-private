"""Pure, fail-closed release preparation, promotion, and visibility gates.

This module performs no publication, filesystem, database, cloud, or network
operation.  It only produces immutable local state that an Integration/Release
Operator can inspect before a separately approved external action.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$")


class ReleaseError(ValueError):
    """Base class for rejected release-state transitions."""


class DuplicateReleaseError(ReleaseError):
    """A release id was reused for different immutable content."""


class UnknownReleaseError(ReleaseError):
    """A requested release does not exist in prepared state."""


class ExpiredReleaseError(ReleaseError):
    """A release is not valid at the requested transition time."""


class ApprovalError(ReleaseError):
    """A Human approval reference is missing, invalid, or out of scope."""


class RollbackError(ReleaseError):
    """A rollback does not target the declared, previously promoted release."""


class CtaDecision(str, Enum):
    APPROVED = "approved"
    PROHIBITED = "prohibited"
    UNREVIEWED = "unreviewed"


class ApprovalDecision(str, Enum):
    GO = "go"
    STOP = "stop"
    CONDITIONAL = "conditional"


class ApprovalScope(str, Enum):
    PROMOTE = "promote"
    ROLLBACK = "rollback"


class ReleaseAction(str, Enum):
    PREPARED = "prepared"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


class VisibilityReason(str, Enum):
    NO_CURRENT_RELEASE = "no_current_release"
    DATA_EXPIRED = "data_expired"
    RIGHTS_EXPIRED = "rights_expired"
    AFFILIATE_EXPIRED = "affiliate_expired"
    CTA_MISSING = "cta_missing"
    CTA_UNAPPROVED = "cta_unapproved"


def _require_exact_string(value: object, field_name: str, *, max_length: int = 200) -> str:
    if type(value) is not str or not value or len(value) > max_length:
        raise TypeError(f"{field_name} must be a non-empty string up to {max_length} characters")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    text = _require_exact_string(value, field_name, max_length=120)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a lowercase stable identifier")
    return text


def _require_sha256(value: object, field_name: str) -> str:
    text = _require_exact_string(value, field_name, max_length=64)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _require_utc(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class AffiliateCta:
    """Hash-only CTA configuration; no live affiliate URL is stored here."""

    decision: CtaDecision
    program_id: str | None = None
    destination_sha256: str | None = None
    disclosure_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.decision) is not CtaDecision:
            raise TypeError("decision must be CtaDecision")
        if self.decision is CtaDecision.APPROVED:
            _require_identifier(self.program_id, "program_id")
            _require_sha256(self.destination_sha256, "destination_sha256")
            _require_sha256(self.disclosure_sha256, "disclosure_sha256")
            return
        if any(
            value is not None
            for value in (self.program_id, self.destination_sha256, self.disclosure_sha256)
        ):
            raise ValueError("unapproved CTA cannot carry program or destination data")


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    """Content-addressed immutable release candidate."""

    release_id: str
    prepared_at: datetime
    artifact_sha256: str
    schema_sha256: str
    data_snapshot_sha256s: tuple[str, ...]
    rights_bundle_sha256: str
    affiliate_bundle_sha256: str
    data_expires_at: datetime
    rights_expires_at: datetime
    affiliate_expires_at: datetime
    cta: AffiliateCta
    rollback_release_id: str | None = None
    manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.release_id, "release_id")
        _require_utc(self.prepared_at, "prepared_at")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        _require_sha256(self.schema_sha256, "schema_sha256")
        _require_sha256(self.rights_bundle_sha256, "rights_bundle_sha256")
        _require_sha256(self.affiliate_bundle_sha256, "affiliate_bundle_sha256")
        if type(self.data_snapshot_sha256s) is not tuple or not self.data_snapshot_sha256s:
            raise TypeError("data_snapshot_sha256s must be a non-empty tuple")
        for index, digest in enumerate(self.data_snapshot_sha256s):
            _require_sha256(digest, f"data_snapshot_sha256s[{index}]")
        if len(self.data_snapshot_sha256s) != len(set(self.data_snapshot_sha256s)):
            raise ValueError("data snapshot digests must be unique")
        for name, expiry in (
            ("data_expires_at", self.data_expires_at),
            ("rights_expires_at", self.rights_expires_at),
            ("affiliate_expires_at", self.affiliate_expires_at),
        ):
            _require_utc(expiry, name)
            if expiry <= self.prepared_at:
                raise ValueError(f"{name} must be later than prepared_at")
        if type(self.cta) is not AffiliateCta:
            raise TypeError("cta must be AffiliateCta")
        if self.rollback_release_id is not None:
            _require_identifier(self.rollback_release_id, "rollback_release_id")
            if self.rollback_release_id == self.release_id:
                raise ValueError("a release cannot roll back to itself")
        object.__setattr__(self, "manifest_sha256", self._calculate_hash())

    @property
    def shortest_expiry(self) -> datetime:
        return min(
            self.data_expires_at,
            self.rights_expires_at,
            self.affiliate_expires_at,
        )

    def _calculate_hash(self) -> str:
        cta_payload = {
            "decision": self.cta.decision.value,
            "program_id": self.cta.program_id,
            "destination_sha256": self.cta.destination_sha256,
            "disclosure_sha256": self.cta.disclosure_sha256,
        }
        payload = {
            "release_id": self.release_id,
            "prepared_at": _utc_text(self.prepared_at),
            "artifact_sha256": self.artifact_sha256,
            "schema_sha256": self.schema_sha256,
            "data_snapshot_sha256s": sorted(self.data_snapshot_sha256s),
            "rights_bundle_sha256": self.rights_bundle_sha256,
            "affiliate_bundle_sha256": self.affiliate_bundle_sha256,
            "data_expires_at": _utc_text(self.data_expires_at),
            "rights_expires_at": _utc_text(self.rights_expires_at),
            "affiliate_expires_at": _utc_text(self.affiliate_expires_at),
            "cta": cta_payload,
            "rollback_release_id": self.rollback_release_id,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HumanApproval:
    """Reference to a separately stored signed Human decision artifact."""

    release_id: str
    scope: ApprovalScope
    decision: ApprovalDecision
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    decision_record_sha256: str

    def __post_init__(self) -> None:
        _require_identifier(self.release_id, "release_id")
        if type(self.scope) is not ApprovalScope:
            raise TypeError("scope must be ApprovalScope")
        if type(self.decision) is not ApprovalDecision:
            raise TypeError("decision must be ApprovalDecision")
        _require_exact_string(self.approved_by, "approved_by", max_length=120)
        _require_utc(self.approved_at, "approved_at")
        _require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expires_at must be later than approved_at")
        _require_sha256(self.decision_record_sha256, "decision_record_sha256")


@dataclass(frozen=True, slots=True)
class ReleaseEvent:
    action: ReleaseAction
    release_id: str
    occurred_at: datetime
    previous_release_id: str | None = None
    decision_record_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.action) is not ReleaseAction:
            raise TypeError("action must be ReleaseAction")
        _require_identifier(self.release_id, "release_id")
        _require_utc(self.occurred_at, "occurred_at")
        if self.previous_release_id is not None:
            _require_identifier(self.previous_release_id, "previous_release_id")
        if self.action is ReleaseAction.PREPARED:
            if self.previous_release_id is not None or self.decision_record_sha256 is not None:
                raise ValueError("prepare event cannot contain promotion approval data")
        else:
            _require_sha256(self.decision_record_sha256, "decision_record_sha256")


@dataclass(frozen=True, slots=True)
class ReleaseState:
    manifests: tuple[ReleaseManifest, ...] = ()
    events: tuple[ReleaseEvent, ...] = ()
    current_release_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.manifests) is not tuple or type(self.events) is not tuple:
            raise TypeError("manifests and events must be tuples")
        if any(type(manifest) is not ReleaseManifest for manifest in self.manifests):
            raise TypeError("manifests must contain ReleaseManifest values")
        if any(type(event) is not ReleaseEvent for event in self.events):
            raise TypeError("events must contain ReleaseEvent values")
        release_ids = [manifest.release_id for manifest in self.manifests]
        if len(release_ids) != len(set(release_ids)):
            raise ValueError("release state contains duplicate release ids")
        known = set(release_ids)
        if any(event.release_id not in known for event in self.events):
            raise ValueError("release event refers to an unknown manifest")
        pointer: str | None = None
        prepared: set[str] = set()
        previous_time: datetime | None = None
        for event in self.events:
            if previous_time is not None and event.occurred_at < previous_time:
                raise ValueError("release events must be in UTC chronological order")
            previous_time = event.occurred_at
            if event.action is ReleaseAction.PREPARED:
                if event.release_id in prepared:
                    raise ValueError("release can only be prepared once")
                prepared.add(event.release_id)
                continue
            if event.release_id not in prepared:
                raise ValueError("release must be prepared before promotion")
            if event.previous_release_id != pointer:
                raise ValueError("release event previous pointer does not match state history")
            pointer = event.release_id
        if prepared != known:
            raise ValueError("every manifest must have exactly one prepare event")
        if self.current_release_id is not None:
            _require_identifier(self.current_release_id, "current_release_id")
            if self.current_release_id not in known:
                raise ValueError("current release must exist in manifests")
        if self.current_release_id != pointer:
            raise ValueError("current release does not match the event history")

    def get(self, release_id: str) -> ReleaseManifest:
        for manifest in self.manifests:
            if manifest.release_id == release_id:
                return manifest
        raise UnknownReleaseError(f"unknown release: {release_id}")


@dataclass(frozen=True, slots=True)
class ReleaseVisibility:
    checked_at: datetime
    release_id: str | None
    manifest_sha256: str | None
    shortest_expiry: datetime | None
    visible: bool
    cta_enabled: bool
    reasons: tuple[VisibilityReason, ...]

    def __post_init__(self) -> None:
        _require_utc(self.checked_at, "checked_at")
        if self.release_id is None:
            if self.manifest_sha256 is not None or self.shortest_expiry is not None:
                raise ValueError("missing release cannot have manifest metadata")
        else:
            _require_identifier(self.release_id, "release_id")
            _require_sha256(self.manifest_sha256, "manifest_sha256")
            _require_utc(self.shortest_expiry, "shortest_expiry")
        if type(self.visible) is not bool or type(self.cta_enabled) is not bool:
            raise TypeError("visibility flags must be booleans")
        if self.cta_enabled and not self.visible:
            raise ValueError("CTA cannot be enabled for hidden content")
        if type(self.reasons) is not tuple or any(
            type(reason) is not VisibilityReason for reason in self.reasons
        ):
            raise TypeError("reasons must be a tuple of VisibilityReason")


def prepare_release(state: ReleaseState, manifest: ReleaseManifest) -> ReleaseState:
    """Add an immutable candidate; exact repeats are idempotent."""

    if type(state) is not ReleaseState or type(manifest) is not ReleaseManifest:
        raise TypeError("prepare_release requires ReleaseState and ReleaseManifest")
    for existing in state.manifests:
        if existing.release_id != manifest.release_id:
            continue
        if existing.manifest_sha256 == manifest.manifest_sha256:
            return state
        raise DuplicateReleaseError(
            f"release id already refers to another manifest: {manifest.release_id}"
        )
    if state.current_release_id is not None and manifest.rollback_release_id is None:
        raise RollbackError("prepared replacement must declare the current release")
    if manifest.rollback_release_id is not None:
        if manifest.rollback_release_id not in {
            existing.release_id for existing in state.manifests
        }:
            raise RollbackError("declared rollback release has not been prepared")
        if state.current_release_id != manifest.rollback_release_id:
            raise RollbackError("prepared replacement must declare the current release")
    event = ReleaseEvent(
        action=ReleaseAction.PREPARED,
        release_id=manifest.release_id,
        occurred_at=manifest.prepared_at,
    )
    return ReleaseState(
        manifests=state.manifests + (manifest,),
        events=state.events + (event,),
        current_release_id=state.current_release_id,
    )


def promote_release(
    state: ReleaseState,
    release_id: str,
    approval: HumanApproval,
    *,
    at: datetime,
) -> ReleaseState:
    """Purely move the local current pointer after all gates pass."""

    instant = _require_utc(at, "at")
    manifest = state.get(_require_identifier(release_id, "release_id"))
    _validate_approval(approval, release_id, ApprovalScope.PROMOTE, at=instant)
    _require_manifest_current(manifest, at=instant)
    if state.current_release_id == release_id:
        return state
    if state.current_release_id is not None:
        if manifest.rollback_release_id != state.current_release_id:
            raise RollbackError(
                "replacement manifest must declare the current release as rollback target"
            )
    event = ReleaseEvent(
        action=ReleaseAction.PROMOTED,
        release_id=release_id,
        previous_release_id=state.current_release_id,
        occurred_at=instant,
        decision_record_sha256=approval.decision_record_sha256,
    )
    return ReleaseState(
        manifests=state.manifests,
        events=state.events + (event,),
        current_release_id=release_id,
    )


def rollback_release(
    state: ReleaseState,
    target_release_id: str,
    approval: HumanApproval,
    *,
    at: datetime,
) -> ReleaseState:
    """Move to the declared previously promoted rollback target."""

    instant = _require_utc(at, "at")
    if state.current_release_id is None:
        raise RollbackError("cannot roll back without a current release")
    current = state.get(state.current_release_id)
    target_id = _require_identifier(target_release_id, "target_release_id")
    if current.rollback_release_id != target_id:
        raise RollbackError("target is not the current manifest's declared rollback release")
    previously_promoted = {
        event.release_id
        for event in state.events
        if event.action in (ReleaseAction.PROMOTED, ReleaseAction.ROLLED_BACK)
    }
    if target_id not in previously_promoted:
        raise RollbackError("rollback target was never promoted")
    target = state.get(target_id)
    _validate_approval(approval, target_id, ApprovalScope.ROLLBACK, at=instant)
    _require_manifest_current(target, at=instant)
    event = ReleaseEvent(
        action=ReleaseAction.ROLLED_BACK,
        release_id=target_id,
        previous_release_id=state.current_release_id,
        occurred_at=instant,
        decision_record_sha256=approval.decision_record_sha256,
    )
    return ReleaseState(
        manifests=state.manifests,
        events=state.events + (event,),
        current_release_id=target_id,
    )


def evaluate_visibility(state: ReleaseState, *, at: datetime) -> ReleaseVisibility:
    """Evaluate every request at read time; static build freshness is insufficient."""

    instant = _require_utc(at, "at")
    if state.current_release_id is None:
        return ReleaseVisibility(
            checked_at=instant,
            release_id=None,
            manifest_sha256=None,
            shortest_expiry=None,
            visible=False,
            cta_enabled=False,
            reasons=(VisibilityReason.NO_CURRENT_RELEASE,),
        )
    manifest = state.get(state.current_release_id)
    reasons: list[VisibilityReason] = []
    if instant >= manifest.data_expires_at:
        reasons.append(VisibilityReason.DATA_EXPIRED)
    if instant >= manifest.rights_expires_at:
        reasons.append(VisibilityReason.RIGHTS_EXPIRED)
    if instant >= manifest.affiliate_expires_at:
        reasons.append(VisibilityReason.AFFILIATE_EXPIRED)

    visible = not reasons
    if manifest.cta.decision is CtaDecision.APPROVED:
        cta_enabled = visible
    else:
        cta_enabled = False
        reasons.append(
            VisibilityReason.CTA_MISSING
            if manifest.cta.decision is CtaDecision.UNREVIEWED
            else VisibilityReason.CTA_UNAPPROVED
        )
    return ReleaseVisibility(
        checked_at=instant,
        release_id=manifest.release_id,
        manifest_sha256=manifest.manifest_sha256,
        shortest_expiry=manifest.shortest_expiry,
        visible=visible,
        cta_enabled=cta_enabled,
        reasons=tuple(reasons),
    )


def _validate_approval(
    approval: HumanApproval,
    release_id: str,
    scope: ApprovalScope,
    *,
    at: datetime,
) -> None:
    if type(approval) is not HumanApproval:
        raise TypeError("approval must be HumanApproval")
    if approval.release_id != release_id or approval.scope is not scope:
        raise ApprovalError("approval scope or release id does not match the transition")
    if approval.decision is not ApprovalDecision.GO:
        raise ApprovalError("only an explicit GO decision permits this transition")
    if not (approval.approved_at <= at < approval.expires_at):
        raise ApprovalError("approval is not effective at transition time")


def _require_manifest_current(manifest: ReleaseManifest, *, at: datetime) -> None:
    expired: list[str] = []
    if at >= manifest.data_expires_at:
        expired.append("data")
    if at >= manifest.rights_expires_at:
        expired.append("rights")
    if at >= manifest.affiliate_expires_at:
        expired.append("affiliate")
    if expired:
        raise ExpiredReleaseError("release has expired " + ", ".join(expired) + " input")


__all__ = [
    "AffiliateCta",
    "ApprovalDecision",
    "ApprovalError",
    "ApprovalScope",
    "CtaDecision",
    "DuplicateReleaseError",
    "ExpiredReleaseError",
    "HumanApproval",
    "ReleaseAction",
    "ReleaseError",
    "ReleaseEvent",
    "ReleaseManifest",
    "ReleaseState",
    "ReleaseVisibility",
    "RollbackError",
    "UnknownReleaseError",
    "VisibilityReason",
    "evaluate_visibility",
    "prepare_release",
    "promote_release",
    "rollback_release",
]
