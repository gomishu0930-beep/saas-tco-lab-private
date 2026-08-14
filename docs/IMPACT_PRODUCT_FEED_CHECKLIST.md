# Impact product feed / catalog確認チェックリスト

基準日: 2026-07-29（Asia/Tokyo）
対象: **Impact上でAffiliate承認済みかつactiveなpartnerだけ**
目的: product feed / catalogの有無と利用scopeをHumanが画面で確認し、条件を満たす場合だけ
Gate A1の許諾済みsourceとしてローカル登録する。これはfeed取得、API接続、FTP接続、公開、CTA変更の
承認ではない。

## 公式画面の前提

Impact公式ヘルプでは、参加済みbrandがcatalogを提供している場合、上部メニューの
`Content → Product Catalogs`からcatalogを確認できる。詳細画面には更新時刻、商品数、file size等が表示され、
Impact Format / advertiser format、FTP、APIの選択肢が存在し得る。catalogの表示には、そのcatalogをuploadした
brandとの参加関係が必要とされている。

- [Download Product Catalogs as a Partner](https://help.impact.com/partner/what-would-you-like-to-learn-about/platform-features/marketing-content/product-marketplace-and-catalogs/download-product-catalogs-as-a-partner)
- [Set Product Catalog Feed Preferences as a Partner](https://help.impact.com/partner/what-would-you-like-to-learn-about/platform-features/marketing-content/product-marketplace-and-catalogs/set-product-catalog-feed-preferences-as-a-partner)
- [Find Products on the Product Marketplace](https://help.impact.com/partner/what-would-you-like-to-learn-about/platform-features/marketing-content/product-marketplace-and-catalogs/find-products-on-the-product-marketplace)

画面名が変わっている場合は、検索や回避操作をせず`unclear`で止める。catalogが見えることだけでは、
保存、履歴化、TCO派生、公開表示の権利まで付与されたとは判定しない。

## 画面別手順（partnerごとに約5分）

### 1. Affiliate関係を確認

- [ ] Impactへ通常の方法でsign inする。
- [ ] `My Brands`または契約一覧で対象partnerを開く。
- [ ] statusが`Joined` / `Active`相当であることを画面上で確認する。
- [ ] pending、pre-qualified、expired、paused、terminatedならここで`HOLD`にする。

記録するのはpartner名、確認日、activeかどうかだけ。program ID、partner ID、契約全文、報酬、
担当者情報はrepositoryへ書かない。

### 2. Catalogの有無だけを確認

- [ ] 上部メニューから`Content → Product Catalogs`を開く。
- [ ] Brand filterまたは画面内検索で対象partnerを絞る。
- [ ] 対象partnerのcatalog行があるか確認する。
- [ ] 行がある場合は`More → View Details`を開く。Downloadは押さない。
- [ ] catalogの用途、locale / region、last updated、提供format、表示field名を読む。

`Product Catalogs`自体が表示されない、または対象行がない場合は`unavailable`とする。API画面、FTP credential
送信、download、Data Feed設定のSaveは、この確認では行わない。

### 3. SaaS比較に必要なfieldを確認

|確認field|画面上の有無|判断|
|---|---|---|
|plan / product名|あり / なし / 不明|なしならplan比較へ直接利用しない|
|current price|あり / なし / 不明|通貨と一体でなければ価格fieldをSTOP|
|currency|あり / なし / 不明|価格から推測しない|
|billing period / commitment|あり / なし / 不明|SKUやdescriptionから推測しない|
|region / locale|あり / なし / 不明|JP/ja適合を推測しない|
|tax treatment|あり / なし / 不明|feedにない場合はunknown|
|seat / quota / overage|あり / なし / 不明|相互補完しない|
|last updated|あり / なし / 不明|観測日として代用せず、source freshness判定にだけ使う|

### 4. A1利用scopeを契約画面で確認

partnerのProgram Terms、data feed条件、Impact共通条件を画面上で確認し、次を一つずつ判定する。

|scope|approved / prohibited / unreviewed|必須条件|
|---|---|---|
|feed/APIによる自動取得method| |画面・規約が対象methodを明示|
|取得頻度 / rate limit| |頻度または制限が明示|
|対象field / region| |対象catalogとfieldを限定可能|
|minimal normalized storage| |保存可否と期間が明示|
|ongoing storage / history| |未記載なら`unreviewed`|
|TCO・比較へのderivation| |派生利用の可否が明示|
|記事上のdisplay / attribution| |表示条件・帰属表示を満たせる|
|終了・撤回時の削除 / 非表示| |期限または即時停止条件が明示|

契約文をrepositoryやchatへ貼らない。Humanのprivate recordを正本とし、repositoryへは判定、対象scope、
確認日、次回確認日、公開された規約URLだけをsafe-summaryとして残す。

## 判定と登録

|状態|返信|A1登録|
|---|---|---|
|Affiliateがactiveでない|`impact_feed_a1: HOLD <partner>`|不可|
|activeだがcatalogがない|`impact_feed_check: unavailable <partner>`|不可|
|catalogはあるがscope表に`unreviewed`がある|`impact_feed_check: available <partner>` + `impact_feed_a1: HOLD <partner>`|候補だけ。approvedにしない|
|catalogがあり、利用する全scopeがapproved|`impact_feed_check: available <partner>` + `impact_feed_a1: GO <partner>`|確認済みscope・method・期限だけA1へ登録|
|画面やtermsが矛盾・不明|`impact_feed_check: unclear <partner>` + `impact_feed_a1: HOLD <partner>`|不可|

`impact_feed_a1: GO`で許可されるのは、Humanがチェックしたexact partner/catalog scopeをsource policyへ
登録することだけ。download、credential発行、API/FTP接続、定期job、raw保存、履歴DB、公開利用は、登録した
policyの各fieldが許可し、かつ該当する実行GOを別に受けた場合だけ行う。feedに存在しないbilling、tax、seat、
quota等はunknownのまま維持する。

## repositoryへ残せるsafe-summary

|項目|記入値|
|---|---|
|partner名| |
|確認日|YYYY-MM-DD|
|次回確認日|YYYY-MM-DD（180日以内）|
|Affiliate関係|active / not_active / unclear|
|catalog提供|available / unavailable / unclear|
|locale / region|公開画面の表記だけ|
|利用可能method|platform_feed / api / ftp（明示されたものだけ）|
|approved scope|scope表でapprovedの行だけ|
|prohibited / unreviewed scope|省略せず列挙|
|公開規約URL|tracking parameterを除いたURL|

partner ID、catalog ID、tracking link、API key、FTP host / username / password、非公開報酬、契約全文、
downloadしたfeed本体はsafe-summaryへ含めない。
