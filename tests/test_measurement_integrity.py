from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import saas_preflight.measurement_integrity as measurement_module
from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.economics import RollbackTestStatus
from saas_preflight.measurement import (
    DailyOperationsSummary,
    DemandClusterSummary,
    DemandSummaryBatch,
    EvidenceReceipt,
    OperationsSummaryBatch,
    ScenarioRates,
)
from saas_preflight.measurement_integrity import (
    AcquisitionClass,
    AffiliateAcceptedClick,
    CohortIntegrityBatch,
    CoveragePartition,
    CoveragePartitionKind,
    CurrentTransaction,
    DemandIntegrityBatch,
    FaultExercise,
    FaultRequirement,
    MeasurementDataset,
    MeasurementBoundDossier,
    MeasurementInputError,
    MeasurementIntegrityReport,
    MeasurementIntegrityRuntime,
    MeasurementIntegrityVerifier,
    MeasurementAuthorityPins,
    MeasurementPolicy,
    MeasurementRulePins,
    MeasurementRunDefinition,
    MeasurementTrustStore,
    LogicalJobRun,
    OperationsIntegrityBatch,
    PayoutAdjustment,
    PayoutAdjustmentKind,
    PayoutRow,
    PayoutStatement,
    ProducerCoverage,
    QualifiedSession,
    REQUIRED_FAULT_IDS,
    RunFreezeDecision,
    TransactionStatus,
    TransactionStatusEvent,
    ValidOutboundClick,
    hash_measurement_policy,
    hash_measurement_trust_store,
    hash_signed_artifact,
    sign_measurement_bundle_index,
    sign_measurement_run_plan,
    sign_producer_attestation,
    verify_measurement_integrity_report,
    verify_measurement_bound_dossier,
)
from saas_preflight.preflight import (
    ArtifactExpiries,
    BusinessDossier,
    DossierProvenance,
)


