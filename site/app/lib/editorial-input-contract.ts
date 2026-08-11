import { pilotFieldScope, type PilotPage, type PilotNumericField } from "./pilot-pages.ts";
import type { ServerZeroInputContract } from "./tco.ts";

export type EditorialScopeKind = "vendor_plan" | "human_scenario";
export type EditorialValueStatus = "known" | "unknown" | "not_applicable";
export type EditorialCurrencyStatus = "known" | "unknown" | "not_applicable";
export type EditorialReviewStatus = "unreviewed" | "approved" | "rejected";
export type EditorialBillingToggleState = "annual_selected" | "monthly_selected" | "not_present" | "unknown";
export type EditorialSaleBannerState = "none" | "annual_discount_permanent" | "time_limited_promo" | "unknown";
export type EditorialObservedPriceBasis = "checkout_billed_total" | "displayed_price" | "human_scenario" | "not_applicable" | "unknown";

export type EditorialFieldFormValue = {
  billingToggleState: EditorialBillingToggleState | "";
  saleBannerState: EditorialSaleBannerState | "";
  valueStatus: EditorialValueStatus;
  value: string;
  unit: string;
  unknownReason: string;
  currencyStatus: EditorialCurrencyStatus;
  currency: string;
  currencyDisplay: string;
  currencyUnknownReason: string;
  billingPeriod: string;
  taxTreatment: string;
  observedPriceBasis: EditorialObservedPriceBasis | "";
  monthlyReferenceValue: string;
  sourceUrl: string;
  observedOn: string;
  nextReviewOn: string;
};

export type EditorialRowFormValue = {
  rowId: string;
  scopeKind: EditorialScopeKind;
  vendorId: string;
  planId: string;
  scenarioBasis: string;
  billingToggleState: EditorialBillingToggleState | "";
  saleBannerState: EditorialSaleBannerState | "";
  values: Record<string, EditorialFieldFormValue>;
};

export type EditorialContract = {
  schema_version: "2.3";
  article_id: PilotPage["id"];
  slug: string;
  title: string;
  disclosure_version: "pr-affiliate-v1";
  numeric_fields: Array<{
    schema_version: "2.3";
    scope_kind: EditorialScopeKind;
    vendor_id: string | null;
    plan_id: string | null;
    field: string;
    value_kind: PilotNumericField["valueKind"];
    value_status: EditorialValueStatus;
    value: string | null;
    unit: string | null;
    unknown_reason: string | null;
    currency_status: EditorialCurrencyStatus;
    currency: string | null;
    currency_display: string | null;
    currency_unknown_reason: string | null;
    billing_period: string | null;
    tax_treatment: string | null;
    billing_toggle_state: EditorialBillingToggleState | null;
    sale_banner_state: EditorialSaleBannerState | null;
    observed_price_basis: EditorialObservedPriceBasis | null;
    derived_monthly_value: string | null;
    derived_monthly_unit: "/ mo" | null;
    derivation_method: "annual_checkout_total_divided_by_12" | null;
    monthly_reference_value: string | null;
    monthly_reference_unit: "/ mo" | null;
    derived_annual_discount_percent: string | null;
    discount_derivation_method: "one_minus_annual_total_divided_by_monthly_price_times_12" | null;
    source_url: string | null;
    scenario_basis: string | null;
    observed_on: string;
    next_review_on: string;
    entered_by: "human";
    acquisition_method: "manual_public_page" | "manual_checkout_review" | "human_scenario_input";
    rights_path: "human_editorial";
    review_status: EditorialReviewStatus;
  }>;
  article_review_status: EditorialReviewStatus;
};

export type EditorialValidation = {
  errors: Readonly<Record<string, readonly string[]>>;
  calculationBlockers: readonly string[];
  contract: EditorialContract | null;
};

type ServerCandidateArtifact = {
  schema_version: "1.0";
  category_id: "servers";
  template_kind: "pricing_tco";
  state: "candidate_only";
  numeric_fields: EditorialContract["numeric_fields"];
};

export type ServerCandidateEvidence = {
  vendorId: string;
  planId: string;
  displayName: string;
  knownCount: number;
  unknownCount: number;
  notApplicableCount: number;
  fields: EditorialContract["numeric_fields"];
  calculatorContract: ServerZeroInputContract;
  tcoBlockers: readonly string[];
  suitabilityBlockers: readonly string[];
};

export const serverEvidenceLabels: Readonly<Record<string, string>> = {
  "pricing.initial_fee": "初期費用",
  "pricing.base_price": "12か月の基本料金",
  "pricing.renewal_fee": "更新時請求額",
  "servers.campaign_price": "キャンペーン価格",
  "servers.campaign_period_months": "キャンペーン適用期間",
  "servers.domain_benefit_amount": "ドメイン特典の確認額",
  "servers.domain_benefit_period_months": "ドメイン特典の適用期間",
  "servers.compute_hours": "計算資源の時間上限",
  "servers.storage_gb": "ストレージ容量",
  "servers.data_transfer_gb": "データ転送量",
  "servers.backup_price": "バックアップ料金",
};

type EditorialEvidenceReuseRule = {
  sourceArticleId: PilotPage["id"];
  sourceField: string;
  targetArticleId: PilotPage["id"];
  targetField: string;
  vendorId: string;
  planId: string;
};

