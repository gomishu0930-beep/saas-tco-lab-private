# Phase 3 measurement intake — acceptance and refutation tests

> These tests retain the unsigned aggregate diagnostic contract. The P12
> production-authority additions and stricter refund/chargeback, coverage,
> signature, and exact-fault rules are authoritative in
> `P12_ACCEPTANCE_TESTS.md`.

## 1. Purpose

This is the TCO/QA acceptance contract for converting synthetic raw summaries
into versioned `DemandEvidence`, `CohortEvidence`, and `OperationsEvidence`.
It defines test inputs and expected results; it contains no observed demand,
affiliate performance, or production operating result.

An implementation passes only when every mandatory test below is automated.
When the expected result is **REJECT**, no partial Evidence, readiness dossier,
or cached aggregate may be emitted. A rejected batch cannot be converted to zero
or silently quarantined while the remaining rows produce GO.

## 2. Common fixture conventions

- Monetary, volume, and rate values enter JSON as decimal strings and are parsed
  as `Decimal`. Binary floats are rejected.
- `H("label")` below means the 64-character lowercase SHA-256 of a synthetic
  label. Tests materialize the hash; raw click IDs, transaction IDs, keywords,
  email addresses, URLs, and affiliate credentials never enter fixtures.
- The common reporting interval is the half-open Asia/Tokyo interval
  `[2026-06-01T00:00:00+09:00, 2026-07-01T00:00:00+09:00)`.
- Unless a test says otherwise, `as_of` is `2026-07-15T00:00:00+09:00`, evidence
  expires at `2026-08-01T00:00:00+09:00`, and all timestamps are timezone-aware.
- IDs identify logical entities, not delivery attempts. Reprocessing the same
  complete batch is idempotent. Duplicate entity IDs inside one strict summary
  batch are rejected even when their rows are identical; two payloads with the
  same ID but different material content are also rejected as conflicts.
- Output ordering and SHA-256 are canonical. Permuting input rows must not change
  values, evidence version, or canonical hash.

Expected outcomes use three levels:

- **EMIT:** create one immutable, versioned Evidence artifact with the exact
  expected values.
- **REJECT:** validation error and no artifact.
- **GATE:** artifact can exist, but the stated readiness gate must PASS, WAIT, or
  STOP as specified.

## 3. Demand deduplication and cluster overlap

`DemandSummaryBatch` must retain country `JP`, language `ja`, source checksum,
deduplication-method SHA-256, freshness, unique hash-only cluster IDs, each
cluster's bear/base/bull Decimal volume, and one four-rate funnel summary per
scenario. The pipeline may validate and aggregate this evidence; it must not
invent semantic overlap from cluster IDs or add overlapping keyword-tool rows.

### D-01 — duplicate cluster ID inside a batch is rejected

Input:

```text
cluster 1: cluster_id_sha256=H("pricing"), bear/base/bull="100/120/150"
cluster 2: cluster_id_sha256=H("pricing"), bear/base/bull="100/120/150"
```

Expected: **REJECT**. Strict summary duplication is not batch replay. Replaying
the complete one-cluster batch in a separate invocation must remain idempotent.

### D-02 — conflicting duplicate delivery is rejected

Input: D-01, except cluster 2 has bear volume `"110"` with the same cluster ID.

Expected: **REJECT**. Do not select the larger, later, or first value.

### D-03 — aggregate cluster IDs cannot prove absence of overlap

Input:

```text
cluster=H("pricing"), bear volume="300"
cluster=H("compare"), bear volume="500"
deduplication-method SHA-256 present, overlap/ownership receipt absent
```

Synthetic ground truth declares that `"200"` belongs to both cluster summaries.
Expected: the local builder must not claim it detected or removed the overlap.
The resulting demand is **GATE STOP / unverified deduplication** unless the
upstream evidence receipt proves canonical ownership or a union calculation.
Merely having distinct cluster hashes and a method-document hash does not prove
the method was executed. Summing to `"800"` and labeling it locally verified is
prohibited.

### D-04 — canonical overlap is counted globally once

This is an upstream-dedup receipt acceptance test. Input membership is:

```text
pricing: q1="100", q2="200"
compare: q2="200", q3="300"
versioned canonical owner: q2 -> pricing
```

Expected upstream summary: global `"600"`, pricing `"300"`, compare `"300"`.
`DemandSummaryBatch` may then emit these non-overlapping cluster totals. If the
intake schema carries only aggregate clusters, this receipt and its SHA-256 must
remain an upstream prerequisite; the builder cannot reconstruct it.

