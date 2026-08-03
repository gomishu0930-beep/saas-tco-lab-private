import assert from "node:assert/strict";
import test from "node:test";

import {
  annualDiscountPercent,
  annualMonthlyEquivalent,
  emptyEditorialField,
  emptyEditorialRow,
  extractPriceTextCandidates,
  prefillExtractedCandidate,
  validateEditorialInput,
  valuesFromContract,
} from "../app/lib/editorial-input-contract.ts";
import { pilotFieldScope, pilotPages } from "../app/lib/pilot-pages.ts";

function oneFieldPage(field) {
  return {
    id: "P01",
    slug: "pricing-calculator",
    title: "料金計算",
    intent: "price_check",
    pageType: "pricing",
    question: "test",
    readerOutcome: "test",
    numericFields: [field],
  };
}

function validVendorRow(page) {
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  row.billingToggleState = "monthly_selected";
  row.saleBannerState = "none";
  for (const field of page.numericFields) {
    if (field.inputScope === "human_scenario") continue;
    row.values[field.key] = {
      ...row.values[field.key],
      value: "90",
      unit: "日",
      ...(field.valueKind === "price" ? {
        currencyStatus: "known",
        currency: "USD",
        billingPeriod: "monthly",
        taxTreatment: "unknown",
        observedPriceBasis: "displayed_price",
      } : {}),
      sourceUrl: "https://example.com/pricing?lang=ja",
      observedOn: "2026-07-29",
      nextReviewOn: "2026-10-27",
    };
  }
  return row;
}

test("a complete vendor-plan field emits the Python-owned 2.3 contract shape", () => {
  const page = pilotPages.find(candidate => candidate.id === "P05");
  const row = validVendorRow(page);
  const result = validateEditorialInput(page, [row]);
  assert.deepEqual(result.errors, {});
  assert.equal(result.contract?.schema_version, "2.3");
  assert.equal(result.contract?.numeric_fields[0].billing_toggle_state, "monthly_selected");
  assert.equal(result.contract?.numeric_fields[0].sale_banner_state, "none");
  assert.equal(result.contract?.numeric_fields[0].vendor_id, "mangools");
  assert.equal(result.contract?.numeric_fields[0].plan_id, "basic");
  assert.equal(result.contract?.numeric_fields[0].entered_by, "human");
  assert.equal(result.contract?.article_review_status, "unreviewed");
  assert.equal(valuesFromContract(page, result.contract)?.[0].vendorId, "mangools");
});

test("unsafe URL and review dates fail closed with Japanese correction guidance", () => {
  const page = pilotPages.find(candidate => candidate.id === "P05");
  const row = validVendorRow(page);
  row.values["enterprise.included_manager_seats"] = {
    ...row.values["enterprise.included_manager_seats"],
    value: "90日",
    unit: "",
    sourceUrl: "https://example.com/pricing?utm_source=test",
    nextReviewOn: "2027-07-29",
  };
  const result = validateEditorialInput(page, [row]);
  assert.equal(result.contract, null);
  const messages = JSON.stringify(result.errors);
  assert.match(messages, /数値だけ/);
  assert.match(messages, /単位/);
  assert.match(messages, /parameterを削除/);
  assert.match(messages, /180日以内/);
});

test("v2.3 price display classification blocks only promo and unknown", () => {
  const page = pilotPages.find(candidate => candidate.id === "P05");
  const row = validVendorRow(page);
  row.billingToggleState = "";
  row.saleBannerState = "";
  const missing = validateEditorialInput(page, [row]);
  assert.equal(missing.contract, null);
  assert.match(JSON.stringify(missing.errors), /billing toggle位置/);
  assert.match(JSON.stringify(missing.errors), /4区分/);

  row.billingToggleState = "monthly_selected";
  for (const state of ["none", "annual_discount_permanent"]) {
    row.saleBannerState = state;
    const eligible = validateEditorialInput(page, [row]);
    assert.deepEqual(eligible.errors, {});
    assert.equal(eligible.calculationBlockers.some(item => item.includes("screen: sale banner")), false);
    assert.equal(eligible.calculationBlockers.some(item => item.includes("time-limited promo")), false);
  }
  row.saleBannerState = "time_limited_promo";
  const promotional = validateEditorialInput(page, [row]);
  assert.deepEqual(promotional.errors, {});
  assert.ok(promotional.calculationBlockers.some(item => item.includes("time-limited promo")));
  row.saleBannerState = "unknown";
  const unknown = validateEditorialInput(page, [row]);
  assert.ok(unknown.calculationBlockers.some(item => item.includes("sale banner unknown")));
  row.saleBannerState = "present";
  assert.equal(validateEditorialInput(page, [row]).contract, null);
});

