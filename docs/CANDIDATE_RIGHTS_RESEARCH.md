# SaaS比較候補5社：権利・Affiliate一次情報調査

初回確認日: 2026-07-21、返信反映日: 2026-07-26（Asia/Tokyo）

対象: Semrush、SE Ranking、Mangools、Serpstat、HubSpot

## 結論

公開Affiliate Programは5社すべてで確認済みです。Mangoolsはaffiliate accessと紹介素材の発行まで到達し、HubSpotとSemrushはImpact上の契約同意checkbox直前まで準備しました。ただし、申請中や単なるaccount発行を「実利用可能な提携」と数えず、公開料金ページを継続取得し、最小fieldを保存し、比較表・12か月TCO・価格履歴として商用公開する一連の権利を明示確認できた会社も0社です。したがって統合gateは現時点で **0/3、STOP** です。

これは各社の価格を人が一度閲覧できないという意味ではありません。Affiliateとして紹介できること、サービス内部のデータをAPI利用できること、各社自身の価格・利用上限を取得・保存・比較・履歴化できることは、それぞれ別の権利です。契約上の明示がない用途を、報酬の高さや一般的な比較記事の存在から推定承認しません。

本書は法的助言ではなく、実装をfail-closedにするための運用調査です。

## 判定記号

- **確認済み**: 公式一次情報が当該用途を明示的に許可、禁止、または条件化している。
- **推定**: 公式情報から用途との整合性は見えるが、その権利を直接は付与していない。
- **unknown**: 明示規定を確認できない、複数規定が衝突する、またはログイン後の契約確認が必要。
- **未取得**: account、affiliate承認、tracking link、書面許諾を実際には取得していない。

「確認済み」は「許可」の意味とは限りません。禁止・制限を確認できた場合も確認済みと表記し、内容を併記します。

## 2026-07-26 rights回答のread-back

Gmailをread-onlyで確認した。回答本文はrepositoryへ保存せず、送信者address、thread ID、全文、署名を
転記しない。下記SHA-256はメール原文ではなく、field判定だけを正規化したsafe-summaryに対するhashである。

|会社|回答状態|権限判定|使える範囲|使えない／未審査の範囲|safe-summary SHA-256|
|---|---|---|---|---|---|
|Semrush|回答あり|Affiliate担当からの明示回答|独立した正確・最新の記事と、Program Terms・広告表示に従うaffiliate linkは条件付き可|website dataの自動取得、継続保存、履歴DB化は不可。12か月TCO派生、終了時処理は未審査|`f560bbbc5d4d902767efba421ae5190636cbd13404cb1e710dbdb7aed4651f8e`|
|Serpstat|回答あり・社内審査中|Customer Supportの手続回答。最終許諾権限は未確認|承認後は公式APIを推奨し、出典linkと観測日の表示を求める方針|照会1–5、8は事前の明示書面同意が必要。item別のYesはまだ0件|`be46d37c0df2cb547ba1436948fb32c1d1ee2ed6513811d4639bfcca4aa615b2`|
|Mangools|未回答|—|—|全fieldを`unreviewed`としてfail-closed|—|
|HubSpot|未回答|—|—|全fieldを`unreviewed`としてfail-closed|—|
|SE Ranking|未回答|—|—|全fieldを`unreviewed`としてfail-closed|—|

Semrushの「条件付き可」はcontent制作とaffiliate promotionの範囲だけであり、価格fieldを
`FieldEvidence`へ採用する許可ではない。SerpstatのAPI推奨もAPI利用許諾そのものではない。
Humanがこの分類を承認しても、相手方が付与していない取得・保存・派生・公開権は生じない。

## 5社rights matrix

