# 日本ASP申請準備checklist

基準日: 2026-08-12（Asia/Tokyo）
状態: `6 SERVER PROGRAMS APPROVED / SERVER CTA DISABLED`

この文書はA8.net、もしもアフィリエイト、バリューコマースの申請画面で迷わないための準備表である。
account作成、規約同意、本人確認、口座登録、送信はHumanだけが行う。credential、本人情報、口座、電話番号、
tracking IDはrepositoryへ記録しない。入力欄が本表と異なる場合は推測せず、画面の最新説明を優先してHOLDする。

## Partner台帳v1.1

審査状態の正本は`docs/AFFILIATE_PARTNER_LEDGER.json`とする。ここには公開可能な審査状態、確認済みの
program条件要約、確認日とruntime secretの参照名だけを記録する。secret値、tracking ID、広告link URL、
本人情報、ログイン後だけ表示される報酬額・確定率は記録しない。後二者は`restricted_dashboard_only`とし、
値をrepositoryから復元できない状態にする。

|ASP|Account状態|個別program|提携状態|CTA|
|---|---|---|---|---|
|A8.net|`registered`|7候補調査済み、XServerビジネスは参加中programとして確認済み|`approved`（XServerビジネス）|記事・destination・CTA gate未完了のため不可|
|もしもアフィリエイト|`registered`|servers候補4件（ロリポップ、シンレンタルサーバー、ConoHa WING、お名前.com）提携承認済み|`approved`|runtime destination・servers記事承認・partner別CTA GOまで不可|
|バリューコマース|`registered`|ABLENET共用サーバーの個別条件確認済み|`approved`（ABLENET共用サーバー）|記事・destination・CTA gate未完了のため不可|
|Mangools|`approved`|確認済み|`approved`|既存gate合格時だけ可|

各ASPのdestinationはrepositoryへ保存せず、台帳に記録したruntime secret参照名から実行時だけ読む。
Account登録だけではCTAを許可しない。対象programの提携承認、規約・開示要件の確認、runtime destination設定、
開示先行の検証、対象partnerを明記した`cta_go`がすべて揃った場合だけ有効化する。

### 承認済みservers programのruntime参照

値はすべてproduction環境のsecretとして設定し、repository、返信、logへ貼らない。下表は参照名だけを正本台帳から
転記したもので、設定済みという意味ではない。

|partner ID|提携状態|承認状態参照|destination参照|
|---|---|---|---|
|`a8net-xserver-business`|approved|`A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT`|`A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION`|
|`moshimo-conoha-wing`|approved|`MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT`|`MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION`|
|`moshimo-lolipop-rental-server`|approved|`MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT`|`MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION`|
|`moshimo-onamae-rental-server`|approved|`MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT`|`MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION`|
|`moshimo-shin-rental-server`|approved|`MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT`|`MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION`|
|`valuecommerce-ablenet-shared-server`|approved|`VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT`|`VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION`|

記事別GOは`SERVER_CTA_GO`へ上表のpartner IDだけを重複なく渡す。提携状態参照が`true`、destinationがASP固有の
HTTPS host・path・必須parameter検証に合格し、SVR記事の承認とindexが成立したpartnerだけを表示する。

## 2026-08-06 A8.net program調査

Humanの`asp_program_search: GO A8.net`に基づき、ログイン済み正規画面をread-onlyで確認した。提携申請、
広告link取得、tracking ID取得、外部送信は行っていない。

|Program|カテゴリ|成果報酬|成果条件の記録範囲|確定率|提携状態|
|---|---|---|---|---|---|
|XServerビジネス|servers|`restricted_dashboard_only`|6か月以上の新規契約と試用期間内支払。tier別条件あり|`restricted_dashboard_only`|`approved`|
|formrun|forms|`restricted_dashboard_only`|広告主新規、有料plan登録、1か月以上継続|`unknown`|`not_applied`|
|WiLL Mail|email_marketing|`restricted_dashboard_only`|広告主新規、trial導線、所定期間内の本人確認|`restricted_dashboard_only`|`not_applied`|
|freee会計|accounting|`restricted_dashboard_only`|通常planの新規導入。詳細未確認|`unknown`|`not_applied`|
|マネーフォワード クラウド会計|accounting|`restricted_dashboard_only`|通常planの新規導入。複数案件のため申請前に再確認|`unknown`|`not_applied`|
|弥生シリーズ|accounting|`unknown`|商品別成果。金額・詳細条件は未確認|`unknown`|`not_applied`|
|Misoca|accounting|`restricted_dashboard_only`|無料体験planの新規申込。詳細未確認|`unknown`|`not_applied`|

