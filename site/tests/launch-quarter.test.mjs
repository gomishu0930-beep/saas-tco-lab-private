import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildDerivativeTemplate,
  verifiedDerivativeArticleIds,
} from "../app/lib/derivative-templates.ts";
import {
  firstReleasePilotIds,
  launchDraftPriority,
  launchPriorityPages,
  pilotPages,
  serverArticleSlate,
  serverBigWordHubs,
  serverCtaPresentationPolicy,
} from "../app/lib/pilot-pages.ts";
import { articleStructuredData } from "../app/lib/structured-data.ts";
import { hasUnknownFact } from "../app/lib/editorial-input-contract.ts";

test("partner ledger keeps Japanese ASP account and program approval evidence exact", async () => {
  const ledgerUrl = new URL("../../docs/AFFILIATE_PARTNER_LEDGER.json", import.meta.url);
  const source = await readFile(ledgerUrl, "utf8");
  const ledger = JSON.parse(source);

  assert.deepEqual(
    ledger.entries.map((entry) => entry.partner_id),
    ["a8net", "mangools", "moshimo", "valuecommerce"],
  );
  assert.equal(ledger.tracking_ids_saved, false);
  assert.equal(ledger.advertising_urls_saved, false);
  assert.equal(ledger.personal_data_saved, false);
  assert.equal(
    ledger.cta_gate,
    "partner_approved+disclosure_precedes_cta+destination_configured+cta_go",
  );
  assert.doesNotMatch(source, /https?:\/\/|www\.|@/i);

  const entries = Object.fromEntries(ledger.entries.map((entry) => [entry.partner_id, entry]));
  assert.equal(entries.mangools.partnership_status, "approved");
  assert.equal(entries.a8net.account_status, "registered");
  assert.equal(entries.moshimo.account_status, "registered");
  assert.equal(entries.valuecommerce.account_status, "registered");
  for (const partnerId of ["a8net", "moshimo", "valuecommerce"]) {
    const entry = entries[partnerId];
    assert.equal(entry.partnership_status, "not_applied");
    assert.equal(entry.program_name, null);
    assert.equal(entry.category, null);
    assert.equal(entry.commission_amount.status, "unknown");
    assert.match(entry.affiliate_approval_runtime_secret, /^[A-Z][A-Z0-9_]+$/);
    assert.match(entry.destination_runtime_secret, /^[A-Z][A-Z0-9_]+$/);
  }

  assert.equal(ledger.schema_version, "1.1");
  assert.deepEqual(
    ledger.program_research.map((entry) => entry.research_id),
    [
      "a8net-formrun",
      "a8net-freee-accounting",
      "a8net-misoca",
      "a8net-money-forward-cloud-accounting",
      "a8net-will-mail",
      "a8net-xserver-business",
      "a8net-yayoi-series",
      "moshimo-conoha-wing",
      "moshimo-lolipop-rental-server",
      "moshimo-onamae-rental-server",
      "moshimo-shin-rental-server",
      "valuecommerce-ablenet-shared-server",
    ],
  );
  assert.deepEqual(
    [...new Set(ledger.program_research.map((entry) => entry.asp_partner_id))].sort(),
    ["a8net", "moshimo", "valuecommerce"],
  );
  assert.equal(
    ledger.program_research.filter((entry) => entry.partnership_status === "pending").length,
    0,
  );
  assert.equal(
    ledger.program_research.filter((entry) => entry.partnership_status === "approved").length,
    6,
  );
  assert.ok(
    ledger.program_research
      .filter((entry) => !new Set([
        "a8net-xserver-business",
        "moshimo-conoha-wing",
        "moshimo-lolipop-rental-server",
        "moshimo-onamae-rental-server",
        "moshimo-shin-rental-server",
        "valuecommerce-ablenet-shared-server",
      ]).has(entry.research_id))
      .every((entry) => entry.partnership_status === "not_applied"),
  );
  assert.ok(ledger.program_research.every((entry) => entry.commission_amount.value === null));
  assert.equal(
    ledger.program_research.filter(
      (entry) => entry.commission_amount.status === "restricted_dashboard_only",
    ).length,
    11,
  );
  const researched = Object.fromEntries(
    ledger.program_research.map((entry) => [entry.research_id, entry]),
  );
  assert.equal(researched["a8net-xserver-business"].partnership_status, "approved");
  assert.equal(researched["valuecommerce-ablenet-shared-server"].partnership_status, "approved");
  assert.equal(researched["valuecommerce-ablenet-shared-server"].condition_review_status, "detail_reviewed");
  assert.equal(researched["a8net-xserver-business"].condition_review_status, "detail_reviewed");
  assert.equal(researched["moshimo-lolipop-rental-server"].partnership_status, "approved");
  assert.equal(researched["moshimo-lolipop-rental-server"].condition_review_status, "detail_reviewed");
  assert.deepEqual(
    ledger.network_search_checks.map((entry) => entry.partner_id),
    ["benchmark-email", "blastmail", "conoha", "cybozu", "hubspot", "kintone"],
  );
  assert.ok(
    ledger.network_search_checks.every(
      (entry) => JSON.stringify(entry.next_networks) === JSON.stringify(["moshimo", "valuecommerce"]),
    ),
  );
});

