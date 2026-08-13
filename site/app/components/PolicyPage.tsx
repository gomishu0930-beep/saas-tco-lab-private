import Link from "next/link";

export type PolicySection = {
  title: string;
  paragraphs: readonly string[];
};

export function PolicyPage({
  eyebrow,
  title,
  lead,
  sections,
}: {
  eyebrow: string;
  title: string;
  lead: string;
  sections: readonly PolicySection[];
}) {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header narrow">
        <p className="eyebrow">{eyebrow} / NOINDEX REVIEW</p>
        <h1>{title}</h1>
        <p>{lead}</p>
      </header>
      <section className="shell page-section policy-page-grid" aria-label={title}>
        {sections.map((section, index) => (
          <article key={section.title}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <h2>{section.title}</h2>
              {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            </div>
          </article>
        ))}
      </section>
      <section className="shell page-section policy-page-links" aria-label="関連情報">
        <Link className="text-link" href="/operator-information">運営者情報</Link>
        <Link className="text-link" href="/privacy">プライバシーポリシー</Link>
        <Link className="text-link" href="/contact">お問い合わせ</Link>
        <Link className="text-link" href="/advertising-policy">広告掲載ポリシー</Link>
      </section>
    </main>
  );
}
