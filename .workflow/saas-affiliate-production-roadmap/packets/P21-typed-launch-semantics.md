# Packet P21 — Typed semantic launch-gate re-evaluation

## Objective

Prevent P16 Gates 2–8 from reaching `READY_FOR_FINAL_HUMAN_REVIEW` using only a consumer-pinned plan, valid gate
signatures and opaque component hashes. Require the P16 consumer to parse, bind and re-evaluate exact typed semantic
payloads for every non-repository gate while preserving the non-authoritative, credential-free STOP boundary.

## Ownership

- Integration/Release: P16 evidence envelope, evaluator integration, CLI and downstream P13 binding.
- Contract/Storage: canonical hashes, exact cardinality, replay/substitution and deterministic serialization.
- Security: consumer-owned roots, scope/expiry/trust substitution and secret-free boundary.
- TCO/QA: demand, operations, gold-set and readiness threshold semantics.

## Required invariants

1. Every Gate 2–8 receipt binds the canonical hash of the exact typed payload carried in the P16 bundle.
2. Missing, duplicate, extra, wrong-kind or hash-only payloads fail the affected gate and all successors.
3. Property, candidate manifest, environment, release identity/manifest/artifact, deployment candidate, provider target,
   expected pre/post state, rollback state, legal pages and Affiliate disclosure are cross-bound. P15 plan v2 owns the
   provider target and expected pre-state, so evidence for target A cannot be re-attributed to target B.
4. Currentness is evaluated at the consumer's `at`; a signed payload cannot extend its upstream expiry.
5. Rights and Affiliate gates derive distinct eligible vendors/partners and require at least three; booleans/counts are
   never accepted as substitutes for the underlying rows.
6. Demand and operations gates derive their values from typed rows and fixed policy thresholds; automation, job rate,
   human time and 30-day coverage are not caller assertions.
7. Gold/source readiness derives coverage and quarantine state from typed facts and cannot pass with omissions.
8. P15 and deployment/publication gates parse their typed upstream reports/records and require exact READY/current
   scope. No P10/P11/P13 execution authorization is imported into P16.
9. The output remains Human-review input only and authorizes no external action.

## Counterexamples

- valid receipt over an absent payload;
- valid receipt over an arbitrary digest;
- self-consistent plan plus all receipts with a payload from another property/environment/release;
- three rows that reuse a vendor, partner, program or evidence identity;
- exact-expiry payload and a payload whose internal expiry exceeds the gate receipt;
- aggregate demand/operations claims that disagree with their rows;
- P15 STOP report renamed or re-hashed as READY;
- deployment/publication record with missing rollback/readback/disclosure facts, a different P11 disable authority,
  a different deployment record, stale/per-deployment readback, or target/pre-state re-attribution;
- synthetic payload mixed into an otherwise verified packet.

## Verification

Focused P16/P13 tests, deterministic schema and blocked fixture generation, all Python partitions, Web checks, lock,
compile, secret scan, workflow verification and independent Contract/Storage, Security and TCO/QA closing audits.
