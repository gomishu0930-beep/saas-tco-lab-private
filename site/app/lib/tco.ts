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

export type ServerTcoTerms = {
  initialFee: string | null;
  renewalFee: string | null;
  renewalDueMonth: number | null;
  campaignPrice: string | null;
  campaignPeriodMonths: number | null;
  domainPrice: string | null;
  domainBillingPeriod: BillingPeriod | null;
  domainIncludedMonths: number | null;
};

export type ServerUseCase = "small_site" | "corporate_site" | "ecommerce";
export type ServerPlanPriceStatus = "known" | "unknown";
export type ServerPlanReviewStatus = "unreviewed" | "approved";

export type ServerZeroInputPlan = {
  vendorId: string;
  planId: string;
  displayName: string;
  priceStatus: ServerPlanPriceStatus;
  reviewStatus: ServerPlanReviewStatus;
  eligibleUseCases: readonly ServerUseCase[];
  quote: PricingQuote | null;
  serverTerms: ServerTcoTerms | null;
  unknownReason: string | null;
  confirmedThroughMonths?: 12 | 24 | 36 | null;
  horizonUnknownReason?: string | null;
  observedOn: string | null;
  nextReviewOn: string | null;
};

export type ServerZeroInputContract = {
  articleReviewStatus: ServerPlanReviewStatus;
  useCaseRequirements: Readonly<Record<ServerUseCase, readonly string[]>>;
  plans: readonly ServerZeroInputPlan[];
};

export type ServerZeroInputRow = {
  vendorId: string;
  planId: string;
  displayName: string;
  status: "ranked" | "confirmed_unranked" | "unconfirmed" | "ineligible" | "currency_mismatch";
  totalMinor: bigint | null;
  currency: string | null;
  minorUnitDigits: number | null;
  rank: number | null;
  differenceFromLowestMinor: bigint | null;
  reason: string | null;
  observedOn: string | null;
  nextReviewOn: string | null;
};

