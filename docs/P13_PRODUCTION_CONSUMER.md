# P13 Production consumer and provider boundary

## Status

P13 is a credential-free local proof. It composes P9–P12 authority, P15 production-readiness authority, a durable
global STOP and a real subprocess boundary with synthetic hash-only provider state. It does not connect a provider,
load a production credential,
deploy, publish, submit an application, send a message or create an account. The business and public decision remains
`STOP`.

## Authority path

Activation has no short path. `ProductionConsumptionRequest` must carry the exact artifacts below and the consumer
revalidates them at claim, redemption, immediately before provider mutation and before the independent probe.

1. P12 `MeasurementBoundDossier` under consumer-owned policy/trust/run/exact-index pins.
2. P10 public `GO` and controller authorization for the same dossier, snapshots, release, manifest and artifact.
3. P9 short-lived serving lease for that exact release tuple.
4. P11 external-action request, separate Human `GO`, controller grant and the exact durable
   `ExternalActionExecutionGuard` claim.
5. P13 provider rule, separate execute/probe executable digests, pinned Python executable, fixed application-source
   closure, allowlist hash, real postcondition-schema artifact, target, exact pre/post-state and idempotency binding.
6. P15 exact production plan, 11 current role-signed environment checks, TCO/QA acceptance, Human environment
   approval and short-lived controller bootstrap authorization for the same P11/P13 stores, property, environment,
   release, adapter/probe closure, capability profile and deployment candidate.
7. P16 v3 full launch-handoff bundle plus packet-external P18, P16 and typed-semantic authority roots. The nested P18 verification includes
   the Storage Auditor-signed P19 one-shot consumption receipt. P13 re-evaluates every P16 receipt,
   the nested P18 bundle, effective expiry, P15 report/TCO components and P10 local-report binding at the final
   subprocess boundary. The request and signed dispatch token carry the exact P18 root, P16 authority, semantic root,
   plan, bundle and semantic-packet hashes; a copied, unconsumed, hash-only or incomplete handoff cannot dispatch.
8. P15 Time Auditor-signed nonce clock attestations and Storage Auditor-signed current-root snapshots. Both callbacks
   are bounded, reject backdating/rollback and are reacquired for every activation phase. Failure before claim persists
   a fenced Global STOP; failure after claim is committed as terminal `UNKNOWN + STOP`.

A copied P11 claim is rejected even if its fields and self-hash are valid: it must exist in the pinned P11 store.
P10 uses `hash_business_dossier()` while P12 has its own signed-artifact hash; the consumer recalculates the P10 hash
from the dossier inside the verified P12 bundle instead of comparing incompatible canonical hash domains.

## Operation-specific STOP semantics

- `activate_public_release` requires P9, P10, P11, P12, P15, P16/P18/P21 semantics and a current `RUNNING` P13 epoch.
- `disable_public_release` requires the exact P11 Human/grant/durable-claim path, but no activation authority. It may
  run while STOP is asserted and never clears STOP. Expired P15 activation authority does not remove this
  Human-approved exposure-reducing lane.
- Rights inquiries and Affiliate applications remain in the P11 Human-controlled boundary. They do not use this
  production release adapter and are not granted P9/P10/P12 authority.

This makes “STOP wins” precise: STOP forbids starting, maintaining or expanding public exposure, while an explicitly
approved exposure-reducing disable remains possible.

## Durable state

`GlobalStopStore` is an authenticated SQLite CAS store with:

- fixed store and policy IDs;
- default STOP at provision;
- monotonic epoch, revision and fencing token;
- HMAC over meta, dispatch, immutable provider-journal and event rows;
- exact schema fingerprint and hash-chained events;
- caller-owned external monotonic anchor checked on every transaction;
- unique request, idempotency and fencing ownership;
- immutable terminal result;
- restart recovery that converts any dead-owner in-flight claim/dispatch/provider-recorded phase to `UNKNOWN`, preserves
  a journaled provider fact, advances the epoch once and asserts STOP;
- one OS-locked in-flight owner per store; a late live opener cannot recover/redeem/terminate it, and duplicate live
  requests return `in progress` rather than a second token;
