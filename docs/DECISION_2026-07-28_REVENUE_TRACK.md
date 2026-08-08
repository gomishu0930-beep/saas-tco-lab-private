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
8. **拡張準備scopeの前倒し**: 2026-08-05のW6はknown 9,610/月、no_data率0.77333333で、必要22,227 sessions/月に対するknown下限が43.24%だった。Human Approver `omishu`は現ニッチ追加queryと5カテゴリquery・ASP確認表・TCO/article templateのlocal準備だけをGOとした。公開、申請、新vendor照会、価格観測、CTAは別GOを維持する。

## 2026-08-06追加決定 — servers政策v2

Human Approver `omishu`はserversの失敗経路を先に潰すため、次を同じlaunch trackへ追加した。

9. **ロングテール先行**: 凍結40語から具体性と購入直前性をproxyに20語を選び、第1弾候補とする。
   query別競合性は未観測のため「競合が薄い」とは断定しない。ビッグワードは内部link hub候補へ延期する。
10. **計算機first**: servers記事は`開示 → 計算機 → 結果 → CTA枠 → 根拠表`の順とする。
    開示先行、Human確認値、unknownのfail-closed、記事承認を省略しない。
11. **partner冗長化**: serversの有効partnerが0社ならCTA無効、1社なら単独CTA、2社以上なら比較CTAとする。
    1社だけの場合は構造上100%依存として80%超警告をdashboardへ表示する。2社以上で実測shareがない場合は
    依存率を推測しない。各partnerの承認・規約・destination・`cta_go`は個別gateのまま維持する。
12. **60分workflow**: 価格確認20分、Operator入力20分、表示・根拠確認20分を標準とする。
    「80点公開」は装飾改善を後日に回す意味だけを持ち、数値・出典・開示・承認hard gateを緩和しない。
13. **固定撤退ライン**: 2026-12-31に公開20本、GSC clicks 300/月、confirmed 1件をすべて要求する。
    閾値は事後に緩めない。未達時はembed配布、note有料、受託を転換候補としてHuman判断へ送る。

実装queueはQ1〜Q9とする。Q1はF1–F3とE1–E10の既存完成確認、Q2は取引意図優先、Q3はembed、
Q4はProduct/FAQ/Breadcrumb JSON-LD、Q5はnote/X template、Q6は日本ASP申請準備、Q7はカテゴリ拡張準備、
Q8は90日閾値固定、Q9はdashboard更新である。外部申請、domain、index、CTA、投稿は従来どおり別のHuman操作・GOを必要とする。

### 2026-07-29 Operator contract clarification

- vendor値はvendor・plan識別子ごとの複数行として保持する。同じfield名でも識別子が異なれば別観測である。
- P01のseat数・月間利用量はHumanシナリオであり、公式料金から補完せずvendor行から分離する。
- 通貨記号だけが表示される場合はISO通貨を断定せず、画面表記と不明理由を保持する。明示的unknownは証拠contractへ記録できるが、TCO計算・記事承認を許可しない。

## 2026-08-02追加決定 — Launch最終シーケンス

Human Approver `omishu`の指示により、launch trackの現在地と次の処理順をイベント駆動で固定する。
新しい方針判断はイベント発生時だけ照会し、完了済みstepを再実行しない。

- `saastcolab.jp`は購入、DNS保存・解決、個別自動更新ON、SitesのSSL Active read-back、
  GSC domain propertyのDNS TXT検証、GA4 streamの新origin更新、旧originからの301 read-backまで完了した。
  2026-08-03時点のS1次工程はImpact website再認証である。
- 観測contract v2.3を適用する。価格表示分類は`none`、`annual_discount_permanent`、
  `time_limited_promo`、`unknown`の4値とし、計算HOLDは後二者だけとする。2026-08-02のHuman exact値指示で
  Mangoolsの年次price 5 observationを確定し、P01–P03のTCO節を再生成した。他vendorのunknownは維持する。
- indexとCTAは個別Human GOまでHOLDする。2026-08-03にP01–P03のindex GOとMangools CTA GOを受領した。

|Event|Trigger|処理|現在状態|
|---|---|---|---|
|S0|本指示|年次checkout総額が12で最小通貨単位まで割り切れない場合、一次値を保持し月額派生値だけを非表示にする。丸め値を作らない|done|
|S1|SSL Active read-back|外部read-back、GSC domain property、GA4新origin、旧origin 301、Impact再認証を順番に実施し記録|done — 2026-08-03|
|S2|Mangools exact checkout値と再生成指示|contract確定、P01–P03価格・TCO節再生成、記事承認待ちを返す|done (Mangools scope)|
|S3|`article_approve: P01,P02,P03`|承認記録と公開候補登録|done (2026-08-03)|
|S4|`index_go: GO`|承認記事だけnoindex解除、robots／sitemap更新、GSC送信と外部read-back|done — P01–P03、2026-08-03|
|S5|`cta_go: GO mangools`|開示先行test後、Mangools CTAだけを有効化|done — P01–P03、2026-08-03|
|S6|公開24時間後|index、GA4、Impactを1回read-backしdashboardへ反映|waiting — 24時間後の自動read-back|

