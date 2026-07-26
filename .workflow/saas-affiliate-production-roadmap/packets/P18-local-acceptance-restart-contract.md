# P18 Work Packet: local repository acceptance and restart contract

## Objective

Close the repository-acceptance handoff gap between the audited P11–P17 working-tree candidate and a Human-recorded,
versioned local integration acceptance. The contract must make exact scope, hashes, verification evidence, exclusions,
expiry and the next external gate machine-verifiable without creating public, production, affiliate or scale authority.

## Ownership

- Contract/Storage: canonical manifest, fixed file inventory, digest, signature and exact replay/substitution boundaries.
- TCO/QA: completion audit against public MVP, 80% automation and revenue-validation restart requirements; false-ready tests.
- Integration/Release: CLI, schema, deterministic blocked fixture, P17 acceptance migration, roadmap and verification.

## Required local contracts

1. The candidate manifest computes hashes from a policy-fixed, repository-relative inventory; callers cannot self-report
   a tree hash, omit a required file, use symlinks, escape the repository or include mutable/untracked external content.
2. Verification evidence is typed and bound to the same candidate. Required checks, commands/tool identities, counts,
   outcomes and observed artifact hashes cannot be replaced by prose or booleans.
3. Candidate assembly has authority `none` and decision `PENDING`. Only a separately supplied, policy-pinned Human
   Approver signature can accept the exact manifest for local integration, with half-open validity and explicit conditions.
4. Local acceptance never authorizes source fetch, application/email, account, credential, billing, provider mutation,
   deploy, publication, affiliate-link change, spend or scale. Those remain separate P11/P13/P15/P16/P17 gates. P16
   Gate 1 must consume the typed P18 bundle and an independently configured authority-root rather than opaque hashes.
5. The output identifies the exact next incomplete gate and required safe input without fabricating rights, Affiliate,
   demand, production or traction evidence.

## Do not

- modify historical P11–P15, P11–P16 or P11–P17 PENDING records;
- turn the current P11–P17 decision to GO or create a Human signature/private key;
- read or store credentials, PII, raw source content, live Affiliate IDs or non-public commission details;
- access network, Git remote, cloud, provider, domain, email, account, billing, deploy or public state.

## Acceptance

- omitted/extra/renamed/changed files, symlink substitution, path traversal, duplicate paths, stale evidence, signature
  substitution, wrong manifest, exact-expiry and unknown-condition cases fail closed;
- model-loaded manifests cannot shrink the fixed scope; root ancestors are no-follow; pre-Human verifier trust is
  consumer-pinned; attestations precede assembly; revision 2+ includes every signed predecessor receipt;
- P13 imports only hash-pinned local/runtime files outside the standard library and rejects unpinned shadow modules;
- a synthetic Human-signed fixture can prove local integration acceptance only, while the checked-in real-state fixture
  remains PENDING/STOP and identifies rights as the first external evidence gate;
- CLI, schemas and fixtures are deterministic; focused/full tests, lock, compile, secret scan, Web and workflow verifier pass;
- independent Contract/Storage and TCO/QA fixed-hash audits report no local blocker.
