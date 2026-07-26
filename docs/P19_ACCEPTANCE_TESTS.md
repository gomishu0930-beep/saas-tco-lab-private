# P19 acceptance tests

## Implemented checks

- V2の正例は14 spec/result、image、advisory、clock、runnerの全署名とpacket外rootが一致した時だけ検証できる。
- self-consistentなpolicy/trust/pins一式差替えも、元のpacket外rootで拒否する。
- timeout、signal、nonzero exit、failure、skip、parser差替え、truncation、出力量超過、wall/monotonic不一致を拒否する。
- dependency auditが署名advisory databaseの完全byte readを結ばない場合を拒否する。
- 空advisory、双方向に矛盾するempty-output hash、空parser output、期限切れ、sequence/head rollbackを拒否する。
- 旧`verified_local_run`は三者署名とHuman GOがあってもSTOPする。
- P18/P19 role key再利用、P19 rootを直接結ばないP18 attestationを拒否する。
- task schedule/execution欠落、mode差替え、manual activity欠落、actor時間重複、未定義labor rate、期限切れを拒否する。
- P17 signed aggregate改変をactivity行との不一致で拒否し、売上20万円・人件費6万円を純利益14万円としてSTOPする。
- V2 verify CLIとoperations derive CLIはwrite-once outputだけを作り、authorityを発行しない。
- replay storeは同一challenge/bundleの再消費、別store消費、row/meta/anchor改ざんを拒否し、SQLiteがanchorよりexact one-tailだけ
  先行した場合に限って復旧する。clock callbackはpolicy timeoutとbackdate上限を持ち、失敗時のfreezeはreopen後も永続する。
  anchor callback停止と別processのstore lock保持も固定deadlineで拒否し、無期限にauthorityを待たない。
- consumption receiptはStorage Auditor署名、store/sequence/head/evidence/authorityを全て満たさなければP18へ昇格できない。
- `TractionRuntimeBroker`の全運用methodはstate key、private key、clock、anchor引数を持たない。
- P13はpacket外P18/P16 root差替え、不完全P16 bundle、backdated clock、current-root変更、claim後のP16 exact expiryをprovider call 0で拒否し、dispatch tokenをP16/P18実効expiryへclipする。

## Focused verification

```bash
uv run pytest -q tests/test_verified_runner.py
uv run pytest -q tests/test_operations_activity.py
uv run pytest -q tests/test_traction_control.py
uv run pytest -q tests/test_repository_acceptance.py
uv run pytest -q tests/test_launch_handoff.py
uv run pytest -q tests/test_production_consumer.py
```

## Supply-chain verification

```bash
first="$(mktemp -d)"
second="$(mktemp -d)"
uv run python scripts/export_schemas.py --output-dir "$first"
uv run python scripts/export_schemas.py --output-dir "$second"
diff -ru "$first" "$second"
diff -ru schemas "$first"
uv lock --check
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

P19 complete判定には上記成功だけでなく、`P19_VERIFIED_RUNNER.md`のRemaining P0 gatesと独立Contract/Storage・
TCO/QA再監査が必要である。現在のlocal evidenceを実OCI/VM、production clock、external anchor、Affiliate実績へ読み替えない。
