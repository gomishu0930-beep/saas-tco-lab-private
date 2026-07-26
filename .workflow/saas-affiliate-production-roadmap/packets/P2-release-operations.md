# P2 Release and Operations

- Objective: immutable release、read-time expiry、affiliate CTA、idempotent run、exception queue、人手budgetのlocal state machineを実装する。
- Ownership: `src/saas_preflight/release.py`、`src/saas_preflight/operations.py`、対応tests、`results/P2-release-operations.md`。
- Do: frozen dataclass/strict validation、UTC、SHA-256、fail-closed、duplicate safety、fault tests。
- Do not: 既存models/storage/tco/CLI編集、network、DB/cloud、publish。
- Expected output: pure local functions/state types and tests。
- Verification: expired data/rights/affiliate hides output、duplicate run rejected/idempotent、576/720分boundary。
