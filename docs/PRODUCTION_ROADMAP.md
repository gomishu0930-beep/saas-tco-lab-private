# SaaS比較Affiliate 完成ロードマップ

基準日: 2026-07-28

> 2026-07-28のHuman decisions `DR-2026-07-28-REVENUE-TRACK`と
> `Human指示 2026-07-28(2)`と`Human指示 2026-07-30(最終)`を優先する。P0–P18はmaintenance only、P19以降の拡張は凍結し、
> 以下の完成定義とGate Aにはrights model v2を適用する。

## 完成の定義

本件のlaunch完成は、次の6条件を同時に満たす状態とする。

1. P01–P12が実記事templateへ変換され、vendor値にはvendor・plan識別子、Human入力値または明示的unknown、出典URL、観測日、次回確認日がある。Humanシナリオ値はvendor値と分離し、入力根拠と日付を持つ。unknownを推測しない。
2. 全記事の冒頭に広告・アフィリエイトのPR表示があり、CTAより先に表示される。
3. 12か月TCOはcanonical Python実装とgolden一致するTypeScript計算機から生成され、重大誤表示が0件である。
4. 運営者情報、About、プライバシーポリシー、お問い合わせ、広告掲載ポリシーがnoindexで確認できる。
5. index対象はHuman承認済み記事だけ、CTA対象はAffiliate承認済みpartnerだけであり、domain・index・CTAの各GOを分離する。
6. 月次に公開記事数、インデックス数、GSC clicks、outbound clicks、confirmed commissionsの5指標を取得できる。

月20万円は目標式として維持する。EPC 60円なら月3,334 confirmed outbound clicks、送客CTR
15%なら約22,227 sessionsが必要である。confirmed 1,000 outbound clicksまではこの単純式と5 KPIだけを使い、P17の複雑なscale判定を再開しない。

## 全体経路

|Phase|目的|主owner|自動化できる部分|Human専有部分|出口|
|---:|---|---|---|---|---|
|0|規律・正本・供給網|Integration|schema、lock、test、scan|承認境界|完了|
|1|local決定論コア|Contract/TCO|validation、TCO、append-only保存|権利承認|完了|
|2|Preflight制御面|全role|release、TTL、CTA、例外、EPC、dry run|候補選択|実装・fixture合格|
|3|rights・Affiliate・需要／30日実証|Evidence/Human|lane別gate検査、集計、故障注入|許諾照会、Affiliate申請、需要入力|A2/B/Cはeditorial、A1/Dはautomated|
|4|許諾済みadapter/gold set（automated data path）|Evidence/Contract|approved fetch、parser、差分、quarantine|曖昧値確定|3社×6プラン|
|5|noindex公開前MVP|Integration/TCO|preview、release、rollback、security test|Human実値・表示・記事承認|editorial L2またはautomated公開前GO|
|6|production launch|Integration/Human|公開境界、監視、serve-time制御|domain、index、CTA、deployの個別GO|lane別に公開・監視稼働|
|7|最大180日Traction|Economics/Human|KPI/cohort集計、STOP判定|施策・投資判断|拡大または撤退|
|8|月20万円scale|全role|例外だけ人手、月次release|新広告主・費用判断|持続条件維持|

## 現在地と完走キュー

この節は二車線で管理する。C1–C7は自動取得・価格DB・履歴DBを扱う
**automated data path専用**であり、editorial launch laneの入口条件ではない。C0は既存local実装の
maintenance基準にすぎず、どちらのlaneにも公開権限を与えない。

### Automated data path — C1–C7

|順序|現在状態|機械的入口|実装・自動処理|Human／外部入力|出口|
|---:|---|---|---|---|---|
|C0|local技術候補完成／business STOP|静止したP21 scope|741 Python lane assertion、197 schema、STOP fixture、Web・供給網・秘密検査|独立監査|P21 local closure|
|C1|`STOP`|3社分のfield-level rights、対象partnerのAffiliate acceptance、JP/ja需要export|P5/P8/P12契約で検査・quarantine|照会・申請・export承認|Gate A1・B・C合格|
|C2|待機|C1合格sourceのみ|source別adapter、3社×6プランgold set、30日shadow|曖昧値label、運用例外判断|Gate D・P8合格|
|C3|待機|P15統合証拠とP16 handoff|noindex deploy候補、readback、rollback drill|domain/cloud/KMS/clock/anchor/provider承認|公開前Human review|
|C4|待機|P18受理と最終Human署名|限定公開、監視、serve-time expiry、kill switch|公開・広告・privacy承認|public MVP稼働|
|C5|待機|実P12 producerと公開MVP|連続30日cohort・operations・settlement集計|返金・欠測・例外review|automation 80%等を実測|
|C6|待機|成熟1,000 clicksまたは最大180日|P17がEPC・純利益・capacityを厳密判定|継続／撤退判断|scale reviewまたはSTOP|
|C7|待機|`READY_FOR_SCALE_REVIEW`とHuman承認|月次release、異常時自動STOP|費用・新partner判断|月20万円純利益を持続確認|

C0の合格はC1以降の実績を生成しない。automated data pathの現在の直接値はfield-level rights 0/3、
実観測0であり、automated fetch・価格DB・履歴DB・その成果物の公開はすべて`STOP`である。

### Editorial launch lane — L1–L4

このlaneはHumanが公開価格を確認するrights model v2のeditorial pathだけを扱う。P15/P16/P18受理、
Gate D、3社×6プランgold set、C1–C7の合格を入口条件にしない。

|順序|現在状態|入口／GO|実装・Human処理|出口|
|---:|---|---|---|---|
|L1|完了 — 2026-08-03|2026-08-02 `domain: GO saastcolab.jp`受領。`saastcolab.jp`登録完了、Sites指定DNS保存・個別自動更新ON、2026-08-03 HTTPS read-back・GSC所有確認・GA4新origin更新・旧originの1段301・Impact Connected確認済み|完了状態を維持し、index／CTAを別GOまでHOLD|domain切替とreadback合格|
|L2|12/12入力・10/12承認・10/12公開|L1完了|P09/P11の自データを取得して承認する。P01–P08・P10・P12は公開済み|12記事の公開候補が承認済み|
|L3|10記事完了 — 2026-08-11|`index_go: GO`と対象記事の承認|承認済み10記事だけnoindex解除し、sitemap 10件・他route noindexを外部read-back済み|承認記事のindexability readback合格|
|L4|Mangools 10記事で稼働 — 2026-08-11|`cta_go: GO mangools`と記事release承認|開示先行、Mangools送客先host、`rel="sponsored noopener noreferrer"`を外部read-back済み|MangoolsだけCTA稼働|

