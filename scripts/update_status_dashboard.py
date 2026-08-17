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

from saas_preflight.affiliate_partner_ledger import (
    AffiliatePartnershipStatus,
    load_affiliate_partner_ledger,
)
from saas_preflight.editorial_input import EditorialArticleInput


ROOT = Path(__file__).resolve().parents[1]
PILOT_IDS = tuple(f"P{number:02d}" for number in range(1, 13))
SERVER_ID_PATTERN = re.compile(r"SVR(?:0[1-9]|1[0-9]|20)")
DATA_START = "// DASHBOARD_DATA_START\nconst DATA = "
DATA_END = ";\n// DASHBOARD_DATA_END"
ALLOWED_LANE_STATES = frozenset({"HOLD", "GO", "DONE"})
ALLOWED_ARTICLE_STATES = frozenset({"unreviewed", "approved", "rejected"})
ARTICLE_REVIEW_FIELD_LABELS = {
    "billing.monthly_contract_price": "月払い",
    "billing.annual_contract_price": "年次checkout総額",
    "billing.minimum_commitment_months": "最低契約期間",
    "billing.termination_cost": "途中解約費用",
    "usage.included_quota": "含有利用量",
    "usage.overage_unit_size": "従量超過単位",
    "usage.overage_price": "従量超過単価",
    "usage.monthly_volume": "Human月間利用量",
    "team.minimum_users": "最低利用者数",
    "team.monthly_admin_hours": "月間運用時間",
    "team.onboarding_hours": "導入時間",
    "enterprise.agency_extra_seats_available": "Agencyで追加可能なseat数",
    "enterprise.agency_annual_checkout_total": "Agency年次checkout総額",
    "enterprise.site_analysis_requests_per_24h": "Site analysis回数 / 24時間",
    "enterprise.migration_support_price": "移行支援費",
    "addon.base_price": "基本料金",
    "addon.required_addon_price": "必須addon料金",
    "addon.required_seats": "必要利用者数",
    "addon.billing_unit": "addon課金単位",
    "migration.support_price": "移行支援料金",
    "migration.overlap_months": "重複契約月数",
    "migration.work_hours": "移行作業時間",
    "migration.training_hours": "教育時間",
    "migration.hourly_cost": "Human時間単価",
    "localization.display_price": "表示価格",
    "localization.tax_rate": "税率",
    "localization.jpy_rate": "JPY換算レート",
    "break_even.monthly_hours_saved": "月間削減時間",
    "break_even.hourly_cost": "Human時間価値",
    "break_even.implementation_cost": "導入費用",
    "break_even.monthly_tco": "月額TCO",
    "evidence.review_interval_days": "根拠確認間隔",
}
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
        "schema_version", "domain", "domain_state", "index_state", "affiliate_cta",
        "articles", "deployed_articles", "index_approved_articles", "server_articles",
        "deployed_server_articles", "index_approved_server_articles", "server_affiliate_cta",
    }
    if not isinstance(state, dict) or set(state) != expected:
        raise DashboardInputError("editorial launch state fields do not match ease-track-2")
    if state["schema_version"] != "ease-track-2":
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
    for field in ("deployed_articles", "index_approved_articles"):
        values = state[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or value not in PILOT_IDS for value in values)
            or len(values) != len(set(values))
            or any(articles[value] != "approved" for value in values)
        ):
            raise DashboardInputError(
                f"{field} must contain unique approved P01-P12 article IDs"
            )
    cta = state["affiliate_cta"]
    if not isinstance(cta, dict) or any(value not in ALLOWED_LANE_STATES for value in cta.values()):
        raise DashboardInputError("affiliate CTA states must be HOLD, GO, or DONE")
    server_articles = state["server_articles"]
    if (
        not isinstance(server_articles, dict)
        or any(not isinstance(key, str) or SERVER_ID_PATTERN.fullmatch(key) is None for key in server_articles)
        or any(value not in ALLOWED_ARTICLE_STATES for value in server_articles.values())
    ):
        raise DashboardInputError("server article state must use unique SVR01-SVR20 keys and valid states")
    for field in ("deployed_server_articles", "index_approved_server_articles"):
        values = state[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or value not in server_articles for value in values)
            or len(values) != len(set(values))
            or any(server_articles[value] != "approved" for value in values)
        ):
            raise DashboardInputError(f"{field} must contain unique approved server article IDs")
    server_cta = state["server_affiliate_cta"]
    if (
        not isinstance(server_cta, dict)
        or any(value not in ALLOWED_LANE_STATES for value in server_cta.values())
    ):
        raise DashboardInputError("server affiliate CTA states must be HOLD, GO, or DONE")
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
        ("SVR01 servers価格観測Operator", root / "site/app/operator/servers/page.tsx"),
        ("SVR01証拠付き・SVR02–SVR20 noindex候補view", root / "site/app/servers/business-server-pricing/page.tsx"),
        ("servers 20記事候補一覧", root / "site/app/operator/servers/page.tsx"),
        ("servers次8記事の取引意図優先queue", root / "docs/CATEGORY_EXPANSION_SLATE.md"),
    )
    return [{"done": path.is_file(), "label": label} for label, path in requirements]


