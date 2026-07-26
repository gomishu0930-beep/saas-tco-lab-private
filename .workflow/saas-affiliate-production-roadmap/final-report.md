# P21 current report — credential-free implementation complete / business STOP

最後まで進められる経路は`docs/PRODUCTION_ROADMAP.md`のPhase 0–8とC0–C7へ固定した。credential-free実装は
C0まで完了したが、事業完成の直接証拠はない。rights 0/3、Affiliate 0/3、qualified demand 0、30日観測0、
confirmed EPC・月20万円純利益は未定義である。したがってpublic、production、business、scaleはいずれも`STOP`を維持する。

P21ではP16 Gates 2–8をopaque hashではなくexact typed payloadから公開鍵だけで再評価する。P12 fault target、
P15 plan v2、P10 manifest、P16 plan、P13 request/dossierを同一release/manifest/artifact/schema/provider target/
pre/post/rollbackへ結合し、P15 plan v2はprovider targetとexpected pre-stateを所有する。Gate 8はP15のexact
independent-readback/rollback evidence、P11 disable policy/authority、直前deployment record、consumer-owned
legal/disclosure期待値、各readbackのdeployment後・個別TTLを強制する。P13 activation/disableは同じproperty、target、
adapter、probe、runtime、dependency、allowlist、postcondition contract以外を受け入れない。

静止treeで重複なしPython laneはbase 524、traction 57、P13 81、Contract/Storage 28、TCO/QA 51の計741件が合格した。
P15/P16 fixtureと197 schemasは再生成・determinism検証済み。Web 13、ESLint、npm audit offline 0、uv lock、
compileall、workflow verifier、Gitleaks 13.71 MB/no leaksも合格した。Contract/Storage、Security、TCO/QAの独立監査は、
target/pre-state再帰属、legal/disclosure両辺再署名、unrelated deployment、stale/pre-deployment readback、rollback policy、
activation/disable target差替えの反例を閉じた後、残存P0/P1なしと判定した。

次はC1の外部入力である。3社分のfield-level rights、Affiliate acceptance、JP/ja需要exportをHumanが取得・承認し、
合格したsourceだけをP5/P8/P12へ投入する。その後C2の30日shadow、C3の実P15統合証拠、C4のP18/Human受理、
C5–C7の実cohort・EPC・純利益検証へ順番に進む。実rights、Affiliate、需要、settlement、KMS/provider/domain/deployを
local fixtureで代替しない。

---

# P18 historical final report — superseded by P19/P20

この文書の648 tests／150 schemas等はP18固定scope時点の履歴であり、現行受入値ではない。現行P19 scopeは
704 testsをcollectionし、base 495件、P13 76件と183 schemasをimmutable-runner policyへ固定している。P19 local slicesは
実装済みだが、実immutable runner/CAS、別OS identityのprovider broker/KMS、production clock/current-root/anchor、
rights・Affiliate・需要・EPC・Human公開承認がないため、decisionは引き続き`IN_PROGRESS / STOP`である。

## Outcome

完成ロードマップをPhase 0–8とP1–P18へ固定し、外部認証なしで進められるcontrol plane、provenance付き
production intake、measurement integrity、offline gold-set、local noindex MVP、release assurance、signed control
boundary、credential-free production consumer、crash-safe provider journal、production-integration readinessまで実装
した。local codeはexact 11 environment checks、P13 phase fence、separate reconciliation ledgerと
`NOT_APPLIED`限定STOP reset、最終Human review用の非権限handoff、P12-bound traction/settlement ledgerを含む。

事業は未完成であり現在`STOP`。理由はrights 0/3、Affiliate 0/3、日本語需要・confirmed EPC・90日automation実績がないため。これを合成値でGOにしないことが今回の主要成果である。

## Accepted Results

