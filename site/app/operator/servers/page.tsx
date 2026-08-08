import type { Metadata } from "next";
import Link from "next/link";

import { ServerObservationForm } from "../../components/ServerObservationForm";

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
      <section className="shell page-section"><Link className="text-link" href="/operator/">通常のOperatorへ戻る</Link></section>
    </main>
  );
}
