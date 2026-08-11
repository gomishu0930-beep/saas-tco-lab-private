from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from saas_preflight.affiliate_partner_ledger import (
    AffiliateCommissionAmount,
    AffiliateCommissionStatus,
    AffiliateCommissionUnit,
    AffiliateCtaRuntimeState,
    AffiliatePartnerLedger,
    AffiliatePartnerLedgerEntry,
    AffiliatePartnershipStatus,
    evaluate_affiliate_cta_gate,
    evaluate_affiliate_program_cta_gate,
    load_affiliate_partner_ledger,
)
from saas_preflight.economics import Decision, RollbackTestStatus
from saas_preflight.models import FieldEvidence, PolicyDecision
from saas_preflight.preflight import (
    CohortInput,
    CommissionInput,
    ScenarioInputs,
    evaluate_business_dossier,
)
from saas_preflight.readiness_builder import (
    AffiliateProgramDecision,
    AffiliateReviewDecision,
    CohortEvidence,
    DemandEvidence,
    OperationsEvidence,
    build_affiliate_bundle,
    build_business_dossier,
    build_rights_bundle,
)

from test_models import NOW, make_plan, make_policy
from test_preflight import _demand


ROOT = Path(__file__).resolve().parents[1]
PARTNER_LEDGER_PATH = ROOT / "docs" / "AFFILIATE_PARTNER_LEDGER.json"


def test_partner_ledger_records_safe_status_without_private_values() -> None:
    ledger = load_affiliate_partner_ledger(PARTNER_LEDGER_PATH)

    assert tuple(entry.partner_id for entry in ledger.entries) == (
        "a8net",
        "mangools",
        "moshimo",
        "valuecommerce",
    )
    assert ledger.tracking_ids_saved is False
    assert ledger.advertising_urls_saved is False
    assert ledger.personal_data_saved is False
    assert ledger.schema_version == "1.1"

    entries = {entry.partner_id: entry for entry in ledger.entries}
    assert entries["mangools"].partnership_status is AffiliatePartnershipStatus.APPROVED
    assert entries["a8net"].account_status.value == "registered"
    assert entries["moshimo"].account_status.value == "registered"
    assert entries["valuecommerce"].account_status.value == "registered"
    for partner_id in ("a8net", "moshimo", "valuecommerce"):
        entry = entries[partner_id]
        assert entry.partnership_status is AffiliatePartnershipStatus.NOT_APPLIED
        assert entry.program_name is None
        assert entry.category is None
        assert entry.performance_condition is None
        assert entry.commission_amount.status is AffiliateCommissionStatus.UNKNOWN

    assert tuple(item.research_id for item in ledger.program_research) == (
        "a8net-formrun",
        "a8net-freee-accounting",
        "a8net-misoca",
        "a8net-money-forward-cloud-accounting",
        "a8net-will-mail",
        "a8net-xserver-business",
        "a8net-yayoi-series",
        "moshimo-conoha-wing",
        "moshimo-lolipop-rental-server",
        "moshimo-onamae-rental-server",
        "moshimo-shin-rental-server",
        "valuecommerce-ablenet-shared-server",
    )
    assert {item.asp_partner_id for item in ledger.program_research} == {
        "a8net",
        "moshimo",
        "valuecommerce",
    }
    assert sum(
        item.partnership_status is AffiliatePartnershipStatus.PENDING
        for item in ledger.program_research
    ) == 0
    assert sum(
        item.partnership_status is AffiliatePartnershipStatus.APPROVED
        for item in ledger.program_research
    ) == 6
    assert all(
        item.partnership_status is AffiliatePartnershipStatus.NOT_APPLIED
        for item in ledger.program_research
        if item.research_id not in {
            "a8net-xserver-business",
            "moshimo-conoha-wing",
            "moshimo-lolipop-rental-server",
            "moshimo-onamae-rental-server",
            "moshimo-shin-rental-server",
            "valuecommerce-ablenet-shared-server",
        }
    )
    assert all(item.commission_amount.value is None for item in ledger.program_research)
    assert sum(
        item.commission_amount.status
        is AffiliateCommissionStatus.RESTRICTED_DASHBOARD_ONLY
        for item in ledger.program_research
    ) == 11
    researched = {item.research_id: item for item in ledger.program_research}
    assert researched["a8net-xserver-business"].partnership_status is AffiliatePartnershipStatus.APPROVED
    assert researched["a8net-xserver-business"].condition_review_status.value == "detail_reviewed"
    assert researched["valuecommerce-ablenet-shared-server"].partnership_status is AffiliatePartnershipStatus.APPROVED
    assert researched["valuecommerce-ablenet-shared-server"].condition_review_status.value == "detail_reviewed"
    assert researched["moshimo-lolipop-rental-server"].partnership_status is AffiliatePartnershipStatus.APPROVED
    assert researched["moshimo-lolipop-rental-server"].condition_review_status.value == "detail_reviewed"
    for research_id in (
        "moshimo-conoha-wing",
        "moshimo-onamae-rental-server",
        "moshimo-shin-rental-server",
    ):
        assert researched[research_id].partnership_status is AffiliatePartnershipStatus.APPROVED
        assert researched[research_id].condition_review_status.value == "detail_reviewed"
    assert tuple(item.partner_id for item in ledger.network_search_checks) == (
        "benchmark-email",
        "blastmail",
        "conoha",
        "cybozu",
        "hubspot",
        "kintone",
    )
    assert all(
        item.next_networks == ("moshimo", "valuecommerce")
        for item in ledger.network_search_checks
    )

    source = PARTNER_LEDGER_PATH.read_text(encoding="utf-8")
    assert "http://" not in source
    assert "https://" not in source
    assert "@" not in source


