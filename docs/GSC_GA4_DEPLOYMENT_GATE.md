# GSC / GA4 deployment gate

基準日: 2026-08-13（Asia/Tokyo）

## 現在地

- Search Consoleは`saastcolab.jp`のdomain propertyをDNS TXTで所有確認済み。verification値はrepositoryへ保存しない。
- GA4の専用streamは2026-08-03に`https://saastcolab.jp`へorigin更新済み。任意data sharingは全OFF、
  event／user retentionは14か月、拡張計測はOFF、internal traffic filterはtestのままである。
- GSC verification metaと同意制御GA4 bootstrapはSites version 5へdeploy・外部read-back済み。
- GA4の拡張計測機能は2026-07-26にOFFへ変更し、下記の明示event以外を自動収集しない。
- verification tokenとmeasurement IDはrepositoryへ保存せず、Sitesのruntime valueだけで渡す。
- 2026-08-09、`saastcolab.jp`のSearch Console domain propertyと専用GA4 streamを連携済み。
  連携画面に表示される利用者メールとstream IDはrepositoryへ保存しない。

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

- 2026-07-26の公開前originでは、Impact verificationを最初のmeta、GSC verificationをその後に維持し、
  noindexも維持した。URL-prefix propertyはHTML tagで所有権を確認した。
- 2026-08-03に`saastcolab.jp`のdomain propertyをDNS TXTで所有確認した。query、page、country、device、
  dateのread-only export境界を維持し、verification値は保存・表示しない。
- 2026-08-04のread-only再確認では、domain property `saastcolab.jp`の`/sitemap.xml`は
  `成功しました`、送信日2026-08-03、最終読み込み2026-08-04、検出ページ3、検出動画0である。
  再送信、URL検査登録、設定変更は行っていない。
- 2026-08-09のS6再確認でもsitemapは`成功しました`、送信日2026-08-03、最終読み込み
  2026-08-06、検出ページ3、検出動画0である。公開sitemapは5 URLなのでGoogle側の再読込待ちとし、
  再送信、URL検査登録、設定変更は行っていない。同日のページ集計は最終更新2026-08-05、登録済み1、
  未登録3で、未登録理由は`検出 - インデックス未登録`である。公開read-backではsitemapとrobotsの
  allowlistが承認済み5記事で一致しており、Google側の処理待ちとして扱う。
- 2026-08-09の後続read-only確認で、sitemapの最終読み込みは2026-08-09、検出ページ5へ更新された。
  ページ集計は最終更新2026-08-05のまま登録済み1、未登録3で、登録済み1件は旧HTTPルート、未登録理由は
  `検出 - インデックス未登録`である。承認記事の登録完了とは扱わず、再送信、URL検査登録、設定変更を
  行わずGoogle側の処理を待つ。
- 2026-08-11のread-only確認で、sitemapは`成功しました`、最終読み込み2026-08-11、検出ページ9、
  検出動画0へ更新された。公開sitemapの9 URLと一致する。一方、ページ集計は最終更新2026-08-07、
  登録済み1、未登録3で、未登録理由は`検出 - インデックス未登録`のままである。sitemapでの検出と
  index登録を混同せず、再送信、URL検査登録、設定変更は行っていない。
- 同日、承認済みP05を10記事目として追加公開し、公開sitemapとrobots allowlistが10記事で一致すること、
  P01–P08・P10・P12だけが`index, follow`・canonical・開示先行Mangools CTAを満たすことを外部read-backした。
  P09/P11はnoindex・canonicalなし・CTAなしを維持する。Search Console側は直前確認の検出9ページが正本で、
  次回の自動再読込まで10ページ検出とは扱わず、sitemap再送信やURL検査登録は行っていない。
- 2026-08-09にP04/P08/P10を追加したSites version 15を公開し、公開sitemapとrobots allowlistが
  承認済み8記事で一致することを外部read-backした。Search Consoleの既存sitemap submissionは維持し、
  再送信・URL検査登録は行わず次回読込を待つ。
- 同日、GA4管理画面からSearch Console domain property `saastcolab.jp`を専用web streamへリンクし、
  連携済み行をread-backした。internal traffic filter、拡張計測、同意設定は変更していない。
- 同日、P12の共通確認間隔を明示的`not_applicable`として承認し、Sites version 17・runtime revision 8へ
  追加公開した。外部read-backで公開sitemapとrobots allowlistは9記事で一致し、P05/P09/P11はnoindex・
  canonicalなし・CTAなしを維持した。GSCへの再送信やURL検査登録は行わず、既存submissionの再読込を待つ。
- GA4は同意前と拒否後に外部script 0件、同意後だけGoogle tag 1件を読み込むことを確認した。
- GA4 Realtimeで初回の`page_view`受信を確認した。2026-07-26の追加read-only確認では、過去30分の
  active user 2、`page_view` 2、`qualified_session` 2を確認した。これは実装確認の訪問を含むため、
  需要、CVR、収益実績へ算入しない。GA4自身の`first_visit`と`session_start`も発生している。
- 2026-08-09のS6再確認ではRealtime過去30分は0件で、過去28日イベント表は`page_view` 7、
  `qualified_session` 7、`outbound_click`は未生成だった。実装確認訪問を分離できないため、月次KPIへ
  転記せず、confirmed成果やCVRを推測しない。
