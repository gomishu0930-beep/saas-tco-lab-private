# Offline control cycle / dead-man lease runbook

基準日: 2026-07-22

## 目的と禁止境界

`evaluate_control_cycle`は、既存のBusiness dossier、GoldSetReport、ReleaseState、
SchedulerHeartbeat、ExceptionQueue、当月Human budgetを、1回分のread-only判断へ束ねる。
外部fetch、DB/file write、scheduler操作、promotion、rollback、deploy、公開、Affiliate URL変更は
行わない。`human_approval_required`もpromotion命令ではなく、Human Approverへの停止点である。

## Ownerと入力

|Artifact|作成/確認owner|control cycleでの扱い|
|---|---|---|
|BusinessDossier|Integration / Human|評価時刻で鮮度とcanonical economicsを再計算|
|GoldSetReport 1.1|TCO/QA / Human labels|report hash、rights binding、candidate hash、鮮度、quarantineを再検証|
|GoldReportAttestation|TCO/QA|別roleのEd25519鍵でreport/rights/candidate hashと期限を署名|
|ReleaseState|Integration / Human promotion|current pointerを変更せず、visibilityとmanifest bindingを再検証|
|ReleaseDecisionAttestation|Human Approver|別鍵でcurrent event/release/manifest/decision recordと期限を署名|
|SchedulerHeartbeat|Integration|future、TTL、次回期限、最大間隔を検査|
|ExceptionQueue|各owner / Integration|未解決SEV0/SEV1だけをcontrol gateへ反映|
|MonthlyHumanBudget|Integration|UTC当月、576分freeze、720分limitを検査|

入力と出力にはcredential、URL、source excerpt、Affiliate destination、raw exception summaryを
渡さない。例外はfingerprintと件数、release/evidenceはSHA-256で結合する。

## 判定優先順位

1. `stop`: dossier不正/STOP、report改変、parser failure STOP、rights・Affiliate・candidate
   binding不一致、open SEV0、720分枯渇、future/hidden/expired current release。
2. `hold`: dossier CONTINUE、heartbeat/reportのfuture・stale・lag、gold未合格、open SEV1、
   当月budget不在/不一致。
3. `human_approval_required`: 上記がすべて合格し、current releaseだけが無い。
4. `maintain_current`: 合格済みcurrent releaseの維持のみ。この場合だけServingLeaseを出す。

576分到達は新規sourceと非重要改善のfreezeであり、既存currentを維持するleaseは止めない。
720分到達は`stop`。期限境界はすべて半開区間で、`at == expires_at`は失効とする。

## Hash bindingとlease期限

currentがある場合は次を同時に満たす必要がある。

- `dossier.provenance.rights_bundle_sha256 == gold_report.rights_bundle_sha256 == manifest.rights_bundle_sha256`
- `dossier.provenance.affiliate_bundle_sha256 == manifest.affiliate_bundle_sha256`
- `gold_report.candidate_batch_sha256`が`manifest.data_snapshot_sha256s`に含まれる
- current manifestのartifact、release visibility、全expiryが評価時刻で有効

ServingLease v2はissuer、controller key ID、scope、control input hash、release ID、manifest hash、
artifact hash、発行/失効時刻を完全なcanonical payloadとしてEd25519署名する。
TCO/QA、Human、controllerの公開鍵は`ControlTrustStore`の別role・別key IDに固定し、秘密鍵は
実行時objectとしてだけ渡す。秘密鍵をmodel、JSON、repo、log、input/report hashへ保存しない。
Configは全issuer/role/key ID/public keyを含むcanonical `trust_store_sha256`をpinするため、callerが
Gold/Human鍵だけを差し替えたTrustStoreは、署名自体が正しくても`stop`となる。
Config・TrustStore・controller signerはtrusted bootstrapで一度だけ`ControllerAuthority`へ封じる。
cycle evaluatorはAuthorityだけを受け、個別config/trust/signer引数を持たない。AuthorityはPydantic
modelではなく、serialize/pickleを拒否し、reprではsignerをredactする。controller秘密鍵または
構築済みAuthorityを取得できる主体はこの境界の外ではなく、controller trust boundaryそのものである。
期限は、設定lease、heartbeat TTL、次回schedule + grace、dossier最短expiry、gold evidence/
report TTL、release最短expiryの最小値。`ControlledMvpRuntime`はprotected routeでleaseが無い、
署名不正、issuer/key/scope/最大TTL不一致、future、失効、別release/manifest/artifactの場合に、
保護データを含まないgeneric 503を返す。
`/healthz`と`/robots.txt`はleaseなしでも固定の非機密応答を返す。

`LocalPreviewRuntime`は名前どおりlocal test専用で、moduleのproduction exportから除外する。
Sites workerは署名検証adapterが別承認で実装されるまで、health/robots以外を常時503にする。
Sitesの`npm run dev`/`build:local`だけは明示的な`synthetic-local` workerを選び、noindex・CTAなしの
合成fixture UIを表示する。通常`build`/`start`はproduction workerを選ぶ。`npm test`は両方を別buildする。
production Cloudflare assetsは`run_worker_first: true`でworkerを必ず通し、実`npm run start`/workerd
HTTP testでbuilt JavaScript、favicon、image routeを含む全assetが503になることを確認する。

## Pinned Ed25519 dependency

`cryptography==49.0.0`をruntime dependencyと`uv.lock`へexact pinした。採用根拠はPyPI verified
publisher、`Apache-2.0 OR BSD-3-Clause`、Python 3.14対応wheel、Ed25519 public APIである。
lockはsdist/wheel URLとSHA-256を固定する。private keyはtestで実行時生成しfixtureへ保存しない。

## Local handoff

schemaはPydantic modelが正本であり、JSON Schemaを手編集しない。

```bash
uv run pytest tests/test_control_cycle.py tests/test_goldset.py tests/test_mvp.py -q
uv run pytest
uv run python scripts/export_schemas.py --output-dir schemas
uv lock --check
uv run python -m compileall -q src tests scripts
```

handoffにはControlReport JSON、入力artifactのSHA-256、評価UTC時刻、lease expiry、test/schema/
scan結果、未解決reason、ownerを含める。会話やAI要約をHuman approvalとして扱わない。

## 外部化前のHuman gate

実scheduler、secret store、HTTP adapter、DB、cloud、production domainへの接続は別承認である。
本runbookの結果は外部操作を許可しない。Human Approverだけがproduction write、公開、rollback、
credential、課金、Affiliate destination変更を承認できる。