- redemption that rechecks the current P11 revocation set and atomically converts an authoritative expired, revoked,
  stopped or stale claim to `UNKNOWN`, advances the epoch and asserts STOP; and
- one-revision-ahead recovery for the narrow case where SQLite committed but publication of the authenticated external
  anchor failed. Older, newer or different anchors still fail closed.

Only a reset signed by the fixed, separate reset-Human key can clear STOP. The reset binds the current store, policy,
STOP epoch, revision, head, reason, remediation, reconciliation record, nonce and half-open time window. The named
record must exist in the separate authenticated P15 reconciliation ledger, remain current under its recovery-auditor
signature, exactly match the current P13 store/revision/head/reason and record an independent `NOT_APPLIED` readback.
`APPLIED` and `AMBIGUOUS` records keep STOP until a separate Human-approved disable/remediation produces a new safe
state. The ledger store ID and P15 trust hash are fixed by policy/plan/runtime. An arbitrary 64-character
reconciliation value is insufficient. A reset does not create release authorization, change a pin or replay an old
dispatch.

DB or anchor rollback, schema change, row tamper, missing store, wrong store ID, stale head and anchor-commit ambiguity
fail closed. The local callback used by tests demonstrates the contract; a production external consensus anchor is
still required.

## Subprocess contract

`SubprocessProviderAdapter` uses distinct checked-in execute and read-only probe programs. It pins both program
digests, the selected Python executable, a fixed manifest of all local package modules, the allowlist and the actual
JSON postcondition schema. Each program is opened with `O_NOFOLLOW`, hashed, and executed through the verified file
descriptor. The launcher uses `shell=False`, closed file descriptors, a minimal environment, bounded output and a
new process session; timeout kills the full process group, including forked descendants.

P14 refines the subprocess fence. Execute holds the exclusive cooperative store lock from the final `DISPATCHED`
authority check through provider return, strict receipt verification and immutable journal commit. The independent
probe uses the shared fence only after the store reaches `provider_recorded`. Immediately before either child launch,
the store rechecks the exact request/token row, phase-aware revision, current policy, epoch, half-open expiry, P11
revocation and activation STOP state. Thus an old local token cannot be sent directly to the adapter after STOP or
restart, and a successful terminal result cannot introduce a receipt that bypassed the journal. P15 authorization is
also revalidated at claim, redemption, provider launch, probe launch and terminal success. Activation dispatch expiry
is clipped to the P15 report/authorization and effective P16/P18/semantic expiry.

The activation request and dispatch token use schema v4. Immediately after redemption and before invoking the
provider adapter, P13 independently re-evaluates the retained P16/P18/semantic authority and reacquires signed current roots
from a monotonic resolver, rather than trusting only bootstrap copies or roots accepted from the handoff packet.
Missing consumption/launch receipts, a swapped root/bundle, exact expiry, a different P12 dossier, changed
P15/P10 component, release/manifest/artifact/schema, property/environment, provider target, pre/post/rollback state, legal pages or Affiliate disclosure expectation produces no provider call and sticky STOP. Activation and disable rules must also share the exact adapter, target, probe, runtime, dependency, allowlist and postcondition contract.
The provider journal requires a fresh signed post-provider clock attestation, so an honest completion timestamp after
the pre-call timestamp is verified against the new observation rather than a captured stale time.

Human, release-controller, measurement and dispatcher private keys are never passed to either child. Execute receives
only the provider-result key; probe receives only the distinct readback key. Each parser rejects the other role's key
argument. Success needs:

1. a provider-signed `succeeded` receipt bound to the token, epoch, fence, action, target and idempotency key;
2. an independently signed exact postcondition probe;
3. a P11 executor receipt committed to the authoritative P11 claim; and
4. a P13 terminal success committed in the same current epoch; and
5. current P15 plan/authorization bindings in both the request and dispatch token; and
6. current packet-external P18/P16/semantic roots and exact P16 plan/bundle/semantic-packet bindings in both artifacts.

Failed, partial, unknown, invalid, late, crashed, timed-out or mismatched outcomes become non-success and sticky STOP.
No automatic retry crosses an epoch. An exact duplicate after provider-fact persistence returns the journaled receipt
without invoking the child or advancing revision. The synthetic state also keeps an idempotency ledger and proves one
side effect for a duplicate successful request.