def _external_action_queue(
    root: Path,
    state: dict[str, Any],
    contracts: dict[str, EditorialArticleInput],
) -> list[dict[str, Any]]:
    """Return non-secret Human/external gates without treating them as repo work."""

    ledger = load_affiliate_partner_ledger(root / "docs" / "AFFILIATE_PARTNER_LEDGER.json")
    accounts = {entry.partner_id: entry for entry in ledger.entries}
    programs = {entry.research_id: entry for entry in ledger.program_research}
    adoption = (root / "docs" / "CURRENT_ADOPTION_ACTIONS.md").read_text(encoding="utf-8")
    server_contract_ready = any(
        path.name.startswith("SVR01")
        for path in (root / "artifacts" / "category-expansion-inputs").glob("*.json")
    )
    server_article_approved = state["server_articles"].get("SVR01") == "approved"
    server_contract_confirmed = "candidate contractの構造確定" in adoption
    x_ready = "handleは`@saastcolab`" in adoption and "投稿0件" in adoption
    r1_release_done = "Sites version 11へ公開した" in adoption
    p01_x_done = "Xスレッド8件を公開した" in adoption
    actions: list[dict[str, Any]] = []
    moshimo = programs["moshimo-lolipop-rental-server"]
    if moshimo.partnership_status.value == "not_applied":
        legal_attestation_waiting = "Humanが画面上の「はい」を押すまでは" in adoption
        result_unverified = "申請ボタン押下後にsessionが失効" in adoption
        actions.append({
            "label": "もしも ロリポップ！レンタルサーバー提携申請",
            "status": (
                "human_legal_attestation_required"
                if legal_attestation_waiting
                else "result_unverified"
                if result_unverified
                else moshimo.partnership_status.value
            ),
            "token": (
                "moshimo_media_attestation: done"
                if legal_attestation_waiting
                else "moshimo_reauth: done"
                if result_unverified
                else "asp_program_apply: GO もしも ロリポップ！レンタルサーバー"
            ),
        })
    if (
        "`plan upgrade required`" in adoption
        and "Mangools Basic契約有効化済み" not in adoption
    ):
        actions.append({
            "label": "KWFinder拡張需要180語の一時upgrade・export",
            "status": "payment_approval_required",
            "token": "mangools_upgrade: GO Basic monthly 61.00 USD max_total 61.00 USD cancel_after_export / HOLD",
        })
    if (
        "Mangools Basic契約有効化済み" in adoption
        and "残りはCRM 40、forms 40、email_marketing 40、SEO追加60" in adoption
        and "拡張需要180語のHuman export完了" not in adoption
    ):
        actions.append({
            "label": "KWFinder拡張需要180語をHuman export（one-command intake準備済み）",
            "status": "human_export_required",
            "token": "mangools_category_csv: done crm,forms,email_marketing,seo_tools_v2_extension",
        })
    for research_id in (
        "moshimo-shin-rental-server",
        "moshimo-conoha-wing",
        "moshimo-onamae-rental-server",
    ):
        program = programs[research_id]
        if program.partnership_status.value != "not_applied":
            continue
        detail_reviewed = program.condition_review_status.value == "detail_reviewed"
        actions.append({
            "label": f"もしも {program.program_name}提携申請",
            "status": (
                "terms_confirmation_required"
                if detail_reviewed
                else "reauth_then_terms_confirmation_required"
            ),
            "token": (
                f"asp_program_terms_accept: GO もしも {program.program_name}"
                if detail_reviewed
                else f"asp_program_apply: GO もしも {program.program_name}"
            ),
        })
    missing_contracts = [article_id for article_id in PILOT_IDS if article_id not in contracts]
    if missing_contracts:
        joined = ",".join(missing_contracts)
        actions.append({
            "label": f"{joined} editorial contract入力",
            "status": "contract_input_required",
            "token": f"article_input: done {joined}",
        })
    a8 = programs["a8net-xserver-business"]
    if a8.partnership_status.value == "not_applied":
        actions.append({
            "label": "A8.net XServerビジネス提携申請",
            "status": a8.partnership_status.value,
            "token": "asp_program_apply: GO A8.net XServerビジネス",
        })
    if accounts["valuecommerce"].account_status.value == "registration_incomplete":
        actions.append({
            "label": "バリューコマース本登録・ABLENET詳細確認",
            "status": "registration_incomplete",
            "token": "valuecommerce_registration: done",
        })
    if not server_contract_ready:
        actions.append({
            "label": "SVR01候補JSON保存",
            "status": (
                "localhost download許可待ち"
                if server_contract_confirmed
                else "入力待ち"
            ),
            "token": (
                "local_download_permission: GO localhost SVR01"
                if server_contract_confirmed
                else "server_price_input: done SVR01"
            ),
        })
    elif (
        "SVR01追加候補はHuman確認待ち" in adoption
        and "SVR01追加候補のHuman確認完了" not in adoption
    ):
        actions.append({
            "label": "SVR01年次総額・backup追加候補の再確認",
            "status": "Human確認待ち",
            "token": "server_price_input: done SVR01",
        })
    if (
        not server_article_approved
        and
        "現在のSVR01はTCOと用途判定の" in adoption
        and "両方がHOLD" in adoption
        and "11 fieldをfield-review済みに更新" not in adoption
    ):
        actions.append({
            "label": "SVR01の公式画面9候補をfield単位でHuman確認",
            "status": "human_field_attestation_required",
            "token": "svr01_candidates: confirm_all / corrections <field>: <value>",
        })
    if (
        not server_article_approved
        and
        "11 fieldをfield-review済みに更新" in adoption
        and "基本料金自体も" in adoption
        and "time_limited_promo" in adoption
    ):
        actions.append({
            "label": "SVR01の価格本体・キャンペーン分類を再確認",
            "status": "human_official_price_observation_required",
            "token": "svr01_candidates: corrections pricing.initial_fee.sale_banner_state=<class>,pricing.base_price.sale_banner_state=<class>",
        })
    held_server_cta = sorted(
        partner_id
        for partner_id, status in state["server_affiliate_cta"].items()
        if status == "HOLD"
    )
    server_destinations_configured = "production runtime secret 6件を設定済み" in adoption
    if server_article_approved and held_server_cta:
        if server_destinations_configured:
            actions.append({
                "label": f"destination設定済みservers {len(held_server_cta)}案件のpartner別CTA GO",
                "status": "server_partner_cta_go_required",
                "token": "server_cta_go: GO <partner IDs comma-separated> / HOLD",
            })
        else:
            actions.append({
                "label": f"承認済みservers {len(held_server_cta)}案件のruntime destination設定",
                "status": "asp_os_authentication_or_destination_required",
                "token": "asp_reauth: done <A8.net|もしも|バリューコマース>",
            })
    unreviewed_contracts = [
        article_id
        for article_id in PILOT_IDS
        if article_id in contracts
        and contracts[article_id].article_review_status.value == "unreviewed"
    ]
    review_ready = [
        article_id
        for article_id in unreviewed_contracts
        if any(
            field.value_status.value in {"known", "not_applicable"}
            for field in contracts[article_id].numeric_fields
        )
    ]
    evidence_required = [
        article_id for article_id in unreviewed_contracts if article_id not in review_ready
    ]
    if review_ready:
        joined = ",".join(review_ready)
        actions.append({
            "label": f"{joined}記事標本のHuman承認",
            "status": "Human承認待ち",
            "token": f"article_approve: {joined}",
        })
    if "p05_field_scope: approve mangools_agency_actual_fields" in adoption and "P05" in evidence_required:
        actions.append({
            "label": "P05をMangools Agencyの公式fieldへ修正",
            "status": "human_field_scope_review_required",
            "token": "p05_field_scope: approve mangools_agency_actual_fields / corrections <item>: <text>",
        })
        evidence_required = [article_id for article_id in evidence_required if article_id != "P05"]
    if evidence_required:
        joined = ",".join(evidence_required)
        owned_timer_ready = set(evidence_required).issubset({"P09", "P11"})
        actions.append({
            "label": (
                f"{joined}のHuman確認済み実測（Operator timer準備済み）"
                if owned_timer_ready
                else f"{joined}の自データ・確認済み実値取得"
            ),
            "status": "owned_data_waiting" if owned_timer_ready else "evidence_required",
            "token": f"article_evidence: pending {joined}",
        })
    release_ready = [
        article_id
        for article_id in PILOT_IDS
        if article_id in contracts
        and state["articles"][article_id] == "approved"
        and contracts[article_id].article_review_status.value == "approved"
        and article_id not in state["deployed_articles"]
    ]
    if release_ready:
        joined = ",".join(release_ready)
        actions.append({
            "label": f"{joined}のproduction release",
            "status": "production_go_required",
            "token": f"deploy_update: GO {joined} / HOLD",
        })
    if not r1_release_done:
        actions.append({
            "label": "P01–P03 R1–R6 release",
            "status": "外部GO待ち",
            "token": "repository_update_push: GO / deploy_update: GO P01,P02,P03 R1-R6",
        })
    if not p01_x_done:
        actions.append({
            "label": "P01 X初回投稿",
            "status": "投稿GO待ち" if x_ready else "account準備待ち",
            "token": "x_post: GO P01",
        })
    return [{"priority": index, **action} for index, action in enumerate(actions, start=1)]


