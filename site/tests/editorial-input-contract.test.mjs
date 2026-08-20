import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  assessServerPromotionCandidate,
  annualDiscountPercent,
  annualMonthlyEquivalent,
  buildP09OwnedDataPrefill,
  buildP11OwnedDataPrefill,
  confirmOwnedObservation,
  emptyEditorialField,
  emptyEditorialRow,
  extractPriceTextCandidates,
  observationMonthTotals,
  parseConfirmedOwnedObservations,
  prefillExtractedCandidate,
  reviewedServerCandidateEvidence,
  reviewedServerCandidateEvidenceBatch,
  reusableEditorialEvidence,
  secondsToDecimalHours,
  serverCategoryRowsFromCandidate,
  serverEvidenceValue,
  serverInitialPaymentProjection,
  summedObservationHours,
  validateEditorialInput,
  valuesFromContract,
} from "../app/lib/editorial-input-contract.ts";
import { pilotFieldScope, pilotPages, serverObservationPage } from "../app/lib/pilot-pages.ts";

const approvedSourceContracts = ["P01", "P02", "P03", "P06", "P07"].map((articleId) => JSON.parse(readFileSync(
  new URL(`../../artifacts/editorial-inputs/${articleId}-editorial-input.json`, import.meta.url),
  "utf8",
)));

const approvedServerCandidate = JSON.parse(readFileSync(
  new URL("../../artifacts/category-expansion-inputs/SVR01-servers-category-expansion-input-v3-2026-08-14.json", import.meta.url),
  "utf8",
));

const m3ServerCandidates = JSON.parse(readFileSync(
  new URL("../../artifacts/category-expansion-inputs/M3-servers-3vendor-candidate-2026-08-18.json", import.meta.url),
  "utf8",
));

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
  row.values["enterprise.agency_extra_seats_available"] = {
    ...row.values["enterprise.agency_extra_seats_available"],
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

test("one vendor-plan can preserve different screen states for monthly and annual fields", () => {
  const page = pilotPages.find(candidate => candidate.id === "P06");
  const row = emptyEditorialRow(page, "vendor_plan", "vendor-1");
  row.vendorId = "mangools";
  row.planId = "basic";
  const common = {
    sourceUrl: "https://mangools.com/plans-and-pricing",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
  };
  row.values["billing.monthly_contract_price"] = {
    ...row.values["billing.monthly_contract_price"], ...common,
    billingToggleState: "monthly_selected", saleBannerState: "annual_discount_permanent",
    value: "61", unit: "/ mo", currencyStatus: "known", currency: "USD",
    billingPeriod: "monthly", taxTreatment: "not_applicable", observedPriceBasis: "displayed_price",
  };
  row.values["billing.annual_contract_price"] = {
    ...row.values["billing.annual_contract_price"], ...common,
    billingToggleState: "annual_selected", saleBannerState: "annual_discount_permanent",
    value: "452.40", unit: "/ yr", currencyStatus: "known", currency: "USD",
    billingPeriod: "annual", taxTreatment: "not_applicable", observedPriceBasis: "checkout_billed_total",
    monthlyReferenceValue: "61",
  };
  row.values["billing.minimum_commitment_months"] = {
    ...row.values["billing.minimum_commitment_months"], ...common,
    billingToggleState: "annual_selected", saleBannerState: "annual_discount_permanent",
    value: "12", unit: "か月",
  };
  row.values["billing.termination_cost"] = {
    ...row.values["billing.termination_cost"], ...common,
    billingToggleState: "unknown", saleBannerState: "unknown",
    valueStatus: "unknown", unknownReason: "Human確認待ち", currencyStatus: "unknown",
    currencyUnknownReason: "金額未確認", billingPeriod: "unknown", taxTreatment: "unknown",
    observedPriceBasis: "unknown",
  };

  const result = validateEditorialInput(page, [row]);
  assert.deepEqual(result.errors, {});
  assert.equal(result.contract?.numeric_fields[0].billing_toggle_state, "monthly_selected");
  assert.equal(result.contract?.numeric_fields[1].billing_toggle_state, "annual_selected");
  const restored = valuesFromContract(page, result.contract);
  assert.equal(restored?.[0].values["billing.monthly_contract_price"].billingToggleState, "monthly_selected");
  assert.equal(restored?.[0].values["billing.annual_contract_price"].billingToggleState, "annual_selected");
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

test("P09 owned-data prefill preserves vendor unknowns and emits only unreviewed Human observations", () => {
  const page = pilotPages.find(candidate => candidate.id === "P09");
  const reusable = reusableEditorialEvidence(page, approvedSourceContracts);
  const prefill = buildP09OwnedDataPrefill({
    overlapMonths: "1",
    workHours: "6.25",
    hourlyCost: "3000",
    trainingHours: "1.5",
    currency: "JPY",
    observedOn: "2026-08-11",
    nextReviewOn: "2026-09-10",
  });
  assert.deepEqual(prefill.errors, {});
  assert.deepEqual(prefill.warnings, []);
  const rows = reusable.rows.map(row => row.scopeKind === "human_scenario" ? {
    ...row,
    scenarioBasis: prefill.scenarioBasis,
    values: { ...row.values, ...prefill.values },
  } : row);
  const validation = validateEditorialInput(page, rows);
  assert.deepEqual(validation.errors, {});
  assert.equal(validation.contract?.article_review_status, "unreviewed");
  assert.ok(validation.contract?.numeric_fields.every(field => field.review_status === "unreviewed"));
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "migration.work_hours")?.value, "6.25");
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "migration.work_hours")?.unit, "hours");
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "migration.hourly_cost")?.currency, "JPY");
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "migration.hourly_cost")?.source_url, null);
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "migration.support_price")?.value_status, "unknown");
});

