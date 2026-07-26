# External action packet — adversarial acceptance

基準日: 2026-07-22<br>
状態: P11 local contractと認証SQLite guardを実装。実外部操作、credential配置、deploy、publicationを許可しない。

## 1. 目的と判定境界

この文書は、Humanが承認した1件の外部操作を、別roleのexecutorが実行し、検証可能な
receiptとappend-only journalを残すためのend-to-end受入契約を定める。P11が実装するのは外部callを伴わない
authorization、local claim/receipt state、journal foldまでであり、provider exactly-onceはP13/provider統合で検証する。
対象actionは次の4種だけである。

1. `send_rights_inquiry`
2. `submit_affiliate_application`
3. `activate_public_release`
4. `disable_public_release`

`source_fetch`、Affiliate link変更、価格取得、promotion、rollback、支払、契約同意、account作成、
credential発行はこのpacketのactionではない。自由記述、URL、prompt、AI判断からactionを推測してはならない。

受入は次の3層を分離する。

- **Authorization:** canonical `ExternalActionRequest`へ、Human `GO`の`HumanExecutionApproval`と短命の
  `ControllerExecutionGrant`がexactに結合されている。
- **Execution:** fixed downstream runtimeとauthenticated SQLite guardは、独立に固定したtrust/policyとcurrent stateで
  request、approval、grant、activation時のP10を再検証し、compare-and-swapで1回だけclaimする。
- **Evidence:** P11は合成hash-only outcomeのexecutor署名`ActionReceipt`とjournal foldを検証する。実external resultと
  poststateの独立readbackはprovider adapter側の未充足要件である。

`GO`は指定action 1件の許可であり、別action、別environment、別vendor/property/releaseへの一般権限ではない。
署名が正しくてもbinding、freshness、prestate、persist済みrevocationのいずれかが不正ならlocal claimを拒否する。
journal不正を全executorの副作用前STOPへ連動するglobal latchはP11に存在せず、P13の必須要件である。

## 2. 共通の正本と状態機械

executorはpacket自身が運ぶkey、policy、clock、environment、endpointを信頼根にしない。起動時に次を独立に
pinする。

- Human/controller/executorのissuer、role、public key IDとpublic key
- actionごとのexact scope、許可environment、最大TTL、必須target field
- production property/domain、vendor/program allowlist
- P10 assurance policy SHA-256とcontroller key（`activate_public_release`だけ）
- local durable idempotency store ID、外部monotonic anchor pin。journal ID/headのsingle-writer pinとglobal latchはP13

local guardは新規作成と再openを分離し、固定store ID、SQLite state file、認証companion anchor、HMAC state head、
exact schema fingerprint、write read-back、別障害領域からread/commitするmonotonic anchor pinをtransactional CAS正本とする。
同じ構成のrestart後replay、空DB再生成、行削除、DB+companion anchorの旧版差替え、trigger置換を拒否する。
production adapterは外部固定monotonic anchor/KMS、approved shared store、worker fencing、provider idempotency、
backup/restoreとtrusted clockを固定し、stateを復元できなければ外部callを開始しない。

local testのmonotonic pinは同一test processのmemory実装であり、production trust serviceではない。DB commit、companion
anchor更新、external pin commit間のcrashはauthorityを広げずfail closedになるが、P11に自動復旧はない。またPythonの
private属性はmalicious same-process pluginへのsecurity boundaryではないため、credentialとprovider adapterはP13で
out-of-process/fenced serviceへ隔離する。

packet、claim、receipt、journal entryはcanonical serializationからSHA-256を計算する。未知field、欠落field、
actionに不要な権限field、非canonical enum、重複IDはvalidation errorとし、自己再hashで救済しない。

Human署名の`HumanExecutionApproval`はexact `ExternalActionRequest`と、action、environment、target、
payload/config SHA-256、property/domain、
該当するrelease binding、prestate、not-before/expiry、idempotency keyを含むexecution scopeへ結合する。wildcardと
未固定targetは禁止する。`ControllerExecutionGrant`は同じrequest、approval、policy、scope、prestateへ結合し、
controllerの署名だけでHuman STOP/CONDITIONALを上書きできない。`ActionRevocation`はrequest/grantの権限を除去する
だけで、外部disable、rollback、別actionを自動実行しない。

