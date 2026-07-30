# 日本ASP申請準備checklist

基準日: 2026-07-31（Asia/Tokyo）
状態: `PREPARED / HUMAN SUBMISSION ONLY`

この文書はA8.net、もしもアフィリエイト、バリューコマースの申請画面で迷わないための準備表である。
account作成、規約同意、本人確認、口座登録、送信はHumanだけが行う。credential、本人情報、口座、電話番号、
tracking IDはrepositoryへ記録しない。入力欄が本表と異なる場合は推測せず、画面の最新説明を優先してHOLDする。

## 共通copy-paste候補

|欄|入力候補|確認|
|---|---|---|
|サイト名|`SaaS TCO Lab`|公開画面の表記と一致|
|カテゴリ|`ビジネス・仕事 / IT・Webサービス / SaaS比較`|画面の最も近い選択肢をHuman選択|
|サイト説明（短）|`SaaSの料金・利用上限・12か月TCOを、公式出典と観測日付きで比較する日本語メディアです。`|誇張・未公開実績なし|
|サイト説明（長）|`業務SaaSを検討する個人事業主・小規模事業者向けに、料金、契約期間、利用上限、追加費用、移行費用を同一条件で整理します。価格はHumanが公式公開画面で確認し、出典URL・観測日・次回確認日を表示します。広告を含む場合は記事冒頭でPR表記を行います。`|実装済み内容だけ|
|月間PV|申請画面で確認できる実数。公開直後で0なら`0`|見込み・他サイト実績を加えない|
|運営形態|画面上は個人または個人事業主。法的名義はHumanのprivate recordから入力|屋号だけで本人欄を埋めない|
|連絡先・口座|Humanが本人画面へ直接入力|chat・repoへ貼らない|

## 申請前のサイト共通gate

- [ ] 独自domainがHuman承認済みで、申請URLと実際の表示URLが一致する。
- [ ] About、運営者情報、プライバシーポリシー、お問い合わせ、広告掲載ポリシーが閲覧できる。
- [ ] P01–P03のHuman承認済み記事が公開され、空templateや未確認placeholderだけではない。
- [ ] 記事冒頭にPR表記があり、CTAより前に表示される。
- [ ] 申請時点のPVは実数を入力し、将来予測や別媒体の数字を混ぜない。
- [ ] 登録するsite以外へ広告を貼らない。note・Xは各ASPとprogramの掲載可否を別確認する。
- [ ] 申請送信前に利用規約、禁止事項、登録media範囲、program別条件をHumanがread-backする。

## A8.net

公式確認先:

- 登録手順・必要情報: https://www.a8.net/howto/entry.html
- メディア会員利用規約: https://www.a8.net/compliance/media-userpolicy.php
- 禁止事項: https://www.a8.net/compliance/prohibited-matter.php
- 入会審査FAQ: https://support.a8.net/a8/as/faq/2007/07/as.html

画面前に用意するもの:

- [ ] 受信可能なメールアドレス。
- [ ] 本人の基本情報。個人事業は個人区分を選び、氏名または屋号＋氏名をHumanが入力する。
- [ ] 登録media名、独自domain URL、説明、実PV。
- [ ] 本人名義の成果報酬振込口座。
- [ ] 登録media以外へ広告を掲載しない条件を確認する。

判断メモ: A8.net公式案内では会員登録自体に入会時審査はないが、規約遵守の巡回とprogram単位の審査は別である。
「入会完了」をSaaS広告主との提携承認として数えない。

## もしもアフィリエイト

公式確認先:

- FAQ（登録media、提携審査、広告掲載範囲）: https://af.moshimo.com/af/www/help
- メディア利用規約: https://af.moshimo.com/af/www/terms/shop
- 不正・違反事例: https://af.moshimo.com/af/www/about/unfaircase

画面前に用意するもの:

- [ ] 既存accountの有無をHuman確認する。公式FAQの一人1account条件に反する重複登録をしない。
- [ ] 独自domainの登録mediaと、公開済みの独自コンテンツを確認する。
- [ ] programごとの審査有無、SNS・検索広告・direct link条件を個別に読む。
- [ ] 登録media以外へ広告を掲載しない。
- [ ] Amazon・楽天等の一般programとSaaS案件を同じ承認として扱わない。

## バリューコマース

公式確認先:

- 登録審査の必須事項: https://www.valuecommerce.ne.jp/registration/
- 会員登録方法・必要情報: https://www.valuecommerce.ne.jp/entry/
- 初心者FAQ: https://www.valuecommerce.ne.jp/beginners/faq/

画面前に用意するもの:

- [ ] 氏名・住所、media種別、media URLを正確に入力する。
- [ ] サイトまたはSNS情報、連絡先、成果報酬振込口座をHumanが用意する。
- [ ] 18歳以上、利用規約、個人情報保護方針の確認をHumanが行う。
- [ ] 登録後の案内メールを確認し、公式案内の期限内に初回password設定を行う。
- [ ] サイト登録審査と、広告主programの提携審査を分けて台帳化する。

## Human返信

申請を開始する時だけ、ASPごとに別のaction-time GOを返す。三社まとめてのGOにしない。

```text
asp_signup: GO A8.net / HOLD A8.net
asp_signup: GO もしも / HOLD もしも
asp_signup: GO バリューコマース / HOLD バリューコマース
```

GOは対象ASPのHuman申請だけを許可し、広告主提携、CTA、tracking link配置、課金、他media掲載を許可しない。