test("P09 owned-data prefill rejects missing or negative observations without a partial candidate", () => {
  const result = buildP09OwnedDataPrefill({
    overlapMonths: "-1",
    workHours: "",
    hourlyCost: "3000円",
    trainingHours: "1",
    currency: "$",
    observedOn: "2026-08-11",
    nextReviewOn: "2027-08-11",
  });
  assert.ok(Object.keys(result.errors).length >= 4);
  assert.deepEqual(result.values, {});
  assert.equal(result.scenarioBasis, "");
});

test("P11 owned-data prefill compares complete calendar months with exact decimal subtraction", () => {
  const page = pilotPages.find(candidate => candidate.id === "P11");
  const prefill = buildP11OwnedDataPrefill({
    baselineMonth: "2026-06",
    comparisonMonth: "2026-07",
    baselineHours: "40.125",
    comparisonHours: "30.025",
    hourlyCost: "3000",
    implementationCost: "12000",
    monthlyTco: "5000",
    currency: "JPY",
    observedOn: "2026-08-11",
    nextReviewOn: "2026-09-10",
  });
  assert.deepEqual(prefill.errors, {});
  assert.equal(prefill.values["break_even.monthly_hours_saved"].value, "10.1");
  assert.equal(prefill.values["break_even.monthly_hours_saved"].unit, "hours / calendar month");
  assert.match(prefill.scenarioBasis, /月途中の値は外挿せず/);
  const scenario = emptyEditorialRow(page, "human_scenario", "scenario-1");
  scenario.scenarioBasis = prefill.scenarioBasis;
  scenario.values = { ...scenario.values, ...prefill.values };
  const validation = validateEditorialInput(page, [scenario]);
  assert.deepEqual(validation.errors, {});
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "break_even.implementation_cost")?.billing_period, "one_time");
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "break_even.monthly_tco")?.billing_period, "monthly");
  assert.ok(validation.contract?.numeric_fields.every(field => field.acquisition_method === "human_scenario_input"));
});

