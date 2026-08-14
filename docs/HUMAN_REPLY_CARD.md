# Human返信カード

返信はこの文書から一行をコピーし、`<>`だけを置き換える。credential、verification値、property ID、
measurement ID、partner ID、tracking ID、支払情報、メール本文は追記しない。GOは書かれたscopeだけに有効で、
domain GOからindex GOやCTA GOを推論しない。

現在地: P01–P12は12/12入力済み、11/12承認・公開済みです。これとは別にserversのSVR01を1本承認・公開し、
公開・index対象は合計12本です。
2026-08-13の外部read-backでP01–P10・P12の11記事だけのindex・sitemap、P11のnoindex、
開示先行gate、Mangools CTAを確認済みです。P09はHuman確認済み実測contractを承認・公開済みで、
P11だけが2026年9月・10月の完全暦月データ待ちです。
Search Console domain propertyと専用GA4 streamも連携済みです。SVR01は通常料金と期間限定cashbackを分離した
v3 contractに基づき、年次一括前払50,160円+初期費用16,500円=契約時請求66,660円を承認・index対象として
公開済みです。24/36か月TCO、更新時料金、順位、推奨はunknownのままです。servers案件は6件提携承認済みですが、
runtime destination未設定のためserver CTAは0件です。Xは`@saastcolab`でP01初回スレッド8件を公開済みです。
X API connectorは2026-08-13のread-only照合でSaaS専用accountではないbindingを返したため使用停止中で、
Safari上のSaaS専用運用と混ぜません。

## 今使うtoken

