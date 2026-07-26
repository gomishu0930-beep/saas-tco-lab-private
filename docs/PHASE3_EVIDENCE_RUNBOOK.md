# Phase 3 実測Evidence受付runbook

> **Authority境界:** 本文の`DemandEvidence` / `CohortEvidence` /
> `OperationsEvidence`直接生成はunsigned diagnostic手順である。Production判定では
> `P12_MEASUREMENT_INTEGRITY.md`の開始前freeze、producer署名、stage別coverage、
> current transaction/payout、exact 8 fault、consumer固定indexを必須とする。旧4 status
> aggregateだけをP12 evidenceへ昇格しない。

## 1. 目的と適用範囲

本runbookは、Human Approverが実測開始を承認した後、次の3種類のlocal inputを、version付きの`DemandEvidence`、`CohortEvidence`、`OperationsEvidence`へ変換する手順です。

1. 日本語需要dataset
2. Affiliate network / vendorのcohort report
3. 30日shadow operations log

外部sourceからの取得方法を定める文書ではありません。申請、login、メール送信、API呼出し、Web fetch、外部uploadは本runbookの範囲外です。Humanが正当な権限で取得済みのlocal exportだけを入力にします。

目的はraw reportをrepoへ集めることではなく、PII、secret、tracking URL、raw本文を残さず、集計値、authority、変換規則、時刻、version、expiryとSHA-256で再検証できる最小Evidenceを作ることです。

## 2. 絶対規則

- raw CSV、spreadsheet、PDF、HTML、メール、dashboard screenshot、全文logをrepo、fixture、prompt、ticketへ保存しません。
- 氏名、メール、IP address、Cookie、token、account ID、customer ID、自由記述、affiliate URL、destination URLをEvidenceへ入れません。
- PIIやsecretをhash化して残すことも禁止します。低entropyのメール、電話番号、URL等はhashから推測できるため、hashは匿名化の代替ではありません。
- hash対象にできるIDは、PII/secretでないことを確認したtransaction/run/event IDだけです。元IDは変換中のmemoryまたはHuman管理の隔離領域から外へ出しません。
- raw値をAIへ渡しません。AIはsafe summary後のschema/test reviewにだけ利用できます。
- 金額と率はbinary floatへ変換せず、原文の10進表現を`Decimal`文字列として扱います。暗黙の通貨換算は行いません。
- 既存Evidenceを上書きしません。修正、再取得、mapping変更は新しい`evidence_version`としてappendします。
- 未観測、不明、分母0、期限切れを0件・100%・PASSへ変換しません。確認不能は`WAIT`または`STOP`です。

## 3. 役割と責任

|工程|Evidence/Policy Steward|Contract/Storage Engineer|TCO/QA Engineer|Integration/Release Operator|Human Approver|
|---|---|---|---|---|---|
|source権限・authority・期間の確認|R|C|I|I|A|
|local exportの取得と隔離|C|I|I|I|R/A|
|PII/secret/raw列の除去規則|R/A|C|C|I|I|
|canonical safe summary変換|C|R/A|C|I|I|
|dedup/status/currency/期間の反証|C|C|R/A|I|I|
|Evidence生成、schema、hash検証|I|R|C|A|I|
|Dossier組立とreadiness評価|I|C|C|R/A|I|
|GO/STOP、公開、費用、外部操作|C|I|C|R|A|

同じ人が複数roleを担当しても、artifactと承認記録を分けます。Human Approverは集計コードの自己承認をせず、TCO/QAは事業上好ましい値へ補正しません。

## 4. Evidence chainと保存境界

### 4.1 四層

|層|内容|保存場所|repoへ入れるか|
|---|---|---|---|
|L0 source|providerから取得したraw export|Human管理の隔離済みlocal領域|禁止|
|L1 sanitized staging|allowlist列だけの一時データ。raw IDは変換中だけ参照|隔離済みlocal working area|禁止|
|L2 safe summary|集計値、hash-only event ID、authority、規則version、件数、時刻、expiry|append-only local evidence area|許可。PII/secret/raw全文がない場合のみ|
|L3 typed Evidence|`DemandEvidence` / `CohortEvidence` / `OperationsEvidence`|readiness input|許可|

