# P12 署名付きmeasurement integrity

## 結論

P12のproduction-authority経路は、`SignedMeasurementRunPlan`、dataset別
`ProducerAttestation`、`MeasurementBundleIndex`、固定
`MeasurementIntegrityRuntime`、TCO/QA署名済み
`MeasurementIntegrityReport`の順です。従来の`aggregate-*`と
`assemble-readiness`は合成fixture・算術診断用であり、単独ではproduction証拠に
なりません。

この実装はnetwork、credential、外部account、Affiliate URL、実価格、実績値を
扱いません。現在の事業・公開判定は引き続き`STOP`です。

## なぜ事前planと事後indexを分けるか

測定開始前にdefinitionを固定することと、終了後に生成されるexact batch hashを
同じ文書へ入れることは同時にできません。結果を見た後のHuman署名は、都合のよい
runだけを採用するcherry-pickingを許します。

```text
Human MEASUREMENT_HUMAN key
  └─ SignedMeasurementRunPlan（開始前、意味・期間・source・ruleをfreeze）
       ├─ demand producer ─────┐
       ├─ cohort producer ─────┼─ signed batch attestations
       └─ operations producer ─┘
                                ↓
                    MEASUREMENT_INDEXER key
                    exact batch/attestation index
                                ↓
                    fixed TCO/QA runtime/key
                    signed integrity report
                                ↓
                    MeasurementBoundDossier
```

Humanは意味とscopeだけを承認し、測定結果やbatchの選択を署名しません。Indexerは
結果の意味を変更せず、exactな3 batchと3 attestationを閉じます。TCO/QA runtimeは
再計算だけを行います。6 roleのEd25519 key IDはすべて別でなければなりません。

## 事前freeze

`MeasurementRunDefinition`は次を固定します。

- run、policy、trust store、property、JP/ja/JPY、Asia/Tokyo
- 半開区間の30日window、需要source month、対象partner集合
- demand/cohort/operationsのmeasurement versionとsource authority receipt
- qualification、session identity、需要dedup、valid outbound filter、event/transaction
  dedup、attribution、status transition、refund/chargeback、new acquisition、payout
  reconciliationのrule hash
- routine inventory、job schedule/status、retry identity、exception dedup、human-time
  union、QA、fault catalog、privacy minimizationのrule hash
- exact 8 fault IDと各definition hash

Planは開始時刻より前にHuman keyで署名され、run終了より後までcurrentであり、downstream
policyが許すTTL内でなければrejectします。`HOLD`と`STOP`のplanからEvidenceは生成
しません。署名timestampだけでは実世界のtrusted timestampを証明できないため、実運用
ではP13のdurable timestamp/anchorへ接続します。

## producerとcoverage

各producerは自dataset以外へ署名できません。Attestationはplan、policy、property、
source authority、measurement version、canonical batch hash、完全export receipt、
coverage rule、privacy scan receipt、issued/expiryへ署名します。Coverageは単一の合計では
なく、session、valid outbound、Affiliate accepted、transaction、status event、payout、
operation day、logical run、faultごとのinput/output/reject/duplicate/conflict/unknown件数と
identity-set rootを持ち、runtimeがbatch全行から再計算します。

Coverage件数と署名は、信頼済みproducerが完全exportを処理したという主張を固定します。
外部networkの真正なexport署名や完全性APIを代替しません。実producer identityとAPIは
Human承認後のP13接続事項です。同じsource receiptのままproducerが行を省略しcoverage
rootも再署名する攻撃は、consumer固定indexの無断rotationを拒否して止めますが、正規
producer・indexer・consumer pin管理者の共謀まではlocal contractで証明できません。実source
のsigned complete-export root、KMS role分離、append-only pin logが接続されるまでGate C/Dの
実測真正性は未充足です。

## cohort・EPC・payout

P12 cohortはpartner別金額bucketを正本にしません。hash-onlyの次のledgerから再計算
します。

- qualified session → valid owned outbound click → Affiliate accepted click → current
  transactionの親子membership
- transactionごとの一意ID、cohort、partner、currency、acquisition evidence、
  append-only status events、exactly one current status
- current paid transactionと1対1のpayout row
- paid後の全額refund/chargeback adjustment
- gross、reversal、fee/tax/withholding、net、paid transaction set hashを持つstatement

親ID不明、partner不一致、期間外、重複、1 clickから複数transaction、status逆行、
unknown acquisition、payout欠落/orphan/金額不一致、部分refundはrejectします。現契約は
部分refundを推測せず、必要なら新schema/rule versionをHumanが開始前にfreezeします。

