from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from saas_preflight.release import (
    AffiliateCta,
    ApprovalDecision,
    ApprovalError,
    ApprovalScope,
    CtaDecision,
    DuplicateReleaseError,
    ExpiredReleaseError,
    HumanApproval,
    ReleaseAction,
    ReleaseManifest,
    ReleaseState,
    RollbackError,
    VisibilityReason,
    evaluate_visibility,
    prepare_release,
    promote_release,
    rollback_release,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64
H5 = "5" * 64
H6 = "6" * 64
H7 = "7" * 64


def approved_cta() -> AffiliateCta:
    return AffiliateCta(
        decision=CtaDecision.APPROVED,
        program_id="vendor-a",
        destination_sha256=H6,
        disclosure_sha256=H7,
    )


def manifest(
    release_id: str = "release-1",
    *,
    prepared_at: datetime = NOW,
    artifact_sha256: str = H1,
    data_expires_at: datetime | None = None,
    rights_expires_at: datetime | None = None,
    affiliate_expires_at: datetime | None = None,
    cta: AffiliateCta | None = None,
    rollback_release_id: str | None = None,
    snapshots: tuple[str, ...] = (H3, H4),
) -> ReleaseManifest:
    return ReleaseManifest(
        release_id=release_id,
        prepared_at=prepared_at,
        artifact_sha256=artifact_sha256,
        schema_sha256=H2,
        data_snapshot_sha256s=snapshots,
        rights_bundle_sha256=H4,
        affiliate_bundle_sha256=H5,
        data_expires_at=data_expires_at or prepared_at + timedelta(days=30),
        rights_expires_at=rights_expires_at or prepared_at + timedelta(days=60),
        affiliate_expires_at=affiliate_expires_at or prepared_at + timedelta(days=90),
        cta=cta or approved_cta(),
        rollback_release_id=rollback_release_id,
    )


def approval(
    release_id: str,
    *,
    scope: ApprovalScope = ApprovalScope.PROMOTE,
    approved_at: datetime = NOW,
    expires_at: datetime | None = None,
    decision: ApprovalDecision = ApprovalDecision.GO,
) -> HumanApproval:
    return HumanApproval(
        release_id=release_id,
        scope=scope,
        decision=decision,
        approved_by="human-approver",
        approved_at=approved_at,
        expires_at=expires_at or approved_at + timedelta(days=7),
        decision_record_sha256=H7,
    )


def promoted_state(item: ReleaseManifest, *, at: datetime | None = None) -> ReleaseState:
    state = prepare_release(ReleaseState(), item)
    instant = at or item.prepared_at + timedelta(minutes=1)
    return promote_release(
        state,
        item.release_id,
        approval(item.release_id, approved_at=item.prepared_at),
        at=instant,
    )


def test_manifest_hash_is_deterministic_and_snapshot_order_independent() -> None:
    first = manifest(snapshots=(H3, H4))
    reordered = manifest(snapshots=(H4, H3))

    assert first.manifest_sha256 == reordered.manifest_sha256
    assert first.shortest_expiry == NOW + timedelta(days=30)
    with pytest.raises(FrozenInstanceError):
        first.release_id = "changed"  # type: ignore[misc]


def test_manifest_rejects_invalid_digest_naive_time_and_duplicate_snapshot() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        manifest(artifact_sha256="not-a-hash")
    with pytest.raises(ValueError, match="UTC"):
        manifest(prepared_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="unique"):
        manifest(snapshots=(H3, H3))


def test_prepare_is_idempotent_but_conflicting_release_id_is_rejected() -> None:
    item = manifest()
    state = prepare_release(ReleaseState(), item)

    assert prepare_release(state, item) is state
    with pytest.raises(DuplicateReleaseError):
        prepare_release(state, manifest(artifact_sha256=H2))


def test_no_current_release_is_hidden() -> None:
    result = evaluate_visibility(ReleaseState(), at=NOW)

    assert result.visible is False
    assert result.cta_enabled is False
    assert result.reasons == (VisibilityReason.NO_CURRENT_RELEASE,)


@pytest.mark.parametrize(
    ("expiry_field", "reason"),
    [
        ("data_expires_at", VisibilityReason.DATA_EXPIRED),
        ("rights_expires_at", VisibilityReason.RIGHTS_EXPIRED),
        ("affiliate_expires_at", VisibilityReason.AFFILIATE_EXPIRED),
    ],
)
def test_read_time_expiry_hides_release_and_cta(expiry_field: str, reason: VisibilityReason) -> None:
    expiry = NOW + timedelta(hours=1)
    item = manifest(**{expiry_field: expiry})
    state = promoted_state(item, at=NOW + timedelta(minutes=1))

    before = evaluate_visibility(state, at=expiry - timedelta(microseconds=1))
    expired = evaluate_visibility(state, at=expiry)
    assert before.visible is True
    assert before.cta_enabled is True
    assert before.shortest_expiry == item.shortest_expiry
    assert expired.visible is False
    assert expired.cta_enabled is False
    assert reason in expired.reasons


def test_unreviewed_cta_never_enables_link_but_content_can_be_visible() -> None:
    item = manifest(cta=AffiliateCta(decision=CtaDecision.UNREVIEWED))
    state = promoted_state(item)

    result = evaluate_visibility(state, at=NOW + timedelta(minutes=2))
    assert result.visible is True
    assert result.cta_enabled is False
    assert VisibilityReason.CTA_MISSING in result.reasons


def test_promotion_requires_matching_current_human_go_and_unexpired_inputs() -> None:
    item = manifest()
    state = prepare_release(ReleaseState(), item)

    with pytest.raises(ApprovalError, match="scope"):
        promote_release(
            state,
            item.release_id,
            approval(item.release_id, scope=ApprovalScope.ROLLBACK),
            at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ApprovalError, match="explicit GO"):
        promote_release(
            state,
            item.release_id,
            approval(item.release_id, decision=ApprovalDecision.STOP),
            at=NOW + timedelta(minutes=1),
        )

    expired_item = manifest(
        release_id="release-expired",
        data_expires_at=NOW + timedelta(minutes=1),
    )
    expired_state = prepare_release(ReleaseState(), expired_item)
    with pytest.raises(ExpiredReleaseError, match="data"):
        promote_release(
            expired_state,
            expired_item.release_id,
            approval(expired_item.release_id),
            at=NOW + timedelta(minutes=1),
        )


def test_prepare_replacement_requires_declared_current_rollback() -> None:
    state = promoted_state(manifest())

    with pytest.raises(RollbackError, match="declare"):
        prepare_release(
            state,
            manifest(
                release_id="release-2",
                prepared_at=NOW + timedelta(minutes=2),
            ),
        )


def test_promote_and_rollback_are_pure_audited_transitions() -> None:
    first = manifest()
    state1 = promoted_state(first)
    second = manifest(
        release_id="release-2",
        prepared_at=NOW + timedelta(minutes=2),
        artifact_sha256=H2,
        rollback_release_id=first.release_id,
    )
    prepared = prepare_release(state1, second)
    promoted = promote_release(
        prepared,
        second.release_id,
        approval(second.release_id, approved_at=second.prepared_at),
        at=NOW + timedelta(minutes=3),
    )

    rolled_back = rollback_release(
        promoted,
        first.release_id,
        approval(
            first.release_id,
            scope=ApprovalScope.ROLLBACK,
            approved_at=NOW + timedelta(minutes=3),
        ),
        at=NOW + timedelta(minutes=4),
    )
    assert state1.current_release_id == first.release_id
    assert promoted.current_release_id == second.release_id
    assert rolled_back.current_release_id == first.release_id
    assert rolled_back.events[-1].action is ReleaseAction.ROLLED_BACK


def test_rollback_rejects_undeclared_or_expired_target() -> None:
    first = manifest(data_expires_at=NOW + timedelta(minutes=4))
    state1 = promoted_state(first)
    second = manifest(
        release_id="release-2",
        prepared_at=NOW + timedelta(minutes=2),
        rollback_release_id=first.release_id,
    )
    promoted = promote_release(
        prepare_release(state1, second),
        second.release_id,
        approval(second.release_id, approved_at=second.prepared_at),
        at=NOW + timedelta(minutes=3),
    )

    with pytest.raises(RollbackError, match="declared"):
        rollback_release(
            promoted,
            "unknown-release",
            approval(
                "unknown-release",
                scope=ApprovalScope.ROLLBACK,
                approved_at=NOW + timedelta(minutes=3),
            ),
            at=NOW + timedelta(minutes=3, seconds=30),
        )
    with pytest.raises(ExpiredReleaseError, match="data"):
        rollback_release(
            promoted,
            first.release_id,
            approval(
                first.release_id,
                scope=ApprovalScope.ROLLBACK,
                approved_at=NOW + timedelta(minutes=3),
            ),
            at=NOW + timedelta(minutes=4),
        )
