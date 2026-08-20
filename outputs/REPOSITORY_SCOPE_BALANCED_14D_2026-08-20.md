# Balanced 14-day sprint — repository scope candidate

Status: original scope received commit/push/deploy GO; required dependency
expansion is not yet authorized, so no external action has been performed.

## Pre-push dependency audit — 2026-08-20

The original file list cannot be built from a clean checkout. The following
existing launch-track files are the verified minimum closure for the current
20-article server surface and its tests. They were already present in the dirty
working tree but were missing from the first scope list.

### Required source and release state

- `artifacts/category-expansion-inputs/M3-servers-3vendor-candidate-2026-08-18.json`
- `docs/EDITORIAL_LAUNCH_STATE.json`
- `site/app/components/ServerObservationForm.tsx`
- `site/app/components/TcoCalculator.tsx`
- `site/app/lib/editorial-input-contract.ts`
- `site/app/lib/server-comparison-contract.ts`
- `site/app/lib/structured-data.ts`
- `site/app/lib/tco.ts`
- `site/app/operator/servers/page.tsx`
- `site/app/page.tsx`
- `site/app/servers/business-server-pricing/page.tsx`

### Required coupled tests

- `site/tests/editorial-input-contract.test.mjs`
- `site/tests/prepublication-assurance.test.mjs`
- `site/tests/tco-golden.test.mjs`

### Required fixed-scope maintenance

- `examples/jp_ja_keyword_slate_v3_brand_servers.csv`
- `src/saas_preflight/repository_acceptance.py`

With the runtime and coupled-test closure above, a clean-checkout site build and
all site tests pass. These additions require a separate exact scope expansion;
they have not been staged, committed, pushed, or deployed.

## Proposed release scope

### Runtime and UI

- `site/app/lib/pilot-pages.ts`
- `site/app/components/PilotArticle.tsx`
- `site/app/servers/[slug]/page.tsx`
- `site/app/globals.css`
- `site/worker/index.ts`

### Regression tests

- `site/tests/launch-quarter.test.mjs`
- `site/tests/local-ui.test.mjs`
- `site/tests/production-worker.test.mjs`

### Decision record and dashboard

- `docs/CURRENT_ADOPTION_ACTIONS.md`
- `scripts/update_status_dashboard.py`
- `tests/test_status_dashboard.py`
- `status-dashboard.html`

### Existing P18 pending-STOP fixture maintenance

- `artifacts/local-acceptance/p18-current-stop/verification-evidence.synthetic.json`
- `artifacts/local-acceptance/p18-current-stop/candidate-manifest.pending.json`
- `artifacts/local-acceptance/p18-current-stop/expected-stop-report.json`

The fixture remains `decision: stop`, `authority: none`, and grants no external,
production, publication, or scale authority. Its fixed path scope was not widened.

## Excluded from commit and external action

- `outputs/GROWTH_SPRINT_14D_2026-08-20.md` — local work plan
- `outputs/EXTERNAL_DRAFTS_SVR01_2026-08-20.md` — DRAFT_ONLY; do not post
- `outputs/GPT_PRO_CONSULTATION_2026-08-20.md` — local consultation packet
- GA4 internal traffic filter activation — HOLD
- home/category hub indexing — HOLD
- push, deploy, external posting — not authorized
- SVR02–SVR09 affiliate CTA activation — not authorized

## Verification receipt

- `scripts/check-all.sh`: PASS on 2026-08-20 Asia/Tokyo
- Python: 863 passed
- Site: 62 local TypeScript + 22 local UI + 1 startup-boundary + 18 production passed
- Schema export/diff: PASS
- Secret scan: PASS
- `git diff --check`: PASS

## Integration caution

The working tree contained prior uncommitted work before this sprint. A future commit
must review the complete hunks of every proposed path; path inclusion alone does not
prove that every pre-existing hunk belongs to this sprint.
