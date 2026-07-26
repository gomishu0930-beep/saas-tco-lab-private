# P11 Work Packet: External-free execution handoff

## Objective

Audit the current repository against the actual Phase 3–6 path and launch blockers L1–L11. Select and implement the highest-leverage missing control that can be completed without vendor contact, account creation, credentials, source fetch, cloud, deployment, publication, or invented business evidence.

## Role and ownership

- Contract/Storage: inspect typed contracts, schemas, append-only/audit boundaries, and Gate A/B handoff authenticity gaps.
- Governance: map L1–L11 and Human-only decisions to missing machine-verifiable requests, receipts, revocation and execution scopes.
- TCO/QA: inspect Gate C/D, public runtime and revenue-validation coverage; define adversarial acceptance tests for the recommended slice.
- Integration/Release: select the critical-path slice, implement it in new/disjoint modules where possible, integrate CLI/schema/docs/workflow, and run final verification.

## Constraints

1. No external write, email, application, login, account, credential, billing, network source fetch, cloud, deploy, public URL, Affiliate link or production data.
2. Do not convert drafts, requests, synthetic fixtures, unsigned records or public program pages into rights/Affiliate/business approval.
3. Keep Human Approver authority exclusive for rights, external action scope, production keys, deploy and publication.
4. Prefer exact canonical artifacts, role-separated Ed25519 signatures, current-time expiry and replay protection over prose-only checklists.
5. Do not duplicate existing contracts. Identify authoritative evidence for each claimed gap and show why the implementation shortens the path to Phase 6/7.

## Discovery output

Each role reports:

- three concrete missing controls, with authoritative file/line evidence;
- which are impossible without external state and which are locally implementable now;
- one recommended implementation slice, its inputs/outputs, owner and tests;
- counterarguments and residual risk.

## Integration acceptance

1. A requirement-by-requirement gap matrix is saved.
2. The selected slice has a strict typed contract, deterministic hash/schema, fail-closed evaluator and adversarial tests where applicable.
3. Synthetic/current-state examples cannot be mistaken for real approval or production evidence.
4. The public/business decision remains STOP.
5. Full Python/Web/schema/SBOM/lock/compile/lint/audit/secret/workflow verification remains green.

## Selected slice after discovery

Implement a provider-neutral signed external-action lifecycle. It performs no external operation.

Supported exact actions:

1. `send_rights_inquiry`
2. `submit_affiliate_application`
3. `activate_public_release`
4. `disable_public_release`

The common envelope is limited to request/scope/hash/time/idempotency/pre-post-state, signature, revocation and receipt binding. Provider IAM, API payloads and credentials stay outside the repository.

Required contracts and behavior:

- `ExternalActionRequest`: exact action, environment, vendor/property/target/payload hashes, idempotency key, expected pre/post-state, release/manifest/artifact/public-report binding where applicable, not-before/expiry and canonical self-hash.
- `HumanExecutionApproval`: role-separated Human key, exact request/policy binding, only explicit `GO` authorizes execution, decision-record hash and bounded expiry.
- `ControllerExecutionGrant`: controller-signed, one-shot, short-lived grant. `activate_public_release` additionally requires a currently valid P10 public-GO authorization for the same release/manifest/artifact/report.
- `ActionRevocation`: controller-signed safety revocation bound to the exact request/grant and effective time. Revocation can only remove authority.
- `ActionReceipt`: executor-signed hash-only outcome bound to request/grant, start/completion, pre/post state, provider-operation/audit receipt hashes and result. `partial` is never success.
- Fixed downstream runtime: pins policy and controller/executor public keys; rejects report-provided or attacker-provided trust roots.
- Canonical journal/fold: one terminal receipt per request/idempotency/grant, valid predecessor chain, revocation-before-start denial, replay and conflicting receipt rejection.

Required counterexamples:

- wrong key/role/scope/policy/environment/action/vendor/property/release/manifest/artifact/public-report;
- Human `STOP`/`CONDITIONAL`, missing signature, request copy/self-rehash and attacker Authority;
- future, exact expiry, excessive TTL, pre-state drift, revocation race and one-shot replay;
- receipt forgery, partial success, wrong post-state, duplicate idempotency and chain gap/reorder;
- an unsigned request or synthetic P10 STOP can never produce an activation grant.

Deferred, not waived:

- P12 measurement-producer signatures, frozen denominators, required eight fault identities and payout/status reconciliation;
- P13 two-stage P10 public authorization + P9 serving-lease production consumer;
- external provider/KMS/credential/domain/account/deploy and real action execution.
