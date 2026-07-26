"""Offline Human gold-set comparison and hash-only quarantine reporting.

No network, persistence, parser execution, or release action occurs here. Gold
labels contain only value/source/receipt hashes. Candidate values are evaluated
through the existing VendorPlan contract and canonical TCO implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from .models import CurrencyCode, PolicyAction, Sha256, StrictModel, VendorPlan
from .tco import calculate_vendor_plan_tco, constant_usage_scenario


class QuarantineReason(str, Enum):
    PARTIAL_GOLDSET = "partial_goldset"
    GOLDSET_NOT_CURRENT = "goldset_not_current"
    CANDIDATE_NOT_CURRENT = "candidate_not_current"
    PARSE_FAILURE = "parse_failure"
    PARSER_FAILURE_RATE = "parser_failure_rate"
    MISSING_PLAN = "missing_plan"
    EXTRA_PLAN = "extra_plan"
    MISSING_FIELD = "missing_field"
    EXTRA_FIELD = "extra_field"
    FIELD_MISMATCH = "field_mismatch"
    SOURCE_MISMATCH = "source_mismatch"
    RIGHTS_INVALID = "rights_invalid"
    LABEL_NOT_CURRENT = "label_not_current"
    TCO_MISMATCH = "tco_mismatch"
    TCO_ERROR = "tco_error"


class ParseFailureCode(str, Enum):
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    SOURCE_CONFLICT = "source_conflict"
    RIGHTS_INVALID = "rights_invalid"


class GoldFieldLabel(StrictModel):
    label_id_sha256: Sha256
    field_path: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    expected_value_sha256: Sha256
    evidence_source_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    human_label_receipt_sha256: Sha256
    labeled_at: datetime
    expires_at: datetime

    @field_validator("labeled_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "label timestamp")
        return value

    @field_validator("evidence_source_sha256s")
    @classmethod
    def canonicalize_source_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_label(self) -> Self:
        if self.expires_at <= self.labeled_at:
            raise ValueError("label expires_at must be later than labeled_at")
        if len(self.evidence_source_sha256s) != len(set(self.evidence_source_sha256s)):
            raise ValueError("label evidence source hashes must be distinct")
        return self


class GoldTcoExpectation(StrictModel):
    scenario_id_sha256: Sha256
    human_label_receipt_sha256: Sha256
    labeled_at: datetime
    expires_at: datetime
    months: Literal[12] = 12
    seats: int = Field(ge=1, le=1_000_000)
    monthly_usage: Decimal = Field(ge=0)
    usage_unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$",
    )
    selected_addon_codes: tuple[str, ...] = ()
    expected_tco_sha256: Sha256
    expected_total_minor: int = Field(ge=0)
    expected_currency: CurrencyCode

    @field_validator("labeled_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "TCO label timestamp")
        return value

    @field_validator("selected_addon_codes")
    @classmethod
    def validate_addons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("selected add-on codes must be distinct")
        for value in values:
            if (
                not value
                or len(value) > 80
                or re.fullmatch(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$", value) is None
            ):
                raise ValueError("selected add-on code must be a lowercase stable identifier")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_label_window(self) -> Self:
        if self.expires_at <= self.labeled_at:
            raise ValueError("TCO label expires_at must be later than labeled_at")
        return self


class GoldPlan(StrictModel):
    vendor_slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    plan_slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    labels: tuple[GoldFieldLabel, ...] = Field(min_length=1)
    tco_expectations: tuple[GoldTcoExpectation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicates(self) -> Self:
        _require_unique((label.label_id_sha256 for label in self.labels), "label IDs")
        _require_unique((label.field_path for label in self.labels), "label field paths")
        _require_unique(
            (item.scenario_id_sha256 for item in self.tco_expectations),
            "TCO scenario IDs",
        )
        return self


class HumanGoldSet(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    goldset_id_sha256: Sha256
    rights_bundle_sha256: Sha256
    created_at: datetime
    expires_at: datetime
    plans: tuple[GoldPlan, ...] = Field(min_length=1)

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "gold-set timestamp")
        return value

    @model_validator(mode="after")
    def validate_goldset(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("gold-set expires_at must be later than created_at")
        _require_unique(
            ((plan.vendor_slug, plan.plan_slug) for plan in self.plans),
            "gold plan keys",
        )
        label_ids = [label.label_id_sha256 for plan in self.plans for label in plan.labels]
        _require_unique(label_ids, "global label IDs")
        if any(label.labeled_at > self.created_at for plan in self.plans for label in plan.labels):
            raise ValueError("labels cannot be created after gold-set created_at")
        if any(
            expectation.labeled_at > self.created_at
            for plan in self.plans
            for expectation in plan.tco_expectations
        ):
            raise ValueError("TCO labels cannot be created after gold-set created_at")
        return self


class CandidatePlan(StrictModel):
    input_id_sha256: Sha256
    plan_sha256: Sha256
    plan: VendorPlan

    @model_validator(mode="after")
    def verify_plan_hash(self) -> Self:
        if self.plan_sha256 != hash_vendor_plan(self.plan):
            raise ValueError("plan_sha256 does not match canonical VendorPlan")
        return self


class CandidateParseFailure(StrictModel):
    input_id_sha256: Sha256
    expected_vendor_slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    expected_plan_slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$",
    )
    code: ParseFailureCode
    error_sha256: Sha256


class CandidateBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_receipt_sha256: Sha256
    parser_sha256: Sha256
    parser_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9]+(?:[A-Za-z0-9._+-]*[A-Za-z0-9])?$",
    )
    captured_at: datetime
    expires_at: datetime
    plans: tuple[CandidatePlan, ...]
    failures: tuple[CandidateParseFailure, ...]

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "candidate timestamp")
        return value

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        if self.expires_at <= self.captured_at:
            raise ValueError("candidate expires_at must be later than captured_at")
        if not self.plans and not self.failures:
            raise ValueError("candidate batch must contain a plan or parse failure")
        input_ids = [item.input_id_sha256 for item in self.plans] + [
            item.input_id_sha256 for item in self.failures
        ]
        _require_unique(input_ids, "candidate input IDs")
        _require_unique(
            ((item.plan.vendor_slug, item.plan.plan_slug) for item in self.plans),
            "candidate plan keys",
        )
        return self


class QuarantineItem(StrictModel):
    reason: QuarantineReason
    subject_sha256: Sha256
    expected_sha256: Sha256 | None = None
    actual_sha256: Sha256 | None = None


class GoldSetReport(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    goldset_id_sha256: Sha256
    goldset_content_sha256: Sha256
    rights_bundle_sha256: Sha256
    candidate_batch_sha256: Sha256
    evaluated_at: datetime
    expires_at: datetime
    gold_vendor_count: int = Field(ge=0)
    gold_plan_count: int = Field(ge=0)
    gold_label_count: int = Field(ge=0)
    candidate_plan_count: int = Field(ge=0)
    parse_failure_count: int = Field(ge=0)
    parse_failure_rate: Decimal = Field(ge=0, le=1)
    parser_failure_stop: bool
    full_goldset_coverage: bool
    ready_for_release: bool
    quarantines: tuple[QuarantineItem, ...]
    report_sha256: Sha256

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value, "report timestamp")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        keys = [_quarantine_sort_key(item) for item in self.quarantines]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("quarantine rows must be unique and canonically sorted")
        expected_ready = (
            self.full_goldset_coverage
            and not self.parser_failure_stop
            and not self.quarantines
        )
        if self.ready_for_release != expected_ready:
            raise ValueError("ready_for_release is inconsistent with report gates")
        if self.report_sha256 != _report_hash(self):
            raise ValueError("report_sha256 does not match canonical report")
        return self


def hash_vendor_plan(plan: VendorPlan) -> str:
    """Return the canonical full-plan digest expected by CandidatePlan."""

    if type(plan) is not VendorPlan:
        raise TypeError("plan must be VendorPlan")
    return _canonical_sha256(plan.model_dump(mode="json"))


def hash_rights_manifest(plans: tuple[VendorPlan, ...] | list[VendorPlan]) -> str:
    """Hash approved policy identity independently of observation snapshots.

    Snapshot IDs, plan capture/effective timestamps, EvidencePointer retrieval
    timestamps, excerpts, and source-content hashes are deliberately excluded.
    SourcePolicy identity, source URL, decisions, reviewer, basis, retention,
    and review window remain bound to the Human rights receipt.
    """

    if not plans:
        raise ValueError("rights manifest requires at least one VendorPlan")
    keys = [(plan.vendor_slug, plan.plan_slug) for plan in plans]
    _require_unique(keys, "rights manifest plan keys")
    manifest_plans: list[dict[str, object]] = []
    for plan in sorted(plans, key=lambda item: (item.vendor_slug, item.plan_slug)):
        fields: list[dict[str, object]] = []
        for evidence in sorted(plan.field_evidence, key=lambda item: item.field):
            policies = [
                pointer.source_policy.model_dump(mode="json")
                for pointer in evidence.pointers
            ]
            unique_policies = {
                _canonical_sha256(policy): policy for policy in policies
            }
            canonical_policies = [
                unique_policies[digest] for digest in sorted(unique_policies)
            ]
            fields.append({"field": evidence.field, "policies": canonical_policies})
        manifest_plans.append(
            {
                "vendor_slug": plan.vendor_slug,
                "plan_slug": plan.plan_slug,
                "fields": fields,
            }
        )
    return _canonical_sha256({"policy_manifest_version": "1.0", "plans": manifest_plans})


def hash_material_field_value(plan: VendorPlan, field_path: str) -> str:
    """Hash one material value without exposing it in the gold-set contract."""

    if field_path not in plan.material_fields():
        raise KeyError(f"not a material VendorPlan field: {field_path}")
    value = _resolve_material_field(plan, field_path)
    return _canonical_sha256(_canonical_value(value))


def hash_tco_result(result: object) -> str:
    """Hash the entire canonical TCO result, including every line item."""

    try:
        payload = asdict(result)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("result must be a dataclass TCO result") from exc
    return _canonical_sha256(_canonical_value(payload))


def evaluate_goldset(
    goldset: HumanGoldSet,
    candidates: CandidateBatch,
    *,
    at: datetime,
) -> GoldSetReport:
    """Compare one offline candidate batch and emit only hash-addressed faults."""

    if type(goldset) is not HumanGoldSet or type(candidates) is not CandidateBatch:
        raise TypeError("evaluate_goldset requires HumanGoldSet and CandidateBatch")
    _require_utc(at, "evaluation timestamp")

    gold_by_key = {(item.vendor_slug, item.plan_slug): item for item in goldset.plans}
    candidate_by_key = {
        (item.plan.vendor_slug, item.plan.plan_slug): item for item in candidates.plans
    }
    quarantines: list[QuarantineItem] = []
    coverage = _full_coverage(goldset)
    if not coverage:
        quarantines.append(
            _fault(
                QuarantineReason.PARTIAL_GOLDSET,
                ("goldset", goldset.goldset_id_sha256),
                expected=("vendors", ">=3", "plans_per_vendor", ">=6", "labels", "60-150"),
                actual=_coverage_payload(goldset),
            )
        )
    if goldset.created_at > at or goldset.expires_at <= at:
        quarantines.append(
            _fault(
                QuarantineReason.GOLDSET_NOT_CURRENT,
                ("goldset", goldset.goldset_id_sha256),
                expected=("current_at", _utc_text(at)),
                actual=("created", _utc_text(goldset.created_at), "expires", _utc_text(goldset.expires_at)),
            )
        )
    if candidates.captured_at > at or candidates.expires_at <= at:
        quarantines.append(
            _fault(
                QuarantineReason.CANDIDATE_NOT_CURRENT,
                ("candidate", candidates.source_receipt_sha256),
                expected=("current_at", _utc_text(at)),
                actual=("captured", _utc_text(candidates.captured_at), "expires", _utc_text(candidates.expires_at)),
            )
        )

    candidate_plans = tuple(item.plan for item in candidates.plans)
    try:
        rights_manifest_sha256 = hash_rights_manifest(candidate_plans)
        if rights_manifest_sha256 != goldset.rights_bundle_sha256:
            quarantines.append(
                _fault(
                    QuarantineReason.RIGHTS_INVALID,
                    ("rights_bundle", goldset.goldset_id_sha256),
                    expected=goldset.rights_bundle_sha256,
                    actual=rights_manifest_sha256,
                )
            )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        quarantines.append(
            _fault(
                QuarantineReason.RIGHTS_INVALID,
                ("rights_bundle", goldset.goldset_id_sha256),
                expected=goldset.rights_bundle_sha256,
                actual=(type(exc).__name__,),
            )
        )

    attempt_count = len(candidates.plans) + len(candidates.failures)
    failure_rate = Decimal(len(candidates.failures)) / Decimal(attempt_count)
    failure_stop = failure_rate > Decimal("0.20")
    for failure in candidates.failures:
        quarantines.append(
            _fault(
                QuarantineReason.PARSE_FAILURE,
                (failure.expected_vendor_slug, failure.expected_plan_slug, failure.input_id_sha256),
                actual=failure.error_sha256,
            )
        )
    if failure_stop:
        quarantines.append(
            _fault(
                QuarantineReason.PARSER_FAILURE_RATE,
                ("parser", candidates.parser_sha256),
                expected=Decimal("0.20"),
                actual=failure_rate,
            )
        )

    for key in sorted(gold_by_key.keys() - candidate_by_key.keys()):
        quarantines.append(
            _fault(QuarantineReason.MISSING_PLAN, key, expected=_gold_plan_hash(gold_by_key[key]))
        )
    for key in sorted(candidate_by_key.keys() - gold_by_key.keys()):
        quarantines.append(
            _fault(QuarantineReason.EXTRA_PLAN, key, actual=candidate_by_key[key].plan_sha256)
        )
    for key in sorted(gold_by_key.keys() & candidate_by_key.keys()):
        plan = candidate_by_key[key].plan
        if plan.captured_at > at or plan.effective_at > at:
            quarantines.append(
                _fault(
                    QuarantineReason.CANDIDATE_NOT_CURRENT,
                    key,
                    expected=("not_future_at", _utc_text(at)),
                    actual=("captured", _utc_text(plan.captured_at), "effective", _utc_text(plan.effective_at)),
                )
            )
        _compare_plan(gold_by_key[key], plan, at, quarantines)

    unique = {_quarantine_sort_key(item): item for item in quarantines}
    canonical_quarantines = tuple(unique[key] for key in sorted(unique))
    report_values: dict[str, Any] = {
        "goldset_id_sha256": goldset.goldset_id_sha256,
        "goldset_content_sha256": _goldset_content_hash(goldset),
        "rights_bundle_sha256": goldset.rights_bundle_sha256,
        "candidate_batch_sha256": _candidate_batch_hash(candidates),
        "evaluated_at": at,
        "expires_at": _report_expiry(goldset, candidates),
        "gold_vendor_count": len({plan.vendor_slug for plan in goldset.plans}),
        "gold_plan_count": len(goldset.plans),
        "gold_label_count": sum(len(plan.labels) for plan in goldset.plans),
        "candidate_plan_count": len(candidates.plans),
        "parse_failure_count": len(candidates.failures),
        "parse_failure_rate": failure_rate,
        "parser_failure_stop": failure_stop,
        "full_goldset_coverage": coverage,
        "ready_for_release": coverage and not failure_stop and not canonical_quarantines,
        "quarantines": canonical_quarantines,
    }
    provisional = GoldSetReport.model_construct(**report_values, report_sha256="0" * 64)
    report_values["report_sha256"] = _report_hash(provisional)
    return GoldSetReport(**report_values)


def hash_goldset_report(report: GoldSetReport) -> str:
    """Recalculate a report digest without trusting its readiness flags."""

    if type(report) is not GoldSetReport:
        raise TypeError("report must be GoldSetReport")
    return _report_hash(report)


def _report_expiry(goldset: HumanGoldSet, candidates: CandidateBatch) -> datetime:
    deadlines = [goldset.expires_at, candidates.expires_at]
    for gold_plan in goldset.plans:
        deadlines.extend(label.expires_at for label in gold_plan.labels)
        deadlines.extend(item.expires_at for item in gold_plan.tco_expectations)
    for candidate in candidates.plans:
        for evidence in candidate.plan.field_evidence:
            for pointer in evidence.pointers:
                deadlines.append(pointer.source_policy.review_due_at)
                if pointer.source_policy.retention_days is not None:
                    deadlines.append(
                        candidate.plan.captured_at
                        + timedelta(days=pointer.source_policy.retention_days)
                    )
                if pointer.raw_archive is not None:
                    deadlines.append(pointer.raw_archive.delete_after)
    return min(deadlines)


def _compare_plan(
    gold: GoldPlan,
    plan: VendorPlan,
    at: datetime,
    quarantines: list[QuarantineItem],
) -> None:
    key = (gold.vendor_slug, gold.plan_slug)
    label_by_field = {label.field_path: label for label in gold.labels}
    material = plan.material_fields()
    for field_path in sorted(material - label_by_field.keys()):
        quarantines.append(
            _fault(QuarantineReason.MISSING_FIELD, (*key, field_path), actual=hash_material_field_value(plan, field_path))
        )
    for field_path in sorted(label_by_field.keys() - material):
        quarantines.append(
            _fault(QuarantineReason.EXTRA_FIELD, (*key, field_path), expected=label_by_field[field_path].expected_value_sha256)
        )
    evidence_by_field = {item.field: item for item in plan.field_evidence}
    for field_path in sorted(material & label_by_field.keys()):
        label = label_by_field[field_path]
        subject = (*key, field_path)
        actual_value_hash = hash_material_field_value(plan, field_path)
        if label.expected_value_sha256 != actual_value_hash:
            quarantines.append(
                _fault(QuarantineReason.FIELD_MISMATCH, subject, expected=label.expected_value_sha256, actual=actual_value_hash)
            )
        sources = tuple(sorted({pointer.sha256 for pointer in evidence_by_field[field_path].pointers}))
        expected_sources = tuple(sorted(label.evidence_source_sha256s))
        if sources != expected_sources:
            quarantines.append(
                _fault(QuarantineReason.SOURCE_MISMATCH, subject, expected=expected_sources, actual=sources)
            )
        if label.labeled_at > at or label.expires_at <= at:
            quarantines.append(
                _fault(
                    QuarantineReason.LABEL_NOT_CURRENT,
                    subject,
                    expected=("current_at", _utc_text(at)),
                    actual=("labeled", _utc_text(label.labeled_at), "expires", _utc_text(label.expires_at)),
                )
            )

    denied: list[tuple[str, str]] = []
    future_evidence: list[tuple[str, str]] = []
    for evidence in plan.field_evidence:
        for pointer in evidence.pointers:
            if pointer.retrieved_at > at:
                future_evidence.append((evidence.field, pointer.sha256))
            for action in (
                PolicyAction.DERIVE,
                PolicyAction.PUBLISH,
                PolicyAction.RETAIN_HISTORY,
            ):
                if not pointer.source_policy.permits(action, at=at):
                    denied.append((evidence.field, action.value))
            retention_days = pointer.source_policy.retention_days
            if (
                retention_days is None
                or plan.captured_at + timedelta(days=retention_days) <= at
            ):
                denied.append((evidence.field, "retention_expired"))
    if future_evidence:
        quarantines.append(
            _fault(
                QuarantineReason.CANDIDATE_NOT_CURRENT,
                key,
                expected=("retrieved_at_lte", _utc_text(at)),
                actual=tuple(sorted(future_evidence)),
            )
        )
    if denied:
        quarantines.append(
            _fault(QuarantineReason.RIGHTS_INVALID, key, expected="derive,publish,retain_history", actual=tuple(sorted(denied)))
        )

    for expectation in sorted(gold.tco_expectations, key=lambda item: item.scenario_id_sha256):
        subject = (*key, expectation.scenario_id_sha256)
        if expectation.labeled_at > at or expectation.expires_at <= at:
            quarantines.append(
                _fault(
                    QuarantineReason.LABEL_NOT_CURRENT,
                    subject,
                    expected=("current_at", _utc_text(at)),
                    actual=(
                        "labeled",
                        _utc_text(expectation.labeled_at),
                        "expires",
                        _utc_text(expectation.expires_at),
                    ),
                )
            )
        try:
            scenario = constant_usage_scenario(
                months=expectation.months,
                seats=expectation.seats,
                monthly_usage=expectation.monthly_usage,
                usage_unit=expectation.usage_unit,
            )
            result = calculate_vendor_plan_tco(
                plan,
                scenario,
                selected_addon_codes=expectation.selected_addon_codes,
            )
            actual_hash = hash_tco_result(result)
            if (
                actual_hash != expectation.expected_tco_sha256
                or result.total_minor != expectation.expected_total_minor
                or result.currency != expectation.expected_currency
            ):
                quarantines.append(
                    _fault(
                        QuarantineReason.TCO_MISMATCH,
                        subject,
                        expected=(expectation.expected_tco_sha256, expectation.expected_total_minor, expectation.expected_currency),
                        actual=(actual_hash, result.total_minor, result.currency),
                    )
                )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            quarantines.append(
                _fault(
                    QuarantineReason.TCO_ERROR,
                    subject,
                    expected=expectation.expected_tco_sha256,
                    actual=(type(exc).__name__,),
                )
            )


def _resolve_material_field(plan: VendorPlan, field_path: str) -> object:
    parts = field_path.split(".")
    if parts[0] == "addons":
        if len(parts) != 3:
            raise KeyError(field_path)
        addon = next((item for item in plan.addons if item.code == parts[1]), None)
        if addon is None:
            raise KeyError(field_path)
        return getattr(addon, parts[2])
    value: object = plan
    for part in parts:
        value = getattr(value, part)
    return value


def _full_coverage(goldset: HumanGoldSet) -> bool:
    vendors = {plan.vendor_slug for plan in goldset.plans}
    if len(vendors) < 3:
        return False
    for vendor in vendors:
        plans = [plan for plan in goldset.plans if plan.vendor_slug == vendor]
        labels = sum(len(plan.labels) for plan in plans)
        if len(plans) < 6 or not 60 <= labels <= 150:
            return False
    return True


def _coverage_payload(goldset: HumanGoldSet) -> dict[str, object]:
    vendors = sorted({plan.vendor_slug for plan in goldset.plans})
    return {
        "vendors": len(vendors),
        "plans": len(goldset.plans),
        "labels_by_vendor": {
            vendor: sum(
                len(plan.labels) for plan in goldset.plans if plan.vendor_slug == vendor
            )
            for vendor in vendors
        },
    }


def _gold_plan_hash(plan: GoldPlan) -> str:
    payload = plan.model_dump(mode="json")
    payload["labels"] = sorted(payload["labels"], key=lambda item: item["field_path"])
    payload["tco_expectations"] = sorted(
        payload["tco_expectations"], key=lambda item: item["scenario_id_sha256"]
    )
    return _canonical_sha256(payload)


def _goldset_content_hash(goldset: HumanGoldSet) -> str:
    return _canonical_sha256(
        {
            "schema_version": goldset.schema_version,
            "goldset_id_sha256": goldset.goldset_id_sha256,
            "rights_bundle_sha256": goldset.rights_bundle_sha256,
            "created_at": _utc_text(goldset.created_at),
            "expires_at": _utc_text(goldset.expires_at),
            "plans": [
                _gold_plan_hash(plan)
                for plan in sorted(goldset.plans, key=lambda item: (item.vendor_slug, item.plan_slug))
            ],
        }
    )


def _candidate_batch_hash(batch: CandidateBatch) -> str:
    return _canonical_sha256(
        {
            "schema_version": batch.schema_version,
            "source_receipt_sha256": batch.source_receipt_sha256,
            "parser_sha256": batch.parser_sha256,
            "parser_version": batch.parser_version,
            "captured_at": _utc_text(batch.captured_at),
            "expires_at": _utc_text(batch.expires_at),
            "plans": [
                {"input_id_sha256": item.input_id_sha256, "plan_sha256": item.plan_sha256}
                for item in sorted(batch.plans, key=lambda item: item.input_id_sha256)
            ],
            "failures": [
                item.model_dump(mode="json")
                for item in sorted(batch.failures, key=lambda item: item.input_id_sha256)
            ],
        }
    )


def _fault(
    reason: QuarantineReason,
    subject: object,
    *,
    expected: object | None = None,
    actual: object | None = None,
) -> QuarantineItem:
    return QuarantineItem(
        reason=reason,
        subject_sha256=_canonical_sha256(_canonical_value(subject)),
        expected_sha256=(None if expected is None else _canonical_sha256(_canonical_value(expected))),
        actual_sha256=(None if actual is None else _canonical_sha256(_canonical_value(actual))),
    )


def _quarantine_sort_key(item: QuarantineItem) -> tuple[str, str, str, str]:
    return (
        item.reason.value,
        item.subject_sha256,
        item.expected_sha256 or "",
        item.actual_sha256 or "",
    )


def _report_hash(report: GoldSetReport) -> str:
    payload = report.model_dump(mode="json", exclude={"report_sha256"})
    return _canonical_sha256(payload)


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be canonicalized")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        _require_utc(value, "canonical datetime")
        return _utc_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_utc(value: datetime, label: str) -> None:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")


def _require_unique(values: object, label: str) -> None:
    sequence = list(values)  # type: ignore[arg-type]
    if len(sequence) != len(set(sequence)):
        raise ValueError(f"{label} must be distinct")


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


__all__ = [
    "CandidateBatch",
    "CandidateParseFailure",
    "CandidatePlan",
    "GoldFieldLabel",
    "GoldPlan",
    "GoldSetReport",
    "GoldTcoExpectation",
    "HumanGoldSet",
    "ParseFailureCode",
    "QuarantineItem",
    "QuarantineReason",
    "evaluate_goldset",
    "hash_goldset_report",
    "hash_material_field_value",
    "hash_rights_manifest",
    "hash_tco_result",
    "hash_vendor_plan",
]
