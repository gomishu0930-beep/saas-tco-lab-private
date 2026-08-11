import Link from "next/link";

import { ComparisonTable } from "./components/ComparisonTable";
import { StatusStrip } from "./components/StatusStrip";
import { syntheticComparison } from "./lib/synthetic-data";

const productionRuntime = process.env.SAAS_RUNTIME_MODE === "production";

function PublicEditorialHome() {
  const samples = [
    {
      href: "/pilot/pricing-calculator/",
      number: "01",
      title: "12か月TCO",
      body: "Human確認済みの年次請求総額から、12か月の支払額と未確認条件を分けて示します。",
    },
    {
      href: "/pilot/plan-comparison/",
      number: "02",
      title: "プラン比較",
      body: "Basic・Premium・Agencyの年次請求総額を、同じ通貨・税表示の範囲で比較します。",
    },
    {
      href: "/pilot/evidence-method/",
      number: "03",
      title: "根拠の検証",
      body: "価格や上限をfield単位で管理し、出所・権利・期限が欠けたclaimを公開しません。",
    },
  ] as const;

  return (
    <main id="main-content">
      <section className="hero shell" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">EVIDENCE-FIRST SAAS EDITORIAL / JAPAN</p>
          <h1 id="hero-title">
            SaaS選定を、<br />
            <span>月額の先まで。</span>
          </h1>
          <p className="hero-lead">
            SaaS TCO Labは、日本の事業者向けに料金、契約条件、利用上限、追加費用をそろえ、
            12か月TCOと適合条件を検証する独立メディアです。
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" href="/methodology/">
              算定方法を見る <span aria-hidden="true">→</span>
            </Link>
            <Link className="text-link" href="/pilot/pricing-calculator/">
              公開中の料金記事を見る
            </Link>
          </div>
        </div>
        <aside className="hero-proof" aria-label="公開運用の状態">
          <div className="proof-heading">
            <span className="signal" aria-hidden="true" />
            PUBLIC EDITORIAL
          </div>
          <dl className="proof-grid">
            <div><dt>対象</dt><dd>JP / ja</dd></div>
            <div><dt>算定</dt><dd>12か月TCO</dd></div>
            <div><dt>公開記事</dt><dd>10本</dd></div>
            <div><dt>広告導線</dt><dd>Mangools</dd></div>
          </dl>
          <p className="proof-note">
            Human確認済みの数値だけを公開し、未確認項目は推測せず明示します。広告リンクは承認済み記事だけで有効です。
          </p>
        </aside>
      </section>

      <section className="process-section" aria-labelledby="public-process-title">
        <div className="shell">
          <div className="section-heading split-heading inverse">
            <div>
              <p className="eyebrow">EDITORIAL PROMISE</p>
              <h2 id="public-process-title">根拠がない比較は、公開しない。</h2>
            </div>
            <p>報酬条件ではなく、同じscenarioと期限内の一次情報で比較します。</p>
          </div>
          <ol className="process-grid">
            <li><span>01</span><h3>条件を固定</h3><p>地域、税、通貨、契約期間、seat数、利用量を先にそろえます。</p></li>
            <li><span>02</span><h3>権利を確認</h3><p>取得・保存・派生・引用・公開の許可をfield単位で確認します。</p></li>
            <li><span>03</span><h3>TCOを算定</h3><p>月額だけでなく、addon、overage、移行、人手を12か月で扱います。</p></li>
            <li><span>04</span><h3>期限で停止</h3><p>data・rights・affiliateの期限切れで数値とCTAを非表示にします。</p></li>
          </ol>
        </div>
      </section>

      <section className="shell section" aria-labelledby="sample-title">
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">EDITORIAL SAMPLES</p>
            <h2 id="sample-title">公開中の記事</h2>
          </div>
          <p>確認済み実額、出典、観測日、次回確認日をそろえた記事だけをご案内します。</p>
        </div>
        <div className="policy-cards">
          {samples.map((sample) => (
            <article key={sample.href}>
              <span>{sample.number}</span>
              <h2><Link href={sample.href}>{sample.title}</Link></h2>
              <p>{sample.body}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

export default function Home() {
  if (productionRuntime) return <PublicEditorialHome />;

  return (
    <>
      <StatusStrip />
      <main id="main-content">
        <section className="hero shell" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">EVIDENCE-FIRST / PRE-PUBLIC MVP</p>
            <h1 id="hero-title">
              SaaS選定を、<br />
              <span>価格表の先まで。</span>
            </h1>
            <p className="hero-lead">
              表面的な月額ではなく、契約条件・利用量・追加費用をそろえた12か月TCOで比較します。
              公開前のため、現在は合成データだけを表示しています。
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/comparison/">
                比較結果を見る <span aria-hidden="true">→</span>
              </Link>
              <Link className="text-link" href="/methodology/">
                算定方法を確認
              </Link>
            </div>
          </div>
          <aside className="hero-proof" aria-label="公開前ゲートの状態">
            <div className="proof-heading">
              <span className="signal" aria-hidden="true" />
              LOCAL PREFLIGHT
            </div>
            <dl className="proof-grid">
              <div>
                <dt>公開状態</dt>
                <dd>NOINDEX</dd>
              </div>
              <div>
                <dt>実データ</dt>
                <dd>未投入</dd>
              </div>
              <div>
                <dt>CTA</dt>
                <dd>無効</dd>
              </div>
              <div>
                <dt>計算元</dt>
                <dd>Python</dd>
              </div>
            </dl>
            <p className="proof-note">
              権利・提携・需要・運用の各ゲートを通過するまで、公開と送客は技術的に停止します。
            </p>
          </aside>
        </section>

        <section className="shell section" aria-labelledby="decision-title">
          <div className="section-heading split-heading">
            <div>
              <p className="eyebrow">DECISION SNAPSHOT</p>
              <h2 id="decision-title">判断に必要な条件を、1枚に。</h2>
            </div>
            <p>
              すべて合成fixtureです。実在サービスの価格・評価・広告リンクは含みません。
            </p>
          </div>
          <ComparisonTable data={syntheticComparison} compact />
          <div className="section-action">
            <Link className="button button-secondary" href="/comparison/">
              条件と根拠をすべて表示 <span aria-hidden="true">→</span>
            </Link>
          </div>
        </section>

        <section className="process-section" aria-labelledby="process-title">
          <div className="shell">
            <div className="section-heading split-heading inverse">
              <div>
                <p className="eyebrow">WHY THIS EXISTS</p>
                <h2 id="process-title">安い、ではなく。合う、を証明する。</h2>
              </div>
              <p>
                情報の出所と期限を隠さず、比較できない状態もそのまま表示します。
              </p>
            </div>
            <ol className="process-grid">
              <li>
                <span>01</span>
                <h3>条件を固定</h3>
                <p>地域、税、通貨、契約期間、seat数、利用量を先にそろえます。</p>
              </li>
              <li>
                <span>02</span>
                <h3>権利を確認</h3>
                <p>取得・派生・引用・公開の許可が現在も有効かfield単位で検査します。</p>
              </li>
              <li>
                <span>03</span>
                <h3>TCOを算定</h3>
                <p>canonical Python実装だけが金額を計算し、画面は結果を表示するだけです。</p>
              </li>
              <li>
                <span>04</span>
                <h3>期限で停止</h3>
                <p>data・rights・affiliateのいずれかが切れれば、表示とCTAを自動停止します。</p>
              </li>
            </ol>
          </div>
        </section>
      </main>
    </>
  );
}
