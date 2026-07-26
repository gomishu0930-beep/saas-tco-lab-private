# 現時点の導入 — あなたの操作表

基準日: 2026-07-26（Asia/Tokyo）

この表は新しい導入計画でHuman本人が行う箇所だけをまとめる。既存H1–H10のrights・Affiliate・
Google Ads・公開手順は`docs/HUMAN_ACTION_MANUAL.md`を優先する。

2026-07-31まではカード不要モードとし、Google Workspace、domain購入、OpenAI API、外部AI課金、
cloud、hosting、有料trialを保留する。カード不要でも外部送信・規約同意・account作成は対象別GOを必要とする。

|ID|時期|本人が行うこと|完了の合図|Codexが続けること|共有禁止|
|---|---|---|---|---|---|
|A-H01|完了|private GitHub repositoryを作成|2026-07-26完了|`saas-tco-lab-private`がprivateかつ空であることをread-back済み。初回commit・pushは別GO待ち|PAT/SSH秘密鍵|
|A-H02|完了|Google Drive pluginをinstall/connectし専用folderを選択|2026-07-26完了|`SaaS TCO Lab`と7分類を作成済み。safe-summaryだけを投入する|契約全文、PIIをchat・Driveへ貼らない|
|A-H03|完了|Google Calendar pluginをconnectし専用calendarを選択|2026-07-26完了|非公開`SaaS TCO Lab`を作成済み。下記event案の承認待ち|個人予定、calendar ID|
|A-H04|Wave 1|Search Console propertyを登録・所有確認|`gsc_property: done`|read-only query/page export contractを検証|verification token|
|A-H05|Wave 1|GA4 property/data streamを作成または対象を選択|`ga4_property: done`|event taxonomyとdebug/consent確認|measurement secret|
|A-H06|月末後|OpenAI API project、budget cap、API keyを本人管理で作成|`openai_project: done`|env参照方法、gold-set benchmark、routerを実装|API key、billing情報|
|A-H07|Affiliate承認後|各partnerからexportを本人取得可能にする|`affiliate_export_ready: <partner>`|safe summary、status mapping、settlement reconcile|tracking ID、税務/受取情報|
|A-H08|条件付き|Notionを使うか決める|`notion: use / skip`|useならeditorial viewだけ作りGitHubを技術正本に固定|個人workspace全体|
|A-H09|100 evaluated runs後|ClaudeまたはGeminiの比較課金を承認|`challenger_budget: GO <provider>`|10–20%標本benchmarkを実行|API key、非公開契約|
|A-H10|public GO後|cloud/DB/hosting/providerと予算を選択|対象ごとのexact GO|staging、backup/restore、readback、rollbackを実装|cloud root credential|
|A-H11|自データ取得開始前|JP/ja需要export、field evidence、初回15件以上のHuman gold labelを確認|`jp_ja_export: done`、`field_evidence: done`、`initial_gold_labels: done`|署名付き初期学習品質bundleを作り、低品質batchを開始前にSTOP|raw本文、PII、credential、tracking ID|

## Plugin画面での既定選択

- Google Drive: `Allow read actions / ask before writes`相当。対象folderを限定する。
- Google Calendar: 書き込み前確認を維持する。
- Notion: 未導入を既定とし、GitHub Issuesで運用しにくいと判明した時だけ使う。
- Gmail: 読取・下書きは許容、送信は毎回Human確認を維持する。

## 返信テンプレート

```text
gsc_property: pending / done
ga4_property: pending / done
openai_project: pending / done
initial_gold_labels: pending / done
notion: use / skip
```

既存H1–H10と同様、credentialや識別子の値そのものは返信しない。

## Drive / Calendarの現在地

Driveの`SaaS TCO Lab`直下には、`00-Control`、`10-Rights`、`20-Affiliate`、
`30-Demand`、`40-Editorial`、`50-Exports-Safe`、`90-Archive`を作成済みです。
raw契約全文、個人情報、credential、tracking IDは置かず、承認済みsafe-summaryだけを受け入れます。

専用Calendarは一般公開・共有・追加通知なしで作成済みです。予定の作成前に、次を一括承認します。

|予定案|日付・周期|目的|
|---|---|---|
|5社rights回答30日確認|2026-08-22|未回答先への再照会判断|
|5社rights回答90日確認|2026-10-21|候補維持・代替vendor判断|
|5社rights回答180日確認|2027-01-19|長期未回答sourceのkill判断|
|Mangools tier確認|毎月4日|直近3か月平均とcommission tier確認|
|Mangools conversion確認|毎月15日|承認済みconversionとexport可否確認|

作成する場合のexact GOは`calendar_events: GO`です。予定は専用Calendarだけに作り、
個人Calendar、参加者、Google Meet、場所、個人情報を追加しません。
