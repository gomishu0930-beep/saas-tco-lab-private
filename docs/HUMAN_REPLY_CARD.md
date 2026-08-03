# Human返信カード

返信はこの文書から一行をコピーし、`<>`だけを置き換える。credential、verification値、property ID、
measurement ID、partner ID、tracking ID、支払情報、メール本文は追記しない。GOは書かれたscopeだけに有効で、
domain GOからindex GOやCTA GOを推論しない。

現在地: P01–P03は2026-08-03承認済み。次のrelease tokenは`index_go: GO / HOLD`であり、
CTAは引き続き別tokenである。

## 今使うtoken

|目的|返信token|記入例|意味|
|---|---|---|---|
|Domain開始|`domain: GO <domain> / HOLD`|`domain: GO example.jp`|exact domainのdomain dayだけを開始|
|価格表示分類|`sale_banner_state: <class> <partner>`|`sale_banner_state: annual_discount_permanent mangools`|`none` / `annual_discount_permanent` / `time_limited_promo` / `unknown`のHuman分類を記録|
|Checkout再観測完了（必要時）|`checkout_values: done`|`checkout_values: done`|既存確定値を更新する再観測時だけ使用。Mangools初回値は2026-08-02に取込済み|
|記事入力完了|`article_input: done <P-ID>`|`article_input: done P01`|Operatorが出力したcontractの取込・再検証を依頼|
|記事承認|`article_approve: <P-ID,...>`|`article_approve: P01,P02,P03`|列挙した記事本文だけをHuman承認|
|記事修正|`article_revise: <P-ID> <修正点>`|`article_revise: P01 税区分を再確認`|対象記事をunreviewedへ戻す|
|Index判断|`index_go: GO / HOLD`|`index_go: HOLD`|承認済み記事だけのindex可否。CTAには効かない|
|Partner CTA|`cta_go: GO <partner> / HOLD <partner>`|`cta_go: GO mangools`|当該partnerの承認済みCTAだけを対象化|
|Impact feed有無|`impact_feed_check: <available\|unavailable\|unclear> <partner>`|`impact_feed_check: available HubSpot`|承認済みpartnerのcatalog表示有無だけを記録|
|Impact feed A1登録|`impact_feed_a1: GO <partner> / HOLD <partner>`|`impact_feed_a1: HOLD HubSpot`|全利用scopeを確認したexact feedだけsource policy候補へ登録。取得は開始しない|
|Mangools需要CSV|`mangools_csv: done / pending`|`mangools_csv: done`|凍結済みquery CSVのlocal検証を開始|
|Scope拡大|`scope_expand: GO / HOLD`|`scope_expand: HOLD`|需要不足時の対象拡大判断|
|日本ASP申請|`asp_signup: GO <ASP> / HOLD <ASP>`|`asp_signup: GO A8.net`|列挙したASPのHuman申請だけを開始|
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