TOKYO = ZoneInfo("Asia/Tokyo")
START = datetime(2026, 6, 1, tzinfo=TOKYO)
END = START + timedelta(days=30)
START_UTC = START.astimezone(timezone.utc)
END_UTC = END.astimezone(timezone.utc)
AT = END_UTC + timedelta(hours=6)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _set_hash(values: list[str]) -> str:
    encoded = json.dumps(
        sorted(values), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_hash(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fault_requirements() -> tuple[FaultRequirement, ...]:
    return tuple(
        FaultRequirement(
            fault_id=fault_id,
            definition_sha256=_sha(f"definition:{fault_id.value}"),
        )
        for fault_id in REQUIRED_FAULT_IDS
    )


def _planned_run_ids() -> list[str]:
    return [
        _sha(f"logical-run:{offset}:{number}")
        for offset in range(30)
        for number in range(10)
    ]


def _keys() -> dict[str, Ed25519PrivateKey]:
    return {
        name: Ed25519PrivateKey.generate()
        for name in ("human", "demand", "cohort", "operations", "indexer", "qa")
    }


def _trust(keys: dict[str, Ed25519PrivateKey]) -> MeasurementTrustStore:
    values = (
        ("human", "measurement-human", SigningRole.MEASUREMENT_HUMAN),
        ("demand", "demand-producer", SigningRole.DEMAND_PRODUCER),
        ("cohort", "cohort-producer", SigningRole.COHORT_PRODUCER),
        ("operations", "operations-producer", SigningRole.OPERATIONS_PRODUCER),
        ("indexer", "measurement-indexer", SigningRole.MEASUREMENT_INDEXER),
        ("qa", "measurement-qa", SigningRole.TCO_QA),
    )
    receipts = {
        name: create_verification_key(
            keys[name].public_key(), issuer=issuer, role=role
        )
        for name, issuer, role in values
    }
    return MeasurementTrustStore(
        run_human=receipts["human"],
        demand_producer=receipts["demand"],
        cohort_producer=receipts["cohort"],
        operations_producer=receipts["operations"],
        bundle_indexer=receipts["indexer"],
        measurement_verifier=receipts["qa"],
    )


def _rules() -> MeasurementRulePins:
    return MeasurementRulePins(
        qualification_sha256=_sha("qualification"),
        session_identity_sha256=_sha("session-identity"),
        demand_deduplication_sha256=_sha("demand-dedup"),
        valid_outbound_filter_sha256=_sha("outbound-filter"),
        event_deduplication_sha256=_sha("event-dedup"),
        attribution_sha256=_sha("attribution"),
        transaction_deduplication_sha256=_sha("transaction-dedup"),
        status_transition_sha256=_sha("status-transition"),
        refund_chargeback_sha256=_sha("refund-chargeback"),
        new_acquisition_sha256=_sha("new-acquisition"),
        payout_reconciliation_sha256=_sha("payout-reconciliation"),
        routine_inventory_sha256=_sha("routine-inventory"),
        job_schedule_sha256=_sha("job-schedule"),
        job_status_mapping_sha256=_sha("job-status"),
        retry_identity_sha256=_sha("retry-identity"),
        exception_deduplication_sha256=_sha("exception-dedup"),
        human_time_union_sha256=_sha("human-time-union"),
        qa_policy_sha256=_sha("qa-policy"),
        fault_catalog_sha256=_sha("fault-catalog"),
        privacy_minimization_sha256=_sha("privacy-minimization"),
        coverage_completeness_sha256=_sha("coverage-completeness"),
    )


def _policy(trust: MeasurementTrustStore) -> MeasurementPolicy:
    rules = _rules()
    authorities = {
        "demand": _sha("demand-authority"),
        "cohort": _sha("cohort-authority"),
        "operations": _sha("operations-authority"),
    }
    faults = _fault_requirements()
    return MeasurementPolicy(
        trust_store_sha256=hash_measurement_trust_store(trust),
        property_record_sha256=_sha("property"),
        property_domain_sha256=_sha("synthetic.invalid"),
        approved_rule_pins_sha256=hash_signed_artifact(rules),
        approved_source_authorities_sha256=_json_hash(authorities),
        approved_fault_requirements_sha256=_json_hash(
            [item.model_dump(mode="json") for item in faults]
        ),
        required_fault_ids=REQUIRED_FAULT_IDS,
        maximum_plan_ttl_seconds=60 * 24 * 60 * 60,
        maximum_producer_ttl_seconds=14 * 24 * 60 * 60,
        maximum_index_ttl_seconds=14 * 24 * 60 * 60,
        maximum_report_ttl_seconds=24 * 60 * 60,
    )


def _plan(
    policy: MeasurementPolicy,
    trust: MeasurementTrustStore,
    key: Ed25519PrivateKey,
):
    rules = _rules()
    definition = MeasurementRunDefinition(
        run_id="synthetic-june-2026",
        decision=RunFreezeDecision.GO,
        policy_sha256=hash_measurement_policy(policy),
        trust_store_sha256=hash_measurement_trust_store(trust),
        property_record_sha256=policy.property_record_sha256,
        property_domain_sha256=policy.property_domain_sha256,
        source_month="2026-06",
        observation_started_at=START,
        observation_ended_at=END,
        partner_ids=("partner-c", "partner-a", "partner-b"),
        demand_measurement_version="demand-v1",
        cohort_measurement_version="cohort-v1",
        operations_measurement_version="operations-v1",
        demand_authority_record_sha256=_sha("demand-authority"),
        cohort_authority_record_sha256=_sha("cohort-authority"),
        operations_authority_record_sha256=_sha("operations-authority"),
        planned_logical_job_count=300,
        planned_logical_job_set_sha256=_set_hash(_planned_run_ids()),
        fault_target_release_sha256=_sha("fault-target-release"),
        fault_target_artifact_sha256=_sha("fault-target-artifact"),
        fault_target_schema_sha256=_sha("fault-target-schema"),
        rules=rules,
        fault_requirements=tuple(reversed(_fault_requirements())),
    )
    return sign_measurement_run_plan(
        definition,
        key,
        issuer="measurement-human",
        issued_at=START_UTC - timedelta(days=1),
        expires_at=AT + timedelta(days=7),
    )


def _receipt(authority: str) -> EvidenceReceipt:
    return EvidenceReceipt(
        authority="synthetic-owned-export",
        authority_record_sha256=_sha(authority),
        source_receipt_sha256=_sha(f"source:{authority}"),
        retrieved_at=END + timedelta(hours=1),
    )


def _rates(value: str) -> ScenarioRates:
    return ScenarioRates(
        organic_visibility=Decimal(value),
        rank_ctr=Decimal("0.20"),
        qualified_rate=Decimal("0.50"),
        outbound_click_rate=Decimal("0.10"),
    )


def _demand() -> DemandIntegrityBatch:
    summary = DemandSummaryBatch(
        measurement_version="demand-v1",
        receipt=_receipt("demand-authority"),
        source_month="2026-06",
        deduplication_sha256=_sha("demand-dedup"),
        volume_is_deduplicated=True,
        captured_at=END,
        expires_at=AT + timedelta(days=7),
        clusters=(
            DemandClusterSummary(
                cluster_id="compare",
                cluster_receipt_sha256=_sha("cluster:compare"),
                deduplicated_monthly_volume=Decimal("200"),
            ),
            DemandClusterSummary(
                cluster_id="pricing",
                cluster_receipt_sha256=_sha("cluster:pricing"),
                deduplicated_monthly_volume=Decimal("100"),
            ),
        ),
        bear=_rates("0.20"),
        base=_rates("0.30"),
        bull=_rates("0.40"),
    )
    return DemandIntegrityBatch(
        summary=summary,
        qualification_sha256=_sha("qualification"),
        session_identity_sha256=_sha("session-identity"),
        valid_outbound_filter_sha256=_sha("outbound-filter"),
        privacy_minimization_sha256=_sha("privacy-minimization"),
    )


def _event(label: str, status: TransactionStatus, hour: int):
    return TransactionStatusEvent(
        status=status,
        effective_at=START_UTC + timedelta(days=3, hours=hour),
        source_row_sha256=_sha(f"status:{label}:{status.value}"),
    )


def _transaction(
    label: str,
    partner: str,
    click: str,
    amount: str,
    acquisition: AcquisitionClass,
    events: tuple[TransactionStatusEvent, ...],
) -> CurrentTransaction:
    return CurrentTransaction(
        transaction_id_sha256=_sha(f"transaction:{label}"),
        affiliate_click_id_sha256=_sha(f"affiliate:{click}"),
        partner_id=partner,
        cohort_id="synthetic-june-2026",
        currency="JPY",
        amount=Decimal(amount),
        acquisition_class=acquisition,
        acquisition_evidence_sha256=_sha(f"acquisition:{label}"),
        attributed_at=START_UTC + timedelta(days=2),
        current_status=events[-1].status,
        status_events=tuple(reversed(events)),
    )


def _cohort(*, reverse_rows: bool = False) -> CohortIntegrityBatch:
    sessions = tuple(
        QualifiedSession(
            session_id_sha256=_sha(f"session:{number}"),
            qualified_at=START_UTC + timedelta(days=1, minutes=number),
        )
        for number in range(4)
    )
    outbound = tuple(
        ValidOutboundClick(
            click_id_sha256=_sha(f"outbound:{number}"),
            session_id_sha256=_sha(f"session:{number}"),
            partner_id=("partner-a", "partner-b", "partner-a", "partner-c")[number],
            clicked_at=START_UTC + timedelta(days=1, hours=1, minutes=number),
        )
        for number in range(4)
    )
    affiliate = tuple(
        AffiliateAcceptedClick(
            affiliate_click_id_sha256=_sha(f"affiliate:{number}"),
            outbound_click_id_sha256=_sha(f"outbound:{number}"),
            partner_id=("partner-a", "partner-b", "partner-a")[number],
            accepted_at=START_UTC + timedelta(days=1, hours=2, minutes=number),
        )
        for number in range(3)
    )
    transactions = (
        _transaction(
            "confirmed-new",
            "partner-a",
            "0",
            "100",
            AcquisitionClass.NEW,
            (_event("confirmed-new", TransactionStatus.CONFIRMED, 0),),
        ),
        _transaction(
            "paid-new",
            "partner-b",
            "1",
            "200",
            AcquisitionClass.NEW,
            (
                _event("paid-new", TransactionStatus.PENDING, 0),
                _event("paid-new", TransactionStatus.CONFIRMED, 1),
                _event("paid-new", TransactionStatus.PAID, 2),
            ),
        ),
        _transaction(
            "paid-existing",
            "partner-a",
            "2",
            "300",
            AcquisitionClass.EXISTING,
            (_event("paid-existing", TransactionStatus.PAID, 3),),
        ),
    )
    paid_ids = [
        row.transaction_id_sha256
        for row in transactions
        if row.current_status is TransactionStatus.PAID
    ]
    payout_rows = tuple(
        PayoutRow(
            payout_row_sha256=_sha(f"payout:{row.transaction_id_sha256}"),
            transaction_id_sha256=row.transaction_id_sha256,
            amount=row.amount,
            currency="JPY",
            paid_at=START_UTC + timedelta(days=4),
        )
        for row in transactions
        if row.current_status is TransactionStatus.PAID
    )
    if reverse_rows:
        sessions, outbound, affiliate, transactions, payout_rows = (
            tuple(reversed(item))
            for item in (sessions, outbound, affiliate, transactions, payout_rows)
        )
    return CohortIntegrityBatch(
        measurement_version="cohort-v1",
        property_record_sha256=_sha("property"),
        source_authority_record_sha256=_sha("cohort-authority"),
        source_receipt_sha256=_sha("cohort-source"),
        cohort_id="synthetic-june-2026",
        cohort_started_at=START,
        cohort_ended_at=END,
        snapshot_as_of=END,
        captured_at=END,
        expires_at=AT + timedelta(days=7),
        partner_ids=("partner-c", "partner-b", "partner-a"),
        click_deduplication_sha256=_sha("event-dedup"),
        status_mapping_sha256=_sha("status-transition"),
        transaction_deduplication_sha256=_sha("transaction-dedup"),
        acquisition_mapping_sha256=_sha("new-acquisition"),
        payout_mapping_sha256=_sha("payout-reconciliation"),
        qualification_sha256=_sha("qualification"),
        session_identity_sha256=_sha("session-identity"),
        valid_outbound_filter_sha256=_sha("outbound-filter"),
        attribution_sha256=_sha("attribution"),
        refund_chargeback_sha256=_sha("refund-chargeback"),
        privacy_minimization_sha256=_sha("privacy-minimization"),
        qualified_sessions=sessions,
        valid_outbound_clicks=outbound,
        affiliate_accepted_clicks=affiliate,
        transactions=transactions,
        payout_rows=payout_rows,
        payout_statement=PayoutStatement(
            statement_sha256=_sha("statement"),
            payout_id_sha256=_sha("payout-id"),
            currency="JPY",
            gross_amount=Decimal("500"),
            reversal_amount=Decimal(0),
            fees_tax_withholding=Decimal(0),
            net_amount=Decimal("500"),
            paid_transaction_set_sha256=_set_hash(paid_ids),
            period_started_at=START,
            period_ended_at=END,
            snapshot_as_of=END,
        ),
    )


def _operations(*, failed_fault: bool = False) -> OperationsIntegrityBatch:
    days = []
    for offset in range(30):
        passed = 1 if offset < 8 and not (failed_fault and offset == 7) else 0
        days.append(
            DailyOperationsSummary(
                summary_id_sha256=_sha(f"day:{offset}"),
                local_date=(START + timedelta(days=offset)).date(),
                human_minutes=24 if offset < 30 else 0,
                routine_tasks_total=10,
                routine_tasks_automated=8,
                job_runs_total=10,
                job_runs_succeeded=10,
                exceptions_total=0,
                major_misstatements=0,
                rollback_tests_total=1 if offset < 8 else 0,
                rollback_tests_passed=passed,
            )
        )
    summary = OperationsSummaryBatch(
        measurement_version="operations-v1",
        receipt=_receipt("operations-authority"),
        property_record_sha256=_sha("property"),
        observation_started_at=START,
        captured_at=END,
        expires_at=AT + timedelta(days=7),
        routine_inventory_sha256=_sha("routine-inventory"),
        job_schedule_sha256=_sha("job-schedule"),
        job_status_mapping_sha256=_sha("job-status"),
        exception_deduplication_sha256=_sha("exception-dedup"),
        qa_policy_sha256=_sha("qa-policy"),
        rollback_catalog_sha256=_sha("fault-catalog"),
        daily_summaries=tuple(reversed(days)),
    )
    faults = []
    for offset, fault_id in enumerate(REQUIRED_FAULT_IDS):
        failed = failed_fault and offset == 7
        faults.append(
            FaultExercise(
                fault_id=fault_id,
                definition_sha256=_sha(f"definition:{fault_id.value}"),
                run_sha256=_sha(f"fault-run:{fault_id.value}"),
                injected_at=START_UTC + timedelta(days=offset, hours=2),
                detected_at=START_UTC + timedelta(days=offset, hours=2, minutes=5),
                restore_started_at=START_UTC
                + timedelta(days=offset, hours=2, minutes=10),
                restored_at=START_UTC + timedelta(days=offset, hours=3),
                pre_state_sha256=_sha(f"pre:{fault_id.value}"),
                fault_state_sha256=_sha(f"fault:{fault_id.value}"),
                restored_state_sha256=_sha(
                    ("failed-restore:" if failed else "pre:") + fault_id.value
                ),
                validation_receipt_sha256=_sha(f"validation:{fault_id.value}"),
                target_release_sha256=_sha("fault-target-release"),
                target_artifact_sha256=_sha("fault-target-artifact"),
                target_schema_sha256=_sha("fault-target-schema"),
                stop_receipt_sha256=_sha(f"stop:{fault_id.value}"),
                passed=not failed,
            )
        )
    logical_runs = tuple(
        LogicalJobRun(
            run_key_sha256=_sha(f"logical-run:{offset}:{number}"),
            scheduled_for=START_UTC
            + timedelta(days=offset, minutes=number * 2),
            attempt_receipt_sha256s=(
                _sha(f"attempt:{offset}:{number}:1"),
                _sha(f"attempt:{offset}:{number}:2"),
            ),
            succeeded=True,
            completed_at=START_UTC
            + timedelta(days=offset, minutes=number * 2 + 1),
        )
        for offset in range(30)
        for number in range(10)
    )
    return OperationsIntegrityBatch(
        summary=summary,
        retry_identity_sha256=_sha("retry-identity"),
        human_time_union_sha256=_sha("human-time-union"),
        privacy_minimization_sha256=_sha("privacy-minimization"),
        logical_job_runs=tuple(reversed(logical_runs)),
        fault_exercises=tuple(reversed(faults)),
    )


def _coverage(batch, label: str) -> ProducerCoverage:
    if isinstance(batch, DemandIntegrityBatch):
        source_receipt = batch.summary.receipt.source_receipt_sha256
        identities = {
            CoveragePartitionKind.DEMAND_CLUSTER: [
                item.cluster_receipt_sha256 for item in batch.summary.clusters
            ]
        }
    elif isinstance(batch, CohortIntegrityBatch):
        source_receipt = batch.source_receipt_sha256
        identities = {
            CoveragePartitionKind.QUALIFIED_SESSION: [
                item.session_id_sha256 for item in batch.qualified_sessions
            ],
            CoveragePartitionKind.VALID_OUTBOUND_CLICK: [
                item.click_id_sha256 for item in batch.valid_outbound_clicks
            ],
            CoveragePartitionKind.AFFILIATE_ACCEPTED_CLICK: [
                item.affiliate_click_id_sha256
                for item in batch.affiliate_accepted_clicks
            ],
            CoveragePartitionKind.TRANSACTION: [
                item.transaction_id_sha256 for item in batch.transactions
            ],
            CoveragePartitionKind.STATUS_EVENT: [
                event.source_row_sha256
                for item in batch.transactions
                for event in item.status_events
            ],
            CoveragePartitionKind.PAYOUT_ROW: [
                item.payout_row_sha256 for item in batch.payout_rows
            ],
            CoveragePartitionKind.PAYOUT_ADJUSTMENT: [
                item.adjustment_id_sha256 for item in batch.payout_adjustments
            ],
        }
    else:
        source_receipt = batch.summary.receipt.source_receipt_sha256
        identities = {
            CoveragePartitionKind.OPERATION_DAY: [
                item.summary_id_sha256 for item in batch.summary.daily_summaries
            ],
            CoveragePartitionKind.LOGICAL_JOB_RUN: [
                item.run_key_sha256 for item in batch.logical_job_runs
            ],
            CoveragePartitionKind.FAULT_EXERCISE: [
                item.run_sha256 for item in batch.fault_exercises
            ],
        }
    partitions = tuple(
        CoveragePartition(
            kind=kind,
            input_records=len(values),
            accepted_records=len(values),
            rejected_records=0,
            duplicate_records=0,
            conflict_records=0,
            unknown_records=0,
            output_records=len(values),
            identity_set_sha256=_set_hash(values),
        )
        for kind, values in sorted(identities.items(), key=lambda item: item[0].value)
    )
    records = sum(item.output_records for item in partitions)
    return ProducerCoverage(
        source_export_sha256=source_receipt,
        complete_export_receipt_sha256=_sha(f"complete:{label}"),
        coverage_rule_sha256=_sha("coverage-completeness"),
        raw_records=records,
        accepted_records=records,
        rejected_records=0,
        duplicate_records=0,
        conflict_records=0,
        unknown_records=0,
        output_records=records,
        partitions=partitions,
        privacy_scan_sha256=_sha(f"privacy:{label}"),
        privacy_scan_passed=True,
    )


def _bundle(*, failed_fault: bool = False):
    keys = _keys()
    trust = _trust(keys)
    policy = _policy(trust)
    plan = _plan(policy, trust, keys["human"])
    demand = _demand()
    cohort = _cohort()
    operations = _operations(failed_fault=failed_fault)
    issued = END_UTC + timedelta(hours=2)
    expires = AT + timedelta(days=7)
    demand_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.DEMAND,
        demand,
        _coverage(demand, "demand"),
        keys["demand"],
        issuer="demand-producer",
        issued_at=issued,
        expires_at=expires,
    )
    cohort_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.COHORT,
        cohort,
        _coverage(cohort, "cohort"),
        keys["cohort"],
        issuer="cohort-producer",
        issued_at=issued + timedelta(minutes=1),
        expires_at=expires,
    )
    operations_attestation = sign_producer_attestation(
        plan,
        MeasurementDataset.OPERATIONS,
        operations,
        _coverage(operations, "operations"),
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
        captured_at=END_UTC,
        issued_at=issued + timedelta(hours=1),
        expires_at=expires,
    )
    pins = MeasurementAuthorityPins(
        expected_policy_sha256=hash_measurement_policy(policy),
        expected_trust_store_sha256=hash_measurement_trust_store(trust),
        expected_run_id=plan.definition.run_id,
        expected_bundle_index_sha256=hash_signed_artifact(index),
    )
    runtime = MeasurementIntegrityRuntime(policy, trust, keys["qa"], pins)
    return {
        "keys": keys,
        "trust": trust,
        "policy": policy,
        "pins": pins,
        "plan": plan,
        "demand": demand,
        "cohort": cohort,
        "operations": operations,
        "demand_attestation": demand_attestation,
        "cohort_attestation": cohort_attestation,
        "operations_attestation": operations_attestation,
        "index": index,
        "runtime": runtime,
    }


