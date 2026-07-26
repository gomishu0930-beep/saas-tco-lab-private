# P12 Result: Signed measurement integrity

## Outcome

Local P12 contract is complete. Business/public state remains `STOP`; no real
source, Affiliate account, credential, URL, price, demand, cohort, external call,
deployment, or publication was introduced.

Authoritative local sequence:

1. Human-signed pre-run `SignedMeasurementRunPlan`
2. demand/cohort/operations role-separated producer attestations
3. stage-specific completeness counts and identity-set roots
4. signed post-run exact `MeasurementBundleIndex`
5. consumer-owned exact policy/trust/run/index pins
6. fixed TCO/QA runtime and signed `MeasurementIntegrityReport`
7. report-bound `MeasurementBoundDossier`

The pre-run plan and post-run index are separate so result-dependent batch hashes
cannot be placed into a document claimed to have been frozen before measurement.

## Implemented invariants

- Six distinct Ed25519 roles: measurement Human, demand producer, cohort
  producer, operations producer, bundle indexer, TCO/QA verifier.
- Policy pins labeled dataset authorities, every rule/privacy hash, exact fault
  definitions, property scope and TTLs.
- Consumer pins are independent inputs and include exact policy hash, trust root,
  run ID and exact signed bundle-index hash.
- Canonical hashes normalize equivalent timezone offsets to UTC and normalize
  Decimal values; input row ordering is canonical.
- Demand wrapper binds qualification, session identity, valid-outbound filter and
  privacy rules to the signed demand summary.
- Cohort uses unique causal session -> outbound -> Affiliate accepted click ->
  transaction membership, global status/acquisition receipt uniqueness and one
  exclusive current transaction status.
- Confirmed EPC uses new-acquisition current confirmed/paid, unreversed amount
  over every valid owned outbound click. Pending, rejected, existing acquisition,
  refund and chargeback never enter the numerator.
- Paid rows, full reversal adjustments, statement period/as-of, gross, reversal,
  fees/tax/withholding, net and paid-transaction set reconcile exactly.
- Producer coverage is partitioned by every funnel/status/payout/day/job/fault
  kind. Counts and identity-set roots are recomputed from the batch; conflict and
  unknown coverage are rejected.
- Unique logical job runs, globally unique attempt receipts and Asia/Tokyo daily
  reconciliation prevent retries from inflating the denominator.
- Exact machine-readable eight fault IDs require unique run, validation and stop
  receipts, frozen target release/artifact/schema, causal injection/detection/
  restore times and exact state restoration. Any failed restore prevents report
  issuance.
- Signed CLI commands assemble/reverify measurement-bound dossiers; legacy
  aggregate/assemble/evaluate commands label themselves `unsigned_diagnostic`.

## Verification

- P12 focused: `20 passed`
- Full Python: `357 passed`
- Generated JSON Schemas: `70`, repeat export byte-identical
- `uv lock --check`: passed, 24 resolved packages
- Python compileall: passed
- Gitleaks directory scan: about 6 MB, no leaks
- Web: local 9, startup boundary 1, production HTTP 3; ESLint passed
- npm audit: 0 vulnerabilities
- CycloneDX SBOM check: passed; existing 649 components / 649 dependency nodes
- Workflow verifier: passed
- Current blocked dossier: `authority=unsigned_diagnostic`, decision `stop`

Fixed audited source hashes:

- `src/saas_preflight/measurement_integrity.py`:
  `4c81eb8b8c77650f9ac9e7a1c537086762a67e913f0fc91378d5fef96d3b611c`
- `tests/test_measurement_integrity.py`:
  `c0d8c3b974db7f0b54df541b71ff154427a188c6aeb48c4c7a5d290c093e4bef`

## Independent refutation

Contract/Storage, Governance and TCO/QA independently tested click omission,
causal inversion, global receipt reuse, timezone aliases, payout timing/set,
unknown acquisition, exact fault failure/identity, retry attempts, per-day job
counts, wrong consumer pin, authority-scope substitution and EPC arithmetic.
No remaining reproduced P12 local blocker was accepted on the final tree.

## Deferred to P13 / external Human gates

- Real source rights and signed complete-export roots
- Real producer identities, KMS/HSM role separation and key rotation
- Approved isolated row-level store, APPI/GDPR decisions, retention/deletion and
  DLP enforcement; hash-only identifiers are not treated as anonymous
- Durable append-only consumer pin/head, rollback detection, shared fencing and
  global STOP latch
- Out-of-process provider adapter and production consumer that refuses every
  naked Evidence/Dossier path
- Actual JP/ja demand, approved Affiliate partners, 30-day cohort/shadow data and
  observed EPC

An authorized producer/indexer plus a consumer pin administrator can still
collude to rotate a complete bundle. That is an external trust, key-management
and durable-head problem, not evidence that the real measurement gate passed.
P13 must close it before any production activation.
