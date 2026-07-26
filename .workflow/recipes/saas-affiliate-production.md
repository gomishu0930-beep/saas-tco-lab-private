# SaaS affiliate production recipe

## Trigger

SaaS比較事業を新規に開始する、source/merchantを追加する、公開releaseまたは拡大判断を行う時。

## Plan shape

```text
official rights + affiliate approval
  -> sanitized L2 demand/cohort/operations summaries
  -> typed L3 evidence aggregation
  -> strict evidence/VendorPlan
  -> canonical Python TCO
  -> immutable candidate release
  -> schema/hash/expiry/fault tests
  -> Human promote approval
  -> serve-time visibility
  -> confirmed cohort economics
  -> scale / conditional / stop
```

## Packets

1. Evidence/Policy: rights 7 action、affiliate、商標、expiry、takedown。
2. Contract/Storage: strict model、append-only observation、schema、retention cohort。
3. TCO/Economics: TCO、demand、confirmed EPC、traffic、fault/counterexample。
4. Integration/Release: run、queue、budget、preview、release、rollback、decision dossier。
5. Measurement Intake: L2 safe summary、dedup/status/schedule receipt、3 Evidence、30日Gate D。
6. Human Approver: external send/account/billing/credential/publish/stop。

## Verification

- `uv run pytest -q`
- `uv run python scripts/export_schemas.py`を再実行し差分なし。
- `uv lock --check`、compileall、Gitleaks。
- current timeでdata/rights/affiliate expiryをinject。
- duplicate run、failed source、rollback、budget 576/720をinject。
- pending/rejected commissionをEPCへ入れない。
- 実データ不在時に`GO`が出ない。

## Known risks

- Public pageとAffiliate programはデータ再利用権を作らない。
- Static build、scheduler、monitorだけではstale displayを防げない。
- AI consensusはrights、料金真実性、計算正解を保証しない。
- 3社、保守需要、confirmed EPC、人手上限のhard gateを平均点で相殺しない。