claim時刻とreceipt completionはstore/file-lock CAS transaction内のdurable write前にguardへ固定したclockから取得する。packet/caller
時刻は権限にならない。低水準の
`ExternalActionRuntime.verifies_artifacts()`は署名・binding・freshness検証であって実行許可ではなく、外部開始に使えるAPIは
durable stateを同じtransactionで確認する`ExternalActionExecutionGuard.claim()`だけである。

```text
draft
  -> authorized
  -> granted
  -> claimed
  -> external_call_started
  -> externally_observed
  -> started
  -> succeeded | failed | partial | unknown
  -> journaled
```

次はterminalまたはHuman介入状態である。

- `denied`: authorization/binding/policy/prestate不正。外部callは0回。
- `expired`: claimまたはcommit時点で期限切れ。外部callは0回。
- `revoked`: irreversible call前にrevocationを観測。外部callは0回。
- `succeeded`: `ActionReceipt.result`が`succeeded`で、observed poststateがexpected poststateと完全一致する。
- `failed`: providerが明示的に失敗した、またはpoststateが期待predicateと不一致だった。
- `partial`: providerが一部だけ変更した。成功ではなく、自動retry禁止。
- `unknown`: timeout、応答欠落、process crash等で副作用の有無を証明できない。自動retry禁止。
- `conflict`: 同一IDの異payload、prestate drift、journal競合。外部callは0回。

`receipt`がない状態を成功にしない。`journaled`前のreceiptは外部完了証拠候補であり、運用上の完了ではない。
receiptはoutcomeの終端だがjournalの終端ではない。後着した正規revocationは既存chain末尾へappendし、過去entryや
receiptを書き換えず`authority=revoked`とfactual outcomeを同時に保持する。

## 3. 4 actionのpositive lifecycle

| Action | Authorizationとprestate | 1回だけ行う外部操作 | 必須poststateとreceipt | 禁止する読み替え |
|---|---|---|---|---|
| `send_rights_inquiry` | Human `GO` approvalとcontroller grant、exact vendor/property/environment、approved contact record hash、inquiry payload hash、未送信prestate | 固定adapterで同じpayloadを1回送信 | provider message/thread IDのhash、accepted/sent時刻、送信payload hash、送信済みpoststate、executor署名receipt | 送信receiptはrights承認・取得許可・回答真正性ではない |
| `submit_affiliate_application` | Human `GO` approvalとcontroller grant、exact vendor/program/property/environment、application payload/disclosure/legal-identity record hash、未申請prestate | 固定adapterで1回申請 | submission ID/statusのhash、accepted時刻、payload hash、`submitted` poststate、executor署名receipt | `submitted`/`pending`はAffiliate承認、CTA利用許可、報酬条件確定ではない |
| `activate_public_release` | Human `GO` approvalとcontroller grant、production execution scope、current P10 `public GO`、exact release/manifest/artifact/local report/public report/policy、inactiveまたは承認済みprevious prestate | exact immutable artifactをtarget propertyのcurrentへ原子的にactivate | provider deployment/current-pointer hash、外部probeで同一artifact、protected route/asset、CTA/expiry、activation時刻、executor署名receipt | P10 local ready、Human `CONDITIONAL`、deploy成功だけを公開成功にしない |
| `disable_public_release` | Human `GO` approvalとcontroller grant、exact production propertyとcurrent release tuple、disable scope、current active prestate。P10 GOやrightsの有効性は停止を妨げない | lease/current servingを失効させ、protected contentとCTAを停止 | current disabled hash、protected route/assetのgeneric 503、CTA無効、health/robotsだけ固定応答、executor署名receipt | disableは削除、rollback、別release activation、再公開許可ではない |

