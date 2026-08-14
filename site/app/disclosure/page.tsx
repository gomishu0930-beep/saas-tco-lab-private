import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "広告表示",
  description: "SaaS TCO Labのアフィリエイト表示、編集判断、CTA制御に関する方針。",
};

export default function DisclosurePage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header narrow">
        <p className="eyebrow">AFFILIATE DISCLOSURE</p>
        <h1>広告収益と、比較判断を混ぜない。</h1>
        <p>
          承認済み記事にはMangoolsのアフィリエイトリンクを含む場合があります。
          提携の有無は比較条件やTCO計算へ混入させません。
        </p>
      </header>
      <section className="shell policy-cards" aria-label="広告方針">
        <article>
          <span>01</span><h2>表示位置</h2>
          <p>広告であることを、CTAと判断箇所のすぐ近くに明示します。</p>
        </article>
        <article>
          <span>02</span><h2>リンク属性</h2>
          <p>有効な広告リンクには sponsored・noopener・noreferrer を付与します。</p>
        </article>
        <article>
          <span>03</span><h2>期限連動</h2>
          <p>提携期限に到達したCTAは自動で無効化し、報酬前提の表示も止めます。</p>
        </article>
        <article>
          <span>04</span><h2>編集独立性</h2>
          <p>TCOと適合判定は証拠とscenarioで決まり、報酬額では並べ替えません。</p>
        </article>
      </section>
      <section className="shell disclosure-statement" aria-labelledby="current-state">
        <p className="eyebrow">CURRENT STATE</p>
        <h2 id="current-state">現在の広告状態: Mangoolsのみ有効</h2>
        <p>
          Human承認済みの11記事に限り、記事冒頭のPR表示より後でMangools CTAを有効にしています。
          他partnerは提携・掲載先・広告表示・個別CTA承認の全条件が一致するまで無効です。
        </p>
      </section>
    </main>
  );
}
