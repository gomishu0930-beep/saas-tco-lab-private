from __future__ import annotations

import hashlib
import inspect
import json
import multiprocessing
import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from threading import Event
from time import monotonic

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import test_measurement_integrity as p12
import saas_preflight.traction_control as traction_module
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.cli import run
from saas_preflight.measurement_integrity import (
    CohortIntegrityBatch,
    CurrentTransaction,
    TransactionStatus,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
)
from saas_preflight.operations_activity import (
    HumanActivityEvent,
    OperationalCostPolicy,
    OperationsActivityBatch,
    RoleLaborRate,
    RoutineExecutionOutcome,
    RoutineTaskDefinition,
    RoutineTaskExecution,
    RoutineTaskMode,
    ScheduledRoutineTask,
    derive_operations_activity,
    hash_operational_cost_policy,
    hash_operations_activity_batch,
)
from saas_preflight.settlement_amendment import (
    SettlementAmendmentPolicy,
    SettlementAmendmentTrustStore,
    SettlementCompletenessCoverage,
    SettlementCompletenessDecision,
    SettlementStatusChange,
    build_original_settlement_binding,
    hash_settlement_policy,
    hash_settlement_trust_store,
    sign_settlement_amendment,
    sign_settlement_completeness_attestation,
)
from saas_preflight.traction_control import (
    P12AuthorityPacket,
    PartnerTractionFacts,
    TractionAuthorityPins,
    TractionDecision,
    TractionInputError,
    TractionLedger,
    TractionObservation,
    TractionPolicy,
    TractionProvenance,
    TractionRuntimeBroker,
    TractionSettlementEvidence,
    TractionTrustStore,
    _sign_model,
    _evaluate_traction,
    build_traction_observation,
    evaluate_traction,
    hash_traction_artifact,
    hash_traction_policy,
    hash_traction_trust_store,
    sign_traction_plan,
    sign_traction_clock_attestation,
    verify_traction_plan,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _p12_metric_bundle(
    *,
    clicks: int = 1000,
    qualified: int = 10000,
    partner_amounts: tuple[Decimal, Decimal, Decimal] = (
        Decimal("80000"),
        Decimal("60000"),
        Decimal("60000"),
    ),
):
    bundle = p12._bundle()
    cohort = bundle["cohort"]
    sessions = tuple(
        p12.QualifiedSession(
            session_id_sha256=_sha(f"metric-session:{number}"),
            qualified_at=p12.START_UTC + timedelta(days=1, seconds=number),
        )
        for number in range(qualified)
    )
    partners = ("partner-a", "partner-b", "partner-c")
    outbound = tuple(
        p12.ValidOutboundClick(
            click_id_sha256=_sha(f"metric-click:{number}"),
            session_id_sha256=_sha(f"metric-session:{number}"),
            partner_id=partners[number % 3],
            clicked_at=p12.START_UTC
            + timedelta(days=1, hours=4, seconds=number),
        )
        for number in range(clicks)
    )
    accepted = tuple(
        p12.AffiliateAcceptedClick(
            affiliate_click_id_sha256=_sha(f"affiliate:{number}"),
            outbound_click_id_sha256=_sha(f"metric-click:{number}"),
            partner_id=partners[number],
            accepted_at=p12.START_UTC
            + timedelta(days=1, hours=8, seconds=number),
        )
        for number in range(3)
    )
    by_id = {item.transaction_id_sha256: item for item in cohort.transactions}
    labels = ("confirmed-new", "paid-new", "paid-existing")
    transactions = []
    for index, label in enumerate(labels):
        original = by_id[_sha(f"transaction:{label}")]
        transactions.append(
            original.model_copy(
                update={
                    "affiliate_click_id_sha256": _sha(f"affiliate:{index}"),
                    "partner_id": partners[index],
                    "amount": partner_amounts[index],
                    "acquisition_class": p12.AcquisitionClass.NEW,
                }
            )
        )
    paid = tuple(
        item
        for item in transactions
        if item.current_status is p12.TransactionStatus.PAID
    )
    payout_rows = tuple(
        p12.PayoutRow(
            payout_row_sha256=_sha(f"metric-payout:{item.transaction_id_sha256}"),
            transaction_id_sha256=item.transaction_id_sha256,
            amount=item.amount,
            currency="JPY",
            paid_at=p12.START_UTC + timedelta(days=4),
        )
        for item in paid
    )
    gross = sum((item.amount for item in paid), Decimal(0))
    statement = p12.PayoutStatement(
        statement_sha256=_sha("metric-statement"),
        payout_id_sha256=_sha("metric-payout-id"),
        currency="JPY",
        gross_amount=gross,
        reversal_amount=Decimal(0),
        fees_tax_withholding=Decimal(0),
        net_amount=gross,
        paid_transaction_set_sha256=p12._set_hash(
            [item.transaction_id_sha256 for item in paid]
        ),
        period_started_at=p12.START,
        period_ended_at=p12.END,
        snapshot_as_of=p12.END,
    )
    changed = p12.CohortIntegrityBatch.model_validate(
        {
            **cohort.model_dump(),
            "qualified_sessions": sessions,
            "valid_outbound_clicks": outbound,
            "affiliate_accepted_clicks": accepted,
            "transactions": tuple(transactions),
            "payout_rows": payout_rows,
            "payout_adjustments": (),
            "payout_statement": statement,
        }
    )
    p12._replace_cohort(bundle, changed, p12._coverage(changed, "cohort"))
    demand = bundle["demand"]
    clusters = tuple(
        item.model_copy(
            update={
                "deduplicated_monthly_volume": (
                    Decimal("499900") if item.cluster_id == "compare" else Decimal("100")
                )
            }
        )
        for item in demand.summary.clusters
    )
    demand = p12.DemandIntegrityBatch.model_validate(
        {
            **demand.model_dump(),
            "summary": demand.summary.model_copy(update={"clusters": clusters}),
        }
    )
    demand_attestation = p12.sign_producer_attestation(
        bundle["plan"],
        p12.MeasurementDataset.DEMAND,
        demand,
        p12._coverage(demand, "demand"),
        bundle["keys"]["demand"],
        issuer="demand-producer",
        issued_at=p12.END_UTC + timedelta(hours=2),
        expires_at=p12.AT + timedelta(days=7),
    )
    index = p12.sign_measurement_bundle_index(
        bundle["plan"],
        demand,
        bundle["cohort"],
        bundle["operations"],
        demand_attestation,
        bundle["cohort_attestation"],
        bundle["operations_attestation"],
        bundle["keys"]["indexer"],
        issuer="measurement-indexer",
        captured_at=p12.END_UTC,
        issued_at=p12.END_UTC + timedelta(hours=3),
        expires_at=p12.AT + timedelta(days=7),
    )
    pins = p12.MeasurementAuthorityPins(
        expected_policy_sha256=hash_measurement_policy(bundle["policy"]),
        expected_trust_store_sha256=hash_measurement_trust_store(bundle["trust"]),
        expected_run_id=bundle["plan"].definition.run_id,
        expected_bundle_index_sha256=hash_signed_artifact(index),
    )
    bundle.update(
        {
            "demand": demand,
            "demand_attestation": demand_attestation,
            "index": index,
            "pins": pins,
            "runtime": p12.MeasurementIntegrityRuntime(
                bundle["policy"], bundle["trust"], bundle["keys"]["qa"], pins
            ),
        }
    )
    return bundle


def _p12_pending_bundle():
    bundle = p12._bundle()
    cohort = bundle["cohort"]
    transaction_id = _sha("transaction:confirmed-new")
    target = next(
        item
        for item in cohort.transactions
        if item.transaction_id_sha256 == transaction_id
    )
    pending = CurrentTransaction.model_validate(
        {
            **target.model_dump(),
            "current_status": TransactionStatus.PENDING,
            "status_events": (
                p12._event("pending-new", TransactionStatus.PENDING, 0),
            ),
        }
    )
    changed = CohortIntegrityBatch.model_validate(
        {
            **cohort.model_dump(),
            "transactions": tuple(
                pending if item.transaction_id_sha256 == transaction_id else item
                for item in cohort.transactions
            ),
        }
    )
    p12._replace_cohort(bundle, changed, p12._coverage(changed, "cohort"))
    return bundle


def _traction_context(p12_bundle=None, *, clock_response_timeout_seconds=5):
    human = Ed25519PrivateKey.generate()
    qa = Ed25519PrivateKey.generate()
    clock = Ed25519PrivateKey.generate()
    trust = TractionTrustStore(
        plan_human=create_verification_key(
            human.public_key(), issuer="traction-human", role=SigningRole.HUMAN_APPROVER
        ),
        observation_tco_qa=create_verification_key(
            qa.public_key(), issuer="traction-qa", role=SigningRole.TCO_QA
        ),
        clock_auditor=create_verification_key(
            clock.public_key(), issuer="traction-clock", role=SigningRole.TIME_AUDITOR
        ),
    )
    p12_bundle = p12._bundle() if p12_bundle is None else p12_bundle
    settlement_trust = SettlementAmendmentTrustStore(
        amendment_producer=p12_bundle["trust"].cohort_producer,
        completeness_verifier=p12_bundle["trust"].measurement_verifier,
    )
    settlement_policy = SettlementAmendmentPolicy(
        trust_store_sha256=hash_settlement_trust_store(settlement_trust),
        p12_policy_sha256=hash_measurement_policy(p12_bundle["policy"]),
        p12_trust_store_sha256=hash_measurement_trust_store(p12_bundle["trust"]),
        completeness_rule_sha256=_sha("settlement-completeness"),
        maximum_amendment_ttl_seconds=7 * 24 * 60 * 60,
        maximum_completeness_ttl_seconds=7 * 24 * 60 * 60,
    )
    identity_key = b"p17-identity-key" * 3
    policy = TractionPolicy(
        trust_store_sha256=hash_traction_trust_store(trust),
        ledger_store_id_sha256=_sha("traction-store"),
        p12_policy_sha256=hash_measurement_policy(p12_bundle["policy"]),
        p12_trust_store_sha256=hash_measurement_trust_store(p12_bundle["trust"]),
        settlement_policy_sha256=hash_settlement_policy(settlement_policy),
        settlement_trust_store_sha256=hash_settlement_trust_store(
            settlement_trust
        ),
        identity_hmac_key_id_sha256=hashlib.sha256(identity_key).hexdigest(),
        maximum_plan_ttl_seconds=400 * 24 * 60 * 60,
        maximum_observation_ttl_seconds=7 * 24 * 60 * 60,
        clock_response_timeout_seconds=clock_response_timeout_seconds,
    )
    issued = p12.START_UTC - timedelta(days=1)
    expires = p12.START_UTC + timedelta(days=240)
    plan = sign_traction_plan(
        policy=policy,
        trust_store=trust,
        signing_key=human,
        issuer="traction-human",
        property_record_sha256=p12_bundle["policy"].property_record_sha256,
        property_domain_sha256=p12_bundle["policy"].property_domain_sha256,
        measured_release_sha256=p12_bundle["plan"].definition.fault_target_release_sha256,
        measured_artifact_sha256=p12_bundle["plan"].definition.fault_target_artifact_sha256,
        measured_schema_sha256=p12_bundle["plan"].definition.fault_target_schema_sha256,
        partner_ids=p12_bundle["plan"].definition.partner_ids,
        rights_evidence_sha256=_sha("rights"),
        rights_expires_at=expires + timedelta(days=1),
        affiliate_evidence_sha256=_sha("affiliate"),
        affiliate_expires_at=expires + timedelta(days=1),
        experiment_started_at=p12.START_UTC,
        issued_at=issued,
        expires_at=expires,
    )
    pins = TractionAuthorityPins(
        expected_policy_sha256=hash_traction_policy(policy),
        expected_trust_store_sha256=hash_traction_trust_store(trust),
        expected_plan_sha256=hash_traction_artifact(plan),
        expected_ledger_store_id_sha256=policy.ledger_store_id_sha256,
        expected_property_record_sha256=plan.property_record_sha256,
        expected_property_domain_sha256=plan.property_domain_sha256,
        expected_release_sha256=plan.measured_release_sha256,
        expected_artifact_sha256=plan.measured_artifact_sha256,
        expected_schema_sha256=plan.measured_schema_sha256,
        expected_partner_set_sha256=plan.partner_set_sha256,
        expected_p12_policy_sha256=policy.p12_policy_sha256,
        expected_p12_trust_store_sha256=policy.p12_trust_store_sha256,
        expected_settlement_policy_sha256=policy.settlement_policy_sha256,
        expected_settlement_trust_store_sha256=policy.settlement_trust_store_sha256,
    )
    return {
        "human": human,
        "qa": qa,
        "clock": clock,
        "trust": trust,
        "policy": policy,
        "plan": plan,
        "pins": pins,
        "identity_key": identity_key,
        "p12": p12_bundle,
        "settlement_policy": settlement_policy,
        "settlement_trust": settlement_trust,
    }


def _packet(bundle) -> P12AuthorityPacket:
    report = p12._evaluate(bundle)
    return P12AuthorityPacket(
        policy=bundle["policy"],
        trust_store=bundle["trust"],
        authority_pins=bundle["pins"],
        plan=bundle["plan"],
        demand_batch=bundle["demand"],
        cohort_batch=bundle["cohort"],
        operations_batch=bundle["operations"],
        demand_attestation=bundle["demand_attestation"],
        cohort_attestation=bundle["cohort_attestation"],
        operations_attestation=bundle["operations_attestation"],
        bundle_index=bundle["index"],
        report=report,
    )


def _operations_activity(
    packet: P12AuthorityPacket,
    *,
    daily_rows=None,
):
    definitions = (
        RoutineTaskDefinition(
            task_id="automated-routine",
            definition_sha256=_sha("activity-definition:auto"),
            mode=RoutineTaskMode.AUTOMATED,
        ),
        RoutineTaskDefinition(
            task_id="manual-routine",
            definition_sha256=_sha("activity-definition:manual"),
            mode=RoutineTaskMode.MANUAL,
        ),
    )
    rows = packet.operations_batch.summary.daily_summaries
    if daily_rows is not None:
        rows = daily_rows
    schedules = []
    executions = []
    activities = []
    for day, row in enumerate(rows):
        manual_count = row.routine_tasks_total - row.routine_tasks_automated
        if manual_count and row.human_minutes < manual_count:
            raise AssertionError("test activity needs at least one minute per manual task")
        manual_minutes = (
            []
            if manual_count == 0
            else [
                row.human_minutes // manual_count
                + (1 if index < row.human_minutes % manual_count else 0)
                for index in range(manual_count)
            ]
        )
        for number in range(row.routine_tasks_total):
            automated = number < row.routine_tasks_automated
            definition = definitions[0 if automated else 1]
            occurrence = _sha(f"activity-occurrence:{day}:{number}")
            scheduled_for = packet.report.observation_started_at + timedelta(
                days=day, hours=1, minutes=number * 60
            )
            schedules.append(
                ScheduledRoutineTask(
                    occurrence_id_sha256=occurrence,
                    task_id=definition.task_id,
                    definition_sha256=definition.definition_sha256,
                    local_date=row.local_date,
                    scheduled_for=scheduled_for,
                )
            )
            minutes = 0 if automated else manual_minutes[number - row.routine_tasks_automated]
            succeeded = number < row.job_runs_succeeded
            executions.append(
                RoutineTaskExecution(
                    occurrence_id_sha256=occurrence,
                    execution_receipt_sha256=_sha(
                        f"activity-execution:{day}:{number}"
                    ),
                    mode=definition.mode,
                    started_at=scheduled_for,
                    completed_at=scheduled_for
                    + timedelta(minutes=max(1, minutes + 1)),
                    outcome=(
                        RoutineExecutionOutcome.SUCCEEDED
                        if succeeded
                        else RoutineExecutionOutcome.FAILED
                    ),
                    exception_count=(
                        row.exceptions_total if number == 0 else 0
                    ),
                    major_misstatement_count=(
                        row.major_misstatements if number == 0 else 0
                    ),
                )
            )
            if not automated:
                activities.append(
                    HumanActivityEvent(
                        activity_id_sha256=_sha(f"activity-human:{day}:{number}"),
                        actor_identity_token_sha256=_sha("activity-test-actor"),
                        role_id="operator",
                        occurrence_id_sha256=occurrence,
                        source_receipt_sha256=_sha(
                            f"activity-human-receipt:{day}:{number}"
                        ),
                        started_at=scheduled_for,
                        ended_at=scheduled_for + timedelta(minutes=minutes),
                    )
                )
        unbound_minutes = row.human_minutes - sum(manual_minutes)
        if unbound_minutes:
            if not schedules:
                raise AssertionError("test activity cannot bind human time")
            occurrence = schedules[-row.routine_tasks_total].occurrence_id_sha256
            execution_index = len(executions) - row.routine_tasks_total
            selected = executions[execution_index]
            executions[execution_index] = selected.model_copy(
                update={
                    "completed_at": selected.started_at
                    + timedelta(minutes=unbound_minutes + 1)
                }
            )
            activities.append(
                HumanActivityEvent(
                    activity_id_sha256=_sha(f"activity-human-oversight:{day}"),
                    actor_identity_token_sha256=_sha("activity-test-actor"),
                    role_id="operator",
                    occurrence_id_sha256=occurrence,
                    source_receipt_sha256=_sha(
                        f"activity-human-oversight-receipt:{day}"
                    ),
                    started_at=selected.started_at,
                    ended_at=selected.started_at
                    + timedelta(minutes=unbound_minutes),
                )
            )
    policy_values = {
        "policy_id": "traction-test-operating-cost",
        "role_labor_rates": (
            RoleLaborRate(role_id="operator", hourly_cost_jpy=Decimal("0")),
        ),
        "maximum_evidence_ttl_seconds": 2_678_400,
    }
    policy_provisional = OperationalCostPolicy.model_construct(
        **policy_values,
        schema_version="1.0",
        objective_basis="net_operating_profit",
        target_monthly_net_profit_jpy=Decimal("200000"),
        policy_sha256="0" * 64,
    )
    cost_policy = OperationalCostPolicy(
        **policy_values,
        policy_sha256=hash_operational_cost_policy(policy_provisional),
    )
    batch_values = {
        "batch_id": f"traction-activity-{packet.report.run_id}",
        "source_operations_batch_sha256": hash_signed_artifact(
            packet.operations_batch
        ),
        "observation_started_at": packet.report.observation_started_at,
        "observation_ended_at": packet.report.observation_ended_at,
        "captured_at": packet.report.issued_at,
        "expires_at": packet.operations_batch.summary.expires_at,
        "definitions": definitions,
        "schedules": tuple(
            sorted(schedules, key=lambda item: item.occurrence_id_sha256)
        ),
        "executions": tuple(
            sorted(executions, key=lambda item: item.occurrence_id_sha256)
        ),
        "human_activities": tuple(
            sorted(activities, key=lambda item: item.activity_id_sha256)
        ),
        "resource_usage": (),
    }
    provisional = OperationsActivityBatch.model_construct(
        **batch_values,
        schema_version="1.0",
        source_timezone="Asia/Tokyo",
        batch_sha256="0" * 64,
    )
    activity_batch = OperationsActivityBatch(
        **batch_values,
        batch_sha256=hash_operations_activity_batch(provisional),
    )
    return activity_batch, cost_policy


def _shift_operations_activity(
    observation: TractionObservation,
    *,
    started_at,
    issued_at,
    suffix: str,
):
    prior = observation.operations_activity_batch
    delta = started_at - prior.observation_started_at
    schedules = tuple(
        item.model_copy(
            update={
                "local_date": (item.scheduled_for + delta).astimezone(
                    traction_module._TOKYO
                ).date(),
                "scheduled_for": item.scheduled_for + delta,
            }
        )
        for item in prior.schedules
    )
    executions = tuple(
        item.model_copy(
            update={
                "started_at": item.started_at + delta,
                "completed_at": item.completed_at + delta,
            }
        )
        for item in prior.executions
    )
    activities = tuple(
        item.model_copy(
            update={
                "started_at": item.started_at + delta,
                "ended_at": item.ended_at + delta,
            }
        )
        for item in prior.human_activities
    )
    values = {
        **prior.model_dump(
            mode="python",
            exclude={
                "schema_version",
                "source_timezone",
                "batch_sha256",
                "batch_id",
                "observation_started_at",
                "observation_ended_at",
                "captured_at",
                "expires_at",
                "schedules",
                "executions",
                "human_activities",
            },
        ),
        "batch_id": f"traction-activity-{suffix}",
        "observation_started_at": started_at,
        "observation_ended_at": started_at + timedelta(days=30),
        "captured_at": issued_at,
        "expires_at": issued_at + timedelta(days=7),
        "schedules": schedules,
        "executions": executions,
        "human_activities": activities,
        "definitions": prior.definitions,
    }
    provisional = OperationsActivityBatch.model_construct(
        **values,
        schema_version="1.0",
        source_timezone="Asia/Tokyo",
        batch_sha256="0" * 64,
    )
    batch = OperationsActivityBatch(
        **values,
        batch_sha256=hash_operations_activity_batch(provisional),
    )
    summary = derive_operations_activity(
        batch,
        observation.operational_cost_policy,
        gross_settled_revenue_jpy=observation.settled_amount_at_window_end,
        at=issued_at,
    )
    return batch, summary


def _real_observation(context) -> TractionObservation:
    packet = _packet(context["p12"])
    activity_batch, cost_policy = _operations_activity(packet)
    return build_traction_observation(
        packet,
        context["p12"]["runtime"],
        traction_plan=context["plan"],
        traction_policy=context["policy"],
        traction_trust_store=context["trust"],
        authority_pins=context["pins"],
        observation_signing_key=context["qa"],
        identity_hmac_key=context["identity_key"],
        operations_activity_batch=activity_batch,
        operational_cost_policy=cost_policy,
        ordinal=1,
        predecessor_sha256="0" * 64,
        at=packet.report.issued_at,
    )


def _settlement_evidence(
    context,
    observation,
    *,
    observed=None,
    label="zero-event",
    events=(),
):
    packet = _packet(context["p12"])
    binding = build_original_settlement_binding(
        packet.report,
        packet.policy,
        packet.trust_store,
        packet.authority_pins,
        packet.plan,
        packet.bundle_index,
        packet.cohort_batch,
        packet.cohort_attestation,
        original_verified_at=p12.AT,
    )
    observed = (
        observation.observation_ended_at + timedelta(days=30)
        if observed is None
        else observed
    )
    issued = observed + timedelta(hours=1)
    expires = issued + timedelta(days=6)
    amendment = sign_settlement_amendment(
        binding,
        tuple(events),
        context["settlement_policy"],
        context["settlement_trust"],
        context["p12"]["keys"]["cohort"],
        amendment_id_sha256=_sha(f"{label}-amendment"),
        observed_through_at=observed,
        issued_at=issued,
        expires_at=expires,
    )
    coverage = SettlementCompletenessCoverage(
        source_export_sha256=_sha(f"{label}-export"),
        complete_export_receipt_sha256=_sha(f"{label}-complete-export"),
        coverage_rule_sha256=context["settlement_policy"].completeness_rule_sha256,
        raw_records=len(events),
        accepted_records=len(events),
        rejected_records=0,
        duplicate_records=0,
        conflict_records=0,
        unknown_records=0,
        output_records=len(events),
        event_id_set_sha256=p12._set_hash(
            [event.event_id_sha256 for event in events]
        ),
        privacy_scan_sha256=_sha(f"{label}-privacy"),
        privacy_scan_passed=True,
    )
    completeness = sign_settlement_completeness_attestation(
        amendment,
        binding,
        coverage,
        context["settlement_policy"],
        context["settlement_trust"],
        context["p12"]["keys"]["qa"],
        decision=SettlementCompletenessDecision.COMPLETE,
        issued_at=issued + timedelta(hours=1),
        expires_at=expires,
    )
    return (
        TractionSettlementEvidence(
            observation_sha256=hash_traction_artifact(observation),
            original_binding=binding,
            cohort_batch=packet.cohort_batch,
            amendments=(amendment,),
            completeness_attestations=(completeness,),
        ),
        issued + timedelta(hours=2),
    )


def _clock_service(context, state):
    def attest(request):
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=state["now"],
        )

    return attest