const editorialEvidenceReuseRules: readonly EditorialEvidenceReuseRule[] = [
  { sourceArticleId: "P02", sourceField: "plan.minimum_seats", targetArticleId: "P04", targetField: "team.minimum_seats", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P06", sourceField: "billing.monthly_contract_price", targetArticleId: "P04", targetField: "team.monthly_price", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P02", sourceField: "plan.price", targetArticleId: "P05", targetField: "enterprise.agency_annual_checkout_total", vendorId: "mangools", planId: "agency" },
  { sourceArticleId: "P01", sourceField: "pricing.base_price", targetArticleId: "P08", targetField: "addon.base_price", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P03", sourceField: "alternative.required_addon_price", targetArticleId: "P08", targetField: "addon.price", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P02", sourceField: "plan.minimum_seats", targetArticleId: "P08", targetField: "addon.required_seats", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P01", sourceField: "pricing.base_price", targetArticleId: "P10", targetField: "localization.displayed_price", vendorId: "mangools", planId: "basic" },
  { sourceArticleId: "P01", sourceField: "pricing.tax_rate", targetArticleId: "P10", targetField: "localization.tax_rate", vendorId: "mangools", planId: "basic" },
] as const;

type EditorialExplicitUnknownRule = {
  targetArticleId: PilotPage["id"];
  targetField: string;
  unknownReason: string;
  sourceUrl?: string;
  observedOn: string;
  nextReviewOn: string;
  billingToggleState?: EditorialBillingToggleState;
  saleBannerState?: EditorialSaleBannerState;
  scenarioBasis?: string;
  currencyUnknownReason?: string;
  vendorId?: string;
  planId?: string;
};

type EditorialExplicitKnownRule = {
  targetArticleId: PilotPage["id"];
  targetField: string;
  vendorId: string;
  planId: string;
  value: string;
  unit: string;
  sourceUrl: string;
  observedOn: string;
  nextReviewOn: string;
  billingToggleState: EditorialBillingToggleState;
  saleBannerState: EditorialSaleBannerState;
};

const editorialExplicitKnownRules: readonly EditorialExplicitKnownRule[] = [
  {
    targetArticleId: "P05",
    targetField: "enterprise.agency_extra_seats_available",
    vendorId: "mangools",
    planId: "agency",
    value: "5",
    unit: "extra seats available",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
  },
  {
    targetArticleId: "P05",
    targetField: "enterprise.site_analysis_requests_per_24h",
    vendorId: "mangools",
    planId: "agency",
    value: "150",
    unit: "requests / 24h",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
  },
] as const;

const editorialExplicitUnknownRules: readonly EditorialExplicitUnknownRule[] = [
  {
    targetArticleId: "P04",
    targetField: "team.monthly_operation_hours",
    unknownReason: "SaaS TCO Labの実運用による月間運用時間をまだ観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labで実運用を開始した後に月間運用時間と初回導入時間を測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P04",
    targetField: "team.onboarding_hours",
    unknownReason: "SaaS TCO Labの初回導入に要したHuman作業時間をまだ観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labで実運用を開始した後に月間運用時間と初回導入時間を測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P05",
    targetField: "enterprise.migration_support_price",
    unknownReason: "公式価格ページで組織向け移行支援の料金を確認できていない",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
    currencyUnknownReason: "移行支援料金自体が未確認のためISO通貨を確定していない",
    vendorId: "mangools",
    planId: "agency",
  },
  {
    targetArticleId: "P08",
    targetField: "addon.billing_unit_size",
    unknownReason: "公式価格ページで別売の必須addonに対する課金単位を確認できていない",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-01",
    nextReviewOn: "2026-08-31",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
  },
  {
    targetArticleId: "P09",
    targetField: "migration.overlap_months",
    unknownReason: "SaaS TCO Labで実移行をまだ行っておらず、重複契約期間を観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実移行後に重複契約、作業、教育、時間単価を測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P09",
    targetField: "migration.work_hours",
    unknownReason: "SaaS TCO Labで実移行をまだ行っておらず、移行作業時間を観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実移行後に重複契約、作業、教育、時間単価を測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P09",
    targetField: "migration.hourly_cost",
    unknownReason: "移行担当者の時間単価をHumanシナリオとしてまだ確定していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実移行後に重複契約、作業、教育、時間単価を測定する。現時点は自データ未取得。",
    currencyUnknownReason: "移行シナリオの時間単価と通貨をまだ選定していない",
  },
  {
    targetArticleId: "P09",
    targetField: "migration.training_hours",
    unknownReason: "SaaS TCO Labで実移行をまだ行っておらず、教育時間を観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実移行後に重複契約、作業、教育、時間単価を測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P09",
    targetField: "migration.support_price",
    unknownReason: "公式価格ページで移行支援料金を確認できていない",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-01",
    nextReviewOn: "2026-08-31",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
    currencyUnknownReason: "移行支援料金自体が未確認のためISO通貨を確定していない",
  },
  {
    targetArticleId: "P10",
    targetField: "localization.exchange_rate",
    unknownReason: "公式価格画面はUSD表示で、記事用のJPY換算レートをHuman確認していない",
    sourceUrl: "https://mangools.com/subscriptions/checkout",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
    billingToggleState: "annual_selected",
    saleBannerState: "annual_discount_permanent",
  },
  {
    targetArticleId: "P11",
    targetField: "break_even.monthly_hours_saved",
    unknownReason: "SaaS TCO Labの導入前後で月間削減時間をまだ比較観測していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実運用開始後に導入前後の時間、時間単価、導入費、月額TCOを同じ期間で測定する。現時点は自データ未取得。",
  },
  {
    targetArticleId: "P11",
    targetField: "break_even.hourly_cost",
    unknownReason: "損益分岐に使う担当者の時間単価をHumanシナリオとしてまだ確定していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実運用開始後に導入前後の時間、時間単価、導入費、月額TCOを同じ期間で測定する。現時点は自データ未取得。",
    currencyUnknownReason: "損益分岐シナリオの時間単価と通貨をまだ選定していない",
  },
  {
    targetArticleId: "P11",
    targetField: "break_even.implementation_cost",
    unknownReason: "SaaS TCO Labの導入作業費をHumanシナリオとしてまだ確定していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実運用開始後に導入前後の時間、時間単価、導入費、月額TCOを同じ期間で測定する。現時点は自データ未取得。",
    currencyUnknownReason: "導入費シナリオの通貨をまだ選定していない",
  },
  {
    targetArticleId: "P11",
    targetField: "break_even.monthly_tco",
    unknownReason: "損益分岐用の月額TCOをHumanシナリオとしてまだ確定していない",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "SaaS TCO Labの実運用開始後に導入前後の時間、時間単価、導入費、月額TCOを同じ期間で測定する。現時点は自データ未取得。",
    currencyUnknownReason: "損益分岐シナリオの月額TCO通貨をまだ選定していない",
  },
  {
    targetArticleId: "P12",
    targetField: "evidence.review_interval_days",
    unknownReason: "全field共通の単一確認間隔は定めず、各観測の次回確認日を個別に管理している",
    observedOn: "2026-08-09",
    nextReviewOn: "2026-09-07",
    scenarioBasis: "価格・税・利用上限ごとに観測日と次回確認日を記録し、共通日数を推測して補完しない。",
  },
] as const;

export type ReusableEditorialEvidence = {
  appliedFields: readonly string[];
  explicitUnknownFields: readonly string[];
  rows: readonly EditorialRowFormValue[];
};

export type ServerPromotionAssessment = {
  tcoReady: boolean;
  suitabilityReady: boolean;
  contractPromotionReady: boolean;
  tcoBlockers: readonly string[];
  suitabilityBlockers: readonly string[];
  reviewBlockers: readonly string[];
};

const serverTcoFields = new Set([
  "pricing.initial_fee",
  "pricing.base_price",
  "pricing.renewal_fee",
  "servers.campaign_price",
  "servers.campaign_period_months",
  "servers.domain_benefit_amount",
  "servers.domain_benefit_period_months",
  "servers.backup_price",
]);

const serverSuitabilityFields = new Set([
  "servers.compute_hours",
  "servers.storage_gb",
  "servers.data_transfer_gb",
]);

function serverFieldReadinessBlockers(
  field: EditorialContract["numeric_fields"][number],
): string[] {
  if (field.value_status === "not_applicable") return [];
  const blockers: string[] = [];
  if (field.value_status === "unknown") blockers.push(`${field.field}: 値が未確認`);
  if (field.billing_toggle_state === "unknown") blockers.push(`${field.field}: 支払周期表示が不明`);
  if (field.sale_banner_state === "unknown") blockers.push(`${field.field}: 価格表示分類が不明`);
  if (field.sale_banner_state === "time_limited_promo") blockers.push(`${field.field}: 期間限定価格`);
  if (field.value_kind === "price" && field.value_status === "known") {
    if (field.currency_status !== "known") blockers.push(`${field.field}: ISO通貨が未確認`);
    if (!field.billing_period || field.billing_period === "unknown") blockers.push(`${field.field}: 請求周期が未確認`);
    if (!field.tax_treatment || field.tax_treatment === "unknown") blockers.push(`${field.field}: 税区分が未確認`);
    if (!field.observed_price_basis || field.observed_price_basis === "unknown") blockers.push(`${field.field}: 一次観測区分が未確認`);
  }
  return blockers;
}

/**
 * Classify a validated servers candidate without promoting or mutating it.
 * Article approval, index and CTA remain separate Human gates even when this is ready.
 */
export function assessServerPromotionCandidate(
  numericFields: readonly EditorialContract["numeric_fields"][number][],
): ServerPromotionAssessment {
  const tcoBlockers = numericFields
    .filter((field) => serverTcoFields.has(field.field))
    .flatMap(serverFieldReadinessBlockers);
  const suitabilityBlockers = numericFields
    .filter((field) => serverSuitabilityFields.has(field.field))
    .flatMap(serverFieldReadinessBlockers);
  const reviewBlockers = numericFields
    .filter((field) => field.review_status !== "approved")
    .map((field) => `${field.field}: ${field.review_status === "rejected" ? "却下済み" : "Human field確認待ち"}`);

  return {
    tcoReady: tcoBlockers.length === 0,
    suitabilityReady: suitabilityBlockers.length === 0,
    contractPromotionReady: tcoBlockers.length === 0
      && suitabilityBlockers.length === 0
      && reviewBlockers.length === 0,
    tcoBlockers: [...new Set(tcoBlockers)],
    suitabilityBlockers: [...new Set(suitabilityBlockers)],
    reviewBlockers: [...new Set(reviewBlockers)],
  };
}

export function hasUnknownFact(field: EditorialContract["numeric_fields"][number]): boolean {
  return field.value_status === "unknown"
    || field.currency_status === "unknown"
    || field.billing_period === "unknown"
    || field.tax_treatment === "unknown"
    || field.billing_toggle_state === "unknown"
    || field.sale_banner_state === "unknown"
    || field.sale_banner_state === "time_limited_promo"
    || field.observed_price_basis === "unknown";
}

export type ExtractedPriceCandidate = {
  id: string;
  lineNumber: number;
  sourceLine: string;
  value: string;
  currency: string | null;
  currencyDisplay: string | null;
  billingPeriod: string | null;
  taxTreatment: string | null;
  warnings: readonly string[];
};

export type PriceTextExtraction = {
  error: string | null;
  candidates: readonly ExtractedPriceCandidate[];
};

const safeQueryKeys = new Set([
  "billing", "country", "currency", "edition", "lang", "locale", "period", "plan", "region",
]);
const trackingMarkers = ["affiliate", "aff", "clickid", "partner", "ref", "subid", "tracking", "utm_"];
const billingPeriods = new Set(["monthly", "annual", "one_time", "per_usage", "not_applicable", "unknown"]);
const taxTreatments = new Set(["included", "excluded", "not_applicable", "unknown"]);
const billingToggleStates = new Set(["annual_selected", "monthly_selected", "not_present", "unknown"]);
const saleBannerStates = new Set(["none", "annual_discount_permanent", "time_limited_promo", "unknown"]);
const observedPriceBases = new Set(["checkout_billed_total", "displayed_price", "human_scenario", "not_applicable", "unknown"]);
const slugPattern = /^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$/;
const dayMilliseconds = 86_400_000;
const maximumPasteCharacters = 100_000;
const maximumCandidates = 200;

function addError(target: Record<string, string[]>, key: string, message: string) {
  (target[key] ??= []).push(message);
}

function isoDay(value: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const stamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(stamp);
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) return null;
  return stamp / dayMilliseconds;
}

