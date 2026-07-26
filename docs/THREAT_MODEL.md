# SaaS comparison release threat model

Baseline date: 2026-07-22<br>
Model version: 1.1<br>
Scope: P10 pre-publication release assurance and P11 external-action authorization

## Decision and scope

**Public decision: STOP.**

This document covers the local, external-credential-free implementation and the controls that would be
required before a production launch. It does not authorize a source fetch, account creation, credential,
billing, cloud resource, deployment, public URL, production write, Affiliate redirect, analytics collection,
promotion, rollback, or publication.

Passing local tests proves only that the local contracts fail closed for the tested inputs. It does not prove
that a production identity, network, datastore, key store, hosting configuration, domain, monitoring path, or
operator process exists. Statements below use these labels:

- **Implemented local:** present in the repository and exercised without external credentials.
- **Required production:** absent or not connected; it is a launch requirement, not a claimed control.
- **Human gate:** a decision that an AI, agent, scheduler, test result, or signature cannot make.

## Security objectives

1. Publish only values with current rights for fetch, storage, display, history, derivation, and retention.
2. Preserve the provenance and append-only history of every canonical observation and release artifact.
3. Prevent unknown or ambiguous values from becoming prices, limits, TCO, suitability, or rankings.
4. Keep credentials, raw source bodies, PII, personal mail, non-public commission data, and tracking URLs out
   of the repository, fixtures, logs, prompts, and public responses.
5. Require independent TCO/QA and Human release attestations before a controller can issue a short-lived
   serving lease.
6. Fail closed when data, rights, Affiliate approval, evidence, attestation, release, scheduler, or lease is
   missing, future-dated, mismatched, revoked, stale, or expired.
7. Make a release stoppable and recoverable without deleting or rewriting its evidence history.
8. Keep local synthetic assurance distinct from a public business or legal approval.
9. Require exact Human GO, fixed target allowlists, a guard-owned clock and durable one-shot claim before any
   future rights inquiry, Affiliate application, release activation or release disable adapter may start.

## Assets and classification

| Asset | Security property | Classification and current state |
|---|---|---|
| Source policies, rights decisions, authority receipts | Authenticity, scope, expiry, non-repudiation | Sensitive governance metadata; local contracts exist, real approvals do not |
| Safe summaries and evidence pointers | Integrity, minimization, freshness, provenance | Hash-only/minimal local contracts; real source summaries not acquired |
| Canonical plans and append-only observations | Integrity, ordering, retention, recoverability | Local strict models plus authenticated SQLite v2 schema/MAC/hash-chain/CAS-anchor/rollback, internal trusted-time watermark and one-retention-cohort-per-DB contract implemented; no production KMS, anchor or DB |
| TCO code, scenarios, results, gold labels and quarantine reports | Determinism, correctness, reviewer independence | Local pure calculation and synthetic gold/fault fixtures implemented |
| Release manifests, current pointer, artifacts and rollback records | Integrity, immutability, availability | Local implementation only; no persistent production release state |
| TCO/QA, Human and controller signing keys | Confidentiality of private keys, role separation, revocation | Ephemeral local test keys only; no production keys or key store |
| Attestations, trust store, ControllerAuthority and ServingLease | Authenticity, binding, freshness, replay resistance | Local Ed25519 boundary implemented; no production bootstrap or verifier adapter |
| Worker, static assets and health/robots responses | Fail-closed routing, confidentiality, availability | Production-mode local build is 503 except fixed health/robots; not deployed |
| Affiliate program decisions and redirect destinations | Integrity, authorization, expiry, attribution | Hash binding exists locally; no real program or active URL |
| Demand, cohort and operations evidence | Integrity, privacy, deduplication, expiry | Local typed aggregation exists; no real 30-day dataset |
| Analytics events and revenue/status mapping | Minimization, integrity, lawful collection | Production collector and privacy controls are not implemented |
| Lockfiles, dependencies, Actions, build outputs and SBOM | Provenance, reproducibility, tamper detection | Pinned local dependencies/scans and deterministic CycloneDX 1.6 SBOM exist; protected remote, production runner and artifact provenance do not |
| Operator workstation, local exports and incident artifacts | Credential and PII confidentiality, integrity | Process restrictions documented; managed production workstation controls absent |
| Backups, retention cohorts and restore evidence | Confidentiality, deletion, RPO/RTO, restorability | Local retention-cohort design only; no production backup system |
| Domain, DNS, Search Console, canonical and structured data | Ownership, index integrity, recovery | No approved domain or public SEO metadata; public indexing is prohibited |
| External-action request, approval, grant, claim, revocation and receipt | Exact authority, role separation, replay resistance, factual outcome integrity | Strict signed contracts and authenticated local SQLite CAS/anchor implemented; no provider adapter, credential or external operation |

