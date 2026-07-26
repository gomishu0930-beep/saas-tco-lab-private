# P14 Crash-safe provider evidence

## Scope

P14 closes a local crash-recovery gap in P13. A verified provider receipt is now committed to the authenticated P13
store before the independent probe, P11 success receipt and P13 terminal result. The receipt records a fact; it does
not grant authority and cannot by itself produce `SUCCEEDED`.

This remains a credential-free, same-host proof. It does not connect a real provider, perform a network request,
publish a site or claim distributed exactly-once behavior.

## Durable phase order

For a dispatch token whose `fencing_token` is `f`, the only normal sequence is:

| Store phase | Revision | Durable meaning |
|---|---:|---|
| `claimed` | `f` | one request owns the current epoch |
| `dispatched` | `f + 1` | P9–P13 authority was rechecked at redemption |
| `provider_recorded` | `f + 2` | exact signed provider fact is immutable |
| terminal | `f + 3` | success or conservative STOP result was committed |

`provider_recorded` is an internal storage phase, not a public `ConsumptionState`. The independent probe is allowed
only at this phase and only while the token, epoch, policy, P11 claim, P9/P10/P12 authority and activation STOP state
remain current.

## Provider fact journal

Store schema version 2 adds `production_provider_receipts` with:

- one row per request and unique dispatch, receipt and provider-audit hashes;
- a foreign key to the exact dispatch;
- canonical signed receipt JSON and UTC verification time;
- database triggers that reject update and delete;
- inclusion in the whole-state HMAC, event hash chain and external monotonic anchor.

The provider call runs while the cooperative store file lock is held. After the child returns, P14 validates the
strict model, signature, token binding, chronology and current authority again, then inserts the fact and advances the
store exactly once. A duplicate call at `provider_recorded` returns the stored receipt without invoking the child and
without changing the revision. There is no public terminal API that can introduce an unjournaled provider receipt.

## Owner and restart behavior

The process that wins `claim` also holds a non-blocking OS owner lock until terminal commit or explicit `close()`.
A second live opener may inspect the authenticated snapshot but cannot redeem, invoke or terminate that request, and
does not start crash recovery. Four-process contention has one claim owner in the local acceptance fixture.
Ownership is PID-bound. After `fork`, the child closes only its inherited descriptor copy without issuing `LOCK_UN`,
resets its local owner state and cannot continue the parent's request. If the parent then dies, a still-live forked
child does not retain the lease and prevent conservative recovery.

If the owner is gone and an in-flight row remains, the next opener performs one recovery transaction:

1. preserve the exact journaled provider receipt, if one exists;
2. create terminal `UNKNOWN` with no probe or P11 success receipt;
3. assert sticky STOP;
4. advance the epoch once and append one recovery event;
5. never rerun the provider and never promote the recovered result later.

A crash before provider journaling creates `UNKNOWN` without inventing a receipt. A crash after the SQLite journal
commit but before external-anchor publication is handled by the existing one-revision-ahead recovery; the following
terminal result is still `UNKNOWN + STOP` and carries the stored fact.

## Success remains stricter than evidence

`SUCCEEDED` still requires all of the following in the current epoch:

- exact P9 serving lease, P10 public authorization, P11 Human-approved durable claim and P12 bound dossier;
- the exact journaled provider receipt with successful expected transition;
- a current independent probe of the expected post-state;
- an authoritative P11 action receipt cross-bound to both provider operation and provider audit hashes;
- one exact P13 terminal commit while activation is not stopped.

Provider, probe and P11 receipts are factual inputs. None is a replacement for the terminal authority check.

## Store compatibility

Schema version 1 is not migrated automatically. An ordinary version-1 open fails closed. Production migration would
need a separately reviewed offline procedure, backup/restore rehearsal, new external anchor and Human approval.

## Residual production gates

P14 does not prove or supply:

- atomicity between a remote provider mutation and delivery of its signed receipt;
- remote conditional fencing or provider-side exactly-once idempotency;
- a transaction spanning the P11 and P13 databases;
- multi-host consensus, distributed leases or multi-region recovery;
- KMS/HSM key isolation, hostile same-user process isolation or trusted time;
- real provider readback, credentials, egress policy, deploy, publication or rollback.

Any ambiguity before exact P13 terminal success remains `UNKNOWN + STOP`. Reconciliation may preserve facts but must
not retroactively promote an ambiguous execution.

See `docs/P14_ACCEPTANCE_TESTS.md` for the local counterexamples and `docs/NEXT_IMPLEMENTATION_HANDOFF.md` for the
separate Human/external gates.