test("scenario and vendor fields are separated for the remaining launch articles", () => {
  const p07 = pilotPages.find(candidate => candidate.id === "P07");
  assert.equal(pilotFieldScope(p07.numericFields.find(field => field.key === "usage.included_quota")), "vendor_plan");
  assert.equal(pilotFieldScope(p07.numericFields.find(field => field.key === "usage.monthly_volume")), "human_scenario");

  const p09 = pilotPages.find(candidate => candidate.id === "P09");
  assert.equal(pilotFieldScope(p09.numericFields.find(field => field.key === "migration.work_hours")), "human_scenario");
  assert.equal(pilotFieldScope(p09.numericFields.find(field => field.key === "migration.support_price")), "vendor_plan");

  const p11 = pilotPages.find(candidate => candidate.id === "P11");
  assert.ok(p11.numericFields.every(field => pilotFieldScope(field) === "human_scenario"));

  const p12 = pilotPages.find(candidate => candidate.id === "P12");
  assert.ok(p12.numericFields.every(field => pilotFieldScope(field) === "human_scenario"));
});

test("ambiguous price currency is kept explicitly unknown and blocks calculation", () => {
  const field = { key: "pricing.base_price", label: "基本料金", valueKind: "price" };
  const page = oneFieldPage(field);
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  row.billingToggleState = "monthly_selected";
  row.saleBannerState = "none";
  row.values[field.key] = {
    ...row.values[field.key],
    value: "37.70",
    unit: "/ mo",
    currencyStatus: "unknown",
    currencyDisplay: "$",
    currencyUnknownReason: "公式ページにISO通貨codeの明記なし",
    billingPeriod: "monthly",
    taxTreatment: "unknown",
    observedPriceBasis: "displayed_price",
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-07-29",
    nextReviewOn: "2026-08-28",
  };
  const result = validateEditorialInput(page, [row]);
  assert.deepEqual(result.errors, {});
  assert.equal(result.contract?.numeric_fields[0].currency, null);
  assert.equal(result.contract?.numeric_fields[0].currency_display, "$");
  assert.equal(result.calculationBlockers.length, 2);
});

test("same field can be repeated across distinct vendor-plan rows", () => {
  const field = { key: "plan.price", label: "各plan料金", valueKind: "price" };
  const page = oneFieldPage(field);
  const basic = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  basic.vendorId = "mangools";
  basic.planId = "basic";
  basic.billingToggleState = "monthly_selected";
  basic.saleBannerState = "none";
  basic.values[field.key] = {
    ...basic.values[field.key], value: "37.70", unit: "/ mo", currencyStatus: "known", currency: "USD",
    billingPeriod: "monthly", taxTreatment: "unknown", observedPriceBasis: "displayed_price", sourceUrl: "https://example.com/pricing",
    observedOn: "2026-07-29", nextReviewOn: "2026-08-28",
  };
  const premium = structuredClone(basic);
  premium.rowId = "vendor-2";
  premium.planId = "premium";
  premium.values[field.key].value = "52.70";
  const result = validateEditorialInput(page, [basic, premium]);
  assert.deepEqual(result.errors, {});
  assert.deepEqual(result.contract?.numeric_fields.map(item => item.plan_id), ["basic", "premium"]);
});

