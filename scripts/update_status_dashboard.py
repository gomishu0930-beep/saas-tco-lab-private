#!/usr/bin/env python3
"""Regenerate the local dashboard from repository state and optional safe KPI input."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from saas_preflight.editorial_input import EditorialArticleInput


ROOT = Path(__file__).resolve().parents[1]
PILOT_IDS = tuple(f"P{number:02d}" for number in range(1, 13))
DATA_START = "// DASHBOARD_DATA_START\nconst DATA = "
DATA_END = ";\n// DASHBOARD_DATA_END"
ALLOWED_LANE_STATES = frozenset({"HOLD", "GO", "DONE"})
ALLOWED_ARTICLE_STATES = frozenset({"unreviewed", "approved", "rejected"})
KPI_FIELDS = (
    "indexed_articles",
    "gsc_clicks",
    "outbound_clicks",
    "confirmed_commissions_yen",
    "sessions",
    "qualified_sessions",
    "confirmed_conversions",
    "pending_commissions_yen",
)
CSV_FIELDS = ("period", *KPI_FIELDS)


class DashboardInputError(ValueError):
    """A local state or monthly drop cannot safely update the dashboard."""


def _split_dashboard(source: str) -> tuple[str, dict[str, Any], str]:
    if source.count(DATA_START) != 1 or source.count(DATA_END) != 1:
        raise DashboardInputError("dashboard must contain one exact DATA boundary")
    before, remainder = source.split(DATA_START, 1)
    raw_data, after = remainder.split(DATA_END, 1)
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise DashboardInputError("dashboard DATA must be strict JSON") from exc
    if not isinstance(data, dict):
        raise DashboardInputError("dashboard DATA must be an object")
    return before, data, after


def _load_launch_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardInputError("editorial launch state is unreadable") from exc
    expected = {
        "schema_version", "domain", "domain_state", "index_state", "affiliate_cta", "articles"
    }
    if not isinstance(state, dict) or set(state) != expected:
        raise DashboardInputError("editorial launch state fields do not match ease-track-1")
    if state["schema_version"] != "ease-track-1":
        raise DashboardInputError("unknown editorial launch state version")
    if state["domain_state"] not in ALLOWED_LANE_STATES or state["index_state"] not in ALLOWED_LANE_STATES:
        raise DashboardInputError("domain/index state must be HOLD, GO, or DONE")
    if state["domain"] is not None:
        if not isinstance(state["domain"], str) or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", state["domain"]
        ):
            raise DashboardInputError("domain state contains an invalid public hostname")
    articles = state["articles"]
    if not isinstance(articles, dict) or tuple(sorted(articles)) != PILOT_IDS:
        raise DashboardInputError("launch state must contain exact P01-P12 article keys")
    if any(value not in ALLOWED_ARTICLE_STATES for value in articles.values()):
        raise DashboardInputError("article state must be unreviewed, approved, or rejected")
    cta = state["affiliate_cta"]
    if not isinstance(cta, dict) or any(value not in ALLOWED_LANE_STATES for value in cta.values()):
        raise DashboardInputError("affiliate CTA states must be HOLD, GO, or DONE")
    return state


def _load_contracts(directory: Path) -> dict[str, EditorialArticleInput]:
    contracts: dict[str, EditorialArticleInput] = {}
    if not directory.exists():
        return contracts
    for path in sorted(directory.glob("*.json")):
        try:
            contract = EditorialArticleInput.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise DashboardInputError(f"invalid editorial contract: {path.name}") from exc
        if contract.article_id in contracts:
            raise DashboardInputError(f"duplicate editorial contract: {contract.article_id}")
        if not contract.numeric_fields:
            raise DashboardInputError(f"editorial contract has no numeric fields: {path.name}")
        contracts[contract.article_id] = contract
    return contracts


def _non_negative_integer(raw: str, field: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", raw.strip()):
        raise DashboardInputError(f"{field} must be a non-negative integer")
    return int(raw)


def _validate_period(raw: str) -> str:
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})", raw.strip())
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise DashboardInputError("period must use YYYY-MM")
    return raw.strip()


def _load_kpi_csv(path: Path) -> dict[str, Any]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise DashboardInputError("monthly KPI CSV header does not match the safe template")
            rows = list(reader)
    except OSError as exc:
        raise DashboardInputError("monthly KPI CSV is unreadable") from exc
    if len(rows) != 1:
        raise DashboardInputError("monthly KPI CSV must contain exactly one data row")
    row = rows[0]
    values: dict[str, Any] = {"period": _validate_period(row["period"])}
    values.update({field: _non_negative_integer(row[field], field) for field in KPI_FIELDS})
    return values


def _current_external(data: dict[str, Any]) -> dict[str, Any]:
    kpis = {item["label"]: item["value"] for item in data.get("kpis", [])}
    funnel = {item["label"]: item["value"] for item in data.get("funnel", [])}
    revenue = data.get("revenue", {})
    return {
        "period": data.get("reportingPeriod", date.today().strftime("%Y-%m")),
        "indexed_articles": int(kpis.get("インデックス数", 0)),
        "gsc_clicks": int(kpis.get("GSC clicks(月)", 0)),
        "outbound_clicks": int(kpis.get("Outbound clicks(月)", 0)),
        "confirmed_commissions_yen": int(kpis.get("確定報酬(月)", 0)),
        "sessions": int(funnel.get("Sessions", 0)),
        "qualified_sessions": int(funnel.get("Qualified sessions", 0)),
        "confirmed_conversions": int(funnel.get("成約(confirmed)", 0)),
        "pending_commissions_yen": int(revenue.get("pendingYen", 0)),
    }


def _prompt_external(current: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "period": "対象月 YYYY-MM",
        "indexed_articles": "インデックス数",
        "gsc_clicks": "GSC clicks",
        "outbound_clicks": "GA4 outbound_click",
        "confirmed_commissions_yen": "確定報酬 JPY",
        "sessions": "GA4 Sessions",
        "qualified_sessions": "GA4 qualified_session",
        "confirmed_conversions": "確定成約数",
        "pending_commissions_yen": "pending報酬 JPY",
    }
    result: dict[str, Any] = {}
    for field in CSV_FIELDS:
        raw = input(f"{labels[field]} [{current[field]}]: ").strip()
        raw = raw or str(current[field])
        result[field] = _validate_period(raw) if field == "period" else _non_negative_integer(raw, field)
    return result


def _work_queue(root: Path) -> list[dict[str, Any]]:
    requirements = (
        ("Q1 F1–F3・E1–E10 completion audit", root / "docs/DECISION_2026-07-28_REVENUE_TRACK.md"),
        ("Q2 取引意図記事の優先順", root / "site/app/lib/pilot-pages.ts"),
        ("Q3 TCO計算機embed", root / "site/app/embed/tco-calculator/page.tsx"),
        ("Q4 Product・FAQ・Breadcrumb JSON-LD", root / "site/app/lib/structured-data.ts"),
        ("Q5 note・X再配信template", root / "site/app/lib/derivative-templates.ts"),
        ("Q6 日本ASP申請checklist", root / "docs/JP_ASP_APPLICATION_CHECKLIST.md"),
        ("Q7 拡張category slate・input contract", root / "docs/CATEGORY_EXPANSION_SLATE.md"),
        ("Q8 90日判定閾値固定", root / "docs/PRODUCTION_ROADMAP.md"),
        ("Q9 dashboard Launch Quarter更新", root / "scripts/update_status_dashboard.py"),
    )
    return [{"done": path.is_file(), "label": label} for label, path in requirements]


def _launch_quarter() -> dict[str, Any]:
    return {
        "period": "2026-08〜2026-10",
        "humanBudgetMinutesPerMonth": 2000,
        "budgetReview": "2026-11",
        "decisionDate": "2026-10-31",
        "decisions": [
            "D5 launch trackのHuman予算を月2,000分へ一時引上げ",
            "D6 単価・需要・channel分散・取引意図集中を採用",
            "D7 index・impressions・click成長で90日固定判定",
        ],
        "weeklyPlan": [
            {"date": "7/31–8/2", "label": "domain day・P01–P03最終標本"},
            {"date": "8/3–8/9", "label": "第1弾記事承認・index準備"},
            {"date": "8/10–8/16", "label": "Mangools CTA gate・W6需要CSV"},
            {"date": "8/17–8/31", "label": "P06–P09中心に約8本・ASP申請可能化"},
            {"date": "9月", "label": "残記事・embed・note/X・Impact/ASP審査"},
            {"date": "10/1–10/24", "label": "取引意図記事改稿・内部導線"},
            {"date": "10/25–10/31", "label": "固定閾値で継続・拡張・縮小判定"},
        ],
        "thresholds": [
            {"tier": "拡張", "indexed": 10, "impressions": 5000, "clicks": 80, "impressionGrowth": "+50%", "clickGrowth": "+30%"},
            {"tier": "継続", "indexed": 8, "impressions": 1500, "clicks": 25, "impressionGrowth": "+25%", "clickGrowth": "0%以上"},
            {"tier": "最低ライン", "indexed": 4, "impressions": 300, "clicks": 5, "impressionGrowth": "0%以上", "clickGrowth": "0%以上"},
        ],
    }


def _regenerate(
    data: dict[str, Any],
    state: dict[str, Any],
    contracts: dict[str, EditorialArticleInput],
    external: dict[str, Any],
    *,
    root: Path,
    as_of: str,
) -> dict[str, Any]:
    approved = {
        article_id
        for article_id, status in state["articles"].items()
        if (
            status == "approved"
            and article_id in contracts
            and contracts[article_id].article_review_status.value == "approved"
        )
    }
    input_count = len(contracts)
    approved_count = len(approved)
    published_count = approved_count if state["index_state"] in {"GO", "DONE"} else 0
    cta_count = sum(value in {"GO", "DONE"} for value in state["affiliate_cta"].values())
    domain_state = state["domain_state"]
    index_state = state["index_state"]
    data["asOf"] = as_of
    data["reportingPeriod"] = external["period"]
    data["phase"] = (
        "editorial launch—記事入力・承認中"
        if domain_state in {"GO", "DONE"}
        else "Launch Quarter準備— domain GO待ち"
    )
    data["kpis"] = [
        {"label": "公開記事数", "value": published_count, "target": 12, "sub": f"入力 {input_count}/12・承認 {approved_count}/12"},
        {"label": "インデックス数", "value": external["indexed_articles"], "target": 12, "sub": f"index_go: {index_state}"},
        {"label": "GSC clicks(月)", "value": external["gsc_clicks"], "target": None, "sub": f"対象月 {external['period']}"},
        {"label": "Outbound clicks(月)", "value": external["outbound_clicks"], "target": 3334, "sub": "目標 3,334 / 月"},
        {"label": "確定報酬(月)", "value": external["confirmed_commissions_yen"], "target": 200000, "sub": "confirmed commissions(円)", "yen": True},
    ]
    outbound = external["outbound_clicks"]
    confirmed = external["confirmed_commissions_yen"]
    data["revenue"] = {
        "monthlyTargetYen": 200000,
        "confirmedYen": confirmed,
        "pendingYen": external["pending_commissions_yen"],
        "epcTargetYen": 60,
        "epcActualYen": None if outbound == 0 else round(confirmed / outbound, 2),
        "requiredClicks": 3334,
        "actualClicks": outbound,
        "partnerBreakdown": [],
    }
    data["funnel"] = [
        {"label": "Sessions", "value": external["sessions"]},
        {"label": "Qualified sessions", "value": external["qualified_sessions"]},
        {"label": "Outbound clicks", "value": outbound},
        {"label": "成約(confirmed)", "value": external["confirmed_conversions"]},
    ]
    data["lane"] = [
        {"id": "L1", "name": "独自domain取得", "status": domain_state, "note": "domain day runbookとread-back"},
        {"id": "L2", "name": "記事実値入力・承認", "status": f"{input_count}/12入力・{approved_count}/12承認", "note": "有効contractとHuman記事承認だけを算入"},
        {"id": "L3", "name": "noindex解除", "status": index_state, "note": "承認済み記事だけ・別GO"},
        {"id": "L4", "name": "CTA有効化", "status": "HOLD" if cta_count == 0 else f"{cta_count} partner GO", "note": "Affiliate承認・規約遵守・開示先行"},
    ]
    data["work"] = _work_queue(root)
    data["launchQuarter"] = _launch_quarter()
    data["deadlines"] = [
        {"date": "2026-08-01", "label": "exact domain選択・domain day開始"},
        {"date": "2026-08 第1週", "label": "P01–P03 Human記事承認"},
        {"date": "2026-08 前半", "label": "Mangools 150 query CSV"},
        {"date": "2026-08-31", "label": "約8本・Impact・W6・ASP申請可能状態"},
        {"date": "2026-10-31", "label": "90日固定判定・scope_expand判断"},
        {"date": "2026-11", "label": "Human予算を720分へ戻すか再判定"},
    ]
    return data


def update_dashboard(
    dashboard: Path,
    launch_state: Path,
    contracts_dir: Path,
    *,
    kpi_csv: Path | None,
    prompt: bool,
    as_of: str,
    root: Path = ROOT,
) -> None:
    source = dashboard.read_text(encoding="utf-8")
    before, data, after = _split_dashboard(source)
    state = _load_launch_state(launch_state)
    contracts = _load_contracts(contracts_dir)
    external = _current_external(data)
    if kpi_csv is not None:
        external = _load_kpi_csv(kpi_csv)
    elif prompt:
        external = _prompt_external(external)
    regenerated = _regenerate(data, state, contracts, external, root=root, as_of=as_of)
    dashboard.write_text(
        before
        + DATA_START
        + json.dumps(regenerated, ensure_ascii=False, indent=2)
        + DATA_END
        + after,
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard", type=Path, default=ROOT / "status-dashboard.html")
    parser.add_argument("--launch-state", type=Path, default=ROOT / "docs/EDITORIAL_LAUNCH_STATE.json")
    parser.add_argument("--contracts-dir", type=Path, default=ROOT / "artifacts/editorial-inputs")
    parser.add_argument("--kpi-csv", type=Path)
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    update_dashboard(
        args.dashboard,
        args.launch_state,
        args.contracts_dir,
        kpi_csv=args.kpi_csv,
        prompt=not args.no_prompt and args.kpi_csv is None,
        as_of=args.as_of,
    )


if __name__ == "__main__":
    main()
