import type { Metadata } from "next";
import Link from "next/link";

import { buildDerivativeTemplate } from "../../lib/derivative-templates";
import { launchPriorityPages } from "../../lib/pilot-pages";

export const metadata: Metadata = {
  title: "note・X再配信template",
  description: "P01–P12の承認済みclaim範囲から作る、Human投稿専用のnote・X再配信template。",
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
};

export default function DerivativeTemplatesPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">LOCAL DERIVATIVES / HUMAN POST ONLY</p>
        <h1>noteとXへ、<br />新しい主張を足さずに再編集。</h1>
        <p>全templateはPR表記から始まり、記事の問い・本文下書き・field一覧だけを再構成します。投稿、URL入力、最終承認はHumanが行います。</p>
      </header>
      <section className="shell derivative-list" aria-label="記事別再配信template">
        {launchPriorityPages().map((page) => {
          const template = buildDerivativeTemplate(page);
          return (
            <details key={page.id}>
              <summary><span>{page.id}</span><strong>{page.title}</strong><small>note {template.note.length.toLocaleString("ja-JP")}字 / X {template.xThread.length}投稿</small></summary>
              <div className="derivative-body">
                <h2>note用template</h2>
                <pre>{template.note}</pre>
                <h2>X用thread</h2>
                <ol>{template.xThread.map((post) => <li key={post}><pre>{post}</pre></li>)}</ol>
              </div>
            </details>
          );
        })}
      </section>
      <section className="shell page-section"><Link className="text-link" href="/operator/">Operatorへ戻る</Link></section>
    </main>
  );
}
