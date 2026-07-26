# P18 local acceptance tests

基準日: 2026-07-22

## 必須反証

- file内容/mode差分、root祖先/file/parent symlink、hardlink、secret名、未知top-level、`.`/`./x`/重複separator、NFC/case衝突を拒否する。artifact直接構築でも固定scopeを1 fileへ縮小できない。
- synthetic、fail、skip、期限切れ、署名欠落、wrong Integration/TCO key、command/context差替えを`local_verification`でSTOPする。Human receiptなしでもconsumer-owned verification-authority rootで署名を検証し、root欠落/不一致はPENDINGにしない。
- 全14 checkの`minimum_assertions`をcode-defined floorへ完全固定し、全roleの署名権限を仮定してもcoverageを1へ縮小するpolicyはvalidation・signing・evaluationの各境界で拒否する。
- authority-root欠落・不一致、policy/trust/receipt splice、exact expiryをSTOPする。
- attestationsは全check後・manifest前、Human receiptはmanifest後というchronologyを逆転できない。
- revision 1の旧GOはrevision 2のcurrent STOP head/pinの下で再生できず、revision 2以降は省略不能な全履歴を要求する。ランダムpredecessor、欠落、fork、履歴署名破損を拒否する。
- `CONDITIONAL`と`STOP`はlocal acceptanceを発行しない。
- P16 v3はtyped P18 bundle欠落、旧opaque component、別P18+別plan+再署名済み全receiptの一式差替えをconsumer-owned元rootで拒否する。Gate 2–8のtyped semantic packet、個別upstream pins、外部semantic rootも再検証する。
- P13は元file/parent symlink、path swap、caller `PYTHONPATH/sys.path/sitecustomize`を拒否または無視し、明示import path上でもclosure外moduleをloadしない。
- diagnostic runnerは14 checkのexact順序、明示test module partition、runtime/tree前後一致、sanitized env、
  output capを検証する。Webだけ`loopback_only`、他は`disabled`とし、runner出力は
  `local_diagnostic_run`のためP18 acceptanceへ使えない。旧`verified_local_run`も三者署名済みであっても永久STOPする。
- offline advisory snapshotが未署名・空・期限不明の間はdependency auditをfailにし、npmのexit 0をclean
  evidenceへ読み替えない。
- P18 fixtureは二生成でbyte-identical、`decision=stop`、`next_gate=local_verification`、`authority=none`である。

## 再現コマンド

```bash
uv run pytest -q tests/test_repository_acceptance.py
uv run pytest -q tests/test_launch_handoff.py
uv run pytest -q tests/test_production_consumer.py

uv run saas-preflight run-local-verification \
  --repo-root . \
  --workflow-verifier \
  /Users/oumishuu/.codex/skills/codex-dynamic-workflows/scripts/verify_workflow.py
# current expected exit: 3 (diagnostic only; advisory/runtime v2 missing)

schema_first="$(mktemp -d)"
schema_second="$(mktemp -d)"
uv run python scripts/export_schemas.py --output-dir "$schema_first"
uv run python scripts/export_schemas.py --output-dir "$schema_second"
diff -ru "$schema_first" "$schema_second"
diff -ru schemas "$schema_first"

fixture_first="$(mktemp -d)"
fixture_second="$(mktemp -d)"
uv run python scripts/generate_p18_pending_fixture.py --output-dir "$fixture_first"
uv run python scripts/generate_p18_pending_fixture.py --output-dir "$fixture_second"
diff -ru "$fixture_first" "$fixture_second"
diff -ru artifacts/local-acceptance/p18-current-stop "$fixture_first"

uv lock --check
uv run python -m compileall -q src scripts tests
python3 /Users/oumishuu/.codex/skills/codex-dynamic-workflows/scripts/verify_workflow.py \
  .workflow/saas-affiliate-production-roadmap
```

最終受理には上記だけでなく、固定source/test/schema/fixture/docs hashに対するContract/StorageとTCO/QAの独立PASS、Integration/TCOの実verification署名、consumer-owned authority-root、Human GOが必要である。テスト成功だけをHuman acceptanceや外部権限に読み替えない。