L1は`saastcolab.jp`の購入・DNS保存・個別自動更新ON・TLS read-back・GSC所有確認・GA4新origin更新・旧originの1段301・Impact Connected確認まで完了した。P01–P03は2026-08-03に本文・TCO承認、index GO、Mangools CTA GOを満たした。P06/P07は2026-08-08、P04/P08/P10/P12は2026-08-09、P05は2026-08-11に同じrelease境界で本番反映し、10記事のindex・CTA・sitemap境界を外部read-backした。P09/P11はnoindex・CTA無効を維持する。Mangools以外のpartner CTAも無効である。

### Launch最終シーケンス — event-driven

2026-08-02のHuman指示により、S0–S6をtrigger受領順に処理する。S0の最小通貨単位で割り切れない
月額派生値の非表示は実装済み。S2は2026-08-02のMangools exact checkout値と再生成指示により完了し、
P01–P03はHuman記事承認済みで、S1–S5は2026-08-03までに完了した。S6はMangools CTA公開から
24時間経過を入口とし、先行実行しない。SE Ranking・Semrushの未観測値は
unknownのまま関連する横断順位だけを停止し、記事・index・CTAは各Human gateを維持する。

## Launch Quarter 2026-08〜10

### Human予算と記事順

- 2026-08-01〜2026-10-31のHuman予算はlaunch track限定で月2,000分。2026-11に720分へ戻すか再判定する。
- 公開第1弾はP01–P03を維持する。
- 下書き・入力の作業優先順は`P01 → P06 → P07 → P08 → P09 → P02 → P03 → P04 → P05 → P11 → P10 → P12`。
- P01、P06、P07、P08、P09を取引意図先行群、P10・P12を最終群とする。

### 週次実行計画

|期間|主作業|Humanの操作|機械的出口|
|---|---|---|---|
|7/31–8/2|domain dayとP01–P03最終標本|domain token、価格・記事確認|L1 read-back、P01–P03承認候補|
|8/3–8/9|第1弾release準備|`article_approve`、domain反映後の`index_go`|承認記事だけindex候補|
|8/10–8/16|拡張需要CSV|CRM 40・forms 40・email marketing 40・SEO追加60のHuman export|残り180語の行単位検証|
|8/17–8/31|P09/P11自データとservers観測|OperatorのHuman確認済みappend-only実測台帳で実運用値を計測し、通常料金/更新条件をHuman確認|P09/P11の観測開始、servers candidate更新|
|9月|残記事、embed、note/X Human再配信、Impact/ASP審査|投稿・申請・回答判断だけ|index/impression/clickの週次観測|
|10/1–10/24|取引意図記事の改稿と内部導線|標本確認だけ|比較可能な連続2期間|
|10/25–10/31|90日判定|現ニッチのGSC実測を確認|継続・拡張・縮小を固定判定。拡張準備scopeは2026-08-05に前倒しGO済み|

### 2026-10-31固定判定

測定windowは、現行28日=`2026-10-04〜2026-10-31`、直前28日=`2026-09-06〜2026-10-03`とする。
index数は2026-10-31 JST終了時点のGSC snapshot、impressionsとclicksはGSC Web検索の合計を使う。
各tierは行内条件をすべて満たす必要があり、上位から判定する。判定後に閾値を動かさない。

|判定|index数|現行28日 impressions|現行28日 clicks|impressions成長|click成長|処置|
|---|---:|---:|---:|---:|---:|---|
|拡張|10以上|5,000以上|80以上|直前28日比+50%以上|直前28日比+30%以上|カテゴリ拡張とpartner分散を提案。実行は`scope_expand: GO`後|
|継続|8以上|1,500以上|25以上|直前28日比+25%以上|直前28日以上|同じscopeで次の90日を継続|
|最低ライン|4以上|300以上|5以上|直前28日以上|直前28日以上|改善を1回だけ実施し、30日後に再判定|

最低ラインのいずれかを下回る場合は縮小する。新規signalで直前28日が0の場合、現行値が当該tierの絶対閾値を
満たす時だけ成長条件を合格とし、無限成長率とは表示しない。GSCの欠測、property不一致、manual action、
security・legal・rights hard gate違反がある場合は数値tierより先にSTOPする。

#### カテゴリ別90日判定

2026-08-05のW6結果はknown 9,610/月、no_data率0.77333333で、既定の必要22,227 sessions/月に対する
known下限が43.24%だった。この不完全な下限を根拠に、拡張の**準備scopeだけ**を前倒しGOとした。
総需要不足の確定、カテゴリ公開、ASP申請、新vendor照会、価格観測のGOではない。

現ニッチ`seo_tools`は上表をそのまま使う。拡張5カテゴリはカテゴリごとに独立cohortとし、第三の
Human承認記事がindex可能になった日をday 0、day 63–90を現行28日、day 35–62を直前28日とする。
第三記事が揃わなければ拡張・継続tierは`not_evaluable`であり、他カテゴリの数値を合算しない。

拡張カテゴリの初期閾値は、上表のpage当たり基準を3記事pilotへ換算して切り上げた。カテゴリ間で
需要実測がない段階の恣意的な差を付けず、各カテゴリを同じ閾値で別々に判定する。

|対象category|拡張（index / impressions / clicks / imp成長 / click成長）|継続（index / impressions / clicks / imp成長 / click成長）|最低ライン（index / impressions / clicks）|
|---|---|---|---|
|servers|3 / 1,500 / 24 / +50% / +30%|3 / 563 / 10 / +25% / 直前以上|2 / 150 / 3|
|accounting|3 / 1,500 / 24 / +50% / +30%|3 / 563 / 10 / +25% / 直前以上|2 / 150 / 3|
|crm|3 / 1,500 / 24 / +50% / +30%|3 / 563 / 10 / +25% / 直前以上|2 / 150 / 3|
|forms|3 / 1,500 / 24 / +50% / +30%|3 / 563 / 10 / +25% / 直前以上|2 / 150 / 3|
|email_marketing|3 / 1,500 / 24 / +50% / +30%|3 / 563 / 10 / +25% / 直前以上|2 / 150 / 3|

最低ラインはimpressionsとclicksも直前28日以上を必要とする。直前値0、欠測、hard gateの扱いは上表と
同じである。カテゴリ別判定はカテゴリの継続・縮小判断にだけ使い、公開やAffiliate CTAを自動許可しない。

### 8月末の目標状態

- 公開記事9本（Human承認・index GOの範囲だけ）。
- ImpactのHuman側残手続き完了、または相手方審査待ちを明示。
- W6 JP/ja需要safe-summary取得済み。
- A8.net、もしもアフィリエイト、バリューコマースをHumanが個別申請できるサイト状態。

### servers政策v2と2026-12-31固定撤退ライン

