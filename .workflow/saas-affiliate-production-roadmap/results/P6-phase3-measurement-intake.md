# P6 Result: Phase 3 measurement intake

## Accepted

- `measurement.py`へDemand/Cohort/Operationsのstrict L2 batchとL3 builderを追加した。
- 入力はstable identifier、Decimal、timezone-aware time、authority/source/rule SHA-256だけを受け、URL、credential、PII、raw本文、自由記述fieldを持たない。
- 需要cluster、Affiliate partner、operation日次summaryのidentityをdistinctにし、row orderをcanonical化した。
- Operationsは30完了日を開始・capture時刻から導出し、全日coverage、routine/job/rollbackの分子≤分母を検証する。
- `BusinessDossier` v3へshadow days、job分子/分母、例外、rollback statusを接続した。
- Gate Dは30日未満をWAIT、成熟後job分母0/99%未満、例外25以上、rollback failedをSTOPとする。
- 3つのaggregate CLI、3入力schema、runbook、acceptance/counterexample仕様を追加した。

## Integration decisions

- L1 raw event処理とL2 typed intakeを分離した。repo codeはsafe summaryから始め、raw exportへ触れない。
- batch内の重複summary identityはexact duplicateでもREJECTする。complete batchの再実行は同一hashとなる。
- semantic keyword overlap、cross-snapshot transaction transition、run-key retry、exception identityは集計値から再構成しない。version付き上流receiptがない場合はverified inputとして扱わない。
- zero click、routine/job分母0は悪い実測としてEvidence化し、DossierでWAIT/STOPにする。都合の悪い値をvalidation errorで消さない。

## Verification

- `uv run pytest -q`: 172 passed。
- summary row permutationでsource/evidence hash不変。
- summary identity conflict、欠測日、分子超過、future/expiry、floatを拒否。
- synthetic L2→L3→Dossier: GO、current missing evidence: STOP。

## External gate unchanged

実需要、Affiliate report、30日shadow logはまだ取得・開始していない。外部申請、login、fetch、raw file保存、deploy、公開は実行していない。