function validateSourceUrl(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "公式ページの完全なURLをHTTPS形式で入力してください。";
  }
  if (url.protocol !== "https:") return "出典URLはHTTPS形式の公開ページにしてください。";
  if (url.username || url.password || url.hash) return "認証情報や # 付き位置情報をURLから削除してください。";
  const host = url.hostname.toLowerCase();
  if (["localhost", "127.0.0.1", "[::1]", "::1"].includes(host) || host.endsWith(".local")) {
    return "localhostではなく、Humanが確認した公開ページURLを入力してください。";
  }
  for (const [key, rawValue] of url.searchParams.entries()) {
    const normalized = key.toLowerCase();
    if (!safeQueryKeys.has(normalized) || trackingMarkers.some((marker) => normalized.includes(marker))) {
      return `URLの「${key}」parameterを削除してください。tracking・紹介parameterは保存できません。`;
    }
    if (!rawValue || rawValue.length > 80) return `URLの「${key}」parameter値を確認してください。`;
  }
  return null;
}

export function emptyEditorialField(): EditorialFieldFormValue {
  return {
    billingToggleState: "",
    saleBannerState: "",
    valueStatus: "known",
    value: "",
    unit: "",
    unknownReason: "",
    currencyStatus: "not_applicable",
    currency: "",
    currencyDisplay: "",
    currencyUnknownReason: "",
    billingPeriod: "",
    taxTreatment: "",
    observedPriceBasis: "",
    monthlyReferenceValue: "",
    sourceUrl: "",
    observedOn: "",
    nextReviewOn: "",
  };
}

export function emptyEditorialRow(
  page: PilotPage,
  scopeKind: EditorialScopeKind,
  rowId: string,
): EditorialRowFormValue {
  return {
    rowId,
    scopeKind,
    vendorId: "",
    planId: "",
    scenarioBasis: scopeKind === "human_scenario" ? "Humanが設定した記事計算scenario" : "",
    billingToggleState: "",
    saleBannerState: "",
    values: Object.fromEntries(
      page.numericFields
        .filter((field) => pilotFieldScope(field) === scopeKind)
        .map((field) => [field.key, {
          ...emptyEditorialField(),
          currencyStatus: field.valueKind === "price" ? "" as EditorialCurrencyStatus : "not_applicable",
        }]),
    ),
  };
}

const zeroMinorUnitCurrencies = new Set([
  "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF",
]);
const threeMinorUnitCurrencies = new Set(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]);
const fourMinorUnitCurrencies = new Set(["CLF", "UYW"]);

function currencyMinorUnitDigits(currency: string): number | null {
  const normalized = currency.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(normalized)) return null;
  if (zeroMinorUnitCurrencies.has(normalized)) return 0;
  if (threeMinorUnitCurrencies.has(normalized)) return 3;
  if (fourMinorUnitCurrencies.has(normalized)) return 4;
  return 2;
}

/** Match Python exact minor-unit division. Never round a derived monthly value. */
export function annualMonthlyEquivalent(value: string, currency: string): string | null {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  const minorUnitDigits = currencyMinorUnitDigits(currency);
  if (minorUnitDigits === null) return null;
  const sign = match[1] === "-" ? -1n : 1n;
  const fraction = match[3] ?? "";
  if (fraction.length > minorUnitDigits && /[1-9]/.test(fraction.slice(minorUnitDigits))) return null;
  const scale = 10n ** BigInt(minorUnitDigits);
  const fractionInMinorUnits = BigInt((fraction.slice(0, minorUnitDigits) || "0").padEnd(minorUnitDigits, "0"));
  const annualMinorUnits = sign * (BigInt(match[2]) * scale + fractionInMinorUnits);
  if (annualMinorUnits % 12n !== 0n) return null;
  const monthlyMinorUnits = annualMinorUnits / 12n;
  const negative = monthlyMinorUnits < 0n;
  const absolute = negative ? -monthlyMinorUnits : monthlyMinorUnits;
  const whole = absolute / scale;
  const decimals = minorUnitDigits === 0
    ? ""
    : (absolute % scale).toString().padStart(minorUnitDigits, "0").replace(/0+$/, "");
  const normalized = decimals ? `${whole}.${decimals}` : whole.toString();
  return negative && absolute !== 0n ? `-${normalized}` : normalized;
}

