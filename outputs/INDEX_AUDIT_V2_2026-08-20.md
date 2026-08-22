# Index audit V2 — 20 approved articles

## 2026-08-22 code / production再監査

SVR01〜SVR09は全件、productionでHTTP 200、robots meta 1件の`index, follow`、self-canonical（末尾slashなし）、sitemap収録、SSR本文、内部リンクを確認した。末尾slashはcanonical URLへ308、query付きvariantはfail-closedでnoindexとなる。CSS・JSもGooglebotから200で取得できる。現在のHEADとproduction生成物に、残存するcrawl/index blockerは見つからなかった。

以下のGSC statusは2026-08-21のHuman観測を維持し、Google再処理後の結果を推測しない。2026-08-22はSVR04を最優先にlive testし、robots許可、index許可、Human canonical、Google選択canonical、最終crawl、取得HTMLのrobots meta 1件を確認する。すべて合格した場合だけSVR04を1回登録要求し、全URL一括要求やsitemap再送信は行わない。

2026-08-21にGSC URL Inspectionを20記事すべて実施した。GSC上のindex済みは6記事で、個別状態は下表のとおり。検索パフォーマンスではP01のslashありvariantだけに29 impressions、clicks 0が記録され、server記事はpage別impressions 0だった。query文字列は取得・保存していない。

同日の完全HTML監査で、公開server記事はheaderと先頭metaが`index, follow`でも、Vinextのlayout由来`noindex, nofollow`が後段に重複していることを確認した。GSCライブテストもSVR04で後段noindexを検出した。単純な先頭meta read-backを合格根拠にせず、robots metaが全HTMLで1件だけであることをrelease条件へ追加する。

|ID|Route|Title|Approval|Expected robots / canonical|Sitemap|CTA|Internal link source|Production read-back|GSC status / reason / last crawl|Next action|
|---|---|---|---|---|---|---|---|---|---|---|
|P01|`/pilot/pricing-calculator`|料金計算|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|slash variantの29 impressionsを監視|
|P02|`/pilot/plan-comparison`|プラン比較|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|discovered-not-indexed / crawlなし|重複robots修正後に処理待ち|
|P03|`/pilot/alternatives`|代替候補|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|監視|
|P04|`/pilot/small-team-fit`|小規模チーム適合|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|discovered-not-indexed / crawlなし|重複robots修正後に処理待ち|
|P05|`/pilot/enterprise-fit`|組織利用適合|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|監視|
|P06|`/pilot/annual-vs-monthly`|年契約と月契約|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|discovered-not-indexed / crawlなし|重複robots修正後に処理待ち|
|P07|`/pilot/usage-overage`|従量超過|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|discovered-not-indexed / crawlなし|重複robots修正後に処理待ち|
|P08|`/pilot/addon-cost`|追加機能費用|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|URLがGoogleに認識されていない / crawlなし|重複robots修正後に検出待ち|
|P09|`/pilot/migration-cost`|移行コスト|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|監視|
|P10|`/pilot/japan-tax`|日本向け税・通貨|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|URLがGoogleに認識されていない / crawlなし|重複robots修正後に検出待ち|
|P12|`/pilot/evidence-method`|根拠の検証|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|監視|
|SVR01|`/servers/business-server-pricing`|法人向けサーバー料金|approved|index,follow / self|yes|Cell A primary 1 + alternative 1|home・SVR02〜09|200 / header index / self canonical|indexed / reasonなし / last crawl未記録|監視|
|SVR02|`/servers/small-business-server`|中小企業向けサーバー料金|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|discovered-not-indexed / crawlなし|重複robots修正後に処理待ち|
|SVR03|`/servers/ec-server-cost`|ECサイト用サーバー費用|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-19 23:23:21|重複robots修正を外部・GSCで再確認|
|SVR04|`/servers/server-first-year-total`|サーバー初期費用込み総額|approved|index,follow / self|yes|Cell B XServer単独CTA active|home|200 / robots meta 1件 / self canonical|noindex除外 / 2026-08-19 16:28:04。2026-08-21 liveは修正前の重複noindex検出|修正後live test。合格時のみ登録要求1回|
|SVR05|`/servers/server-renewal-cost`|サーバー2年目料金|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-20 00:16:53|重複robots修正を外部・GSCで再確認|
|SVR06|`/servers/server-migration-cost`|サーバー乗り換え費用|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-19 17:04:13|同上|
|SVR07|`/servers/business-rental-server`|法人向けレンタルサーバー|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-19 23:42:54|同上|
|SVR08|`/servers/ec-server-requirements`|ECサイト向けサーバー|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-19 23:34:02|同上|
|SVR09|`/servers/business-mail-server`|法人メールサーバー料金|approved|index,follow / self|yes|affiliate off|home|200 / header index / self canonical|noindex除外 / 2026-08-20 00:06:11|同上|

## GSC Human入力規則

20記事の個別検査は2026-08-21に完了した。Google選択canonicalが未決定・未表示のURLはunknownのままとし、aggregate値から補完しない。修正版deploy後はSVR04のlive testを1回行い、全URLの一括登録要求はしない。

優先queueは、SVR04、SVR02、SVR03、SVR05、SVR06、SVR07、SVR09、SVR08、SVR01、P01の順とする。SVR01とP01はindex済みのためcanonical確認だけで、正常なら登録要求しない。SVR02はdiscovered-not-indexed、SVR03〜SVR09は旧noindex再処理の確認対象である。

## Homepage / hub候補

|Route|現状|候補評価|Decision|
|---|---|---|---|
|`/`|production index,follow / sitemap収録|20記事・2カテゴリへのHuman編集済み入口|GO済み。旧noindex報告は2026-08-14 crawl由来のstale状態|
|`/pilot`|production index,follow / sitemap収録|公開済みSEOツール11記事だけの読者向けhub|GO済み。P11は除外|
|`/servers`|routeなし|新規route作成は今回scope外|HOLD|
|`/comparison`|production public allowlist外|thin/function routeの可能性があり現状index候補にしない|HOLD|

管理画面、未承認route、P11は候補外である。
