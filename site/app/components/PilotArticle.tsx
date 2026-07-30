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

function evidenceIdentity(field: ImportedField): string {
  return field.scope_kind === "vendor_plan"
    ? `${field.vendor_id} / ${field.plan_id}`
    : "Human scenario";
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
  const unknownFields = contract?.numeric_fields.filter(hasUnknownFact).length ?? 0;
  return (
    <main id="main-content" className="page-main">
      <AdvertisingDisclosure />
      <ArticleStructuredData page={page} contract={contract} />
      <header className="shell page-header">
        <p className="eyebrow">{page.id} / {contract ? "HUMAN INPUT" : "EDITORIAL TEMPLATE"} / DRAFT / {page.pageType}</p>
        <h1>{contract ? `${page.title}のHuman確認値を反映した公開前記事。` : `${page.title}を、実記事にするための公開前template。`}</h1>
        {contract ? (
          <p>
            問いは「{page.question}」。Humanが公式公開画面で確認した値、出典、観測日と、
            確定できないunknownを同時に表示します。記事は未承認、noindex、CTA無効のままです。
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
            <h2 id={`${page.id}-article-structure`}>6章の本文下書き</h2>
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

      <section className="shell page-section" aria-labelledby={`${page.id}-field-inputs`}>
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">{contract ? "IMPORTED FIELD EVIDENCE" : "HUMAN FIELD INPUT"}</p>
            <h2 id={`${page.id}-field-inputs`}>{contract ? "実値とunknownを同じ行で確認" : "数値ごとに根拠経路を固定"}</h2>
          </div>
          <p>
            {contract
              ? `Python正本で再検証したcontractを表示中。unknownを含むfieldは${unknownFields}件あり、総額・順位計算には使いません。`
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
                  {isPrice ? <div><dt>請求周期</dt><dd>{field.billing_period}</dd></div> : null}
                  {isPrice ? <div><dt>税区分</dt><dd>{field.tax_treatment}</dd></div> : null}
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
      </section>

      {children}

      <section className="shell target-band" aria-labelledby="pilot-refresh-title">
        <div><p className="eyebrow">REFRESH TRIGGER</p><h2 id="pilot-refresh-title">更新と停止</h2></div>
        <dl>
          <div><dt>Human入力</dt><dd>{contract ? "contract取込済み" : "未投入"}</dd></div>
          <div><dt>記事review</dt><dd>未承認</dd></div>
          <div><dt>CTA</dt><dd>DISABLED</dd></div>
        </dl>
        <p>
          {contract && unknownFields > 0
            ? `unknownを含むfield ${unknownFields}件を保持中です。TCO・価格順位・記事承認はSTOPします。`
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
