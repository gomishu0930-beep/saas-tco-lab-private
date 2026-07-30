export type BillingPeriod = "monthly" | "annual";
export type PriceBasis = "flat" | "per_seat";
export type TaxTreatment = "included" | "excluded" | "not_applicable" | "unknown";

export type RecurringCharge = {
  name: string;
  amount: string;
  currency: string;
  billingPeriod: BillingPeriod;
  priceBasis: PriceBasis;
  minimumSeats: number;
  includedSeats: number;
  maximumSeats: number | null;
};

export type UsageCharge = {
  name: string;
  includedQuantity: string;
  includedBasis: PriceBasis;
  overageUnitPrice: string | null;
  currency: string;
  unit: string;
  billingPeriod: BillingPeriod;
};

export type PricingQuote = {
  currency: string;
  minorUnitDigits: number;
  minimumCommitmentMonths: number;
  base: RecurringCharge;
  addons: readonly RecurringCharge[];
  usage: UsageCharge | null;
  tax: { treatment: TaxTreatment; rate: string | null };
};

export type UsageScenario = {
  seats: number;
  monthlyUsage: readonly string[];
  usageUnit: string | null;
};

export type TcoLineItem = {
  name: string;
  kind: string;
  listedMinor: bigint;
  addedTaxMinor: bigint;
  totalMinor: bigint;
  billedOccurrences: number;
};

export type TcoResult = {
  currency: string;
  minorUnitDigits: number;
  months: number;
  seats: number;
  listedMinor: bigint;
  addedTaxMinor: bigint;
  totalMinor: bigint;
  lineItems: readonly TcoLineItem[];
};

type Rational = { numerator: bigint; denominator: bigint };

export class TcoError extends Error {}

function decimal(value: string, field: string): Rational {
  if (typeof value !== "string" || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) {
    throw new TcoError(`${field} must be a non-negative plain decimal string`);
  }
  const [whole, fraction = ""] = value.split(".");
  const denominator = 10n ** BigInt(fraction.length);
  return {
    numerator: BigInt(`${whole}${fraction}`),
    denominator,
  };
}

function add(left: Rational, right: Rational): Rational {
  return {
    numerator: left.numerator * right.denominator + right.numerator * left.denominator,
    denominator: left.denominator * right.denominator,
  };
}

function subtractFloorZero(left: Rational, right: Rational): Rational {
  const numerator = left.numerator * right.denominator - right.numerator * left.denominator;
  if (numerator <= 0n) return { numerator: 0n, denominator: 1n };
  return { numerator, denominator: left.denominator * right.denominator };
}

function multiply(left: Rational, right: Rational): Rational {
  return {
    numerator: left.numerator * right.numerator,
    denominator: left.denominator * right.denominator,
  };
}

function multiplyInteger(value: Rational, quantity: number): Rational {
  return { numerator: value.numerator * BigInt(quantity), denominator: value.denominator };
}

function roundHalfUp(value: Rational): bigint {
  return (2n * value.numerator + value.denominator) / (2n * value.denominator);
}

function majorToMinor(value: Rational, digits: number): bigint {
  return roundHalfUp({
    numerator: value.numerator * 10n ** BigInt(digits),
    denominator: value.denominator,
  });
}

function positiveInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new TcoError(`${field} must be a positive safe integer`);
  }
  return value;
}

function nonNegativeInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TcoError(`${field} must be a non-negative safe integer`);
  }
  return value;
}

function normalizeCurrency(value: string, field: string): string {
  if (typeof value !== "string" || !/^[A-Z]{3}$/.test(value)) {
    throw new TcoError(`${field} must be an uppercase ISO-like currency code`);
  }
  return value;
}

function requireCurrency(value: string, expected: string, field: string): void {
  if (normalizeCurrency(value, field) !== expected) {
    throw new TcoError(`${field} differs from quote currency; conversion is disabled`);
  }
}

