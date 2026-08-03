# 日本ASP申請準備checklist

基準日: 2026-07-31（Asia/Tokyo）
状態: `COPY READY / PUBLIC SITE GATE HOLD / HUMAN SUBMISSION ONLY`

この文書はA8.net、もしもアフィリエイト、バリューコマースの申請画面で迷わないための準備表である。
account作成、規約同意、本人確認、口座登録、送信はHumanだけが行う。credential、本人情報、口座、電話番号、
tracking IDはrepositoryへ記録しない。入力欄が本表と異なる場合は推測せず、画面の最新説明を優先してHOLDする。

## 2026-07-31 readiness read-back

|対象|現在地|次の解除条件|
|---|---|---|
|A8.net|`COPY READY / SIGNUP GO待ち`|public site gate復旧後にHumanが登録・規約・口座を確認|
|もしもアフィリエイト|`COPY READY / SIGNUP GO待ち`|public site gate復旧後にHumanが登録。正確な本人情報でaccount審査を受ける|
|バリューコマース|`COPY READY / HOLD`|public site gate復旧、独自domain、Human承認済み記事の表示後に申請|

公開originのread-only確認結果:

- `/`、`/methodology/`、`/disclosure/`、公開前の記事見本3routeはHTTP 200。
- `/about`、`/operator-information`、`/privacy`、`/contact`、`/advertising-policy`はHTTP 503。
- 全応答の`noindex`は維持され、`saastcolab.jp`は取得・DNS保存済みでTLS反映待ち。P01–P03のarticle reviewは2026-08-03承認済み公開候補。

したがって、3社とも申請文は完成しているが、ASPへ提示するsiteは現時点でgate不合格とする。account作成だけが
可能なASPでも、申請URLは独自domainへ切り替えるまで確定しない。503復旧と独自domain反映を
満たした後、下の順序で開始する。P01–P03承認条件は完了済みである。

## 推奨申請順

1. A8.net: 会員登録に入会時審査がないため最初に実行する。ただしprogram提携は別審査として扱う。
2. もしもアフィリエイト: account登録後に会員情報審査がある。重複accountと入力欠けを先に確認する。
3. バリューコマース: media内容が閲覧できる状態で登録審査を受ける。P01–P03の公開表示確認後に実行する。

この順番は承認を保証しない。3社accountの成立を、個別SaaS partnerとのAffiliate提携承認として数えない。

## 共通copy-paste候補

|欄|入力候補|確認|
|---|---|---|
|サイト名|`SaaS TCO Lab`|公開画面の表記と一致|
|申請URL|独自domainのcanonical origin。現在のprelaunch originは入力しない|`domain_day: done <domain>`とHTTP read-back後にHumanが貼付|
|カテゴリ|`ビジネス・仕事 / IT・Webサービス / SaaS比較`|画面の最も近い選択肢をHuman選択|
|サイト説明（短）|`SaaSの料金・利用上限・12か月TCOを、公式出典と観測日付きで比較する日本語メディアです。`|誇張・未公開実績なし|
|サイト説明（長）|`業務SaaSを検討する個人事業主・小規模事業者向けに、料金、契約期間、利用上限、追加費用、移行費用を同一条件で整理します。価格はHumanが公式公開画面で確認し、出典URL・観測日・次回確認日を表示します。広告を含む場合は記事冒頭でPR表記を行います。`|実装済み内容だけ|
|月間PV|申請画面で確認できる実数。公開直後で0なら`0`|見込み・他サイト実績を加えない|
|運営形態|画面上は個人または個人事業主。法的名義はHumanのprivate recordから入力|屋号だけで本人欄を埋めない|
|連絡先・口座|Humanが本人画面へ直接入力|chat・repoへ貼らない|

## Humanがprivateに用意する入力

|項目|扱い|
|---|---|
|氏名、住所、生年月日、電話番号|ASP画面へHumanが直接入力。repo、chat、screenshotへ残さない|
|受信可能なメールアドレス|登録・認証専用。mobile carrier address不可のASPではwork addressを使う|
|本人名義の振込口座|ASP画面だけで入力し、画面共有・自動入力をしない|
|インボイス登録状態|登録番号がなければ、その事実を画面の選択肢どおりに回答。番号を推測しない|
|月間PV|申請直前に実測。0なら0と記入し、見込み値を使わない|
|password・認証code|Humanだけが入力。Codexへ共有しない|

## 申請前のサイト共通gate

- [ ] 独自domainがHuman承認済みで、申請URLと実際の表示URLが一致する。
- [ ] About、運営者情報、プライバシーポリシー、お問い合わせ、広告掲載ポリシーが閲覧できる。
- [ ] P01–P03のHuman承認済み記事が公開され、空templateや未確認placeholderだけではない。
- [ ] 記事冒頭にPR表記があり、CTAより前に表示される。
- [ ] 申請時点のPVは実数を入力し、将来予測や別媒体の数字を混ぜない。
- [ ] 登録するsite以外へ広告を貼らない。note・Xは各ASPとprogramの掲載可否を別確認する。
- [ ] ASP account承認と、掲載したいSaaS partnerのprogram提携承認を別々に記録する。
- [ ] 申請送信前に利用規約、禁止事項、登録media範囲、program別条件をHumanがread-backする。

## A8.net

公式確認先:

- 登録手順・必要情報: https://www.a8.net/howto/entry.html
- メディア会員利用規約: https://www.a8.net/compliance/media-userpolicy.php
- 禁止事項: https://www.a8.net/compliance/prohibited-matter.php
- 入会審査FAQ: https://www.a8.net/faq/14.html

画面前に用意するもの:

- [ ] 受信可能なメールアドレス。
- [ ] 本人の基本情報。個人事業は個人区分を選び、氏名または屋号＋氏名をHumanが入力する。
- [ ] 登録media名、独自domain URL、説明、実PV。
- [ ] 本人名義の成果報酬振込口座。
- [ ] 登録media以外へ広告を掲載しない条件を確認する。
- [ ] A8.net広告をXへ掲載しない。X再配信は記事への通常linkとPR表記だけにし、A8.netの広告linkを含めない。

判断メモ: A8.net公式案内では会員登録自体に入会時審査はないが、規約遵守の巡回とprogram単位の審査は別である。
「入会完了」をSaaS広告主との提携承認として数えない。

## もしもアフィリエイト

公式確認先:

- FAQ（登録media、提携審査、広告掲載範囲）: https://af.moshimo.com/af/www/help
- メディア利用規約: https://af.moshimo.com/af/www/terms/shop
- 不正・違反事例: https://af.moshimo.com/af/www/about/unfaircase

画面前に用意するもの:

- [ ] 既存accountの有無をHuman確認する。公式FAQの一人1account条件に反する重複登録をしない。
- [ ] 氏名、住所、メール、電話番号、インボイス登録状態を正確に入力する。ニックネームや住所欠けを使わない。
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
