# Revenue Cell V2 runbook

基準日: 2026-08-20 / 観測基準: 2026-08-19 / Asia/Tokyo

## 公開権限と正本

- 本書は実装・検証手順であり、公開、CTA activation、GA4管理画面変更、外部投稿の権限を付与しない。
- price・tax・renewal・cancellation・use-case fit・program規約はHuman確認済みcontractだけを使う。
- runtime destinationはsecretから読み、URL全文やtracking parameterを本書・event・logへ残さない。
- P11はnoindex, follow・CTA無効のまま維持する。

## Revenue Cells

|Cell|記事|型|現在のlocal状態|production状態|
|---|---|---|---|---|
|A|SVR01|比較型|XServer primary + ConoHa alternativeの最大2枠|Sites v38 / commit `af95bdb`。主1・代替1、開示先行、mobile overflowなしを外部read-back済み|
|B|SVR04|初期費用込み総額の単独型|XServerビジネスをHuman選定。owned-site限定の単独CTA|単独CTA 1件を外部read-back済み。外部媒体・deep-link・sub-IDはHOLD|

Cell Bはpage別GSC値を取得していないため、検索表示の多寡を推測して選んでいない。Human指示のfallbackである「初期費用込み総額」とrepository内intentが一致するSVR04を採用し、`cell_b: GO SVR04 xserver-business`によりXServerビジネスを単独vendorとして確定した。更新時請求額、解約条件、キャンペーン条件、A8.netのprogram別外部channel条件はunknownのまま保持する。

## Event contract

正本: `artifacts/revenue-cells/revenue-analytics-contract-v1.json`

|Event|発火条件|dedupe|主なdimension|
|---|---|---|---|
|`calculator_result_view`|server計算結果がviewportへ25%以上表示|同一DOM elementは1回|article / cell / version / channel / safe source・medium class / campaign / environment / traffic scope / test|
|`cta_view`|active affiliate CTAがviewportへ50%以上で1秒継続、または許可済みCTAを実click|同一DOM elementは1回|上記 + vendor / position / type|
|`cta_eligible_session`|上記のCTA view成立|sessionStorageでarticle + cell + versionごとに1回|article / cell / version / channel / safe source・medium class|
|`outbound_click`|active CTAかつ許可hostへのclick|sessionStorageでarticle + cell + version + vendor + positionごとに1回。GA4集計ではevent数でなくsessions-with-eventを使う|article / cell / version / vendor / position / type / channel / campaign|

一般の外部リンクは`external_link_click`とし、affiliate用`outbound_click`へ混ぜない。disabled CTAはanchorへ変換されないため、view/clickのselectorに一致しない。

### Safe campaign attribution

query stringは使用しない。site URLのfragmentだけに、列挙済みchannelと短いcampaign IDを置く。

```text
https://saastcolab.jp/servers/business-server-pricing#ch=note&cid=svr01-note-audit-01
```

fragmentはHTTP request、canonical、page_locationへ送られない。受理channelは`direct / organic / referral / note / x / partner / internal / unknown`だけ、campaignは英小文字・数字・hyphenの最大64文字だけである。外部referrerのhost名やqueryは保存せず、`referral` classへ丸める。最初に確認できたsafe acquisition classはsession内で保持し、同一site内の遷移で`internal`へ上書きしない。

## CTA eligible sessionとsafe aggregate

`page_view`をCTRの分母にしない。GA4から日次・article・cell・version・CTA・channel・safe source/medium class・campaignが同一のsafe aggregateだけを転記し、`examples/revenue_cell_daily_aggregate.json`の形にする。異なるcell/version/sourceを同じ入力へ混ぜるとvalidatorは停止する。

```sh
uv run python scripts/summarize_revenue_cells.py --input <safe-aggregate.json>
```

集計はproduction・external・test=falseだけを含める。internal、bot、test、local/previewは除外する。CTRの分子はGA4のevent countではなく、`outbound_click`を含むunique session数である。clean対象行が1件もないsummaryは`decision_ready=false`であり、0 outboundのSTOP判定へ使わない。maturityまたはcommissionが未取得なら、confirmed RPESは`null`のままにする。

