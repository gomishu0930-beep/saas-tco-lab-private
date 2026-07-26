# P17 traction / scale boundary matrix

## 1. Purpose and authority boundary

This document is the TCO/QA source of truth for P17 traction and scale
calculations. It defines the exact time grain, formulas, decision precedence,
and counterexamples for a signed sequence of P12-bound observations.

P17 emits only `STOP`, `CONTINUE`, or `SCALE_REVIEW`. `SCALE_REVIEW` is a
non-authoritative recommendation for Human review. It does not authorize
publication, deployment, spend, account or credential creation, release
promotion, partner changes, affiliate-link changes, or production writes.

All quantities are derived at ingestion from a complete P12 authority packet
that has been re-evaluated by `MeasurementIntegrityRuntime` while current. A
caller-supplied count, rate, amount, boolean, or copied report field is not an
authoritative P17 input.

## 2. Time grain and notation

P12 does not produce a calendar-month observation. Each P12 run covers one
exact half-open 30-day interval `[start, end)` whose bounds are midnight in
`Asia/Tokyo`. P17 therefore uses the term **30-day observation window** and
must not relabel it as a calendar month.

For consecutive verified windows `i = 1..n`, define:

- `Q_i`: qualified sessions in window `i`;
- `C_i`: all valid owned outbound clicks in window `i`;
- `S_i(t)`: settled new-acquisition amount attributed to window `i`, in JPY,
  after every verified settlement amendment effective by evaluation time `t`;
- `S_i,p(t)`: the portion of `S_i(t)` attributed to partner `p`;
- `A_i`: eligible routine workflow instances in window `i`;
- `A_i,auto`: eligible routine instances completed without a human touch;
- `H_i`: actual union-deduplicated human minutes in window `i`;
- `J_i`: unique planned logical job runs in window `i`;
- `J_i,ok`: successful unique logical job runs in window `i`;
- `X_i`: deduplicated operational exceptions in window `i`;
- `M_i`: major misstatements in window `i`.

The chain is contiguous only when:

```text
window[1].start = traction_plan.experiment_started_at
window[i].start = window[i - 1].end, for every i > 1
window[i].end - window[i].start = exactly 30 days
```

An overlap, gap, retroactive insertion, alternative snapshot for the same
window, or observation outside the frozen experiment interval invalidates the
chain. A missing window is not a zero-valued observation.

The authoritative experiment age is:

```text
age_days_n = floor((window[n].end - experiment_started_at) / 1 day)
```

It is not the sum of P12 cohort ages and does not advance across an unobserved
gap. Six consecutive windows have `age_days = 180`.

## 3. Cumulative traction metrics

The following metrics use the complete contiguous experiment chain, not only
the latest P12 report:

```text
cumulative_qualified_sessions Q = sum(Q_i)
cumulative_valid_clicks       C = sum(C_i)
cumulative_settled_amount     S = sum(S_i(t))

mature = (C >= 1000) OR (age_days >= 180)

confirmed_EPC = undefined, if C = 0
confirmed_EPC = S / C,       otherwise
```

EPC is a ratio of sums. P17 must not average window-level EPC values, weight
only converting windows, or remove clicks related to pending, rejected,
refunded, charged-back, unmatched, or non-converting outcomes.

For one transaction, the settled numerator is:

```text
settled(tx) = tx.amount
  iff tx.acquisition_class = NEW
  and tx.current_status in {CONFIRMED, PAID}
  and tx has no verified full payout reversal;
settled(tx) = 0 otherwise.
```

`PENDING`, `REJECTED`, `REFUNDED`, `CHARGED_BACK`, `EXISTING`, and `UNKNOWN`
never enter the numerator. P12 already rejects `UNKNOWN` before emitting a
report. `CONFIRMED` and `PAID` are mutually exclusive current-state buckets;
they must not double count one transaction.

The following cumulative fields are monotonic in a valid append-only chain:

- complete-window count;
- chain end and elapsed days;
- qualified-session count;
- valid-outbound-click count.

Cumulative settled revenue, partner revenue, EPC, net payout, and partner share
are **not** monotonic. A verified refund or chargeback can reduce them. A
monotonic-revenue validation would reject correct financial evidence and is
therefore prohibited.

## 4. Latest 30-day scale metrics

