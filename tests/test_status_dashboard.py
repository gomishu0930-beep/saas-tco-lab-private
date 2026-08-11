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
    assert len(data["work"]) == 12
    assert all(item["done"] for item in data["work"])
    assert any(item["label"] == "SVR01–SVR20 noindex候補view" for item in data["work"])
    assert any(item["label"] == "servers 20記事候補一覧" for item in data["work"])
    assert [item["priority"] for item in data["externalActions"]] == [1, 2]
    assert data["externalActions"][0] == {
        "priority": 1,
        "label": "KWFinder拡張需要の残り150語をHuman export",
        "status": "human_export_required",
        "token": "mangools_category_csv: done crm,forms,email_marketing,seo_tools_v2_extension",
    }
    assert data["externalActions"][1]["status"] == "contract_input_required"
    assert all(
        item["status"] != "human_field_attestation_required"
        for item in data["externalActions"]
    )
    assert all(
        not item["token"].startswith("article_approve:")
        for item in data["externalActions"]
    )
    assert all("独自domain未取得" not in item["label"] for item in data["risks"])
    assert all("JP/ja需要規模が未検証" not in item["label"] for item in data["risks"])
    assert any(item.get("riskId") == "editorial-coverage" for item in data["risks"])
    assert any(item.get("riskId") == "server-candidate-only" for item in data["risks"])
    assert data["launchQuarter"]["humanBudgetMinutesPerMonth"] == 2000
    assert data["launchQuarter"]["decisionDate"] == "2026-10-31"
    assert data["launchQuarter"]["scopeExpansion"] == {
        "state": "PREPARATION GO",
        "observedKnownVolume": 9610,
        "requiredSessions": 22227,
        "noDataRate": "77.33%",
        "frozenQueries": 260,
        "externalActions": "HOLD",
    }
    assert [item["tier"] for item in data["launchQuarter"]["thresholds"]] == [
        "拡張", "継続", "最低ライン"
    ]
    assert data["serverPartnerPolicy"] == {
        "approvedPartnerCount": 3,
        "ctaMode": "comparison",
        "dependencyStatus": "confirmed_commission_share_unobserved",
        "dominantSharePercent": None,
        "warningThresholdPercent": 80,
        "warning": False,
        "individualCtaGateRequired": True,
    }
    semrush = next(partner for partner in data["partners"] if partner["name"] == "Semrush")
    assert semrush == {
        "name": "Semrush",
        "affiliate": "Impact Marketplace却下済み(8/9確認)",
        "affStatus": "warn",
        "rights": "自動取得系prohibited / editorial条件付き可",
        "next": "流入実績形成後に新しいexact GOで再評価",
    }
    assert data["launchQuarter"]["exitLine"] == {
        "decisionDate": "2026-12-31",
        "publishedArticlesMinimum": 20,
        "gscClicksPerMonthMinimum": 300,
        "confirmedConversionsMinimum": 1,
        "allConditionsRequired": True,
        "thresholdCanBeRelaxed": False,
        "pivotCandidates": ["embed配布", "note有料", "受託"],
    }
    assert data["deadlines"][-1]["date"] == "2026-12-31"
    assert "monthly.csv" not in dashboard.read_text(encoding="utf-8")