P11はlocal claimのCAS直前にauthorization、expiry、persist済みrevocation、bound prestate hashを再検証する。
independent external prestate readbackとirreversible commit直前の再検証はP13/provider adapterの必須要件である。
`activate_public_release`はP10 authorization、Human approval、controller grantが同じrelease tupleへ一致する場合
だけ進む。`disable_public_release`は安全停止を失効したP10 reportへ依存させないが、古いdisable packetを新しいreleaseへ
適用することも禁止する。

## 4. Adversarial acceptance matrix

このmatrixはend-to-end正本である。P11では外部call自体が存在しないため、`external call count`、provider readback、
global executor stopは実測済みと扱わない。表中の**拒否**はproduction統合後に「外部call 0回、secret/URL/payloadを
含まないtyped reason」を意味する。現在の
`ActionJournalEntry`は有効なgrant以後のgrant/claim/revocation/receiptだけを扱う。claim前のdenial/expiryを
durable operator auditへ記録する機能はproduction adapter側の未充足要件であり、P11 journalへ捏造しない。
**不確定停止**は「自動retry 0回、対象action IDをlock、外部照合または新しいHuman decision待ち」を意味する。

| ID | 対象 | 反証・故障注入 | 期待結果 | 必須観測 |
|---|---|---|---|---|
| A-01 | 全action | 正規request、Human GO approval、controller grant、executor key、scope、policy、target、prestate、時刻 | P11: 4 actionのlocal lifecycle。P13/provider: action固有positive lifecycle | P11はcall 0。後続でexternal call count = 1、provider receipt、連続journal |
| A-02 | 全action | request/approval/grant署名またはself-hashなし、署名bit改変、attacker key、未知key ID | 拒否 | claimなし、external call count = 0 |
| A-03 | 全action | 正しい署名だがHuman/controller/executorのrole違い、同一keyのrole使い回し | 拒否 | pinned role/key分離reason |
| A-04 | 全action | scopeが別action、wildcard、複数action、別propertyを許す | 拒否 | exact scope比較。部分一致・prefix一致を禁止 |
| A-05 | 全action | policy/config SHA-256だけを差替え、またはattacker Authority/policy/config/keyを同時差替え | 拒否 | downstream runtime側pinned trust/policy/configとの不一致 |
| A-06 | 全action | `ExternalActionRequest`をcopyし、actionまたはtargetを変更して自己hashも差替え | 拒否 | Human approval/controller grant binding不一致。endpointを自由記述から選ばない |
| A-07 | 全action | unknown action、alias、大文字小文字差、actionに不要な高権限field | validation error、拒否 | strict discriminated union、external call count = 0 |
| A-08 | 全action | staging packetをproductionへ、production packetを別account/regionへ使用 | 拒否 | exact environment/account binding |
| A-09 | rights/affiliate | vendor ID、program ID、contact authorityのいずれかを差替え | 拒否 | allowlistとpacket/approval/payloadのexact vendor binding |
| A-10 | 全action | property/domainを差替え、subdomainやlook-alike domainへ拡張 | 拒否 | normalized exact property binding。suffix一致禁止 |
| A-11 | activate/disable | release IDだけ差替え、または別releaseの正規IDを再利用 | 拒否 | release/manifest/artifact/reportの同時一致 |
| A-12 | activate/disable | manifest SHA-256を別releaseまたはself-rehash copyへ変更 | 拒否 | P10、packet、current state、provider targetとのcross-binding |
| A-13 | activate/disable | artifact SHA-256と実配信bytesの片方だけを変更 | call前は拒否。call後は`failed`/`partial`/`unknown`で成功にしない | content-addressed readbackとexternal probe。必要なら別承認のdisable request |
| A-14 | activate | local reportまたはpublic reportを別release/policyから流用 | 拒否 | P10 authorization core、local/public report hashのexact binding |
| A-15 | activate | P10 reportは`local ready`だがpublic decisionはSTOP | 拒否 | external call count = 0、公開権限なし |
| A-16 | 全action | `HumanExecutionApproval.decision`が`STOP` | grantを作らず拒否 | STOPを有効署名として監査するが実行しない |
| A-17 | 全action | Human decisionが`CONDITIONAL`、条件文字列が「実行可」に見える | grantを作らず拒否 | structured decisionが`GO`以外なら実行しない |
| A-18 | activate | P10 Human approvalがSTOPまたはCONDITIONAL | 拒否 | external-action GOでP10不足を上書きできない |
| A-19 | 全action | request `not_before`またはapproval/grant `issued_at`が評価時刻より1 microsecond未来 | 拒否 | future/not-yet-valid reason、external call count = 0 |
| A-20 | 全action | `at == expires_at` | 拒否 | 半開区間`issued_at <= at < expires_at` |
| A-21 | 全action | TTLがaction policy最大値を1 microsecond超過 | 拒否 | issuerが正しくても過長TTLは無効 |
| A-22 | 全action | TTL最大値ちょうど、全binding current | 許可 | 境界値を勝手に短縮・延長しない |
| A-23 | 全action | authorizationはclaim時current、その後completion前にexpired | claim前ならexpired停止。claim後は権限を再利用せず、実際に観測できた結果だけをreceiptへ記録。不明なら`unknown` | claim/start時刻とcompletionをreceipt/journalへ記録 |
| A-24 | 全action | packetのprestate hashは正しいが、claim前にexternal stateが変化 | provider統合でconflict、拒否 | P11はcaller supplied hash bindingのみ。後続でindependent current prestate readback |
| A-25 | activate/disable | claim後、commit前にcurrent release pointerが変化 | conflict、拒否 | 古いpacketを新currentへ適用しない |
| A-26 | rights/affiliate | 別channelから同じ問い合わせ/申請が既に完了 | conflictまたは既存正規receiptへ収束。再送信禁止 | provider-side lookupとpayload fingerprint |
| A-27 | 全action | claim直前にrequest/grant/approver key/policy/targetが`ActionRevocation`でrevoked | revoked、拒否 | revocationのrequest/grant bindingとeffective time |
| A-28 | 全action | claim後、irreversible call直前にrequest/grant revocation | revoked、拒否 | commit直前の2回目revocation check。別actionを自動実行しない |
| A-29 | activate | activation start後、receipt前にrequest/P10/rights/affiliateがrevoked | receiptは実際のprovider resultを記録するが、revocationで過去の開始を改変せず、現在の公開権限にも使わない | P13 serve-time 503、別Human GOのdisable request。自動disable禁止 |
| A-30 | disable | disable中にapprovalがrevoked | 既に停止済みなら停止を維持しreceiptへraceを記録。再activation禁止 | fail-safe poststate、Human review |
| A-31 | 全action | 同一grant/action ID・同一canonical requestを完了後にreplay | P11は2回目local claimを拒否。provider exactly-onceは後続 | local claim cardinality。後続でprovider call count累計1とreceipt照合 |
| A-32 | 全action | 同一action IDだが1 fieldだけ異なるpayload | conflict、拒否 | original packet hashを保持、上書き禁止 |
| A-33 | 全action | 異action IDだが同じone-shot target/payload/window | duplicate conflict。自動で2回実行しない | semantic idempotency keyとprovider lookup |
| A-34 | 全action | external call timeout/connection resetで結果不明 | 不確定停止、自動retry禁止 | action ID lock、provider reconciliation待ち |
| A-35 | 全action | providerがpartial successまたはmulti-step途中で失敗 | `partial`。副作用範囲も不明なら`unknown`。`succeeded`を発行しない | signed terminal receipt、step bitmap、poststate hash |
| A-36 | 全action | `ActionReceipt`署名欠落、wrong executor key/role/scope、wrong request/grant binding | 成功として受理しない | fixed runtimeのreceipt verifierが拒否、action lock維持 |
| A-37 | 全action | receiptは`succeeded`だがobserved poststateが欠落 | receiptを拒否し、folded stateを成功にしない。自動retry禁止 | required field/署名payload不正、actionをreconciliation待ちにlock |
| A-38 | activate | provider deploy成功だがpublic bytes/artifact、CTA、expiryのいずれか不一致 | `failed`/`partial`/`unknown`、P13は503、別承認のdisableを要求 | protected routeとstatic assetのactual HTTP probe。自動disable禁止 |
| A-39 | disable | APIはsuccessだが1 routeまたはassetが200/cache hit | `failed`または`partial`、SEV0、再公開禁止 | 全protected path/asset 503、cache purge/readback |
| A-40 | 全action | receiptのtarget/action/poststate/packet hashを1 field改変し自己再hash | 成功として受理しない | executor署名とpacket bindingを再検証 |
| A-41 | journal | expected sequence `n`の次に`n+2`をappend | P11 fold拒否。P13 global latchで全executor停止 | gap reason。P11単体は外部processを停止しない |
| A-42 | journal | entry順序を入替え、過去entryを削除、previous hashを差替え | P11 fold拒否。P13 global latchで全executor停止 | hash-chain/sequence再検証と後続STOP連動 |
| A-43 | journal | 同一sequenceへ異なる2 entry、または2 writerが同時append | conflict、両方を成功扱いしない | single-writer/CAS、conflict quarantine |
| A-44 | journal | 同一action IDへ異なるreceipt、または同一receipt IDへ異action | P11 durable receipt/fold拒否。P13 global latchで全executor停止 | action ID/receipt ID unique constraintと後続STOP連動 |
| A-45 | journal | external `succeeded` receiptはあるがjournal append前にprocess crash | 再実行せずrecoveryへ | receipt signatureとprovider poststateから同じentryを1回append |
| A-46 | journal | grant/claim/revocation/receiptの途中entryだけを削除して残りを成功履歴にする | audit invalid、公開・追加action停止 | predecessorを含む完全hash-chain |

