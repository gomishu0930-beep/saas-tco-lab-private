from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from saas_preflight.control_cycle import (
    SigningRole,
    create_verification_key,
    sign_gold_report_attestation,
)
from saas_preflight.goldset import evaluate_goldset
from saas_preflight.launch_semantics import (
    AffiliateSemanticPacket,
    DeploymentPublicationSemanticPacket,
    DeploymentReadinessFacts,
    DeploymentReadinessRecord,
    GoldSemanticPacket,
    LaunchSemanticPacket,
    LaunchSemanticScope,
    MeasurementSemanticPacket,
    ProductionSemanticPacket,
    PublicationContentReadback,
    PublicationDisclosureReadback,
    PublicationIndexabilityReadback,
    PublicationReadinessFacts,
    PublicationReadinessRecord,
    RightsSemanticPacket,
    build_launch_semantic_authority_pins,
    hash_launch_semantic_packet,
    sign_deployment_readiness_record,
    sign_publication_readiness_record,
)
from saas_preflight.measurement_integrity import (
    AffiliateAcceptedClick,
    CohortIntegrityBatch,
    CurrentTransaction,
    MeasurementAuthorityPins,
    MeasurementBoundDossier,
    MeasurementDataset,
    MeasurementIntegrityRuntime,
    PayoutRow,
    PayoutStatement,
    QualifiedSession,
    ValidOutboundClick,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    sign_measurement_bundle_index,
    sign_measurement_run_plan,
    sign_producer_attestation,
)
from saas_preflight.production_readiness import (
    ProductionEvidenceProvenance,
    ProductionIntegrationCheck,
    REQUIRED_PRODUCTION_INTEGRATION_CHECKS,
    ReadinessAttestationDecision,
    build_production_integration_bundle,
    evaluate_production_integration_readiness,
    hash_production_integration_evidence,
    sign_production_tco_qa_attestation,
)
from saas_preflight.readiness_builder import (
    AffiliateDecisionBatch,
    AffiliateProgramDecision,
    AffiliateReviewDecision,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)
from saas_preflight.release_assurance import evaluate_local_assurance
from saas_preflight.traction_control import P12AuthorityPacket

import test_goldset as gold
import test_measurement_integrity as measurement
import test_production_readiness as production
import test_release_assurance as assurance


EVALUATED_AT = production.AT


def _affiliate_decisions(plans) -> tuple[AffiliateProgramDecision, ...]:
    return tuple(
        AffiliateProgramDecision(
            partner_id=f"partner-{suffix}",
            vendor_slug=f"vendor-{suffix}",
            property_domain="synthetic.invalid",
            territory="JP",
            decision=AffiliateReviewDecision.APPROVED,
            reviewed_at=EVALUATED_AT - timedelta(days=1),
            review_due_at=EVALUATED_AT + timedelta(days=30),
            reviewed_by="semantic-human",
            decision_record_sha256=measurement._sha(f"affiliate:{suffix}"),
            program_id=f"program-{suffix}",
            destination_sha256=measurement._sha(f"destination:{suffix}"),
            disclosure_sha256=measurement._sha(f"disclosure:{suffix}"),
        )
        for suffix in ("a", "b", "c")
    )


def _high_demand(batch):
    clusters = tuple(
        item.model_copy(update={"deduplicated_monthly_volume": Decimal("1000000")})
        for item in batch.summary.clusters
    )
    return batch.model_copy(
        update={"summary": batch.summary.model_copy(update={"clusters": clusters})}
    )


