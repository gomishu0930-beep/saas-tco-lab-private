import assert from "node:assert/strict";
import test from "node:test";

import { articleDraft } from "../app/lib/article-drafts.ts";
import { pilotPages } from "../app/lib/pilot-pages.ts";

test("P01-P12 each have a six-section evidence-safe draft", () => {
  assert.equal(pilotPages.length, 12);
  for (const page of pilotPages) {
    const draft = articleDraft(page);
    assert.equal(draft.sections.length, 6, page.id);
    assert.deepEqual(draft.reviewVoices, ["analyst", "editor", "skeptical_buyer"], page.id);
    const body = draft.sections.map(section => section.body).join("\n");
    if (Number(page.id.slice(1)) <= 3) assert.doesNotMatch(body, /\{\{contract:/, page.id);
    else assert.match(body, /\{\{contract:/, page.id);
    assert.doesNotMatch(body, /[¥$€£][0-9]|[0-9][,.][0-9]/, page.id);
  }
});

test("P01-P03 are the explicit first batch", () => {
  for (const page of pilotPages) {
    assert.equal(articleDraft(page).priority, Number(page.id.slice(1)) <= 3 ? "first" : "standard");
  }
});

test("P02 and P03 name unlike quota fields without implying equivalence", () => {
  const p02 = pilotPages.find(page => page.id === "P02");
  const p03 = pilotPages.find(page => page.id === "P03");
  assert.equal(p02?.numericFields.find(field => field.key === "plan.usage_quota")?.label, "keyword検索回数 / 24h");
  assert.equal(p03?.numericFields.find(field => field.key === "alternative.usage_quota")?.label, "追跡keyword数（候補別単位）");
  assert.match(articleDraft(p03).sections.find(section => section.title === "料金と上限")?.body ?? "", /checkout請求総額を一次観測値/);
});

test("P06 permits an approximate annual discount fact only from v2.3 permanent evidence", () => {
  const p06 = pilotPages.find(page => page.id === "P06");
  const pricing = articleDraft(p06).sections.find(section => section.title === "料金と上限")?.body ?? "";
  assert.match(pricing, /annual_discount_permanent/);
  assert.match(pricing, /同一通貨・同一税条件/);
  assert.match(pricing, /年払いは月払い比で約N%割安/);
});
