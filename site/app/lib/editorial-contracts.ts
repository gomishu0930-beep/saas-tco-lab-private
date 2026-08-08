import p01ContractJson from "../../../artifacts/editorial-inputs/P01-editorial-input.json";
import p02ContractJson from "../../../artifacts/editorial-inputs/P02-editorial-input.json";
import p03ContractJson from "../../../artifacts/editorial-inputs/P03-editorial-input.json";
import p04ContractJson from "../../../artifacts/editorial-inputs/P04-editorial-input.json";
import p05ContractJson from "../../../artifacts/editorial-inputs/P05-editorial-input.json";
import p06ContractJson from "../../../artifacts/editorial-inputs/P06-editorial-input.json";
import p07ContractJson from "../../../artifacts/editorial-inputs/P07-editorial-input.json";
import p08ContractJson from "../../../artifacts/editorial-inputs/P08-editorial-input.json";
import p09ContractJson from "../../../artifacts/editorial-inputs/P09-editorial-input.json";
import p10ContractJson from "../../../artifacts/editorial-inputs/P10-editorial-input.json";
import p11ContractJson from "../../../artifacts/editorial-inputs/P11-editorial-input.json";
import p12ContractJson from "../../../artifacts/editorial-inputs/P12-editorial-input.json";

import type { EditorialContract } from "./editorial-input-contract";
import { validateEditorialInput, valuesFromContract } from "./editorial-input-contract";
import type { PilotPage } from "./pilot-pages";

export { hasUnknownFact } from "./editorial-input-contract";

const importedContracts: Readonly<Record<string, unknown>> = {
  P01: p01ContractJson,
  P02: p02ContractJson,
  P03: p03ContractJson,
  P04: p04ContractJson,
  P05: p05ContractJson,
  P06: p06ContractJson,
  P07: p07ContractJson,
  P08: p08ContractJson,
  P09: p09ContractJson,
  P10: p10ContractJson,
  P11: p11ContractJson,
  P12: p12ContractJson,
};

/**
 * Return only contracts that still pass the same deterministic form validation.
 * Python/Pydantic remains authoritative; this second check protects the site build
 * from a stale or structurally mismatched generated artifact.
 */
export function editorialContract(page: PilotPage): EditorialContract | null {
  const candidate = importedContracts[page.id] as EditorialContract | undefined;
  if (!candidate) return null;
  if (
    candidate.schema_version !== "2.3"
    || candidate.article_id !== page.id
    || candidate.slug !== page.slug
    || candidate.title !== page.title
    || candidate.disclosure_version !== "pr-affiliate-v1"
    || !["unreviewed", "approved", "rejected"].includes(candidate.article_review_status)
  ) {
    throw new Error(`${page.id}: imported editorial contract metadata is invalid`);
  }
  const rows = valuesFromContract(page, candidate);
  if (!rows) throw new Error(`${page.id}: imported editorial contract fields are invalid`);
  const validation = validateEditorialInput(page, rows);
  if (!validation.contract || Object.keys(validation.errors).length) {
    throw new Error(`${page.id}: imported editorial contract failed site validation`);
  }
  return candidate;
}