Cell全体のCTRはGA4でarticle + cell + version + acquisition groupを固定し、`outbound_click`を1回以上含むsessionを数える。vendor/position別のevent表を合算してCell全体を作ると同一sessionが重複し得るため禁止する。Cell全体のsafe aggregateではvendor/positionを`none`として転記し、CTA別内訳は診断表として分ける。

### 日次最小レポート（未取得値は空欄）

この表へ仮値や0埋めをしない。GA4 Internal Trafficが`テスト`の間は、自己アクセス除外を確認できた行だけをcleanとして算入する。

|観測日|article|cell|version|channel|source class|medium class|campaign|clean eligible sessions|CTA view sessions|unique outbound sessions|outbound CTR|ASP clicks|pending件数|pending金額|confirmed件数|confirmed金額|
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| | | | | | | | | | | | | | | | |

|GSC観測日|SVR01 impressions|SVR01 clicks|SVR04 impressions|SVR04 clicks|server cluster impressions|server cluster clicks|
|---|---:|---:|---:|---:|---:|---:|
| | | | | | | |

ASP側に許可済みsub-IDがない間、ASP click以降はdate / network / vendor単位までとし、Cell A/Bへ推測配賦しない。

## Production read-back

2026-08-20にSites v38で実施済み。以後のreleaseでも同じ項目を再確認する。

1. `/servers/business-server-pricing`でPR表示がCTAより前にある。
2. active CTAが1 primary + 最大1 alternativeである。
3. `rel="sponsored noopener noreferrer"`、許可host、vendor/position/type属性を確認する。URL全文は報告しない。
4. `/servers/server-first-year-total`はCell B markerを持ち、XServerビジネスの単独CTAが1件だけである。ConoHaその他のaffiliate anchorは0件とする。
5. SVR02〜SVR09からSVR01へのintent別内部リンクを確認する。
6. P11はnoindex, follow、affiliate anchor 0件である。
7. consent前はGA通信がない。consent後にDebugViewでresult → CTA view → outboundの順を確認する。
8. 同じsessionで同じCTAを二度押しても`outbound_click`が1回であり、Cell Aを見た後でもCell Bの`cta_eligible_session`が別に1回発火することを確認する。
9. CTAを50%以上表示して1秒未満で離脱した場合は`cta_view`が発火せず、許可済みCTAを先にclickした場合は`cta_view`→`cta_eligible_session`→`outbound_click`の順で1回ずつ発火する。
10. 同意を撤回した後のtimer・clickでは追加eventが発火しない。

## Internal/test traffic

### Codex側で実装済み

- production / local / previewをaggregate contractで分離する。
- browser自動化を`bot`、明示flagを`internal`、test flagを`test_flag=true`として送る。
- query/referrer本文、IP、Cookie、affiliate URLは送らない。
- sessionStorageが利用できない場合、clean eligible/outboundのsession eventはfail-closedで送らない。

テスト端末ではDevTools Consoleで一時的に次を設定し、検証後に削除する。

```js
localStorage.setItem("saas_tco_lab_traffic_scope_v1", "internal")
localStorage.setItem("saas_tco_lab_test_traffic_v1", "1")
```

終了時:

```js
localStorage.removeItem("saas_tco_lab_traffic_scope_v1")
localStorage.removeItem("saas_tco_lab_test_traffic_v1")
```

### Human: GA4管理画面

現在のfilterは`test`。2026-08-22に`ga4_internal_ip_transmit: GO`を受領し、現回線を`traffic_type=internal`のdefinition ruleへ登録した。IP値はrepo・docs・報告へ保存していない。

1. 管理 → データの収集と修正 → データフィルタ。
2. Internal Trafficが`テスト`であることを確認。
3. DebugViewで自分のeventがinternal/testとして識別できるか確認。
4. Realtime/DebugViewで外部テスト1件が誤除外されないことを別回線で確認。
5. 24時間の比較後、Humanが`ga4_internal_filter: GO active`を明示した場合だけ有効化する。
6. 有効化後にeventが全消失した場合は直ちにHOLDへ戻し、設定値を推測で変更しない。

## ASP reconciliation

