# P13 acceptance tests

## Implemented local assertions

| Area | Counterexample | Expected result |
|---|---|---|
| Stage splice | P9/P10/P12 fields omitted | typed request cannot be constructed |
| P15 splice | plan/authorization fields omitted or another valid pair substituted | reject before P13 claim; provider/store unchanged |
| P16/P18/P21 splice | packet-external repository, handoff or semantic root is swapped; typed semantic packet is absent/substituted; or P15/P10 component differs | reject before provider; state unchanged or sticky STOP |
| P16 exact expiry | P16 live receipt expires after claim but immediately before dispatch | provider call 0; terminal `UNKNOWN + STOP` |
| Trusted time | signed clock is backdated beyond policy or moves backwards | persistent STOP; provider call 0 |
| Current roots | Storage Auditor signs a newer repository, handoff or semantic root different from bootstrap authority | persistent STOP; provider call 0 |
| Low-level bypass | caller supplies an old raw `at` directly to reset/claim/redeem/provider/probe/terminal store APIs | ignore caller time; require a fresh signed phase attestation inside the store API |
| Root rollback | store accepts root revision 2, reopens, then receives revision 1 | persistent STOP; rollback survives process restart |
| Dispatch clipping | P16/P18 effective expiry precedes request/P15 expiry | signed token expires at the P16/P18 boundary |
| Provider chronology | provider completes after its pre-call timestamp | verify against a fresh signed post-provider time |
| P11 durability | valid-shaped claim absent from the pinned P11 store | reject before P13 claim |
| Binding | wrong P12 run or exact request expiry | reject; provider call count 0 |
| STOP | activation while provisioned STOP | reject; no dispatch |
| Reset | changed STOP reason/head binding or exact expiry | reject; STOP unchanged |
| Success | full signed P9–P12 path, Human reset, subprocess receipt and separate probe | terminal success |
| Idempotency | same successful request delivered twice | identical terminal result; provider call count 1 |
| Conflict | another request reuses the same idempotency key | reject; first claim remains owner |
| Provider drift | signed provider observes the wrong pre-state | terminal failed; sticky STOP; epoch advances |
| Safety lane | P11-approved disable during STOP | may succeed; STOP remains asserted |
| Crash recovery | reopen with an in-flight claim | terminal unknown; sticky STOP; no provider call |
| Rollback | restore DB while external anchor remains current | open rejects |
| Executable | adapter file does not match pinned SHA-256 | reject before launch |
| Revocation | P11 revocation becomes effective after P13 claim but before redemption | atomic `UNKNOWN` + STOP + one epoch increment; provider call 0 |
| Factual result | revocation becomes effective after provider completion | preserve signed provider receipt, omit success receipts, terminal `UNKNOWN`, sticky STOP |
| Provider ambiguity | provider returns a signed receipt but the post-provider clock fails | persist immutable attempt first; terminal `UNKNOWN + STOP`; never retry |
| Callback/anchor double fault | provider callback escapes while the external anchor is unavailable | revoke the live store's launch authority and lease immediately; only a new opener may recover the intent to `UNKNOWN + STOP` |
| Revocation TOCTOU | controller tries to register revocation after the last check while provider mutation is fenced | revocation writer blocks until mutation exits; terminal success rechecks revocation |
| In-flight expiry | remaining dispatch authority is shorter than the policy execution margin | reject before external mutation |
| Exact expiry | redeem or success commit at exact token expiry | reject success; redemption becomes atomic `UNKNOWN` + STOP |
| P15 expiry | authorization expires after claim or at terminal success | reject before provider or reject success; `UNKNOWN + STOP` |
| Adapter fence | old token is sent after STOP/epoch advance | reject before child launch; provider state unchanged |
| Policy splice | policy-B runtime is used with policy-A store | constructor and direct claim reject without revision change |
| Receipt forgery | forged provider receipt is passed directly to success commit | reject; no P13 success |
| Cross-receipt splice | authoritative P11 receipt names different provider-operation/audit hashes | reject; no P13 success |
| Chronology | correctly signed probe predates provider completion | reject |
| Disable semantics | no-op disable or rule that does not start at active state | typed policy rejects before launch |
| Process roles | execute receives probe key or probe receives provider key | child parser rejects |
| Process tree | timed-out adapter forks a delayed child | kill the entire process group; delayed mutation absent |
| TOCTOU | adapter path is replaced between verification and launch | execute the already-verified descriptor, not replacement bytes |
| Import closure | an unpinned module exists on an explicitly supplied runtime import path | child import guard rejects it before module execution |
| Import TOCTOU | a pinned Python module path is replaced after guard open/hash | execute verified bytes or reject; replacement code never runs |
| Stdlib binding | base `argparse`/runtime source changes | dependency closure hash changes; request no longer matches |
| Output flood | child exceeds stdout/stderr cap and keeps running | kill process group immediately; no unbounded parent buffer |
| Arbitrary provider callback | caller passes a structural fake/callable to the low-level store API | reject before attempt intent, revision, epoch, or provider state changes |
| Concurrency | two live claims for the same request | one owner; one `in progress`; one token |
| Schema | rogue trigger outside the application prefix | exact whole-store schema fingerprint rejects |
| Anchor ambiguity | SQLite is one committed revision ahead after anchor callback failure | republish exact authenticated anchor once; no synthetic extra revision |
| Reconciliation reset | missing, expired, stale-head or wrong-store P15 ledger record is named by Human reset | reject; STOP unchanged |
| Unsafe reset | P15 record says `APPLIED` or `AMBIGUOUS` | reject until a separate safe `NOT_APPLIED` readback record exists |
| Ledger splice | same plan is presented through a different ledger store or recovery trust | runtime bootstrap rejects |
| Disable/P15 | P15 activation authorization is expired while a new P11 Human disable is current | disable remains available; STOP stays asserted |