def _synthetic_observation(
    context,
    *,
    clicks: int = 1000,
    qualified: int = 10000,
    settled: Decimal = Decimal("200000"),
    partner_amounts: tuple[Decimal, Decimal, Decimal] = (
        Decimal("80000"),
        Decimal("60000"),
        Decimal("60000"),
    ),
    automation_total: int = 100,
    automation_done: int = 80,
    human_minutes: int = 720,
    jobs_total: int = 100,
    jobs_succeeded: int = 99,
    provenance: TractionProvenance = TractionProvenance.VERIFIED_P12,
) -> TractionObservation:
    plan = context["plan"]
    packet = _packet(context["p12"])
    values = _real_observation(context).model_dump(
        mode="python", exclude={"payload_sha256", "signature_base64url"}
    )
    if jobs_total != automation_total:
        raise AssertionError("test activity requires one logical run per routine task")

    def distribute(total: int) -> list[int]:
        return [
            total // 30 + (1 if day < total % 30 else 0)
            for day in range(30)
        ]

    task_counts = distribute(automation_total)
    automated_counts = []
    remaining_automated = automation_done
    for count in task_counts:
        selected = min(count, remaining_automated)
        automated_counts.append(selected)
        remaining_automated -= selected
    success_counts = []
    remaining_success = jobs_succeeded
    for count in task_counts:
        selected = min(count, remaining_success)
        success_counts.append(selected)
        remaining_success -= selected
    manual_counts = [
        total - automated
        for total, automated in zip(task_counts, automated_counts, strict=True)
    ]
    effective_human_minutes = 0 if automation_total == 0 else human_minutes
    human_counts = list(manual_counts)
    remaining_human = effective_human_minutes - sum(human_counts)
    if remaining_human < 0:
        raise AssertionError("test activity has less than one minute per manual task")
    eligible_days = [
        day for day, count in enumerate(manual_counts) if count > 0
    ] or [day for day, count in enumerate(task_counts) if count > 0]
    for offset in range(remaining_human):
        human_counts[eligible_days[offset % len(eligible_days)]] += 1
    daily_rows = tuple(
        original.model_copy(
            update={
                "human_minutes": human_counts[day],
                "routine_tasks_total": task_counts[day],
                "routine_tasks_automated": automated_counts[day],
                "job_runs_total": task_counts[day],
                "job_runs_succeeded": success_counts[day],
                "exceptions_total": 24 if day == 0 and task_counts[day] else 0,
                "major_misstatements": 0,
            }
        )
        for day, original in enumerate(
            packet.operations_batch.summary.daily_summaries
        )
    )
    activity_batch, cost_policy = _operations_activity(
        packet, daily_rows=daily_rows
    )
    activity = derive_operations_activity(
        activity_batch,
        cost_policy,
        gross_settled_revenue_jpy=settled,
        at=packet.report.issued_at,
    )
    values.update({
        "provenance": provenance,
        "qualified_sessions": qualified,
        "valid_outbound_clicks": clicks,
        "settled_amount_at_window_end": settled,
        "partner_facts": tuple(
            PartnerTractionFacts(partner_id=partner, settled_amount=amount)
            for partner, amount in zip(plan.partner_ids, partner_amounts, strict=True)
        ),
        "bear_qualified_sessions": Decimal("10000"),
        "bear_outbound_click_rate": Decimal("0.10"),
        "operations_activity_batch": activity_batch,
        "operational_cost_policy": cost_policy,
        "operations_activity": activity,
        "human_minutes": effective_human_minutes,
        "routine_tasks_total": automation_total,
        "routine_tasks_automated": automation_done,
        "job_runs_total": jobs_total,
        "job_runs_succeeded": jobs_succeeded,
        "major_misstatements": 0,
        "exceptions_total": sum(item.exceptions_total for item in daily_rows),
        "exact_faults_passed": 8,
        "click_identity_tokens": tuple(
            sorted(_sha(f"click:{number}") for number in range(clicks))
        ),
        "transaction_identity_tokens": (),
        "issued_at": p12.AT,
        "expires_at": p12.AT + timedelta(days=7),
    })
    return _sign_model(TractionObservation, values, context["qa"])