## Trust boundaries and entry points

```text
Untrusted source / Affiliate / analytics export
  -> Human-owned quarantine and rights decision
  -> approved, minimized intake adapter
  -> candidate + quarantine boundary
  -> append-only canonical storage
  -> deterministic TCO + independent gold/QA
  -> role-separated signed attestations
  -> trusted ControllerAuthority + short ServingLease
  -> production verifier / Worker / static assets
  -> user, crawler, Affiliate redirect and privacy-safe analytics

Repository / lockfiles / CI runner -> build and SBOM -> immutable release artifact
Operator workstation / secret store -> approved production control plane only
```

| Boundary | Untrusted or less-trusted entry point | Higher-trust destination | Rule |
|---|---|---|---|
| B1 Rights intake | Terms, robots, vendor mail, API/feed documentation | Human-approved `SourcePolicy` | Ambiguous, missing, conflicting, or expired scope is denied |
| B2 Network intake | URL, DNS, redirect, HTTP response | Transient source bytes and minimal receipt | Approved HTTPS host/method only; production egress control is still required |
| B3 Safe-summary intake | Local raw export, email/report, parser output | Allowlisted hash-only summary | PII/secret/raw URL/free text detection quarantines the whole batch |
| B4 Candidate admission | Parser/AI/plugin candidate | Strict model, append-only observation, quarantine | AI never writes canonical or release state directly |
| B5 TCO/gold | Canonical plan and scenario | TCO result and GoldSetReport | Pure calculation, current labels/rights, complete failure accounting |
| B6 Signing | Gold report, current release event, role keys | TCO/QA and Human attestations, controller lease | Separate roles and keys; config/trust/signer sealed at trusted bootstrap |
| B7 Delivery | Lease, release state, artifact, HTTP request | Protected response | Fixed issuer/key/scope/content/TTL; missing or invalid lease returns generic 503 |
| B8 Static assets | Asset URL and framework routes | Worker response | Production build routes assets worker-first; only health/robots bypass the lease adapter |
| B9 Affiliate | Approved destination bundle and CTA state | User redirect | Destination and disclosure must be current and hash-bound; no active local CTA |
| B10 Analytics | Browser/event/export | Aggregate demand/cohort evidence | Production allowlist, consent, minimization and bot/fraud controls are absent |
| B11 Supply chain | Package metadata, lockfile, PR, runner, action | Build artifact and release evidence | Exact pins and local checks exist; remote CI identity and signing are absent |
| B12 Operations | Workstation, secret store, backup, DNS/hosting console | Production control plane | Requires managed identity, least privilege, audit, rotation and Human approval |

Primary entry points are local JSON/CLI input, approved source URL, local export import, SQLite repository,
release preparation API, attestation signing ceremony, controller evaluation, runtime HTTP routes, static asset
routes, Affiliate redirect, analytics event/export, dependency update/CI job, operator filesystem, backup/restore,
secret store, hosting/DNS console, and crawler/indexing requests.

## Threat actors and capabilities

| Actor | Relevant capability |
|---|---|
| Malicious or compromised source | Changes terms/data, redirects, oversized or crafted content, false prices |
| Affiliate or analytics provider | Changes destination/status semantics, injects identifiers, reports fraudulent or delayed data |
| Internet attacker, bot or crawler | Enumerates assets, exploits redirects/XSS/SSRF, scrapes stale content, causes load |
| Compromised dependency, package publisher, Action or runner | Executes during install/build/test, alters artifacts or exfiltrates secrets |
| Compromised operator workstation or account | Reads exports/keys, changes config, deploys or approves the wrong artifact |
| Compromised signing role | Forges only that role's attestations; controller compromise can mint leases |
| Malicious insider or colluding roles | Alters evidence, suppresses failures, replaces keys or bypasses separation of duties |
| AI, plugin or agent as confused deputy | Hallucinates rights/values, leaks prompt data, attempts canonical or external writes |
| Accidental operator or configuration error | Uses stale evidence, wrong domain/key, asset-first route, backup, or rollback target |
| Availability attacker or provider outage | Exhausts request/job capacity or prevents source, key, DB, DNS, hosting, or alert access |

