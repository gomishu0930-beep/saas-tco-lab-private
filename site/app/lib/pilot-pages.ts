export type PilotNumericField = {
  key: string;
  label: string;
  valueKind:
    | "price"
    | "quota"
    | "seat_count"
    | "tax_rate"
    | "exchange_rate"
    | "duration"
    | "usage"
    | "percentage"
    | "other";
  inputScope?: "vendor_plan" | "human_scenario";
};

export type PilotPage = {
  id: `P${string}`;
  slug: string;
  title: string;
  intent: string;
  pageType: string;
  question: string;
  readerOutcome: string;
  numericFields: readonly PilotNumericField[];
};

export const pilotPages: readonly PilotPage[] = [
  { id: "P01", slug: "pricing-calculator", title: "料金計算", intent: "price_check", pageType: "pricing", question: "seat数と利用量をそろえると12か月総額はいくらか", readerOutcome: "自分のseat数と利用量で、初年度の支払総額を再計算できる", numericFields: [
    { key: "pricing.base_price", label: "基本料金", valueKind: "price" }, { key: "scenario.seat_count", label: "seat数", valueKind: "seat_count", inputScope: "human_scenario" }, { key: "scenario.monthly_usage", label: "月間利用量", valueKind: "usage", inputScope: "human_scenario" }, { key: "pricing.overage_price", label: "超過単価", valueKind: "price" }, { key: "pricing.tax_rate", label: "税率", valueKind: "tax_rate" },
  ] },
  { id: "P02", slug: "plan-comparison", title: "プラン比較", intent: "compare", pageType: "comparison", question: "同じ利用条件で複数プランをどう比較するか", readerOutcome: "同一scenarioで価格差と上限差を比較できる", numericFields: [
    { key: "plan.price", label: "各plan料金", valueKind: "price" }, { key: "plan.minimum_seats", label: "最低seat数", valueKind: "seat_count" }, { key: "plan.usage_quota", label: "keyword検索回数 / 24h", valueKind: "quota" }, { key: "plan.overage_price", label: "超過単価", valueKind: "price" }, { key: "plan.commitment_months", label: "契約月数", valueKind: "duration" },
  ] },
  { id: "P03", slug: "alternatives", title: "代替候補", intent: "replace", pageType: "alternatives", question: "置き換え候補をTCOと適合条件でどう絞るか", readerOutcome: "必要条件を落とさず候補を3社以内へ絞れる", numericFields: [
    { key: "alternative.price", label: "各候補の料金", valueKind: "price" }, { key: "alternative.usage_quota", label: "追跡keyword数（候補別単位）", valueKind: "quota" }, { key: "alternative.required_addon_price", label: "必須addon料金", valueKind: "price" }, { key: "alternative.migration_cost", label: "移行費用", valueKind: "price" },
  ] },
  { id: "P04", slug: "small-team-fit", title: "小規模チーム適合", intent: "fit_check", pageType: "use_case_fit", question: "少人数運用で固定費と人手を抑えられるか", readerOutcome: "少人数scenarioの固定費と運用時間を見積もれる", numericFields: [
    { key: "team.minimum_seats", label: "最低seat数", valueKind: "seat_count" }, { key: "team.monthly_price", label: "月額料金", valueKind: "price" }, { key: "team.monthly_operation_hours", label: "月間運用時間", valueKind: "duration" }, { key: "team.onboarding_hours", label: "導入時間", valueKind: "duration" },
  ] },
  { id: "P05", slug: "enterprise-fit", title: "組織利用適合", intent: "fit_check", pageType: "use_case_fit", question: "権限・監査・運用費を含めて組織要件に合うか", readerOutcome: "組織向け必須条件と追加費用を切り分けられる", numericFields: [
    { key: "enterprise.included_manager_seats", label: "含有manager seat数", valueKind: "seat_count" }, { key: "enterprise.agency_pack_price", label: "Agency Pack料金", valueKind: "price" }, { key: "enterprise.audit_pages_per_month", label: "監査page上限", valueKind: "quota" }, { key: "enterprise.migration_support_price", label: "移行支援費", valueKind: "price" },
  ] },
  { id: "P06", slug: "annual-vs-monthly", title: "年契約と月契約", intent: "compare", pageType: "comparison", question: "commitmentと解約リスクを含む総額差はいくらか", readerOutcome: "契約期間と解約リスクを含む差額を判断できる", numericFields: [
    { key: "billing.monthly_contract_price", label: "月契約料金", valueKind: "price" }, { key: "billing.annual_contract_price", label: "年契約料金", valueKind: "price" }, { key: "billing.minimum_commitment_months", label: "最低契約月数", valueKind: "duration" }, { key: "billing.termination_cost", label: "解約費用", valueKind: "price" },
  ] },
  { id: "P07", slug: "usage-overage", title: "従量超過", intent: "price_check", pageType: "pricing", question: "利用量が基準を超えた時の増分費用はいくらか", readerOutcome: "通常・繁忙期の超過費用を別々に計算できる", numericFields: [
    { key: "usage.included_quota", label: "含有利用量", valueKind: "quota" }, { key: "usage.overage_unit_size", label: "超過単位", valueKind: "usage" }, { key: "usage.overage_price", label: "超過単価", valueKind: "price" }, { key: "usage.monthly_volume", label: "月間利用量", valueKind: "usage", inputScope: "human_scenario" },
  ] },
  { id: "P08", slug: "addon-cost", title: "追加機能費用", intent: "price_check", pageType: "pricing", question: "必須addonを含めた実効総額はいくらか", readerOutcome: "必須・任意addonを分けて実効総額を確認できる", numericFields: [
    { key: "addon.base_price", label: "基本料金", valueKind: "price" }, { key: "addon.price", label: "addon料金", valueKind: "price" }, { key: "addon.billing_unit_size", label: "addon課金単位", valueKind: "usage" }, { key: "addon.required_seats", label: "必要seat数", valueKind: "seat_count" },
  ] },
  { id: "P09", slug: "migration-cost", title: "移行コスト", intent: "migrate", pageType: "migration", question: "移行作業・重複契約・教育を含む初年度費用はいくらか", readerOutcome: "見落としやすい移行費用を初年度TCOへ足せる", numericFields: [
    { key: "migration.overlap_months", label: "重複契約月数", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.work_hours", label: "作業時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.hourly_cost", label: "時間単価", valueKind: "price", inputScope: "human_scenario" }, { key: "migration.training_hours", label: "教育時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "migration.support_price", label: "移行支援費", valueKind: "price" },
  ] },
  { id: "P10", slug: "japan-tax", title: "日本向け税・通貨", intent: "verify_method", pageType: "methodology", question: "JPY換算と日本向け税表示をどう検証するか", readerOutcome: "税・通貨がunknownの値を計算から除外できる", numericFields: [
    { key: "localization.displayed_price", label: "表示価格", valueKind: "price" }, { key: "localization.tax_rate", label: "税率", valueKind: "tax_rate" }, { key: "localization.exchange_rate", label: "換算レート", valueKind: "exchange_rate" },
  ] },
  { id: "P11", slug: "break-even", title: "損益分岐", intent: "fit_check", pageType: "use_case_fit", question: "削減時間と運用費から導入の損益分岐をどう求めるか", readerOutcome: "削減時間が費用を上回る条件を試算できる", numericFields: [
    { key: "break_even.monthly_hours_saved", label: "月間削減時間", valueKind: "duration", inputScope: "human_scenario" }, { key: "break_even.hourly_cost", label: "時間単価", valueKind: "price", inputScope: "human_scenario" }, { key: "break_even.implementation_cost", label: "導入費", valueKind: "price", inputScope: "human_scenario" }, { key: "break_even.monthly_tco", label: "月額TCO", valueKind: "price", inputScope: "human_scenario" },
  ] },
  { id: "P12", slug: "evidence-method", title: "根拠の検証", intent: "verify_method", pageType: "methodology", question: "field単位の根拠・権利・期限をどう監査するか", readerOutcome: "数値ごとの出典と鮮度を読者自身が確認できる", numericFields: [
    { key: "evidence.review_interval_days", label: "確認間隔日数", valueKind: "duration", inputScope: "human_scenario" },
  ] },
] as const;

export const firstReleasePilotIds = ["P01", "P02", "P03"] as const;

/**
 * Launch-quarter drafting order. Transaction-intent pages are completed first,
 * while the first public review batch remains P01-P03.
 */
export const launchDraftPriority = [
  "P01",
  "P06",
  "P07",
  "P08",
  "P09",
  "P02",
  "P03",
  "P04",
  "P05",
  "P11",
  "P10",
  "P12",
] as const satisfies readonly PilotPage["id"][];

export function launchPriorityPages(): readonly PilotPage[] {
  const byId = new Map(pilotPages.map((page) => [page.id, page]));
  return launchDraftPriority.map((id) => {
    const page = byId.get(id);
    if (!page) throw new Error(`Unknown launch-priority article: ${id}`);
    return page;
  });
}

export function pilotPage(slug: string): PilotPage {
  const page = pilotPages.find((candidate) => candidate.slug === slug);
  if (!page) throw new Error(`Unknown editorial template slug: ${slug}`);
  return page;
}

export function pilotFieldScope(field: PilotNumericField): "vendor_plan" | "human_scenario" {
  return field.inputScope ?? "vendor_plan";
}
