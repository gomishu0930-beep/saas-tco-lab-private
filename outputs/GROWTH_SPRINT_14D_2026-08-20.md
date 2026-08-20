# Balanced 14-day growth sprint

基準日: 2026-08-20（Asia/Tokyo）
Human Approver: omishu
目的: 新規記事を増やさず、SVR01を中心に「閲覧 → 比較結果 → CTA表示 → outbound」の最初の実測を得る。

## 受領済みscope

```text
growth_sprint: GO balanced_14d
svr01_cta_experiment: GO primary_1 alternative_1
server_internal_funnel: GO SVR02-SVR09 -> SVR01
repository_scope_prepare: GO
ga4_internal_filter: HOLD
hub_index: HOLD
external_posts: DRAFT_ONLY
```

このGOはlocal code、tests、docs、投稿下書きの準備だけを許可する。push、deploy、投稿、GA4 filter変更、
ホーム／カテゴリーハブのindex化、SVR02–SVR09のaffiliate CTA有効化は許可しない。

## 実験設計

- 対象ページ: SVR01 `/servers/business-server-pricing`
- primary枠: 既存SVR01で記事対象として先頭表示されていたXServerビジネス。
- alternative枠: 既存のHuman確認・runtime順で最初の別候補だったConoHa WING。
- 表示上限: primary 1、alternative 1。残る承認programは台帳とruntime gateを維持するが、SVR01には表示しない。
- 推奨の意味: 価格だけで「最安」「おすすめ」と判定しない。記事対象と既存Human確認順を保った表示実験である。
- SVR02–SVR09: affiliate CTAは無効のまま、記事意図に合わせたSVR01への内部リンクを1本だけ表示する。

## 計測

analytics consentがgrantedの場合だけ、既存の`page_view`、`qualified_session`、`outbound_click`に加えて、
次のsafe event候補を送る。query、tracking ID、Affiliate URL、PIIは送らない。

|event|発火条件|safe parameter|
|---|---|---|
|`calculator_result_view`|server計算結果が25%以上表示された最初の1回|`content_path`, `calculator_kind`|
|`cta_view`|有効なaffiliate CTAが25%以上表示された最初の1回|`content_path`, `cta_position`, `cta_kind`|
|`cta_eligible_session`|同一session・pathで最初の`cta_view`|`content_path`, `eligibility_rule`|
|`server_internal_funnel`|SVR02–SVR09からSVR01への内部リンクclick|`content_path`, `destination_path`|

GA4 internal traffic filterは`HOLD`を維持する。内部／外部を分離できない集計を収益証拠として扱わない。

## 14日キュー

|順|作業|owner|Human分目安|完了条件|
|---:|---|---|---:|---|
|1|未commit差分をscope別に監査|Codex|30|今回scopeと既存差分を混同しない一覧がある|
|2|SVR01を1 primary＋1 alternativeへ限定|Codex + Human read-back|30|残る4 programが表示されず、開示先行とfail-closedが通る|
|3|SVR02–SVR09をSVR01へ接続|Codex + Human標本|40|8記事それぞれに意図別内部リンクが1本ある|
|4|収益eventのlocal／production境界test|Codex|30|consent前送信なし、event名とsafe parameterが固定される|
|5|20 URLのindex理由を分類|Human画面確認 + Codex整理|150|全URLに状態、理由、最終crawl、次回確認日がある|
|6|note 1本・X 6投稿を下書き|Codex + Human公開判断|45|PR先行、誇張なし、投稿は未送信|
|7|外部送客後に14日判定|Human + Codex|60|clean eligible sessions、outbound、commissionを欠測込みで判定|

## 14日判定

- `30以上のclean CTA-eligible sessions`かつ`outbound 3件以上`: 次の3記事のarticle別CTA候補を精査する。
- `30以上のclean CTA-eligible sessions`かつ`outbound 0件`: 新規記事を増やさず、SVR01のoffer・文言・意図を再設計する。
- 30件未満: CTRを断定せず、配信経路かindexのどちらが不足したかを分類する。
- いずれも統計的な因果証明ではなく、Human時間の次配分を決める運用gateとする。

## 継続HOLD

- 新規記事の量産
- SVR02–SVR09のaffiliate CTA
- GA4 internal traffic filterの`active`化
- ホーム／カテゴリーハブのindex化
- note／Xの実投稿
- embed配布、別カテゴリ公開、新vendor照会
- push、deploy、本番設定変更
