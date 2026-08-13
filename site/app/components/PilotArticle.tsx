import Link from "next/link";
import type { ReactNode } from "react";

import { articleDraft } from "../lib/article-drafts";
import { nextToReadPages } from "../lib/article-navigation";
import type { EditorialContract } from "../lib/editorial-input-contract";
import { editorialContract, hasUnknownFact } from "../lib/editorial-contracts";
import {
  editorialPresentation,
  planDisplayName,
  vendorDisplayName,
} from "../lib/editorial-presentation";
import {
  pilotFieldScope,
  pilotPages,
  type PilotPage,
  type ServerArticleSlateEntry,
  type ServerCtaPresentationPolicy,
} from "../lib/pilot-pages";
import type { ServerZeroInputContract } from "../lib/tco";
import { AdvertisingDisclosure } from "./AdvertisingDisclosure";
import { ArticleStructuredData } from "./ArticleStructuredData";
import { ServerZeroInputCalculator } from "./TcoCalculator";

const publicPrelaunch = process.env.SAAS_RUNTIME_MODE === "production";

type ImportedField = EditorialContract["numeric_fields"][number];

function fieldValue(field: ImportedField): string {
  if (field.value_status === "unknown") return "未確認";
  if (field.value_status === "not_applicable") return "該当なし";
  return `${field.value} ${field.unit}`.trim();
}

function currencyValue(field: ImportedField): string {
  if (field.currency_status === "known") return field.currency ?? "unknown（不明）";
  if (field.currency_status === "unknown") {
    return field.currency_display
      ? `unknown（画面表記: ${field.currency_display}）`
      : "unknown（不明）";
  }
  return "not_applicable（該当なし）";
}

function evidenceIdentity(field: ImportedField): string {
  if (field.scope_kind !== "vendor_plan") return "試算条件";
  return `${vendorDisplayName(field.vendor_id)} / ${planDisplayName(field.vendor_id, field.plan_id)}`;
}

function contractTokenValue(field: ImportedField): string {
  const value = fieldValue(field);
  const reviewPrefix = field.review_status === "approved" ? "" : "確認待ち: ";
  if (field.value_kind === "price" && field.currency_status === "known" && field.currency) {
    return `${reviewPrefix}${evidenceIdentity(field)}: ${field.currency} ${value}`;
  }
  return `${reviewPrefix}${evidenceIdentity(field)}: ${value}`;
}

function renderContractTokens(body: string, contract: EditorialContract | null): string {
  return body.replace(/\{\{contract:([a-z0-9_.]+)\.value\}\}/g, (_match, fieldPath: string) => {
    const matches = contract?.numeric_fields.filter((field) => field.field === fieldPath) ?? [];
    return matches.length ? matches.map(contractTokenValue).join("／") : "未確認（確認値なし）";
  });
}

function billingPeriodValue(value: string | null): string {
  switch (value) {
    case "annual": return "年次請求";
    case "monthly": return "月次請求";
    case "one_time": return "一回払い";
    case "per_usage": return "従量課金";
    case "not_applicable": return "not_applicable（該当なし）";
    default: return "unknown（不明）";
  }
}

function billingToggleValue(value: ImportedField["billing_toggle_state"]): string {
  switch (value) {
    case "annual_selected": return "年払い選択";
    case "monthly_selected": return "月払い選択";
    case "not_present": return "切替表示なし";
    default: return "unknown（不明）";
  }
}

function saleBannerValue(value: ImportedField["sale_banner_state"]): string {
  switch (value) {
    case "none": return "割引・キャンペーン表示なし";
    case "annual_discount_permanent": return "通常の年払い割引";
    case "time_limited_promo": return "期間限定価格（計算対象外）";
    default: return "表示条件を未確認（計算対象外）";
  }
}

function observedPriceBasisValue(value: ImportedField["observed_price_basis"]): string {
  switch (value) {
    case "checkout_billed_total": return "checkout請求総額（一次観測値）";
    case "displayed_price": return "公式画面の表示価格（一次観測値）";
    case "human_scenario": return "読者が変更できる試算条件";
    case "not_applicable": return "not_applicable（該当なし）";
    default: return "unknown（不明）";
  }
}

