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
EXPANSION_SLATES = {
    "seo_tools_v2": (
        ROOT / "examples" / "jp_ja_keyword_universe_v2_seo_extension.csv",
        60,
        "4e1930a108569222ff91afcc0d5aecc716765514d3ae3a769b0cfa86028a7b7d",
    ),
    "servers": (
        ROOT / "examples" / "jp_ja_keyword_slate_v2_servers.csv",
        40,
        "a826707c61169a9efebc3bb4838cee624035d04f19b98b52d508a0c96f9e8ee1",
    ),
    "accounting": (
        ROOT / "examples" / "jp_ja_keyword_slate_v2_accounting.csv",
        40,
        "9bc33b2c63c31f5d22a67cfa2f52bf7e1ef36e36b586bddfe4030c1102907c4e",
    ),
    "crm": (
        ROOT / "examples" / "jp_ja_keyword_slate_v2_crm.csv",
        40,
        "b7bcc093aa85bda86d16a915dd83f5f1a50993afb6a429d71a2f28c0d98ceca3",
    ),
    "forms": (
        ROOT / "examples" / "jp_ja_keyword_slate_v2_forms.csv",
        40,
        "2ea8dacda2813cbf1752b9886a1888e226acb50b763571a0976c436175b0f68d",
    ),
    "email_marketing": (
        ROOT / "examples" / "jp_ja_keyword_slate_v2_email_marketing.csv",
        40,
        "1cd09f8281e0227b9e614f7da6b65a763c83920fcec434402f9bab6105539219",
    ),
}
BRAND_SERVER_SLATE = (
    ROOT / "examples" / "jp_ja_keyword_slate_v3_brand_servers.csv"
)


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


def test_scope_expansion_query_slates_are_frozen_safe_and_disjoint() -> None:
    original_queries = {row.query for row in load_keyword_universe(UNIVERSE)}
    seen_queries: set[str] = set()

    for slate_id, (path, expected_count, expected_sha256) in EXPANSION_SLATES.items():
        minimum = 50 if slate_id == "seo_tools_v2" else 30
        maximum = 100 if slate_id == "seo_tools_v2" else 50
        rows = load_keyword_universe(
            path,
            minimum_keywords=minimum,
            maximum_keywords=maximum,
        )
        summary = summarize_keyword_universe(rows)
        queries = {row.query for row in rows}

        assert summary.universe_version == "jp-ja-v2"
        assert summary.keyword_count == expected_count
        assert summary.sha256 == expected_sha256
        assert not queries.intersection(original_queries)
        assert not queries.intersection(seen_queries)
        if slate_id == "seo_tools_v2":
            assert dict(summary.intent_counts) == {"category": 30, "comparison": 30}
        else:
            assert dict(summary.intent_counts) == {
                "category": 10,
                "comparison": 10,
                "fit": 10,
                "pricing": 10,
            }
        seen_queries.update(queries)


def test_brand_server_slate_is_frozen_and_matches_published_vendor_scope() -> None:
    rows = load_keyword_universe(
        BRAND_SERVER_SLATE,
        minimum_keywords=30,
        maximum_keywords=30,
    )
    summary = summarize_keyword_universe(rows)
    generic_server_queries = {
        row.query
        for row in load_keyword_universe(
            EXPANSION_SLATES["servers"][0], minimum_keywords=30, maximum_keywords=50
        )
    }

    assert summary.universe_version == "jp-ja-v3"
    assert summary.keyword_count == 30
    assert summary.sha256 == (
        "f16005b8bf6acdd06627a0b2a7787c372a3a441cf372876d89e3f3785d43726b"
    )
    assert dict(summary.intent_counts) == {"brand": 30}
    assert dict(summary.vendor_counts) == {
        "ablenet": 3,
        "conoha-wing": 5,
        "kagoya": 4,
        "lolipop": 3,
        "onamae-rental-server": 3,
        "sakura-rental-server": 4,
        "shin-rental-server": 3,
        "xserver-business": 5,
    }
    assert not {row.query for row in rows}.intersection(generic_server_queries)


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