test("Human scenario has no vendor identity or official source URL", () => {
  const field = { key: "scenario.seat_count", label: "seat数", valueKind: "seat_count", inputScope: "human_scenario" };
  const page = oneFieldPage(field);
  const row = emptyEditorialRow(page, "human_scenario", "scenario-1");
  row.values[field.key] = {
    ...row.values[field.key], value: "5", unit: "seats", observedOn: "2026-07-29", nextReviewOn: "2026-08-28",
  };
  const result = validateEditorialInput(page, [row]);
  assert.deepEqual(result.errors, {});
  assert.equal(result.contract?.numeric_fields[0].scope_kind, "human_scenario");
  assert.equal(result.contract?.numeric_fields[0].source_url, null);
  assert.equal(result.contract?.numeric_fields[0].acquisition_method, "human_scenario_input");
});

test("explicit unknown numeric value is not converted to zero", () => {
  const field = { key: "pricing.overage_price", label: "超過単価", valueKind: "price" };
  const page = oneFieldPage(field);
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  row.billingToggleState = "not_present";
  row.saleBannerState = "unknown";
  row.values[field.key] = {
    ...row.values[field.key], valueStatus: "unknown", unknownReason: "公式ページに記載なし",
    currencyStatus: "unknown", currencyDisplay: "", currencyUnknownReason: "超過価格と通貨表記が未掲載",
    billingPeriod: "unknown", taxTreatment: "unknown", observedPriceBasis: "unknown", sourceUrl: "https://example.com/pricing",
    observedOn: "2026-07-29", nextReviewOn: "2026-08-28",
  };
  const result = validateEditorialInput(page, [row]);
  assert.deepEqual(result.errors, {});
  assert.equal(result.contract?.numeric_fields[0].value, null);
  assert.equal(result.contract?.numeric_fields[0].currency_display, null);
  assert.ok(result.calculationBlockers.length >= 1);
});

test("annual vendor price accepts only checkout total and derives monthly equivalent", () => {
  const field = { key: "pricing.base_price", label: "基本料金", valueKind: "price" };
  const page = oneFieldPage(field);
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  row.billingToggleState = "annual_selected";
  row.saleBannerState = "none";
  row.values[field.key] = {
    ...row.values[field.key], value: "732", unit: "annual checkout total", currencyStatus: "known",
    currency: "USD", billingPeriod: "annual",
    taxTreatment: "unknown", observedPriceBasis: "checkout_billed_total", sourceUrl: "https://example.com/pricing",
    observedOn: "2026-07-31", nextReviewOn: "2026-08-30",
  };
  const accepted = validateEditorialInput(page, [row]);
  assert.deepEqual(accepted.errors, {});
  assert.equal(accepted.contract?.numeric_fields[0].value, "732");
  assert.equal(accepted.contract?.numeric_fields[0].derived_monthly_value, "61");
  assert.equal(accepted.contract?.numeric_fields[0].derivation_method, "annual_checkout_total_divided_by_12");
  assert.equal(accepted.contract?.numeric_fields[0].acquisition_method, "manual_checkout_review");

  row.values[field.key].value = "100";
  const nondivisible = validateEditorialInput(page, [row]);
  assert.deepEqual(nondivisible.errors, {});
  assert.equal(nondivisible.contract?.numeric_fields[0].value, "100");
  assert.equal(nondivisible.contract?.numeric_fields[0].derived_monthly_value, null);
  assert.equal(nondivisible.contract?.numeric_fields[0].derived_monthly_unit, null);
  assert.equal(nondivisible.contract?.numeric_fields[0].derivation_method, null);

  row.values[field.key].value = "61";
  row.values[field.key].unit = "/ mo";
  row.values[field.key].observedPriceBasis = "displayed_price";
  const rejected = validateEditorialInput(page, [row]);
  assert.equal(rejected.contract, null);
  assert.match(JSON.stringify(rejected.errors), /checkoutで確認した請求総額/);
});

