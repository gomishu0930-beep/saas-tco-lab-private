# Repository scope — Final V2 local implementation

## Baseline

- Branch: `codex/site-funnel-affiliate-ux`
- HEAD: `0b801b69988a4c1a4004e46ea9ac31c3d0817b91`
- 既存dirty tree: tracked 46 modified、staged 0、多数untracked
- Deployment commit: unknown
- Pre-change: `CHECK-ALL: PASS`（Python 863 / typed site 62 / UI 22 / startup 1 / production 18）

## V2 scope

- `src/saas_preflight/revenue_cells.py`: analytics aggregateとmerchant matrixのPydantic正本
- `scripts/export_schemas.py`: 3 schema export
- `scripts/summarize_revenue_cells.py`: safe aggregate CLI
- `artifacts/revenue-cells/*`: event contractと3 vendor matrix
- `examples/revenue_cell_daily_aggregate.json`: null-preserving intake例
- `site/app/lib/pilot-pages.ts`: Cell A/B assignment
- `site/app/components/PilotArticle.tsx`: article/cell marker、Cell B fail-closed slot
- `site/worker/index.ts`: safe dimensions、dedupe、affiliate outbound専用化、host allowlist
- `src/saas_preflight/repository_acceptance.py`と`artifacts/local-acceptance/p18-current-stop/*`: launch-track追加後も現行v8 exact-scopeと既定STOPを維持するfixture maintenance
- focused Python/site tests
- runbook、index audit、distribution draft、option lane、Human queue

## Excluded

- 既存46 tracked変更のうちV2と無関係な価格入力、dashboard
- P11変更
- homepage/hub index変更
- ASP account/program write
- GA4 admin write
- external post
- commit / push / deploy

## Rollback

V2は未commitのため、既存dirty changeと重なる3 site filesをファイル単位で戻してはいけない。rollback時は本書のV2 hunkだけをinverse patchし、schema 3件・新規module/script/tests/docs/artifactsを削除候補としてHuman reviewする。`git reset --hard`、`git clean`、checkoutによる全体破棄は禁止。