export type ServerZeroInputTable = {
  months: 12 | 24 | 36;
  useCase: ServerUseCase;
  comparisonMode: "ranked_comparison" | "confirmed_list";
  confirmedVendorCount: number;
  rows: readonly ServerZeroInputRow[];
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

function greaterThan(left: Rational, right: Rational): boolean {
  return left.numerator * right.denominator > right.numerator * left.denominator;
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

function priceFixed(
  name: string,
  kind: string,
  amount: Rational,
  billed: boolean,
  digits: number,
  tax: ReturnType<typeof validateTax>,
): TcoLineItem {
  const invoiceMinor = billed ? majorToMinor(amount, digits) : 0n;
  const taxMinor = addedTax(invoiceMinor, tax.treatment, tax.rate);
  return {
    name,
    kind,
    listedMinor: invoiceMinor,
    addedTaxMinor: taxMinor,
    totalMinor: invoiceMinor + taxMinor,
    billedOccurrences: billed ? 1 : 0,
  };
}

function pairPresent(left: unknown, right: unknown, message: string): boolean {
  const leftPresent = left !== null;
  const rightPresent = right !== null;
  if (leftPresent !== rightPresent) throw new TcoError(message);
  return leftPresent;
}

function calculateTcoInternal(
  quote: PricingQuote,
  scenario: UsageScenario,
  serverTerms: ServerTcoTerms | null,
): TcoResult {
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
  const lineItems: TcoLineItem[] = [];

  if (serverTerms?.initialFee !== null && serverTerms?.initialFee !== undefined) {
    lineItems.push(priceFixed(
      "initial fee",
      "server.initial_fee",
      decimal(serverTerms.initialFee, "server.initialFee"),
      true,
      quote.minorUnitDigits,
      tax,
    ));
  }

  const hasCampaign = serverTerms === null
    ? false
    : pairPresent(
        serverTerms.campaignPrice,
        serverTerms.campaignPeriodMonths,
        "server campaign price and period must be supplied together",
      );
  if (!hasCampaign) {
    lineItems.push(priceRecurring(quote.base, "base", months, seats, currency, quote.minorUnitDigits, tax));
  } else {
    if (quote.base.billingPeriod !== "monthly") {
      throw new TcoError("server campaign pricing currently requires an observed monthly base price");
    }
    const campaignPrice = decimal(serverTerms!.campaignPrice!, "server.campaignPrice");
    if (greaterThan(campaignPrice, decimal(quote.base.amount, "base.amount"))) {
      throw new TcoError("server campaign price cannot exceed the observed regular price");
    }
    const campaignPeriodMonths = positiveInteger(
      serverTerms!.campaignPeriodMonths!,
      "server.campaignPeriodMonths",
    );
    const campaignMonths = Math.min(months, campaignPeriodMonths);
    lineItems.push(priceRecurring(
      { ...quote.base, name: `${quote.base.name} (campaign)`, amount: serverTerms!.campaignPrice! },
      "base.campaign",
      campaignMonths,
      seats,
      currency,
      quote.minorUnitDigits,
      tax,
    ));
    const regularMonths = months - campaignMonths;
    if (regularMonths > 0) {
      lineItems.push(priceRecurring(
        quote.base,
        "base.regular",
        regularMonths,
        seats,
        currency,
        quote.minorUnitDigits,
        tax,
      ));
    }
  }

  quote.addons.forEach((addon, index) => {
    lineItems.push(priceRecurring(addon, `addon[${index}]`, months, seats, currency, quote.minorUnitDigits, tax));
  });
  if (quote.usage === null) {
    if (values.some((value) => value.numerator !== 0n)) throw new TcoError("scenario contains usage but quote has no usage pricing");
  } else {
    lineItems.push(priceUsage(quote.usage, values, scenario.usageUnit, months, seats, baseMinimumSeats, currency, quote.minorUnitDigits, tax));
  }

  if (serverTerms !== null) {
    const hasRenewal = pairPresent(
      serverTerms.renewalFee,
      serverTerms.renewalDueMonth,
      "server renewal fee and due month must be supplied together",
    );
    if (hasRenewal) {
      const dueMonth = positiveInteger(serverTerms.renewalDueMonth!, "server.renewalDueMonth");
      lineItems.push(priceFixed(
        "renewal fee",
        "server.renewal_fee",
        decimal(serverTerms.renewalFee!, "server.renewalFee"),
        dueMonth <= months,
        quote.minorUnitDigits,
        tax,
      ));
    }

    const domainValues = [
      serverTerms.domainPrice,
      serverTerms.domainBillingPeriod,
      serverTerms.domainIncludedMonths,
    ];
    const domainPresent = domainValues.filter((value) => value !== null).length;
    if (domainPresent !== 0 && domainPresent !== domainValues.length) {
      throw new TcoError("server domain price, billing period, and included months must be supplied together");
    }
    if (domainPresent === domainValues.length) {
      const includedMonths = nonNegativeInteger(
        serverTerms.domainIncludedMonths!,
        "server.domainIncludedMonths",
      );
      lineItems.push(priceRecurring(
        {
          name: "domain after included benefit",
          amount: serverTerms.domainPrice!,
          currency,
          billingPeriod: serverTerms.domainBillingPeriod!,
          priceBasis: "flat",
          minimumSeats: 1,
          includedSeats: 0,
          maximumSeats: null,
        },
        "server.domain",
        Math.max(months - includedMonths, 0),
        1,
        currency,
        quote.minorUnitDigits,
        tax,
      ));
    }
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

export function calculateTco(quote: PricingQuote, scenario: UsageScenario): TcoResult {
  return calculateTcoInternal(quote, scenario, null);
}

export function calculateServerTco(
  quote: PricingQuote,
  scenario: UsageScenario,
  serverTerms: ServerTcoTerms,
): TcoResult {
  return calculateTcoInternal(quote, scenario, serverTerms);
}

/**
 * Display-only server comparison derived from approved contract projections.
 * It accepts no reader-entered price, seat, tax, or pricing-basis values.
 */
export function calculateServerZeroInputTable(
  contract: ServerZeroInputContract,
  months: 12 | 24 | 36,
  useCase: ServerUseCase,
): ServerZeroInputTable {
  if (![12, 24, 36].includes(months)) {
    throw new TcoError("server zero-input horizon must be 12, 24, or 36 months");
  }
  if (!["small_site", "corporate_site", "ecommerce"].includes(useCase)) {
    throw new TcoError("server zero-input use case is invalid");
  }
  const useCaseRequirements = contract.useCaseRequirements?.[useCase];
  if (!Array.isArray(useCaseRequirements) || useCaseRequirements.some((item) => typeof item !== "string")) {
    throw new TcoError("server zero-input use-case requirements are invalid");
  }
  const confirmedRequirements = useCaseRequirements.map((item) => item.trim()).filter(Boolean);
  const requirementsConfirmed = confirmedRequirements.length > 0;
  const identities = contract.plans.map((plan) => `${plan.vendorId}\u0000${plan.planId}`);
  if (new Set(identities).size !== identities.length) {
    throw new TcoError("server zero-input plan identities must be unique");
  }

  const pending: ServerZeroInputRow[] = [];
  const calculated: { plan: ServerZeroInputPlan; result: TcoResult }[] = [];
  for (const plan of contract.plans) {
    if (!plan.vendorId.trim() || !plan.planId.trim() || !plan.displayName.trim()) {
      throw new TcoError("server zero-input plan identity cannot be blank");
    }
    if (plan.priceStatus === "unknown") {
      if (plan.quote !== null || plan.serverTerms !== null) {
        throw new TcoError("unknown server plan cannot carry calculable price terms");
      }
      if (!plan.unknownReason?.trim()) {
        throw new TcoError("unknown server plan requires a reason");
      }
      pending.push({
        vendorId: plan.vendorId,
        planId: plan.planId,
        displayName: plan.displayName,
        status: "unconfirmed",
        totalMinor: null,
        currency: null,
        minorUnitDigits: null,
        rank: null,
        differenceFromLowestMinor: null,
        reason: plan.unknownReason.trim(),
        observedOn: plan.observedOn,
        nextReviewOn: plan.nextReviewOn,
      });
      continue;
    }
    if (plan.quote === null || plan.serverTerms === null) {
      throw new TcoError("known server plan requires quote and server terms");
    }
    if (plan.confirmedThroughMonths !== undefined && plan.confirmedThroughMonths !== null) {
      if (![12, 24, 36].includes(plan.confirmedThroughMonths)) {
        throw new TcoError("confirmed server horizon must be 12, 24, or 36 months");
      }
      if (!plan.horizonUnknownReason?.trim()) {
        throw new TcoError("bounded server horizon requires an unknown reason");
      }
      if (months > plan.confirmedThroughMonths) {
        pending.push({
          vendorId: plan.vendorId,
          planId: plan.planId,
          displayName: plan.displayName,
          status: "unconfirmed",
          totalMinor: null,
          currency: plan.quote.currency,
          minorUnitDigits: plan.quote.minorUnitDigits,
          rank: null,
          differenceFromLowestMinor: null,
          reason: plan.horizonUnknownReason.trim(),
          observedOn: plan.observedOn,
          nextReviewOn: plan.nextReviewOn,
        });
        continue;
      }
    } else if (plan.horizonUnknownReason !== undefined && plan.horizonUnknownReason !== null) {
      throw new TcoError("unbounded server horizon cannot carry an unknown reason");
    }
    if (contract.articleReviewStatus !== "approved" || plan.reviewStatus !== "approved") {
      pending.push({
        vendorId: plan.vendorId,
        planId: plan.planId,
        displayName: plan.displayName,
        status: "unconfirmed",
        totalMinor: null,
        currency: null,
        minorUnitDigits: null,
        rank: null,
        differenceFromLowestMinor: null,
        reason: "Human承認前のため計算対象外",
        observedOn: plan.observedOn,
        nextReviewOn: plan.nextReviewOn,
      });
      continue;
    }
    if (!requirementsConfirmed || !plan.eligibleUseCases.includes(useCase)) {
      pending.push({
        vendorId: plan.vendorId,
        planId: plan.planId,
        displayName: plan.displayName,
        status: "ineligible",
        totalMinor: null,
        currency: plan.quote.currency,
        minorUnitDigits: plan.quote.minorUnitDigits,
        rank: null,
        differenceFromLowestMinor: null,
        reason: requirementsConfirmed
          ? "選択した用途区分の承認対象外"
          : "用途の必要条件がHuman確認前のため順位対象外",
        observedOn: plan.observedOn,
        nextReviewOn: plan.nextReviewOn,
      });
      continue;
    }
    calculated.push({
      plan,
      result: calculateServerTco(plan.quote, {
        seats: 1,
        monthlyUsage: Array.from({ length: months }, () => "0"),
        usageUnit: null,
      }, plan.serverTerms),
    });
  }

  const currenciesComparable = new Set(calculated.map(({ result }) => result.currency)).size <= 1;
  const confirmedVendorCount = new Set(calculated.map(({ plan }) => plan.vendorId)).size;
  const rankingEnabled = currenciesComparable && confirmedVendorCount >= 3;
  const ranks = new Map<string, number>();
  const lowestTotalMinor = rankingEnabled
    ? calculated.reduce<bigint | null>(
        (lowest, { result }) => lowest === null || result.totalMinor < lowest ? result.totalMinor : lowest,
        null,
      )
    : null;
  if (rankingEnabled) {
    [...calculated]
      .sort((left, right) => {
        if (left.result.totalMinor < right.result.totalMinor) return -1;
        if (left.result.totalMinor > right.result.totalMinor) return 1;
        return left.plan.displayName.localeCompare(right.plan.displayName, "ja");
      })
      .forEach(({ plan }, index) => ranks.set(`${plan.vendorId}\u0000${plan.planId}`, index + 1));
  }
  const calculatedRows: ServerZeroInputRow[] = calculated.map(({ plan, result }) => ({
    vendorId: plan.vendorId,
    planId: plan.planId,
    displayName: plan.displayName,
    status: rankingEnabled
      ? "ranked"
      : currenciesComparable
        ? "confirmed_unranked"
        : "currency_mismatch",
    totalMinor: result.totalMinor,
    currency: result.currency,
    minorUnitDigits: result.minorUnitDigits,
    rank: ranks.get(`${plan.vendorId}\u0000${plan.planId}`) ?? null,
    differenceFromLowestMinor: rankingEnabled && lowestTotalMinor !== null
      ? result.totalMinor - lowestTotalMinor
      : null,
    reason: rankingEnabled
      ? null
      : currenciesComparable
        ? "確認済みvendorが3社未満のため順位なし"
        : "通貨換算を行わないため順位なし",
    observedOn: plan.observedOn,
    nextReviewOn: plan.nextReviewOn,
  }));
  const rows = new Map(
    [...calculatedRows, ...pending].map((row) => [`${row.vendorId}\u0000${row.planId}`, row]),
  );
  return {
    months,
    useCase,
    comparisonMode: rankingEnabled ? "ranked_comparison" : "confirmed_list",
    confirmedVendorCount,
    rows: identities.map((identity) => rows.get(identity)!),
  };
}

export function formatMinor(value: bigint, currency: string, digits: number): string {
  const scale = 10n ** BigInt(digits);
  const whole = value / scale;
  const fraction = value % scale;
  const rendered = digits === 0 ? whole.toString() : `${whole}.${fraction.toString().padStart(digits, "0")}`;
  return `${currency} ${rendered}`;
}