### D-05 — semantic overlap uses evidenced group volume, not member sum

Input:

```text
overlap group=H("g1"), member q4 volume="500", member q5 volume="400"
evidenced deduplicated group volume="600", canonical cluster="alternatives"
```

Expected upstream cluster summary `alternatives="600"`, not `"900"`. If the
group-level value or execution receipt is missing, expected **GATE STOP**; the
aggregate intake cannot infer search-audience intersection.

### D-06 — market, period, or unit mixing is rejected

Input: one row for `ja-JP / 2026-06 / monthly` and another for either `en-US`,
`2026-05`, or `daily`, in one evidence batch.

Expected: **REJECT**. No locale conversion, period averaging, or daily-to-monthly
extrapolation is permitted.

### D-07 — explicit deduplication assertion is mandatory

Input: otherwise valid cluster volume `"1000"`, but
`deduplication_method_sha256` is absent, malformed, or not the approved method
receipt for the source batch.

Expected: **REJECT** before economics. It must not become a zero-volume STOP
artifact or be relabeled as deduplicated.

### D-08 — Decimal funnel arithmetic remains exact

Input:

```text
sum of non-overlapping cluster bear volumes="1000"
bear DemandFunnelSummary has a unique summary_id_sha256
organic visibility="0.50"
rank CTR="0.20"
qualified rate="0.50"
outbound click rate="0.10"
```

Expected:

```text
organic sessions="100"
qualified sessions="50"
outbound clicks="5"
```

No intermediate integer rounding is accepted.

### D-09 — bear/base/bull cannot be silently reordered

Input projections with qualified sessions `bear="100"`, `base="90"`,
`bull="120"`.

Expected: **REJECT**, not a sorted output. Scenario labels are evidence, and bear
must remain the capacity gate.

### D-10 — row-order and batch-replay property

For any valid synthetic demand batch, shuffle all rows and replay the batch
twice.

Expected: the three scenario values and artifact hash are identical on every
run. Materially changing one deduplicated volume changes the artifact hash.

## 4. Commission status movement and confirmed EPC

`CohortSummaryBatch` is a current snapshot keyed by hash-only commission ID. Each
commission ID may appear exactly once per batch and contributes to one bucket:
pending, rejected, confirmed, or paid. `confirmed` and `paid` are settled but
mutually exclusive current statuses. Status movement is tested across immutable
snapshot versions; old and new snapshots must never be summed.

### C-01 — pending moves to confirmed; it is not copied

Input for `commission_id_sha256=H("tx1")`, amount `"60000"`, currency JPY:

```text
snapshot v1 captured June 10: one row with status=pending
snapshot v2 captured July 10: one row with status=confirmed
```

Expected when v2 is selected at the common `as_of`: **EMIT** pending `"0"`,
confirmed `"60000"`, paid `"0"`. Settled numerator is `"60000"`, not
`"120000"`; v1 remains immutable history but is not added to v2.

### C-02 — confirmed moves to paid without double counting

Input for one JPY `"60000"` commission: v1 current status confirmed, v2 current
status paid.

Expected: confirmed `"0"`, paid `"60000"`; settled numerator `"60000"`.
Keeping the amount in both buckets and producing `"120000"` is a test failure.

### C-03 — pending moves to rejected

Input for one JPY `"60000"` commission: v1 pending and v2 rejected.

Expected: rejected `"60000"`; pending/confirmed/paid `"0"`; settled numerator
`"0"`.

### C-04 — duplicate commission ID in one snapshot is rejected

Input A: the same commission ID appears twice with identical confirmed rows.
Input B: the same ID appears once confirmed and once rejected.

Expected: **REJECT** for both. A full batch replay is idempotent, but duplicate
rows inside one strict snapshot are invalid. Source row order must not decide
the status.

### C-05 — prohibited backward or unknown transition is rejected

Input A: v1 paid followed by v2 pending for the same commission ID. Input B:
status `"approved-ish"` absent from the versioned status map.

Expected: B is **REJECT** at strict parsing. A requires the snapshot-history
validator to **REJECT**; a single-snapshot builder cannot detect it. If no layer
compares v1/v2, it must not claim transition validation and production cohort
acceptance remains incomplete. A mapping hash alone does not permit an unmapped
or backward transition.

### C-06 — pending and rejected never enter confirmed EPC

Input cohort:

```text
valid clicks=1000
pending="900000"
rejected="500000"
confirmed="20000"
paid="40000"
```

Expected confirmed EPC:

```text
(20000 + 40000) / 1000 = Decimal("60")
```

