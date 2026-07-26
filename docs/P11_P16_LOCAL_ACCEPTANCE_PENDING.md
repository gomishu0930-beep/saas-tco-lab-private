# P11–P16 local scope acceptance v4 — PENDING

この文書はHuman Approver用の新しいversion付き承認票である。現在のdecisionは`PENDING`であり、AIやagentには
`GO`へ変更する権限がない。repoの形式的承認記録は`AGENTS.md`のP0–P10までである。

このv4は、履歴である`docs/P11_P15_LOCAL_ACCEPTANCE_PENDING.md`を書き換えず、その固定scope/hash候補を
SHA-256で参照し、P16差分を追加する。v3のPENDING decisionをGOへ読み替えない。Humanがv4を受理する場合だけ、
P11–P16のlocal working-tree候補を一つのversionとして扱う。

## Decision

```text
decision: PENDING  # Humanが GO | STOP | CONDITIONAL のいずれかを記入
approver_id:
decided_at_utc:
expires_at_utc:
conditions:
signature_or_external_record_reference:
```

## 承認候補scope

- v3に固定されたP11 external-action boundary、P12 measurement integrity、P13 production consumer、P14
  crash-safe evidence、P15 production integration readiness/reconciliationのlocal候補。
- P16 exact 8-gate handoff、固定artifact component set、Human/TCO鍵分離、plan/policy/trust pin。
- receipt ordinal/predecessor chain、cross-gate duplicate/conflict、half-open expiry、canonical bundle/report。
- local-only CLI、8 missingのblocked fixture、113件のdeterministic schema、50件のP16反証。
- P16 reportの非権限契約: final Human review入力のみ、外部mutation不可、実行境界再検証必須。

明示的な対象外:

- 実source fetch、問い合わせ・申請・メール送信、account/OAuth/credential/KMS/課金。
- production DB/provider write、Git push、cloud/deploy/domain変更、公開・rollback。
- rights、利用可能Affiliate 3社、実JP需要、30日shadow、observed EPC、月20万円gateの合格認定。
- P15 Human environment approval/bootstrap authorization、P13 dispatch token、P11 execution grant、P10 release
  authorization。P16のcomponentにも含めない。
- P16が参照する上流artifactの現実世界での真実性。最終Human reviewと各実行consumerで別途再検証する。

## 固定hash

```text
P11–P15 v3 candidate record 3806667f95f507c4279dad62afdad7c81e98d70a0872e9da56fb2b855626defa
P16 source                  959a1049946cebe2aada6abed7a99a573397d231be799e6cbd48e00e23a8ba85
P16 tests                   c2bbfeb545cb633a63064fc723808925ab96fcb7fa463d7b4fe9531ee25fbfa2
CLI                         845eb6b108baf453c7fd15002c3c1425a6ef55d789ebb7d40d527517d1f41d50
schema exporter             b74461245d3c6608dd2f0ad40168dd7fc3dab91c47b2bbaecff2a436f7ecb08f
schema set (113)            33c5655dafec57575f51a74fe889058098e7af8a2e699d5c751d841c7cf0dea1
P16 fixture generator       f597a7fd84cd7133f38ea18d530a6043bcedc2059e6ecf85db9fe0b2554da1f5
P16 blocked bundle          c12e0ec26ec62968b914ece980bc8a79b4903e20b1bc8731f033cd273668c0ba
P16 blocked report          71c10b5bc5f92a822a73a29c710d217a05e449244231a8f06a2bd3a3b81d01bb
P16 blocked plan            e4a80bab1f55086cb0ec0994656579ff3651b98f77c28b84d78f682aecd27a71
P16 blocked policy          d1ecf3a9a2b66857f52d17aba12fab7ba9529a7716637312639d2ded89a70863
P16 blocked trust           c3db4aba647cabaeb4f738c4b6d307089e06d0c4a0f6308650966e0261a91e9f
P16 runbook                 f197cba302884f69bbb1a179b33ecc2d6909c55cd9179e482bd7d64142b31d9e
P16 acceptance tests doc    187f9a4270412dbde5b968def5c66de85ade2f26fe2828342fa7931084aecfa1
```

`schema set`は113個のschemaをfilename順に並べ、各fileのSHA-256行を再度SHA-256した値である。上記hashが
変わった場合、この票は変更後の候補を承認しない。新しい差分・test・hashを持つ次versionが必要である。

## Acceptance evidence

- P16 focused: 50 passed。Python full suite: 564 passed。
- JSON Schema 113件: repeat export、checked-in set一致。
- blocked fixture二重生成、CLI STOP output/expected report: byte-identical。
- `uv lock --check`: 24 packages。compileall、workflow verifier、Gitleaks 8.19 MB/no leaks: passed。
- Web: local 9、startup boundary 1、production 3、ESLint、npm audit 0: passed。
- Contract/Storage fixed-hash audit: PASS。署名tie-break不足の初回blockerを修正後、再監査でblockerなし。
- TCO/QA fixed-hash audit: PASS。11 false-ready反例は全てSTOP、full suite/diff clean。
- business/public state: `STOP`。

この票をHumanが`GO`へ変更しても、対象外のexternal/production行為は一切承認されない。実行順は
`docs/NEXT_IMPLEMENTATION_HANDOFF.md`、P16の意味は`docs/P16_LAUNCH_HANDOFF.md`に従う。
