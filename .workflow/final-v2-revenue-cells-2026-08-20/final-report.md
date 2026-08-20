# Final Report: SaaS TCO Lab Final V2 Revenue Cells 14-day Sprint

## Outcome

- Two Revenue Cells V2 was implemented, pushed, deployed as Sites v38, and externally read back at commit `af95bdb`.
- Cell A is SVR01 with one Human-selected primary and one alternative slot.
- Cell B is provisionally SVR04, but its affiliate slot remains disabled until the article/vendor decision is explicitly approved.
- A typed merchant evidence matrix, bounded analytics contract, eligible-session aggregate, index audit, distribution drafts, option-lane table, and Human queue are available. External posts remain drafts.

## Accepted Results

- Revenue events are limited to `calculator_result_view`, `cta_view`, `cta_eligible_session`, and `outbound_click` with enumerated, non-PII dimensions.
- CTA view/click collection is limited to active affiliate elements and an allowlisted destination host.
- Session eligibility excludes internal, test, bot, unknown, and non-production observations.
- P11 remains `noindex, follow` with CTA disabled. The 20 approved article boundary is unchanged.
- SVR01 now exposes exactly one primary and one alternative CTA after hydration. Mangools pages expose one CTA. Both paths are disclosure-first, use the required `rel`, fit a 390px viewport, and produce no page error in the production bootstrap read-back.
- Homepage and `/pilot` are Human-approved indexable hubs. The production sitemap now contains the 20 approved articles plus those two hubs, exactly 22 URLs.
- The existing P18 v8 exact-scope STOP fixture was regenerated after adding launch-track files; no new phase, signature layer, or acceptance document was added.

## Rejected Results

- No commission, EPC, RPES, GSC per-URL status, network sub-ID capability, or merchant confirmation period was inferred.
- Cell B's merchant remains unselected. The all-GO instruction authorizes execution but is not evidence for vendor suitability, program terms, or Human-observed commercial fields, so its affiliate slot stays disabled.
- GA4 internal filter was not activated: the filter remains test and there are zero internal-traffic definition rules. Sending the current public IP to Google requires an action-time confirmation.
- No Option Lane candidate was ranked because required evidence remains unknown.

## Conflicts Resolved

- The shared state said SVR01 had six live links. V2 replaced them with one primary and one alternative after runtime validation, without changing the editorial ranking.
- First production read-back found a self-triggering MutationObserver in both CTA hydration paths and a 988px mobile overflow in server evidence. Both defects were fixed, regression-tested, redeployed, and re-read back successfully.
- The first final test run exposed one P18 path-scope mismatch caused by the new launch-track files. The current v8 scope hash and deterministic STOP fixture were updated; the second full run passed.

## Verification Evidence

- Baseline: `scripts/check-all.sh` PASS — Python 863, site 62/22/1/18, schema and secret scan PASS.
- Final `scripts/check-all.sh`: Python 870、site 63/22/1/20、schema export/diff、secret scanの全項目PASS。
- `git diff --check` PASS.
- Production v38 read-back: sitemap 22 URLs; all included URLs 200/index/follow/self-canonical; P11 noindex/follow; SVR01 active CTA count 2; Mangools active CTA count 1; disclosure precedes every CTA; required rel attributes present; 390px document width equals viewport width.

## Remaining Risks

- The working tree remains broadly dirty, but the reviewed V2 scope was isolated into an explicit 75-file commit without staging unrelated untracked files.
- Cell B merchant selection, channel permission, success/rejection conditions, confirmation periods, and multiple renewal/cancellation fields remain Human-gated.
- GA4 internal traffic filter remains HOLD, so current GA4 values are not revenue evidence.
- GSC is stale relative to the current release: last page report update was 2026-08-17 with 6 indexed and 9 unregistered. Known per-page states were recorded without inferring the rest.
- Search performance remains 28 impressions and 0 clicks at the last read-back. GA4 values remain non-revenue evidence until internal/test traffic is separated.

## Reusable Follow-up

- `outputs/HUMAN_ACTION_QUEUE_V2_2026-08-20.md`
- `outputs/INDEX_AUDIT_V2_2026-08-20.md`
- `outputs/SERVER_PRICE_AUDIT_DISTRIBUTION_V2_2026-08-20.md`
- `outputs/OPTION_LANE_V2_2026-08-20.md`
- `docs/REVENUE_CELL_V2_RUNBOOK.md`