```text
confirmed EPC numerator
  = new acquisitionかつcurrent confirmed/paid、未reversalの金額

confirmed EPC denominator
  = cohort内の全valid owned outbound clicks

net payout EPC
  = reconciled statement net / 同じ全valid outbound clicks
```

pending、rejected、refunded、charged-back、existing acquisitionはconfirmed EPC分子へ
入りません。非転換clickやprovider未match clickを分母から落としません。paidはstatus
上terminalのままにし、post-paid reversalを別append-only adjustmentにします。

hash-only IDは匿名情報とはみなしません。実IDがPII/customer-linkedの場合はhash化して
repoへ保存せず、承認済み隔離領域でmembership検証し、repoには最小commitmentと署名済み
aggregateだけを渡します。本moduleのrow fixtureは合成値だけです。

## operationsとexact 8 faults

件数`8/8`だけでは合格しません。次のmachine IDをこの順序で各1件要求します。

1. `fi-01-price-change`
2. `fi-02-plan-rename`
3. `fi-03-billing-period-change`
4. `fi-04-currency-change`
5. `fi-05-quota-overage-change`
6. `fi-06-source-conflict`
7. `fi-07-affiliate-expiry`
8. `fi-08-fetch-failure-duplicate-delivery`

各`FaultExercise`はdefinition、unique run、注入/復旧時刻、pre/fault/restored state、
validation receipt、resultを持ちます。FI-08のdefinitionはfetch failureとduplicate
deliveryの両subcaseを含める必要があります。ID欠落・反復・置換、古いdefinition、
passedなのにpre stateへ戻らない入力はrejectします。P12 authority reportは8件すべてが
成功した場合だけ発行します。失敗receipt自体は上流の監査領域へ保持しますが、L3 Evidence
や`MeasurementBoundDossier`へ昇格しません。

Job成功率はdelivery attempt数ではなく、unique `LogicalJobRun.run_key_sha256`を分母に
します。retry receiptが複数でも1 logical runです。日次job countとlogical-run ledgerが
一致しなければrejectします。

## 事後indexとruntime

Indexerはrun終了後、exact 3 batch hashとexact 3 producer attestation hashを1つの
`MeasurementBundleIndex`へ署名します。Runtimeは次を同時に再検証します。

- consumerが別管理するexact policy/trust-root/run/bundle-index hashと6 distinct roles
- plan/index/producer/TCO signature、issuer、key ID、scope、future、exact expiry、TTL
- run/property/locale/currency/window/source/month/version/rule/authorityの一致
- batch、attestation、indexのexact hashとcoverage件数
- funnel membership、current transaction、new acquisition、payout/adjustment/statement
- logical job denominatorとexact 8 fault ledger

1つでも真正性、coverage、fault restoreまたはreconciliationが壊れればEvidenceをemit
しません。真正で完全だがEPC不足、job成功率不足等の悪い実測値は署名済みEvidenceとして
emitし、既存経済gateが`STOP`を返します。

`MeasurementBoundDossier`は署名report本体とDossierを同梱し、需要、cohort、operations
の全派生fieldとsource hashがreportに一致することを再検証します。P13 production
consumerは裸の`BusinessDossier`や従来L3 Evidenceを受け取らず、このbundleと固定policy/
trust storeを検証する必要があります。

## 実装済みと未接続

実装済み:

- strict Pydantic contracts、timezoneをUTC正規化するcanonical hash、Ed25519 role separation
- 事前freeze、3 producer attestations、事後index、固定runtime、TCO署名report
- row-level synthetic funnel/current transaction/payout/adjustment再計算
- logical-run分母、exact 8 fault identity、signed report-bound dossier
- stage別coverage root、因果時系列、global receipt uniqueness、日別logical-run照合
- consumer側exact index pinとsigned-report-bound dossier/CLI
- future/expiry/TTL/wrong key/role/tamper/overlap/denominator/payout/fault反証test

未接続・承認待ち:

- 実source rights、実Affiliate提携、実provider producer keys/export signatures
- 実30日JP cohort、需要、operation ledgerと隔離secure store
- KMS/HSM、trusted timestamp、durable transparency log、shared replay/fencing
- P13 out-of-process consumer、global STOP latch、実deploy/公開

これらがないため、P12 local contractの完成は市場性、提携可否、EPC、月20万円達成を
証明しません。
