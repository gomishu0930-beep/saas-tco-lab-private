from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from saas_preflight.economics import Decision
from saas_preflight.models import BillingPeriod
from saas_preflight.measurement import (
    build_cohort_evidence,
    build_demand_evidence,
    build_operations_evidence,
)
from saas_preflight.preflight import evaluate_business_dossier
from saas_preflight.preview import FitStatus, PreviewPage, PreviewPlan, render_preview
from saas_preflight.release import (
    AffiliateCta,
    ApprovalDecision,
    ApprovalScope,
    CtaDecision,
    HumanApproval,
    ReleaseManifest,
    ReleaseState,
    evaluate_visibility,
    prepare_release,
    promote_release,
)
from saas_preflight.tco import calculate_vendor_plan_tco, constant_usage_scenario
from saas_preflight.readiness_builder import build_business_dossier

from test_models import make_plan
from test_measurement import (
    _cluster,
    _cohort_batch,
    _demand_batch,
    _operations_batch,
)
from test_preflight import _dossier
from test_readiness_builder import _affiliates, _plans


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_synthetic_plan_to_tco_preview_release_and_readiness() -> None:
    plan = make_plan()
    scenario = constant_usage_scenario(
        months=12,
        seats=1,
        monthly_usage=Decimal(0),
        usage_unit=None,
    )
    tco = calculate_vendor_plan_tco(plan, scenario)
    assert tco.total_minor == 13_200

    preview = PreviewPage(
        title="Synthetic end-to-end comparison",
        methodology="Canonical TCO fixture; not production evidence.",
        rendered_at=NOW,
        plans=(
            PreviewPlan(
                vendor_slug=plan.vendor_slug,
                vendor_name=plan.vendor_name,
                plan_slug=plan.plan_slug,
                plan_name=plan.plan_name,
                scenario_name="one seat / twelve months",
                region="JP",
                tax_note="synthetic tax included",
                currency=plan.currency,
                billing_period=BillingPeriod.MONTHLY,
                commitment_months=12,
                minor_unit_digits=plan.minor_unit_digits,
                total_minor=tco.total_minor,
                fit_status=FitStatus.FIT,
                fit_reason="Synthetic scenario requirements are met.",
                evidence_url="https://example.com/pricing",
                evidence_retrieved_at=NOW,
                data_expires_at=NOW + timedelta(days=7),
                rights_expires_at=NOW + timedelta(days=30),
                affiliate_expires_at=NOW + timedelta(days=30),
                affiliate_url="https://example.com/synthetic-affiliate",
                affiliate_active=True,
            ),
        ),
    )
    html = render_preview(preview, at=NOW + timedelta(minutes=1))
    assert "JPY 13,200" in html
    assert 'rel="sponsored nofollow noopener noreferrer"' in html

    manifest = ReleaseManifest(
        release_id="synthetic-release-1",
        prepared_at=NOW + timedelta(minutes=1),
        artifact_sha256=_sha(html.encode("utf-8")),
        schema_sha256="1" * 64,
        data_snapshot_sha256s=(_sha(plan.model_dump_json().encode("utf-8")),),
        rights_bundle_sha256="2" * 64,
        affiliate_bundle_sha256="3" * 64,
        data_expires_at=NOW + timedelta(days=7),
        rights_expires_at=NOW + timedelta(days=30),
        affiliate_expires_at=NOW + timedelta(days=30),
        cta=AffiliateCta(
            decision=CtaDecision.APPROVED,
            program_id="synthetic-program",
            destination_sha256="4" * 64,
            disclosure_sha256="5" * 64,
        ),
    )
    prepared = prepare_release(ReleaseState(), manifest)
    approval = HumanApproval(
        release_id=manifest.release_id,
        scope=ApprovalScope.PROMOTE,
        decision=ApprovalDecision.GO,
        approved_by="synthetic-human",
        approved_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        decision_record_sha256="6" * 64,
    )
    promoted = promote_release(
        prepared,
        manifest.release_id,
        approval,
        at=NOW + timedelta(minutes=2),
    )
    visibility = evaluate_visibility(promoted, at=NOW + timedelta(minutes=2))
    assert visibility.visible is True
    assert visibility.cta_enabled is True

    economics = evaluate_business_dossier(
        _dossier(), at=NOW + timedelta(minutes=2)
    )
    assert economics.decision is Decision.GO


def test_expiry_still_hides_an_already_promoted_synthetic_release() -> None:
    manifest = ReleaseManifest(
        release_id="synthetic-release-expiry",
        prepared_at=NOW,
        artifact_sha256="1" * 64,
        schema_sha256="2" * 64,
        data_snapshot_sha256s=("3" * 64,),
        rights_bundle_sha256="4" * 64,
        affiliate_bundle_sha256="5" * 64,
        data_expires_at=NOW + timedelta(hours=1),
        rights_expires_at=NOW + timedelta(days=1),
        affiliate_expires_at=NOW + timedelta(days=1),
        cta=AffiliateCta(decision=CtaDecision.PROHIBITED),
    )
    state = prepare_release(ReleaseState(), manifest)
    state = promote_release(
        state,
        manifest.release_id,
        HumanApproval(
            release_id=manifest.release_id,
            scope=ApprovalScope.PROMOTE,
            decision=ApprovalDecision.GO,
            approved_by="synthetic-human",
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            decision_record_sha256="6" * 64,
        ),
        at=NOW + timedelta(minutes=1),
    )

    visibility = evaluate_visibility(state, at=NOW + timedelta(hours=1))
    assert visibility.visible is False
    assert visibility.cta_enabled is False


def test_safe_summaries_flow_into_a_provenance_dossier() -> None:
    at = NOW + timedelta(hours=2)
    demand = build_demand_evidence(
        _demand_batch(clusters=(_cluster("pricing", "2000000"),)), at=at
    )
    cohort = build_cohort_evidence(_cohort_batch(), at=at)
    operations = build_operations_evidence(_operations_batch(), at=at)
    dossier = build_business_dossier(
        plans=_plans(),
        affiliate_decisions=_affiliates(),
        property_domain="example.test",
        demand=demand,
        cohort=cohort,
        operations=operations,
        at=at,
    )

    evaluation = evaluate_business_dossier(dossier, at=at)
    assert evaluation.decision is Decision.GO
    assert evaluation.economics is not None
    assert evaluation.economics.job_success_rate == Decimal("0.99")
