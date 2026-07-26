# P6 Phase 3 measurement intake

- Objective: rights/Affiliateの外部承認を待つ間に、重複除去済み需要、confirmed EPC cohort、30日shadow運用実績をraw summaryからversion付きEvidenceへ変換するlocal pipelineを完成する。
- Owners: Contract/Storage（typed aggregation）、TCO/QA（反証・acceptance）、Evidence/Policy（runbook）、Integration/Release（CLI/schema/integration）。
- Ownership:
  - Contract/Storage: `src/saas_preflight/measurement.py`、`tests/test_measurement.py`
  - TCO/QA: `docs/PHASE3_ACCEPTANCE_TESTS.md`
  - Evidence/Policy: `docs/PHASE3_EVIDENCE_RUNBOOK.md`
  - Integration/Release: CLI、schema export、workflow/result、全体統合
- Do: strict/frozen Pydantic、Decimal、hash-only event IDs、deduplication、mutually exclusive commission status、currency/cohort境界、automation分母、人手月境界、freshness、deterministic output。
- Do not: network、実Affiliate URL/secret/PII、仮需要/EPC、pending revenueの確定扱い、raw vendor report全文、既存canonical economicsの再実装。
- Expected output: raw summary batch → `DemandEvidence` / `CohortEvidence` / `OperationsEvidence` の決定論変換、CLI、schema、docs。
- Verification: duplicate/conflict/currency/status/future/expiry/zero denominator/月外eventを反証し、synthetic fixtureだけで再現する。
