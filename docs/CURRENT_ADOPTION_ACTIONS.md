# 現時点の導入 — あなたの操作表

基準日: 2026-08-09（Asia/Tokyo）

2026-07-28のHuman decision `DR-2026-07-28-REVENUE-TRACK`により、P0–P18はmaintenance only、
人手予算はlaunch trackへ全振りする。rights model v2では、自動取得・価格DB・履歴DBはstrict gateを
維持し、Human確認済み公開価格をvendor・plan識別子、画面状態、出典URL・観測日・次回確認日付きで記事化するeditorial pathは
field-level書面許諾をlaunch blockerにしない。

2026-07-30の最終Human指示により、2026-08〜2026-10はHuman予算をlaunch track限定で月2,000分とし、
取引意図記事、TCO embed、構造化data、note/X再配信、日本ASP申請準備を先行する。2026-10-31に固定済み閾値で
継続・拡張・縮小を判定し、2026-11の通常720分へ戻すかを再判断する。

2026-07-28(3)およびE9–E10のHuman指示により、現在のHuman作業は次の四つだけに集約する。下のA-H表と
`docs/HUMAN_ACTION_MANUAL.md`は完了履歴またはtrigger後の参照であり、日常の追加作業ではない。

1. `docs/DOMAIN_MIGRATION_CHECKLIST.md`をdomain dayに実行する。
2. `docs/PRICE_CHECK_CHECKLIST.md`を見ながら`/operator`へ実値・billing toggle位置・価格表示の4区分を入力する。年払いはcheckout請求総額を一次値とし、前回差分を見てHuman確定する。
3. `docs/HUMAN_REPLY_CARD.md`からexact tokenを返す。Impact承認済みpartnerのfeed確認通知時だけ`docs/IMPACT_PRODUCT_FEED_CHECKLIST.md`も見る。
4. `docs/MONTHLY_15_MIN_ROUTINE.md`を月一回実行する。

それ以外のlocal検証、contract再検証、記事差込み、dashboard再生成、公開前QAはCodexが行う。

カード不要モードは2026-07-31で終了した。domain購入は開始カードのexact token
`domain: GO <domain>`、購入対象・初年度価格・更新価格のread-back、購入直前のHuman確認を満たした場合だけ進める。
その他の外部送信・規約同意・account作成・課金も対象別GOを必要とする。
例外として、2026-07-26のHuman指示により、実データ・Affiliate CTAを含まないSites公開前版だけを本番originへ公開した。

|ID|時期|本人が行うこと|完了の合図|Codexが続けること|共有禁止|
|---|---|---|---|---|---|
|A-H01|完了|GitHub repositoryと初回baselineを作成|2026-07-28公開化完了|`saas-tco-lab-private`はpublic。秘密scan後に匿名HTTP 200を確認済み。launch trackの未commit変更は未公開|PAT/SSH秘密鍵|
|A-H02|完了|Google Drive pluginをinstall/connectし専用folderを選択|2026-07-26完了|`SaaS TCO Lab`と7分類を作成済み。safe-summaryだけを投入する|契約全文、PIIをchat・Driveへ貼らない|
|A-H03|完了|Google Calendar pluginをconnectし専用calendarを選択|2026-07-26完了|非公開`SaaS TCO Lab`と5予定を作成・read-back済み|個人予定、calendar ID|
|A-H04|完了|確定済みoriginのSearch Console URL-prefix propertyをHTML tagで所有確認済み。query/page/country/device/dateとexport UIをread-back済み|2026-07-26 `gsc_verification_deploy: GO`実行済み|初日の処理完了後に実測query/page exportを取得する|verification token|
|A-H05|deploy・基本受信確認済み|専用GA4 streamへ同意制御tagをdeploy。任意data sharingと拡張計測は全OFF、retentionは14か月。同意前・拒否後0通信、同意後Realtime `page_view`を確認|2026-07-26 `ga4_tag_deploy: GO`実行済み|internal traffic filterは対象sourceを確認した別承認後だけtestからactiveへ移す|measurement secret、測定ID|
|A-H06|月末後|OpenAI API project、budget cap、API keyを本人管理で作成|`openai_project: done`|env参照方法、gold-set benchmark、routerを実装|API key、billing情報|
|A-H07|Affiliate承認後|各partnerからexportを本人取得可能にする|`affiliate_export_ready: <partner>`|safe summary、status mapping、settlement reconcile|tracking ID、税務/受取情報|
|A-H08|見送り|Notionを使うか決める|2026-07-26 `notion: skip`|GitHubを技術正本として継続。運用上の必要が実証された時だけ再評価|個人workspace全体|
|A-H09|100 evaluated runs後|ClaudeまたはGeminiの比較課金を承認|`challenger_budget: GO <provider>`|10–20%標本benchmarkを実行|API key、非公開契約|
|A-H10|editorial production稼働|Sitesを公開originとして採用し、rights model v2のHuman editorial laneだけを本番化|2026-07-26 public-prelaunch GOと後続のdomain・記事・index・CTA・deploy承認|9記事の外部readbackとfail-closed経路を継続監視。automated data pathはGate A–Cまで停止|cloud root credential|
|A-H11|進行中 — 12/12入力・10/12承認・9/12公開|Human確認済み価格をvendor・plan別に入力し、Humanシナリオを分離してP01–P12を確認|P01–P04・P06–P08・P10・P12を承認済みかつindex・Mangools CTA対象として外部read-back済み。P05は公式field修正と記事承認を完了したが未deploy|P09/P11は自データ未取得のため承認せず、P05とともにnoindex・CTA無効を維持|raw本文、PII、credential、tracking ID|
|A-H12|完了|`saastcolab.jp`の新規登録、Sites指定DNS、自動更新を完了する|2026-08-02 `domain: GO saastcolab.jp`受領。登録完了（有効期限2027-08-31）、Sites指定の4 recordをValue Domainへ保存し、個別domain設定の自動更新をON。2026-08-03にHTTPS/noindex read-back、GSC domain property所有確認、GA4 streamの新origin更新、旧originから同一path/queryへの1段301、Impact websiteのConnected確認を完了。拡張計測OFF、保持14か月、任意data sharing全OFF、internal filter test、同意前tag未読込、redirect loopなしを確認済み|9記事releaseのdomain・redirect・計測境界を維持する|registrar credential、住所、電話、メール、支払情報、DNS record値、verification値、GA4識別子|
|A-H13|完了 — v1.1分類済み|KWFinder正規画面からJP/ja CSVをHuman exportする|2026-08-05 batch-e/fを含む150件をexport・検証済み|rawをrepositoryへ保存せず、known/no_data/rejectedを分離したsafe-summaryだけを扱う|account情報、raw CSVのrepo保存、no_dataの0補完|
|A-H14|完了 — 9記事index境界確認済み|index解除対象を確定する|2026-08-03 `index_go: GO`、2026-08-08〜09の最優先タスク一括承認を受領|承認済みP01–P04・P06–P08・P10・P12だけindex可。その他記事と他HTML routeはnoindex|verification・tracking ID|

