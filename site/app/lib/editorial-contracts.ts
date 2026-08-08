import p01ContractJson from "../../../artifacts/editorial-inputs/P01-editorial-input.json";
import p02ContractJson from "../../../artifacts/editorial-inputs/P02-editorial-input.json";
import p03ContractJson from "../../../artifacts/editorial-inputs/P03-editorial-input.json";
import p06ContractJson from "../../../artifacts/editorial-inputs/P06-editorial-input.json";
import p07ContractJson from "../../../artifacts/editorial-inputs/P07-editorial-input.json";

import type { EditorialContract } from "./editorial-input-contract";
import { validateEditorialInput, valuesFromContract } from "./editorial-input-contract";
import type { PilotPage } from "./pilot-pages";

export { hasUnknownFact } from "./editorial-input-contract";

const importedContracts: Readonly<Record<string, unknown>> = {
  P01: p01ContractJson,
  P02: p02ContractJson,
  P03: p03ContractJson,
  P06: p06ContractJson,
  P07: p07ContractJson,
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
