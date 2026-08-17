import assert from "node:assert/strict";
import test from "node:test";

import { approvedArticleIds, evaluatePublicationGate } from "../app/lib/publication-gate.ts";

const ready = {
  articleId: "P01",
  indexGo: true,
  articleApproved: true,
  articleReviewCurrent: true,
  ctaGo: true,
  affiliatePartnerApproved: true,
  affiliateApprovalCurrent: true,
  destinationConfigured: true,
  disclosureBeforeCta: true,
};

test("indexing requires both global GO and exact article approval", () => {
  assert.equal(evaluatePublicationGate(ready).indexable, true);
  const held = evaluatePublicationGate({ ...ready, indexGo: false });
  assert.equal(held.indexable, false);
  assert.equal(held.robots, "noindex, follow, noarchive, nosnippet");
  assert.equal(evaluatePublicationGate({ ...ready, articleApproved: false }).indexable, false);
  assert.equal(evaluatePublicationGate({ ...ready, articleReviewCurrent: false }).indexable, false);
});

test("CTA requires approved current partner, destination, article, and prior disclosure", () => {
  assert.equal(evaluatePublicationGate(ready).ctaEnabled, true);
  for (const field of ["ctaGo", "affiliatePartnerApproved", "affiliateApprovalCurrent", "destinationConfigured", "disclosureBeforeCta", "articleApproved"]) {
    assert.equal(evaluatePublicationGate({ ...ready, [field]: false }).ctaEnabled, false, field);
  }
});

test("approved article list rejects ambiguity and non-P01-P12 values", () => {
  assert.deepEqual([...approvedArticleIds("P01,P12")], ["P01", "P12"]);
  assert.throws(() => approvedArticleIds("P01,P01"), /unique/);
  assert.throws(() => approvedArticleIds("P13"), /P01-P12/);
});