2026-08-02、Human ApproverがMangoolsの年次checkout総額452.40／632.40／1,172.40 USD、
同planの月払い比較値61.00／81.00／141.00 USD、Japan選択時VAT 0表示を確認し、P01–P03の
TCO節再生成を明示指示した。Basic、Premium、Agencyの年次総額を一次観測値へ昇格し、月額換算
37.70／52.70／97.70 USDと月払い比の約38%／35%／31%を固定式の派生値として記録した。
P03のSE Ranking・Semrush年次総額と移行費用はunknownのまま横断順位から除外する。2026-08-03、
Human Approver `omishu`がこの2026-08-02観測contractに基づく本文・TCO節を承認した。P01–P03は
公開候補へ登録後、2026-08-03の`index_go: GO`と`cta_go: GO mangools`を受領した。P01–P03を先行して
index可・Mangools CTA有効とした。2026-08-08にP06/P07を同じrelease境界へ追加し、P04・P05・P08–P12、
他HTML route、Mangools以外のCTAは無効を維持する。

2026-08-05、R1–R6の読者向け改稿、contract駆動SEO/OGメタ、承認済み記事だけの関連記事、
確認済み価格による計算機初期表示、人間可読JSON-LDをlocalで実装した。これは2026-08-03に承認された
公開中本文とは異なる改稿版であるため、P01–P03は再度の`article_approve`を受けるまでcommit・push・deployしない。
数値証拠そのもののreview statusは変更せず、改稿で新しい価格・税・通貨・課金周期を追加していない。
2026-08-06、Human Approver `omishu`から改稿版の`article_approve: P01,P02,P03`を受領した。
2026-08-08の`repository_update_push: GO`と`deploy_update: GO P01,P02,P03 R1-R6`に基づき、
commit `494c211`をpushし、Sites version 11へ公開した。外部read-backでP01–P03のみ
`index, follow`、OG/Twitter meta、承認記事間リンク、JSON-LD、開示先行、MangoolsのみのCTAを確認し、
P04–P12と他HTML routeのnoindex、他partner CTA無効を維持した。

P06とP07はP01–P03のHuman確認済みMangools観測を記事別contractへ再配置したlocal標本である。
P06は月払い61.00 USD、年次checkout総額452.40 USD、最低契約12か月を表示し、途中解約時の費用は
unknownのまま総額から除外する。P07は100 keyword research requests / 24h、従量超過単位・単価の
公式表示なし、Human scenario 400 lookup/月を分けて表示する。両記事とも新しい値を推測せず、
2026-08-07、Human Approver `omishu`から`article_approve: P06,P07`を受領し、本文と既存contractを承認済みにした。
2026-08-08の最優先タスク一括承認により、P06/P07をdeploy・index・既存の承認済みMangools CTAのrelease対象へ
追加した。同日、`CHECK-ALL: PASS`（Python 841件、schema export/diff、site tests、secret scan）後に
commit `793fdf3`をprivate remoteへpushし、Sites version 12・runtime環境revision 6を本番deployした。
外部read-backではP01–P03・P06・P07がHTTP 200かつ`index, follow`、各記事の開示がMangools CTAより前、
CTA送客先hostが`mangools.com`、`rel="sponsored noopener noreferrer"`であることを確認した。
P04/P05/P08–P12は`noindex, nofollow`かつCTA 0件、sitemapは上記5記事だけ、robotsは承認記事と
`/assets/`・faviconを許可し、Googlebot user agentで参照assetがHTTP 200だった。Search Consoleは
2026-08-09の後続read-only確認でsitemapを再読込し、検出5ページへ更新した。ページ集計は最終更新
2026-08-05のまま登録済み1・未登録3で、登録済み1件は旧HTTPルートである。承認記事のindex完了とは扱わない。

同日、P04/P08/P10を追加した8記事release候補をproduction workerへsynthetic runtime値でlocal dry-runした。
8記事だけが`index, follow`・canonical・開示先行Mangools CTA・robots Allow・sitemap対象となり、
P05/P09/P11/P12は`noindex, nofollow`・canonicalなし・CTAなしを維持することを回帰testへ固定した。
2026-08-09、Human Approverの「最優先タスクをすべて行い、承認系は承認扱い」とする実行指示を、
P04/P08/P10のdeploy・index・既存Mangools CTA追加へ限定適用した。`CHECK-ALL: PASS`済みcommit
`9aad7e6`をSites sourceへpushし、version 15・runtime revision 7として本番deployした。
外部read-backでは8記事がHTTP 200、`index, follow`、canonical、Mangools送客先host、
`rel="sponsored noopener noreferrer"`を満たし、robots allowlistとsitemapも同じ8記事で一致した。
開示先行はproduction workerのDOM順序guardと回帰testで維持する。P05/P09/P11/P12、運営route、
operator routeはnoindex、canonicalなし、CTAなしを維持し、Mangools以外のCTAは追加していない。
また、明示的`not_applicable`をunknownと混ぜずdashboardへ別表示し、数値の適用外をHumanが確認済みなら
記事標本reviewへ進められるようにした。P12の現contractはまだunknownなので、Humanの方針確認までは証拠待ちを維持する。

同日の継続指示に基づき、P12の確認間隔fieldを再評価した。これは日数の未取得ではなく「全field共通の
単一間隔を適用せず、各観測の次回確認日を個別に管理する」という既存の運用方針であるため、数値を補わず
`not_applicable`へ訂正し、本文を読者向けに修正して承認した。`CHECK-ALL: PASS`（Python 844件、schema、
site、secret scan）後、commit `d2aa788`をpushし、Sites version 17・runtime revision 8として公開した。
外部read-backではP12を含む9記事がHTTP 200、`index, follow`、canonical、開示先行Mangools CTA、
`rel="sponsored noopener noreferrer"`を満たし、robots allowlistとsitemap 9件が一致した。P05/P09/P11は
noindex、canonicalなし、CTAなしを維持する。

公開9記事のnote/X再配信素材も確認済みclaimだけで再生成した。各noteは約1,300〜1,500字、Xは8投稿、
PR表記を先頭、記事URLを末尾に固定し、公開用placeholderを除去した。3-voice／claim-evidence packageは
一時領域で9件すべて`ready_for_human_review`、material claim coverage 100%、authorityなしを確認した。
P18固定scopeを増やさないため検証用control artifactはrepositoryへ残さず、既存の回帰testだけを保存する。

観測contract v2.3では価格表示を`none`、`annual_discount_permanent`、`time_limited_promo`、`unknown`の
4区分とする。計算HOLDは期間限定promoとunknownだけである。2026-08-02にHuman token
`sale_banner_state: annual_discount_permanent mangools`を受領し、P01–P03のMangools 22 fieldへ反映した。
後続のexact値指示によりMangoolsの年次price 5 observationは確定済みである。他vendorのunknownから
値を推測せず、関連claimだけを停止する。

## Plugin画面での既定選択

- Google Drive: `Allow read actions / ask before writes`相当。対象folderを限定する。
- Google Calendar: 書き込み前確認を維持する。
- Notion: 未導入を既定とし、GitHub Issuesで運用しにくいと判明した時だけ使う。
- Gmail: 読取・下書きは許容、送信は毎回Human確認を維持する。

