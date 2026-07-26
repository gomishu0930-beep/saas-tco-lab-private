# GSC / GA4 deployment gate

基準日: 2026-07-26（Asia/Tokyo）

## 現在地

- Search Consoleの中立origin URL-prefix propertyは作成・HTML tag所有確認済み。
- GA4の中立origin専用streamは作成済み。任意data sharingは全OFF、event retentionは14か月。
- GSC verification metaと同意制御GA4 bootstrapはSites version 5へdeploy・外部read-back済み。
- GA4の拡張計測機能は2026-07-26にOFFへ変更し、下記の明示event以外を自動収集しない。
- verification tokenとmeasurement IDはrepositoryへ保存せず、Sitesのruntime valueだけで渡す。

## Fail-closed実装

|制御|runtime条件|条件を満たさない場合|
|---|---|---|
|GSC verification|正規形式の`GOOGLE_SITE_VERIFICATION`が存在|metaを一切出力しない|
|GA4 bootstrap|`GA4_ANALYTICS_ENABLED=true`かつ正規形式の`GA4_MEASUREMENT_ID`が存在|Google用script・CSP許可・同意UIを一切出力しない|
|Impact verification|正規形式の`IMPACT_SITE_VERIFICATION`が存在|Impact metaを出力しない|

Impact値とGSC値が同時に存在する場合も、Impact verification metaを`<head>`内の最初のmetaとして維持する。

GA4を有効にしても、訪問者が「同意する」を選ぶまで`googletagmanager.com`のscriptを読み込まず、
Google Analytics endpointへの通信を開始しない。拒否時はdevice-localな選択だけを保存する。

## event taxonomy

|event|発火条件|送る値|
|---|---|---|
|`page_view`|同意後、GA4 scriptを初期化した時に1回|queryを除いたorigin+path、page title、content path|
|`qualified_session`|同意後、表示中のpageで30秒到達|30秒という固定閾値、content path|
|`comparison_interaction`|明示的な比較scopeまたはevent属性内の操作|要素種別、content path|
|`outbound_click`|将来、同意後に外部linkを操作|domainだけ。URL、query、affiliate IDは送らない|

広告用storage・Google Signals・広告personalizationは有効にしない。referrer、個人メール、PII、
verification token、Affiliate URL、tracking IDをevent parameterへ入れない。

## 実行済みHuman action-time gate

```text
gsc_verification_deploy: GO / STOP
ga4_tag_deploy: GO / STOP
```

2026-07-26に2件とも`GO`を受領し、同日の公開versionへ反映した。将来の再deploy、runtime値変更、
analytics scope拡張をこの承認へ含めない。

## 実行結果

- 公開HTMLはImpact verificationを最初のmeta、GSC verificationをその後に維持し、noindexも維持した。
- Search ConsoleはHTML tagで所有権を確認した。query、page、country、device、dateとexport UIを確認し、
  初日のため実データだけは「処理中（1日後に再確認）」である。
- GA4は同意前と拒否後に外部script 0件、同意後だけGoogle tag 1件を読み込むことを確認した。
- GA4 Realtimeで1 active user、`page_view` 1件を確認した。GA4自身のsystem eventである
  `first_visit`と`session_start`も各1件発生した。
- 拡張計測はOFF。内部traffic filterは不可逆な除外を避けるためtestのまま維持し、対象sourceを
  確定した別承認後だけactiveへ移す。

## GO後の実行と合格条件

### GSC

1. Sites runtimeへverification値を保存し、値をlog・chat・repoへ出さない。
2. 検証済みsourceを新versionとしてdeployする。
3. 公開HTMLでHTTP 200、Impact metaが最初、GSC metaがその後、noindex header維持をread-backする。
4. Search Consoleで所有確認し、query/page/country/device/dateのread-only export contractを確認する。

### GA4

1. Sites runtimeへmeasurement IDと明示enable flagを保存する。
2. 同意前にGoogle宛network requestが0件であることを確認する。
3. 拒否後も0件、同意後だけ`page_view`と30秒後の`qualified_session`がDebugViewへ届くことを確認する。
4. 内部traffic rule/filterをtestからactiveへ移す前に、自分のtrafficだけが除外対象であることを確認する。
5. query、referrer、PII、Affiliate識別子がparameterにないことをread-backする。

## Rollback

- GSC: runtime verification値を撤去し、直前の検証済みversionへ戻す。
- GA4: まずenable flagを外して新規送信を停止し、必要なら直前versionへrollbackする。
- どちらもImpact verification、noindex、公開route allowlist、503境界を維持する。
