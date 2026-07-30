import type { Metadata } from "next";

import type { PilotPage } from "./pilot-pages";
import { approvedArticleIds, evaluatePublicationGate } from "./publication-gate";

export function editorialMetadata(page: PilotPage): Metadata {
  const approved = approvedArticleIds(process.env.SAAS_INDEX_APPROVED_ARTICLES);
  const decision = evaluatePublicationGate({
    articleId: page.id,
    indexGo: process.env.SAAS_INDEX_GO === "GO",
    articleApproved: approved.has(page.id),
    articleReviewCurrent: process.env.SAAS_ARTICLE_REVIEWS_CURRENT === "true",
    ctaGo: false,
    affiliatePartnerApproved: false,
    affiliateApprovalCurrent: false,
    destinationConfigured: false,
    disclosureBeforeCta: true,
  });
  return {
    title: `記事template・${page.title}`,
    description: `${page.question}をHuman確認値と出典日付で検証する記事template。`,
    robots: {
      index: decision.indexable,
      follow: decision.indexable,
      noarchive: !decision.indexable,
      nosnippet: !decision.indexable,
    },
  };
}
