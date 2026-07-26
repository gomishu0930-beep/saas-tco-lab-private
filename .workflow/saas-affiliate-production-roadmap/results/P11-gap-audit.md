# P11 Result: External-action gap audit and selected handoff

Historical status at checkpoint: discovery and design recorded; root integration was not yet certified

Final integration note (2026-07-22): the selected local slice is now implemented and independently audited. The
completion evidence, verified counts, fixed findings and remaining production blockers are recorded in
`results/P11-external-action-boundary.md`. The rest of this file is preserved as the pre-implementation gap audit;
its statements that code or root integration were incomplete describe that earlier checkpoint, not current state.

## Decision

The three-role audit selected a provider-neutral signed external-action lifecycle as the highest-leverage local
slice. It can make the Human-to-executor handoff machine-verifiable without contacting a vendor, creating an
account, loading a credential or performing an external operation.

This result does not claim that P11 code, schemas, CLI, tests, examples, journal or production adapters are
complete. Root integration and full verification must establish that separately. The business/public decision
remains `STOP`.

## Three-role gap audit

| Audit role | Repository finding | Recommended control | Limitation raised |
|---|---|---|---|
| Contract/Storage | Strict source, Affiliate, evidence, append-only snapshot and release contracts exist, but there is no authoritative request-to-external-receipt chain for vendor inquiry or application activity | Canonical request, idempotency, predecessor-linked append-only action journal, executor receipt and pre/post-state binding | A local receipt or hash cannot create provider authority or prove an external result |
| Governance | P10 strongly binds technical evidence, dossier, Human public GO and controller authorization, while its runbook explicitly requires a separate Human-approved execution scope for accounts, cloud, domain, credentials, deploy and publication | Exact Human-signed execution scope, role-separated controller grant, monotonic revocation and fixed downstream trust roots | Revocation must never be described as an external disable, rollback or credential operation |
| TCO/QA | P10 checks local assurance, but production measurement producers, exact fault identities and the deployed two-stage authorization/lease consumer remain outside P11 | Adversarial lifecycle tests now; preserve P12 measurement and P13 consumer as separate gates | A valid action lifecycle cannot repair fabricated measurement or a bypassable production consumer |

## Exactly three control gaps

1. **Authoritative external business/legal evidence.** Real three-vendor rights, Affiliate approvals, Human gold,
   JP/ja demand, mature cohort, 30-day operations and privacy/legal decisions require external evidence. Local
   contracts can reject bad inputs but cannot manufacture authenticity.
2. **Production substrate and independent proof.** KMS/non-exportable keys, production datastore and journal,
   backup/restore, hosting/domain/DNS/WAF, redirect/analytics controls, protected CI/runner, artifact provenance,
   provider audit and deployed probes require later provider-specific integration and Human approval.
3. **Machine-verifiable external-action lifecycle.** The repository has signed release assurance and local pure
   transitions, but it lacks one exact chain joining action request, Human execution approval, controller grant,
   revocation, executor receipt, idempotency and observed pre/post-state. This is locally implementable without
   granting or exercising external authority and is therefore selected for P11.

The first two gaps are not closed by P11. They remain launch blockers. The third is the selected local slice.

## Conflict resolution

### Scope breadth

Governance initially favored release activation/disable as the narrow public critical path. Contract/Storage
showed that the first real Gate A/B operations also need auditable handoff. The selected closed action set is:

1. `send_rights_inquiry`
2. `submit_affiliate_application`
3. `activate_public_release`
4. `disable_public_release`

No generic command, arbitrary URL, provider payload, shell command or wildcard action is allowed. New actions
require a new policy/schema version and review.

### Meaning of revocation

An automated controller may remove pending authority for safety. It may not use revocation to claim that a
message was withdrawn, an application was cancelled, a deployment was disabled, DNS was changed, a credential
was revoked or a release was rolled back. Every external action, including `disable_public_release`, still
requires its own exact request, explicit Human `GO`, current scope and approved execution path. There is no
`unrevoke`; recovery creates a new request and decision.

### Meaning of a receipt

A signed receipt proves only what the pinned executor signed. It does not prove provider truth, legal authority
or the external post-state. `partial`, `unknown`, missing, late, conflicting or wrong-post-state receipts fail.
Provider audit evidence and independent probes remain required in production.

### Priority against P12 and P13

TCO/QA correctly identified measurement-producer authenticity and the deployed consumer as independent critical
risks. They are deferred, not waived. P11 is sequenced first because no vendor contact, Affiliate application or
production action should cross the Human boundary without a bounded request/grant/receipt path. P12 and P13 must
still pass before their corresponding launch blockers can close.

## Selected lifecycle

