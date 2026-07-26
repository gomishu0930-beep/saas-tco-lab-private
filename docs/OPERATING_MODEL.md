# SaaS比較Preflight 運用モデル

## 1. 目的と基本原則

この運用モデルは、Evidence、data contract、TCO、releaseを分業し、判断の独立性を保ちながら、月の人手を720分以内に制御するためのものです。自動化率を上げても、権利判断と外部・公開操作の責任はHuman Approverに残します。

すべての処理は次の順序を守ります。

`権利確認 → 型付き証拠 → strict contract → 決定論TCO/QA → release候補 → 人の承認 → 機械的promote`

AIは証拠探索、候補値抽出、実装、テスト、差分説明を支援できますが、権利の承認、曖昧値の確定、canonical dataへの直接write、公開判断は行いません。

## 2. 役割

### Evidence/Policy Steward

責務: sourceのauthorityと利用権を調査し、field単位の取得・保存・表示・履歴・派生利用をpolicy化します。期限、attribution、許可host/method、撤回条件を管理します。

- 入力: 公式URL、terms、robots、API/affiliate条件、書面許諾、必要field一覧
- 出力: `source_policy`案、最小`EvidencePointer`、権利期限、許可host/method、拒否・要確認理由
- 非権限: 自分のpolicy案を`approved`にすること、曖昧な規約を許諾と解釈すること、全文archiveを許可すること

### Contract/Storage Engineer

責務: Pydantic modelを唯一のschema authorityとして、strict validation、JSON Schema生成、append-only observation、migration、storage boundaryを所有します。

- 入力: 承認済み`source_policy`、field定義、EvidencePointer、schema change request
- 出力: version付きmodel/schema、migration、append-only repository、data dictionary、storage test、checksum
- 非権限: 未承認sourceを保存すること、raw全文保存を既定化すること、TCO式やrightsを独自変更すること

### TCO/QA Engineer

責務: 12か月TCOの純粋関数、gold/fault fixture、unit/property/regression test、重大誤表示0の判定を所有します。実装者と独立した反証を最低1件実施します。

- 入力: version付きcontract、承認済みgold set、計算仕様、期待値、既知の曖昧点
- 出力: TCO結果、test report、fixture checksum、false-change/coverage指標、未計算理由、release可否勧告
- 非権限: 不明な税・通貨・単位を補完すること、失敗testをwaiveすること、公開を承認すること

### Integration/Release Operator

責務: 所有者間のinterfaceを統合し、lock/schema/scan/testを実行し、immutable release候補とrollbackを準備します。運用キュー、人手時間、障害とSLOを管理します。

- 入力: 各役割のversion付きartifact、test report、承認記録、release request
- 出力: 統合結果、release manifest、artifact hash、expiry一覧、差分、rollback/kill-switch手順、運用時間台帳
- 非権限: source rightsや事業判断の代行、失敗検証の無視、無承認のexternal write・push・deploy・公開

### Human Approver

責務: 法務・契約・事業・費用・reputationを伴う判断を引き受け、GO、STOP、条件付き承認をscopeと期限付きで記録します。この役割はAIやagentへ委任できません。

- 入力: rights dossier、schema/TCO差分、test/scan結果、KPI、費用、外送・権限一覧、rollback案
- 出力: signed decision（`GO | STOP | CONDITIONAL`）、scope、条件、有効期限、承認者、時刻
- 専有権限: source rights、全文archive、外部account・課金・credential、production write、公開・rollback、affiliate link変更、重大例外

## 3. RACI

R = 実行、A = 最終説明責任、C = 事前相談、I = 結果通知。1行につきAは1役割です。

|活動|Evidence/Policy|Contract/Storage|TCO/QA|Integration/Release|Human Approver|
|---|---|---|---|---|---|
|source候補・規約調査|R|I|I|I|A|
|`source_policy`案作成|R|C|I|I|A|
|rights承認・期限延長・撤回|R|C|I|I|A|
|通常の承認済みsource観測|A|R|I|C|I|
|data contract/schema/storage|C|R/A|C|C|I|
|TCO仕様・純粋関数・gold/fault test|C|C|R/A|I|I|
|重大誤表示・品質gate判定|C|C|R|I|A|
|dependency/plugin/MCP導入票|C|C|C|R|A|
|統合・release候補・rollback準備|I|C|C|R/A|I|
|external write・push・deploy・公開|I|I|C|R|A|
|定常monitoring・一次incident対応|C|C|C|R/A|I|
|権利・privacy・secret incident対応|R|C|C|C|A|
|KPI、月20万円目標、GO/STOP|C|I|C|R|A|

Human ApproverがAでも、証拠収集や実装のRにはなりません。Human Approverの承認が必要な行は、承認なしではIntegration/Release Operatorが実行できません。

