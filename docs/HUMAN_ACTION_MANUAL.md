# Human Action Manual — あなたが操作する箇所だけ

基準日: 2026-07-26（Asia/Tokyo）

この表は、本人確認、credential、法的同意、税務・受取情報、最終事業判断のように、Human Approver本人でなければ完了できない作業だけを残したものです。価格収集、入力整形、比較計算、検証、実装、集計、監視はCodex側で進めます。

パスワード、2FAコード、Cookie、Affiliate URL、tracking ID、税番号、口座情報は、チャット、メール本文、repoへ貼らないでください。

## 月末までのカード不要モード

2026-07-31までは、カード登録、有料trial、支払いプロファイル作成、課金開始を行わない。
Google Workspace、domain購入、OpenAI API、challenger AI、有料cloud・有料hosting、有料SEO toolは保留する。
カード不要Sitesの公開前originだけは、2026-07-26のHuman指示に基づき一般公開済みである。
無料登録であってもカード画面が出た時点で停止し、代替カードや別Payments profileを繰り返し試さない。

この期間に先行できるのは、許諾文面の確認、対象別GO後の問い合わせ、Mangools無料登録、
SE Ranking Affiliate窓口への例外問い合わせ、HubSpot申請準備、ローカル品質検証である。
カード不要という条件は、外部送信、規約同意、account作成を包括承認しない。下記のexact GOは維持する。

## 操作一覧

|ID|時期|あなたが行うこと|所要目安|現在地|完了の合図|完了後にCodexが行うこと|
|---|---|---|---:|---|---|---|
|H1|完了|公開名義と公開予定URLを決める|0分|brand=`SaaS TCO Lab`、approver=`omishu`、恒久origin確定・外部readback済み|追加操作なし|GSC/GA4と申請先siteを同一originへそろえる|
|H2|初回分類承認済み・追加回答待ち|5社への利用許諾照会を承認する|0分|Semrush/Serpstatの保守的分類は2026-07-26承認済み。Serpstat正式回答と他3社回答待ち|新回答時だけfield判定表へ`approve / revise`|Human承認済みのrights decisionだけを台帳化する|
|H3|見送り|Google Adsをカード要求前まで進める変更不能設定を承認する|0分|2026-07-26、日本・日本時間をread-back後、支払い方法の一時承認課金画面で未送信停止。同日Human判断でGoogle Ads／Keyword Planner経路をskip|追加操作なし|Google Adsへ再進入せず、承認済みの代替JP/ja需要exportを待つ|
|H4|完了|MangoolsのcredentialとreCAPTCHAを本人操作する|5–8分|2026-07-26登録済み・Affiliate有効|追加操作なし|回答待ちのrightsと公開準備が整うまで紹介IDを非公開のまま保持する|
|H5|完了|SE Rankingへwork emailなしの登録方法を問い合わせる|2分|2026-07-23送信済み・回答待ち|追加操作なし|回答を登録可否・必要証拠・条件へ分解する|
|H6|申請完了・審査待ち|HubSpot Impact契約への同意、credential、申請送信を本人操作する|0分|2026-07-26に申請送信済み。JPY確定、追加Marketplace・税務・受取設定は未操作|追加操作なし|審査を追跡し、承認・条件・期限をhash-only記録へ変換する|
|H6-S|Impact Marketplace規約同意完了・税務待ち|表示中のImpact税務画面で正しい登録状況を本人判断し`Save`する|2–5分|税務情報、profile、media propertyが未完了。Semrush申請未送信|保存後に`impact_tax_information: done`|税務値を保存せず、SaaS TCO Lab限定で残りのonboardingへ進む|
|H7|回答到着時|各社回答の権限・scopeについて最終判断する|1社5分|未到着|Codexのfield別判定案に`approve`または`reject`|`SourcePolicy`へfield単位で反映し、許可済みsourceだけadapterを実装する|
|H8|提携承認後|受取方法・税務情報・本人確認を各サービスで入力する|1社10–20分|提携承認待ち|画面上の完了だけを知らせる。値は共有しない|支払条件と期限だけを非機密の証拠へ反映する|
|H9|需要合格後|30日shadow runの開始日を承認する|2分|Gate A–C待ち|開始日と`shadow_run: GO`|30日の日次処理、故障試験、例外・人手・成功率の集計を開始する|
|H10|一部完了|実データ、indexing、Affiliate CTA、独自domain、法的表示を個別承認する|10分|安全なnoindex公開前版だけ本番originで稼働中|各対象へのexact `GO`|実運用releaseをreadbackし、rollback可能性を確認する|