Any result using pending or rejected is a critical failure.

### C-07 — all valid clicks remain in the denominator

Input: non-overlapping `ClickSummary` windows whose counts total 1,000, while
only 100 clicks can be joined to a commission row; settled commission is JPY
`"60000"`.

Expected EPC `"60"`. Dividing by 100 and returning `"600"` is prohibited.
Clicks without a commission, and clicks associated with pending/rejected
transactions, remain in the denominator.

### C-08 — duplicate or overlapping click summaries

Input A: the same `summary_id_sha256` appears twice, even identically. Expected:
**REJECT** inside one batch; replaying the complete batch separately is
idempotent.

Input B: two different summary IDs have overlapping click windows. Expected:
**REJECT**, because aggregated counts cannot prove that the overlapping clicks
are disjoint.

### C-09 — zero denominator is undefined

Input: zero valid clicks and zero settled commission.

Expected: the cohort artifact may record zero clicks if the schema permits, but
confirmed EPC is undefined and readiness is **STOP**. It must not be `0`, `NaN`,
infinity, or PASS. Reverse traffic calculation must not run.

### C-10 — settled-amount monotonicity property

For fixed valid clicks greater than zero, increase only confirmed or paid amount.

Expected: confirmed EPC never decreases. Varying only pending or rejected amount
must leave confirmed EPC bit-for-bit unchanged.

## 5. Currency, cohort, and time boundaries

### B-01 — mixed currency cannot be aggregated

Input: a JPY cohort containing JPY confirmed `"60000"` and one USD paid
`"100"` transaction.

Expected: **REJECT**. No FX rate, zero-value substitution, or separate-currency
subtraction may be applied inside one cohort.

### B-02 — partner and cohort IDs cannot be crossed

Input: a click summary belonging to partner A/cohort June and a commission row
declaring partner B or cohort May.

Expected: **REJECT** for the claimed cohort. Moving the transaction to make the
EPC threshold pass is prohibited.

### B-03 — click window is start-inclusive and end-exclusive

For the common reporting interval, use adjacent `ClickSummary` windows:

```text
summary A: [2026-06-01T00:00+09, 2026-06-15T00:00+09), count=1
summary B: [2026-06-15T00:00+09, 2026-07-01T00:00+09), count=1
```

Expected: exactly two valid cohort clicks. A summary starting exactly at cohort
end or ending at/before cohort start is outside and rejected; a summary ending
after cohort end is rejected. Changing B to start June 14 creates overlap and is
rejected. No local/UTC double conversion.

### B-04 — later settlement may update an in-cohort click

Input: a click summary covering June 20 and a commission with `attributed_at`
June 20. Snapshot v1 captured June 21 is pending; immutable snapshot v2 captured
July 10 carries the same commission ID as confirmed.

Expected: the click and attribution remain in the June cohort and v2's current
bucket is confirmed. Snapshot capture/status change may occur after the click
window; `attributed_at` must be inside the cohort, capture must be no later than
`as_of`, and the commission must carry the same partner/cohort/currency identity.

### B-05 — future and expiry boundaries fail closed

Inputs and expected results:

- `captured_at > as_of`: **REJECT** as future evidence.
- status event effective after `as_of`: **REJECT** as a future event.
- `expires_at == as_of`: **REJECT** as expired.
- `captured_at == as_of < expires_at`: accepted if all source events are not
  later than `as_of`.
- naive timestamp without offset: **REJECT**.

### B-06 — traction maturity boundaries remain canonical

Inputs:

|valid clicks|age days|Expected maturity|EPC decision|
|---:|---:|---|---|
|999|179|false|WAIT/CONTINUE|
|1000|0|true|evaluate mature EPC|
|0|180|true|STOP; EPC undefined|

The measurement intake must not redefine the economics thresholds.

## 6. Operations and 30-day shadow gate

`OperationsSummaryBatch` contains one strict `DailySummary` per observed local
date. Each daily row has a unique summary hash and date plus human minutes,
routine total/automated, job total/succeeded, exceptions, major misstatements,
and rollback tests total/passed. Duplicate summary IDs or dates are rejected.

The operations denominator comes from the versioned schedule/task inventory,
not only from rows that successfully emitted an event. Missing scheduled jobs
and manually completed routine tasks therefore cannot disappear from the
upstream daily denominator.

One logical job is identified by its run key. Retry attempts do not add jobs to
the denominator or numerator. A logical job is successful only if its terminal
outcome by the evaluation cutoff is success; missing, failed, cancelled, and
timed-out scheduled jobs are failures.