def _evaluate(bundle: dict):
    return bundle["runtime"].evaluate(
        bundle["plan"],
        bundle["demand"],
        bundle["cohort"],
        bundle["operations"],
        bundle["demand_attestation"],
        bundle["cohort_attestation"],
        bundle["operations_attestation"],
        bundle["index"],
        at=AT,
    )


def test_credential_blind_verifier_rederives_the_exact_signed_report() -> None:
    bundle = _bundle()
    report = _evaluate(bundle)
    verifier = MeasurementIntegrityVerifier(
        bundle["policy"], bundle["trust"], bundle["pins"]
    )
    arguments = (
        report,
        bundle["plan"],
        bundle["demand"],
        bundle["cohort"],
        bundle["operations"],
        bundle["demand_attestation"],
        bundle["cohort_attestation"],
        bundle["operations_attestation"],
        bundle["index"],
    )
    assert verifier.verify(*arguments, at=AT) is True
    assert verifier.verify(*arguments, at=report.expires_at) is False


def test_credential_blind_verifier_rejects_a_validly_signed_false_report() -> None:
    bundle = _bundle()
    report = _evaluate(bundle)
    changed_demand = report.demand.model_copy(
        update={
            "scenarios": report.demand.scenarios.model_copy(
                update={
                    "bear": report.demand.scenarios.bear.model_copy(
                        update={"deduplicated_search_volume": Decimal("999999")}
                    )
                }
            )
        }
    )
    values = {
        field: getattr(report, field)
        for field in type(report).model_fields
        if field not in {"payload_sha256", "signature_base64url"}
    }
    values["demand"] = changed_demand
    provisional = MeasurementIntegrityReport.model_construct(
        **values, payload_sha256="0" * 64, signature_base64url="A" * 86
    )
    payload_sha256 = measurement_module._signed_payload_hash(provisional)
    with_payload = MeasurementIntegrityReport.model_construct(
        **values,
        payload_sha256=payload_sha256,
        signature_base64url="A" * 86,
    )
    false_report = MeasurementIntegrityReport(
        **values,
        payload_sha256=payload_sha256,
        signature_base64url=measurement_module._encode_base64url(
            bundle["keys"]["qa"].sign(
                measurement_module._signature_message(with_payload)
            )
        ),
    )
    assert verify_measurement_integrity_report(
        false_report,
        bundle["policy"],
        bundle["trust"],
        bundle["pins"],
        at=AT,
    ) is True
    verifier = MeasurementIntegrityVerifier(
        bundle["policy"], bundle["trust"], bundle["pins"]
    )
    assert (
        verifier.verify(
            false_report,
            bundle["plan"],
            bundle["demand"],
            bundle["cohort"],
            bundle["operations"],
            bundle["demand_attestation"],
            bundle["cohort_attestation"],
            bundle["operations_attestation"],
            bundle["index"],
            at=AT,
        )
        is False
    )