def _evaluate(context, observation, *, complete=True):
    evidence = ()
    at = p12.AT
    if complete:
        item, at = _settlement_evidence(context, observation)
        evidence = (item,)
    return evaluate_traction(
        (observation,),
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        at=at,
        settlement_evidence=evidence,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )


def test_complete_p12_packet_is_rerun_and_minimized() -> None:
    context = _traction_context()
    observation = _real_observation(context)
    assert observation.valid_outbound_clicks == 4
    assert observation.settled_amount_at_window_end == Decimal("300")
    assert observation.human_minutes == 720
    assert observation.exact_faults_passed == 8
    assert not hasattr(observation, "transactions")
    report = _evaluate(context, observation, complete=False)
    assert report.decision is TractionDecision.CONTINUE_OBSERVATION
    assert report.settlement_complete is False


def test_plan_full_substitution_and_exact_expiry_fail() -> None:
    context = _traction_context()
    assert verify_traction_plan(
        context["plan"], context["policy"], context["trust"], context["pins"], at=p12.AT
    )
    assert not verify_traction_plan(
        context["plan"],
        context["policy"],
        context["trust"],
        context["pins"],
        at=context["plan"].expires_at,
    )
    replaced_pins = context["pins"].model_copy(
        update={"expected_plan_sha256": _sha("attacker-plan")}
    )
    assert not verify_traction_plan(
        context["plan"], context["policy"], context["trust"], replaced_pins, at=p12.AT
    )


