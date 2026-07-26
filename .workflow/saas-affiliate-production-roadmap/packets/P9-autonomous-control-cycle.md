# P9 Offline autonomous control cycle and dead-man lease

## Ownership

- Implementation: Contract/Storage owns `src/saas_preflight/control_cycle.py`, the minimal P8 report binding extension, controlled runtime integration, focused tests, schema export and runbook.
- Integration: root owns workflow/roadmap integration and final verification.
- Independent verification: TCO/QA performs read-only adversarial review after implementation.

## Objective

Compose the existing evidence-backed business dossier, gold-set acceptance report, immutable release state, scheduler heartbeat, exception queue and monthly Human budget into one deterministic, offline, fail-closed control decision. A passing current release may receive a short-lived, content-bound serving lease. The cycle must never promote, roll back, publish, fetch, persist, deploy or contact an external service.

## Required design

1. Add a strict typed control configuration/heartbeat/report and a pure evaluator with canonical input/report hashes.
2. Bind the gold-set report to its `rights_bundle_sha256`; reject a mismatch with the dossier rights receipt.
3. For a current release, require dossier/gold/report/release agreement on rights bundle, affiliate bundle and accepted candidate-batch snapshot.
4. Re-evaluate dossier freshness/economics and release visibility at the cycle time; never trust caller-supplied readiness booleans.
5. Fail closed for future/stale heartbeat, excessive scheduler lag, future/stale gold report, open SEV0/SEV1 faults, wrong/missing current-month Human budget, exhausted budget, hidden/expired release or hash mismatch.
6. Distinguish `stop`, `hold`, `human_approval_required` and `maintain_current`. No result may encode an automatic promotion action.
7. Issue a serving lease only for `maintain_current`. Bind it to release ID, manifest hash and artifact hash; expire it no later than the configured lease, heartbeat deadline, next schedule deadline, dossier/gold evidence deadline and release shortest expiry.
8. Add a production-controlled runtime boundary that returns generic 503 for protected content if the lease is missing, denied, mismatched, future or expired. Keep `/healthz` and `/robots.txt` safe and non-sensitive.
9. Make identical typed inputs and evaluation time order-invariant and hash-identical. Outputs contain no URL, source excerpt, credential, Affiliate destination or raw exception summary.
10. Export any new public Pydantic schema deterministically and document the local-only handoff.

## Independent-review hardening addendum

The initial self-hashed lease is not an authenticity boundary. P9 cannot complete until all of the following hold:

11. Use a pinned, audited Ed25519 implementation. A serving lease must be signed by the controller private key outside serialized models and verified against one fixed public verification key at the runtime boundary. A public controller ID plus an unkeyed SHA-256 is insufficient.
12. Runtime verification must cover issuer/key ID, scope, release ID, manifest hash, artifact hash, issued-at, expiry, maximum TTL and the complete signed payload. Recomputed self-hashes, another controller, modified TTL and post-expiry copies must fail.
13. Require separately signed, role-scoped attestations for the accepted GoldSetReport and the current Human release decision. Verify report/manifest hash, rights/candidate or release-event scope, signer role, signer key ID and validity window before issuing a lease.
14. Keep legacy/local preview execution visibly local-only. The production export/entry point must require the verified lease. The current Sites worker must fail closed for every protected/publication route and may expose only non-sensitive health/robots until a separately approved production adapter implements signature verification.
15. A constructed `HumanApproval` or recomputed GoldSetReport hash alone cannot authorize a production serving lease. Missing/invalid attestations must produce no lease.

## Counterexamples

- exact heartbeat/schedule/gold/lease expiry boundaries;
- heartbeat or gold report from the future;
- report rights bundle changed while content hashes remain plausible;
- current release affiliate/rights/candidate-batch substitution;
- open SEV0/SEV1 versus resolved faults and reordered queues;
- stale or wrong-month budget, 576 freeze and 720 exhaustion;
- business `STOP`/`CONTINUE` despite a ready gold set;
- ready candidate without current release returns Human approval required, never promoted;
- exact retry and input ordering produce the same hashes;
- lease copied to another release/artifact or used after expiry returns 503 without protected data.
- arbitrary self-hashed lease with the public controller ID and long expiry;
- wrong Ed25519 key, modified signature/payload/scope and TTL above the configured maximum;
- zero-count forged GoldSetReport with recomputed report hash but no valid TCO/QA attestation;
- unsigned/forged HumanApproval or release-event attestation;
- direct local runtime and Sites worker requests without a signed lease.

## Verification

Run focused tests first, then full Python tests, deterministic schema export, lock, compileall, Gitleaks, Web build/tests/lint/audit and the workflow verifier. Independent QA must report no release blocker before P9 becomes complete.

## External boundary

No account, credential, scheduler, database, secret store, cloud, email, source fetch, Affiliate application, deployment, public URL, promotion or publication is authorized by this packet.