|会社|低頻度の自動取得|最小field保存|比較表示|派生12か月TCO|価格履歴|商標・素材|Affiliate参加|現判定|
|---|---|---|---|---|---|---|---|---|
|Semrush|**回答で禁止**: website dataの自動収集は不可。公式APIは別規約|**回答で禁止**: website pricing/featuresの継続保存は不可|**条件付き可**: 正確・最新の独立記事。系統的field転載は不可|**未回答**|**回答で禁止**: website dataの履歴DB化は不可|**条件付き可**: publication ruleとAffiliate Termsに従う|**契約同意直前・未申請**|data sourceはSTOP。手動検証記事だけ候補|
|SE Ranking|**unknown**: 公開価格pageのautomation許諾なし。Serviceはinternal use|**unknown**|**unknown**: Affiliate素材の限定licenseはあるが、SE Ranking contentの複製・派生は書面許諾が原則|**unknown**|**unknown**|**確認済み・Affiliate素材のみ条件付き**|**確認済み・公開契約あり**。現account/linkは未取得|優先照会、未承認|
|Mangools|**unknown**: 公式pageは公開だが、IP利用はinternal businessに限定|**unknown**|**unknown**: Affiliate promotionは可能だが、IPの商用再利用は書面同意が原則|**unknown**|**unknown**|**推定**: 提供bannerは利用可能。ブランドのPPC/domain/social名利用は禁止|**確認済み・free accountで自動access**。現account/linkは未取得|最優先照会、未承認|
|Serpstat|**書面同意待ち**|**書面同意待ち**|**書面同意待ち**|**書面同意待ち**|**書面同意待ち**|**未回答**|**未申請**|社内審査中、全data field STOP|
|HubSpot|**unknown**: 一般Site Contentは非商用利用に限定。Affiliateの個別許諾範囲は別途確認が必要|**unknown**|**推定**: software reviewer/content creatorを募集するが、Contentの複製・商用利用は包括許諾されない|**unknown**|**unknown**|**確認済み・採用後の提供素材のみ条件付き**|**確認済み・要審査**。現account/linkは未取得|優先照会、未承認|

いずれも、比較ページに必要な7権利のうち1つでも`unknown`なら`source_policy=approved`にしません。低頻度であっても、robots遵守だけで契約上の保存・商用表示・履歴利用が許可されたことにはなりません。

## 1. Semrush

### 公式確認

- 2026-07-24のAffiliate担当回答は、website data（pricing/featuresを含む）のscraping等による
  自動取得、継続保存、履歴database化を許可しないと明示した。独立した正確・最新のcontentと
  Affiliate Terms・広告表示に従うlink利用は可能だが、12か月TCO派生と終了時処理は未回答だった。
