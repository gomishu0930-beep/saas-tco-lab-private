from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from saas_preflight.models import BillingPeriod
from saas_preflight.mvp import LocalPreviewRuntime, MvpArtifact, build_mvp_artifact
from saas_preflight.preview import FitStatus, PreviewPage, PreviewPlan
from saas_preflight.release import (
    AffiliateCta,
    ApprovalDecision,
    ApprovalScope,
    CtaDecision,
    HumanApproval,
    ReleaseManifest,
    ReleaseState,
    prepare_release,
    promote_release,
    rollback_release,
)


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64
H5 = "5" * 64
H7 = "7" * 64


def page(*, active_cta: bool = True, title: str = "Synthetic TCO comparison") -> PreviewPage:
    return PreviewPage(
        title=title,
        methodology="Canonical Python TCO fixture; not production evidence.",
        rendered_at=NOW,
        affiliate_disclosure="広告リンクを含む場合はこの判断領域に表示します。",
        plans=(
            PreviewPlan(
                vendor_slug="sample-vendor",
                vendor_name="Sample Vendor",
                plan_slug="basic",
                plan_name="Basic",
                scenario_name="one seat / twelve months",
                region="JP",
                tax_note="synthetic tax included",
                currency="JPY",
                billing_period=BillingPeriod.MONTHLY,
                commitment_months=12,
                minor_unit_digits=0,
                total_minor=13200,
                fit_status=FitStatus.FIT,
                fit_reason="Synthetic requirements are met.",
                evidence_url="https://example.com/synthetic-pricing",
                evidence_retrieved_at=NOW - timedelta(hours=1),
                data_expires_at=NOW + timedelta(days=7),
                rights_expires_at=NOW + timedelta(days=30),
                affiliate_expires_at=(
                    NOW + timedelta(days=10) if active_cta else None
                ),
                affiliate_url=(
                    "https://example.com/synthetic-affiliate" if active_cta else None
                ),
                affiliate_active=active_cta,
            ),
        ),
    )


def manifest(
    artifact: MvpArtifact,
    *,
    release_id: str = "release-1",
    prepared_at: datetime = NOW,
    cta: AffiliateCta | None = None,
    rollback_release_id: str | None = None,
    expiry: datetime | None = None,
) -> ReleaseManifest:
    selected_cta = cta or AffiliateCta(
        decision=CtaDecision.APPROVED,
        program_id="synthetic-program",
        destination_sha256=artifact.destination_bundle_sha256,
        disclosure_sha256=artifact.disclosure_sha256,
    )
    limit = expiry or NOW + timedelta(days=6)
    return ReleaseManifest(
        release_id=release_id,
        prepared_at=prepared_at,
        artifact_sha256=artifact.artifact_sha256,
        schema_sha256=H2,
        data_snapshot_sha256s=(H3,),
        rights_bundle_sha256=H4,
        affiliate_bundle_sha256=H5,
        data_expires_at=limit,
        rights_expires_at=limit + timedelta(days=1),
        affiliate_expires_at=limit + timedelta(days=2),
        cta=selected_cta,
        rollback_release_id=rollback_release_id,
    )


def approval(
    release_id: str,
    *,
    at: datetime,
    scope: ApprovalScope = ApprovalScope.PROMOTE,
) -> HumanApproval:
    return HumanApproval(
        release_id=release_id,
        scope=scope,
        decision=ApprovalDecision.GO,
        approved_by="human-approver",
        approved_at=at,
        expires_at=at + timedelta(days=1),
        decision_record_sha256=H7,
    )


def promoted(artifact: MvpArtifact, *, item: ReleaseManifest | None = None) -> ReleaseState:
    candidate = item or manifest(artifact)
    state = prepare_release(ReleaseState(), candidate)
    return promote_release(
        state,
        candidate.release_id,
        approval(candidate.release_id, at=candidate.prepared_at),
        at=candidate.prepared_at + timedelta(seconds=1),
    )


def test_artifact_is_content_addressed_immutable_and_accessible() -> None:
    artifact = build_mvp_artifact(page(), at=NOW)

    assert len(artifact.artifact_sha256) == 64
    assert artifact.has_active_cta is True
    assert "<main>" in artifact.comparison_html
    assert "<header>" in artifact.comparison_html
    assert "<footer>" in artifact.comparison_html
    assert 'aria-label="広告表示"' in artifact.comparison_html
    with pytest.raises(FrozenInstanceError):
        artifact.home_html = "changed"  # type: ignore[misc]


def test_active_cta_requires_exact_destination_and_disclosure_hashes() -> None:
    artifact = build_mvp_artifact(page(), at=NOW)
    good = LocalPreviewRuntime(artifact, promoted(artifact)).handle(
        "/comparison/?scenario=synthetic", at=NOW + timedelta(minutes=1)
    )

    assert good.status == 200
    assert "synthetic-affiliate" in good.body
    assert 'rel="sponsored nofollow noopener noreferrer"' in good.body

    wrong_cta = AffiliateCta(
        decision=CtaDecision.APPROVED,
        program_id="synthetic-program",
        destination_sha256="6" * 64,
        disclosure_sha256=artifact.disclosure_sha256,
    )
    redacted_runtime = LocalPreviewRuntime(
        artifact,
        promoted(artifact, item=manifest(artifact, cta=wrong_cta)),
    )
    redacted = redacted_runtime.handle(
        "/comparison/", at=NOW + timedelta(minutes=1)
    )
    assert redacted.status == 200
    assert "JPY 13,200" in redacted.body
    assert "synthetic-affiliate" not in redacted.body
    assert "公式サイトへ" not in redacted.body


