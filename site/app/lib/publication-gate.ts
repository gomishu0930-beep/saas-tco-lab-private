export type PublicationGateInput = {
  articleId: string;
  indexGo: boolean;
  articleApproved: boolean;
  articleReviewCurrent: boolean;
  ctaGo: boolean;
  affiliatePartnerApproved: boolean;
  affiliateApprovalCurrent: boolean;
  destinationConfigured: boolean;
  disclosureBeforeCta: boolean;
};

export type PublicationGateDecision = {
  indexable: boolean;
  ctaEnabled: boolean;
  robots: "index, follow" | "noindex, nofollow, noarchive, nosnippet";
  stopReasons: readonly string[];
};

const ARTICLE_ID_PATTERN = /^P(?:0[1-9]|1[0-2])$/;

export function evaluatePublicationGate(input: PublicationGateInput): PublicationGateDecision {
  if (!ARTICLE_ID_PATTERN.test(input.articleId)) {
    throw new Error("publication gate requires a P01-P12 article ID");
  }
  const stopReasons: string[] = [];
  const indexable = input.indexGo && input.articleApproved && input.articleReviewCurrent;
  if (!input.indexGo) stopReasons.push("index_go_hold");
  if (!input.articleApproved) stopReasons.push("article_unapproved");
  if (!input.articleReviewCurrent) stopReasons.push("article_review_expired");

  const ctaEnabled =
    indexable &&
    input.ctaGo &&
    input.affiliatePartnerApproved &&
    input.affiliateApprovalCurrent &&
    input.destinationConfigured &&
    input.disclosureBeforeCta;
  if (!input.ctaGo) stopReasons.push("cta_go_hold");
  if (!input.affiliatePartnerApproved) stopReasons.push("partner_unapproved");
  if (!input.affiliateApprovalCurrent) stopReasons.push("partner_approval_expired");
  if (!input.destinationConfigured) stopReasons.push("destination_missing");
  if (!input.disclosureBeforeCta) stopReasons.push("disclosure_after_cta");

  return {
    indexable,
    ctaEnabled,
    robots: indexable ? "index, follow" : "noindex, nofollow, noarchive, nosnippet",
    stopReasons,
  };
}

export function approvedArticleIds(value: string | undefined): ReadonlySet<string> {
  if (!value?.trim()) return new Set();
  const ids = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (ids.some((id) => !ARTICLE_ID_PATTERN.test(id)) || new Set(ids).size !== ids.length) {
    throw new Error("approved article IDs must be unique P01-P12 IDs");
  }
  return new Set(ids);
}
