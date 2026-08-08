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
    const readerText = body.replace(/\{\{contract:[^}]+\}\}/g, "確認値");
    assert.doesNotMatch(
      readerText,
      /vendor|billing toggle|価格表示分類|Human scenario|contract/i,
      `${page.id}: reader copy excludes internal terms`,
    );
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
  assert.equal(p02?.numericFields.find(field => field.key === "plan.usage_quota")?.label, "キーワード検索回数 / 24時間");
  assert.equal(p03?.numericFields.find(field => field.key === "alternative.usage_quota")?.label, "追跡キーワード数（候補別単位）");
  assert.match(articleDraft(p03).sections.find(section => section.title === "料金と利用上限")?.body ?? "", /課金単位が同じとは限らない/);
});

test("P06 explains the permanent annual discount condition in reader language", () => {
  const p06 = pilotPages.find(page => page.id === "P06");
  const pricing = articleDraft(p06).sections.find(section => section.title === "月払いと年払い")?.body ?? "";
  assert.match(pricing, /通貨と税条件をそろえて/);
  assert.match(pricing, /終了日のない年払い割引/);
  assert.doesNotMatch(pricing.replace(/\{\{contract:[^}]+\}\}/g, "確認値"), /annual_discount_permanent|contract/i);
});
