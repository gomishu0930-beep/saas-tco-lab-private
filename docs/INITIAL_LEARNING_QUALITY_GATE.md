# 自データ初回取得の品質ゲート

基準日: 2026-07-23（Asia/Tokyo）

## 結論

現時点では、外部の過去事例や合成fixtureはあるが、私たち自身の実観測データはまだない。
そのため、最初の1件から「量は少なくても、出所・定義・欠損・時刻・結合・Human正解が追跡できる」
状態だけを学習候補として受け入れる。新しい品質ゲートは、条件を一つでも満たさないbatchを`STOP`にする。

`READY_FOR_HUMAN_REVIEW`は、学習・公開・Affiliate・本番書込みの許可ではない。
Human確認へ進めるという意味だけで、出力の`authority`は常に`none`である。

## 二段階で開始する

|段階|required source|目的|
|---|---|---|
|Bootstrap|`field_evidence`, `keyword_demand`|記事化前に公式fieldとJP/ja需要を正しく扱えるか確認|
|Observed loop|上記 + `search_console`, `analytics`, `affiliate`, `operations`|impressionからpaid、費用、Human時間までを自データで結ぶ|

まだ存在しないsourceをゼロや推定値で埋めない。Observed loop用policyへ切り替えた時点で、
GSC、GA4、Affiliate、operationsのいずれかが欠ければ`required_source_missing`で停止する。

## 初期値

|検査|厳格な初期値|
|---|---:|
|対象|`JP / ja`固定|
|Affiliate通貨|`JPY`のみ|
|行数|received = accepted + duplicate + quarantined の完全一致|
|duplicate / quarantine / required-value missing / orphan|すべて0|
|join coverage|join対象sourceは99%以上|
|取得鮮度|7日以内|
|report終了からexportまで|24時間以内|
|source・label・QA署名|24時間以内に発行|
|schema drift|未審査drift 0|
|duplicate header / mixed currency / ambiguous timestamp / unknown state|すべて0|
|sensitive data|0。raw本文、PII、credential、tracking IDを入れない|
|synthetic / modeled|自データ学習では0|
|Human gold|5 domain × 3件以上、全件non-synthetic|
|署名|source steward、Human labeler、TCO/QAのEd25519公開鍵を分離|

5 domain × 3件は「初回の受入下限」で、統計的な十分性やmodel promotionを意味しない。
料金parserのrelease判定は別途`GOLD_SET_RUNBOOK.md`の3社 × 6プラン、各社60–150 material
field、quarantine 0、TCO一致を満たす必要がある。

## データ作成順

1. Humanが正規画面からexportする。raw fileはrepository外の専用保管場所へ置く。
2. 許諾範囲を確認し、raw receipt、抽出spec、schema、mapping、grain、candidate key、coverageをSHA-256で固定する。
3. adapterがhash-only / aggregate-only profileを作る。失敗行を捨てず、duplicateとquarantineへ全数計上する。
4. Source Stewardが件数、欠損、時刻、currency、coverage limitationを確認してprofileへ署名する。
5. Human Labelerが5 domainの実例をlabelし、gold setへ別鍵で署名する。
6. TCO/QAがprofile、gold、全署名をまとめたinput rootを再確認し、第三の鍵で署名する。
7. consumer自身が保持するpolicy + trust-store hashを`--expected-authority-sha256`として渡して評価する。
8. `READY_FOR_HUMAN_REVIEW`のbatchだけをHumanが標本確認する。学習runへの接続は別GOとする。

一人運用の場合も三つの鍵は分ける。ただし、同一人物の二回目確認は組織的な独立QAではないため、
初回pilotのHuman reviewまでに限定し、production promotionには別レビューを要求する。

## 実行

```bash
uv run saas-preflight evaluate-initial-learning-quality bundle.json \
  --policy strict-policy.json \
  --trust-store public-trust-store.json \
  --expected-authority-sha256 <consumer-owned-sha256> \
  --at 2026-07-23T03:00:00Z
```

CLIはlocal JSONを読むだけで、fetch、秘密鍵作成、署名鍵保存、学習、外部送信、DB更新、公開を行わない。
秘密鍵はrepository外の承認済みkeystoreで管理する。コードから署名する場合も
`sign_initial_learning_attestation`は秘密鍵bytesを保存・返却しない。

JSON入力契約は`schemas/initial-learning-*.schema.json`、判定実装は
`src/saas_preflight/initial_learning_quality.py`を正本とする。

## 本人操作

|本人が行うこと|完了の合図|Codexが続けること|共有禁止|
|---|---|---|---|
|JP/ja Keyword Plannerを正規export|`jp_ja_export: done`|coverage・欠損・重複を検査しprofile化|customer ID、credential|
|対象3社のfield evidenceと利用許諾を確認|`field_evidence: done`|field単位hashとgold候補を作る|規約全文、未公開資料|
|GSC/GA4をread-only接続|`gsc_property: done`, `ga4_property: done`|Observed policy用profileとjoin QA|verification token、measurement secret|
|承認済みAffiliate exportを取得|`affiliate_export_ready: <partner>`|state/currency/settlementを照合|tracking ID、税務・受取情報|
|15件以上の初回gold labelを確認|`initial_gold_labels: done`|署名対象hashと品質reportを作る|raw本文、PII|

## 停止時の扱い

- 不足sourceは推定補完せず、取得またはpolicy見直しまで停止する。
- duplicate、missing、unknown stateは除外して成功率を上げず、原因と件数を残す。
- schema driftは旧mappingで強行せず、新schema hashとmapping reviewを作る。
- GSC等の既知のrow limitはcoverage manifestへ残し、「全件取得」と表現しない。
- 署名・policy・consumer pinのいずれかが不一致なら、正しい鍵とartifactで作り直す。