function unsignedDecimalParts(value: string): { coefficient: bigint; scaleDigits: number } | null {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  const fraction = match[2] ?? "";
  if (fraction.length > 8) return null;
  return {
    coefficient: BigInt(`${match[1]}${fraction}`),
    scaleDigits: fraction.length,
  };
}

/** Match Python ROUND_HALF_UP to the nearest whole percent without floating-point drift. */
export function annualDiscountPercent(
  annualTotal: string,
  monthlyReference: string,
): string | null {
  const annual = unsignedDecimalParts(annualTotal);
  const monthly = unsignedDecimalParts(monthlyReference);
  if (!annual || !monthly || monthly.coefficient <= 0n) return null;
  const scaleDigits = Math.max(annual.scaleDigits, monthly.scaleDigits);
  const annualCoefficient = annual.coefficient * (10n ** BigInt(scaleDigits - annual.scaleDigits));
  const monthlyTwelveCoefficient = monthly.coefficient
    * (10n ** BigInt(scaleDigits - monthly.scaleDigits))
    * 12n;
  if (annualCoefficient >= monthlyTwelveCoefficient) return null;
  const discountNumerator = (monthlyTwelveCoefficient - annualCoefficient) * 100n;
  let rounded = discountNumerator / monthlyTwelveCoefficient;
  const remainder = discountNumerator % monthlyTwelveCoefficient;
  if (remainder * 2n >= monthlyTwelveCoefficient) rounded += 1n;
  return rounded.toString();
}

function exactlyOne(values: readonly string[], warning: string, warnings: string[]) {
  const unique = [...new Set(values)];
  if (unique.length > 1) {
    warnings.push(warning);
    return null;
  }
  return unique[0] ?? null;
}

function explicitCurrency(line: string, warnings: string[]) {
  const values: string[] = [];
  const patterns: ReadonlyArray<readonly [string, RegExp]> = [
    ["JPY", /(?:\bJPY\b|日本円|[¥￥]|円)/iu],
    ["USD", /(?:\bUSD\b|US\$)/iu],
    ["EUR", /(?:\bEUR\b|€)/iu],
    ["GBP", /(?:\bGBP\b|£)/iu],
    ["AUD", /\bAUD\b/iu],
    ["CAD", /\bCAD\b/iu],
    ["NZD", /\bNZD\b/iu],
    ["SGD", /\bSGD\b/iu],
    ["HKD", /\bHKD\b/iu],
    ["CNY", /\bCNY\b/iu],
    ["KRW", /\bKRW\b/iu],
    ["INR", /\bINR\b/iu],
  ];
  for (const [currency, pattern] of patterns) {
    if (pattern.test(line)) values.push(currency);
  }
  if (/\$/u.test(line) && !/(?:\bUSD\b|US\$)/iu.test(line)) {
    warnings.push("$記号だけでは通貨を確定できません。表示記号だけをunknownとして保持します。");
  }
  return exactlyOne(values, "同じ行に複数通貨があるため、通貨は事前入力しません。", warnings);
}

function ambiguousCurrencyDisplay(line: string, currency: string | null) {
  if (!currency && /\$/u.test(line)) return "$";
  return null;
}

function explicitBillingPeriod(line: string, warnings: string[]) {
  const values: string[] = [];
  if (/(?:月額|毎月|\/\s*(?:月|month|mo)\b|per\s+month|monthly)/iu.test(line)) values.push("monthly");
  if (/(?:年額|年間|毎年|\/\s*(?:年|year|yr)\b|per\s+year|annual|yearly)/iu.test(line)) values.push("annual");
  if (/(?:従量|\/\s*回|per\s+(?:use|request|unit))/iu.test(line)) values.push("per_usage");
  if (/(?:一回|一度限り|買い切り|one[- ]time)/iu.test(line)) values.push("one_time");
  return exactlyOne(values, "同じ行に複数の請求周期があるため、周期は事前入力しません。", warnings);
}

function explicitTaxTreatment(line: string, warnings: string[]) {
  const values: string[] = [];
  if (/(?:税込|税を含|tax\s+included|incl\.?\s*tax)/iu.test(line)) values.push("included");
  if (/(?:税別|税を含ま|tax\s+excluded|excl\.?\s*tax|plus\s+tax)/iu.test(line)) values.push("excluded");
  return exactlyOne(values, "同じ行に税込・税別の両方があるため、税区分は事前入力しません。", warnings);
}

