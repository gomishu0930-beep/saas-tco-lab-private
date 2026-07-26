# P11 Result: Authenticated local external-action boundary

## Outcome

P11 implements a provider-neutral, external-call-free handoff for exactly four actions:
`send_rights_inquiry`, `submit_affiliate_application`, `activate_public_release`, and
`disable_public_release`. It does not send, submit, deploy, publish, disable, fetch, load a credential, or create
an account. The current business/public decision remains `STOP`.

The local boundary requires an exact self-hashed request, exact Human `GO`, controller-signed short grant, fixed
policy/trust/target allowlist, and current P10 public authorization for activation. The only public start boundary
is `ExternalActionExecutionGuard.claim()`; the lower-level artifact verifier is not execution authority.

## Durable local state

- Guard provisioning and reopen are separate; a missing configured store cannot become an empty recovery store.
- SQLite uses fixed store identity, strict exact schema, `BEGIN IMMEDIATE`, grant/request/idempotency uniqueness,
  row-count and canonical read-back checks.
- A caller-held HMAC key authenticates the logical state head. A companion authenticated anchor and separately
  read/committed monotonic pin bind generation and revision, including DB+companion rollback detection.
- Claim and receipt clocks are sampled inside the store/file-lock CAS. Expiry or receipt-delay boundaries cannot
  be bypassed by waiting on the lock with an earlier timestamp.
- Revocation is monotonic and remains recordable after claim or receipt. Authority state and factual outcome are
  separate, so a late revocation can coexist with a truthful succeeded/failed/partial/unknown receipt.
- Journal reports bind store ID, state revision, external anchor hash and chain head. Fold uses one immutable
  snapshot and rejects a concurrent durable change before return. A receipt ends the outcome, not the append-only
  authority history; later revocations append without rewriting the receipt.

## Counterexamples closed

- wrong/attacker role, key, policy, scope, target, environment, vendor, property, P10 report and post-state;
- Human `STOP`/`CONDITIONAL`, future and exact-expiry authority, excessive TTL and caller-controlled clock;
- same grant, same request ID with changed payload, and duplicate idempotency replay;
- missing store, row deletion, metadata mutation, trigger/schema substitution, main-DB rollback and
  DB+companion rollback under a current external pin;
- two guards racing for one claim, lock-wait expiry, late receipt commit, receipt/revocation arrival-order changes;
- forged/conflicting receipts, missing durable sidecars, chain gaps/reorder, future fold and fold/revocation TOCTOU.

## Verification

- P11 focused: 50 passed.
- Python full: 337 passed.
- JSON Schema: 49 files, repeated export byte-identical.
- `compileall`: passed.
- Web: local 9, startup boundary 1, production actual-HTTP 3; ESLint passed and no residual production process.
- npm audit: 0 after updating transitive `fast-uri` to 3.1.4. Current 649-component/649-node SBOM SHA-256 is
  `d0d53f29420e8b7f0fcbf6d2113b704d986737bae11c46b8efbef935c7a39932` and `--check` passes.
- `uv lock --check`, Gitleaks (5.39 MB, 0 leaks) and workflow verification passed.
- Contract/Storage, Governance and TCO/QA independently reproduced the adversarial cases and found no remaining
  authority blocker within the documented local trusted-process boundary.

## Boundary and deferred controls

Python name-mangling is not a hostile-code sandbox. The local in-memory monotonic pin used by tests is not a
production trust service. The DB commit, companion-anchor update and external-pin commit fail closed but are not
one crash-atomic transaction; interruption can require recovery and must never be repaired by lowering the pin or
creating an empty store.

P13 must therefore place credentials and irreversible provider adapters behind an out-of-process, least-privilege
boundary with durable external monotonic anchoring/KMS, shared transactional state, worker fencing, provider
idempotency, pre-call authority/current-state readback, global STOP latch, backup/restore and independent provider
audit/probes. P12 must first close measurement-producer signature, frozen denominator, exact eight-fault identity,
status/payout and funnel reconciliation gaps. Neither phase is waived by P11.
