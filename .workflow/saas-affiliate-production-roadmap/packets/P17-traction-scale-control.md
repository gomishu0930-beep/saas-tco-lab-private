# P17 Work Packet: Traction and scale control ledger

## Objective

Implement the missing credential-free Phase 7–8 execution layer. It must preserve a sequence of signed, P12-bound
30-day observations plus later settlement amendments, evaluate the 1,000-click/180-day traction boundary, merchant
concentration, settled EPC, JPY 200,000 capacity and operating guardrails, and produce a non-authoritative
scale/continue/stop recommendation.

## Ownership

- Contract/Storage: immutable observation contract, chronology, canonical chain, append-only ledger and replay safety.
- TCO/QA: exact formulas, maturity/target/concentration boundaries, counterexamples and deterministic outputs.
- Integration/Release: P12 binding, strict models, evaluator, CLI/schema/fixtures/docs and full verification.

## Required local contracts

1. A Human-frozen traction plan binds property, release, experiment window, P12 trust/policy identity, KPI definitions,
   JPY 200,000 target, minimum EPC 60, maturity at 1,000 clicks or 180 days, and operating/concentration guardrails.
2. Each 30-day observation is derived at ingestion by rerunning the complete current P12 authority packet. It preserves
   the exact report, run plan, bundle-index, property, release, partner, batch, attestation and time commitments. It may
   not accept self-reported counts, ratios or aggregate booleans.
3. Observations are canonical, non-overlapping, predecessor-linked, cumulative-monotonic where applicable and signed by
   a policy-pinned TCO/QA key. Missing months, duplicate/conflicting snapshots, retroactive rewrite and cross-plan splice
   fail closed.
4. A signed Settlement Amendment is bound to an original P12 cohort and can only apply later status/adjustment deltas;
   it cannot alter sessions, clicks, attribution, partner, currency or original amount. Exactly-once replay and signed
   positive/negative settlement deltas are required. Without settlement completeness, real scale review is STOP.
5. Settled EPC uses the amended settled new-acquisition amount over all valid outbound clicks. Pending/rejected amounts
   never enter revenue. Revenue and EPC may decrease after a valid reversal. Partner concentration uses the same settled
   numerator and preserves the exact frozen partner set, including zero-revenue partners.
6. Cumulative clicks, covered days and EPC are kept separate from latest-window revenue, CTR, concentration and
   operations. Before maturity, only CONTINUE/STOP is possible. At maturity, low/undefined EPC or target-capacity is STOP.
   SCALE_REVIEW additionally requires revenue/capacity, CTR, partner diversity/concentration, quality, automation and
   human-budget guardrails. It never authorizes spend, release, merchant changes or publication.
7. Current checked-in fixture contains no real observations and remains STOP according to an explicit production policy;
   synthetic observations can prove wiring only and can never be treated as real traction evidence.

## Do not

- access analytics, affiliate networks, Search Console, providers, email, cloud or production databases;
- create credentials, accounts, tracking URLs, campaigns, spend, deployment or public state;
- store PII, raw events, transaction IDs, URLs, account IDs, free-form notes or non-public commission details;
- reinterpret P16 final-review readiness as launch authority;
- replace missing months, settlement, rights, affiliate or Human decisions with estimates.

## Acceptance

- blocked fixture, settlement-incomplete fixture and all-synthetic fixture cannot reach scale review;
- exact 999/1000 clicks, day 179/180, EPC 59.99/60, CTR 9.99%/10%, revenue 199999.99/200000,
  partner share 40%/over-40%, automation 80%, human 720 minutes and job 99% boundaries are tested;
- append-only chronology, duplicates, conflicts, cross-plan/report/property/partner splices and exact expiry fail closed;
- settlement amendment positive/negative deltas, replay, foreign-cohort splice and incompleteness are tested;
- P12 report verification is exercised, not replaced by a copied count;
- focused/full tests, schema determinism, CLI offline, lock, compile, secret scan and workflow verifier pass;
- independent Contract/Storage and TCO/QA fixed-hash audits report no local blocker.
