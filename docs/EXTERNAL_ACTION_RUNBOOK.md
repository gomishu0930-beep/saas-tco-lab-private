# External action authorization runbook

Baseline date: 2026-07-22<br>
P11 status: local contract and authenticated SQLite execution guard implemented; no production execution authority

## 1. Purpose and non-authority

This runbook defines a provider-neutral, machine-verifiable handoff around an external action. It does not
perform an action and does not create a vendor contact, application, account, credential, billing relationship,
cloud resource, deployment, public URL, Affiliate link, source right, business approval or production fact.

The repository remains credential-free and connector-free. A request, Human signature, controller grant,
revocation or receipt is not permission to bypass a provider's terms, account controls, legal review or the
Human-only boundaries in `docs/THREAT_MODEL.md` and `docs/OPERATING_MODEL.md`. Every external execution still
requires an explicit, current Human-approved execution scope for that exact request. A broad project approval,
P10 local readiness, an AI summary, a previous action or a synthetic fixture is not reusable authority.

The current public decision remains `STOP`. The strict local contracts, fixed verifier, authenticated SQLite execution
guard, schemas and synthetic tests are implemented. This must not be cited as proof that a production journal,
provider adapter, credential, production consumer or any external operation exists.

## 2. Exact supported actions

P11 limits the common lifecycle to four closed action identifiers. Unknown values and wildcards are rejected.

| Action | Exact purpose | Required binding | Additional gate |
|---|---|---|---|
| `send_rights_inquiry` | Send one approved rights question set to one identified vendor authority | environment, vendor/target hash, frozen payload hash, policy/request version, expected pre/post-state | Human `GO` for this transmission |
| `submit_affiliate_application` | Submit one frozen application for one property and one Affiliate target | environment, vendor/partner target, property/domain hash, frozen payload hash, expected pre/post-state | Human `GO` for this submission |
| `activate_public_release` | Activate one exact release in one approved production environment | environment/account/domain/config, release, manifest, artifact and P10 public-report authorization hashes, expected current and post-state | Human `GO` plus a current, independently verified P10 public `GO` for the same release/manifest/artifact/report |
| `disable_public_release` | Disable one exact public release in one environment | environment/account/domain/config, current release/manifest/artifact, incident or decision-record hash, expected current and post-state | Human `GO` for this external disable execution |

The payload field is a hash of a separately controlled, frozen payload. Raw mail, form bodies, credentials,
Affiliate URLs, cookies, personal data and provider secrets do not enter the repository contract, journal,
receipt or prompt.

Adding an action requires a new reviewed policy/schema version, counterexamples and Human approval. It must not
be emulated by changing a target, payload or free-text field under an existing action.

## 3. Roles and separation of duties

| Role | May do | Must not do |
|---|---|---|
| Integration/Release requester | Prepare an exact hash-bound request and evidence packet | Approve its own request, widen scope, supply invented evidence or execute without a grant |
| Human Approver | Sign `GO`, `STOP` or `CONDITIONAL` for the exact request and execution scope | Delegate judgment to AI, issue a wildcard scope, or treat `CONDITIONAL` as executable |
| Controller | Recalculate policy, signature, binding, freshness and P10 activation gate; issue a short grant; revoke authority for safety | Make the Human decision, change the request, execute the provider action or turn a revocation into an external side effect |
| Executor | Execute only the exact approved action through a separately approved provider adapter and return a signed hash-only receipt | Select targets, change payloads, reuse grants, infer permission or declare success without the required post-state |
| Downstream verifier/auditor | Pin policy and role keys, fold the append-only journal and verify grants, revocations and receipts | Trust report-provided roots, mutable latest-state claims or an executor's unsigned assertion |

Human-only decisions remain Human-only: rights and ambiguity interpretation, gold labels, Affiliate program and
destination, privacy/legal basis, accounts, credentials, keys, cloud, domain, billing, production writes,
deployment, publication, rollback/disable execution, destructive retention, restore, risk acceptance and
re-enable. Automation may detect and remove authority, stop a local queue and fail closed. It may not approve,
publish, re-enable, choose a rollback target or expand scope.

