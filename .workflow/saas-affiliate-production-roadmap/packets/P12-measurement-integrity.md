# P12 Work Packet: Signed measurement integrity

## Objective

Close the local authenticity and reconciliation gaps between Phase 3 L2 summaries and Gate C/D evidence without
fetching real data, loading credentials, contacting an Affiliate network, or changing the current `STOP` decision.

## Ownership

- Contract/Storage: strict signed producer artifacts, immutable run/policy binding, exclusive transaction status,
  payout/funnel reconciliation and deterministic schema/hash behavior.
- Governance: qualification, denominator, dedup, status, refund/chargeback, new-acquisition and privacy definitions;
  Human freeze boundary and producer trust separation.
- TCO/QA: exact eight required fault identities, double-count/omission/overlap/future/expiry counterexamples,
  Decimal EPC/funnel/payout invariants and full regression.
- Integration/Release (root): interface integration, schema export, docs/workflow, current STOP proof and final audit.

## Required local contracts

1. A fixed measurement trust store and policy pin independently configured downstream.
2. A Human-signed pre-run plan for JP/ja/property/currency/window, producer keys, all denominator/mapping/privacy
   hashes, source partitions, required eight fault IDs and TTL. It contains no result-dependent batch hash.
3. Producer-signed demand, cohort and operations attestations bind canonical batch hashes and stage-specific complete
   coverage; a separately signed post-run index closes the exact three batches and attestations.
4. Cohort rows keyed by hash-only transaction ID with exactly one current status. Confirmed and paid are mutually
   exclusive; old snapshots are not summed. Refund/chargeback and new-acquisition treatment is explicit.
5. Funnel reconciliation from qualified sessions through outbound clicks, Affiliate clicks, current transactions and
   payout evidence. Missing/overlapping denominators or mismatched payout totals fail closed.
6. Operations receipts identify the exact canonical fault set: price, plan name, billing period, currency, quota,
   source conflict, Affiliate expiry and fetch failure. Counts alone cannot satisfy Gate D.
7. A fixed runtime verifies signatures, roles, policy/plan/index/batch binding, consumer-owned exact pins,
   future/expiry and all reconciliation invariants before emitting existing readiness evidence.

## Acceptance

- Unknown fields, duplicate identities, wrong role/key/policy/manifest/property/window/currency and copied self-hash
  artifacts are rejected.
- Pending/rejected/refunded/charged-back amounts never enter settled EPC; confirmed-to-paid movement contributes once.
- Valid-click denominator cannot be replaced by attributed/converted clicks. Funnel counts are non-increasing and
  exact payout totals reconcile to exclusive current transactions.
- One repeated fault ID cannot satisfy eight cases; omission, substitution, duplicate and failed restore reject.
- Future, exact expiry, excessive TTL and unsigned producer batches reject under a downstream-pinned runtime.
- Deterministic schemas/examples/tests and full Python/Web/SBOM/lock/secret/workflow checks pass.
- No real data, Affiliate URL, account, credential, external source or network action is introduced; business/public
  state remains `STOP`.

## Deferred, not waived

- Real producer identities/export signatures, Affiliate network status/payout APIs and actual 30-day evidence.
- P13 out-of-process provider adapter, shared state/fencing, global STOP latch and two-stage production consumer.