test("annual monthly equivalent is shown only for exact currency-minor-unit division", () => {
  assert.equal(annualMonthlyEquivalent("100", "USD"), null);
  assert.equal(annualMonthlyEquivalent("120", "USD"), "10");
  assert.equal(annualMonthlyEquivalent("452.40", "USD"), "37.7");
  assert.equal(annualMonthlyEquivalent("732", "JPY"), "61");
  assert.equal(annualMonthlyEquivalent("733", "JPY"), null);
  assert.equal(annualMonthlyEquivalent("120.000", "KWD"), "10");
  assert.equal(annualMonthlyEquivalent("120", ""), null);
});

test("permanent annual discount uses the fixed monthly-reference derivation", () => {
  assert.equal(annualDiscountPercent("452.40", "61.00"), "38");
  assert.equal(annualDiscountPercent("632.40", "81.00"), "35");
  assert.equal(annualDiscountPercent("1172.40", "141.00"), "31");
  assert.equal(annualDiscountPercent("1200", "100"), null);

  const field = { key: "pricing.base_price", label: "基本料金", valueKind: "price" };
  const page = oneFieldPage(field);
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  row.billingToggleState = "annual_selected";
  row.saleBannerState = "annual_discount_permanent";
  row.values[field.key] = {
    ...row.values[field.key], value: "452.40", unit: "annual checkout total",
    currencyStatus: "known", currency: "USD", billingPeriod: "annual",
    taxTreatment: "not_applicable", observedPriceBasis: "checkout_billed_total",
    monthlyReferenceValue: "61.00", sourceUrl: "https://example.com/pricing",
    observedOn: "2026-08-02", nextReviewOn: "2026-08-31",
  };
  const accepted = validateEditorialInput(page, [row]);
  assert.deepEqual(accepted.errors, {});
  assert.equal(accepted.contract?.numeric_fields[0].monthly_reference_value, "61.00");
  assert.equal(accepted.contract?.numeric_fields[0].derived_annual_discount_percent, "38");

  row.values[field.key].monthlyReferenceValue = "";
  const rejected = validateEditorialInput(page, [row]);
  assert.equal(rejected.contract, null);
  assert.match(JSON.stringify(rejected.errors), /月払い価格/);
});

test("copied price text yields explicit local candidates without inventing missing fields", () => {
  const result = extractPriceTextCandidates(`Starter\n月額 ￥1,980 税込\nAnnual USD 120 tax excluded\nhttps://example.com/2026/pricing`);
  assert.equal(result.error, null);
  const monthly = result.candidates.find(candidate => candidate.value === "1980");
  assert.equal(monthly?.currency, "JPY");
  assert.equal(monthly?.billingPeriod, "monthly");
  assert.equal(monthly?.taxTreatment, "included");
  const annual = result.candidates.find(candidate => candidate.value === "120");
  assert.equal(annual?.currency, "USD");
  assert.equal(annual?.billingPeriod, "annual");
  assert.equal(annual?.taxTreatment, "excluded");
  assert.equal(result.candidates.some(candidate => candidate.sourceLine.includes("example.com")), false);
});

test("ambiguous currency candidate prefill keeps the dollar display without inferring USD", () => {
  const result = extractPriceTextCandidates("Basic $37.70 / mo");
  const candidate = result.candidates[0];
  assert.equal(candidate.currency, null);
  assert.equal(candidate.currencyDisplay, "$");
  assert.match(candidate.warnings.join(" "), /通貨を確定できません/);
  const current = { ...emptyEditorialField(), unit: "/ mo", sourceUrl: "https://example.com/pricing" };
  const prefilled = prefillExtractedCandidate(
    { key: "pricing.base_price", label: "基本料金", valueKind: "price" }, current, candidate,
  );
  assert.equal(prefilled.value, "37.70");
  assert.equal(prefilled.currency, "");
  assert.equal(prefilled.currencyStatus, "unknown");
  assert.equal(prefilled.currencyDisplay, "$");
  assert.equal(prefilled.sourceUrl, current.sourceUrl);
});

test("paste analysis is bounded and does not emit a candidate for empty text", () => {
  assert.match(extractPriceTextCandidates("").error, /貼り付け/);
  assert.match(extractPriceTextCandidates("1".repeat(100_001)).error, /100,000文字以内/);
});
