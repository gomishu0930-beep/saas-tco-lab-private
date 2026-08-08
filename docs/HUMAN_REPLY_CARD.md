# Human返信カード

返信はこの文書から一行をコピーし、`<>`だけを置き換える。credential、verification値、property ID、
measurement ID、partner ID、tracking ID、支払情報、メール本文は追記しない。GOは書かれたscopeだけに有効で、
domain GOからindex GOやCTA GOを推論しない。

現在地: P01–P03のR1–R6読者向け改稿版とP06/P07は2026-08-08に公開済みで、5記事のMangools CTAも稼働中。
外部read-backで5記事だけのindex・sitemap、他記事のnoindex、開示先行を確認済み。serversはSVR01
candidate-only contractをlocal保存済みで、XServerビジネスとABLENET共用サーバーは各ASP管理画面の提携済み表示をread-back済みである。
価格のcanonical採用・servers記事公開は未完了。Xは`@saastcolab`でP01初回スレッド8件を公開済みである。

## 今使うtoken

|目的|返信token|記入例|意味|
|---|---|---|---|
|Domain開始|`domain: GO <domain> / HOLD`|`domain: GO example.jp`|exact domainのdomain dayだけを開始|
|価格表示分類|`sale_banner_state: <class> <partner>`|`sale_banner_state: annual_discount_permanent mangools`|`none` / `annual_discount_permanent` / `time_limited_promo` / `unknown`のHuman分類を記録|
|Checkout再観測完了（必要時）|`checkout_values: done`|`checkout_values: done`|既存確定値を更新する再観測時だけ使用。Mangools初回値は2026-08-02に取込済み|
|記事入力完了|`article_input: done <P-ID>`|`article_input: done P01`|Operatorが出力したcontractの取込・再検証を依頼|
|記事承認|`article_approve: <P-IDまたはSVR-ID,...>`|`article_approve: P01,P02,P03`|列挙した記事本文だけをHuman承認。serversは価格・TCO・用途判定がREADYのSVR-IDだけ有効|
|記事修正|`article_revise: <P-ID> <修正点>`|`article_revise: P01 税区分を再確認`|対象記事をunreviewedへ戻す|
|Index判断|`index_go: GO / HOLD`|`index_go: HOLD`|承認済み記事だけのindex可否。CTAには効かない|
|Partner CTA|`cta_go: GO <partner> / HOLD <partner>`|`cta_go: GO mangools`|当該partnerの承認済みCTAだけを対象化|
|Impact feed有無|`impact_feed_check: <available\|unavailable\|unclear> <partner>`|`impact_feed_check: available HubSpot`|承認済みpartnerのcatalog表示有無だけを記録|
|Impact feed A1登録|`impact_feed_a1: GO <partner> / HOLD <partner>`|`impact_feed_a1: HOLD HubSpot`|全利用scopeを確認したexact feedだけsource policy候補へ登録。取得は開始しない|
|Mangools需要CSV|`mangools_csv: done / pending`|`mangools_csv: done`|凍結済みquery CSVのlocal検証を開始|
|Scope拡大準備|`scope_expand: GO (準備scope) / HOLD`|`scope_expand: GO (準備scope)`|2026-08-05受領済み。query・checklist・template準備だけで、公開・申請・照会は許可しない|
|優先カテゴリ|`category_primary: GO <category> / HOLD`|`category_primary: GO servers`|2026-08-06受領済み。serversのlocal記事・観測表・計算機準備だけを許可|
|日本ASP申請|`asp_signup: GO <ASP> / HOLD <ASP>`|`asp_signup: GO A8.net`|列挙したASPのHuman申請だけを開始|
|ASP account状態|`asp_account: <partner> <registration_incomplete / registered / under_review / approved>`|`asp_account: a8net registered`|機密値を含めずpartner台帳を更新|
|もしも本登録完了（確認済み）|`moshimo_email_verify: done / HOLD`|`moshimo_email_verify: done`|2026-08-07に管理画面へログイン済みであることをread-back済み。再返信不要|
|ASP個別提携状態|`asp_partnership: <partner> <not_applied / pending / approved / denied>`|`asp_partnership: a8net pending`|program名・カテゴリ・公開可能な条件を別途確認して更新|
|ASP個別program申請|`asp_program_apply: GO <ASP> <program名> / HOLD <ASP> <program名>`|`asp_program_apply: GO A8.net formrun`|対象program一件だけの提携申請を許可。CTA・広告link取得は別GO|
|A8再認証完了（確認済み）|`a8_reauth: done`|`a8_reauth: done`|2026-08-07にSaaS TCO Lab選択済みのprogram詳細をread-back済み。再返信不要|
|もしも再認証・結果確認|`moshimo_reauth: done`|`moshimo_reauth: done`|ロリポップ！申請操作後にsessionが失効したため、Human再ログイン後に提携状態だけをread-only確認。重複申請しない|
|もしもメディア適法性確認|`moshimo_media_attestation: done`|`moshimo_media_attestation: done`|SaaS TCO Labが権利を侵害していないことをHuman本人が画面で確認し「はい」を押した後だけ使用。Codexは代行しない|
|バリューコマース本登録完了|`valuecommerce_registration: done`|`valuecommerce_registration: done`|本登録案内メールの期限内URLからHumanが手続きを完了した後、ABLENET候補の個別条件をread-onlyで再確認|
|servers候補入力|`server_price_input: done <SVR-ID>`|`server_price_input: done SVR01`|`/operator/servers/`の候補値をHumanが確認し、確定ボタンを押して保存したcandidate-only JSONをlocal検証。公開・CTAには効かない|
|servers記事承認|`article_approve: <SVR-ID>`|`article_approve: SVR01`|TCO・用途判定・Human確認がすべてREADYの本文だけを承認。index・CTAには効かない|
|localhost候補JSON download許可|`local_download_permission: GO localhost <SVR-ID> / HOLD`|`local_download_permission: GO localhost SVR01`|Safariの一回のlocalhost download許可だけを承認。外部送信・公開・CTA・ASP申請には効かない|
|P01 note修正|`note_edit_go: GO P01 PR先頭追記 / HOLD`|`note_edit_go: GO P01 PR先頭追記`|既存noteの先頭へlocal templateのPR表示だけを追記する外部編集を許可|
|SaaS専用X（完了記録）|`account_repurpose: GO <旧handle> retire_fanza`|`account_repurpose: GO @fanza_poll_lab retire_fanza`|2026-08-06受領・完了済み。再実行しない|
|P01 X初回投稿|`x_post: GO P01 / HOLD P01`|`x_post: HOLD P01`|冒頭PR表示、P01の読者向け本文、saastcolab.jpのP01 URLだけを投稿対象にする。ASP広告linkは含めない|
|Release用push|`repository_update_push: GO / HOLD`|`repository_update_push: HOLD`|提示済みrelease対象だけをcommit・pushする。診断履歴、output、credentialは除外|
|R1–R6 deploy|`deploy_update: GO P01,P02,P03 R1-R6 / HOLD`|`deploy_update: HOLD`|push済みの読者向け改稿3記事だけを本番反映。index・Mangools CTAの既存gateは維持|
|月次KPI CSV|`monthly_kpi_csv: done / pending <source>`|`monthly_kpi_csv: done`|dashboard safe total更新を開始|
|Mangools月次|`mangools_monthly: unchanged / changed review_needed`|`mangools_monthly: unchanged`|tier・conversion画面の変化有無だけを記録|
|Rights回答|`rights_decision: approve / revise / reject`|`rights_decision: revise Semrush history`|新しい実質回答のfield分類だけを判断|

