from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from saas_preflight.tco import (
    BillingPeriod,
    PriceBasis,
    PricingQuote,
    RecurringCharge,
    TaxPolicy,
    TaxTreatment,
    UsageCharge,
    UsageScenario,
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
        result = calculate_tco(
            quote,
            UsageScenario(
                seats=raw_scenario["seats"],
                monthly_usage=tuple(Decimal(value) for value in raw_scenario["monthlyUsage"]),
                usage_unit=raw_scenario["usageUnit"],
            ),
        )
        assert str(result.listed_minor) == case["expected"]["listedMinor"], case["name"]
        assert str(result.added_tax_minor) == case["expected"]["addedTaxMinor"], case["name"]
        assert str(result.total_minor) == case["expected"]["totalMinor"], case["name"]
