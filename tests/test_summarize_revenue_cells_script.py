from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_safe_aggregate_script_keeps_unknown_revenue_null(tmp_path: Path) -> None:
    row = json.loads((ROOT / "examples/revenue_cell_daily_aggregate.json").read_text())
    row.update({
        "traffic_scope": "external",
        "calculator_result_views": 3,
        "cta_views": 2,
        "cta_view_sessions": 2,
        "eligible_sessions": 2,
        "outbound_clicks": 1,
        "unique_outbound_sessions": 1,
    })
    source = tmp_path / "aggregate.json"
    source.write_text(json.dumps([row]), encoding="utf-8")
    result = subprocess.run(
        ["uv", "run", "python", "scripts/summarize_revenue_cells.py", "--input", str(source)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    assert output["included_rows"] == 1
    assert output["outbound_ctr_percent"] == "50.00"
    assert output["revenue_cell_version"] == "v2"
    assert output["confirmed_commission_minor"] is None
    assert output["confirmed_rpes_minor"] is None


def test_safe_aggregate_script_accepts_single_daily_row(tmp_path: Path) -> None:
    row = json.loads((ROOT / "examples/revenue_cell_daily_aggregate.json").read_text())
    row.update({
        "traffic_scope": "external",
        "calculator_result_views": 1,
        "cta_views": 1,
        "cta_view_sessions": 1,
        "eligible_sessions": 1,
        "outbound_clicks": 0,
        "unique_outbound_sessions": 0,
    })
    source = tmp_path / "single-daily-row.json"
    source.write_text(json.dumps(row), encoding="utf-8")
    result = subprocess.run(
        ["uv", "run", "python", "scripts/summarize_revenue_cells.py", "--input", str(source)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    assert output["included_rows"] == 1
    assert output["eligible_sessions"] == 1
    assert output["outbound_ctr_percent"] == "0.00"