P17 evaluates current monthly operating and scale capacity from the latest
complete 30-day window. Older strong windows cannot hide current deterioration.

### 4.1 Observed net operating profit and CTR

```text
latest_revenue = S_n(t)
latest_operating_TCO = labor_cost_n + resource_cost_n
latest_net_operating_profit = latest_revenue - latest_operating_TCO

latest_CTR = undefined, if Q_n = 0
latest_CTR = C_n / Q_n, otherwise
```

The economic goal gate passes at `latest_net_operating_profit >= JPY 200000`. The observed
site-to-merchant CTR gate passes at `latest_CTR >= 0.10`. A causally valid P12
batch cannot contain a valid outbound click without its qualified parent;
`Q_n = 0, C_n > 0` is therefore an invalid packet, not a defined rate.

### 4.2 Conservative target capacity

For cumulative mature EPC `E > 0` and the frozen P12 bear-scenario outbound
rate `r_bear > 0`:

```text
gross_revenue_required = 200000 + latest_operating_TCO
required_clicks_exact = gross_revenue_required / E
required_qualified_sessions_exact = (gross_revenue_required / E) / r_bear

capacity_pass =
  bear_qualified_sessions >= required_qualified_sessions_exact
```

No intermediate value is rounded. Display-only click and session counts are
independently rounded upward. The rounded click count must not feed the exact
session formula. Because the demand model defines
`bear_outbound_clicks = bear_qualified_sessions * r_bear`, an additional
outbound-click capacity comparison is algebraically redundant and may only be
used as an internal consistency assertion.

Observed `latest_net_operating_profit` and modeled bear capacity are separate gates. A
projected `bear.confirmed_revenue` must not be presented as observed revenue.

### 4.3 Partner diversity and concentration

The frozen eligible partner set must exactly match the P17 plan and every P12
run in the chain. Its count is the count of distinct identities, not the count
of rows:

```text
partner_count = count(distinct frozen eligible partner IDs)
partner_count_pass = partner_count >= 3
```

If the policy calls these partners "currently approved", current affiliate
approval evidence must be verified and bound by hash. `report.partner_ids`
alone proves the measured set, not approval status.

For the latest complete window:

```text
partner_share_p = undefined, if S_n(t) = 0
partner_share_p = S_n,p(t) / S_n(t), otherwise

maximum_partner_share = max(partner_share_p)
concentration_pass = maximum_partner_share <= 0.40
```

The partner numerator is derived from the same settled transaction predicate as
EPC. Zero-revenue partners remain in the frozen partner set with share zero.
Zero-converting clicks remain in the EPC and CTR denominators; clicks are not a
dimension of the revenue-share denominator.

### 4.4 Operations and quality

```text
automation_rate = 0,                   if A_n = 0
automation_rate = A_n,auto / A_n,      otherwise

human_minutes = H_n

job_success_rate = undefined,          if J_n = 0
job_success_rate = J_n,ok / J_n,       otherwise
```

The latest-window gates are:

| Gate | Inclusive requirement |
|---|---:|
| Automation | `automation_rate >= 0.80` |
| Human operation | `human_minutes <= 720` |
| Logical-job success | `job_success_rate >= 0.99` |
| Major misstatements | `M_n = 0` |
| Operational exceptions | `X_n <= 24` |
| Fault restoration | canonical eight exercises, each passed and restored |

Human time includes review, supervision, and exception handling. Retry delivery
attempts do not increase the logical-job denominator. A valid P12 plan requires
at least one planned logical job; P17 nevertheless treats a zero denominator as
undefined and unable to pass.

task schedule、execution receipt、匿名化actor-minute区間、resource receipt、labor rateをP17 observationに保持し、
上記集計とTCOを再構築する。署名済みaggregateだけの差替えは無効である。

## 5. Settlement completeness

P12's current signed report establishes a valid current-state snapshot at the
end of its own 30-day cohort. It does not establish that all later confirmation,
payment, refund, or chargeback activity for that cohort has been observed.

The current P12 contract requires:

```text
snapshot_as_of = captured_at = cohort_ended_at
```

It also requires an adjustment to occur no later than `snapshot_as_of`. A later
P12 run cannot carry a late update for the older transaction because that
transaction's attribution falls outside the new run's cohort. Consequently,
six ordinary P12 reports cannot by themselves prove a current day-180 settled
ledger.

