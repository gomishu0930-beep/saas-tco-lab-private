"""Local, fail-closed command line interface for the Phase 0-1 core.

The CLI deliberately has no network, publication, affiliate, or production
write command.  It only validates local snapshots, stores approved history in
an append-only local SQLite file, and calculates deterministic TCO after a
current field-level derivation-rights check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .ai_routing import (
    ModelRouteDecision,
    ModelRouterPolicy,
    ModelRoutingRequest,
    evaluate_model_route,
)
from .goldset import CandidateBatch, HumanGoldSet, evaluate_goldset
from .editorial_input import (
    CategoryExpansionInput,
    ExpansionCategory,
    merge_category_expansion_inputs,
)
from .growth_system import (
    ActivationDecision,
    ConditionalActivationInput,
    CtaDecision,
    CtaHealthInput,
    EditorialDecision,
    EditorialPackage,
    FeedbackBatch,
    InitiativePortfolio,
    OperationsKpiInput,
    build_kpi_scorecard,
    build_policy_memo,
    evaluate_cta_health,
    evaluate_conditional_activation,
    evaluate_editorial_package,
)
from .initial_learning_quality import (
    InitialLearningQualityBundle,
    InitialLearningQualityDecision,
    InitialLearningQualityPolicy,
    InitialLearningTrustStore,
    evaluate_initial_learning_quality,
)
from .launch_handoff import (
    LaunchHandoffBundle,
    LaunchHandoffDecision,
    LaunchHandoffPlan,
    LaunchHandoffPolicy,
    LaunchHandoffTrustStore,
    evaluate_launch_handoff,
)
from .launch_semantics import LaunchSemanticAuthorityPins
from .keyword_universe import load_keyword_universe, summarize_keyword_universe
from .mangools_export import (
    build_mangools_expansion_set_safe_summary,
    validate_mangools_human_export,
    validate_mangools_human_export_batches,
)
from .measurement import (
    CohortSummaryBatch,
    DemandSummaryBatch,
    OperationsSummaryBatch,
    build_cohort_evidence,
    build_demand_evidence,
    build_operations_evidence,
)
from .measurement_integrity import (
    MeasurementAuthorityPins,
    MeasurementBoundDossier,
    MeasurementIntegrityReport,
    MeasurementPolicy,
    MeasurementTrustStore,
    assemble_measurement_bound_dossier,
    verify_measurement_bound_dossier,
)
from .models import PolicyAction, VendorPlan
from .operations_activity import (
    OperationalCostPolicy,
    OperationsActivityBatch,
    derive_operations_activity,
)
from .preflight import BusinessDossier, evaluate_business_dossier
from .preview import PreviewPage, render_preview
from .production_readiness import (
    ProductionIntegrationEvidenceBundle,
    ProductionIntegrationPlan,
    ProductionIntegrationPolicy,
    ProductionIntegrationTrustStore,
    ProductionReadinessDecision,
    ProductionReconciliationFacts,
    evaluate_production_integration_readiness,
    evaluate_production_reconciliation,
)
from .readiness_builder import (
    AffiliateDecisionBatch,
    CohortEvidence,
    DemandEvidence,
    OperationsEvidence,
    build_business_dossier,
)
from .repository_acceptance import (
    HumanRepositoryAcceptance,
    RepositoryAcceptanceAuthorityPins,
    RepositoryAcceptanceDecision,
    RepositoryAcceptancePolicy,
    RepositoryAcceptanceReceiptChain,
    RepositoryAcceptanceTrustStore,
    RepositoryCandidateManifest,
    RepositoryVerificationCheck,
    RepositoryVerificationAttestation,
    RepositoryVerificationEvidenceBundle,
    build_repository_candidate_manifest,
    build_repository_verification_from_verified_runner_evidence,
    evaluate_repository_acceptance,
    run_repository_verification,
    run_repository_verification_check,
)
from .storage import SQLitePlanRepository
from .tco import calculate_vendor_plan_tco, constant_usage_scenario
from .settlement_amendment import (
    SettlementAmendmentPolicy,
    SettlementAmendmentTrustStore,
)
from .traction_control import (
    SignedTractionPlan,
    TractionAuthorityPins,
    TractionDecision,
    TractionEvaluationBundle,
    TractionPolicy,
    TractionTrustStore,
    evaluate_traction,
)
from .verified_runner import (
    VerifiedRunnerAuthorityPins,
    VerifiedRunnerConsumptionReceipt,
    VerifiedRunnerEvidenceBundle,
    VerifiedRunnerPolicy,
    VerifiedRunnerTrustStore,
    verify_verified_runner_evidence,
    verify_verified_runner_consumption_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saas-preflight",
        description="Validate and calculate approved SaaS pricing snapshots locally.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_db = commands.add_parser("init-db", help="Create a secure append-only SQLite DB.")
    init_db.add_argument("--db", type=Path, required=True)

    validate = commands.add_parser("validate-plan", help="Validate one local VendorPlan JSON file.")
    validate.add_argument("plan", type=Path)

    keyword_universe = commands.add_parser(
        "validate-keyword-universe",
        help="Validate a frozen offline JP/ja Keyword Planner input CSV.",
    )
    keyword_universe.add_argument("universe", type=Path)
    keyword_universe.add_argument("--minimum-keywords", type=int, default=100)
    keyword_universe.add_argument("--maximum-keywords", type=int, default=200)

    kwfinder_upload = commands.add_parser(
        "prepare-kwfinder-upload",
        help="Write an exact query-only slice of a frozen slate for Human KWFinder input.",
    )
    kwfinder_upload.add_argument("universe", type=Path)
    kwfinder_upload.add_argument("--output", type=Path, required=True)
    kwfinder_upload.add_argument("--start-index", type=int, default=0)
    kwfinder_upload.add_argument("--limit", type=int)

    mangools_export = commands.add_parser(
        "validate-mangools-export",
        help="Validate one Human-exported KWFinder CSV and emit a safe aggregate only.",
    )
    mangools_export.add_argument("csv", type=Path)
    mangools_export.add_argument("--universe", type=Path, required=True)
    mangools_export.add_argument("--observed-on", type=date.fromisoformat, required=True)
    mangools_export.add_argument("--next-review-on", type=date.fromisoformat, required=True)
    mangools_export.add_argument("--monthly-revenue-target-jpy", type=int, default=200_000)
    mangools_export.add_argument("--assumed-confirmed-epc-jpy", type=_decimal_argument, default=Decimal("60"))
    mangools_export.add_argument("--assumed-outbound-ctr", type=_decimal_argument, default=Decimal("0.15"))

    mangools_slate_export = commands.add_parser(
        "validate-mangools-slate-export",
        help="Validate a complete frozen query slate split across Human-exported CSV files.",
    )
    mangools_slate_export.add_argument("csv", type=Path, nargs="+")
    mangools_slate_export.add_argument("--slate-id", required=True)
    mangools_slate_export.add_argument("--universe", type=Path, required=True)
    mangools_slate_export.add_argument(
        "--observed-on", type=date.fromisoformat, required=True
    )
    mangools_slate_export.add_argument(
        "--next-review-on", type=date.fromisoformat, required=True
    )
    mangools_slate_export.add_argument(
        "--monthly-revenue-target-jpy", type=int, default=200_000
    )
    mangools_slate_export.add_argument(
        "--assumed-confirmed-epc-jpy",
        type=_decimal_argument,
        default=Decimal("60"),
    )
    mangools_slate_export.add_argument(
        "--assumed-outbound-ctr", type=_decimal_argument, default=Decimal("0.15")
    )
    mangools_slate_export.add_argument(
        "--output",
        type=Path,
        help=(
            "Append-only local safe-summary destination under outputs/. Raw CSV "
            "inputs must be outside --repository-root."
        ),
    )
    mangools_slate_export.add_argument(
        "--repository-root", type=Path, default=Path.cwd()
    )

    mangools_expansion_set = commands.add_parser(
        "validate-mangools-expansion-set",
        help="Validate all four remaining Human-exported expansion slates at once.",
    )
    mangools_expansion_set.add_argument("--crm", type=Path, required=True)
    mangools_expansion_set.add_argument("--forms", type=Path, required=True)
    mangools_expansion_set.add_argument(
        "--email-marketing", type=Path, required=True
    )
    mangools_expansion_set.add_argument(
        "--seo-tools-v2-extension", type=Path, required=True
    )
    mangools_expansion_set.add_argument(
        "--slates-dir", type=Path, default=Path("examples")
    )
    mangools_expansion_set.add_argument(
        "--observed-on", type=date.fromisoformat, required=True
    )
    mangools_expansion_set.add_argument(
        "--next-review-on", type=date.fromisoformat, required=True
    )
    mangools_expansion_set.add_argument(
        "--monthly-revenue-target-jpy", type=int, default=200_000
    )
    mangools_expansion_set.add_argument(
        "--assumed-confirmed-epc-jpy",
        type=_decimal_argument,
        default=Decimal("60"),
    )
    mangools_expansion_set.add_argument(
        "--assumed-outbound-ctr", type=_decimal_argument, default=Decimal("0.15")
    )

    merge_servers = commands.add_parser(
        "merge-server-candidates",
        help=(
            "Merge separately saved server candidate JSON files into one "
            "candidate-only contract."
        ),
    )
    merge_servers.add_argument("candidate", type=Path, nargs="+")
    merge_servers.add_argument("--output", type=Path, required=True)

    store = commands.add_parser("store-plan", help="Append one validated plan to a local DB.")
    store.add_argument("plan", type=Path)
    store.add_argument("--db", type=Path, required=True)

    listing = commands.add_parser("list-plans", help="List snapshot metadata without excerpts.")
    listing.add_argument("--db", type=Path, required=True)
    listing.add_argument("--vendor", dest="vendor_slug")
    listing.add_argument("--plan", dest="plan_slug")
    listing.add_argument("--limit", type=int)

    tco = commands.add_parser("calculate-tco", help="Calculate local TCO after a derivation-rights gate.")
    tco.add_argument("plan", type=Path)
    tco.add_argument("--seats", type=int, required=True)
    tco.add_argument("--months", type=int, default=12)
    tco.add_argument("--monthly-usage", type=_decimal_argument, default=Decimal("0"))
    tco.add_argument("--usage-unit")
    tco.add_argument(
        "--addon",
        action="append",
        default=[],
        help="Optional add-on code to include; repeat for multiple add-ons.",
    )

    preview = commands.add_parser(
        "render-preview",
        help="Render a noindex HTML preview from precomputed canonical TCO JSON.",
    )
    preview.add_argument("page", type=Path)
    preview.add_argument("--output", type=Path, required=True)

    readiness = commands.add_parser(
        "evaluate-readiness",
        help="Evaluate an unsigned diagnostic dossier; never production authority.",
    )
    readiness.add_argument("dossier", type=Path)

    assemble = commands.add_parser(
        "assemble-readiness",
        help="Build an unsigned diagnostic dossier; never production authority.",
    )
    assemble.add_argument("--plan", action="append", type=Path, required=True)
    assemble.add_argument("--affiliate-decisions", type=Path, required=True)
    assemble.add_argument("--demand-evidence", type=Path, required=True)
    assemble.add_argument("--cohort-evidence", type=Path, required=True)
    assemble.add_argument("--operations-evidence", type=Path, required=True)
    assemble.add_argument("--property-domain", required=True)
    assemble.add_argument("--output", type=Path, required=True)
    assemble.add_argument("--at", type=_utc_datetime_argument)

    signed_assemble = commands.add_parser(
        "assemble-signed-readiness",
        help="Verify a pinned P12 report and build a measurement-bound dossier.",
    )
    signed_assemble.add_argument("--plan", action="append", type=Path, required=True)
    signed_assemble.add_argument("--affiliate-decisions", type=Path, required=True)
    signed_assemble.add_argument("--measurement-report", type=Path, required=True)
    signed_assemble.add_argument("--measurement-policy", type=Path, required=True)
    signed_assemble.add_argument("--measurement-trust-store", type=Path, required=True)
    signed_assemble.add_argument("--authority-pins", type=Path, required=True)
    signed_assemble.add_argument("--property-domain", required=True)
    signed_assemble.add_argument("--output", type=Path, required=True)

    signed_evaluate = commands.add_parser(
        "evaluate-signed-readiness",
        help="Reverify a pinned measurement-bound dossier before local economics.",
    )
    signed_evaluate.add_argument("bundle", type=Path)
    signed_evaluate.add_argument("--measurement-policy", type=Path, required=True)
    signed_evaluate.add_argument("--measurement-trust-store", type=Path, required=True)
    signed_evaluate.add_argument("--authority-pins", type=Path, required=True)

    demand = commands.add_parser(
        "aggregate-demand",
        help="Convert one sanitized demand summary into immutable evidence.",
    )
    demand.add_argument("summary", type=Path)
    demand.add_argument("--output", type=Path, required=True)

    cohort = commands.add_parser(
        "aggregate-cohort",
        help="Convert one sanitized affiliate cohort summary into immutable evidence.",
    )
    cohort.add_argument("summary", type=Path)
    cohort.add_argument("--output", type=Path, required=True)

    operations = commands.add_parser(
        "aggregate-operations",
        help="Convert one sanitized shadow-operations summary into immutable evidence.",
    )
    operations.add_argument("summary", type=Path)
    operations.add_argument("--output", type=Path, required=True)

    operations_activity = commands.add_parser(
        "derive-operations-activity",
        help=(
            "Derive receipt-backed 30-day automation, human-time, TCO, and "
            "net-profit evidence without network or secrets."
        ),
    )
    operations_activity.add_argument("batch", type=Path)
    operations_activity.add_argument("--cost-policy", type=Path, required=True)
    operations_activity.add_argument(
        "--gross-settled-revenue-jpy",
        type=_decimal_argument,
        required=True,
    )
    operations_activity.add_argument(
        "--at", type=_utc_datetime_argument, required=True
    )
    operations_activity.add_argument("--output", type=Path, required=True)

    goldset = commands.add_parser(
        "evaluate-gold-set",
        help="Compare an offline Human gold set with one typed candidate batch.",
    )
    goldset.add_argument("--gold-set", type=Path, required=True)
    goldset.add_argument("--candidates", type=Path, required=True)
    goldset.add_argument("--at", type=_utc_datetime_argument)

    editorial = commands.add_parser(
        "evaluate-editorial-package",
        help="Evaluate a hash-only three-draft editorial package for local review.",
    )
    editorial.add_argument("package", type=Path)
    editorial.add_argument("--at", type=_utc_datetime_argument, required=True)

    scorecard = commands.add_parser(
        "build-growth-scorecard",
        help="Build one observed KPI scorecard from sanitized local feedback facts.",
    )
    scorecard.add_argument("feedback", type=Path)
    scorecard.add_argument("--operations", type=Path, required=True)
    scorecard.add_argument("--at", type=_utc_datetime_argument, required=True)
    scorecard.add_argument("--output", type=Path, required=True)

    initiatives = commands.add_parser(
        "rank-growth-initiatives",
        help="Rank exactly three local initiatives after independent hard gates.",
    )
    initiatives.add_argument("portfolio", type=Path)

    cta_health = commands.add_parser(
        "evaluate-cta-health",
        help="Fail closed on affiliate, rights, destination, disclosure, or link drift.",
    )
    cta_health.add_argument("input", type=Path)
    cta_health.add_argument("--at", type=_utc_datetime_argument, required=True)

    activation = commands.add_parser(
        "evaluate-growth-activation",
        help="Evaluate a deferred tool against its evidence trigger; never activates it.",
    )
    activation.add_argument("input", type=Path)
    activation.add_argument("--at", type=_utc_datetime_argument, required=True)

    model_route = commands.add_parser(
        "evaluate-model-route",
        help="Select one evaluated pinned model route; performs no API call.",
    )
    model_route.add_argument("request", type=Path)
    model_route.add_argument("--policy", type=Path, required=True)
    model_route.add_argument("--at", type=_utc_datetime_argument, required=True)

    initial_learning = commands.add_parser(
        "evaluate-initial-learning-quality",
        help=(
            "Verify signed owned-data profiles and Human labels before any "
            "learning run; grants no learning or publication authority."
        ),
    )
    initial_learning.add_argument("bundle", type=Path)
    initial_learning.add_argument("--policy", type=Path, required=True)
    initial_learning.add_argument("--trust-store", type=Path, required=True)
    initial_learning.add_argument("--expected-authority-sha256", required=True)
    initial_learning.add_argument("--at", type=_utc_datetime_argument, required=True)

    production_readiness = commands.add_parser(
        "evaluate-production-readiness",
        help="Evaluate one local P15 evidence bundle; performs no external operation.",
    )
    production_readiness.add_argument("bundle", type=Path)
    production_readiness.add_argument("--plan", type=Path, required=True)
    production_readiness.add_argument("--policy", type=Path, required=True)
    production_readiness.add_argument("--trust-store", type=Path, required=True)
    production_readiness.add_argument("--at", type=_utc_datetime_argument, required=True)

    reconciliation = commands.add_parser(
        "evaluate-production-reconciliation",
        help="Evaluate local P15 reconciliation facts without changing P13 or external state.",
    )
    reconciliation.add_argument("facts", type=Path)
    reconciliation.add_argument("--at", type=_utc_datetime_argument, required=True)

    handoff = commands.add_parser(
        "evaluate-launch-handoff",
        help="Evaluate a local P16 packet for final Human review; grants no authority.",
    )
    handoff.add_argument("bundle", type=Path)
    handoff.add_argument("--plan", type=Path, required=True)
    handoff.add_argument("--policy", type=Path, required=True)
    handoff.add_argument("--trust-store", type=Path, required=True)
    handoff.add_argument(
        "--expected-repository-acceptance-authority-pins-sha256",
        required=True,
    )
    handoff.add_argument(
        "--expected-launch-handoff-authority-sha256", required=True
    )
    handoff.add_argument("--launch-semantic-authority-pins", type=Path)
    handoff.add_argument(
        "--expected-launch-semantic-authority-pins-sha256"
    )
    handoff.add_argument("--at", type=_utc_datetime_argument, required=True)

    traction = commands.add_parser(
        "evaluate-traction",
        help="Evaluate a local P17 traction packet; grants no scale or external authority.",
    )
    traction.add_argument("bundle", type=Path)
    traction.add_argument("--plan", type=Path, required=True)
    traction.add_argument("--policy", type=Path, required=True)
    traction.add_argument("--trust-store", type=Path, required=True)
    traction.add_argument("--authority-pins", type=Path, required=True)
    traction.add_argument("--settlement-policy", type=Path, required=True)
    traction.add_argument("--settlement-trust-store", type=Path, required=True)
    traction.add_argument("--at", type=_utc_datetime_argument, required=True)

    acceptance_build = commands.add_parser(
        "build-local-acceptance-manifest",
        help="Hash the fixed local repository scope into an authority-free P18 candidate.",
    )
    acceptance_build.add_argument("--repo-root", type=Path, required=True)
    acceptance_build.add_argument(
        "--verification-evidence", type=Path, required=True
    )
    acceptance_build.add_argument("--integration-attestation", type=Path)
    acceptance_build.add_argument("--tco-qa-attestation", type=Path)
    acceptance_build.add_argument("--candidate-id", required=True)
    acceptance_build.add_argument(
        "--assembled-at", type=_utc_datetime_argument, required=True
    )
    acceptance_build.add_argument(
        "--expires-at", type=_utc_datetime_argument, required=True
    )
    acceptance_build.add_argument("--output", type=Path, required=True)

    acceptance_evaluate = commands.add_parser(
        "evaluate-local-acceptance",
        help="Recompute a P18 repository manifest and evaluate optional Human authority.",
    )
    acceptance_evaluate.add_argument("manifest", type=Path)
    acceptance_evaluate.add_argument("--repo-root", type=Path, required=True)
    acceptance_evaluate.add_argument("--at", type=_utc_datetime_argument, required=True)
    acceptance_evaluate.add_argument("--receipt", type=Path)
    acceptance_evaluate.add_argument("--receipt-chain", type=Path)
    acceptance_evaluate.add_argument("--policy", type=Path)
    acceptance_evaluate.add_argument("--trust-store", type=Path)
    acceptance_evaluate.add_argument("--authority-pins", type=Path)
    acceptance_evaluate.add_argument("--expected-verification-authority-sha256")
    acceptance_evaluate.add_argument("--expected-authority-pins-sha256")

    verification_run = commands.add_parser(
        "run-local-verification",
        help="Run the fixed network-restricted P18 checks and emit unsigned facts.",
    )
    verification_run.add_argument("--repo-root", type=Path, required=True)
    verification_run.add_argument(
        "--workflow-verifier", type=Path, required=True
    )
    verification_run.add_argument(
        "--fact-ttl-seconds", type=int, default=86_400
    )
    verification_run.add_argument(
        "--maximum-output-bytes", type=int, default=4 * 1024 * 1024
    )

    immutable_verify = commands.add_parser(
        "verify-immutable-runner-evidence",
        help=(
            "Verify retained P19 V2 evidence plus its signed one-shot consumption "
            "receipt and emit the P18 structural summary; grants no authority."
        ),
    )
    immutable_verify.add_argument("evidence", type=Path)
    immutable_verify.add_argument(
        "--consumption-receipt", type=Path, required=True
    )
    immutable_verify.add_argument("--policy", type=Path, required=True)
    immutable_verify.add_argument("--trust-store", type=Path, required=True)
    immutable_verify.add_argument("--authority-pins", type=Path, required=True)
    immutable_verify.add_argument(
        "--expected-authority-sha256", required=True
    )
    immutable_verify.add_argument(
        "--at", type=_utc_datetime_argument, required=True
    )
    immutable_verify.add_argument("--output", type=Path, required=True)

    internal_check = commands.add_parser(
        "_run-repository-check", help=argparse.SUPPRESS
    )
    internal_check.add_argument("check", type=RepositoryVerificationCheck)
    internal_check.add_argument("--repo-root", type=Path, required=True)
    internal_check.add_argument("--work-dir", type=Path, required=True)
    internal_check.add_argument(
        "--python-executable", type=Path, required=True
    )
    internal_check.add_argument("--uv-executable", type=Path, required=True)
    internal_check.add_argument(
        "--gitleaks-executable", type=Path, required=True
    )
    internal_check.add_argument("--npm-executable", type=Path, required=True)
    internal_check.add_argument("--node-executable", type=Path, required=True)
    internal_check.add_argument(
        "--workflow-verifier", type=Path, required=True
    )
    internal_check.add_argument(
        "--maximum-output-bytes", type=int, required=True
    )
    return parser


def _decimal_argument(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return result


def _utc_datetime_argument(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 UTC timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("must be a timezone-aware UTC timestamp")
    return result


def _load_plan(path: Path) -> VendorPlan:
    return VendorPlan.model_validate_json(path.read_text(encoding="utf-8"))


def _load_preview(path: Path) -> PreviewPage:
    return PreviewPage.model_validate_json(path.read_text(encoding="utf-8"))


def _load_dossier(path: Path) -> BusinessDossier:
    return BusinessDossier.model_validate_json(path.read_text(encoding="utf-8"))


def _load_model(path: Path, model_type: Any) -> Any:
    serialized = path.read_text(encoding="utf-8")
    json.loads(serialized, object_pairs_hook=_reject_duplicate_json_keys)
    return model_type.model_validate_json(serialized)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _write_new_model(path: Path, model: Any) -> None:
    with path.open("x", encoding="utf-8") as destination:
        destination.write(model.model_dump_json(indent=2))
        destination.write("\n")


def _denied_fields(
    plan: VendorPlan, action: PolicyAction, *, at: datetime
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                evidence.field
                for evidence in plan.field_evidence
                if any(
                    not pointer.source_policy.permits(action, at=at)
                    for pointer in evidence.pointers
                )
            }
        )
    )


def _earliest_history_delete_after(plan: VendorPlan) -> datetime:
    deadlines: list[datetime] = []
    for evidence in plan.field_evidence:
        for pointer in evidence.pointers:
            days = pointer.source_policy.retention_days
            if days is None:
                raise PermissionError(
                    f"history retention has no maximum for field: {evidence.field}"
                )
            deadlines.append(plan.captured_at + timedelta(days=days))
    if not deadlines:
        raise PermissionError("history retention deadline cannot be determined")
    return min(deadlines)


def _plan_status(plan: VendorPlan, *, at: datetime) -> dict[str, Any]:
    derive_denied = _denied_fields(plan, PolicyAction.DERIVE, at=at)
    publish_denied = _denied_fields(plan, PolicyAction.PUBLISH, at=at)
    return {
        "schema_version": plan.schema_version,
        "snapshot_id": str(plan.snapshot_id),
        "vendor_slug": plan.vendor_slug,
        "plan_slug": plan.plan_slug,
        "material_fields": sorted(plan.material_fields()),
        "derivable_now": not derive_denied,
        "derive_denied_fields": list(derive_denied),
        "publishable_now": not publish_denied,
        "publish_denied_fields": list(publish_denied),
    }


def _emit(payload: Any) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"unsupported JSON output type: {type(value).__name__}")


def _validation_error_message(exc: ValidationError) -> str:
    """Render model errors without echoing evidence values into logs."""

    details: list[str] = []
    for error in exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = (
            "<unknown-field>"
            if error["type"] == "extra_forbidden"
            else ".".join(str(part) for part in error["loc"]) or "document"
        )
        details.append(f"{location}: {error['msg']}")
    return "document validation failed: " + "; ".join(details)


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.command == "_run-repository-check":
            result = run_repository_verification_check(
                args.check,
                args.repo_root,
                args.work_dir,
                python_executable=args.python_executable,
                uv_executable=args.uv_executable,
                gitleaks_executable=args.gitleaks_executable,
                npm_executable=args.npm_executable,
                node_executable=args.node_executable,
                workflow_verifier=args.workflow_verifier,
                maximum_output_bytes=args.maximum_output_bytes,
            )
            _emit(result)
            return result["exit_code"]

        if args.command == "run-local-verification":
            bundle = run_repository_verification(
                args.repo_root,
                workflow_verifier=args.workflow_verifier,
                fact_ttl_seconds=args.fact_ttl_seconds,
                maximum_output_bytes=args.maximum_output_bytes,
            )
            _emit(bundle.model_dump(mode="json"))
            return 0 if all(item.succeeded for item in bundle.facts) else 3

        if args.command == "verify-immutable-runner-evidence":
            policy = _load_model(args.policy, VerifiedRunnerPolicy)
            runner_trust = _load_model(
                args.trust_store, VerifiedRunnerTrustStore
            )
            pins = _load_model(
                args.authority_pins, VerifiedRunnerAuthorityPins
            )
            verified = verify_verified_runner_evidence(
                _load_model(args.evidence, VerifiedRunnerEvidenceBundle),
                policy=policy,
                trust_store=runner_trust,
                authority_pins=pins,
                expected_authority_sha256=args.expected_authority_sha256,
                at=args.at,
            )
            receipt = verify_verified_runner_consumption_receipt(
                _load_model(
                    args.consumption_receipt, VerifiedRunnerConsumptionReceipt
                ),
                verified,
                trust_store=runner_trust,
                policy=policy,
                authority_pins=pins,
                expected_authority_sha256=args.expected_authority_sha256,
                at=args.at,
            )
            summary = build_repository_verification_from_verified_runner_evidence(
                verified,
                consumption_receipt=receipt,
            )
            _write_new_model(args.output, summary)
            _emit(
                {
                    "authority": "none",
                    "bundle_sha256": verified.bundle_sha256,
                    "check_count": len(verified.records),
                    "mode": "pure-verification-only",
                    "output": str(args.output.resolve()),
                    "status": "verified",
                }
            )
            return 0

        if args.command == "derive-operations-activity":
            summary = derive_operations_activity(
                _load_model(args.batch, OperationsActivityBatch),
                _load_model(args.cost_policy, OperationalCostPolicy),
                gross_settled_revenue_jpy=args.gross_settled_revenue_jpy,
                at=args.at,
            )
            _write_new_model(args.output, summary)
            _emit(
                {
                    "authority": "none",
                    "mode": "credential-free-derivation",
                    "net_operating_profit_jpy": (
                        summary.operating_tco.net_operating_profit_jpy
                    ),
                    "output": str(args.output.resolve()),
                    "status": "derived",
                    "summary_sha256": summary.summary_sha256,
                    "target_achieved": summary.operating_tco.target_achieved,
                }
            )
            return 0

        if args.command == "init-db":
            repository = SQLitePlanRepository(args.db)
            _emit({"database": str(repository.path.resolve()), "mode": "0600", "status": "ready"})
            return 0

        if args.command == "validate-plan":
            plan = _load_plan(args.plan)
            _emit(_plan_status(plan, at=now))
            return 0

        if args.command == "validate-keyword-universe":
            rows = load_keyword_universe(
                args.universe,
                minimum_keywords=args.minimum_keywords,
                maximum_keywords=args.maximum_keywords,
            )
            _emit(summarize_keyword_universe(rows).as_dict())
            return 0

        if args.command == "prepare-kwfinder-upload":
            rows = load_keyword_universe(
                args.universe, minimum_keywords=1, maximum_keywords=200
            )
            if args.start_index < 0 or args.start_index >= len(rows):
                raise ValueError("start-index must select a row in the frozen slate")
            if args.limit is not None and args.limit <= 0:
                raise ValueError("limit must be positive")
            selected = rows[
                args.start_index:
                None if args.limit is None else args.start_index + args.limit
            ]
            if args.limit is not None and len(selected) != args.limit:
                raise ValueError("requested slice extends beyond the frozen slate")
            content = "\n".join(row.query for row in selected) + "\n"
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            _emit(
                {
                    "count": len(selected),
                    "output": str(args.output.resolve()),
                    "query_values_emitted_to_stdout": False,
                    "source_sha256": summarize_keyword_universe(rows).sha256,
                    "start_index": args.start_index,
                    "status": "ready_for_human_kwfinder_input",
                }
            )
            return 0

        if args.command == "validate-mangools-export":
            rows = load_keyword_universe(args.universe, minimum_keywords=150, maximum_keywords=150)
            universe_summary = summarize_keyword_universe(rows)
            summary = validate_mangools_human_export(
                args.csv,
                universe_rows=rows,
                universe_sha256=universe_summary.sha256,
                observed_on=args.observed_on,
                next_review_on=args.next_review_on,
                monthly_revenue_target_jpy=args.monthly_revenue_target_jpy,
                assumed_confirmed_epc_jpy=args.assumed_confirmed_epc_jpy,
                assumed_outbound_ctr=args.assumed_outbound_ctr,
            )
            _emit(summary.model_dump(mode="json"))
            return 0

        if args.command == "validate-mangools-slate-export":
            rows = load_keyword_universe(
                args.universe, minimum_keywords=1, maximum_keywords=200
            )
            universe_summary = summarize_keyword_universe(rows)
            summary = validate_mangools_human_export_batches(
                tuple(args.csv),
                slate_id=args.slate_id,
                universe_rows=rows,
                universe_sha256=universe_summary.sha256,
                observed_on=args.observed_on,
                next_review_on=args.next_review_on,
                monthly_revenue_target_jpy=args.monthly_revenue_target_jpy,
                assumed_confirmed_epc_jpy=args.assumed_confirmed_epc_jpy,
                assumed_outbound_ctr=args.assumed_outbound_ctr,
            )
            if args.output is None:
                _emit(summary.model_dump(mode="json"))
                return 0

            repository_root = args.repository_root.resolve()
            csv_paths = tuple(path.resolve() for path in args.csv)
            if any(path.is_relative_to(repository_root) for path in csv_paths):
                raise ValueError("raw Mangools CSV must stay outside the repository")
            safe_summary_dir = (
                repository_root / "outputs" / "demand-safe-summaries"
            ).resolve()
            output = args.output.resolve()
            if output.parent != safe_summary_dir:
                raise ValueError(
                    "safe-summary output must use outputs/demand-safe-summaries"
                )
            expected_name = f"{args.slate_id}-{args.observed_on.isoformat()}.json"
            if output.name != expected_name:
                raise ValueError(
                    f"safe-summary output filename must be {expected_name}"
                )
            if summary.raw_saved or summary.query_values_saved:
                raise ValueError("safe-summary unexpectedly retains raw or query values")
            if summary.rejected_volume_count:
                raise ValueError("rejected rows prevent safe-summary saving")
            output.parent.mkdir(parents=True, exist_ok=True)
            _write_new_model(output, summary)
            _emit(
                {
                    "keyword_count": summary.keyword_count,
                    "known_monthly_search_volume_total": (
                        summary.known_monthly_search_volume_total
                    ),
                    "known_volume_count": summary.known_volume_count,
                    "no_data_rate": summary.no_data_rate,
                    "no_data_volume_count": summary.no_data_volume_count,
                    "output": str(output.relative_to(repository_root)),
                    "query_values_saved": False,
                    "raw_saved": False,
                    "rejected_volume_count": summary.rejected_volume_count,
                    "slate_id": summary.slate_id,
                    "status": "safe_summary_saved",
                    "top_2_known_volume_share": summary.top_2_known_volume_share,
                    "top_5_known_volume_share": summary.top_5_known_volume_share,
                }
            )
            return 0

        if args.command == "validate-mangools-expansion-set":
            specifications = (
                ("crm", args.crm, "jp_ja_keyword_slate_v2_crm.csv"),
                ("forms", args.forms, "jp_ja_keyword_slate_v2_forms.csv"),
                (
                    "email_marketing",
                    args.email_marketing,
                    "jp_ja_keyword_slate_v2_email_marketing.csv",
                ),
                (
                    "seo_tools_v2_extension",
                    args.seo_tools_v2_extension,
                    "jp_ja_keyword_universe_v2_seo_extension.csv",
                ),
            )
            summaries = []
            for slate_id, csv_path, universe_name in specifications:
                rows = load_keyword_universe(
                    args.slates_dir / universe_name,
                    minimum_keywords=1,
                    maximum_keywords=200,
                )
                summaries.append(
                    validate_mangools_human_export_batches(
                        (csv_path,),
                        slate_id=slate_id,
                        universe_rows=rows,
                        universe_sha256=summarize_keyword_universe(rows).sha256,
                        observed_on=args.observed_on,
                        next_review_on=args.next_review_on,
                        monthly_revenue_target_jpy=args.monthly_revenue_target_jpy,
                        assumed_confirmed_epc_jpy=args.assumed_confirmed_epc_jpy,
                        assumed_outbound_ctr=args.assumed_outbound_ctr,
                    )
                )
            summary_set = build_mangools_expansion_set_safe_summary(tuple(summaries))
            _emit(summary_set.model_dump(mode="json"))
            return 0

        if args.command == "merge-server-candidates":
            candidates = tuple(
                _load_model(path, CategoryExpansionInput)
                for path in args.candidate
            )
            if any(
                candidate.category_id is not ExpansionCategory.SERVERS
                for candidate in candidates
            ):
                raise ValueError("merge-server-candidates accepts servers inputs only")
            merged = merge_category_expansion_inputs(candidates)
            _write_new_model(args.output, merged)
            output_bytes = args.output.read_bytes()
            identities = {
                (field.vendor_id, field.plan_id)
                for field in merged.numeric_fields
            }
            _emit(
                {
                    "authority": "none",
                    "category_id": merged.category_id.value,
                    "condition_record_count": len(merged.server_conditions),
                    "field_count": len(merged.numeric_fields),
                    "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                    "status": "candidate_only_merged",
                    "values_emitted_to_stdout": False,
                    "vendor_plan_count": len(identities),
                }
            )
            return 0

        if args.command == "store-plan":
            plan = _load_plan(args.plan)
            deadline = _earliest_history_delete_after(plan)
            if deadline <= now:
                raise PermissionError(
                    "history retention deadline has passed; do not store this snapshot"
                )
            repository = SQLitePlanRepository(args.db)
            repository.insert(plan)
            _emit(
                {
                    "database": str(repository.path.resolve()),
                    "snapshot_id": str(plan.snapshot_id),
                    "earliest_history_delete_after": deadline.isoformat(),
                    "retention_action": (
                        "Keep one retention cohort per DB; rotate and delete or "
                        "crypto-erase the whole DB by this deadline after Human approval."
                    ),
                    "status": "stored",
                }
            )
            return 0

        if args.command == "list-plans":
            repository = SQLitePlanRepository(args.db)
            plans = repository.list(
                vendor_slug=args.vendor_slug,
                plan_slug=args.plan_slug,
                limit=args.limit,
            )
            _emit(
                [
                    {
                        "snapshot_id": str(plan.snapshot_id),
                        "vendor_slug": plan.vendor_slug,
                        "plan_slug": plan.plan_slug,
                        "captured_at": plan.captured_at.isoformat(),
                        "schema_version": plan.schema_version,
                    }
                    for plan in plans
                ]
            )
            return 0

        if args.command == "calculate-tco":
            plan = _load_plan(args.plan)
            denied = _denied_fields(plan, PolicyAction.DERIVE, at=now)
            if denied:
                raise PermissionError(
                    "derivation is not currently approved for fields: " + ", ".join(denied)
                )
            scenario = constant_usage_scenario(
                months=args.months,
                seats=args.seats,
                monthly_usage=args.monthly_usage,
                usage_unit=args.usage_unit,
            )
            result = calculate_vendor_plan_tco(
                plan,
                scenario,
                selected_addon_codes=args.addon,
            )
            _emit(asdict(result))
            return 0

        if args.command == "render-preview":
            page = _load_preview(args.page)
            rendered = render_preview(page, at=now)
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(rendered)
            _emit(
                {
                    "output": str(args.output.resolve()),
                    "robots": "noindex,nofollow,noarchive",
                    "status": "rendered",
                }
            )
            return 0

        if args.command == "evaluate-readiness":
            dossier = _load_dossier(args.dossier)
            evaluation = evaluate_business_dossier(dossier, at=now)
            _emit({"authority": "unsigned_diagnostic", **asdict(evaluation)})
            return 0

        if args.command == "assemble-readiness":
            dossier = build_business_dossier(
                plans=tuple(_load_plan(path) for path in args.plan),
                affiliate_decisions=_load_model(
                    args.affiliate_decisions, AffiliateDecisionBatch
                ).decisions,
                property_domain=args.property_domain,
                demand=_load_model(args.demand_evidence, DemandEvidence),
                cohort=_load_model(args.cohort_evidence, CohortEvidence),
                operations=_load_model(
                    args.operations_evidence, OperationsEvidence
                ),
                at=args.at or now,
            )
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(dossier.model_dump_json(indent=2))
                destination.write("\n")
            _emit(
                {
                    "authority": "unsigned_diagnostic",
                    "evidence_version": dossier.evidence_version,
                    "output": str(args.output.resolve()),
                    "schema_version": dossier.schema_version,
                    "status": "assembled",
                }
            )
            return 0

        if args.command == "assemble-signed-readiness":
            bundle = assemble_measurement_bound_dossier(
                _load_model(args.measurement_report, MeasurementIntegrityReport),
                _load_model(args.measurement_policy, MeasurementPolicy),
                _load_model(args.measurement_trust_store, MeasurementTrustStore),
                _load_model(args.authority_pins, MeasurementAuthorityPins),
                plans=tuple(_load_plan(path) for path in args.plan),
                affiliate_decisions=_load_model(
                    args.affiliate_decisions, AffiliateDecisionBatch
                ).decisions,
                property_domain=args.property_domain,
                at=now,
            )
            _write_new_model(args.output, bundle)
            _emit(
                {
                    "authority": "signed_p12_measurement",
                    "dossier_sha256": bundle.dossier_sha256,
                    "output": str(args.output.resolve()),
                    "status": "assembled",
                }
            )
            return 0

        if args.command == "evaluate-signed-readiness":
            bundle = _load_model(args.bundle, MeasurementBoundDossier)
            policy = _load_model(args.measurement_policy, MeasurementPolicy)
            trust_store = _load_model(
                args.measurement_trust_store, MeasurementTrustStore
            )
            pins = _load_model(args.authority_pins, MeasurementAuthorityPins)
            if not verify_measurement_bound_dossier(
                bundle, policy, trust_store, pins, at=now
            ):
                raise ValueError("signed measurement-bound dossier is not current")
            evaluation = evaluate_business_dossier(bundle.dossier, at=now)
            _emit({"authority": "signed_p12_measurement", **asdict(evaluation)})
            return 0

        if args.command == "aggregate-demand":
            evidence = build_demand_evidence(
                _load_model(args.summary, DemandSummaryBatch), at=now
            )
            _write_new_model(args.output, evidence)
            _emit(
                {
                    "authority": "unsigned_diagnostic",
                    "evidence_version": evidence.evidence_version,
                    "output": str(args.output.resolve()),
                    "status": "aggregated",
                    "type": "demand",
                }
            )
            return 0

        if args.command == "aggregate-cohort":
            evidence = build_cohort_evidence(
                _load_model(args.summary, CohortSummaryBatch), at=now
            )
            _write_new_model(args.output, evidence)
            _emit(
                {
                    "authority": "unsigned_diagnostic",
                    "evidence_version": evidence.evidence_version,
                    "output": str(args.output.resolve()),
                    "status": "aggregated",
                    "type": "cohort",
                }
            )
            return 0

        if args.command == "aggregate-operations":
            evidence = build_operations_evidence(
                _load_model(args.summary, OperationsSummaryBatch), at=now
            )
            _write_new_model(args.output, evidence)
            _emit(
                {
                    "authority": "unsigned_diagnostic",
                    "evidence_version": evidence.evidence_version,
                    "output": str(args.output.resolve()),
                    "status": "aggregated",
                    "type": "operations",
                }
            )
            return 0

        if args.command == "evaluate-gold-set":
            report = evaluate_goldset(
                _load_model(args.gold_set, HumanGoldSet),
                _load_model(args.candidates, CandidateBatch),
                at=args.at or now,
            )
            _emit(report.model_dump(mode="json"))
            return 0

        if args.command == "evaluate-editorial-package":
            report = evaluate_editorial_package(
                _load_model(args.package, EditorialPackage), at=args.at
            )
            _emit({"authority": "none", **report.model_dump(mode="json")})
            return (
                0
                if report.decision is EditorialDecision.READY_FOR_HUMAN_REVIEW
                else 3
            )

        if args.command == "build-growth-scorecard":
            report = build_kpi_scorecard(
                _load_model(args.feedback, FeedbackBatch),
                _load_model(args.operations, OperationsKpiInput),
                at=args.at,
            )
            _write_new_model(args.output, report)
            _emit(
                {
                    "authority": "none",
                    "evidence_mode": "observed",
                    "metric_version": report.metric_version,
                    "output": str(args.output.resolve()),
                    "status": "derived",
                }
            )
            return 0

        if args.command == "rank-growth-initiatives":
            report = build_policy_memo(
                _load_model(args.portfolio, InitiativePortfolio)
            )
            _emit({"authority": "none", **report.model_dump(mode="json")})
            return 0 if report.recommended_proposal_id_sha256 is not None else 3

        if args.command == "evaluate-cta-health":
            report = evaluate_cta_health(
                _load_model(args.input, CtaHealthInput), at=args.at
            )
            _emit({"authority": "none", **report.model_dump(mode="json")})
            return 0 if report.decision is CtaDecision.ENABLED else 3

        if args.command == "evaluate-growth-activation":
            report = evaluate_conditional_activation(
                _load_model(args.input, ConditionalActivationInput), at=args.at
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision is ActivationDecision.READY_FOR_HUMAN_GATE
                else 3
            )

        if args.command == "evaluate-model-route":
            report = evaluate_model_route(
                _load_model(args.request, ModelRoutingRequest),
                _load_model(args.policy, ModelRouterPolicy),
                at=args.at,
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision is ModelRouteDecision.READY_FOR_CONTROLLER_GATE
                else 3
            )

        if args.command == "evaluate-initial-learning-quality":
            report = evaluate_initial_learning_quality(
                _load_model(args.bundle, InitialLearningQualityBundle),
                _load_model(args.policy, InitialLearningQualityPolicy),
                _load_model(args.trust_store, InitialLearningTrustStore),
                expected_authority_sha256=args.expected_authority_sha256,
                at=args.at,
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision
                is InitialLearningQualityDecision.READY_FOR_HUMAN_REVIEW
                else 3
            )

        if args.command == "evaluate-production-readiness":
            report = evaluate_production_integration_readiness(
                _load_model(args.bundle, ProductionIntegrationEvidenceBundle),
                _load_model(args.plan, ProductionIntegrationPlan),
                _load_model(args.policy, ProductionIntegrationPolicy),
                _load_model(args.trust_store, ProductionIntegrationTrustStore),
                at=args.at,
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision
                is ProductionReadinessDecision.READY_FOR_HUMAN_GATE
                else 3
            )

        if args.command == "evaluate-production-reconciliation":
            report = evaluate_production_reconciliation(
                _load_model(args.facts, ProductionReconciliationFacts), at=args.at
            )
            _emit(report.model_dump(mode="json"))
            return 3

        if args.command == "evaluate-launch-handoff":
            report = evaluate_launch_handoff(
                _load_model(args.bundle, LaunchHandoffBundle),
                _load_model(args.plan, LaunchHandoffPlan),
                _load_model(args.policy, LaunchHandoffPolicy),
                _load_model(args.trust_store, LaunchHandoffTrustStore),
                at=args.at,
                expected_repository_acceptance_authority_pins_sha256=(
                    args.expected_repository_acceptance_authority_pins_sha256
                ),
                expected_launch_handoff_authority_sha256=(
                    args.expected_launch_handoff_authority_sha256
                ),
                launch_semantic_authority_pins=(
                    None
                    if args.launch_semantic_authority_pins is None
                    else _load_model(
                        args.launch_semantic_authority_pins,
                        LaunchSemanticAuthorityPins,
                    )
                ),
                expected_launch_semantic_authority_pins_sha256=(
                    args.expected_launch_semantic_authority_pins_sha256
                ),
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision
                is LaunchHandoffDecision.READY_FOR_FINAL_HUMAN_REVIEW
                else 3
            )

        if args.command == "evaluate-traction":
            bundle = _load_model(args.bundle, TractionEvaluationBundle)
            report = evaluate_traction(
                bundle.observations,
                plan=_load_model(args.plan, SignedTractionPlan),
                policy=_load_model(args.policy, TractionPolicy),
                trust_store=_load_model(args.trust_store, TractionTrustStore),
                authority_pins=_load_model(
                    args.authority_pins, TractionAuthorityPins
                ),
                settlement_evidence=bundle.settlement_evidence,
                settlement_policy=_load_model(
                    args.settlement_policy, SettlementAmendmentPolicy
                ),
                settlement_trust_store=_load_model(
                    args.settlement_trust_store, SettlementAmendmentTrustStore
                ),
                at=args.at,
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision is TractionDecision.READY_FOR_SCALE_REVIEW
                else 3
            )

        if args.command == "build-local-acceptance-manifest":
            if (args.integration_attestation is None) is not (
                args.tco_qa_attestation is None
            ):
                raise ValueError(
                    "integration and TCO/QA attestations must be supplied together"
                )
            manifest = build_repository_candidate_manifest(
                args.repo_root,
                _load_model(
                    args.verification_evidence,
                    RepositoryVerificationEvidenceBundle,
                ),
                candidate_id=args.candidate_id,
                assembled_at=args.assembled_at,
                expires_at=args.expires_at,
                integration_verification=(
                    None
                    if args.integration_attestation is None
                    else _load_model(
                        args.integration_attestation,
                        RepositoryVerificationAttestation,
                    )
                ),
                tco_qa_verification=(
                    None
                    if args.tco_qa_attestation is None
                    else _load_model(
                        args.tco_qa_attestation,
                        RepositoryVerificationAttestation,
                    )
                ),
            )
            _write_new_model(args.output, manifest)
            _emit(
                {
                    "authority": "none",
                    "decision": "pending",
                    "file_count": len(manifest.files),
                    "manifest_sha256": manifest.manifest_sha256,
                    "output": str(args.output.resolve()),
                    "tree_sha256": manifest.tree_sha256,
                }
            )
            return 3

        if args.command == "evaluate-local-acceptance":
            if (args.policy is None) is not (args.trust_store is None):
                raise ValueError(
                    "policy and trust-store must be supplied together"
                )
            if (args.receipt is None) is not (args.authority_pins is None):
                raise ValueError(
                    "receipt and authority-pins must be supplied together"
                )
            if args.receipt is not None and (
                args.policy is None
                or args.expected_authority_pins_sha256 is None
            ):
                raise ValueError(
                    "signed receipt evaluation requires policy, trust-store, and an expected authority-pins root"
                )
            if args.receipt_chain is not None and args.receipt is None:
                raise ValueError("receipt-chain requires a current receipt")
            if (
                args.policy is not None
                and args.receipt is None
                and args.expected_verification_authority_sha256 is None
            ):
                raise ValueError(
                    "pre-Human verification requires an expected verification-authority root"
                )
            if (
                args.policy is None
                and args.expected_verification_authority_sha256 is not None
            ):
                raise ValueError(
                    "expected verification-authority root requires policy and trust-store"
                )
            report = evaluate_repository_acceptance(
                _load_model(args.manifest, RepositoryCandidateManifest),
                args.repo_root,
                at=args.at,
                receipt=(
                    None
                    if args.receipt is None
                    else _load_model(args.receipt, HumanRepositoryAcceptance)
                ),
                policy=(
                    None
                    if args.policy is None
                    else _load_model(args.policy, RepositoryAcceptancePolicy)
                ),
                trust_store=(
                    None
                    if args.trust_store is None
                    else _load_model(
                        args.trust_store, RepositoryAcceptanceTrustStore
                    )
                ),
                authority_pins=(
                    None
                    if args.authority_pins is None
                    else _load_model(
                        args.authority_pins,
                        RepositoryAcceptanceAuthorityPins,
                    )
                ),
                expected_authority_pins_sha256=(
                    args.expected_authority_pins_sha256
                ),
                expected_verification_authority_sha256=(
                    args.expected_verification_authority_sha256
                ),
                receipt_chain=(
                    ()
                    if args.receipt_chain is None
                    else _load_model(
                        args.receipt_chain,
                        RepositoryAcceptanceReceiptChain,
                    ).receipts
                ),
            )
            _emit(report.model_dump(mode="json"))
            return (
                0
                if report.decision is RepositoryAcceptanceDecision.ACCEPTED
                else 3
            )

        raise RuntimeError(f"unsupported command: {args.command}")
    except ValidationError as exc:
        print(f"error: {_validation_error_message(exc)}", file=sys.stderr)
        return 2
    except (KeyError, OSError, PermissionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