serversの第1弾は凍結40語から選んだ20ロングテール候補とし、query別競合値は未観測のまま扱う。
記事順は`開示 → 計算機 → 結果 → CTA枠 → 根拠表`、Human作業は価格確認20分、Operator入力20分、
表示・根拠確認20分を標準とする。60分到達はhard gateを免除せず、主要claimが未確認なら`HOLD`する。

serversのCTA表示は次の決定表を使う。これは表示形式の選択であり、個別partnerのCTAを承認しない。

serversの計算機はzero-inputとし、承認済みcontract価格だけから初期表示時に総額表を計算する。読者操作は
期間12/24/36か月と用途区分だけで、金額、seat、価格基準、税区分は表示・入力させない。unknown行は
`未確認`として順位外、用途対象外と異通貨比較も順位外にする。入力式の詳細計算は`/methodology/`へ分離し、
記事からの参照linkは1本だけにする。両モードともPython正本とTypeScript golden一致をrelease条件に含める。

|有効な承認partner|表示|依存監視|
|---:|---|---|
|0|CTA無効|依存率は測定不能|
|1|単独CTA|構造上100%依存として80%超警告|
|2以上|比較CTA|confirmed commission shareがある場合だけ最大shareを計算。未観測はunknown|

2026-12-31 JST終了時点で、次の3条件を**すべて**満たすことを最低ラインとする。

|指標|固定閾値|測定|
|---|---:|---|
|公開記事|20本以上|同日時点で公開中かつindex対象のHuman承認記事|
|GSC clicks|300/月以上|`2026-12-01〜2026-12-31`のsaastcolab.jp Web検索clicks|
|confirmed成果|1件以上|launch開始から同日時点までのconfirmed transaction。pendingは算入しない|

欠測は合格にせず、閾値は判定後に緩めない。1条件でも未達なら現行SEO記事投資を継続前提にせず、
embed配布、note有料、受託の順に転換案を比較してHuman判断へ送る。転換の公開、販売、営業送信、受注は
それぞれ別GOとする。

## Phase 0 — 規律と供給網（完了）

成果物:

- `AGENTS.md`、RACI、月720分budget、SEV0–3。
- uv lock、SHA固定CI、Dependabot、Gitleaks。
- local git。remote push、deployは未実施。

再検証:

```bash
uv lock --check
gitleaks dir . --redact --no-banner --no-color
```

## Phase 1 — local決定論コア（完了）

成果物:

- field-level `SourcePolicy`、`EvidencePointer`、`VendorPlan`。
- legacy local SQLiteに加え、本番候補用`AuthenticatedSQLitePlanRepository`を実装した。v2はexact schema fingerprint、
  HMAC state、row hash chain、別系統CAS anchor、rollback/one-ahead recovery、repository内部で取得する信頼時刻、
  全操作のdurable time watermark、read時のrights再確認を持つ。最初のsnapshotが固定した
  `min(captured_at + retention_days, review_due_at)`をDB全体の単一retention cohortとし、異なる期限の混在を拒否する。
  実KMS/anchor/backup/crypto-erasureは未接続である。
- monthly/annual、flat/per-seat、usage/overage、tax、addonのTCO。
- local CLIと生成JSON Schema。

残っている外部入力: 実vendorの承認済みpolicyとgold record。fixture合格を実vendor合格に読み替えない。

## Phase 2 — Preflight制御面（local実装完了）

### 2A release/運用

- immutable release manifestとSHA-256。
- `prepare → validate → promote`。AIやparserはprepareまで。
- `data / rights / affiliate`最短expiryによるserve-time visibility。
- Affiliate無効時はCTAと報酬前提rankingを同時に隠す。
- `run_key` unique、重複delivery無害化、例外queue、576/720分budget freeze。

### 2B economics/測定

- 需要を `deduplicated volume × organic visibility × rank CTR × qualified rate` で算定。
- revenueは`confirmed`だけ。pending/rejectedをEPC分子へ入れない。
- 月20万円に必要なclick/session、EPC60円、人手720分を同じreadiness reportで判定する。3社条件は
  editorial launch gateではなく、単一partner依存が60%を超えた後の拡大診断にだけ用いる。

### 2C local end-to-end

- sample policy → VendorPlan → append-only storage → TCO → immutable release → noindex preview。
- 8故障: price、plan name、billing period、currency、quota、source conflict、affiliate expiry、fetch failure。
- fixtureに実社名、実価格、実Affiliate IDを入れない。

### 2D provenance付きproduction intake

- `BusinessDossier` v3は、rights/affiliate/demand/cohort/operationsのhash-only receiptと組立時刻を必須化し、30日shadow・job成功率・例外・rollbackをoperation gateへ含める。
- `assemble-readiness`は`VendorPlan`の全field policyからderive/publish/history権利を導出し、自己申告の`rights_approved`を受け取らない。
- Affiliateは対象domain、審査期限、decision record、program/CTA hashを検査する。URL、credential、同一partner・同一vendorの重複は受け取らない。
- 人手時間は分から、automation率はroutine taskの分子・分母から導出する。分母0は0%としてfail-closed。
- demand、confirmed cohort、operationsはversion、source SHA-256、captured/expiryを持ち、期限切れや未来時刻ではdossierを作らない。

### 2E Phase 3 measurement intake

この3つの`aggregate-*`はunsigned diagnosticであり、単独ではproduction authorityに
しない。

- `aggregate-demand`はJP/ja月次の重複除去済みcluster summaryとscenario rateから`DemandEvidence`を生成する。
- `aggregate-cohort`は単一通貨・単一cohortのdistinct partner summaryを合算し、status mapping hashを保持する。0 clickは隠さずundefined EPC/STOPへ渡す。
- `aggregate-operations`は連続したJST日次summaryから人手、routine、job、例外、重大誤表示、rollbackを集計する。欠測日、重複日、分子超過を拒否する。
- 3入力はauthority/source receipt/rule hashだけを受け、raw export、PII、URL、credential、自由記述をschema外に置く。
- semantic query overlap、transaction status履歴、run retry/exception dedupはL2 builderで推測せず、Human管理領域の上流receiptを必須にする。

### 2F P12 signed measurement integrity

- 開始前Human planはrule/source/privacy/window/exact 8 faultをfreezeし、実測batch hashを
  含めない。終了後indexがexact 3 batch/attestationを閉じる。
- Human、3 producer、indexer、TCO/QAのEd25519 keyを分離し、consumerはartifact外で
  policy/trust/run/exact index hashを固定する。
- demand/cohort/operationsはstage別coverage countとidentity-set rootを持ち、conflict、
  unknown、omission、row tamperをruntimeでrejectする。