Real `SCALE_REVIEW` therefore requires a verified settlement-completeness
artifact for every cohort contributing to cumulative EPC and for the latest
revenue/concentration window. A bare caller boolean is prohibited. Until an
authoritative extension exists, P17 records existing P12 amounts as
`PROVISIONAL_WINDOW_END_SNAPSHOT` and cannot treat them as complete.

The required extension is an append-only signed settlement amendment bound to
the original P12 report and cohort. It must:

- preserve original transaction/cohort/partner/currency/amount commitments;
- permit only valid later status events and full payout adjustments;
- prohibit changes to sessions, clicks, attribution, qualification, and the
  original measurement window;
- bind exact producer, index, TCO/QA, source, rule, and event-set hashes;
- deduplicate by original cohort plus status-event or adjustment-set identity;
- derive partner and total deltas from verified rows rather than supplied
  amounts.

For verified amendment deltas `delta_j`:

```text
S_i(t) = S_i(initial_snapshot) + sum(delta_j effective by t)
S(t)   = sum(S_i(t))
```

A verified amendment chain must also prove `S_i(t) >= 0`. A delta may be
positive or negative. Replaying the exact amendment is an
idempotent no-op and never appends a second financial effect. A conflicting
amendment, partial refund unsupported by the frozen schema, foreign-cohort
adjustment, or unsigned delta fails closed.

An explicitly verified but still provisional settlement state may produce
`CONTINUE` before traction maturity. At maturity, incomplete or unknown
settlement evidence produces `STOP`; pending settlement does not extend the
180-day boundary automatically.

## 6. P12 derivation and provenance requirements

P17 ingestion must receive the complete P12 authority packet:

- `SignedMeasurementRunPlan`;
- demand, cohort, and operations v2 batches;
- the three producer attestations;
- `MeasurementBundleIndex`;
- the P12 policy, trust store, and exact per-run authority pins.

It must call `MeasurementIntegrityRuntime.evaluate(...)` at an ingestion instant
strictly before every relevant expiry and require the newly generated report
and hash to equal the supplied signed report. It then derives P17 values from
the same verified batches. Merely calling
`verify_measurement_integrity_report` and copying reconciliation counts is
insufficient for partner concentration and does not exercise row-level P12
reconciliation.

Currentness is checked at the original ingestion instant. A historical P12
report is expected to expire before a later P17 evaluation; re-running its
ordinary currentness check with the later wall-clock time would make every
longitudinal chain unusable. The P17 observation must therefore bind the exact
ingestion time and a durable, independently verifiable time/append-only anchor.
Later replay verifies the original signature and anchored proof that ingestion
occurred before expiry. Without that anchor, historical currentness is
unproven and real `SCALE_REVIEW` fails closed.

The ingestion/evaluation time is not a caller datetime. A distinct policy-pinned
time-auditor signature binds the exact ledger event revision/head, purpose and
subject hash plus a fresh random request nonce. The ledger obtains that receipt
online inside the append/evaluate method; callers cannot submit a pre-minted
receipt. After the target event is committed to both SQLite and the external
anchor, a second online receipt binds that durable target and its exact expiry;
the resulting finalization is itself chained and anchored. Every persisted
event, including finalization, is monotonic in that attested time. A policy-pinned
1–30 second callback timeout bounds ledger-lock retention. The callback worker
holds a host-global nonblocking OS flock on the non-replaceable filesystem-root
directory inode. At most one live callback worker can therefore exist on the
host across reopened instances, processes and hard-link aliases; retries fail
immediately while it is alive instead of creating unbounded threads. A fork
child closes its inherited worker-lock and ordinary ledger-file-lock descriptors
and resets its in-memory registry. FD open/register and close/discard transitions
are synchronized with the fork before/parent/child handlers, preventing a
long-lived child or an acquire/cleanup race from orphaning either lock after a
parent crash. A sole unfinalized tail may
be resumed after transient failure, including one-ahead external-anchor repair.
If recovery reaches or passes exact expiry, the target is never promoted into
the active projection: an immutable signed `expired` tombstone records the
failure instead. A bare
sequence evaluator has no authentication flag/capability and is structurally
unable to produce `SCALE_REVIEW`; only the ledger method may materialize that
decision after MAC, schema, global event chain and current external anchor pass.

