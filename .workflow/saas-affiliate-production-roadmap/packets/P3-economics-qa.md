# P3 Economics and QA

- Objective: 月20万円のqualified demand、outbound click、confirmed EPC、cohort maturation、GO/STOPを決定論的に計算する。
- Ownership: `src/saas_preflight/economics.py`、`tests/test_economics.py`、`docs/MEASUREMENT_MODEL.md`、`results/P3-economics-qa.md`。
- Do: Decimal、母数、pending/rejected除外、弱気/基準/強気、1,000 click/180日gate、property tests。
- Do not: SEO需要やEPCを捏造、外部検索、既存正本編集。
- Expected output: types/functions/tests/measurement definitions。
- Verification: 200,000/EPC、session=click/CTR、confirmed cohort only、zero/invalid input fail-closed。