## 今すぐ返信するテンプレート

公開URL、名義、Google Ads見送り、Mangools登録、HubSpot申請は確定済みなので再入力しません。
直前の外部3操作と候補台帳3件は2026-07-26に一括承認され、実行・記録済みです。
現在必要なのは、Impact税務情報の本人入力と、新しい公開・analytics送信gateの判断です。

```text
impact_tax_information: done
gsc_verification_deploy: GO / STOP
ga4_tag_deploy: GO / STOP
```

利用許諾照会の既定値は、取得頻度を`週1回以下`、履歴保持を`36か月（相手方がより短い期間を指定した場合はその期間）`とします。変更したい場合だけ返信へ追記してください。

## 画面別マニュアル

### H3 — Google Ads / Keyword Planner

1. Google Adsの「アカウント設定の確認」を開きます。
2. `請求先住所の国 = 日本`、`タイムゾーン = (GMT+09:00) 日本時間`、`通貨 = 日本円 (JPY)`を確認します。
3. この3項目は後から変更できないため、問題なければ`google_ads: GO`と返信します。
4. Codexが「続行」以後を進めます。支払情報、追加規約、2FA、本人確認が表示された場合だけあなたへ引き継ぎます。
5. カードまたはPayments profileを要求された場合は入力せず、月末まで停止します。
6. 無料範囲でKeyword Plannerへ入れた場合だけ、地域=`日本`、言語=`日本語`、150語の投入、CSV export、重複除去をCodexが実行します。

2026-07-26の実行では、日本と日本時間を確認した後、既存の支払い方法を使う一時承認課金の
説明と送信ボタンが表示されたため、カード不要条件に従って未送信で停止した。カード情報、
支払いprofile識別子、Google Ads識別子は記録していない。同日Human判断でこの経路はskipし、
月末後も自動再試行しない。JP/ja需要gateには、利用権が承認された別exportまたは公開後の
Search Console実測を使用する。Google Trendsの相対指数だけでは需要gateを合格扱いにしない。

### H4 — Mangools

2026-07-26に無料アカウントの作成とAffiliate sectionの有効化を確認しました。紹介IDと
紹介素材は発行済みですが、識別子そのものはrepo・文書・会話へ保存しません。確認時点の最小条件は、
Silver tier 25%、cookie 30日、PayPal、支払申請条件は承認済み売上$150以上かつ異なる利用者2名以上です。
報酬tierは直近3か月平均売上を基準に毎月4日に再計算され、conversion承認は毎月15日、
支払申請期限は報酬発生から2年です。

禁止事項はcoupon site、MangoolsへのPPC直リンク、Mangoolsブランドを使うPPC・domain・subdomain・
social profile、誤認表示、self-referral、未承諾emailです。これはAffiliate利用状態の確認であり、
価格データの取得・保存・比較表示・TCO派生・履歴利用の許諾回答ではありません。

### H5 — SE Ranking

1. 通常登録はwork email必須のため再試行しません。
2. `affiliates@seranking.com`宛ての例外問い合わせは2026-07-23に送信済みです。
3. 回答前にGoogle Workspace、別Payments profile、架空の会社情報を作りません。
4. 公式回答到着後、登録方法とAffiliate条件を改めてHumanが確認します。

送信済み文面は次のとおりです。Gmailの送信済みメールを正本とし、ここから再送しません。

```text
To: affiliates@seranking.com
Subject: Affiliate registration without a corporate email

Hello SE Ranking Affiliate Team,

I am an independent publisher based in Japan and am preparing a
Japanese-language SEO/SaaS comparison website.

I would like to join the SE Ranking Affiliate Program, but the account
registration form requires a work email address. I currently do not have
a corporate-domain email address.

Could you please advise whether an independent publisher can register
using a personal email address, or whether manual review or invitation is
available?

I will comply with the SE Ranking Affiliate Agreement and applicable
promotional requirements.

Best regards,
omishu
```

### H6 — HubSpot Impact（2026-07-26申請送信済み）