def _replace_cohort(bundle: dict, cohort: CohortIntegrityBatch, coverage):
    issued = END_UTC + timedelta(hours=2, minutes=1)
    cohort_attestation = sign_producer_attestation(
        bundle["plan"],
        MeasurementDataset.COHORT,
        cohort,
        coverage,
        bundle["keys"]["cohort"],
        issuer="cohort-producer",
        issued_at=issued,
        expires_at=AT + timedelta(days=7),
    )
    index = sign_measurement_bundle_index(
        bundle["plan"],
        bundle["demand"],
        cohort,
        bundle["operations"],
        bundle["demand_attestation"],
        cohort_attestation,
        bundle["operations_attestation"],
        bundle["keys"]["indexer"],
        issuer="measurement-indexer",
        captured_at=END_UTC,
        issued_at=END_UTC + timedelta(hours=3),
        expires_at=AT + timedelta(days=7),
    )
    pins = MeasurementAuthorityPins(
        expected_policy_sha256=hash_measurement_policy(bundle["policy"]),
        expected_trust_store_sha256=hash_measurement_trust_store(bundle["trust"]),
        expected_run_id=bundle["plan"].definition.run_id,
        expected_bundle_index_sha256=hash_signed_artifact(index),
    )
    bundle.update(
        {
            "cohort": cohort,
            "cohort_attestation": cohort_attestation,
            "index": index,
            "pins": pins,
            "runtime": MeasurementIntegrityRuntime(
                bundle["policy"], bundle["trust"], bundle["keys"]["qa"], pins
            ),
        }
    )
    return bundle