test("P11 owned-data prefill rejects non-sequential months and warns instead of hiding a negative result", () => {
  const invalid = buildP11OwnedDataPrefill({
    baselineMonth: "2026-07",
    comparisonMonth: "2026-07",
    baselineHours: "30",
    comparisonHours: "40",
    hourlyCost: "3000",
    implementationCost: "12000",
    monthlyTco: "5000",
    currency: "JPY",
    observedOn: "2026-08-11",
    nextReviewOn: "2026-09-10",
  });
  assert.match(JSON.stringify(invalid.errors), /比較月/);
  assert.deepEqual(invalid.values, {});

  const negative = buildP11OwnedDataPrefill({
    baselineMonth: "2026-06",
    comparisonMonth: "2026-07",
    baselineHours: "30",
    comparisonHours: "40",
    hourlyCost: "3000",
    implementationCost: "12000",
    monthlyTco: "5000",
    currency: "JPY",
    observedOn: "2026-08-11",
    nextReviewOn: "2026-09-10",
  });
  assert.deepEqual(negative.errors, {});
  assert.equal(negative.values["break_even.monthly_hours_saved"].value, "-10");
  assert.match(negative.warnings.join(" "), /増加/);
  const scenario = emptyEditorialRow(pilotPages.find(candidate => candidate.id === "P11"), "human_scenario", "scenario-1");
  scenario.scenarioBasis = negative.scenarioBasis;
  scenario.values = { ...scenario.values, ...negative.values };
  const validation = validateEditorialInput(pilotPages.find(candidate => candidate.id === "P11"), [scenario]);
  assert.deepEqual(validation.errors, {});
  assert.equal(validation.contract?.numeric_fields.find(field => field.field === "break_even.monthly_hours_saved")?.value, "-10");

  const incomplete = buildP11OwnedDataPrefill({
    baselineMonth: "2026-07",
    comparisonMonth: "2026-08",
    baselineHours: "40",
    comparisonHours: "30",
    hourlyCost: "3000",
    implementationCost: "12000",
    monthlyTco: "5000",
    currency: "JPY",
    observedOn: "2026-08-11",
    nextReviewOn: "2026-09-10",
  });
  assert.match(JSON.stringify(incomplete.errors), /全日が終了した暦月/);
  assert.deepEqual(incomplete.values, {});
});

test("owned observation ledger persists only explicit Human-confirmed whole-second sessions", () => {
  const confirmed = confirmOwnedObservation({
    articleId: "P09",
    kind: "p09_migration_work",
    calendarMonth: "2026-08",
    elapsedSeconds: "3600",
    confirmedOn: "2026-08-12",
    observationId: "P09:p09_migration_work:1",
  });
  assert.deepEqual(confirmed.errors, []);
  assert.equal(confirmed.observation?.authority, "human_confirmed");
  assert.equal(confirmed.observation?.elapsed_seconds, "3600");

  const wrongArticle = confirmOwnedObservation({
    articleId: "P11",
    kind: "p09_migration_work",
    calendarMonth: "2026-08",
    elapsedSeconds: "3600",
    confirmedOn: "2026-08-12",
    observationId: "P11:wrong-kind:1",
  });
  assert.equal(wrongArticle.observation, null);
  assert.match(wrongArticle.errors.join(" "), /記事と作業区分/);

  const reassignedMonth = confirmOwnedObservation({
    articleId: "P11",
    kind: "p11_baseline_work",
    calendarMonth: "2026-07",
    elapsedSeconds: "3600",
    confirmedOn: "2026-08-12",
    observationId: "P11:p11_baseline_work:1",
  });
  assert.equal(reassignedMonth.observation, null);
  assert.match(reassignedMonth.errors.join(" "), /別月へ付け替えません/);
});

