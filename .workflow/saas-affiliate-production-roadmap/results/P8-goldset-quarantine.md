# P8 Result: Offline gold set and quarantine

## Accepted

- `HumanGoldSet` / `GoldPlan` / field label / TCO expectationをstrict frozen contractにした。
- labelはvalue/source/Human receiptをSHA-256で保持し、TCOはcurrency、total minor units、full result hashを持つ。
- `CandidateBatch`へsource receipt、parser artifact/version、成功plan、全parse failureを同居させた。
- partial setは入力として受理するが、3 vendor以上 × 各6 plans以上、vendorごと60–150 labelsまでrelease不可。
- current derive/publish/retain-history、retention、Evidence取得時刻、source、field、field/TCO label期限、full TCO、missing/extra/future/expiryを独立quarantineする。
- snapshot observationを除外しつつvendor/plan/fieldと全SourcePolicyを結合するrights manifestで、source/policy差替えを検知する。
- parser failure率は`> 0.20`でSTOP。exact 0.20はrate STOPではないが、failure quarantineのためreadyにならない。
- outputはURL、excerpt、raw errorを含まないhash-only reportで、plan/label/batch row順序に対してhash不変。
- `evaluate-gold-set` read-only CLIと`human-gold-set` / `candidate-batch` schemaを追加した。

## Rejected

- parser成功rowだけで成功率を算定すること。
- partial gold setを完成扱いすること。
- field値やraw source本文をquarantine reportへ出すこと。
- unknown addon、曖昧scenario、期限切れrightsを推測してTCO計算すること。
- machine reportをHuman publish approvalとして扱うこと。

## Verification

- P8 module/CLI tests: 25 passed。
- Full Python suite: 204 passed。
- 14 JSON Schema生成。
- 14 schemaの再生成差分なし、`uv lock --check`、compileall、Gitleaks leak 0。
- Web build、4 route tests、ESLint、`npm audit` vulnerability 0、workflow verifier合格。
- 独立TCO/QA再反証でrelease blockerなし。future evidence、retention/TCO labelの期限一致、rights source/policy差替え、source hash順序、3 vendors・19 plansのovercoverageを確認した。

## External boundary

実vendor、実価格、実source URL、実Affiliate URLは追加していない。Human receiptとrights bundle SHA-256の署名真正性は外部artifact側で確認する。source-specific parserと実gold labelはGate A/B合格後だけ追加する。