function billingOccurrences(period: BillingPeriod, months: number, field: string): number {
  if (period === "monthly") return months;
  if (period !== "annual") throw new TcoError(`${field} has an unknown billing period`);
  if (months % 12 !== 0) {
    throw new TcoError(`${field} is annual but ${months} months requires unspecified proration`);
  }
  return months / 12;
}

function validateTax(tax: PricingQuote["tax"]): { treatment: Exclude<TaxTreatment, "unknown">; rate: Rational | null } {
  if (tax.treatment === "unknown") throw new TcoError("tax treatment is unknown");
  if (tax.treatment === "excluded") {
    if (tax.rate === null) throw new TcoError("excluded tax requires a rate");
    const rate = decimal(tax.rate, "tax.rate");
    if (rate.numerator > rate.denominator) throw new TcoError("tax.rate must be between 0 and 1");
    return { treatment: tax.treatment, rate };
  }
  if (tax.rate !== null) throw new TcoError("included or not-applicable tax cannot have a rate");
  return { treatment: tax.treatment, rate: null };
}

function addedTax(invoiceMinor: bigint, treatment: Exclude<TaxTreatment, "unknown">, rate: Rational | null): bigint {
  if (treatment !== "excluded") return 0n;
  if (rate === null) throw new TcoError("excluded tax requires a rate");
  return roundHalfUp({ numerator: invoiceMinor * rate.numerator, denominator: rate.denominator });
}

function priceRecurring(
  charge: RecurringCharge,
  kind: string,
  months: number,
  seats: number,
  currency: string,
  digits: number,
  tax: ReturnType<typeof validateTax>,
): TcoLineItem {
  requireCurrency(charge.currency, currency, `${kind}.currency`);
  const amount = decimal(charge.amount, `${kind}.amount`);
  const minimumSeats = positiveInteger(charge.minimumSeats, `${kind}.minimumSeats`);
  const includedSeats = nonNegativeInteger(charge.includedSeats, `${kind}.includedSeats`);
  if (includedSeats > minimumSeats) throw new TcoError(`${kind}.includedSeats exceeds minimumSeats`);
  if (charge.maximumSeats !== null) {
    positiveInteger(charge.maximumSeats, `${kind}.maximumSeats`);
    if (charge.maximumSeats < minimumSeats) throw new TcoError(`${kind}.maximumSeats is below minimumSeats`);
    if (seats > charge.maximumSeats) throw new TcoError(`${kind} supports at most ${charge.maximumSeats} seats`);
  }
  const occurrences = billingOccurrences(charge.billingPeriod, months, kind);
  const quantity = charge.priceBasis === "per_seat" ? Math.max(Math.max(seats, minimumSeats) - includedSeats, 0) : 1;
  if (charge.priceBasis !== "flat" && charge.priceBasis !== "per_seat") throw new TcoError(`${kind}.priceBasis is unknown`);
  const invoiceMinor = majorToMinor(multiplyInteger(amount, quantity), digits);
  const invoiceTax = addedTax(invoiceMinor, tax.treatment, tax.rate);
  const listedMinor = invoiceMinor * BigInt(occurrences);
  const addedTaxMinor = invoiceTax * BigInt(occurrences);
  return {
    name: charge.name,
    kind,
    listedMinor,
    addedTaxMinor,
    totalMinor: listedMinor + addedTaxMinor,
    billedOccurrences: occurrences,
  };
}