1. Humanのaction-time承認後、ImpactのPartner Program Agreementへ同意し、申請を送信しました。
2. siteは`https://saas-tco-lab-jp.shukun0930.chatgpt.site`、表示名は`SaaS TCO Lab`、
   事業区分は`Search/Comparison`、通貨はJPYで確定しました。
3. 申請後に表示されたImpact Marketplace参加、追加規約、税務情報、受取情報は別gateとして未操作です。
4. HubSpotの審査結果が届くまで、Affiliate承認・CTA・収益計上へ進めません。
5. 承認後もpublic pricingの取得・保存・TCO・履歴権は別回答として確認します。

### H6-S — Semrush Impact

1. 2026-07-26、Humanのaction-time承認後に契約checkboxと`Continue`を完了しました。
2. macOS credential store解除、Impact credential受付、SMS端末認証、既存Impact accountへのloginは完了しました。
3. 2026-07-26、Humanのaction-time承認`impact_terms_accept: GO`後にPartner User Agreement（画面上の更新日2024-07-10）とMaster Program Agreement（現行URLを2026-07-26確認）へ同意しました。規約全文は保存していません。
4. 現在はImpact税務画面で、`JapanのCT登録済み`、`別国のIndirect Tax登録済み`、`Indirect Tax未登録`のいずれかを選択して`Save`する本人判断で停止しています。
5. Humanが正しい税務状態を画面上で選択・保存し、`impact_tax_information: done`とだけ知らせます。選択内容や税番号等はchat・repo・logへ共有しません。
6. Codexが税務完了checkboxを確認後、profileとmedia propertyをSaaS TCO Labだけに限定して送信直前まで進めます。FANZA・成人向けbrand/domain/contentは登録しません。
7. カード、有料契約、支払方法を要求された場合は未送信で停止します。Marketplace onboarding完了後もSemrush最終送信は別のaction-time確認まで行いません。
8. Affiliate承認を、禁止回答済みの自動取得・継続保存・履歴DB化の許可へ読み替えません。

### H7 — 利用許諾回答

1. 回答メールは削除・転送せずGmail内に残します。
2. `○○社から回答あり`とだけ知らせます。
3. Codexが、取得・保存・比較表示・TCO派生・履歴・商標・Affiliate・終了時削除の8項目へ分解します。
4. Codexが示す`approved / prohibited / unreviewed`案と期限を確認し、Human Approverが最終承認します。
5. 曖昧な回答は承認へ補完せず、再質問または`unreviewed`のまま停止します。

## Codex側で完了済み・継続する範囲

|作業|状態|
|---|---|
|5社の公式規約・Affiliate条件の分離調査|完了|
|5社のfield-level利用許諾メール|2026-07-23送信済み。Semrush回答確認済み。Serpstatは2026-07-26 requested due-diligence返信済み・正式回答待ち。Mangools・HubSpot・SE Ranking待ち|
|SE Ranking公式窓口とAffiliate条件|確認済み|
|SE Ranking通常登録|work email必須で停止。カード不要の公式問い合わせを2026-07-23送信済み、回答待ち|
|HubSpot / Semrush Impact申請導線|HubSpotは申請済み・審査待ち。SemrushはImpact Marketplace規約同意済み、税務・profile・media property待ち・申請未送信|
|Google Ads / Keyword Planner|変更不能な初期設定の続行直前|
|Google Trends予備export|汎用5語・ブランド5語の2 CSV取得済み。相対指数なので本番証拠には不採用|
|JP/ja購買意図キーワード|150語のfreeze・重複/PII/locale検証を実装|
|公開前site|カード不要Sitesで公開済み。noindex、外部link 0、実価格0、Affiliate CTA 0、内部routeは503|
|Search Console / GA4|新originのGSC propertyとGA4 streamを作成済み。GSC所有確認用deployとGA4 tag/送信は別gateで未実行|
|実価格取得・indexing・実Affiliate CTA|Gate A–C合格まで技術的にSTOP|

## 停止条件

- credential、2FA、CAPTCHA、税務・受取情報はCodexへ共有しない。
- 規約同意、契約発効、申請送信は、対象文書を確認したHuman本人が行う。
- 利用許諾が届くまで、対象会社の価格fieldを自動取得・保存・公開しない。
- Affiliate申請中を承認済みとして数えない。
- Google Trends指数を月間検索数へ換算しない。
- 3社のrights、3社のAffiliate、JP/ja需要が揃うまで、実価格、実Affiliate CTA、indexingを公開しない。
