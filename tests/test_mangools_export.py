from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from saas_preflight.cli import run
from saas_preflight.keyword_universe import load_keyword_universe, summarize_keyword_universe
from saas_preflight.mangools_export import (
    DemandCapacityDecision,
    MangoolsCsvBomError,
    MangoolsCsvColumnMappingError,
    MangoolsCsvHeaderError,
    MangoolsSlateDemandSafeSummary,
    MangoolsVolumeStatus,
    classify_mangools_volume,
    validate_mangools_human_export,
    validate_mangools_human_export_batches,
)


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "examples" / "jp_ja_keyword_universe_v1.csv"
SERVER_SLATE_PATH = ROOT / "examples" / "jp_ja_keyword_slate_v2_servers.csv"


def _export(
    tmp_path: Path,
    *,
    volume: int | str | Decimal = 1000,
    location: str = "Japan",
    volume_header: str = "Avg. Search Volume",
    overrides: dict[int, int | str | Decimal] | None = None,
) -> Path:
    rows = load_keyword_universe(UNIVERSE_PATH, minimum_keywords=150, maximum_keywords=150)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=["Keyword", volume_header, "Location", "CPC", "PPC", "Keyword Difficulty"],
    )
    writer.writeheader()
    for index, row in enumerate(rows):
        value = (overrides or {}).get(index, volume)
        writer.writerow(
            {
                "Keyword": row.query,
                volume_header: value,
                "Location": location,
                "CPC": "",
                "PPC": "",
                "Keyword Difficulty": "",
            }
        )
    target = tmp_path / "mangools-human-export.csv"
    target.write_text(buffer.getvalue(), encoding="utf-8")
    return target


def _validate(path: Path):
    rows = load_keyword_universe(UNIVERSE_PATH, minimum_keywords=150, maximum_keywords=150)
    return validate_mangools_human_export(
        path,
        universe_rows=rows,
        universe_sha256=summarize_keyword_universe(rows).sha256,
        observed_on=date(2026, 7, 28),
        next_review_on=date(2026, 8, 28),
    )


def _slate_exports(tmp_path: Path, *, row_limit: int = 40) -> tuple[Path, ...]:
    rows = load_keyword_universe(
        SERVER_SLATE_PATH, minimum_keywords=40, maximum_keywords=40
    )[:row_limit]
    targets: list[Path] = []
    for batch_number, start in enumerate(range(0, len(rows), 15), start=1):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer,
            fieldnames=["Keyword", "Avg. Search Volume (Last Known Values)", "Location"],
        )
        writer.writeheader()
        for absolute_index, row in enumerate(rows[start : start + 15], start=start):
            if absolute_index == 0:
                volume: int | str | Decimal = ""
            elif absolute_index == 1:
                volume = "1,234"
            elif absolute_index == 2:
                volume = Decimal("12.5")
            else:
                volume = 1000
            writer.writerow(
                {
                    "Keyword": row.query.casefold(),
                    "Avg. Search Volume (Last Known Values)": volume,
                    "Location": "Japan",
                }
            )
        target = tmp_path / f"server-slate-{batch_number}.csv"
        target.write_text(buffer.getvalue(), encoding="utf-8")
        targets.append(target)
    return tuple(targets)


def _validate_slate(paths: tuple[Path, ...]) -> MangoolsSlateDemandSafeSummary:
    rows = load_keyword_universe(
        SERVER_SLATE_PATH, minimum_keywords=40, maximum_keywords=40
    )
    return validate_mangools_human_export_batches(
        paths,
        slate_id="servers",
        universe_rows=rows,
        universe_sha256=summarize_keyword_universe(rows).sha256,
        observed_on=date(2026, 8, 6),
        next_review_on=date(2026, 9, 4),
    )


def test_human_export_emits_only_safe_capacity_summary(tmp_path: Path) -> None:
    summary = _validate(_export(tmp_path, volume=1000))

    assert summary.schema_version == "1.1"
    assert summary.keyword_count == 150
    assert summary.known_volume_count == 150
    assert summary.no_data_volume_count == 0
    assert summary.rejected_volume_count == 0
    assert summary.known_monthly_search_volume_total == Decimal("150000")
    assert summary.no_data_rate == Decimal("0E-8")
    assert summary.required_confirmed_outbound_clicks == 3334
    assert summary.required_sessions_at_assumed_ctr == 22_227
    assert summary.capacity_decision is DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
    assert summary.scope_expansion_recommended is False
    assert summary.raw_saved is False
    assert summary.query_values_saved is False


def test_low_volume_recommends_scope_expansion_even_at_impossible_full_capture(tmp_path: Path) -> None:
    summary = _validate(_export(tmp_path, volume=100))

    assert summary.known_monthly_search_volume_total == Decimal("15000")
    assert summary.capacity_decision is DemandCapacityDecision.INSUFFICIENT_EVEN_AT_FULL_CAPTURE
    assert summary.scope_expansion_recommended is True