- P1: 5社公式調査、現在0/3、Human照会template、確認順`Mangools → SE Ranking → HubSpot → Semrush → Serpstat`。
- P2: immutable prepare/promote/rollback、三expiry、hash-only CTA、run/exception/budget state machine。
- P3: Decimal demand/EPC/traffic、confirmed+paidだけのEPC、1,000 clicks/180日、GO/CONTINUE/STOP。
- P4: Phase 0–8 roadmap、BusinessDossier、2 CLI、noindex preview、HTTP safety boundary、synthetic E2E、8故障matrix。
- P5: provenance付きBusinessDossier、rights/Affiliate bundle、需要/cohort/operations evidence、自己申告bool/件数/率を持たない`assemble-readiness`、5追加schema。P6でoperation gate追加に伴いschema v3へ更新。
- P6: L2 safe summary→3 Evidence、30日/job99%/例外24/rollback gate、3集計CLI、3入力schema、Evidence runbook、反証仕様。
- P7: responsive 5画面、preview v2、artifact/CTA hash、serve-time TTL、generic 503、robots/security/health、rollback fault、Web dependency audit 0件。
- P8: 3社以上×各6プラン以上、vendor 60–150 field labels、parser provenance、policy-only rights manifest、evidence/retention/TCO-label TTL、field/source/full-TCO hash、failure-rate 20%境界、hash-only quarantine。
- P9: ControllerAuthority、TCO/QA・Human別署名、signed bounded lease、worker-first production deny、synthetic-local UI分離。自動promote/publishは含まない。
- P10: 13 check固有facts、tool/version/command/subject pin、controller runner署名、TCO/QAとHumanの別署名、Humanによるmanifest全snapshot完全承認、GOだけのcontroller authorization、consumer固定runtimeを実装。24件の脅威、651-component SBOM、a11y/mobile/SEOと本番起動・終了境界を監査した。
- P11: 4種のexact external-action request、Human GO、controller grant、P10 activation binding、固定target allowlist、revocation、executor receipt、revision-bound journalを実装。固定ID SQLite、HMAC state head、companion anchorと外部monotonic pin、schema/write read-back、CAS内clockでlocal replay・rollback・競合をfail closedにした。外部callは0件。
- P12: signed measurement producer、固定run/分母、transaction/payout/funnel reconciliation、必須8 fault、
  report-bound dossierを実装した。
- P13: P9–P12 authority、global STOP、durable claim/token、subprocess execute/probe、provider receiptとterminal
  resultを一つのcredential-free consumerへ統合した。
- P14: provider factをterminalより前にimmutable journalへ保存し、fork/process death/anchor outageを
  `UNKNOWN + STOP`へ回収する同一host crash contractを実装した。
- P15: exact 11 production checks、10 role trust、policy-only thresholds、TCO/QA→Human→controller chronology、
  plan-expiry clip、P13全phase再検証、separate reconciliation ledger/store/trust pinを実装した。
- P16 v2: Gate 1をtyped P18 authority bundleへ置換し、consumer-owned authority-root、manifest/tree/Human receiptを
  cross-bindした。exact 8 gate、Human/TCO鍵、ordinal/predecessor chain、final-review-only reportは維持する。
- P17: 完全P12 packet再実行、署名済み30日observation、後日確定・返金、complete zero-event settlement、
  post-anchor finalization、expired tombstone、exact Decimal scale gateを一つの認証ledgerへ統合した。
  trusted-clock callbackはhost-global root lock、fork handler、one-shot FD leaseで直列化し、出力は
  `READY_FOR_SCALE_REVIEW`までで外部authorityを持たない。
- P18: P11–P18 exact-file manifest、argv/cwd/environment/network/interpreter/import closure付き14検証、
  Human前verification-authority root、Integration/TCO/Human別署名、全revision chain/current headと
  consumer-owned authority-rootを実装した。P13 childはdirfd検証、`-I -S`隔離、hash済みimport allowlistで
  外部`PYTHONPATH/sitecustomize`と未pin shadow moduleを拒否する。
- P18 diagnostic runner: 14 checkを明示・重複なしlaneへ固定し、network sandbox、sanitized env、runtime/tree
  前後hash、timeout/output capを実装した。host隔離とsigned advisoryがない現runnerは意図的に
  `local_diagnostic_run`/STOPで、`verified_local_run`を自己発行しない。
- P18 policyは14 checkの最低assertion数をcode-defined registryへ完全固定し、低いcoverage floorへの
  差替えをvalidation、Human signing、evaluationの各境界で拒否する。

## Rejected Results

- 公開Affiliate programを実利用可能な提携として数えること。
- Affiliate参加条件をprice/limit取得・保存・TCO・履歴の許諾として扱うこと。
- pending/rejected commission、重複keyword volume、仮定EPCを月20万円の実績に使うこと。
- 入力JSONの古いrender時刻でexpiryを回避すること。
- 任意HTTP clientのCookie/auth/proxy/redirect設定を取得境界へ持ち込むこと。
- rights前の実fetch、申請、メール送信、cloud、deploy、公開。
- live Affiliate URL/credentialを審査bundleへ保存すること、同一partner/vendorで3社gateを水増しすること。

## Conflicts Resolved

- 「最後まで実装」と「rights前はfetch禁止」を、control plane/fixtureを先行実装し、実source adapter有効化だけをHuman gateに置くことで両立した。
- Static previewのbuild時判定では期限切れを防げないため、CLI実行時刻とrelease read-timeの二重expiry判定に修正した。
- Affiliate expiry時のCTAだけでなく、採用済みproduction policyどおりnumeric/ranking/release全体をhideするrelease gateへ統一した。
- business GOとHuman publish approvalを分離した。計算GOでも外部操作権限にはならない。
- local checkの自己申告件数を廃止し、check別facts・固定実行条件・runner署名へ置換した。最終consumerはreport内の鍵でなく、別途固定したcontroller鍵とpolicyで再検証する。
- synthetic build後の`start`と、test終了後の孤児Wranglerを反証し、production再build・worker-first検証・process-group回収を正規commandへ固定した。