## 4. 型付きhandoff

handoffは共有artifactで行い、口頭、チャット、AI要約だけでは完了とみなしません。受領者は必須項目が欠けたpacketをfail-closedで差し戻します。

### Evidence/Policy → Contract/Storage

必須: `source_id`、公式URL/publisher、authority、rightsの5軸（fetch/store/display/history/derive）、allowed host/method、attribution、最小引用、承認者・承認時刻・有効期限、撤回条件、証拠hash。

受領条件: 全軸が`approved`または明示的`denied`であり、未指定軸がないこと。`pending`、期限切れ、規約矛盾は保存処理へ渡しません。

### Contract/Storage → TCO/QA

必須: model/schema version、data dictionary、migration、fixture、fixture checksum、validation result、rights reference、既知のnull/曖昧値。

受領条件: schemaが再生成可能、未知field拒否、append-only test合格、ネットワークなしでfixtureを再現できること。

### TCO/QA → Integration/Release

必須: test対象commit/artifact hash、unit/property/regression結果、gold/fault coverage、重大誤表示件数、false change、未計算理由、反証、release可否勧告。

受領条件: 必須testが全合格、重大誤表示0、曖昧値を計算していないこと。勧告は承認ではありません。

### Integration/Release → Human Approver

必須: release manifest、source/schema/extractor version、rights/data/affiliateの最短expiry、差分、test/scan、KPI、費用・外送・権限、rollback/kill switch、月間人手残量。

受領条件: `prepare`済みでもcurrent pointerを変更していないこと。Human Approverのsigned decision後だけ、決定論的なpromote処理を実行できます。

### Human Approver → Integration/Release

必須: decision、scope、条件、有効期限、承認者、時刻。`CONDITIONAL`は機械検証可能な条件にし、満たせなければ`STOP`として扱います。

### append-only DBの保持期限handoff

SQLiteは証拠履歴のupdate/deleteを禁止するため、権利・保持期限が異なるsnapshotを同じDBへ混在させません。Contract/Storageは1 retention cohortにつき1 DBを作り、Integration/Releaseへ最短`captured_at + retention_days`をhandoffします。期限前に新DBへrotateし、旧DBはHuman Approverの承認後にファイル全体を削除またはcrypto-eraseします。行単位削除、期限延長の推測、承認なしの退避copyは禁止します。

## 5. 承認境界と禁止事項

### 人の追加承認なしで実行可能

- 承認済みlocal依存をlockfileどおりに使用すること
- 承認済みfixtureを用いたlocal test、schema生成、TCO計算、secret scan
- 承認済みsource policy内のreadとappend-only observation
- immutable release候補の`prepare`と、既存公開物を変えないQA
- 同一scope・有効期限内で、signed decision後に行う機械的promote
- 外部callを伴わないP11 request/approval/grant/claim/receipt/journalの合成検証
- 外部callを伴わないP13 global STOP/reset/epoch、固定local subprocess、provider/probe署名の合成検証
- 外部callを伴わないP14 provider fact journal、owner crash recovery、same-host process競合の合成検証
- 外部callを伴わないP15 typed readiness、P13 authority結合、reconciliation ledger/reset bindingの合成検証
- 外部callを伴わないP16 artifact-set/署名/期限/predecessor-chainの最終review handoff検証
- 外部callを伴わないP18 exact-file manifest、verification context、Integration/TCO/Human署名、current-head/root検証

### Human Approverの明示承認が必要

- 新規source、rights変更・期限延長、規約矛盾、全文archive
- 新規dependency/plugin/MCP/AI/API、外部account、OAuth、credential、課金、cloud
- production DB write、external write、push、deploy、公開・非公開化、rollback
- affiliate program/link、表示順位、収益ロジック、public methodologyの変更
- PII、非公開情報、証拠を外部AI/サービスへ送る例外

現在の形式的なrepo承認記録は`AGENTS.md`にあるP0–P10のlocal scopeまでです。P11–P21のlocal
code/docs/testsは本taskの実装指示に基づくworking-tree候補ですが、P18のversion/revision付きHuman acceptanceが未記録の
ため、統合・release承認済みとは扱いません。P11のgrant/claim、P12の合成attestation、P13/P14のsynthetic
provider success、P15のproduction-shaped readiness/authorization、P16のfinal-review-ready report、P17のscale-review勧告を含め、外部source取得・送信・申請・
account・credential・課金・push・deploy・公開・
非公開化操作へ拡張解釈しません。

### 常時禁止