def test_expiry_boundary_hides_numbers_and_cta_fail_closed() -> None:
    artifact = build_mvp_artifact(page(), at=NOW)
    expiry = NOW + timedelta(hours=1)
    runtime = LocalPreviewRuntime(
        artifact,
        promoted(artifact, item=manifest(artifact, expiry=expiry)),
    )

    before = runtime.handle(
        "/comparison/", at=expiry - timedelta(microseconds=1)
    )
    expired = runtime.handle("/comparison/", at=expiry)
    assert before.status == 200
    assert "JPY 13,200" in before.body
    assert expired.status == 503
    assert "JPY 13,200" not in expired.body
    assert "synthetic-affiliate" not in expired.body


def test_artifact_mismatch_never_serves_candidate_content() -> None:
    artifact = build_mvp_artifact(page(), at=NOW)
    altered = MvpArtifact(
        built_at=artifact.built_at,
        home_html=artifact.home_html + "<!-- altered -->",
        comparison_html=artifact.comparison_html,
        comparison_redacted_html=artifact.comparison_redacted_html,
        methodology_html=artifact.methodology_html,
        disclosure_html=artifact.disclosure_html,
        destination_bundle_sha256=artifact.destination_bundle_sha256,
        disclosure_sha256=artifact.disclosure_sha256,
        has_active_cta=artifact.has_active_cta,
    )
    response = LocalPreviewRuntime(altered, promoted(artifact)).handle(
        "/", at=NOW + timedelta(minutes=1)
    )

    assert response.status == 503
    assert "altered" not in response.body
    assert "13,200" not in response.body


def test_security_robots_methods_unknown_routes_and_health_are_safe() -> None:
    artifact = build_mvp_artifact(page(active_cta=False), at=NOW)
    runtime = LocalPreviewRuntime(
        artifact,
        promoted(
            artifact,
            item=manifest(
                artifact,
                cta=AffiliateCta(decision=CtaDecision.PROHIBITED),
            ),
        ),
    )

    robots = runtime.handle("/robots.txt", at=NOW + timedelta(minutes=1))
    assert robots.status == 200
    assert robots.body == "User-agent: *\nDisallow: /\n"
    assert robots.header("X-Robots-Tag") == "noindex, nofollow, noarchive, nosnippet"

    comparison = runtime.handle("/comparison/", at=NOW + timedelta(minutes=1))
    assert comparison.status == 200
    assert "frame-ancestors 'none'" in (comparison.header("Content-Security-Policy") or "")
    assert comparison.header("Cache-Control") == "no-store"
    assert "synthetic-affiliate" not in comparison.body

    head = runtime.handle("/methodology/", method="HEAD", at=NOW + timedelta(minutes=1))
    assert head.status == 200
    assert head.body == ""
    rejected = runtime.handle("/comparison/", method="POST", at=NOW + timedelta(minutes=1))
    assert rejected.status == 405
    assert rejected.header("Allow") == "GET, HEAD"
    assert runtime.handle("/missing/", at=NOW + timedelta(minutes=1)).status == 404
    health = runtime.handle("/healthz", at=NOW + timedelta(minutes=1))
    assert health.body == "ok\n"
    assert "13,200" not in health.body


def test_rollback_only_serves_the_reselected_artifact() -> None:
    first = build_mvp_artifact(page(title="First candidate"), at=NOW)
    first_manifest = manifest(first)
    first_state = promoted(first, item=first_manifest)

    second_at = NOW + timedelta(minutes=2)
    second = build_mvp_artifact(page(title="Second candidate"), at=second_at)
    second_manifest = manifest(
        second,
        release_id="release-2",
        prepared_at=second_at,
        rollback_release_id=first_manifest.release_id,
    )
    second_state = promote_release(
        prepare_release(first_state, second_manifest),
        second_manifest.release_id,
        approval(second_manifest.release_id, at=second_at),
        at=second_at + timedelta(seconds=1),
    )
    rolled_back = rollback_release(
        second_state,
        first_manifest.release_id,
        approval(
            first_manifest.release_id,
            at=second_at + timedelta(seconds=2),
            scope=ApprovalScope.ROLLBACK,
        ),
        at=second_at + timedelta(seconds=3),
    )

    first_response = LocalPreviewRuntime(first, rolled_back).handle(
        "/comparison/", at=second_at + timedelta(minutes=1)
    )
    second_response = LocalPreviewRuntime(second, rolled_back).handle(
        "/comparison/", at=second_at + timedelta(minutes=1)
    )
    assert first_response.status == 200
    assert "First candidate" in first_response.body
    assert second_response.status == 503
    assert "Second candidate" not in second_response.body


def test_build_rejects_expired_rights_and_affiliate() -> None:
    expired_rights = page().model_copy(
        update={
            "plans": (
                page().plans[0].model_copy(update={"rights_expires_at": NOW}),
            )
        }
    )
    with pytest.raises(ValueError, match="expired data or rights"):
        build_mvp_artifact(expired_rights, at=NOW)

    expired_affiliate = page().model_copy(
        update={
            "plans": (
                page().plans[0].model_copy(update={"affiliate_expires_at": NOW}),
            )
        }
    )
    with pytest.raises(ValueError, match="expired affiliate"):
        build_mvp_artifact(expired_affiliate, at=NOW)
