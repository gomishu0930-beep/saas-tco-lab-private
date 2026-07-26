# P11–P14 local scope acceptance v2 — PENDING

この文書はHuman Approver用のversion付き承認票である。現在のdecisionは`PENDING`であり、AIやagentには
変更権限がない。P11–P13 v1候補の後にP14とdependency security updateが加わったため、旧票のhashでは
現在の候補を承認できない。

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
- P13 credential-free production consumerとsynthetic execute/probe。
- P14 immutable provider-fact journal、phase fence、same-host owner lock、fork/restart recovery。
- `sharp` 0.35.3 security override、lockfile、再生成SBOM、networkなしのlocal test/build/scan。

明示的な対象外:

- 実source fetch、問い合わせ・申請・メール送信、account/OAuth/credential/KMS/課金。
- production DB/provider write、remote provider、Git push、cloud/deploy/domain変更、公開・rollback。
- remote exactly-once、multi-host consensus、trusted time、P11/P13 cross-store atomicityの合格認定。
- 実Affiliate URL/ID、実価格、PII、raw HTML/PDF/メール全文の投入。
- rights、Affiliate、JP需要、30日shadow、EPC、月20万円gateの合格認定。

## 固定hash

```text
P11 source     a27f3a1a4f4eda67bea67ab703cb31378601a1c7471f579d56deb62607281a46
P11 tests      a36027df80de62829e8233e78b4817d888010e97578897fd9c8154a2a2463e36
P12 source     4c81eb8b8c77650f9ac9e7a1c537086762a67e913f0fc91378d5fef96d3b611c
P12 tests      c0d8c3b974db7f0b54df541b71ff154427a188c6aeb48c4c7a5d290c093e4bef
P13/P14 source 15c9a936bb6a213972c19d279eb3f415b4ab1d4980cbb3e49ee5ad51ae20e0f6
P13/P14 tests  8cb91d383120d9691423af89fc4246d53a93f2281b10819a0154f46f6e2b84a6
execute child  1b7d446f87444aa7c0efb10d557a1d8f34d2630049989a81b42ae16e4ea1c027
probe child    5395cfa0a02417282522c56273ea0500becd8d0f095643fd34353752a409c118
site package   c157375eccc20437c79ee28a267f893f023e9d2e83015ed1b6088450bf0afc84
site lock      164cf0e8a67cba5486d18c6eddcbb95ef504dbb7f8082ebd839a92484afaa156
SBOM           a860dd9810e1fb76f75198ff23870c4c4b271609670124aa90dd9ee803595c13
```

いずれかのhashが変わった場合、この票は変更後の候補を承認しない。新しい差分、test結果、hashを持つ
新versionが必要である。

## Acceptance evidence

- production-consumer focused: 42 passed。
- Python full suite: 399 passed。
- JSON Schema 80件: repeat export byte-identical。
- compileall、`uv lock --check`、workflow verifier、Gitleaks: passed。
- Web local/startup/production tests and builds、ESLint: passed。
- `npm audit`: 0 vulnerabilities。`sharp` 0.35.3 overrideでNext/Miniflare build互換を再検証。
- CycloneDX 1.6 SBOM: 651 components / 651 dependency nodes、`--check` passed。
- business/public state: `STOP`。

この票を`GO`へ変更しても、対象外のexternal/production行為は一切承認されない。外部操作は
`docs/NEXT_IMPLEMENTATION_HANDOFF.md`のgateごとに別decisionを必要とする。