- 2026-08-11のread-only確認ではRealtime過去30分のactive userとeventはいずれも0件で、
  `page_view`と`qualified_session`の新規受信は確認できなかった。設定変更やテスト送信は行っていない。
- 2026-08-12のread-only確認では、公開sitemapとrobots allowlistは承認済み10記事で一致する一方、GSCの
  sitemapは最終読み込み2026-08-11、検出9ページのままである。ページ集計は登録済み1・未登録3、
  集計期間の表示回数とclicksは0で、10記事のindex完了とは扱わない。GA4は表示上の直近7日間で
  `page_view`、`qualified_session`、`outbound_click`がすべて0、Realtimeも0である。再送信、URL検査登録、
  設定変更、テスト送信は行っていない。
- 同日後続のread-only確認で、GSCのsitemapは最終読み込み2026-08-12、検出10ページへ更新され、
  公開sitemap 10 URLと一致した。検索clicksは0、ページ集計は登録済み1・未登録3のままであり、10記事の
  index完了とは扱わない。GA4はRealtimeと直近7日間が0、過去28日イベント表は`page_view` 7、
  `qualified_session` 7、`outbound_click`行なしである。既存の実装確認訪問を含むため需要・CVRへ算入しない。
- 拡張計測はOFF。内部traffic filterは不可逆な除外を避けるためtestのまま維持し、対象sourceを
  確定した別承認後だけactiveへ移す。
- 2026-08-13、Human確認済みP09を11記事目として限定releaseした。外部read-backでP09はHTTP 200、
  `index, follow`、canonical、確認済みHuman作業費2,006.67 JPYと公式支援費unknown、開示先行Mangools CTA、
  送客hostとlink属性のgateに合格した。P11はHTTP 200・noindex・canonicalなし・CTAなしを維持し、
  sitemapとrobots allowlistは11記事で一致した。GSCへのURL検査登録要求は行っていない。
- 同日のGSC再確認で、performance対象期間2026-08-02〜08-11は表示回数0・clicks 0、ページ集計は
  最終更新2026-08-07の登録済み1・未登録3だった。sitemap行は`成功しました`、最終読み込み2026-08-11、
  検出9ページを表示し、前日に記録した検出10ページと一致しない。公開sitemapの承認済み11 URLだけを
  同じsubmissionへ再送信し、未承認route・URL検査登録・index対象は増やしていない。再処理が完了するまで
  11件検出やindex完了とは扱わない。
- GA4の2026-08-06〜08-12 events reportは合計0、Realtime過去30分も0だった。公開HTMLには同意制御bootstrap、
  `page_view`、`qualified_session`、`outbound_click`の明示経路が存在する。無流入と同意未取得を分離できないため、
  0件を計測停止・需要・CVR・収益の証拠へ補完せず、設定変更やテスト送信も行っていない。
- 2026-08-14、URL検査でP01は`検出 - インデックス未登録`と表示された。Human承認済みのP01だけを対象に
  登録要求を送信したが、初回と時間を置いた再試行の双方で「送信中に問題が発生」と表示され、成功確認できなかった。
  quota超過やページ不適格とは補完せず、追加の連続再試行、他URLへの要求、設定変更を停止した。公開sitemapの
  11承認URLと既存submissionを維持し、通常クロールとSearch Console側の再処理を待つ。
- 同日の後続read-only確認では、検索clicks 0、登録済み1、未登録3、sitemapは`成功しました`・最終読込
  2026-08-13・検出10ページだった。公開sitemap 11 URLとの差1件を未登録理由や失敗へ補完しない。GA4は
  過去28日で`page_view` 10、`qualified_session` 8、`outbound_click`行なし、Realtime 0だった。
  自己確認訪問を分離できないため月次KPIへ転記せず、GSC/GA4とも設定変更・テスト送信を行っていない。

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

## 公開前30回監視

1日1回、30回のthread heartbeatでGmail、GSC、GA4、local QA、Gate A–Cをread-only確認する。
この監視は外部回答待ちの公開前監視であり、実shadow runの30日には算入しない。

- Gmailは対象6社を`automated_ack / waiting / information_request / substantive_partial /
  substantive_complete / affiliate_approved / rejected`へ分類する。送信、下書き、label変更、archiveは行わない。
- 実質回答だけを`fetch / store_raw / send_to_ai / derive / publish / retain_history / quote`へ分解し、
  回答にないfield、action、期限、attribution、retentionは`unreviewed`のままにする。
- GSCはquery/page生成状態、GA4は`page_view`と`qualified_session`の受信有無だけを確認する。
- rawメール、message ID、個人メール、PII、query、Affiliate URL・識別子を保存しない。
- 正常かつ変化なしなら`変化なし・Human操作なし`だけを通知する。
- 実質回答、承認・拒否、計測停止、test失敗、rights期限、重大誤記候補だけを通知する。
- 未承認source取得、実データ取込、外部送信、filter変更、deploy、push、indexing、公開、CTA変更は禁止する。

権利3社、Affiliate 3社、JP/ja需要、rights承認済み実データ、non-synthetic gold、開始日付き
`shadow_run: GO`が揃った後だけ実shadowを開始する。開始後はjob 99%以上、重大誤記0、例外24件以下、
自動化率80%以上、Human 720分以下、rollback fault合格を30日連続で検査する。