def _mature_cohort(batch: CohortIntegrityBatch) -> CohortIntegrityBatch:
    sessions = list(batch.qualified_sessions)
    outbound = list(batch.valid_outbound_clicks)
    for number in range(len(sessions), 1000):
        sessions.append(
            QualifiedSession(
                session_id_sha256=measurement._sha(f"session:{number}"),
                qualified_at=measurement.START_UTC
                + timedelta(days=2, seconds=number),
            )
        )
        outbound.append(
            ValidOutboundClick(
                click_id_sha256=measurement._sha(f"outbound:{number}"),
                session_id_sha256=measurement._sha(f"session:{number}"),
                partner_id=("partner-a", "partner-b", "partner-c")[number % 3],
                clicked_at=measurement.START_UTC
                + timedelta(days=2, hours=1, seconds=number),
            )
        )
    scaled_transactions = tuple(
        CurrentTransaction.model_validate(
            item.model_copy(update={"amount": item.amount * Decimal(1000)}).model_dump()
        )
        for item in batch.transactions
    )
    scaled_rows = tuple(
        PayoutRow.model_validate(
            item.model_copy(update={"amount": item.amount * Decimal(1000)}).model_dump()
        )
        for item in batch.payout_rows
    )
    statement = PayoutStatement.model_validate(
        batch.payout_statement.model_copy(
            update={
                "gross_amount": batch.payout_statement.gross_amount * Decimal(1000),
                "net_amount": batch.payout_statement.net_amount * Decimal(1000),
            }
        ).model_dump()
    )
    return CohortIntegrityBatch.model_validate(
        batch.model_copy(
            update={
                "qualified_sessions": tuple(sessions),
                "valid_outbound_clicks": tuple(outbound),
                "transactions": scaled_transactions,
                "payout_rows": scaled_rows,
                "payout_statement": statement,
            }
        ).model_dump()
    )


def _measurement_packet(
    plans,
    decisions,
    *,
    release_identity_sha256: str,
    release_artifact_sha256: str,
    deployment_candidate_sha256: str,
) -> MeasurementSemanticPacket:
    original = {
        name: getattr(measurement, name)
        for name in ("START", "END", "START_UTC", "END_UTC", "AT")
    }
    local_at = EVALUATED_AT.astimezone(measurement.TOKYO)
    end_local = local_at.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = end_local - timedelta(days=30)
    measurement.START = start_local
    measurement.END = end_local
    measurement.START_UTC = start_local.astimezone(timezone.utc)
    measurement.END_UTC = end_local.astimezone(timezone.utc)
    measurement.AT = EVALUATED_AT
    try:
        return _measurement_packet_at_current_clock(
            plans,
            decisions,
            release_identity_sha256=release_identity_sha256,
            release_artifact_sha256=release_artifact_sha256,
            deployment_candidate_sha256=deployment_candidate_sha256,
        )
    finally:
        for name, value in original.items():
            setattr(measurement, name, value)


def _measurement_packet_at_current_clock(
    plans,
    decisions,
    *,
    release_identity_sha256: str,
    release_artifact_sha256: str,
    deployment_candidate_sha256: str,
) -> MeasurementSemanticPacket:
    context = measurement._bundle()
    definition = context["plan"].definition.model_copy(
        update={
            "fault_target_release_sha256": release_identity_sha256,
            "fault_target_artifact_sha256": release_artifact_sha256,
            "fault_target_schema_sha256": deployment_candidate_sha256,
        }
    )
    plan = sign_measurement_run_plan(
        definition,
        context["keys"]["human"],
        issuer=context["plan"].issuer,
        issued_at=context["plan"].issued_at,
        expires_at=context["plan"].expires_at,
    )
    operations = context["operations"].model_copy(
        update={
            "fault_exercises": tuple(
                row.model_copy(
                    update={
                        "target_release_sha256": release_identity_sha256,
                        "target_artifact_sha256": release_artifact_sha256,
                        "target_schema_sha256": deployment_candidate_sha256,
                    }
                )
                for row in context["operations"].fault_exercises
            )
        }
    )
    demand = _high_demand(context["demand"])
    cohort = _mature_cohort(context["cohort"])
    keys = context["keys"]
    issued = measurement.END_UTC + timedelta(hours=2)
    expires = EVALUATED_AT + timedelta(days=7)
    demand_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.DEMAND,
        demand,
        measurement._coverage(demand, "demand"),
        keys["demand"],
        issuer="demand-producer",
        issued_at=issued,
        expires_at=expires,
    )
    cohort_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.COHORT,
        cohort,
        measurement._coverage(cohort, "cohort"),
        keys["cohort"],
        issuer="cohort-producer",
        issued_at=issued + timedelta(minutes=1),
        expires_at=expires,
    )
    operations_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.OPERATIONS,
        operations,
        measurement._coverage(operations, "operations"),
        keys["operations"],
        issuer="operations-producer",
        issued_at=issued + timedelta(minutes=2),
        expires_at=expires,
    )
    index = sign_measurement_bundle_index(
        plan,
        demand,
        cohort,
        operations,
        demand_attestation,
        cohort_attestation,
        operations_attestation,
        keys["indexer"],
        issuer="measurement-indexer",
        captured_at=measurement.END_UTC,
        issued_at=issued + timedelta(hours=1),
        expires_at=expires,
    )
    pins = MeasurementAuthorityPins(
        expected_policy_sha256=hash_measurement_policy(context["policy"]),
        expected_trust_store_sha256=hash_measurement_trust_store(context["trust"]),
        expected_run_id=plan.definition.run_id,
        expected_bundle_index_sha256=hash_signed_artifact(index),
    )
    report = MeasurementIntegrityRuntime(
        context["policy"], context["trust"], keys["qa"], pins
    ).evaluate(
        plan,
        demand,
        cohort,
        operations,
        demand_attestation,
        cohort_attestation,
        operations_attestation,
        index,
        at=EVALUATED_AT,
    )
    dossier = build_business_dossier(
        plans=plans,
        affiliate_decisions=decisions,
        property_domain="synthetic.invalid",
        demand=report.demand,
        cohort=report.cohort,
        operations=report.operations,
        at=EVALUATED_AT,
    )
    bound = MeasurementBoundDossier(
        report=report,
        dossier=dossier,
        dossier_sha256=hash_signed_artifact(dossier),
    )
    authority_packet = P12AuthorityPacket(
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=pins,
        plan=plan,
        demand_batch=demand,
        cohort_batch=cohort,
        operations_batch=operations,
        demand_attestation=demand_attestation,
        cohort_attestation=cohort_attestation,
        operations_attestation=operations_attestation,
        bundle_index=index,
        report=report,
    )
    return MeasurementSemanticPacket(
        authority_packet=authority_packet,
        bound_dossier=bound,
    )