def test_999_clicks_continue_but_1000_needs_authenticated_ledger_for_review(
    tmp_path,
) -> None:
    immature_context = _traction_context(_p12_metric_bundle(clicks=999))
    assert (
        _evaluate(immature_context, _real_observation(immature_context)).decision
        is TractionDecision.CONTINUE_OBSERVATION
    )
    mature_context = _traction_context(_p12_metric_bundle(clicks=1000))
    observation = _real_observation(mature_context)
    bare_report = _evaluate(mature_context, observation)
    assert bare_report.decision is TractionDecision.STOP
    assert bare_report.ledger_authenticated is False

    anchor = {"value": ""}
    clock_state = {"now": p12.AT}
    ledger_key = b"mature-ledger-authentication-key" * 2

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "mature-traction.db",
        plan=mature_context["plan"],
        policy=mature_context["policy"],
        trust_store=mature_context["trust"],
        authority_pins=mature_context["pins"],
        state_authentication_key=ledger_key,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(mature_context, clock_state),
    )
    ledger.append(observation)
    evidence, evaluated_at = _settlement_evidence(mature_context, observation)
    clock_state["now"] = evaluated_at
    ledger.append_settlement(
        evidence,
        settlement_policy=mature_context["settlement_policy"],
        settlement_trust_store=mature_context["settlement_trust"],
    )
    settlement_anchor = anchor["value"]
    assert (
        ledger.append_settlement(
            evidence,
            settlement_policy=mature_context["settlement_policy"],
            settlement_trust_store=mature_context["settlement_trust"],
        )
        == evidence
    )
    assert anchor["value"] == settlement_anchor
    report = ledger.evaluate(
        settlement_policy=mature_context["settlement_policy"],
        settlement_trust_store=mature_context["settlement_trust"],
    )
    assert report.decision is TractionDecision.READY_FOR_SCALE_REVIEW
    assert report.ledger_authenticated is True
    assert report.settlement_evidence_sha256s == (
        hash_traction_artifact(evidence),
    )
    assert ledger.reports() == (report,)
    reopened = TractionLedger(
        tmp_path / "mature-traction.db",
        plan=mature_context["plan"],
        policy=mature_context["policy"],
        trust_store=mature_context["trust"],
        authority_pins=mature_context["pins"],
        state_authentication_key=ledger_key,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(mature_context, clock_state),
    )
    assert reopened.observations() == (observation,)
    assert reopened.reports() == (report,)
    class Bootstrap:
        def open_traction_ledger(self):
            return reopened

    broker = TractionRuntimeBroker(Bootstrap())
    assert broker.observations() == (observation,)
    assert broker.reports() == (report,)
    forbidden_runtime_parameters = {
        "state_authentication_key",
        "anchor_commit",
        "anchor_read",
        "clock_attest",
        "private_key",
        "secret",
    }
    for method_name in (
        "append_observation",
        "append_settlement",
        "evaluate",
        "observations",
        "reports",
    ):
        assert not forbidden_runtime_parameters.intersection(
            inspect.signature(getattr(broker, method_name)).parameters
        )
    assert "settlement_evidence" not in inspect.signature(
        reopened.evaluate
    ).parameters
    assert "ledger_authenticated" not in inspect.signature(
        _evaluate_traction
    ).parameters

    refresh_observed = evidence.amendments[0].expires_at + timedelta(hours=1)
    refreshed, refreshed_at = _settlement_evidence(
        mature_context,
        observation,
        observed=refresh_observed,
        label="refreshed-zero-event",
    )
    clock_state["now"] = refreshed_at
    ledger.append_settlement(
        refreshed,
        settlement_policy=mature_context["settlement_policy"],
        settlement_trust_store=mature_context["settlement_trust"],
    )
    refreshed_report = ledger.evaluate(
        settlement_policy=mature_context["settlement_policy"],
        settlement_trust_store=mature_context["settlement_trust"],
    )
    assert refreshed_report.decision is TractionDecision.READY_FOR_SCALE_REVIEW
    assert refreshed_report.settlement_evidence_sha256s == (
        hash_traction_artifact(refreshed),
    )
    assert reopened.reports() == (report, refreshed_report)


@pytest.mark.parametrize(
    ("updates", "failed_check"),
    [
        ({"settled": Decimal("59990"), "partner_amounts": (Decimal("23996"), Decimal("17997"), Decimal("17997"))}, "epc"),
        ({"settled": Decimal("199999.99"), "partner_amounts": (Decimal("79999.996"), Decimal("59999.997"), Decimal("59999.997"))}, "revenue"),
        ({"qualified": 10001}, "ctr"),
        ({"partner_amounts": (Decimal("80000.01"), Decimal("60000"), Decimal("59999.99"))}, "concentration"),
        ({"automation_done": 79}, "automation"),
        ({"human_minutes": 721}, "human"),
        ({"jobs_succeeded": 98}, "jobs"),
    ],
)
def test_exact_scale_boundaries_fail_below_or_above(updates, failed_check) -> None:
    partner_amounts = updates.get(
        "partner_amounts",
        (Decimal("80000"), Decimal("60000"), Decimal("60000")),
    )
    qualified = updates.get("qualified", 10000)
    context = _traction_context(
        _p12_metric_bundle(
            qualified=qualified,
            partner_amounts=partner_amounts,
        )
    )
    observation = _real_observation(context)
    local_updates = {
        key: value
        for key, value in updates.items()
        if key
        in {
            "automation_done",
            "human_minutes",
            "jobs_succeeded",
        }
    }
    if local_updates:
        observation = _synthetic_observation(context, **local_updates)
    report = _evaluate(context, observation)
    assert report.decision is TractionDecision.STOP
    assert next(item for item in report.checks if item.name == failed_check).status.value == "fail"


def test_zero_routine_task_denominator_has_exact_zero_automation_rate() -> None:
    context = _traction_context(_p12_metric_bundle())
    observation = _synthetic_observation(
        context,
        automation_total=0,
        automation_done=0,
        jobs_total=0,
        jobs_succeeded=0,
    )
    report = _evaluate(context, observation)
    check = next(item for item in report.checks if item.name == "automation")
    assert report.latest_automation_rate == Decimal(0)
    assert check.observed == "0"
    assert check.status.value == "fail"


def test_signed_aggregate_tamper_is_rejected_without_matching_activity_rows() -> None:
    context = _traction_context(_p12_metric_bundle())
    observation = _synthetic_observation(context)
    values = observation.model_dump(
        mode="python", exclude={"payload_sha256", "signature_base64url"}
    )
    values["human_minutes"] = observation.human_minutes + 1
    with pytest.raises(ValueError, match="not reconstructable"):
        _sign_model(TractionObservation, values, context["qa"])


