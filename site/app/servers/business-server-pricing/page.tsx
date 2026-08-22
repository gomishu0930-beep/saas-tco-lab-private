import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ServerArticleTemplate } from "../../components/PilotArticle";
import {
  serverEvidenceLabels,
  serverEvidenceValue,
} from "../../lib/editorial-input-contract";
import { serverArticleSlate, serverCtaPresentationPolicy } from "../../lib/pilot-pages";
import {
  m3ConfirmedFirstYearEvidence,
  m3ServerEvidence,
  serverUseCaseRequirements,
  xserverSmallSiteEvidence,
} from "../../lib/server-comparison-contract";

const svr01Evidence = xserverSmallSiteEvidence;

const svr01ArticleApproved = svr01Evidence?.initialPayment !== null;
const approvedSvr01Title = "XServerビジネス料金（2026年8月確認）：契約時請求66,660円と未確認費用";
const unconfirmedServerComparators = [
  ["lolipop", "ロリポップ！ / プラン未確認"],
  ["onamae-rental-server", "お名前.com レンタルサーバー / プラン未確認"],
  ["shin-rental-server", "シンレンタルサーバー / プラン未確認"],
  ["ablenet-shared-server", "ABLENET / プラン未確認"],
] as const;

function displayAmount(value: string): string {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return value;
  return `${BigInt(match[1]).toLocaleString("ja-JP")}${match[2] ? `.${match[2]}` : ""}`;
}

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
  const isApprovedSvr01 = article.id === "SVR01" && svr01ArticleApproved;
  const title = isApprovedSvr01
    ? approvedSvr01Title
    : article.titleTemplate;
  const description = isApprovedSvr01
    ? "XServerビジネス共有スタンダードの12か月一括前払額と初期費用を公式画面で確認。キャッシュバック控除前の契約時請求額と、未確認の更新・特典条件を分けて説明します。"
    : `${article.readerQuestion} Human確認済み価格だけで検証する公開前候補です。未確認値は順位と計算から除外します。`;
  return {
    title,
    description,
    robots: { index: false, follow: false, noarchive: true, nosnippet: true },
    openGraph: { title, description, type: "article", siteName: "SaaS TCO Lab" },
    twitter: { card: "summary", title, description },
  };
}

