import type { Metadata } from "next";
import Link from "next/link";

import { pilotPages } from "../lib/pilot-pages";

export const metadata: Metadata = {
  title: "合成noindex pilot",
  description: "高意図クエリ向け12本の記事構造を合成データだけで検証する公開前pilot。",
};

export default function PilotIndexPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">12 SYNTHETIC PILOT PAGES</p>
        <h1>高意図記事を、公開せずに12本検証する。</h1>
        <p>すべて合成fixture、robots noindex、CTA無効です。実在価格やAffiliate評価は含みません。</p>
      </header>
      <section className="shell page-section" aria-labelledby="pilot-list-title">
        <div className="section-heading"><p className="eyebrow">PILOT MANIFEST</p><h2 id="pilot-list-title">記事構造一覧</h2></div>
        <div className="policy-cards">
          {pilotPages.map((page, index) => (
            <article key={page.slug}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2><Link href={`/pilot/${page.slug}/`}>{page.title}</Link></h2>
              <p>{page.question}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
