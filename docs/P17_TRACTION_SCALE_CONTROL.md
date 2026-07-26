# P17 traction and scale control

基準日: 2026-07-22

## 目的

P17は、公開後Phase 7–8の30日観測をP12の完全packetから再検証し、最大180日のtractionを改変不能な順序で
保存するlocal-only境界である。出力は`STOP | CONTINUE_OBSERVATION | READY_FOR_SCALE_REVIEW`であり、最後の値も
Human review入力にすぎない。広告費、提携先変更、公開、deploy、外部writeは一切許可しない。

## 信頼経路

1. Human Approver署名のplanと3役trust storeがproperty、release/artifact/schema、3社以上の固定partner set、P12 policy/trust、
   settlement policy/trust、権利・affiliate evidenceと期限、180日窓を固定する。
2. ingest時に`P12AuthorityPacket`のrun plan、3 batch、3 producer attestation、bundle indexを
   `MeasurementIntegrityRuntime.evaluate`で再実行し、新しく発行されたreportと完全一致させる。
3. P17 observationはP12の全hash、30日窓、TCO/QA署名、HMAC再トークン化したclick/transaction identityに加え、
   task schedule、execution receipt、匿名化human activity、resource usage、cost policyと再計算summaryを保持する。
   aggregateだけの差替えは拒否する。raw ID、URL、account、PII、credential、非公開報酬は保持しない。
4. `TractionLedger`は0600 SQLite、STRICT schema、UPDATE/DELETE trigger、file lock、`BEGIN IMMEDIATE`、
   HMAC、全event hash chain、外部monotonic anchorで観測・settlement snapshot・評価reportと、そのpost-anchor
   finalizationの末尾追加だけを許可する。完全一致再送はrevision-neutralである。
5. cohort終了後の確定・返金・chargebackは、元P12 transactionを固定したSettlement Amendmentでだけ反映する。
   cohort、partner、通貨、原額、click、attributionは変更できない。0イベントでも完全exportと独立TCO/QA署名が要る。

P12 reportは期限切れになるため、通常のcurrentnessはingest時に検証する。append/evaluateは呼出側日時を受け付けず、
別鍵の`TIME_AUDITOR`が正確なledger revision/head、purpose、subject hashへ署名した時刻だけを使う。全eventで時刻後退を
拒否する。署名requestは各メソッド内部で新しいrandom nonce付きでオンライン発行し、事前取得receiptや別stateへの
replayを受け付けない。target eventをDBと外部anchorへcommitした後に、同じtargetと期限をbindする2回目の時刻署名を
取得し、finalization eventもcommit・anchorする。callbackはpolicy固定1–30秒でtimeoutし、ledger lockを無期限保持しない。
SQLiteのprocess間file lockとexternal anchor read/commitも固定deadlineを持ち、hung callbackは現在の呼出しを
fail closedにする。anchor callback専用のprocess共有flockは、呼出側がtimeoutしても実callbackが終了するまでworkerが
保持する。同一hostのretry/reopenは古いcallbackと並行せず固定deadlineでSTOPし、古いrevisionの遅延commitが新しい
revisionを巻き戻せない。callback終了後の明示的retry/reopenだけがone-ahead状態を回復する。multi-hostでは同じ保証を
外部anchor serviceのCAS/idempotencyで実装する必要があり、local flockを代替にしない。
停止中workerは置換不能なfilesystem root directory inodeへhost-globalのnonblocking flockを保持し、同一hostで
最大1本だけ追跡する。生存中の再試行、別instance、別process、hard-link別名は新しいthreadを作らず即時STOPする。
fork前後handlerはFD registryを同期し、子processは継承したworker FDと通常のledger file-lock FDをcloseして
registryを初期化するが、親lockは解除しない。親がcrashしても長寿命の子がいずれのlockも孤児化せず、kernelが解放する。
FDはcallerとworkerが共有するone-shot leaseで追跡し、どちらか一方だけがunlock・closeできる。worker開始前の
owner allocation、registry登録、fstat/flock/Queue/Event/Thread/start失敗はcallerが回収し、開始後に`start()`や
ownership通知が例外になった場合はworkerの`finally`だけが回収する。FD番号が再利用されても二重closeせず、
host-global lockを例外後へ残さない。
target commit後の一時失敗またはDBがanchorより1 revision先行したcrashは、唯一の未確定tailだけを再検証・anchor回復して
再finalizeする。回復時刻が期限以上ならtargetは削除・採用せず、署名付き`expired` tombstoneをchainへ残してactive projection
から除外する。後日の評価では、認証ledgerに保存された当時の署名、time attestation、chain、anchorを検証し、古いreportを
現在時刻で再current判定しない。settlement artifactは評価時にcurrentで、各窓終了から固定30日後までを完全にcover
しなければ成熟判定へ使えない。

