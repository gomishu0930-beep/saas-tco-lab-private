# P15 本番統合準備・照合ゲート

基準日: 2026-07-22

## 目的

P13/P14のlocal synthetic consumerが合格しても、実provider環境の安全性は証明されない。P15は実providerへ
接続する前に、provider mutation、周辺基盤、復旧手順について、exact planへ結合した型付き・期限付き・
役割分離署名の証拠を要求する。

この実装はURL、endpoint、account、credential、API key、OAuth、deployment commandを受け取らず、network
clientや外部write commandを持たない。`synthetic_contract`証拠は11件が揃っても必ず`STOP`である。

## 判定レベル

|入力|判定|意味|
|---|---|---|
|missing、duplicate、conflict、failed、future、expired、wrong binding/signature|`STOP`|activation不可|
|11件の合成証拠|`STOP / synthetic_evidence`|contract配線testだけ|
|11件の実環境形証拠|`READY_FOR_HUMAN_GATE`|外部write権限ではない|
|上記report + TCO/QA ACCEPT + Human APPROVE|controller authorization候補|exact report/plan/environmentだけ|
|P13 request/tokenへ結合し、全実行fenceでcurrent|activation候補|P9–P13の全authorityも別途必要|

waiver、conditional approval、self-attested `passed=true`、件数だけの合格経路はない。

## exact production plan

`ProductionIntegrationPlan`は次をSHA-256だけで固定する。

- property、environment、provider account identity。
- P11 policy/store、P13 policy/store。
- release artifact/manifest。
- adapter/probe executableとdependency closure。
- provider capability profile、deployment candidate、provider target、expected pre-state。
- exact 11 evidence identity、collector role/key、tool/version、command/subject。
- `issued_at <= not_before < expires_at`。

plan側はthresholdを変更できない。thresholdの正本はhash固定された`ProductionIntegrationPolicy`だけである。

## 11 checkと初期threshold

|check|導出する合格条件|
|---|---|
|provider conditional mutation|matching conditionのeffect 1、stale/lower fenceのeffect 0、concurrent winner 1、replay side effect 0|
|provider idempotency retention|同一key・同一requestは同一audit/receiptでside effect 0、同一key・異requestは拒否かつside effect 0、retention 30日以上|
|provider receipt lookup|known lookupがexact receipt、別queryのunknown lookupが明示NOT_FOUNDでmutation 0、lag 60秒以下|
|independent readback|adapterとreader identity分離、expected stateとexact一致、lag 60秒以下|
|KMS identity separation|provider/probe/controller/runnerの4 identity分離、pairwise 6/6、non-exportable|
|external monotonic anchor|storeと別identity、revision増加、rollback/equivocation/replay拒否、authoritative readback|
|trusted clock|3 source・2 failure domain、`abs(offset)+uncertainty <= 1000ms`、backward/future 0|
|shared durable store/fencing|8 worker・3 failure domain、winner 1、stale reject 7以上、unfenced write 0|
|egress allowlist|approved destination identityだけ、DNS/private/metadata/wildcard反証、unapproved success 0|
|backup/restore|snapshot/head/journal/anchor exact、isolated target、production pointer不変、RPO 900秒/RTO 3600秒、resume gap 0|
|rollback/disable|activeとdisabledの実state差、P11 authority/provider receipt/独立probe、RUNNING/STOP lane、300秒以内、post-disable activation/retry 0|

anchor、clock、shared store factsの最大TTLは300秒。他の通常証拠とrecovery証拠はpolicyの別上限を使う。
reportとcontroller authorizationはplan期限より後へ延長できない。境界はhalf-openで、
`at == expires_at`は失効である。

## 署名role分離

trust storeは次の10鍵を全て別key IDとして要求する。

1. controller
2. provider conformance
3. independent provider probe
4. security auditor
5. storage auditor
6. time auditor
7. network auditor
8. recovery auditor
9. TCO/QA
10. Human environment approver

checkごとの期待role/keyはplan requirementへ固定される。provider conformance鍵でclockやbackupを署名する
role splice、TCO/QAとHumanの鍵再利用、controller自己承認は拒否する。

## P13 activationへの結合

`ProductionConsumerPolicy` v2はP15 policy/trust store hashとreconciliation ledger store IDを固定する。P15
planも同じledger store IDを固定し、runtimeは実ledgerのstore/trustを照合する。activation用
`ProductionConsumptionRequest` v2と`ProviderDispatchToken` v2は次を保持する。

- `production_integration_plan_sha256`
- `production_readiness_authorization_sha256`

runtime bootstrapはP15 plan v2がexact P11/P13 store/policy、property/environment、release、adapter/probe closure、
capability、deployment candidate、provider target、expected pre-stateを指すことを再検証する。claim、redeem、provider call直前、probe直前、terminal
successでauthorizationを再検証する。dispatch expiryはP15 report/authorizationより後にならない。

P15 expiryはactivationを止めるが、P11で新たにHuman承認されたdisableはP15 activation authorityを持たず、
sticky STOPをclearしない安全レーンとして維持される。

## UNKNOWN後の照合

照合の入力stateは`UNKNOWN | STOP`だけで、`SUCCESS`という入力・昇格経路を持たない。output decisionは常に
`STOP`で、推奨actionは次の3つだけである。

- `keep_stop`
- `request_human_disable`
- `manual_remediation`

recovery auditorが署名したfactsは、P14 provider journalとは別の`ProductionReconciliationLedger`へ保存する。
ledgerは次を持つ。

- strict SQLite schema、update/delete trigger拒否。
- HMAC state MAC、record hash-chain、revision/head。
- 別callbackのexternal monotonic anchorとexact one-ahead recovery。
- exact duplicateはrevision/anchor不変。
- 同一P13 resultへのconflicting factを拒否。

P13 global STOP resetは、現在のP13 store、stopped revision/head/reasonと一致し、currentで署名有効かつ
独立readbackで`NOT_APPLIED`を確認した`keep_stop` ledger recordを取得できなければ拒否する。`APPLIED`の
`request_human_disable`や`AMBIGUOUS`の`manual_remediation`はreset不可である。任意の64桁hashをHumanが
署名するだけでもresetできない。

## local CLI

blocked fixtureは次で再現する。exit code `3`が期待値である。

```bash
uv run saas-preflight evaluate-production-readiness \
  examples/p15/blocked/evidence-bundle.json \
  --plan examples/p15/blocked/plan.json \
  --policy examples/p15/blocked/policy.json \
  --trust-store examples/p15/blocked/trust-store.json \
  --at 2026-07-22T03:00:00Z
```

`evaluate-production-reconciliation`もlocal JSONと明示UTC時刻だけを受け取り、常にSTOP reportを返す。
両commandはsocket、DNS、HTTP、subprocess、provider、DB mutation commandを持たない。duplicate JSON keyは
validation前に拒否する。

## 非保証事項

local P15合格は、実KMS availability、remote linearizability、provider mutationとreceiptの原子性、cloud全障害、
時刻源の真実性、out-of-band管理者操作、実backup/restore、実egress、P11/P13/providerの分散transactionを
証明しない。P15 authorization自体もprovider credentialや外部操作権限ではない。実環境で採取した11証拠、
別Human decision、account/credential配置、deploy/publish approvalが別途必要である。
