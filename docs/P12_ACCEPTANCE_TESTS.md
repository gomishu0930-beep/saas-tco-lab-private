# P12 acceptance / refutation matrix

すべてsynthetic local入力で実行します。`REJECT`はEvidence/reportを1件もemitしない、
`EMIT+STOP`は真正・完全・8 fault成功済みだが経済値またはoperation KPIが不足し、既存
gateを失敗させる意味です。

|境界|反証|期待|
|---|---|---|
|Pre-run freeze|開始後署名、HOLD/STOP、wrong property/policy/window/currency/source、future、exact expiry、過大TTL|REJECT|
|Role separation|同一key再利用、wrong role/scope/issuer/key ID、dataset attestation入替え|REJECT|
|Batch binding|署名後のvolume/row/hash変更、別run replay、unindexed batch、attestation欠落|REJECT|
|Coverage|raw count不一致、output count不一致、privacy scan不合格、conflict/unknownをacceptedへ混入|REJECT|
|Funnel|orphan、partner mismatch、child増加、重複parent、期間外、converted clickを分母へ置換|REJECT|
|EPC|valid outbound 4、transaction 3、新規settled 300|EPC=75。3で割る100は禁止|
|Status|pending→confirmed→paid|各snapshotで1 current status、同額1回|
|Status攻撃|confirmed+paid同時計上、paid→pending、同一tx異amount、unknown acquisition|REJECT|
|Payout|current paid集合とrow/statement grossが完全一致|ACCEPT|
|Payout攻撃|missing/orphan/duplicate、amount/currency/set hash/net不一致、部分reversal|REJECT|
|Reversal|paid transactionへ全額refund/chargeback adjustment|confirmed EPC分子から除外、netへ反映|
|Fault|canonical 8、unique definition/run、全restore成功|PASSED|
|Fault攻撃|missing/duplicate/extra/substitute/stale definition/false restore|REJECT|
|Fault実測失敗|canonical 8の1件がfailed|REJECT。authority report非発行|
|Job denominator|300 unique run、各2 retry attempt|分母300。600にしない|
|Canonicality|row shuffle|同じcanonical hash|
|Materiality|volume/status/amount/click/faultの1値変更|異なるhash、古い署名/indexをREJECT|
|Bound dossier|signed reportからvalid clicksを4→1へ書換え|REJECT|

実行:

```bash
uv run pytest -q tests/test_measurement_integrity.py
uv run pytest -q
uv run python scripts/export_schemas.py
```

既存`tests/test_measurement.py`はunsigned aggregateの算術・schema診断です。P12
production-authority合格数へ単独で加算しません。
