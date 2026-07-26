# Readiness production input contract

`BusinessDossier`は手編集する入力票ではない。旧`assemble-readiness`はunsigned diagnostic
互換経路であり、production authorityではない。P12以後の計測authorityは
`assemble-signed-readiness`が作る`MeasurementBoundDossier`で、consumer固定のpolicy、
trust root、run、exact bundle-index hashを再検証する。rights/Affiliateと合わせる正本は
次の5種類である。

|入力|正本|Dossierへ入る値|禁止する内容|
|---|---|---|---|
|rights|1件以上の`VendorPlan`と全`EvidencePointer.source_policy`|承認可否、対象vendor、bundle SHA-256、最短期限|自己申告bool、期限延長の推測|
|affiliate|`AffiliateDecisionBatch`|distinct partner ID、vendor、bundle SHA-256、最短期限|live URL、credential、Cookie、同一vendorの件数水増し|
|demand|`DemandEvidence`|重複除去済みbear/base/bull scenario、source SHA-256、期限|X投稿数だけの需要推定、float、出典なし推定|
|cohort|`CohortEvidence`|valid click、status別commission、mapping SHA-256、期限|pendingをconfirmedへ算入、異通貨の黙示換算|
|operations|`OperationsEvidence`|分から計算した人手時間、task分子/分母から計算した自動化率、30日観測、job成功率、例外数、rollback、重大誤表示|率や時間の自己申告、分母0を100%扱い、未実施rollbackの合格扱い|

## Rightsの成立条件

全planの全field pointerについて、組立時点で`derive`、`publish`、`retain_history`が明示的にapprovedでなければ`rights_approved=false`になる。policy review期限または保持期限そのものが切れている場合は、古いSTOP票を作るのではなく組立を拒否し、再審査へ戻す。`fetch`は`EvidencePointer`作成時点ですでに明示承認を要求する。

## Affiliateの成立条件

審査記録には対象property domain、territory、review window、reviewer、decision-record SHA-256を持たせる。approvedだけがprogram ID、destination hash、disclosure hashを持てる。リンク先そのものや秘密情報は入力JSONへ保存しない。approved vendorには対応する`VendorPlan`が必要であり、同一vendorの複数programで3社gateを水増しできない。

## 実行順

1. Human ApproverがrightsとAffiliate審査記録をscope・期限付きで確定する。
2. Evidence/Policy Stewardがplan policyとhash-only decisionを作る。
3. repo外でraw exportからPII/secret/raw本文を除去し、3種類のL2 safe summaryを作る。
4. Diagnosticだけなら`aggregate-demand`、`aggregate-cohort`、`aggregate-operations`で
   unsigned L3 Evidenceを新規生成する。これはproduction authorityへ渡さない。
5. P12 authorityでは、開始前plan、3 producer attestation、事後indexを固定runtimeへ同時に
   渡し、TCO/QA署名`MeasurementIntegrityReport`を生成する。
6. `assemble-signed-readiness`でconsumer固定pinを検証し、`MeasurementBoundDossier`を
   一度だけ書き出す。`assemble-readiness`はdiagnostic専用である。
6. `evaluate-readiness`でfreshnessを先に、経済性を後に判定する。
7. STOPなら失敗したgateだけを更新し、既存Dossierを上書きしない。

JSON Schemaは上記Evidence/Dossierに加え、`demand-summary-batch.schema.json`、`cohort-summary-batch.schema.json`、`operations-summary-batch.schema.json`を正本modelから生成する。