L0を別roleへコピーしてhandoffしません。Evidence/Policy StewardとContract/Storage Engineerは、Human管理端末上でallowlistと集計結果だけを確認します。L0の削除はsource policyとHumanのretention判断に従い、本pipelineが自動削除しません。

### 4.2 必須provenance

各L2 safe summaryは次を持ちます。該当しない項目も省略せず`not_applicable`と理由を記録します。

|項目|意味|
|---|---|
|`authority`|publisher/network/owned scheduler等の発行主体、report種別、official exportかowned logか|
|`authority_record_sha256`|権限・対象property・territoryを記した承認済み記録のhash。実account名やURLは含めない|
|`retrieved_at`|Humanがexportをlocalへ取得したtimezone-aware時刻|
|`source_period_start/end`|sourceが表す半開区間`[start, end)`|
|`source_timezone`|source UI/reportのtimezone。欠落時は推測せずSTOP|
|`canonical_timezone`|常に`UTC`。Human月次境界は別に`Asia/Tokyo`を記録|
|`currency`|Affiliate金額はISO 4217の単一通貨。需要/operationsは`not_applicable`|
|`status_mapping_version/sha256`|raw statusからcanonical statusへの完全mapping。Affiliateとjob/exceptionで必須|
|`dedup_version/sha256`|重複key、正規化、優先順位、conflict規則のversionとhash|
|`schema_version`|受入schemaのversion|
|`evidence_version`|意味変更または再取得ごとに増やすimmutable version|
|`captured_at`|snapshotまたは観測終了のtimezone-aware UTC時刻|
|`expires_at`|承認済みfreshness policyから算出した時刻。`captured_at`より後であること|
|`source_receipt_sha256`|元exportのbytes checksum。値はlocalで計算し、raw内容やpath名を残さない|
|`safe_summary_sha256`|canonical化したL2全体のSHA-256。L3の`source_sha256`に使用|

`retrieved_at`、`captured_at`、`expires_at`は別概念です。再downloadしただけで`captured_at`や`expires_at`を延長しません。

### 4.3 canonical hash

L2はUTF-8 JSON、key sort、余分なwhitespaceなし、LF、timezoneはISO 8601 UTC、金額/率はDecimal文字列、setは正規sortした配列としてcanonical化します。

```text
safe_summary_sha256 = SHA256(canonical_safe_summary_bytes)
```

event IDは用途を分離して衝突を避けます。

```text
event_hash = SHA256(
  "phase3:<dataset-kind>:<dedup-version>:" + authority + ":" + non_pii_raw_id
)
```

元IDがPII、secret、URL、低entropy値の場合はこの式を使わず、その行をquarantineします。複数fileの同一eventを判定できるstable non-PII IDがない場合、推定dedupをせずSTOPします。

## 5. 共通intake手順

### Step 0: 測定定義をfreeze

開始前にHuman Approverが対象property、territory、source、期間、timezone、currency、qualification rule、routine-task分母、status mapping、dedup、freshness、fault catalogをscope・期限付きで承認します。30日の途中で意味を変えません。変更が必要なら現runを終了し、新versionで再開始します。

### Step 1: local source receiptを作る

Humanは正規のexport機能で取得したfileをrepo外の隔離領域へ置き、authority、report名、report period、source timezone、retrieved timeを記録します。filenameに氏名、account、email、campaign IDを残しません。source bytesのSHA-256だけをreceiptへ記録します。

### Step 2: denylistを先に検査

headerとsampleをHumanがlocalで確認し、次を含むcolumn/rowを変換対象から除きます。

- email、name、phone、address、IP、user-agent全文、free text
- token、Cookie、session、API key、login、account/customer ID
- affiliate/deep/tracking URL、query parameter、destination URL
- raw keyword全文に混入した個人名、メール、電話等
- transaction/customerの説明、invoice、memo、support本文

denylist検出が1件でも残ればL2を生成せずquarantineします。値を伏字やhashへ変えて通過させません。

### Step 3: allowlistだけを変換

dataset別allowlistに存在しないcolumnはstrict errorにします。missing値を0や一般平均で埋めません。raw IDはPIIでないことを確認し、dedup hashへ変換した直後にsafe rowから除きます。

### Step 4: dedupとconflict検査