### O-01 — complete boundary-pass fixture

Input for one versioned 30-day shadow window:

```text
shadow_observation_days=30
job_runs_total=100
job_runs_succeeded=99
exceptions_total=24
routine tasks total=100
routine tasks completed without human touch=80
human_minutes_per_month=720
rollback_test_status=passed
major_misstatements=0
```

Expected derived values and gates:

```text
job success rate = 99 / 100 = Decimal("0.99")       PASS
automation rate  = 80 / 100 = Decimal("0.80")      PASS
human budget     = 720 minutes = 12 hours           PASS
shadow duration  = 30 days                          PASS
exceptions       = 24                               PASS
rollback status  = passed                           PASS
major errors     = 0                                PASS
```

Gate D may pass only if all seven checks pass; this does not authorize production
or replace Human GO.

### O-02 — automation threshold and denominator

Inputs and expectations:

- 80 automated / 100 eligible routine tasks: rate `"0.80"`, **PASS**.
- 79 / 100: rate `"0.79"`, **STOP**.
- 0 / 0: measurement artifact is allowed, derived automation rate `"0"`, and
  readiness is **STOP**; never 100% or not-applicable PASS.
- 101 / 100: **REJECT** as impossible.
- 80 automated completion rows but schedule inventory contains 100 eligible
  tasks, including 20 manual/failed tasks: denominator remains 100.
- A task that required any human touch is manual even if automation completed the
  last step; it is not in the automated numerator.

### O-03 — human monthly limit and month boundary

Inputs and expectations:

- 720 unique human minutes in the reporting month: 12 hours, **PASS**.
- 721 minutes: **STOP**.
- negative duration, end before start, or conflicting duplicate activity ID:
  **REJECT**.
- An upstream activity from June 30 23:50 through July 1 00:10 must produce 10
  minutes in the June 30 daily summary and 10 in the July 1 summary. The June
  batch accepts only June's 10; it must not contain 20. Because the intake sees
  daily aggregates, the allocation rule and source checksum are upstream
  prerequisites rather than something it can reconstruct.
- Duplicate daily date or summary ID inside one batch is **REJECT**. Replaying
  the complete batch separately is idempotent.

Human review and time spent supervising agents are human minutes. Agent runtime
without human supervision is not.

### O-04 — job success threshold and zero denominator

Inputs and expectations:

- 99 success / 100 scheduled logical jobs: `"0.99"`, **PASS**.
- 98 / 100: `"0.98"`, **STOP**.
- At 30 or more shadow days, 0 / 0: artifact generation is allowed, operational
  rate is undefined, and readiness is **STOP**; never 100%.
- Before 30 shadow days, including 0 / 0: job gate is **WAIT** and the overall
  result may be **CONTINUE** if no independent hard gate fails.
- Upstream 100 attempts from 50 logical run keys must enter daily summaries as
  50 logical jobs, not 100 attempts. A failed attempt followed by successful
  retry before cutoff is one job and one success.
- Because daily aggregates contain no run keys, a schedule/run-key receipt must
  prove this consolidation. If the input has only attempt totals with no receipt,
  expected **GATE STOP / unverified denominator**; the local builder cannot
  reconstruct retry identity.
- For any daily row, `job_runs_succeeded > job_runs_total` is **REJECT**.

### O-05 — shadow observation duration

- 30 unique in-month daily summaries with a valid observation start/capture
  interval: `shadow_observation_days=30`, **PASS**.
- 29 unique days: observation and job-success gates are **WAIT** and the preflight result
  is **CONTINUE** if no independent hard gate fails. It is not PASS or GO.
- Duplicate date, out-of-month date, negative value, missing observation
  start/capture receipt, or a window ending after `as_of`: **REJECT**.

Observation days are derived from the versioned shadow start/end window. Missing
daily jobs affect job success; they do not let the implementation shorten the
denominator or claim 30 completed days early.

### O-06 — monthly exception limit

- Daily summary counts sum to 24 for the month: **PASS** after 30 observation
  days; before maturity the exception gate is WAIT.
- Daily counts sum to 25: immediate **STOP**.
- Upstream duplicate delivery/notification/retry of one exception must count
  once; an exception resolved later still counts on its raised date.
- Daily aggregates contain no exception IDs, so the exception-dedup receipt is an
  upstream prerequisite. Counts without that receipt are **GATE STOP /
  unverified**, not locally deduplicated.

### O-07 — rollback gate

- A current, versioned rollback test receipt mapped to
  `rollback_test_status=passed`: **PASS**.
