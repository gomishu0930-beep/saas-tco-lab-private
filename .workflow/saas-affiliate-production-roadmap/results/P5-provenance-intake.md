# P5 Result: Provenance-backed production intake

## Accepted

- `readiness_builder.py`を追加し、RightsBundleとAffiliateBundleを入力recordから決定論的に導出した。
- `BusinessDossier`へproperty、5 source/bundle SHA-256、組立時刻を必須化した。P6 operation gate追加時にv3へ更新した。
- demand、cohort、operationsをversion・source hash・captured/expiry付きcontractにした。
- 人手時間をminuteから、自動化率をroutine task分子/分母から計算した。分母0は0%になる。
- `assemble-readiness` CLIは既存outputを上書きせず、外部network・Affiliate URL・credentialを扱わない。
- schemaを5件追加し、production input contractとroadmapを更新した。

## Counterexamples closed

- 同じpartner IDの重複。
- 異なるpartner IDを使った同一vendor programの件数水増し。
- 対象propertyが異なるapprovalの流用。
- 期限切れrights/affiliate/demand/cohort/operations。
- Affiliate審査JSONへのlive URL追加。
- automated taskの分母0を100%とみなすこと。
- approved Affiliate vendorに対応するVendorPlanがないこと。

## Verification

- `uv run pytest -q`: 147 passed。
- 9 JSON Schemaを再生成。
- blocked current-state fixture: STOP。
- complete synthetic 3-vendor evidence: GO。

## External gate unchanged

実rights回答、Affiliate審査、需要dataset、confirmed cohort、30日shadow実績はまだ0であり、事業判定はSTOPのまま。外部申請・送信・fetch・公開は実行していない。