- current transaction、causal funnel、payout/全額adjustment、全valid outbound click分母、
  logical job run、exact 8 faultを再計算する。8 fault未達はreport非発行。
- `MeasurementBoundDossier`だけが署名reportの計測値をDossierへ渡す。裸のEvidence/
  Dossierはdiagnostic。P13 production consumerはbound bundleを毎回再検証する。

出口:

- networkなしで全workflowを再現。
- expired/unknown/duplicateがfail-closed。
- full tests、schema、lock、secret scan合格。

実装上の入力契約とCLI手順は`docs/READINESS_INPUTS.md`を参照する。

## Phase 3 — lane別gateと30日Preflight実証（Human入力待ち）

### Gate A: rights model v2

Gate Aは経路を分ける。

#### A1 automated data path（strict gate維持）

対象候補をSE Ranking、Mangools、Serpstatから開始し、Semrush、HubSpotは冷開始条件と審査を別管理する。自動取得、価格DB保存、履歴DB化、canonical計算への採用について次を権限者または契約文書で確定する。

- 対象domain、plan/field、region。
- API/feed/manual/browserの許可methodと頻度。
- 正規化値、短い根拠、raw archive、履歴の保存期間。
- 競合比較、派生TCO、Web/X表示、商標・logo、attribution。
- 契約終了・撤回時の非表示・削除期限。

Human action: 問い合わせ送信、回答者権限の確認、承認scope/期限の署名。一般FAQだけで`approved`へしない。Semrushのautomated fetch、ongoing storage、historyは禁止を維持する。

Impact承認済みpartnerに正規product feed / catalogが表示される場合は、
`docs/IMPACT_PRODUCT_FEED_CHECKLIST.md`でAffiliate関係、catalog、method、field、region、保存、履歴、
派生、表示、終了処理をHumanが画面確認する。catalogの存在だけではapprovedにせず、利用する全scopeが
明示されたexact feedだけを`impact_feed_a1: GO <partner>`でA1 source policyへ登録する。登録はfetch、
download、API/FTP credential、定期job、raw保存、公開の実行権限を含まない。

現在地: 5社の同一8項目照会は、公開名義`omishu`、公開予定URLは未公開として
2026-07-23に送信済み。送信receiptは許諾ではないため、回答・Human判定まではrights 0/3のまま停止する。

Exit: 自動取得・DB化するfieldの100%がapproved/prohibitedに確定し、unreviewedが0。3社未満なら自動取得trackをSTOPする。

#### A2 human editorial path（launch blockerから分離）

Humanが公開価格を正規画面で確認し、vendor・plan識別子、入力値または明示的unknown、billing toggle位置、価格表示分類、出典URL、観測日、次回確認日を観測contract v2.3へ記録する。価格表示分類は`none`、`annual_discount_permanent`、`time_limited_promo`、`unknown`の4値で、計算HOLDは後二者だけとする。年払いplanはcheckout請求総額を一次観測値とし、月額換算はその総額を12で最小通貨単位まで完全に割り切れる場合だけ派生値として分離する。割り切れない場合は一次総額を保持し、月額換算を非表示にする。checkout総額が確認できない年払い価格はunknownとする。`annual_discount_permanent`の割引率は、同一通貨・同一税条件のHuman確認済み月払い価格と年次checkout総額がそろう場合だけ、`1 - annual_total / (monthly_price * 12)`から約N%として記載できる。seat数・利用量等のHumanシナリオはvendor観測から分離し、入力根拠と日付を記録する。この経路はfield-level書面許諾をlaunch blockerにしない。値の自動取得、raw保存、価格DB、履歴DB、禁止回答済み行為、推測補完は行わない。ベンダー照会と30/90/180日追跡は継続する。

Exit: 記事内の数値fieldがHuman入力contractを満たし、出典がcurrentで、記事とindexがHuman承認済みである。未承認fieldはunknownまたは非表示とする。

### Gate B: affiliate

Gate BはAffiliate利用権だけを判定し、価格data rightsとは分離する。editorial laneのCTA条件は、
**当該partnerのAffiliate承認が有効で、規約・広告表示・商標・link条件を遵守できること**である。
field-level rights回答、3社確保、automated data pathのgold setはこの条件へ混ぜない。

Human action: 専用事業mail/accountで申請し、program ID、対象site、報酬、cookie、region、広告表示、
商標、deep link、tracking、失効条件をprivate recordへ記録する。記事側は開示先行と
`rel="sponsored"`を検査し、credential、紹介ID、非公開報酬をrepositoryへ保存しない。

現在地の再判定:

- **Mangools: editorial laneでAffiliate承認済みとして算入可。** 2026-07-26に審査不要のAffiliate
  sectionが有効化され、紹介IDと提供素材の発行を確認済みである。禁止事項、報酬条件、表示条件も
  Human記録にある。価格の自動取得・DB保存・履歴利用の権利は未承認のままで、CTAはpartner別GOまで無効とする。
- HubSpot: 2026-08-03にImpactで`Declined`（low reach）を確認したため未承認。流入実績ができるまで再申請しない。
- Semrush: Impact Marketplaceは2026-08-09に却下済みで、個別programの受付も成立していないため未承認。公開記事・流入実績が改善するまで再申請しない。
- SE Ranking、Serpstat: Affiliate利用を開始できる承認記録がないため未承認。

Exit（editorial lane）: 掲載対象partner単位でAffiliate承認がcurrentで、規約・表示遵守を検査できる。
MangoolsはこのAffiliate条件を満たす。実利用可能3社はlaunch条件ではなく、公開後に単一partner依存が
confirmed outbound clicksまたはconfirmed commissionsの60%を超えた場合の拡大・分散候補とする。

### Gate C: qualified demand

100–200語を料金、比較、代替、乗換え、利用量適合へcluster化し、近似語を重複除去する。代表20–30 SERPを人が確認し、広告、動画、AI answer、公式siteなどorganic可視率を下げる要素を記録する。

Exit: 保守ケースで必要qualified sessionsへの説明可能な経路。Keyword PlannerのCompetition/CPCをSEO難易度やCVRとして使わない。

Local受入contract、集計CLI、schema、反証仕様は実装済み。実JP/ja datasetとauthority receiptは未取得。

開始前universe `jp-ja-v1`は購買意図150語、82 cluster、JP/ja、canonical SHA-256
`82040e6babcf4063a63ab7c3f40f8aab41f868ab3360650ffa766f79f85fe19f`としてfreeze済み。
Google Trendsの予備CSVは相対指数なのでauthorityにせず、Google Adsの変更不能な日本・日本時間・JPY
設定へのHuman GO後にKeyword Planner official exportを取得する。

### Gate D: operations

30日shadow runで、parser成功、false change、例外、人手、job、8故障を測る。

