# P4 Integration

- Objective: 完成ロードマップとPreflight dossier/CLI/previewを作り、P1–P3を統合する。
- Ownership: `docs/PRODUCTION_ROADMAP.md`、`src/saas_preflight/preflight.py`、CLI差分、preview、integration tests、workflow files。
- Do: Human-only gateを明示し、real dataなしでもfixtureでend-to-end dry runできるようにする。
- Do not: external application、credential、source fetch、push/deploy/publication。
- Expected output: machine-evaluable readiness report、noindex preview、fault matrix、next-action manifest。
- Verification: full suite、lock/schema/secret/workflow、blocked gatesがGOにならないこと。
