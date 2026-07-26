from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from pydantic import ValidationError

import test_goldset as gold_fixtures
import test_measurement_integrity as measurement_fixtures
import test_production_readiness as production_readiness_fixtures
import test_readiness_builder as readiness_fixtures
import test_release_assurance as assurance_fixtures
from launch_semantic_support import build_semantic_context
from saas_preflight.control_cycle import (
    ControlTrustStore,
    hash_control_trust_store,
    sign_gold_report_attestation,
)
from saas_preflight.goldset import evaluate_goldset
from saas_preflight.launch_semantics import (
    AffiliateSemanticPacket,
    DeploymentPublicationSemanticPacket,
    DeploymentReadinessRecord,
    GoldSemanticPacket,
    LaunchSemanticGate,
    LaunchSemanticInputError,
    LaunchSemanticPacket,
    LaunchSemanticReason,
    LaunchSemanticScope,
    MeasurementSemanticPacket,
    ProductionSemanticPacket,
    PublicationReadinessRecord,
    RightsSemanticPacket,
    build_launch_semantic_authority_pins,
    evaluate_launch_semantics,
    hash_deployment_readiness_record,
    hash_launch_semantic_packet,
    hash_publication_readiness_record,
    sign_deployment_readiness_record,
    sign_publication_readiness_record,
)
from saas_preflight.measurement_integrity import (
    MeasurementBoundDossier,
    hash_signed_artifact,
)
from saas_preflight.readiness_builder import (
    AffiliateDecisionBatch,
    AffiliateProgramDecision,
    AffiliateReviewDecision,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)
from saas_preflight.production_readiness import (
    ProductionIntegrationCheck,
    ProductionEvidenceProvenance,
    ReadinessAttestationDecision,
    hash_production_integration_evidence,
    sign_production_tco_qa_attestation,
)
from saas_preflight.traction_control import P12AuthorityPacket


ZERO_SHA256 = "0" * 64


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _rehash_packet(
    packet: LaunchSemanticPacket, **updates: object
) -> LaunchSemanticPacket:
    provisional = packet.model_copy(
        update={**updates, "packet_sha256": ZERO_SHA256}, deep=True
    )
    values = provisional.model_dump(exclude={"packet_sha256"})
    return LaunchSemanticPacket(
        **values,
        packet_sha256=hash_launch_semantic_packet(provisional),
    )


def _rehash_deployment(
    record: DeploymentReadinessRecord, **updates: object
) -> DeploymentReadinessRecord:
    provisional = record.model_copy(
        update={**updates, "record_sha256": ZERO_SHA256}, deep=True
    )
    values = provisional.model_dump(exclude={"record_sha256"})
    return DeploymentReadinessRecord(
        **values,
        record_sha256=hash_deployment_readiness_record(provisional),
    )


def _rehash_publication(
    record: PublicationReadinessRecord, **updates: object
) -> PublicationReadinessRecord:
    provisional = record.model_copy(
        update={**updates, "record_sha256": ZERO_SHA256}, deep=True
    )
    values = provisional.model_dump(exclude={"record_sha256"})
    return PublicationReadinessRecord(
        **values,
        record_sha256=hash_publication_readiness_record(provisional),
    )


def _affiliate_decisions() -> tuple[AffiliateProgramDecision, ...]:
    return tuple(
        readiness_fixtures._affiliate(
            partner_id=f"partner-{suffix}",
            vendor_slug=f"vendor-{suffix}",
            property_domain="synthetic.invalid",
            decision_record_sha256=_sha(f"affiliate-decision:{suffix}"),
        )
        for suffix in ("a", "b", "c")
    )