## Threat register

`P`, `D`, `C`, and `R` mean prevention, detection, containment/kill switch, and recovery. Controls prefixed
`Local` are implemented locally; controls prefixed `Prod` are requirements and must not be read as current.

### Rights, intake and storage

| ID and threat state | P | D | C | R | Residual risk | Owner | Human-only boundary |
|---|---|---|---|---|---|---|---|
| R1 — Missing, forged, over-broad or expired source policy permits unauthorized collection, derivation, history or display | Local: field-level rights axes, authority/hash/scope/expiry, unknown and expiry deny. Prod: verified decision-record store and expiry/revocation monitor | Policy/hash/binding validation; expiry and conflict exceptions | Stop source, parser, release and display; revoke policy; hide affected artifact/CTA | Obtain a new authoritative decision, create a new policy/evidence version, rebuild and re-attest; do not extend by copying | An authentic approver may still misunderstand terms; vendor terms can change without notice | Evidence/Policy; incident A: Human | Human approves rights, exceptions, archive and any renewal/revocation |
| R2 — Source-policy expiry or withdrawal is not propagated, leaving stale pages or index entries | Local: shortest rights expiry participates in dossier, manifest and lease. Prod: event-driven revocation plus periodic reconciliation | Dead-man heartbeat, expiry checks, public synthetic probe and index audit required | Revoke lease, return 503/redact CTA, pause jobs, request removal from indexes | Re-evaluate every affected field, issue a new manifest and attestations, then submit removal/recrawl as needed | Search and downstream caches may retain prior content after shutdown | Evidence/Policy + Integration | Human confirms withdrawal scope, legal deletion and republication |
| I1 — SSRF, DNS rebinding, malicious redirect, oversized response or forbidden authenticated fetch reaches private services | Local: approved HTTPS/443 exact host, redirect/DNS recheck, public IP checks, proxy/cookie/auth disabled, size/type limits. Prod: network egress allowlist and isolated fetcher | Rejected host/IP/redirect/status/content exceptions; egress and DNS logs required | Disable source and fetch credential, block host/route, stop scheduler | Review policy and DNS history, rebuild isolated adapter, rotate any exposed credential | Application DNS checks cannot eliminate rebinding or cloud/network misconfiguration | Contract/Storage; network A: Integration | Human approves host, method, credential scope and any source re-enable |
| I2 — Raw HTML/PDF/mail, PII, secret, tracking URL or non-public commission enters repo, DB, log, prompt, fixture or SBOM | Local: raw archive forbidden by default; allowlist safe summaries; unknown fields rejected; secret scan. Prod: DLP, encrypted quarantine, log/prompt redaction and retention policy | Denylist/schema/secret scans; repository and object-store audit required | Quarantine whole batch, stop processing/publication, revoke leaked secret, restrict artifact access | Purge or crypto-erase under recorded authority, rotate credentials, regenerate clean summaries and history | Hashing low-entropy PII is still identifying; scanners have false negatives | Evidence/Policy + Security/Integration | Human approves exceptional archive, incident disclosure, deletion and external processing |
| S1 — Observation, evidence, release or audit history is overwritten, reordered, deleted or backdated | Local: frozen strict models, append-only observation, canonical hashes, immutable release artifacts. Prod: transaction log, object lock/WORM, trusted clock and independent audit export | Hash/sequence/duplicate checks, DB integrity and backup reconciliation required | Stop writes and serving; isolate affected cohort/database and current pointer | Restore to a new store, replay verified append-only events, rebuild report/manifest and re-attest | A privileged storage administrator or compromised backup could alter all copies | Contract/Storage; release A: Integration | Human authorizes destructive retention, restore selection and production pointer change |
| S2 — Backup leaks data, outlives rights, is untested, or cannot meet RPO/RTO | Local: one DB per retention cohort and whole-file deletion design. Prod: encrypted/versioned backups, separate keys, inventory, expiry jobs, restore drills and deletion attestations | Backup age/coverage/restore checksum, retention breach and orphan-copy alerts required | Suspend new data, revoke backup access/key, isolate or crypto-erase affected cohort | Restore into isolated validation, compare hashes, reissue release; document irreversible loss | Provider snapshots and legal holds may delay deletion; restore can reproduce compromised state | Contract/Storage + Integration | Human sets RPO/RTO, retention/legal hold, restore and deletion decision |

