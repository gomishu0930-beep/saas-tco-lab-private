# Final Report: SaaS TCO Lab Final V2 Revenue Cells 14-day Sprint

## Outcome

- Two Revenue Cells V2 was implemented and verified locally without changing the public release.
- Cell A is SVR01 with one Human-selected primary and one alternative slot.
- Cell B is provisionally SVR04, but its affiliate slot remains disabled until the article/vendor decision is explicitly approved.
- A typed merchant evidence matrix, bounded analytics contract, eligible-session aggregate, index audit, distribution drafts, option-lane table, and Human queue are available.

## Accepted Results

- Revenue events are limited to `calculator_result_view`, `cta_view`, `cta_eligible_session`, and `outbound_click` with enumerated, non-PII dimensions.
- CTA view/click collection is limited to active affiliate elements and an allowlisted destination host.
- Session eligibility excludes internal, test, bot, unknown, and non-production observations.
- P11 remains `noindex, follow` with CTA disabled. The 20 approved article boundary is unchanged.
- The existing P18 v8 exact-scope STOP fixture was regenerated after adding launch-track files; no new phase, signature layer, or acceptance document was added.

## Rejected Results

- No commission, EPC, RPES, GSC per-URL status, network sub-ID capability, or merchant confirmation period was inferred.
- Initial V2 implementation was committed and pushed as `46b606d` after explicit Human GO. Production deployment and external read-back remain separate states until Sites confirms them.
- Homepage and the SEO tools hub received source-level GO after the initial report. Their local implementation uses an additional runtime gate and excludes P11; deploy status must still be reported separately.
- No Option Lane candidate was ranked because required evidence remains unknown.

## Conflicts Resolved

- The shared state said SVR01 had six live production links. Production read-back confirmed this, while the dirty local tree already contained a one-primary/one-alternative design. Local and production state are therefore explicitly separated.
- The first final test run exposed one P18 path-scope mismatch caused by the new launch-track files. The current v8 scope hash and deterministic STOP fixture were updated; the second full run passed.

## Verification Evidence

- Baseline: `scripts/check-all.sh` PASS — Python 863, site 62/22/1/18, schema and secret scan PASS.
- Final: `scripts/check-all.sh` PASS — Python 870, site 63/22/1/19, schema and secret scan PASS.
- `git diff --check` PASS.
- Production baseline read-back: sitemap 20 URLs; approved pages 200/index/follow/self-canonical; P11 noindex/follow; SVR01 six sponsored links. The V2 changes were not deployed and therefore have no V2 production read-back.

## Remaining Risks

- The working tree remains broadly dirty, but the reviewed V2 scope was isolated into an explicit 75-file commit without staging unrelated untracked files.
- Cell B merchant selection, channel permission, success/rejection conditions, confirmation periods, and multiple renewal/cancellation fields remain Human-gated.
- GA4 internal traffic filter remains HOLD, so current GA4 values are not revenue evidence.
- Production remains on the pre-V2 experience until the saved Sites version is deployed and externally read back; a Git push alone is not treated as deployment evidence.

## Reusable Follow-up

- `outputs/HUMAN_ACTION_QUEUE_V2_2026-08-20.md`
- `outputs/INDEX_AUDIT_V2_2026-08-20.md`
- `outputs/SERVER_PRICE_AUDIT_DISTRIBUTION_V2_2026-08-20.md`
- `outputs/OPTION_LANE_V2_2026-08-20.md`
- `docs/REVENUE_CELL_V2_RUNBOOK.md`