Settlement packets are appended as immutable snapshots before evaluation, not
passed transiently to the authenticated decision path. Latest-per-observation
snapshot hashes, the pre-evaluation ledger revision/head and clock attestation
are committed by the report; the report is then appended and anchored as its
own event. Reopening the same ledger therefore preserves the exact historical
READY/STOP evidence even when a later live evaluation requires refreshed
settlement completeness.

Settlement refresh preserves the accumulated signed event map
`event_id -> exact canonical event hash`, not the expired amendment-envelope
hash. A fresh current envelope may re-sign the exact old event set and add new
events, while omission, mutation, conflict or observed-through regression fails
closed. This avoids requiring a historical short-TTL signature to remain
current for the full 180-day experiment.

The raw highest settlement ordinal controls recency before acceptance is
projected. If that newest target has an `expired` finalization, evaluation must
not fall back to an older accepted amount: the newest target may contain a
refund or chargeback. Settlement evidence remains absent, and therefore cannot
produce scale review, until a later complete snapshot is timely finalized.

The minimized P17 observation preserves commitments to at least:

- P17 plan and predecessor observation;
- P12 policy and trust store;
- P12 report, run plan, run ID, bundle index, all three batches, and all three
  producer attestations;
- property record and property domain;
- measured release/artifact/schema;
- exact partner set;
- exact observation interval and ingestion time;
- settlement state and any amendment chain.

The P12 `MeasurementIntegrityReport` does not expose a measured-release field.
P17 must verify the full run plan and bind an explicit measured release hash. It
may use `fault_target_release_sha256` only if the contract explicitly defines it
as the measured release; name similarity is not sufficient.

Per-partner settled amounts are absent from the signed P12 report. They must be
derived during full batch verification. P17 should persist the minimum signed
concentration result and partner-distribution commitment, not raw transaction
IDs, event IDs, customer-linked hashes, URLs, or non-public per-partner
commission details.

Exact replay of the same ingestion identity and artifact hash may return an
idempotent no-op. It must not add another ledger record. The same run, window,
or idempotency identity with different content is a conflict and fails closed.

## 7. Decision precedence

Decision order is deterministic:

All threshold decisions use exact operands and cross multiplication; displayed
quotients never control a gate. Decimal canonicalization is derived directly
from the sign/digits/exponent tuple and does not call ambient-context
`normalize()`, so two allowed high-precision amounts cannot share a signature
through rounding.

1. **Reject ingestion and preserve/raise STOP.** Invalid type or Decimal,
   signature, role, scope, TTL, exact expiry, hash, coverage, chronology,
   predecessor, property, release, partner set, policy, trust root, settlement
   amendment, or cross-plan binding emits no new canonical observation. A
   production consumer remains stopped.
2. **STOP synthetic or unusable evidence.** An empty production ledger, an
   all-synthetic ledger, any synthetic observation mixed into a production
   chain, a missing 30-day window, or a retroactively rewritten chain cannot
   reach `SCALE_REVIEW`. A local fixture may expose a non-decision diagnostic
   state such as `WAIT`, but the canonical P17 production decision is `STOP`.
3. **STOP hard failures at any age.** Expired rights or affiliate approval,
   fewer than three eligible partners, tampered or unverifiable concentration
   evidence, major misstatement, human-budget breach, automation failure,
   excessive exceptions, failed fault restoration, or a mature-window job
   failure stops evaluation. P12 report verification failure is not converted
   into a self-attested negative observation.
4. **CONTINUE while immature.** If the chain is valid, no hard gate fails, and
   both `C < 1000` and `age_days < 180`, the only positive result is
   `CONTINUE`. Provisional EPC, revenue, or settlement cannot create scale.
5. **STOP mature economics or completeness failures.** At maturity, undefined
   or sub-JPY-60 EPC, incomplete settlement, latest net operating profit below JPY 200000,
   failed bear capacity, CTR below 10%, partner share above 40%, or any current
   operating/quality failure produces `STOP`.
6. **SCALE_REVIEW.** This is possible only when maturity and every provenance,
   settlement, economics, diversity, concentration, capacity, quality,
   automation, job, and human-budget gate pass.

The output must state that its authority effect is `none` and that its permitted
use is Human scale-review input only.

