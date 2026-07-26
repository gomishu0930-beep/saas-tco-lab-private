# P2 Release / Operations result

## Outcome

Implemented immutable local release and operations state machines without
network, database, cloud, filesystem publication, or changes to the existing
contract/TCO/CLI authority.

Owned implementation:

- `src/saas_preflight/release.py`
- `src/saas_preflight/operations.py`
- `tests/test_release.py`
- `tests/test_operations.py`

## Release boundary

`ReleaseManifest` is a frozen, content-addressed record containing:

- artifact and schema SHA-256;
- one or more data-snapshot SHA-256 values;
- rights and affiliate bundle SHA-256 values;
- independent data, rights, and affiliate expiry timestamps;
- a hash-only affiliate CTA decision;
- an explicit rollback release id for replacements.

The manifest hash is generated from canonical JSON. All timestamps must be UTC,
all external artifact references must be lowercase SHA-256, snapshot digests
must be unique, and every expiry must follow preparation.

`prepare_release`, `promote_release`, and `rollback_release` are pure state
transitions. They do not publish anything. Promotion and rollback require an
exact release/scope match to a current, explicit `GO` Human approval reference.
`STOP`, `CONDITIONAL`, expired approvals, expired releases, undeclared rollback
targets, targets never previously promoted, and event-history inconsistencies
fail closed.

Exact preparation and promotion retries are idempotent. Reusing a release id
for a different manifest is rejected. State construction replays its immutable
events, so a current pointer cannot be inserted without a valid prepare and
promotion/rollback history.

## Read-time visibility and CTA

`evaluate_visibility(state, at=UTC)` evaluates every read independently of the
build time. At the exact earliest data, rights, or affiliate expiry:

- comparison content becomes hidden;
- affiliate CTA becomes disabled;
- the specific expiry reason is returned;
- the manifest hash and shortest expiry remain available for safe operational
  diagnosis.

An approved CTA contains only program id, destination hash, and disclosure
hash; no live affiliate URL is kept in the state. An unreviewed or prohibited
CTA can never be enabled. Unreviewed CTA alone may leave non-monetized content
visible, while any affiliate-bundle expiry hides the entire release as required
by the production gate.

## Idempotent operations

`RunKey` is a deterministic SHA-256 of job name, scheduled UTC instant, and
input SHA-256. `claim_run` permits one claim per key:

- the same owner receives the existing claim on retry;
- another owner is rejected;
- a run cannot be claimed before schedule;
- completion after lease expiry is rejected;
- the same output completion is idempotent;
- changing a completed output or failed-run code is rejected.

Failed or expired keys are not silently recycled. A deliberate retry requires a
new scheduled/input key and can be linked to the exception queue by integration.

## Exception queue

`OperationalException` and `ExceptionQueue` provide immutable, hash-deduplicated
open → acknowledged → resolved transitions. Summaries are bounded single-line
metadata and cannot contain copied raw source bodies. Resolution requires a
SHA-256 reference to a separate artifact; an exception must be acknowledged
before resolution. A stable key cannot be reused for a different fault.

## Human-time budget

`MonthlyHumanBudget` and `record_time` enforce the operating model:

- normal below 576 minutes;
- frozen at 576 minutes, blocking new sources and noncritical improvements;
- exhausted at 720 minutes, blocking all normal work;
- Evidence 180, Contract 90, TCO 120, Integration 210, Human 120 minute role
  allocations;
- exact-entry retries are idempotent and conflicting references are rejected;
- all entries must be UTC, chronological, and inside the declared month.

A frozen work item cannot cross from 575 past the 576-minute boundary. At or
after 720, only `SEV0_SAFETY_STOP` and `STOP_DECISION` may be recorded. Those two
safety categories may exceed the numeric cap so the ledger never suppresses an
emergency stop; the resulting overage remains visible as exhausted state and is
not authority for ordinary work.

## Verification

- P2 release/operations tests: `23 passed`
- Full suite at P2 handoff: `128 passed`
- Compileall: passed
- Covered faults: invalid UTC/hash, immutable mutation, duplicate release/run,
  all three expiry kinds, CTA unreviewed, approval mismatch/STOP/expiry,
  undeclared and expired rollback, pre-schedule run, lease expiry, conflicting
  result, exception deduplication/order, 576 freeze crossing, 720 exhaustion,
  role overage, wrong month, and emergency stop behavior.

## Integration handoff

Primary APIs:

- release: `prepare_release`, `promote_release`, `rollback_release`,
  `evaluate_visibility`;
- run: `claim_run`, `complete_run`, `fail_run`;
- queue: `enqueue_exception`, `acknowledge_exception`, `resolve_exception`;
- budget: `record_time`.

`HumanApproval.decision_record_sha256` is a reference to a separately retained
signed decision; this module does not claim to cryptographically verify a Human
signature. External publication, rollback, affiliate URL resolution, and
credential use remain separate Human-controlled operations.
