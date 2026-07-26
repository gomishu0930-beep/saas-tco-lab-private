# P17 local acceptance tests

基準日: 2026-07-22

## 必須判定

- P12完全packetをingest時に再実行し、report転記や自己申告集計を受け付けない。
- release/artifact/schema、property、partner、P12/settlement policy・trustのfull substitutionを拒否する。
- 30日窓、ordinal、predecessor、identity tokenのgap、overlap、fork、重複、conflictを拒否する。
- 999/1000 clicks、180日、EPC 59.99/60、CTR 9.99%/10%、純利益199999.99/200000、share 40%/超過、
  automation 80%、人手720、job 99%、例外24をinclusive boundaryで検査する。
- pending/rejectedはsettled numeratorへ入れず、全valid clickはEPC denominatorへ残す。
- 後日確定と全額reversalの正負delta、0イベントCOMPLETE、exact replay、conflict、foreign cohortを検査する。
- 全partnerをゼロ額込みで保持し、amendment後のpartner合計とtotalを一致させる。
- 未成熟provisionalはCONTINUE可能だが、成熟settlement不完全、empty、syntheticはscale review不可。
- reportは外部authorityを含まず、blocked CLIはexit 3でexpected STOP reportと一致する。
- task schedule/execution/human/resource行から集計を再構築し、署名済みaggregateだけの改変を拒否する。売上20万円でも人件費6万円なら純利益14万円としてSTOPする。
- ledgerは0600、STRICT、immutable trigger、HMAC、hash chain、external anchor、crash回復を検証する。
- 別processがfile lockを保持した場合とhung anchor read/commitを固定deadlineで拒否する。timeout後も専用anchor lockを
  callback完了まで保持し、その間のretryはcallbackへ入らずSTOPする。遅延した旧revision commitと新revision commitを
  並行させず、完了後の明示的回復だけを許可する。
- caller-supplied時刻と認証booleanを持たず、別TIME_AUDITOR署名がrevision/head/purpose/subjectを完全にbindする。
- 一度遅い時刻をanchorした後のbackdated append、clock request replay/state splice、clock鍵置換を拒否する。
- finalization時刻もglobal monotonic順序へ含め、次targetがその時刻より前ならcommit前に拒否する。
- target commit後の一時clock失敗、再open、DBだけ1 revision進んだanchor outageを再開し、唯一のpending tail以外は拒否する。
- exact-expiryの遅延応答はactive evidenceにせず、署名付きexpired tombstoneとして保存・anchorし、再open可能にする。
- hung clock callbackはpolicy固定timeoutで失敗し、SQLite/file lockを無期限保持しない。host-global root-inode flockにより
  反復・再open・別process・hard-link別名でも生存workerを1本より増やさず、provider回復後だけ再開する。
- clock workerまたは通常ledger file lock保持中のfork後に親processがcrashしても、同期済み子FD cleanupにより
  acquire/register・close/discard raceを含めlockを孤児化しない。
- host lock取得後のQueue/Thread生成・start等のsetup失敗でもFD/registryを必ず解放し、healthy retry可能にする。
- file/clock FDのowner allocation・registry登録がMemoryErrorでも未追跡FDを残さず、`Thread.start()`開始後例外や
  ownership通知例外でもone-shot leaseにより二重close・第二callback・host lock残留を起こさない。
- settlement snapshotと評価reportを同じglobal event chainへ保存し、READY根拠hashとreportがreopen後も一致する。
- bare sequenceや一時settlement引数からはREADYを生成できず、台帳経路だけがledger checkを昇格できる。
- short-TTL settlement envelope失効後も、同一event setをfresh署名へ包み直して更新でき、event欠落・変更は拒否する。
- raw最新settlementのfinalizationがexpiredなら旧accepted売上へfallbackせず、fresh accepted到着までscale review不可にする。
- 30桁Decimalのcanonical hash衝突を拒否し、EPC・CTR・share・automation・job・capacityはcross multiplicationで判定する。

## command

```bash
uv run pytest -q tests/test_traction_control.py tests/test_settlement_amendment.py tests/test_measurement_integrity.py
# process-group kill/fork fault tests are isolated from the long-lived runner
uv run pytest -q --ignore=tests/test_production_consumer.py --ignore=tests/test_traction_control.py
uv run pytest -q tests/test_traction_control.py
uv run pytest -q tests/test_production_consumer.py

first=$(mktemp -d)
second=$(mktemp -d)
uv run python scripts/export_schemas.py --output-dir "$first"
uv run python scripts/export_schemas.py --output-dir "$second"
diff -rq "$first" "$second"

fixture_first=$(mktemp -d)
fixture_second=$(mktemp -d)
uv run python scripts/generate_p17_blocked_fixture.py --output-dir "$fixture_first"
uv run python scripts/generate_p17_blocked_fixture.py --output-dir "$fixture_second"
diff -rq "$fixture_first" "$fixture_second"
diff -rq "$fixture_first" examples/p17/blocked

uv lock --check
python3 -m compileall -q src tests scripts
gitleaks dir . --redact --no-banner --no-color
```

Web実装はP17で変更しないが、既存境界の回帰として`npm test`、ESLint、build、`npm audit`も最終監査で実行する。

## release blocker

local passは実traffic、実売上、権利、Affiliate承認、source/producer真正性、公開承認を作らない。P11–P17の形式的
Human受理と外部gate完了までは事業/public/scaling状態を`STOP`とする。