HubSpot、kintone、サイボウズ、ConoHa、Benchmark Email、blastmailはA8.netで直接programを確認できなかった。
不存在とは断定せず、台帳では`not_confirmed`として、もしもアフィリエイトとバリューコマースの確認待ちにする。

## 2026-08-07 もしも・バリューコマース program調査

ログイン済みのもしもアフィリエイト正規画面で`レンタルサーバー`をread-only検索し、次の4件を
servers候補として台帳へ追加した。バリューコマースではABLENETの個別条件を確認し、2026-08-08に
提携申請後の「提携済み」をread-backした。広告素材、広告link、tracking IDは取得していない。ログイン後だけ表示される報酬値は
`restricted_dashboard_only`として値を保存しない。

|ASP|Program|確認範囲|提携状態|
|---|---|---|---|
|もしも|ロリポップ！レンタルサーバー会員登録|新規契約・3か月以上の契約・入金。本人等の申込と更新は対象外。審査なし、再訪問90日、承認期限60日|`approved`（2026-08-09 read-back）|
|もしも|シンレンタルサーバー|複数planの新規成約後、試用期間内の料金支払い完了。本人申込は1回限り、成果承認期限45日|`approved`（2026-08-12 read-back）|
|もしも|ConoHa WING|新規account登録後30日以内のWING申込。30日以上の利用状況・planでtier確定。本人申込は1回限りで、3か月契約の本人申込は対象外|`approved`（2026-08-12 read-back）|
|もしも|お名前.com レンタルサーバー|共用サーバーまたはVPSの申込完了。本人申込可、成果承認期限120日|`approved`（2026-08-12 read-back）|
|バリューコマース|ABLENETレンタルサーバー（共用サーバー）|新規申込・決済完了と翌月利用確認、除外条件、検索広告禁止を個別画面で確認|`approved`|

## 単価×需要判定

月20万円に必要な成約数は`ceil(200,000円 ÷ 最高単価)`、必要sessionsは成約率1%の仮定値として
`成約数 ÷ 0.01`で計算する。1%は実績ではなくmodeled assumptionであり、confirmed conversionが得られたら置換する。
ログイン後だけ表示される単価を公開repositoryへ保存しないため、下表の逆算値もrepositoryでは`restricted`とする。

|カテゴリ|W6 known需要/月|最高単価案件|必要成約数|必要sessions（CVR 1%仮定）|判定|
|---|---:|---|---:|---:|---|
|servers|28,220（14/40 known、no_data率65%）|XServerビジネス|`restricted`|`restricted`|2026-08-06 Human選定のprimary。需要単独では5万/月未満で、収益性確定とは扱わない|
|accounting|6,320（9/40 known、no_data率77.5%）|マネーフォワード クラウド会計|`restricted`|`restricted`|必要22,227 sessionのknown下限未達。現時点では拡張しない|
|forms|`unknown`|formrun|`restricted`|`restricted`|需要CSV未取得のため判定しない|
|email_marketing|`unknown`|WiLL Mail|`restricted`|`restricted`|需要CSV未取得のため判定しない|
|crm|`unknown`（30/40の部分結果は不採用）|A8.net直接program未確認|`unknown`|`unknown`|残り10語と、もしも・バリューコマースのprogram確認を待つ|

### Evidence-gated next step

|姿勢|調査案|Hard gate|停止条件|
|---|---|---|---|
|conservative|serversの既知需要と承認済み6programを記事候補へ対応付ける|SVR01のcanonical価格・記事承認・runtime destination・partner別CTA GOが未完了|提携否認、またはHuman価格観測不能|
|balanced|serversの6記事slate・価格観測・TCO対応をlocalで先行し、1 vendorずつ検証|価格・提携・公開は各別gate|golden不一致、unknownの推測補完、需要または提携の否定証拠|
|aggressive|5カテゴリを同時申請・同時公開する|需要unknownかつ提携未承認のため`ineligible`|現状は開始しない|