def test_p17_monthly_goal_uses_net_profit_after_receipt_backed_tco() -> None:
    context = _traction_context(_p12_metric_bundle())
    observation = _synthetic_observation(context)
    policy_values = observation.operational_cost_policy.model_dump(
        mode="python", exclude={"policy_sha256"}
    )
    policy_values["role_labor_rates"] = (
        RoleLaborRate(role_id="operator", hourly_cost_jpy=Decimal("5000")),
    )
    provisional = OperationalCostPolicy.model_construct(
        **policy_values, policy_sha256="0" * 64
    )
    cost_policy = OperationalCostPolicy(
        **policy_values,
        policy_sha256=hash_operational_cost_policy(provisional),
    )
    activity = derive_operations_activity(
        observation.operations_activity_batch,
        cost_policy,
        gross_settled_revenue_jpy=observation.settled_amount_at_window_end,
        at=observation.ingested_at,
    )
    values = observation.model_dump(
        mode="python", exclude={"payload_sha256", "signature_base64url"}
    )
    values.update(
        {
            "operational_cost_policy": cost_policy,
            "operations_activity": activity,
        }
    )
    costed = _sign_model(TractionObservation, values, context["qa"])
    report = _evaluate(context, costed)
    assert report.latest_revenue == Decimal("200000")
    assert report.latest_operating_tco == Decimal("60000")
    assert report.latest_net_operating_profit == Decimal("140000")
    assert report.decision is TractionDecision.STOP
    revenue = next(item for item in report.checks if item.name == "revenue")
    assert revenue.status.value == "fail"
    assert "net operating profit" in revenue.requirement


def test_high_precision_concentration_cannot_round_or_signature_collide() -> None:
    context = _traction_context(_p12_metric_bundle())
    amounts = (
        Decimal("400000000000000000000.00000001"),
        Decimal("300000000000000000000"),
        Decimal("299999999999999999999.99999999"),
    )
    observation = _synthetic_observation(
        context,
        settled=Decimal("1000000000000000000000"),
        partner_amounts=amounts,
    )
    report = _evaluate(context, observation, complete=False)
    concentration = next(
        item for item in report.checks if item.name == "concentration"
    )
    assert report.latest_max_partner_share > Decimal("0.40")
    assert concentration.status.value == "fail"

    altered = observation.model_dump(mode="python")
    altered["partner_facts"] = (
        PartnerTractionFacts(
            partner_id=context["plan"].partner_ids[0],
            settled_amount=Decimal("400000000000000000000.00000002"),
        ),
        PartnerTractionFacts(
            partner_id=context["plan"].partner_ids[1],
            settled_amount=amounts[1],
        ),
        PartnerTractionFacts(
            partner_id=context["plan"].partner_ids[2],
            settled_amount=Decimal("299999999999999999999.99999998"),
        ),
    )
    with pytest.raises(ValueError, match="payload hash mismatch"):
        TractionObservation.model_validate(altered)


def test_synthetic_provenance_never_reaches_review() -> None:
    context = _traction_context(_p12_metric_bundle())
    observation = _synthetic_observation(
        context, provenance=TractionProvenance.SYNTHETIC_CONTRACT
    )
    assert _evaluate(context, observation).decision is TractionDecision.STOP


def test_six_contiguous_windows_make_day_180_mature_but_need_settlement() -> None:
    context = _traction_context(_p12_metric_bundle(clicks=167, qualified=1670))
    first = _real_observation(context)
    observations = []
    previous = "0" * 64
    click_counts = (167, 167, 167, 167, 167, 164)
    for ordinal, click_count in enumerate(click_counts, 1):
        values = first.model_dump(
            mode="python", exclude={"payload_sha256", "signature_base64url"}
        )
        started = context["plan"].experiment_started_at + timedelta(
            days=30 * (ordinal - 1)
        )
        issued = started + timedelta(days=30, hours=6)
        activity_batch, activity = _shift_operations_activity(
            first,
            started_at=started,
            issued_at=issued,
            suffix=f"window-{ordinal}",
        )
        values.update(
            {
                "ordinal": ordinal,
                "predecessor_sha256": previous,
                "run_id": f"synthetic-window-{ordinal}",
                "cohort_id": f"synthetic-cohort-{ordinal}",
                "p12_report_sha256": _sha(f"window-report:{ordinal}"),
                "valid_outbound_clicks": click_count,
                "qualified_sessions": click_count * 10,
                "click_identity_tokens": tuple(
                    sorted(
                        _sha(f"window:{ordinal}:click:{number}")
                        for number in range(click_count)
                    )
                ),
                "transaction_identity_tokens": tuple(
                    sorted(
                        _sha(f"window:{ordinal}:transaction:{number}")
                        for number in range(3)
                    )
                ),
                "observation_started_at": started,
                "observation_ended_at": started + timedelta(days=30),
                "ingested_at": issued,
                "issued_at": issued,
                "expires_at": issued + timedelta(days=7),
                "operations_activity_batch": activity_batch,
                "operations_activity": activity,
            }
        )
        item = _sign_model(TractionObservation, values, context["qa"])
        observations.append(item)
        previous = hash_traction_artifact(item)
    report = evaluate_traction(
        tuple(observations),
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        at=context["plan"].experiment_ended_at + timedelta(hours=6),
    )
    assert report.covered_days == 180
    assert report.cumulative_valid_clicks == 999
    assert report.traction_mature is True
    assert report.decision is TractionDecision.STOP


def test_ledger_append_is_idempotent_and_tamper_evident(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    clock_state = {"now": p12.AT}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "traction.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"ledger-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, clock_state),
    )
    assert ledger.append(observation) == observation
    assert ledger.append(observation) == observation
    assert ledger.observations() == (observation,)
    with ledger._connect() as connection:
        with pytest.raises(Exception):
            connection.execute(
                "UPDATE traction_observations SET run_id='tampered' WHERE ordinal=1"
            )


def test_backdated_append_after_late_anchored_event_is_rejected(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    clock_state = {"now": observation.expires_at + timedelta(days=1)}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "clock-rewind.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-rewind-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, clock_state),
    )
    late = observation.expires_at + timedelta(days=1)
    late_report = ledger.evaluate()
    assert late_report.decision is TractionDecision.STOP

    clock_state["now"] = observation.issued_at
    with pytest.raises(TractionInputError, match="cannot move backward"):
        ledger.append(observation)
    assert ledger.observations() == ()


def test_next_event_cannot_precede_prior_post_anchor_finalization(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    clock_values = iter(
        (
            p12.AT,
            p12.AT + timedelta(hours=2),
            p12.AT + timedelta(hours=1),
        )
    )

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def sequenced_clock(request):
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=next(clock_values),
        )

    ledger = TractionLedger.create(
        tmp_path / "finalization-rewind.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"finalization-rewind-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=sequenced_clock,
    )
    assert ledger.append(observation) == observation
    with pytest.raises(TractionInputError, match="cannot move backward"):
        ledger.evaluate()
    assert ledger.observations() == (observation,)
    assert ledger.reports() == ()


def test_online_clock_nonce_rejects_cached_receipt_replay(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    cached = {"attestation": None}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def replaying_clock(request):
        if cached["attestation"] is None:
            cached["attestation"] = sign_traction_clock_attestation(
                request,
                context["trust"],
                context["clock"],
                observed_at=p12.AT,
            )
        return cached["attestation"]

    ledger = TractionLedger.create(
        tmp_path / "clock-replay.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-replay-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=replaying_clock,
    )
    with pytest.raises(TractionInputError, match="untrusted"):
        ledger.append(observation)
    with pytest.raises(TractionInputError, match="untrusted"):
        ledger.observations()
    assert "at" not in inspect.signature(ledger.append).parameters
    assert "clock_attestation" not in inspect.signature(ledger.append).parameters


def test_post_anchor_finalization_rejects_inflight_expiry_delay(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    calls = {"count": 0}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def delayed_clock(request):
        calls["count"] += 1
        observed_at = (
            observation.issued_at
            if calls["count"] == 1
            else observation.expires_at
        )
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=observed_at,
        )

    ledger = TractionLedger.create(
        tmp_path / "clock-delay.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-delay-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=delayed_clock,
    )
    with pytest.raises(TractionInputError, match="not finalized before"):
        ledger.append(observation)
    assert ledger.observations() == ()
    with ledger._connect() as connection:
        row = connection.execute(
            "SELECT outcome FROM traction_finalizations"
        ).fetchone()
    assert row["outcome"] == "expired"
    stopped = ledger.evaluate()
    assert stopped.decision is TractionDecision.STOP
    assert ledger.reports() == (stopped,)


def test_transient_finalization_failure_is_resumed_on_retry_and_reopen(
    tmp_path,
) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    fail_finalization = {"value": True}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def recoverable_clock(request):
        if (
            request.purpose.value == "finalize_event"
            and fail_finalization["value"]
        ):
            fail_finalization["value"] = False
            raise RuntimeError("transient clock failure")
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=p12.AT,
        )

    path = tmp_path / "recover-finalization.db"
    ledger = TractionLedger.create(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"recover-finalization-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=recoverable_clock,
    )
    with pytest.raises(TractionInputError, match="callback failed"):
        ledger.append(observation)
    assert ledger.append(observation) == observation
    reopened = TractionLedger(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"recover-finalization-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=recoverable_clock,
    )
    assert reopened.observations() == (observation,)