## 5. Action固有の追加反証

### `send_rights_inquiry`

- contact recordやpayload hashが同じでもvendor/propertyが異なれば別actionであり、使い回さない。
- providerの自動返信、delivery receipt、担当者名だけをrights approvalへ昇格しない。
- timeout後に同じメールを再送せず、sent folder/provider APIをHuman領域で照合する。
- raw mail本文、個人email、署名、thread URLをreceipt/journalへ保存せず、approved storeのhashだけを残す。

### `submit_affiliate_application`

- applicationの`submitted`、`received`、`pending`、`approved`を別statusとして固定mappingする。
- application receiptからprogram approvalや実CTAを生成しない。別のAffiliate decision evidenceを要求する。
- vendor/program/property/legal identity/disclosureのどれかが変われば新しいHuman GOを要求する。
- duplicate submissionをproviderが受理しても、2件を2 approved partnerとして数えない。

### `activate_public_release`

- `ReleaseAssuranceRuntime`がpinned controller key、P10 policy hash、最大TTL、現在時刻で許可することをactivation
  の必要条件にする。report自身のkey/policyをtrust rootにしない。
- P10 authorization、external action packet、manifest、artifact、provider poststateの
  `release_id / manifest_sha256 / artifact_sha256`を完全一致させる。
- Humanのexternal-action GOは、P10 local test、BusinessDossier、TCO/QA署名、Human public GOの欠落を補えない。
- deployment APIのsuccessだけで完了せず、別network pathからdocumentとstatic assetを取得し、content hash、CTA、
  security header、cache、expiryを検証する。

