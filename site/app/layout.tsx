import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

const productionRuntime = process.env.SAAS_RUNTIME_MODE === "production";

export const metadata: Metadata = {
  metadataBase: new URL("https://saastcolab.jp"),
  title: {
    default: "SaaS TCO Lab",
    template: "%s | SaaS TCO Lab",
  },
  description:
    "Human確認済みの価格、契約条件、利用上限を根拠付き12か月TCOで比較するSaaS選定メディア。",
  robots: {
    index: false,
    follow: productionRuntime,
    noarchive: true,
    nosnippet: true,
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>
        <a className="skip-link" href="#main-content">
          本文へ移動
        </a>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/" aria-label="SaaS TCO Lab ホーム">
              <span className="brand-mark" aria-hidden="true">S</span>
              <span>
                SaaS TCO <b>LAB</b>
              </span>
            </Link>
            <nav aria-label="主要ナビゲーション">
              {productionRuntime ? (
                <>
                  <Link data-public-article-link="/servers/business-server-pricing" href="/servers/business-server-pricing">サーバー料金</Link>
                  <Link data-public-article-link="/pilot/pricing-calculator" href="/pilot/pricing-calculator">SEOツール料金</Link>
                  <Link href="/methodology">算定方法</Link>
                </>
              ) : (
                <>
                  <Link href="/methodology">算定方法</Link>
                  <Link href="/comparison">比較</Link>
                  <Link href="/learning">学習と施策</Link>
                  <Link href="/readiness">公開準備</Link>
                  <Link href="/operator">あなたの操作</Link>
                </>
              )}
              <Link href="/disclosure">広告表示</Link>
            </nav>
            <span className="noindex-badge">{productionRuntime ? "検証方針公開" : "CONTROLLED"}</span>
          </div>
        </header>
        {children}
        <footer className="site-footer">
          <div className="shell footer-grid">
            <div>
              <p className="footer-brand">SaaS TCO LAB</p>
              <p>根拠・権利・期限を先にする、データ駆動型SaaS比較。</p>
            </div>
            <div>
              <p className="footer-label">PUBLICATION CONTROL</p>
              <p>Human review / index gate / CTA gate</p>
            </div>
            <nav aria-label="フッターナビゲーション">
              <Link href="/about">About</Link>
              <Link href="/operator-information">運営者情報</Link>
              <Link href="/privacy">プライバシー</Link>
              <Link href="/contact">お問い合わせ</Link>
              <Link href="/advertising-policy">広告ポリシー</Link>
              <Link href="/methodology">算定方法</Link>
              <Link href="/disclosure">広告表示</Link>
              {productionRuntime ? (
                <>
                  <Link data-public-article-link="/servers/business-server-pricing" href="/servers/business-server-pricing">サーバー料金</Link>
                  <Link data-public-article-link="/pilot/pricing-calculator" href="/pilot/pricing-calculator">SEOツール料金</Link>
                  <Link data-public-article-link="/pilot/evidence-method" href="/pilot/evidence-method">根拠方針</Link>
                </>
              ) : (
                <>
                  <Link href="/readiness">公開準備</Link>
                  <Link href="/learning">学習と施策</Link>
                  <Link href="/operator">あなたの操作</Link>
                </>
              )}
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