def _production_scale_measurement(monkeypatch):
    at = production_readiness_fixtures.AT
    end = at.astimezone(measurement_fixtures.TOKYO).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_utc = end.astimezone(measurement_fixtures.timezone.utc)
    start = end - timedelta(days=30)
    monkeypatch.setattr(measurement_fixtures, "START", start)
    monkeypatch.setattr(measurement_fixtures, "END", end)
    monkeypatch.setattr(
        measurement_fixtures,
        "START_UTC",
        start.astimezone(measurement_fixtures.timezone.utc),
    )
    monkeypatch.setattr(measurement_fixtures, "END_UTC", end_utc)
    monkeypatch.setattr(measurement_fixtures, "AT", at)
    original_demand = measurement_fixtures._demand

    def production_scale_demand():
        demand = original_demand()
        values = demand.summary.model_dump()
        values["clusters"] = tuple(
            row.__class__(
                **{
                    **row.model_dump(),
                    "deduplicated_monthly_volume": (
                        row.deduplicated_monthly_volume * 10_000
                    ),
                }
            )
            for row in demand.summary.clusters
        )
        return demand.__class__(
            **{
                **demand.model_dump(exclude={"summary"}),
                "summary": demand.summary.__class__(**values),
            }
        )

    monkeypatch.setattr(measurement_fixtures, "_demand", production_scale_demand)
    bundle = measurement_fixtures._bundle()
    cohort = bundle["cohort"]
    extra_sessions = tuple(
        measurement_fixtures.QualifiedSession(
            session_id_sha256=measurement_fixtures._sha(f"session:{number}"),
            qualified_at=start.astimezone(measurement_fixtures.timezone.utc)
            + timedelta(days=1, minutes=number),
        )
        for number in range(4, 1000)
    )
    extra_outbound = tuple(
        measurement_fixtures.ValidOutboundClick(
            click_id_sha256=measurement_fixtures._sha(f"outbound:{number}"),
            session_id_sha256=measurement_fixtures._sha(f"session:{number}"),
            partner_id=("partner-a", "partner-b", "partner-c")[number % 3],
            clicked_at=start.astimezone(measurement_fixtures.timezone.utc)
            + timedelta(days=2, minutes=number),
        )
        for number in range(4, 1000)
    )
    transactions = tuple(
        row.__class__(**{**row.model_dump(), "amount": row.amount * 1000})
        for row in cohort.transactions
    )
    payout_rows = tuple(
        row.__class__(**{**row.model_dump(), "amount": row.amount * 1000})
        for row in cohort.payout_rows
    )
    statement = cohort.payout_statement.__class__(
        **{
            **cohort.payout_statement.model_dump(),
            "gross_amount": cohort.payout_statement.gross_amount * 1000,
            "net_amount": cohort.payout_statement.net_amount * 1000,
        }
    )
    cohort = cohort.__class__(
        **{
            **cohort.model_dump(
                exclude={
                    "qualified_sessions",
                    "valid_outbound_clicks",
                    "transactions",
                    "payout_rows",
                    "payout_statement",
                }
            ),
            "qualified_sessions": cohort.qualified_sessions + extra_sessions,
            "valid_outbound_clicks": cohort.valid_outbound_clicks + extra_outbound,
            "transactions": transactions,
            "payout_rows": payout_rows,
            "payout_statement": statement,
        }
    )
    measurement_fixtures._replace_cohort(
        bundle,
        cohort,
        measurement_fixtures._coverage(cohort, "cohort"),
    )
    return bundle, measurement_fixtures._evaluate(bundle)


