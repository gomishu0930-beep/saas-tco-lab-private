import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { calculateServerTco, calculateServerZeroInputTable, calculateTco } from "../app/lib/tco.ts";

const cases = JSON.parse(
  await readFile(new URL("../../tests/fixtures/tco_golden.json", import.meta.url), "utf8"),
);

test("TypeScript calculator matches every Python-owned golden fixture", () => {
  for (const fixture of cases) {
    const result = fixture.serverTerms
      ? calculateServerTco(fixture.quote, fixture.scenario, fixture.serverTerms)
      : calculateTco(fixture.quote, fixture.scenario);
    assert.equal(result.listedMinor.toString(), fixture.expected.listedMinor, fixture.name);
    assert.equal(result.addedTaxMinor.toString(), fixture.expected.addedTaxMinor, fixture.name);
    assert.equal(result.totalMinor.toString(), fixture.expected.totalMinor, fixture.name);
  }
});

test("unknown tax never produces a modeled total", () => {
  const fixture = structuredClone(cases[0]);
  fixture.quote.tax.treatment = "unknown";
  assert.throws(() => calculateTco(fixture.quote, fixture.scenario), /unknown/);
});

test("server calculator keeps partial commercial terms fail-closed", () => {
  const fixture = structuredClone(cases[0]);
  assert.throws(
    () => calculateServerTco(fixture.quote, fixture.scenario, {
      initialFee: null,
      renewalFee: "500",
      renewalDueMonth: null,
      campaignPrice: null,
      campaignPeriodMonths: null,
      domainPrice: null,
      domainBillingPeriod: null,
      domainIncludedMonths: null,
    }),
    /renewal fee and due month/,
  );
});

function zeroInputPlan(overrides = {}) {
  return {
    vendorId: "alpha",
    planId: "basic",
    displayName: "Alpha Basic",
    priceStatus: "known",
    reviewStatus: "approved",
    eligibleUseCases: ["small_site", "corporate_site"],
    quote: structuredClone(cases[0].quote),
    serverTerms: {
      initialFee: null,
      renewalFee: null,
      renewalDueMonth: null,
      campaignPrice: null,
      campaignPeriodMonths: null,
      domainPrice: null,
      domainBillingPeriod: null,
      domainIncludedMonths: null,
    },
    unknownReason: null,
    observedOn: "2026-08-06",
    nextReviewOn: "2026-11-04",
    ...overrides,
  };
}

test("zero-input server table matches Python-owned totals and holds ranking below three vendors", () => {
  const contract = {
    articleReviewStatus: "approved",
    useCaseRequirements: {
      small_site: ["Human確認済み小規模要件"],
      corporate_site: ["Human確認済み法人要件"],
      ecommerce: ["Human確認済みEC要件"],
    },
    plans: [zeroInputPlan()],
  };
  for (const [months, expected] of [[12, "12000"], [24, "24000"], [36, "36000"]]) {
    const table = calculateServerZeroInputTable(contract, months, "corporate_site");
    assert.equal(table.rows[0].totalMinor.toString(), expected);
    assert.equal(table.comparisonMode, "confirmed_list");
    assert.equal(table.confirmedVendorCount, 1);
    assert.equal(table.rows[0].rank, null);
    assert.equal(table.rows[0].differenceFromLowestMinor, null);
  }
});

test("zero-input server table holds totals beyond the Human-confirmed horizon", () => {
  const plan = zeroInputPlan({
    quote: {
      ...structuredClone(cases[0].quote),
      base: { ...structuredClone(cases[0].quote.base), amount: "12000", billingPeriod: "annual" },
    },
    serverTerms: {
      initialFee: "1000",
      renewalFee: null,
      renewalDueMonth: null,
      campaignPrice: null,
      campaignPeriodMonths: null,
      domainPrice: null,
      domainBillingPeriod: null,
      domainIncludedMonths: null,
    },
    confirmedThroughMonths: 12,
    horizonUnknownReason: "更新時請求総額が未確認のため24か月・36か月は計算しません",
  });
  const contract = {
    articleReviewStatus: "approved",
    useCaseRequirements: {
      small_site: ["Human確認済み小規模要件"],
      corporate_site: ["Human確認済み法人要件"],
      ecommerce: ["Human確認済みEC要件"],
    },
    plans: [plan],
  };

  assert.equal(calculateServerZeroInputTable(contract, 12, "small_site").rows[0].totalMinor.toString(), "13000");
  const held = calculateServerZeroInputTable(contract, 24, "small_site").rows[0];
  assert.equal(held.totalMinor, null);
  assert.equal(held.status, "unconfirmed");
  assert.match(held.reason, /更新時請求総額が未確認/);
});

