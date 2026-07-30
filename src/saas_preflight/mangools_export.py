"""One-shot validation of a Human-exported KWFinder CSV.

The raw CSV is read locally and never written by this module.  Output contains
only a safe aggregate, hashes, and a conservative monthly-revenue capacity
floor.  No API, browser, or network access exists in this module.
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .keyword_universe import KeywordUniverseRow, normalize_query
from .models import Sha256, StrictModel


class DemandCapacityDecision(str, Enum):
    INSUFFICIENT_EVEN_AT_FULL_CAPTURE = "insufficient_even_at_full_capture"
    VOLUME_FLOOR_MET_NOT_PROVEN = "volume_floor_met_not_proven"


class MangoolsDemandSafeSummary(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provider: Literal["mangools_kwfinder_human_csv"] = "mangools_kwfinder_human_csv"
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    acquisition_method: Literal["human_ui_export"] = "human_ui_export"
    raw_saved: Literal[False] = False
    query_values_saved: Literal[False] = False
    keyword_count: Literal[150]
    missing_volume_count: Literal[0]
    total_monthly_search_volume: int = Field(ge=0)
    observed_on: date
    next_review_on: date
    raw_csv_sha256: Sha256
    frozen_universe_sha256: Sha256
    monthly_revenue_target_jpy: int = Field(gt=0)
    assumed_confirmed_epc_jpy: Decimal = Field(gt=0, decimal_places=8)
    assumed_outbound_ctr: Decimal = Field(gt=0, le=1, decimal_places=8)
    required_confirmed_outbound_clicks: int = Field(gt=0)
    required_sessions_at_assumed_ctr: int = Field(gt=0)
    capacity_decision: DemandCapacityDecision
    scope_expansion_recommended: bool

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if self.next_review_on <= self.observed_on:
            raise ValueError("next_review_on must be later than observed_on")
        if self.next_review_on > self.observed_on + timedelta(days=90):
            raise ValueError("Mangools demand review interval cannot exceed 90 days")
        insufficient = self.total_monthly_search_volume < self.required_sessions_at_assumed_ctr
        expected = (
            DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE
            if insufficient
            else DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
        )
        if self.capacity_decision is not expected or self.scope_expansion_recommended is not insufficient:
            raise ValueError("capacity decision does not match the conservative volume floor")
        return self


_HEADER_ALIASES = {
    "keyword": frozenset({"keyword", "kw"}),
    "volume": frozenset({"avg search volume", "avg. search volume", "search volume", "sv"}),
    "location": frozenset({"location", "country"}),
}
_JAPAN_VALUES = frozenset({"jp", "japan", "日本"})
_INTEGER_PATTERN = re.compile(r"^(?:0|[1-9]\d*)$")


def _normalized_header(value: str) -> str:
    return " ".join(value.replace("_", " ").strip().lower().split())


def _select_columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise ValueError("Mangools CSV has no header")
    normalized = {_normalized_header(value): value for value in fieldnames}
    selected: dict[str, str] = {}
    for field, aliases in _HEADER_ALIASES.items():
        matches = [normalized[alias] for alias in aliases if alias in normalized]
        if len(matches) != 1:
            raise ValueError(f"Mangools CSV requires exactly one {field} column")
        selected[field] = matches[0]
    return selected


def validate_mangools_human_export(
    csv_path: Path,
    *,
    universe_rows: tuple[KeywordUniverseRow, ...],
    universe_sha256: str,
    observed_on: date,
    next_review_on: date,
    monthly_revenue_target_jpy: int = 200_000,
    assumed_confirmed_epc_jpy: Decimal = Decimal("60"),
    assumed_outbound_ctr: Decimal = Decimal("0.15"),
) -> MangoolsDemandSafeSummary:
    raw = csv_path.read_bytes()
    if not raw or len(raw) > 5_000_000:
        raise ValueError("Mangools CSV size must be between 1 byte and 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Mangools CSV must be UTF-8") from exc

    reader = csv.DictReader(text.splitlines())
    columns = _select_columns(reader.fieldnames)
    expected_queries = {row.query for row in universe_rows}
    if len(expected_queries) != 150:
        raise ValueError("frozen universe must contain exactly 150 unique queries")

    observed: dict[str, int] = {}
    for number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Mangools CSV row {number} is malformed")
        query = normalize_query(row[columns["keyword"]])
        if not query:
            raise ValueError(f"Mangools CSV row {number} has a blank keyword")
        if query in observed:
            raise ValueError("Mangools CSV contains duplicate normalized queries")
        if query not in expected_queries:
            raise ValueError("Mangools CSV query set differs from the frozen universe")
        location = " ".join(row[columns["location"]].strip().lower().split())
        if location not in _JAPAN_VALUES:
            raise ValueError("Mangools CSV must contain only Japan location rows")
        volume = row[columns["volume"]].replace(",", "").strip()
        if not _INTEGER_PATTERN.fullmatch(volume):
            raise ValueError("Mangools CSV contains a missing or non-integer search volume")
        observed[query] = int(volume)

    if set(observed) != expected_queries:
        raise ValueError("Mangools CSV must match all 150 frozen queries exactly")
    if monthly_revenue_target_jpy <= 0:
        raise ValueError("monthly revenue target must be positive")
    if assumed_confirmed_epc_jpy <= 0:
        raise ValueError("assumed confirmed EPC must be positive")
    if not Decimal("0") < assumed_outbound_ctr <= Decimal("1"):
        raise ValueError("assumed outbound CTR must be in (0, 1]")

    required_clicks = int(
        (Decimal(monthly_revenue_target_jpy) / assumed_confirmed_epc_jpy).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    required_sessions = int(
        (Decimal(required_clicks) / assumed_outbound_ctr).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    total = sum(observed.values())
    insufficient = total < required_sessions
    return MangoolsDemandSafeSummary(
        keyword_count=150,
        missing_volume_count=0,
        total_monthly_search_volume=total,
        observed_on=observed_on,
        next_review_on=next_review_on,
        raw_csv_sha256=hashlib.sha256(raw).hexdigest(),
        frozen_universe_sha256=universe_sha256,
        monthly_revenue_target_jpy=monthly_revenue_target_jpy,
        assumed_confirmed_epc_jpy=assumed_confirmed_epc_jpy,
        assumed_outbound_ctr=assumed_outbound_ctr,
        required_confirmed_outbound_clicks=required_clicks,
        required_sessions_at_assumed_ctr=required_sessions,
        capacity_decision=(
            DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE
            if insufficient
            else DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
        ),
        scope_expansion_recommended=insufficient,
    )