def _legacy_launch_case(monkeypatch):
    at = production_readiness_fixtures.AT
    measurement, p12_report = _production_scale_measurement(monkeypatch)
    goldset, candidates, plans = gold_fixtures.full_fixture()
    gold_report = evaluate_goldset(goldset, candidates, at=gold_fixtures.NOW)
    gold_attestation = sign_gold_report_attestation(
        gold_report,
        assurance_fixtures.TCO_PRIVATE,
        issuer=assurance_fixtures.TCO_KEY.issuer,
        issued_at=gold_report.evaluated_at,
        expires_at=gold_report.evaluated_at + timedelta(days=1),
    )

    decisions = _affiliate_decisions()
    dossier = build_business_dossier(
        plans=plans,
        affiliate_decisions=decisions,
        property_domain="synthetic.invalid",
        demand=p12_report.demand,
        cohort=p12_report.cohort,
        operations=p12_report.operations,
        at=at,
    )
    bound_dossier = MeasurementBoundDossier(
        report=p12_report,
        dossier=dossier,
        dossier_sha256=hash_signed_artifact(dossier),
    )
    authority_packet = P12AuthorityPacket(
        policy=measurement["policy"],
        trust_store=measurement["trust"],
        authority_pins=measurement["pins"],
        plan=measurement["plan"],
        demand_batch=measurement["demand"],
        cohort_batch=measurement["cohort"],
        operations_batch=measurement["operations"],
        demand_attestation=measurement["demand_attestation"],
        cohort_attestation=measurement["cohort_attestation"],
        operations_attestation=measurement["operations_attestation"],
        bundle_index=measurement["index"],
        report=p12_report,
    )

    manifest = assurance_fixtures.manifest()
    p15_plan = production_readiness_fixtures._plan(
        property_record_sha256=p12_report.property_record_sha256,
        release_artifact_sha256=manifest.artifact_sha256,
        release_manifest_sha256=manifest.manifest_sha256,
    )
    p15_bundle = production_readiness_fixtures._bundle(plan=p15_plan, at=at)
    p15_report = production_readiness_fixtures._report(
        p15_bundle, plan=p15_plan, at=at
    )
    p15_tco = sign_production_tco_qa_attestation(
        p15_report,
        production_readiness_fixtures.TCO_PRIVATE,
        issuer=production_readiness_fixtures.TRUST.tco_qa.issuer,
        decision=ReadinessAttestationDecision.ACCEPT,
        issued_at=at,
        expires_at=at + timedelta(minutes=30),
    )
    scope = LaunchSemanticScope(
        candidate_manifest_sha256=manifest.manifest_sha256,
        property_record_sha256=p15_plan.property_record_sha256,
        environment_identity_sha256=p15_plan.environment_identity_sha256,
        release_artifact_sha256=p15_plan.release_artifact_sha256,
        deployment_candidate_sha256=p15_plan.deployment_candidate_sha256,
    )
    deployment_provisional = DeploymentReadinessRecord.model_construct(
        property_record_sha256=scope.property_record_sha256,
        environment_identity_sha256=scope.environment_identity_sha256,
        release_artifact_sha256=scope.release_artifact_sha256,
        deployment_candidate_sha256=scope.deployment_candidate_sha256,
        production_integration_plan_sha256=p15_plan.plan_sha256,
        provider_target_sha256=_sha("provider-target"),
        staged_readback_sha256=_sha("staged-readback"),
        rollback_plan_sha256=_sha("rollback-plan"),
        staged_readback_matches=True,
        rollback_test_passed=True,
        observed_at=at - timedelta(minutes=1),
        expires_at=at + timedelta(minutes=20),
        record_sha256=ZERO_SHA256,
    )
    deployment = _rehash_deployment(deployment_provisional)

    rights_bundle = build_rights_bundle(plans, at=at)
    affiliate_bundle = build_affiliate_bundle(
        decisions, property_domain="synthetic.invalid", at=at
    )
    publication_provisional = PublicationReadinessRecord.model_construct(
        property_record_sha256=scope.property_record_sha256,
        environment_identity_sha256=scope.environment_identity_sha256,
        release_artifact_sha256=scope.release_artifact_sha256,
        deployment_candidate_sha256=scope.deployment_candidate_sha256,
        rights_bundle_sha256=rights_bundle.bundle_sha256,
        affiliate_bundle_sha256=affiliate_bundle.bundle_sha256,
        legal_pages_sha256=_sha("legal-pages"),
        disclosure_sha256=_sha("affiliate-disclosure"),
        approved_partner_ids=affiliate_bundle.approved_partner_ids,
        indexability_verified=True,
        noindex_removed=True,
        disclosure_visible=True,
        observed_at=at - timedelta(minutes=1),
        expires_at=at + timedelta(minutes=20),
        record_sha256=ZERO_SHA256,
    )
    publication = _rehash_publication(publication_provisional)

    assurance_bundle = assurance_fixtures.evidence_bundle(
        manifest
    )
    local_report = assurance_fixtures.local_report(manifest)
    semantic_values = {
        "scope": scope,
        "rights": RightsSemanticPacket(plans=plans),
        "affiliate": AffiliateSemanticPacket(
            property_domain="synthetic.invalid",
            decisions=AffiliateDecisionBatch(decisions=decisions),
        ),
        "measurement": MeasurementSemanticPacket(
            authority_packet=authority_packet,
            bound_dossier=bound_dossier,
        ),
        "gold": GoldSemanticPacket(
            goldset=goldset,
            candidates=candidates,
            report=gold_report,
            attestation=gold_attestation,
            tco_qa_verifier=assurance_fixtures.TCO_KEY,
        ),
        "production": ProductionSemanticPacket(
            plan=p15_plan,
            policy=production_readiness_fixtures.POLICY,
            trust_store=production_readiness_fixtures.TRUST,
            evidence_bundle=p15_bundle,
            report=p15_report,
            tco_qa_attestation=p15_tco,
        ),
        "deployment_publication": DeploymentPublicationSemanticPacket(
            assurance_policy=assurance_fixtures.POLICY,
            assurance_trust_store=assurance_fixtures.TRUST,
            assurance_bundle=assurance_bundle,
            local_assurance_report=local_report,
            deployment=deployment,
            publication=publication,
        ),
    }
    provisional = LaunchSemanticPacket.model_construct(
        **semantic_values, packet_sha256=ZERO_SHA256
    )
    packet = LaunchSemanticPacket(
        **semantic_values,
        packet_sha256=hash_launch_semantic_packet(provisional),
    )
    pins = build_launch_semantic_authority_pins(packet)
    evaluation = evaluate_launch_semantics(
        packet,
        pins,
        at=at,
        expected_authority_pins_sha256=pins.pins_sha256,
    )
    assert evaluation.passed, evaluation.gates
    return {"at": at, "packet": packet, "pins": pins}


