# SaaS比較Affiliate 完成ロードマップ

基準日: 2026-07-23

## 完成の定義

本件の「完成」は、サイトが表示できることではない。次の6条件を同時に満たし、停止・復旧も再現できる状態とする。

1. 公開する全fieldに、取得、正規化保存、履歴、派生TCO、比較表示、最小引用、公開の有効な根拠がある。
2. 実利用可能なAffiliate広告主が3社以上あり、CTA、商標、広告表示、対象地域、期限が検証される。
3. 料金・上限・適合判定・12か月TCOがcanonical Python実装から生成され、重大誤表示が0件である。
4. `data / rights / affiliate`の最短期限をrequest/serve時に検査し、期限切れ数値・順位・CTAが自動非表示になる。
5. 定常90日で人手イベント比率20%以下、人手720分/月以下、job成功率99%以上を満たす。
6. 成熟したconfirmed 1,000 outbound clicksで新規獲得EPC 60円以上、または180日でSTOP/縮小を判断する。

月20万円は完成条件から逆算する。EPC 60円なら月3,334 confirmed outbound clicksが必要である。送客CTR 15%なら約22,227 qualified sessions、12%なら約27,783 sessionsが必要になる。これは目標式であり、実績値ではない。

## 全体経路

|Phase|目的|主owner|自動化できる部分|Human専有部分|出口|
|---:|---|---|---|---|---|
|0|規律・正本・供給網|Integration|schema、lock、test、scan|承認境界|完了|
|1|local決定論コア|Contract/TCO|validation、TCO、append-only保存|権利承認|完了|
|2|Preflight制御面|全role|release、TTL、CTA、例外、EPC、dry run|候補選択|実装・fixture合格|
|3|30日実証|Evidence/Human|dossier検査、集計、故障注入|許諾照会、Affiliate申請、需要入力|Gate A–D合格|
|4|許諾済みadapter/gold set|Evidence/Contract|approved fetch、parser、差分、quarantine|曖昧値確定|3社×6プラン|
|5|noindex公開前MVP|Integration/TCO|preview、release、rollback、security test|表示・広告・公開承認|公開前GO|
|6|production launch|Integration/Human|scheduler、DB、監視、serve-time TTL|account、credential、課金、deploy|公開・監視稼働|
|7|最大180日Traction|Economics/Human|KPI/cohort集計、STOP判定|施策・投資判断|拡大または撤退|
|8|月20万円scale|全role|例外だけ人手、月次release|新広告主・費用判断|持続条件維持|

## 現在地と完走キュー

|順序|現在状態|機械的入口|実装・自動処理|Human／外部入力|出口|
|---:|---|---|---|---|---|
|C0|local技術候補完成／business STOP|静止したP21 scope|741 Python lane assertion、197 schema、STOP fixture、Web・供給網・秘密検査|独立監査|P21 local closure|
|C1|`STOP`|3社分のfield-level rights、Affiliate acceptance、JP/ja需要export|P5/P8/P12契約で検査・quarantine|照会・申請・export承認|Gate A–C合格|
|C2|待機|C1合格sourceのみ|source別adapter、3社×6プランgold set、30日shadow|曖昧値label、運用例外判断|Gate D・P8合格|
|C3|待機|P15統合証拠とP16 handoff|noindex deploy候補、readback、rollback drill|domain/cloud/KMS/clock/anchor/provider承認|公開前Human review|
|C4|待機|P18受理と最終Human署名|限定公開、監視、serve-time expiry、kill switch|公開・広告・privacy承認|public MVP稼働|
|C5|待機|実P12 producerと公開MVP|連続30日cohort・operations・settlement集計|返金・欠測・例外review|automation 80%等を実測|
|C6|待機|成熟1,000 clicksまたは最大180日|P17がEPC・純利益・capacityを厳密判定|継続／撤退判断|scale reviewまたはSTOP|
|C7|待機|`READY_FOR_SCALE_REVIEW`とHuman承認|月次release、異常時自動STOP|費用・新partner判断|月20万円純利益を持続確認|

