# Human Action Manual — あなたが操作する箇所だけ

基準日: 2026-07-23（Asia/Tokyo）

この表は、本人確認、credential、法的同意、税務・受取情報、最終事業判断のように、Human Approver本人でなければ完了できない作業だけを残したものです。価格収集、入力整形、比較計算、検証、実装、集計、監視はCodex側で進めます。

パスワード、2FAコード、Cookie、Affiliate URL、tracking ID、税番号、口座情報は、チャット、メール本文、repoへ貼らないでください。

## 月末までのカード不要モード

2026-07-31までは、カード登録、有料trial、支払いプロファイル作成、課金開始を行わない。
Google Workspace、domain購入、OpenAI API、challenger AI、cloud、hosting、有料SEO toolは保留する。
無料登録であってもカード画面が出た時点で停止し、代替カードや別Payments profileを繰り返し試さない。

この期間に先行できるのは、許諾文面の確認、対象別GO後の問い合わせ、Mangools無料登録、
SE Ranking Affiliate窓口への例外問い合わせ、HubSpot申請準備、ローカル品質検証である。
カード不要という条件は、外部送信、規約同意、account作成を包括承認しない。下記のexact GOは維持する。

## 操作一覧

|ID|時期|あなたが行うこと|所要目安|現在地|完了の合図|完了後にCodexが行うこと|
|---|---|---|---:|---|---|---|
|H1|今|公開名義と公開予定URLを決める|3分|入力待ち|下の返信テンプレート3項目を返す|5社の許諾メールを同じscopeへ確定する|
|H2|完了|5社への利用許諾照会を承認する|2分|2026-07-23送信済み・回答待ち|追加操作なし|回答を8項目へ分解し、Human最終判定へ回す|
|H3|今|Google Adsをカード要求前まで進める変更不能設定を承認する|2分|日本／日本時間／日本円の「続行」直前|`google_ads: GO`と返す|無料範囲ならKeyword Plannerへ進み、カード要求時は停止する|
|H4|完了|MangoolsのcredentialとreCAPTCHAを本人操作する|5–8分|2026-07-26登録済み・Affiliate有効|追加操作なし|回答待ちのrightsと公開準備が整うまで紹介IDを非公開のまま保持する|
|H5|完了|SE Rankingへwork emailなしの登録方法を問い合わせる|2分|2026-07-23送信済み・回答待ち|追加操作なし|回答を登録可否・必要証拠・条件へ分解する|
|H6|H4と並行可|HubSpot Impact契約への同意、credential、申請送信を本人操作する|10–15分|契約checkbox直前。契約PDF保存済み|送信後に`hubspot_application: submitted`|2–3営業日の審査を追跡し、承認・条件・期限をhash-only記録へ変換する|
|H7|回答到着時|各社回答の権限・scopeについて最終判断する|1社5分|未到着|Codexのfield別判定案に`approve`または`reject`|`SourcePolicy`へfield単位で反映し、許可済みsourceだけadapterを実装する|
|H8|提携承認後|受取方法・税務情報・本人確認を各サービスで入力する|1社10–20分|提携承認待ち|画面上の完了だけを知らせる。値は共有しない|支払条件と期限だけを非機密の証拠へ反映する|
|H9|需要合格後|30日shadow runの開始日を承認する|2分|Gate A–C待ち|開始日と`shadow_run: GO`|30日の日次処理、故障試験、例外・人手・成功率の集計を開始する|
|H10|公開直前|domain、法的表示、privacy、公開を個別承認する|10分|まだ実施禁止|各対象へのexact `GO`|noindex staging、readback、rollback後に別途公開判定へ進む|

## 今すぐ返信するテンプレート

未公開の場合、`site_url`は`未公開`で構いません。ただしHubSpotなどの審査は、外部から確認できる公開URLがないと不承認または保留になる可能性があります。

```text
legal_name_or_entity:
site_url:
human_approver_name:

google_ads: GO / STOP

mangools_terms: GO / STOP
hubspot_impact_contract: GO / STOP
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

### H6 — HubSpot Impact

1. 保存済み`HubSpot-Affiliate-Agreement-2024-09-18.pdf`を読みます。
2. Impactの`Contract Terms for HubSpot`画面へ戻ります。
3. 同意する場合だけcheckboxを選び、`Continue`を押します。
4. credential、2FA、本人・事業情報、公開予定site、集客方法は本人が入力します。
5. 申請内容を確認し、本人が送信します。
6. `hubspot_application: submitted`と返信します。入力値やcredentialは共有しません。
7. カード、有料契約、支払方法を要求された場合は送信せず停止します。

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
|5社のfield-level利用許諾メール|2026-07-23送信済み、回答待ち|
|SE Ranking公式窓口とAffiliate条件|確認済み|
|SE Ranking通常登録|work email必須で停止。カード不要の公式問い合わせを2026-07-23送信済み、回答待ち|
|HubSpot Impact申請導線|契約同意直前まで準備済み|
|Google Ads / Keyword Planner|変更不能な初期設定の続行直前|
|Google Trends予備export|汎用5語・ブランド5語の2 CSV取得済み。相対指数なので本番証拠には不採用|
|JP/ja購買意図キーワード|150語のfreeze・重複/PII/locale検証を実装|
|公開site・実価格取得・実Affiliate CTA|Gate A–C合格まで技術的にSTOP|

## 停止条件

- credential、2FA、CAPTCHA、税務・受取情報はCodexへ共有しない。
- 規約同意、契約発効、申請送信は、対象文書を確認したHuman本人が行う。
- 利用許諾が届くまで、対象会社の価格fieldを自動取得・保存・公開しない。
- Affiliate申請中を承認済みとして数えない。
- Google Trends指数を月間検索数へ換算しない。
- 3社のrights、3社のAffiliate、JP/ja需要が揃うまで公開しない。