test("launch drafting prioritizes transaction intent while retaining P01-P03 release batch", () => {
  assert.deepEqual(
    [...launchDraftPriority],
    ["P01", "P06", "P07", "P08", "P09", "P02", "P03", "P04", "P05", "P11", "P10", "P12"],
  );
  assert.deepEqual([...firstReleasePilotIds], ["P01", "P02", "P03"]);
  assert.deepEqual(launchPriorityPages().map((page) => page.id), [...launchDraftPriority]);
});

test("servers launch slate fixes twenty long-tail candidates and defers big-word hubs", async () => {
  assert.equal(serverArticleSlate.length, 20);
  assert.deepEqual(serverArticleSlate.map((article) => article.id),
    Array.from({ length: 20 }, (_, index) => `SVR${String(index + 1).padStart(2, "0")}`),
  );
  assert.equal(new Set(serverArticleSlate.map((article) => article.sourceQuery)).size, 20);
  assert.ok(serverArticleSlate.every((article) => article.state === "candidate_only"));
  assert.ok(serverArticleSlate.every((article) => article.competitionStatus === "unobserved"));
  assert.ok(serverArticleSlate.every(
    (article) => article.selectionBasis === "transaction_intent_specificity_proxy",
  ));
  assert.ok(serverArticleSlate.every(
    (article) => JSON.stringify(article.layoutOrder)
      === JSON.stringify(["disclosure", "calculator", "result", "cta_slot", "evidence"]),
  ));
  assert.ok(serverArticleSlate.every((article) => article.sections.length === 6));
  assert.ok(serverArticleSlate.every(
    (article) => JSON.stringify(article.reviewVoices)
      === JSON.stringify(["analyst", "editor", "skeptical_buyer"]),
  ));
  assert.ok(serverArticleSlate.every((article) => article.queryMatch === "exact"));
  assert.match(serverArticleSlate.find((article) => article.id === "SVR05").titleTemplate, /2年目料金/);
  assert.match(serverArticleSlate.find((article) => article.id === "SVR06").titleTemplate, /二重支払い/);
  const firstWaveQueries = new Set(serverArticleSlate.map((article) => article.sourceQuery));
  for (const hub of serverBigWordHubs) {
    assert.equal(hub.state, "deferred_internal_link_hub");
    assert.equal(firstWaveQueries.has(hub.sourceQuery), false, hub.sourceQuery);
  }
  const frozenSlate = await readFile(
    new URL("../../examples/jp_ja_keyword_slate_v2_servers.csv", import.meta.url),
    "utf8",
  );
  for (const article of serverArticleSlate) {
    assert.match(frozenSlate, new RegExp(`,${article.sourceQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`, "m"));
  }
});

test("servers CTA policy is disabled, single, or comparison and warns above 80 percent", () => {
  const valid = (partnerId, share = null) => ({
    partnerId,
    partnershipApproved: true,
    approvalCurrent: true,
    disclosureCompliant: true,
    destinationConfigured: true,
    ctaGo: true,
    confirmedCommissionSharePercent: share,
  });
  assert.equal(serverCtaPresentationPolicy([]).mode, "disabled");
  const single = serverCtaPresentationPolicy([valid("partner-a")]);
  assert.equal(single.mode, "single");
  assert.equal(single.dominantSharePercent, 100);
  assert.equal(single.dependencyWarning, true);

  const comparison = serverCtaPresentationPolicy([valid("partner-a", 50), valid("partner-b", 50)]);
  assert.equal(comparison.mode, "comparison");
  assert.equal(comparison.dependencyWarning, false);
  const concentrated = serverCtaPresentationPolicy([valid("partner-a", 81), valid("partner-b", 19)]);
  assert.equal(concentrated.mode, "comparison");
  assert.equal(concentrated.dependencyWarning, true);

  const missingGate = serverCtaPresentationPolicy([
    valid("partner-a"),
    { ...valid("partner-b"), ctaGo: false },
  ]);
  assert.equal(missingGate.mode, "single");
});

