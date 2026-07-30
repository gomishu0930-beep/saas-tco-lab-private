import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { calculateTco } from "../app/lib/tco.ts";

const cases = JSON.parse(
  await readFile(new URL("../../tests/fixtures/tco_golden.json", import.meta.url), "utf8"),
);

test("TypeScript calculator matches every Python-owned golden fixture", () => {
  for (const fixture of cases) {
    const result = calculateTco(fixture.quote, fixture.scenario);
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