C0の合格はC1以降の実績を生成しない。現在の直接値はrights 0/3、Affiliate 0/3、実観測0であり、
public・production・business・scaleはすべて`STOP`である。

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
- 月20万円に必要なclick/session、3社gate、EPC60円、人手720分を同じreadiness reportで判定。

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

## Phase 3 — 30日Preflight実証（Human入力待ち）

### Gate A: rights

対象候補をSE Ranking、Mangools、Serpstatから開始し、Semrush、HubSpotは冷開始条件と審査を別管理する。各社について次を権限者または契約文書で確定する。

- 対象domain、plan/field、region。
- API/feed/manual/browserの許可methodと頻度。
- 正規化値、短い根拠、raw archive、履歴の保存期間。
- 競合比較、派生TCO、Web/X表示、商標・logo、attribution。
- 契約終了・撤回時の非表示・削除期限。

Human action: 問い合わせ送信、回答者権限の確認、承認scope/期限の署名。一般FAQだけで`approved`へしない。

現在地: 5社の同一8項目照会は、公開名義`omishu`、公開予定URLは未公開として
2026-07-23に送信済み。送信receiptは許諾ではないため、回答・Human判定まではrights 0/3のまま停止する。

Exit: 公開予定fieldの100%がapproved/prohibitedに確定し、unreviewedが0。3社未満ならSTOP。

### Gate B: affiliate

Human action: 専用事業mail/accountで申請し、program ID、対象site、報酬、cookie、region、広告表示、商標、deep link、tracking、失効条件を記録する。

現在地: Mangoolsは2026-07-26に無料account作成・Affiliate section・紹介ID発行まで確認済み。
ただしrights回答と対象siteの承認記録がないため、Gate Bではまだ未承認として0/3に数える。
SE Rankingはaccount/Agreement発効前、HubSpot Impactは契約checkbox前まで準備済み。

Exit: 実利用可能3社。申請中は0.5社として数えず0社扱い。単一広告主依存60%超見込みなら拡大保留。

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

## Phase 4 — 許諾済みadapterと3社×6プランgold set

Entry: Gate A/Bを合格したsourceだけ。

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
- `uv.lock`と`site/package-lock.json`だけから、networkなしでCycloneDX 1.6 SBOMを決定論生成する。651 components・651 graph nodes、lock hash、purl、利用可能な配布物hash、npm licenseを保持し、credential URL・絶対path・timestampを拒否する。
- synthetic-local 5 routeで、document metadata、landmark、skip link、internal link、table semantics、広告説明、無効CTA、900/620px reflow、keyboard focus、reduced motion、canonical/JSON-LD/public origin不在を検査する。
- 13の必須checkごとにfacts種別、tool/version、command/subject hashをpolicyへ固定し、controller-role runnerが型付きfactsへ署名する。件数、coverage、exit code、determinism、finding、future、expiry、最大TTLをcheck別に再計算し、全件合格だけを`local ready`とする。
- `public GO`には、local reportへ結合したTCO/QA署名、exact BusinessDossierとmanifest全snapshot完全listへ結合したHuman署名、事業`GO`、manifestとのrights/Affiliate/demand/cohort/operations binding、current CTA/expiryを全て要求する。local readyをpublic GOへ読み替えない。
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
- 現在fixtureはsynthetic/unsignedのため`STOP / local_verification`。P18 acceptedでも次はrights evidenceであり、
  public/production/affiliate/spend/scale authorityは全てfalseである。

詳細は`docs/P18_REPOSITORY_ACCEPTANCE.md`と`docs/P18_ACCEPTANCE_TESTS.md`を参照する。

画面:

- 方法・更新日・region/tax/currency/commitmentを常時表示。
- サイト数、keyword数、seat、監査page、AI tracking条件の代表scenario。
- TCO、適合/非適合理由、根拠URL、期限。
- 広告であることを判断箇所の近くに表示。Affiliate linkは`rel="sponsored"`。
- filter/sort/query/空結果/個別入力はnoindex。canonicalは代表pageだけ。

