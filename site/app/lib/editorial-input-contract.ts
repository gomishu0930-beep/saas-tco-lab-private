import { pilotFieldScope, type PilotPage, type PilotNumericField } from "./pilot-pages.ts";

export type EditorialScopeKind = "vendor_plan" | "human_scenario";
export type EditorialValueStatus = "known" | "unknown" | "not_applicable";
export type EditorialCurrencyStatus = "known" | "unknown" | "not_applicable";
export type EditorialReviewStatus = "unreviewed" | "approved" | "rejected";
export type EditorialBillingToggleState = "annual_selected" | "monthly_selected" | "not_present" | "unknown";
export type EditorialSaleBannerState = "none" | "annual_discount_permanent" | "time_limited_promo" | "unknown";
export type EditorialObservedPriceBasis = "checkout_billed_total" | "displayed_price" | "human_scenario" | "not_applicable" | "unknown";

export type EditorialFieldFormValue = {
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
      billingToggleState: stored.billing_toggle_state ?? "",
      saleBannerState: stored.sale_banner_state ?? "",
      values: {},
    };
    if (
      row.billingToggleState !== (stored.billing_toggle_state ?? "")
      || row.saleBannerState !== (stored.sale_banner_state ?? "")
    ) return null;
    row.values[stored.field] = {
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
      if (!billingToggleStates.has(row.billingToggleState)) addError(errors, `${rowPrefix}.billingToggleState`, "確認時のbilling toggle位置を選択してください。見当たらなければ「toggleなし」、判別不能なら「不明」です。");
      if (!saleBannerStates.has(row.saleBannerState)) addError(errors, `${rowPrefix}.saleBannerState`, "価格表示を「なし・年払い恒常割引・期間限定promo・不明」の4区分から選択してください。");
      identity = `vendor_plan:${vendorId}:${planId}`;
      if (row.billingToggleState === "unknown") calculationBlockers.push(`${identity} / screen: billing toggle unknown`);
      if (row.saleBannerState === "unknown") calculationBlockers.push(`${identity} / screen: sale banner unknown`);
      if (row.saleBannerState === "time_limited_promo") calculationBlockers.push(`${identity} / screen: time-limited promo`);
    } else {
      if (!scenarioBasis || scenarioBasis.length > 300) addError(errors, `${rowPrefix}.scenarioBasis`, "Humanシナリオの根拠を300文字以内で入力してください。個人情報は入れません。");
      identity = "human_scenario";
    }
    if (identities.has(identity)) addError(errors, `${rowPrefix}.identity`, "同じvendor・plan行またはHumanシナリオ行が重複しています。");
    identities.add(identity);

    for (const field of fieldsForRow(page, row)) {
      const current = row.values[field.key] ?? emptyEditorialField();
      const prefix = `${rowPrefix}.${field.key}`;
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
        else if (valueStatus === "unknown" && observedPriceBasis !== "unknown") addError(errors, `${prefix}.observedPriceBasis`, "不明価格では一次観測区分も「不明」にしてください。");
        else if (row.scopeKind === "human_scenario" && observedPriceBasis !== "human_scenario") addError(errors, `${prefix}.observedPriceBasis`, "Humanシナリオ価格は公式価格の一次観測として扱いません。");
        else if (row.scopeKind === "vendor_plan" && valueStatus === "known" && billingPeriod === "annual") {
          if (observedPriceBasis !== "checkout_billed_total") addError(errors, `${prefix}.observedPriceBasis`, "年払いplanの値にはcheckoutで確認した請求総額を入力してください。料金表の月額換算表示は一次観測値にできません。");
          if (row.billingToggleState !== "annual_selected") addError(errors, `${prefix}.billingPeriod`, "年払いcheckout総額では画面状態を「年払い選択」にしてください。");
          derivedMonthlyValue = annualMonthlyEquivalent(contractValue ?? "", currency ?? "");
          if (derivedMonthlyValue !== null) {
            derivedMonthlyUnit = "/ mo";
            derivationMethod = "annual_checkout_total_divided_by_12";
          }
          if (row.saleBannerState === "annual_discount_permanent") {
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
        if (billingPeriod === "monthly" && row.billingToggleState === "annual_selected") addError(errors, `${prefix}.billingPeriod`, "月払い価格に「年払い選択」の画面状態は使えません。");
        if (billingPeriod === "annual" && row.billingToggleState === "monthly_selected") addError(errors, `${prefix}.billingPeriod`, "年払い価格に「月払い選択」の画面状態は使えません。");
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
        billing_toggle_state: row.scopeKind === "vendor_plan" ? row.billingToggleState as EditorialBillingToggleState : null,
        sale_banner_state: row.scopeKind === "vendor_plan" ? row.saleBannerState as EditorialSaleBannerState : null,
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
