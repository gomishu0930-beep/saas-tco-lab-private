# P16 launch handoff sequencer

基準日: 2026-07-23

## 目的

P16 v3は、P18で受理されたP11–P21 local候補、権利、Affiliate、需要、shadow運用、gold/source、本番統合、公開前準備の
成果物を、一つの候補・property・environment・releaseへ結合するlocal-onlyの最終handoffである。
外部状態は変更せず、出力は`STOP | READY_FOR_FINAL_HUMAN_REVIEW`だけである。

`READY_FOR_FINAL_HUMAN_REVIEW`は事業GO、公開GO、deploy許可、provider write権限ではない。reportには
`authority_effect=none`、`permitted_use=final_human_review_input_only`、
`authorizes_external_mutation=false`、`requires_execution_boundary_revalidation=true`が必ず入る。

## 固定8ゲート

|順序|gate|署名role|固定artifact components|
|---:|---|---|---|
|1|local candidate acceptance|Human Approver|typed P18 repository acceptance authority bundle|
|2|rights approval|Human Approver|rights decision record|
|3|affiliate acceptance|Human Approver|affiliate decision record|
|4|qualified demand|TCO/QA|qualified-demand record|
|5|shadow operations|TCO/QA|shadow-operations record|
|6|gold-set/source readiness|TCO/QA|gold/source readiness record|
|7|production integration readiness|TCO/QA|P15 readiness report、P15 TCO/QA attestation|
|8|deployment/publication readiness|Human Approver|P10 local assurance、deployment readiness、publication readiness|

7番にはP15 Human environment approvalやbootstrap authorizationを含めない。8番にもP10 release
authorization、P11 grant、P13 dispatch tokenを含めない。これらは最終Human decision後に、各実行境界で
新たに検証するauthorityである。

## 契約

- trust storeはHumanとTCO/QAのEd25519公開鍵を分離する。policy、plan、receipt、bundleはtrust/policyを
  SHA-256で相互固定する。CLIへ渡すtrust root自体はrepo外の既知値と照合する。
- planは候補manifest、P18 authority-root pin、typed-semantic authority-root pin、property、environment、release identity/manifest/artifact、deployment candidate、provider target、expected pre/post state、rollback state、legal pages、Affiliate disclosureと、8件のrequirementを
  固定する。requirementはartifact componentの種類・順序・hash set、signer role/key、tool/command/subjectを
  固定する。
- receiptはordinalと直前receipt hashを署名対象に含める。bundle builderは順序をcanonical化するが、sortで
  不正な依存関係を修復せず、predecessor chainと時刻を別途検証する。
- receiptの完全一致重複もdedupせずSTOP。別payloadはconflict、同一ID横断再利用もduplicateとしてSTOP。
- future、exact expiry、policy TTL超過、plan前のreceipt、scope/artifact/key spliceはSTOP。
- Gate 1はP18 bundle hash、Human receipt、repository tree、manifestをcross-bindし、packet外から渡すconsumer-owned
  authority-rootとplan pinとP18 pins hashの三者一致を要求する。旧P11–P15 opaque componentはv3 schemaで表現できない。
- P18 authority-rootとは別に、P16 consumerは`plan + policy + trust store`から計算したP16 launch-handoff
  authority-rootをpacket外の既知値として渡す。攻撃者がP16 trust、policy、plan、全8 receiptを自己整合的に
  作り直しても、元consumerが固定したP16 rootとは一致せずSTOPになる。
- Gate 2–8は`LaunchSemanticPacket`のexact typed payloadをbundleへ埋め込み、別経路の
  `LaunchSemanticAuthorityPins`でpacket、P12 policy/trust/index/report、gold report/TCO key、P15
  plan/policy/trust/bundle/report/TCO attestation、P10 assurance、deployment/publication recordを個別固定する。
  typed packetまたは外部rootが欠落すれば7 gateすべてSTOPになる。