## 返信テンプレート

```text
gsc_property: pending / done
ga4_property: partial / done
measurement_origin: GO https://saas-tco-lab-jp.shukun0930.chatgpt.site
openai_project: pending / done
initial_gold_labels: pending / done
notion: use / skip
```

既存H1–H10と同様、credentialや識別子の値そのものは返信しない。

公開brandは`SaaS TCO Lab`、Human Approver表示は`omishu`とする。法的名義はHumanの
private recordで確認済みだが、実名をrepo、Calendar、event、log、promptへ転記しない。

候補優先順位は、`Mangools`、`HubSpot`、`SE Ranking`、`Semrush`、`Serpstat`の順とする。
Google Ads／Keyword Plannerは2026-07-26のHuman判断でskipし、自動再試行しない。JP/ja需要は、
Mangools KWFinderのHuman exportまたは公開後のSearch Console実測で満たす。Mangools CSVはinternal
business purposeの需要判断に限定し、volumeのsafe-summaryだけをrepositoryへ保存できる。

2026-08-09、Humanが完了したcheckout後の正規Dashboardをread-onlyで確認し、
**Mangools Basic契約有効化済み**と記録した。credential、認証URL、請求手段、invoice、個人情報は
保存していない。残りqueryの取得は引き続きHuman exportに限定し、API・browser自動取得へは拡張しない。
export完了後の更新停止は、Human本人がsubscription画面で実行するまで未完了である。

## Affiliate提携とrights回答の現在地

Affiliate partner状態の非機密な正本として`docs/AFFILIATE_PARTNER_LEDGER.json`を追加した。A8.net、
もしもアフィリエイト、バリューコマースはAccount登録済みである。もしもアフィリエイトは
2026-08-07の正規管理画面read-backで確認し、バリューコマースは2026-08-08のHuman token
`valuecommerce_registration: done`により本登録完了を記録した。登録完了は個別programの提携承認として扱わない。
2026-08-06にA8.netの7 programをread-onlyで調査し、XServerビジネスへ2026-08-07に申請した。
2026-08-08の正規管理画面では同programが「参加中」、提携日2026-08-07、終了日未定と表示されることを
read-backし、Affiliate提携を承認済みへ更新した。同日、バリューコマースのABLENET共用サーバーも
個別条件を確認して提携申請し、正規画面の「提携済み」をread-backした。ログイン後だけ表示される報酬額・確定率は
`restricted_dashboard_only`として値をrepositoryへ保存しない。
XServerビジネスも開示先行、runtime destination設定、partner別`cta_go`が
すべて揃うまでCTA対象外としてfail-closedを維持する。台帳はruntime secretの参照名だけを持ち、tracking ID、広告link URL、
本人情報、secret値を保存しない。

|会社|Affiliate現在地|rights回答|統合gateへの算入|次の本人操作|
|---|---|---|---:|---|
|Mangools|affiliate access有効、紹介素材発行済み|未回答。2026-07-26追送済み|0|rights回答を待つ。紹介IDは共有しない|
|A8.net|Account登録済み、XServerビジネス提携承認済み|条件要約を台帳v1.1へ記録。報酬値は非保存|1|servers記事承認後にruntime destinationとpartner別CTA gateを設定|
|もしもアフィリエイト|Account・saastcolab.jpメディア登録済み、ロリポップ提携承認済み・他3件未申請|ロリポップの詳細条件と承認状態を台帳へ記録。報酬値は非保存|1|servers記事承認後にruntime destinationとpartner別CTA gateを設定|
|バリューコマース|Account本登録済み、ABLENET共用サーバー提携承認済み|個別条件を台帳v1.1へ要約。報酬値は非保存|1|servers記事承認後にruntime destinationとpartner別CTA gateを設定|
|HubSpot|2026-08-03 Impact画面でDeclined（low reach）を確認|未回答。2026-07-26追送済み|0|公開・流入実績を作るまで再申請しない。拒否を承認済みと数えない|
|Semrush|Impact Marketplaceは2026-08-09に却下済み。個別申請は未成立|回答あり|0|公開記事・流入実績を蓄積し、再申請条件を満たした後に新しいexact GOで再評価する|
|SE Ranking|work email例外回答待ち|未回答。ticket 112501へ2026-07-26追送済み|0|回答まで再登録しない|
|Serpstat|未申請|回答あり・社内審査中。2026-07-26 due-diligence返信済み|0|authorized teamの8項目回答を待つ|

A8.netで直接確認できなかったHubSpot、kintone、サイボウズ、ConoHa、Benchmark Email、blastmailは
不存在と断定せず、もしもアフィリエイトとバリューコマースの確認待ちとする。単価×需要表は
`docs/JP_ASP_APPLICATION_CHECKLIST.md`に置き、W6 safe-summaryがないカテゴリを有望扱いしない。

E10のImpact product feed確認は、Impact上でAffiliateがactiveになったpartnerだけがtriggerである。現在は
HubSpotはlow reachでDeclined、Impact Marketplace自体も2026-08-09に却下済みで、Semrush個別申請は未成立である。
対象partnerは0社なのでHuman操作はまだ不要であり、流入実績形成前の再申請も行わない。
active通知後に`docs/IMPACT_PRODUCT_FEED_CHECKLIST.md`を使い、catalog有無とA1利用scopeを確認する。

2026-08-09、もしもアフィリエイトのメディア登録審査・運営・SNS掲載ガイドラインを
ログイン済み正規画面でread-only確認した。公開9記事、独自domain、独自の編集内容、出典、広告表示先行、
誤認ランキングを作らない境界は適合方向である。生成AIの補助利用は全記事の広告表示と広告掲載ポリシーで
明示し、公開前に人が一次情報・数値・計算結果を確認する実態を記載する。最終的な3ガイドライン確認checkboxは
Human本人だけが押す。もしものX向けpromotionはフォロワー3,000人以上という画面条件があるため、条件達成を
read-backするまでXへもしも広告を掲載しない。サイト登録・ロリポップ提携とX掲載可否を混同しない。
Human token `moshimo_media_attestation: done`受領後、正規画面で`saastcolab.jp`のメディア登録を確認した。
申請中一覧は0件、提携中一覧は楽天市場だけだったため、過去のロリポップ申請は成立していないと判定した。
既存の個別GOに基づき、本人申込専用ではない`ロリポップ！レンタルサーバー会員登録`だけへ提携申請し、
同画面で即時に`提携中`へ変わったことをread-backした。報酬額、広告URL、識別子は保存していない。
CTAはruntime destination、servers記事承認、開示先行、partner別CTA GOが揃うまで無効である。

