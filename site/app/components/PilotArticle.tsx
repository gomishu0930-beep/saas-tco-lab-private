import Link from "next/link";
import type { ReactNode } from "react";

import { pilotFieldScope, type PilotPage } from "../lib/pilot-pages";
import { articleDraft } from "../lib/article-drafts";
import type { EditorialContract } from "../lib/editorial-input-contract";
import { editorialContract, hasUnknownFact } from "../lib/editorial-contracts";
import { AdvertisingDisclosure } from "./AdvertisingDisclosure";
import { ArticleStructuredData } from "./ArticleStructuredData";

const publicPrelaunch = process.env.SAAS_RUNTIME_MODE === "production";

type ImportedField = EditorialContract["numeric_fields"][number];

function fieldValue(field: ImportedField): string {
  if (field.value_status === "unknown") return "unknown（不明）";
  if (field.value_status === "not_applicable") return "not_applicable（該当なし）";
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

const vendorDisplayNames: Readonly<Record<string, string>> = {
  mangools: "Mangools",
  "se-ranking": "SE Ranking",
  semrush: "Semrush",
};

const planDisplayNames: Readonly<Record<string, string>> = {
  "mangools/basic": "Basic",
  "mangools/premium": "Premium",
  "mangools/agency": "Agency",
  "se-ranking/core": "Core",
  "semrush/seo": "SEO",
};

function evidenceIdentity(field: ImportedField): string {
  if (field.scope_kind !== "vendor_plan") return "Human scenario";
  const vendorId = field.vendor_id ?? "unknown-vendor";
  const planId = field.plan_id ?? "unknown-plan";
  return `${vendorDisplayNames[vendorId] ?? vendorId} / ${planDisplayNames[`${vendorId}/${planId}`] ?? planId}`;
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
    case "not_present": return "toggleなし";
    default: return "unknown（不明）";
  }
}

function saleBannerValue(value: ImportedField["sale_banner_state"]): string {
  switch (value) {
    case "none": return "none（割引・promo表示なし）";
    case "annual_discount_permanent": return "年払い恒常割引（計算可）";
    case "time_limited_promo": return "期間限定promo（計算HOLD）";
    default: return "unknown（分類未確認・計算HOLD）";
  }
}

