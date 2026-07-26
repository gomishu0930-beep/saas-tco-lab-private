# Preflight故障注入matrix

実データ・実Affiliate link・外部networkを使わず、次の8故障をrelease候補へ注入する。期待動作を変更する場合はHuman Approverのpolicy version更新が必要である。

|Machine ID|故障|検知境界|期待する自動動作|Human handoff|現在の検証|
|---|---|---|---|---|---|
|`fi-01-price-change`|価格変更|VendorPlan snapshot/TCO diff|候補を新versionとして隔離。currentを上書きしない|根拠とTCO差分を承認|model/storage/TCO/P12 tests|
|`fi-02-plan-rename`|プラン改称|material field evidence|旧planを勝手に同一視せずcandidate化|rename/migration判断|material evidence/P12 tests|
|`fi-03-billing-period-change`|課金周期変更|strict BillingPeriod、annual proration|不明prorationを計算せずSTOP|新fixture承認|TCO annual/P12 tests|
|`fi-04-currency-change`|通貨変更|CurrencyCode/currency equality|換算せずSTOP|原通貨・表示方針承認|currency mismatch/P12 tests|
|`fi-05-quota-overage-change`|quota/overage変更|unit/reset period/overage validation|単位不明を計算せずquarantine|公式定義確認|usage/P12 tests|
|`fi-06-source-conflict`|情報源矛盾|field-level pointer/policy|自動で片方を採用せず例外queue|authority優先順位決定|policy/evidence/P12 tests|
|`fi-07-affiliate-expiry`|Affiliate失効|affiliate expiry/CTA decision|数値・順位・CTAをserve-time非表示|再承認または非収益化|release/preview/P12 tests|
|`fi-08-fetch-failure-duplicate-delivery`|取得失敗・重複delivery|HTTP boundary/run key|Retry-After尊重、current維持、重複無害化|3回連続でescalate|source access/operations/P12 tests|

重大誤表示は、適合判定逆転、広告主/plan違い、12か月TCOが`max(1,000円, 2%)`超ずれる、期限切れ値の表示、広告表示欠落とする。fixtureで検知できない意味変更は自動承認しない。

実行:

```bash
uv run pytest tests/test_models.py tests/test_tco.py tests/test_release.py \
  tests/test_operations.py tests/test_source_access.py tests/test_end_to_end.py
```