test("owned observation ledger sums confirmed seconds deterministically without inferred time", () => {
  assert.equal(secondsToDecimalHours("3600"), "1");
  assert.equal(secondsToDecimalHours("90"), "0.025");
  assert.equal(secondsToDecimalHours("1"), "0.00027778");
  assert.equal(secondsToDecimalHours("0"), null);

  const rows = [
    ["baseline-a", "p11_baseline_work", "1800", "2026-08"],
    ["baseline-b", "p11_baseline_work", "2700", "2026-08"],
    ["comparison-a", "p11_comparison_work", "3600", "2026-09"],
  ].map(([observationId, kind, elapsedSeconds, calendarMonth]) => confirmOwnedObservation({
    articleId: "P11",
    kind,
    calendarMonth,
    elapsedSeconds,
    confirmedOn: `${calendarMonth}-12`,
    observationId,
  }).observation).filter(Boolean);
  assert.equal(rows.length, 3);
  assert.equal(summedObservationHours(rows, "P11", "p11_baseline_work", "2026-08"), "1.25");
  assert.equal(summedObservationHours(rows, "P11", "p11_comparison_work", "2026-09"), "1");
  assert.deepEqual(observationMonthTotals(rows, "P11"), [
    { calendarMonth: "2026-08", kind: "p11_baseline_work", hours: "1.25", sessions: 2 },
    { calendarMonth: "2026-09", kind: "p11_comparison_work", hours: "1", sessions: 1 },
  ]);
});

