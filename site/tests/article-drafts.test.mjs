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
