# P11–P15 local scope acceptance v3 — PENDING

この文書はHuman Approver用のversion付き承認票である。現在のdecisionは`PENDING`であり、AIやagentには
`GO`へ変更する権限がない。repoの形式的承認記録は`AGENTS.md`のP0–P10までである。P11–P15のlocal候補を
受理する場合だけ、Humanがこの固定hash版へdecisionを記録する。

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

- P11署名付きexternal-action boundaryのlocal code/docs/tests/schema。
- P12署名付きmeasurement-integrity boundaryのlocal code/docs/tests/schema。
- P13 credential-free production consumer、P14 crash-safe provider journal/fencing/recovery。
- P15 exact 11 production-readiness contract、10 role trust、policy-only threshold、P13 activation binding。
- P15 separate reconciliation ledger、store/trust pin、`NOT_APPLIED`限定STOP reset。
- blocked/synthetic fixture、offline CLI、deterministic schema、local test/scan。
- 既存の`sharp` 0.35.3 override、lockfile、CycloneDX SBOM。

明示的な対象外:

- 実source fetch、問い合わせ・申請・メール送信、account/OAuth/credential/KMS/課金。
- production DB/provider write、remote provider、Git push、cloud/deploy/domain変更、公開・rollback。
- 実provider conditional mutation、idempotency/receipt、KMS identity、trusted clock、external anchor、multi-host
  fencing、egress、backup/restore、incident disableの合格認定。
- remote exactly-once、provider mutation/receiptの原子性、P11/P13/providerの分散transaction保証。
- 実Affiliate URL/ID、実価格、PII、raw HTML/PDF/メール全文の投入。
- rights、利用可能Affiliate 3社、JP qualified demand、30日shadow、observed EPC、月20万円gateの合格認定。

## 固定hash

```text
P11 source                  a27f3a1a4f4eda67bea67ab703cb31378601a1c7471f579d56deb62607281a46
P11 tests                   a36027df80de62829e8233e78b4817d888010e97578897fd9c8154a2a2463e36
P12 source                  4c81eb8b8c77650f9ac9e7a1c537086762a67e913f0fc91378d5fef96d3b611c
P12 tests                   c0d8c3b974db7f0b54df541b71ff154427a188c6aeb48c4c7a5d290c093e4bef
P13/P14/P15 consumer source 04d69871689d1fa53fb5879e4a21e3c2fedd7eac6634ce39245661ddca7c44ab
P13/P14/P15 consumer tests  11e2aab00254ac3262c874227c9987af79e62aa51cf93c60589fb8d286ca8e5d
P15 readiness source        a97dd051758c754f2ac31527f37b9adbd1e3dbe1bf5087afd69538930aa2318d
P15 readiness tests         98699667c0fc645e1ee92064905ba377b8cfb8af4d6bc16d5d3330cdfa930c87
control-cycle roles         c812121dd0b20a05c0e7f34dd14162af61d42d0b0f5ea224b6046cb32f5d7288
execute child               1b7d446f87444aa7c0efb10d557a1d8f34d2630049989a81b42ae16e4ea1c027
probe child                 5395cfa0a02417282522c56273ea0500becd8d0f095643fd34353752a409c118
schema exporter             9798ae4c53c24231795e47ff3a5ceb225e0d02e49130705ba3aa329f6b84f270
schema set                  323f273593b0a8f2839992714af23f117faca760afc19b6793ca6bdef7c4dde0
P15 fixture generator       3ac942d645c2ed6f9202e90c13cdccbf63aa4e455648c5c7c76d7665c049a952
P15 blocked bundle          7c5010132999af848d06dfcad5168bfb533286b4dc51a9b9087533051dbd0d3b
P15 blocked report          f9b98dfce56569f1174a6c4f5534e94a6518ade482ee6e4a15d7641d148092d4
P15 blocked plan            965be04bed1d2d743287da2f9bf40f0231cfc91a107837d17746e24a2cda4fd4
P15 blocked policy          cdc6715d942715f18b80c80a027fa2e7d0c1920331b5c362342c38add1728562
P15 blocked trust           2e3e87db631341cd27b558f90ade5cd8d6b1e3d4ae6e06750d2b143a9bd1f667
site package                c157375eccc20437c79ee28a267f893f023e9d2e83015ed1b6088450bf0afc84
site lock                   164cf0e8a67cba5486d18c6eddcbb95ef504dbb7f8082ebd839a92484afaa156
SBOM                        a860dd9810e1fb76f75198ff23870c4c4b271609670124aa90dd9ee803595c13
```

`schema set`は、105個のschemaをfilename順に並べ、各fileのSHA-256行を再度SHA-256した値である。いずれかの
hashが変わった場合、この票は変更後の候補を承認しない。新しい差分・test結果・hashを持つ新versionが必要。

## Acceptance evidence

- P15 readiness focused: 105 passed。
- P13/P14/P15 production-consumer focused: 52 passed。
- Python full suite: 514 passed。
- JSON Schema 105件: repeat exportおよびchecked-in setとの差分なし。
- blocked fixture二重生成: byte-identical。offline CLI: expected STOP、exit 3、expected reportとbyte-identical。
- compileall、`uv lock --check`、workflow verifier、Gitleaks: passed。
- P15 independent Contract/Storage and TCO/QA fixed-hash audits: PASS、local blockerなし。
- business/public state: `STOP`。

この票をHumanが`GO`へ変更しても、対象外のexternal/production行為は一切承認されない。次の再開条件は、
`docs/NEXT_IMPLEMENTATION_HANDOFF.md`のgateごとの別decisionと、実環境で新たに採取したP15証拠である。