test("owned observation ledger rejects the entire local ledger on tampering or duplicate IDs", () => {
  const row = confirmOwnedObservation({
    articleId: "P09",
    kind: "p09_training",
    calendarMonth: "2026-08",
    elapsedSeconds: "120",
    confirmedOn: "2026-08-12",
    observationId: "training-1",
  }).observation;
  assert.ok(row);
  assert.deepEqual(parseConfirmedOwnedObservations(JSON.stringify([row])).observations, [row]);

  const duplicate = parseConfirmedOwnedObservations(JSON.stringify([row, row]));
  assert.deepEqual(duplicate.observations, []);
  assert.match(duplicate.error, /不正・重複/);

  const tampered = parseConfirmedOwnedObservations(JSON.stringify([{ ...row, authority: "ai_generated" }]));
  assert.deepEqual(tampered.observations, []);
  assert.match(tampered.error, /不正・重複/);
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

function serverAssessmentField(field, valueKind, overrides = {}) {
  return {
    schema_version: "2.3",
    scope_kind: "vendor_plan",
    vendor_id: "xserver-business",
    plan_id: "shared-standard",
    field,
    value_kind: valueKind,
    value_status: "known",
    value: "1",
    unit: valueKind === "price" ? "JPY" : "GB",
    unknown_reason: null,
    currency_status: valueKind === "price" ? "known" : "not_applicable",
    currency: valueKind === "price" ? "JPY" : null,
    currency_display: null,
    currency_unknown_reason: null,
    billing_period: valueKind === "price" ? "monthly" : null,
    tax_treatment: valueKind === "price" ? "included" : null,
    billing_toggle_state: "not_present",
    sale_banner_state: "none",
    observed_price_basis: valueKind === "price" ? "displayed_price" : null,
    derived_monthly_value: null,
    derived_monthly_unit: null,
    derivation_method: null,
    monthly_reference_value: null,
    monthly_reference_unit: null,
    derived_annual_discount_percent: null,
    discount_derivation_method: null,
    source_url: "https://example.com/pricing",
    scenario_basis: null,
    observed_on: "2026-08-08",
    next_review_on: "2026-09-08",
    entered_by: "human",
    acquisition_method: "manual_public_page",
    rights_path: "human_editorial",
    review_status: "approved",
    ...overrides,
  };
}

test("servers promotion assessment separates TCO, suitability and Human review blockers", () => {
  const fields = [
    serverAssessmentField("pricing.base_price", "price", { sale_banner_state: "time_limited_promo", review_status: "unreviewed" }),
    serverAssessmentField("pricing.renewal_fee", "price", {
      value_status: "unknown", value: null, currency_status: "unknown", currency: null,
      billing_period: "unknown", tax_treatment: "unknown", observed_price_basis: "unknown",
      review_status: "unreviewed",
    }),
    serverAssessmentField("servers.storage_gb", "quota"),
    serverAssessmentField("servers.data_transfer_gb", "quota", {
      value_status: "unknown", value: null, unknown_reason: "公式確認待ち", review_status: "unreviewed",
    }),
  ];
  const assessment = assessServerPromotionCandidate(fields);
  assert.equal(assessment.tcoReady, false);
  assert.equal(assessment.suitabilityReady, false);
  assert.equal(assessment.contractPromotionReady, false);
  assert.ok(assessment.tcoBlockers.some((item) => item.includes("期間限定価格")));
  assert.ok(assessment.tcoBlockers.some((item) => item.includes("pricing.renewal_fee: 値が未確認")));
  assert.deepEqual(assessment.suitabilityBlockers, ["servers.data_transfer_gb: 値が未確認"]);
  assert.equal(assessment.reviewBlockers.length, 3);
});

test("servers promotion assessment accepts explicit approved values and not-applicable fields", () => {
  const fields = [
    serverAssessmentField("pricing.initial_fee", "price"),
    serverAssessmentField("pricing.base_price", "price"),
    serverAssessmentField("pricing.renewal_fee", "price", {
      value_status: "not_applicable", value: null, unit: null, currency_status: "not_applicable",
      currency: null, billing_period: "not_applicable", tax_treatment: "not_applicable",
      observed_price_basis: "not_applicable", unknown_reason: "更新料なしを公式画面で確認",
    }),
    serverAssessmentField("servers.campaign_price", "price", {
      value_status: "not_applicable", value: null, unit: null, currency_status: "not_applicable",
      currency: null, billing_period: "not_applicable", tax_treatment: "not_applicable",
      observed_price_basis: "not_applicable", unknown_reason: "キャンペーンなしを公式画面で確認",
    }),
    serverAssessmentField("servers.campaign_period_months", "duration", {
      value_status: "not_applicable", value: null, unit: null, unknown_reason: "キャンペーンなしを公式画面で確認",
    }),
    serverAssessmentField("servers.domain_benefit_amount", "price", {
      value_status: "not_applicable", value: null, unit: null, currency_status: "not_applicable",
      currency: null, billing_period: "not_applicable", tax_treatment: "not_applicable",
      observed_price_basis: "not_applicable", unknown_reason: "金額換算しない特典",
    }),
    serverAssessmentField("servers.domain_benefit_period_months", "duration", {
      value_status: "not_applicable", value: null, unit: null, unknown_reason: "金額換算しない特典",
    }),
    serverAssessmentField("servers.compute_hours", "usage", {
      value_status: "not_applicable", value: null, unit: null, unknown_reason: "時間上限なしを公式画面で確認",
    }),
    serverAssessmentField("servers.storage_gb", "quota"),
    serverAssessmentField("servers.data_transfer_gb", "quota"),
    serverAssessmentField("servers.backup_price", "price"),
  ];
  const assessment = assessServerPromotionCandidate(fields);
  assert.equal(assessment.tcoReady, true);
  assert.equal(assessment.suitabilityReady, true);
  assert.equal(assessment.contractPromotionReady, true);
  assert.deepEqual(assessment.reviewBlockers, []);
});

test("reviewed servers evidence carries only a bounded first-year calculator input", () => {
  const evidence = reviewedServerCandidateEvidence(
    approvedServerCandidate,
    "XServerビジネス 共有スタンダード（12か月）",
    "business.xserver.ne.jp",
  );
  assert.ok(evidence);
  assert.deepEqual(
    [evidence.knownCount, evidence.unknownCount, evidence.notApplicableCount],
    [4, 6, 1],
  );
  assert.equal(evidence.calculatorContract.articleReviewStatus, "unreviewed");
  assert.equal(evidence.calculatorContract.plans[0].priceStatus, "known");
  assert.equal(evidence.calculatorContract.plans[0].reviewStatus, "approved");
  assert.equal(evidence.calculatorContract.plans[0].quote.base.amount, "50160");
  assert.equal(evidence.calculatorContract.plans[0].serverTerms.initialFee, "16500");
  assert.equal(evidence.calculatorContract.plans[0].confirmedThroughMonths, 12);
  assert.match(evidence.calculatorContract.plans[0].horizonUnknownReason, /24か月・36か月/);
  assert.ok(evidence.tcoBlockers.length > 0);
  assert.ok(evidence.suitabilityBlockers.length > 0);
  assert.deepEqual(evidence.initialPayment, {
    amount: "66660",
    annualCheckoutTotal: "50160",
    initialFee: "16500",
    currency: "JPY",
    taxTreatment: "included",
    observedOn: "2026-08-14",
    nextReviewOn: "2026-09-13",
  });

  const campaign = evidence.fields.find((field) => field.field === "servers.campaign_price");
  assert.equal(campaign.value_status, "unknown");
  assert.equal(campaign.sale_banner_state, "time_limited_promo");
  assert.equal(evidence.calculatorContract.articleReviewStatus, "unreviewed");

  const basePrice = evidence.fields.find((field) => field.field === "pricing.base_price");
  const renewal = evidence.fields.find((field) => field.field === "pricing.renewal_fee");
  const transfer = evidence.fields.find((field) => field.field === "servers.data_transfer_gb");
  assert.equal(serverEvidenceValue(basePrice), "JPY 50160 / yr");
  assert.equal(serverEvidenceValue(renewal), "未確認");
  assert.match(serverEvidenceValue(transfer), /^該当なし/);

  const mixedCurrency = structuredClone(approvedServerCandidate.numeric_fields);
  mixedCurrency.find((field) => field.field === "pricing.initial_fee").currency = "USD";
  assert.equal(serverInitialPaymentProjection(mixedCurrency), null);

  const wrongBasis = structuredClone(approvedServerCandidate.numeric_fields);
  wrongBasis.find((field) => field.field === "pricing.base_price").observed_price_basis = "displayed_price";
  assert.equal(serverInitialPaymentProjection(wrongBasis), null);

  const unreviewed = structuredClone(approvedServerCandidate);
  unreviewed.numeric_fields[0].review_status = "unreviewed";
  assert.equal(reviewedServerCandidateEvidence(unreviewed, "XServerビジネス", "business.xserver.ne.jp"), null);

  for (const sourceUrl of [
    "https://example.com/price/",
    "https://business.xserver.ne.jp/price/?utm_source=test",
  ]) {
    const unsafe = structuredClone(approvedServerCandidate);
    unsafe.numeric_fields[0].source_url = sourceUrl;
    assert.equal(reviewedServerCandidateEvidence(unsafe, "XServerビジネス", "business.xserver.ne.jp"), null);
  }
});

test("servers candidate batch restores and validates every complete vendor-plan independently", () => {
  const identities = [
    { vendorId: "alpha-host", planId: "business", displayName: "Alpha Business", host: "pricing.alpha.test" },
    { vendorId: "beta-host", planId: "standard", displayName: "Beta Standard", host: "pricing.beta.test" },
  ];
  const numericFields = identities.flatMap(({ vendorId, planId, host }) => (
    approvedServerCandidate.numeric_fields.map((field) => ({
      ...structuredClone(field),
      vendor_id: vendorId,
      plan_id: planId,
      source_url: `https://${host}/pricing`,
    }))
  ));
  const batch = {
    schema_version: "1.0",
    category_id: "servers",
    template_kind: "pricing_tco",
    state: "candidate_only",
    numeric_fields: numericFields,
  };

  const rows = serverCategoryRowsFromCandidate(serverObservationPage, batch);
  assert.ok(rows);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => [row.vendorId, row.planId]), [
    ["alpha-host", "business"],
    ["beta-host", "standard"],
  ]);

  const evidence = reviewedServerCandidateEvidenceBatch(
    batch,
    identities.map(({ host, ...source }) => ({ ...source, expectedSourceHost: host })),
  );
  assert.ok(evidence);
  assert.equal(evidence.length, 2);
  assert.ok(evidence.every((item) => item.calculatorContract.articleReviewStatus === "unreviewed"));
  assert.ok(evidence.every((item) => item.calculatorContract.plans[0].reviewStatus === "approved"));
  assert.ok(evidence.every((item) => item.calculatorContract.plans[0].confirmedThroughMonths === 12));

  const incomplete = structuredClone(batch);
  incomplete.numeric_fields.pop();
  assert.equal(serverCategoryRowsFromCandidate(serverObservationPage, incomplete), null);
  assert.equal(reviewedServerCandidateEvidenceBatch(incomplete, identities.map(({ host, ...source }) => ({
    ...source,
    expectedSourceHost: host,
  }))), null);
  assert.equal(reviewedServerCandidateEvidenceBatch(batch, [{
    vendorId: "alpha-host",
    planId: "business",
    displayName: "Alpha Business",
    expectedSourceHost: "pricing.alpha.test",
  }]), null);
});