同一event hashの完全重複は1件にし、`raw_rows / accepted_rows / duplicate_deliveries / quarantined_rows`を記録します。同一hashでamount、currency、status、timestamp、resultが異なる場合は新しい方を選ばずbatch全体をSTOPします。

### Step 5: aggregateと反証

集計は決定論的に行い、入力順を変えても同じcanonical JSON/hashになることを確認します。TCO/QA Engineerは少なくとも、duplicate、conflict、unknown status、mixed currency、future time、expired evidence、zero denominator、期間外eventのfault fixtureを再実行します。

### Step 6: expiryを適用

`expires_at`はsource別freshness policyのversionからだけ算出します。期限が不明、`expires_at <= captured_at`、Dossier組立時に期限切れならEvidenceを作り直すかSTOPします。copyやversion番号変更で延命しません。

### Step 7: typed Evidenceを生成

L2をschemaへ通し、L2のSHA-256をL3の`source_sha256`へ渡します。Affiliateはstatus mappingのcanonical bytesを別にhashし、`status_mapping_sha256`にも記録します。schemaで許されるfieldだけを書き出します。

## 6. Demand dataset → `DemandEvidence`

Keyword Plannerへ投入する開始前universeは`examples/jp_ja_keyword_universe_v1.csv`に
`country=JP`、`language=ja`、購買意図150語としてfreezeする。これは需要Evidenceではなく
測定入力である。次で件数、exact正規化重複、PII/URL/identifier、cluster、scope、canonical
hashを検査してからUIへ投入する。

```bash
uv run saas-preflight validate-keyword-universe examples/jp_ja_keyword_universe_v1.csv
```

Google Trendsの相対指数をこのuniverseの月間検索数へ換算しない。Keyword Planner等のapproved
official exportをrepo外L0で取得した後だけ、以下のL1/L2手順へ進む。

### 6.1 authorityとscope

許容するauthorityは、Humanが正規にexportしたapproved keyword tool、owned Search Console/analytics、Human確認済みSERP observation等です。X投稿数、匿名記事、AI推定、業界平均だけの値はauthorityにしません。

L2へ次を記録します。

- country=`JP`、language=`ja`、device、検索面、対象月
- keyword universe version/hash、source別capture date
- modeled demandかobserved trafficか。両者を同一columnへ混ぜない
- bear/base/bull各rateのauthority receipt hash
- raw row数、PII除外数、exact duplicate数、semantic cluster数、dedup後volume

### 6.2 dedup

1. queryをlocal staging内でUnicode NFKC、前後空白、連続空白、Latin case等のversion付き規則で正規化します。語を削って意味を変えません。
2. exact normalized queryを一意にします。
3. 「料金」「価格」等の同一需要を重ねる近似語は、測定前にfreezeしたcluster mapへ割り当てます。
4. 同一clusterを単純合計しません。sourceがunique reachを提供しない場合は、事前承認した保守的rule（例: cluster内最大値）を適用し、rule version/hashを残します。
5. 複数sourceのvolumeを足しません。metricごとのauthority優先順位をfreezeし、同一universeは1 sourceだけ採用します。
6. raw query文字列とcluster labelはL2に残さず、非PIIのquery/cluster hashとaggregateだけを残します。

`volume_is_deduplicated=true`は、上記の件数とdedup proofが存在する場合だけ設定します。

### 6.3 scenario

`deduplicated_search_volume`、`organic_visibility`、`rank_ctr`、`qualified_rate`、`outbound_click_rate`はすべて個別receiptを持つDecimalです。不明な率を埋めません。`bear <= base <= bull`になるよう並べ替えず、違反は入力labelまたは根拠の誤りとしてSTOPします。

需要volumeが0でもEvidence自体を0として記録できますが、positive bear demand gateはSTOPです。未観測を0とは記録しません。

## 7. Affiliate report → `CohortEvidence`

### 7.1 cohort境界

partner、territory、property、cohort start/end、snapshot time、currencyが同じeventだけを1 cohortにします。実partner/account/propertyは承認記録のhashで参照し、credential、affiliate URL、customer情報を含めません。

currencyは1 cohortにつき1つのISO 4217 codeです。異通貨は別batchへ分割し、JPYへ換算しません。JPY以外のcohortはJPY 200,000 readinessの代替になりません。

