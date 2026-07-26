import type { Metadata } from "next";

import { ComparisonTable } from "../components/ComparisonTable";
import { StatusStrip } from "../components/StatusStrip";
import { syntheticComparison } from "../lib/synthetic-data";

export const metadata: Metadata = {
  title: "合成SaaS比較",
  description: "公開前の合成データだけを使った12か月TCO比較。",
};

export default function ComparisonPage() {
  return (
    <>
      <StatusStrip />
      <main id="main-content" className="page-main">
        <header className="shell page-header">
          <p className="eyebrow">COMPARISON / SYNTHETIC ONLY</p>
          <h1>同じ条件で、総額と適合を比べる。</h1>
          <p>
            金額は画面で計算していません。canonical Python TCOから受け取った合成結果と、
            その判断条件・根拠・期限を一緒に表示しています。
          </p>
        </header>
        <section className="shell page-section" aria-labelledby="comparison-title">
          <h2 id="comparison-title" className="sr-only">比較結果</h2>
          <aside className="disclosure-panel" aria-label="広告とデータの状態">
            <strong>広告に関する表示</strong>
            <p>
              この公開前fixtureにはアフィリエイトリンクがなく、送客CTAは無効です。
              将来CTAを有効にする場合も、広告表示と提携期限を同じ判断領域に表示します。
            </p>
          </aside>
          <ComparisonTable data={syntheticComparison} />
        </section>
        <section className="shell conditions-grid" aria-labelledby="conditions-title">
          <div>
            <p className="eyebrow">FIXED INPUTS</p>
            <h2 id="conditions-title">今回の固定条件</h2>
          </div>
          <dl>
            <div><dt>市場</dt><dd>日本 / JP</dd></div>
            <div><dt>通貨</dt><dd>JPY</dd></div>
            <div><dt>seat</dt><dd>1</dd></div>
            <div><dt>期間</dt><dd>12か月</dd></div>
            <div><dt>利用量</dt><dd>0（合成条件）</dd></div>
            <div><dt>税</dt><dd>税込（合成条件）</dd></div>
          </dl>
        </section>
      </main>
    </>
  );
}
