import type { Metadata } from "next";
import Link from "next/link";

import { editorialContract } from "../lib/editorial-contracts";
import { firstReleasePilotIds, launchPriorityPages } from "../lib/pilot-pages";

export const metadata: Metadata = {
  title: "公開前の記事template",
  description: "Human確認済みの数値fieldを受け入れるP01–P12の公開前記事template。",
};

export default function PilotIndexPage() {
  const orderedPages = launchPriorityPages();
  const firstRelease = new Set(firstReleasePilotIds);
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">12 EDITORIAL TEMPLATES / NOINDEX</p>
        <h1>高意図記事を、公開前に12本組み立てる。</h1>
        <p>本文下書きは12本完成し、P01–P04・P06–P08・P10の8本はHuman承認後に公開済みです。P05・P09・P11・P12は入力・reviewを継続し、承認と個別releaseを満たすまではnoindex・CTA無効を維持します。</p>
      </header>
      <section className="shell page-section" aria-labelledby="pilot-list-title">
        <div className="section-heading"><p className="eyebrow">PILOT MANIFEST</p><h2 id="pilot-list-title">記事構造一覧</h2></div>
        <div className="policy-cards">
          {orderedPages.map((page, index) => {
            const approvedCandidate = editorialContract(page)?.article_review_status === "approved";
            return <article key={page.slug}>
              <span>{page.id} / 優先 {String(index + 1).padStart(2, "0")}{firstRelease.has(page.id as (typeof firstReleasePilotIds)[number]) ? " / 公開第1弾" : ""}{approvedCandidate ? " / 承認済み公開候補" : ""}</span>
              <h2><Link href={`/pilot/${page.slug}/`}>{page.title}</Link></h2>
              <p>{page.question}</p>
            </article>;
          })}
        </div>
      </section>
    </main>
  );
}
