# P14 acceptance tests

## New local counterexamples

| Area | Counterexample | Expected result |
|---|---|---|
| Live owner | another store opens while a claim owner is alive | no recovery; snapshot unchanged; redeem/terminal write rejected |
| Dead owner | owner closes with an in-flight claim | one recovery event; terminal `UNKNOWN`; sticky STOP |
| Post-provider crash | owner disappears after provider journal, before probe/terminal | exact provider receipt preserved; call count 1; `UNKNOWN + STOP` |
| Pre-journal crash | owner disappears after redemption but before provider fact commit | no receipt invented; provider not retried |
| Mutation/receipt gap | provider child increments its real call count, then owner exits before returning the receipt | recover `UNKNOWN + STOP`; call count stays 1; no journal fact invented |
| Duplicate | execute is requested again after exact fact persistence | stored receipt returned; child not called; revision/head unchanged |
| Injection | a valid signed receipt obtained outside the journal is passed to terminal commit | reject; unjournaled fact cannot enter the result |
| Immutability | direct update/delete of a provider journal row | database trigger rejects |
| Anchor outage | SQLite journal commits but external anchor callback fails once | recover the exact one-ahead anchor; preserve fact; terminal `UNKNOWN + STOP` |
| Process contention | four OS processes claim the same request concurrently | exactly one owner; three `in progress`; no live-owner recovery |
| Fork inheritance | a child inherits the live owner's Python object and file descriptor | child owner state is cleared without unlocking parent; redeem/invoke/terminal reject |
| Parent death | owner exits while its forked child remains alive | child descriptor does not retain lease; next opener recovers `UNKNOWN + STOP` |
| Phase fence | probe is attempted before fact persistence or after epoch/STOP change | reject before child launch |
| Artifact mutation | pinned postcondition schema changes after provider fact, before probe | reject; no success; fact may terminate as `UNKNOWN` |
| Legacy schema | ordinary open of a version-1 store | exact schema mismatch; no implicit migration |
| Terminal binding | caller supplies a different receipt from the immutable journal | reject; journal cannot be replaced |
| Valid conflict | a second correctly signed provider receipt names different factual audit data | reject immutable-journal replacement; revision unchanged |
| P9/P10 splice | another valid same-controller lease or public report is substituted | claim rejects; revision/head/epoch unchanged; provider call 0 |
| Receipt authority | wrong provider key or receipt bound to a separately signed alternate-policy dispatch | journal rejects; revision/head/epoch unchanged; row count 0 |
| Journal chronology | signed probe predates provider-journal verification time | success commit rejects even if provider completion predates the probe |
| Existing P13 paths | success, failure, revocation, expiry, process kill, FD path-swap and schema/anchor faults | unchanged fail-closed behavior |

## Required invariants

- A provider fact advances revision once and never advances it on exact duplicate read.
- Only the live owner can redeem, invoke or terminate an in-flight request.
- A late opener cannot convert a live request into restart recovery.
- A dead in-flight owner is never resumed and the provider is never automatically retried.
- A recovered journaled fact is evidence only and always terminates as `UNKNOWN + STOP`.
- `SUCCEEDED` can use only the exact immutable journal receipt plus current probe, P11 receipt and P9–P13 authority.
- No terminal path can insert, replace, update or delete a provider fact.
- STOP and epoch recovery happen once per recovered request set, not once per receipt.

## Recorded local run

The P14 fixed candidate was recorded as:

- focused production-consumer suite: 42 passed;
- Python full suite: 399 passed;
- generated JSON Schemas: 80, repeat export byte-identical;
- compileall: passed;
- `uv lock --check`: 24 resolved packages;
- Gitleaks: no leaks.

P15 subsequently extends, rather than rewrites, this boundary. The current integrated candidate records 52
production-consumer tests, 105 dedicated P15 tests, 514 full Python tests and 105 deterministic schemas. P15 evidence,
reset-ledger and activation-expiry cases are specified in `docs/P15_ACCEPTANCE_TESTS.md`.

These results apply only to the fixed local candidate hashes recorded in the pending acceptance document after the
independent audits. They are not evidence of real provider, rights, Affiliate, demand, EPC, deploy or public readiness.

## Deferred environment acceptance

Before any production connection, separately test remote idempotency and conditional writes, mutation/receipt crash
reconciliation, real readback, durable out-of-process anchor, multi-host fencing, KMS identities, trusted time,
cross-store P11/P13 ambiguity, backup/restore and incident disable. Failure or missing evidence keeps public/business
state at STOP.
