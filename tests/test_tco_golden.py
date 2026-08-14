from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from saas_preflight.tco import (
    BillingPeriod,
    PriceBasis,
    PricingQuote,
    RecurringCharge,
    ServerTcoTerms,
    TaxPolicy,
    TaxTreatment,
    UsageCharge,
    UsageScenario,
    calculate_server_tco,
    calculate_tco,
)


CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "tco_golden.json").read_text(encoding="utf-8")
)


def _recurring(value: dict[str, object]) -> RecurringCharge:
    return RecurringCharge(
        name=str(value["name"]),
        amount=Decimal(str(value["amount"])),
        currency=str(value["currency"]),
        billing_period=BillingPeriod(str(value["billingPeriod"])),
        price_basis=PriceBasis(str(value["priceBasis"])),
        minimum_seats=int(value["minimumSeats"]),
        included_seats=int(value["includedSeats"]),
        maximum_seats=(None if value["maximumSeats"] is None else int(value["maximumSeats"])),
    )


def test_shared_golden_cases_match_python_canonical() -> None:
    for case in CASES:
        raw_quote = case["quote"]
        raw_usage = raw_quote["usage"]
        quote = PricingQuote(
            currency=raw_quote["currency"],
            minor_unit_digits=raw_quote["minorUnitDigits"],
            minimum_commitment_months=raw_quote["minimumCommitmentMonths"],
            base=_recurring(raw_quote["base"]),
            addons=tuple(_recurring(item) for item in raw_quote["addons"]),
            usage=(
                None
                if raw_usage is None
                else UsageCharge(
                    name=raw_usage["name"],
                    included_quantity=Decimal(raw_usage["includedQuantity"]),
                    included_basis=PriceBasis(raw_usage["includedBasis"]),
                    overage_unit_price=(None if raw_usage["overageUnitPrice"] is None else Decimal(raw_usage["overageUnitPrice"])),
                    currency=raw_usage["currency"],
                    unit=raw_usage["unit"],
                    billing_period=BillingPeriod(raw_usage["billingPeriod"]),
                )
            ),
            tax=TaxPolicy(
                TaxTreatment(raw_quote["tax"]["treatment"]),
                None if raw_quote["tax"]["rate"] is None else Decimal(raw_quote["tax"]["rate"]),
            ),
        )
        raw_scenario = case["scenario"]
        scenario = UsageScenario(
            seats=raw_scenario["seats"],
            monthly_usage=tuple(
                Decimal(value) for value in raw_scenario["monthlyUsage"]
            ),
            usage_unit=raw_scenario["usageUnit"],
        )
        raw_server_terms = case.get("serverTerms")
        result = (
            calculate_tco(quote, scenario)
            if raw_server_terms is None
            else calculate_server_tco(
                quote,
                scenario,
                ServerTcoTerms(
                    initial_fee=(
                        None
                        if raw_server_terms["initialFee"] is None
                        else Decimal(raw_server_terms["initialFee"])
                    ),
                    renewal_fee=(
                        None
                        if raw_server_terms["renewalFee"] is None
                        else Decimal(raw_server_terms["renewalFee"])
                    ),
                    renewal_due_month=raw_server_terms["renewalDueMonth"],
                    campaign_price=(
                        None
                        if raw_server_terms["campaignPrice"] is None
                        else Decimal(raw_server_terms["campaignPrice"])
                    ),
                    campaign_period_months=raw_server_terms[
                        "campaignPeriodMonths"
                    ],
                    domain_price=(
                        None
                        if raw_server_terms["domainPrice"] is None
                        else Decimal(raw_server_terms["domainPrice"])
                    ),
                    domain_billing_period=(
                        None
                        if raw_server_terms["domainBillingPeriod"] is None
                        else BillingPeriod(raw_server_terms["domainBillingPeriod"])
                    ),
                    domain_included_months=raw_server_terms[
                        "domainIncludedMonths"
                    ],
                ),
            )
        )
        assert str(result.listed_minor) == case["expected"]["listedMinor"], case["name"]
        assert str(result.added_tax_minor) == case["expected"]["addedTaxMinor"], case["name"]
        assert str(result.total_minor) == case["expected"]["totalMinor"], case["name"]
