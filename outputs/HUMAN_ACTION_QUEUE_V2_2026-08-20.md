# Human Action Queue V2

14日スプリント上限1,200分。下表は855分、修正・再確認reserve 345分を残す。

|Priority|対象|必要な判断 / なぜ|画面と確認項目|入力先|分|GO時|HOLD時|期限|
|---:|---|---|---|---|---:|---|---|---|
|1|Cell A primary / alternative|既存Human選定をV2 evidence matrixへ再確認|A8/もしもprogram詳細、公式価格、用途fit、destination連続性|`cell_a_merchants: GO primary=xserver-business alternative=conoha-wing`|15|2 CTA release候補|本番6 CTAを維持しV2 deploy HOLD|2026-08-22|
|2|Cell B article / vendor|SVR04暫定候補と単独vendorを確定|GSCページ別表示、SVR04本文、program/価格/用途|`cell_b: GO SVR04 <vendor-id>`|25|source-level article CTA GO準備|affiliate slot無効・SVR01内部CTAのみ|2026-08-24|
|3|成果・否認条件|confirmed照合の条件を確定|A8/もしもprogram詳細の成果条件・除外条件|merchant matrix intake|45|matrix knownへ更新|unknown維持、CTA拡張なし|2026-08-24|
|4|確認期間|matured eligible sessionを定義|各ASPの確定目安・再訪問・承認期間|merchant matrix intake|30|RPES maturity開始|RPES null維持|2026-08-24|
|5|channel / deep link|note・X・partner配信とsub ID可否|各programの掲載可能媒体、SNS、deep link、sub ID仕様|`channel_terms: GO/HOLD <network>`|45|許可channelだけcampaign運用|draftのみ・tracking拡張なし|投稿前|
|6|price / tax / renewal / cancellation|期限・主要条件の鮮度を維持|4社公式料金/checkout/規約画面|Operator / merchant matrix|180|該当fieldをapproved更新|unknown・順位/推奨除外|ConoHa 2026-08-24、他は次回確認日|
|7|GA4 internal filter|実訪問と内部testの分離|管理→データフィルタ、DebugView、別回線read-back|`ga4_internal_filter: GO active / HOLD`|45|明示GO後だけactive|testのまま、KPIを収益証拠にしない|V2 deploy後24h|
|8|GSC 20 URL Inspection|aggregate 7/6の個別内訳を確定|URL検査の状態・理由・canonical・最終crawl・impression有無|Index audit表|200|page別next action|unknown維持、登録数を推測しない|2026-08-27|
|9|homepage / hub index|editorial価値と重複を審査|本番home、`/pilot`、GSC canonical|`hub_index: GO <routes> / HOLD`|45|別releaseでnoindex解除候補|noindex,follow維持|2026-08-29|
|10|note / X / partner投稿|外部送信と表現を承認|distribution draft・各channel公開画面|`external_posts: GO <campaign-ids>`|180|指定campaignのみHuman投稿|DRAFT_ONLY維持|規約確認後|
|11|mobile / accessibility read-back|CTA・開示・tableの重大退行を確認|iPhone幅、keyboard、VoiceOver見出し/CTA順|`revenue_cells_ui: GO / HOLD`|45|deploy候補|修正後再確認|deploy前|

## 現在のtoken状態

```text
ga4_internal_filter: HOLD
hub_index: HOLD
external_posts: DRAFT_ONLY
cell_b: HOLD vendor_selection
```

推測でGOへ変えない。