/** Parse explicit candidates in memory. Raw text never enters the contract. */
export function extractPriceTextCandidates(rawText: string): PriceTextExtraction {
  if (!rawText.trim()) {
    return { error: "価格ページからコピーしたテキストを貼り付けてください。", candidates: [] };
  }
  if (rawText.length > maximumPasteCharacters) {
    return { error: `貼り付けは${maximumPasteCharacters.toLocaleString("ja-JP")}文字以内に分けてください。`, candidates: [] };
  }

  const candidates: ExtractedPriceCandidate[] = [];
  const lines = rawText.normalize("NFKC").split(/\r?\n/u);
  for (const [lineIndex, rawLine] of lines.entries()) {
    const line = rawLine.replace(/\s+/gu, " ").trim();
    if (!line || line.includes("://")) continue;
    const numericPattern = /[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/gu;
    for (const match of line.matchAll(numericPattern)) {
      const value = match[0].replaceAll(",", "");
      const unsigned = value.replace(/^[+-]/u, "");
      const [whole, fraction = ""] = unsigned.split(".");
      if (`${whole}${fraction}`.length > 30 || fraction.length > 8) continue;
      const warnings: string[] = [];
      if (/\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b/u.test(line)) {
        warnings.push("日付を含む行です。価格・上限値かをHumanが確認してください。");
      }
      const currency = explicitCurrency(line, warnings);
      candidates.push({
        id: `line-${lineIndex + 1}-candidate-${candidates.length + 1}`,
        lineNumber: lineIndex + 1,
        sourceLine: line.slice(0, 300),
        value,
        currency,
        currencyDisplay: ambiguousCurrencyDisplay(line, currency),
        billingPeriod: explicitBillingPeriod(line, warnings),
        taxTreatment: explicitTaxTreatment(line, warnings),
        warnings,
      });
      if (candidates.length >= maximumCandidates) {
        return {
          error: `候補が${maximumCandidates}件に達しました。必要な料金表部分だけに分けて再解析してください。`,
          candidates,
        };
      }
    }
  }
  if (!candidates.length) {
    return { error: "数値候補を見つけられませんでした。料金・上限が見える範囲をコピーしてください。", candidates: [] };
  }
  return { error: null, candidates };
}

export function prefillExtractedCandidate(
  field: PilotNumericField,
  current: EditorialFieldFormValue,
  candidate: ExtractedPriceCandidate,
): EditorialFieldFormValue {
  const pricePrefill = field.valueKind === "price" ? {
    currencyStatus: candidate.currency ? "known" as const : candidate.currencyDisplay ? "unknown" as const : current.currencyStatus,
    currency: candidate.currency ?? current.currency,
    currencyDisplay: candidate.currencyDisplay ?? current.currencyDisplay,
    currencyUnknownReason: candidate.currencyDisplay
      ? "公式表示が通貨記号のみでISO 4217 codeを確認できない"
      : current.currencyUnknownReason,
    billingPeriod: candidate.billingPeriod ?? current.billingPeriod,
    taxTreatment: candidate.taxTreatment ?? current.taxTreatment,
  } : {};
  return {
    ...current,
    valueStatus: "known",
    value: candidate.value,
    ...pricePrefill,
  };
}

function fieldsForRow(page: PilotPage, row: EditorialRowFormValue) {
  return page.numericFields.filter((field) => pilotFieldScope(field) === row.scopeKind);
}

export function valuesFromContract(page: PilotPage, contract: EditorialContract): EditorialRowFormValue[] | null {
  if (contract.schema_version !== "2.3" || contract.article_id !== page.id) return null;
  const groups = new Map<string, EditorialRowFormValue>();
  for (const stored of contract.numeric_fields) {
    const field = page.numericFields.find((candidate) => candidate.key === stored.field);
    if (!field || field.valueKind !== stored.value_kind || pilotFieldScope(field) !== stored.scope_kind) return null;
    const identity = stored.scope_kind === "vendor_plan"
      ? `vendor_plan:${stored.vendor_id ?? ""}:${stored.plan_id ?? ""}`
      : "human_scenario";
    const row = groups.get(identity) ?? {
      rowId: `stored-${groups.size + 1}`,
      scopeKind: stored.scope_kind,
      vendorId: stored.vendor_id ?? "",
      planId: stored.plan_id ?? "",
      scenarioBasis: stored.scenario_basis ?? "",
      billingToggleState: "",
      saleBannerState: "",
      values: {},
    };
    row.values[stored.field] = {
      billingToggleState: stored.billing_toggle_state ?? "",
      saleBannerState: stored.sale_banner_state ?? "",
      valueStatus: stored.value_status,
      value: stored.value ?? "",
      unit: stored.unit ?? "",
      unknownReason: stored.unknown_reason ?? "",
      currencyStatus: stored.currency_status,
      currency: stored.currency ?? "",
      currencyDisplay: stored.currency_display ?? "",
      currencyUnknownReason: stored.currency_unknown_reason ?? "",
      billingPeriod: stored.billing_period ?? "",
      taxTreatment: stored.tax_treatment ?? "",
      observedPriceBasis: stored.observed_price_basis ?? "",
      monthlyReferenceValue: stored.monthly_reference_value ?? "",
      sourceUrl: stored.source_url ?? "",
      observedOn: stored.observed_on,
      nextReviewOn: stored.next_review_on,
    };
    groups.set(identity, row);
  }
  const rows = [...groups.values()];
  for (const row of rows) {
    if (fieldsForRow(page, row).some((field) => !row.values[field.key])) return null;
  }
  return rows;
}

export function validateEditorialInput(
  page: PilotPage,
  rows: readonly EditorialRowFormValue[],
): EditorialValidation {
  const errors: Record<string, string[]> = {};
  const calculationBlockers: string[] = [];
  const numericFields: EditorialContract["numeric_fields"] = [];
  const neededScopes = new Set(page.numericFields.map(pilotFieldScope));
  for (const scope of neededScopes) {
    if (!rows.some((row) => row.scopeKind === scope)) {
      addError(errors, "_rows", scope === "vendor_plan" ? "vendor・plan行を1件以上追加してください。" : "Humanシナリオ行が必要です。");
    }
  }

  const identities = new Set<string>();
  for (const row of rows) {
    const rowPrefix = row.rowId;
    const vendorId = row.vendorId.trim();
    const planId = row.planId.trim();
    const scenarioBasis = row.scenarioBasis.trim().replace(/\s+/g, " ");
    let identity: string;
    if (row.scopeKind === "vendor_plan") {
      if (!slugPattern.test(vendorId)) addError(errors, `${rowPrefix}.vendorId`, "vendor識別子は英小文字・数字・ハイフンで入力してください（例: mangools）。");
      if (!slugPattern.test(planId)) addError(errors, `${rowPrefix}.planId`, "plan識別子は英小文字・数字・ハイフンで入力してください（例: basic）。");
      identity = `vendor_plan:${vendorId}:${planId}`;
    } else {
      if (!scenarioBasis || scenarioBasis.length > 300) addError(errors, `${rowPrefix}.scenarioBasis`, "Humanシナリオの根拠を300文字以内で入力してください。個人情報は入れません。");
      identity = "human_scenario";
    }
    if (identities.has(identity)) addError(errors, `${rowPrefix}.identity`, "同じvendor・plan行またはHumanシナリオ行が重複しています。");
    identities.add(identity);

    for (const field of fieldsForRow(page, row)) {
      const current = row.values[field.key] ?? emptyEditorialField();
      const prefix = `${rowPrefix}.${field.key}`;
      const billingToggleState = current.billingToggleState || row.billingToggleState;
      const saleBannerState = current.saleBannerState || row.saleBannerState;
      if (row.scopeKind === "vendor_plan") {
        if (!billingToggleStates.has(billingToggleState)) addError(errors, `${prefix}.billingToggleState`, "このfieldを確認した時のbilling toggle位置を選択してください。見当たらなければ「toggleなし」、判別不能なら「不明」です。");
        if (!saleBannerStates.has(saleBannerState)) addError(errors, `${prefix}.saleBannerState`, "このfieldの価格表示を「なし・年払い恒常割引・期間限定promo・不明」の4区分から選択してください。");
        if (billingToggleState === "unknown") calculationBlockers.push(`${identity} / ${field.key}: billing toggle unknown`);
        if (saleBannerState === "unknown") calculationBlockers.push(`${identity} / ${field.key}: sale banner unknown`);
        if (saleBannerState === "time_limited_promo") calculationBlockers.push(`${identity} / ${field.key}: time-limited promo`);
      }
      const valueStatus = current.valueStatus;
      const numeric = current.value.trim();
      const unit = current.unit.trim().replace(/\s+/g, " ");
      const unknownReason = current.unknownReason.trim().replace(/\s+/g, " ");
      let contractValue: string | null = null;
      let contractUnit: string | null = null;
      let contractUnknownReason: string | null = null;

      if (valueStatus === "known") {
        const decimalMatch = /^[+-]?\d+(?:\.\d+)?$/.exec(numeric);
        if (!numeric) addError(errors, `${prefix}.value`, "確認した数値を入力してください。不明なら値状態を「不明」にします。");
        else if (!decimalMatch) addError(errors, `${prefix}.value`, "数値だけを入力してください。通貨記号やカンマは別欄へ分けます。");
        else {
          const unsigned = numeric.replace(/^[+-]/, "");
          const [whole, fraction = ""] = unsigned.split(".");
          if (`${whole}${fraction}`.length > 30) addError(errors, `${prefix}.value`, "数値は合計30桁以内にしてください。");
          if (fraction.length > 8) addError(errors, `${prefix}.value`, "小数は8桁以内にしてください。");
        }
        if (!unit) addError(errors, `${prefix}.unit`, "画面表記どおりの単位を入力してください。推測して埋めません。");
        else if (unit.length > 80) addError(errors, `${prefix}.unit`, "単位は80文字以内にしてください。");
        contractValue = numeric;
        contractUnit = unit;
      } else {
        if (numeric) addError(errors, `${prefix}.value`, "不明・該当なしでは数値欄を空にしてください。");
        if (!unknownReason || unknownReason.length > 300) addError(errors, `${prefix}.unknownReason`, "不明または該当なしの理由を300文字以内で入力してください。");
        contractUnit = unit || null;
        contractUnknownReason = unknownReason;
        calculationBlockers.push(`${identity} / ${field.key}: ${valueStatus}`);
      }

      let currencyStatus: EditorialCurrencyStatus = "not_applicable";
      let currency: string | null = null;
      let currencyDisplay: string | null = null;
      let currencyUnknownReason: string | null = null;
      let billingPeriod: string | null = null;
      let taxTreatment: string | null = null;
      let observedPriceBasis: EditorialObservedPriceBasis | null = null;
      let derivedMonthlyValue: string | null = null;
      let derivedMonthlyUnit: "/ mo" | null = null;
      let derivationMethod: "annual_checkout_total_divided_by_12" | null = null;
      let monthlyReferenceValue: string | null = null;
      let monthlyReferenceUnit: "/ mo" | null = null;
      let derivedAnnualDiscountPercent: string | null = null;
      let discountDerivationMethod: "one_minus_annual_total_divided_by_monthly_price_times_12" | null = null;
      if (field.valueKind === "price") {
        currencyStatus = current.currencyStatus;
        billingPeriod = current.billingPeriod;
        taxTreatment = current.taxTreatment;
        observedPriceBasis = row.scopeKind === "human_scenario" ? "human_scenario" : current.observedPriceBasis || null;
        if (valueStatus === "not_applicable") {
          if (currencyStatus !== "not_applicable") addError(errors, `${prefix}.currencyStatus`, "該当なし価格では通貨状態も「該当なし」にしてください。");
          if (billingPeriod !== "not_applicable") addError(errors, `${prefix}.billingPeriod`, "該当なし価格では請求周期も「該当なし」にしてください。");
          if (taxTreatment !== "not_applicable") addError(errors, `${prefix}.taxTreatment`, "該当なし価格では税区分も「該当なし」にしてください。");
        } else if (currencyStatus === "known") {
          currency = current.currency.trim().toUpperCase();
          if (!/^[A-Z]{3}$/.test(currency)) addError(errors, `${prefix}.currency`, "公式表示で確認したISO通貨codeを英大文字3文字で入力してください。");
        } else if (currencyStatus === "unknown") {
          const displayedCurrency = current.currencyDisplay.trim();
          currencyDisplay = displayedCurrency || null;
          currencyUnknownReason = current.currencyUnknownReason.trim().replace(/\s+/g, " ");
          if (valueStatus === "known" && !displayedCurrency) addError(errors, `${prefix}.currencyDisplay`, "数値が表示されている場合は、公式画面の通貨表記をそのまま入力してください（例: $）。");
          if (displayedCurrency.length > 20) addError(errors, `${prefix}.currencyDisplay`, "画面の通貨表記は20文字以内にしてください。");
          if (!currencyUnknownReason || currencyUnknownReason.length > 300) addError(errors, `${prefix}.currencyUnknownReason`, "通貨を確定できない理由を300文字以内で入力してください。");
          calculationBlockers.push(`${identity} / ${field.key}: currency unknown`);
        } else {
          addError(errors, `${prefix}.currencyStatus`, "通貨を「確認済み」または「不明」として明示してください。");
        }
        if (!billingPeriods.has(billingPeriod ?? "")) addError(errors, `${prefix}.billingPeriod`, "請求周期を選択してください。不明なら「不明」を選びます。");
        if (!taxTreatments.has(taxTreatment ?? "")) addError(errors, `${prefix}.taxTreatment`, "税込・税別を選択してください。不明なら「不明」を選びます。");
        if (!observedPriceBases.has(observedPriceBasis ?? "")) addError(errors, `${prefix}.observedPriceBasis`, "価格の一次観測区分を選択してください。年払いはcheckout請求総額だけを選べます。");
        if (valueStatus === "not_applicable" && observedPriceBasis !== "not_applicable") addError(errors, `${prefix}.observedPriceBasis`, "該当なし価格では一次観測区分も「該当なし」にしてください。");
        else if (row.scopeKind === "human_scenario" && observedPriceBasis !== "human_scenario") addError(errors, `${prefix}.observedPriceBasis`, "Humanシナリオ価格は公式価格の一次観測として扱いません。");
        else if (row.scopeKind === "vendor_plan" && valueStatus === "unknown" && observedPriceBasis !== "unknown") addError(errors, `${prefix}.observedPriceBasis`, "不明価格では一次観測区分も「不明」にしてください。");
        else if (row.scopeKind === "vendor_plan" && valueStatus === "known" && billingPeriod === "annual") {
          if (observedPriceBasis !== "checkout_billed_total") addError(errors, `${prefix}.observedPriceBasis`, "年払いplanの値にはcheckoutで確認した請求総額を入力してください。料金表の月額換算表示は一次観測値にできません。");
          if (billingToggleState !== "annual_selected") addError(errors, `${prefix}.billingPeriod`, "年払いcheckout総額では画面状態を「年払い選択」にしてください。");
          derivedMonthlyValue = annualMonthlyEquivalent(contractValue ?? "", currency ?? "");
          if (derivedMonthlyValue !== null) {
            derivedMonthlyUnit = "/ mo";
            derivationMethod = "annual_checkout_total_divided_by_12";
          }
          if (saleBannerState === "annual_discount_permanent") {
            monthlyReferenceValue = current.monthlyReferenceValue.trim();
            const decimalMatch = /^\d+(?:\.\d+)?$/.exec(monthlyReferenceValue);
            if (!monthlyReferenceValue) {
              addError(errors, `${prefix}.monthlyReferenceValue`, "恒常年払い割引には、同じplanの月払い価格を入力してください。");
            } else if (!decimalMatch) {
              addError(errors, `${prefix}.monthlyReferenceValue`, "月払い比較値は通貨記号を除いた数値だけで入力してください。");
            } else {
              const [whole, fraction = ""] = monthlyReferenceValue.split(".");
              if (`${whole}${fraction}`.length > 30 || fraction.length > 8) {
                addError(errors, `${prefix}.monthlyReferenceValue`, "月払い比較値は合計30桁・小数8桁以内にしてください。");
              }
              derivedAnnualDiscountPercent = annualDiscountPercent(
                contractValue ?? "",
                monthlyReferenceValue,
              );
              if (derivedAnnualDiscountPercent === null) {
                addError(errors, `${prefix}.monthlyReferenceValue`, "年次checkout総額より月払い価格×12が大きい、同一条件の正の月払い価格を確認してください。");
              } else {
                monthlyReferenceUnit = "/ mo";
                discountDerivationMethod = "one_minus_annual_total_divided_by_monthly_price_times_12";
              }
            }
          } else if (current.monthlyReferenceValue.trim()) {
            addError(errors, `${prefix}.monthlyReferenceValue`, "月払い比較値は価格表示分類が「年払い恒常割引」の時だけ入力できます。");
          }
        } else if (
          row.scopeKind === "vendor_plan"
          && valueStatus === "known"
          && !["displayed_price", "checkout_billed_total"].includes(observedPriceBasis ?? "")
        ) addError(errors, `${prefix}.observedPriceBasis`, "確認済み価格の一次観測区分を選択してください。");
        if (billingPeriod === "monthly" && billingToggleState === "annual_selected") addError(errors, `${prefix}.billingPeriod`, "月払い価格に「年払い選択」の画面状態は使えません。");
        if (billingPeriod === "annual" && billingToggleState === "monthly_selected") addError(errors, `${prefix}.billingPeriod`, "年払い価格に「月払い選択」の画面状態は使えません。");
        if (billingPeriod === "unknown") calculationBlockers.push(`${identity} / ${field.key}: billing period unknown`);
        if (taxTreatment === "unknown") calculationBlockers.push(`${identity} / ${field.key}: tax treatment unknown`);
      }

      let sourceUrl: string | null = null;
      if (row.scopeKind === "vendor_plan") {
        sourceUrl = current.sourceUrl.trim();
        const sourceError = validateSourceUrl(sourceUrl);
        if (sourceError) addError(errors, `${prefix}.sourceUrl`, sourceError);
      }

      const observedDay = isoDay(current.observedOn);
      const nextReviewDay = isoDay(current.nextReviewOn);
      if (observedDay === null) addError(errors, `${prefix}.observedOn`, "確認した日をYYYY-MM-DD形式で入力してください。");
      if (nextReviewDay === null) addError(errors, `${prefix}.nextReviewOn`, "次回確認日をYYYY-MM-DD形式で入力してください。");
      if (observedDay !== null && nextReviewDay !== null) {
        if (nextReviewDay <= observedDay) addError(errors, `${prefix}.nextReviewOn`, "次回確認日は観測日より後にしてください。");
        else if (nextReviewDay - observedDay > 180) addError(errors, `${prefix}.nextReviewOn`, "次回確認日は観測日から180日以内にしてください。");
      }

      numericFields.push({
        schema_version: "2.3",
        scope_kind: row.scopeKind,
        vendor_id: row.scopeKind === "vendor_plan" ? vendorId : null,
        plan_id: row.scopeKind === "vendor_plan" ? planId : null,
        field: field.key,
        value_kind: field.valueKind,
        value_status: valueStatus,
        value: contractValue,
        unit: contractUnit,
        unknown_reason: contractUnknownReason,
        currency_status: currencyStatus,
        currency,
        currency_display: currencyDisplay,
        currency_unknown_reason: currencyUnknownReason,
        billing_period: billingPeriod,
        tax_treatment: taxTreatment,
        billing_toggle_state: row.scopeKind === "vendor_plan" ? billingToggleState as EditorialBillingToggleState : null,
        sale_banner_state: row.scopeKind === "vendor_plan" ? saleBannerState as EditorialSaleBannerState : null,
        observed_price_basis: observedPriceBasis,
        derived_monthly_value: derivedMonthlyValue,
        derived_monthly_unit: derivedMonthlyUnit,
        derivation_method: derivationMethod,
        monthly_reference_value: monthlyReferenceValue,
        monthly_reference_unit: monthlyReferenceUnit,
        derived_annual_discount_percent: derivedAnnualDiscountPercent,
        discount_derivation_method: discountDerivationMethod,
        source_url: sourceUrl,
        scenario_basis: row.scopeKind === "human_scenario" ? scenarioBasis : null,
        observed_on: current.observedOn,
        next_review_on: current.nextReviewOn,
        entered_by: "human",
        acquisition_method: row.scopeKind === "human_scenario"
          ? "human_scenario_input"
          : observedPriceBasis === "checkout_billed_total"
            ? "manual_checkout_review"
            : "manual_public_page",
        rights_path: "human_editorial",
        review_status: "unreviewed",
      });
    }
  }

  return {
    errors,
    calculationBlockers: [...new Set(calculationBlockers)],
    contract: Object.keys(errors).length ? null : {
      schema_version: "2.3",
      article_id: page.id,
      slug: page.slug,
      title: page.title,
      disclosure_version: "pr-affiliate-v1",
      numeric_fields: numericFields,
      article_review_status: "unreviewed",
    },
  };
}

function reusableFieldFormValue(
  field: EditorialContract["numeric_fields"][number],
): EditorialFieldFormValue {
  return {
    billingToggleState: field.billing_toggle_state ?? "",
    saleBannerState: field.sale_banner_state ?? "",
    valueStatus: field.value_status,
    value: field.value ?? "",
    unit: field.unit ?? "",
    unknownReason: field.unknown_reason ?? "",
    currencyStatus: field.currency_status,
    currency: field.currency ?? "",
    currencyDisplay: field.currency_display ?? "",
    currencyUnknownReason: field.currency_unknown_reason ?? "",
    billingPeriod: field.billing_period ?? "",
    taxTreatment: field.tax_treatment ?? "",
    observedPriceBasis: field.observed_price_basis ?? "",
    monthlyReferenceValue: field.monthly_reference_value ?? "",
    sourceUrl: field.source_url ?? "",
    observedOn: field.observed_on,
    nextReviewOn: field.next_review_on,
  };
}

/**
 * Build prefill-only rows from already approved evidence.
 *
 * The target form still creates unreviewed fields and an unreviewed article.
 * No source value is inferred, recalculated, promoted, or written automatically.
 */
export function reusableEditorialEvidence(
  page: PilotPage,
  sourceContracts: readonly EditorialContract[],
): ReusableEditorialEvidence | null {
  const rules = editorialEvidenceReuseRules.filter((rule) => rule.targetArticleId === page.id);
  const knownRules = editorialExplicitKnownRules.filter((rule) => rule.targetArticleId === page.id);
  const unknownRules = editorialExplicitUnknownRules.filter((rule) => rule.targetArticleId === page.id);
  if (!rules.length && !knownRules.length && !unknownRules.length) return null;

  const scopes = new Set(page.numericFields.map(pilotFieldScope));
  const rows: EditorialRowFormValue[] = [
    ...(scopes.has("vendor_plan") ? [emptyEditorialRow(page, "vendor_plan", "reused-vendor-1")] : []),
    ...(scopes.has("human_scenario") ? [emptyEditorialRow(page, "human_scenario", "scenario-1")] : []),
  ];
  const vendorRow = rows.find((row) => row.scopeKind === "vendor_plan");

  const appliedFields: string[] = [];
  for (const rule of rules) {
    if (!vendorRow) continue;
    const sourceContract = sourceContracts.find((candidate) => candidate.article_id === rule.sourceArticleId);
    if (!sourceContract || sourceContract.article_review_status !== "approved") continue;
    const source = sourceContract.numeric_fields.find((field) => (
      field.scope_kind === "vendor_plan"
      && field.vendor_id === rule.vendorId
      && field.plan_id === rule.planId
      && field.field === rule.sourceField
      && field.review_status === "approved"
    ));
    const target = page.numericFields.find((field) => field.key === rule.targetField);
    if (!source || !target || source.value_kind !== target.valueKind) continue;
    vendorRow.vendorId = rule.vendorId;
    vendorRow.planId = rule.planId;
    vendorRow.values[target.key] = reusableFieldFormValue(source);
    appliedFields.push(target.key);
  }

  for (const rule of knownRules) {
    if (!vendorRow) continue;
    const target = page.numericFields.find((field) => field.key === rule.targetField);
    if (!target || target.valueKind === "price") continue;
    vendorRow.vendorId = rule.vendorId;
    vendorRow.planId = rule.planId;
    vendorRow.values[target.key] = {
      ...emptyEditorialField(),
      billingToggleState: rule.billingToggleState,
      saleBannerState: rule.saleBannerState,
      valueStatus: "known",
      value: rule.value,
      unit: rule.unit,
      currencyStatus: "not_applicable",
      sourceUrl: rule.sourceUrl,
      observedOn: rule.observedOn,
      nextReviewOn: rule.nextReviewOn,
    };
    appliedFields.push(target.key);
  }

  const explicitUnknownFields: string[] = [];
  for (const rule of unknownRules) {
    const target = page.numericFields.find((field) => field.key === rule.targetField);
    if (!target) continue;
    const scopeKind = pilotFieldScope(target);
    const row = rows.find((candidate) => candidate.scopeKind === scopeKind);
    const field = row?.values[target.key];
    if (!row || !field) continue;
    if (scopeKind === "vendor_plan") {
      row.vendorId = rule.vendorId ?? "mangools";
      row.planId = rule.planId ?? "basic";
    } else if (rule.scenarioBasis) {
      row.scenarioBasis = rule.scenarioBasis;
    }
    Object.assign(field, {
      billingToggleState: rule.billingToggleState ?? "",
      saleBannerState: rule.saleBannerState ?? "",
      valueStatus: "unknown",
      value: "",
      unit: "",
      unknownReason: rule.unknownReason,
      currencyStatus: target.valueKind === "price" ? "unknown" : "not_applicable",
      currencyUnknownReason: target.valueKind === "price"
        ? rule.currencyUnknownReason ?? "対象金額自体が未確認のためISO通貨を確定していない"
        : "",
      billingPeriod: target.valueKind === "price" ? "unknown" : "",
      taxTreatment: target.valueKind === "price" ? "unknown" : "",
      observedPriceBasis: target.valueKind === "price"
        ? scopeKind === "human_scenario" ? "human_scenario" : "unknown"
        : "",
      sourceUrl: rule.sourceUrl ?? "",
      observedOn: rule.observedOn,
      nextReviewOn: rule.nextReviewOn,
    });
    explicitUnknownFields.push(target.key);
  }

  return appliedFields.length || explicitUnknownFields.length
    ? { appliedFields, explicitUnknownFields, rows }
    : null;
}

function safeServerEvidenceSlug(value: unknown): value is string {
  return typeof value === "string" && /^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$/.test(value);
}

function safeServerEvidenceUrl(value: unknown, expectedHost: string): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === expectedHost
      && url.port === ""
      && url.username === ""
      && url.password === ""
      && url.hash === ""
      && [...url.searchParams.keys()].every((key) => !/^(?:utm_|ref|aff|partner|clickid|subid)/i.test(key));
  } catch {
    return false;
  }
}