test("M3 servers evidence promotes only Human-confirmed first-year checkout totals", () => {
  const evidence = reviewedServerCandidateEvidenceBatch(m3ServerCandidates, [
    {
      vendorId: "conoha-wing",
      planId: "wing-pack-standard-12m",
      displayName: "ConoHa WING Standard（WINGパック12か月）",
      expectedSourceHost: "www.conoha.jp",
      eligibleUseCases: ["small_site"],
    },
    {
      vendorId: "sakura-rental-server",
      planId: "business-12m",
      displayName: "さくらのレンタルサーバ Business（12か月）",
      expectedSourceHost: "rs.sakura.ad.jp",
      eligibleUseCases: ["small_site", "corporate_site"],
    },
    {
      vendorId: "kagoya",
      planId: "light-1c4g-12m",
      displayName: "KAGOYA Light（1コア/4GB・12か月）",
      expectedSourceHost: "www.kagoya.jp",
      eligibleUseCases: ["small_site", "corporate_site"],
    },
  ]);

  assert.ok(evidence);
  assert.equal(evidence.length, 3);
  assert.deepEqual(evidence.map((item) => [item.knownCount, item.unknownCount, item.notApplicableCount]), [
    [5, 5, 1],
    [3, 5, 3],
    [5, 3, 3],
  ]);
  assert.ok(evidence.every((item) => item.calculatorContract.articleReviewStatus === "unreviewed"));
  assert.deepEqual(evidence.map((item) => item.calculatorContract.plans[0].priceStatus), [
    "unknown", "known", "known",
  ]);
  assert.equal(evidence[0].calculatorContract.plans[0].quote, null);
  assert.deepEqual(evidence.slice(1).map((item) => item.calculatorContract.plans[0].confirmedThroughMonths), [12, 12]);
  assert.deepEqual(evidence.map((item) => item.calculatorContract.plans[0].eligibleUseCases), [
    ["small_site"],
    ["small_site", "corporate_site"],
    ["small_site", "corporate_site"],
  ]);
  assert.ok(evidence.every((item) => item.tcoBlockers.length > 0));
  assert.equal(evidence[0].initialPayment, null, "ConoHaの期間限定価格を通常TCOへ昇格しない");
  assert.deepEqual(evidence[1].initialPayment, {
    amount: "29040",
    annualCheckoutTotal: "29040",
    initialFee: "0",
    currency: "JPY",
    taxTreatment: "included",
    observedOn: "2026-08-18",
    nextReviewOn: "2026-09-17",
  });
  assert.deepEqual(evidence[2].initialPayment, {
    amount: "17820",
    annualCheckoutTotal: "17820",
    initialFee: "0",
    currency: "JPY",
    taxTreatment: "included",
    observedOn: "2026-08-18",
    nextReviewOn: "2026-09-17",
  });
});