### Calculation, quality and decision integrity

| ID and threat state | P | D | C | R | Residual risk | Owner | Human-only boundary |
|---|---|---|---|---|---|---|---|
| Q1 — False price, quota, suitability, TCO or ranking is produced through ambiguity, unit/currency/tax error or malicious source data | Local: strict no-inference contracts, Decimal pure TCO, scenario binding, property/fault tests and current evidence. Prod: real Human gold labels and source-specific parsers | Gold/TCO mismatch, source conflict, major-misstatement ledger, independent counterexample | Quarantine plan/batch, revoke lease, hide comparison and reward-dependent ranking | Correct by a new observation/parser/model version, rerun TCO/gold, issue new manifest/attestations | An authoritative source or Human label can itself be wrong; correctness is not created by a signature | TCO/QA; business A: Human | Human resolves ambiguous commercial definitions and approves material correction/publication |
| Q2 — Parser/AI suppresses failed rows, poisons gold data, or writes candidates directly into canonical/release state | Local: candidate-only AI boundary, success and failure in one batch, full coverage, quarantine, parser-failure stop and independent labels | Missing/extra candidate, failure ratio, parser/source/version/hash and field/TCO diff | Disable parser/source, quarantine batch, prohibit promote and lease | Fix parser with fault fixture, create a new batch, independently relabel and re-attest | Collusion between parser owner and label approver or incomplete gold coverage | TCO/QA + Contract/Storage | Human owns gold labels, conflict resolution and readiness acceptance |
| Q3 — Demand, Affiliate cohort or 30-day operations evidence is fabricated, duplicated, cherry-picked or uses changed definitions | Local: versioned mappings/dedup, strict periods/denominators, maturity/expiry and hash-only receipts. Prod: authoritative exports and coverage receipts | Conflict/duplicate/unknown-status/period/zero-denominator checks and counterexamples | Reject dataset/dossier, freeze run definition, keep public decision STOP | Restart measurement under a new signed manifest; never rewrite the failed window | Provider fraud/bots/attribution and unobserved missing events can bias results | Integration + TCO/QA | Human freezes metric definitions and makes business GO/STOP decision |

### Keys, attestations and leases

| ID and threat state | P | D | C | R | Residual risk | Owner | Human-only boundary |
|---|---|---|---|---|---|---|---|
| K1 — TCO/QA, Human or controller key/role/trust store is substituted; unsigned or wrong-scope evidence is accepted | Local: distinct Ed25519 roles/keys, key IDs, issuer/scope, full canonical signatures, trust-store hash, frozen non-serializable `ControllerAuthority`. Prod: approved trust root and controlled bootstrap | Invalid role/key/signature/scope/pin is STOP; production key/config audit required | Disable controller, remove verification key, revoke all leases and fail 503 | Conduct new key ceremony, update trust root by separately approved release, re-sign current evidence | Python object privacy is not a hostile-code sandbox; a holder of Authority/controller key is inside the trust boundary | Integration; role evidence: TCO/QA and Human | Human approves trust root, key ceremony, role assignment and trust-store change |
| K2 — Private key or ControllerAuthority is leaked, copied, misused, lost or not rotated/revoked | Local: private keys excluded from models/repo/log/hash, signer-redacted repr, serialization rejected, ephemeral test keys. Prod: KMS/HSM or secret manager, non-exportable keys, least privilege, dual control, inventory, rotation and revocation runbook | Key-use audit, unexpected issuer/key/lease-rate, secret scan and canary alerts required | Remove key access, stop controller, revoke key ID at verifier, fail all protected routes, rotate dependent credentials | Generate a new role-specific key, approve/pin it, re-attest/release, invalidate old leases and investigate exposure | A stolen controller key can mint authentic leases until verifier revocation; short TTL only bounds replay | Integration/Security; incident A: Human | Human authorizes production key creation, rotation, revocation, emergency disclosure and re-enable |
| K3 — Valid lease is replayed after expiry, copied to another release/artifact, modified, future-dated or given excessive TTL | Local: issuer/key/scope/release/manifest/artifact/input/time binding, maximum TTL, half-open validity and request-time verification | Signature/content/time mismatch and stale heartbeat lead to 503; production replay telemetry required | Stop controller or heartbeat; revoke key/release; generic 503 for protected paths | Restore authoritative release state and clock, issue a new short lease after all gates pass | Replay within a valid lease window remains possible; clock integrity becomes a production dependency | Integration/Release | Human approves current release/rollback; automation may only maintain an already approved current release |
| K4 — Genuine signatures are used over false or stale underlying facts | Local: attestation binds exact report, rights/candidate, release event/manifest/decision and validity. Prod: approver identity proof and evidence-review procedure | Cross-binding, expiry, gold and operations checks; periodic independent review | Revoke attestation/release/lease and quarantine affected data | Correct evidence and obtain fresh independent attestations | Cryptography proves key possession, not truth, competence or freedom from coercion | TCO/QA + Human | Only Human accepts legal/business fact and current release decision |