def _article_review_queue(
    contracts: dict[str, EditorialArticleInput],
) -> list[dict[str, Any]]:
    """Build a non-secret, contract-driven Human review card for pending articles."""

    queue: list[dict[str, Any]] = []
    for article_id in PILOT_IDS:
        contract = contracts.get(article_id)
        if contract is None or contract.article_review_status.value != "unreviewed":
            continue
        confirmed: list[str] = []
        not_applicable: list[str] = []
        unresolved: list[str] = []
        next_reviews: list[date] = []
        observed: list[date] = []
        for field in contract.numeric_fields:
            label = ARTICLE_REVIEW_FIELD_LABELS.get(field.field, field.field)
            observed.append(field.observed_on)
            next_reviews.append(field.next_review_on)
            if field.value_status.value == "known":
                amount = f"{field.value} {field.unit or ''}".strip()
                if field.currency is not None:
                    amount = f"{amount} {field.currency}".strip()
                confirmed.append(f"{label}: {amount}")
            elif field.value_status.value == "not_applicable":
                reason = field.unknown_reason or "数値適用なし"
                not_applicable.append(f"{label}: 対象外（{reason}）")
            else:
                reason = field.unknown_reason or "数値適用なし"
                unresolved.append(
                    f"{label}: {field.value_status.value}（{reason}）"
                )
        ready_for_approval = bool(confirmed or not_applicable)
        queue.append(
            {
                "articleId": article_id,
                "title": contract.title,
                "previewUrl": f"http://localhost:3000/pilot/{contract.slug}",
                "confirmed": confirmed,
                "notApplicable": not_applicable,
                "unresolved": unresolved,
                "observedOn": min(observed).isoformat(),
                "nextReviewOn": min(next_reviews).isoformat(),
                "reviewState": "approval_ready" if ready_for_approval else "evidence_required",
                "token": (
                    f"article_approve: {article_id}"
                    if ready_for_approval
                    else f"article_evidence: pending {article_id}"
                ),
            }
        )
    return queue