def _dossier(report) -> BusinessDossier:
    operations = report.operations
    return BusinessDossier(
        evidence_version="signed-p12-synthetic",
        provenance=DossierProvenance(
            property_domain="synthetic.invalid",
            rights_bundle_sha256=_sha("rights"),
            affiliate_bundle_sha256=_sha("affiliate"),
            demand_source_sha256=report.demand.source_sha256,
            cohort_source_sha256=report.cohort.source_sha256,
            operations_source_sha256=operations.source_sha256,
            assembled_at=AT,
        ),
        as_of=AT,
        expires_at=ArtifactExpiries(
            rights=AT + timedelta(days=1),
            affiliate=AT + timedelta(days=1),
            demand=report.demand.expires_at,
            cohort=report.cohort.expires_at,
            operations=operations.expires_at,
        ),
        approved_affiliate_ids=("partner-a", "partner-b", "partner-c"),
        rights_approved=True,
        scenarios=report.demand.scenarios,
        cohort=report.cohort.cohort,
        human_hours_per_month=operations.human_hours(),
        automation_rate=operations.automation_rate(),
        major_misstatements=operations.major_misstatements,
        shadow_observation_days=operations.shadow_observation_days(),
        job_runs_total=operations.job_runs_total,
        job_runs_succeeded=operations.job_runs_succeeded,
        exceptions_total=operations.exceptions_total,
        rollback_test_status=operations.rollback_test_status,
    )