### 7.2 status mapping

sourceの全raw statusを、次の相互排他的bucketへmappingします。

|canonical status|意味|confirmed EPC分子|
|---|---|---|
|`pending`|未確定・locking中|含めない|
|`rejected`|取消、refund、fraud等で否認|含めない|
|`confirmed`|network上で確定、未払|含める|
|`paid`|支払済みの終端status|含める|

mapping tableにはsource status、canonical status、根拠、effective date、reviewer、versionを記録し、canonical JSONのSHA-256を保存します。unknown status、1 raw statusから複数bucket、同一transactionの同時二重計上はSTOPです。

transactionが`confirmed → paid`へ進んだ場合、snapshotでは`paid`だけに置きます。過去snapshotは上書きせず別Evidenceとして残します。pending/rejectedのclickを分母から除きません。

### 7.3 dedupとaggregate

- clickはapproved bot/internal/broken-link filter後の全valid clickを分母にします。filter version/hashを残します。
- click/transactionのstable non-PII IDをdomain-separated hashへ変換し、duplicate deliveryだけを除外します。
- 同一transaction hashで金額・currency・statusが衝突したらSTOPします。
- commissionはstatus別にDecimalで合計し、roundingやFXを行いません。
- cohort ageは`captured_at - cohort_start`の完了日数から算出し、Human入力値を信用しません。

valid clicksが0ならEPCはundefinedです。1,000 clicks未満かつ180日未満なら成熟判定は`WAIT`、180日時点で0 clickなら`STOP`です。0 EPCや無限大を生成しません。

## 8. Shadow operations log → `OperationsEvidence`

### 8.1 30日window

Phase 3は、`Asia/Tokyo`の開始境界を記録した連続30日、半開区間`[start_at, end_at)`で測ります。canonical timestampはUTCへ変換します。開始前event、終了以後eventを除き、途中の欠測日は削除せずmissed runとして扱います。

Phase 3のHuman budgetはこの30日windowに対して720分をそのまま適用し、短い観測から月換算してPASSを作りません。production移行後は暦月境界を別versionで定義します。

L3では開始境界を`observation_started_at`、評価時点を`captured_at`として保持し、`captured_at - observation_started_at`の完了日数から成熟度を導出します。30完了日未満は、数値が閾値内でもGate Dを`PASS`にせず、全体判定を`WAIT/CONTINUE`にします。

### 8.2 operations safe summaryの必須値

次のGate D入力のうち正式fieldはL3 `OperationsEvidence`へ格納し、全項目をL2 hash-only operations summaryへも含めます。`rollback_faults_total`と`rollback_faults_passed`はL3 statusの導出根拠としてL2に保持します。L3の`source_sha256`は、この全項目を含むL2のhashです。

|項目|格納先|算出規則|PASS条件|
|---|---|---|---|
|`observation_started_at`|L2 / L3|JSTでfreezeした開始境界をUTCへ正規化|`captured_at`まで30完了日以上|
|`human_minutes_per_month`|L2 / L3|活動ledgerの実秒数を重複区間統合後に合計し、最後に分へ切上げ。agent監督・例外対応を含む|`<=720`|
|`routine_tasks_total`|L2 / L3|開始前にfreezeしたeligible routine task instances。human-only approvalは別集計|`>0`|
|`routine_tasks_automated`|L2 / L3|開始から終了までhuman touchなしで完了したeligible instance|`automated/total >= 0.80`|
|`job_runs_total`|L2 / L3|schedule manifest上のplanned run全件。telemetry欠落・missed runも分母に含む|`>0`|
|`job_runs_succeeded`|L2 / L3|SLO内完了かつ後続validation合格のrunだけ|`succeeded/total >= 0.99`|
|`exceptions_total`|L2 / L3|distinct occurrence数。duplicate deliveryのみdedupし、同じ原因の再発は別件|`<=24`|
|`major_misstatements`|L2 / L3|window中に発生したmajor事象。解決済みでも発生件数に含む|`0`|
|`rollback_faults_total`|L2|開始前にfreezeしたfault catalogの必須case数|`>0`かつplanned数と一致|
|`rollback_faults_passed`|L2|rollback後のhash/schema/visibility/state復元まで確認したcase|`passed=total`|
|`rollback_test_status`|L2 / L3|上2値、planned数、復元validationから決定論導出|`passed`|