公開前gate:

- threat model、secret/SBOM/dependency scan、accessibility、mobile、structured data、robots/canonical。
- expired release、affiliate invalid、scheduler停止、DB破損、rollbackのE2E。
- Human signed `GO | STOP | CONDITIONAL`。GOまでは公開URLを作らない。

## Phase 6 — production launch（別承認）

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

判定は累積1,000 valid outbound clicksまたは連続180日の早い方。EPCはsettlement amendment適用後の
new-acquisition settled額を全valid clickで割る。最新30日売上・CTR・partner集中・運用品質と累積EPCを混ぜない。

- Scale review候補: settled new-acquisition EPC≥60円、最新settled売上≥20万円、bear capacity、
  site→merchant CTR≥10%、3社以上、最大partner share≤40%、automation≥80%、job≥99%、重大誤表示0、人手≤720分。
- Continue: sample不足かつhard operations合格。成功扱いせず、追加投資は新しいHuman decision。
- Stop/縮小: EPC<60円、3社未満、rights失効、薄い再掲しか作れない、人手超過。

local出力は`READY_FOR_SCALE_REVIEW`までで外部authorityはない。詳細は`docs/P17_TRACTION_SCALE_CONTROL.md`、
境界は`docs/P17_BOUNDARY_MATRIX.md`を参照する。

## Phase 8 — 月20万円scale

優先順位:

1. qualified率と送客CTRを改善し、必要trafficを減らす。
2. confirmed EPCの高いmerchant/scenarioを増やす。ただし単一広告主依存40%未満を目標。
3. 実測で価値があるsource/fieldだけ増やす。
4. parser不能20%以上または確認4時間/月超で初めて抽出AI 1社をA/Bする。
5. 2 provider、90日、1万req/月またはAI費5万円/月になるまでgateway/MCPを入れない。

月20万円達成後も、権利・品質・人手gateを破る拡大は行わない。

## 現在の停止点と再開条件

credential-free実装はP21 typed launch semanticsまで進み、P13 exact one-shot execution port、P17 bounded
file-lock/anchor、authenticated plan storage v2を追加した。現在の外部順序はP18 `local_verification`、Human
repository acceptance、rights evidenceである。外部入力と分離して、
typed task/activity evidenceによるautomation 80%・人手・運用TCO・純利益の再計算と、immutable P18 verification
runner V2、Storage Auditor署名consumption receiptのP18→P16→P13 binding、store固定/durable-freeze replay consumer、credential-blind P17 broker、P13の署名clock/current-root再取得・provider後時刻・P18/P16実行直前再検証は実装した。P21はrightsからpublicationまでの型付き上流証拠を再計算し、P16 receiptの正しい署名だけではREADYにならない。P13 request/token/current-rootにも意味packetとpacket外rootを固定した。実quote/CASとproduction clock/anchor/current-root serviceは環境engineering backlogとして残る。real adapter、実環境11証拠、30日実証、公開、
実tractionは外部stateを変えるため、個別Human承認まで進めない。

形式的なrepo承認記録はP0–P10までである。P11–P21は監査対象のworking-tree候補であり、local統合へ進める
前にP18 manifest/verification/authority-rootへHumanがrevision付きdecisionを署名する。既存P11–P17 PENDING票は
履歴として変更しない。これは実環境・公開・scale承認ではない。

1. 対象3–5社の優先順位。
2. 各社rights回答または契約根拠。
3. Affiliate承認結果と公開可能な条件（secret/ID本体はrepoへ入れない）。
4. 重複除去済み需要dataset。
5. production時のdomain/account/billing/deploy承認と、P15 exact 11証拠を採取する実環境・role/KMS/anchor
   のidentity hash。

これらがなくても再検証と保守はできるが、synthetic/local範囲を実環境・公開へ拡張しない。
