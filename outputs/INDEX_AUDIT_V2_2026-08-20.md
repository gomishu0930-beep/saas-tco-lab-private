# Index audit V2 — 20 approved articles

Production read-back: 2026-08-20。GSC列は2026-08-19のaggregate共有値からURL単位へ推測せず、すべてHuman入力待ちとする。

|ID|Route|Title|Approval|Expected robots / canonical|Sitemap|CTA|Internal link source|Production read-back|GSC status / reason / last crawl|Next action|
|---|---|---|---|---|---|---|---|---|---|---|
|P01|`/pilot/pricing-calculator`|料金計算|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|URL InspectionをHuman入力|
|P02|`/pilot/plan-comparison`|プラン比較|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P03|`/pilot/alternatives`|代替候補|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P04|`/pilot/small-team-fit`|小規模チーム適合|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P05|`/pilot/enterprise-fit`|組織利用適合|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P06|`/pilot/annual-vs-monthly`|年契約と月契約|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P07|`/pilot/usage-overage`|従量超過|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P08|`/pilot/addon-cost`|追加機能費用|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P09|`/pilot/migration-cost`|移行コスト|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P10|`/pilot/japan-tax`|日本向け税・通貨|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|P12|`/pilot/evidence-method`|根拠の検証|approved|index,follow / self|yes|Mangools active|home・P関連記事|200 / index / self canonical|unknown / unknown / unknown|同上|
|SVR01|`/servers/business-server-pricing`|法人向けサーバー料金|approved|index,follow / self|yes|production 6 / local V2 max2|home・SVR02〜09|200 / index / self canonical|unknown / unknown / unknown|V2 deploy後read-back|
|SVR02|`/servers/small-business-server`|中小企業向けサーバー料金|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|URL InspectionをHuman入力|
|SVR03|`/servers/ec-server-cost`|ECサイト用サーバー費用|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|同上|
|SVR04|`/servers/server-first-year-total`|サーバー初期費用込み総額|approved|index,follow / self|yes|Cell B HOLD|home|200 / index / self canonical|unknown / unknown / unknown|GSC確認・vendor GO判断|
|SVR05|`/servers/server-renewal-cost`|サーバー2年目料金|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|URL InspectionをHuman入力|
|SVR06|`/servers/server-migration-cost`|サーバー乗り換え費用|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|同上|
|SVR07|`/servers/business-rental-server`|法人向けレンタルサーバー|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|同上|
|SVR08|`/servers/ec-server-requirements`|ECサイト向けサーバー|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|同上|
|SVR09|`/servers/business-mail-server`|法人メールサーバー料金|approved|index,follow / self|yes|affiliate off|home|200 / index / self canonical|unknown / unknown / unknown|同上|

## GSC Human入力規則

各URLについて `index状態 / 理由 / Google選択canonical / 最終crawl / impressions有無 / 次回確認日` を入力する。aggregateの「index 7・未登録6」から残り7 URLや個別URLを推測しない。

## Homepage / hub候補

|Route|現状|候補評価|Decision|
|---|---|---|---|
|`/`|productionはnoindex,follow|20記事・2カテゴリへのHuman編集済み入口|`HOME` source GO済み。runtime `HUB_INDEX_GO=GO` + exact scope後だけindex|
|`/pilot`|productionはnoindex,follow|公開済みSEOツール11記事だけの読者向けhubへ改稿|`SEO_TOOLS` source GO済み。P11除外・runtime二重gate後だけindex|
|`/servers`|routeなし|新規route作成は今回scope外|HOLD|
|`/comparison`|production public allowlist外|thin/function routeの可能性があり現状index候補にしない|HOLD|

管理画面、未承認route、P11は候補外である。