function priceUsage(
  usage: UsageCharge,
  values: readonly Rational[],
  scenarioUnit: string | null,
  months: number,
  seats: number,
  baseMinimumSeats: number,
  currency: string,
  digits: number,
  tax: ReturnType<typeof validateTax>,
): TcoLineItem {
  requireCurrency(usage.currency, currency, "usage.currency");
  if (!usage.unit.trim() || scenarioUnit === null || usage.unit.trim() !== scenarioUnit.trim()) {
    throw new TcoError("usage unit mismatch");
  }
  let included = decimal(usage.includedQuantity, "usage.includedQuantity");
  if (usage.includedBasis === "per_seat") included = multiplyInteger(included, Math.max(seats, baseMinimumSeats));
  else if (usage.includedBasis !== "flat") throw new TcoError("usage.includedBasis is unknown");

  let windows: Rational[];
  if (usage.billingPeriod === "monthly") windows = [...values];
  else {
    billingOccurrences(usage.billingPeriod, months, "usage");
    windows = [];
    for (let index = 0; index < values.length; index += 12) {
      windows.push(values.slice(index, index + 12).reduce(add, { numerator: 0n, denominator: 1n }));
    }
  }

  const overagePrice = usage.overageUnitPrice === null ? null : decimal(usage.overageUnitPrice, "usage.overageUnitPrice");
  let listedMinor = 0n;
  let addedTaxMinor = 0n;
  for (const measured of windows) {
    const overage = subtractFloorZero(measured, included);
    if (overage.numerator > 0n && overagePrice === null) throw new TcoError("usage exceeds allowance but overage price is unknown");
    const invoiceMinor = majorToMinor(multiply(overage, overagePrice ?? { numerator: 0n, denominator: 1n }), digits);
    listedMinor += invoiceMinor;
    addedTaxMinor += addedTax(invoiceMinor, tax.treatment, tax.rate);
  }
  return {
    name: usage.name,
    kind: "usage",
    listedMinor,
    addedTaxMinor,
    totalMinor: listedMinor + addedTaxMinor,
    billedOccurrences: windows.length,
  };
}

export function calculateTco(quote: PricingQuote, scenario: UsageScenario): TcoResult {
  const currency = normalizeCurrency(quote.currency, "quote.currency");
  if (!Number.isSafeInteger(quote.minorUnitDigits) || quote.minorUnitDigits < 0 || quote.minorUnitDigits > 8) {
    throw new TcoError("minorUnitDigits must be an integer between 0 and 8");
  }
  const months = positiveInteger(scenario.monthlyUsage.length, "scenario.months");
  const seats = positiveInteger(scenario.seats, "scenario.seats");
  const commitment = positiveInteger(quote.minimumCommitmentMonths, "minimumCommitmentMonths");
  if (months < commitment) throw new TcoError("scenario is shorter than the minimum commitment");
  const values = scenario.monthlyUsage.map((value, index) => decimal(value, `monthlyUsage[${index}]`));
  const tax = validateTax(quote.tax);
  const baseMinimumSeats = positiveInteger(quote.base.minimumSeats, "base.minimumSeats");
  const lineItems: TcoLineItem[] = [
    priceRecurring(quote.base, "base", months, seats, currency, quote.minorUnitDigits, tax),
  ];
  quote.addons.forEach((addon, index) => {
    lineItems.push(priceRecurring(addon, `addon[${index}]`, months, seats, currency, quote.minorUnitDigits, tax));
  });
  if (quote.usage === null) {
    if (values.some((value) => value.numerator !== 0n)) throw new TcoError("scenario contains usage but quote has no usage pricing");
  } else {
    lineItems.push(priceUsage(quote.usage, values, scenario.usageUnit, months, seats, baseMinimumSeats, currency, quote.minorUnitDigits, tax));
  }
  const listedMinor = lineItems.reduce((total, item) => total + item.listedMinor, 0n);
  const addedTaxMinor = lineItems.reduce((total, item) => total + item.addedTaxMinor, 0n);
  return {
    currency,
    minorUnitDigits: quote.minorUnitDigits,
    months,
    seats,
    listedMinor,
    addedTaxMinor,
    totalMinor: listedMinor + addedTaxMinor,
    lineItems,
  };
}

export function formatMinor(value: bigint, currency: string, digits: number): string {
  const scale = 10n ** BigInt(digits);
  const whole = value / scale;
  const fraction = value % scale;
  const rendered = digits === 0 ? whole.toString() : `${whole}.${fraction.toString().padStart(digits, "0")}`;
  return `${currency} ${rendered}`;
}
