# SaaS affiliate measurement model

> The four-bucket cohort below is the pure economics adapter, not an
> authoritative intake. P12 derives those buckets from a signed exclusive
> current-state ledger. `paid` remains terminal at the transaction-status layer;
> post-payment full refund/chargeback is an append-only financial adjustment.
> See `P12_MEASUREMENT_INTEGRITY.md`.

## 1. Scope and evidence boundary

This document defines calculations; it does not assert that Japanese search
demand, affiliate availability, or EPC currently meets a threshold. Every input
must arrive from a versioned evidence artifact. Unknown values stay unknown and
must not be replaced with AI estimates, industry averages, or values copied from
another currency or market.

The economic unit is one calendar month's qualified Japanese demand and one
affiliate click cohort. The default decision target is JPY 200,000 per month.
Currency conversion is outside the model and is rejected by the evaluator.

## 2. Search-demand funnel

The model accepts only a deduplicated monthly search volume. Deduplication must
happen before this calculation and its method, source date, country/language,
keyword universe, and overlapping query clusters must be retained in the input
artifact. Summing overlapping keyword-tool rows and marking the result as
deduplicated is not permitted.

For each scenario:

```text
organic sessions
  = deduplicated search volume × organic visibility × rank CTR

qualified sessions
  = organic sessions × qualified rate

outbound clicks
  = qualified sessions × outbound click rate
```

All rates are `Decimal` fractions from 0 through 1. No intermediate value is
rounded. The definitions are:

- **Organic visibility:** share of the deduplicated search universe for which an
  eligible result is visible. It is not rank CTR.
- **Rank CTR:** visits to the owned comparison property per visible search.
- **Qualified rate:** share of those visits meeting the versioned qualification
  rule, such as visiting an eligible product-comparison or TCO route. The event
  rule must not be changed during a cohort without a metric version change.
- **Outbound click rate:** valid affiliate outbound clicks per qualified session.
  Bot, internal, duplicate, and broken-link events are excluded by a documented
  filter before this rate is produced.

Modeled demand is capacity evidence, not observed traffic. Observed Search
Console, analytics, and affiliate values must remain separately labeled.

## 3. Bear, base, and bull scenarios

Each scenario supplies its own five inputs. The calculator requires projected
qualified sessions and outbound clicks to satisfy:

```text
bear <= base <= bull
```

A mislabeled set is invalid rather than silently reordered. The bear scenario is
the production capacity gate. Base and bull are planning sensitivity only and
cannot rescue a failing bear scenario.

Scenario values are not constants in source code. Their evidence version and
date belong in the caller's artifact. This repository deliberately contains no
claimed Japanese demand volume or claimed affiliate conversion rate.

## 4. Affiliate cohort and commission statuses

One `AffiliateCohort` contains:

- currency;
- all valid outbound clicks in the cohort denominator;
- elapsed age in whole days;
- four mutually exclusive commission amount buckets at the snapshot time:
  `pending`, `rejected`, `confirmed`, and `paid`.

A commission that advances from confirmed to paid moves buckets; it must not
remain in both. Paid is a terminal settled status, so confirmed EPC uses both
currently confirmed and currently paid amounts:

```text
confirmed EPC
  = (confirmed commission + paid commission) / all valid cohort clicks
```

Pending and rejected amounts never enter the numerator. Their clicks remain in
the denominator. Removing non-converting, rejected, or pending clicks from the
denominator would introduce survivorship bias. A zero-click cohort has no EPC;
the calculator does not manufacture zero or infinity.

The affiliate-import artifact must preserve partner, click-cohort start/end,
snapshot time, currency, status mapping version, duplicate-transaction rule, and
the source report checksum. Combining currencies is prohibited.

## 5. Revenue target reversal

For target revenue `R`, mature confirmed EPC `E`, and outbound click rate `C`:

```text
required confirmed outbound clicks = R / E
required qualified sessions         = (R / E) / C
```

Exact Decimal expectations are retained. Displayed operational counts use
ceiling rounding independently from the exact results. The rounded click count
is not cascaded into the session formula.

For the threshold values only—not as an empirical forecast—JPY 200,000 at
confirmed EPC JPY 60 requires exactly `200000 / 60` clicks, displayed as 3,334.
If outbound click rate were explicitly evidenced as 0.10, the exact qualified
session requirement would be `200000 / 60 / 0.10`, displayed as 33,334.

Zero revenue target, zero EPC, and zero outbound rate are invalid inputs to this
reverse calculation because they do not describe the approved business test.