test("remaining articles reuse only approved same-type evidence as unreviewed form candidates", () => {
  const expected = new Map([
    ["P04", { approved: ["team.minimum_seats", "team.monthly_price"], unknown: ["team.monthly_operation_hours", "team.onboarding_hours"] }],
    ["P05", { approved: ["enterprise.agency_annual_checkout_total", "enterprise.agency_extra_seats_available", "enterprise.site_analysis_requests_per_24h"], unknown: ["enterprise.migration_support_price"] }],
    ["P08", { approved: ["addon.base_price", "addon.price", "addon.required_seats"], unknown: ["addon.billing_unit_size"] }],
    ["P09", { approved: [], unknown: ["migration.overlap_months", "migration.work_hours", "migration.hourly_cost", "migration.training_hours", "migration.support_price"] }],
    ["P10", { approved: ["localization.displayed_price", "localization.tax_rate"], unknown: ["localization.exchange_rate"] }],
    ["P11", { approved: [], unknown: ["break_even.monthly_hours_saved", "break_even.hourly_cost", "break_even.implementation_cost", "break_even.monthly_tco"] }],
    ["P12", { approved: [], unknown: ["evidence.review_interval_days"] }],
  ]);

  for (const [articleId, expectedFields] of expected) {
    const page = pilotPages.find((candidate) => candidate.id === articleId);
    assert.ok(page);
    const reusable = reusableEditorialEvidence(page, approvedSourceContracts);
    assert.ok(reusable);
    assert.deepEqual(reusable.appliedFields, expectedFields.approved);
    assert.deepEqual(reusable.explicitUnknownFields, expectedFields.unknown);
    const vendor = reusable.rows.find((row) => row.scopeKind === "vendor_plan");
    if (page.numericFields.some((field) => (field.inputScope ?? "vendor_plan") === "vendor_plan")) {
      assert.equal(vendor?.vendorId, "mangools");
      assert.equal(vendor?.planId, articleId === "P05" ? "agency" : "basic");
    }
    if (articleId === "P04") {
      const scenario = reusable.rows.find((row) => row.scopeKind === "human_scenario");
      assert.ok(scenario);
      assert.ok(scenario.values["team.monthly_operation_hours"]);
      assert.ok(scenario.values["team.onboarding_hours"]);
      assert.equal(vendor?.values["team.monthly_operation_hours"], undefined);
      assert.equal(vendor?.values["team.onboarding_hours"], undefined);
    }
    for (const field of expectedFields.approved) {
      assert.ok(vendor?.values[field]?.sourceUrl.startsWith("https://"));
      assert.ok(vendor?.values[field]?.observedOn);
      assert.ok(vendor?.values[field]?.nextReviewOn);
    }
    const validation = validateEditorialInput(page, reusable.rows);
    assert.ok(validation.contract);
    assert.equal(validation.contract.article_review_status, "unreviewed");
    assert.ok(validation.contract.numeric_fields.every((field) => field.review_status === "unreviewed"));
    for (const field of expectedFields.unknown) {
      const candidate = validation.contract.numeric_fields.find((item) => item.field === field);
      assert.equal(candidate?.value_status, "unknown");
      assert.equal(candidate?.value, null);
      assert.ok(candidate?.unknown_reason);
      if (candidate?.value_kind === "price") {
        assert.equal(candidate.currency_status, "unknown");
        assert.equal(candidate.billing_period, "unknown");
        assert.equal(candidate.tax_treatment, "unknown");
        assert.equal(
          candidate.observed_price_basis,
          candidate.scope_kind === "human_scenario" ? "human_scenario" : "unknown",
        );
      }
    }
  }
});

test("articles without exact semantic reuse rules receive no suggested evidence", () => {
  for (const articleId of ["P01", "P02", "P03", "P06", "P07"]) {
    const page = pilotPages.find((candidate) => candidate.id === articleId);
    assert.ok(page);
    assert.equal(reusableEditorialEvidence(page, approvedSourceContracts), null);
  }
});
