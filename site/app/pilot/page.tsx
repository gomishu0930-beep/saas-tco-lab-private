import type { Metadata } from "next";
import Link from "next/link";

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
        <p>本文下書きは12本完成し、第1弾はP01–P03です。作業順は取引意図の強いP01、P06、P07、P08、P09を先行し、P10・P12を最後にします。すべてrobots noindex、CTA無効で、Human入力値・出典URL・観測日・次回確認日が揃うまで実在価格を表示しません。</p>
      </header>
      <section className="shell page-section" aria-labelledby="pilot-list-title">
        <div className="section-heading"><p className="eyebrow">PILOT MANIFEST</p><h2 id="pilot-list-title">記事構造一覧</h2></div>
        <div className="policy-cards">
          {orderedPages.map((page, index) => (
            <article key={page.slug}>
              <span>{page.id} / 優先 {String(index + 1).padStart(2, "0")}{firstRelease.has(page.id as (typeof firstReleasePilotIds)[number]) ? " / 公開第1弾" : ""}</span>
              <h2><Link href={`/pilot/${page.slug}/`}>{page.title}</Link></h2>
              <p>{page.question}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
