# P13 Work Packet: Two-stage production consumer and provider boundary

## Objective

Implement the last credential-free production boundary: a local consumer that refuses every naked/unsigned
artifact, verifies P10 release authorization plus P9 serving lease and P12 measurement-bound dossier under
independent fixed pins, applies one durable global STOP/fencing state before any provider call, and exposes a strict
out-of-process adapter contract with idempotent postcondition receipts. No real provider, credential, deployment,
publication, application, email or external write is connected.

## Ownership

- Contract/Storage: durable global state, epoch/fencing token, append-only command/result journal, restart/replay,
  crash/fork/tamper behavior and exact schema/hash pins.
- Governance: STOP precedence, Human reset scope, separation of release/measurement/provider authority, privacy and
  external-action constraints, honest local-vs-production claims.
- TCO/QA: two-stage authorization counterexamples, stale/future/expiry, naked dossier bypass, conflicting epoch,
  duplicate delivery, partial/unknown postcondition, process restart and fail-closed properties.
- Integration/Release (root): consumer API, provider protocol, local subprocess fixture, docs/schema/workflow and full
  regression.

## Required local contracts

1. Activation uses consumer-owned pins for P9 controller/lease, P10 release-assurance policy/trust/controller and P12
   measurement authority; none may be derived from the request being verified. A P11-approved safety disable is an
   action-discriminated STOP-preserving lane and cannot carry or create activation authority.
2. A typed `ProductionConsumptionRequest` binding exact release authorization, serving lease, measurement-bound
   dossier, release/property/measurement scope, desired provider operation and idempotency key.
3. A durable `GlobalStopStore` with fixed store ID, monotonic epoch/fencing token, authenticated append-only head and
   explicit STOP as the default/recovery state. Only a separately signed Human reset under a fixed key may clear STOP.
4. A claim protocol that verifies both authorization stages and current STOP/epoch inside one local CAS boundary,
   rejects replay/fork/rollback and issues one single-use provider dispatch token.
5. A provider adapter protocol that runs outside the consumer process, receives no Human/controller/measurement/
   dispatch private key, verifies the dispatch token and provider-specific allowlist, requires provider idempotency
   and uses only its own dedicated provider receipt key to return signed/hashed
   postcondition facts (`succeeded | failed | partial | unknown`).
6. The consumer commits only exact successful postconditions. Failure, partial, unknown, timeout, malformed receipt,
   process crash or probe mismatch atomically raises/sticks global STOP; no automatic retry may cross an epoch.
7. An actual local subprocess adapter fixture proves the process boundary without network or credentials. The public
   Web runtime remains fail-closed until a real adapter, durable external anchor and Human-approved environment exist.

## Acceptance

- Naked `BusinessDossier`, unsigned diagnostic Evidence, P9 lease alone, P10 authorization alone, or P12 report alone
  can never create a dispatch.
- Wrong policy/trust/run/index/controller/provider/store/epoch/release/property/target/action/idempotency binding,
  future, exact expiry and excessive TTL reject.
- STOP wins over every GO. Reset signed before the current STOP, for another epoch/store/reason, or by another role
  rejects. A reset never replays an old dispatch.
- Same request/idempotency returns the same terminal result; conflicting reuse rejects. Only one claimant wins races.
- DB/companion rollback, process restart, duplicate delivery, provider crash/timeout, forged/partial/unknown receipt,
  and postcondition mismatch fail closed. Successful receipt plus exact probe is required to commit success.
- Deterministic schemas/tests/docs and full Python/Web/SBOM/lock/secret/workflow checks pass.
- Business/public state remains `STOP`; real external connection remains a separate Human/KMS/provider approval gate.

## Deferred, not waived

- Real KMS/HSM, transparency service/external consensus anchor and multi-region database.
- Real provider credentials, APIs, webhooks, egress policy, legal/privacy review and incident channel.
- Actual rights approvals, Affiliate approvals, JP demand, 30-day shadow/cohort and observed EPC.
