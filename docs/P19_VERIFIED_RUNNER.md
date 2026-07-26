# P19 verified runner and operational evidence

## Current decision

P19は`IN_PROGRESS / STOP`である。credential-free契約・検証器・反例、timeout付きlocal durable one-shot consumer、
Storage Auditor署名consumption receipt、credential-blind P17 broker、P13のP18/P16/semantic最終再検証は実装したが、
実immutable runner、platform quote verifier、保持byteを確認できる外部CAS、production clock/anchor/current-root serviceは未接続である。
この文書、local test、合成鍵、pure CLIはいずれもP18 Human acceptance、公開、production write、scaleを許可しない。

## Verified runner V2

`saas_preflight.verified_runner`は14検証を固定順序にし、次を一つのV2 evidence bundleへ保持する。

- sequence、nonce、対象tree、消費先store ID、前evidence head、有効期間を持つchallenge。
- subjectをread-onlyで内包するimage identityと、image/quote/isolation/record setを結ぶProvider Conformance署名。
- record countが1以上でdatabase hashと期限を持つSecurity Auditor署名advisory snapshot。
- argv、固定cwd、environment、network、interpreter、import closure、parser、tool、assertion floor、timeout、出力量上限を持つcheck spec。
- wall/monotonic時刻、termination、exit/signal、stdout/stderrの別hash・byte数・truncation、parser output、assertion/failure/skip、dependency advisory readを持つresult。
- record setに対するTime Auditor署名と、全evidence/policy/trustを結ぶIntegration runner署名。
- runner、advisory、image、time、storageの5鍵が相互に異なるtrust storeと、packet外から渡すauthority root。
- exact store/sequence/head/evidence/authorityを結び、nonce付きclock requestとTime Auditor署名clock responseの全artifactを内包するStorage Auditor署名consumption receipt。

各hashは型別domain separatorを持つ。timeout、signal、nonzero exit、failure、skip、parser/tool差替え、output truncation、
assertion floor未達、空advisory、advisory database差替え、期限切れ、sequence/head rollbackは常にrejectする。

旧`verified_local_run`は、Integration/TCO/Humanの署名が全部正しくても永久に`STOP / local_verification`である。
V2 summaryへ変換できるのは、retained V2 evidenceと署名済みone-shot consumption receiptをpacket外authority rootで再検証した場合だけである。
P18 IntegrationとTCO/QAの二署名はP18 summaryだけでなく、P19 bundle hashとP19 authority rootも直接署名する。
P18とP19の8 role keyに一つでも再利用があればSTOPになる。receiptはP18 verification bundleへ含まれるため、P18二署名、P16、P13まで同じ消費事実がhash連鎖する。

## CLI boundary

次のCLIは既に消費済みのreceiptを検証する専用境界であり、CLI自身はreplay stateを消費しない。

```bash
uv run saas-preflight verify-immutable-runner-evidence evidence.json \
  --consumption-receipt consumption-receipt.json \
  --policy runner-policy.json \
  --trust-store runner-trust-store.json \
  --authority-pins runner-pins.json \
  --expected-authority-sha256 PACKET_EXTERNAL_ROOT \
  --at 2026-07-22T08:00:00Z \
  --output p18-structural-summary.json
```

出力は`authority=none`、`mode=pure-verification-only`である。CLIは署名receiptを検証するだけなので、one-shot消費そのものは
必ずsecret-owning `VerifiedRunnerReplayStore`で先に行う。

production向けの状態境界はCLIではなく`VerifiedRunnerReplayStore`である。exact sequence/head CAS、challengeと
bundleの一意制約、immutable row、state HMAC、schema fingerprint、外部monotonic anchorとone-ahead recoveryを持つ。
challenge/pinsはexact store IDを固定し、別storeでの再消費を拒否する。Time Auditor callbackはpolicy固定timeout、最大backdateで検証され、
timeout・例外・署名/store/head/sequence/lagを含む不正応答後は外部anchorへ結ばれたdurable freezeを保存するため、DB reopenでも消費を再開しない。
receiptの検証側は内包clockの署名、request/attestation hash、store/sequence/head/evidence/authority、TTL、観測遅延、consumed時刻を再検証する。
store flockとanchor read/commitも固定deadlineを持ち、停止した外部serviceを無期限には待たない。
鍵・clock・anchorをCLI引数や環境変数へ渡す入口はない。

## Reconstructable operations and the JPY 200,000 objective

`saas_preflight.operations_activity`は30 Tokyo日について、routine task定義、全schedule、scheduleごとの一意な
execution receipt、匿名化actor tokenごとの分単位human activity、resource usage receipt、role labor rateを保持する。
欠落実行、余分な実行、mode差替え、manual taskのactivity欠落、同一actorの時間重複、未定義rate、期間外usageを拒否する。

`derive-operations-activity`は自動化率、人手時間、job成功、例外、重大誤表示、人件費、resource費を行から再計算する。
P17 `TractionObservation`はbatch・cost policy・derived summaryを丸ごと保持し、P12 operations hashと30日windowへ結ぶ。
署名済み観測でもaggregateだけを変更すればrejectされる。

月20万円は`net_operating_profit`を正本とする。判定式は次のとおりである。

```text
net operating profit = latest settled revenue - labor cost - resource cost
GO threshold input   = net operating profit >= JPY 200,000
capacity gross need  = JPY 200,000 + operating TCO
```

settlement amendmentが入った場合は、最新の修正済みsettled revenueから固定された同windowのoperating TCOを再控除する。
売上20万円だけでは純利益GOにならない。

`TractionRuntimeBroker`は、secret-owning bootstrapが完成済み`TractionLedger`だけを渡す運用portである。append、
settlement、evaluate、readの各methodはstate-MAC key、signer、clock callback、anchor callbackを引数に持たない。
broker自体は外部操作・scale権限を発行せず、`READY_FOR_SCALE_REVIEW`は引き続きHuman review入力に限られる。

P13 activation request/dispatch token v4はP18 root、P16 authority/plan/bundle hash、semantic root/packet hashを保持する。claim後、provider
subprocessの直前にnested P18、P16全receipt、Gate 2–8 typed semanticsをpacket外rootで再検証し、P15 report/TCO、P10 local report、
property/environment/deployment candidateを照合する。P15 Time Auditorのnonce付き時刻とStorage Auditor署名current-rootを
各実行phaseで取得し、provider完了後の新時刻でreceiptを検証する。dispatch expiryはP16/P18実効expiryにもclipされる。

## Remaining P0 gates

以下が揃うまでP19をcompleteにしない。

1. build/runtimeが別trust domainの実immutable imageであることをquote bytesから検証するprovider実装。
2. stdout/stderr、parser output、advisory database、image manifest/rootfsをretained bytesまたはStorage Auditor署名CASからread-backするresolver。
3. 実装済みtimeout、used-challenge table、sequence/head CAS、state MAC、durable freezeへ、production trusted clock、
   別障害領域monotonic anchor、current-root registryを接続するservice。
4. 別OS identity/KMS鍵を持ち、durable attempt intent、current STOP/epoch/root、P11 revocationをprovider mutation直前に
   再検証し、prelaunchから完了まで一つの総deadlineとprovider-side conditional one-shot mutationを強制するbroker。

これらは外部credential、account、deploy、公開を自動承認する項目ではない。実接続後もrights、Affiliate、需要、
gold source、P15、Human publication approvalは別gateである。