@pytest.fixture
def launch_case():
    context = build_semantic_context()
    evaluation = evaluate_launch_semantics(
        context["packet"],
        context["pins"],
        at=context["at"],
        expected_authority_pins_sha256=context["pins"].pins_sha256,
    )
    assert evaluation.passed, evaluation.gates
    return context


def _gate(evaluation, gate: LaunchSemanticGate):
    return next(item for item in evaluation.gates if item.gate is gate)


def test_missing_typed_packet_and_arbitrary_packet_hash_are_rejected(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    missing = packet.model_dump()
    missing.pop("rights")

    with pytest.raises(ValidationError):
        LaunchSemanticPacket.model_validate(missing)
    with pytest.raises(ValidationError, match="packet hash mismatch"):
        LaunchSemanticPacket.model_validate(
            {**packet.model_dump(), "packet_sha256": "a" * 64}
        )


def test_stale_typed_artifact_cannot_be_rewrapped_with_fresh_packet_and_pins(
    launch_case,
) -> None:
    at = launch_case["at"]
    packet = launch_case["packet"]
    stale_deployment = _rehash_deployment(
        packet.deployment_publication.deployment,
        observed_at=at - timedelta(hours=1),
        expires_at=at,
    )
    deployment_publication = packet.deployment_publication.model_copy(
        update={"deployment": stale_deployment}, deep=True
    )
    rewrapped = _rehash_packet(
        packet, deployment_publication=deployment_publication
    )
    fresh_pins = build_launch_semantic_authority_pins(rewrapped)

    evaluation = evaluate_launch_semantics(
        rewrapped,
        fresh_pins,
        at=at,
        expected_authority_pins_sha256=fresh_pins.pins_sha256,
    )

    gate = _gate(evaluation, LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS)
    assert evaluation.passed is False
    assert LaunchSemanticReason.DEPLOYMENT_RECORD_INVALID in gate.reasons
    assert LaunchSemanticReason.UPSTREAM_EXPIRY_INVALID in gate.reasons


def test_substituted_policy_trust_and_pins_fail_the_consumer_owned_root(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    original_pins = launch_case["pins"]
    p10 = packet.deployment_publication
    substituted_controller = p10.assurance_trust_store.controller.model_copy(
        update={"issuer": "substituted-controller"}
    )
    substituted_trust = ControlTrustStore(
        controller=substituted_controller,
        gold_tco_qa=p10.assurance_trust_store.gold_tco_qa,
        release_human=p10.assurance_trust_store.release_human,
    )
    substituted_policy = p10.assurance_policy.model_copy(
        update={
            "policy_id": "substituted-policy-v1",
            "trust_store_sha256": hash_control_trust_store(substituted_trust),
        }
    )
    substituted_p10 = p10.model_copy(
        update={
            "assurance_policy": substituted_policy,
            "assurance_trust_store": substituted_trust,
        },
        deep=True,
    )
    substituted_packet = _rehash_packet(
        packet, deployment_publication=substituted_p10
    )
    substituted_pins = build_launch_semantic_authority_pins(substituted_packet)

    with pytest.raises(LaunchSemanticInputError, match="consumer root"):
        evaluate_launch_semantics(
            substituted_packet,
            substituted_pins,
            at=launch_case["at"],
            expected_authority_pins_sha256=original_pins.pins_sha256,
        )


def test_property_environment_release_and_deployment_scope_splices_are_rejected(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    for field in (
        "property_record_sha256",
        "environment_identity_sha256",
        "release_identity_sha256",
        "release_manifest_sha256",
        "release_artifact_sha256",
        "deployment_candidate_sha256",
        "provider_target_sha256",
        "expected_pre_state_sha256",
        "expected_post_state_sha256",
        "rollback_state_sha256",
        "legal_pages_sha256",
        "affiliate_disclosure_sha256",
    ):
        spliced_scope = packet.scope.model_copy(update={field: _sha(f"splice:{field}")})
        spliced_packet = _rehash_packet(packet, scope=spliced_scope)
        spliced_pins = build_launch_semantic_authority_pins(spliced_packet)

        evaluation = evaluate_launch_semantics(
            spliced_packet,
            spliced_pins,
            at=launch_case["at"],
            expected_authority_pins_sha256=spliced_pins.pins_sha256,
        )

        assert evaluation.passed is False, field
        assert any(not gate.passed for gate in evaluation.gates), field


def test_authorized_probe_cannot_replace_p15_readback_with_arbitrary_fact(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    original = packet.deployment_publication.deployment
    changed_facts = original.facts.model_copy(
        update={"independent_readback_evidence_sha256": _sha("arbitrary-readback")}
    )
    changed = sign_deployment_readiness_record(
        changed_facts,
        production_readiness_fixtures.PROBE_PRIVATE,
        packet.production.trust_store.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=original.observed_at,
        expires_at=original.expires_at,
    )
    changed_section = packet.deployment_publication.model_copy(
        update={"deployment": changed}
    )
    attacked = _rehash_packet(
        packet, deployment_publication=changed_section
    )
    pins = build_launch_semantic_authority_pins(attacked)

    evaluation = evaluate_launch_semantics(
        attacked,
        pins,
        at=launch_case["at"],
        expected_authority_pins_sha256=pins.pins_sha256,
    )

    gate = _gate(evaluation, LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS)
    assert evaluation.passed is False
    assert LaunchSemanticReason.DEPLOYMENT_RECORD_INVALID in gate.reasons

    rollback = next(
        row
        for row in packet.production.evidence_bundle.evidence
        if row.check is ProductionIntegrationCheck.ROLLBACK_DISABLE
    )
    wrong_policy_facts = rollback.facts.model_copy(
        update={
            "disable_policy_sha256": _sha("unrelated-p11-disable-policy"),
            "p11_disable_authority_sha256": _sha(
                "unrelated-p11-disable-authority"
            ),
        }
    )
    resigned_rollback = production_readiness_fixtures._evidence(
        ProductionIntegrationCheck.ROLLBACK_DISABLE,
        plan=packet.production.plan,
        observed_at=rollback.observed_at,
        expires_at=rollback.expires_at,
        facts_override=wrong_policy_facts,
    )
    evidence = tuple(
        resigned_rollback if row is rollback else row
        for row in packet.production.evidence_bundle.evidence
    )
    bundle = production_readiness_fixtures.build_production_integration_bundle(
        packet.production.plan,
        packet.production.policy,
        evidence,
    )
    report = production_readiness_fixtures.evaluate_production_integration_readiness(
        bundle,
        packet.production.plan,
        packet.production.policy,
        packet.production.trust_store,
        at=launch_case["at"],
    )
    assert report.decision is packet.production.report.decision
    tco = sign_production_tco_qa_attestation(
        report,
        production_readiness_fixtures.TCO_PRIVATE,
        issuer=packet.production.trust_store.tco_qa.issuer,
        decision=ReadinessAttestationDecision.ACCEPT,
        issued_at=launch_case["at"],
        expires_at=launch_case["at"] + timedelta(minutes=30),
    )
    changed_production = packet.production.model_copy(
        update={
            "evidence_bundle": bundle,
            "report": report,
            "tco_qa_attestation": tco,
        }
    )
    rebound_facts = original.facts.model_copy(
        update={
            "rollback_disable_evidence_sha256": (
                hash_production_integration_evidence(resigned_rollback)
            )
        }
    )
    rebound_deployment = sign_deployment_readiness_record(
        rebound_facts,
        production_readiness_fixtures.PROBE_PRIVATE,
        packet.production.trust_store.independent_probe,
        provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
        observed_at=original.observed_at,
        expires_at=original.expires_at,
    )
    changed_section = packet.deployment_publication.model_copy(
        update={"deployment": rebound_deployment}
    )
    attacked = _rehash_packet(
        packet,
        production=changed_production,
        deployment_publication=changed_section,
    )
    pins = build_launch_semantic_authority_pins(attacked)
    evaluation = evaluate_launch_semantics(
        attacked,
        pins,
        at=launch_case["at"],
        expected_authority_pins_sha256=pins.pins_sha256,
    )
    gate = _gate(evaluation, LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS)
    assert evaluation.passed is False
    assert LaunchSemanticReason.DEPLOYMENT_RECORD_INVALID in gate.reasons


def test_synthetic_publication_readback_cannot_be_rehashed_and_reauthorized(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    original = packet.deployment_publication.publication
    changed = sign_publication_readiness_record(
        original.facts,
        production_readiness_fixtures.PROBE_PRIVATE,
        packet.production.trust_store.independent_probe,
        provenance=ProductionEvidenceProvenance.SYNTHETIC_CONTRACT,
        observed_at=original.observed_at,
        expires_at=original.expires_at,
    )
    changed_section = packet.deployment_publication.model_copy(
        update={"publication": changed}
    )
    attacked = _rehash_packet(
        packet, deployment_publication=changed_section
    )
    pins = build_launch_semantic_authority_pins(attacked)

    evaluation = evaluate_launch_semantics(
        attacked,
        pins,
        at=launch_case["at"],
        expected_authority_pins_sha256=pins.pins_sha256,
    )

    gate = _gate(evaluation, LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS)
    assert evaluation.passed is False
    assert LaunchSemanticReason.PUBLICATION_RECORD_INVALID in gate.reasons

    at = launch_case["at"]
    ttl = packet.production.policy.maximum_live_control_ttl_seconds
    disclosure = original.facts.disclosure_readback
    attacks = (
        original.facts.model_copy(
            update={
                "disclosure_readback": disclosure.model_copy(
                    update={
                        "expected_legal_pages_sha256": _sha("attacker-legal"),
                        "observed_legal_pages_sha256": _sha("attacker-legal"),
                        "expected_disclosure_sha256": _sha("attacker-disclosure"),
                        "observed_disclosure_sha256": _sha("attacker-disclosure"),
                        "response_receipt_sha256": _sha("attacker-response"),
                    }
                )
            }
        ),
        original.facts.model_copy(
            update={
                "deployment_readiness_record_sha256": _sha(
                    "unrelated-deployment-record"
                )
            }
        ),
        original.facts.model_copy(
            update={
                "indexability_readback": (
                    original.facts.indexability_readback.model_copy(
                        update={"observed_at": at - timedelta(seconds=ttl + 1)}
                    )
                )
            }
        ),
        original.facts.model_copy(
            update={
                "content_readback": original.facts.content_readback.model_copy(
                    update={
                        "observed_at": (
                            packet.deployment_publication.deployment.observed_at
                            - timedelta(microseconds=1)
                        )
                    }
                )
            }
        ),
    )
    for changed_facts in attacks:
        resigned = sign_publication_readiness_record(
            changed_facts,
            production_readiness_fixtures.PROBE_PRIVATE,
            packet.production.trust_store.independent_probe,
            provenance=ProductionEvidenceProvenance.PRODUCTION_ENVIRONMENT,
            observed_at=original.observed_at,
            expires_at=original.expires_at,
        )
        changed_section = packet.deployment_publication.model_copy(
            update={"publication": resigned}
        )
        attacked = _rehash_packet(
            packet, deployment_publication=changed_section
        )
        pins = build_launch_semantic_authority_pins(attacked)
        evaluation = evaluate_launch_semantics(
            attacked,
            pins,
            at=at,
            expected_authority_pins_sha256=pins.pins_sha256,
        )
        gate = _gate(
            evaluation,
            LaunchSemanticGate.DEPLOYMENT_PUBLICATION_READINESS,
        )
        assert evaluation.passed is False
        assert LaunchSemanticReason.PUBLICATION_RECORD_INVALID in gate.reasons


def test_semantic_stop_survives_recalculation_of_every_packet_hash(
    launch_case,
) -> None:
    packet = launch_case["packet"]
    decisions = packet.affiliate.decisions.decisions
    first = decisions[0]
    prohibited = AffiliateProgramDecision(
        **{
            **first.model_dump(),
            "decision": AffiliateReviewDecision.PROHIBITED,
            "program_id": None,
            "destination_sha256": None,
            "disclosure_sha256": None,
        }
    )
    stopped_affiliate = AffiliateSemanticPacket(
        property_domain=packet.affiliate.property_domain,
        decisions=AffiliateDecisionBatch(
            decisions=(prohibited, *decisions[1:])
        ),
    )
    stopped_packet = _rehash_packet(packet, affiliate=stopped_affiliate)
    stopped_pins = build_launch_semantic_authority_pins(stopped_packet)

    evaluation = evaluate_launch_semantics(
        stopped_packet,
        stopped_pins,
        at=launch_case["at"],
        expected_authority_pins_sha256=stopped_pins.pins_sha256,
    )

    gate = _gate(evaluation, LaunchSemanticGate.AFFILIATE_ACCEPTANCE)
    assert evaluation.passed is False
    assert gate.passed is False
    assert LaunchSemanticReason.MINIMUM_VENDOR_SET_NOT_MET in gate.reasons