Exit: 重大誤表示0、例外≤24/月、人手≤720分/月見込、job≥99%、rollback合格。

30日の日次coverageとGate D判定はlocal実装済み。実shadow runは権利・source・schedule scope確定後に開始する。

## Phase 4 — 許諾済みadapterと3社×6プランgold set（automated data path専用）

Entry: **automated data pathに限り**、Gate A1と対象用途に必要なGate Bを合格したsourceだけを扱う。
このPhaseのadapter、P8、3社×6プランgold set、30日shadowはeditorial launch laneのL1–L4、
Phase 5–6のeditorial公開、Human記事承認、index解除、partner CTAの入口条件ではない。

### Local P8受入境界（完了）

- `HumanGoldSet`はHuman label receipt、policy-only rights manifest、field value/source hash、代表scenarioのcurrency/total/full TCO hashとTCO label TTLを保持する。
- `CandidateBatch`はparser/source receipt、固定parser version、成功planと全parse failureを同じbatchで受ける。失敗rowを黙って除外できない。
- partial setは保存可能だが、3 vendor以上 × 各6 plans以上かつvendorごと60–150 labelsを満たすまでrelease不可。
- current derive/publish/history/retention、future evidence、field/source/field・TCO label TTL、TCO、missing/extra/future/expiryを独立quarantineする。
- parser failure率は20%超でSTOP。exact 20%でもfailure quarantineがあるためrelease不可。
- reportはhash-onlyで順序不変。Human署名真正性、source-specific parser、実labelは外部Gate後に残す。
- `evaluate-gold-set` CLIと2 JSON Schema、synthetic fault testsを実装した。詳細は`docs/GOLD_SET_RUNBOOK.md`。

実装順:

1. manual/公式feed/公式APIを優先。
2. HTTPX static adapterはapproved host/method、redirect再検証、ETag、timeout、`Retry-After`を実装。
3. JS必須かつbrowserがapprovedの場合だけPlaywrightを1 sourceずつ追加。
4. deterministic parserで候補値を作り、schema/evidence/TCO差分をquarantineする。
5. 6プラン/社、60–150 material fieldsをHumanがgold label化する。

停止:

- 403、CAPTCHA、login、region restriction、規約回避が必要。
- parser不能20%超かつ手動更新でも720分/月を超える。
- source conflictを一意に解けない。

## Phase 5 — noindex公開前MVP

Phase 5には二つの入口がある。automated data pathから入る場合はPhase 4成果物と既存P7–P18 controlを使う。
editorial launch laneから入る場合はL1–L2、Human editorial input contract、PR開示、TCO golden test、
記事別承認を使い、Phase 4、P15、P16、P18、3社×6プランgold setに依存しない。以下のP7–P18説明は
maintenance中のautomated data path controlであり、editorial laneへ入口条件を追加しない。

### Local P7実装（完了）

- Sites/vinext互換の`site/`へhome、comparison、methodology、disclosure、readiness、robotsを実装した。
- 実価格・実Affiliate URLを入れず、事前計算済み合成fixtureだけを表示する。UI側TCO計算はない。
- preview contract v2へregion、tax、billing、commitment、適合理由、根拠取得時刻、data/rights期限を追加した。
- `saas_preflight.mvp`はcontent-addressed artifact、destination/disclosure hash、request-time release/TTL、CTA redaction、generic 503、health、security headerをpure functionで実装した。
- expiry境界、CTA mismatch、artifact改変、method/route、robots/CSP、landmark、rollbackをsynthetic testで再現した。
- Web dependency auditは0 vulnerability。local buildまでで止め、Sites project作成・hosting・deployは実行していない。

実装契約と検証手順は`docs/LOCAL_MVP.md`を参照する。

### Local P10公開前Release Assurance（完了・独立再監査合格）

- 24件のmaterial threatを、予防・検知・停止・復旧・残余リスク・owner・Human gateまで分解した。local実装済みcontrolとproduction未実装controlを分離し、launch blocker L1–L11を固定した。
- `uv.lock`と`site/package-lock.json`だけから、networkなしでCycloneDX 1.6 SBOMを決定論生成する。451 components・451 graph nodes、lock hash、purl、利用可能な配布物hash、npm licenseを保持し、credential URL・絶対path・timestampを拒否する。
- synthetic-local 5 routeで、document metadata、landmark、skip link、internal link、table semantics、広告説明、無効CTA、900/620px reflow、keyboard focus、reduced motion、canonical/JSON-LD/public origin不在を検査する。
- 13の必須checkごとにfacts種別、tool/version、command/subject hashをpolicyへ固定し、controller-role runnerが型付きfactsへ署名する。件数、coverage、exit code、determinism、finding、future、expiry、最大TTLをcheck別に再計算し、全件合格だけを`local ready`とする。
- automated data pathの`public GO`には、local reportへ結合したTCO/QA署名、exact BusinessDossierとmanifest全snapshot完全listへ結合したHuman署名、事業`GO`、manifestとのrights/Affiliate/demand/cohort/operations binding、current CTA/expiryを全て要求する。local readyをpublic GOへ読み替えない。この条件はeditorial laneのL1–L4へ適用しない。
- 最終GOだけにcontroller署名authorizationを発行する。consumerはrepo外から固定するcontroller公開鍵、policy hash、最大TTL、現在時刻で再検証し、別Authorityの自己承認とexpired report replayを拒否する。
- 現在のcurrent-state fixtureは、合成local passを与えてもbusiness `STOP`、CTA未承認、TCO/QA・Human署名なしでpublic `STOP`となる。

詳細は`docs/THREAT_MODEL.md`、`docs/SBOM_RUNBOOK.md`、`docs/RELEASE_ASSURANCE_RUNBOOK.md`を参照する。

### Local P11署名付き外部action境界（完了・production実行は未承認）

- rights問い合わせ、Affiliate申請、公開activate、公開disableの4 actionをclosed enumに固定し、target・payload・property・pre/post-state・idempotency・release/P10 bindingをhash-only requestへ閉じた。
- exact requestへのHuman `GO`とcontrollerの短命grantを別鍵で署名する。fixed runtimeはcontroller署名だけを信用せず、Human署名、policy/trust、TTL、prestateを再検証し、activation時は同一releaseのcurrent P10 public GOも再検証する。
- guardだけが新規作成または固定IDと外部monotonic pinで再openできる専用SQLiteへrevocation、grant/idempotency claim、terminal receiptを保存する。companion認証anchor、HMAC state head、schema fingerprint、write read-back、別read/commit anchor sourceで行削除・DB+anchor旧版差替え・trigger置換・空DB再生成をfail closedにし、同じstoreのrestart後replayを拒否する。claim時刻とreceipt completionはstore/file-lock CAS transaction内のdurable write前にguard clockから取得する。
- policyは4 actionそれぞれのenvironment、vendor/program相当、property、target hashをexact allowlistへ固定する。journal foldはdurable stateとclaim/receipt/revocation集合を完全一致させ、署名、predecessor、時刻単調性、future、extra/欠落sidecar、wrong-post successをfail closedで検査する。authority stateとfactual outcomeを別fieldにして、開始後revocationと実結果を混同しない。
- 49 JSON Schemasと署名なし合成requestを生成した。provider adapter、credential、実送信・申請・activate・disableは後続の外部統合とHuman承認まで禁止する。testの外部pinはmemory実装で、same-process hostile codeとpin/key source侵害はP11の信頼境界外である。productionではout-of-process固定anchor/KMS、shared durable store、worker fencing、crash-safe recovery、provider idempotency、backup/restore、approved clock sourceを別途検証する。