def build_semantic_context(*, candidate_manifest_sha256: str | None = None):
    goldset, candidates, plans = gold.full_fixture()
    plans = tuple(sorted(plans, key=lambda item: (item.vendor_slug, item.plan_slug, str(item.snapshot_id))))
    candidates = candidates.model_copy(
        update={
            "plans": tuple(
                sorted(
                    candidates.plans,
                    key=lambda item: (
                        item.plan.vendor_slug,
                        item.plan.plan_slug,
                        str(item.plan.snapshot_id),
                    ),
                )
            )
        }
    )
    decisions = _affiliate_decisions(plans)
    selected_manifest = assurance.manifest()
    release_identity_sha256 = measurement._sha(selected_manifest.release_id)
    measurement_packet = _measurement_packet(
        plans,
        decisions,
        release_identity_sha256=release_identity_sha256,
        release_artifact_sha256=selected_manifest.artifact_sha256,
        deployment_candidate_sha256=selected_manifest.schema_sha256,
    )
    property_record_sha256 = (
        measurement_packet.authority_packet.policy.property_record_sha256
    )

    assurance_bundle = assurance.evidence_bundle(selected_manifest)
    local_report = evaluate_local_assurance(
        assurance_bundle, assurance.AUTHORITY, at=assurance.AT
    )
    provider_target_sha256 = measurement._sha("provider-target")
    expected_pre_state_sha256 = measurement._sha("provider-pre-state")
    p15_plan = production._plan(
        property_record_sha256=property_record_sha256,
        release_manifest_sha256=selected_manifest.manifest_sha256,
        release_artifact_sha256=selected_manifest.artifact_sha256,
        deployment_candidate_sha256=selected_manifest.schema_sha256,
        provider_target_sha256=provider_target_sha256,
        expected_pre_state_sha256=expected_pre_state_sha256,
    )
    expected_post_state_sha256 = measurement._sha("provider-active-state")
    rollback_state_sha256 = measurement._sha("provider-disabled-state")
    p15_evidence = []
    for check in REQUIRED_PRODUCTION_INTEGRATION_CHECKS:
        facts = production._facts(check)
        if check is ProductionIntegrationCheck.INDEPENDENT_READBACK:
            facts = facts.model_copy(
                update={
                    "expected_state_sha256": expected_post_state_sha256,
                    "observed_state_sha256": expected_post_state_sha256,
                }
            )
        elif check is ProductionIntegrationCheck.ROLLBACK_DISABLE:
            facts = facts.model_copy(
                update={
                    "disable_policy_sha256": p15_plan.p11_policy_sha256,
                    "p11_disable_authority_sha256": p15_plan.p11_policy_sha256,
                    "active_state_sha256": expected_post_state_sha256,
                    "disabled_state_sha256": rollback_state_sha256,
                    "final_observed_state_sha256": rollback_state_sha256,
                }
            )
        p15_evidence.append(
            production._evidence(
                check,
                plan=p15_plan,
                observed_at=(
                    EVALUATED_AT
                    if check
                    in {
                        ProductionIntegrationCheck.EXTERNAL_MONOTONIC_ANCHOR,
                        ProductionIntegrationCheck.SHARED_DURABLE_STORE_FENCING,
                        ProductionIntegrationCheck.TRUSTED_CLOCK,
                    }
                    else EVALUATED_AT - timedelta(minutes=1)
                ),
                facts_override=facts,
            )
        )
    p15_bundle = build_production_integration_bundle(
        p15_plan, production.POLICY, tuple(p15_evidence)
    )
    p15_report = evaluate_production_integration_readiness(
        p15_bundle,
        p15_plan,
        production.POLICY,
        production.TRUST,
        at=EVALUATED_AT,
    )
    p15_tco = sign_production_tco_qa_attestation(
        p15_report,
        production.TCO_PRIVATE,
        issuer="p15-tco",
        decision=ReadinessAttestationDecision.ACCEPT,
        issued_at=EVALUATED_AT,
        expires_at=EVALUATED_AT + timedelta(minutes=30),
    )
    legal_pages_sha256 = measurement._sha("legal-pages")
    disclosure_sha256 = measurement._sha("publication-disclosure")
    scope = LaunchSemanticScope(
        candidate_manifest_sha256=(
            candidate_manifest_sha256
            if candidate_manifest_sha256 is not None
            else measurement._sha("candidate-manifest")
        ),
        property_record_sha256=property_record_sha256,
        environment_identity_sha256=p15_plan.environment_identity_sha256,
        release_identity_sha256=release_identity_sha256,
        release_manifest_sha256=selected_manifest.manifest_sha256,
        release_artifact_sha256=p15_plan.release_artifact_sha256,
        deployment_candidate_sha256=p15_plan.deployment_candidate_sha256,
        provider_target_sha256=provider_target_sha256,
        expected_pre_state_sha256=expected_pre_state_sha256,
        expected_post_state_sha256=expected_post_state_sha256,
        rollback_state_sha256=rollback_state_sha256,
        legal_pages_sha256=legal_pages_sha256,
        affiliate_disclosure_sha256=disclosure_sha256,
    )
    rights_bundle = build_rights_bundle(plans, at=EVALUATED_AT)
    affiliate_bundle = build_affiliate_bundle(
        decisions, property_domain="synthetic.invalid", at=EVALUATED_AT
    )

    gold_report = evaluate_goldset(goldset, candidates, at=EVALUATED_AT)
    gold_private = Ed25519PrivateKey.generate()
    gold_key = create_verification_key(
        gold_private.public_key(), issuer="semantic-gold-tco", role=SigningRole.TCO_QA
    )
    gold_attestation = sign_gold_report_attestation(
        gold_report,
        gold_private,
        issuer=gold_key.issuer,
        issued_at=EVALUATED_AT,
        expires_at=EVALUATED_AT + timedelta(hours=2),
    )

    readback_evidence = next(
        row
        for row in p15_bundle.evidence
        if row.check is ProductionIntegrationCheck.INDEPENDENT_READBACK
    )
    rollback_evidence = next(
        row
        for row in p15_bundle.evidence
        if row.check is ProductionIntegrationCheck.ROLLBACK_DISABLE
    )
    deployment_facts = DeploymentReadinessFacts(
        property_record_sha256=scope.property_record_sha256,
        environment_identity_sha256=scope.environment_identity_sha256,
        release_identity_sha256=scope.release_identity_sha256,
        release_manifest_sha256=scope.release_manifest_sha256,
        release_artifact_sha256=scope.release_artifact_sha256,
        deployment_candidate_sha256=scope.deployment_candidate_sha256,
        production_integration_plan_sha256=p15_plan.plan_sha256,
        provider_target_sha256=scope.provider_target_sha256,
        expected_pre_state_sha256=scope.expected_pre_state_sha256,
        independent_readback_evidence_sha256=(
            hash_production_integration_evidence(readback_evidence)
        ),
        rollback_disable_evidence_sha256=(
            hash_production_integration_evidence(rollback_evidence)
        ),
        staged_expected_state_sha256=scope.expected_post_state_sha256,
        staged_observed_state_sha256=scope.expected_post_state_sha256,
        rollback_active_state_sha256=scope.expected_post_state_sha256,
        rollback_expected_state_sha256=scope.rollback_state_sha256,
        rollback_observed_state_sha256=scope.rollback_state_sha256,
    )
    deployment = sign_deployment_readiness_record(
        deployment_facts,
        production.PROBE_PRIVATE,
        production.TRUST.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=EVALUATED_AT,
        expires_at=EVALUATED_AT + timedelta(minutes=5),
    )
    readback_at = EVALUATED_AT
    publication_facts = PublicationReadinessFacts(
        property_record_sha256=scope.property_record_sha256,
        environment_identity_sha256=scope.environment_identity_sha256,
        release_identity_sha256=scope.release_identity_sha256,
        release_manifest_sha256=scope.release_manifest_sha256,
        release_artifact_sha256=scope.release_artifact_sha256,
        deployment_candidate_sha256=scope.deployment_candidate_sha256,
        deployment_readiness_record_sha256=deployment.record_sha256,
        rights_bundle_sha256=rights_bundle.bundle_sha256,
        affiliate_bundle_sha256=affiliate_bundle.bundle_sha256,
        approved_partner_ids=affiliate_bundle.approved_partner_ids,
        content_readback=PublicationContentReadback(
            expected_release_manifest_sha256=scope.release_manifest_sha256,
            observed_release_manifest_sha256=scope.release_manifest_sha256,
            expected_release_artifact_sha256=scope.release_artifact_sha256,
            observed_release_artifact_sha256=scope.release_artifact_sha256,
            response_receipt_sha256=measurement._sha("content-response"),
            observed_at=readback_at,
        ),
        indexability_readback=PublicationIndexabilityReadback(
            response_receipt_sha256=measurement._sha("indexability-response"),
            observed_at=readback_at,
        ),
        disclosure_readback=PublicationDisclosureReadback(
            expected_legal_pages_sha256=legal_pages_sha256,
            observed_legal_pages_sha256=legal_pages_sha256,
            expected_disclosure_sha256=disclosure_sha256,
            observed_disclosure_sha256=disclosure_sha256,
            response_receipt_sha256=measurement._sha("disclosure-response"),
            observed_at=readback_at,
        ),
    )
    publication = sign_publication_readiness_record(
        publication_facts,
        production.PROBE_PRIVATE,
        production.TRUST.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=readback_at,
        expires_at=EVALUATED_AT + timedelta(minutes=5),
    )

    values = {
        "schema_version": "1.0",
        "scope": scope,
        "rights": RightsSemanticPacket(plans=plans),
        "affiliate": AffiliateSemanticPacket(
            property_domain="synthetic.invalid",
            decisions=AffiliateDecisionBatch(decisions=decisions),
        ),
        "measurement": measurement_packet,
        "gold": GoldSemanticPacket(
            goldset=goldset,
            candidates=candidates,
            report=gold_report,
            attestation=gold_attestation,
            tco_qa_verifier=gold_key,
        ),
        "production": ProductionSemanticPacket(
            plan=p15_plan,
            policy=production.POLICY,
            trust_store=production.TRUST,
            evidence_bundle=p15_bundle,
            report=p15_report,
            tco_qa_attestation=p15_tco,
        ),
        "deployment_publication": DeploymentPublicationSemanticPacket(
            assurance_policy=assurance.POLICY,
            assurance_trust_store=assurance.TRUST,
            assurance_bundle=assurance_bundle,
            local_assurance_report=local_report,
            deployment=deployment,
            publication=publication,
        ),
    }
    provisional = LaunchSemanticPacket.model_construct(
        **values, packet_sha256="0" * 64
    )
    packet = LaunchSemanticPacket(
        **values, packet_sha256=hash_launch_semantic_packet(provisional)
    )
    pins = build_launch_semantic_authority_pins(packet)
    return {
        "packet": packet,
        "pins": pins,
        "at": EVALUATED_AT,
        "rights_bundle": rights_bundle,
        "affiliate_bundle": affiliate_bundle,
    }