HubSpotは2026-07-26にHumanのaction-time承認後、Impact申請を送信し、JPYを確定しました。2026-08-03に
Impact画面でlow reachを理由とするDeclinedを確認しました。公開・流入実績を作るまで再申請せず、追加表示された
Impact Marketplace設定、税務情報、受取情報は未操作です。Semrushは
2026-07-26に契約同意、Impact credential受付、SMS端末認証、既存Impact accountへのloginまで完了しました。同日、Humanのaction-time承認`impact_terms_accept: GO`後にPartner User AgreementとMaster Program Agreementへ同意しました。税務workflowは値を記録せず完了し、SaaS TCO Lab限定の公開profileも保存済みです。media propertyはwebsite認証済みで、Impact Marketplace申請は受領済みです。Humanの`semrush_submit: GO`後にSemrush個別申請の送信を再試行しましたが、既存Impact accountへのsign-in後はHubSpot homeへ遷移し、Semrushの受付画面・通知・受付メールはいずれも確認できませんでした。2026-08-09に既存accountの任意business profileをpublisher・individual・website・product/service reviewsとして完了し、申請完了画面の後にMarketplace状態が`却下済み`であることをread-backしました。新規に追加したwebsite channelのverificationは成立しておらず、過去のwebsite認証記録をこのchannelへ読み替えません。Marketplace却下中はSemrushを再申請せず、公開記事・流入実績が改善した後に新しいexact GOで再評価します。却下を承認済みと数えず、Affiliate、data rights、対象site、
payoutの全条件が揃った会社だけを1社と数えます。

## Google Ads以外のJP/ja需要source

第一候補を`Mangools KWFinderの正規画面からHumanが出力するCSV`へ確定します。既存のカード不要accountで、
凍結済み150 queryを投入でき、location/languageを指定した検索量と月次volumeをCSVで出力できます。
Mangools Termsはデータ利用をinternal business purposeとし、publicationにはattributionを求め、自動化は
API経由を前提とします。Humanが正規画面からexportし、rawをrepository外でvalidatorへ一度だけ渡す需要検証を
本decisionで承認します。CSVのraw、query別volume、Mangools固有IDはrepositoryへ保存せず、150 query一致、
known/no_data/rejectedの行数、known行だけの合計、no_data率、観測日、hashだけをsafe-summaryにします。
no_dataは0として合計へ混ぜません。API・browser自動取得は行いません。

|順位|source|採用判断|役割|停止条件|
|---:|---|---|---|---|
|1|Mangools KWFinder Human CSV|`human_export_approved`|公開前bootstrapのJP/ja volume|自動取得、raw保存、150 query不一致|
|2|Microsoft Advertising Keyword Planner|`contingency_unverified`|Mangools不許可時の代替|account作成GOなし、カード不要性未確認|
|3|Search Console|`available_waiting_data`|公開後の自サイト実需要|所有確認済み。初日データ処理中で実測queryは未生成|
|4|Google Trends|`supporting_only`|季節性・相対比較|絶対需要やCVRへ換算禁止|

2026-08-05のvalidator v1.1結果は、exact 150 query、重複0、Japan以外0、known 34、no_data 116、
rejected 0、known合計9,610、no_data率0.77333333です。月20万円の既定逆算22,227 sessionに対して、
`known_volume_floor_below_required_incomplete`と判定しました。これはknown下限での拡張推奨であり、
no_dataを0とみなした総需要不足の確定ではありません。raw CSVとquery別volumeはrepository外に維持します。
field-level回答は自動取得trackで追跡を続けますが、このHuman exportによるinternal demand検証を停止しません。

2026-08-05、Human Approver `omishu`は上記known下限に基づき`scope_expand: GO (準備scope)`を承認しました。
X1の現ニッチ追加60語と、X2のservers / accounting / crm / forms / email_marketing各40語を
`docs/CATEGORY_EXPANSION_SLATE.md`と`examples/`へ凍結します。X3としてカテゴリ別90日判定を
`docs/PRODUCTION_ROADMAP.md`へ固定しました。公開、ASP申請、新vendor照会、価格取得、CTAは別GOまでHOLDです。

2026-08-06、Human Approverは`category_primary: GO servers`を発効しました。serversは40/40検証済み、
known 28,220/月、14 known、26 no_data、rejected 0です。A8.net管理画面で確認された報酬・確定率と
そこから逆算できる値は`restricted_dashboard_only`としてrepositoryへ保存しません。旧Y1の6記事案は
政策v2で、凍結40語から選ぶ取引意図・具体性proxyの20記事へ置き換えました。query別競合性は未観測のため
「競合が薄い」とは断定しません。記事順は開示→計算機→結果→CTA枠→根拠表、作業は20分×3工程です。
Y2のHuman価格観測checklist、Y3のservers TCO contract・Python/TypeScript計算機をlocalで準備します。
XServerビジネスの個別提携は2026-08-08に承認済みをread-backしたが、servers記事の公開、index、CTAは
記事contractとruntime destinationが揃うまでHOLDです。P01–P03は既存資産として
維持し、Mangools CTA以外を追加しません。accounting / forms / crm / email_marketingは需要unknownのまま、
有望と判定しません。serversの比較CTAは承認partner 2社以上、1社なら単独CTAとし、構造上の1社依存100%を
dashboardで警告します。2026-12-31の固定撤退ラインは公開20本、GSC clicks 300/月、confirmed 1件の全達成です。

2026-08-09、accountingはKWFinder正規画面のJapan指定で40/40を再取得し、凍結slate完全一致を
validatorで確認しました。known 9、no_data 31、rejected 0、known合計6,320/月、no_data率77.5%で、
必要22,227 sessionのknown下限を下回ります。したがってaccountingは現時点で拡張せず、P18固定scopeを増やさないため
safe-summaryは既存のカテゴリ表へ記録しました。CRMは同日に30/40まで取得しましたが、完全一致前の部分合計は採用せず、残り10語を
検索回数枠の回復後に取得します。forms、email_marketing、SEO追加60語は引き続き未観測です。
同日の再試行では、KWFinder正規画面が検索枠の単純な日次resetではなく`plan upgrade required`を表示しました。
残りはCRM 10、forms 40、email_marketing 40、SEO追加60の計150語です。自動upgradeや課金は行わず、
Basic月払い61.00 USDを上限とする1か月利用とexport後の自動更新停止について、exact Human支払承認を待ちます。

Z6–Z7としてservers記事の計算機をzero-inputへ固定しました。記事には承認済みcontractから事前計算する
総額表と、12/24/36か月・用途区分のbuttonだけを置き、金額、seat、価格基準、税区分の入力欄は置きません。
unknown、未承認、用途対象外は順位から除外し、unknownは`未確認`と表示します。従来の任意入力式計算機は
`/methodology/#detailed-calculator`だけに移設し、記事からは1リンクで参照します。serversの承認済み価格は
まだ0件なので、local実装には実価格をseedせず、Python/TypeScriptのsynthetic goldenだけを使います。

2026-08-06、serversのHuman入力導線を`/operator/servers/`へ追加し、Y2の11 fieldをvendor・plan単位で
`CategoryExpansionInput(category_id=servers, state=candidate_only)`候補へ変換できるようにしました。値、出典URL、
観測日、次回確認日、画面の支払周期、価格表示分類がそろい、Humanが確定操作をした場合だけ候補JSONを出します。
`/servers/business-server-pricing/`にはSVR01のnoindex標本を追加しました。実価格0件、CTA 0件、順位なしを維持し、
価格入力、記事承認、index、partner CTAはそれぞれ別gateです。