function observedPriceBasisValue(value: ImportedField["observed_price_basis"]): string {
  switch (value) {
    case "checkout_billed_total": return "checkout請求総額（一次観測値）";
    case "displayed_price": return "公式画面の表示価格（一次観測値）";
    case "human_scenario": return "Humanシナリオ入力";
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
        <div><p className="eyebrow">HUMAN-CONFIRMED TCO</p><h2 id={`${page.id}-annual-tco`}>Human確認済み12か月TCO</h2></div>
        <p>年次checkout請求総額を一次観測値とし、月額換算と年払い割引率はcontractの固定式による派生値として分離します。</p>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="Human確認済み12か月TCO表を横スクロール">
        <table className="annual-tco-table">
          <thead><tr><th>vendor / plan</th><th>12か月checkout総額</th><th>請求上の月額換算</th><th>月払い比較値</th><th>年払い差</th><th>観測</th></tr></thead>
          <tbody>{rows.map((field) => <tr key={`${field.vendor_id}-${field.plan_id}-${field.field}`}>
            <th>{evidenceIdentity(field)}</th>
            <td><strong>{`${field.currency} ${field.value}`}</strong><small>一次観測値</small></td>
            <td>{field.derived_monthly_value !== null ? `${field.currency} ${field.derived_monthly_value} ${field.derived_monthly_unit}` : "割り切れないため非表示"}</td>
            <td>{field.monthly_reference_value !== null ? `${field.currency} ${field.monthly_reference_value} ${field.monthly_reference_unit}` : "比較値なし"}</td>
            <td>{field.derived_annual_discount_percent !== null ? `月払い比で約${field.derived_annual_discount_percent}%割安` : "算出なし"}</td>
            <td>{field.observed_on}<small>次回 {field.next_review_on}</small></td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="annual-tco-note">
        {page.id === "P03" && unresolvedAnnualPrices.length > 0
          ? `Mangools Basicの12か月総額だけを確定しました。${unresolvedAnnualPrices.map(evidenceIdentity).join("、")}は年次checkout総額がunknownのため、横断価格順位を付けません。`
          : page.id === "P02"
            ? "3プランの支払総額は比較できます。最低seat数がunknownのplanは適合順位から除外します。"
            : "Basic 1ユーザー・月400 lookupのHuman scenarioはplan上限内です。従量超過課金は公式提示なし、Japan checkoutのVAT表示は0でした。"}
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
  const articleApproved = contract?.article_review_status === "approved";
  const unknownFields = contract?.numeric_fields.filter(hasUnknownFact).length ?? 0;
  const sourceUrls = [...new Set(contract?.numeric_fields.flatMap((field) => field.source_url ? [field.source_url] : []) ?? [])];
  const observedDates = [...new Set(contract?.numeric_fields.map((field) => field.observed_on) ?? [])];
  const nextReviewDates = [...new Set(contract?.numeric_fields.map((field) => field.next_review_on) ?? [])];
  return (
    <main id="main-content" className="page-main">
      <AdvertisingDisclosure />
      <ArticleStructuredData page={page} contract={contract} />
      <header className="shell page-header">
        <p className="eyebrow">{page.id} / {contract ? "HUMAN INPUT" : "EDITORIAL TEMPLATE"} / {articleApproved ? "APPROVED" : "DRAFT"} / {page.pageType}</p>
        <h1>{contract ? `${page.title}のHuman確認値を反映した${articleApproved ? "承認済み記事" : "公開前記事"}。` : `${page.title}を、実記事にするための公開前template。`}</h1>
        {contract ? (
          <p>
            問いは「{page.question}」。Humanが公式公開画面で確認した値、出典、観測日と、
            確定できないunknownを同時に表示します。記事は{articleApproved ? "Human承認済み" : "未承認"}です。
            検索公開とCTAは別ゲートで制御し、CTAは現在無効です。
          </p>
        ) : (
          <p>
            問いは「{page.question}」。このURLは記事構造の合成fixtureであり、
            実在サービスの値・評価・提携リンクはまだ含みません。数値fieldはOperator入力contractとだけ
            接続し、読後には「{page.readerOutcome}」状態を目指します。
          </p>
        )}
      </header>

      <section className="shell page-section" aria-labelledby={`${page.id}-article-structure`}>
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">ARTICLE BODY</p>
            <h2 id={`${page.id}-article-structure`}>{articleApproved ? "承認済み6章本文" : "6章の本文下書き"}</h2>
          </div>
          <p>
            intentは{page.intent}。analyst、editor、skeptical buyerの3視点で反証し、
            Human入力contractを満たす数値だけをclaim候補にします。
          </p>
        </div>
        <div className="editorial-sections">
          {draft.sections.map((section, index) => (
            <article key={section.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </article>
          ))}
        </div>
      </section>

      <AnnualTcoEvidence page={page} contract={contract} />

      <section className="shell page-section" aria-labelledby={`${page.id}-field-inputs`}>
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">{contract ? "IMPORTED FIELD EVIDENCE" : "HUMAN FIELD INPUT"}</p>
            <h2 id={`${page.id}-field-inputs`}>{contract ? "実値とunknownを同じ行で確認" : "数値ごとに根拠経路を固定"}</h2>
          </div>
          <p>
            {contract
              ? unknownFields > 0
                ? `Python正本で再検証したcontractを表示中。unknownを含むfieldは${unknownFields}件あり、そのfieldを使う総額・順位claimから除外します。`
                : "Python正本で再検証したcontractを表示中。TCOに必要なfieldは確認済みで、Human記事reviewへ進めます。"
              : "vendor値は値・公式URL・観測日・次回確認日、Humanシナリオは値・入力根拠・観測日・次回確認日を必須にします。"}
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
                  <div><dt>Human入力値</dt><dd>{fieldValue(field)}</dd></div>
                  <div><dt>値状態</dt><dd>{field.value_status}</dd></div>
                  {field.unknown_reason ? <div><dt>unknown理由</dt><dd>{field.unknown_reason}</dd></div> : null}
                  {isPrice ? <div><dt>通貨</dt><dd>{currencyValue(field)}</dd></div> : null}
                  {isPrice && field.currency_unknown_reason ? <div><dt>通貨unknown理由</dt><dd>{field.currency_unknown_reason}</dd></div> : null}
                  {isPrice ? <div><dt>請求周期</dt><dd>{billingPeriodValue(field.billing_period)}</dd></div> : null}
                  {isPrice ? <div><dt>税区分</dt><dd>{taxTreatmentValue(field.tax_treatment)}</dd></div> : null}
                  {field.scope_kind === "vendor_plan" ? <div><dt>billing toggle</dt><dd>{billingToggleValue(field.billing_toggle_state)}</dd></div> : null}
                  {field.scope_kind === "vendor_plan" ? <div><dt>価格表示の分類</dt><dd>{saleBannerValue(field.sale_banner_state)}</dd></div> : null}
                  {isPrice ? <div><dt>価格の一次観測</dt><dd>{observedPriceBasisValue(field.observed_price_basis)}</dd></div> : null}
                  {isPrice && field.derived_monthly_value !== null ? <div><dt>月額換算（派生値）</dt><dd>{field.derived_monthly_value} {field.derived_monthly_unit}<br /><small>{field.derivation_method}</small></dd></div> : null}
                  {isPrice && field.monthly_reference_value != null ? <div><dt>月払い比較値</dt><dd>{field.monthly_reference_value} {field.monthly_reference_unit}</dd></div> : null}
                  {isPrice && field.derived_annual_discount_percent != null ? <div><dt>年払い差（派生値）</dt><dd>月払い比で約{field.derived_annual_discount_percent}%割安<br /><small>{field.discount_derivation_method}</small></dd></div> : null}
                  <div>
                    <dt>{field.scope_kind === "vendor_plan" ? "公式出典URL" : "scenario根拠"}</dt>
                    <dd className="field-evidence-source">{field.source_url ?? field.scenario_basis}</dd>
                  </div>
                  <div><dt>観測日</dt><dd>{field.observed_on}</dd></div>
                  <div><dt>次回確認日</dt><dd>{field.next_review_on}</dd></div>
                </dl>
                <small>contract: {field.field} / {field.value_kind} / {field.scope_kind} / {field.review_status}</small>
              </article>
            );
          }) : page.numericFields.map((field) => (
              <article key={field.key}>
                <h2>{field.label}</h2>
                <dl>
                  <div><dt>Human入力値</dt><dd>未入力</dd></div>
                  <div><dt>{pilotFieldScope(field) === "vendor_plan" ? "出典URL" : "scenario根拠"}</dt><dd>未入力</dd></div>
                  <div><dt>観測日</dt><dd>未入力</dd></div>
                  <div><dt>次回確認日</dt><dd>未入力</dd></div>
                </dl>
                <small>contract: {field.key} / {field.valueKind} / {pilotFieldScope(field)}</small>
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
        <div><p className="eyebrow">REFRESH TRIGGER</p><h2 id="pilot-refresh-title">更新と停止</h2></div>
        <dl>
          <div><dt>Human入力</dt><dd>{contract ? "contract取込済み" : "未投入"}</dd></div>
          <div><dt>記事review</dt><dd>{articleApproved ? "承認済み・公開候補" : "未承認"}</dd></div>
          <div><dt>CTA</dt><dd>DISABLED</dd></div>
        </dl>
        <p>
          {contract && unknownFields > 0
            ? `unknownを含むfield ${unknownFields}件を保持中です。承認scopeどおり該当TCO・価格順位だけをSTOPし、unknownを明示した本文は公開候補として保持します。`
            : articleApproved
              ? "本文・TCOはHuman承認済みです。index GO、CTA GO、期限確認は別gateとして維持します。"
              : "自動取得権とeditorial pathを混同せず、期限切れ、推測値、未承認記事、CTA不一致でSTOPします。"}
        </p>
        <span className="cta-disabled" aria-describedby="article-pr-disclosure">CTA DISABLED</span>
      </section>

      <section className="shell page-section">
        <Link className="text-link" href={publicPrelaunch ? "/" : "/pilot/"}>
          {publicPrelaunch ? "SaaS TCO Labへ戻る" : "12本の記事template一覧へ戻る"}
        </Link>
      </section>
    </main>
  );
}
