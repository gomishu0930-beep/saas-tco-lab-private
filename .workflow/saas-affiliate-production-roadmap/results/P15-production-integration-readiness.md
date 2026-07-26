# P15 Result: Production integration readiness and reconciliation gate

## Status

Technical candidate complete. Business/public state remains `STOP`. Formal P11–P15 Human acceptance and every real
environment/external gate remain pending.

## Delivered

- Exact 11-check, policy-thresholded, role-signed production-readiness model and evaluator.
- Synthetic evidence is permanently non-authoritative; complete synthetic input remains `STOP`.
- TCO/QA, Human and controller attestations with exact artifact, chronology and earliest-expiry binding.
- P13 request/token binding and revalidation at claim, redeem, provider, probe and terminal success.
- Activation expiry clipping while preserving the separately Human-approved disable safety lane.
- Separate authenticated reconciliation ledger with immutable records, HMAC, hash-chain and external-anchor contract.
- Ledger store/trust pins and reset eligibility restricted to current exact `NOT_APPLIED` independent readback.
- Deterministic offline CLI, 105 schemas and deterministic blocked fixture.

## Independent audit closures

- Future-evaluated report could be authorized earlier: fixed with report → TCO/Human → controller chronology.
- Report/authorization could outlive the plan: fixed by plan-expiry clipping and current-plan validation.
- Same-check duplicate order changed bundle/report hashes: fixed by a complete canonical sort key.
- Ledger store/trust could be spliced: fixed in plan, consumer policy and runtime.
- `APPLIED`/`AMBIGUOUS` reconciliation could clear STOP: fixed; only `NOT_APPLIED + keep_stop` is reset-eligible.
- Same idempotency key with a different request was untested: typed rejection and zero-side-effect evidence added.
- Unknown receipt lookup and no-op disable semantics were weak: explicit `not_found`, distinct queries and real state
  transition added.
- Policy boundaries lacked adjacent-fail coverage: threshold and normal/live/recovery TTL boundary tests added.

## Fixed evidence

```text
readiness source  a97dd051758c754f2ac31527f37b9adbd1e3dbe1bf5087afd69538930aa2318d
readiness tests   98699667c0fc645e1ee92064905ba377b8cfb8af4d6bc16d5d3330cdfa930c87
consumer source   04d69871689d1fa53fb5879e4a21e3c2fedd7eac6634ce39245661ddca7c44ab
consumer tests    11e2aab00254ac3262c874227c9987af79e62aa51cf93c60589fb8d286ca8e5d
schema set        323f273593b0a8f2839992714af23f117faca760afc19b6793ca6bdef7c4dde0
```

- P15 focused: 105 passed.
- P13/P14/P15 consumer focused: 52 passed.
- Python full suite: 514 passed.
- Schema/fixture repeat generation, expected CLI STOP/exit 3, compileall, lock check, workflow verification and secret
  scan: passed.

## Residual limits

The ledger is a same-host local SQLite/flock contract and the external anchor in tests is an in-memory callback. No
real provider, credential, KMS, trusted clock, shared multi-host store, remote anchor, egress rule, backup/restore,
deployment or public mutation was exercised. Signed evidence cannot by itself prove the truthfulness or continuing
availability of those external systems. Rights, Affiliate availability, JP demand, 30-day shadow and observed EPC
also remain unproven.
