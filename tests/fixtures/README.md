# TCO fixture conventions

The executable fixtures live in `tests/test_tco.py`; this file records the
economic assumptions that must stay visible during review.

| Case | Monthly quote | Annual quote | 12-month expectation |
|---|---:|---:|---:|
| JPY flat, no tax | JPY 1,000 | JPY 12,000 | JPY 12,000 |
| USD exact cents, no tax | USD 10.00 | USD 120.00 | USD 120.00 |

Boundary fixtures cover:

- requested seats below a minimum and seats included in the recurring fee;
- requested seats above a declared maximum;
- usage exactly at and one unit above an included allowance;
- an unknown overage rate when the allowance is exceeded;
- required add-ons, explicitly selected optional add-ons, and unknown add-on
  selections, in addition to flat/per-seat pricing;
- tax included, excluded, not applicable, unknown, and excluded without a rate;
- annual prices with a non-divisible horizon, which fail instead of being
  prorated implicitly;
- monthly billing with a 12-month commitment, and a commitment longer than the
  analysis horizon;
- quote/add-on currency mismatch and usage-unit mismatch;
- per-invoice `ROUND_HALF_UP` behavior for prices and excluded tax.

All expected totals are integer minor units. No fixture performs currency
conversion or infers a tax rate.
