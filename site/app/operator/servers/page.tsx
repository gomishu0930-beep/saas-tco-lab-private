import type { Metadata } from "next";
import Link from "next/link";

import { ServerObservationForm } from "../../components/ServerObservationForm";
import { serverArticleSlate } from "../../lib/pilot-pages";

export const metadata: Metadata = {
  title: "サーバー価格観測",
  description: "サーバー料金をHuman確認し、candidate-only contractへ変換するローカル入力画面。",
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
};

export default function ServerOperatorPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">SERVERS / HUMAN INPUT</p>
        <h1>通常料金・更新料・特典を、<br />一つずつ分けて記録。</h1>
        <p>価格確認20分、入力20分、表示確認20分。値を推測せず、未確認は理由付きで残します。</p>
      </header>
      <div className="shell operator-input-wrap"><ServerObservationForm /></div>
      <section className="shell page-section" aria-labelledby="server-candidate-list-title">
        <div className="section-heading">
          <p className="eyebrow">SVR01–SVR20</p>
          <h2 id="server-candidate-list-title">価格観測と承認の待ち行列</h2>
        </div>
        <div className="route-grid" data-server-candidate-index="20">
          {serverArticleSlate.map((article) => (
            <article key={article.id}>
              <span>{article.id}</span>
              <h3><Link href={`/servers/business-server-pricing/?candidate=${article.id}`}>{article.topic}</Link></h3>
              <p>{article.readerQuestion}</p>
              <small>candidate only / 競合性未観測 / 実価格0件</small>
            </article>
          ))}
        </div>
      </section>
      <section className="shell page-section"><Link className="text-link" href="/operator/">通常のOperatorへ戻る</Link></section>
    </main>
  );
}