- [Terms of Service（2026-02-19更新）](https://www.semrush.com/company/legal/terms-of-service/)は、Website/Services/APIをinternal business purposeに限定し、Service contentのharvest/scrapeを禁止しています。
- [Semrush API usage restrictions](https://developer.semrush.com/api/v4/introduction/api-usage-restrictions/)は、10 requests/second、10 concurrent requestsに加え、明示的な書面同意なしでAPI情報を1か月超cacheできないとしています。
- [公式Pricing](https://www.semrush.com/pricing/seo-ai-search/)には現行plan、年/月価格、limits、add-onが掲載されています。ただし公開掲載は、第三者による自動保存・商用履歴化の許諾ではありません。
- [Affiliate Program](https://www.semrush.com/lp/affiliate-program/en/)は、comparison pieceをpromotion方法として挙げ、標準価格と全顧客向けpromotionの紹介を認めています。一方、応募を審査し、content creatorの目安として月間1,000 unique visitorsまたは相当のorganic social audienceを示し、未完成siteを通常承認しないと明記しています。
- 同Affiliate pageではlast-click / cookie 120日、productとtierにより最大$450/sale・trial最大$10を案内しています。正確なAffiliate TermsはImpactのsign-up pageで確認する方式なので、本調査では契約全文を確認済みにできません。
- [Trademark and Brand Usage Policy](https://www.semrush.com/company/legal/brand-policy/)は、publicationでのproduct名・一定のscreenshot利用条件、誤認防止、表示方法を定め、AffiliateにはAffiliate Termsも併用するとしています。

### rights判定

|権利|判定|理由|
|---|---|---|
|取得|回答で禁止|website dataの定常自動取得は行わない。公式APIは別契約・別用途として再審査が必要|
|保存|回答で禁止|website pricing/featuresの継続保存とcanonical DB採用は不可|
|比較表示|条件付き可|正確・最新の独立記事は可能。価格fieldの系統的保存・転載権とは分離する|
|派生TCO|unknown|価格fieldから12か月TCOを生成・商用表示する権利の明示なし|
|履歴|回答で禁止|website dataのhistorical databaseを作らない|
|商標|確認済み・条件付き|publication ruleに従う。広告・domain・誤認表示は別制限。Affiliate条件を優先|
|Affiliate|契約同意直前 / 未申請|Impactの契約checkboxはHuman本人の確認・同意待ち|

### 結論

自動価格DBのsource候補からは外す。Affiliate承認後も、公式pageをHumanが都度確認し、保存を伴わない
独立記事へ縮小できる場合だけ採用候補にする。派生TCOは未回答のため表示しない。

## 2. SE Ranking

### 公式確認

- [Terms of Service（2026-06-25更新）](https://seranking.com/legal/terms-of-service.html)は、Service利用をinternal useに限定し、Provider IP/Serviceのcopy、derivative work、distribution、publicationを制限しています。
- [API commercial-use guideline](https://seranking.com/api/usage-guidelines-for-commercial-purposes/)はAPI dataのcommercial useをTerms準拠で認めますが、direct competitorはaccess/use/distribution前にexplicit consentが必要です。これはSE Ranking自身の価格pageを比較DBへ保存する包括許諾ではありません。
- [公式Pricing](https://seranking.com/subscription.html)にはplan価格、seat、tracking、API/MCP、add-on等が掲載されています。
- [Affiliate Agreement（2025-05-06）](https://seranking.com/legal/affiliate.html)は、referral link、last-click / cookie 120日、non-coupon affiliateの30%、$50以上で14日ごとのpayout、米国外の者を含むW-8BEN/W-8BEN-E等の税務書類を定めています。
- Affiliate Agreementは、提供されたlogo/trademark/banner等だけを、promotion目的で、無改変・revocable licenseとして使えるとします。brand keyword広告、商標をdomain/social account/community名に使うこと、self-referral、未承認広告network等を禁止しています。
- 同AgreementはSE Ranking contentのcopy/distribution/derivative workを、書面で明示承認された場合を除き禁止します。またAffiliate経由で開示されたpricingをconfidential informationの例に含めます。公開Pricingと非公開partner pricingの境界は明記されないため照会が必要です。

### rights判定

|権利|判定|理由|
|---|---|---|
|取得|unknown|公開Pricingを人が閲覧できるが、定常automationの許諾を確認できない|
|保存|unknown|API dataの商用利用可能性はあるが、vendor自身のprice/limit履歴の保存条件は不明|
|比較表示|unknown|Affiliate promotionは認める一方、contentのcopy/derivativeは書面許諾が原則|
|派生TCO|unknown|独自計算の公開条件なし。direct competitor該当性も確認が必要|
|履歴|unknown|保持期間、更新後の過去価格表示、termination時の削除条件を確認する|
|商標|確認済み・Affiliate提供素材だけ条件付き|Affiliate加入中、最新版、無改変。終了時は削除|
|Affiliate|確認済み / 未取得|公開契約は具体的。accountでlinkをcopyした時にAgreement開始。実link・税務確認は未取得|

### 結論

公開Affiliate契約が最も具体的で、3社gate候補として優先度は高いです。ただしAffiliate参加とprice database権は分離し、public pricing / affiliate confidential pricingの境界を必ず書面確認します。

## 3. Mangools

### 公式確認

- [Terms & Conditions](https://mangools.com/conditions)は、text、database、graphics等をMangoolsまたは第三者のIPとし、subscription licenseをinternal business purposeに限定します。copy、derivative、commercial exploitation、競合product利用等は、明示許可または事前書面同意がない限り認めていません。
- 同TermsはMangools dataのpublication/distributionでMangools等のattributionを要求しますが、attribution義務は商用再利用の許可そのものではありません。
- [Affiliate Program](https://mangools.com/affiliate-program)は、free account作成でaffiliate sectionへ自動accessでき、審査なしと案内しています。cookie 30日、最大35% recurring、$150 threshold、PayPal、最低2人のpaid referralを案内します。
- Affiliate marketing pageの“lifetime”表示に対し、[Terms](https://mangools.com/conditions)はcommissionを原則24か月でcapし、直近6か月に新しいpaid referralがあれば継続するとしています。収益modelではTerms側の条件を採用し、“無条件の永久報酬”と表示しません。
- Affiliate pageは提供bannerの利用を案内する一方、brand/logo/tool名をPPC、domain、subdomain、social profile名に使うこと、coupon site、direct-link PPC、self-referral、誤情報を禁止しています。
- [公式Pricing](https://mangools.com/plans-and-pricing)はplan/limitsを公開していますが、表示内容はclient-side要素を含み、一次調査結果だけで自動取得方法を確定しません。

### rights判定

|権利|判定|理由|
|---|---|---|
|取得|unknown|公開閲覧は可能だが、internal-use licenseから定常自動取得の許諾は導けない|
|保存|unknown|最小価格field・hashの保持条件が明示されない|
|比較表示|unknown|Affiliate promotionは可能だが、価格/limit databaseの商用転載権は別途書面同意が必要|
|派生TCO|unknown|derivative work制限と衝突し得るため明示確認が必要|
|履歴|unknown|過去価格の保存・公開・affiliate終了後の保持が不明|
|商標|推定・提供素材だけ|Affiliate dashboardの提供banner利用は想定。word mark、logo、screenshotの詳細scopeは確認する|
|Affiliate|確認済み・審査なし / 未取得|加入経路は最短。ただしaccount、link、PayPal、本人・税務条件は未確認|

### 結論

Affiliate参加の速さから最初の照会先です。ただしprice/TCO database権は最も楽観視しやすい箇所なので、書面許諾前のfetch・保存・公開は行いません。

## 4. Serpstat

### 公式確認

- 2026-07-26までに確認したCustomer Support回答では、照会1–5と8はLicense Agreement 2.1に基づく
  prior written express consentが必要で、現在はauthorized teamの社内審査中である。承認後の取得経路は
  公式APIを推奨し、active official linkと観測日のattributionを求める方針が示されたが、item別許諾は0件である。
- [License Agreement（2024-12-26更新）](https://serpstat.com/users/license-agreement/)はWebsiteを価格pageを含むtext/graphics等として定義し、personal useの限定licenseを付与します。Service/Websiteの全部または一部の商用exploitationは、prior written express consentなしでは認めないとしています。
- [公式Pricing](https://serpstat.com/page/pricing-plans/)はplan、月額、limit、API、retention等を公開していますが、Agreement上の商用再利用制限を解除しません。
- [公式API documentation](https://api-docs.serpstat.com/)は大量データ取得を可能とし、reselling data/custom volumeは専門teamへの相談を案内しています。標準API accessをprice comparison databaseの再販売・再公開許可とは扱いません。
- [公式Discounts / Affiliate案内](https://serpstat.com/serpstat-discounts/)はreferral link、promo material、最大30%を案内します。しかし本調査で確認できる公開pageからはcookie、commission期間、payout threshold/method、tax、self-referral、商標license、termination等を網羅する現行Affiliate Agreementを確認できませんでした。

### rights判定

|権利|判定|理由|
|---|---|---|
|取得|unreviewed / 書面同意待ち|API推奨は利用許可ではなく、authorized teamのYesが必要|
|保存|unreviewed / 書面同意待ち|Agreementは商用exploitationを広く制限|
|比較表示|unreviewed / 書面同意待ち|一般的なAffiliate案内だけでは比較表の権利にならない|
|派生TCO|unreviewed / 書面同意待ち|item別の明示回答なし|
|履歴|unreviewed / 書面同意待ち|保持期間とtermination後の扱いが未回答|
|商標|unknown|Affiliate提供素材、text mark、logoのlicense scopeを確認できない|
|Affiliate|推定 / 未取得|programと最大30%は確認。契約詳細と実linkは未確認|

### 結論

requested due-diligence情報を返した後のauthorized team回答が必要です。現返信は手続案内であって
書面許諾そのものではないため、全data fieldをSTOPし、3社gateにも数えません。

## 5. HubSpot

### 公式確認

- [Website Terms of Use（2026-04-14更新）](https://legal.hubspot.com/website-terms-of-use)はSite Contentを非商用・個人利用またはHubSpotを知る目的に限定し、Contentのcommercial exploitation/distributionを禁止します。
- [公式Pricing](https://www.hubspot.com/pricing/suite)はplan、seat、commitment、credits等を公開しています。ただし表示が動的で、region、billing、contact/seat、add-onでTCOが変わるため、取得権とは別に計算仕様の明示が必要です。
- [Affiliate overview](https://www.hubspot.com/partners/affiliates)はsoftware reviewer、content creator、online educator、business solutionを対象とし、30% recurring up to one year、cookie 180日、Impact、最低$10でEFT/PayPalを案内しています。応募内容をreviewし、websiteとpromotion planを求めます。
- [Affiliate Program Agreement（2026-02-23）](https://legal.hubspot.com/affiliate-program-agreement)は申請後の審査・追加要件、affiliate link、commission eligibility、提供商標の限定使用、Contentのcopy/distribution/derivative work禁止、affiliate disclosure等を定めます。正確なcommission/cookieはAffiliate ToolまたはProgram Policiesが優先されます。
- [Affiliate Program Policies](https://www.hubspot.com/partners/affiliates/program-policies)はaffiliate link前の明確な報酬開示、brand keywordと競合する広告の制限、self-purchase禁止、掲載場所の開示、client紹介との分離を要求します。
- [Developer Terms（2026-05-04更新）](https://legal.hubspot.com/hs-developer-terms)はHubSpot API等で取得するCustomer Data/Contentの同意、attribution、合理的な期間だけの保存、termination時削除等を規定します。しかしHubSpot自身のpublic pricingを取得するためのlicenseではありません。

### rights判定

|権利|判定|理由|
|---|---|---|
|取得|unknown|Site一般規約は非商用。Affiliate acceptanceがprice page automationまで許すとは明記されない|
|保存|unknown|価格field、短い根拠、hash、履歴の保持期間を個別確認する|
|比較表示|推定|software reviewerを募集し、review contentを想定するが、公式Contentの系統的複製は別制限|
|派生TCO|unknown|seat/contact/credits/add-onを用いた計算と公開の明示許諾なし|
|履歴|unknown|過去価格・termination後データの保持条件なし|
|商標|確認済み・採用後の提供素材のみ|Affiliate Tool提供imageを無改変で使用し、endorsementを示さず、停止要求に従う|
|Affiliate|確認済み・要審査 / 未取得|対象audienceとは整合。live siteとpromotion planがない現段階では承認を推定しない|

### 結論

Affiliate programとcomparison audienceの相性は強い一方、一般Website Termsは商用再利用を許可しません。Affiliate担当者からprice/TCO comparisonに関するspecific written permissionを得るまでデータsourceをapprovedにしません。

## 3社gateの現在地

実利用可能な1社は、次をすべて満たす会社と定義します。

1. Affiliate accountが承認・有効で、自己所有のtracking linkが発行済み。
2. 日本居住者または利用予定の日本法人/個人事業として参加・受領でき、税務・payout手段が確認済み。
3. 対象site/domain/channelが登録・承認され、比較記事、広告、link disclosureの条件を満たす。
4. 公開価格/limitの取得・最小保存・比較表示・派生TCO・履歴を許す一次証拠または書面回答がある。
5. 商標・素材のscope、更新通知、削除/takedown、affiliate終了後の扱いを実装できる。

|会社|公開program|公開条件の把握|有効account|tracking link|データ/TCO/履歴の明示権利|gate count|
|---|---|---|---|---|---|---:|
|Semrush|確認済み|Impact契約同意直前まで表示確認|未取得|未取得|自動取得・継続保存・履歴は明示不可|0|
|SE Ranking|確認済み|確認済み|未取得|未取得|未取得|0|
|Mangools|確認済み|確認済み。ただし“lifetime”に条件差あり|有効|発行済み・値は非保存|未取得|0|
|Serpstat|確認済み|書面同意が必要・社内審査中|未取得|未取得|item別許諾0|0|
|HubSpot|確認済み|Impact契約同意直前まで表示確認|未取得|未取得|未取得|0|
|**合計**||||||**0/3**|

公開programが5件あることを「提携5社」と数えません。現時点ではsourceをfetchせず、Human Approverの照会・申請判断へhandoffします。

## 推奨確認順

1. **Mangools**: 審査なしでaffiliate accessできるため加入経路は短い。最初に書面でprice/TCO database権を確認する。
2. **SE Ranking**: Affiliate契約が具体的。public pricingとconfidential pricingの境界、比較/TCO/履歴を確認する。
3. **HubSpot**: review audienceとの適合性が高い。一般Website Termsとのspecific overrideを文書化する。
4. **Semrush**: 高いpayoutとcomparison contentの明示は魅力的だが、site完成・月間traffic目安とscrape/cache制限がある。traffic形成後に申請する。
5. **Serpstat**: prior written express consentとAffiliate契約全文の両方を先に取得できた場合だけ再評価する。

上位3社から同じ質問への明示的な回答を得られない場合、会社を入れ替えて数だけ揃えず、モデル自体を「公式価格へのリンク＋人手更新、履歴なし」へ縮小するかSTOPします。

## Human Approverが送る照会テンプレート

送信はまだ行っていません。Human Approverが送信先、法人/個人名、site URL、予定処理を確定した後に使用します。権利ごとにYes/Noを求め、曖昧な「Affiliateなら問題ない」という回答を承認証拠にしません。

### 推奨送信先

|会社|公開されている窓口候補|備考|
|---|---|---|
|Semrush|`affiliates@semrush.com`、商標のみ`trademarks@semrush.com`|data利用は適切なlegal/sales窓口への転送を依頼|
|SE Ranking|公式contact / sales / support|Affiliate AgreementとAPI commercial-use pageを参照|
|Mangools|`info@mangools.com`|Affiliate/rights担当への転送を依頼|
|Serpstat|`support@serpstat.com`|written express consentとAffiliate terms全文を同時依頼|
|HubSpot|`affiliates@hubspot.com`|Affiliate acceptanceとspecific content permissionを分離して回答依頼|

### English template

```text
Subject: Written permission request for an independent SaaS pricing and 12-month TCO comparison

Hello [Company] Affiliate / Legal Team,

I am preparing an independent Japanese-language comparison site for business software. The site will clearly disclose affiliate relationships before affiliate links and will link each displayed fact to your official source.

Before collecting or publishing any data, I would like written confirmation for each separate activity below. The planned scope is limited to your own public official pricing and plan-limit pages. We will not bypass authentication, CAPTCHAs, robots directives, rate limits, or technical restrictions, and we will not collect customer or personal data.

Please answer Yes / No / Conditional for each item:

1. Fetch: May we access the specified public pricing URLs at a low frequency, no more than [frequency], using an identified user agent, for change detection?
2. Store: May we store only factual fields such as plan name, currency, list price, billing period, commitment, included seats, usage limits, add-ons, tax status, source URL, observed timestamp, a content hash, and a short supporting excerpt?
3. Display: May we publish those factual fields in an independent comparison table with the official source URL and “last checked” date?
4. Derive: May we calculate and publish our own deterministic 12-month TCO scenarios from those fields, clearly labeled as our calculation and not your quotation?
5. History: May we retain and display prior versions of factual pricing fields for audit and price-history purposes? If yes, what retention period applies?
6. Marks: May we use your company and product word marks for nominative identification? May we use only the current logos/banners supplied in the affiliate dashboard, unmodified? Please provide required attribution and brand rules.
7. Affiliate: Is this comparison format eligible for your affiliate program for a publisher based in Japan? Please confirm approved channels, disclosure wording, prohibited keywords/ads, cookie window, commission duration, payout method/threshold, tax documentation, and whether the listed site/domain must be approved before links are placed.
8. Termination: If permission or affiliate participation ends, which stored facts, evidence, historical records, marks, and links must be deleted or disabled, and within what period?

Our intended safeguards are: minimal factual storage rather than full-page archives; source attribution; a visible affiliate disclosure; no misleading discounts; expiry-based removal; human approval before publication; and prompt takedown on request.

Please identify the agreement/policy URL and version/date governing your answer. If affiliate acceptance alone does not grant these data rights, please state the separate permission or agreement required.

Planned URLs: [exact official source URLs]
Planned publisher/site: [legal name, country, domain, short description]
Planned collection frequency and retention: [frequency / period]

Thank you,
[Human Approver name / legal entity]
```

### 会社別の追記

- Semrush: APIを使う場合とpublic Websiteを参照する場合を分け、1か月超のcache/history、comparison pieceで利用可能なprice/limit field、Impact termsの優先順位を確認する。
- SE Ranking: public pricingとAffiliate Agreement上のconfidential pricingの境界、比較siteがdirect competitorに該当するかを確認する。
- Mangools: “up to 35% lifetime”と24か月cap/直近6か月referral条件の正確な運用、提供banner以外のword mark使用を確認する。
- Serpstat: License Agreement上のprior written express consentとして本回答が十分か、cookie・commission期間・payout・tax・terminationを含む現行Affiliate Agreement全文を依頼する。
- HubSpot: Affiliate AgreementがWebsite Termsの非商用制限に対して、指定fieldの比較/TCO/historyを明示的に許すか、Affiliate Toolのcurrent commission/cookie条件を確認する。

## source policyへの反映

明示回答がないfieldは次の状態にする。Semrushの禁止回答は`prohibited`、記事・Affiliateに
関する条件付き回答は用途限定のHuman decision候補として別管理し、価格`FieldEvidence`へ流用しない。

```text
fetch = pending
store = pending
display = pending
derive = pending
history = pending
trademark = pending
affiliate = pending
effective_policy = denied_fail_closed
```

Human Approverのsigned decision、回答本文の最小証拠、回答日、適用URL、expiry、撤回条件が揃った会社だけを個別に`approved`へ変更します。Affiliate approvalだけでは、残り6軸を自動承認しません。