def test_partner_ledger_cta_gate_is_fail_closed() -> None:
    ledger = load_affiliate_partner_ledger(PARTNER_LEDGER_PATH)
    entries = {entry.partner_id: entry for entry in ledger.entries}
    approved_runtime = AffiliateCtaRuntimeState(
        partner_id="mangools",
        partner_approval_current=True,
        disclosure_precedes_cta=True,
        destination_configured=True,
        cta_go=True,
    )

    assert evaluate_affiliate_cta_gate(entries["mangools"], approved_runtime) is True
    for field in (
        "partner_approval_current",
        "disclosure_precedes_cta",
        "destination_configured",
        "cta_go",
    ):
        held = approved_runtime.model_copy(update={field: False})
        assert evaluate_affiliate_cta_gate(entries["mangools"], held) is False

    for partner_id in ("a8net", "moshimo", "valuecommerce"):
        unapproved_runtime = approved_runtime.model_copy(
            update={"partner_id": partner_id}
        )
        assert evaluate_affiliate_cta_gate(entries[partner_id], unapproved_runtime) is False

    a8_account = entries["a8net"]
    for program in ledger.program_research:
        unapproved_program_runtime = approved_runtime.model_copy(
            update={"partner_id": program.research_id}
        )
        assert (
            evaluate_affiliate_program_cta_gate(
                a8_account,
                program,
                unapproved_program_runtime,
            )
            is False
        )


def test_partner_ledger_rejects_private_fields_and_incoherent_rewards() -> None:
    source = json.loads(PARTNER_LEDGER_PATH.read_text(encoding="utf-8"))
    source["entries"][0]["tracking_id"] = "must-not-be-stored"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AffiliatePartnerLedger.model_validate_json(json.dumps(source))

    with pytest.raises(ValidationError, match="known commission requires"):
        AffiliateCommissionAmount(status=AffiliateCommissionStatus.KNOWN)
    with pytest.raises(ValidationError, match="unavailable commission cannot retain"):
        AffiliateCommissionAmount(
            status=AffiliateCommissionStatus.UNKNOWN,
            value=Decimal("1"),
            unit=AffiliateCommissionUnit.JPY,
        )
    with pytest.raises(ValidationError, match="unavailable commission cannot retain"):
        AffiliateCommissionAmount(
            status=AffiliateCommissionStatus.RESTRICTED_DASHBOARD_ONLY,
            value=Decimal("1"),
            unit=AffiliateCommissionUnit.JPY,
        )

    entry = load_affiliate_partner_ledger(PARTNER_LEDGER_PATH).entries[0]
    payload = entry.model_dump(mode="json")
    payload["category"] = "未選定カテゴリ"
    with pytest.raises(ValidationError, match="unselected partnership"):
        AffiliatePartnerLedgerEntry.model_validate_json(json.dumps(payload))

    payload = entry.model_dump(mode="json")
    payload.update(
        {
            "program_name": "選定済み未申請program",
            "category": "業務SaaS",
            "performance_condition": "公開規約で確認済みの成果条件",
            "commission_amount": {
                "status": "known",
                "value": "1000",
                "unit": "JPY",
            },
        }
    )
    selected = AffiliatePartnerLedgerEntry.model_validate_json(json.dumps(payload))
    assert selected.partnership_status is AffiliatePartnershipStatus.NOT_APPLIED


