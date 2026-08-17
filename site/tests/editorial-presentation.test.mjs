import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { nextToReadPages } from "../app/lib/article-navigation.ts";
import { calculatorPrefill } from "../app/lib/calculator-prefill.ts";
import { editorialPresentation } from "../app/lib/editorial-presentation.ts";
import { pilotPages } from "../app/lib/pilot-pages.ts";

const p09Contract = JSON.parse(readFileSync(
  new URL("../../artifacts/editorial-inputs/P09-editorial-input.json", import.meta.url),
  "utf8",
));

function approvedContract() {
  return {
    schema_version: "2.3",
    article_id: "P01",
    slug: "pricing-calculator",
    title: "料金計算",
    disclosure_version: "pr-affiliate-v1",
    article_review_status: "approved",
    numeric_fields: [
      {
        schema_version: "2.3",
        scope_kind: "vendor_plan",
        vendor_id: "mangools",
        plan_id: "basic",
        field: "pricing.base_price",
        value_kind: "price",
        value_status: "known",
        value: "452.40",
        unit: "/ yr",
        unknown_reason: null,
        currency_status: "known",
        currency: "USD",
        currency_display: "$",
        currency_unknown_reason: null,
        billing_period: "annual",
        tax_treatment: "not_applicable",
        billing_toggle_state: "annual_selected",
        sale_banner_state: "annual_discount_permanent",
        observed_price_basis: "checkout_billed_total",
        derived_monthly_value: "37.70",
        derived_monthly_unit: "/ mo",
        derivation_method: "annual_checkout_total_divided_by_12",
        monthly_reference_value: "61.00",
        monthly_reference_unit: "/ mo",
        derived_annual_discount_percent: "38",
        discount_derivation_method: "one_minus_annual_total_divided_by_monthly_price_times_12",
        source_url: "https://mangools.com/subscriptions/checkout",
        scenario_basis: null,
        observed_on: "2026-08-02",
        next_review_on: "2026-08-31",
        entered_by: "human",
        acquisition_method: "manual_checkout_review",
        rights_path: "human_editorial",
        review_status: "approved",
      },
      {
        schema_version: "2.3",
        scope_kind: "human_scenario",
        vendor_id: null,
        plan_id: null,
        field: "scenario.seat_count",
        value_kind: "seat_count",
        value_status: "known",
        value: "1",
        unit: "ユーザー",
        unknown_reason: null,
        currency_status: "not_applicable",
        currency: null,
        currency_display: null,
        currency_unknown_reason: null,
        billing_period: null,
        tax_treatment: null,
        billing_toggle_state: null,
        sale_banner_state: null,
        observed_price_basis: null,
        derived_monthly_value: null,
        derived_monthly_unit: null,
        derivation_method: null,
        monthly_reference_value: null,
        monthly_reference_unit: null,
        derived_annual_discount_percent: null,
        discount_derivation_method: null,
        source_url: null,
        scenario_basis: "1名で利用",
        observed_on: "2026-08-02",
        next_review_on: "2026-08-31",
        entered_by: "human",
        acquisition_method: "human_scenario_input",
        rights_path: "human_editorial",
        review_status: "approved",
      },
    ],
  };
}

test("reader presentation derives title, description, and first sentence from approved evidence", () => {
  const presentation = editorialPresentation(pilotPages[0], approvedContract());
  assert.equal(presentation.title, "Mangools料金(2026年8月確認): USD 452.40と12か月TCO");
  assert.match(presentation.description, /Mangools BasicのUSD 452\.40を公式画面で確認/);
  assert.match(presentation.lead, /^Mangools Basicの確認済み実額はUSD 452\.40（年次請求）で、/);
  assert.doesNotMatch(`${presentation.description}\n${presentation.lead}`, /contract|vendor|billing toggle|Human scenario/i);
});

test("articles without an approved price use an honest no-amount fallback", () => {
  const presentation = editorialPresentation(pilotPages[3], null);
  assert.equal(presentation.title, "SaaS料金: 確認済み実額なし・小規模チーム費用は確認中");
  assert.match(presentation.lead, /^確認済みの実額はまだなく、/);
  assert.doesNotMatch(presentation.title, /[¥$€£]|\b(?:JPY|USD|EUR)\s+\d/);
});

test("P09 derives the Human migration labor cost while keeping official support unknown", () => {
  const page = pilotPages.find((candidate) => candidate.id === "P09");
  assert.ok(page);
  const presentation = editorialPresentation(page, p09Contract);
  assert.equal(presentation.title, "移行作業費用(2026年8月確認): JPY 2,006.67・公式支援費は未確認");
  assert.match(presentation.description, /Human作業費JPY 2,006\.67/);
  assert.match(presentation.lead, /^確認済み実測に基づくHuman作業費はJPY 2,006\.67/);
  assert.match(presentation.lead, /移行費用全体の確定額ではありません/);
});

test("calculator prefill copies only approved amount, currency, period, seats, tax, and source", () => {
  assert.deepEqual(calculatorPrefill(approvedContract()), {
    amount: "452.40",
    currency: "USD",
    billingPeriod: "annual",
    seats: "1",
    taxTreatment: "not_applicable",
    taxRate: "",
    sourceUrl: "https://mangools.com/subscriptions/checkout",
    observedOn: "2026-08-02",
    nextReviewOn: "2026-08-31",
    sourceLabel: "Mangools Basic",
  });
  const held = approvedContract();
  held.numeric_fields[0].review_status = "unreviewed";
  assert.equal(calculatorPrefill(held), null);
});

test("next-to-read derives links from pilot pages and excludes noindex or unapproved pages", () => {
  const current = pilotPages[0];
  const enabled = nextToReadPages(current, {
    indexGo: true,
    approvedArticleIdsValue: "P01,P02,P03,P04",
    articleReviewsCurrent: true,
    reviewApprovedArticleIds: new Set(["P01", "P02", "P03"]),
  });
  assert.deepEqual(enabled.map((page) => page.id), ["P02", "P03"]);
  assert.deepEqual(nextToReadPages(current, {
    indexGo: false,
    approvedArticleIdsValue: "P01,P02,P03",
    articleReviewsCurrent: true,
    reviewApprovedArticleIds: new Set(["P01", "P02", "P03"]),
  }), []);
});

test("next-to-read rotates through every approved article instead of concentrating on the first three", () => {
  const approvedIds = "P01,P02,P03,P04,P05,P06,P07,P08,P10,P12";
  const reviews = new Set(approvedIds.split(","));
  const links = new Map(pilotPages
    .filter((page) => reviews.has(page.id))
    .map((page) => [page.id, nextToReadPages(page, {
      indexGo: true,
      approvedArticleIdsValue: approvedIds,
      articleReviewsCurrent: true,
      reviewApprovedArticleIds: reviews,
    }).map((candidate) => candidate.id)]));

  assert.deepEqual(links.get("P02"), ["P03", "P04", "P05"]);
  assert.deepEqual(links.get("P12"), ["P01", "P02", "P03"]);
  for (const articleId of reviews) {
    assert.ok(
      [...links.values()].some((targets) => targets.includes(articleId)),
      `${articleId}: at least one approved inbound link`,
    );
  }
});
