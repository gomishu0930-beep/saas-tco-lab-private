import type { EditorialContract, ServerCandidateEvidence } from "./editorial-input-contract";
import {
  billingPeriodLabel,
  editorialPresentation,
  planDisplayName,
  vendorDisplayName,
} from "./editorial-presentation.ts";
import type { PilotPage, ServerArticleSlateEntry } from "./pilot-pages";

type JsonLdObject = Record<string, unknown>;

const OFFER_PRICE_FIELDS = new Set(["pricing.base_price", "plan.price", "alternative.price"]);

function approvedOffers(contract: EditorialContract | null): JsonLdObject[] {
  if (!contract || contract.article_review_status !== "approved") return [];
  return contract.numeric_fields
    .filter((field) => (
      field.value_kind === "price"
      && OFFER_PRICE_FIELDS.has(field.field)
      && field.scope_kind === "vendor_plan"
      && field.review_status === "approved"
      && field.value_status === "known"
      && field.currency_status === "known"
      && field.value !== null
      && field.currency !== null
      && field.vendor_id !== null
      && field.plan_id !== null
    ))
    .map((field) => ({
      "@type": "Offer",
      name: `${vendorDisplayName(field.vendor_id)} ${planDisplayName(field.vendor_id, field.plan_id)}（${billingPeriodLabel(field.billing_period)}）`,
      price: field.value,
      priceCurrency: field.currency,
      priceValidUntil: field.next_review_on,
    }));
}

export function articleStructuredData(
  page: PilotPage,
  contract: EditorialContract | null,
): JsonLdObject {
  const offers = approvedOffers(contract);
  const presentation = editorialPresentation(page, contract);
  const product: JsonLdObject = {
    "@type": "Product",
    name: presentation.title,
    description: presentation.description,
    category: "Business Software",
  };
  if (offers.length) product.offers = offers;

  return {
    "@context": "https://schema.org",
    "@graph": [
      product,
      {
        "@type": "FAQPage",
        mainEntity: [{
          "@type": "Question",
          name: page.question,
          acceptedAnswer: {
            "@type": "Answer",
            text: `${page.readerOutcome}ように、確認できた値、未確認項目、出典、確認日を分けて説明します。`,
          },
        }],
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "SaaS TCO Lab" },
          { "@type": "ListItem", position: 2, name: "記事" },
          { "@type": "ListItem", position: 3, name: presentation.title },
        ],
      },
    ],
  };
}

const SERVER_OFFER_SCOPE: Readonly<Partial<Record<ServerArticleSlateEntry["id"], "all" | "small_site" | "corporate_site" | "ecommerce">>> = {
  SVR02: "small_site",
  SVR04: "all",
  SVR07: "corporate_site",
};

/**
 * Server comparison schema keeps article approval and price semantics separate.
 * Only articles whose question is exactly answered by a confirmed first-year
 * checkout amount may emit Offers; all other pages keep Product/FAQ/Breadcrumb
 * without a modeled or partial price.
 */
export function serverArticleStructuredData(
  article: ServerArticleSlateEntry,
  articleReviewStatus: "approved" | "unreviewed",
  evidence: readonly ServerCandidateEvidence[],
): JsonLdObject {
  const scope = SERVER_OFFER_SCOPE[article.id];
  const offers = articleReviewStatus !== "approved" || !scope
    ? []
    : evidence.flatMap((item) => {
      const payment = item.initialPayment;
      const plan = item.calculatorContract.plans[0];
      const eligible = scope === "all" || plan?.eligibleUseCases.includes(scope);
      if (!payment || !eligible) return [];
      return [{
        "@type": "Offer",
        name: item.displayName.includes("12か月") ? item.displayName : `${item.displayName}（12か月）`,
        price: payment.amount,
        priceCurrency: payment.currency,
        priceValidUntil: payment.nextReviewOn,
      }];
    });
  const product: JsonLdObject = {
    "@type": "Product",
    name: article.titleTemplate,
    description: article.readerQuestion,
    category: "レンタルサーバー",
  };
  if (offers.length) product.offers = offers;
  return {
    "@context": "https://schema.org",
    "@graph": [
      product,
      {
        "@type": "FAQPage",
        mainEntity: [{
          "@type": "Question",
          name: article.readerQuestion,
          acceptedAnswer: {
            "@type": "Answer",
            text: "公式ページで確認できた料金と条件だけを使い、未確認項目は0円や推測値に置き換えず説明します。",
          },
        }],
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "SaaS TCO Lab" },
          { "@type": "ListItem", position: 2, name: "サーバー料金" },
          { "@type": "ListItem", position: 3, name: article.titleTemplate },
        ],
      },
    ],
  };
}

export function serializeStructuredData(value: JsonLdObject): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}