function latestServerEvidenceDay(values: readonly (string | null | undefined)[]): string | null {
  const days = values.filter((value): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value));
  return days.length ? [...days].sort().at(-1) ?? null : null;
}

function earliestServerEvidenceDay(values: readonly (string | null | undefined)[]): string | null {
  const days = values.filter((value): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value));
  return days.length ? [...days].sort()[0] ?? null : null;
}

/**
 * Convert a Pydantic-validated candidate artifact into display-only evidence.
 * The resulting calculator row is deliberately unknown and unranked: candidate
 * evidence is not article approval, canonical price, index, or CTA authority.
 */
export function reviewedServerCandidateEvidence(
  input: unknown,
  displayName: string,
  expectedSourceHost: string,
): ServerCandidateEvidence | null {
  if (!input || typeof input !== "object") return null;
  const candidate = input as Partial<ServerCandidateArtifact>;
  if (
    candidate.schema_version !== "1.0"
    || candidate.category_id !== "servers"
    || candidate.template_kind !== "pricing_tco"
    || candidate.state !== "candidate_only"
    || !Array.isArray(candidate.numeric_fields)
    || candidate.numeric_fields.length !== Object.keys(serverEvidenceLabels).length
  ) return null;

  const fields = candidate.numeric_fields as EditorialContract["numeric_fields"];
  const identities = new Set(fields.map((field) => `${field.vendor_id ?? ""}\u0000${field.plan_id ?? ""}`));
  const fieldNames = new Set(fields.map((field) => field.field));
  if (
    identities.size !== 1
    || fieldNames.size !== Object.keys(serverEvidenceLabels).length
    || Object.keys(serverEvidenceLabels).some((field) => !fieldNames.has(field))
    || fields.some((field) => (
      !safeServerEvidenceSlug(field.vendor_id)
      || !safeServerEvidenceSlug(field.plan_id)
      || !safeServerEvidenceUrl(field.source_url, expectedSourceHost)
      || field.entered_by !== "human"
      || field.rights_path !== "human_editorial"
      || field.review_status !== "approved"
    ))
  ) return null;

  const vendorId = fields[0].vendor_id!;
  const planId = fields[0].plan_id!;
  const assessment = assessServerPromotionCandidate(fields);
  const observedOn = latestServerEvidenceDay(fields.map((field) => field.observed_on));
  const nextReviewOn = earliestServerEvidenceDay(fields.map((field) => field.next_review_on));
  const unknownReason = assessment.tcoBlockers.length || assessment.suitabilityBlockers.length
    ? "期間限定表示、更新時請求額または用途条件に未確認項目があるため総額を算出しません"
    : "記事確認前のため計算対象外";

  return {
    vendorId,
    planId,
    displayName,
    knownCount: fields.filter((field) => field.value_status === "known").length,
    unknownCount: fields.filter((field) => field.value_status === "unknown").length,
    notApplicableCount: fields.filter((field) => field.value_status === "not_applicable").length,
    fields,
    tcoBlockers: assessment.tcoBlockers,
    suitabilityBlockers: assessment.suitabilityBlockers,
    calculatorContract: {
      articleReviewStatus: "unreviewed",
      plans: [{
        vendorId,
        planId,
        displayName,
        priceStatus: "unknown",
        reviewStatus: "unreviewed",
        eligibleUseCases: [],
        quote: null,
        serverTerms: null,
        unknownReason,
        observedOn,
        nextReviewOn,
      }],
    },
  };
}

export function serverEvidenceValue(
  field: EditorialContract["numeric_fields"][number],
): string {
  if (field.value_status === "unknown") return "未確認";
  if (field.value_status === "not_applicable") return `該当なし${field.unknown_reason ? `（${field.unknown_reason}）` : ""}`;
  const currency = field.currency_status === "known" && field.currency ? `${field.currency} ` : "";
  return `${currency}${field.value ?? ""}${field.unit ? ` ${field.unit}` : ""}`.trim();
}
