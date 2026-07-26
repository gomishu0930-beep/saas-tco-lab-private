import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SaaS TCO Lab | 公開前比較MVP",
    template: "%s | SaaS TCO Lab",
  },
  description:
    "権利と根拠期限を検査し、事前計算済み12か月TCOでSaaSを比較する公開前MVP。",
  robots: {
    index: false,
    follow: false,
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
              <Link href="/comparison/">比較</Link>
              <Link href="/methodology/">算定方法</Link>
              <Link href="/learning/">学習と施策</Link>
              <Link href="/readiness/">公開準備</Link>
              <Link href="/operator/">あなたの操作</Link>
              <Link href="/disclosure/">広告表示</Link>
            </nav>
            <span className="noindex-badge">NOINDEX</span>
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
              <p className="footer-label">PRE-PUBLIC CONTROL</p>
              <p>合成データのみ / 外部送客なし / robots noindex</p>
            </div>
            <nav aria-label="フッターナビゲーション">
              <Link href="/methodology/">算定方法</Link>
              <Link href="/disclosure/">広告表示</Link>
              <Link href="/readiness/">公開準備</Link>
              <Link href="/learning/">学習と施策</Link>
              <Link href="/operator/">あなたの操作</Link>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
