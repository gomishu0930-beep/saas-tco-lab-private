import type { EditorialContract } from "./editorial-input-contract";
import type { PilotPage } from "./pilot-pages";

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
      name: `${field.vendor_id} / ${field.plan_id} / ${field.field}`,
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
  const product: JsonLdObject = {
    "@type": "Product",
    name: `${page.title} — SaaS TCO比較`,
    description: page.question,
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
            text: `${page.readerOutcome}ように、Human確認値・unknown・出典・観測日を分けて確認します。`,
          },
        }],
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "SaaS TCO Lab" },
          { "@type": "ListItem", position: 2, name: "記事" },
          { "@type": "ListItem", position: 3, name: page.title },
        ],
      },
    ],
  };
}

export function serializeStructuredData(value: JsonLdObject): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}
