# P14 Work Packet: Crash-safe provider evidence and conformance

## Objective

Close the credential-free reliability gaps that remain after P13 without claiming remote-provider or distributed
production guarantees. Persist a verified provider fact before P11/P13 terminal success, preserve that fact through
crash recovery, and add adversarial conformance tests for multi-process fencing and pinned runtime artifacts.

## Ownership

- Contract/Storage: immutable provider-fact journal, authenticated schema/state, restart recovery and idempotency.
- Governance: factual outcome versus authority, STOP precedence, honest local/production boundary.
- TCO/QA: crash points, multi-process contention, key/policy swap, schema/artifact mutation counterexamples.
- Integration/Release: P13 flow integration, schemas, docs, workflow and full regression.

## Required local contracts

1. A verified provider receipt is written to the authenticated P13 store before probe, P11 receipt and P13 terminal
   success. The journal entry is immutable and exact-token/request bound.
2. Terminal commit must use the exact journaled provider receipt. Success additionally uses the exact journaled probe
   if probe journaling is implemented.
3. Restart with a journaled provider fact never retries or promotes. It creates terminal `UNKNOWN`, preserves the
   factual provider receipt, advances epoch and asserts STOP.
4. A crash before provider-fact persistence may remain `UNKNOWN` without a factual receipt; production reconciliation
   with a real provider remains a separate gate.
5. Multiple OS processes cannot obtain two live dispatch owners for one store. Artifact/key/schema mutations reject
   before success.

## Acceptance

- Provider-fact duplicate is idempotent only when byte/exact-model equal; conflicting replacement rejects.
- Forged, wrong-token, old-epoch, late or wrong-policy provider facts reject.
- Crash/reopen after provider-fact persistence returns immutable `UNKNOWN` carrying that fact, provider call count 1,
  sticky STOP and one epoch advance.
- Existing success, failure, revocation, expiry, anchor and adapter-fence tests remain green.
- P9/P10 key swap, postcondition-schema mutation and multi-process claim contention have explicit tests.
- No network, credential, external write, deploy or publication path is added.

## Deferred, not waived

- Remote provider atomic conditional mutation/readback and exactly-once guarantee.
- Distributed consensus anchor, multi-host fence, KMS/OS identity separation and trusted time.
- Cross-database transaction spanning P11/P13; reconciliation can prove facts but cannot retroactively promote an
  ambiguous execution to success.