def test_signed_runtime_emits_reconciled_evidence_and_report() -> None:
    bundle = _bundle()
    report = _evaluate(bundle)

    assert report.cohort.cohort.valid_clicks == 4
    assert report.cohort.cohort.commissions.confirmed == Decimal("100")
    assert report.cohort.cohort.commissions.paid == Decimal("200")
    assert report.reconciliation.confirmed_epc == Decimal("75")
    assert report.reconciliation.net_payout_epc == Decimal("125")
    assert report.reconciliation.exact_faults_passed == 8
    assert report.operations.rollback_test_status is RollbackTestStatus.PASSED
    assert verify_measurement_integrity_report(
        report,
        bundle["policy"],
        bundle["trust"],
        bundle["pins"],
        at=AT,
    )


def test_all_valid_outbound_clicks_stay_in_epc_denominator() -> None:
    report = _evaluate(_bundle())
    assert report.reconciliation.valid_outbound_clicks == 4
    assert report.reconciliation.current_transactions == 3
    assert report.reconciliation.settled_new_acquisition_amount == Decimal("300")
    assert report.reconciliation.confirmed_epc != Decimal("100")


def test_measurement_bound_dossier_keeps_signed_fields_attached() -> None:
    bundle = _bundle()
    report = _evaluate(bundle)
    dossier = _dossier(report)
    bound = MeasurementBoundDossier(
        report=report,
        dossier=dossier,
        dossier_sha256=hash_signed_artifact(dossier),
    )
    assert verify_measurement_bound_dossier(
        bound,
        bundle["policy"],
        bundle["trust"],
        bundle["pins"],
        at=AT,
    )

    inflated = dossier.model_copy(
        update={
            "cohort": dossier.cohort.model_copy(update={"valid_clicks": 1})
        }
    )
    with pytest.raises(ValidationError, match="do not match signed report"):
        MeasurementBoundDossier(
            report=report,
            dossier=inflated,
            dossier_sha256=hash_signed_artifact(inflated),
        )


def test_material_batch_change_breaks_producer_and_index_binding() -> None:
    bundle = _bundle()
    changed_cluster = bundle["demand"].summary.clusters[0].model_copy(
        update={"deduplicated_monthly_volume": Decimal("999")}
    )
    changed_summary = bundle["demand"].summary.model_copy(
        update={
            "clusters": (changed_cluster, *bundle["demand"].summary.clusters[1:])
        }
    )
    bundle["demand"] = bundle["demand"].model_copy(
        update={"summary": changed_summary}
    )
    with pytest.raises(MeasurementInputError, match="demand producer"):
        _evaluate(bundle)