### Delivery, Affiliate, analytics and SEO

| ID and threat state | P | D | C | R | Residual risk | Owner | Human-only boundary |
|---|---|---|---|---|---|---|---|
| W1 — Worker/static asset/framework route bypasses lease checks or exposes synthetic/protected content | Local: separate synthetic-local entry, production worker returns 503 except health/robots, `run_worker_first`, actual-HTTP asset tests. Prod: deployed-config attestation and post-deploy probes | Probe real page, hashed JS, favicon, image and unknown routes; compare deployed config hash | Disable route/deployment/domain, remove asset binding or force worker-first, return fixed 503 | Redeploy exact approved artifact/config and repeat external probes before DNS enable | Hosting/CDN behavior can differ from local workerd and change after provider updates | Integration/Release | Human approves hosting, deploy, public URL and re-enable |
| W2 — XSS, HTML/script injection, clickjacking or content-type confusion executes source-controlled content | Local: structured fields and escaped local Python HTML, restrictive CSP/security headers, no raw body/public CTA. Prod: framework sink review, CSP nonce/hash policy and browser security tests | CSP violation and synthetic payload tests; public security monitoring required | Revoke lease, return 503, disable affected source/template | Sanitize at typed boundary, patch template/dependency, rebuild/re-attest and invalidate caches | CSP/header regressions and browser/framework zero-days remain | Integration + TCO/QA | Human approves any HTML/archive exception and public remediation |
| W3 — Open redirect, Affiliate destination substitution, unsafe scheme, disclosure removal or expired Affiliate CTA misdirects users | Local: destination/disclosure hashes and Affiliate expiry redact CTA; synthetic UI has no active external link. Prod: HTTPS domain allowlist, server-side redirect ID, destination revalidation and audit | Destination/hash/expiry mismatch; external redirect and disclosure proximity probes required | Disable redirect/CTA and reward-based ranking independently of page; revoke program | Revalidate program/property/domain, issue a new destination bundle and manifest after Human approval | Approved merchant may redirect downstream or change landing content | Integration; policy: Evidence/Policy | Human exclusively approves program, destination, disclosure and link change |
| A1 — Analytics collects PII/identifiers without authority, leaks events, or permits event/revenue fraud | Local: only typed aggregate evidence and non-PII hashes; no collector installed. Prod: consent/legal basis, event allowlist, first-party minimization, retention, access, bot/internal filtering and export reconciliation | Schema/DLP, volume anomalies, duplicate/fraud/status mapping and provider reconciliation required | Disable collector/tag and downstream ingestion, rotate token, quarantine affected cohort | Delete/crypto-erase per approved policy, rebuild aggregates from clean authoritative export | Fingerprinting/re-identification, blockers, provider processing and attribution fraud cannot be eliminated | Integration + Evidence/Policy | Human approves provider, legal/privacy text, consent, retention, external transfer and KPI use |
| E1 — Crawler exposure, stale index, malicious canonical/structured data or SEO spam publishes unsupported claims | Local: noindex/nofollow/noarchive/nosnippet, disallow-all robots, canonical/JSON-LD/public origin absent, no public domain. Prod: approved canonical/domain/structured data plus index monitoring | Metadata/static assurance, Search Console and external crawler/index queries required | Revoke lease/domain route, serve noindex/503, remove sitemap/canonical and request de-indexing | Correct evidence/page, purge caches, resubmit removal or recrawl only after approval | `robots.txt` and `noindex` are advisory; caches/screenshots can persist | Integration + Evidence/Policy | Human approves domain, SEO claims, canonical/structured data and index remediation |
| W4 — DoS, bot load, source/provider outage, scheduler failure or DB/key-store loss prevents safe refresh or serving | Local: heartbeat/dead-man lease and generic fail-closed response. Prod: quotas, rate limiting/WAF, timeouts, queue backpressure, redundant monitoring, capacity and RPO/RTO | Heartbeat/job/SLO/error-rate/resource/dependency alerts and external health probes required | Shed load, stop intake, expire lease, serve fixed 503; never extend stale data to preserve availability | Restore dependencies/state from verified backup, rerun gates and issue a new lease | Safety favors outage over stale/unauthorized publication; volumetric attacks may also affect health/robots | Integration/Release | Human approves availability spend, disaster recovery and any exceptional degraded mode |
| W5 — Rollback points to a tampered/incompatible artifact or restores data without current rights | Local: immutable manifest/artifact hashes, current visibility checks and synthetic rollback/fault tests. Prod: durable release journal and tested deployment rollback | Pre/post state hashes, schema/rights/expiry validation and fault drills required | Stop current lease and serve 503; do not blindly promote previous release | Select a still-valid immutable release, re-evaluate and re-attest; otherwise rebuild from evidence | No historical release is guaranteed to remain legally/currently safe | Integration/Release | Human exclusively approves production rollback target and execution |