- public-key-only verifierはrights/affiliateを元行から再構築し、3 vendor/partnerと同一vendor setを要求する。
  P12 exact reportとBusinessDossierを再構築して需要・30日運用gateを再評価し、gold、P15、P10も元評価器で再実行する。
  P12 fault target、P15 plan、P10 local manifest、P13 request/dossierを同一release chainへ結び、component、evidence identity、subject、property/environment/release/manifest/deployment/target/state scope、最短expiryがreceipt requirementと
  一致しなければ後続gateを通さない。
- `synthetic_contract`が1件でもSTOP。checked-in fixtureはP18 bundleと全8 receiptがmissingのままSTOPである。

P16はまずpacket外のhandoff/semantic rootを照合し、Gate 1ではP18 evaluatorを再実行してexact Human GO/current
rootを検証する。この再評価にはP18 verification bundleへ結合されたStorage Auditor署名P19 consumption receiptも含む。
Gate 2–8は上記の業務的意味をconsumer時刻で再判定する。Gate 8のdeployment rowはP15のexact independent-readback/rollback evidence hash、P11 disable policy/authority root、stateを保持する。publication rowは直前deployment record hashとcontent、indexability、legal/disclosureの個別readbackを保持し、各観測がdeployment後・consumer時刻以前・最大live TTL内であることを要求する。法務・開示期待値はP16 planのconsumer-owned rootから固定する。両recordはP15 independent-probe公開鍵、`production_environment` provenance、最大live TTLで検証する。ただし外部事実そのものをローカルで
発生させる機能ではなく、実環境で得た署名recordを検証する契約である。実行時にはP13 request/dispatch token
v4がP9–P15に加えてP18/P16/semanticのpacket外rootと完全bundleをprovider subprocess直前に再検証する。signerの虚偽、
侵害されたprobe鍵・外部root、response receiptの取得元、probeが観測できないprovider内部の虚偽は別のHuman・provider・KMS・network信頼境界である。

## 現在の状態

`docs/P11_P18_LOCAL_ACCEPTANCE_PENDING.md`は履歴上PENDINGであり、現行P11–P21 scopeにもHuman receiptがないため第1ゲートを満たさない。rights 0/3、Affiliate
0/3、実JP需要、30日shadow、実gold/source、P15実環境証拠、deployment/publication readinessも未取得である。
したがってchecked-in P16 reportは`STOP`であり、事業・公開状態も`STOP`のままである。

## local CLI

```bash
uv run saas-preflight evaluate-launch-handoff \
  examples/p16/blocked/evidence-bundle.json \
  --plan examples/p16/blocked/plan.json \
  --policy examples/p16/blocked/policy.json \
  --trust-store examples/p16/blocked/trust-store.json \
  --expected-repository-acceptance-authority-pins-sha256 \
  00000000000000000000000000000000000000000000000000000000000001f4 \
  --expected-launch-handoff-authority-sha256 <consumer-owned-p16-root> \
  --at 2026-07-22T06:00:00Z
```

現在の期待値はexit code `3`と全8件missingのSTOP reportである。commandはlocal JSONと明示UTC時刻だけを
受け取り、socket、DNS、HTTP、subprocess、DB、provider、deploy、publish、output writeを持たない。READY候補を
評価する場合だけ、さらに`--launch-semantic-authority-pins`と
`--expected-launch-semantic-authority-pins-sha256`を渡す。片方だけ、またはbundleにtyped packetがなければSTOPする。

## Human再開手順

1. P18 manifestを独立Integration/TCO検証後にHumanがversion付きreceiptで受理し、current P18 authority-rootをpacket外のconsumerへ固定する。PENDING文書は履歴として変更しない。
2. 各外部gateのtyped upstream artifactを生成し、secretを含めないexact `LaunchSemanticPacket`へまとめる。
3. P16 plan/policy/trustとsemantic pinsを承認し、handoff rootとsemantic rootをpacket外のconsumerへ固定する。
4. gate順にrole署名receiptを作る。先行gateがSTOP/期限切れなら後続receiptを作らない。
5. P16を三つのconsumer-owned rootで評価し、review-readyでもHumanが全componentを確認する。
6. 外部操作ごとにP11/P13/P15等の短命authorityを新規発行し、実行直前に再検証する。
