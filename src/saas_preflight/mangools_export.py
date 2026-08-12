"""One-shot validation of a Human-exported KWFinder CSV.

The raw CSV is read locally and never written by this module. Output contains
only a safe aggregate, hashes, and a conservative monthly-revenue capacity
comparison. No API, browser, or network access exists in this module.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from .keyword_universe import KeywordUniverseRow, normalize_query
from .models import Sha256, StrictModel


class DemandCapacityDecision(str, Enum):
    INSUFFICIENT_EVEN_AT_FULL_CAPTURE = "insufficient_even_at_full_capture"
    KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE = (
        "known_volume_floor_below_required_incomplete"
    )
    VOLUME_FLOOR_MET_NOT_PROVEN = "volume_floor_met_not_proven"


class MangoolsVolumeStatus(str, Enum):
    INTEGER = "integer"
    COMMA_INTEGER = "comma_integer"
    DECIMAL = "decimal"
    NO_DATA = "no_data"
    REJECTED = "rejected"


class MangoolsVolumeClassification(StrictModel):
    status: MangoolsVolumeStatus
    source_text: str
    normalized_volume: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_classification(self) -> Self:
        known = self.status in {
            MangoolsVolumeStatus.INTEGER,
            MangoolsVolumeStatus.COMMA_INTEGER,
            MangoolsVolumeStatus.DECIMAL,
        }
        if known != (self.normalized_volume is not None):
            raise ValueError("known volume status and normalized_volume must agree")
        return self


class MangoolsRejectedVolumeRow(StrictModel):
    line_number: int = Field(ge=2)
    source_text: str


class MangoolsSlateRejectedVolumeRow(StrictModel):
    batch_number: int = Field(ge=1)
    line_number: int = Field(ge=2)
    source_text: str


class MangoolsDemandSafeSummary(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    provider: Literal["mangools_kwfinder_human_csv"] = "mangools_kwfinder_human_csv"
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    acquisition_method: Literal["human_ui_export"] = "human_ui_export"
    raw_saved: Literal[False] = False
    query_values_saved: Literal[False] = False
    keyword_count: Literal[150]
    known_volume_count: int = Field(ge=0, le=150)
    no_data_volume_count: int = Field(ge=0, le=150)
    rejected_volume_count: int = Field(ge=0, le=150)
    integer_volume_count: int = Field(ge=0, le=150)
    comma_integer_volume_count: int = Field(ge=0, le=150)
    decimal_volume_count: int = Field(ge=0, le=150)
    known_monthly_search_volume_total: Decimal = Field(ge=0)
    no_data_rate: Decimal = Field(ge=0, le=1, decimal_places=8)
    rejected_rows: tuple[MangoolsRejectedVolumeRow, ...] = ()
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
        if (
            self.known_volume_count
            + self.no_data_volume_count
            + self.rejected_volume_count
            != self.keyword_count
        ):
            raise ValueError("volume status counts must equal keyword_count")
        if (
            self.integer_volume_count
            + self.comma_integer_volume_count
            + self.decimal_volume_count
            != self.known_volume_count
        ):
            raise ValueError("known volume format counts must equal known_volume_count")
        if len(self.rejected_rows) != self.rejected_volume_count:
            raise ValueError("rejected_rows must match rejected_volume_count")
        expected_no_data_rate = (
            Decimal(self.no_data_volume_count) / Decimal(self.keyword_count)
        ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        if self.no_data_rate != expected_no_data_rate:
            raise ValueError("no_data_rate does not match no_data_volume_count")

        below_required = (
            self.known_monthly_search_volume_total < self.required_sessions_at_assumed_ctr
        )
        incomplete = self.no_data_volume_count > 0 or self.rejected_volume_count > 0
        if not below_required:
            expected = DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
        elif incomplete:
            expected = DemandCapacityDecision.KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE
        else:
            expected = DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE
        if self.capacity_decision is not expected:
            raise ValueError("capacity decision does not match the known volume floor")
        if self.scope_expansion_recommended is not below_required:
            raise ValueError("scope expansion recommendation does not match the known volume floor")
        return self


class MangoolsSlateDemandSafeSummary(StrictModel):
    """Safe aggregate for one frozen variable-length query slate."""

    schema_version: Literal["1.0"] = "1.0"
    provider: Literal["mangools_kwfinder_human_csv"] = "mangools_kwfinder_human_csv"
    country: Literal["JP"] = "JP"
    language: Literal["ja"] = "ja"
    acquisition_method: Literal["human_ui_export"] = "human_ui_export"
    raw_saved: Literal[False] = False
    query_values_saved: Literal[False] = False
    slate_id: str = Field(pattern=r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
    source_file_count: int = Field(ge=1, le=20)
    keyword_count: int = Field(ge=1, le=200)
    known_volume_count: int = Field(ge=0, le=200)
    no_data_volume_count: int = Field(ge=0, le=200)
    rejected_volume_count: int = Field(ge=0, le=200)
    integer_volume_count: int = Field(ge=0, le=200)
    comma_integer_volume_count: int = Field(ge=0, le=200)
    decimal_volume_count: int = Field(ge=0, le=200)
    known_monthly_search_volume_total: Decimal = Field(ge=0)
    no_data_rate: Decimal = Field(ge=0, le=1, decimal_places=8)
    rejected_rows: tuple[MangoolsSlateRejectedVolumeRow, ...] = ()
    observed_on: date
    next_review_on: date
    raw_csv_sha256: tuple[Sha256, ...] = Field(min_length=1, max_length=20)
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
        if self.source_file_count != len(self.raw_csv_sha256):
            raise ValueError("source_file_count must match raw_csv_sha256")
        if (
            self.known_volume_count
            + self.no_data_volume_count
            + self.rejected_volume_count
            != self.keyword_count
        ):
            raise ValueError("volume status counts must equal keyword_count")
        if (
            self.integer_volume_count
            + self.comma_integer_volume_count
            + self.decimal_volume_count
            != self.known_volume_count
        ):
            raise ValueError("known volume format counts must equal known_volume_count")
        if len(self.rejected_rows) != self.rejected_volume_count:
            raise ValueError("rejected_rows must match rejected_volume_count")
        expected_no_data_rate = (
            Decimal(self.no_data_volume_count) / Decimal(self.keyword_count)
        ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        if self.no_data_rate != expected_no_data_rate:
            raise ValueError("no_data_rate does not match no_data_volume_count")

        below_required = (
            self.known_monthly_search_volume_total < self.required_sessions_at_assumed_ctr
        )
        incomplete = self.no_data_volume_count > 0 or self.rejected_volume_count > 0
        if not below_required:
            expected = DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
        elif incomplete:
            expected = DemandCapacityDecision.KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE
        else:
            expected = DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE
        if self.capacity_decision is not expected:
            raise ValueError("capacity decision does not match the known volume floor")
        if self.scope_expansion_recommended is not below_required:
            raise ValueError(
                "scope expansion recommendation does not match the known volume floor"
            )
        return self


_EXPANSION_SET_SLATE_IDS = (
    "crm",
    "forms",
    "email_marketing",
    "seo_tools_v2_extension",
)


class MangoolsExpansionSetSafeSummary(StrictModel):
    """Safe aggregate envelope for the four remaining expansion slates."""

    schema_version: Literal["1.0"] = "1.0"
    provider: Literal["mangools_kwfinder_human_csv"] = "mangools_kwfinder_human_csv"
    acquisition_method: Literal["human_ui_export"] = "human_ui_export"
    raw_saved: Literal[False] = False
    query_values_saved: Literal[False] = False
    all_complete: Literal[True] = True
    slate_ids: tuple[
        Literal["crm"],
        Literal["forms"],
        Literal["email_marketing"],
        Literal["seo_tools_v2_extension"],
    ]
    summaries: tuple[
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
    ]
    total_keyword_count: Literal[180]
    total_known_volume_count: int = Field(ge=0, le=180)
    total_no_data_volume_count: int = Field(ge=0, le=180)
    total_rejected_volume_count: int = Field(ge=0, le=180)
    known_monthly_search_volume_total: Decimal = Field(ge=0)
    observed_on: date
    next_review_on: date

    @model_validator(mode="after")
    def validate_expansion_set(self) -> Self:
        if self.slate_ids != _EXPANSION_SET_SLATE_IDS:
            raise ValueError("expansion set slate_ids must match the frozen four-slate order")
        if tuple(summary.slate_id for summary in self.summaries) != self.slate_ids:
            raise ValueError("expansion summaries must match slate_ids in exact order")
        if tuple(summary.keyword_count for summary in self.summaries) != (40, 40, 40, 60):
            raise ValueError("expansion summaries must contain exact 40/40/40/60 query counts")
        if any(
            summary.observed_on != self.observed_on
            or summary.next_review_on != self.next_review_on
            for summary in self.summaries
        ):
            raise ValueError("expansion summaries must share one observation window")
        expected_counts = (
            sum(summary.known_volume_count for summary in self.summaries),
            sum(summary.no_data_volume_count for summary in self.summaries),
            sum(summary.rejected_volume_count for summary in self.summaries),
        )
        if expected_counts != (
            self.total_known_volume_count,
            self.total_no_data_volume_count,
            self.total_rejected_volume_count,
        ):
            raise ValueError("expansion aggregate counts must match its summaries")
        if sum(expected_counts) != self.total_keyword_count:
            raise ValueError("expansion aggregate counts must total 180")
        if self.known_monthly_search_volume_total != sum(
            (summary.known_monthly_search_volume_total for summary in self.summaries),
            start=Decimal(0),
        ):
            raise ValueError("expansion known volume total must match its summaries")
        return self


def build_mangools_expansion_set_safe_summary(
    summaries: tuple[
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
        MangoolsSlateDemandSafeSummary,
    ],
) -> MangoolsExpansionSetSafeSummary:
    """Build a fail-closed envelope only after all four exact slates validate."""

    if len(summaries) != 4:
        raise ValueError("expansion set requires exactly four complete summaries")
    observed_on = summaries[0].observed_on
    next_review_on = summaries[0].next_review_on
    return MangoolsExpansionSetSafeSummary(
        slate_ids=_EXPANSION_SET_SLATE_IDS,
        summaries=summaries,
        total_keyword_count=180,
        total_known_volume_count=sum(item.known_volume_count for item in summaries),
        total_no_data_volume_count=sum(item.no_data_volume_count for item in summaries),
        total_rejected_volume_count=sum(item.rejected_volume_count for item in summaries),
        known_monthly_search_volume_total=sum(
            (item.known_monthly_search_volume_total for item in summaries),
            start=Decimal(0),
        ),
        observed_on=observed_on,
        next_review_on=next_review_on,
    )


class MangoolsCsvError(ValueError):
    """Base class for structural CSV failures that still reject the whole file."""


class MangoolsCsvHeaderError(MangoolsCsvError):
    pass


class MangoolsCsvBomError(MangoolsCsvError):
    pass


class MangoolsCsvColumnMappingError(MangoolsCsvError):
    pass


_HEADER_ALIASES = {
    "keyword": frozenset({"keyword", "kw"}),
    "volume": frozenset(
        {
            "avg search volume",
            "avg. search volume",
            "avg search volume (last known values)",
            "avg. search volume (last known values)",
            "search volume",
            "sv",
        }
    ),
    "location": frozenset({"location", "country"}),
}
_JAPAN_VALUES = frozenset({"jp", "japan", "日本"})
_INTEGER_PATTERN = re.compile(r"^(?:0|[1-9]\d*)$")
_COMMA_INTEGER_PATTERN = re.compile(r"^(?:[1-9]\d{0,2})(?:,\d{3})+$")
_DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)\.\d+$")
_NO_DATA_VALUES = frozenset({"", "-", "—", "–", "n/a"})
_KNOWN_VOLUME_STATUSES = frozenset(
    {
        MangoolsVolumeStatus.INTEGER,
        MangoolsVolumeStatus.COMMA_INTEGER,
        MangoolsVolumeStatus.DECIMAL,
    }
)
_BOMS = (
    (codecs.BOM_UTF8, "UTF-8"),
    (codecs.BOM_UTF32_LE, "UTF-32 LE"),
    (codecs.BOM_UTF32_BE, "UTF-32 BE"),
    (codecs.BOM_UTF16_LE, "UTF-16 LE"),
    (codecs.BOM_UTF16_BE, "UTF-16 BE"),
)


def classify_mangools_volume(source_text: str) -> MangoolsVolumeClassification:
    """Classify one volume cell without inferring that missing data means zero."""

    stripped = source_text.strip()
    if stripped.casefold() in _NO_DATA_VALUES:
        return MangoolsVolumeClassification(
            status=MangoolsVolumeStatus.NO_DATA,
            source_text=source_text,
        )
    if _INTEGER_PATTERN.fullmatch(stripped):
        return MangoolsVolumeClassification(
            status=MangoolsVolumeStatus.INTEGER,
            source_text=source_text,
            normalized_volume=Decimal(stripped),
        )
    if _COMMA_INTEGER_PATTERN.fullmatch(stripped):
        return MangoolsVolumeClassification(
            status=MangoolsVolumeStatus.COMMA_INTEGER,
            source_text=source_text,
            normalized_volume=Decimal(stripped.replace(",", "")),
        )
    if _DECIMAL_PATTERN.fullmatch(stripped):
        return MangoolsVolumeClassification(
            status=MangoolsVolumeStatus.DECIMAL,
            source_text=source_text,
            normalized_volume=Decimal(stripped.replace(",", "")),
        )
    return MangoolsVolumeClassification(
        status=MangoolsVolumeStatus.REJECTED,
        source_text=source_text,
    )


def _normalized_header(value: str) -> str:
    return " ".join(value.replace("_", " ").strip().lower().split())


def _select_columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise MangoolsCsvHeaderError("header_mismatch: Mangools CSV has no header")
    if any(not value.strip() for value in fieldnames):
        raise MangoolsCsvHeaderError("header_mismatch: Mangools CSV has a blank header")
    normalized_names = [_normalized_header(value) for value in fieldnames]
    if len(normalized_names) != len(set(normalized_names)):
        raise MangoolsCsvHeaderError("header_mismatch: Mangools CSV has duplicate headers")
    normalized = dict(zip(normalized_names, fieldnames, strict=True))
    selected: dict[str, str] = {}
    for field, aliases in _HEADER_ALIASES.items():
        matches = [normalized[alias] for alias in aliases if alias in normalized]
        if len(matches) != 1:
            raise MangoolsCsvColumnMappingError(
                f"column_mapping_failed: Mangools CSV requires exactly one {field} column"
            )
        selected[field] = matches[0]
    return selected


def _reject_bom(raw: bytes) -> None:
    for marker, label in _BOMS:
        if raw.startswith(marker):
            raise MangoolsCsvBomError(f"bom_present: Mangools CSV contains a {label} BOM")


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
    _reject_bom(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MangoolsCsvError("encoding_error: Mangools CSV must be UTF-8") from exc

    reader = csv.DictReader(text.splitlines())
    columns = _select_columns(reader.fieldnames)
    expected_queries = {row.query for row in universe_rows}
    if len(expected_queries) != 150:
        raise ValueError("frozen universe must contain exactly 150 unique queries")

    observed_queries: set[str] = set()
    classifications: list[MangoolsVolumeClassification] = []
    rejected_rows: list[MangoolsRejectedVolumeRow] = []
    for number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Mangools CSV row {number} is malformed")
        query = normalize_query(row[columns["keyword"]])
        if not query:
            raise ValueError(f"Mangools CSV row {number} has a blank keyword")
        if query in observed_queries:
            raise ValueError("Mangools CSV contains duplicate normalized queries")
        if query not in expected_queries:
            raise ValueError("Mangools CSV query set differs from the frozen universe")
        observed_queries.add(query)
        location = " ".join(row[columns["location"]].strip().lower().split())
        if location not in _JAPAN_VALUES:
            raise ValueError("Mangools CSV must contain only Japan location rows")

        classification = classify_mangools_volume(row[columns["volume"]])
        classifications.append(classification)
        if classification.status is MangoolsVolumeStatus.REJECTED:
            rejected_rows.append(
                MangoolsRejectedVolumeRow(
                    line_number=number,
                    source_text=classification.source_text,
                )
            )

    if observed_queries != expected_queries:
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
    status_counts = {status: 0 for status in MangoolsVolumeStatus}
    known_total = Decimal("0")
    for classification in classifications:
        status_counts[classification.status] += 1
        if classification.status in _KNOWN_VOLUME_STATUSES:
            assert classification.normalized_volume is not None
            known_total += classification.normalized_volume
    known_count = sum(status_counts[status] for status in _KNOWN_VOLUME_STATUSES)
    no_data_count = status_counts[MangoolsVolumeStatus.NO_DATA]
    rejected_count = status_counts[MangoolsVolumeStatus.REJECTED]
    no_data_rate = (Decimal(no_data_count) / Decimal(150)).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )
    below_required = known_total < required_sessions
    incomplete = no_data_count > 0 or rejected_count > 0
    if not below_required:
        decision = DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
    elif incomplete:
        decision = DemandCapacityDecision.KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE
    else:
        decision = DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE

    return MangoolsDemandSafeSummary(
        keyword_count=150,
        known_volume_count=known_count,
        no_data_volume_count=no_data_count,
        rejected_volume_count=rejected_count,
        integer_volume_count=status_counts[MangoolsVolumeStatus.INTEGER],
        comma_integer_volume_count=status_counts[MangoolsVolumeStatus.COMMA_INTEGER],
        decimal_volume_count=status_counts[MangoolsVolumeStatus.DECIMAL],
        known_monthly_search_volume_total=known_total,
        no_data_rate=no_data_rate,
        rejected_rows=tuple(rejected_rows),
        observed_on=observed_on,
        next_review_on=next_review_on,
        raw_csv_sha256=hashlib.sha256(raw).hexdigest(),
        frozen_universe_sha256=universe_sha256,
        monthly_revenue_target_jpy=monthly_revenue_target_jpy,
        assumed_confirmed_epc_jpy=assumed_confirmed_epc_jpy,
        assumed_outbound_ctr=assumed_outbound_ctr,
        required_confirmed_outbound_clicks=required_clicks,
        required_sessions_at_assumed_ctr=required_sessions,
        capacity_decision=decision,
        scope_expansion_recommended=below_required,
    )


def validate_mangools_human_export_batches(
    csv_paths: tuple[Path, ...],
    *,
    slate_id: str,
    universe_rows: tuple[KeywordUniverseRow, ...],
    universe_sha256: str,
    observed_on: date,
    next_review_on: date,
    monthly_revenue_target_jpy: int = 200_000,
    assumed_confirmed_epc_jpy: Decimal = Decimal("60"),
    assumed_outbound_ctr: Decimal = Decimal("0.15"),
) -> MangoolsSlateDemandSafeSummary:
    """Validate one complete frozen slate split across Human-exported CSV files.

    Files are read once, locally. The result contains no query values and no raw
    rows; it retains only per-file hashes and aggregate volume classifications.
    """

    if not 1 <= len(csv_paths) <= 20:
        raise ValueError("Mangools slate export requires 1–20 CSV files")
    expected_queries = {normalize_query(row.query).casefold() for row in universe_rows}
    if not 1 <= len(expected_queries) <= 200:
        raise ValueError("frozen slate must contain 1–200 unique queries")
    if len(expected_queries) != len(universe_rows):
        raise ValueError("frozen slate contains duplicate normalized queries")

    observed_queries: set[str] = set()
    classifications: list[MangoolsVolumeClassification] = []
    rejected_rows: list[MangoolsSlateRejectedVolumeRow] = []
    raw_hashes: list[str] = []

    for batch_number, csv_path in enumerate(csv_paths, start=1):
        raw = csv_path.read_bytes()
        if not raw or len(raw) > 5_000_000:
            raise ValueError(
                f"Mangools CSV batch {batch_number} size must be between 1 byte and 5 MB"
            )
        _reject_bom(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MangoolsCsvError(
                f"encoding_error: Mangools CSV batch {batch_number} must be UTF-8"
            ) from exc

        reader = csv.DictReader(text.splitlines())
        columns = _select_columns(reader.fieldnames)
        batch_row_count = 0
        for line_number, row in enumerate(reader, start=2):
            batch_row_count += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"Mangools CSV batch {batch_number} row {line_number} is malformed"
                )
            query = normalize_query(row[columns["keyword"]]).casefold()
            if not query:
                raise ValueError(
                    f"Mangools CSV batch {batch_number} row {line_number} has a blank keyword"
                )
            if query in observed_queries:
                raise ValueError(
                    "Mangools CSV batches contain duplicate normalized queries"
                )
            if query not in expected_queries:
                raise ValueError(
                    "Mangools CSV batch query set differs from the frozen slate"
                )
            observed_queries.add(query)

            location = " ".join(row[columns["location"]].strip().lower().split())
            if location not in _JAPAN_VALUES:
                raise ValueError("Mangools CSV must contain only Japan location rows")

            classification = classify_mangools_volume(row[columns["volume"]])
            classifications.append(classification)
            if classification.status is MangoolsVolumeStatus.REJECTED:
                rejected_rows.append(
                    MangoolsSlateRejectedVolumeRow(
                        batch_number=batch_number,
                        line_number=line_number,
                        source_text=classification.source_text,
                    )
                )

        if batch_row_count == 0:
            raise ValueError(f"Mangools CSV batch {batch_number} has no data rows")
        raw_hashes.append(hashlib.sha256(raw).hexdigest())

    if observed_queries != expected_queries:
        raise ValueError(
            "Mangools CSV batches must match the complete frozen slate exactly; "
            f"observed {len(observed_queries)} of {len(expected_queries)} rows"
        )
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
    status_counts = {status: 0 for status in MangoolsVolumeStatus}
    known_total = Decimal("0")
    for classification in classifications:
        status_counts[classification.status] += 1
        if classification.status in _KNOWN_VOLUME_STATUSES:
            assert classification.normalized_volume is not None
            known_total += classification.normalized_volume
    known_count = sum(status_counts[status] for status in _KNOWN_VOLUME_STATUSES)
    no_data_count = status_counts[MangoolsVolumeStatus.NO_DATA]
    rejected_count = status_counts[MangoolsVolumeStatus.REJECTED]
    keyword_count = len(expected_queries)
    no_data_rate = (Decimal(no_data_count) / Decimal(keyword_count)).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )
    below_required = known_total < required_sessions
    incomplete = no_data_count > 0 or rejected_count > 0
    if not below_required:
        decision = DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
    elif incomplete:
        decision = DemandCapacityDecision.KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE
    else:
        decision = DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE

    return MangoolsSlateDemandSafeSummary(
        slate_id=slate_id,
        source_file_count=len(csv_paths),
        keyword_count=keyword_count,
        known_volume_count=known_count,
        no_data_volume_count=no_data_count,
        rejected_volume_count=rejected_count,
        integer_volume_count=status_counts[MangoolsVolumeStatus.INTEGER],
        comma_integer_volume_count=status_counts[MangoolsVolumeStatus.COMMA_INTEGER],
        decimal_volume_count=status_counts[MangoolsVolumeStatus.DECIMAL],
        known_monthly_search_volume_total=known_total,
        no_data_rate=no_data_rate,
        rejected_rows=tuple(rejected_rows),
        observed_on=observed_on,
        next_review_on=next_review_on,
        raw_csv_sha256=tuple(raw_hashes),
        frozen_universe_sha256=universe_sha256,
        monthly_revenue_target_jpy=monthly_revenue_target_jpy,
        assumed_confirmed_epc_jpy=assumed_confirmed_epc_jpy,
        assumed_outbound_ctr=assumed_outbound_ctr,
        required_confirmed_outbound_clicks=required_clicks,
        required_sessions_at_assumed_ctr=required_sessions,
        capacity_decision=decision,
        scope_expansion_recommended=below_required,
    )