test("servers template fixes disclosure, calculator, result, CTA slot, evidence order", async () => {
  const source = await readFile(
    new URL("../app/components/PilotArticle.tsx", import.meta.url),
    "utf8",
  );
  const templateStart = source.indexOf("/** Candidate-only servers layout");
  assert.ok(templateStart >= 0);
  const templateSource = source.slice(templateStart);
  const positions = [
    templateSource.indexOf("<AdvertisingDisclosure"),
    templateSource.indexOf('data-server-template-step="calculator"'),
    templateSource.indexOf('data-server-template-step="result"'),
    templateSource.indexOf('data-server-template-step="cta_slot"'),
    templateSource.indexOf('data-server-template-step="evidence"'),
  ];
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual([...positions].sort((left, right) => left - right), positions);
  assert.match(templateSource, /data-server-affiliate-cta-state="disabled"/);
  assert.match(templateSource, /data-server-affiliate-cta-placeholder="a8net-xserver-business"/);
  assert.match(templateSource, /data-server-affiliate-cta-placeholder="moshimo-lolipop-rental-server"/);
  assert.match(templateSource, /data-server-affiliate-cta-placeholder="valuecommerce-ablenet-shared-server"/);
  assert.doesNotMatch(templateSource, /href=|rel="sponsored/);
});

test("servers calculator is zero-input and detailed inputs live only on methodology", async () => {
  const calculatorSource = await readFile(
    new URL("../app/components/TcoCalculator.tsx", import.meta.url),
    "utf8",
  );
  const zeroInputSource = calculatorSource.slice(calculatorSource.indexOf("export function ServerZeroInputCalculator"));
  assert.match(zeroInputSource, /\[12, 24, 36\]/);
  assert.match(zeroInputSource, /small_site|corporate_site|ecommerce/);
  assert.match(zeroInputSource, /calculateServerZeroInputTable/);
  assert.match(zeroInputSource, /未確認/);
  assert.doesNotMatch(zeroInputSource, /<input\b|<select\b/i);
  assert.match(zeroInputSource, /href="\/methodology\/#detailed-calculator"/);

  const articleSource = await readFile(
    new URL("../app/components/PilotArticle.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(articleSource, /<TcoCalculator\b/);
  assert.match(articleSource, /<ServerZeroInputCalculator\b/);

  const methodologySource = await readFile(
    new URL("../app/methodology/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(methodologySource, /id="detailed-calculator"/);
  assert.match(methodologySource, /<TcoCalculator\b/);
});

test("released note and X derivatives contain verified copy while held pages fail closed", async () => {
  const launchState = JSON.parse(await readFile(
    new URL("../../docs/EDITORIAL_LAUNCH_STATE.json", import.meta.url),
    "utf8",
  ));
  assert.deepEqual(
    [...verifiedDerivativeArticleIds],
    [...launchState.deployed_articles].sort(),
    "derivatives must cover the exact deployed article set",
  );
  const released = new Set(verifiedDerivativeArticleIds);
  for (const page of launchPriorityPages()) {
    const template = buildDerivativeTemplate(page);
    assert.match(template.note, /^\[PR\]/, page.id);
    assert.match(template.xThread[0], /^\[PR\]/, page.id);
    assert.ok(template.xThread.every((post) => post.length <= 280), page.id);
    if (released.has(page.id)) {
      assert.ok(template.note.length >= 1_300 && template.note.length <= 1_700, `${page.id}: note length ${template.note.length}`);
      assert.equal(template.xThread.length, 8, page.id);
      assert.match(template.note, /https:\/\/saastcolab\.jp\/pilot\//);
      assert.match(template.note, /観測日は2026-08-/);
      assert.match(template.xThread.at(-1), /https:\/\/saastcolab\.jp\/pilot\//);
      assert.doesNotMatch(`${template.note}\n${template.xThread.join("\n")}`, /【|Humanが公開時に入力|contract:/);
    } else {
      assert.equal(template.xThread.length, 1, page.id);
      assert.match(template.note, /確認待ち/);
      assert.match(template.xThread[0], /投稿しません/);
      assert.doesNotMatch(template.note, /https:\/\/saastcolab\.jp\/pilot\//);
    }
    assert.doesNotMatch(`${template.note}\n${template.xThread.join("\n")}`, /rel=["']sponsored|[?&](?:utm_|ref=|affiliate|tracking)/i);
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
    name: "vendor plan（月次請求）",
    price: "100",
    priceCurrency: "JPY",
    priceValidUntil: "2026-10-28",
  }]);
  assert.equal(
    approved["@graph"][0].name,
    "vendor料金(2026年7月確認): JPY 100と12か月TCO｜料金計算",
  );

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