1. networkごとの確認期間をHumanがprogram詳細画面で確認する。
2. 許可されたexportだけを取得し、`affiliate-export-intake`でtransaction IDをhash化したlocal evidenceへ変換する。
3. GA4はdate / article / cell / vendor / position / channelのaggregate、ASPはdate / vendor / pending / confirmed / rejectedのaggregateで照合する。
4. network sub ID仕様がHuman確認されるまではcapability=`unknown`、sub ID付与は無効。
5. maturity期間前のoutboundをconfirmed 0として扱わない。
6. confirmed RPESは、成熟済みeligible sessionとconfirmed commissionの両方が揃った時だけ計算する。

## STOP conditions

- 30 eligible sessionsでoutbound 0: 現cell/version × 現流入をHOLDし、CTR 15%仮説を強く疑う。事業全体の失敗判定にはしない。
- 50 eligible sessionsでoutbound 0: 現versionを継続しない。1〜4件なら拡張しない。
- 100 eligible sessionsでoutbound 0〜2: 現cellを失敗扱い。3〜7件は再設計、8〜14件はcommission検証継続、15件以上は点推定上15%以上だがASP/EPCは未証明。
- 確認期間後outbound 100でconfirmed 0: program / merchant / intentの組合せを停止候補にする。
- productionとrepositoryが再び対応不能: deployをHOLDしrelease基線を復旧する。

100 eligible sessions未満だけを理由にCTA失敗とは判定しない。

## Revenue validation v1 監査（2026-08-23）

判定は**条件付きGO**。これは収益性の証明ではなく、Cell・version・safe acquisition単位の分母とunique outbound sessionを誤判定しにくくするための計測・公開境界の修正である。GSC再処理結果、clean eligible、ASP click、Pending、Confirmedは未取得であり、0として扱わない。

|ID|重大度|失敗モード|処置|
|---|---|---|---|
|R01|Critical|P11をruntime一覧へ誤登録するとsource未承認でも公開対象になり得る|source decision recordとの交差を強制し回帰test|
|R02|High|Cell A閲覧後のCell Bでeligible分母が欠落する|article + cell + version単位でsession dedupe|
|R03|High|variant前後を分離できない|固定versionをDOM・event・aggregateへ追加|
|R04|High|event countをoutbound sessionとしてCTR計算する|GA4 sessions-with-eventを正本にする|
|R05|High|Cell・source・CTAの異なる行が合算される|group不一致をvalidation error|
|R06|High|clickがobserverより先だとoutboundだけ発火する|許可clickを強いview証拠としてV→E→O順で記録|
|R07|High|内部遷移後にorganic/referralがinternalへ変わる|最初のsafe acquisition classをsession保持|
|R08|High|未承認deep-link/sub-ID queryでもCTAが有効化される|network別の既知query key集合以外を拒否|
|R09|High|SVR01から本番503のOperatorへ遷移する|公開記事からOperator linkを削除|
|R10|Medium|SVR04がactive CTAの下で外部linkなしと表示する|根拠表だけに限定した表現へ修正|
|R11|Medium|同意撤回後もtimer/click eventが続く|全eventでconsentを再確認|
|R12|Medium|storage利用不可時にsession eventが重複する|eligible/outboundをfail-closed|
|R13|Medium|瞬間表示をCTA viewとする|50%以上1秒、実clickは同等以上の証拠|
|R14|Medium|clean対象0行が0 outboundの証拠に見える|`decision_ready=false`を必須化|
|R15|Medium|不可能なsession数・金額関係を受理する|単調性とpositive conversionを検証|
|R16|External|server impressionsの未発生原因が再処理待ちか品質か未確定|コードで補完せずURL Inspectionで再分類|
|R17|Operational|GA4 Internal TrafficがTEST中でもself visitをclean扱いし得る|Human確認までclean KPIをHOLD|

### 週次review template

|週|article|cell|version|channel|source class|medium class|campaign|clean E sessions|V sessions|unique O sessions|ASP clicks|Pending件数|Pending金額|Confirmed件数|Confirmed金額|
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| | | | | | | | | | | | | | | | |

同一group内だけでE→V、V→O、E→Oを計算する。ASP側はnetwork・vendor・日付単位でGA4 unique Oとの差分を記録し、sub-IDが未承認の間はCell単位の成果帰属を主張しない。
