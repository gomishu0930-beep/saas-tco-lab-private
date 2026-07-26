# P18 repository acceptance / restart contract

基準日: 2026-07-22

## 目的

P18は、未commit・全file未追跡のworking treeでも、P11–P21のlocal候補を一意に再計算できるMerkle manifestへ固定し、検証実行者、TCO/QA、Human Approverを別鍵へ分離する。P18の肯定結果は`local_integration_accepted`だけであり、source fetch、申請・送信、account、credential、課金、deploy、公開、production write、affiliate link変更、spend、scaleを一切許可しない。

現在のchecked-in fixtureは合成検証かつHuman receiptなしのため、`STOP / local_verification`である。実在のHuman署名や外部承認をfixtureで代用しない。

## 固定scope

`p11-p18-local-candidate-v1`、`p11-p20-local-candidate-v2`、`p11-p21-local-candidate-v3`、
`p11-p21-growth-local-candidate-v4`と`p11-p21-owned-learning-local-candidate-v5`は履歴profileとして
path-set hashを変更せず保持する。現行`p11-p21-measurement-deploy-ready-local-candidate-v6`は、
growth semantic、AI routing、12本の合成noindex pilot、実装台帳、署名付き自データ初期品質gate、
GSC/GA4のfail-closed deployment gateを含め、rootの`.gitignore`、`.gitleaks.toml`、`AGENTS.md`、`README.md`、
`pyproject.toml`、`uv.lock`と、`.github`、workflow recipe/roadmap、release-assurance artifact、`docs`、
`examples`、`schemas`、`scripts`、`site`、`src`、`tests`を全列挙する。runtime cache、virtualenv、
Web build/node modulesと`artifacts/local-acceptance`はscope外である。

各entryはcanonical relative path、size、executable bit、SHA-256を持つ。scope profileはexact path-setの
canonical hashをcode registryへ固定する。既存profile名のpath-set hashは変更禁止であり、対象fileを増減する
場合は新しいversionのprofileを追加し、旧profileを履歴として残す。artifactを読み込む時点でもregistryと
manifestのpath-set hash、全root file、各必須directory配下の最低1 file、previous-candidate recordの実digestとの
一致を再検証するため、call側が1 fileや`.`だけのmanifestへscopeを縮小できない。rootの全祖先と全path
componentをdirfd相対で`O_NOFOLLOW` openし、pre/post `fstat`と二回scanを照合する。symlink、hardlink、
secret-bearing filename、未知top-level、絶対/親参照、非canonical表記、NFC/case衝突、途中変更は拒否する。

acceptance artifact自身によるhash自己参照を避けるため、生成済みmanifest/reportはscope外の`artifacts/local-acceptance/p18-current-stop`へ置く。scope内の本書は固定手順だけを記し、生成後のhashを追記しない。

## 検証と役割分離

14件のverification factはtree、argv、repository-root cwd、sanitized environment hash、network mode、interpreter hash、import closure hash、tool/version、開始・失効時刻、assertion/fail/skip/exit、output hashを持つ。command hashはargvと実行contextから再計算される。

`run-local-verification`は、この14件を人手転記せず実行するcredential-free diagnostic runnerである。Python
testsを明示的で重複しない5 laneへ分け、schema/fixture二重生成、lock、compile、secret scan、Web、lint、
offline dependency check、workflowを固定順に実行する。外部通信はmacOS Seatbeltで拒否し、actual-HTTP Web test
だけlocalhost bind/inbound/outboundを許可する。pytest plugin autoloadとcaller環境を遮断し、各commandはtimeout、
combined output cap、process-group killを持つ。runnerは秘密鍵、署名、Human decisionを一切受け取らない。

ただし現在のhost runnerは`local_diagnostic_run`であり、`verified_local_run`を名乗らない。Seatbeltはnetwork
境界を実効化するがhost filesystem/processをimmutable snapshotへ閉じず、live tool/pathのswap-and-restoreを
完全には反証できない。また`npm audit --offline`の空cacheによるfalse-cleanを防ぐ署名済みadvisory snapshotが
ないため、dependency audit factは意図的にfailとなる。旧`verified_local_run`は署名済みでも永久STOPであり、P18 acceptanceに使用できるV2 evidenceは、
consumer-pinned read-only image、network none、host volume非公開、fresh/non-empty/digest/expiry付きadvisory
snapshot、typed termination/output contract v2を備えた後続runnerだけが生成する。現在のdiagnostic bundleを
署名してもlocal acceptanceにはならない。

V2 summaryはP19 evidenceだけでは構築できない。consumer store IDをchallenge/pinsへ固定したdurable replay
consumerが、exact sequence/head/evidence/authorityをStorage Auditor鍵で署名したconsumption receiptを必要とする。
このreceiptはnonce付きclock requestとTime Auditor署名responseを全量保持し、P18 verification bundle hashに含まれ、Integration/TCO二署名、P16、P13まで同じone-shot消費事実を
連鎖する。P18はclock署名・TTL・lagも再検証する。未消費、別store消費、署名差替え、bundle/head不一致はP18でSTOPする。

V2のIntegration Evidence RunnerとTCO/QAの発行時刻は、全checkだけでなくdurable consumption receiptの`consumed_at`以後でなければならず、manifest assembly以前でなければならない。

