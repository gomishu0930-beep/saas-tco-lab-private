export type PilotPage = {
  slug: string;
  title: string;
  intent: string;
  pageType: string;
  question: string;
};

export const pilotPages: readonly PilotPage[] = [
  { slug: "pricing-calculator", title: "料金計算", intent: "price_check", pageType: "pricing", question: "seat数と利用量をそろえると12か月総額はいくらか" },
  { slug: "plan-comparison", title: "プラン比較", intent: "compare", pageType: "comparison", question: "同じ利用条件で複数プランをどう比較するか" },
  { slug: "alternatives", title: "代替候補", intent: "replace", pageType: "alternatives", question: "置き換え候補をTCOと適合条件でどう絞るか" },
  { slug: "small-team-fit", title: "小規模チーム適合", intent: "fit_check", pageType: "use_case_fit", question: "少人数運用で固定費と人手を抑えられるか" },
  { slug: "enterprise-fit", title: "組織利用適合", intent: "fit_check", pageType: "use_case_fit", question: "権限・監査・運用費を含めて組織要件に合うか" },
  { slug: "annual-vs-monthly", title: "年契約と月契約", intent: "compare", pageType: "comparison", question: "commitmentと解約リスクを含む総額差はいくらか" },
  { slug: "usage-overage", title: "従量超過", intent: "price_check", pageType: "pricing", question: "利用量が基準を超えた時の増分費用はいくらか" },
  { slug: "addon-cost", title: "追加機能費用", intent: "price_check", pageType: "pricing", question: "必須addonを含めた実効総額はいくらか" },
  { slug: "migration-cost", title: "移行コスト", intent: "migrate", pageType: "migration", question: "移行作業・重複契約・教育を含む初年度費用はいくらか" },
  { slug: "japan-tax", title: "日本向け税・通貨", intent: "verify_method", pageType: "methodology", question: "JPY換算と日本向け税表示をどう検証するか" },
  { slug: "break-even", title: "損益分岐", intent: "fit_check", pageType: "use_case_fit", question: "削減時間と運用費から導入の損益分岐をどう求めるか" },
  { slug: "evidence-method", title: "根拠の検証", intent: "verify_method", pageType: "methodology", question: "field単位の根拠・権利・期限をどう監査するか" },
] as const;

export function pilotPage(slug: string): PilotPage {
  const page = pilotPages.find((candidate) => candidate.slug === slug);
  if (!page) throw new Error(`Unknown synthetic pilot slug: ${slug}`);
  return page;
}