def _affiliate(
    partner_id: str = "partner-a",
    vendor_slug: str = "example",
    **overrides: object,
) -> AffiliateProgramDecision:
    values: dict[str, object] = {
        "partner_id": partner_id,
        "vendor_slug": vendor_slug,
        "property_domain": "example.test",
        "territory": "JP",
        "decision": AffiliateReviewDecision.APPROVED,
        "reviewed_at": NOW - timedelta(days=1),
        "review_due_at": NOW + timedelta(days=30),
        "reviewed_by": "human-owner",
        "decision_record_sha256": "a" * 64,
        "program_id": f"program-{partner_id}",
        "destination_sha256": "b" * 64,
        "disclosure_sha256": "c" * 64,
    }
    values.update(overrides)
    return AffiliateProgramDecision(**values)


def _scenarios() -> ScenarioInputs:
    return ScenarioInputs(
        bear=_demand("1000000", "0.10"),
        base=_demand("1200000", "0.12"),
        bull=_demand("1500000", "0.15"),
    )


def _demand_evidence() -> DemandEvidence:
    return DemandEvidence(
        evidence_version="demand-v1",
        source_sha256="d" * 64,
        captured_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        scenarios=_scenarios(),
    )


def _cohort_evidence() -> CohortEvidence:
    return CohortEvidence(
        evidence_version="cohort-v1",
        source_sha256="e" * 64,
        status_mapping_sha256="f" * 64,
        captured_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
        cohort=CohortInput(
            currency="JPY",
            valid_clicks=1000,
            age_days=30,
            commissions=CommissionInput(
                pending=Decimal(0),
                rejected=Decimal(0),
                confirmed=Decimal("30000"),
                paid=Decimal("30000"),
            ),
        ),
    )


def _operations_evidence(**overrides: object) -> OperationsEvidence:
    values: dict[str, object] = {
        "evidence_version": "operations-v1",
        "source_sha256": "1" * 64,
        "observation_started_at": NOW - timedelta(days=31),
        "captured_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(days=7),
        "human_minutes_per_month": 720,
        "routine_tasks_total": 100,
        "routine_tasks_automated": 80,
        "major_misstatements": 0,
        "job_runs_total": 100,
        "job_runs_succeeded": 99,
        "exceptions_total": 24,
        "rollback_test_status": RollbackTestStatus.PASSED,
    }
    values.update(overrides)
    return OperationsEvidence(**values)


def _plans() -> tuple:
    return tuple(
        make_plan(
            snapshot_id=uuid4(),
            vendor_slug=vendor,
            vendor_name=vendor.title(),
        )
        for vendor in ("vendor-a", "vendor-b", "vendor-c")
    )


def _affiliates() -> tuple[AffiliateProgramDecision, ...]:
    return tuple(
        _affiliate(partner_id=f"partner-{suffix}", vendor_slug=f"vendor-{suffix}")
        for suffix in ("a", "b", "c")
    )


def test_rights_bundle_is_derived_from_every_field_policy() -> None:
    bundle = build_rights_bundle([make_plan()], at=NOW)

    assert bundle.approved is True
    assert bundle.eligible_vendor_slugs == ("example",)
    assert len(bundle.bundle_sha256) == 64


def test_one_prohibited_publish_policy_makes_rights_fail() -> None:
    plan = make_plan()
    changed: list[FieldEvidence] = []
    for item in plan.field_evidence:
        if item.field == "base_price":
            pointer = item.pointers[0]
            policy = make_policy(
                field=item.field,
                publish=PolicyDecision.PROHIBITED,
            )
            item = item.model_copy(
                update={
                    "pointers": (
                        pointer.model_copy(update={"source_policy": policy}),
                    )
                }
            )
        changed.append(item)
    denied_plan = plan.model_copy(update={"field_evidence": tuple(changed)})

    bundle = build_rights_bundle([denied_plan], at=NOW)
    assert bundle.approved is False
    assert bundle.eligible_vendor_slugs == ()
    assert "example.basic.base_price:publish" in bundle.denied_fields


