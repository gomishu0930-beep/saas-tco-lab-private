# 現時点の導入 — あなたの操作表

基準日: 2026-08-01（Asia/Tokyo）

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
|A-H10|公開前版完了|カード不要Sitesを公開前originとして採用済み。実データ、indexing、CTA、DB、独自domainは別承認|2026-07-26 public-prelaunch GO|外部readbackとfail-closed経路を継続監視。実運用releaseはGate A–Cまで停止|cloud root credential|
|A-H11|P01–P03承認済み／P04–P12継続|Human確認済み価格をvendor・plan別に入力し、Humanシナリオを分離してP01–P12を確認|2026-08-03 `article_approve: P01,P02,P03`受領|承認scopeをcontractへ固定し、unknown依存claimだけSTOP。P01–P03は公開候補、残記事はreview継続|raw本文、PII、credential、tracking ID|
|A-H12|完了|`saastcolab.jp`の新規登録、Sites指定DNS、自動更新を完了する|2026-08-02 `domain: GO saastcolab.jp`受領。登録完了（有効期限2027-08-31）、Sites指定の4 recordをValue Domainへ保存し、個別domain設定の自動更新をON。2026-08-03にHTTPS/noindex read-back、GSC domain property所有確認、GA4 streamの新origin更新、旧originから同一path/queryへの1段301、Impact websiteのConnected確認を完了。拡張計測OFF、保持14か月、任意data sharing全OFF、internal filter test、同意前tag未読込、redirect loopなしを確認済み|indexとCTAは別GOまでHOLDする|registrar credential、住所、電話、メール、支払情報、DNS record値、verification値、GA4識別子|
|A-H13|150 query export時|KWFinder正規画面からJP/ja CSVをHuman exportする|`mangools_csv: done`|rawを保存せずvalidatorでsafe-summaryだけ生成|account情報、raw CSVのrepo保存|
|A-H14|記事承認後|index解除対象を確定する|`index_go: GO`|承認済み記事だけindex候補化。CTAは別GO|verification・tracking ID|

2026-08-02、Human ApproverがMangoolsの年次checkout総額452.40／632.40／1,172.40 USD、
同planの月払い比較値61.00／81.00／141.00 USD、Japan選択時VAT 0表示を確認し、P01–P03の
TCO節再生成を明示指示した。Basic、Premium、Agencyの年次総額を一次観測値へ昇格し、月額換算
37.70／52.70／97.70 USDと月払い比の約38%／35%／31%を固定式の派生値として記録した。
P03のSE Ranking・Semrush年次総額と移行費用はunknownのまま横断順位から除外する。2026-08-03、
Human Approver `omishu`がこの2026-08-02観測contractに基づく本文・TCO節を承認した。P01–P03は
公開候補へ登録済みだが、`index_go`未受領のためnoindex・CTA無効を維持する。

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

## Affiliate提携とrights回答の現在地

|会社|Affiliate現在地|rights回答|統合gateへの算入|次の本人操作|
|---|---|---|---:|---|
|Mangools|affiliate access有効、紹介素材発行済み|未回答。2026-07-26追送済み|0|rights回答を待つ。紹介IDは共有しない|
|HubSpot|2026-08-03 Impact画面でDeclined（low reach）を確認|未回答。2026-07-26追送済み|0|公開・流入実績を作るまで再申請しない。拒否を承認済みと数えない|
|Semrush|Impact Marketplace申請受領・website認証済み。個別申請の送信を試行したが未受領|回答あり|0|Marketplace承認を待つ。`Discover`表示後にSemrushを再申請し、受付receiptを確認する|
|SE Ranking|work email例外回答待ち|未回答。ticket 112501へ2026-07-26追送済み|0|回答まで再登録しない|
|Serpstat|未申請|回答あり・社内審査中。2026-07-26 due-diligence返信済み|0|authorized teamの8項目回答を待つ|

E10のImpact product feed確認は、Impact上でAffiliateがactiveになったpartnerだけがtriggerである。現在は
HubSpotはlow reachでDeclined、SemrushはMarketplace手続中であり、対象partnerは0社なのでHuman操作はまだ不要。
active通知後に`docs/IMPACT_PRODUCT_FEED_CHECKLIST.md`を使い、catalog有無とA1利用scopeを確認する。

HubSpotは2026-07-26にHumanのaction-time承認後、Impact申請を送信し、JPYを確定しました。2026-08-03に
Impact画面でlow reachを理由とするDeclinedを確認しました。公開・流入実績を作るまで再申請せず、追加表示された
Impact Marketplace設定、税務情報、受取情報は未操作です。Semrushは
2026-07-26に契約同意、Impact credential受付、SMS端末認証、既存Impact accountへのloginまで完了しました。同日、Humanのaction-time承認`impact_terms_accept: GO`後にPartner User AgreementとMaster Program Agreementへ同意しました。税務workflowは値を記録せず完了し、SaaS TCO Lab限定の公開profileも保存済みです。media propertyはwebsite認証済みで、Impact Marketplace申請は受領済みです。Humanの`semrush_submit: GO`後にSemrush個別申請の送信を再試行しましたが、既存Impact accountへのsign-in後はHubSpot homeへ遷移し、Semrushの受付画面・通知・受付メールはいずれも確認できませんでした。再認証の失敗ではなく、Marketplace承認前の導線または既存account callbackの停止と判定します。Marketplace承認後に`Discover`から再開し、受付receiptを確認します。申請中も承認済みと数えず、Affiliate、data rights、対象site、
payoutの全条件が揃った会社だけを1社と数えます。

## Google Ads以外のJP/ja需要source

第一候補を`Mangools KWFinderの正規画面からHumanが出力するCSV`へ確定します。既存のカード不要accountで、
凍結済み150 queryを投入でき、location/languageを指定した検索量と月次volumeをCSVで出力できます。
Mangools Termsはデータ利用をinternal business purposeとし、publicationにはattributionを求め、自動化は
API経由を前提とします。Humanが正規画面からexportし、rawをrepository外でvalidatorへ一度だけ渡す需要検証を
本decisionで承認します。CSVのraw、query別volume、Mangools固有IDはrepositoryへ保存せず、150 query一致、
合計volume、欠損、観測日、hashだけをsafe-summaryにします。API・browser自動取得は行いません。

|順位|source|採用判断|役割|停止条件|
|---:|---|---|---|---|
|1|Mangools KWFinder Human CSV|`human_export_approved`|公開前bootstrapのJP/ja volume|自動取得、raw保存、150 query不一致|
|2|Microsoft Advertising Keyword Planner|`contingency_unverified`|Mangools不許可時の代替|account作成GOなし、カード不要性未確認|
|3|Search Console|`available_waiting_data`|公開後の自サイト実需要|所有確認済み。初日データ処理中で実測queryは未生成|
|4|Google Trends|`supporting_only`|季節性・相対比較|絶対需要やCVRへ換算禁止|

`mangools_csv: done`はHumanがCSVを正規exportし、validatorでlocale、exact 150 query、欠損、重複、
観測日を検証した合図です。field-level回答は自動取得trackで追跡を続けますが、このHuman exportによる
internal demand検証を停止しません。

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
`Verified`となり、Marketplace進捗100%、Marketplace application受領を確認した。Semrush個別申請は送信を試行したが、既存accountへのsign-in後にHubSpot homeへ戻り、受付receiptは生成されなかった。

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