## 4. Canonical lifecycle artifacts

All timestamps are UTC and use half-open validity (`issued_at <= at < expires_at`). Hashes are canonical SHA-256.
IDs, enum values and ordered collections are strict; unknown fields, duplicate IDs and non-canonical ordering are
rejected.

`ExternalActionPolicy.target_rules` independently pins the exact action, environment hash, vendor/program
identifier where applicable, property-record hash and target hash. Human and controller signatures cannot widen
that allowlist. Only `ExternalActionExecutionGuard.claim()` is execution-start authority: it obtains `at` from
the guard-owned/injected clock and atomically consults durable revocation/idempotency state. The lower-level
`ExternalActionRuntime.verifies_artifacts()` checks signed structure and freshness but must never be called as a substitute
for the guard claim.

### 4.1 `ExternalActionRequest`

The request contains:

- request ID, policy version/hash and one of the four exact actions;
- environment ID and provider/account/target/property/domain/config hashes applicable to the action;
- frozen payload hash, idempotency key, expected pre-state hash and expected post-state hash;
- release, manifest, artifact and P10 public report/authorization hashes when the action is release-bound;
- requester identity, `not_before`, `expires_at` and a canonical self-hash.

The request never contains an access token, password, cookie, live Affiliate destination, raw source body, mail
body or application form content. A copied request with a new self-hash is not a new approval.

### 4.2 `HumanExecutionApproval`

The Human Approver signs the exact request hash, policy hash, action, environment, execution scope, decision
record hash, decision, issue time and expiry with the pinned Human-role key. Only explicit `GO` is executable.
`STOP`, `CONDITIONAL`, missing conditions, non-machine-checkable conditions, expired approval and scope mismatch
fail closed.

### 4.3 P10 activation prerequisite

`activate_public_release` additionally requires a P10 `ReleaseAssuranceReport` that:

1. is public `GO` with a controller authorization;
2. is current at grant issuance and execution start;
3. verifies under the downstream-pinned controller key, policy hash and maximum TTL; and
4. matches the request's release, manifest, artifact and public-report/authorization hashes exactly.

P10 `local ready`, a P10 `STOP`, a copied report, a report from another trust root or a valid report for another
release cannot authorize activation. P10 GO is necessary but not sufficient: the exact Human execution approval
and all P11 checks remain required.

### 4.4 `ControllerExecutionGrant`

The controller signs a short-lived grant after recomputing the request, Human approval, fixed policy/key pins
and time window. The grant binds the request and approval hashes, exact execution scope, P10 authorization when
required, executor key ID, issue/expiry and grant ID. The downstream runtime independently re-proves the Human
GO and, for activation, the current P10 GO; a controller signature alone is insufficient. One-shot behavior is
provided by the separate atomic execution claim, not by treating the grant document as mutable state.

### 4.5 `ActionRevocation`

A controller safety revocation binds the exact request and grant, reason-record hash, issue/effective time and
controller signature. The execution guard registers it monotonically for that grant. It only removes
authority: it does not send a message, withdraw an application, disable a deployment, roll back a release,
change DNS, revoke a provider credential or create any other external side effect.

Consequently, an external `disable_public_release` remains a separate request with its own Human `GO` and grant.
There is no `unrevoke`; recovery uses a new request and a new decision.

### 4.6 `ActionReceipt`

After the guard atomically changes an unclaimed idempotency key to a canonical `ActionExecutionClaim`, the
executor signs a hash-only receipt binding the request, grant, claim, executor key, idempotency key,
start/completion times, observed pre/post-state hashes, result, provider operation-ID hash and provider audit
receipt hash. The completion time comes from the guard-owned clock rather than executor input. The grant binds the Human approval transitively. Allowed terminal results distinguish
`succeeded`, `failed`, `partial` and `unknown`; only `succeeded` with the exact expected post-state may satisfy
the action. Completion must fall within the policy's `maximum_receipt_delay_seconds` from claim; later evidence
is rejected from this terminal contract and requires separate reconciliation.