def test_one_ahead_target_anchor_is_recovered_before_finalization(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    fail_revision_one = {"value": True}

    def commit(revision: int, value: str) -> None:
        if revision == 1 and fail_revision_one["value"]:
            fail_revision_one["value"] = False
            raise RuntimeError("anchor unavailable")
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "recover-target-anchor.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"recover-target-anchor-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    with pytest.raises(
        TractionInputError, match="traction-anchor-commit failed"
    ) as captured:
        ledger.append(observation)
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "anchor unavailable"
    assert ledger.append(observation) == observation
    assert ledger.observations() == (observation,)


def test_cross_process_file_lock_has_a_fixed_deadline(
    tmp_path, monkeypatch
) -> None:
    context = _traction_context()
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "cross-process-lock-timeout.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"cross-process-lock-timeout-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    holder = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "import fcntl, sys, time; "
                "handle = open(sys.argv[1], 'a+b'); "
                "fcntl.flock(handle.fileno(), fcntl.LOCK_EX); "
                "print('locked', flush=True); "
                "time.sleep(30)"
            ),
            str(ledger._lock_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        monkeypatch.setattr(
            traction_module, "_STORE_COORDINATION_TIMEOUT_SECONDS", 0.05
        )
        started = monotonic()
        with pytest.raises(
            TractionInputError, match="traction ledger lock timed out"
        ):
            ledger.observations()
        assert monotonic() - started < 0.5
    finally:
        holder.terminate()
        holder.wait(timeout=2)
    assert traction_module._FORK_CLEANUP_FDS == {}
    assert ledger.observations() == ()


def test_hung_anchor_read_has_a_fixed_deadline_and_releases_lock(
    tmp_path, monkeypatch
) -> None:
    context = _traction_context()
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "anchor-read-timeout.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"anchor-read-timeout-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    entered = Event()
    release = Event()
    finished = Event()

    def hung_read() -> str:
        entered.set()
        release.wait()
        finished.set()
        return anchor["value"]

    ledger._anchor_read = hung_read
    monkeypatch.setattr(
        traction_module, "_STORE_COORDINATION_TIMEOUT_SECONDS", 0.05
    )
    try:
        started = monotonic()
        with pytest.raises(
            TractionInputError, match="traction-anchor-read timed out"
        ):
            ledger.observations()
        assert monotonic() - started < 0.5
        assert entered.is_set()
        assert finished.is_set() is False
        assert len(traction_module._FORK_CLEANUP_FDS) == 1
    finally:
        release.set()
    assert finished.wait(timeout=1)
    assert traction_module._FORK_CLEANUP_FDS == {}
    assert ledger.observations() == ()


def test_hung_anchor_commit_fails_current_call_and_requires_explicit_recovery(
    tmp_path, monkeypatch
) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    block_revision_one = {"value": False}
    entered = Event()
    release = Event()
    finished = Event()

    def commit(revision: int, value: str) -> None:
        if revision == 1 and block_revision_one["value"]:
            entered.set()
            release.wait()
            anchor["value"] = value
            finished.set()
            return
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "anchor-commit-timeout.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"anchor-commit-timeout-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    block_revision_one["value"] = True
    monkeypatch.setattr(
        traction_module, "_STORE_COORDINATION_TIMEOUT_SECONDS", 0.05
    )
    try:
        started = monotonic()
        with pytest.raises(
            TractionInputError, match="traction-anchor-commit timed out"
        ):
            ledger.append(observation)
        assert monotonic() - started < 0.5
        assert entered.is_set()
        assert finished.is_set() is False
        with ledger._connect() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM traction_observations"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM traction_finalizations"
            ).fetchone()[0] == 0

        retry_started = monotonic()
        with pytest.raises(
            TractionInputError,
            match="traction anchor coordination lock timed out",
        ):
            ledger.append(observation)
        assert monotonic() - retry_started < 0.5
        assert finished.is_set() is False
        with ledger._connect() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM traction_finalizations"
            ).fetchone()[0] == 0
    finally:
        release.set()
    assert finished.wait(timeout=1)
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM traction_finalizations"
        ).fetchone()[0] == 0
    assert ledger.append(observation) == observation
    assert ledger.observations() == (observation,)


def test_reopen_resumes_pending_finalization(tmp_path) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}
    fail_once = {"value": True}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def clock(request):
        if request.purpose.value == "finalize_event" and fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("transient finalization failure")
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=p12.AT,
        )

    path = tmp_path / "reopen-finalization.db"
    ledger = TractionLedger.create(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"reopen-finalization-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=clock,
    )
    with pytest.raises(TractionInputError, match="callback failed"):
        ledger.append(observation)
    reopened = TractionLedger(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"reopen-finalization-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=clock,
    )
    assert reopened.observations() == (observation,)


def test_clock_callback_timeout_releases_ledger_locks(tmp_path) -> None:
    context = _traction_context(clock_response_timeout_seconds=1)
    observation = _real_observation(context)
    anchor = {"value": ""}
    release = Event()
    calls = {"count": 0}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def hung_clock(request):
        calls["count"] += 1
        release.wait()
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=p12.AT,
        )

    path = tmp_path / "clock-timeout.db"
    ledger = TractionLedger.create(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=hung_clock,
    )
    started = monotonic()
    with pytest.raises(TractionInputError, match="timed out"):
        ledger.append(observation)
    assert monotonic() - started < 2.5
    pending_worker = ledger._clock_thread
    assert pending_worker is not None and pending_worker.is_alive()
    for _ in range(4):
        with pytest.raises(TractionInputError, match="still running"):
            ledger.append(observation)
        assert ledger._clock_thread is pending_worker
    reopened = TractionLedger(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=hung_clock,
    )
    with pytest.raises(TractionInputError, match="still running"):
        reopened.append(observation)
    assert reopened._clock_thread is pending_worker
    alias_path = tmp_path / "clock-timeout-alias.db"
    os.link(path, alias_path)
    aliased = TractionLedger(
        alias_path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-timeout-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=hung_clock,
    )
    with pytest.raises(TractionInputError, match="still running"):
        aliased.append(observation)
    assert calls["count"] == 1
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM traction_observations"
        ).fetchone()[0] == 0
    release.set()
    pending_worker.join(timeout=1)
    assert pending_worker.is_alive() is False
    assert aliased.append(observation) == observation


@pytest.mark.parametrize("setup_boundary", ("queue", "thread"))
def test_clock_setup_failure_releases_tracked_host_lock(
    tmp_path, monkeypatch, setup_boundary
) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / f"clock-{setup_boundary}-failure.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-setup-failure-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )

    def fail_setup(*_args, **_kwargs):
        raise RuntimeError(f"synthetic {setup_boundary} failure")

    with monkeypatch.context() as patch:
        patch.setattr(traction_module, setup_boundary.title(), fail_setup)
        with pytest.raises(RuntimeError, match=f"synthetic {setup_boundary}"):
            ledger.append(observation)
    assert traction_module._FORK_CLEANUP_FDS == {}
    assert ledger.append(observation) == observation


def test_clock_thread_post_start_failure_keeps_one_shot_lock_owned(
    tmp_path, monkeypatch
) -> None:
    context = _traction_context(clock_response_timeout_seconds=1)
    observation = _real_observation(context)
    anchor = {"value": ""}
    callback_entered = Event()
    callback_release = Event()

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def blocked_clock(request):
        callback_entered.set()
        callback_release.wait()
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=p12.AT,
        )

    ledger = TractionLedger.create(
        tmp_path / "clock-post-start-failure.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-post-start-failure-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=blocked_clock,
    )
    real_thread = traction_module.Thread

    class StartThenRaise(real_thread):
        def start(self) -> None:
            super().start()
            raise RuntimeError("synthetic post-start failure")

    pending_worker = None
    try:
        with monkeypatch.context() as patch:
            patch.setattr(traction_module, "Thread", StartThenRaise)
            with pytest.raises(RuntimeError, match="synthetic post-start"):
                ledger.append(observation)
        assert callback_entered.wait(timeout=1)
        pending_worker = ledger._clock_thread
        assert pending_worker is not None and pending_worker.is_alive()
        assert traction_module._FORK_CLEANUP_FDS
        with pytest.raises(TractionInputError, match="still running"):
            ledger.append(observation)
    finally:
        callback_release.set()
        if pending_worker is not None:
            pending_worker.join(timeout=1)
    assert pending_worker is not None and pending_worker.is_alive() is False
    assert traction_module._FORK_CLEANUP_FDS == {}
    assert ledger.append(observation) == observation


def test_clock_ownership_notification_failure_releases_host_lock(
    tmp_path, monkeypatch
) -> None:
    context = _traction_context(clock_response_timeout_seconds=1)
    observation = _real_observation(context)
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "clock-ownership-notification-failure.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"clock-ownership-notification-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )

    class BrokenOwnershipEvent:
        def set(self) -> None:
            raise KeyboardInterrupt("synthetic ownership notification failure")

        def wait(self, timeout=None) -> bool:
            return False

    with monkeypatch.context() as patch:
        patch.setattr(traction_module, "Event", BrokenOwnershipEvent)
        with pytest.raises(TractionInputError, match="callback failed"):
            ledger.append(observation)
    assert traction_module._FORK_CLEANUP_FDS == {}
    assert ledger.append(observation) == observation


@pytest.mark.parametrize("failed_registration", (1, 2))
def test_descriptor_registration_failure_closes_untracked_fd(
    tmp_path, monkeypatch, failed_registration
) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / f"descriptor-registration-{failed_registration}.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"descriptor-registration-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )

    class FailSelectedRegistration(dict):
        def __init__(self) -> None:
            super().__init__()
            self.registrations = 0
            self.failed_descriptor = None

        def __setitem__(self, key, value) -> None:
            self.registrations += 1
            if self.registrations == failed_registration:
                self.failed_descriptor = key
                raise MemoryError("synthetic descriptor registry failure")
            super().__setitem__(key, value)

    registry = FailSelectedRegistration()
    with monkeypatch.context() as patch:
        patch.setattr(traction_module, "_FORK_CLEANUP_FDS", registry)
        with pytest.raises(MemoryError, match="descriptor registry"):
            ledger.append(observation)
        assert registry.failed_descriptor is not None
        with pytest.raises(OSError):
            os.fstat(registry.failed_descriptor)
        assert registry == {}
    assert ledger.append(observation) == observation