## 6. Traction maturity

The default cohort becomes mature when either condition is met:

```text
valid clicks >= 1,000 OR age days >= 180
```

Before both thresholds are missed, mature-EPC and revenue-capacity checks are
`WAIT`, not `PASS`. A provisional high EPC cannot create GO. At day 180 a cohort
with no valid clicks is mature by time but fails because EPC is undefined.

Pending status does not pause the clock or enter EPC. If affiliate settlement
latency makes the 180-day snapshot unusable, the decision is STOP/exception and
requires a new Human-approved criterion version; the evaluator does not extend
the period automatically.

## 7. GO, CONTINUE, and STOP

Default criteria are:

| Gate | Default |
|---|---:|
| Monthly confirmed revenue target | JPY 200,000 |
| Distinct currently approved affiliate partners | at least 3 |
| Mature confirmed EPC | at least JPY 60 per valid click |
| Traction maturity | 1,000 valid clicks or 180 days |
| Human operation | at most 12 hours per month |
| Automated routine-operation rate | at least 80% |
| Major misstatements | 0 |
| Shadow observation | at least 30 complete days |
| Job success rate | at least 99% after shadow maturity |
| Operational exceptions | at most 24 per measurement month |
| Rollback fault test | passed |
| Rights | explicitly approved |
| Demand capacity | bear scenario meets the target |

Decision precedence is deterministic:

1. Invalid inputs raise an error and no decision is published.
2. Any hard failure—rights, partner count, errors, human budget, automation,
   positive bear demand, excessive exceptions, failed rollback, or a mature
   job-success rate below 99%—returns `STOP`.
3. If hard gates pass but the 30-day shadow or traction cohort is immature,
   the corresponding checks remain
   `WAIT`, producing `CONTINUE`.
4. Once mature, EPC below threshold, undefined EPC, or bear capacity below the
   exact required qualified sessions returns `STOP`.
5. `GO` requires every check to pass. It is a calculation recommendation, not a
   Human approval to publish, spend, change affiliate links, or write production.

Distinct affiliate IDs are counted once. Three rows naming the same partner do
not satisfy the three-partner gate.

## 8. Operational measurements

- **Human hours/month:** sum of actual human activity-ledger durations for the
  scoped operation, including reviews and exception handling. Agent runtime is
  excluded; time spent supervising agents is included.
- **Automation rate:** eligible routine workflow instances completed without a
  human touch divided by all eligible routine workflow instances. Human-only
  approval gates are reported separately and the eligible set/version must be
  fixed before measurement.
- **Major misstatement:** a price, limit, TCO, affiliate status, or ranking error
  classified major by the versioned QA policy. One unresolved event fails GO.
- **Shadow observation days:** complete 24-hour intervals from the recorded
  observation start through the artifact capture time. A caller-supplied day
  count is not accepted.
- **Job success rate:** succeeded scheduled jobs divided by every scheduled job
  in the same observation window. Zero total jobs is undefined and cannot pass
  after 30 days.
- **Operational exceptions:** all deduplicated exceptions detected in the
  measurement month, including resolved items. Resolution does not remove an
  incident from the denominator.
- **Rollback test:** a versioned fault-injection result with `not_run`, `passed`,
  or `failed`; only `passed` satisfies GO.
- **Approved affiliate:** a distinct partner whose current approval, eligible
  property, territory, destination, and terms are recorded and unexpired. An
  application, public affiliate page, or pending review is not approval.

All observed inputs use an `as_of` time even though this pure calculation module
does not own timestamps. Expired or mismatched artifacts must be blocked by the
release/evidence layer before calling the evaluator.

## 9. QA invariants and counterexamples

Required automated properties are:

- demand never decreases when one non-negative funnel input increases and the
  others remain fixed;
- required traffic never increases when confirmed EPC increases;
- confirmed EPC never decreases when settled commission increases;
- pending and rejected amounts never change confirmed EPC;
- the 1,000-click and 180-day boundaries both mature the cohort;
- Decimal values remain unrounded until an explicitly documented ceiling.
- 99/100 jobs passes while 98/100 fails; zero jobs never passes a mature window;
- 24 monthly exceptions passes while 25 fails;
- `not_run` rollback waits and `failed` rollback stops.

Regression counterexamples include a large pending balance falsely creating GO,
duplicate affiliate IDs falsely satisfying three partners, a strong base case
hiding a failed bear case, and period-end aggregate rounding replacing exact
Decimal arithmetic.