## Domain dayで順番に返すtoken

途中のHOLDで後続stepは停止する。値やrecord内容は返信しない。

```text
domain_purchase: done <domain>
sites_domain_record: ready <domain>
dns_saved: done <domain> / HOLD <domain>
domain_readback: done <domain> / HOLD <domain>
gsc_property: done <domain> / HOLD <domain>
ga4_stream: done <domain> / HOLD <domain>
redirect_map: approve <domain> / HOLD
impact_domain_verification: done <domain> / HOLD
domain_day: done <domain> / HOLD <domain>
```

Rollbackが必要な時だけ:

```text
rollback: GO prelaunch-origin
```

## 記事承認の例

### 第1弾を一つずつ

```text
article_input: done P01
article_approve: P01
```

### 複数記事をまとめる

```text
article_approve: P01,P02,P03
```

空白区切り、範囲表記、`all`は使わない。未入力・validation不合格・期限切れ記事は列挙しても承認状態へ進めない。

## Impact feed確認の例

`docs/IMPACT_PRODUCT_FEED_CHECKLIST.md`を使う。Affiliateがactiveで、catalogが表示されても、取得・保存・
履歴・派生・表示・終了時処理の利用scopeに未確認があればA1はHOLDにする。

```text
impact_feed_check: available HubSpot
impact_feed_a1: HOLD HubSpot
```

全scopeを確認できた場合だけ、二行目を`GO`にする。GOはlocal source policy登録だけを許可し、download、
API/FTP credential、定期取得、raw保存、公開、CTA変更を許可しない。

## 通知された時だけ使うtoken

|Trigger|Token|既定|
|---|---|---|
|Affiliate exportが用意できた|`affiliate_export_ready: <partner>`|未通知なら返さない|
|GA4 internal filter本番化|`ga4_internal_filter_activate: GO / HOLD`|HOLD。testのまま|
|30日shadow開始|`shadow_run: GO / STOP`|STOP。editorial launch条件ではない|
|外部challenger予算|`challenger_budget: GO <provider> / HOLD`|HOLD|
|初期gold label確認|`initial_gold_labels: done / pending`|pending|
|Notion導入再評価|`notion: use / skip`|skip|
|OpenAI課金project|`openai_project: done / pending`|pending|

## 完了済み・再利用しないtoken

次は履歴確認用であり、新しい指示として再送しない。

```text
gsc_verification_deploy: GO
ga4_tag_deploy: GO
ga4_property: done
gsc_property: done
impact_terms_accept: GO
impact_verification_deploy: GO
semrush_submit: GO
```

Google Adsはskip済みで、自動再試行しない。

`human_budget: GO 2000min/month`は2026-07-30最終指示で発効済み。再返信は不要で、2026-08〜10の
launch trackだけに適用する。