function taxTreatmentValue(value: string | null): string {
  switch (value) {
    case "included": return "included（税込）";
    case "excluded": return "excluded（税別）";
    case "not_applicable": return "not_applicable（該当なし）";
    default: return "unknown（税込・税別未確認）";
  }
}

function AnnualTcoEvidence({ page, contract }: { page: PilotPage; contract: EditorialContract | null }) {
  if (!contract || !["P01", "P02", "P03"].includes(page.id)) return null;
  const rows = contract.numeric_fields.filter((field) => (
    field.scope_kind === "vendor_plan"
    && field.value_kind === "price"
    && field.value_status === "known"
    && field.billing_period === "annual"
    && field.observed_price_basis === "checkout_billed_total"
    && field.value !== null
    && field.currency_status === "known"
    && field.currency !== null
  ));
  if (!rows.length) return null;
  const unresolvedAnnualPrices = contract.numeric_fields.filter((field) => (
    field.scope_kind === "vendor_plan"
    && field.value_kind === "price"
    && field.billing_period === "annual"
    && field.value_status !== "known"
  ));
  return (
    <section className="shell page-section" aria-labelledby={`${page.id}-annual-tco`}>
      <div className="section-heading split-heading">
        <div><p className="eyebrow">確認済みの支払額</p><h2 id={`${page.id}-annual-tco`}>12か月TCO</h2></div>
        <p>公式の購入直前画面で確認した12か月分の請求総額と、比較用に計算した月あたりの参考額を分けて表示します。</p>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="確認済み12か月TCO表を横スクロール">
        <table className="annual-tco-table">
          <thead><tr><th>サービス / プラン</th><th>12か月分の請求総額</th><th>月あたりの参考額</th><th>月払い価格</th><th>年払い差</th><th>確認日</th></tr></thead>
          <tbody>{rows.map((field) => <tr key={`${field.vendor_id}-${field.plan_id}-${field.field}`}>
            <th>{evidenceIdentity(field)}</th>
            <td><strong>{`${field.currency} ${field.value}`}</strong><small>公式画面の確認値</small></td>
            <td>{field.derived_monthly_value !== null ? `${field.currency} ${field.derived_monthly_value} ${field.derived_monthly_unit}` : "割り切れないため非表示"}</td>
            <td>{field.monthly_reference_value !== null ? `${field.currency} ${field.monthly_reference_value} ${field.monthly_reference_unit}` : "比較値なし"}</td>
            <td>{field.derived_annual_discount_percent !== null ? `月払い比で約${field.derived_annual_discount_percent}%割安` : "算出なし"}</td>
            <td>{field.observed_on}<small>次回 {field.next_review_on}</small></td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="annual-tco-note">
        {page.id === "P03" && unresolvedAnnualPrices.length > 0
          ? `Mangools Basicの12か月総額だけを確認できました。${unresolvedAnnualPrices.map(evidenceIdentity).join("、")}は年次の請求総額が未確認のため、横断価格順位を付けません。`
          : page.id === "P02"
            ? "確認済みの3プランは支払総額を比較できます。最低利用者数が未確認のプランは、適合順位から除外します。"
            : "今回の利用者数と月間利用量は確認済みの上限内です。上限超過時の追加課金は公式表示がなく、日本向け購入画面ではVATが0と表示されました。"}
      </p>
    </section>
  );
}

export function PilotArticle({
  page,
  children,
}: {
  page: PilotPage;
  children?: ReactNode;
}) {
  const draft = articleDraft(page);
  const contract = editorialContract(page);
  const presentation = editorialPresentation(page, contract);
  const articleApproved = contract?.article_review_status === "approved";
  const unknownFields = contract?.numeric_fields.filter(hasUnknownFact).length ?? 0;
  const sourceUrls = [...new Set(contract?.numeric_fields.flatMap((field) => field.source_url ? [field.source_url] : []) ?? [])];
  const observedDates = [...new Set(contract?.numeric_fields.map((field) => field.observed_on) ?? [])];
  const nextReviewDates = [...new Set(contract?.numeric_fields.map((field) => field.next_review_on) ?? [])];
  const reviewApprovedPages = pilotPages.filter(
    (candidate) => editorialContract(candidate)?.article_review_status === "approved",
  );
  const nextPages = nextToReadPages(page, {
    indexGo: process.env.SAAS_INDEX_GO === "GO",
    approvedArticleIdsValue: process.env.SAAS_INDEX_APPROVED_ARTICLES,
    articleReviewsCurrent: process.env.SAAS_ARTICLE_REVIEWS_CURRENT === "true",
    reviewApprovedArticleIds: new Set(reviewApprovedPages.map((candidate) => candidate.id)),
  });
  return (
    <main id="main-content" className="page-main">
      <AdvertisingDisclosure />
      <ArticleStructuredData page={page} contract={contract} />
      <header className="shell page-header">
        <p className="eyebrow">{page.id} / {articleApproved ? "確認済み" : "記事レビュー待ち"}{presentation.observedMonth ? ` / ${presentation.observedMonth}` : ""}</p>
        <h1>{presentation.title}</h1>
        <p>{presentation.description}</p>
      </header>

      <section className="shell page-section" aria-labelledby={`${page.id}-article-structure`}>
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">料金と判断材料</p>
            <h2 id={`${page.id}-article-structure`}>{page.question}</h2>
          </div>
          <p>確認できた事実と、まだ確認できない費用を分けて説明します。</p>
        </div>
        <p className="article-lead">{presentation.lead}</p>
        <p className="article-methodology-link">
          数値の確認方法と任意条件の試算は<Link href="/methodology#detailed-calculator">詳細計算モード</Link>にまとめています。
        </p>
        <div className="editorial-sections">
          {draft.sections.map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{renderContractTokens(section.body, contract)}</p>
            </article>
          ))}
        </div>
      </section>

      <AnnualTcoEvidence page={page} contract={contract} />

      <section className="shell page-section" aria-labelledby={`${page.id}-field-inputs`}>
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">数値の根拠</p>
            <h2 id={`${page.id}-field-inputs`}>{contract ? "確認値と未確認項目" : "確認待ちの項目"}</h2>
          </div>
          <p>
            {contract
              ? unknownFields > 0
                ? `未確認の項目が${unknownFields}件あります。その項目を使う総額や順位は表示しません。`
                : "12か月TCOに必要な項目は確認済みです。各数値の出典と確認日を下で確認できます。"
              : "公式ページ、確認日、次回確認日がそろうまで金額を表示しません。"}
          </p>
        </div>
        <div className="field-input-grid">
          {contract ? contract.numeric_fields.map((field, index) => {
            const definition = page.numericFields.find((candidate) => candidate.key === field.field);
            const isPrice = field.value_kind === "price";
            return (
              <article className={hasUnknownFact(field) ? "field-evidence-unknown" : undefined} key={`${evidenceIdentity(field)}-${field.field}-${index}`}>
                <p className="field-evidence-identity">{evidenceIdentity(field)}</p>
                <h2>{definition?.label ?? field.field}</h2>
                <dl>
                  <div><dt>確認値</dt><dd>{fieldValue(field)}</dd></div>
                  <div><dt>確認状態</dt><dd>{field.value_status === "known" ? "確認済み" : field.value_status === "not_applicable" ? "該当なし" : "未確認"}</dd></div>
                  {field.unknown_reason ? <div><dt>未確認・該当なしの理由</dt><dd>{field.unknown_reason}</dd></div> : null}
                  {isPrice ? <div><dt>通貨</dt><dd>{currencyValue(field)}</dd></div> : null}
                  {isPrice && field.currency_unknown_reason ? <div><dt>通貨を確認できない理由</dt><dd>{field.currency_unknown_reason}</dd></div> : null}
                  {isPrice ? <div><dt>請求周期</dt><dd>{billingPeriodValue(field.billing_period)}</dd></div> : null}
                  {isPrice ? <div><dt>税区分</dt><dd>{taxTreatmentValue(field.tax_treatment)}</dd></div> : null}
                  {field.scope_kind === "vendor_plan" ? <div><dt>画面の支払周期</dt><dd>{billingToggleValue(field.billing_toggle_state)}</dd></div> : null}
                  {field.scope_kind === "vendor_plan" ? <div><dt>価格表示の扱い</dt><dd>{saleBannerValue(field.sale_banner_state)}</dd></div> : null}
                  {isPrice ? <div><dt>価格を確認した場所</dt><dd>{observedPriceBasisValue(field.observed_price_basis)}</dd></div> : null}
                  {isPrice && field.derived_monthly_value !== null ? <div><dt>月あたりの参考額</dt><dd>{field.derived_monthly_value} {field.derived_monthly_unit}<br /><small>{field.derivation_method}</small></dd></div> : null}
                  {isPrice && field.monthly_reference_value != null ? <div><dt>月払い比較値</dt><dd>{field.monthly_reference_value} {field.monthly_reference_unit}</dd></div> : null}
                  {isPrice && field.derived_annual_discount_percent != null ? <div><dt>年払い差（派生値）</dt><dd>月払い比で約{field.derived_annual_discount_percent}%割安<br /><small>{field.discount_derivation_method}</small></dd></div> : null}
                  <div>
                    <dt>{field.scope_kind === "vendor_plan" ? "公式出典URL" : "試算条件の根拠"}</dt>
                    <dd className="field-evidence-source">{field.source_url ?? field.scenario_basis}</dd>
                  </div>
                  <div><dt>観測日</dt><dd>{field.observed_on}</dd></div>
                  <div><dt>次回確認日</dt><dd>{field.next_review_on}</dd></div>
                </dl>
                <small>確認記録: {field.field} / {field.review_status === "approved" ? "確認済み" : "レビュー待ち"}</small>
              </article>
            );
          }) : page.numericFields.map((field) => (
              <article key={field.key}>
                <h2>{field.label}</h2>
                <dl>
                  <div><dt>確認値</dt><dd>未入力</dd></div>
                  <div><dt>{pilotFieldScope(field) === "vendor_plan" ? "出典URL" : "試算条件の根拠"}</dt><dd>未入力</dd></div>
                  <div><dt>観測日</dt><dd>未入力</dd></div>
                  <div><dt>次回確認日</dt><dd>未入力</dd></div>
                </dl>
                <small>確認記録: {field.key} / 未入力</small>
              </article>
            ))}
        </div>
        {contract ? (
          <aside className="article-evidence-summary" aria-label="記事単位の出典・更新状態">
            <h2>記事単位の出典・更新状態</h2>
            <dl>
              <div>
                <dt>出典URL</dt>
                <dd className="article-evidence-sources">
                  {sourceUrls.length > 0 ? sourceUrls.map((url) => <span key={url}>{url}</span>) : "なし"}
                </dd>
              </div>
              <div><dt>観測日</dt><dd>{observedDates.join(", ")}</dd></div>
              <div><dt>次回確認日</dt><dd>{nextReviewDates.join(", ")}</dd></div>
              <div><dt>記事状態</dt><dd>{contract.article_review_status}</dd></div>
            </dl>
          </aside>
        ) : null}
      </section>

      {children}

      <section className="shell target-band" aria-labelledby="pilot-refresh-title">
        <div><p className="eyebrow">掲載情報の状態</p><h2 id="pilot-refresh-title">再確認と紹介リンク</h2></div>
        <dl>
          <div><dt>数値の確認記録</dt><dd>{contract ? "反映済み" : "未入力"}</dd></div>
          <div><dt>記事確認</dt><dd>{articleApproved ? "確認済み" : "レビュー待ち"}</dd></div>
          <div><dt>紹介リンク</dt><dd><span data-affiliate-cta-state="disabled">無効</span></dd></div>
        </dl>
        <p>
          {contract && unknownFields > 0
            ? `未確認の項目が${unknownFields}件あります。その項目を必要とする総額と価格順位は、確認できるまで表示しません。`
            : articleApproved
              ? "本文と12か月TCOは確認済みです。検索掲載、紹介リンク、価格の再確認日はそれぞれ別に管理します。"
              : "記事レビューが終わるまで検索掲載と紹介リンクを有効にしません。"}
        </p>
        <span
          className="cta-disabled"
          aria-describedby="article-pr-disclosure"
          data-affiliate-cta-placeholder="mangools"
        >
          紹介リンクは無効です
        </span>
      </section>

      {nextPages.length > 0 ? (
        <section className="shell page-section next-reading" aria-labelledby={`${page.id}-next-reading`}>
          <div className="section-heading">
            <p className="eyebrow">次に読む</p>
            <h2 id={`${page.id}-next-reading`}>関連する料金記事</h2>
          </div>
          <ul>
            {nextPages.map((candidate) => (
              <li key={candidate.id}>
                <Link href={`/pilot/${candidate.slug}`}>{candidate.title}</Link>
                <span>{candidate.readerOutcome}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <div data-next-reading-placeholder={page.id}>
          {reviewApprovedPages
            .filter((candidate) => candidate.id !== page.id)
            .map((candidate) => (
              <template
                key={candidate.id}
                data-next-reading-path={`/pilot/${candidate.slug}`}
                data-next-reading-title={candidate.title}
                data-next-reading-outcome={candidate.readerOutcome}
              />
            ))}
        </div>
      )}

      <section className="shell page-section">
        <Link className="text-link" href={publicPrelaunch ? "/" : "/pilot"}>
          {publicPrelaunch ? "SaaS TCO Labへ戻る" : "12本の記事一覧へ戻る"}
        </Link>
      </section>
    </main>
  );
}

/** Candidate-only servers layout. It contains no destination or active CTA. */
export function ServerArticleTemplate({
  article,
  calculatorContract,
  evidence,
  ctaPolicy,
}: {
  article: ServerArticleSlateEntry;
  calculatorContract: ServerZeroInputContract;
  evidence: ReactNode;
  ctaPolicy: ServerCtaPresentationPolicy;
}) {
  return (
    <main id="main-content" className="page-main" data-server-article-state={article.state}>
      <AdvertisingDisclosure />
      <header className="shell page-header">
        <p className="eyebrow">SERVERS / PRICE REVIEW IN PROGRESS</p>
        <h1>{article.titleTemplate}</h1>
        <p>{article.readerQuestion}</p>
      </header>
      <section className="shell page-section" data-server-template-step="calculator">
        <div data-server-template-step="result" aria-label="計算結果">
          <ServerZeroInputCalculator contract={calculatorContract} />
        </div>
      </section>
      <section
        className="shell target-band"
        data-server-template-step="cta_slot"
        data-server-cta-mode={ctaPolicy.mode}
        aria-label="サーバー紹介リンク枠"
      >
        {ctaPolicy.mode === "comparison" ? (
          <p>承認済みpartnerを同じ比較条件で確認する枠です。各リンクは個別CTA gateを通過するまで無効です。</p>
        ) : ctaPolicy.mode === "single" ? (
          <p>承認済みpartnerは1社です。単独CTAだけを扱い、比較表示にはしません。</p>
        ) : (
          <p>公開条件をすべて通過したpartnerがないためCTAは無効です。</p>
        )}
        <p>
          <span data-server-affiliate-cta-state="disabled">
            サーバー紹介リンクは無効です
          </span>
        </p>
        <div className="server-cta-options" aria-label="承認済みサーバー候補">
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="a8net-xserver-business"
          >
            XServerビジネス紹介リンクは無効です
          </span>
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="moshimo-conoha-wing"
          >
            ConoHa WING紹介リンクは無効です
          </span>
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="moshimo-lolipop-rental-server"
          >
            ロリポップ！紹介リンクは無効です
          </span>
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="moshimo-onamae-rental-server"
          >
            お名前.com レンタルサーバー紹介リンクは無効です
          </span>
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="moshimo-shin-rental-server"
          >
            シンレンタルサーバー紹介リンクは無効です
          </span>
          <span
            className="cta-disabled"
            aria-describedby="article-pr-disclosure"
            data-server-affiliate-cta-placeholder="valuecommerce-ablenet-shared-server"
          >
            ABLENET紹介リンクは無効です
          </span>
        </div>
      </section>
      <section className="shell page-section" data-server-template-step="evidence" aria-label="価格の根拠表">{evidence}</section>
    </main>
  );
}
