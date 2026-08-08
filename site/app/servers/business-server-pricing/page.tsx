import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";

import { ServerArticleTemplate } from "../../components/PilotArticle";
import { serverArticleSlate, serverCtaPresentationPolicy } from "../../lib/pilot-pages";
import type { ServerZeroInputContract } from "../../lib/tco";

const emptyContract: ServerZeroInputContract = { articleReviewStatus: "unreviewed", plans: [] };

type ServerCandidatePageProps = {
  searchParams: Promise<{ candidate?: string | string[] }>;
};

async function requestedArticle(searchParams: ServerCandidatePageProps["searchParams"]) {
  const candidate = (await searchParams).candidate;
  if (candidate === undefined) return serverArticleSlate[0];
  if (Array.isArray(candidate)) notFound();
  const article = serverArticleSlate.find((item) => item.id === candidate);
  if (!article) notFound();
  return article;
}

export async function generateMetadata({ searchParams }: ServerCandidatePageProps): Promise<Metadata> {
  const article = await requestedArticle(searchParams);
  const description = `${article.readerQuestion} Human確認済み価格だけで検証する公開前候補です。未確認値は順位と計算から除外します。`;
  return {
    title: article.titleTemplate,
    description,
    robots: { index: false, follow: false, noarchive: true, nosnippet: true },
    openGraph: { title: article.titleTemplate, description, type: "article", siteName: "SaaS TCO Lab" },
    twitter: { card: "summary", title: article.titleTemplate, description },
  };
}

export default async function BusinessServerPricingPage({ searchParams }: ServerCandidatePageProps) {
  const article = await requestedArticle(searchParams);
  return (
    <ServerArticleTemplate
      article={article}
      calculatorContract={emptyContract}
      ctaPolicy={serverCtaPresentationPolicy([])}
      evidence={(
        <div className="editorial-sections">
          {article.sections.map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.focus}。確認済み価格がない間は、実額・順位・推奨を表示しません。</p>
            </article>
          ))}
          <article>
            <span>07</span>
            <h2>価格観測の入口</h2>
            <p>公式料金ページをHumanが確認し、初期費用・通常料金・更新時請求額・キャンペーン・ドメイン特典を別fieldとしてOperatorへ入力します。</p>
            <Link className="text-link" href="/operator/servers/">servers価格観測Operatorを開く</Link>
          </article>
        </div>
      )}
    />
  );
}
