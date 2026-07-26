# SaaS比較 Preflight recipe

## Trigger

比較対象SaaSを追加・更新し、料金・上限・12か月TCOを公開候補にしたいとき。

## Roles

1. Evidence/Policy Stewardがfield単位の権利と最小証拠を作る。
2. Contract/Storage Engineerがschemaへ適合させ、append-onlyで保存する。
3. TCO/QA Engineerが決定論計算とfixtureを検証する。
4. Integration/Release Operatorが結果を統合するが、権利承認や値の推測はしない。
5. Human Approverだけが権利状態と将来の公開を承認できる。

## Plan Shape

```text
approved source policy
  -> minimal evidence + hash
  -> strict VendorPlan
  -> deterministic TCO
  -> tests and conflict queue
  -> human GO/STOP
```

## Verification

- policyがapprovedである。
- schemaとfield evidenceが揃う。
- 税・通貨・単位・期間を推測していない。
- TCO unit/property testsが通る。
- raw全文、credential、PIIが保存されていない。
- 人手作業時間を記録する。

## Efficient Handoff

- Evidence/Policyは承認前の候補をcanonical DBへ渡さず、未決事項を1つの例外queueへ送る。
- Contract/StorageはPydanticだけをschema正本とし、JSON Schemaを生成する。1 retention cohortを1 DBに分ける。
- TCO/QAはPython純粋関数だけを計算正本とし、実装と独立した反証を最低1件残す。
- Integration/Releaseは日次の正常runを人へ通知せず、期限切れ、schema差分、test失敗、権利矛盾だけをbatchする。
- Human Approverは原則月1回のdecision gateで、rights、費用、外部接続、公開をまとめて判断する。
- 月間人手576分で新規source・非重大改善をfreezeし、720分以後はSEV0対応だけを許可する。

## Known Risks

- APIで取得できても公開・保存・AI投入が許可されるとは限らない。
- 旧値保持と旧値表示は別であり、公開後はread-time TTLが必要。
- 二言語で同じTCOや公開判定を実装すると意味driftが起きる。
