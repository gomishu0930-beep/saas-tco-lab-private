import type { Metadata } from "next";
import Link from "next/link";

import { editorialContract } from "../lib/editorial-contracts";
import { firstReleasePilotIds, launchPriorityPages } from "../lib/pilot-pages";

export const metadata: Metadata = {
  title: "SEOツール料金・契約条件の比較",
  description: "人が公式画面で確認した料金、契約条件、利用上限をもとに、SEOツールの12か月費用と未確認条件を整理します。",
};

export default function PilotIndexPage() {
  const orderedPages = launchPriorityPages().filter(
    (page) => editorialContract(page)?.article_review_status === "approved",
  );
  const firstRelease = new Set(firstReleasePilotIds);
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">SEO TOOL PRICING / VERIFIED EDITORIAL</p>
        <h1>SEOツールの料金を、請求総額と契約条件から確認する。</h1>
        <p>公式画面を人が確認した料金だけを使い、12か月の支払額、プラン差、利用上限、税、移行費用を整理しています。未確認値は推測せず、計算や順位から除外します。</p>
      </header>
      <section className="shell page-section" aria-labelledby="pilot-list-title">
        <div className="section-heading"><p className="eyebrow">PUBLISHED GUIDES</p><h2 id="pilot-list-title">確認したい条件から選ぶ</h2></div>
        <div className="policy-cards">
          {orderedPages.map((page, index) => {
            return <article key={page.slug}>
              <span>{page.id} / {String(index + 1).padStart(2, "0")}{firstRelease.has(page.id as (typeof firstReleasePilotIds)[number]) ? " / 基本ガイド" : ""}</span>
              <h2><Link href={`/pilot/${page.slug}`}>{page.title}</Link></h2>
              <p>{page.question}</p>
            </article>;
          })}
        </div>
      </section>
    </main>
  );
}