## Invariants

- `SUCCEEDED` implies exact provider receipt, exact independent probe and authoritative P11 receipt.
- activation success implies current P9, P10, P11, P12, P13, P15, P16 and nested P18 authorities for one release/property/environment scope.
- terminal results are immutable.
- request, idempotency and fencing ownership are unique.
- epoch and revision never decrease in a valid store.
- STOP never changes to RUNNING without a current exact Human reset and matching current P15 reconciliation-ledger record.
- disable cannot create activation or clear STOP.
- an in-flight restart never auto-retries.
- an authoritative redemption failure cannot remain stranded in `CLAIMED` while the store reports RUNNING.
- provider/probe keys, programs and arguments are role-separated; local same-user filesystem isolation is not claimed.
- factual provider completion may survive an authority loss, but it cannot become P13 success.
- every mutation-capable store API obtains signed time internally; activation phases also obtain current P18/P16/semantic roots, and accepted time/root revision are state-MAC/anchor protected.
- provider execution is ordered as `durable one-shot attempt intent + pre-authority observation -> P11 revocation/deadline fence -> signed factual receipt journal -> post-provider time/root verification -> verified receipt journal`.
- provider mutation accepts only an exact immutable one-shot subprocess execution port bound to request, token, adapter closure, timeout and output limits; the store method is private and arbitrary callbacks are rejected before durable intent.
- one monotonic deadline is created before pre-provider authority work and propagated through manifest verification and subprocess communication. Deadline exhaustion after intent is recovered as `UNKNOWN + STOP`, never retried.
- after a timeout the process group is killed, but the authority-bearing caller never performs an unbounded child wait. An already-dead child is reaped synchronously with a zero-time poll; a still-exiting child is handed to an isolated daemon reaper.
- if both callback closure and its anchor operation fail, the live store loses its provider-capability registration and in-flight lease before control returns; reopen recovery must commit `UNKNOWN + STOP` before any later launch.
- OS store locks and external anchor callbacks have fixed deadlines; timeout is failure, never an unbounded wait.

## Deferred environment tests

The local Python process is a cooperative synthetic harness, not an isolation boundary against hostile code running
under the same OS identity. Python-private fields can be introspected or rewritten by such code. Production therefore
requires a separately isolated provider broker/OS identity that owns non-exportable keys and revalidates the durable
intent, current STOP/epoch/root, P11 revocation and provider-side conditional mutation immediately before the point of
no return. The broker must enforce one total deadline across prelaunch work and provider completion; a captured local
timestamp is not sufficient.

The following cannot be honestly proven by the credential-free fixture: cross-host fencing, provider-side
exactly-once behavior, real provider readback, KMS key non-exportability, production time/current-root service, external consensus-anchor
availability, network egress policy, production process identity, multi-region recovery and provider incident
handling. They are mandatory launch acceptance tests, not waived risks.

The current production-consumer partition contains 81 tests, including packet-external P18/P16/semantic root replacement,
typed packet substitution, a different measurement dossier, a rehashed provider-target splice, incomplete handoff, signed clock/root counterexamples and exact dispatch-expiry clipping. Counts are fixed in the immutable-runner policy and verified by
collection before evidence can be accepted. See `docs/P14_ACCEPTANCE_TESTS.md` and `docs/P15_ACCEPTANCE_TESTS.md`.
A passing synthetic fixture is not evidence that any real provider or business gate is ready.
