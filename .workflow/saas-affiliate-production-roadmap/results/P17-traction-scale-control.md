# P17 Result: traction and scale control ledger

## Outcome

Implemented the credential-free Phase 7–8 control plane. A complete P12 packet is rerun at ingestion, minimized into a
signed 30-day observation, appended to an authenticated local ledger, reconciled with signed post-window settlement
amendments, and evaluated as STOP, CONTINUE_OBSERVATION, or READY_FOR_SCALE_REVIEW. Every output has authority `none`.

## Role integration

- Contract/Storage implemented and tested the original-cohort-bound Settlement Amendment, zero-event completeness,
  replay neutrality, positive/negative deltas and per-partner reconciliation.
- TCO/QA fixed the cumulative/latest split, exact formulas, decision precedence and boundary matrix.
- Integration/Release connected the complete P12 runtime, HMAC-minimized identities, Human plan and consumer pins,
  SQLite ledger, settlement evaluation, CLI, schemas, fixtures, roadmap and acceptance artifacts.

## Safety properties

- No network, account, credential, billing, provider, publication, deploy, affiliate mutation or spend path exists.
- P12 report counts are not copied. The run plan, all three batches and attestations, bundle index and report are rerun
  and cross-bound at the original ingestion instant.
- Settlement cannot be asserted by a caller boolean. Each contributing window needs a current producer amendment and
  independent TCO/QA COMPLETE attestation observed through the fixed 30-day settlement lag.
- A no-change cohort still requires a signed zero-event complete export. Empty amendment lists do not prove completion.
- Original transaction identity, cohort, partner, currency and amount remain immutable; valid reversals may reduce EPC.
- Observation history uses 0600 SQLite, STRICT schema, immutable triggers, file lock, `BEGIN IMMEDIATE`, HMAC state,
  predecessor chain and external monotonic anchor. Exact replay is revision-neutral and conflicts fail closed.
- Every operational target is followed by a post-anchor finalization event. The sole unfinalized tail can be recovered;
  evidence recovered at or after expiry becomes an immutable expired tombstone and is excluded from active projection.
- Trusted-clock callbacks are revision/head/purpose/subject/nonce bound and timeout under a host-global root-inode flock.
  Fork cleanup and a one-shot descriptor lease prevent orphan locks, double-close, FD-reuse corruption and concurrent
  callbacks across instances, hardlinks and processes. Setup, post-start and ownership-notification failures are covered.
- The raw latest settlement ordinal controls recency. An expired latest snapshot cannot fall back to older accepted
  revenue; exact Decimal and cross-multiplied gates avoid rounded READY decisions.
- Empty or synthetic evidence cannot reach scale review. Mature incomplete settlement is STOP. Review readiness never
  grants spend, release, publication, merchant change or external mutation authority.

## Exact fixed artifacts

- `src/saas_preflight/traction_control.py`: `f7e73dd88de7f61ee0b69fc420a9856508d3c046428feb38b6c8b819348ae5d4`
- `tests/test_traction_control.py`: `b7e545cf088382b1b79fccf883b55fa873efd02e5b3f99518fcd00dd9dbb95dc`
- `src/saas_preflight/settlement_amendment.py`: `83db3c4be0ba431eae7c3dbb1d76faa7471fbd20c56b6afb18cc1def1ed3f793`
- `tests/test_settlement_amendment.py`: `3dfae9e1405d12ffdcf0e9c53eaefb69ac080772d986e7404c42d46362e693e5`
- `docs/P17_BOUNDARY_MATRIX.md`: `8917ebbed06bd61ea2d10800edceb8a2fd74c5384246aa003114738313b8be56`

## Verification record

- Focused P12/P17/settlement: 72 passed; P17 traction file contains 38 tests.
- Split full Python verification: 616 passed without overlap (526 base + 38 traction + 52 production consumer).
- 137 JSON Schemas: two exports and checked-in set byte-identical.
- P17 blocked fixture: eight files, two generations and checked-in set byte-identical; local CLI returns exit 3/STOP.
- `uv lock --check`, compileall, workflow verifier and `git diff --check`: passed.
- Gitleaks: 9.58 MB, no leaks.
- Web: 13 tests, ESLint, production build and npm audit (0 vulnerabilities): passed.
- Contract/Storage and TCO/QA independently reproduced all three former FD/worker blockers on the final hashes and
  reported PASS. Contract/Storage also passed nine targeted attacks; the final registry and root lock were empty/free.

## Unfinished external state

Formal P11–P17 Human repo acceptance is PENDING. Real rights, three affiliate approvals, JP demand, production provider,
KMS/anchor/clock/store, publish approval, six possible observation windows and complete settlement exports do not exist.
Business, public and scale states therefore remain STOP.
