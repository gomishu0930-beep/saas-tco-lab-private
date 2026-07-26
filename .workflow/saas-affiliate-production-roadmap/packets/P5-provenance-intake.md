# P5 Provenance and Intake

- Objective: `rights_approved`やAffiliate件数を手入力せず、VendorPlan field policy、hash-only Affiliate decision、需要/cohort/operations evidenceからBusinessDossierを決定論的に組み立てる。
- Owner: Integration/Release。
- Ownership: `src/saas_preflight/readiness_builder.py`、対応tests/schema/examples/CLI、P5 result。
- Do: current policy permission、distinct partner、artifact SHA-256、expiry、currency、automation denominatorをderiveする。
- Do not: live Affiliate URL/secret、実績値捏造、外部fetch、申請、既存canonical TCOの再実装。
- Expected output: production-path assemblerとfail-closed input contracts。
- Verification: forged boolean/duplicate partner/expired artifact/zero denominator/missing planを拒否し、synthetic fixtureだけで再現する。
