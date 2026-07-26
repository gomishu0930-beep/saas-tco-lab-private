# 現時点の導入 — あなたの操作表

基準日: 2026-07-26（Asia/Tokyo）

この表は新しい導入計画でHuman本人が行う箇所だけをまとめる。既存H1–H10のrights・Affiliate・
Google Ads・公開手順は`docs/HUMAN_ACTION_MANUAL.md`を優先する。

2026-07-31まではカード不要モードとし、Google Workspace、domain購入、OpenAI API、外部AI課金、
有料cloud・有料hosting・有料trialを保留する。カード不要でも外部送信・規約同意・account作成は対象別GOを必要とする。
例外として、2026-07-26のHuman指示により、実データ・Affiliate CTAを含まないSites公開前版だけを本番originへ公開した。

|ID|時期|本人が行うこと|完了の合図|Codexが続けること|共有禁止|
|---|---|---|---|---|---|
|A-H01|完了|private GitHub repositoryと初回baselineを作成|2026-07-26完了|`saas-tco-lab-private`のprivate設定、`main`、500-file baseline、remote CI全3jobをread-back済み|PAT/SSH秘密鍵|
|A-H02|完了|Google Drive pluginをinstall/connectし専用folderを選択|2026-07-26完了|`SaaS TCO Lab`と7分類を作成済み。safe-summaryだけを投入する|契約全文、PIIをchat・Driveへ貼らない|
|A-H03|完了|Google Calendar pluginをconnectし専用calendarを選択|2026-07-26完了|非公開`SaaS TCO Lab`と5予定を作成・read-back済み|個人予定、calendar ID|
|A-H04|property作成済み・所有確認待ち|確定済みoriginのSearch Console URL-prefix propertyは作成済み。所有確認用の公開site変更は未承認|`gsc_property: done`|確認tag/fileを別gateでdeployし、所有確認とread-only query/page export contractを検証|verification token|
|A-H05|stream作成済み・計測実装待ち|確定済みoriginの専用GA4 streamを作成済み。任意data sharingは全OFF、event retentionは14か月。tag未設置・送信未開始|`ga4_stream: done`|別gateでconsent付きtag、event taxonomy、DebugView、内部traffic除外を設定・検証|measurement secret、測定ID|
|A-H06|月末後|OpenAI API project、budget cap、API keyを本人管理で作成|`openai_project: done`|env参照方法、gold-set benchmark、routerを実装|API key、billing情報|
|A-H07|Affiliate承認後|各partnerからexportを本人取得可能にする|`affiliate_export_ready: <partner>`|safe summary、status mapping、settlement reconcile|tracking ID、税務/受取情報|
|A-H08|見送り|Notionを使うか決める|2026-07-26 `notion: skip`|GitHubを技術正本として継続。運用上の必要が実証された時だけ再評価|個人workspace全体|
|A-H09|100 evaluated runs後|ClaudeまたはGeminiの比較課金を承認|`challenger_budget: GO <provider>`|10–20%標本benchmarkを実行|API key、非公開契約|
|A-H10|公開前版完了|カード不要Sitesを公開前originとして採用済み。実データ、indexing、CTA、DB、独自domainは別承認|2026-07-26 public-prelaunch GO|外部readbackとfail-closed経路を継続監視。実運用releaseはGate A–Cまで停止|cloud root credential|
|A-H11|自データ取得開始前|Google Ads以外の承認済みJP/ja需要export、field evidence、初回15件以上のHuman gold labelを確認|`jp_ja_export: done`、`field_evidence: done`、`initial_gold_labels: done`|署名付き初期学習品質bundleを作り、低品質batchを開始前にSTOP|raw本文、PII、credential、tracking ID|

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
権利承認済みの代替exportまたは公開後のSearch Console実測で満たす。

## Affiliate提携とrights回答の現在地

|会社|Affiliate現在地|rights回答|統合gateへの算入|次の本人操作|
|---|---|---|---:|---|
|Mangools|affiliate access有効、紹介素材発行済み|未回答|0|rights回答を待つ。紹介IDは共有しない|
|HubSpot|2026-07-26 Impact申請送信済み・審査待ち|未回答|0|審査結果を待つ。申請中を承認済みと数えない|
|Semrush|Impact Marketplace規約同意・税務workflow・公開profile完了。SaaS TCO Lab media propertyは未認証、申請未送信|回答あり|0|認証metaだけのSites version 2公開を承認し、website認証後もSemrush最終申請は別GOまで停止する|
|SE Ranking|work email例外回答待ち|未回答|0|回答まで再登録しない|
|Serpstat|未申請|回答あり・社内審査中。2026-07-26 due-diligence返信済み|0|authorized teamの8項目回答を待つ|

