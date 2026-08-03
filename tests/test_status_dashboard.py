from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from saas_preflight.editorial_input import (
    EditorialArticleInput,
    EditorialBillingToggleState,
    EditorialCurrencyStatus,
    EditorialReviewStatus,
    EditorialScopeKind,
    EditorialSaleBannerState,
    EditorialValueKind,
    EditorialValueStatus,
    HumanEditorialNumericField,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_status_dashboard.py"
START = "// DASHBOARD_DATA_START\nconst DATA = "
END = ";\n// DASHBOARD_DATA_END"
CSV_FIELDS = (
    "period",
    "indexed_articles",
    "gsc_clicks",
    "outbound_clicks",
    "confirmed_commissions_yen",
    "sessions",
    "qualified_sessions",
    "confirmed_conversions",
    "pending_commissions_yen",
)


def _dashboard_data(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    raw = source.split(START, 1)[1].split(END, 1)[0]
    return json.loads(raw)


def _run(dashboard: Path, state: Path, contracts: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--launch-state",
            str(state),
            "--contracts-dir",
            str(contracts),
            "--as-of",
            "2026-07-29",
            *extra,
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_dashboard_uses_safe_csv_totals_and_repo_work_queue(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    state.write_bytes((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_bytes())
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    kpi_csv = tmp_path / "monthly.csv"
    with kpi_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "period": "2026-07",
                "indexed_articles": 2,
                "gsc_clicks": 3,
                "outbound_clicks": 4,
                "confirmed_commissions_yen": 500,
                "sessions": 6,
                "qualified_sessions": 5,
                "confirmed_conversions": 1,
                "pending_commissions_yen": 20,
            }
        )
    result = _run(dashboard, state, contracts, "--kpi-csv", str(kpi_csv))
    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    assert data["reportingPeriod"] == "2026-07"
    assert {item["label"]: item["value"] for item in data["kpis"]} == {
        "公開記事数": 0,
        "インデックス数": 2,
        "GSC clicks(月)": 3,
        "Outbound clicks(月)": 4,
        "確定報酬(月)": 500,
    }
    assert len(data["work"]) == 9
    assert all(item["done"] for item in data["work"])
    assert data["launchQuarter"]["humanBudgetMinutesPerMonth"] == 2000
    assert data["launchQuarter"]["decisionDate"] == "2026-10-31"
    assert [item["tier"] for item in data["launchQuarter"]["thresholds"]] == [
        "拡張", "継続", "最低ライン"
    ]
    assert "monthly.csv" not in dashboard.read_text(encoding="utf-8")


def test_only_valid_contract_and_matching_approval_count_as_publishable(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    raw_state = json.loads((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_text(encoding="utf-8"))
    raw_state["articles"]["P12"] = "approved"
    raw_state["index_state"] = "GO"
    state = tmp_path / "state.json"
    state.write_text(json.dumps(raw_state), encoding="utf-8")
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    contract = EditorialArticleInput(
        article_id="P12",
        slug="evidence-method",
        title="根拠の検証",
        numeric_fields=(
            HumanEditorialNumericField(
                scope_kind=EditorialScopeKind.VENDOR_PLAN,
                vendor_id="example-vendor",
                plan_id="standard",
                field="evidence.review_interval_days",
                value_kind=EditorialValueKind.DURATION,
                value_status=EditorialValueStatus.KNOWN,
                value=Decimal("90"),
                unit="日",
                currency_status=EditorialCurrencyStatus.NOT_APPLICABLE,
                billing_toggle_state=EditorialBillingToggleState.NOT_PRESENT,
                sale_banner_state=EditorialSaleBannerState.NONE,
                observed_price_basis=None,
                derived_monthly_value=None,
                derived_monthly_unit=None,
                derivation_method=None,
                source_url="https://example.com/pricing",
                observed_on=date(2026, 7, 29),
                next_review_on=date(2026, 10, 27),
                acquisition_method="manual_public_page",
            ),
        ),
        article_review_status=EditorialReviewStatus.UNREVIEWED,
    )
    (contracts / "P12-editorial-input.json").write_text(
        contract.model_dump_json(indent=2), encoding="utf-8"
    )
    result = _run(dashboard, state, contracts, "--no-prompt")
    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    assert data["kpis"][0]["value"] == 0
    assert data["lane"][1]["status"] == "1/12入力・0/12承認"

    approved_contract = contract.model_copy(
        update={"article_review_status": EditorialReviewStatus.APPROVED}
    )
    (contracts / "P12-editorial-input.json").write_text(
        approved_contract.model_dump_json(indent=2), encoding="utf-8"
    )
    result = _run(dashboard, state, contracts, "--no-prompt")
    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    assert data["kpis"][0]["value"] == 1
    assert data["lane"][1]["status"] == "1/12入力・1/12承認"


def test_csv_with_unapproved_extra_column_is_rejected(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    state.write_bytes((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_bytes())
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        ",".join((*CSV_FIELDS, "tracking_id")) + "\n"
        + ",".join(("2026-07", *("0" for _ in CSV_FIELDS[1:]), "secret")) + "\n",
        encoding="utf-8",
    )
    result = _run(dashboard, state, contracts, "--kpi-csv", str(bad_csv))
    assert result.returncode != 0
    assert "safe template" in result.stderr
