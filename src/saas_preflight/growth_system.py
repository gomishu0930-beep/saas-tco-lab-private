"""Deterministic learning, editorial, policy and growth feedback contracts.

This module is deliberately credential-blind and network-free. It complements
the authoritative P10-P21 rights, measurement, settlement and publication
controls; it never grants a fetch, affiliate, production or publication right.
Raw prompts, article bodies, URLs, tracking IDs and personal data are outside
these contracts. Only stable identifiers, hashes and aggregated values enter.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .models import CurrencyCode, Sha256, Slug, StrictModel


class GrowthSystemError(ValueError):
    """Raised when a growth-system artifact is ambiguous or unsafe."""


class EvidenceMode(str, Enum):
    MODELED = "modeled"
    OBSERVED = "observed"


class MetricUnit(str, Enum):
    COUNT = "count"
    MINOR_CURRENCY = "minor_currency"
    RATIO = "ratio"
    MINUTES = "minutes"


class GoldDomain(str, Enum):
    FIELD_ACCURACY = "field_accuracy"
    POLICY_DECISION = "policy_decision"
    CONTENT_BRIEF = "content_brief"
    CLAIM_CITATION = "claim_citation"
    CTA_CONVERSION = "cta_conversion"


class StrategyPosture(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class ProposalLane(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"
    SHARED = "shared"


class PolicyDecisionOutcome(str, Enum):
    APPROVE_EXPERIMENT = "approve_experiment"
    REVISE = "revise"
    REJECT = "reject"


class PageType(str, Enum):
    COMPARISON = "comparison"
    PRICING = "pricing"
    ALTERNATIVES = "alternatives"
    USE_CASE_FIT = "use_case_fit"
    MIGRATION = "migration"
    METHODOLOGY = "methodology"


class ContentIntent(str, Enum):
    COMPARE = "compare"
    PRICE_CHECK = "price_check"
    REPLACE = "replace"
    FIT_CHECK = "fit_check"
    MIGRATE = "migrate"
    VERIFY_METHOD = "verify_method"


class DraftVoice(str, Enum):
    ANALYST = "analyst"
    EDITOR = "editor"
    SKEPTICAL_BUYER = "skeptical_buyer"


class EditorialDecision(str, Enum):
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    STOP = "stop"


class DerivativeChannel(str, Enum):
    X = "x"
    EMAIL = "email"
    CHART = "chart"


class FunnelStage(str, Enum):
    SEARCH_IMPRESSION = "search_impression"
    ORGANIC_CLICK = "organic_click"
    QUALIFIED_SESSION = "qualified_session"
    COMPARISON_INTERACTION = "comparison_interaction"
    OUTBOUND_CLICK = "outbound_click"
    MERCHANT_EVENT = "merchant_event"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAID = "paid"


class LinkStatus(str, Enum):
    HEALTHY = "healthy"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class CtaDecision(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ActivationKind(str, Enum):
    NOTION_EDITORIAL_UI = "notion_editorial_ui"
    CHALLENGER_MODEL = "challenger_model"
    LLM_OBSERVABILITY = "llm_observability"
    DURABLE_SCHEDULER = "durable_scheduler"
    TELEMETRY = "telemetry"
    CLOUD_RUNTIME = "cloud_runtime"
    PUBLIC_HOSTING = "public_hosting"


class ActivationDecision(str, Enum):
    READY_FOR_HUMAN_GATE = "ready_for_human_gate"
    STOP = "stop"


class GrowthIdentity(StrictModel):
    property_id_sha256: Sha256
    content_id_sha256: Sha256
    query_cluster_id_sha256: Sha256
    campaign_id_sha256: Sha256
    cta_id_sha256: Sha256
    cohort_id_sha256: Sha256


class MetricDefinition(StrictModel):
    metric_key: Slug
    metric_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$",
    )
    unit: MetricUnit
    denominator_metric_key: Slug | None = None
    description_sha256: Sha256

    @model_validator(mode="after")
    def validate_denominator(self) -> Self:
        if self.unit is MetricUnit.RATIO and self.denominator_metric_key is None:
            raise ValueError("ratio metric requires denominator_metric_key")
        if self.unit is not MetricUnit.RATIO and self.denominator_metric_key is not None:
            raise ValueError("denominator_metric_key is only valid for ratio metrics")
        if self.denominator_metric_key == self.metric_key:
            raise ValueError("metric cannot use itself as denominator")
        return self


class SemanticFact(StrictModel):
    fact_id_sha256: Sha256
    identity: GrowthIdentity
    metric_key: Slug
    metric_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$",
    )
    value: Decimal
    evidence_mode: EvidenceMode
    source_artifact_sha256: Sha256 | None = None
    scenario_sha256: Sha256 | None = None
    captured_at: datetime
    expires_at: datetime

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "semantic fact timestamp")

    @model_validator(mode="after")
    def validate_fact(self) -> Self:
        if self.expires_at <= self.captured_at:
            raise ValueError("semantic fact expiry must be later than capture")
        if self.evidence_mode is EvidenceMode.OBSERVED:
            if self.source_artifact_sha256 is None or self.scenario_sha256 is not None:
                raise ValueError("observed fact requires source artifact and forbids scenario")
        else:
            if self.scenario_sha256 is None or self.source_artifact_sha256 is not None:
                raise ValueError("modeled fact requires scenario and forbids observed source")
        return self


class SemanticSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime
    definitions: tuple[MetricDefinition, ...] = Field(min_length=1)
    facts: tuple[SemanticFact, ...] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "semantic snapshot timestamp")

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        definitions = {(item.metric_key, item.metric_version): item for item in self.definitions}
        if len(definitions) != len(self.definitions):
            raise ValueError("metric definition keys must be unique")
        if list(definitions) != sorted(definitions):
            raise ValueError("metric definitions must be canonically sorted")
        fact_ids = [item.fact_id_sha256 for item in self.facts]
        if fact_ids != sorted(fact_ids) or len(fact_ids) != len(set(fact_ids)):
            raise ValueError("semantic facts must have unique canonically sorted IDs")
        fact_keys: set[tuple[str, str, str]] = set()
        for fact in self.facts:
            key = (fact.metric_key, fact.metric_version)
            if key not in definitions:
                raise ValueError("semantic fact references unknown metric definition")
            if fact.captured_at > self.created_at:
                raise ValueError("semantic fact cannot be captured after snapshot creation")
            identity_hash = hash_growth_identity(fact.identity)
            fact_key = (identity_hash, fact.metric_key, fact.metric_version)
            if fact_key in fact_keys:
                raise ValueError("semantic snapshot has duplicate identity metric fact")
            fact_keys.add(fact_key)
        return self


class LearningGoldCase(StrictModel):
    case_id_sha256: Sha256
    domain: GoldDomain
    input_artifact_sha256: Sha256
    expected_artifact_sha256: Sha256
    human_label_receipt_sha256: Sha256
    synthetic: bool
    labeled_at: datetime
    expires_at: datetime

    @field_validator("labeled_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "learning gold timestamp")

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.expires_at <= self.labeled_at:
            raise ValueError("learning gold case expiry must be later than label")
        return self


class LearningGoldSet(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    goldset_id_sha256: Sha256
    created_at: datetime
    expires_at: datetime
    cases: tuple[LearningGoldCase, ...] = Field(min_length=5)

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "learning gold-set timestamp")

    @model_validator(mode="after")
    def validate_goldset(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("learning gold-set expiry must be later than creation")
        ids = [item.case_id_sha256 for item in self.cases]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("learning gold cases must have unique canonically sorted IDs")
        domains = {item.domain for item in self.cases}
        if domains != set(GoldDomain):
            raise ValueError("learning gold-set must cover all five domains")
        if any(item.labeled_at > self.created_at for item in self.cases):
            raise ValueError("learning gold case cannot be labeled after set creation")
        if any(item.expires_at < self.expires_at for item in self.cases):
            raise ValueError("gold-set expiry cannot exceed a case expiry")
        return self


class PromptModelRun(StrictModel):
    run_id_sha256: Sha256
    provider: Slug
    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    model_snapshot: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    prompt_sha256: Sha256
    input_artifact_sha256: Sha256
    output_artifact_sha256: Sha256
    started_at: datetime
    completed_at: datetime
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_minor: int = Field(ge=0)
    cost_currency: CurrencyCode
    evaluation_case_ids: tuple[Sha256, ...] = Field(min_length=1)
    evaluation_passed: bool
    contains_sensitive_data: Literal[False] = False

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "model run timestamp")

    @field_validator("evaluation_case_ids")
    @classmethod
    def canonicalize_cases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("model run evaluation cases must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("model run cannot complete before start")
        return self


class PromptRunLedger(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    ledger_id_sha256: Sha256
    runs: tuple[PromptModelRun, ...]

    @model_validator(mode="after")
    def validate_ledger(self) -> Self:
        ordering = [(run.started_at, run.run_id_sha256) for run in self.runs]
        if ordering != sorted(ordering):
            raise ValueError("model runs must be ordered by start time and ID")
        run_ids = [run.run_id_sha256 for run in self.runs]
        outputs = [run.output_artifact_sha256 for run in self.runs]
        if len(run_ids) != len(set(run_ids)) or len(outputs) != len(set(outputs)):
            raise ValueError("model run and output IDs must be unique")
        return self


class InitiativeProposal(StrictModel):
    proposal_id_sha256: Sha256
    posture: StrategyPosture
    title: str = Field(min_length=1, max_length=160)
    evidence_artifact_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    expected_impact_low_minor: int = Field(ge=0)
    expected_impact_high_minor: int = Field(ge=0)
    confidence: Decimal = Field(ge=0, le=1)
    cost_minor: int = Field(gt=0)
    time_to_signal_days: int = Field(gt=0, le=365)
    reversibility: Decimal = Field(gt=0, le=1)
    kill_condition: str = Field(min_length=1, max_length=500)
    owner_lane: ProposalLane
    rights_gate_passed: bool
    legal_gate_passed: bool
    security_gate_passed: bool

    @field_validator("evidence_artifact_sha256s")
    @classmethod
    def canonicalize_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("proposal evidence artifacts must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_impact(self) -> Self:
        if self.expected_impact_high_minor < self.expected_impact_low_minor:
            raise ValueError("expected impact high must not be below low")
        return self


class InitiativePortfolio(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    currency: CurrencyCode
    as_of: datetime
    proposals: tuple[InitiativeProposal, ...] = Field(min_length=1)

    @field_validator("as_of")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "initiative portfolio timestamp")

    @model_validator(mode="after")
    def validate_portfolio(self) -> Self:
        ids = [item.proposal_id_sha256 for item in self.proposals]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("proposals must have unique canonically sorted IDs")
        return self


class InitiativeAssessment(StrictModel):
    proposal_id_sha256: Sha256
    posture: StrategyPosture
    eligible: bool
    expected_value_of_information: Decimal | None
    hard_gate_failures: tuple[str, ...]


class PolicyMemo(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    as_of: datetime
    currency: CurrencyCode
    recommended_proposal_id_sha256: Sha256 | None
    assessments: tuple[InitiativeAssessment, ...]

    @field_validator("as_of")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "policy memo timestamp")

    @model_validator(mode="after")
    def validate_memo(self) -> Self:
        if {item.posture for item in self.assessments} != set(StrategyPosture):
            raise ValueError("policy memo requires conservative, balanced and aggressive options")
        ids = [item.proposal_id_sha256 for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("policy memo proposal IDs must be unique")
        eligible_ids = {item.proposal_id_sha256 for item in self.assessments if item.eligible}
        if self.recommended_proposal_id_sha256 is not None and self.recommended_proposal_id_sha256 not in eligible_ids:
            raise ValueError("recommended proposal must be eligible")
        return self


class HumanPolicyDecisionReceipt(StrictModel):
    """Hash-only record of a Human policy choice; not an execution grant."""

    schema_version: Literal["1.0"] = "1.0"
    memo_sha256: Sha256
    outcome: PolicyDecisionOutcome
    selected_proposal_id_sha256: Sha256 | None = None
    decided_by_sha256: Sha256
    decision_artifact_sha256: Sha256
    basis_artifact_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    decided_at: datetime
    expires_at: datetime
    grants_external_action: Literal[False] = False

    @field_validator("decided_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "Human policy decision timestamp")

    @field_validator("basis_artifact_sha256s")
    @classmethod
    def canonicalize_basis(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("policy decision basis artifacts must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.expires_at <= self.decided_at:
            raise ValueError("policy decision expiry must be later than decision")
        needs_selection = self.outcome in {
            PolicyDecisionOutcome.APPROVE_EXPERIMENT,
            PolicyDecisionOutcome.REVISE,
        }
        if needs_selection != (self.selected_proposal_id_sha256 is not None):
            raise ValueError("approve or revise requires one selected proposal; reject forbids it")
        return self


class ContentBrief(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    brief_id_sha256: Sha256
    page_type: PageType
    query_cluster_id_sha256: Sha256
    intent: ContentIntent
    audience: str = Field(min_length=1, max_length=200)
    comparison_unit_sha256: Sha256
    approved_evidence_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    forbidden_claim_sha256s: tuple[Sha256, ...] = ()
    cta_eligible: bool
    cta_basis_sha256: Sha256 | None = None
    created_at: datetime
    source_valid_until: datetime

    @field_validator("created_at", "source_valid_until")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "content brief timestamp")

    @field_validator("approved_evidence_sha256s", "forbidden_claim_sha256s")
    @classmethod
    def canonicalize_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("content brief hash sets must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_brief(self) -> Self:
        if self.source_valid_until <= self.created_at:
            raise ValueError("content brief source validity must extend beyond creation")
        if self.cta_eligible != (self.cta_basis_sha256 is not None):
            raise ValueError("CTA eligibility and CTA basis must be present together")
        return self


class ClaimEvidenceLink(StrictModel):
    claim_id_sha256: Sha256
    material: bool
    evidence_sha256s: tuple[Sha256, ...]
    citation_id_sha256: Sha256 | None = None

    @field_validator("evidence_sha256s")
    @classmethod
    def canonicalize_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("claim evidence must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_link(self) -> Self:
        if self.material and (not self.evidence_sha256s or self.citation_id_sha256 is None):
            raise ValueError("material claim requires evidence and citation")
        if not self.evidence_sha256s and self.citation_id_sha256 is not None:
            raise ValueError("citation cannot exist without evidence")
        return self


class EditorialDraft(StrictModel):
    voice: DraftVoice
    content_sha256: Sha256
    claim_id_sha256s: tuple[Sha256, ...]

    @field_validator("claim_id_sha256s")
    @classmethod
    def canonicalize_claims(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("draft claim IDs must be unique")
        return tuple(sorted(values))


class EditorialPackage(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    brief: ContentBrief
    drafts: tuple[EditorialDraft, ...] = Field(min_length=3, max_length=3)
    claims: tuple[ClaimEvidenceLink, ...]
    synthesized_content_sha256: Sha256
    synthesized_claim_id_sha256s: tuple[Sha256, ...]

    @field_validator("synthesized_claim_id_sha256s")
    @classmethod
    def canonicalize_synthesized_claims(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("synthesized claim IDs must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        if {draft.voice for draft in self.drafts} != set(DraftVoice):
            raise ValueError("editorial package requires analyst, editor and skeptical buyer drafts")
        claim_map = {claim.claim_id_sha256: claim for claim in self.claims}
        if len(claim_map) != len(self.claims):
            raise ValueError("editorial package claim IDs must be unique")
        known = set(claim_map)
        for draft in self.drafts:
            if not set(draft.claim_id_sha256s) <= known:
                raise ValueError("draft references unknown claim")
        if not set(self.synthesized_claim_id_sha256s) <= known:
            raise ValueError("synthesized article references unknown claim")
        approved = set(self.brief.approved_evidence_sha256s)
        if any(not set(claim.evidence_sha256s) <= approved for claim in self.claims):
            raise ValueError("claim uses evidence outside approved brief")
        if set(self.brief.forbidden_claim_sha256s) & set(self.synthesized_claim_id_sha256s):
            raise ValueError("synthesized article includes a forbidden claim")
        return self


class EditorialEvaluation(StrictModel):
    decision: EditorialDecision
    evaluated_at: datetime
    brief_id_sha256: Sha256
    unsupported_material_claims: int = Field(ge=0)
    missing_synthesized_claims: int = Field(ge=0)
    reasons: tuple[str, ...]

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "editorial evaluation timestamp")


class ContentDerivative(StrictModel):
    derivative_id_sha256: Sha256
    channel: DerivativeChannel
    canonical_content_sha256: Sha256
    derivative_content_sha256: Sha256
    claim_id_sha256s: tuple[Sha256, ...]

    @field_validator("claim_id_sha256s")
    @classmethod
    def canonicalize_claims(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("derivative claim IDs must be unique")
        return tuple(sorted(values))


class DerivativeBundle(StrictModel):
    package_sha256: Sha256
    editorial_evaluation_sha256: Sha256
    canonical_content_sha256: Sha256
    canonical_claim_id_sha256s: tuple[Sha256, ...]
    derivatives: tuple[ContentDerivative, ...]

    @model_validator(mode="after")
    def validate_derivatives(self) -> Self:
        ids = [item.derivative_id_sha256 for item in self.derivatives]
        if len(ids) != len(set(ids)):
            raise ValueError("derivative IDs must be unique")
        canonical_claims = set(self.canonical_claim_id_sha256s)
        for item in self.derivatives:
            if item.canonical_content_sha256 != self.canonical_content_sha256:
                raise ValueError("derivative references wrong canonical content")
            if not set(item.claim_id_sha256s) <= canonical_claims:
                raise ValueError("derivative cannot introduce a new claim")
        return self


class FunnelEvent(StrictModel):
    event_id_sha256: Sha256
    parent_event_id_sha256: Sha256 | None = None
    identity: GrowthIdentity
    stage: FunnelStage
    occurred_at: datetime
    source_artifact_sha256: Sha256
    transaction_id_sha256: Sha256 | None = None
    amount_minor: int = Field(default=0, ge=0)
    currency: CurrencyCode | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "funnel event timestamp")

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        monetary = self.stage in {FunnelStage.PENDING, FunnelStage.CONFIRMED, FunnelStage.PAID}
        if monetary:
            if self.transaction_id_sha256 is None or self.currency is None:
                raise ValueError("monetary funnel event requires transaction and currency")
        elif self.transaction_id_sha256 is not None or self.amount_minor != 0 or self.currency is not None:
            raise ValueError("non-monetary funnel event cannot contain transaction amount")
        return self


class FeedbackBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    batch_id_sha256: Sha256
    metric_version: str = Field(pattern=r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
    captured_at: datetime
    expires_at: datetime
    events: tuple[FunnelEvent, ...]

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "feedback batch timestamp")

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        if self.expires_at <= self.captured_at:
            raise ValueError("feedback batch expiry must be later than capture")
        ordering = [(item.occurred_at, item.event_id_sha256) for item in self.events]
        if ordering != sorted(ordering):
            raise ValueError("feedback events must be ordered by time and ID")
        event_map = {item.event_id_sha256: item for item in self.events}
        if len(event_map) != len(self.events):
            raise ValueError("feedback event IDs must be unique")
        transaction_stages: set[tuple[str, FunnelStage]] = set()
        currencies = {item.currency for item in self.events if item.currency is not None}
        if len(currencies) > 1:
            raise ValueError("feedback batch cannot mix currencies")
        for item in self.events:
            if item.occurred_at > self.captured_at:
                raise ValueError("feedback event cannot occur after batch capture")
            if item.parent_event_id_sha256 is None:
                if item.stage is not FunnelStage.SEARCH_IMPRESSION:
                    raise ValueError("only search impression may omit parent event")
            else:
                parent = event_map.get(item.parent_event_id_sha256)
                if parent is None:
                    raise ValueError("feedback event parent is missing")
                if parent.occurred_at > item.occurred_at:
                    raise ValueError("feedback event cannot predate parent")
                if parent.identity != item.identity:
                    raise ValueError("feedback event identity must match parent")
                if _stage_index(item.stage) <= _stage_index(parent.stage):
                    raise ValueError("feedback stage must advance from parent")
            if item.transaction_id_sha256 is not None:
                transaction_key = (item.transaction_id_sha256, item.stage)
                if transaction_key in transaction_stages:
                    raise ValueError("transaction stage must be unique")
                transaction_stages.add(transaction_key)
        return self


class OperationsKpiInput(StrictModel):
    human_minutes: int = Field(ge=0)
    routine_tasks_total: int = Field(ge=0)
    routine_tasks_automated: int = Field(ge=0)
    jobs_total: int = Field(ge=0)
    jobs_succeeded: int = Field(ge=0)
    major_misstatements: int = Field(ge=0)
    operating_cost_minor: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.routine_tasks_automated > self.routine_tasks_total:
            raise ValueError("automated routine tasks cannot exceed total")
        if self.jobs_succeeded > self.jobs_total:
            raise ValueError("succeeded jobs cannot exceed total")
        return self


class KpiScorecard(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_mode: Literal[EvidenceMode.OBSERVED] = EvidenceMode.OBSERVED
    metric_version: str
    as_of: datetime
    currency: CurrencyCode | None
    search_impressions: int = Field(ge=0)
    organic_clicks: int = Field(ge=0)
    qualified_sessions: int = Field(ge=0)
    valid_outbound_clicks: int = Field(ge=0)
    confirmed_revenue_minor: int = Field(ge=0)
    confirmed_epc_minor: Decimal | None
    revenue_per_qualified_session_minor: Decimal | None
    net_operating_profit_minor: int
    human_minutes: int = Field(ge=0)
    automation_rate: Decimal | None
    job_success_rate: Decimal | None
    major_misstatements: int = Field(ge=0)

    @field_validator("as_of")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "KPI scorecard timestamp")


class CtaHealthInput(StrictModel):
    identity: GrowthIdentity
    affiliate_approved: bool
    rights_current: bool
    link_status: LinkStatus
    expected_destination_sha256: Sha256
    observed_destination_sha256: Sha256
    expected_disclosure_sha256: Sha256
    observed_disclosure_sha256: Sha256
    checked_at: datetime
    expires_at: datetime

    @field_validator("checked_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "CTA health timestamp")

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.expires_at <= self.checked_at:
            raise ValueError("CTA health expiry must be later than check")
        return self


class CtaHealthEvaluation(StrictModel):
    decision: CtaDecision
    evaluated_at: datetime
    identity_sha256: Sha256
    reasons: tuple[str, ...]

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "CTA evaluation timestamp")


class ConditionalActivationInput(StrictModel):
    """Authority-free facts for tools deliberately deferred until evidence exists."""

    schema_version: Literal["1.0"] = "1.0"
    activation_id_sha256: Sha256
    kind: ActivationKind
    captured_at: datetime
    expires_at: datetime
    evidence_artifact_sha256s: tuple[Sha256, ...] = Field(min_length=1)
    upstream_ready: bool = False
    operational_need_demonstrated: bool = False
    evaluated_runs: int = Field(default=0, ge=0)
    meaningful_monthly_runs: int = Field(default=0, ge=0)
    observed_days: int = Field(default=0, ge=0)
    approved_sources: int = Field(default=0, ge=0)
    quality_gain_percent: Decimal = Field(default=Decimal("0"), ge=-100, le=1000)
    cost_or_latency_gain_percent: Decimal = Field(default=Decimal("0"), ge=-100, le=100)
    quality_regression: bool = False
    single_provider_candidate: bool = False
    retention_approved: bool = False
    hosting_approved: bool = False
    budget_approved: bool = False
    tool_choice_approved: bool = False
    public_go_approved: bool = False
    approval_receipt_sha256s: tuple[Sha256, ...] = ()

    @field_validator("captured_at", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "conditional activation timestamp")

    @field_validator("evidence_artifact_sha256s", "approval_receipt_sha256s")
    @classmethod
    def canonicalize_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("conditional activation hashes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if self.expires_at <= self.captured_at:
            raise ValueError("conditional activation expiry must be later than capture")
        human_flags = (
            self.retention_approved,
            self.hosting_approved,
            self.budget_approved,
            self.tool_choice_approved,
            self.public_go_approved,
        )
        if any(human_flags) and not self.approval_receipt_sha256s:
            raise ValueError("Human approval flags require an approval receipt hash")
        return self


class ConditionalActivationEvaluation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    activation_id_sha256: Sha256
    kind: ActivationKind
    evaluated_at: datetime
    decision: ActivationDecision
    reasons: tuple[str, ...]
    authority: Literal["none"] = "none"

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc(value, "conditional activation evaluation timestamp")


def hash_growth_identity(identity: GrowthIdentity) -> str:
    return _sha256(identity.model_dump(mode="json"))


def hash_growth_artifact(artifact: StrictModel) -> str:
    return _sha256(artifact.model_dump(mode="json"))


def build_policy_memo(portfolio: InitiativePortfolio) -> PolicyMemo:
    proposals_by_posture: dict[StrategyPosture, InitiativeProposal] = {}
    for proposal in portfolio.proposals:
        if proposal.posture in proposals_by_posture:
            raise GrowthSystemError("portfolio may contain only one proposal per posture")
        proposals_by_posture[proposal.posture] = proposal
    if set(proposals_by_posture) != set(StrategyPosture):
        raise GrowthSystemError("portfolio requires exactly three strategy postures")

    assessments: list[InitiativeAssessment] = []
    for posture in StrategyPosture:
        proposal = proposals_by_posture[posture]
        failures = tuple(
            name
            for name, passed in (
                ("rights", proposal.rights_gate_passed),
                ("legal", proposal.legal_gate_passed),
                ("security", proposal.security_gate_passed),
            )
            if not passed
        )
        score = None if failures else _proposal_evi(proposal)
        assessments.append(
            InitiativeAssessment(
                proposal_id_sha256=proposal.proposal_id_sha256,
                posture=posture,
                eligible=not failures,
                expected_value_of_information=score,
                hard_gate_failures=failures,
            )
        )
    eligible = [item for item in assessments if item.eligible]
    recommended = (
        None
        if not eligible
        else max(
            eligible,
            key=lambda item: (
                item.expected_value_of_information or Decimal("0"),
                item.proposal_id_sha256,
            ),
        ).proposal_id_sha256
    )
    return PolicyMemo(
        as_of=portfolio.as_of,
        currency=portfolio.currency,
        recommended_proposal_id_sha256=recommended,
        assessments=tuple(assessments),
    )


def evaluate_editorial_package(
    package: EditorialPackage, *, at: datetime
) -> EditorialEvaluation:
    instant = _utc(at, "editorial evaluation time")
    claim_map = {item.claim_id_sha256: item for item in package.claims}
    unsupported = sum(
        1
        for claim_id in package.synthesized_claim_id_sha256s
        if claim_map[claim_id].material
        and (
            not claim_map[claim_id].evidence_sha256s
            or claim_map[claim_id].citation_id_sha256 is None
        )
    )
    missing = sum(
        1
        for claim_id in package.synthesized_claim_id_sha256s
        if claim_id not in claim_map
    )
    reasons: list[str] = []
    if instant >= package.brief.source_valid_until:
        reasons.append("source_expired")
    if unsupported:
        reasons.append("unsupported_material_claim")
    if missing:
        reasons.append("unknown_synthesized_claim")
    return EditorialEvaluation(
        decision=(EditorialDecision.STOP if reasons else EditorialDecision.READY_FOR_HUMAN_REVIEW),
        evaluated_at=instant,
        brief_id_sha256=package.brief.brief_id_sha256,
        unsupported_material_claims=unsupported,
        missing_synthesized_claims=missing,
        reasons=tuple(sorted(reasons)),
    )


def build_kpi_scorecard(
    batch: FeedbackBatch,
    operations: OperationsKpiInput,
    *,
    at: datetime,
) -> KpiScorecard:
    instant = _utc(at, "KPI scorecard time")
    if instant < batch.captured_at:
        raise GrowthSystemError("scorecard cannot predate feedback batch capture")
    if instant >= batch.expires_at:
        raise GrowthSystemError("feedback batch is expired")
    counts = {stage: 0 for stage in FunnelStage}
    for event in batch.events:
        counts[event.stage] += 1

    latest_transactions: dict[str, FunnelEvent] = {}
    for event in batch.events:
        if event.transaction_id_sha256 is not None:
            current = latest_transactions.get(event.transaction_id_sha256)
            if current is None or (event.occurred_at, _stage_index(event.stage)) > (
                current.occurred_at,
                _stage_index(current.stage),
            ):
                latest_transactions[event.transaction_id_sha256] = event
    settled_events = [
        event
        for event in latest_transactions.values()
        if event.stage in {FunnelStage.CONFIRMED, FunnelStage.PAID}
    ]
    currencies = {event.currency for event in settled_events}
    if len(currencies) > 1:
        raise GrowthSystemError("scorecard cannot mix settled currencies")
    currency = next(iter(currencies), None)
    revenue = sum(event.amount_minor for event in settled_events)
    outbound = counts[FunnelStage.OUTBOUND_CLICK]
    qualified = counts[FunnelStage.QUALIFIED_SESSION]
    epc = None if outbound == 0 else Decimal(revenue) / Decimal(outbound)
    revenue_per_qualified = None if qualified == 0 else Decimal(revenue) / Decimal(qualified)
    automation_rate = (
        None
        if operations.routine_tasks_total == 0
        else Decimal(operations.routine_tasks_automated) / Decimal(operations.routine_tasks_total)
    )
    job_success_rate = (
        None
        if operations.jobs_total == 0
        else Decimal(operations.jobs_succeeded) / Decimal(operations.jobs_total)
    )
    return KpiScorecard(
        metric_version=batch.metric_version,
        as_of=instant,
        currency=currency,
        search_impressions=counts[FunnelStage.SEARCH_IMPRESSION],
        organic_clicks=counts[FunnelStage.ORGANIC_CLICK],
        qualified_sessions=qualified,
        valid_outbound_clicks=outbound,
        confirmed_revenue_minor=revenue,
        confirmed_epc_minor=epc,
        revenue_per_qualified_session_minor=revenue_per_qualified,
        net_operating_profit_minor=revenue - operations.operating_cost_minor,
        human_minutes=operations.human_minutes,
        automation_rate=automation_rate,
        job_success_rate=job_success_rate,
        major_misstatements=operations.major_misstatements,
    )


def evaluate_cta_health(value: CtaHealthInput, *, at: datetime) -> CtaHealthEvaluation:
    instant = _utc(at, "CTA evaluation time")
    reasons: list[str] = []
    if not value.affiliate_approved:
        reasons.append("affiliate_not_approved")
    if not value.rights_current:
        reasons.append("rights_not_current")
    if value.link_status is not LinkStatus.HEALTHY:
        reasons.append(f"link_{value.link_status.value}")
    if value.expected_destination_sha256 != value.observed_destination_sha256:
        reasons.append("destination_mismatch")
    if value.expected_disclosure_sha256 != value.observed_disclosure_sha256:
        reasons.append("disclosure_mismatch")
    if instant < value.checked_at:
        reasons.append("future_check")
    if instant >= value.expires_at:
        reasons.append("health_expired")
    return CtaHealthEvaluation(
        decision=CtaDecision.DISABLED if reasons else CtaDecision.ENABLED,
        evaluated_at=instant,
        identity_sha256=hash_growth_identity(value.identity),
        reasons=tuple(sorted(reasons)),
    )


def evaluate_conditional_activation(
    value: ConditionalActivationInput, *, at: datetime
) -> ConditionalActivationEvaluation:
    """Return readiness for a separate Human gate, never tool activation authority."""

    instant = _utc(at, "conditional activation evaluation time")
    reasons: list[str] = []
    if instant < value.captured_at:
        reasons.append("future_evidence")
    if instant >= value.expires_at:
        reasons.append("evidence_expired")
    if not value.upstream_ready:
        reasons.append("upstream_not_ready")

    if value.kind is ActivationKind.NOTION_EDITORIAL_UI:
        if not value.operational_need_demonstrated:
            reasons.append("operational_need_not_demonstrated")
        if not value.tool_choice_approved:
            reasons.append("tool_choice_not_approved")
    elif value.kind is ActivationKind.CHALLENGER_MODEL:
        if value.evaluated_runs < 100:
            reasons.append("fewer_than_100_evaluated_runs")
        if not value.single_provider_candidate:
            reasons.append("single_provider_not_selected")
        if not value.retention_approved:
            reasons.append("retention_not_approved")
        if not value.budget_approved:
            reasons.append("budget_not_approved")
        quality_path = value.quality_gain_percent >= Decimal("5")
        efficiency_path = (
            value.cost_or_latency_gain_percent >= Decimal("30")
            and not value.quality_regression
        )
        if not (quality_path or efficiency_path):
            reasons.append("promotion_threshold_not_met")
    elif value.kind is ActivationKind.LLM_OBSERVABILITY:
        if value.meaningful_monthly_runs < 100:
            reasons.append("fewer_than_100_meaningful_monthly_runs")
        if not value.retention_approved:
            reasons.append("retention_not_approved")
        if not value.hosting_approved:
            reasons.append("hosting_not_approved")
    elif value.kind is ActivationKind.DURABLE_SCHEDULER:
        if value.observed_days < 30:
            reasons.append("fewer_than_30_observed_days")
        if value.approved_sources < 1:
            reasons.append("no_approved_source")
    elif value.kind is ActivationKind.TELEMETRY:
        if value.observed_days < 30:
            reasons.append("fewer_than_30_observed_days")
        if value.approved_sources < 1:
            reasons.append("no_approved_alert_source")
    elif value.kind is ActivationKind.CLOUD_RUNTIME:
        if value.observed_days < 30:
            reasons.append("fewer_than_30_observed_days")
        if not value.budget_approved:
            reasons.append("budget_not_approved")
        if not value.hosting_approved:
            reasons.append("hosting_not_approved")
        if not value.public_go_approved:
            reasons.append("public_go_not_approved")
    elif value.kind is ActivationKind.PUBLIC_HOSTING:
        if not value.public_go_approved:
            reasons.append("public_go_not_approved")

    return ConditionalActivationEvaluation(
        activation_id_sha256=value.activation_id_sha256,
        kind=value.kind,
        evaluated_at=instant,
        decision=(
            ActivationDecision.STOP
            if reasons
            else ActivationDecision.READY_FOR_HUMAN_GATE
        ),
        reasons=tuple(sorted(reasons)),
    )


def _proposal_evi(proposal: InitiativeProposal) -> Decimal:
    midpoint = (
        Decimal(proposal.expected_impact_low_minor)
        + Decimal(proposal.expected_impact_high_minor)
    ) / Decimal("2")
    return (
        midpoint * proposal.confidence * proposal.reversibility
        / (Decimal(proposal.cost_minor) * Decimal(proposal.time_to_signal_days))
    )


def _stage_index(stage: FunnelStage) -> int:
    return list(FunnelStage).index(stage)


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value


def _sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "ActivationDecision",
    "ActivationKind",
    "ContentBrief",
    "ContentDerivative",
    "ContentIntent",
    "CtaDecision",
    "CtaHealthEvaluation",
    "CtaHealthInput",
    "ConditionalActivationEvaluation",
    "ConditionalActivationInput",
    "DerivativeBundle",
    "DerivativeChannel",
    "DraftVoice",
    "EditorialDecision",
    "EditorialDraft",
    "EditorialEvaluation",
    "EditorialPackage",
    "EvidenceMode",
    "FeedbackBatch",
    "FunnelEvent",
    "FunnelStage",
    "GoldDomain",
    "GrowthIdentity",
    "GrowthSystemError",
    "InitiativeAssessment",
    "InitiativePortfolio",
    "InitiativeProposal",
    "HumanPolicyDecisionReceipt",
    "KpiScorecard",
    "LearningGoldCase",
    "LearningGoldSet",
    "LinkStatus",
    "MetricDefinition",
    "MetricUnit",
    "OperationsKpiInput",
    "PageType",
    "PolicyMemo",
    "PolicyDecisionOutcome",
    "PromptModelRun",
    "PromptRunLedger",
    "ProposalLane",
    "SemanticFact",
    "SemanticSnapshot",
    "StrategyPosture",
    "build_kpi_scorecard",
    "build_policy_memo",
    "evaluate_cta_health",
    "evaluate_conditional_activation",
    "evaluate_editorial_package",
    "hash_growth_artifact",
    "hash_growth_identity",
]