def _server_partner_redundancy(root: Path) -> dict[str, Any]:
    ledger = load_affiliate_partner_ledger(root / "docs" / "AFFILIATE_PARTNER_LEDGER.json")
    approved = sorted({
        item.research_id
        for item in ledger.program_research
        if item.category == "サーバー"
        and item.partnership_status is AffiliatePartnershipStatus.APPROVED
    })
    if not approved:
        mode = "disabled"
        dependency_status = "not_measurable"
        dominant_share = None
    elif len(approved) == 1:
        mode = "single"
        dependency_status = "structural_single_partner"
        dominant_share = 100
    else:
        mode = "comparison"
        dependency_status = "confirmed_commission_share_unobserved"
        dominant_share = None
    return {
        "approvedPartnerCount": len(approved),
        "ctaMode": mode,
        "dependencyStatus": dependency_status,
        "dominantSharePercent": dominant_share,
        "warningThresholdPercent": 80,
        "warning": dominant_share is not None and dominant_share > 80,
        "individualCtaGateRequired": True,
    }


def _launch_quarter() -> dict[str, Any]:
    scope_expansion = {
        "state": "MEASURED 180/180",
        "observedKnownVolume": 6500,
        "requiredSessions": 22227,
        "noDataRate": "90.00%",
        "frozenQueries": 180,
        "externalActions": "DONE",
    }
    return {
        "period": "2026-08〜2026-10",
        "humanBudgetMinutesPerMonth": 2000,
        "budgetReview": "2026-11",
        "decisionDate": "2026-10-31",
        "decisions": [
            "D5 launch trackのHuman予算を月2,000分へ一時引上げ",
            "D6 単価・需要・channel分散・取引意図集中を採用",
            "D7 index・impressions・click成長で90日固定判定",
            "D8 W6 known下限によりカテゴリ拡張の準備scopeを前倒しGO",
            "D9 serversをロングテール・計算機first・partner冗長化で運用",
            "D10 servers記事はzero-input、入力式はmethodologyだけに分離",
        ],
        "scopeExpansion": scope_expansion,
        "weeklyPlan": [
            {"date": "7/31–8/2", "label": "domain day・P01–P03最終標本"},
            {"date": "8/3–8/9", "label": "第1弾記事承認・index準備"},
            {"date": "8/10–8/16", "label": "拡張需要180語完了・カテゴリ別判定反映"},
            {"date": "8/17–8/31", "label": "servers価格確認・P11完全暦月計測の準備"},
            {"date": "9月", "label": "P11導入前の完全暦月計測・embed・Impact/ASP審査"},
            {"date": "10/1–10/24", "label": "P11導入後の完全暦月計測・取引意図記事改稿"},
            {"date": "10/25–10/31", "label": "固定閾値で継続・拡張・縮小判定"},
        ],
        "thresholds": [
            {"tier": "拡張", "indexed": 10, "impressions": 5000, "clicks": 80, "impressionGrowth": "+50%", "clickGrowth": "+30%"},
            {"tier": "継続", "indexed": 8, "impressions": 1500, "clicks": 25, "impressionGrowth": "+25%", "clickGrowth": "0%以上"},
            {"tier": "最低ライン", "indexed": 4, "impressions": 300, "clicks": 5, "impressionGrowth": "0%以上", "clickGrowth": "0%以上"},
        ],
        "exitLine": {
            "decisionDate": "2026-12-31",
            "publishedArticlesMinimum": 20,
            "gscClicksPerMonthMinimum": 300,
            "confirmedConversionsMinimum": 1,
            "allConditionsRequired": True,
            "thresholdCanBeRelaxed": False,
            "pivotCandidates": ["embed配布", "note有料", "受託"],
        },
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
    deployed = set(state["deployed_articles"])
    index_approved = set(state["index_approved_articles"])
    published_count = len(approved & deployed)
    approved_server_articles = {
        article_id
        for article_id, status in state["server_articles"].items()
        if status == "approved"
    }
    deployed_server_articles = set(state["deployed_server_articles"])
    index_approved_server_articles = set(state["index_approved_server_articles"])
    index_target_count = len(index_approved) + len(index_approved_server_articles)
    enabled_server_cta = sorted(
        partner_id
        for partner_id, status in state["server_affiliate_cta"].items()
        if status in {"GO", "DONE"}
    )
    held_server_cta = sorted(
        partner_id
        for partner_id, status in state["server_affiliate_cta"].items()
        if status == "HOLD"
    )
    published_server_count = len(approved_server_articles & deployed_server_articles)
    total_published_count = published_count + published_server_count
    server_contract_ready = any(
        path.name.startswith("SVR01")
        for path in (root / "artifacts" / "category-expansion-inputs").glob("*.json")
    )
    cta_count = sum(value in {"GO", "DONE"} for value in state["affiliate_cta"].values())
    domain_state = state["domain_state"]
    index_state = state["index_state"]
    adoption = (root / "docs" / "CURRENT_ADOPTION_ACTIONS.md").read_text(encoding="utf-8")
    data["asOf"] = as_of
    data["reportingPeriod"] = external["period"]
    data["phase"] = (
        f"公開後成長運転—{total_published_count}記事公開・P記事{12 - approved_count}本証拠/承認待ち"
        if total_published_count > 0
        else "editorial launch—記事入力・承認中"
        if domain_state in {"GO", "DONE"}
        else "Launch Quarter準備— domain GO待ち"
    )
    data["kpis"] = [
        {"label": "公開記事数", "value": total_published_count, "target": 20, "sub": f"P記事 {published_count}本・servers {published_server_count}本"},
        {"label": "インデックス数", "value": external["indexed_articles"], "target": 12, "sub": f"index_go: {index_state}"},
        {"label": "GSC clicks(月)", "value": external["gsc_clicks"], "target": None, "sub": f"対象月 {external['period']}"},
        {"label": "Outbound clicks(月)", "value": external["outbound_clicks"], "target": 3334, "sub": "目標 3,334 / 月"},
        {"label": "確定報酬(月)", "value": external["confirmed_commissions_yen"], "target": 200000, "sub": "confirmed commissions(円)", "yen": True},
    ]
    data["categoryPublication"] = [
        {"category": "servers", "publishedArticles": published_server_count, "targetArticles": 9},
        {"category": "seo_tools", "publishedArticles": published_count, "targetArticles": 11},
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
    server_partner_policy = _server_partner_redundancy(root)
    data["serverPartnerPolicy"] = server_partner_policy
    data["funnel"] = [
        {"label": "Sessions", "value": external["sessions"]},
        {"label": "Qualified sessions", "value": external["qualified_sessions"]},
        {"label": "Outbound clicks", "value": outbound},
        {"label": "成約(confirmed)", "value": external["confirmed_conversions"]},
    ]
    data["lane"] = [
        {"id": "L1", "name": "独自domain取得", "status": domain_state, "note": "domain day runbookとread-back"},
        {"id": "L2", "name": "記事実値入力・承認", "status": f"{input_count}/12入力・{approved_count}/12承認", "note": "有効contractとHuman記事承認だけを算入"},
        {"id": "L3", "name": "noindex解除", "status": index_state, "note": f"index承認 {len(index_approved)}本・記事承認だけでは追加しない"},
        {"id": "L4", "name": "CTA有効化", "status": "HOLD" if cta_count == 0 else f"{cta_count} partner GO", "note": "Affiliate承認・規約遵守・開示先行"},
    ]
    data["serverLaunch"] = {
        "approvedArticles": len(approved_server_articles),
        "deployedArticles": published_server_count,
        "indexApprovedArticles": len(index_approved_server_articles),
        "ctaEnabledPartners": len(enabled_server_cta),
        "ctaHeldPartners": len(held_server_cta),
    }
    data["partners"] = [
        {
            "name": "Mangools",
            "affiliate": "有効(紹介ID発行済)",
            "affStatus": "go",
            "rights": "未回答(7/26追送)",
            "next": "editorial CTA候補。tier確認 毎月4日",
        },
        {
            "name": "HubSpot",
            "affiliate": "ImpactでDeclined(low reach・8/3確認)",
            "affStatus": "warn",
            "rights": "未回答(7/26追送)",
            "next": "流入実績を作るまで再申請しない",
        },
        {
            "name": "Semrush",
            "affiliate": "Impact Marketplace却下済み(8/9確認)",
            "affStatus": "warn",
            "rights": "自動取得系prohibited / editorial条件付き可",
            "next": "流入実績形成後に新しいexact GOで再評価",
        },
        {
            "name": "SE Ranking",
            "affiliate": "work email例外回答待ち",
            "affStatus": "hold",
            "rights": "未回答(ticket追送済)",
            "next": "回答まで再登録しない",
        },
        {
            "name": "Serpstat",
            "affiliate": "未申請",
            "affStatus": "hold",
            "rights": "社内審査中",
            "next": "項目別回答待ち",
        },
    ]
    data["work"] = _work_queue(root)
    data["externalActions"] = _external_action_queue(root, state, contracts)
    data["articleReviews"] = _article_review_queue(contracts)
    data["launchQuarter"] = _launch_quarter()
    data["deadlines"] = [
        {"date": "2026-08-01", "label": "exact domain選択・domain day開始"},
        {"date": "2026-08 第1週", "label": "P01–P03 Human記事承認"},
        {"date": "2026-08-05", "label": "W6 150 query完了・拡張準備260 query凍結"},
        {"date": "2026-08-31", "label": "約8本・Impact・W6・ASP申請可能状態"},
        {"date": "2026-09-01", "label": "P11導入前月の完全暦月計測開始"},
        {"date": "2026-10-01", "label": "P11導入後月の完全暦月計測開始"},
        {"date": "2026-10-31", "label": "現ニッチ90日固定判定・カテゴリ別判断"},
        {"date": "2026-11-01以降", "label": "P11の2完全暦月を比較しcontract候補化"},
        {"date": "2026-11", "label": "Human予算を720分へ戻すか再判定"},
        {"date": "2026-12-31", "label": "20本・GSC clicks 300/月・confirmed 1件の固定撤退判定"},
    ]
    obsolete_risk_labels = {
        "JP/ja需要規模が未検証(Mangools CSVで判定)",
        "独自domain未取得(L1で解消)",
    }
    generated_risk_ids = {
        "server-candidate-only",
        "editorial-coverage",
        "gsc-processing",
        "server-launch",
        "server-partner-dependency",
        "index-discovery-path",
    }
    dynamic_risks = [
        item for item in data.get("risks", [])
        if item.get("riskId") not in generated_risk_ids
        and item.get("label") not in obsolete_risk_labels
    ]
    if approved_count < 12:
        dynamic_risks.append({
            "riskId": "editorial-coverage",
            "level": "warn",
            "label": f"編集記事は{approved_count}/12承認。未承認記事はnoindex・CTA無効を維持",
        })
    if "sitemapは成功・12ページ検出" in adoption:
        dynamic_risks.append({
            "riskId": "gsc-processing",
            "level": "monitor",
            "label": "GSC sitemapは12/12検出済み。index登録7・未登録6の再処理を監視",
        })
    elif "sitemap成功・最終読込2026-08-13・検出10" in adoption:
        dynamic_risks.append({
            "riskId": "gsc-processing",
            "level": "warn",
            "label": (
                f"GSCはsitemap 10/{index_target_count}検出・"
                "P01登録要求一時エラー。通常クロール待ち"
            ),
        })
    if "トップの旧nofollowはインデックス停滞の原因候補" in adoption:
        dynamic_risks.append({
            "riskId": "index-discovery-path",
            "level": "monitor",
            "label": "旧トップのnofollowをI1でnoindex,followへ修正。承認記事のindex,followと未承認記事のnoindexを維持して再処理監視",
        })
    if published_server_count:
        server_destinations_configured = "production runtime secret 6件を設定済み" in adoption
        dynamic_risks.append({
            "riskId": "server-launch",
            "level": "warn",
            "label": (
                f"SVR01は承認・index対象として公開済み。servers CTA {len(enabled_server_cta)}件稼働・"
                f"残る{len(held_server_cta)}partnerはHOLD"
                if enabled_server_cta
                else "SVR01は承認・index対象として公開済み。destination設定済み・"
                "partner別CTA GO未受領のためservers CTAは0件"
                if server_destinations_configured
                else "SVR01は承認・index対象として公開済み。runtime destination未設定のためservers CTAは0件"
            ),
        })
    if len(enabled_server_cta) == 1:
        dynamic_risks.append({
            "riskId": "server-partner-dependency",
            "level": "warn",
            "label": "serversの稼働CTAは1partnerのみで運用上100%依存。第2partner GOまでは単独CTAを維持",
        })
    elif server_partner_policy["warning"]:
        dynamic_risks.append({
            "riskId": "server-partner-dependency",
            "level": "warn",
            "label": "serversの単一partner依存が80%を超過。第2partner承認までは単独CTAを維持",
        })
    data["risks"] = dynamic_risks
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
