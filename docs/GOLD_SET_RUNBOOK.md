# Gold set / Candidate Quarantine Runbook

基準日: 2026-07-22

## 目的

Phase 4で承認済みsourceから得たplan候補を、Humanが確定したgold labelと照合し、
release候補へ進めるかquarantineへ送るかを決定論的に判定する。これはsource parserでも
Human承認の代替でもない。rights回答・Affiliate承認・実データがない現在はsynthetic testだけを実行する。

## 役割と境界

|Artifact|作成owner|確定owner|禁止|
|---|---|---|---|
|SourcePolicy / EvidencePointer|Evidence/Policy|Human Approver|規約を推測してapprovedにする|
|VendorPlan candidate|Contract/Storage|なし（候補）|canonical DBへ直接writeする|
|Gold field/TCO label|TCO/QA|Human Approver|parser自身を正解としてlabelする|
|Quarantine report|Integration/Release|なし（機械判定）|失敗rowを黙って除外する|
|Release recommendation|TCO/QA|Human Approver|reportだけでpromoteする|

gold labelにはraw source本文、実Affiliate URL、credential、PII、非公開報酬を入れない。
material valueはcanonical JSONのSHA-256で保持し、別管理のHuman decision recordを参照する。

## Gold set完成条件

1. distinct vendor 3社以上。
2. 各vendorにdistinct plan 6件以上。
3. 各vendorのlabel済みmaterial field値が60〜150件。
4. 各planに1件以上の代表scenarioがあり、currency、total minor units、full TCO result SHA-256をHuman labelとして持つ。
5. label record、rights bundle、source snapshotをSHA-256で参照する。
6. label・TCO label・derive・publish・history権利とretention windowが評価時刻に有効。
7. 同じvendor/plan/scenario、field、candidate keyの重複がない。

上記未達のpartial setは入力契約として保存できるが、`ready_for_release`にはならない。

## Candidate batch

parserは成功candidateと失敗candidateを同じbatchへ出す。失敗を捨てて成功率を上げない。

成功candidateに必要なprovenance:

- `VendorPlan` strict contract。
- source response SHA-256。
- parser artifact SHA-256と固定version。
- parse時刻。
- source hashがplan内のEvidencePointerに存在すること。

失敗candidateに必要なprovenance:

- stable candidate key。
- vendor/plan identity。
- bounded error code。
- parser/source/diagnostic SHA-256。
- raw exception、HTML、stack trace、URLを含めない。

## 判定

1. Gold coverageとfield/TCO label期限を検査する。
2. Candidate identityをgold identityへ1対1で突き合わせる。
3. 全material fieldをcanonical JSON化しSHA-256で比較する。
4. current `derive / publish / retain_history`、未来EvidencePointer、retention期限を全fieldで検査する。
5. vendor/plan/fieldに対応する全SourcePolicyをcanonical化したrights manifest SHA-256をHuman gold setと照合する。snapshot IDや取得時刻はmanifestへ含めず、同一承認policyの新snapshotを許容する。
6. scenarioをcanonical Python TCOへ渡し、currency、total minor units、full result hashを照合する。
7. missing、extra、parse failure、rights、source hash、field、TCO差分をhash-only quarantineへ出す。
8. parser failure率が20%を超えたらSTOP。exact 20%だけではrelease可能にならず、全gold record合格が別途必要。
9. quarantine 0、full coverage、failure 0のときだけ`ready_for_release`候補とする。これは公開承認ではない。

## 失敗時

|Reason|動作|Human確認|
|---|---|---|
|Label/rights expiry|batch全体をrelease不可|再審査。期限を推測延長しない|
|Source hash mismatch|plan単位quarantine|取得receiptとEvidencePointer|
|Field mismatch|plan単位quarantine|公式定義、effective date、parser rule|
|TCO mismatch|SEV1、release停止|scenario、税、billing、rounding|
|Missing/extra candidate|plan単位quarantine|source一覧とparser coverage|
|Parser failure >20%|Phase 4 STOP候補|manual更新で720分以内か|
|Source conflict|source単位quarantine|authority優先順位をHuman確定|

## Acceptance command

CLIはlocal JSONをread-only評価し、stdoutへhash-only reportを出す。既存ファイル、DB、release pointerを変更しない。

```bash
uv run saas-preflight evaluate-gold-set \
  --gold-set gold-set.json \
  --candidates candidate-batch.json \
  --at 2026-07-21T12:00:00Z
```

`--at`を指定すると、同じ入力を同じ評価時刻で再現できる。省略時は現在時刻を使う。

実入力を作成するのはGate A/B合格後。それまではtest内のsynthetic fixtureだけを使う。