def test_nonconverting_click_omission_fails_stage_coverage_even_when_resigned() -> None:
    bundle = _bundle()
    old_coverage = bundle["cohort_attestation"].coverage
    cohort = bundle["cohort"]
    omitted = CohortIntegrityBatch.model_validate(
        {
            **cohort.model_dump(),
            "qualified_sessions": tuple(
                item
                for item in cohort.qualified_sessions
                if item.session_id_sha256 != _sha("session:3")
            ),
            "valid_outbound_clicks": tuple(
                item
                for item in cohort.valid_outbound_clicks
                if item.click_id_sha256 != _sha("outbound:3")
            ),
        }
    )
    _replace_cohort(bundle, omitted, old_coverage)
    with pytest.raises(MeasurementInputError, match="cohort producer"):
        _evaluate(bundle)


def test_funnel_causal_inversion_is_rejected() -> None:
    cohort = _cohort()
    first_click = cohort.valid_outbound_clicks[0]
    parent = next(
        item
        for item in cohort.qualified_sessions
        if item.session_id_sha256 == first_click.session_id_sha256
    )
    inverted = first_click.model_copy(
        update={"clicked_at": parent.qualified_at - timedelta(seconds=1)}
    )
    with pytest.raises(ValidationError, match="predate qualification"):
        CohortIntegrityBatch.model_validate(
            {
                **cohort.model_dump(),
                "valid_outbound_clicks": (
                    inverted,
                    *(
                        item
                        for item in cohort.valid_outbound_clicks
                        if item.click_id_sha256 != inverted.click_id_sha256
                    ),
                ),
            }
        )


def test_unknown_acquisition_is_retained_and_signed_runtime_rejects_readiness() -> None:
    bundle = _bundle()
    cohort = bundle["cohort"]
    first = cohort.transactions[0].model_copy(
        update={"acquisition_class": AcquisitionClass.UNKNOWN}
    )
    changed = CohortIntegrityBatch.model_validate(
        {
            **cohort.model_dump(),
            "transactions": (first, *cohort.transactions[1:]),
        }
    )
    _replace_cohort(bundle, changed, _coverage(changed, "cohort"))
    with pytest.raises(MeasurementInputError, match="unknown acquisition"):
        _evaluate(bundle)


def test_equivalent_timezone_offsets_have_one_canonical_hash() -> None:
    cohort = _cohort()
    statement = cohort.payout_statement.model_copy(
        update={
            "period_started_at": START_UTC,
            "period_ended_at": END_UTC,
            "snapshot_as_of": END_UTC,
        }
    )
    utc_equivalent = CohortIntegrityBatch.model_validate(
        {
            **cohort.model_dump(),
            "cohort_started_at": START_UTC,
            "cohort_ended_at": END_UTC,
            "snapshot_as_of": END_UTC,
            "captured_at": END_UTC,
            "expires_at": cohort.expires_at.astimezone(timezone.utc),
            "payout_statement": statement,
        }
    )
    assert hash_signed_artifact(cohort) == hash_signed_artifact(utc_equivalent)


def test_consumer_index_pin_rejects_another_validly_signed_bundle() -> None:
    bundle = _bundle()
    wrong_pins = bundle["pins"].model_copy(
        update={"expected_bundle_index_sha256": _sha("other-index")}
    )
    runtime = MeasurementIntegrityRuntime(
        bundle["policy"], bundle["trust"], bundle["keys"]["qa"], wrong_pins
    )
    bundle["runtime"] = runtime
    with pytest.raises(MeasurementInputError, match="bundle index"):
        _evaluate(bundle)


def test_row_shuffle_is_canonical_and_material_change_is_not() -> None:
    first = _cohort()
    second = _cohort(reverse_rows=True)
    assert hash_signed_artifact(first) == hash_signed_artifact(second)
    changed = first.model_copy(
        update={
            "valid_outbound_clicks": first.valid_outbound_clicks[:-1]
        }
    )
    assert hash_signed_artifact(first) != hash_signed_artifact(changed)


def test_exact_eight_with_one_failed_restore_emits_failed_gate_evidence() -> None:
    with pytest.raises(MeasurementInputError, match="all eight fault restores"):
        _evaluate(_bundle(failed_fault=True))


def test_retry_attempts_do_not_inflate_logical_job_denominator() -> None:
    bundle = _bundle()
    assert len(bundle["operations"].logical_job_runs) == 300
    assert sum(
        len(item.attempt_receipt_sha256s)
        for item in bundle["operations"].logical_job_runs
    ) == 600
    report = _evaluate(bundle)
    assert report.operations.job_runs_total == 300
    assert report.operations.job_runs_succeeded == 300


def test_fault_omission_and_repetition_cannot_construct_integrity_batch() -> None:
    operations = _operations()
    with pytest.raises(ValidationError, match="at least 8 items"):
        OperationsIntegrityBatch(
            summary=operations.summary,
            retry_identity_sha256=operations.retry_identity_sha256,
            human_time_union_sha256=operations.human_time_union_sha256,
            privacy_minimization_sha256=operations.privacy_minimization_sha256,
            logical_job_runs=operations.logical_job_runs,
            fault_exercises=operations.fault_exercises[:-1],
        )
    duplicate = operations.fault_exercises[:-1] + (operations.fault_exercises[0],)
    with pytest.raises(ValidationError, match="identities must be unique"):
        OperationsIntegrityBatch(
            summary=operations.summary,
            retry_identity_sha256=operations.retry_identity_sha256,
            human_time_union_sha256=operations.human_time_union_sha256,
            privacy_minimization_sha256=operations.privacy_minimization_sha256,
            logical_job_runs=operations.logical_job_runs,
            fault_exercises=duplicate,
        )

    reused_receipt = operations.fault_exercises[1].model_copy(
        update={
            "validation_receipt_sha256": operations.fault_exercises[0].validation_receipt_sha256
        }
    )
    with pytest.raises(ValidationError, match="validation receipts must be distinct"):
        OperationsIntegrityBatch(
            summary=operations.summary,
            retry_identity_sha256=operations.retry_identity_sha256,
            human_time_union_sha256=operations.human_time_union_sha256,
            privacy_minimization_sha256=operations.privacy_minimization_sha256,
            logical_job_runs=operations.logical_job_runs,
            fault_exercises=(
                operations.fault_exercises[0],
                reused_receipt,
                *operations.fault_exercises[2:],
            ),
        )