If P11 authority is revoked after provider execution begins, the journaled signed provider receipt remains a factual record,
but P13 commits `UNKNOWN`, omits probe/action success receipts, advances the epoch and asserts STOP. P11 and P13 use
separate authenticated stores, so their commits are not a cross-database transaction. A P11 receipt is evidence that
an external mutation occurred, never standalone release authority; P13 success still requires the exact current P11
receipt plus the P13 terminal commit. A real remote adapter must still prove provider-side conditional fencing and
production-grade reconciliation/outbox semantics before launch. P15 supplies the typed evidence contract and a
separate local reconciliation ledger; it does not turn the local SQLite/flock fixture into a distributed provider
transaction.

Before callback entry, P13 persists an immutable provider-attempt intent and its pre-provider signed authority. If the
callback escapes without an authoritative fact, the store closes the attempt to `UNKNOWN + STOP`. If that close and
the external anchor fail together, the live store object irreversibly loses its capability registration and in-flight
lease; a new opener must recover the durable intent to `UNKNOWN + STOP` before any later launch. The low-level local
callback API remains a cooperative test harness: only the pinned subprocess adapter is deadline bounded, and hostile
same-user Python is outside this security boundary.

## Local verification

```bash
uv run pytest -q tests/test_production_consumer.py
uv run pytest -q
uv run python scripts/export_schemas.py --output-dir schemas
python3 -m compileall -q src tests scripts
```

The fixture scales only synthetic P12 demand/click/commission facts and production-shaped P15 evidence so a positive
authority composition can be tested. These values are not market or production-environment evidence and are not
accepted by the current business dossier.

The local child runs with `-I -S -B`, fixed environment/cwd and no caller `PYTHONPATH`. Its closure manifest hashes all
local `saas_preflight` modules, the base-interpreter standard library and importable files from the eight required
third-party distributions. The manifest is transferred through a passed file descriptor rather than one size-limited
argv. A meta-path guard opens every non-built-in import with no-follow, hashes the opened inode, executes Python source
from those exact verified bytes and loads extension modules through the retained descriptor. Newly added site-packages
modules and hash-to-loader path swaps are rejected. This closes the local import race exercised by the fixture; it does
not replace a reviewed immutable production image, separate OS identity or KMS isolation. On macOS, the base Python
executable itself cannot be launched from a retained `/dev/fd` with this mechanism; therefore the bootstrap executable
and modules imported before the guard is installed remain an explicit same-user trust boundary. A production P13
consumer must run the consumer-pinned interpreter/dependency closure from a read-only immutable image or volume and
revalidate that image/SBOM at P15. The local packet does not claim safety against a concurrent process that can mutate
that bootstrap runtime.

## Production gates still required

- real environment collection and independent signatures for all 11 P15 checks, including provider conditional
  mutation, idempotency retention, exact receipt lookup/readback and approved egress;
- KMS/HSM and non-exportable provider/probe keys;
- production implementations of the typed trusted-clock/current-root callbacks, process identity, external consensus anchor and multi-host fencing;
- a separately isolated provider broker that rechecks durable intent, STOP/epoch/root, revocation and total
  prelaunch-to-completion deadline at the provider mutation boundary;
- immutable/containerized dependency closure and separately permissioned OS identities or KMS ACLs for execute and
  probe (two local files under one OS account prove argument/key-role separation, not hostile-user isolation);
- a shared transaction, durable outbox or reconciler spanning factual provider completion and the P11/P13 stores;
- approved secrets store, privacy/legal review, incident channel and backup/restore drill;
- rights approval, three usable Affiliate programs, JP demand, 30-day shadow/cohort and observed EPC;
- explicit Human approval for account, credential, billing, deployment, domain and publication.

Until all gates pass, the public runtime must return generic 503 for protected content and no real adapter may be
configured.

P14 storage and recovery details are normative in `docs/P14_CRASH_SAFE_EVIDENCE.md`; P15 requirements and nonclaims
are normative in `docs/P15_PRODUCTION_INTEGRATION_READINESS.md`. Neither adds real-provider or distributed guarantees
until current production-environment evidence is supplied.