## 8. Exact boundary matrix

Unless stated otherwise, every non-tested gate is valid and passing.

| ID | Input | Expected result |
|---|---|---|
| M-01 | `C=999`, `age_days=179` | Immature; `CONTINUE` |
| M-02 | `C=1000`, `age_days=179` | Mature; eligible for `SCALE_REVIEW` |
| M-03 | `C=999`, `age_days=180` | Mature; eligible for `SCALE_REVIEW` |
| M-04 | `C=0`, `age_days=180` | Mature, EPC undefined; `STOP` |
| E-01 | Mature EPC `59.99` | `STOP` |
| E-02 | Mature EPC `60` | EPC gate passes |
| E-03 | Add pending or rejected amount only | EPC is unchanged |
| E-04 | Add a valid non-converting click only | EPC cannot increase |
| C-01 | Latest CTR `0.0999` | `STOP` |
| C-02 | Latest CTR `0.10` | CTR gate passes |
| C-03 | `Q_n=0`, `C_n=0` | CTR undefined; `STOP` at maturity |
| C-04 | `Q_n=0`, `C_n>0` | Invalid causal P12 packet; reject |
| R-01 | Latest net operating profit `199999.99` | `STOP` |
| R-02 | Latest net operating profit `200000` | Economic goal gate passes |
| R-02a | Settled revenue `200000`, operating TCO `60000` | Net profit `140000`; `STOP` |
| R-03 | Bear qualified demand equals exact required sessions | Capacity gate passes |
| R-04 | Bear qualified demand is below exact requirement by the smallest represented Decimal | `STOP` |
| P-01 | Two distinct eligible partners | `STOP` |
| P-02 | Three distinct eligible partners | Partner-count gate passes |
| P-03 | Maximum latest partner share `0.40` | Concentration gate passes |
| P-04 | Maximum latest partner share `0.40000001` | `STOP` |
| P-05 | Latest settled total is zero | Share undefined; `STOP` at maturity |
| A-01 | Automation rate `0.7999` | `STOP` |
| A-02 | Automation rate `0.80` | Automation gate passes |
| A-03 | `A_n=0`, `A_n,auto=0` | Derived rate is zero; `STOP` |
| H-01 | Human minutes `720` | Human-budget gate passes |
| H-02 | Human minutes `721` | `STOP` |
| J-01 | 99 successful logical runs of 100 | Job gate passes |
| J-02 | 98 successful logical runs of 100 | `STOP` |
| J-03 | Zero logical runs | Undefined; `STOP` |
| J-04 | One logical run with multiple delivery attempts | Denominator remains one |
| Q-01 | Major misstatements `0` | Quality gate passes |
| Q-02 | Major misstatements `1` | `STOP` |
| Q-03 | Exceptions `24` | Exception gate passes |
| Q-04 | Exceptions `25` | `STOP` |
| F-01 | Canonical eight fault exercises pass and restore | Fault gate passes |
| F-02 | Missing, duplicate, failed, stale-definition, or restore-mismatched fault | P12 emits no report; reject |
| T-01 | Verification instant is one unit before expiry | May pass if all other checks pass |
| T-02 | Verification instant equals expiry | Expired under half-open currentness; reject |
| T-03 | Exact six consecutive 30-day windows | `age_days=180` |
| T-04 | Gap between windows | `STOP`; do not zero-fill or advance observed age |
| T-05 | Overlap between windows | Reject conflicting chronology |
| T-06 | Exact duplicate ingestion | Idempotent no-op; no new row or count |
| T-07 | Same run/window identity with different hash | Conflict; reject and preserve STOP |
| T-08 | Wrong predecessor or retroactive insertion | Chain rewrite; reject |
| T-09 | Cross-plan/property/release/partner/index splice | Reject |
| S-01 | Verified later confirmation produces positive delta | Settled amount and EPC may increase |
| S-02 | Verified full refund/chargeback produces negative delta | Settled amount and EPC may decrease; chain remains valid |
| S-03 | Exact amendment replay | Idempotent no-op; no second financial effect |
| S-04 | Unsigned, partial, or foreign-cohort adjustment | Reject |
| S-05 | Mature chain with unproven settlement completeness | `STOP` |
| V-01 | Empty production ledger | Default `STOP` |
| V-02 | All-synthetic ledger | `STOP`; never `SCALE_REVIEW` |
| V-03 | Synthetic observation mixed into real chain | `STOP` |
| V-04 | Valid real evidence, immature, no hard failure | `CONTINUE` |
| V-05 | Valid real evidence, mature, all gates exact-pass | `SCALE_REVIEW` only; authority effect `none` |

