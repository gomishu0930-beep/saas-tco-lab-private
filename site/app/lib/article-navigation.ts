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
  const eligible = pilotPages.filter((candidate) => {
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
  });
  const currentIndex = eligible.findIndex((candidate) => candidate.id === current.id);
  if (currentIndex < 0) return eligible.slice(0, 3);
  return Array.from(
    { length: Math.min(3, Math.max(0, eligible.length - 1)) },
    (_, offset) => eligible[(currentIndex + offset + 1) % eligible.length],
  );
}