`rollback_test_status`は`RollbackTestStatus`を使い、L3の直列化値は`not_run / passed / failed`です。全planned faultを実施し、`rollback_faults_total > 0`、`rollback_faults_passed = rollback_faults_total`、かつ復元validation合格の場合だけ`passed`です。一部失敗または復元不成立は`failed`、未実施は`not_run`とします。手入力で`passed`へ上書きしません。

未観測を`exceptions_total=0`、成功率100%、`rollback_test_status=passed`にしません。30日未完了は`WAIT/CONTINUE`です。30日完了後の`job_runs_total=0`、`routine_tasks_total=0`、`rollback_faults_total=0`、観測欠落、または`rollback_test_status != passed`は、不足を補完せず`STOP`にします。実測された`exceptions_total=0`は、全event範囲のcoverage receiptによってゼロ件を立証できる場合だけ有効です。

### 8.3 event mappingとdedup

job statusは`planned / succeeded / failed / missed / cancelled_by_gate`を全source statusから一意にmappingします。`missed`と未記録のplanned runは失敗側です。意図的なgate停止は理由を残して`cancelled_by_gate`とし、成功へ数えません。

同一runのretryは`run_key`で1 planned runとして評価し、最終的にSLO内で合格したかを記録します。ただし副作用重複やretry起因incidentはexceptionから消しません。

exceptionは`run_key + canonical_error_code + occurrence_time_bucket`等のversion付きkeyでduplicate deliveryだけを除外します。同じerrorが別runで再発した場合は別occurrenceです。重大度を下げて件数を減らしません。

Human activityは非PIIのactivity type、start/end、role、ticket hashだけを使います。氏名や自由記述を残しません。重なる時間帯は同一Humanの実時間としてunionし、二重加算しません。

rollback faultはfault catalog ID、injected-at、pre-state hash、post-rollback state hash、validation resultだけを残します。log本文、secret、payload、実URLは残しません。8故障の実行対象がfreezeされている場合、8件すべての実施と合格が必要です。

## 9. 30日cadence

|時点|作業|成果|
|---|---|---|
|Day -2〜0|authority、rights、source、timezone、currency、dedup、status、routine denominator、schedule、fault catalog、expiryをfreeze|signed measurement manifestと各rule hash|
|Day 1|JST境界でwindow開始。planned run manifestを固定|start receipt、planned denominator|
|毎営業日|自動処理は継続。Humanはexception queueとrights/secret警報だけを10分以内で確認。正常log全文を読まない|activity ledger、ack hash|
|Day 7|週次integrity review。欠測、duplicate、未知status、時計ずれ、budget消化を確認|interim integrity receipt。GO判定には使わない|
|Day 14|同じschema/versionのまま中間反証。mapping変更が必要ならrunをSTOP|counterexample report hash|
|Day 15〜21|shadow環境でfreeze済みfault/rollbackを実行。観測runと区別する|fault receipt、rollback state hash|
|Day 21|2回目の週次integrity review。80%人手budget到達予測なら非重大作業を凍結|freeze/continue decision hash|
|Day 22〜29|定常性を測定。欠測を後日成功runで置換しない|append-only run/event hash|
|Day 30終了|`end_at`でwindowをcloseし、それ以降のeventを除外。L0→L2→L3を一度だけ変換|3 Evidence候補、safe summaries、QA packet|
|次の営業日|QA合格後にDossierを新規assembleし、readiness評価|GO/CONTINUE/STOP recommendationとHuman handoff|

週次値が良くても30日完了前はGate DをPASSにしません。途中の問題を直した場合も、問題eventを削除せず30日Evidenceに残します。

## 10. 停止条件

### 10.1 intakeを即時停止

- source rights、Affiliate approval、authority recordがない、期限切れ、またはscope不一致
- PII、secret、raw本文、実URL、credential、個人/顧客IDがL1/L2に残る
- source timezone、period、retrieval time、currency、version、expiryのいずれかが不明
- file/hash不一致、future timestamp、期間逆転、expiry非正、schema未知field
- stable dedup keyがない、同一hashが異なる値を持つ、source間の重複を単純加算している
- Affiliate statusにunknown/多重mappingがある、異通貨が混在、FX換算されている
- 30日途中でmetric、status、dedup、qualification、routine denominator、fault catalogを無承認変更した