`annual_discount_permanent`は、終了日・カウントダウン・クーポン・取消線priceのない恒常的な年払い・
月払い差としてHumanが分類する。同一通貨・同一税条件の月払い価格と年次checkout総額がともに
Human確認済みである場合だけ、`1 - annual_total / (monthly_price * 12)`から「年払いは月払い比で約N%割安」
という事実記載を許可する。Mangoolsの旧`present`候補は分類を推測せず`unknown`へ移行し、Humanの4値分類を待つ。

2026-08-02、Human Approver `omishu`から
`sale_banner_state: annual_discount_permanent mangools`を受領した。P01–P03のMangools vendor fieldは
`annual_discount_permanent`へ昇格する。年次checkout総額、通貨・税、価格値、記事承認、index、CTAの
承認を価格表示分類tokenだけから推論しない。後続のHuman exact値指示で、同一plan・通貨・税条件の
月払い値と年次checkout総額をcontractへ確定し、記事承認待ちへ進めた。

同日の画面分類根拠は、終了日、カウントダウン、クーポン、取消線priceがいずれもないという
Human確認である。月払い61.00／81.00／141.00 USDの12か月分と年次checkout総額
452.40／632.40／1,172.40 USDの差が、約38%／35%／31%の恒常年払い差と整合することを
Python正本とTypeScriptの固定式で再検証する。

2026-08-03、Human Approver `omishu`から`article_approve: P01,P02,P03`を受領した。承認scopeは
2026-08-02観測contractに基づく各記事の6章本文とTCO節である。contract内のknown／unknown、出典、
観測日、次回確認日を含む表示境界を承認し、P01–P03を公開候補へ登録する。P03の未観測価格・移行費用を
既知へ変更せず、該当する横断順位は引き続きSTOPする。index、CTA、deploy、push、公開は承認scope外であり、
`index_go`受領までnoindexを維持する。その後の2026-08-03 `index_go: GO`はP01–P03だけ、
`cta_go: GO mangools`は同3記事のMangoolsだけをscopeとし、他記事・他partnerへ拡張しない。

2026-08-08、Human Approver `omishu`は最優先残タスクについて承認系を一括GOとした。既に本文と
contractが承認済みのP06/P07に限り、deploy、index追加、既存の承認済みMangools CTAを同じrelease境界へ
拡張する。P04・P05・P08–P12、servers記事、Mangools以外のCTAには拡張しない。公開反映は
`CHECK-ALL: PASS`と外部read-backを必要とする。

2026-08-09、Human Approverは「最優先タスクをすべて行い、承認系は承認扱い」とする実行指示を追加した。
これを既に本文・contract承認済みで8記事release回帰testに合格したP04/P08/P10へ限定適用し、deploy、
index追加、既存Mangools CTAを同じrelease境界へ拡張した。P05/P09/P11/P12、servers記事、Mangools以外の
CTAには拡張しない。同じ指示に基づき、`saastcolab.jp`のSearch Console domain propertyと専用GA4 streamを
連携した。PII・stream ID・verification値を保存せず、internal traffic filterと同意境界は変更しない。

同日の継続実行では、P12の確認間隔fieldを「全field共通の単一間隔を適用せず、観測ごとの次回確認日を
管理する」という既存運用方針に基づく`not_applicable`として承認した。数値は補完せず、本文修正、index追加、
既存Mangools CTAを9記事release境界へ拡張した。P05/P09/P11はnoindex・CTA無効を維持する。

2026-08-06、Human Approver `omishu`から改稿版について
`article_approve: P01,P02,P03`を再受領した。承認scopeはR1–R6の読者向け本文、
contract駆動SEO／OGメタ、関連記事、計算機prefill、人間可読JSON-LDである。
新しい価格、税、通貨、課金周期の追加はなく、known／unknownと証拠表の境界を維持する。
この再承認はlocal公開候補への登録までを対象とし、commit、push、deployの承認を含まない。

S1のSSL、DNS、GSC、GA4、Impact操作は画面別手順書を提示し、Humanが実行する。旧`chatgpt.site`
originはImpactがVerifiedになるまで存続させ、その後も301を維持する。

残りのHuman tokenは`mangools_csv: done`である。S6は公開24時間後にread-onlyで自動実行する。

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
