# P11–P13 local scope acceptance — PENDING

この文書はHuman Approver用のversion付き承認票である。現在のdecisionは`PENDING`であり、作成したAIや
agentには変更権限がない。未記入のままではP11–P13を統合・release承認済みとして扱わない。

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

承認対象は次だけである。

- P11署名付きexternal-action boundaryのlocal code/docs/tests/schema。
- P12署名付きmeasurement-integrity boundaryのlocal code/docs/tests/schema。
- P13 credential-free production consumer、synthetic execute/probe、STOP store、local code/docs/tests/schema。
- 合成fixtureを使うnetworkなしのcompile、test、schema、secret、SBOM、Web build検証。

明示的な対象外:

- 実source fetch、問い合わせ・申請・メール送信、account/OAuth/credential/KMS/課金。
- production DB/provider write、Git remote push、cloud/deploy/domain変更、公開・非公開化・rollback。
- 実Affiliate URL/ID/非公開条件、実価格、PII、raw HTML/PDF/メール全文の投入。
- rights、Affiliate、JP需要、30日shadow、EPC、月20万円gateの合格認定。

## 固定core hash

```text
P11 source  a27f3a1a4f4eda67bea67ab703cb31378601a1c7471f579d56deb62607281a46
P11 tests   a36027df80de62829e8233e78b4817d888010e97578897fd9c8154a2a2463e36
P12 source  4c81eb8b8c77650f9ac9e7a1c537086762a67e913f0fc91378d5fef96d3b611c
P12 tests   c0d8c3b974db7f0b54df541b71ff154427a188c6aeb48c4c7a5d290c093e4bef
P13 source  06fe2c7585370c56863500d74688238b1832240c2b8a2afe3cc78eddf8f72495
P13 tests   f4511a0b814334b6a70b21d39be0e8344fe62ba39b2a2cfd529d3e38f112bad0
```

hashが変わった場合、この票はその変更を承認しない。新しい差分、test結果、hashを付けた新versionが必要。

## Acceptance evidence

- P13 focused: 25 passed。
- Python full suite: 382 passed。
- generated JSON Schema 80件: 再生成前後でbyte-identical。
- compileall: passed。
- Gitleaks: no leaks。
- Web local/production boundary tests and production build: passed。
- npm audit: 0 vulnerabilities at the recorded run。
- 独立監査: Contract/Storage、Governance technical、TCO/QAがlocal technical contractをPASS。
- business/public state: `STOP`。

この記録を`GO`へ変更しても、対象外のexternal/production行為は一切承認されない。外部操作は
`docs/NEXT_IMPLEMENTATION_HANDOFF.md`のgateごとに別decisionを必要とする。
