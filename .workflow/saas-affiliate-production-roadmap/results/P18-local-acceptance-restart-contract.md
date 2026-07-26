# P18 Result: repository acceptance and restart contract

## Outcome

Implemented the credential-free P18 candidate. The current real-state fixture remains `STOP / local_verification`; no Human, public, production, affiliate, spend or scale authority was created.

## Implemented

- Code-defined P11–P18 inventory with dirfd/openat-style `O_NOFOLLOW`, double scan, pre/post `fstat`, mode/content hash, and symlink/hardlink/secret/unknown/collision rejection.
- Fourteen structured verification facts binding argv, cwd, environment, network mode, interpreter/import closure, tool/version, result counts, output hash and expiry.
- Distinct Integration Evidence Runner, TCO/QA and Human Ed25519 roles; policy pins; current receipt revision/predecessor/head; consumer-owned authority-root.
- Exact next gate/input reporting for local verification, Human acceptance, pinned current chain and rights evidence.
- P16 schema v2 singleton typed P18 Gate 1 with external authority-root, cross-binding and expiry clipping. Legacy P11–P15 opaque components are rejected.
- P16 plan/policy/trustを別のconsumer-owned launch-handoff authority-rootへ固定し、P16 trustと全receiptの自己整合型完全差替えを拒否する。
- P13 pinned-file dirfd validation、verified-byte/extension-FD import、全stdlib+8 distribution closure、bounded outputを持つisolated `-I -S` subprocess launcher。
- Fixed-order 14-check local diagnostic runner。明示5 test lane、schema/fixture二重生成、network-disabled/loopback-only
  Seatbelt、sanitized env、timeout/output cap、runtime/tree前後hashを実装した。署名・秘密鍵・Human decisionは扱わない。
- Empty-cache `npm audit --offline` false-cleanとhost filesystem/process非隔離を反証したため、runner provenanceは
  `local_diagnostic_run`、dependency checkは意図的STOP。immutable runner v2だけが`verified_local_run`を生成する。
- Deterministic schemas, P16 blocked fixture and P18 current STOP fixture plus runbooks and handoff updates.

## Final fixed implementation hashes used by independent audit

- `repository_acceptance.py`: `e6af0b7f273e97f7763c733f0667bf7a31ba49d4a9913bb6a2733fe47e0b20ca`
- `launch_handoff.py`: `53128cd3b8c9c3e32be41f432b1f17f506f4e13da90664dc6cb760fd59507731`
- `production_consumer.py`: `f3df8c0d7eae0c396ebd2eefb389aa0553420fc69da5d0d05f9d0e52fb6be5d8`
- `cli.py`: `5b18e45f510233135a23c0ff59522ed1162a6219083749deb52e73837bbf35e2`
- focused tests: `bb8a3b76465ab6c172de5c4582beb97131cc50791ea03cad4529d30e1578891e`, `31f7c14fb45d36f725963f1ed3319c7710726123e8c76a5ff51e06d209dc5e94`, `c52b75d2a6997c65145a9411bd5caa19bcf268b5c045c4ef6037bc7ebd9bec3c`
- 150-schema digest-list hash: `a1c344cc465b644a202174b783bd061b72c704b272729782ea136a525ff5a6a9`

The final whole-tree/manifest/report hashes are intentionally stored only in the scope-external P18 fixture to avoid self-reference. Regenerate it after any in-scope change.

## Final verification and independent audit

- focused P18/P16/P13: 134/134 passed
- full Python: 648/648 passed in 493.33 seconds
- schemas: 150, two exports and checked-in set byte-identical
- P18 fixture: two generations and checked-in set byte-identical
- diagnostic runner: base 462、traction 52、P13 58、schema 150、fixtures 8、Web 13、P18 audit 24、P16 audit 50と
  lock/compile/secret/lint/workflow passed。unsigned advisory不足だけが意図どおりfail/exit 3。
- `uv lock --check`, compileall, workflow verifier: passed
- Web: 13 tests and lint passed。online advisory resultはacceptance evidenceに数えない。
- Gitleaks: no leaks
- Contract/Storage: PASS、残存P0/P1 code blockerなし。P18/P16 76件とP13 58件を独立再実行。
- TCO/QA: PASS。P18 25件とP16 51件、低assertion policy反証、diagnostic非昇格を独立確認。

## Remaining boundaries

- P18 Human acceptance is PENDING and the first external gate remains rights evidence.
- Typed per-task/per-Human-activity automation proof, an operational P17 ledger CLI/adapter, immutable verification
  runner/result contract v2、signed advisory snapshot、P18/P16 revalidation at final publication/production consumption remain follow-up local packets.
- Real rights, affiliate acceptance, demand, gold source, production controls, publication, 30-day observations, settlement, EPC and revenue remain external evidence gates.