A receipt proves what the executor signed, not that the provider or external world is truthful. `partial`,
`unknown`, timeout, missing receipt, wrong post-state, provider/audit mismatch or an unsigned receipt is failure
and must not be promoted to success.

### 4.7 Canonical action journal

The verifier folds an append-only predecessor-linked journal beginning `grant -> claim`, followed by at most one
receipt and zero or more revocations in observed append order. A receipt is terminal for factual outcome but not for
authority history: a signed revocation registered after the receipt appends after it without rewriting prior entries.
The guard separates one-time provisioning from fixed-ID reopen. It uses an explicit SQLite file,
companion authenticated anchor, caller-held synthetic/local HMAC key, a separately read/committed monotonic anchor
pin, exact schema fingerprint and `BEGIN IMMEDIATE`
transactions to permit one claim per grant and idempotency key across restart, register revocations, and accept one
exact terminal receipt. Every mutation verifies the state head and schema, checks row count and canonical read-back,
then advances the authenticated revision. The fold requires
the supplied claim/receipt/revocation set to equal that durable state and rejects invalid grant or
revocation signatures, future or non-monotonic entries, gaps, reorder, extra sidecars, duplicate payloads and
wrong-post-state success. A caller-provided "latest revocation state" is not authoritative.

Reopening requires the same state file, companion anchor, store ID, authentication key and exact pin obtained from
the separate monotonic anchor source. A missing file cannot silently
bootstrap; row deletion, metadata mutation, trigger/schema substitution and replacement of the main DB by an older
revision, including a DB+companion pair rollback under a current external pin, are fail-closed. Tests use an in-memory
monotonic pin only; this is not a production trust service. Rollback that also compromises the independent pin/key
source and arbitrary same-process Python introspection are outside this local trust boundary. Production still
requires an out-of-process externally pinned monotonic anchor/KMS, approved shared transactional store, worker
fencing, provider-side idempotency, backup/restore, independently audited journal and trusted clock. Failure to open
or reconcile the configured state is `STOP`, never permission to create an empty guard and continue.

The DB commit, companion-anchor write and external-pin commit are fail-closed but not crash-atomic. Failure in either
gap can make the local store unavailable; it must not be repaired by creating an empty store or lowering the pin.
P13 must supply fenced recovery and a transactionally coordinated external anchor. Python name-mangling is not an
authorization sandbox, so provider credentials and irreversible adapters must live behind an out-of-process service
boundary rather than inside an untrusted plugin sharing this interpreter.

`fold_action_journal()` rejects an invalid supplied chain; it is not itself a global queue latch and does not stop an
unrelated executor process. The production consumer must connect fold/store failure to a durable global STOP/fencing
control before any provider call. Likewise, local claim cardinality does not prove provider-side exactly-once.

The intended state progression is:

```text
requested -> human_go -> granted -> claimed -> succeeded | failed | partial | unknown
                              \-> revoked (before claim)
```

`authority_state` and `outcome_state` are separate. A claim-time or later revocation keeps authority revoked; a
signed receipt may still report the factual outcome of an operation already started. Factual success is never
current permission to execute, serve or retry. Failed, partial and unknown outcomes require reconciliation and a
new request or policy-defined continuation with a new exact approval and grant.

## 5. Operator flow

1. Integration/Release freezes the external payload outside the repository and prepares a hash-only request.
2. The local validator renders the exact action, target, environment, scope, pre/post-state, P10 binding if any,
   idempotency key and expiry. Validation does not contact a provider.
3. The Human Approver reviews the underlying legal/business material and signs the exact request. A chat reply,
   checkbox, AI recommendation or previous approval is insufficient.
4. The controller independently verifies the Human signature, policy, scope and time. For activation it also
   verifies the exact current P10 public GO using a pinned downstream runtime.
