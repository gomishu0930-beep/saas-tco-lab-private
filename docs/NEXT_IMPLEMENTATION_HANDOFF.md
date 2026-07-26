# 次工程の実装handoff

基準日: 2026-07-23

## 現在地

一時運用条件: 2026-07-31まではカード不要モードとする。Google Workspace、domain購入、
OpenAI API、challenger AI、cloud、hosting、有料trialは実行しない。権利照会、無料Affiliate導線、
ローカル品質検証は継続するが、外部送信・規約同意・account作成のexact Human GOは省略しない。

P18 repository acceptance、P16 v3 typed Gate 1–8 semantic re-evaluation、P13 isolated subprocessまで実装した。public/business/scale stateは
`STOP`、protected routeはgeneric 503、実価格・実Affiliate URL・credentialは未投入である。現在の正確な次gateは
`local_verification`である。schema/fixture/test/secret/Web/workflowのdiagnostic runnerは実装済みだが、
result contract V2とsigned advisory/image/time/runner契約、store固定・durable freeze・署名receipt付きchallenge消費、P18→P16→P13連鎖は実装済みだが、read-only digest-pinned実行image、quote byte検証、artifact CAS read-backが
未成立なので`local_diagnostic_run`のままSTOPする。これらを満たすrunnerで別role署名を得た後、Human repository
acceptanceへ進む。

外部入力以外には、実quote/CAS、production clock/current-root/anchor service、別OS identity/KMSのprovider brokerが残る。P17 production ledgerのcredential-blind
運用brokerと、P18/P16/typed semanticsをP13 provider直前に再検証させる下流bindingは実装済みである。
実測automation、人手、運用TCO、純利益をtyped task/activity evidenceから再計算する境界は実装済みである。
したがって「コード不足ではない」とは扱わず、外部gateとlocal engineering backlogを分離して進める。

repoの形式的な承認範囲は現在P0–P10である。P11–P21をlocal統合候補として受け入れる場合は、
`docs/P18_REPOSITORY_ACCEPTANCE.md`の機械契約でmanifest、verification、別role署名、current rootを検証し、Humanが
version/revision付きdecisionを記録する。既存P11–P17 PENDING票は履歴として変更しない。

## 最後までの直列gate

|順序|Humanから必要な入力|受領後に自動実装・検証するもの|出口|
|---:|---|---|---|
|0|immutable runner環境、signed advisory snapshot、P18 exact manifestへのHuman decisionとpacket外authority-root固定|14 verified checks→別Integration/TCO署名→P16 v3 Gate 1でP18 bundle/root/tree/receipt再検証|local integration acceptance、次はrights|
|1|候補3–5社の優先順位、各社の権利回答または権限ある契約根拠|field別`SourcePolicy`、禁止field、保持期限、adapter方式、rights expiry|公開予定fieldのunreviewed 0、利用可能3社以上|
|2|各Affiliate審査結果、対象property/地域/広告条件/期限|`AffiliateDecisions`、CTA/disclosure/deep-link policy、expiry kill switch|利用可能3 program以上|
|3|重複除去済みJP/ja需要summaryとHuman承認した定義|署名付きP12 demand batch、coverage/identity root、保守traffic反証|必要qualified sessionsへの説明可能な経路|
|4|30日shadow開始承認と日次summary|cohort/operations batch、8 fault、job/例外/人手、signed dossier|重大誤表示0、job 99%以上、人手720分/月以下|
|5|承認sourceのsampleとHuman gold label|source別deterministic adapter、3社×6 plan gold set、TCO差分/quarantine|P8/P10 local public GO候補|
|6|domain/brand/legal表示、production製品、account、billing、credential配置、deploy/publishの各別承認|real provider adapterとP15 exact 11証拠、KMS/secret/anchor/outbox、backup/restore、noindex staging、rollback drill、P21 typed semantic packet|Human署名のproduction GO|
|7|公開後のprivacy-safe P12 packetとsettlement export|P17の30日chain、後日確定・返金、最大180日settled EPC、merchant依存|EPC 60円以上または縮小/撤退|
|8|scale投資判断|勝ちscenario拡張、例外だけHuman、月次release|運用TCO控除後の純利益月20万円かつ品質・権利・720分gate維持|

順序を飛ばさない。申請中は承認済みに数えず、synthetic passは実測passへ読み替えない。

## 最初に返してもらう5項目

本人操作の最小表、完了の合図、credentialを共有しない画面別手順は
`docs/HUMAN_ACTION_MANUAL.md`を正本とする。local UIの`/operator/`にも同じ停止境界を表示する。

1. 候補3–5社の優先順位。
2. 各社rights回答または契約根拠。回答本文そのものをrepoへ置けない場合は、権限者、scope、期限、
   decision-record hashだけを渡す。
3. Affiliate承認結果と公開可能な条件。secret、password、tracking ID本体はチャットやrepoへ貼らない。
4. `docs/PHASE3_EVIDENCE_RUNBOOK.md`のL1/L2契約にしたがう重複除去済み需要summary。
5. domain/account/billing/deploy/publishについて、どこまでを今回承認するか。まとめて承認せず別decisionにする。

## 受領直後の実行順

```text
validate Human scope
→ build policy-only rights/affiliate records
→ run approved adapters in no-publish prepare mode
→ quarantine and Human gold labels
→ start signed 30-day shadow
→ assemble P12 dossier
→ evaluate P10/P9/P11/P12/P13 authority with P14 crash recovery and P15 readiness
→ verify the exact P18 repository acceptance and consumer-owned root
→ assemble and evaluate the P16 v3 final-review handoff plus typed semantic packet and external semantic root
→ build noindex staging
→ fault/rollback/backup/security acceptance
→ request an exact publish approval
→ publish and monitor only after GO
→ ingest each complete P12 30-day packet into P17
→ verify signed settlement amendments after the fixed lag
→ request a Human scale decision only after P17 review readiness
```

実source fetch、問い合わせ送信、Affiliate申請、account作成、credential設定、課金、deploy、domain変更、公開は
それぞれ外部stateを変える。対応するHuman approvalを受けるまではCodexが実行しない。

## 再検証コマンド

```bash
uv lock --check
uv run pytest -q tests/test_production_consumer.py
uv run pytest -q tests/test_repository_acceptance.py tests/test_launch_handoff.py
uv run pytest -q
uv run saas-preflight run-local-verification \
  --repo-root . \
  --workflow-verifier \
  /Users/oumishuu/.codex/skills/codex-dynamic-workflows/scripts/verify_workflow.py
# current expected exit 3: local diagnostic only
uv run python scripts/export_schemas.py --output-dir schemas
uv run python scripts/generate_p18_pending_fixture.py
python3 -m compileall -q src tests scripts
```

正本ロードマップは`docs/PRODUCTION_ROADMAP.md`、入力の意味は`docs/READINESS_INPUTS.md`、実測手順は
`docs/PHASE3_EVIDENCE_RUNBOOK.md`、P13 authority境界は`docs/P13_PRODUCTION_CONSUMER.md`、P14 crash境界は
`docs/P14_CRASH_SAFE_EVIDENCE.md`、実環境証拠は`docs/P15_PRODUCTION_INTEGRATION_READINESS.md`、最終review
handoffは`docs/P16_LAUNCH_HANDOFF.md`、traction/scale制御は`docs/P17_TRACTION_SCALE_CONTROL.md`、repo受入は
`docs/P18_REPOSITORY_ACCEPTANCE.md`を参照する。
