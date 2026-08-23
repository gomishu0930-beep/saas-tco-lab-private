import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import editorialLaunchState from "../../../../docs/EDITORIAL_LAUNCH_STATE.json";

import { ServerArticleTemplate } from "../../components/PilotArticle";
import {
  serverEvidenceLabels,
  serverEvidenceValue,
} from "../../lib/editorial-input-contract";
import {
  serverArticleSlate,
  serverCtaPresentationPolicy,
  serverInternalRevenueFunnelFor,
  serverLaunchBriefFor,
  type ServerArticleSlateEntry,
} from "../../lib/pilot-pages";
import {
  serverFirstYearComparisonEvidence,
  serverUseCaseRequirements,
} from "../../lib/server-comparison-contract";
import {
  serializeStructuredData,
  serverArticleStructuredData,
} from "../../lib/structured-data";

type ServerCandidatePageProps = {
  params: Promise<{ slug: string }>;
};

const candidateArticles = serverArticleSlate.filter((article) => article.id !== "SVR01");
const approvedServerArticleIds = new Set(
  Object.entries(editorialLaunchState.server_articles ?? {})
    .filter(([, state]) => state === "approved")
    .map(([articleId]) => articleId),
);

function articleBySlug(slug: string): ServerArticleSlateEntry {
  const article = candidateArticles.find((item) => item.slug === slug);
  if (!article) notFound();
  return article;
}

export function generateStaticParams() {
  return candidateArticles.map((article) => ({ slug: article.slug }));
}

export async function generateMetadata({ params }: ServerCandidatePageProps): Promise<Metadata> {
  const article = articleBySlug((await params).slug);
  const approved = approvedServerArticleIds.has(article.id);
  const title = approved ? article.titleTemplate : `${article.titleTemplate}（価格確認中）`;
  const description = approved
    ? `${article.readerQuestion} 公式ページで確認した価格・条件だけを使い、未確認値を順位・差額・推奨へ使いません。`
    : `${article.readerQuestion} 公式価格の確認が終わるまで、未確認値を順位・差額・推奨へ使わない候補記事です。`;
  return {
    title,
    description,
    openGraph: { title, description, type: "article", siteName: "SaaS TCO Lab" },
    twitter: { card: "summary", title, description },
  };
}