2026-08-09、既存の固定acceptance scopeを増やさず、SVR02–SVR20をSVR01と同じfail-closed rendererで
切り替えるlocal候補viewを追加し、`/operator/servers/`へ20本の確認待ち一覧を作成しました。
各routeはPR表示を最初に置き、zero-input計算機は承認済み価格0件、
CTAはgate通過partner 0件、実額・順位・推奨0件、`noindex, nofollow`です。記事別の価格観測・Human承認・
index・runtime destination・partner別CTAは未実行であり、production deployもこのlocal実装には含めません。

同日のexternal read-backでは、A8.netのXServerビジネスprogramは第一申請候補ですが、申請時の掲載siteが旧mediaを
指していました。2026-08-06の`a8_reauth: done`後、A8の登録site `SaaS TCO Lab`を主サイトへ変更し、
画面read-backで反映を確認しました。XServerビジネスの個別提携申請は同日の対象名付きGOにより送信済みです。
2026-08-07のread-only再確認では、A8.netはSaaS TCO Labが主サイトのままで、XServerビジネスの詳細画面も
再認証なしで表示できました。未提携・SaaS TCO Lab選択済みを確認後に申請し、完了画面をread-backしました。
もしもアフィリエイトは本登録済み管理画面へアクセスでき、`レンタルサーバー`検索12件から
シンレンタルサーバー、ConoHa WING、ロリポップ！レンタルサーバー、お名前.comレンタルサーバーを
優先候補として台帳へ追加しました。ロリポップ！は2026-08-09に提携承認済みで、他3件は未申請です。
非公開の報酬値・広告ID・tracking URLは保存していません。
ロリポップ！は詳細画面で、3か月以上の新規契約と入金、本人等の申込・更新等の対象外条件、審査なし、
再訪問90日、承認期限60日、広告出稿条件を確認し、safe-summaryだけを台帳へ更新しました。
バリューコマースは検索結果確認後にsession切れとなり、2026-08-07の再確認で本登録前の仮登録状態と判明しました。

同日、バリューコマースのsession切れ直前の検索結果概要で、サーバー候補として
`ABLENETレンタルサーバー（共用サーバー）`を確認しました。2026-08-08に本登録後の個別画面で成果・除外・
検索広告条件を確認して提携申請し、「提携済み」と広告素材9件の表示をread-backしました。広告素材は選択・取得せず、
非公開の報酬値・確定率・広告ID・tracking URLは保存していません。runtime destination、記事承認、CTAは別gateです。

同日、XServerビジネス公式料金画面からSVR01の候補入力をBrowser sessionへ準備しました。初期費用と共有
スタンダードの容量だけを確認済み候補とし、年次請求総額、更新、キャッシュバック、ドメイン特典の金銭価値、
転送量等は理由付きunknownのままです。構造validationは合格していますが、Human確認と候補JSON保存前なので
repositoryのeditorial contractには採用していません。2026-08-07、受領済み`server_price_input: done SVR01`と
`local_download_permission: GO localhost SVR01`に基づきHuman確認と候補JSON保存を実行しました。候補は
`artifacts/category-expansion-inputs/`へ分離し、正本modelで検証済みです。既知値は初期費用16,500円（税込）と
容量700GB、残る9 fieldはunknownです。candidate-onlyのため、総額・順位・CTA・indexのHOLDを維持します。
2026-08-08の追加Browser観測候補では、公式料金シミュレーションに共有スタンダード12か月の一括前払額
50,160円（税込）、初期費用16,500円（別途）が表示され、公式機能ページには自動バックアップが全plan標準、
初期費用・月額費用0円、Web・mail・MySQL各14日分保持と表示されました。一方、更新用シミュレーションは
plan・12か月選択後も金額が`--`表示でした。これらはHuman確認前の候補であり、既存contractのHuman入力値を
上書きせず、基本料金・backup料金の確定と更新料unknownの維持をOperatorでHumanが確認するまでcanonical採用しません。
2026-08-09、`/operator/servers/`へ保存済みcandidate-only JSONのローカル再読込と価格テキストの候補抽出を追加した。
JSONと貼り付け原文はHuman選択後だけブラウザメモリで処理し、公開前HTML、端末保存、外部通信へ含めない。
Safariでは既存SVR01の11 fieldを復元し、上記の年次請求総額とbackup月額0円を候補として事前入力した。
構造validation合格後、Human Approverの全承認指示を受け、追加候補の観測日を2026-08-08、次回確認日を2026-09-07へ整合し、
`SVR01-servers-category-expansion-input-v2-2026-08-08.json`として追記保存した。**SVR01追加候補のHuman確認完了**。
正本modelで11 field、known 4、unknown 7を再検証済みである。candidate-onlyは維持し、更新料等のunknownを
0へ補完せず、記事承認・index・CTA・順位にはまだ採用しない。
同日、公式公開画面から抽出したcampaign、通常額・promo額、storage、CPU、転送量、domain特典、
2年目更新、移行、backupの9候補を`/operator/servers/`へHuman確認専用カードとして追加した。
これらは`data-candidate-authority="none"`であり、`svr01_candidates: confirm_all`またはfield単位の
訂正をHuman本人から受領するまでcontract、TCO、順位、記事、index、CTAへ採用しない。
同日、Operatorにcandidate-onlyからの準備判定を追加し、TCO field、用途判定field、Human field確認を
別々に`READY / HOLD`表示するようにした。`not_applicable`は理由付き明示値として扱う一方、unknown、
期間限定価格、通貨・税・請求周期・一次観測区分の不明はfail-closedを維持する。3判定がREADYになっても
自動昇格はせず、記事承認・index・CTAは従来どおり別のHuman gateである。現在のSVR01はTCOと用途判定の
両方がHOLDで、canonical価格、zero-input計算、順位、記事公開へは未採用である。

同日、`asp_program_apply: GO A8.net XServerビジネス`のscopeで提携申請完了画面を確認しました。台帳は
`pending`へ更新しました。2026-08-08、A8.netの参加中プログラム一覧でXServerビジネスの提携日と終了日未定を
read-backし、台帳を`approved`へ更新しました。非公開報酬、確定率、program IDは保存していません。
`asp_program_apply: GO もしも ロリポップ！レンタルサーバー`では
申請ボタン押下後にsessionが失効し、結果画面を確認できませんでした。重複送信を避けるため台帳は
`not_applied`のまま保守的に維持しました。2026-08-09のHumanによるガイドライン確認とメディア登録後、
申請中0件をread-backし、同じ個別GOのscopeで通常Affiliateプログラムだけを申請して即時承認を確認しました。

同日、ValueCommerceのABLENET共用サーバーは個別条件の確認後に提携申請し、「提携済み」をread-backしました。
serversカテゴリの承認済みprogramはXServerビジネス、ロリポップ、ABLENETの3件です。ただしconfirmed commission shareは
未観測であり、各partnerともruntime destination・記事承認・開示先行・個別`cta_go`がそろうまでCTAへ出しません。