2026-08-06のHuman decisionで`balanced`を採用した。これはserversのlocal準備だけを許可し、申請・公開・CTAを許可しない。
accountingは40/40実測でknown下限が必要sessionを下回ったため拡張しない。forms / crm / email_marketingは
完全slate未取得のまま、有望と判定しない。

## 2026-08-07 readiness read-back

|対象|現在地|次の解除条件|
|---|---|---|
|A8.net|`ACCOUNT REGISTERED / XSERVER APPROVED`|2026-08-08に参加中プログラム一覧で提携承認をread-back済み。servers記事承認、runtime destination、開示先行、partner別CTA gateがそろうまではCTA不可|
|もしもアフィリエイト|`ACCOUNT + MEDIA REGISTERED / 4 SERVER PROGRAMS APPROVED`|2026-08-09にロリポップ、2026-08-12にシンレンタルサーバー、ConoHa WING、お名前.comの提携中表示をread-back済み|
|バリューコマース|`ACCOUNT REGISTERED / ABLENET APPROVED`|個別条件と「提携済み」を2026-08-08にread-back済み。servers記事承認、runtime destination、開示先行、partner別CTA gateがそろうまではCTA不可|

公開originのread-only確認結果:

- `https://saastcolab.jp/`、運営者情報5route、P01–P03はすべてHTTP 200。
- P01–P03はHuman承認済みでindex可、PR開示先行、Mangools CTAだけが有効。他記事・他partner CTAはfail-closedを維持する。
- 申請URL、公開origin、canonical originは`https://saastcolab.jp`で一致する。

したがって、Account登録はA8.net、もしも、バリューコマースの三社で完了し、serversの個別programは6件が
`approved`である。次にHumanが行うのは、Human確認済み価格を使ったservers記事の承認と、対象programごとの
runtime destination設定・partner別CTA GOである。これらがそろうまで、servers CTAはすべて無効とする。

2026-08-06の画面確認では、A8.netのXServerビジネス詳細画面で選択中のappeal siteがSaaS TCO Labではなく
既存の別mediaだった。その後、A8の登録site `SaaS TCO Lab`を主サイトへ変更して画面read-back済みである。
2026-08-07にSaaS TCO Lab選択済みのprogram詳細を再度read-backし、Humanの対象program名付きGOに基づいて
申請しました。申請完了画面は確認済みですが、提携承認とは数えません。

2026-08-12、SafariでHuman本人認証が完了した後、もしもの残り3program（シンレンタルサーバー、
ConoHa WING、お名前.com レンタルサーバー）についてprogram名付き`asp_program_terms_accept`を受領し、
`saaslab`を対象に申請した。正規検索画面のread-backでは3programとも`提携中`である。非公開の報酬値、
広告link、tracking IDはrepoへ保存していない。CTAはruntime destination設定、記事承認、partner別GOまで無効を維持する。

## 推奨申請順

1. A8.net: 会員登録に入会時審査がないため最初に実行する。ただしprogram提携は別審査として扱う。
2. もしもアフィリエイト: Account・メディア登録済み。servers候補4programは提携承認済み。CTAは別GOまで無効。
3. バリューコマース: Account本登録済み。ABLENET共用サーバーは提携承認済みで、CTAは記事・destination・個別gateを待つ。

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

Accountまたは個別programの状態が変わった場合は、機密値を含めず次の形式で返す。

```text
asp_account: <a8net|moshimo|valuecommerce> <registration_incomplete|registered|under_review|approved>
asp_program: <partner> <program名> <カテゴリ>
asp_partnership: <partner> <not_applied|pending|approved|denied>
asp_program_apply: GO A8.net <program名> / HOLD A8.net <program名>
```

成果報酬額、成果条件、開示要件は公開可能な規約表示だけを転記する。tracking ID、広告link URL、
本人情報、非公開条件は返信にも含めない。