5. If and only if every check passes, the controller issues a short grant to one pinned executor key.
   Until a connector, credential and external execution are separately approved, processing stops here.
6. In a later approved production integration, a durable execution guard re-proves request, Human GO, grant and
   current P10 where applicable, checks registered revocations and expected pre-state, then atomically claims the
   grant/idempotency key immediately before one operation. It does not retry an ambiguous result automatically.
7. The executor records a signed hash-only receipt whose completion time is fixed by the guard. Independent postcondition probes and provider audit evidence
   are reconciled before the journal may classify the action as succeeded.
8. Integration/Release hands the receipt, journal head, probes and unresolved residual risk to the Human
   Approver. A receipt does not authorize the next action.

## 6. Kill, containment and recovery

### Kill and containment

1. Stop the local executor queue and reject new grant issuance.
2. Append a controller-signed revocation for every affected pending grant. This prevents later in-scope use but
   does not undo an action already started and does not change external state.
3. Treat missing, stale or ambiguous journal/revocation evidence as revoked and fail closed.
4. Keep protected serving on fixed 503 where the production consumer cannot prove a current authorization.
5. A revocation effective after a valid claim cannot erase a possible external side effect. Preserve the signed
   factual receipt, but quarantine late, duplicate, partial, unknown or wrong-post-state outcomes for
   reconciliation. Do not rewrite or delete them.
6. If an external disable, credential rotation, DNS change, rollback, provider withdrawal or account operation is
   required, prepare a separate exact request and obtain the required Human approval. Do not describe an internal
   revocation as completion of that external operation.

### Recovery

1. Reconcile provider audit evidence and independent probes against the request, grant and receipt. Record
   uncertainty explicitly.
2. Determine whether the external state is unchanged, completely changed or partial. `unknown` is never success.
3. Correct the policy, adapter or payload under a new version; do not mutate the failed request or receipt.
4. Create a new request with a new idempotency decision and expected pre-state. Obtain a new Human decision.
5. Activation or re-enable requires a fresh matching P10 public GO and a fresh Human execution approval. A prior
   grant, revoked grant or serving lease cannot be reused.
6. Restore execution only after the fixed verifier accepts the new chain and the separately approved provider
   controls, credentials, audit and postcondition probes are available.

## 7. Required counterexamples before integration acceptance

- wrong role/key/issuer/policy/action/environment/vendor/property/domain/release/manifest/artifact/report;
- unsigned request, request copy/self-rehash, extra fields, wildcard scope and attacker-controlled trust root;
- Human `STOP`/`CONDITIONAL`, approval reuse, future/not-yet-valid, exact expiry and excessive TTL;
- activation from P10 local-ready or STOP, stale/cross-release P10 authorization and mismatched artifact;
- expected pre-state drift, revocation effective before start, revocation race and one-shot replay;
- duplicate idempotency, chain gap/reorder, conflicting terminal receipts and late receipt;
- wrong executor, forged receipt, `partial`/`unknown`, wrong post-state and provider/audit hash mismatch.

The full implementation must export deterministic strict schemas, reject unknown fields, use fixed downstream
trust roots and keep private keys, payloads and credentials outside serialized artifacts.

## 8. Deferred controls

P11 does not waive or complete:

- **P12 measurement:** producer signatures, frozen denominator/run specifications, the required eight fault
  identities and payout/status/coverage reconciliation;
- **P13 production consumer:** the two-stage P10 public authorization plus P9 serving-lease verifier at the actual
  production edge, provider-specific post-deploy probes and fail-closed adapter;
- provider selection, accounts, KMS/HSM/external monotonic state anchor with crash-safe recovery, credentials, domain, billing, shared production CAS/idempotency store,
  worker fencing, provider idempotency and production audit journal, deployment, public URL, Affiliate
  destination, analytics, source contact or any real action execution.

Those phases require their own evidence and Human approvals. A passing P11 test cannot be substituted for them.
