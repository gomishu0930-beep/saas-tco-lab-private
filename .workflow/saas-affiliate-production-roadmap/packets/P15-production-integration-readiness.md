# P15 Work Packet: Production integration readiness and reconciliation gate

## Objective

Implement the strongest credential-free gate that can precede a real production provider. A concrete environment
must not be admitted merely because the local P13/P14 simulator passes. It must supply current, hash-bound,
role-separated evidence for provider mutation semantics and the surrounding production controls.

## Ownership

- Contract/Storage: provider idempotency/lookup, shared store/fencing, anchor and backup/restore facts.
- Governance: fact versus authority, Human approval, expiry, prohibited secret/URL fields and honest STOP semantics.
- TCO/QA: exact check matrix, thresholds, fault cases and no-waiver evaluation.
- Integration/Release: strict models, evaluator, CLI/schema/docs/fixtures and full verification.

## Required local contracts

1. One exact production plan binds property, environment, P13 policy/store, release artifact, adapter/probe closure,
   provider capability profile, deployment candidate and all evidence identities by SHA-256 only.
2. Exact required checks cover provider conditional mutation, idempotency retention, receipt lookup, independent
   readback, KMS identity separation, external monotonic anchor, trusted clock, shared durable store/fencing, egress,
   backup/restore and rollback/disable.
3. Evidence is typed, current, bounded, role-signed and bound to the exact plan/check. Count-only or free-form claims,
   URLs, credentials and self-approved booleans are rejected.
4. TCO/QA acceptance and Human environment approval are distinct signatures. A controller authorization, if emitted,
   is bound to the exact passing report and expires before every input.
5. Missing, duplicate, conflicting, failed, future or expired checks return STOP. There is no waiver path and no
   synthetic fixture is production evidence.
6. Reconciliation can preserve a provider fact and recommend STOP/disable, but can never retroactively promote an
   ambiguous P13 `UNKNOWN` to success.

## Do not

- connect to a provider, cloud, KMS, database, domain or analytics service;
- create accounts, credentials, billing, OAuth, URLs or deployment configuration;
- send, publish, deploy, push or mutate external state;
- claim remote exactly-once, distributed consensus or real backup/restore success from a local fixture.

## Acceptance

- current blocked fixture evaluates STOP with explicit missing checks;
- a complete synthetic fixture proves only deterministic contract wiring;
- exact threshold boundaries and all failure modes have checked-in tests;
- schemas repeat byte-identically; CLI has no network/external mutation command;
- independent Contract/Storage and TCO/QA/Governance reviews report no local blocker.
