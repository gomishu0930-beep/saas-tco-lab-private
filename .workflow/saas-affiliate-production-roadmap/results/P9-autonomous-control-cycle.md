# P9 Result: Offline autonomous control cycle and dead-man lease

## Accepted

- Business dossier、GoldSetReport、ReleaseState、SchedulerHeartbeat、ExceptionQueue、当月Human
  budgetを1回のpure control decisionへ統合した。
- `stop / hold / human_approval_required / maintain_current`を分離し、機械的なpromotion、rollback、
  publication actionを出力契約から除外した。
- GoldSetReportを1.1へ更新し、rights bundleと、gold/candidate/label/TCO/policy/retentionから算出する
  最短expiryをreport hashへ結合した。
- current releaseではdossier/gold/releaseのrights、dossier/releaseのAffiliate、gold/releaseの
  candidate batch snapshot、artifact/manifest/current visibilityを再照合する。
- dossier economics/freshness、gold report hash/readiness/freshness、heartbeat TTL/schedule lag、
  open SEV0/SEV1、UTC当月budget、release visibilityを評価時刻で再計算する。
- `ControllerAuthority`がfrozen config、3 roleの公開鍵TrustStore、controller秘密鍵をtrusted bootstrapで
  1回だけ固定する。evaluatorへconfig/trust/signerを個別注入できず、秘密鍵は非serializable・repr redacted。
- TCO/QAはreport/rights/candidate、Humanはcurrent event/release/manifest/decision recordを別Ed25519鍵で
  署名する。構築済み`HumanApproval`や再計算した自己hashだけではleaseを発行しない。
- `maintain_current`だけがEd25519署名済み短命ServingLease v2を受け取る。issuer/role/key/scope/
  input/release/manifest/artifact/全時刻へ固定し、全入力deadlineの最小値以前に失効する。
- `ControlledMvpRuntime`は署名、固定controller公開鍵、最大TTL、future/expiry/copyを再検証し、失敗時は
  protected routeをgeneric 503にする。production Workerは`assets.run_worker_first=true`で実JS assetも
  Workerより先へ抜けない。`/healthz`と`/robots.txt`だけ非機密固定応答を維持する。
- 合成UIは`synthetic-local`専用entryへ分離し、production buildへlocal bypassを含めない。
- control outputはhash、bounded enum、件数だけで、URL、excerpt、credential、Affiliate destination、
  raw exception summaryを含まない。exception queue順序とexact retryでhashが一致する。
- ControlConfig、TrustStore、公開鍵、2 attestation、SchedulerHeartbeat、ServingLease、ControlReport、
  GoldSetReportのschemaを正本modelからdeterministic exportし、local handoff runbookを追加した。

## Boundary decisions

- 576分は新規source/非重要改善のfreezeであり、合格済みcurrentの維持leaseは許容する。
- 720分は`stop`。
- business `CONTINUE`、SEV1、stale/future heartbeat/report、wrong/missing month budgetは`hold`。
- business `STOP`、report/hash/binding破壊、SEV0、parser failure STOP、720分枯渇、hidden/expired
  releaseは`stop`。
- ready candidateにcurrentが無い場合は`human_approval_required`で停止し、自動promoteしない。
- expiryは半開区間で、heartbeat/schedule/gold/lease/releaseのexact boundaryを失効とする。

## Verification

- P9 control + delivery focused tests: 36 passed。独立QA focusedは59 passed。
- Full Python suite: 233 passed。
- 23 JSON Schemaを2回生成し、byte差分なし。
- `cryptography==49.0.0` exact pin、Ed25519 smoke、`uv lock --check`、compileall合格。
- Gitleaks約3.18 MBをscanし、leak 0。
- Webはsynthetic local UI 4件とproduction actual HTTP 3件。実JS asset/favicon/image/unknownは503、
  health/robotsだけ200。ESLint、`npm audit` vulnerability 0。
- workflow verifier合格。独立TCO/QA・Governance最終再監査ともrelease blockerなし。

## External boundary

account、credential、scheduler、database、secret store、cloud、email、source fetch、Affiliate申請、
deployment、public URL、promotion、publicationは実行していない。本成果物はlocal decision contractであり、
production接続とHuman GOを代替しない。