### 10.2 有効Evidenceとして残し`WAIT/CONTINUE`

- 連続30日の観測windowが未完了。中間値は保存するが、閾値内でもGate Dを`PASS`にしない
- Affiliate cohortが1,000 clicks未満かつ180日未満で未成熟
- rollbackが未実施で`rollback_test_status=not_run`、かつ30日windowが未完了

### 10.3 成熟後または確定値で`STOP`

- demandのbear経路が正の必要qualified sessionsを満たさない
- Affiliate cohortの成熟時EPC<60 JPY、または180日でEPC undefined
- approved distinct affiliate partnerが3社未満
- Human >720分、automation <80%、major misstatement >0
- job success <99%、`exceptions_total > 24`、rollback faultが一部失敗
- 30日完了後のroutine/job/faultの分母0、`rollback_test_status != passed`、観測欠落

悪い実測値や成熟後の不足は入力errorではありません。値を除外・補正せず、正しいSTOP evidenceとしてhandoffします。

### 10.4 安全停止

secret/PII露出、権利失効、誤価格/誤順位、無承認writeを検知した場合はSEV0としてjobを止め、該当表示/CTAをfail-closedにし、Human Approverへ15分以内に通知します。incident本文を本Evidenceへ複製しません。

## 11. Handoff契約

### Human Approver → Evidence/Policy

渡すもの: signed measurement manifest、authority、rights/affiliate decision hash、対象期間・timezone・currency、local source receipt。raw fileはHuman領域から移動しません。

拒否条件: scope/期限/authority不明、raw取得権なし、実測開始時刻が未確定。

### Evidence/Policy → Contract/Storage

渡すもの: allowlist/denylist、safe staging receipt、dedup/status/freshness version/hash、quarantine件数、source receipt SHA-256。

拒否条件: PII/secret検査未完了、unknown mapping、raw column混入、authority/expiry欠落。

### Contract/Storage → TCO/QA

渡すもの: immutable L2 safe summary、L3 Evidence候補、schema/evidence version、canonical hash、変換件数、determinism test。

拒否条件: 同一inputでhash不一致、float/rounding、期間外event、分母自己申告。

### TCO/QA → Integration/Release

渡すもの: duplicate/conflict/currency/status/future/expiry/zero denominator/月外eventの反証結果、Gate D job/exception/rollback結果、未解決事項、`ACCEPT | WAIT | REJECT`。

拒否条件: counterexample未実行、重大誤表示候補、30日未完了をPASS扱い。

### Integration/Release → Human Approver

渡すもの: 新規Dossier hash、source Evidence hashes、最短expiry、gate別結果、rollback、月間人手残量。既存Dossierを上書きしません。

Human ApproverのGOは公開・課金・外部writeを自動承認しません。次phaseへのsigned decisionを別に発行します。

## 12. 完了checklist

- [ ] 3 sourceのauthorityとrightsがcurrent
- [ ] L0/rawがrepo、prompt、fixtureに存在しない
- [ ] PII/secret/URL/free textを除去し、PIIをhash化していない
- [ ] retrieval/source period/timezone/canonical UTCを記録
- [ ] currencyをcohort単位で固定し、FXなし
- [ ] status mappingとdedup ruleのversion/hashを記録
- [ ] demandはJP/ja、重複除去済み、各rateにauthorityあり
- [ ] cohortは全valid clicksを分母にし、pending/rejectedを分子に含めない
- [ ] operationsは連続30日で、`observation_started_at`、human/routine、`job_runs_total`、`job_runs_succeeded`、`exceptions_total`、misstatement、`rollback_test_status`あり
- [ ] L2に`rollback_faults_total`と`rollback_faults_passed`があり、`rollback_test_status`を決定論導出している
- [ ] routine/job/faultの分母0や未観測をPASSにしていない
- [ ] schema/evidence version、captured/expiry、source/safe summary SHA-256あり
- [ ] deterministic conversionとfault反証が合格
- [ ] EvidenceとDossierはappend-onlyで新規作成
- [ ] 外部送信、申請、fetch、公開を実行していない
