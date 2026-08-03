import assert from "node:assert/strict";
import test from "node:test";

import { buildDerivativeTemplate } from "../app/lib/derivative-templates.ts";
import {
  firstReleasePilotIds,
  launchDraftPriority,
  launchPriorityPages,
  pilotPages,
} from "../app/lib/pilot-pages.ts";
import { articleStructuredData } from "../app/lib/structured-data.ts";
import { hasUnknownFact } from "../app/lib/editorial-input-contract.ts";

test("launch drafting prioritizes transaction intent while retaining P01-P03 release batch", () => {
  assert.deepEqual(
    [...launchDraftPriority],
    ["P01", "P06", "P07", "P08", "P09", "P02", "P03", "P04", "P05", "P11", "P10", "P12"],
  );
  assert.deepEqual([...firstReleasePilotIds], ["P01", "P02", "P03"]);
  assert.deepEqual(launchPriorityPages().map((page) => page.id), [...launchDraftPriority]);
});

test("note and X templates are bounded, disclosed first, and remain Human-posted", () => {
  for (const page of launchPriorityPages()) {
    const template = buildDerivativeTemplate(page);
    assert.match(template.note, /^\[PR\]/, page.id);
    assert.ok(template.note.length >= 1_300 && template.note.length <= 1_700, `${page.id}: note length ${template.note.length}`);
    assert.equal(template.xThread.length, 8, page.id);
    assert.match(template.xThread[0], /^\[PR\]/, page.id);
    assert.ok(template.xThread.every((post) => post.length <= 280), page.id);
    assert.match(template.note, /Humanが公開時に入力/);
    assert.match(template.xThread.at(-1), /Humanが公開時に入力/);
    assert.doesNotMatch(`${template.note}\n${template.xThread.join("\n")}`, /rel=["']sponsored|https?:\/\//i);
  }
});

function contract(reviewStatus, fieldReviewStatus) {
  return {
    schema_version: "2.3",
    article_id: "P01",
    slug: "pricing-calculator",
    title: "料金計算",
    disclosure_version: "pr-affiliate-v1",
    article_review_status: reviewStatus,
    numeric_fields: [{
      schema_version: "2.3",
      scope_kind: "vendor_plan",
      vendor_id: "vendor",
      plan_id: "plan",
      field: "pricing.base_price",
      value_kind: "price",
      value_status: "known",
      value: "100",
      unit: "/ mo",
      unknown_reason: null,
      currency_status: "known",
      currency: "JPY",
      currency_display: "¥",
      currency_unknown_reason: null,
      billing_period: "monthly",
      tax_treatment: "unknown",
      billing_toggle_state: "monthly_selected",
      sale_banner_state: "none",
      observed_price_basis: "displayed_price",
      derived_monthly_value: null,
      derived_monthly_unit: null,
      derivation_method: null,
      source_url: "https://example.com/pricing",
      scenario_basis: null,
      observed_on: "2026-07-30",
      next_review_on: "2026-10-28",
      entered_by: "human",
      acquisition_method: "manual_public_page",
      rights_path: "human_editorial",
      review_status: fieldReviewStatus,
    }],
  };
}

test("structured data emits an Offer only for Human-approved price fields", () => {
  const page = pilotPages[0];
  const unreviewed = articleStructuredData(page, contract("unreviewed", "unreviewed"));
  assert.equal("offers" in unreviewed["@graph"][0], false);

  const approved = articleStructuredData(page, contract("approved", "approved"));
  assert.deepEqual(approved["@graph"][0].offers, [{
    "@type": "Offer",
    name: "vendor / plan / pricing.base_price",
    price: "100",
    priceCurrency: "JPY",
    priceValidUntil: "2026-10-28",
  }]);

  const fieldHeld = articleStructuredData(page, contract("approved", "unreviewed"));
  assert.equal("offers" in fieldHeld["@graph"][0], false);
});

test("v2.3 treats only time-limited or unknown price display classes as held facts", () => {
  const field = contract("approved", "approved").numeric_fields[0];
  for (const state of ["none", "annual_discount_permanent"]) {
    assert.equal(hasUnknownFact({ ...field, sale_banner_state: state, tax_treatment: "included" }), false);
  }
  for (const state of ["time_limited_promo", "unknown"]) {
    assert.equal(hasUnknownFact({ ...field, sale_banner_state: state, tax_treatment: "included" }), true);
  }
});
