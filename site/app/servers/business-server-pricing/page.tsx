import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";

import savedSvr01Candidate from "../../../../artifacts/category-expansion-inputs/SVR01-servers-category-expansion-input-v2-2026-08-08.json";

import { ServerArticleTemplate } from "../../components/PilotArticle";
import {
  reviewedServerCandidateEvidence,
  serverEvidenceLabels,
  serverEvidenceValue,
} from "../../lib/editorial-input-contract";
import { serverArticleSlate, serverCtaPresentationPolicy } from "../../lib/pilot-pages";

const localRuntime = process.env.SAAS_RUNTIME_MODE !== "production";
const svr01Evidence = reviewedServerCandidateEvidence(
  savedSvr01Candidate,
  "XServerビジネス 共有スタンダード（12か月）",
  "business.xserver.ne.jp",
);

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
  const evidence = localRuntime && article.id === "SVR01" ? svr01Evidence : null;
  return (
    <ServerArticleTemplate
      article={article}
      calculatorContract={evidence?.calculatorContract ?? { articleReviewStatus: "unreviewed", plans: [] }}
      ctaPolicy={serverCtaPresentationPolicy([])}
      evidence={(
        <div className="editorial-sections">
          {evidence ? <article className="server-observation-summary">
            <span>00</span>
            <h2>現在の確認状態</h2>
            <p>
              {evidence.displayName}は、確認済み{evidence.knownCount}項目、未確認{evidence.unknownCount}項目、
              該当なし{evidence.notApplicableCount}項目です。期間限定表示と更新額未確認が残るため、総額・順位・推奨は表示しません。
            </p>
          </article> : null}
          {article.sections.map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.focus}。確認済みの値だけを表示し、未確認値は0円へ置き換えません。</p>
            </article>
          ))}
          {evidence ? <article className="server-evidence-table">
            <span>07</span>
            <h2>公式画面の確認記録</h2>
            <div className="table-scroll" tabIndex={0} aria-label="XServerビジネスの確認記録を横スクロール">
              <table>
                <thead><tr><th>確認項目</th><th>値</th><th>出典</th><th>観測日</th><th>次回確認日</th></tr></thead>
                <tbody>{evidence.fields.map((field) => <tr key={field.field}>
                  <th>{serverEvidenceLabels[field.field] ?? field.field}</th>
                  <td>{serverEvidenceValue(field)}</td>
                  <td>{field.source_url ? <a href={field.source_url} rel="noopener noreferrer">公式ページ</a> : "—"}</td>
                  <td>{field.observed_on}</td>
                  <td>{field.next_review_on}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </article> : null}
          <article>
            <span>{evidence ? "08" : "07"}</span>
            <h2>価格観測の入口</h2>
            <p>公式料金ページで、初期費用・通常料金・更新時請求額・キャンペーン・ドメイン特典を別々に確認します。</p>
            <Link className="text-link" href="/operator/servers/">servers価格観測Operatorを開く</Link>
          </article>
        </div>
      )}
    />
  );
}
