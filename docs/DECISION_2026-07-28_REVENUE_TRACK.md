# Decision record — 収益実現トラック最優先

- decision ID: `DR-2026-07-28-REVENUE-TRACK`
- decided at: 2026-07-28（Asia/Tokyo）
- Human Approver: `omishu`
- status: `approved`
- supersedes: field-level書面許諾を編集記事経路の一律launch blockerとする運用、およびP19以降の拡張計画

## 決定

1. **ガバナンス凍結**: P0–P18はmaintenance onlyとする。P19以降の新phase、新署名層、新acceptance文書を追加しない。月720分のHuman予算はlaunch trackへ配分する。
2. **rights model v2**:
   - `automated_data_path`: 自動取得、価格DB保存、履歴DB化、canonical計算への採用は従来のstrict gateを維持する。Semrushから禁止回答済みのautomated fetch、ongoing storage、historyを行わない。
   - `human_editorial_path`: Humanが公開価格を確認し、入力値、出典URL、観測日、次回確認日を揃えた編集記事への記載を承認する。field-level書面許諾はこの経路のlaunch blockerにしない。raw archive、価格DB、履歴DB、自動取得を兼ねない。
3. **launch track**: `domain取得（別GO）→ P01–P12実記事化 → noindex解除（別GO）→ 承認済みpartner CTA（別GO）`の順で進める。
4. **KPI簡素化**: 月次の正本は、公開記事数、インデックス数、GSC clicks、outbound clicks、confirmed commissionsの5つとする。P17の複雑な判定はconfirmed 1,000 outbound clicks到達後に再開する。

## 2026-07-30追加決定 — Launch Quarter 2026-08〜10

Human Approver `omishu`の最終指示により、次を同じdecision IDの実行計画として追加する。

5. **Human予算**: 2026-08-01〜2026-10-31はlaunch trackに限り月2,000分へ引き上げる。automated data pathのhard gateを緩和せず、2026-11に720分へ戻すか再判定する。
6. **確率向上レバー**: 単価（Impact完遂・日本ASP追加）、需要（W6実測・不足時のカテゴリ拡張準備）、チャネル分散（TCO embed・note/X・構造化data）、取引意図記事への集中を採用する。
7. **90日固定判定**: 2026-10-31にindex数、GSC impressions、GSC clicksと直前28日比で継続・拡張・縮小を判定する。閾値は実測前に`docs/PRODUCTION_ROADMAP.md`へ固定し、判定後に変更しない。

実装queueはQ1〜Q9とする。Q1はF1–F3とE1–E10の既存完成確認、Q2は取引意図優先、Q3はembed、
Q4はProduct/FAQ/Breadcrumb JSON-LD、Q5はnote/X template、Q6は日本ASP申請準備、Q7はカテゴリ拡張準備、
Q8は90日閾値固定、Q9はdashboard更新である。外部申請、domain、index、CTA、投稿は従来どおり別のHuman操作・GOを必要とする。

### 2026-07-29 Operator contract clarification

- vendor値はvendor・plan識別子ごとの複数行として保持する。同じfield名でも識別子が異なれば別観測である。
- P01のseat数・月間利用量はHumanシナリオであり、公式料金から補完せずvendor行から分離する。
- 通貨記号だけが表示される場合はISO通貨を断定せず、画面表記と不明理由を保持する。明示的unknownは証拠contractへ記録できるが、TCO計算・記事承認を許可しない。

## 変更しない境界

- credential、PII、tracking ID、非公開報酬はrepositoryへ保存しない。
- 外部送信、account作成、課金、domain購入、deploy、indexing、CTA有効化は個別のHuman GOが必要である。
- 価格、税、通貨、課金周期、seat、quota、overage、addonを推測しない。unknownはunknownのまま表示または停止する。
- ベンダー照会と30/90/180日追跡は継続する。ただしhuman editorial pathの公開を止めない。

## 実装queueとauthority

|Work|local実装|外部実行authority|
|---|---|---|
|W1 decision・roadmap・action更新|本decisionで承認|不要|
|W2 P01–P12実記事template・Human入力schema・PR表示|本decisionで承認|実値入力と記事承認はHuman review|
|W3 TS TCO計算機・Python golden一致|本decisionで承認|公開は`index_go`とは別のrelease review|
|W4 審査用5 route|本decisionで承認|deployは別GO|
|W5 domain移行checklist|本decisionで承認|`domain: GO <domain>`|
|W6 Mangools Human CSV validator|本decisionで承認|CSV exportはHuman、外部送信なし|
|W7 index/CTA/disclosure release gate|本decisionで承認|`index_go: GO`、partner CTAは別GO|

## 返信token

```text
domain: GO <domain> / HOLD
index_go: GO / HOLD
mangools_csv: done / pending
scope_expand: GO / HOLD
human_budget: GO 2000min/month
```

`human_budget: GO 2000min/month`は本指示で発効済みである。その他のtokenは記録時点で`HOLD`または`pending`である。