export default async function ServerCandidatePage({ params }: ServerCandidatePageProps) {
  const article = articleBySlug((await params).slug);
  const articleReviewStatus = approvedServerArticleIds.has(article.id) ? "approved" as const : "unreviewed" as const;
  const launchBrief = serverLaunchBriefFor(article.id);
  const internalRevenueFunnel = serverInternalRevenueFunnelFor(article.id);
  const calculatorContract = {
    articleReviewStatus,
    useCaseRequirements: serverUseCaseRequirements,
    plans: serverFirstYearComparisonEvidence.flatMap((evidence) => evidence.calculatorContract.plans),
  };
  const totalKnown = serverFirstYearComparisonEvidence.reduce((total, evidence) => total + evidence.knownCount, 0);
  const totalUnknown = serverFirstYearComparisonEvidence.reduce((total, evidence) => total + evidence.unknownCount, 0);
  const totalNotApplicable = serverFirstYearComparisonEvidence.reduce(
    (total, evidence) => total + evidence.notApplicableCount,
    0,
  );
  const structuredData = serverArticleStructuredData(
    article,
    articleReviewStatus,
    serverFirstYearComparisonEvidence,
  );

  return (
    <ServerArticleTemplate
      article={article}
      articleReviewStatus={articleReviewStatus}
      calculatorContract={calculatorContract}
      ctaPolicy={serverCtaPresentationPolicy([])}
      internalRevenueFunnel={internalRevenueFunnel}
      evidence={(
        <div className="editorial-sections">
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: serializeStructuredData(structuredData) }}
          />
          {launchBrief ? <article className="server-launch-brief" data-server-launch-brief={article.id}>
            <span>00</span>
            <h2>この記事で判断すること</h2>
            <p>{launchBrief.decisionRule}</p>
            <p>公式ページで確認できた金額と条件だけを使います。確認できない項目は0円に置き換えず、順位や差額から除外します。</p>
          </article> : null}
          <article className="server-observation-summary" data-server-candidate-batch="M3">
            <span>{launchBrief ? "00A" : "00"}</span>
            <h2>4社の料金と用途条件を確認しました</h2>
            <p>
              XServerビジネス、ConoHa WING、さくらのレンタルサーバ、KAGOYAの公式画面を確認し、
              {serverFirstYearComparisonEvidence.length}社・{serverFirstYearComparisonEvidence.length * Object.keys(serverEvidenceLabels).length}項目を記録しました。
            </p>
            <p>
              内訳は確認済み{totalKnown}項目、未確認{totalUnknown}項目、該当なし{totalNotApplicable}項目です。
              期間限定価格、申込時の請求総額、更新額に未確認が残る行は、総額・順位・推奨から除外します。
            </p>
          </article>
          {(launchBrief?.readerSections ?? article.sections).map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.focus}。</p>
            </article>
          ))}
          {launchBrief ? <article className="server-launch-checks" data-server-launch-checks={article.id}>
            <span>07</span>
            <h2>公開前に残る確認</h2>
            <p>次の項目は公式料金だけでは確定できないため、未確認のまま表示します。</p>
            <ul>{launchBrief.additionalHumanChecks.map((check) => <li key={check}>{check}</li>)}</ul>
            <p><strong>最終確認:</strong> {launchBrief.approvalQuestion}</p>
          </article> : null}
          <article>
            <span>{launchBrief ? "08" : "07"}</span>
            <h2>{launchBrief ? "この記事で使う確認値" : "確認値と未確認理由"}</h2>
            <p>値が確認できた項目だけを表示します。未確認値は0円へ置き換えず、計算機と順位から除外します。</p>
            {serverFirstYearComparisonEvidence.map((evidence) => (
              <details className="evidence-details" key={`${evidence.vendorId}-${evidence.planId}`}>
                <summary>
                  {evidence.displayName}：確認済み{evidence.knownCount}／未確認{evidence.unknownCount}／該当なし{evidence.notApplicableCount}
                </summary>
                <div className="table-scroll" tabIndex={0} aria-label={`${evidence.displayName}の価格根拠表を横スクロール`}>
                  <table className="evidence-table">
                    <thead><tr><th>確認項目</th><th>値</th><th>状態・理由</th><th>観測日</th><th>次回確認日</th></tr></thead>
                    <tbody>{evidence.fields
                      .filter((field) => !launchBrief || launchBrief.reusableObservationFields.some((candidate) => candidate === field.field))
                      .map((field) => (
                      <tr key={`${evidence.vendorId}-${evidence.planId}-${field.field}`}>
                        <th>{serverEvidenceLabels[field.field] ?? field.field}</th>
                        <td>{serverEvidenceValue(field)}</td>
                        <td>{field.value_status === "known" ? "公式ページで確認済み" : field.unknown_reason ?? "未確認"}</td>
                        <td>{field.observed_on}</td>
                        <td>{field.next_review_on}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
                <p>出典URLは確認記録に保持しています。公開前レビュー中のため、このページから外部サイトへはリンクしません。</p>
              </details>
            ))}
            {articleReviewStatus === "approved"
              ? <p><strong>内容確認済みです。</strong> 検索登録と紹介リンクは、それぞれの公開設定が有効な場合だけ表示します。</p>
              : <p><strong>公開前レビュー中です。</strong> 内容確認が終わるまで検索登録と紹介リンクを有効にしません。</p>}
            <Link className="text-link" href="/methodology/">料金確認と計算方法を見る</Link>
          </article>
        </div>
      )}
    />
  );
}
