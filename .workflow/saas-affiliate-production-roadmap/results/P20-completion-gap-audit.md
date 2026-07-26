# P20 Result — LOCAL IMPLEMENTATION COMPLETE / BUSINESS STOP

## Decision

The original business objective is **not complete** and remains `STOP`. The repository is a strong credential-free
control-plane candidate; it is not evidence of a market, approved affiliate inventory, a public property, autonomous
production operation, or revenue. Current checked-in STOP fixtures directly contradict any claim that launch or the
JPY 200,000 monthly net-profit target has already been achieved.

## Requirement evidence matrix

| Original requirement | Required direct evidence | Current direct evidence | Class | Mechanical resume condition |
|---|---|---|---|---|
| Field-level rights for at least 3 vendors | current Human-approved fetch/derive/display/history/retention records tied to exact fields and sources | approved vendors: 0 | external governance input | three non-expired signed rights decisions pass P1/P5/P16 |
| Usable affiliate supply for at least 3 vendors | accepted program/account decisions and publishable CTA/program hashes | accepted partners: 0 | external account/contract input | three distinct accepted partners pass dossier and P16 |
| Qualified Japanese demand | deduplicated authoritative query/export data for the fixed property and period | qualified demand records: 0 | external measurement input | signed P12 demand producer batch passes Gate C |
| Correct comparison inventory | Human gold labels plus current approved source evidence for 3 vendors × 6 plans | synthetic/local gold contract only | mixed | rights inputs plus real labels pass P8 without quarantine |
| Public noindex/indexable MVP | approved repo revision, domain/account, deployment and publication receipts | no domain, deployment, publication or public readback | external mutation input | P18 acceptance, P15 environment evidence and P16 Gate 8 all pass |
| 80% autonomous routine operation | 30-day signed task schedule/execution/human-activity ledger | observations: 0; automation undefined | external runtime evidence | at least one complete 30-day P12/P17 observation at >=80% |
| Confirmed EPC | settled transactions joined to all valid affiliate clicks | clicks: 0; settled revenue: 0; EPC undefined | external settlement input | complete signed cohort and amendments produce EPC >= JPY 60 |
| JPY 200,000 monthly net operating profit | settled revenue minus measured labor and resource cost | revenue/cost observation absent; capacity undefined | external business result | mature P17 window passes exact net-profit and bear-capacity gates |
| Safe production mutation | provider-native CAS/idempotency/lookup, independent readback, KMS, clock/root, anchor, shared fencing | only synthetic/local contracts; real provider deliberately disconnected | external environment plus local contracts | all exact P15 evidence and provider conformance checks pass |
| Credential-free control plane | fail-closed models, deterministic evaluation, local MVP and immutable evidence contracts | implemented P1–P19 candidate; public/business authority remains none | locally achieved for declared scope | immutable runner and independent Human P18 acceptance still required |

The diagnostic commands `evaluate-readiness` and `evaluate-traction` currently return STOP because the rights,
affiliate, demand, observation and settlement collections are empty. A complete-looking signature chain cannot
substitute for the missing semantic business facts.

## Accepted local remediation in P20

1. **P13 provider execution boundary** — removed the public arbitrary callback path. The store now accepts only an
   exact immutable, one-shot subprocess execution port bound to request, token, adapter closure, timeout and output
   limits. One monotonic deadline covers pre-provider work and communication. A fake structural port is rejected
   before attempt intent, revision, epoch or provider state changes.
2. **P17 bounded coordination** — process-shared file lock and every external anchor read/commit use fixed deadlines.
   After a caller timeout, a dedicated process-shared anchor lock remains owned by the callback worker until the real
   callback exits. A retry cannot overlap the old commit or roll a newer revision back; explicit retry/reopen after
   callback completion preserves one-ahead recovery. Cross-host ordering still requires provider-side CAS.
3. **Authenticated pricing storage v2** — added exact schema fingerprint, HMAC state, immutable row hash chain,
   external idempotent CAS anchor, rollback detection, one-ahead recovery, anchor-timeout quarantine and trusted
   insert/read-time retention enforcement. Trusted time is obtained inside the repository and every forward time is
   durably HMAC/CAS anchored, including rejected writes. One database accepts exactly one effective retention cohort.
   Legacy storage remains only for local compatibility; production acceptance must select v2 with external
   KMS/anchor authority.
4. **Repository scope v2** — retained historical `p11-p18-local-candidate-v1` and introduced
   `p11-p20-local-candidate-v2` so P19/P20 paths cannot be accepted under the older name.
5. **Immutable-runner floors** — raised Python partitions to base 506, traction 57 and production-consumer 77 after
   collecting the exact current partitions.

## Rejected shortcuts

- X posts, unsigned screenshots, synthetic fixtures, self-declared booleans and arbitrary signed hashes are not
  authoritative market or revenue evidence.
- Pending/rejected transactions never enter settled revenue; an empty denominator never becomes EPC zero/pass.
- Local noindex rendering is not public deployment, and repository acceptance is not rights/publication authority.
- A Python-private class is not an OS/KMS isolation boundary. Real provider mutation remains disabled.
- The JPY 200,000 target is net operating profit, not gross affiliate revenue.

## Remaining credential-free backlog

Priority remains: (1) require typed semantic payload re-evaluation for P16 Gates 2–8 instead of signed component
hashes alone; (2) persist operations run/exception/human-budget state and alert outbox with crash-safe acknowledgement;
(3) define the credential-blind provider broker, role-specific signer ports, conditional provider state machine and
late-result reconciliation; (4) add cross-store outbox/reconciliation for P11/P13/P17. These improve production
safety but cannot manufacture the external business facts above.

## Verification receipts so far

- `tests/test_storage.py`: 19 passed, including rejected-write clock anchoring and single-retention-cohort enforcement.
- `tests/test_traction_control.py`: 43 passed; combined traction partition collects 57.
- Base regression excluding P13/P17 reached 599/600 before final P18 regeneration; its sole expected failure proved
  the checked-in exact-tree fixture was stale rather than silently accepted.
- P13 changed-path focused tests: passed, including arbitrary-port rejection, crash/exception recovery, process-group
  timeout, descriptor TOCTOU and output cap. The production partition collects 77.
- P13 first full run reported two dependency-closure mismatches because `storage.py` was deliberately edited while the
  immutable test run was active; both exact tests then passed on the static tree, followed by a clean `77 passed in
  441.55s` full partition run.

- Static-tree partitions passed: base 506, traction 57, production consumer 77, Contract/Storage 28 and TCO/QA 50.
- Schema export is deterministic at 183 files; P15/P16/P17 generated fixtures match the checked-in bytes.
- Web 13, ESLint, npm audit 0, uv lock (24 packages), compileall, workflow verifier and Gitleaks 12.36 MB/no leaks passed.
- Independent Contract/Storage re-audit closed retention-cohort mixing and P17 late-callback overlap; final Security
  and P13 audits reported no remaining credential-free P0/P1.

The P18 exact-tree STOP fixture was regenerated after the final documentation update and its deterministic self-check
passed. P20's credential-free implementation and audit scope is complete. This does not complete P19's real immutable
runner or any external rights, Affiliate, market, production, publication, observation or revenue gate.