詳細は`docs/EXTERNAL_ACTION_RUNBOOK.md`と`docs/EXTERNAL_ACTION_ACCEPTANCE.md`を参照する。

### Local P13 production consumer（実装済み・production接続は未承認）

- activationはP12 `MeasurementBoundDossier`、P10 public authorization、P9短命lease、P11のexact Human
  GO/controller grant/durable claimを同一release・property・targetへ再結合する。裸のDossier、P9/P10/P12単独、
  detached P11 claimはdispatchを作れない。
- 固定store/policy、default STOP、Human署名reset、monotonic epoch/revision/fence、全state HMAC、schema
  fingerprint、hash-chain event、外部monotonic anchor付きSQLiteを実装した。in-flight restartは`UNKNOWN`+
  STOPとなり自動retryしない。
- activationはRUNNING時だけ許可する。P11-approved disableはSTOPを維持した安全レーンで、P9/P10/P12
  activation authorityを必要とせず、STOPをclearできない。
- checked-in execute/probeを別subprocessで起動し、両executable、Python、固定source closure、allowlist、実
  postcondition schemaをpinする。実行はverified file descriptor、timeout時はprocess group全体kill、直前の
  store共有fenceでcurrent epoch/P11 revocation/STOPを再検証する。専用provider署名receiptと別process・別鍵
  probe、provider idempotency 1回を検証し、Human/controller/measurement/dispatcher秘密鍵はchildへ渡さない。
- local childはbase stdlibと必要な8 distributionを含む全import closureをhash検証し、manifest/config/key/schemaを
  FDで渡す。macOSではPython bootstrap executable自体のsame-user差替えをFD executionで閉じられないため、本番は
  consumer-pinned image digest、read-only runtime、P15のSBOM再検証を必須とする。local fixtureはこの環境保証を
  代替しない。
- claim後の取消・exact expiryは同一transactionで`UNKNOWN`+STOP+epoch更新にし、provider実行後の取消は
  signed factual receiptだけを残してsuccess権限にはしない。P11/P13のcross-store transaction、remote provider
  fence、KMS/OS identity分離は実環境gateとして残す。
- failed/partial/unknown/timeout/crash/malformed receipt/probe mismatchはsuccessにせずsticky STOPへ進む。
  実provider exactly-once、KMS、trusted clock、cross-host anchor/fencing、実readback、credential、egressは
  production gateに残る。

詳細は`docs/P13_PRODUCTION_CONSUMER.md`と`docs/P13_ACCEPTANCE_TESTS.md`を参照する。

### Local P14 crash-safe provider evidence（実装済み・production接続は未承認）

- schema v2の追記専用provider journalへ、署名・token・時刻・policyを検証したfactual receiptをprobe/P11
  receipt/P13 terminalより先に保存する。journalは外部anchor、全state HMAC、event hash-chainの対象で、update/
  deleteを拒否する。
- claim ownerはsame-host OS lockを保持する。live owner中の別openerは回収もredeem/terminal mutationもできず、
  4-process同時claimは1 ownerだけとなる。
- provider保存後のowner lossはreceiptを保持した`UNKNOWN + STOP`へ1 event/1 epochで回収し、再実行・再昇格
  しない。保存前crashはreceiptを捏造しない。SQLite commit後のanchor一時障害もone-ahead復旧後に同じSTOP
  semanticsを維持する。
- probeは`provider_recorded` phaseだけ、terminalはexact journalだけを使用できる。provider/P11/probe receiptは
  factsであり、current P9–P13 authorityとexact terminal commitの代替ではない。
- schema v1の自動migration、remote mutation/receipt atomicity、provider exactly-once、multi-host consensus、
  KMS/trusted clock、P11/P13 cross-store transactionは実環境gateとして残す。

詳細は`docs/P14_CRASH_SAFE_EVIDENCE.md`と`docs/P14_ACCEPTANCE_TESTS.md`を参照する。

### Local P15 production integration readiness（実装済み・実環境証拠は未取得）

- provider conditional mutation/idempotency/receipt lookup、独立readback、KMS identity分離、external anchor、
  trusted clock、shared store/fencing、egress、backup/restore、rollback/disableのexact 11 checkを型付きfactsへ
  固定した。plan v2はprovider targetとexpected pre-stateも固定し、別対象のreadback再利用を拒否する。
  thresholdはpolicyだけが持ち、plan/evidenceの自己申告で変更できない。
- provider conformance、probe、security、storage、time、network、recovery、TCO/QA、Human、controllerの10鍵を
  分離する。synthetic証拠は全件合格形でもSTOPで、実環境形証拠も`READY_FOR_HUMAN_GATE`までである。
- P13 request/dispatch token v4へP15 policy/trust/plan/authorizationとpacket外P18/P16/semantic root、P16 plan/bundle/semantic packetを結合した。claim、redeem、provider/
  probe直前、terminal successで再検証し、dispatch token expiryをP15より後にしない。P15 expiry時も
  Human-approved disable safety laneは維持する。
- `UNKNOWN | STOP`だけを入力とし、常にSTOPを返すreconciliationを実装した。recovery auditor署名factsはP14
  journalへ後挿入せず、HMAC・hash-chain・external anchor付き別ledgerへ追記する。P13 resetは現在のSTOP
  head/revision/reasonと一致するledger recordを必須にした。
- checked-in blocked fixtureは11 missingでSTOP。URL、credential、account、network client、provider/cloud接続、
  deploy commandは実装していない。

詳細は`docs/P15_PRODUCTION_INTEGRATION_READINESS.md`と`docs/P15_ACCEPTANCE_TESTS.md`を参照する。

### Local P16 v3 / P21 typed launch semantics（実装済み・全実gateはSTOP）

- typed P18 repository acceptance、rights、Affiliate、qualified demand、shadow operations、gold/source、P15 readiness、
  deployment/publication readinessをexact 8 gateの固定順序へ結合した。