### `disable_public_release`

- current P10 authorizationやServingLeaseが失効していても、正規disable actionを拒否する理由にしない。
- exact current releaseへのdisableだけを許し、古いpacketで新releaseを停止するreplayを拒否する。
- health/robots以外のdocument、JavaScript、CSS、image、favicon、framework routeをdeny-by-defaultで確認する。
- 停止後もrelease/receipt/journalを削除せず、再activationには新しいP10 GOと新しいexternal-action GOを要求する。

## 6. Receiptとjournalの完了条件

現在のterminal `ActionReceipt`は次を署名payloadへ含める。

- request ID/SHA-256、grant SHA-256、claim SHA-256、policy SHA-256、idempotency key、exact action
- environment、prestate SHA-256、poststate SHA-256、provider operation/audit receipt SHA-256
- call startとcompletionのUTC時刻、result (`succeeded | failed | partial | unknown`)
- executor issuer、role、scope、key ID、receipt payload SHA-256、署名

approvalはgrantとclaimを通じてtransitiveに、vendor/property/target/releaseはrequest SHA-256を通じて
transitiveに結合される。journal predecessorは`ActionJournalEntry`側へ結合する。別時刻のexternal observation、
provider step bitmap、direct target fieldsが必要なadapterはprovider-specific receipt versionを追加し、現行fieldが
存在するかのように扱わない。