### Supply chain and operations

| ID and threat state | P | D | C | R | Residual risk | Owner | Human-only boundary |
|---|---|---|---|---|---|---|---|
| C1 — Dependency, package source, lockfile, build script, GitHub Action, runner or generated artifact is compromised | Local: exact dependency pins/hashes, lock checks, isolated tests, secret scan, dependency audit, deterministic lock-derived SBOM, policy-pinned command/subject/tool and controller-signed typed facts. Prod: protected remote, pinned Action SHAs/images, least-privilege ephemeral runner, artifact signing/provenance | Lock/SBOM drift, license/source validation, audit, signed evidence review and artifact hash comparison required | Freeze install/build/deploy, revoke runner/controller token or key, quarantine artifact and dependency | Rebuild from reviewed lock/source on clean runner, rotate secrets, reissue evidence/provenance/release | Approved runner/controller can still sign dishonest facts; signed or pinned malicious upstream and zero-days remain possible | Contract/Storage + Integration | Human approves new dependency/tool, permissions, exception and production artifact |
| O1 — Compromised workstation, broad cloud account, copied export or malicious plugin leaks data/keys or changes production | Local: no credentials/PII in repo/prompt and no external production connection. Prod: managed device, disk encryption, updates, separate profiles, phishing-resistant MFA, least privilege/JIT, no local private-key export and audit | EDR/login/secret-access/config-change/export anomaly and periodic access review required | Disable account/device/session, revoke keys/tokens, stop controller/deploy and isolate exports | Reimage device, rotate all reachable credentials, verify release/config/backups and reapprove access | A fully privileged live operator session can perform authorized-looking malicious actions | Integration/Security; incident A: Human | Human approves account, credential, cloud access, plugin/AI external transfer and re-enable |
| O2 — AI/plugin/agent hallucinates rights or values, exfiltrates data, or directly writes canonical DB, release, Affiliate URL or production | Local: AI candidate-only rule, strict contracts, no production connector, ownership boundaries. Prod: scoped service identities, egress/tool allowlists and approval-enforced write APIs | Audit tool calls, schema/quarantine failures and unexpected writes/egress required | Disable agent/plugin/token, reject candidate and freeze affected release | Restore append-only state, rotate credential, independently rebuild and review evidence | Prompt injection may influence candidate output; tool configuration can defeat policy | All technical owners; governance A: Human | AI cannot receive delegation for rights, ambiguity, external write, production or publication decisions |
| O3 — Configuration drift selects synthetic-local mode, wrong trust root/domain, asset-first serving or permissive logging in production | Local: explicit runtime modes, production worker-first tests, config/hash bindings. Prod: policy-as-code deployment, environment identity, sealed config and post-deploy attestation | Diff approved/deployed config, synthetic markers, key/domain/log policy and external route probes | Abort deployment or disable domain; revoke lease/config and fail 503 | Redeploy approved immutable config/artifact and repeat assurance | Provider defaults or manual console edits can bypass repository review | Integration/Release | Human approves environment, domain, trust root, logging and deployment |