def test_clock_worker_lock_is_shared_across_processes_and_hardlinks(
    tmp_path,
) -> None:
    context = _traction_context(clock_response_timeout_seconds=1)
    observation = _real_observation(context)
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    path = tmp_path / "process-clock-timeout.db"
    TractionLedger.create(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"process-clock-timeout-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    alias_path = tmp_path / "process-clock-timeout-alias.db"
    os.link(path, alias_path)
    process_context = multiprocessing.get_context("fork")
    first_ready = process_context.Event()
    release = process_context.Event()
    calls = process_context.Value("i", 0)
    results = process_context.Queue()

    def run_candidate(selected_path, label):
        def blocked_clock(request):
            with calls.get_lock():
                calls.value += 1
            release.wait()
            return sign_traction_clock_attestation(
                request,
                context["trust"],
                context["clock"],
                observed_at=p12.AT,
            )

        ledger = TractionLedger(
            selected_path,
            plan=context["plan"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            state_authentication_key=b"process-clock-timeout-key" * 2,
            anchor_commit=commit,
            anchor_read=lambda: anchor["value"],
            clock_attest=blocked_clock,
        )
        started = monotonic()
        try:
            ledger.append(observation)
        except TractionInputError as exc:
            results.put((label, str(exc), monotonic() - started))
        if label == "first":
            first_ready.set()
            release.wait()
            if ledger._clock_thread is not None:
                ledger._clock_thread.join(timeout=1)

    first = process_context.Process(target=run_candidate, args=(path, "first"))
    first.start()
    assert first_ready.wait(timeout=3)
    second = process_context.Process(
        target=run_candidate, args=(alias_path, "second")
    )
    second.start()
    second.join(timeout=3)
    assert second.is_alive() is False
    observed = {
        label: (message, elapsed)
        for label, message, elapsed in (results.get(timeout=2) for _ in range(2))
    }
    assert "timed out" in observed["first"][0]
    assert "still running" in observed["second"][0]
    assert observed["second"][1] < 0.5
    assert calls.value == 1
    release.set()
    first.join(timeout=3)
    assert first.is_alive() is False


def test_fork_child_cannot_orphan_clock_lock_after_parent_crash(tmp_path) -> None:
    context = _traction_context(clock_response_timeout_seconds=1)
    observation = _real_observation(context)
    anchor = {"value": ""}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    path = tmp_path / "fork-clock-crash.db"
    TractionLedger.create(
        path,
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"fork-clock-crash-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, {"now": p12.AT}),
    )
    process_context = multiprocessing.get_context("fork")
    calls = process_context.Value("i", 0)
    crash_receive, crash_send = process_context.Pipe(duplex=False)
    grandchild_release_read, grandchild_release_write = os.pipe()

    def crash_with_fork(send_connection, release_read, release_write):
        never = Event()

        def blocked_clock(request):
            with calls.get_lock():
                calls.value += 1
            never.wait()
            return sign_traction_clock_attestation(
                request,
                context["trust"],
                context["clock"],
                observed_at=p12.AT,
            )

        ledger = TractionLedger(
            path,
            plan=context["plan"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            state_authentication_key=b"fork-clock-crash-key" * 2,
            anchor_commit=commit,
            anchor_read=lambda: anchor["value"],
            clock_attest=blocked_clock,
        )
        with pytest.raises(TractionInputError, match="timed out"):
            ledger.append(observation)
        grandchild_pid = os.fork()
        if grandchild_pid == 0:
            os.close(release_write)
            os.read(release_read, 1)
            os.close(release_read)
            os._exit(0)
        os.close(release_read)
        os.close(release_write)
        send_connection.send(grandchild_pid)
        send_connection.close()
        os._exit(0)

    crashing = process_context.Process(
        target=crash_with_fork,
        args=(crash_send, grandchild_release_read, grandchild_release_write),
    )
    crashing.start()
    crash_send.close()
    os.close(grandchild_release_read)
    grandchild_pid = crash_receive.recv()
    assert grandchild_pid > 1
    crashing.join(timeout=3)
    assert crashing.is_alive() is False
    healthy_receive, healthy_send = process_context.Pipe(duplex=False)

    def run_healthy(send_connection):
        def healthy_clock(request):
            with calls.get_lock():
                calls.value += 1
            return sign_traction_clock_attestation(
                request,
                context["trust"],
                context["clock"],
                observed_at=p12.AT,
            )

        ledger = TractionLedger(
            path,
            plan=context["plan"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            state_authentication_key=b"fork-clock-crash-key" * 2,
            anchor_commit=commit,
            anchor_read=lambda: anchor["value"],
            clock_attest=healthy_clock,
        )
        try:
            ledger.append(observation)
        except Exception as exc:
            send_connection.send((False, str(exc)))
        else:
            send_connection.send((True, "accepted"))
        finally:
            send_connection.close()

    healthy = process_context.Process(target=run_healthy, args=(healthy_send,))
    try:
        healthy.start()
        healthy_send.close()
        healthy.join(timeout=4)
        assert healthy.is_alive() is False
        assert healthy_receive.recv() == (True, "accepted")
        assert calls.value == 3
    finally:
        try:
            os.write(grandchild_release_write, b"1")
        except OSError:
            pass
        os.close(grandchild_release_write)


def test_settlement_refresh_rewraps_exact_events_after_old_envelope_expiry(
    tmp_path,
) -> None:
    p12_bundle = _p12_pending_bundle()
    context = _traction_context(p12_bundle)
    observation = _real_observation(context)
    transaction = next(
        item
        for item in p12_bundle["cohort"].transactions
        if item.transaction_id_sha256 == _sha("transaction:confirmed-new")
    )
    event = SettlementStatusChange(
        event_id_sha256=_sha("refresh-event:pending-confirmed"),
        transaction_id_sha256=transaction.transaction_id_sha256,
        original_transaction_sha256=hash_signed_artifact(transaction),
        previous_status=TransactionStatus.PENDING,
        current_status=TransactionStatus.CONFIRMED,
        source_row_sha256=_sha("refresh-event-source"),
        effective_at=p12.AT + timedelta(hours=1),
    )
    anchor = {"value": ""}
    clock_state = {"now": p12.AT}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "settlement-refresh.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"settlement-refresh-authentication-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, clock_state),
    )
    ledger.append(observation)
    initial, initial_at = _settlement_evidence(
        context,
        observation,
        label="initial-event-set",
        events=(event,),
    )
    clock_state["now"] = initial_at
    ledger.append_settlement(
        initial,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )

    refreshed, refreshed_at = _settlement_evidence(
        context,
        observation,
        observed=initial.amendments[0].expires_at + timedelta(hours=1),
        label="refreshed-event-set",
        events=(event,),
    )
    clock_state["now"] = refreshed_at
    ledger.append_settlement(
        refreshed,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )
    report = ledger.evaluate(
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )
    assert report.cumulative_settled_amount == Decimal("300")
    assert report.settlement_evidence_sha256s == (
        hash_traction_artifact(refreshed),
    )

    regressed_event, _ = _settlement_evidence(
        context,
        observation,
        observed=refreshed.amendments[0].observed_through_at - timedelta(days=1),
        label="regressed-event-coverage",
        events=(event,),
    )
    masking_empty, masking_at = _settlement_evidence(
        context,
        observation,
        observed=refreshed.amendments[0].observed_through_at + timedelta(days=1),
        label="masking-empty-coverage",
        events=(),
    )
    masked = TractionSettlementEvidence(
        observation_sha256=hash_traction_artifact(observation),
        original_binding=regressed_event.original_binding,
        cohort_batch=regressed_event.cohort_batch,
        amendments=(
            regressed_event.amendments + masking_empty.amendments
        ),
        completeness_attestations=(
            regressed_event.completeness_attestations
            + masking_empty.completeness_attestations
        ),
    )
    clock_state["now"] = masking_at
    with pytest.raises(TractionInputError, match="event coverage cannot regress"):
        ledger.append_settlement(
            masked,
            settlement_policy=context["settlement_policy"],
            settlement_trust_store=context["settlement_trust"],
        )

    omitted, omitted_at = _settlement_evidence(
        context,
        observation,
        observed=refreshed.amendments[0].expires_at + timedelta(hours=1),
        label="omitted-event-set",
        events=(),
    )
    clock_state["now"] = omitted_at
    with pytest.raises(TractionInputError, match="rewrites prior events"):
        ledger.append_settlement(
            omitted,
            settlement_policy=context["settlement_policy"],
            settlement_trust_store=context["settlement_trust"],
        )


def test_expired_settlement_does_not_poison_next_accepted_snapshot(
    tmp_path,
) -> None:
    p12_bundle = _p12_pending_bundle()
    context = _traction_context(p12_bundle)
    observation = _real_observation(context)
    transaction = next(
        item
        for item in p12_bundle["cohort"].transactions
        if item.transaction_id_sha256 == _sha("transaction:confirmed-new")
    )
    event = SettlementStatusChange(
        event_id_sha256=_sha("expired-settlement-event"),
        transaction_id_sha256=transaction.transaction_id_sha256,
        original_transaction_sha256=hash_signed_artifact(transaction),
        previous_status=TransactionStatus.PENDING,
        current_status=TransactionStatus.CONFIRMED,
        source_row_sha256=_sha("expired-settlement-source"),
        effective_at=p12.AT + timedelta(hours=1),
    )
    expired, expired_at = _settlement_evidence(
        context,
        observation,
        label="expired-event-bearing",
        events=(event,),
    )
    accepted, accepted_at = _settlement_evidence(
        context,
        observation,
        label="accepted-zero-event",
    )
    fresh, fresh_at = _settlement_evidence(
        context,
        observation,
        observed=expired.amendments[0].expires_at + timedelta(hours=1),
        label="fresh-zero-event",
    )
    anchor = {"value": ""}
    clock_state = {"now": p12.AT, "expire_finalization": None}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    def clock(request):
        observed_at = clock_state["now"]
        if (
            request.purpose.value == "finalize_event"
            and clock_state["expire_finalization"] is not None
        ):
            observed_at = clock_state["expire_finalization"]
        return sign_traction_clock_attestation(
            request,
            context["trust"],
            context["clock"],
            observed_at=observed_at,
        )

    ledger = TractionLedger.create(
        tmp_path / "expired-settlement-projection.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"expired-settlement-projection-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=clock,
    )
    ledger.append(observation)
    clock_state["now"] = accepted_at
    assert ledger.append_settlement(
        accepted,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    ) == accepted
    clock_state["now"] = expired_at
    clock_state["expire_finalization"] = expired.amendments[0].expires_at
    with pytest.raises(TractionInputError, match="not finalized before"):
        ledger.append_settlement(
            expired,
            settlement_policy=context["settlement_policy"],
            settlement_trust_store=context["settlement_trust"],
        )
    with ledger._connect() as connection:
        assert ledger._latest_settlements(connection) == ()
    clock_state["now"] = expired.amendments[0].expires_at
    stopped = ledger.evaluate(
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )
    assert stopped.decision is not TractionDecision.READY_FOR_SCALE_REVIEW
    assert stopped.settlement_evidence_sha256s == ()
    with pytest.raises(TractionInputError, match="expired finalized"):
        ledger.append_settlement(
            expired,
            settlement_policy=context["settlement_policy"],
            settlement_trust_store=context["settlement_trust"],
        )
    clock_state["now"] = fresh_at
    clock_state["expire_finalization"] = None
    assert ledger.append_settlement(
        fresh,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    ) == fresh
    with ledger._connect() as connection:
        assert ledger._latest_settlements(connection) == (fresh,)


def test_settlement_evidence_permutations_are_canonical_and_replay_neutral(
    tmp_path,
) -> None:
    context = _traction_context()
    observation = _real_observation(context)
    first, at = _settlement_evidence(
        context, observation, label="canonical-first"
    )
    second, _ = _settlement_evidence(
        context, observation, label="canonical-second"
    )
    forward = TractionSettlementEvidence(
        observation_sha256=first.observation_sha256,
        original_binding=first.original_binding,
        cohort_batch=first.cohort_batch,
        amendments=first.amendments + second.amendments,
        completeness_attestations=(
            first.completeness_attestations
            + second.completeness_attestations
        ),
    )
    reverse = TractionSettlementEvidence(
        observation_sha256=first.observation_sha256,
        original_binding=first.original_binding,
        cohort_batch=first.cohort_batch,
        amendments=tuple(reversed(forward.amendments)),
        completeness_attestations=tuple(
            reversed(forward.completeness_attestations)
        ),
    )
    duplicate = TractionSettlementEvidence(
        observation_sha256=first.observation_sha256,
        original_binding=first.original_binding,
        cohort_batch=first.cohort_batch,
        amendments=forward.amendments + forward.amendments,
        completeness_attestations=(
            forward.completeness_attestations
            + forward.completeness_attestations
        ),
    )
    assert forward == reverse == duplicate
    assert hash_traction_artifact(forward) == hash_traction_artifact(reverse)

    anchor = {"value": ""}
    clock_state = {"now": p12.AT}

    def commit(_revision: int, value: str) -> None:
        anchor["value"] = value

    ledger = TractionLedger.create(
        tmp_path / "canonical-settlement.db",
        plan=context["plan"],
        policy=context["policy"],
        trust_store=context["trust"],
        authority_pins=context["pins"],
        state_authentication_key=b"canonical-settlement-auth-key" * 2,
        anchor_commit=commit,
        anchor_read=lambda: anchor["value"],
        clock_attest=_clock_service(context, clock_state),
    )
    ledger.append(observation)
    clock_state["now"] = at
    ledger.append_settlement(
        forward,
        settlement_policy=context["settlement_policy"],
        settlement_trust_store=context["settlement_trust"],
    )
    settled_anchor = anchor["value"]
    assert (
        ledger.append_settlement(
            reverse,
            settlement_policy=context["settlement_policy"],
            settlement_trust_store=context["settlement_trust"],
        )
        == forward
    )
    assert anchor["value"] == settled_anchor


def test_cross_window_identity_reuse_is_rejected() -> None:
    context = _traction_context()
    first = _synthetic_observation(context)
    values = first.model_dump(
        mode="python", exclude={"payload_sha256", "signature_base64url"}
    )
    second_at = first.observation_ended_at + timedelta(days=30, hours=6)
    activity_batch, activity = _shift_operations_activity(
        first,
        started_at=first.observation_ended_at,
        issued_at=second_at,
        suffix="boundary-run-two",
    )
    values.update(
        {
            "ordinal": 2,
            "predecessor_sha256": hash_traction_artifact(first),
            "run_id": "synthetic-boundary-run-two",
            "p12_report_sha256": _sha("p12-report-two"),
            "observation_started_at": first.observation_ended_at,
            "observation_ended_at": first.observation_ended_at + timedelta(days=30),
            "ingested_at": second_at,
            "issued_at": second_at,
            "expires_at": second_at + timedelta(days=7),
            "operations_activity_batch": activity_batch,
            "operations_activity": activity,
        }
    )
    second = _sign_model(TractionObservation, values, context["qa"])
    with pytest.raises(TractionInputError, match="chain"):
        evaluate_traction(
            (first, second),
            plan=context["plan"],
            policy=context["policy"],
            trust_store=context["trust"],
            authority_pins=context["pins"],
            at=second_at,
        )


def test_p12_report_splice_is_rejected() -> None:
    context = _traction_context()
    packet = _packet(context["p12"])
    activity_batch, cost_policy = _operations_activity(packet)
    packet = packet.model_copy(
        update={
            "report": packet.report.model_copy(
                update={"bundle_index_sha256": _sha("foreign-index")}
            )
        }
    )
    with pytest.raises((TractionInputError, ValueError)):
        build_traction_observation(
            packet,
            context["p12"]["runtime"],
            traction_plan=context["plan"],
            traction_policy=context["policy"],
            traction_trust_store=context["trust"],
            authority_pins=context["pins"],
            observation_signing_key=context["qa"],
            identity_hmac_key=context["identity_key"],
            operations_activity_batch=activity_batch,
            operational_cost_policy=cost_policy,
            ordinal=1,
            predecessor_sha256="0" * 64,
            at=p12.AT,
        )


def test_foreign_runtime_cannot_be_relabelled_with_frozen_p12_authority() -> None:
    context = _traction_context()
    frozen_packet = _packet(context["p12"])
    foreign_bundle = _p12_metric_bundle()
    foreign_packet = _packet(foreign_bundle).model_copy(
        update={
            "policy": frozen_packet.policy,
            "trust_store": frozen_packet.trust_store,
            "authority_pins": frozen_packet.authority_pins,
        }
    )
    activity_batch, cost_policy = _operations_activity(foreign_packet)

    with pytest.raises(TractionInputError, match="authority verification"):
        build_traction_observation(
            foreign_packet,
            foreign_bundle["runtime"],
            traction_plan=context["plan"],
            traction_policy=context["policy"],
            traction_trust_store=context["trust"],
            authority_pins=context["pins"],
            observation_signing_key=context["qa"],
            identity_hmac_key=context["identity_key"],
            operations_activity_batch=activity_batch,
            operational_cost_policy=cost_policy,
            ordinal=1,
            predecessor_sha256="0" * 64,
            at=p12.AT,
        )


def test_blocked_fixture_cli_is_offline_stop(capsys) -> None:
    root = "examples/p17/blocked"
    exit_code = run(
        [
            "evaluate-traction",
            f"{root}/evidence-bundle.json",
            "--plan",
            f"{root}/plan.json",
            "--policy",
            f"{root}/policy.json",
            "--trust-store",
            f"{root}/trust-store.json",
            "--authority-pins",
            f"{root}/authority-pins.json",
            "--settlement-policy",
            f"{root}/settlement-policy.json",
            "--settlement-trust-store",
            f"{root}/settlement-trust-store.json",
            "--at",
            "2026-07-31T15:00:00Z",
        ]
    )
    actual = json.loads(capsys.readouterr().out)
    with open(f"{root}/expected-stop-report.json", encoding="utf-8") as source:
        expected = json.load(source)
    assert exit_code == 3
    assert actual == expected
    assert actual["authority"] == "none"
    assert actual["external_mutation_authorized"] is False
