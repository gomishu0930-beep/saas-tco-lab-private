import { pilotPages, type PilotPage } from "./pilot-pages.ts";
import { approvedArticleIds, evaluatePublicationGate } from "./publication-gate.ts";

type NavigationControls = {
  indexGo: boolean;
  approvedArticleIdsValue: string | undefined;
  articleReviewsCurrent: boolean;
  reviewApprovedArticleIds: ReadonlySet<string>;
};

/** Return only Human-approved articles that are also eligible for indexing. */
export function nextToReadPages(
  current: PilotPage,
  controls: NavigationControls,
): readonly PilotPage[] {
  const approved = approvedArticleIds(controls.approvedArticleIdsValue);
  return pilotPages.filter((candidate) => {
    if (candidate.id === current.id) return false;
    return evaluatePublicationGate({
      articleId: candidate.id,
      indexGo: controls.indexGo,
      articleApproved: approved.has(candidate.id) && controls.reviewApprovedArticleIds.has(candidate.id),
      articleReviewCurrent: controls.articleReviewsCurrent,
      ctaGo: false,
      affiliatePartnerApproved: false,
      affiliateApprovalCurrent: false,
      destinationConfigured: false,
      disclosureBeforeCta: true,
    }).indexable;
  }).slice(0, 3);
}