## Credential and key rotation/revocation requirement

No production credential or private key currently exists. Before launch, Integration/Release must produce a
Human-approved inventory covering owner, purpose, role, environment, issuer/key ID, creation, last rotation,
expiry, allowed operation, storage location, audit source and revocation procedure. Production private signing
keys must be non-exportable where the selected provider permits it and must never be placed in repository,
fixture, log, prompt, client bundle, backup without a separately approved encrypted key-backup design, or
operator clipboard.

A production rotation must:

1. stop new leases or enter a bounded maintenance state;
2. create a role-specific replacement under dual control;
3. update the separately approved trust root/config without allowing one role to replace another role's key;
4. deploy verifiers that recognize only the explicitly approved transition set;
5. reissue Gold/Human attestations and the current release lease as applicable;
6. revoke the old key ID, wait out the maximum lease TTL, and verify old signatures fail;
7. record hashes, scope, approver, time, result and rollback without recording private material.

Suspected compromise skips overlap: stop the controller, fail protected routes to 503, revoke the affected key
and all dependent attestations/leases, preserve audit evidence, rotate reachable credentials, and require a new
Human release decision. Short lease TTL is containment, not revocation.

## Implemented local controls

The following are supported by current local code/tests, subject to their documented input assumptions:

- strict frozen Pydantic contracts, canonical hashes and deterministic Python TCO;
- rights/freshness/retention checks, minimal evidence pointers and fail-closed source adapter rules;
- append-only observation and immutable release/rollback contracts;
- safe-summary demand, cohort and 30-day operations intake with dedup/conflict/maturity checks;
- complete synthetic gold/fault quarantine and independent calculation checks;
- separate TCO/QA, Human and controller Ed25519 keys, attestations, trust-store pinning,
  `ControllerAuthority`, signed content-bound short leases and request-time verification;
- synthetic-local UI isolation, no active CTA, noindex/robots controls, security headers;
- production-mode local Worker with worker-first static assets and fixed health/robots-only exposure;
- pinned local dependencies, lock verification, local tests, dependency audit and secret scanning.
- P11 fixed policy/trust/target rules, exact Human/controller/executor bindings, guard-owned claim/receipt clock,
  fixed-ID SQLite claim/revocation/receipt CAS with HMAC state head, companion authenticated anchor, separately
  read/committed monotonic pin, exact schema/write verification, revision-bound canonical journal fold and separate
  authority/outcome state. Tests use an in-memory pin; compromise of DB, pin/key source or the shared Python process,
  and crash-safe multi-store recovery remain production blockers.
- P16 v3/P21 typed launch semantics: Gate 2–8 carry exact upstream rows/reports instead of only opaque hashes;
  consumer-owned external pins fix each P12/P15/P10/gold artifact; public-key-only evaluators rebuild the seven
  gate meanings, bind P12/P15/P10/P13 to one release/manifest/artifact/schema/target/state chain, and require P15-linked
  probe-signed production deployment/content/indexability/disclosure readbacks before binding scope/currentness into P16 receipts and the P13 request/token/current-root boundary. Publication is bound to the exact preceding deployment, consumer-owned legal/disclosure expectations and per-readback freshness/order; rollback evidence is bound to the P11 disable policy.
  This prevents a valid signature over an arbitrary digest from becoming launch readiness, but cannot prove that an
  externally supplied observation is honest when its authorized probe signer or external root is compromised.

These controls do not create real rights, factual price evidence, Affiliate approval, demand, operating history,
credentials, production availability, a public domain, or a Human publication decision.

## Required production controls and launch blockers

The public release remains STOP until all items below have current, scope-bound evidence and the final typed
release-assurance evaluator also returns public STOP until a signed Human GO exists.