settlementは評価引数として一時注入できない。署名・scope・complete coverageを検証したsnapshotを先に台帳へ追記し、
評価は各観測の最新snapshotだけを読む。reportはその全evidence hash、評価前のevent revision/head、trusted-clock hashを
commitし、report自体も次のeventとして保存・anchorする。
古いsettlement envelopeのTTL後は、過去のevent IDと内容を完全保持した新しい署名envelope・completenessへ更新できる。
旧eventの欠落・変更とcoverage後退は拒否し、期限切れ署名そのものを現在時刻で再検証し続けない。
各観測のraw最新settlementが`expired`なら、それ以前のaccepted snapshotへfallbackしない。返金を含み得る最新情報の
確定失敗を旧売上で覆い隠さず、次のfresh accepted snapshotまではsettlement evidenceなしとしてfail closedにする。

日常運用は`TractionRuntimeBroker`だけを受け取る。別権限のbootstrap portがKMS由来state-MAC key、trusted clock、
外部anchorを使って完成済み`TractionLedger`を開き、brokerへ返す。brokerのappend observation、append settlement、
evaluate、read APIにはkey、signer、clock callback、anchor callbackが存在しない。CLI・環境変数・repositoryから
秘密を発見するfallbackも実装しない。production bootstrap service自体のKMS/anchor/clock接続は環境gateである。

## 数式と時間粒度

P12の「月」はAsia/Tokyo 00:00境界の連続30日半開区間で、暦月ではない。欠測・重複・overlapは補完せず拒否する。

- 累積: `clicks = Σ valid_clicks`、`settled = Σ amended_settled`、`EPC = settled / clicks`、covered days。
- 最新30日: 実settled売上、運用TCO、`net operating profit = settled - labor - resource`、`CTR = valid_clicks / qualified_sessions`、partner share、運用品質。
- maturity: 累積valid clickが1,000以上、または連続covered daysが180以上。
- capacity: `bear_sessions × settled × click_rate >= (target_net_profit + operating_TCO) × clicks`をexact cross multiplicationで判定し、
  表示用の必要click/sessionだけを別に算出する。
- settlement後の売上・EPCは、正しい返金により減少できる。monotonicを要求しない。

成熟後の全条件は、EPC 60円以上、最新net operating profit 20万円以上、CTR 10%以上、partner 3社以上、最大share 40%以下、
automation 80%以上、人手720分以下、logical job 99%以上、重大誤表示0、例外24以下、exact fault 8/8、bear capacity
合格である。境界の正本は`docs/P17_BOUNDARY_MATRIX.md`とする。

## 判定

- empty、synthetic混入、署名・pin・chain・scope・clock不正は`STOP`またはingest拒否。
- 未成熟でprovenanceとhard operationsが正しく、settlementがまだprovisionalなら`CONTINUE_OBSERVATION`。
- 成熟時にsettlement不完全、EPC未定義/60円未満、または一つでもscale gate不合格なら`STOP`。
- 全て満たした場合だけ`READY_FOR_SCALE_REVIEW`。reportは常に`authority=none`、
  `purpose=human_scale_review_input_only`、`external_mutation_authorized=false`である。

## local CLI

```bash
uv run saas-preflight evaluate-traction \
  examples/p17/blocked/evidence-bundle.json \
  --plan examples/p17/blocked/plan.json \
  --policy examples/p17/blocked/policy.json \
  --trust-store examples/p17/blocked/trust-store.json \
  --authority-pins examples/p17/blocked/authority-pins.json \
  --settlement-policy examples/p17/blocked/settlement-policy.json \
  --settlement-trust-store examples/p17/blocked/settlement-trust-store.json \
  --at 2026-07-31T15:00:00Z
```

checked-in fixtureは観測0件でexit code 3、`STOP`である。CLIはlocal JSONと明示UTC時刻だけを読み、network、DB
write、subprocess、deploy、publishを行わない。このCLIは未永続化packetの診断専用で、構造上
`READY_FOR_SCALE_REVIEW`を生成しない。READY候補は認証済み`TractionLedger.evaluate`経路だけである。

## 外部再開条件

P11–P17 local候補の一括Human受理後も、実rights、Affiliate 3社、公開承認、実P12 producer、実30日観測、
settlement完全export、KMS/anchor/clock、domain/cloud credentialが別に必要である。これらを取得するまでは事業・公開・
scale状態は`STOP`であり、synthetic fixtureを実績へ読み替えない。