- Gate 1はP18 bundle/manifest/tree/Human receiptとconsumer-owned P18 authority-rootを再検証する。さらに
  P16 plan/policy/trustを別のconsumer-owned launch-handoff authority-rootへ固定し、旧P11–P15 opaque hash列、
  P18一式差替え、P16 trust+plan+全receiptの自己整合型完全差替えを拒否する。
- 各gateは固定artifact component set、candidate/property/environment/release、role/key、TTL、ordinal、直前receipt
  hashへ署名する。canonical sortは重複を消さず、predecessor chainと非減少時刻を別に検証する。
- gate 7はP15 report/TCO attestationまで、gate 8はP10 local assurance、P11 disable policyとP15原証拠へexact bindingしたprobe署名deployment readback、そのdeployment hashへ結合したcontent/indexability/disclosureの個別publication readbackまで
  とし、bootstrap authorization、dispatch token、execution grant、public GOを含めない。
- Gate 2–8はrights/affiliate元行、P12 exact report+dossier、gold set、P15、P10、deployment/publicationの
  typed packetを公開鍵専用verifierで再実行する。P12 fault target、P15 plan、P10 manifest、P13 request/dossierは同一release/manifest/artifact/schema/provider target/pre/post/rollbackへ固定し、P16 planはlegal pagesとAffiliate disclosureの期待hashも固定する。packet外semantic rootが各upstream hashを固定し、opaque hash、自己申告readback、scope splice、意味的STOPの再署名、個別観測の期限・deployment順序違反、receiptがupstream expiryを延長する形を拒否する。
- 完全な実環境形packetでも`READY_FOR_FINAL_HUMAN_REVIEW`までであり、外部操作のauthority effectは常にnone。
  checked-in fixtureは8 missingでSTOPである。

詳細は`docs/P16_LAUNCH_HANDOFF.md`と`docs/P16_ACCEPTANCE_TESTS.md`を参照する。

### Local P18 repository acceptance（実装済み・Human acceptance PENDING）

- P11–P21のcode、tests、schemas、docs、scripts、locks、workflowを全file manifestへ固定し、symlink、hardlink、
  secret名、未知top-level、NFC/case衝突、途中変更を拒否する。
- exact path-set hashをversion付きscope profile registryへ固定する。既存profileの意味は変更せず、対象pathの
  増減は新profileとして追加するため、過去manifestを同名の縮小scopeへ読み替えられない。
- 14検証はargv、cwd、environment、network、interpreter/import closure、tool/version、assertion/fail/skip/exit、
  output hashと期限を保持し、Integration Evidence RunnerとTCO/QAが別鍵で署名する。
- 14検証を固定順に実行するlocal diagnostic runnerを追加した。Python testは明示5 laneへ分割し、Web以外は
  network disabled、Webはloopback only、schema/fixtureはchecked-in bytesまで二重照合する。秘密鍵・署名・
  Human decisionはrunnerから分離した。
- local runnerはhost filesystem/processをimmutable snapshotへ隔離できず、署名済みfresh advisory snapshotも
  ないためprovenanceは`local_diagnostic_run`でdependency checkをfailにする。`verified_local_run`はread-only
  digest-pinned OCI/VM、network none、host mount非公開、typed result v2を実装する後続production packetまで発行しない。
- Human前からpolicy+trustを別verification-authority rootで固定して両role署名を検証する。Human receiptは
  GO/CONDITIONAL/STOP、revision、predecessor、current headを持ち、revision 2以降は全履歴を要求する。
  consumer-owned authority-rootで旧GO replayとself-issued trust一式差替えを拒否する。
- P13 subprocessは全componentをdirfd+`O_NOFOLLOW`で検証し、`-I -S` isolated childへ固定src/runtime pathと
  hash済みimport-file allowlistをFDで渡す。検証した同じPython bytesまたはextension descriptorからloadし、caller
  `PYTHONPATH/sys.path/sitecustomize`と未pin runtime moduleは継承・loadしない。bootstrap Python executableは
  read-only immutable production imageを信頼境界とする。
- 現在fixtureはsynthetic/unsignedのため`STOP / local_verification`。P18 acceptedでもautomated data pathでは
  次にrights evidenceが必要で、automated sourceのpublic/production/affiliate/spend/scale authorityはfalseである。
  これはHuman editorial pathのL1–L4を停止する根拠にはしない。

詳細は`docs/P18_REPOSITORY_ACCEPTANCE.md`と`docs/P18_ACCEPTANCE_TESTS.md`を参照する。

画面:

- 方法・更新日・region/tax/currency/commitmentを常時表示。
- サイト数、keyword数、seat、監査page、AI tracking条件の代表scenario。
- TCO、適合/非適合理由、根拠URL、期限。
- 広告であることを判断箇所の近くに表示。Affiliate linkは`rel="sponsored"`。
- filter/sort/query/空結果/個別入力はnoindex。canonicalは代表pageだけ。

automated data pathの公開前gate:

- threat model、secret/SBOM/dependency scan、accessibility、mobile、structured data、robots/canonical。
- expired release、affiliate invalid、scheduler停止、DB破損、rollbackのE2E。
- Human signed `GO | STOP | CONDITIONAL`。automated data成果物はGOまで公開しない。

editorial laneの公開前gateは、L2の記事別Human承認、PR開示先行、currentな出典・次回確認日、
TCO golden一致、秘密検査、承認記事だけを対象にした`index_go: GO`で構成する。CTAはさらにGate Bと
partner別GOを要求し、index GOから推論しない。

## Phase 6 — production launch（別承認）

editorial laneのPhase 6はL3–L4を実行する。Phase 4成果物、P15、P16、P18、3社×6プランgold setの
受理を要求せず、承認記事だけのindex解除と承認partnerだけのCTAを独立したGOで行う。
以下のP9 control boundaryはautomated data pathのproduction serving用であり、editorial公開の入口条件ではない。

### Local P9署名付きcontrol boundary（完了）

- frozen config、role分離したTCO/QA・Human・controller公開鍵、controller signerを`ControllerAuthority`へ固定した。
- TCO/QAのgold report attestationとHumanのcurrent release decision attestationが揃い、全rights・Affiliate・release・heartbeat・例外・budget gateを再計算した`maintain_current`の場合だけ、短命ServingLeaseを発行する。
- production runtimeは固定controller鍵、scope、release/manifest/artifact、最大TTL、半開expiry、Ed25519署名をrequest時に再検証する。失敗時は静的assetを含む保護routeをgeneric 503へ閉じる。
- production Workerは`assets.run_worker_first=true`でasset-first bypassを禁止し、`/healthz`と`/robots.txt`だけを固定応答として維持する。合成UIは`synthetic-local`専用entryに分離した。
- 自動promote、rollback、deploy、publicationは出力契約に含めない。実provider接続、秘密鍵配置、scheduler、domain、公開はHuman Approverの別承認である。