def test_affiliate_duplicates_cannot_inflate_partner_count() -> None:
    duplicate = _affiliate()
    with pytest.raises(ValueError, match="partner IDs must be distinct"):
        build_affiliate_bundle(
            [duplicate, duplicate], property_domain="example.test", at=NOW
        )


def test_two_approved_programs_for_one_vendor_are_rejected() -> None:
    with pytest.raises(ValueError, match="one current approved"):
        build_affiliate_bundle(
            [_affiliate("partner-a"), _affiliate("partner-b")],
            property_domain="example.test",
            at=NOW,
        )


def test_nonapproved_decision_cannot_smuggle_cta_data() -> None:
    with pytest.raises(ValidationError, match="cannot carry program or CTA data"):
        _affiliate(decision=AffiliateReviewDecision.UNREVIEWED)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _affiliate(affiliate_url="https://example.test/secret")


def test_expired_rights_and_evidence_are_rejected() -> None:
    expired_plan = make_plan(captured_at=NOW - timedelta(days=400))
    with pytest.raises(ValueError, match="retention window has expired"):
        build_rights_bundle([expired_plan], at=NOW)

    with pytest.raises(ValueError, match="demand evidence is expired"):
        build_business_dossier(
            plans=_plans(),
            affiliate_decisions=_affiliates(),
            property_domain="example.test",
            demand=_demand_evidence().model_copy(
                update={"expires_at": NOW}
            ),
            cohort=_cohort_evidence(),
            operations=_operations_evidence(),
            at=NOW,
        )


def test_zero_routine_denominator_derives_zero_not_a_false_go() -> None:
    operations = _operations_evidence(
        routine_tasks_total=0, routine_tasks_automated=0
    )
    dossier = build_business_dossier(
        plans=_plans(),
        affiliate_decisions=_affiliates(),
        property_domain="example.test",
        demand=_demand_evidence(),
        cohort=_cohort_evidence(),
        operations=operations,
        at=NOW,
    )

    assert dossier.automation_rate == Decimal(0)
    assert evaluate_business_dossier(dossier, at=NOW).decision is Decision.STOP


def test_provenance_assembler_reaches_go_with_complete_synthetic_evidence() -> None:
    dossier = build_business_dossier(
        plans=_plans(),
        affiliate_decisions=_affiliates(),
        property_domain="Example.Test.",
        demand=_demand_evidence(),
        cohort=_cohort_evidence(),
        operations=_operations_evidence(),
        at=NOW,
    )

    assert dossier.schema_version == "3.0"
    assert dossier.provenance.property_domain == "example.test"
    assert dossier.rights_approved is True
    assert dossier.approved_affiliate_ids == (
        "partner-a",
        "partner-b",
        "partner-c",
    )
    assert dossier.human_hours_per_month == Decimal(12)
    assert dossier.automation_rate == Decimal("0.8")
    assert dossier.shadow_observation_days == 30
    assert dossier.job_runs_total == 100
    assert dossier.job_runs_succeeded == 99
    assert dossier.exceptions_total == 24
    assert dossier.rollback_test_status is RollbackTestStatus.PASSED
    assert evaluate_business_dossier(dossier, at=NOW).decision is Decision.GO


def test_evidence_version_binds_derived_operations_payload() -> None:
    common = {
        "plans": _plans(),
        "affiliate_decisions": _affiliates(),
        "property_domain": "example.test",
        "demand": _demand_evidence(),
        "cohort": _cohort_evidence(),
        "at": NOW,
    }
    first = build_business_dossier(
        **common, operations=_operations_evidence(human_minutes_per_month=60)
    )
    second = build_business_dossier(
        **common, operations=_operations_evidence(human_minutes_per_month=120)
    )

    assert first.evidence_version != second.evidence_version


def test_operations_evidence_rejects_impossible_run_and_time_counts() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        _operations_evidence(job_runs_total=1, job_runs_succeeded=2)
    with pytest.raises(ValidationError, match="cannot be after"):
        _operations_evidence(observation_started_at=NOW)


def test_approved_affiliate_requires_a_corresponding_plan() -> None:
    with pytest.raises(ValueError, match="lack VendorPlan evidence"):
        build_business_dossier(
            plans=[make_plan()],
            affiliate_decisions=[_affiliate(vendor_slug="missing-vendor")],
            property_domain="example.test",
            demand=_demand_evidence(),
            cohort=_cohort_evidence(),
            operations=_operations_evidence(),
            at=NOW,
        )