| Blocker | Required evidence/control | Owner and gate |
|---|---|---|
| L1 Real source rights | Current field-level authority for at least three vendors, including fetch/store/display/history/derive/retention and withdrawal | Evidence/Policy; Human rights approval |
| L2 Real Affiliate availability | At least three usable programs for the approved property, current disclosure/destination/region/expiry and no unsafe concentration | Integration/Evidence; Human program/link approval |
| L3 Real factual quality | Approved source adapters, 3 vendors × 6 plans, Human gold labels, zero quarantine and zero major misstatements | Contract/TCO; Human ambiguity and gold acceptance |
| L4 Demand and operations | Authoritative JP/ja demand path and completed 30-day shadow run meeting job, exception, rollback, automation and 720-minute gates | Integration/TCO; Human measurement freeze and business decision |
| L5 Production identity and keys | Selected secret/KMS service, approved trust root, key ceremony, least privilege, rotation/revocation and audit; deployed lease verifier | Integration/Security; Human credential/key approval |
| L6 Production data plane | Durable append-only DB, retention cohorts, encryption, backups, restore/deletion evidence, RPO/RTO and dead-man monitoring | Contract/Integration; Human cloud/retention approval |
| L7 Production edge | Approved hosting/domain/DNS, worker-first deployed config, WAF/rate limits, actual external asset/page probes and cache/de-index kill switch | Integration; Human account/billing/deploy/publication approval |
| L8 Affiliate redirects and analytics | Domain allowlists, privacy/legal basis, consent as required, event minimization, status mapping, fraud/bot controls and incident disable path | Integration/Evidence; Human legal/privacy/link approval |
| L9 Supply chain and release evidence | Current deterministic SBOM, scans/audit, protected remote/runner, pinned CI, artifact provenance, rollback/fault proof and no unresolved release blocker | Contract/Integration; Human tool/dependency exceptions |
| L10 Accessibility/mobile/SEO assurance | All P10 synthetic-local tests pass; public canonical/structured data remain absent until domain and source-backed claims are approved | TCO/QA; Human domain/SEO approval |
| L11 Public decision | Typed evidence is current and bound to the exact release/manifest/artifact/policy; Human signed `GO`, scope, conditions and expiry | Integration; Human Approver exclusively |

## Residual-risk disposition

No residual risk is accepted here for public operation. Within the already approved offline/local scope only,
the following are tolerated because no production credentials, real source data, active Affiliate link, public
domain or public traffic is present:

- standard cryptographic hash/signature and pinned-dependency implementation risk;
- compromise of the local operator host, bounded by the absence of production secrets and external writes;
- synthetic fixture inaccuracies, because they cannot be represented as real vendor facts;
- advisory limits of robots/noindex, because the local preview is not a public launch control;
- application-layer DNS/redirect checks that require an additional production egress boundary;
- fail-closed unavailability when freshness, lease, scheduler or dependency cannot be proven.

Moving any residual risk into production requires an explicit Human record naming the risk, scope, owner,
compensating control, expiry, trigger for withdrawal, and recovery path. Silence, a passing test, an AI summary,
or a `CONDITIONAL` record with non-machine-checkable conditions is STOP.

## Human-only decision boundaries

Only the Human Approver may authorize:

- source rights, expiry extension, conflict interpretation, withdrawal handling or raw archive exception;
- gold labels and resolution of ambiguous price, tax, currency, billing, unit, quota or commercial terms;
- external account, credential, key ceremony, role assignment, cloud, domain, billing and production write;
- Affiliate program, destination, disclosure, ranking/revenue-policy or redirect change;
- analytics provider, privacy/legal basis, consent, retention and external data transfer;
- deployment, current release promotion, public URL, publication, non-publication and rollback;
- incident disclosure, destructive retention, backup restore, exception/risk acceptance and recovery re-enable;
- the final signed `GO | STOP | CONDITIONAL` decision with scope, conditions and expiry.

AI and automation may gather evidence, calculate, test, detect, stop, quarantine, redact and maintain a valid
already-approved current release. They may not approve, widen scope, extend expiry, replace a signing role,
waive a failed check, promote a new release, choose a rollback target, or publish.

## Review and recovery governance

Integration/Release owns this model's release-level coordination. Each threat remains operationally owned by
the role named in the register; ownership never grants Human-only authority. Review is required when a source,
rights scope, schema, TCO rule, parser, signing key, trust root, dependency, CI runner, datastore, backup,
hosting provider, domain, Affiliate program, analytics provider, privacy policy, redirect behavior or threat
assumption changes, and after every SEV0/SEV1 incident.

The handoff must include this version and hash, unresolved threat IDs, exact artifact/config/evidence hashes,
test/scan/SBOM results, key and lease expiry, kill-switch and restore evidence, residual risks, owner, and the
Human decision record. Until the production requirements and Human gate are complete, recovery always returns
to a non-public or fixed-503 state, not to stale content.