詳細は`docs/CONTROL_CYCLE_RUNBOOK.md`を参照する。

選定はカテゴリごと1製品:

- managed job、Postgres、secret store、dead-man/error monitor、privacy-safe analytics、hosting。
- 実source数、RPO/RTO、月額、export、kill switchで比較し、製品名を先に固定しない。

Human input: domain/brand、法人/個人事業表示、privacy/affiliate disclosure、専用account、billing、credential、GitHub remote、deploy/publish承認。

自動deployは故障注入とrollback合格後。production DB/public release/affiliate URLへAIをdirect writeさせない。

## Phase 7 — 最大180日Traction test

### Local P17 traction/settlement control（実装候補完了・実測未開始）

母数は暦月ではなく、Asia/Tokyo境界の連続30日cohortで保存する。ingest時にP12完全packetを再実行し、
TCO/QA署名observationをauthenticated append-only ledgerへ追加する。append/evaluate時刻は別TIME_AUDITOR鍵で
exact ledger stateへ署名し、caller時刻と後退を拒否する。targetをDB+外部anchorへcommitした後のfinalizationも
同じglobal時刻順序へ含める。clock callbackはpolicy上限で打ち切り、唯一のpending tailはcrash後にanchor回復して
再finalizeし、期限超過はactive evidenceでなく署名付きtombstoneへ固定する。clock/file-lock FDはfork handlerと
one-shot leaseで所有権を固定し、開始前・開始後例外、FD再利用、親crashでも二重closeと並行callbackを拒否する。
後日確定・返金・chargebackは元cohortへ固定したsigned
Settlement Amendmentだけで反映し、裸の`settlement_complete`や調整額を受け取らない。settlement snapshotと
評価report、そのfinalizationも観測と同じglobal event chain、HMAC、外部anchorへ永続化する。

- Search impressions、organic clicks、qualified sessions、outbound clicks。
- affiliate click、pending、rejected、confirmed、paid revenue。
- source freshness、rights/affiliate expiry、重大誤表示、false change、例外、人手分。

P17の複雑な判定はconfirmed 1,000 outbound clicks到達まで再開しない。再開後のEPCはsettlement amendment適用後の
new-acquisition settled額を全valid clickで割る。最新30日売上・CTR・partner集中・運用品質と累積EPCを混ぜない。

- Scale review候補: settled new-acquisition EPC≥60円、最新settled売上≥20万円、bear capacity、
  site→merchant CTR≥10%、automation≥80%、job≥99%、重大誤表示0、人手≤720分。3社以上はlaunch・reviewの
  必須条件ではない。単一partnerがconfirmed outbound clicksまたはconfirmed commissionsの60%を超えた場合に、
  実利用可能partnerを最大3社まで増やす分散施策を評価する。
- Continue: sample不足かつhard operations合格。成功扱いせず、追加投資は新しいHuman decision。
- Stop/縮小: EPC<60円、掲載中partnerのAffiliate失効、薄い再掲しか作れない、人手超過。3社未満だけを
  STOP理由にしない。

local出力は`READY_FOR_SCALE_REVIEW`までで外部authorityはない。詳細は`docs/P17_TRACTION_SCALE_CONTROL.md`、
境界は`docs/P17_BOUNDARY_MATRIX.md`を参照する。

## Phase 8 — 月20万円scale

優先順位:

1. qualified率と送客CTRを改善し、必要trafficを減らす。
2. confirmed EPCの高いmerchant/scenarioを増やす。単一広告主依存60%超を分散施策の発動条件とし、
   実利用可能3社はその緩和策であってlaunch条件にしない。
3. 実測で価値があるsource/fieldだけ増やす。
4. parser不能20%以上または確認4時間/月超で初めて抽出AI 1社をA/Bする。
5. 2 provider、90日、1万req/月またはAI費5万円/月になるまでgateway/MCPを入れない。

月20万円達成後も、権利・品質・人手gateを破る拡大は行わない。

## 現在の停止点と再開条件

automated data pathのcredential-free実装はP21 typed launch semanticsまで進み、P13 exact one-shot execution port、
P17 bounded file-lock/anchor、authenticated plan storage v2を追加した。このlaneの外部順序はP18
`local_verification`、Human repository acceptance、rights evidenceである。外部入力と分離して、
typed task/activity evidenceによるautomation 80%・人手・運用TCO・純利益の再計算と、immutable P18 verification
runner V2、Storage Auditor署名consumption receiptのP18→P16→P13 binding、store固定/durable-freeze replay consumer、credential-blind P17 broker、P13の署名clock/current-root再取得・provider後時刻・P18/P16実行直前再検証は実装した。P21はrightsからpublicationまでの型付き上流証拠を再計算し、P16 receiptの正しい署名だけではREADYにならない。P13 request/token/current-rootにも意味packetとpacket外rootを固定した。実quote/CASとproduction clock/anchor/current-root serviceは環境engineering backlogとして残る。real adapterと自動取得成果物の公開は個別Human承認まで進めない。

editorial launch laneはこの順序から独立し、L1 `domain: GO saastcolab.jp`は購入・DNS保存・個別自動更新ON・Sites／TLS・GSC・GA4・旧origin 301・Impact Connectedのread-backまで完了した。再開順は
`L2 P04–P12 Human実値入力・記事承認 → L3 index GO → L4 partner別CTA GO`とする。
P15/P16/P18受理、field-level書面許諾、3社×6プランgold set、実利用可能3社を待たない。

形式的なrepo承認記録はP0–P10までである。P11–P21はautomated data pathの監査対象working-tree候補であり、
そのlaneのlocal統合前にP18 manifest/verification/authority-rootへHumanがrevision付きdecisionを署名する。
既存P11–P17 PENDING票は履歴として変更しない。editorial laneはこの受理に依存せず、L1–L4の個別GOと
記事・partner単位の条件だけで判定する。

Automated data pathの残入力:

1. 対象3–5社の優先順位。
2. 各社rights回答または契約根拠。
3. 対象partnerのAffiliate承認結果と公開可能な条件（secret/ID本体はrepoへ入れない）。
4. 重複除去済み需要dataset。
5. automated production時のaccount/billing/deploy承認と、P15 exact 11証拠を採取する実環境・role/KMS/anchor
   のidentity hash。

Editorial launch laneの残入力は、domain GO、P01–P12のHuman実値と記事承認、index GO、partner別CTA GOである。

これらがなくても再検証と保守はできるが、synthetic/local範囲を実環境・公開へ拡張しない。