Integration Evidence RunnerとTCO/QAは、全check実行後かつmanifest assembly以前に、同じverification bundleへ別Ed25519鍵で署名する。policyはcheck順、command/context hash、tool/version、最低assertion数、3 role key、TTL、9 authority exclusionを固定する。14件の最低assertion数はcode-defined registryとの完全一致をpolicy validationと評価境界の双方で要求し、低いcoverage floorへ署名し直す攻撃を入力エラーとして拒否する。policy+trustのhashを束ねたverification-authority rootをconsumerが別経路で固定し、Human receiptがまだない段階でも両attestationの鍵・issuer・署名を検証する。root欠落/不一致、`synthetic_contract`、失敗、skip、期限切れ、署名欠落・置換は`STOP / local_verification`である。

Human receiptは`GO | CONDITIONAL | STOP`、manifest/policy/trust hash、revision、predecessor、発行・失効時刻を署名対象にする。Human発行はmanifest assembly後でなければならない。revision 2以降はrevision 1からcurrent直前までの省略不能・連続・署名済みreceipt chainを要求し、ランダムなpredecessor、fork、欠落履歴では受理しない。consumerが別経路で保持するauthority-pins hashとcurrent receipt head/revisionが一致しない旧GOは再利用できない。root欠落・差替え・期限切れは`current_pinned_acceptance_chain`を要求する。

## 次gate

評価順は次で固定する。

1. local verification不足: `STOP / local_verification / current_signed_verification_bundle`
2. Human receiptなし: `PENDING / repository_acceptance / human_signed_repository_acceptance`
3. authority root/current chain不一致: `STOP / repository_acceptance / current_pinned_acceptance_chain`
4. exact Human GO: `ACCEPTED / rights_evidence / current_rights_decision_records`

`first_external_gate`は常に`rights_evidence`である。`CONDITIONAL`は条件が残る限りacceptedにしない。

## P16 v3との結合

P16 Gate 1は旧P11–P15 opaque hash 5件を受け取らない。singletonの`P18_REPOSITORY_ACCEPTANCE_AUTHORITY_BUNDLE`を要求し、P18 bundle hash、Human receipt identity、repository tree、manifestをP16 requirement/planへcross-bindする。さらにP16 packet外のconsumerが渡すexpected P18 authority-rootとP16 plan pinとP18 pins hashの三者一致を要求する。P16自身も別のconsumer-owned launch-handoff authority-rootでplan/policy/trustを固定する。

P16 v3はGate 2–8に型付き`LaunchSemanticPacket`を必須化する。rights、Affiliate、P12需要・運用、gold set、P15 readiness、P10 local assurance、deployment/publication recordを公開鍵専用verifierで再構築し、receiptのcomponent、evidence identity、subject、scope、最短expiryと完全一致させる。packet外の第三ルート`LaunchSemanticAuthorityPins`は個々の上流artifact hashを固定するため、正しい署名を付けた任意hash、別property／environment／releaseのpacket、意味的STOPの再包装ではGate 2–8を通過できない。

P16がREADYでもauthorityは`none`であり、最短expiryはP18 manifest、verification facts、Integration/TCO attestations、Human receipt、P16 receipts/plan/report TTLの最小値にclipされる。

P13 activation request/dispatch token v4は、packet外P18 authority-root、P16 authority-root、意味証拠authority-root、P16 plan hash、
P16 bundle hash、意味packet hashをexactに保持する。claim後・provider subprocess直前にP16評価器を再実行し、Storage Auditor署名の
current-root resolverも再取得するため、Human review後に
P18/P16/意味証拠が期限切れ・欠落・差替えになった場合はprovider call 0で停止する。緊急のHuman承認済みdisable laneは
activation authorityを運ばず、この追加gateで妨げない。

## P13 subprocess closure

P13のpinned file hashとscript launcherは、元pathを`resolve()`してsymlinkを隠さない。root dirfdから全componentを`O_NOFOLLOW`でopenし、regular/single-link file、pre/post identityを検証する。childはverified file descriptorを`-I -S -B`のisolated interpreterで実行する。固定launcherはlocal source、base stdlib、必要な8 distributionの全importable fileをhash manifestへ固定し、manifest自体はFDで渡す。各Python moduleは検証した同じbytesから実行し、extensionは保持したdescriptorからloadするため、site-packages追加とhash後path swapを拒否する。cwdは`/`、environmentは固定し、callerの`PYTHONPATH`、`sys.path`、`sitecustomize`を継承しない。stdout/stderrはstreaming上限超過時にprocess groupをkillする。

## CLI

diagnostic 14-check bundleは次でstdoutへ出す。現在はdependency advisoryとimmutable runnerが未成立なのでexit
code `3`が正しい。出力を保存する場合はscope外の`artifacts/local-acceptance`配下を使う。

```bash
uv run saas-preflight run-local-verification \
  --repo-root . \
  --workflow-verifier \
  /Users/oumishuu/.codex/skills/codex-dynamic-workflows/scripts/verify_workflow.py \
  > artifacts/local-acceptance/p18-diagnostic-verification.json
```

Integration/TCOの実署名済みbundleからmanifestを組み立てる手順は次である。

```bash
uv run saas-preflight build-local-acceptance-manifest \
  --repo-root . \
  --verification-evidence /path/to/signed-verification-bundle.json \
  --integration-attestation /path/to/integration.json \
  --tco-qa-attestation /path/to/tco.json \
  --candidate-id p11-p21-growth-local-candidate \
  --assembled-at 2026-07-22T09:00:00Z \
  --expires-at 2026-07-23T09:00:00Z \
  --output /new/path/candidate-manifest.json
```

Human前の評価はpolicy、trust、consumer-owned expected verification-authority hashを渡す。Human receiptを評価する場合はさらにpins、consumer-owned expected pins hashを渡し、revision 2以降は`--receipt-chain`でcurrentより前の全receiptをtyped chainとして渡す。CLIは外部接続、署名鍵生成、Human decision作成、publish/deployを行わない。
