# P3 — Economics and QA handoff

## Scope and ownership

Implemented the deterministic economics boundary only:

- `src/saas_preflight/economics.py`
- `tests/test_economics.py`
- `docs/MEASUREMENT_MODEL.md`

No network search, production metric, Japanese demand volume, affiliate approval,
or empirical conversion rate was added. Existing contract/TCO/storage and other
roles' files were not edited.

## Public calculation interface

- `calculate_demand(DemandAssumptions) -> DemandProjection`
- `calculate_confirmed_epc(AffiliateCohort) -> Decimal`
- `calculate_required_traffic(target, confirmed_epc, outbound_rate)
  -> TrafficRequirement`
- `traction_mature(AffiliateCohort, GateCriteria) -> bool`
- `project_scenarios(ScenarioSet, confirmed_epc) -> ScenarioProjectionSet`
- `evaluate_go_stop(GoStopInputs, GateCriteria) -> GoStopEvaluation`

`GoStopEvaluation` returns `GO`, `CONTINUE`, or `STOP`, every individual gate,
current confirmed EPC if defined, target traffic requirements when mature, and
bear/base/bull projections. It has no external write capability.

## Calculation decisions

1. Demand uses only an explicitly deduplicated monthly volume:
   `volume × visibility × rank CTR × qualified rate`.
2. Affiliate outbound clicks add `× outbound click rate`. No intermediate
   rounding occurs.
3. Confirmed EPC uses `(confirmed + paid) / all valid cohort clicks`.
   Pending/rejected amounts are separate, excluded from the numerator, and their
   clicks remain in the denominator.
4. Paid and confirmed are mutually exclusive current-status buckets. Preventing
   transaction duplication belongs to the versioned import artifact; aggregate
   amounts alone cannot prove exclusivity.
5. Required confirmed clicks are `target / EPC`; required qualified sessions are
   `(target / EPC) / outbound rate`. Exact Decimal and independently ceiling-
   rounded operational counts are both retained.
6. Cohort maturity is `valid clicks >= 1,000 OR age >= 180 days` by default.
7. Bear/base/bull outputs must be monotonic. Bear capacity alone controls GO;
   stronger scenarios are sensitivity information.
8. Default gates encode the requested decision criteria: JPY 200,000/month,
   three distinct approved partners, mature confirmed EPC >= JPY 60, human work
   <=12 hours/month, automation >=80%, zero major misstatements, and approved
   rights.
9. Before maturity, EPC and capacity are `WAIT`; provisional EPC cannot create
   GO. A separate hard failure still returns STOP.
10. Currency conversion, binary float input, non-deduplicated volume, invalid
    ratios, zero reverse-calculation denominators, and undefined mature EPC fail
    closed.

The threshold example is deterministic: JPY 200,000 / JPY 60 gives exact
3,333.33… confirmed clicks and an operational ceiling of 3,334. At a separately
evidenced outbound rate of 0.10, exact required qualified sessions are
33,333.33… and the ceiling is 33,334. This is arithmetic, not a claim that the
rate exists.

## Independent counterexamples

The following plausible but incorrect implementations were tested and rejected:

- **Pending-revenue inflation:** JPY 1,000,000 pending with zero settled revenue
  produces confirmed EPC 0 and STOP, not GO.
- **Partner row inflation:** `partner-a, partner-b, partner-b` counts as two
  distinct approved partners and fails the three-partner gate.
- **Base-case rescue:** a base/bull case above target does not override a bear
  capacity shortfall.
- **Premature success:** EPC 60 at 999 clicks and day 179 produces CONTINUE, not
  GO.
- **Time maturity without evidence:** day 180 with zero clicks is mature by time
  but stops because confirmed EPC is undefined.
- **Status survivorship bias:** changing pending/rejected amounts cannot change
  confirmed EPC; all valid clicks remain in its denominator.

## Verification

- `uv run pytest tests/test_economics.py -q`: **36 passed**.
- `uv run pytest -q`: **99 passed**.
- Hypothesis properties: demand monotonicity, required-traffic inverse EPC
  monotonicity, pending/rejected EPC invariance, settled-revenue EPC
  monotonicity.
- `python3 -m py_compile src/saas_preflight/economics.py
  tests/test_economics.py`: pass.
- Major-misstatement regressions in deterministic fixtures: 0.
- External facts or measured traction records introduced: 0.

Artifact SHA-256:

- economics module:
  `3462530834395790b73ddba6ef14bba26c7cf9e3c70f339ce9a8983347216de7`
- tests:
  `0bd7e7d2632143d60636a4f529e369153f883cca2e0e2483c47280b2faebd347`
- measurement model:
  `2c6fbbac88929895e37a5be3bf3e4c6bbcb74b78697a985c10a2d1e5d4ec8095`

## Handoff and release recommendation

**Code recommendation: CONDITIONAL for local integration.** The implementation
and synthetic regression suite pass. Business GO is not established because no
production `GoStopInputs` artifact is present.

Before a real evaluation, Integration/Release must provide versioned inputs for:

- currently approved, distinct affiliate partner IDs;
- field-level rights approval;
- documented, deduplicated Japanese search volume and all scenario rates;
- one currency-consistent click cohort with mutually exclusive commission
  statuses and import checksum;
- actual human activity hours, routine-operation automation denominator, and
  major-misstatement count.

Missing, expired, or contradictory inputs are STOP. A calculated GO remains a
recommendation and does not authorize publication, spending, credentials,
affiliate-link changes, or production writes.
