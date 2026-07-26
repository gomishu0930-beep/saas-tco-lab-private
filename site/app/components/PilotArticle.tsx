import Link from "next/link";

import type { PilotPage } from "../lib/pilot-pages";

export function PilotArticle({ page }: { page: PilotPage }) {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">SYNTHETIC NOINDEX PILOT / {page.pageType}</p>
        <h1>{page.title}を、公開前の証拠構造で検証する。</h1>
        <p>
          問いは「{page.question}」。このURLは記事構造の合成fixtureであり、
          実在サービスの価格・評価・提携リンクは含みません。
        </p>
      </header>

      <section className="shell page-section" aria-labelledby="pilot-structure-title">
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">BRIEF CONTRACT</p>
            <h2 id="pilot-structure-title">記事化前に固定するもの</h2>
          </div>
          <p>intentは{page.intent}。実データとfield-level権利が揃うまでclaim本文を生成しません。</p>
        </div>
        <div className="policy-cards">
          <article><span>01</span><h2>比較単位</h2><p>地域、通貨、税、期間、seat、利用量を同じscenarioに固定します。</p></article>
          <article><span>02</span><h2>証拠と期限</h2><p>material fieldごとにsource hashとdata・rights expiryを持たせます。</p></article>
          <article><span>03</span><h2>3視点の原稿</h2><p>analyst、editor、skeptical buyerを別々に評価し、claim map外の追加を拒否します。</p></article>
          <article><span>04</span><h2>収益導線</h2><p id="pilot-ad-disclosure">広告表示と提携承認が一致するまで送客CTAは無効です。</p><span className="cta-disabled" aria-describedby="pilot-ad-disclosure">CTA DISABLED</span></article>
        </div>
      </section>

      <section className="shell target-band" aria-labelledby="pilot-refresh-title">
        <div><p className="eyebrow">REFRESH TRIGGER</p><h2 id="pilot-refresh-title">更新と停止</h2></div>
        <dl>
          <div><dt>実データ</dt><dd>未投入</dd></div>
          <div><dt>field権利</dt><dd>未承認</dd></div>
          <div><dt>CTA</dt><dd>DISABLED</dd></div>
        </dl>
        <p>source・rights・Affiliateの期限切れ、遷移先や広告表示の不一致で即時STOPします。</p>
      </section>

      <section className="shell page-section">
        <Link className="text-link" href="/pilot/">12本のpilot一覧へ戻る</Link>
      </section>
    </main>
  );
}