def test_paid_transaction_requires_exact_payout_set_and_amount() -> None:
    cohort = _cohort()
    statement = cohort.payout_statement.model_copy(
        update={"gross_amount": Decimal("499"), "net_amount": Decimal("499")}
    )
    with pytest.raises(ValidationError, match="paid transaction ledger"):
        CohortIntegrityBatch.model_validate(
            {**cohort.model_dump(), "payout_statement": statement.model_dump()}
        )


def test_payout_adjustment_source_receipt_cannot_be_reused() -> None:
    cohort = _cohort()
    paid = [
        item
        for item in cohort.transactions
        if item.current_status is TransactionStatus.PAID
    ]
    adjustments = tuple(
        PayoutAdjustment(
            adjustment_id_sha256=_sha(f"adjustment:{item.transaction_id_sha256}"),
            transaction_id_sha256=item.transaction_id_sha256,
            kind=PayoutAdjustmentKind.REFUND,
            amount=item.amount,
            currency="JPY",
            source_row_sha256=_sha("reused-adjustment-source"),
            adjusted_at=START_UTC + timedelta(days=5),
        )
        for item in paid
    )
    statement = cohort.payout_statement.model_copy(
        update={"reversal_amount": Decimal("500"), "net_amount": Decimal(0)}
    )
    with pytest.raises(ValidationError, match="adjustment source receipts"):
        CohortIntegrityBatch.model_validate(
            {
                **cohort.model_dump(),
                "payout_adjustments": adjustments,
                "payout_statement": statement,
            }
        )


def test_unknown_acquisition_is_preserved_but_not_readiness_eligible() -> None:
    unknown = _transaction(
        "unknown",
        "partner-a",
        "0",
        "100",
        AcquisitionClass.UNKNOWN,
        (_event("unknown", TransactionStatus.CONFIRMED, 0),),
    )
    assert unknown.acquisition_class is AcquisitionClass.UNKNOWN


def test_regressive_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="regressive"):
        _transaction(
            "regressive",
            "partner-a",
            "0",
            "100",
            AcquisitionClass.NEW,
            (
                _event("regressive", TransactionStatus.PAID, 0),
                _event("regressive", TransactionStatus.PENDING, 1),
            ),
        )


def test_plan_signed_after_start_is_rejected_before_runtime() -> None:
    keys = _keys()
    trust = _trust(keys)
    policy = _policy(trust)
    valid_plan = _plan(policy, trust, keys["human"])
    with pytest.raises(ValidationError, match="before the run starts"):
        sign_measurement_run_plan(
            valid_plan.definition,
            keys["human"],
            issuer="measurement-human",
            issued_at=START_UTC + timedelta(seconds=1),
            expires_at=AT + timedelta(days=7),
        )


def test_dataset_scoped_source_authorities_cannot_be_swapped() -> None:
    bundle = _bundle()
    definition = bundle["plan"].definition
    swapped_definition = definition.model_copy(
        update={
            "demand_authority_record_sha256": definition.cohort_authority_record_sha256,
            "cohort_authority_record_sha256": definition.demand_authority_record_sha256,
        }
    )
    bundle["plan"] = sign_measurement_run_plan(
        swapped_definition,
        bundle["keys"]["human"],
        issuer="measurement-human",
        issued_at=START_UTC - timedelta(days=1),
        expires_at=AT + timedelta(days=7),
    )
    with pytest.raises(MeasurementInputError, match="run plan"):
        _evaluate(bundle)


def test_exact_expiry_and_wrong_role_fail_closed() -> None:
    bundle = _bundle()
    with pytest.raises(MeasurementInputError, match="run plan"):
        bundle["runtime"].evaluate(
            bundle["plan"],
            bundle["demand"],
            bundle["cohort"],
            bundle["operations"],
            bundle["demand_attestation"],
            bundle["cohort_attestation"],
            bundle["operations_attestation"],
            bundle["index"],
            at=bundle["plan"].expires_at,
        )

    wrong_role_key = create_verification_key(
        bundle["keys"]["human"].public_key(),
        issuer="measurement-human",
        role=SigningRole.DEMAND_PRODUCER,
    )
    with pytest.raises(ValidationError, match="role mismatch"):
        MeasurementTrustStore(
            run_human=wrong_role_key,
            demand_producer=bundle["trust"].demand_producer,
            cohort_producer=bundle["trust"].cohort_producer,
            operations_producer=bundle["trust"].operations_producer,
            bundle_indexer=bundle["trust"].bundle_indexer,
            measurement_verifier=bundle["trust"].measurement_verifier,
        )