## 9. Property and fault assertions

In addition to example boundaries, tests must assert:

- increasing one non-negative settled amount cannot decrease EPC unless a
  separate verified reversal is added;
- increasing cumulative valid clicks without increasing settlement cannot
  increase EPC;
- pending and rejected amounts are irrelevant to confirmed EPC;
- required traffic cannot increase when mature EPC increases;
- no ordering or grouping of windows changes a ratio-of-sums result;
- no row ordering changes a canonical observation or ledger hash;
- cumulative clicks, qualified sessions, window count, and elapsed time never
  decrease in an accepted chain;
- verified financial adjustments may decrease cumulative revenue and EPC;
- a latest-window failure cannot be rescued by an older passing window;
- three rows for one partner count as one partner;
- no conversion-only click subset may replace all valid outbound clicks;
- binary floats, NaN, infinity, currency conversion, or intermediate rounding
  are rejected;
- a copied P12 count without full runtime evaluation cannot create an
  observation;
- report-level reconciliation alone cannot establish partner concentration;
- P16 readiness or any P17 recommendation cannot be reinterpreted as external
  execution authority.

## 10. Reuse boundary for `economics.py`

P17 should reuse the following deterministic behavior where its inputs have
already been derived from verified P12/P17 evidence:

- Decimal validation and rejection of floats/non-finite values;
- inclusive `1000 clicks OR 180 days` maturity semantics;
- `(confirmed + paid) / all valid clicks` EPC arithmetic after P12 has removed
  ineligible acquisitions and reversals;
- exact target-traffic reversal and independent ceiling display values;
- bear/base/bull demand projection ordering;
- inclusive thresholds for JPY 60 EPC, 12 human hours, 80% automation, 99% job
  success, zero major misstatements, and 24 exceptions;
- hard-failure precedence before `CONTINUE`.

P17 must not call `evaluate_go_stop` as its authoritative final evaluator. The
following exact mismatches must be resolved at the P17 boundary:

| Existing economics behavior | P17 requirement |
|---|---|
| One `AffiliateCohort` supplies clicks and age | Sum a verified contiguous P12 observation chain and derive age from chain bounds |
| Commission buckets are accepted inputs | Derive NEW/current/settled/reversal state from the verified P12 batch and amendment chain |
| `approved_affiliate_ids` and `rights_approved` are caller inputs | Bind current signed rights and affiliate evidence; no self-attested IDs/boolean |
| Human, automation, jobs, errors, and exceptions are caller aggregates | Retain task/activity/resource receipts and derive latest-window values while binding the verified P12 operations batch |
| Automation receives a precomputed rate | Derive numerator and denominator; define `0/0` as zero and fail |
| Result can be `GO` | Positive P17 result is only non-authoritative `SCALE_REVIEW` |
| No observed CTR gate | Require latest verified `C_n/Q_n >= 0.10` |
| No observed JPY 200000 profit gate | Require latest verified settled revenue minus receipt-backed operating TCO `>= 200000` separately from modeled capacity |
| Affiliate count only, no concentration | Require exact frozen partner set and latest settled share `<= 0.40` |
| No chronology, provenance, synthetic, or expiry model | Verify full P12 packet and append-only P17 chain; synthetic and splice failures stop |
| Paid is terminal and post-payment adjustment is outside the pure calculator | Apply verified settlement amendments before EPC/revenue/share and do not require revenue monotonicity |
| `bear.confirmed_revenue` is a projection | Never label it as observed latest revenue |
| `job_success_rate=None` only follows a supplied zero total | Preserve undefined/fail semantics even though valid P12 plans require at least one logical job |

The safe reuse pattern is to call small pure functions such as
`calculate_required_traffic`, or to reproduce their exact Decimal equations in
a P17-specific pure evaluator. Adapting verified P17 evidence into
`GoStopInputs` and accepting its `GO` would silently omit required P17 gates and
is prohibited.