def test_only_valid_contract_and_matching_approval_count_as_publishable(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    raw_state = json.loads((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_text(encoding="utf-8"))
    raw_state["articles"]["P12"] = "approved"
    raw_state["deployed_articles"].remove("P12")
    raw_state["index_approved_articles"].remove("P12")
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
    assert data["kpis"][0]["value"] == 0
    assert data["lane"][1]["status"] == "1/12入力・1/12承認"

    raw_state["deployed_articles"].append("P12")
    raw_state["index_approved_articles"].append("P12")
    state.write_text(json.dumps(raw_state), encoding="utf-8")
    result = _run(dashboard, state, contracts, "--no-prompt")
    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    assert data["kpis"][0]["value"] == 1


def test_pending_p06_p07_review_cards_are_contract_driven(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    state.write_bytes((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_bytes())
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    for article_id in ("P06", "P07"):
        source = ROOT / "artifacts" / "editorial-inputs" / f"{article_id}-editorial-input.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["article_review_status"] = "unreviewed"
        for field in raw["numeric_fields"]:
            field["review_status"] = "unreviewed"
        (contracts / source.name).write_text(json.dumps(raw), encoding="utf-8")

    result = _run(dashboard, state, contracts, "--no-prompt")

    assert result.returncode == 0, result.stderr
    cards = _dashboard_data(dashboard)["articleReviews"]
    assert [card["articleId"] for card in cards] == ["P06", "P07"]
    assert cards[0]["confirmed"] == [
        "月払い: 61.00 / mo USD",
        "年次checkout総額: 452.40 / yr（checkout請求総額） USD",
        "最低契約期間: 12 か月（年次請求）",
    ]
    assert cards[0]["unresolved"][0].startswith("途中解約費用: unknown")
    assert cards[0]["nextReviewOn"] == "2026-08-31"
    assert cards[1]["confirmed"] == [
        "含有利用量: 100 keyword research req. / 24h",
        "Human月間利用量: 400 ルックアップ/月",
    ]
    assert len(cards[1]["notApplicable"]) == 2
    assert cards[1]["unresolved"] == []
    assert cards[1]["reviewState"] == "approval_ready"
    assert cards[1]["token"] == "article_approve: P07"


def test_approved_p05_contract_is_not_returned_to_the_human_review_queue(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    state.write_bytes((ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_bytes())
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = ROOT / "artifacts" / "editorial-inputs" / "P05-editorial-input.json"
    (contracts / source.name).write_bytes(source.read_bytes())

    result = _run(dashboard, state, contracts, "--no-prompt")

    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    assert data["articleReviews"] == []
    assert all(
        action["status"] != "human_field_scope_review_required"
        for action in data["externalActions"]
    )


def test_explicit_not_applicable_policy_is_ready_for_human_article_review(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    raw_state = json.loads(
        (ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_text(encoding="utf-8")
    )
    raw_state["deployed_articles"].remove("P12")
    raw_state["index_approved_articles"].remove("P12")
    raw_state["articles"]["P12"] = "unreviewed"
    state.write_text(json.dumps(raw_state), encoding="utf-8")
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = ROOT / "artifacts" / "editorial-inputs" / "P12-editorial-input.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["article_review_status"] = "unreviewed"
    raw["numeric_fields"][0]["review_status"] = "unreviewed"
    (contracts / source.name).write_text(json.dumps(raw), encoding="utf-8")

    result = _run(dashboard, state, contracts, "--no-prompt")

    assert result.returncode == 0, result.stderr
    data = _dashboard_data(dashboard)
    card = data["articleReviews"][0]
    assert card["articleId"] == "P12"
    assert card["reviewState"] == "approval_ready"
    assert card["token"] == "article_approve: P12"
    assert card["confirmed"] == []
    assert card["notApplicable"] == [
        "根拠確認間隔: 対象外（全field共通の単一確認間隔は適用せず、各観測の次回確認日を個別に管理する運用方針のため）"
    ]
    assert not any(
        action["status"] == "evidence_required"
        for action in data["externalActions"]
    )


def test_approved_undeployed_contract_requires_exact_production_go(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_bytes((ROOT / "status-dashboard.html").read_bytes())
    state = tmp_path / "state.json"
    launch_state = json.loads(
        (ROOT / "docs/EDITORIAL_LAUNCH_STATE.json").read_text(encoding="utf-8")
    )
    launch_state["deployed_articles"].remove("P04")
    launch_state["index_approved_articles"].remove("P04")
    state.write_text(json.dumps(launch_state), encoding="utf-8")
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    source = ROOT / "artifacts" / "editorial-inputs" / "P04-editorial-input.json"
    (contracts / source.name).write_bytes(source.read_bytes())

    result = _run(dashboard, state, contracts, "--no-prompt")

    assert result.returncode == 0, result.stderr
    release = next(
        action
        for action in _dashboard_data(dashboard)["externalActions"]
        if action["status"] == "production_go_required"
    )
    assert release["label"] == "P04のproduction release"
    assert release["token"] == "deploy_update: GO P04 / HOLD"


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


def test_risk_register_is_sanitized_and_has_exactly_one_hundred_risks() -> None:
    source = (ROOT / "docs/RISK_REGISTER_100.md").read_text(encoding="utf-8")
    risk_ids = [f"C{number:03d}" for number in range(1, 101)]

    assert "sanitization_authority: `human_authorized_sanitization`" in source
    assert "review_status: `unreviewed`" in source
    assert all(source.count(f"|{risk_id}|") == 1 for risk_id in risk_ids)
    assert "restricted_dashboard_only" not in source
    assert "年間20万円超" not in source
    assert "最低賃金" not in source
    assert "月次固定費が3,000円超" not in source
    assert "内部IPフィルタをactive化" not in source
    assert "tracking ID、広告URL" in source