```text
ExternalActionRequest
  -> HumanExecutionApproval (exact request and scope; GO only)
  -> ControllerExecutionGrant (one-shot, short TTL, fixed policy/keys)
  -> approved executor start
  -> ActionReceipt (signed pre/post-state and provider/audit hashes)

Controller ActionRevocation
  -> removes pending request/grant authority only
  -> never performs or proves an external side effect
```

The canonical journal rejects gaps, reorder, replay, duplicate idempotency and conflicting terminal receipts.
Activation has an additional hard gate: a current P10 public `GO` authorization must verify under the pinned
P10 runtime and match the exact release, manifest, artifact and public report in the request. P10 local readiness
or `STOP` cannot produce an activation grant. P10 GO alone is not an execution approval.

## Human-only boundary

The Human Approver exclusively decides rights and ambiguity, gold acceptance, Affiliate program/destination,
privacy/legal basis, external accounts/credentials/keys/cloud/domain/billing, production writes, deployment,
publication, rollback/disable execution, destructive retention/restore, exception/risk acceptance, recovery
re-enable and final `GO | STOP | CONDITIONAL` scope and expiry.

AI and automation may prepare a candidate request, validate, calculate, detect, stop a local queue, revoke
pending authority and verify a receipt. They may not sign Human approval, change a target/payload/scope, turn
`CONDITIONAL` into GO, execute through an unapproved connector, publish, roll back, re-enable or infer authority
from a previous approval.

## Connector, credential and execution boundary

P11 stores hashes and signatures only. It does not add a provider SDK, MCP, browser automation, mail sender,
application submitter, deploy API, DNS API, cloud account, secret, token, cookie, private provider ID, Affiliate
URL, production database or external write. A future adapter must receive separate Human approval and
least-privilege credentials outside repository artifacts.

Until that approval exists, the lifecycle must stop before execution even if a local request, Human test
signature and controller grant validate. Synthetic examples are not evidence that an external action occurred.

## Operator, kill and recovery handoff

1. Requester freezes the external payload outside the repository and creates an exact hash-only request.
2. Human reviews the real legal/business material and signs the exact execution scope.
3. Controller recomputes policy, key, scope, time, idempotency, journal, revocation and, for activation, P10 GO.
4. A grant is one-shot and executor-bound. No approved connector/credential means stop before execution.
5. The executor must check current pre-state immediately before a later approved external operation and return a
   signed receipt. Ambiguous results are not retried automatically.
6. Kill begins by stopping the queue and appending revocations for pending grants. This removes authority only.
7. Any required external disable, withdrawal, key rotation, DNS change or rollback is a new explicitly approved
   action, not an implicit consequence of revocation.
8. Recovery reconciles provider audit and independent probes, records partial/unknown state, versions any fix,
   and starts from a new request, Human approval and grant. Activation/re-enable also needs a fresh matching P10
   public GO.

## Residual risk

- Human, controller and executor collusion can produce internally valid but dishonest artifacts.
- A compromised executor or provider can act outside the protocol or lie in a receipt.
- Revocation cannot undo a side effect already started, and a short valid window still has race risk.
- Provider consoles, IAM, DNS, caches, search indexes and downstream systems may diverge from repository state.
- Hash-only payload binding does not prove that the out-of-repository payload shown to the Human is the payload
  sent unless the future executor and provider audit bind the same bytes.
- A generic envelope can create false confidence if it hides provider-specific IAM, API semantics or partial
  failure modes.

The mitigation is to keep the envelope narrow, retain provider-specific adapters and receipts, use
least-privilege/JIT identities, short TTLs, immutable external audit, independent postcondition probes and
fail-closed recovery. No residual risk is accepted for public operation by this document.

## Deferred, not waived

- **P12:** measurement-producer signatures, frozen denominators/run specification, required eight fault
  identities and payout/status/coverage reconciliation.
- **P13:** deployed consumer for the two-stage P10 public authorization plus P9 serving lease, with actual edge
  fail-closed behavior and provider-specific probes.
- All real accounts, provider selection, KMS, credentials, domain, billing, source contact, Affiliate application,
  deployment, publication, redirect, analytics and production execution.

## Root integration acceptance still required

- strict frozen typed contracts and closed enums for all lifecycle artifacts;
- deterministic canonical hashes and exported JSON Schemas with unknown-field rejection;
- fixed policy and controller/Human/executor keys, bounded TTL and half-open expiry;
- append-only journal/fold and exact idempotency, predecessor, revocation and terminal-state rules;
- activation bound to the independently verified exact P10 public GO;
- adversarial tests for wrong scope/key/policy/environment/binding, STOP/CONDITIONAL, replay, expiry, pre-state
  drift, revocation race, receipt forgery, partial/unknown, wrong post-state and journal conflict;
- full Python, Web, schema, SBOM, lock, compile, lint, dependency, secret and workflow verification;
- explicit confirmation that current-state fixtures remain public `STOP` and no external operation occurred.

Until root integration records those results, this artifact is a gap audit and design handoff, not completion
evidence.