2026-08-09、上記3件のCTAをrepositoryへURL保存せず実行時だけ有効化するserver runtime gateを実装しました。
SVR01のexact承認、`INDEX_GO`、`CTA_GO`、partner別`SERVER_CTA_GO`、提携有効フラグ、ASP固有host/pathの
runtime destinationがすべて成立したpartnerだけを表示します。1社だけ成立した場合は単独CTA、2社以上成立時は
比較CTAとし、PR開示より前には挿入しません。query付きSVR02–SVR20候補はSVR01が承認されてもnoindex・CTA無効を
維持します。現productionにはserver承認・destination・server CTA GOを設定していないため、公開状態は変わりません。

同日、XServerビジネスの正規公開画面を追加でread-only確認しました。機能一覧は共有serverについて
「転送量課金なし」「転送量無制限」を明示しています。一方、契約更新simulationは共有スタンダードと12か月を
選択しても`--円/月`のままで、更新時請求総額を確定できませんでした。したがって転送量は数値上限なしの
`not_applicable`候補、更新料は`unknown`候補ですが、Human field確認前のため既存candidate-only contractへは
書き込まず、TCO・用途判定HOLDを維持します。

同日、Human Approverの継続指示「承認系に関してはすべて承認扱い」を、Operatorに固定したexact token
`svr01_candidates: confirm_all`へ適用した。公式画面の9表示をHuman確認済みとし、保存済みSVR01 v2 contractの
11 fieldをfield-review済みに更新した。転送量は`not_applicable`へ反映したが、CPUの`-`表示、期間限定
キャッシュバック、更新額、ドメイン特典の実額・期間は推測せずunknownを維持する。基本料金自体も
`time_limited_promo`分類のため、TCO・用途判定・contract昇格・順位・記事・index・CTAは引き続きHOLDである。

既存のHuman承認済みMangools観測を別記事で再入力しないため、`/operator`へ証拠再利用prefillを追加しました。
P04は最低利用者数と月契約料金、P08は基本料金・必須addon料金・必要利用者数、P10は表示価格と税fieldだけを
同じvendor・planかつ同じ値型の承認済みfieldから候補化します。P04の未観測Human時間、P08のaddon課金単位、
P10のJPY換算レートは数値を作らず、理由・確認先・期限を持つ`unknown`候補として事前入力します。
対象記事では全fieldを`unreviewed`へ戻し、Human確認前にcontractへ保存しません。これは記事承認・index・CTA authorityを持ちません。
P04の月間運用時間と導入時間はvendor観測ではなくHuman scenarioへ修正し、公式料金と自運用時間が同じ
vendor・plan行へ混在しないようにしました。P04・P08・P10は再利用候補をHuman確認し、2026-08-09に
記事contractと本文を承認済みへ進めました。当時のP05・P09・P11は、同義の承認済み証拠がないfieldを
明示的な`unknown`としてcontract化しました。構造検証は合格していますが確認済み実値が0件のため、記事は
`unreviewed`、noindex、CTA無効を維持します。P12は共通確認間隔を適用しない方針を`not_applicable`として
承認・公開済みです。この時点では12/12入力、9/12承認、9/12公開でした。

2026-08-09のMangools公式料金画面read-backでは、Basicは追加seat不可、Premiumは追加seat 3、Agencyは
追加seat 5と表示され、Site analysisは順に20 / 70 / 150 requests / 24hであった。これはP05既存fieldの
「管理者数」「Agency Pack」「月間監査ページ」と同義ではないため、自動変換しない。OperatorへAgencyを対象とする
4項目のfield修正候補を`authority=none`で表示し、`p05_field_scope: approve mangools_agency_actual_fields`
または訂正をHuman本人から受領するまでP05 contract・本文・index・CTAを変更しない。移行支援料金は公式料金画面に
見当たらないことだけを根拠に0円・対象外とはせずunknownを維持する。

同日、Human Approverの継続指示「承認系に関してはすべて承認扱い」を、Operatorに固定したexact token
`p05_field_scope: approve mangools_agency_actual_fields`へ適用した。旧fieldの管理者数、Agency Pack、月間監査ページを
廃止し、Mangools Agencyの`5 extra seats available`、承認済み年次checkout総額1,172.40 USD、
`Site analysis 150 requests / 24h`へ修正した。seat総数・管理者数・月間値への換算は行わず、移行支援料金だけは
unknownを維持する。P05 contractの4 fieldをHuman承認済みにし、本文を公式単位へ合わせて改稿した。
P05は記事承認済みだが、production deploy・index・CTAは個別release前のため無効である。これにより現在は
12/12入力、10/12承認、9/12公開で、P09/P11だけが自データ待ちである。

P01のnote記事は2026-08-04に公開済みです。2026-08-06の`note_edit_go: GO P01 PR先頭追記`により、
公開記事の本文先頭へ`[PR]`を追記し、公開read-backで反映を確認しました。localの再配信templateは
確認済み実額・公式記事URL・冒頭PR表示を含む版です。2026-08-06のHuman承認
`account_repurpose: GO @fanza_poll_lab retire_fanza`、`legacy_posts: DELETE`、`profile_update: GO`、
`legacy_posts_delete_final: GO 14`に基づき、当該未使用accountをSaaS専用mediaへ転用しました。
表示名は`SaaS TCO Lab`、handleは`@saastcolab`、websiteは`https://saastcolab.jp`です。
旧投稿10件を削除し、repost 3件を解除し、元投稿削除に伴うself-repost 1件の消滅を確認した結果、
外部read-backで投稿0件を確認しました。別accountで稼働中のFANZA運用には変更を加えておらず、
brand、domain、repo、credential、analyticsの分離を維持します。2026-08-08の`x_post: GO P01`に基づき、
冒頭PR表示、承認済みP01 claim、`saastcolab.jp`の記事URLだけでXスレッド8件を公開した。
ASP広告link、非公開報酬、tracking IDは含めていない。公開後のread-backで`@saastcolab`の(1/8)と(8/8)を確認した。

2026-08-09、公開後もhomepage、広告表示、About、運営者情報、privacyに残っていた「公開前・CTA 0件」の
旧表示を現在の9記事・Mangools CTA稼働状態へ更新した。homepageから未承認P09へのlinkを削除し、承認済み
P01/P02/P12だけを案内する。`CHECK-ALL: PASS`後のcommit `1d9389b`をSites version 19として公開した。
外部read-backではhomepageと信用情報routeが新しい現在地を表示し、P01は`index, follow`、開示先行、
Mangools CTA 1件、送客hostとlink属性が合格、P05は`noindex`・CTA 0件、sitemapは9件のままである。
Affiliate識別子・URL全文・非公開条件は記録していない。

## field-level rights decision slate

原文メールはGmailを正本とし、repositoryには保存しません。以下のhashは原文hashではなく、PIIを除いた
正規化safe-summaryのhashです。`Human案`は相手方の回答どおりに分類した候補で、Human Approverが
`approve`するまでcanonical `SourcePolicy`にはなりません。

2026-07-26、Human Approverはdecision record version `2026-07-26.1`として、source commit
`9c27338769f309341e0dab105bfc75e547c440a8`の下記分類を承認しました。承認対象は保守的な分類だけで、
vendorから未付与の利用権を生成せず、source activation、公開、analytics送信も許可しません。

