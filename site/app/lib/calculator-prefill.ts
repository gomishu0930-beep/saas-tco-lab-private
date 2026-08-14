import type { EditorialContract } from "./editorial-input-contract";
import { planDisplayName, primaryConfirmedPrice, vendorDisplayName } from "./editorial-presentation.ts";

export type CalculatorPrefill = {
  amount: string;
  currency: string;
  billingPeriod: "monthly" | "annual";
  seats: string;
  taxTreatment: "included" | "excluded" | "not_applicable" | "unknown";
  taxRate: string;
  sourceUrl: string;
  observedOn: string;
  nextReviewOn: string;
  sourceLabel: string;
};

/** Build a calculator prefill only from approved, directly observed evidence. */
export function calculatorPrefill(contract: EditorialContract | null): CalculatorPrefill | null {
  const price = primaryConfirmedPrice(contract);
  if (
    !contract
    || !price
    || !price.source_url
    || (price.billing_period !== "monthly" && price.billing_period !== "annual")
  ) return null;

  const seats = contract.numeric_fields.find((field) => (
    field.value_kind === "seat_count"
    && field.value_status === "known"
    && field.review_status === "approved"
    && field.value !== null
    && (
      field.scope_kind === "human_scenario"
      || (field.vendor_id === price.vendor_id && field.plan_id === price.plan_id)
    )
  ));
  if (!seats?.value) return null;

  const taxRate = contract.numeric_fields.find((field) => (
    field.value_kind === "tax_rate"
    && field.value_status === "known"
    && field.review_status === "approved"
    && field.value !== null
    && (
      field.scope_kind === "human_scenario"
      || (field.vendor_id === price.vendor_id && field.plan_id === price.plan_id)
    )
  ));
  const taxTreatment = price.tax_treatment === "included"
    || price.tax_treatment === "excluded"
    || price.tax_treatment === "not_applicable"
    ? price.tax_treatment
    : "unknown";

  return {
    amount: price.value as string,
    currency: price.currency as string,
    billingPeriod: price.billing_period,
    seats: seats.value,
    taxTreatment,
    taxRate: taxRate?.value ?? "",
    sourceUrl: price.source_url,
    observedOn: price.observed_on,
    nextReviewOn: price.next_review_on,
    sourceLabel: `${vendorDisplayName(price.vendor_id)} ${planDisplayName(price.vendor_id, price.plan_id)}`,
  };
}
