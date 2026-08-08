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

test("zero-input server table matches Python-owned totals for 12/24/36 months", () => {
  const contract = { articleReviewStatus: "approved", plans: [zeroInputPlan()] };
  for (const [months, expected] of [[12, "12000"], [24, "24000"], [36, "36000"]]) {
    const table = calculateServerZeroInputTable(contract, months, "corporate_site");
    assert.equal(table.rows[0].totalMinor.toString(), expected);
    assert.equal(table.rows[0].rank, 1);
  }
});

test("zero-input server table keeps unknown and use-case-excluded rows out of ranking", () => {
  const contract = {
    articleReviewStatus: "approved",
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
  assert.deepEqual(table.rows.map((row) => row.status), ["ranked", "unconfirmed", "ineligible"]);
  assert.deepEqual(table.rows.map((row) => row.rank), [1, null, null]);
  assert.equal(table.rows[1].totalMinor, null);
});