HubSpotは2026-07-26にHumanのaction-time承認後、Impact申請を送信し、JPYを確定しました。現在は
審査待ちで、追加表示されたImpact Marketplace設定、税務情報、受取情報は未操作です。Semrushは
2026-07-26に契約同意、Impact credential受付、SMS端末認証、既存Impact accountへのloginまで完了しました。同日、Humanのaction-time承認`impact_terms_accept: GO`後にPartner User AgreementとMaster Program Agreementへ同意しました。税務workflowは値を記録せず完了し、SaaS TCO Lab限定の公開profileも保存済みです。media propertyは登録済みですがwebsite認証前で、認証metaをruntime secretから出すSites version 2は保存のみ、未公開です。Semrush申請は未送信です。申請中も承認済みと数えず、Affiliate、data rights、対象site、
payoutの全条件が揃った会社だけを1社と数えます。

## Google Ads以外のJP/ja需要source

第一候補を`Mangools KWFinderの正規画面からHumanが出力するCSV`へ確定します。既存のカード不要accountで、
凍結済み150 queryを投入でき、location/languageを指定した検索量と月次volumeをCSVで出力できます。
ただしMangools Termsはデータ利用をinternal business purposeとし、publicationにはattributionを求め、
自動化はAPI経由を前提とします。照会回答がまだないため状態は`selected_pending_rights`であり、現時点の
CSV取得・repository取込・記事利用はすべてSTOPです。

|順位|source|採用判断|役割|停止条件|
|---:|---|---|---|---|
|1|Mangools KWFinder Human CSV|`selected_pending_rights`|公開前bootstrapのJP/ja volume|field-level書面回答がない|
|2|Microsoft Advertising Keyword Planner|`contingency_unverified`|Mangools不許可時の代替|account作成GOなし、カード不要性未確認|
|3|Search Console|`available_after_property`|公開後の自サイト実需要|origin確定済み、property・実測データは未作成|
|4|Google Trends|`supporting_only`|季節性・相対比較|絶対需要やCVRへ換算禁止|

`jp_ja_export: done`はMangoolsから8権利の書面回答を得て、HumanがCSVを正規exportし、locale、欠損、
重複、取得時刻、権利receiptを検証した後だけ使用します。

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
- 結論: 現時点で、価格・limit・TCO用の承認済み`FieldEvidence`は`0件`。禁止・未審査を
  approvedへ補完せず、実データ取得を開始しません。

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
確認済みの未完了項目は、同意シグナル未実装、内部traffic filterがtest、DebugView実データなし、
新originのSearch Console propertyと専用GA4 streamが未作成である。

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

2026-07-26、Search Consoleは新originのURL-prefix propertyを作成した。所有確認には公開siteの
`<head>`へ確認tagを追加するか、確認fileを置く必要があり、新しいpublic deployは別gateのため停止した。
GA4は同originの`SaaS TCO Lab — Public Web` streamを作成しread-backしたが、tagは設置せず、
analytics送信も開始していない。次に必要なのは作成承認ではなく、公開site変更と送信開始の個別承認である。

```text
gsc_verification_deploy: GO / STOP
ga4_tag_deploy: GO / STOP
impact_verification_deploy: GO / STOP
```

## 公開前originの現在地

2026-07-26、Humanの「本番で使用するURLを使う」指示を、`SaaS TCO Lab`の公開前originを
一般閲覧可能な本番URLへ置く承認として実行した。scopeはSites version 1、commit
`17123624f55090465970ee6b27917cb04dc54594`、上記originに限定する。条件は全ページ`noindex`、
外部link 0件、実在vendorの価格・評価・Affiliate CTA 0件、公開allowlist 6経路である。
外部readbackでは公開6経路がHTTP 200、`/operator`と`/comparison`がHTTP 503、`robots.txt`が
`Disallow: /`、全応答が`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`であることを確認した。
この承認は実データ取得、実価格公開、indexing、Affiliate link、GA4送信、独自domain、課金へ拡張しない。

2026-07-26、Impact website認証専用のSites version 2を保存した。sourceはruntime secretが存在する時だけ
`impact-site-verification` metaをHTMLへ挿入し、値そのものをrepoへ保存しない。local build・testは全件合格し、
version 2は未deployである。既存の一般公開version 1を更新する前に`impact_verification_deploy: GO`を必要とする。

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