## Historical P18 Verification Evidence

- P18/P16/P13 focused 134/134件、full Python 648/648件、150 schemas、deterministic P16/P18 fixtures、lock、compileall、
  workflow verifier、Web 13 tests、ESLint、Gitleaks no leaks。offline dependency advisory不足は意図的STOP。
- P18固定コードhashに対するContract/StorageとTCO/QAの独立監査は、低assertion policy迂回の初回blockerを
  修正後にPASS。credential-free technical candidateに残存P0/P1 code blockerなし。本番昇格は別gateとしてBLOCK。

- split実行で重複なし616 Python tests（base 526、P17 traction 38、production consumer 52）passed。
- P12/P17/settlement focused 72件、137 schema export deterministic、checked-in set一致、lock、compileall合格。
- CycloneDX 1.6 SBOMは651 components/651 nodes、SHA-256
  `a860dd9810e1fb76f75198ff23870c4c4b271609670124aa90dd9ee803595c13`で固定。npm audit 0件。
- Gitleaks directory scanでleak 0。
- vinext local/production build、production JS assetの503、`npm test` exit 0・残留production process 0、ESLint、npm audit 0 vulnerabilities。
- P16固定hashに対するContract/Storage、TCO/QAの独立反証は、署名tie-break初回blocker修正後に全てPASS。
- P17固定hashに対するContract/Storage、TCO/QA独立反証は、post-start二重close/並行callback、registry登録
  MemoryError、ownership通知例外の3 blockerを再現・修正後にPASS。終了時FD registryは空、root lockは解放済み。
- P17 blocked fixture 8 filesは二生成・checked-in一致、diagnostic CLIはexit 3/STOP。Web 13 tests、ESLint、
  production build、npm audit 0、Gitleaks 9.58 MB/no leaks。
- blocked real-state fixtureはdecision `stop`。
- synthetic-only end-to-endはplan→TCO→preview→Human-approved local release→visibility→economics GOを再現。
- provenance assemblerは3社のsynthetic policy/decision/evidenceからv3 DossierとGOを再現し、期限切れ・重複・分母0をfail-closed。
- safe summary→Evidence→Dossierのsynthetic end-to-endとGate D境界を再現。

## Remaining Risks

- 5社すべてについてprice/limit/TCO/historyの書面許諾がない。
- Affiliate account/tracking linkが0社。専用account、税務、payout、domain承認も未確認。
- Japanese qualified demand、SERP取得可能性、confirmed EPCは未観測。
- HTTP application-layer DNS検査はcloud/network egress allowlistの代替ではない。
- production provider、domain、legal/privacy/affiliate disclosure、credential、billing、deployは未選定・未承認。
- production key store、protected runner、実KMS、trusted clock、remote anchor、multi-host shared store/fencingは
  未接続。正規runner/controller鍵保有者の虚偽は信頼境界内の残余リスクである。
- P13/P14/P15のstore、flock、anchor callbackとproviderはlocal fixtureである。typed evidenceは実providerの
  conditional mutation、receipt durability、remote exactly-onceや災害復旧の真実性を代替しない。
- P17のhost-global root lockは安全側の可用性トレードオフである。clock callbackが永久停止すれば、そのprocessを
  終了するまで同一hostのP17 clock処理を停止する。Python外のnative fork/platformはdeployment contract外である。
- 形式的repo acceptanceはP0–P10まで。P11–P18はP18 Human receipt/current authority-rootが未記録である。
- automation 80%はtyped per-task/per-Human-activity ledgerから未立証。P17 operational CLI/adapterと、P18/P16の
  final publication/production consumer再検証もfollow-up local packetである。
- P18 `verified_local_run`には、read-only digest-pinned OCI/VM、host mount非公開、network none、fresh/non-empty/
  signed advisory snapshot、termination/outputを直接bindするresult contract v2が必要である。

## Reusable Follow-up

まずimmutable verification runner v2と署名済みadvisory snapshotを用意し、14 checkへIntegration/TCOの別role署名を付け、Human ApproverがP11–P18 exact manifestをrevision付きで受理する。その後も、上位3社への照会、専用
mailbox、申請名義、予定domain、provider/account/credential/deployをgateごとに別承認する。rightsと
Affiliateが3社通った場合だけ実source/adapterへ進み、P15実環境11証拠、30日shadow、observed EPCを順に
採取する。P17は実P12窓とcomplete settlementだけを追記し、最大180日後も未達ならSTOPまたはmanual-onlyへ縮小する。
