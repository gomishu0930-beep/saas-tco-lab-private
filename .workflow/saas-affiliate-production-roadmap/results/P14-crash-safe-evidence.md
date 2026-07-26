# P14 Result: Crash-safe provider evidence and conformance

## Outcome

Credential-free technical candidate complete. Public/business state remains `STOP`; formal P11–P14 local acceptance
remains `PENDING` and no external provider, credential, network mutation, deploy or publication was performed.

## Implemented

- authenticated schema-v2 provider-fact journal with immutable update/delete triggers;
- HMAC, hash-chain and external-anchor coverage of the canonical provider receipt;
- exclusive authority check → provider call → receipt validation → journal transition;
- phase-aware `f`, `f+1`, `f+2`, `f+3` claim/redeem/journal/terminal fencing;
- exact duplicate as revision-neutral read and conflicting terminal receipt rejection;
- dead-owner recovery to one `UNKNOWN + STOP` event/epoch while preserving any journaled fact;
- PID-bound same-host owner lock and `after_in_child` descriptor reset without unlocking the parent;
- probe chronology requiring provider-journal verification before probe;
- ordinary schema-v1 open refusal without implicit migration.

## Counterexamples

- 4-process one-owner claim, live late opener and parent-death/fork-child lease behavior;
- actual provider call followed by pre-journal `os._exit`, with call count 1 and no invented fact/retry;
- post-journal restart and one-ahead external-anchor outage;
- wrong provider key, alternate-policy dispatch binding and valid signed conflicting receipt;
- valid P9 lease and P10 public-report artifact substitution;
- postcondition-schema mutation, direct unjournaled terminal injection and journal update/delete.

## Fixed evidence

```text
source 15c9a936bb6a213972c19d279eb3f415b4ab1d4980cbb3e49ee5ad51ae20e0f6
tests  8cb91d383120d9691423af89fc4246d53a93f2281b10819a0154f46f6e2b84a6
```

- focused: 42 passed;
- full Python: 399 passed;
- schemas: 80, repeat byte-identical;
- compile, uv lock, workflow verifier and Gitleaks: passed;
- Web local/startup/production build/tests and ESLint: passed;
- npm audit: 0 after `sharp` 0.35.3 override;
- SBOM: 651 components/nodes, SHA-256
  `a860dd9810e1fb76f75198ff23870c4c4b271609670124aa90dd9ee803595c13`;
- independent Contract/Storage and TCO/QA final audits: PASS, no local release-evidence blocker.

## Residual production gates

Remote mutation-to-receipt atomicity, provider-side idempotency/readback, cross-store P11/P13 coordination,
multi-host consensus/fencing, KMS identities, trusted time, backup/restore and real incident disable remain separate
Human-approved environment acceptance tests. Ambiguity cannot be retroactively promoted from `UNKNOWN` to success.
