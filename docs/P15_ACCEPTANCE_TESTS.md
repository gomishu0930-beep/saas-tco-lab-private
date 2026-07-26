# P15 local acceptance tests

基準日: 2026-07-22

## 必須判定

- current blocked fixtureは11件全て`missing_evidence`で`STOP`。
- complete `synthetic_contract` fixtureは11件全て`synthetic_evidence`で`STOP`。
- production-shaped fixtureは`READY_FOR_HUMAN_GATE`までで、authorizationを内包しない。
- TCO/QA、Human、controllerの順にexact artifactへcross-bindし、最短input expiryより後のauthorizationを拒否。
- missing、exact duplicate、conflicting duplicate、duplicate evidence ID、failed、future、exact expiry、TTL超過、
  11 checkそれぞれのwrong key、wrong issuer/plan/policy/requirementは全てSTOP。
- plan v2のproperty/environment/P11/P13/release/closure/capability/deployment/provider target/expected pre-state/evidence map変更はold evidenceを無効化。
- strict model/schemaはURL、credential、free-form note、waiver、self-approved bool、unknown nested fieldを拒否。
- reconciliationは`UNKNOWN`を成功へ変えず、output decisionを常にSTOPとする。
- reconciliation ledgerはappend-only、duplicate neutral、正当署名付きconflict拒否、state MAC改変拒否、
  anchor one-ahead recoveryと複数revision rollback拒否を満たす。
- P13 resetはnonexistent/stale/wrong-head、別store/trust、`APPLIED`、`AMBIGUOUS` reconciliation recordを拒否し、
  currentな`NOT_APPLIED`だけを候補にする。
- P13 activationはP15 plan/auth spliceとexact expiryをprovider call前に拒否し、disable safety laneを維持。

## 実行command

```bash
uv run pytest -q tests/test_production_readiness.py
uv run pytest -q tests/test_production_consumer.py
uv run pytest -q

first=$(mktemp -d)
second=$(mktemp -d)
uv run python scripts/export_schemas.py --output-dir "$first"
uv run python scripts/export_schemas.py --output-dir "$second"
diff -rq "$first" "$second"

uv run python scripts/generate_p15_blocked_fixture.py
uv lock --check
python3 -m compileall -q src tests scripts
gitleaks dir . --redact --no-banner --no-color
```

現在のlocal記録は、P15専用105件、P13統合52件、全体514件、JSON Schema 105件である。schema repeat export、
checked-in schemaとの差分、blocked fixture二重生成、CLI outputとのbyte比較はいずれも一致した。

## 反証群

1. 11 checkそれぞれのexact thresholdと1 unit outside、normal/live/recovery TTLのexact境界。
2. evidence欠落・重複・競合・同一ID再利用。
3. synthetic provenance、wrong role/key/issuer、署名後mutation、cross-plan replay。
4. plan future、exact expiry、evidence future/exact expiry/TTL超過。
5. property、environment、P11/P13 policy/store、release、adapter/probe、capability、deployment splice。
6. controller authorizationのwrong pin、STOP report、Human/TCO拒否、earliest expiry超過。
7. reconciliation `UNKNOWN + applied`でも`STOP + request_human_disable`。
8. ledger row update/delete、同一P13 result conflict、expired recovery signature、anchor outage one-ahead、store/trust splice。
9. nonexistent/stale/unsafe-state reconciliationによるP13 reset。
10. P15 hash抜け、request splice、authorization exact expiry、terminal success再検証、disable継続。
11. readiness/reconciliation CLI socket/DNS/subprocess sentinel、duplicate JSON key、STOP exit 3。
12. schema repeat export、全suite、lock、compile、secret scan。

## release blocker

skip、xfail、waiver、合成証拠、11件という件数だけでは受入にしない。実providerへ接続する前に、このlocal
contractをHumanがversion付きで受け入れ、実環境の各roleが新しい証拠へ署名する必要がある。