|会社|field / action|相手方回答|Human案|価格FieldEvidenceへの利用|
|---|---|---|---|---|
|Semrush|automated fetch|website dataの自動収集は許可しない|`prohibited`|不可|
|Semrush|minimal/ongoing storage|pricing/featuresの継続保存は許可しない|`prohibited`|不可|
|Semrush|history|historical databaseは許可しない|`prohibited`|不可|
|Semrush|independent editorial|正確・最新の独立contentはAffiliate条件下で可能|`conditional_approved`|数値fieldの保存許可ではない|
|Semrush|affiliate link|Program Termsと広告表示に従う|`conditional_approved`|提携承認後だけCTA候補|
|Semrush|derived 12m TCO / termination|明示回答なし|`unreviewed`|不可|
|Serpstat|fetch/store/display/derive/history/termination|事前の明示書面同意が必要、社内審査中|`unreviewed`|不可|
|Serpstat|API / attribution|承認時は公式API、出典linkと観測日を推奨|`conditional_process_only`|API利用許可ではない|
|Mangools / HubSpot / SE Ranking|全field|返信なし|`unreviewed`|不可|

- Semrush safe-summary SHA-256: `f560bbbc5d4d902767efba421ae5190636cbd13404cb1e710dbdb7aed4651f8e`
- Serpstat safe-summary SHA-256: `be46d37c0df2cb547ba1436948fb32c1d1ee2ed6513811d4639bfcca4aa615b2`
- 結論: 自動取得・価格DB・履歴DB用の承認済み`FieldEvidence`は`0件`でありstrict STOPを維持します。
  human editorial pathでは書面許諾を待たず、vendor・plan識別子、Human入力値または明示的unknown、出典URL、観測日、次回確認日を揃えたfieldを
  証拠候補にできます。Humanシナリオはvendor観測と分離します。unknownを使う計算・記事承認と、禁止・未審査の自動取得権への補完は行いません。

## Human gold label — 15件の確認候補

これはlabel方針を確認するためのprelabel slateです。実観測ではないため全件`synthetic=true`、
status=`CANDIDATE_ONLY`です。Humanが内容を確認しても、rights承認済みの実データへ差し替えるまでは
初期学習gateの「15件non-synthetic」を満たしません。

Human Approverは2026-07-26にG01–G15を`approve_all`しました。全件のsynthetic状態は維持します。

|ID|domain|入力状況|期待label|
|---|---|---|---|
|G01|field_accuracy|月額だけ確認でき、年契約discountが不明|年額を推測せず`quarantine`|
|G02|field_accuracy|税込・税別の明記がない|taxをunknownのまま`quarantine`|
|G03|field_accuracy|quotaは確認済み、overage単価は不明|quotaとoverageを分離し単価はunknown|
|G04|policy_decision|権限者が自動取得を明示禁止|fetch=`prohibited`、処理STOP|
|G05|policy_decision|独立記事は可、TCO派生は未回答|editorialだけ条件付き、derive=`unreviewed`|
|G06|policy_decision|許諾期限を過ぎたfield|期限切れとしてdeny、再審査へ|
|G07|content_brief|料金意図だがseat・利用量条件がない|対象条件を埋めるまでdraft STOP|
|G08|content_brief|代替記事で各社の前提条件が異なる|同一利用条件へ正規化してから比較|
|G09|content_brief|移行記事がsubscription料金だけを扱う|重複契約・作業時間・教育費を追加|
|G10|claim_citation|数値claimにsource URLだけがある|field hash・取得日・期限不足でreject|
|G11|claim_citation|短いparaphraseはあるがderive権がない|引用・要約に流用せずreject|
|G12|claim_citation|公式source間で値が矛盾|勝手に最新値を採らずconflict quarantine|
|G13|cta_conversion|Affiliate未承認partnerへのCTA|CTA disabled|
|G14|cta_conversion|開示文の前にaffiliate linkがある|順序違反でCTA disabled|
|G15|cta_conversion|click実績のみ、confirmed commissionなし|revenue/EPCへ換算せずunknown|

## 合成記事構造 — 12件の標本確認

全件が合成fixture、noindex、CTA disabledです。確認は構造だけを対象とし、価格、rights、Affiliate、
indexing、公開の承認にはなりません。

Human Approverは2026-07-26にP01–P12を`approve_all`しました。

|ID|記事構造|intent / page type|確認する問い|
|---|---|---|---|
|P01|料金計算|price_check / pricing|seat数と利用量をそろえると12か月総額はいくらか|
|P02|プラン比較|compare / comparison|同じ利用条件で複数プランをどう比較するか|
|P03|代替候補|replace / alternatives|置き換え候補をTCOと適合条件でどう絞るか|
|P04|小規模チーム適合|fit_check / use_case_fit|少人数運用で固定費と人手を抑えられるか|
|P05|組織利用適合|fit_check / use_case_fit|権限・監査・運用費を含めて組織要件に合うか|
|P06|年契約と月契約|compare / comparison|commitmentと解約リスクを含む総額差はいくらか|
|P07|従量超過|price_check / pricing|利用量が基準を超えた時の増分費用はいくらか|
|P08|追加機能費用|price_check / pricing|必須addonを含めた実効総額はいくらか|
|P09|移行コスト|migrate / migration|移行作業・重複契約・教育を含む初年度費用はいくらか|
|P10|日本向け税・通貨|verify_method / methodology|JPY換算と日本向け税表示をどう検証するか|
|P11|損益分岐|fit_check / use_case_fit|削減時間と運用費から導入の損益分岐をどう求めるか|
|P12|根拠の検証|verify_method / methodology|field単位の根拠・権利・期限をどう監査するか|

確認後は次の形式だけを返信します。`approve_all`はprelabel/構造の妥当性確認であり、実観測化や公開GOではありません。

```text
rights_decision_slate: approve / revise <ID:修正>
gold_prelabel_slate: approve_all / revise <G-ID:修正> / reject <G-ID>
pilot_structure_slate: approve_all / revise <P-ID:修正> / reject <P-ID>
```

## Search Console / GA4の現在地

2026-07-26、Humanの「未使用FANZA環境を転用してよい」という承認に基づき、既存GA4の
アカウント名を`SaaS TCO Lab`、プロパティ名を`SaaS TCO Lab — Web`へ変更し、画面上で
保存後の値をread-backした。旧環境には受信データ、実装済みtag、Search Console連携、
custom definitionがなく、初期作成以外の運用変更もなかった。

ただし、旧Search Console propertyは成人向けを連想させるURL-prefixそのものに固定され、
現在そのoriginはDNS解決もしない。propertyは改名・別URLへの付け替えができないため、
SaaS用途へは転用しない。GA4内の旧web streamも同じlegacy originを指すため、本番collectorには
採用しない。中立originは2026-07-26に
`https://saas-tco-lab-jp.shukun0930.chatgpt.site`へ確定したが、専用property・streamの検証までは
`gsc_property`と`ga4_property`を完了扱いにしない。

