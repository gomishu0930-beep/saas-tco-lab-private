# 法人向けサーバー価格・条件監査レポート draft

> PR: 本稿から案内するSaaS TCO Labの記事にはアフィリエイトリンクが含まれます。価格順位を報酬額で変更していません。

## 確認範囲

2026-08-14〜18にHumanが公式画面を確認した4社について、同じ条件にできた12か月の初回請求額だけを整理した。更新、解約、キャンペーン、用途適合にunknownがある場合は、長期TCO・おすすめ・最安を断定しない。

|Vendor / plan|確認済み初回請求額|更新|promotion|観測日 / 次回確認|
|---|---:|---|---|---|
|XServerビジネス 共有スタンダード 12か月|JPY 66,660（税込）|unknown|キャッシュバック額・受取条件・終了日unknown|2026-08-14 / 2026-09-13|
|ConoHa WING Standard 12か月|JPY 25,740（税込）|unknown|期間限定表示、2026-08-24までの観測|2026-08-18 / 2026-08-24|
|さくら Business 12か月|JPY 29,040（税込）|unknown|期間限定campaignは確認していない|2026-08-18 / 2026-09-17|
|KAGOYA Light 1コア/4GB 12か月|JPY 17,820（税込）|JPY 17,820確認済み|恒常年払い表示、期間限定campaignは確認していない|2026-08-18 / 2026-09-17|

上表の最小額は「確認済み条件の範囲の初回請求額」であり、法人向け最適や完全TCOではない。affiliate承認・runtime destination・channel GOがないKAGOYAはaffiliate CTA対象外である。

比較ページ: `https://saastcolab.jp/servers/business-server-pricing`

## note用draft — campaign `svr01-note-audit-01`

> PR: 紹介する比較記事にはアフィリエイトリンクが含まれます。

レンタルサーバーは「月額○円」だけを見ると、契約時にいくら支払うのか分かりにくいことがあります。そこで今回は、公式画面で確認できた12か月の初回請求額だけを、初期費用・税・期間限定表示と分けて整理しました。

確認できた初回請求額は、KAGOYA 17,820円、ConoHa WING 25,740円、さくら 29,040円、XServerビジネス 66,660円です。いずれも税込の確認値ですが、同じ意味の「総コスト」ではありません。更新額、解約、キャンペーン、用途条件の確認範囲が異なるためです。

特にConoHaは期間限定表示で、次回確認日が2026-08-24です。XServerは更新時請求とキャッシュバック条件、さくらは更新額、各社は解約条件にunknownが残っています。そのため「最安」「法人向け1位」とはせず、必要条件が揃うまで順位から外す設計にしています。

比較ページでは、読者が期間と用途を選んだ時に、確認済みの行だけを計算結果へ出します。unknownは0円にしません。月額表示ではなく初回請求額を見たい方は、根拠表と観測日を含めて確認できます。

導線: `https://saastcolab.jp/servers/business-server-pricing#ch=note&cid=svr01-note-audit-01`

## X用draft（未投稿）

共通先頭: `PR: リンク先の記事にはアフィリエイトリンクが含まれます。`

1. `月額表示だけでは契約時の支払額が分かりません。公式画面で確認できた12か月初回請求額を4社分整理しました。更新・解約がunknownの行は長期TCOやおすすめに使いません。 #サーバー選び`
2. `確認値はKAGOYA 17,820円、ConoHa 25,740円、さくら29,040円、XServerビジネス66,660円。これは同条件で確認できた初回請求額で、法人向け最適順位ではありません。`
3. `ConoHaは期間限定表示で次回確認が8/24。XServerとさくらは更新額がunknown。unknownを0円にしない比較ページを作りました。`
4. `安さより先に見る条件: 税、請求周期、最低契約期間、更新額、解約、用途適合。揃わないvendorは順位から除外しています。`
5. `12か月・small-siteの確認範囲と完全な根拠表はこちら。 https://saastcolab.jp/servers/business-server-pricing#ch=x&cid=svr01-x-01`

## パートナー紹介文 — campaign `svr01-partner-intro-01`

> PR: 紹介先の比較記事にはアフィリエイトリンクが含まれます。

法人・小規模事業者向けのサーバー選定時に使える、12か月初回請求額の監査ページです。公式画面でHuman確認した値、観測日、次回確認日、unknown理由を同じ表で確認できます。更新・解約・用途適合が揃わない候補を推奨しないため、制作・移行の初回ヒアリング資料として利用できます。

導線: `https://saastcolab.jp/servers/business-server-pricing#ch=partner&cid=svr01-partner-intro-01`

## 公開前Human checklist

- [ ] note / X / partner channelが各program規約で許可されることを確認した
- [ ] PR表示が本文とリンクより前にある
- [ ] affiliate URLを直接配信せずSaaS TCO Labへ案内している
- [ ] 2026-08-24を過ぎたConoHa価格は再確認するまで使用しない
- [ ] 「最安」「完全TCO」「法人向け最適」「おすすめ1位」を使用していない
- [ ] fragmentのchannel/campaign IDがregistryどおりである
- [ ] 投稿ごとのHuman GOを記録した

## Campaign registry

|Channel|Campaign ID|State|
|---|---|---|
|note|`svr01-note-audit-01`|DRAFT_ONLY|
|x|`svr01-x-01`|DRAFT_ONLY|
|partner|`svr01-partner-intro-01`|DRAFT_ONLY|

投稿、DM、partner連絡は行っていない。
