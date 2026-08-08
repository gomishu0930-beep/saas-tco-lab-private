import type { Metadata } from "next";
import Link from "next/link";

import { AdvertisingDisclosure } from "../../components/AdvertisingDisclosure";

export const metadata: Metadata = {
  title: "埋め込み用TCO表示",
  description: "承認済み価格contractを使うzero-input TCO表示の埋め込み境界。",
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nosnippet: true,
  },
};

export default function EmbeddedTcoCalculatorPage() {
  return (
    <main id="main-content" className="embed-page">
      <AdvertisingDisclosure />
      <h1>埋め込み用TCO表示</h1>
      <section className="embed-calculator" aria-labelledby="embed-zero-input-title">
        <div className="calculator-card">
          <div>
            <p className="eyebrow">ZERO-INPUT ONLY</p>
            <h2 id="embed-zero-input-title">承認済み価格を待っています</h2>
            <p>serversの承認済みcontractがないため、価格や税を推測した計算結果は表示しません。</p>
          </div>
          <output className="calculator-result">
            <span>表示状態</span><strong>未確認</strong><small>承認済み行だけを表示します</small>
          </output>
          <p className="calculator-source">
            <Link href="/methodology/#detailed-calculator" target="_top">詳細計算モード</Link>
            <span>任意入力式は算定方法ページへ移設しました。</span>
          </p>
        </div>
      </section>
    </main>
  );
}
