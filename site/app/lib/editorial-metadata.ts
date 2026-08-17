import type { Metadata } from "next";

import { editorialContract } from "./editorial-contracts";
import { editorialPresentation } from "./editorial-presentation";
import type { PilotPage } from "./pilot-pages";
import { approvedArticleIds, evaluatePublicationGate } from "./publication-gate";

export function editorialMetadata(page: PilotPage): Metadata {
  const contract = editorialContract(page);
  const presentation = editorialPresentation(page, contract);
  const approved = approvedArticleIds(process.env.SAAS_INDEX_APPROVED_ARTICLES);
  const decision = evaluatePublicationGate({
    articleId: page.id,
    indexGo: process.env.SAAS_INDEX_GO === "GO",
    articleApproved: approved.has(page.id) && contract?.article_review_status === "approved",
    articleReviewCurrent: process.env.SAAS_ARTICLE_REVIEWS_CURRENT === "true",
    ctaGo: false,
    affiliatePartnerApproved: false,
    affiliateApprovalCurrent: false,
    destinationConfigured: false,
    disclosureBeforeCta: true,
  });
  const url = `https://saastcolab.jp/pilot/${page.slug}`;
  return {
    title: presentation.title,
    description: presentation.description,
    openGraph: {
      title: presentation.title,
      description: presentation.description,
      type: "article",
      url,
      siteName: "SaaS TCO Lab",
    },
    twitter: {
      card: "summary",
      title: presentation.title,
      description: presentation.description,
    },
    robots: {
      index: decision.indexable,
      follow: process.env.SAAS_RUNTIME_MODE === "production",
      noarchive: !decision.indexable,
      nosnippet: !decision.indexable,
    },
  };
}