|目的|返信token|記入例|意味|
|---|---|---|---|
|Domain開始|`domain: GO <domain> / HOLD`|`domain: GO example.jp`|exact domainのdomain dayだけを開始|
|価格表示分類|`sale_banner_state: <class> <partner>`|`sale_banner_state: annual_discount_permanent mangools`|`none` / `annual_discount_permanent` / `time_limited_promo` / `unknown`のHuman分類を記録|
|Checkout再観測完了（必要時）|`checkout_values: done`|`checkout_values: done`|既存確定値を更新する再観測時だけ使用。Mangools初回値は2026-08-02に取込済み|
|記事入力完了|`article_input: done <P-ID>`|`article_input: done P11`|Operatorが出力したcontractの取込・再検証を依頼。P09は完了済み。P11は導入前後の完全暦月をtimerで計測→秒数をHuman確認してappend-only台帳へ追記→確認済み合計を自データ候補へ反映→一般入力欄確認→Human確定の順で使う|
|記事証拠不足|`article_evidence: pending <P-ID,...>`|`article_evidence: pending P11`|contractは構造合格だが確認済み実値がなく、記事承認・公開へ進めない状態を記録|
|P05公式field修正（完了）|`p05_field_scope: approve mangools_agency_actual_fields`|`p05_field_scope: approve mangools_agency_actual_fields`|2026-08-09にfield修正・記事承認、2026-08-11に限定release済み。再返信不要|
|記事承認|`article_approve: <P-IDまたはSVR-ID,...>`|`article_approve: P01,P02,P03`|列挙した記事本文だけをHuman承認。serversは価格・TCO・用途判定がREADYのSVR-IDだけ有効|
|記事修正|`article_revise: <P-ID> <修正点>`|`article_revise: P01 税区分を再確認`|対象記事をunreviewedへ戻す|
|Index判断|`index_go: GO / HOLD`|`index_go: HOLD`|承認済み記事だけのindex可否。CTAには効かない|
|Partner CTA|`cta_go: GO <partner> / HOLD <partner>`|`cta_go: GO mangools`|当該partnerの承認済みCTAだけを対象化|
|Impact feed有無|`impact_feed_check: <available\|unavailable\|unclear> <partner>`|`impact_feed_check: available HubSpot`|承認済みpartnerのcatalog表示有無だけを記録|
|Impact feed A1登録|`impact_feed_a1: GO <partner> / HOLD <partner>`|`impact_feed_a1: HOLD HubSpot`|全利用scopeを確認したexact feedだけsource policy候補へ登録。取得は開始しない|
|Mangools需要CSV|`mangools_csv: done / pending`|`mangools_csv: done`|凍結済みquery CSVのlocal検証を開始|
|Mangools一時upgrade（完了）|`mangools_upgrade: done Basic monthly`|`mangools_upgrade: done Basic monthly`|2026-08-09に正規DashboardでBasic有効化、2026-08-13までに残り180語のHuman export・検証、2026-08-14に自動更新OFFをread-back済み。2026-09-10までは利用可能で、追加Human操作なし|
|拡張需要CSVの残り180語|`mangools_category_csv: done crm,forms,email_marketing,seo_tools_v2_extension / pending`|`mangools_category_csv: done crm,forms,email_marketing,seo_tools_v2_extension`|CRM 40、forms 40、email marketing 40、SEO追加60をHuman export後に行単位validatorへ渡す。自動取得は行わない|
|Scope拡大準備|`scope_expand: GO (準備scope) / HOLD`|`scope_expand: GO (準備scope)`|2026-08-05受領済み。query・checklist・template準備だけで、公開・申請・照会は許可しない|
|優先カテゴリ|`category_primary: GO <category> / HOLD`|`category_primary: GO servers`|2026-08-06受領済み。serversのlocal記事・観測表・計算機準備だけを許可|
|日本ASP申請|`asp_signup: GO <ASP> / HOLD <ASP>`|`asp_signup: GO A8.net`|列挙したASPのHuman申請だけを開始|
|ASP account状態|`asp_account: <partner> <registration_incomplete / registered / under_review / approved>`|`asp_account: a8net registered`|機密値を含めずpartner台帳を更新|
|もしも本登録完了（確認済み）|`moshimo_email_verify: done / HOLD`|`moshimo_email_verify: done`|2026-08-07に管理画面へログイン済みであることをread-back済み。再返信不要|
|ASP個別提携状態|`asp_partnership: <partner> <not_applied / pending / approved / denied>`|`asp_partnership: a8net pending`|program名・カテゴリ・公開可能な条件を別途確認して更新|
|ASP個別program申請|`asp_program_apply: GO <ASP> <program名> / HOLD <ASP> <program名>`|`asp_program_apply: GO A8.net formrun`|対象program一件だけの提携申請を許可。CTA・広告link取得は別GO|
|ASP再認証|`asp_reauth: done <ASP>`|`asp_reauth: done もしも`|保存済みcredentialのOS認証をHumanが完了し、対象ASPの正規管理画面へ戻ったことだけを通知。passwordは返信しない|
|ASP個別program規約同意|`asp_program_terms_accept: GO <ASP> <program名> / HOLD`|`asp_program_terms_accept: GO もしも シンレンタルサーバー`|対象programの最新条件を画面で確認した直後に、法的同意を伴う最終申請button一回だけを許可。CTA・広告link取得は別GO|
|A8再認証完了（確認済み）|`a8_reauth: done`|`a8_reauth: done`|2026-08-07にSaaS TCO Lab選択済みのprogram詳細をread-back済み。再返信不要|
|もしも再認証・結果確認（完了）|`moshimo_reauth: done`|`moshimo_reauth: done`|2026-08-09にメディア登録とロリポップ提携承認をread-back済み。再返信不要|
|もしもメディア適法性確認（完了）|`moshimo_media_attestation: done`|`moshimo_media_attestation: done`|2026-08-09にHuman本人が確認済み。saastcolab.jpのメディア登録へ反映済み|
|バリューコマース本登録完了|`valuecommerce_registration: done`|`valuecommerce_registration: done`|本登録案内メールの期限内URLからHumanが手続きを完了した後、ABLENET候補の個別条件をread-onlyで再確認|
|servers候補入力|`server_price_input: done <SVR-ID>`|`server_price_input: done SVR01`|`/operator/servers/`の候補値をHumanが確認し、確定ボタンを押して保存したcandidate-only JSONをlocal検証。公開・CTAには効かない|
|SVR01公式画面候補の確認|`svr01_candidates: confirm_all` または `svr01_candidates: corrections <field>: <value>`|`svr01_candidates: confirm_all`|`/operator/servers/`の「公式画面の確認候補」9件をHuman本人が読み、すべて正しければ一括確認、相違があればfield単位で訂正する。確認前はcontract・TCO・順位・記事・CTAへ採用しない|
|servers記事承認|`article_approve: <SVR-ID>`|`article_approve: SVR01`|当該本文が扱うmaterial claimとHuman確認がREADYの場合だけ承認。SVR01は2026-08-14に承認・公開済み。index・CTAには自動では効かない|
|servers destination設定完了|`server_destination_configured: done <partner-id,...>`|`server_destination_configured: done a8net-xserver-business`|ASP正規画面で取得した広告linkをruntime secretへ設定した事実だけを通知。URL・tracking ID・secret値は返信・repo保存しない|
|servers記事index|`index_go: GO <SVR-ID> / HOLD <SVR-ID>`|`index_go: GO SVR01`|Human承認済みの列挙記事だけをindex対象へ加える。CTAには効かない|
|servers partner CTA|`server_cta_go: GO <SVR-ID> partners=<partner-id,...> / HOLD <SVR-ID>`|`server_cta_go: GO SVR01 partners=a8net-xserver-business`|記事承認・index・現行提携・runtime destination・開示先行が全て成立した列挙partnerだけを有効化。未列挙partnerと未承認記事は無効|
|localhost候補JSON download許可|`local_download_permission: GO localhost <SVR-ID> / HOLD`|`local_download_permission: GO localhost SVR01`|Safariの一回のlocalhost download許可だけを承認。外部送信・公開・CTA・ASP申請には効かない|
|P01 note修正|`note_edit_go: GO P01 PR先頭追記 / HOLD`|`note_edit_go: GO P01 PR先頭追記`|既存noteの先頭へlocal templateのPR表示だけを追記する外部編集を許可|
|SaaS専用X（完了記録）|`account_repurpose: GO <旧handle> retire_fanza`|`account_repurpose: GO @fanza_poll_lab retire_fanza`|2026-08-06受領・完了済み。再実行しない|
|P01 X初回投稿|`x_post: GO P01 / HOLD P01`|`x_post: HOLD P01`|冒頭PR表示、P01の読者向け本文、saastcolab.jpのP01 URLだけを投稿対象にする。ASP広告linkは含めない|
|Release用push|`repository_update_push: GO / HOLD`|`repository_update_push: HOLD`|提示済みrelease対象だけをcommit・pushする。診断履歴、output、credentialは除外|
|承認済み記事のproduction release|`deploy_update: GO <P-ID,...> / HOLD`|`deploy_update: GO P04,P08,P10`|列挙した承認済み記事だけをproduction候補へ進める。index・partner CTAの対象追加は別のexact GO|
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