- `rollback_test_status=not_run`: **WAIT** and therefore no GO.
- `rollback_test_status=failed`: **STOP**.
- Daily aggregate mapping is exact: total `0`, passed `0` -> `not_run`; total
  `1`, passed `1` -> `passed`; total `2`, passed `1` -> `failed`.
- `rollback_tests_passed > rollback_tests_total` is **REJECT**.
- Absent, expired, for a different release/schema version, string `"true"`, AI
  assertion, or unsigned free text: **REJECT**, not enum/bool coercion.

### O-08 — major misstatement gate

- Daily summary counts sum to `major_misstatements=0`: **PASS**.
- Monthly sum `1`: **STOP**, even if corrected before month end.
- Upstream duplicate delivery of one incident ID counts once; two distinct
  incidents with the same root cause count twice. Daily aggregates cannot prove
  this identity rule, so the incident-ledger receipt is required.
- Reclassifying a major incident after seeing the gate outcome requires a new
  Human-approved QA-policy version; the intake cannot change classification.

### O-09 — property tests for operational aggregates

For generated valid batches, verify:

- increasing successful jobs with a fixed positive job denominator never lowers
  job success rate;
- adding a scheduled failed/missing job never raises job success rate;
- adding a human-touched routine task never raises automation rate;
- adding human minutes never changes PASS from false to true;
- row permutation and exact redelivery never change output or artifact hash.

## 7. Cross-artifact acceptance

### X-01 — provenance and strictness

Every emitted artifact must contain schema/evidence version, canonical source
SHA-256, captured and expiry times, and the relevant method/status-map/task-
inventory hashes. Unknown fields, missing hashes, raw IDs, secrets, URLs where a
hash is required, PII, `NaN`, infinity, and binary floats are **REJECT**.

### X-02 — independent artifact periods must be explicit

Demand, cohort, and operations may have different valid periods, but the dossier
must preserve each `captured_at`/`expires_at` and evaluate all at one timezone-
aware `as_of`. It must not replace them with the longest expiry. At
`expires_at <= as_of`, dossier assembly/readiness is **REJECT/STOP** before
economics.

### X-03 — immutable replay

Reprocessing an identical source batch yields the same Evidence content and
hash. A corrected material row creates a new evidence version; it never
overwrites the previous version or keeps the old checksum.

### X-04 — economics handoff must preserve canonical meanings

The generated economics input must preserve:

- globally deduplicated bear/base/bull demand;
- all valid cohort clicks as the EPC denominator;
- mutually exclusive pending/rejected/confirmed/paid current buckets;
- one currency and cohort identity;
- human hours derived from minutes and automation derived from task counts.

No downstream builder may accept caller-supplied replacements for these derived
values.

## 8. Gate D integration contract

The readiness/economics path now carries these canonical fields:

- `shadow_observation_days`;
- `job_runs_total` and `job_runs_succeeded`;
- `exceptions_total`;
- `rollback_test_status: not_run | passed | failed`.

Acceptance requires these values to be derived from `OperationsEvidence`, not
accepted as caller-supplied readiness overrides. The economics semantics are:

1. `shadow_observation_days < 30` makes the observation and job checks WAIT. With
   no independent hard failure, the result is CONTINUE, never GO.
2. At 30 or more days, `job_runs_total == 0` or success rate below `0.99` is
   STOP; a positive denominator at or above `0.99` is PASS.
3. More than 24 monthly exceptions is an immediate STOP. At or below 24 it
   becomes PASS after 30 days and WAIT before 30 days.
4. Rollback `not_run` is WAIT, `failed` is STOP, and `passed` is PASS.

This wiring resolves the former field-level integration gap, but it does not
create production evidence. A manually supplied rate, prose report, CLI flag,
or boolean replacing the enum/derived counts is not an acceptable bridge. Until
a current 30-day `OperationsEvidence` passes O-01 through O-08, Phase 3 Gate D
remains non-GO.

## 9. Required automated test inventory

Before P6 acceptance, the implementation test suite must map every ID in this
document to at least one automated test and include these generated properties:

- demand/event idempotency and input-order invariance;
- one global count for overlapping query/group membership;
- exactly one current commission status per transaction;
- pending/rejected invariance and settled EPC monotonicity;
- click denominator deduplication and zero-denominator failure;
- currency/cohort/time isolation;
- automation, human-minute, job-success, exception, and incident boundaries;
- deterministic Evidence serialization and hash sensitivity to material change.

The acceptance run must use synthetic fixtures only, run without network access,
and report failing test IDs. Passing unit tests does not convert synthetic values
into production evidence.
