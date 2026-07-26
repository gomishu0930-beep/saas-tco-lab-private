from __future__ import annotations

from pathlib import Path

import pytest

from saas_preflight.cli import run
from saas_preflight.keyword_universe import (
    EXPECTED_COLUMNS,
    load_keyword_universe,
    normalize_query,
    summarize_keyword_universe,
)


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "examples" / "jp_ja_keyword_universe_v1.csv"


def test_checked_in_keyword_universe_is_frozen_and_safe() -> None:
    rows = load_keyword_universe(UNIVERSE)
    summary = summarize_keyword_universe(rows)

    assert summary.universe_version == "jp-ja-v1"
    assert summary.country == "JP"
    assert summary.language == "ja"
    assert summary.keyword_count == 150
    assert summary.cluster_count >= 20
    assert len(summary.sha256) == 64
    assert dict(summary.vendor_counts) == {
        "generic": 110,
        "hubspot": 8,
        "mangools": 8,
        "se-ranking": 8,
        "semrush": 8,
        "serpstat": 8,
    }


def test_summary_hash_is_input_order_independent() -> None:
    rows = load_keyword_universe(UNIVERSE)
    assert summarize_keyword_universe(rows).sha256 == summarize_keyword_universe(
        tuple(reversed(rows))
    ).sha256


def test_cli_emits_hash_only_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["validate-keyword-universe", str(UNIVERSE)]) == 0
    output = capsys.readouterr().out
    assert '"keyword_count": 150' in output
    assert '"country": "JP"' in output
    assert "SEO ツール" not in output


@pytest.mark.parametrize(
    "bad_query",
    [
        "person@example.com SEO",
        "https://example.com SEO",
        "090-1234-5678 SEO",
        "123456789 SEO",
    ],
)
def test_rejects_pii_url_or_identifier(tmp_path: Path, bad_query: str) -> None:
    rows = load_keyword_universe(UNIVERSE)
    source = UNIVERSE.read_text(encoding="utf-8")
    source = source.replace(rows[0].query, bad_query, 1)
    target = tmp_path / "unsafe.csv"
    target.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="PII|URL|identifier"):
        load_keyword_universe(target)


def test_rejects_normalized_duplicate(tmp_path: Path) -> None:
    source = UNIVERSE.read_text(encoding="utf-8")
    lines = source.splitlines()
    first = lines[1].split(",")
    second = lines[2].split(",")
    second[-1] = f"  {first[-1]}  "
    lines[2] = ",".join(second)
    target = tmp_path / "duplicate.csv"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicates"):
        load_keyword_universe(target)


def test_rejects_wrong_columns(tmp_path: Path) -> None:
    target = tmp_path / "columns.csv"
    target.write_text("query,country\nSEO ツール,JP\n", encoding="utf-8")

    with pytest.raises(ValueError, match="columns"):
        load_keyword_universe(target, minimum_keywords=1)


def test_normalization_is_conservative() -> None:
    assert normalize_query("  ＳＥＯ   ツール  ") == "SEO ツール"
    assert EXPECTED_COLUMNS[-1] == "query"
