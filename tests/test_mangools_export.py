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
    validate_mangools_human_export,
)


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "examples" / "jp_ja_keyword_universe_v1.csv"


def _export(tmp_path: Path, *, volume: int = 1000, location: str = "Japan") -> Path:
    rows = load_keyword_universe(UNIVERSE_PATH, minimum_keywords=150, maximum_keywords=150)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["Keyword", "Avg. Search Volume", "Location", "CPC", "PPC", "Keyword Difficulty"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"Keyword": row.query, "Avg. Search Volume": volume, "Location": location, "CPC": "", "PPC": "", "Keyword Difficulty": ""})
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


def test_human_export_emits_only_safe_capacity_summary(tmp_path: Path) -> None:
    summary = _validate(_export(tmp_path, volume=1000))

    assert summary.keyword_count == 150
    assert summary.total_monthly_search_volume == 150_000
    assert summary.required_confirmed_outbound_clicks == 3334
    assert summary.required_sessions_at_assumed_ctr == 22_227
    assert summary.capacity_decision is DemandCapacityDecision.VOLUME_FLOOR_MET_NOT_PROVEN
    assert summary.scope_expansion_recommended is False
    assert summary.raw_saved is False
    assert summary.query_values_saved is False


def test_low_volume_recommends_scope_expansion_even_at_impossible_full_capture(tmp_path: Path) -> None:
    summary = _validate(_export(tmp_path, volume=100))

    assert summary.total_monthly_search_volume == 15_000
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
    assert '"total_monthly_search_volume": 150000' in output


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
