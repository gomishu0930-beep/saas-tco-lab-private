# Human Action Queue V2

14日スプリント上限1,200分。GSC 20 URL InspectionはCodexがread-onlyで完了したため、残作業は655分、修正・再確認reserve 545分を残す。

|Priority|対象|必要な判断 / なぜ|画面と確認項目|入力先|分|GO時|HOLD時|期限|
|---:|---|---|---|---|---:|---|---|---|
|1|Cell A primary / alternative|既存Human選定をV2 evidence matrixへ再確認|A8/もしもprogram詳細、公式価格、用途fit、destination連続性|2026-08-20 all-GOで再確認済み|0|1 primary + 1 alternativeをrelease|不整合時はruntimeでfail-closed|done|
|2|Cell B article / vendor|SVR04暫定候補と単独vendorを確定|GSCページ別表示、SVR04本文、program/価格/用途|`cell_b: GO SVR04 <vendor-id>`|25|source-level article CTA GO準備|affiliate slot無効・SVR01内部CTAのみ|2026-08-24|
|3|成果・否認条件|confirmed照合の条件を確定|A8/もしもprogram詳細の成果条件・除外条件|merchant matrix intake|45|matrix knownへ更新|unknown維持、CTA拡張なし|2026-08-24|
|4|確認期間|matured eligible sessionを定義|各ASPの確定目安・再訪問・承認期間|merchant matrix intake|30|RPES maturity開始|RPES null維持|2026-08-24|
|5|channel / deep link|note・X・partner配信とsub ID可否|各programの掲載可能媒体、SNS、deep link、sub ID仕様|`channel_terms: GO/HOLD <network>`|45|許可channelだけcampaign運用|draftのみ・tracking拡張なし|投稿前|
|6|price / tax / renewal / cancellation|期限・主要条件の鮮度を維持|4社公式料金/checkout/規約画面|Operator / merchant matrix|180|該当fieldをapproved更新|unknown・順位/推奨除外|ConoHa 2026-08-24、他は次回確認日|
|7|GA4 internal filter|実訪問と内部testの分離|管理→データストリーム→タグ設定→内部トラフィック定義で現IP、次にデータフィルタとDebugView|`ga4_internal_ip_transmit: GO`（現在IPをGoogleへ送る直前確認）|45|rule作成→別回線検証→filter active|test維持、KPIを収益証拠にしない|2026-08-21|
|8|GSC 20 URL Inspection|20 URLの個別内訳を確定|2026-08-21にread-only検査完了。SVR03〜09で後段noindexを検出|Index audit表|0|重複robots修正後にSVR04だけlive再検査|全URL一括登録要求はしない|done|
|9|homepage / hub index|editorial価値と重複を審査|本番home、`/pilot`、GSC canonical|`hub_index: GO HOME,SEO_TOOLS`受領済み|0|source + runtime二重gateでindex候補|gate欠落時はnoindex,follow|done（deployed）|
|10|note / X / partner投稿|外部送信と表現を承認|distribution draft・各channel公開画面|all-GO受領済み、ただしchannel規約は未確認|180|規約確認済みcampaignだけ投稿確認へ進む|規約unknownならDRAFT_ONLY維持|規約確認後|
|11|mobile / accessibility read-back|CTA・開示・tableの重大退行を確認|390px描画、開示/CTA DOM順、active数、rel、JS error|自動read-back完了|0|Sites v38へdeploy済み|再発時rollback|done|

## 現在のtoken状態

```text
ga4_internal_filter: TEST / definition rules 0
hub_index: GO HOME,SEO_TOOLS (deployed / sitemap included)
external_posts: GO pending_channel_terms_and_action_time_confirmation
cell_b: HOLD vendor_selection
```

all-GOは実行権限として記録した。merchant固有値、channel規約、Cell B vendorは情報がないため推測で確定しない。
