import type { Metadata } from "next";

import { ServerArticleTemplate } from "../../components/PilotArticle";
import { serverArticleSlate, serverCtaPresentationPolicy } from "../../lib/pilot-pages";
import type { ServerZeroInputContract } from "../../lib/tco";

export const metadata: Metadata = {
  title: "法人向けサーバー料金: 価格観測待ち",
  description: "初期費用・更新料込み12か月TCOをHuman確認済み価格だけで比較する公開前標本。",
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
};

const contract: ServerZeroInputContract = { articleReviewStatus: "unreviewed", plans: [] };
const article = serverArticleSlate[0];

export default function BusinessServerPricingPage() {
  return (
    <ServerArticleTemplate
      article={article}
      calculatorContract={contract}
      ctaPolicy={serverCtaPresentationPolicy([])}
      evidence={<div className="editorial-sections">
        {article.sections.map((section, index) => <article key={section.title}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <h2>{section.title}</h2>
          <p>{section.focus}。確認済み価格がない間は実額・順位・推奨を表示しません。</p>
        </article>)}
        <article>
          <span>07</span><h2>価格観測の入口</h2>
          <p>公式料金ページをHumanが確認し、初期費用・通常料金・更新時請求額・キャンペーン・ドメイン特典を別fieldとしてOperatorへ入力します。</p>
        </article>
      </div>}
    />
  );
}