`partial`、`unknown`、poststate mismatchは成功ではなく、`succeeded`かつexact poststateだけがpositive lifecycleを
満たす。receiptは外部の事実や許可を作らず、観測した結果だけを証明する。receipt verifierはpacket、pinned executor key、action scope、
全target、時刻、poststateを再検証する。secret、credential、実Affiliate URL、raw mail、application本文、provider
response本文をreceiptへ入れない。

journal entryはsequence、previous entry SHA-256、request/grant/idempotency SHA-256、event kind/payload SHA-256、
append時刻をcanonical署名対象にする。P11 foldはsequence gap、reorder、fork、同一actionのconflicting receiptを拒否するが、
新規外部actionを止めるdurable global latchはP13が実装する。reportは評価に使用したstore ID、revision、外部pin済みanchor
hashを結合し、返却直前にrevision/headが変わればfail closedにする。request/idempotency/grantごとにterminal receiptは
1件だけである。journal修復は欠落を捏造せず、
provider poststateと正規receiptを使う独立Human手順とする。

## 7. 未充足の後続gate

### P12 — local measurement integrity: **実装済み / 実測未充足**

このP11 packetとreceiptだけでは、Gate C/DまたはPhase 7の測定真正性を作らない。P12の
開始前freeze、producer署名、stage coverage、transaction/payout/logical-run/exact-fault
runtimeはlocal実装済みだが、次の実producer/実測は未充足であり、本matrixのpositive
actionだけでは合格しない。

- approved real producer key、complete export signatureとconsumer固定anchor
- 実JP/ja需要の分子・分母・sample/coverage、重複除去、bot/internal filter
- 30日shadowのplanned run、全retry/exception、人手activity、必須8 fault IDの完全ledger
- qualified session -> outbound -> Affiliate click -> transaction status -> payoutの照合
- confirmed/paid排他遷移、refund/chargeback、new-acquisition判定、provider reconciliation

`send_rights_inquiry`はrights approval evidenceではなく、`submit_affiliate_application`はapproved partner evidenceでは
ない。`activate_public_release`で得たtraffic/revenueも、P12 collectorとreconciliationがない限りGate C/D、EPC、
月20万円の実績証拠へ使わない。

### P13 — two-stage production consumer: **未充足**

このmatrixはactivation contractを定義するが、production Worker/HTTP adapterを実装しない。次のtwo-stage consumer
が実装・actual HTTP検証されるまで、`activate_public_release`のend-to-end positive caseは**BLOCKED**である。

1. activation/promotion時にP10 `ReleaseAssuranceRuntime`がcontroller authorization、policy、report、
   release/manifest/artifact、TTLを固定trust rootで検証する。
2. request時にP9 serving leaseを固定controller key、scope、current state、artifact、TTLで再検証し、documentと全static
   assetをworker-firstで保護する。

P10だけ、P9だけ、action receiptだけ、provider deploy successだけでは200を許可しない。state/KMS/store/clock/probe
障害、exact expiry、revocation時はhealth/robots以外をgeneric 503へ閉じ、cache済み保護contentも配信しないことが
P13の受入条件である。

## 8. P11完了判定

P11で合格と呼べるのは、4 actionのrequest/approval/grant/revocation/runtime/claim/receipt/journal契約と、
A-01〜A-46のうちproviderやdurable substrateを要しない反証がlocalで決定論実行できる状態までである。
provider call count/readback、commit直前check、actual probe、shared/distributed fencing、durable operator journalと
global STOP latchを要するA-01/24/25/26/28/29/30/31/33/38/39/41/42/43/44/45/46の
end-to-end確認はP13またはprovider integrationの受入項目として残り、免除されない。実providerへのcall、実送信、
実申請、実activate、実disableは、外部account/credential、P12、P13、action固有Human GOが揃うまで実施しない。