- AI/agent/plugin/MCPによるcanonical DB・本番DB・公開・affiliate linkへの直接write
- raw HTML/PDF/メール全文、credential、Cookie、PII、個人メール、非公開報酬の既定保存・prompt投入・外送
- 税、通貨、請求周期、seat、quota、overage、addon、rightsの推測補完
- robots、規約、rate limit、`Retry-After`、CAPTCHA、login、403、地域制限の回避
- `latest`、未固定install、未審査image、広すぎるOAuth、auto-merge、検証を飛ばしたpublish
- 他roleの所有ファイルの上書き、revert、無断整形、履歴削除
- scheduleやAI出力だけをfreshness・正確性・合法性の保証にすること

## 6. 稼働cadenceと月720分の人手budget

人が操作・判断する時間を、1暦月あたり最大720分（12時間）に制限します。agentの自動実行時間は含めませんが、agentの待機監視を人が行った時間は含めます。5週ある月でも上限は増やしません。

|cadence|内容|担当と配分|月間分|
|---|---|---|---:|
|営業日ごと、非同期10分|権利期限・失敗source・freshness・secret/公開異常の例外だけ確認。正常runは読まない|Evidence 4分 + Integration 6分 × 20日|200|
|週1回、60分|rights/expiry 25分、schema/storage change 20分、gold/fault regression 15分|Evidence 100、Contract 80、TCO 60|240|
|月1回、160分|schema debt 10分、品質/反証 60分、運用/KPI 50分、事業判断 40分|Contract 10、TCO 60、Integration 50、Human 40|160|
|release/decision gate|差分・rollback・費用確認とsigned decision。原則月1回にbatch|Integration 40、Human 60|100|
|incident reserve|SEV0/1専用。通常改善へ転用しない|Human 20|20|
|**合計**|||**720**|

役割別上限は Evidence 180分、Contract 90分、TCO 120分、Integration 210分、Human 120分です。

効率化規則:

- 正常系のdashboard、成功通知、全logを人に読ませず、期限切れ・schema差分・SLO違反・重大誤表示候補だけを1つの例外queueへ集約します。
- 同種の変更は週次または月次releaseにbatchし、context switchingを減らします。
- 人が1件を二度入力しないよう、handoff artifactからrelease dossierを自動生成します。
- 月間消化が576分（80%）に達したら、Integration/Release Operatorは新規sourceと非重大改善を凍結します。720分到達後はSEV0の安全停止とSTOP判断以外を翌月へ送ります。
- 2か月連続で720分を超える見込み、または80%自動化後も12時間を超える見込みなら、source数縮小、機能削減、第一候補STOPの順に判断します。人手超過を未承認AI自動化で埋めません。

## 7. 失敗時escalation

|severity|例|即時動作|ack/判断|owner|
|---|---|---|---|---|
|SEV0|secret/PII流出、権利失効データの公開、重大な誤価格・誤順位、無承認production write|該当field/CTA/releaseをfail-closedで非表示、job停止、credential隔離。raw内容をincident logへ複製しない|Humanへ15分以内に通知、再公開は新しいsigned GOのみ|Human A、EvidenceまたはIntegration R|
|SEV1|TCO regression、schema破壊、release/rollback不能、freshness SLO違反で公開影響|release停止、current維持または承認済みrollback、障害artifact保存|4営業時間以内にack、同営業日にGO/STOP判断|Integration A/R、TCO/Contract C|
|SEV2|単一source parser失敗、429/一時停止、non-critical false change|`Retry-After`内で抑制、上限付きretry後にsource単位でquarantine|2営業日以内、週次queueで処理|該当role R、Integration A|
|SEV3|改善案、軽微な表示/保守性、将来dependency更新|通常運用を止めずbacklog化|次回週次/月次で優先度判断|Integration A、該当role R|

次の条件ではseverityに関係なくHuman Approverへescalateします。

- rights、license、terms、retention、外部AI training利用が不明または矛盾する
- 同じsource/原因で3回連続失敗する、またはfaultが複数sourceへ波及する
- 重大誤表示候補が1件でもある、affiliate linkや順位が意図せず変わる
- credential、OAuth scope、network destination、月額費用が承認票から変わる
- 人手budgetが80%へ達する、または月20万円の成立条件を変えるKPI差分が出る

incident終了条件は、原因と影響範囲の確定、証拠保全、修正test、rights再確認、rollback/forward fixの検証、Human Approverの再開判断です。時間不足だけを理由にseverityを下げません。

## 8. 完了定義

運用上の作業は、次をすべて満たすまで完了ではありません。

1. 所有roleとAが一意で、version付きartifactによるhandoffが完了している。
2. rightsが有効で、raw全文・secret・PIIが混入していない。
3. contract、TCO、gold/fault、lock、schema、secret scanが合格している。
4. release候補、expiry、rollback、kill switch、人手残量が確認できる。
5. 外部・公開操作はscopeと期限付きのsigned decisionを持つ。