export default async function BusinessServerPricingPage({ searchParams }: ServerCandidatePageProps) {
  const article = await requestedArticle(searchParams);
  const evidence = article.id === "SVR01" ? svr01Evidence : null;
  const initialPayment = evidence?.initialPayment;
  const evidenceObservedDates = [...new Set(evidence?.fields.map((field) => field.observed_on) ?? [])];
  const evidenceNextReviewDates = [...new Set(evidence?.fields.map((field) => field.next_review_on) ?? [])];
  const calculatorContract = evidence ? {
    articleReviewStatus: article.id === "SVR01" && initialPayment ? "approved" as const : "unreviewed" as const,
    useCaseRequirements: serverUseCaseRequirements,
    plans: [
      ...evidence.calculatorContract.plans.map((plan) => ({
        ...plan,
        eligibleUseCases: plan.eligibleUseCases,
      })),
      ...m3ServerEvidence.flatMap((item) => item.calculatorContract.plans),
      ...unconfirmedServerComparators.map(([vendorId, displayName]) => ({
        vendorId,
        planId: "unconfirmed",
        displayName,
        priceStatus: "unknown" as const,
        reviewStatus: "unreviewed" as const,
        eligibleUseCases: [] as const,
        quote: null,
        serverTerms: null,
        unknownReason: "公式価格と同条件の請求総額が未確認のため順位対象外",
        confirmedThroughMonths: null,
        horizonUnknownReason: null,
        observedOn: null,
        nextReviewOn: null,
      })),
    ],
  } : {
    articleReviewStatus: "unreviewed" as const,
    useCaseRequirements: serverUseCaseRequirements,
    plans: [],
  };
  const confirmedFirstYearPrices = [
    ...(evidence?.initialPayment ? [{
      displayName: evidence.displayName,
      initialPayment: evidence.initialPayment,
      suitability: "small_siteをHuman確認済み",
    }] : []),
    ...m3ConfirmedFirstYearEvidence.map((item) => ({
      displayName: item.displayName,
      initialPayment: item.initialPayment!,
      suitability: item.calculatorContract.plans[0].eligibleUseCases.length
        ? `${item.calculatorContract.plans[0].eligibleUseCases.join(" / ")}をHuman確認済み`
        : "用途条件の追加Human確認待ち",
    })),
  ];
  const displayArticle = initialPayment ? {
    ...article,
    titleTemplate: approvedSvr01Title,
    readerQuestion: "新規12か月契約で最初に請求される金額と、まだ確定できない更新・特典条件は何か",
  } : article;
  const serverStructuredData = initialPayment ? {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        name: approvedSvr01Title,
        description: "XServerビジネス共有スタンダードの新規12か月契約について、公式画面で確認した契約時請求額と未確認条件を分けた料金記録。",
        category: "法人向けレンタルサーバー",
        offers: {
          "@type": "Offer",
          name: "XServerビジネス 共有スタンダード（新規12か月・キャッシュバック控除前）",
          price: initialPayment.amount,
          priceCurrency: initialPayment.currency,
          priceValidUntil: initialPayment.nextReviewOn,
        },
      },
      {
        "@type": "FAQPage",
        mainEntity: [{
          "@type": "Question",
          name: displayArticle.readerQuestion,
          acceptedAnswer: {
            "@type": "Answer",
            text: `公式画面で確認できた契約時請求額は${displayAmount(initialPayment.amount)}円（税込）です。期間限定キャッシュバックは控除せず、更新額や特典価値は未確認として分離しています。`,
          },
        }],
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "SaaS TCO Lab", item: "https://saastcolab.jp/" },
          { "@type": "ListItem", position: 2, name: approvedSvr01Title },
        ],
      },
    ],
  } : null;
  const evidenceValue = (fieldName: string) => {
    const field = evidence?.fields.find((item) => item.field === fieldName);
    return field ? serverEvidenceValue(field) : "未確認";
  };
  const readerSections = initialPayment ? [
    { title: "結論", body: `新規12か月契約で確認できた契約時請求額は${displayAmount(initialPayment.amount)}円（${initialPayment.taxTreatment === "included" ? "税込" : "税別"}）です。期間限定キャッシュバックを控除する前の金額で、更新後の総額や他社との順位ではありません。` },
    { title: "比較前提", body: "対象はXServerビジネスの共有スタンダード、12か月契約です。新規契約時の表示だけを扱い、契約更新、別プラン、専用サーバーの価格へは流用しません。" },
    { title: "料金と上限", body: `12か月の一括前払額は${displayAmount(initialPayment.annualCheckoutTotal)}円、初期費用は${displayAmount(initialPayment.initialFee)}円です。確認済みの仕様はストレージ${evidenceValue("servers.storage_gb")}、データ転送量${evidenceValue("servers.data_transfer_gb")}、バックアップ料金${evidenceValue("servers.backup_price")}です。` },
    { title: "12か月TCO", body: `確認済みの契約料金だけを足すと${displayAmount(initialPayment.amount)}円です。年額と初期費用を二重計上せず、未確定のキャッシュバックやドメイン特典を値引きとして差し引いていません。` },
    { title: "反証", body: "更新時請求額、キャッシュバックの確定額と受取条件、ドメイン特典の金銭価値・適用期間、計算資源の時間上限は未確認です。このため24か月・36か月の総額や費用対効果は確定できません。" },
    { title: "選び方", body: "この記録は1社1プランの契約時負担を確認する材料です。他社より安いとは断定せず、必要な運用条件と更新額を同じ基準で確認できた候補がそろってから比較します。" },
  ] : evidence ? [
    { title: "結論", body: "12か月の年次請求画面には50,160 JPY（税込）、初期費用には16,500 JPY（税込）と表示されています。ただし、どちらも現在の観測記録では期間限定表示に分類されているため、合算した契約時総額やTCOは確定していません。" },
    { title: "比較前提", body: "対象はXServerビジネスの共有スタンダード、12か月契約です。新規契約時の表示だけを扱い、契約更新、別プラン、専用サーバーの価格へは流用しません。" },
    { title: "料金と上限", body: `確認済みの表示は年次請求50,160 JPYと初期費用16,500 JPYです。仕様はストレージ${evidenceValue("servers.storage_gb")}、データ転送量${evidenceValue("servers.data_transfer_gb")}、バックアップ料金${evidenceValue("servers.backup_price")}を確認しています。` },
    { title: "12か月の表示額", body: "表示された2つの金額は証拠表へ個別に残します。価格本体とキャンペーンの関係をHumanが再確認するまでは、合算値を本文・計算機・構造化データへ出しません。" },
    { title: "反証", body: "更新時請求額、キャッシュバックの確定額と受取条件、ドメイン特典の金銭価値・適用期間、計算資源の時間上限は未確認です。このため12か月TCO、24か月・36か月の総額や費用対効果は確定できません。" },
    { title: "選び方", body: "この記録は1社1プランの画面表示を確認する材料です。他社より安いとは断定せず、価格表示分類と更新額を同じ基準で確認できた候補がそろってから比較します。" },
  ] : article.sections.map((section) => ({
    title: section.title,
    body: `${section.focus}。確認済みの値だけを表示し、未確認値は0円へ置き換えません。`,
  }));
  return (
    <ServerArticleTemplate
      article={displayArticle}
      articleReviewStatus={article.id === "SVR01" && initialPayment ? "approved" : "unreviewed"}
      calculatorContract={calculatorContract}
      ctaPolicy={serverCtaPresentationPolicy([])}
      evidence={(
        <div className="editorial-sections">
          {serverStructuredData ? <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(serverStructuredData).replaceAll("<", "\\u003c") }}
          /> : null}
          {evidence ? <article className="server-observation-summary">
            <span>00</span>
            <h2>現在の確認状態</h2>
            {initialPayment ? <>
              <p><strong>{evidence.displayName}の新規12か月契約で、契約時に確認できた請求額は{displayAmount(initialPayment.amount)}円（{initialPayment.taxTreatment === "included" ? "税込" : "税別"}）です。</strong></p>
              <p>証拠11項目の内訳は、確認済み{evidence.knownCount}項目、未確認{evidence.unknownCount}項目、該当なし{evidence.notApplicableCount}項目です。</p>
              <p>年次請求総額{displayAmount(initialPayment.annualCheckoutTotal)}円と初期費用{displayAmount(initialPayment.initialFee)}円の合計です。期間限定キャッシュバックは控除せず、更新額・特典価値・用途適合が未確認のため、24/36か月総額・順位・推奨は表示しません。</p>
            </> : <>
              <p>{evidence.displayName}は、確認済み{evidence.knownCount}項目、未確認{evidence.unknownCount}項目、該当なし{evidence.notApplicableCount}項目です。</p>
              <p><strong>年次請求50,160 JPYと初期費用16,500 JPYは個別の確認値として表示しますが、期間限定表示と更新額未確認が残るため、合算総額・TCO・順位・推奨は表示しません。</strong></p>
            </>}
          </article> : null}
          {confirmedFirstYearPrices.length ? <article className="server-first-year-price-summary" data-server-confirmed-price-vendors={confirmedFirstYearPrices.length}>
            <span>00B</span>
            <h2>3社の12か月契約時価格を確認</h2>
            <p>
              同じ通貨・税込・12か月の契約時請求額として確認できた価格だけを並べます。
              更新時請求額が未確認の行は24か月・36か月へ延長せず、用途条件が未確認の行は順位から除外します。
            </p>
            <div className="table-scroll" tabIndex={0} aria-label="3社の12か月契約時価格を横スクロール">
              <table>
                <thead><tr><th>サービス・プラン</th><th>契約時請求額</th><th>用途条件</th><th>観測日</th><th>次回確認日</th></tr></thead>
                <tbody>{confirmedFirstYearPrices.map(({ displayName: name, initialPayment: payment, suitability }) => (
                  <tr key={name}>
                    <th>{name}</th>
                    <td><strong>{payment.currency} {displayAmount(payment.amount)}</strong></td>
                    <td>{suitability}</td>
                    <td>{payment.observedOn}</td>
                    <td>{payment.nextReviewOn}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p>この一覧は確認済み価格の存在を示すもので、用途条件がそろう前に最安順位を付けるものではありません。</p>
          </article> : null}
          {readerSections.map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </article>
          ))}
          {evidence ? <article className="server-evidence-table">
            <span>07</span>
            <h2>公式画面の確認記録</h2>
            <p>確認済み実額は契約時請求66,660円です。観測日 {evidenceObservedDates.join(", ")}／次回確認日 {evidenceNextReviewDates.join(", ")}。</p>
            <details className="evidence-details">
              <summary>出典・観測日・未確認理由を詳しく見る</summary>
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
            </details>
          </article> : null}
          <article>
            <span>{evidence ? "08" : "07"}</span>
            <h2>価格観測の方法</h2>
            <p>公式料金ページで、初期費用・通常料金・更新時請求額・キャンペーン・ドメイン特典を別々に確認します。</p>
          </article>
        </div>
      )}
    />
  );
}
