# Baseline audit — 2026-08-20 Asia/Tokyo

## Git

- Branch: `codex/site-funnel-affiliate-ux`
- HEAD: `0b801b69988a4c1a4004e46ea9ac31c3d0817b91`
- Upstream divergence: 0 ahead / 0 behind at audit time
- Staged: 0
- Tracked modified: 46
- Untracked: existing workflow, candidate, output, contract, and dynamic route artifacts
- Existing worktree record: `/private/tmp/saastcolab-index-release.vCa7dS` is prunable because its gitdir is absent; left untouched
- Deployment source commit: unknown from public read-back

## Pre-change verification

`./scripts/check-all.sh` completed successfully:

- Python: 863 passed
- Schema export: PASS
- Schema diff: PASS
- Site local typed tests: 62 passed
- Site local UI: 22 passed
- Startup boundary: 1 passed
- Production boundary: 18 passed
- Secret scan: PASS
- Final: CHECK-ALL PASS

## Production read-back

- `/sitemap.xml`: 20 approved article URLs
- 20/20 article URLs: HTTP 200, `index, follow`, self-canonical
- P articles: Mangools CTA host allowlist and required rel attributes observed
- SVR01: 6 active sponsored CTA links observed
- SVR02–SVR09: 0 active sponsored CTA links observed
- P11: `noindex, follow`, no active CTA
- homepage and methodology: `noindex, follow`
- PR disclosure marker precedes sponsored CTA on sampled P01 and SVR01

## Shared console observations not re-fetched

The following are Human-shared observations dated 2026-08-19, not newly verified in this run:

- GSC sitemap success, 20 detected URLs
- GSC aggregate: 7 indexed, 6 not indexed, remaining URL states unknown
- GSC impressions 13, clicks 0
- GA4 7-day: page_view 7, qualified_session 2, outbound_click 0
- GA4 internal traffic filter: test
- confirmed commission: 0

## Baseline conflict to preserve

Production SVR01 still exposes six active CTA links. The dirty local tree already contains a non-deployed 1-primary/1-alternative experiment. No report may describe that local experiment as production until an authorized deploy and external read-back occur.