test("zero-input server table derives rank and first-place difference from three approved vendors", () => {
  const contract = {
    articleReviewStatus: "approved",
    useCaseRequirements: {
      small_site: ["Human確認済み小規模要件"],
      corporate_site: ["Human確認済み法人要件"],
      ecommerce: ["Human確認済みEC要件"],
    },
    plans: [
      zeroInputPlan(),
      zeroInputPlan({ vendorId: "beta", planId: "business", displayName: "Beta", quote: { ...structuredClone(cases[0].quote), base: { ...structuredClone(cases[0].quote.base), amount: "1500" } } }),
      zeroInputPlan({ vendorId: "gamma", planId: "business", displayName: "Gamma", quote: { ...structuredClone(cases[0].quote), base: { ...structuredClone(cases[0].quote.base), amount: "1250" } } }),
    ],
  };
  const table = calculateServerZeroInputTable(contract, 12, "corporate_site");
  assert.equal(table.comparisonMode, "ranked_comparison");
  assert.equal(table.confirmedVendorCount, 3);
  assert.deepEqual(table.rows.map((row) => row.rank), [1, 3, 2]);
  assert.deepEqual(table.rows.map((row) => row.differenceFromLowestMinor?.toString()), ["0", "6000", "3000"]);
});

test("zero-input server table keeps unknown and use-case-excluded rows out of ranking", () => {
  const contract = {
    articleReviewStatus: "approved",
    useCaseRequirements: {
      small_site: ["Human確認済み小規模要件"],
      corporate_site: ["Human確認済み法人要件"],
      ecommerce: ["Human確認済みEC要件"],
    },
    plans: [
      zeroInputPlan(),
      zeroInputPlan({
        vendorId: "beta",
        planId: "unknown",
        displayName: "Beta 未確認",
        priceStatus: "unknown",
        reviewStatus: "unreviewed",
        eligibleUseCases: [],
        quote: null,
        serverTerms: null,
        unknownReason: "更新料が未確認",
        observedOn: null,
        nextReviewOn: null,
      }),
      zeroInputPlan({ vendorId: "gamma", planId: "ec", displayName: "Gamma EC", eligibleUseCases: ["ecommerce"] }),
    ],
  };
  const table = calculateServerZeroInputTable(contract, 12, "small_site");
  assert.deepEqual(table.rows.map((row) => row.status), ["confirmed_unranked", "unconfirmed", "ineligible"]);
  assert.deepEqual(table.rows.map((row) => row.rank), [null, null, null]);
  assert.equal(table.rows[1].totalMinor, null);
});

test("zero-input server table excludes every plan until use-case requirements are Human-confirmed", () => {
  const contract = {
    articleReviewStatus: "approved",
    useCaseRequirements: { small_site: [], corporate_site: [], ecommerce: [] },
    plans: [
      zeroInputPlan(),
      zeroInputPlan({ vendorId: "beta", planId: "business", displayName: "Beta" }),
      zeroInputPlan({ vendorId: "gamma", planId: "business", displayName: "Gamma" }),
    ],
  };
  const table = calculateServerZeroInputTable(contract, 12, "small_site");
  assert.equal(table.comparisonMode, "confirmed_list");
  assert.equal(table.confirmedVendorCount, 0);
  assert.deepEqual(table.rows.map((row) => row.status), ["ineligible", "ineligible", "ineligible"]);
  assert.ok(table.rows.every((row) => row.reason === "用途の必要条件がHuman確認前のため順位対象外"));
});