def test_rejects_non_japan_or_incomplete_query_set(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Japan"):
        _validate(_export(tmp_path, location="United States"))

    target = _export(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="150"):
        _validate(target)


def test_cli_output_contains_no_queries(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = _export(tmp_path)
    first_query = load_keyword_universe(UNIVERSE_PATH)[0].query
    assert run([
        "validate-mangools-export",
        str(target),
        "--universe",
        str(UNIVERSE_PATH),
        "--observed-on",
        "2026-07-28",
        "--next-review-on",
        "2026-08-28",
    ]) == 0
    output = capsys.readouterr().out
    assert first_query not in output
    assert '"query_values_saved": false' in output
    assert '"known_monthly_search_volume_total": "150000"' in output


def test_assumptions_are_explicit_and_adjustable(tmp_path: Path) -> None:
    rows = load_keyword_universe(UNIVERSE_PATH)
    summary = validate_mangools_human_export(
        _export(tmp_path),
        universe_rows=rows,
        universe_sha256=summarize_keyword_universe(rows).sha256,
        observed_on=date(2026, 7, 28),
        next_review_on=date(2026, 8, 28),
        monthly_revenue_target_jpy=200_000,
        assumed_confirmed_epc_jpy=Decimal("100"),
        assumed_outbound_ctr=Decimal("0.20"),
    )
    assert summary.required_confirmed_outbound_clicks == 2000
    assert summary.required_sessions_at_assumed_ctr == 10_000


def test_volume_cells_are_classified_without_losing_source_text() -> None:
    integer = classify_mangools_volume("100")
    comma = classify_mangools_volume("1,234")
    decimal = classify_mangools_volume("1,234.50")
    no_data = classify_mangools_volume("N/A")
    rejected = classify_mangools_volume("about 20")

    assert (integer.status, integer.normalized_volume) == (
        MangoolsVolumeStatus.INTEGER,
        Decimal("100"),
    )
    assert comma.status is MangoolsVolumeStatus.COMMA_INTEGER
    assert comma.source_text == "1,234"
    assert comma.normalized_volume == Decimal("1234")
    assert decimal.status is MangoolsVolumeStatus.DECIMAL
    assert decimal.source_text == "1,234.50"
    assert decimal.normalized_volume == Decimal("1234.50")
    assert no_data.status is MangoolsVolumeStatus.NO_DATA
    assert no_data.normalized_volume is None
    assert rejected.status is MangoolsVolumeStatus.REJECTED
    assert rejected.source_text == "about 20"


def test_no_data_and_rejected_volume_rows_remain_in_the_safe_summary(tmp_path: Path) -> None:
    target = _export(
        tmp_path,
        volume=100,
        overrides={0: "", 1: "—", 2: "N/A", 3: "about 20", 4: "1,234", 5: "12.5"},
    )

    summary = _validate(target)

    assert summary.known_volume_count == 146
    assert summary.no_data_volume_count == 3
    assert summary.rejected_volume_count == 1
    assert summary.integer_volume_count == 144
    assert summary.comma_integer_volume_count == 1
    assert summary.decimal_volume_count == 1
    assert summary.known_monthly_search_volume_total == Decimal("15646.5")
    assert summary.no_data_rate == Decimal("0.02000000")
    assert summary.rejected_rows[0].line_number == 5
    assert summary.rejected_rows[0].source_text == "about 20"
    assert (
        summary.capacity_decision
        is DemandCapacityDecision.KNOWN_VOLUME_FLOOR_BELOW_REQUIRED_INCOMPLETE
    )
    assert summary.scope_expansion_recommended is True


def test_actual_kwfinder_last_known_volume_header_is_mapped(tmp_path: Path) -> None:
    summary = _validate(
        _export(
            tmp_path,
            volume=100,
            volume_header="Avg. Search Volume (Last Known Values)",
        )
    )

    assert summary.known_volume_count == 150


def test_bom_header_and_column_mapping_fail_with_distinct_errors(tmp_path: Path) -> None:
    bom_target = _export(tmp_path)
    bom_target.write_bytes(b"\xef\xbb\xbf" + bom_target.read_bytes())
    with pytest.raises(MangoolsCsvBomError, match="bom_present"):
        _validate(bom_target)

    header_target = tmp_path / "duplicate-header.csv"
    header_target.write_text("Keyword,Keyword,Location\na,b,Japan\n", encoding="utf-8")
    with pytest.raises(MangoolsCsvHeaderError, match="header_mismatch"):
        _validate(header_target)

    mapping_target = tmp_path / "mapping.csv"
    mapping_target.write_text("Keyword,Metric,Location\na,10,Japan\n", encoding="utf-8")
    with pytest.raises(MangoolsCsvColumnMappingError, match="column_mapping_failed"):
        _validate(mapping_target)


def test_variable_slate_batches_emit_one_complete_safe_summary(tmp_path: Path) -> None:
    summary = _validate_slate(_slate_exports(tmp_path))

    assert summary.schema_version == "1.0"
    assert summary.slate_id == "servers"
    assert summary.source_file_count == 3
    assert summary.keyword_count == 40
    assert summary.known_volume_count == 39
    assert summary.no_data_volume_count == 1
    assert summary.rejected_volume_count == 0
    assert summary.integer_volume_count == 37
    assert summary.comma_integer_volume_count == 1
    assert summary.decimal_volume_count == 1
    assert summary.known_monthly_search_volume_total == Decimal("38246.5")
    assert summary.no_data_rate == Decimal("0.02500000")
    assert len(summary.raw_csv_sha256) == 3
    assert summary.capacity_decision is DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
    assert summary.raw_saved is False
    assert summary.query_values_saved is False


def test_variable_slate_batches_fail_closed_when_incomplete(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="observed 30 of 40"):
        _validate_slate(_slate_exports(tmp_path, row_limit=30))


def test_variable_slate_cli_emits_no_queries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _slate_exports(tmp_path)
    first_query = load_keyword_universe(
        SERVER_SLATE_PATH, minimum_keywords=40, maximum_keywords=40
    )[0].query

    assert run(
        [
            "validate-mangools-slate-export",
            *(str(path) for path in paths),
            "--slate-id",
            "servers",
            "--universe",
            str(SERVER_SLATE_PATH),
            "--observed-on",
            "2026-08-06",
            "--next-review-on",
            "2026-09-04",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert first_query not in output
    assert '"query_values_saved": false' in output
    assert '"keyword_count": 40' in output