同日、Humanの明示指定に従い、任意のGoogle data sharing 4項目をすべてOFF、event data retentionを
14か月へ変更し、保存後の画面でread-backした。ユーザーデータ保持は既存の14か月を維持した。
その後、新originのSearch Console propertyと専用GA4 streamを作成した。2026-07-26の個別GO後、
GSC verificationと同意制御GA4を公開し、Search Console所有確認、同意前・拒否後0通信、同意後の
Realtime `page_view`受信まで確認した。未完了は初日のSearch Console実測生成と、別承認を要する
internal traffic filterのactive化だけである。

確定したoriginを変更する場合だけ、次の形式で新しいURLを返信する。新しいdeploy、DNS変更、
credential作成をこの返信だけで承認するものではない。

```text
measurement_origin: GO https://<new-neutral-public-origin>
ga4_data_sharing: OFF / KEEP
ga4_event_retention: 14_months / KEEP_2_months
```

`ga4_data_sharing: OFF`と`ga4_event_retention: 14_months`は設定・read-back済み。origin確定後は、
新origin専用stream、deny既定のconsent、`qualified_session`・`comparison_interaction`・
`outbound_click`、DebugView、内部traffic除外、新Search Console property、GA4 linkの順で検証する。
PII、affiliate URL、測定ID、verification token、個人メールはartifactやevent parameterに保存しない。

2026-07-26、Search Consoleは新originのURL-prefix propertyを作成し、個別GO後にruntime HTML tagを
公開して所有確認した。query/page/country/device/dateとexport UIは利用可能で、初日の実測だけ処理中である。
GA4は同originの`SaaS TCO Lab — Public Web`へ同意制御tagを公開した。runtime値がない場合はmarkupと
Google向けCSP許可を出さず、有効時も訪問者の同意前と拒否後はGoogle scriptを読み込まない。
同意後のRealtime `page_view`受信を確認済み。2026-07-26の追加確認では`page_view` 2、
`qualified_session` 2までread-backしたが、実装確認の訪問を含むため需要・CVR・収益へ算入しない。実行・検証・rollback手順は
`docs/GSC_GA4_DEPLOYMENT_GATE.md`を正本とする。

2026-08-09のS6再確認では、Search Consoleのdomain propertyでsitemapは`成功しました`であり、後続確認で
最終読み込み2026-08-09、検出5ページへ更新されました。ページ集計は最終更新2026-08-05、登録済み1、
未登録3で、登録済み1件は旧HTTPルートです。承認記事のindex完了とは扱わず、再送信やURL検査登録は
行っていません。GA4 Realtimeの過去30分は0件で、過去28日イベント表では`page_view` 7、
`qualified_session` 7、`outbound_click`は行自体がありませんでした。実装確認訪問を含むため、これらを
月次需要・CVR・収益へ算入しません。

2026-08-09、GA4管理画面で`saastcolab.jp`のSearch Console domain propertyと
`SaaS TCO Lab — Public Web` streamの連携を作成し、連携済み行をread-backした。連携に伴って表示される
利用者メール、stream ID、verification値はrepository・報告へ保存しない。internal traffic filterはtest、
拡張計測OFF、同意既定denyを変更していない。同日のP12追加後の公開sitemapは9 URLであり、
Search Console側の次回再読込までは検出5ページのまま処理待ちとする。

```text
gsc_verification_deploy: GO / STOP
ga4_tag_deploy: GO / STOP
```

上記2件は2026-07-26に`GO`受領・実行済みで、再返信は不要である。

同日、直近14日の対象vendor・Affiliateメールをread-onlyで再確認した。追送後の新しい実質回答、
Affiliate承認、拒否は0件で、受付確認・survey・既存審査中threadはGate A/Bへ算入しない。
今後30回の日次確認は`docs/GSC_GA4_DEPLOYMENT_GATE.md`の公開前監視手順に従い、
変化またはHuman判断が必要な時だけ通知する。

## 公開前originの現在地

2026-07-26、Humanの「本番で使用するURLを使う」指示を、`SaaS TCO Lab`の公開前originを
一般閲覧可能な本番URLへ置く承認として実行した。scopeはSites version 1、commit
`17123624f55090465970ee6b27917cb04dc54594`、上記originに限定する。条件は全ページ`noindex`、
外部link 0件、実在vendorの価格・評価・Affiliate CTA 0件、公開allowlist 6経路である。
外部readbackでは公開6経路がHTTP 200、`/operator`と`/comparison`がHTTP 503、`robots.txt`が
`Disallow: /`、全応答が`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`であることを確認した。
この承認は実データ取得、実価格公開、indexing、Affiliate link、GA4送信、独自domain、課金へ拡張しない。

2026-07-26、Humanの`impact_verification_deploy: GO`後にImpact website認証専用のSites更新を公開した。
sourceはruntime secretが存在する時だけ`impact-site-verification` metaをHTMLへ挿入し、値そのものをrepoへ
保存しない。Impact公式手順に合わせてmetaを`<head>`内の最初のmetaとするversion 3を再検証・公開し、
外部readbackでHTTP 200、meta位置、従来のnoindex security headerを確認した。Impact画面ではwebsiteが
`Verified`となり、当時のMarketplace進捗100%、Marketplace application受領を確認した。Semrush個別申請は送信を試行したが、既存accountへのsign-in後にHubSpot homeへ戻り、受付receiptは生成されなかった。2026-08-09の最新read-backではMarketplaceは`却下済み`であり、この後続状態を現在地とする。

同日、HumanのGSC/GA4個別GO後にversion 5を公開した。verification値とmeasurement値はSites runtime
secretだけへ保存し、repositoryへ保存していない。外部readbackでImpact meta first、GSC meta、noindex、
同意前・拒否後0通信、同意後tag読込とRealtime `page_view`を確認した。

`ga4_property: done`は中立origin、consent、event taxonomy、DebugView、内部traffic除外の全条件を
満たした時だけ許可する。`gsc_property: done`は中立originの所有確認とread-only export contractを
検証した時だけ許可する。legacy propertyの存在だけでは完了にしない。

## Drive / Calendarの現在地

Driveの`SaaS TCO Lab`直下には、`00-Control`、`10-Rights`、`20-Affiliate`、
`30-Demand`、`40-Editorial`、`50-Exports-Safe`、`90-Archive`を作成済みです。
raw契約全文、個人情報、credential、tracking IDは置かず、承認済みsafe-summaryだけを受け入れます。

専用Calendarは一般公開・共有・追加通知なしで作成済みです。2026-07-26、次の5予定を
`Asia/Tokyo`の09:00–09:15、非公開、予定を塞がない、通知・参加者・Meet・場所なしで作成し、
検索read-backした。

|予定案|日付・周期|目的|
|---|---|---|
|5社rights回答30日確認|2026-08-22 09:00|未回答先への再照会判断|
|5社rights回答90日確認|2026-10-21 09:00|候補維持・代替vendor判断|
|5社rights回答180日確認|2027-01-19 09:00|長期未回答sourceのkill判断|
|Mangools tier確認|毎月4日 09:00|直近3か月平均とcommission tier確認|
|Mangools conversion確認|毎月15日 09:00|承認済みconversionとexport可否確認|

予定は専用Calendarだけに作成済みで、個人Calendar、参加者、Google Meet、場所、個人情報を
追加していない。繰り返し2件はCalendar側で毎月展開されることを確認済みである。
