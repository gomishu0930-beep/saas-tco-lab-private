import Link from "next/link";

import { ComparisonTable } from "./components/ComparisonTable";
import { StatusStrip } from "./components/StatusStrip";
import { syntheticComparison } from "./lib/synthetic-data";

const productionRuntime = process.env.SAAS_RUNTIME_MODE === "production";

function PublicEditorialHome() {
  const samples = [
    {
      href: "/servers/business-server-pricing",
      number: "01",
      title: "法人向けサーバーの契約時総額",
      body: "初期費用と12か月分の請求額を分け、更新料や特典の未確認条件も同じ画面で確認できます。",
      category: "サーバー",
    },
    {
      href: "/pilot/pricing-calculator",
      number: "02",
      title: "Mangoolsの12か月TCO",
      body: "人が公式画面で確認した年次請求総額から、12か月の支払額と未確認条件を分けて示します。",
      category: "SEOツール",
    },
    {
      href: "/pilot/plan-comparison",
      number: "03",
      title: "Mangoolsのプラン比較",
      body: "Basic・Premium・Agencyの年次請求総額を、同じ通貨・税表示の範囲で比較します。",
      category: "SEOツール",
    },
    {
      href: "/pilot/annual-vs-monthly",
      number: "04",
      title: "年払いと月払い",
      body: "年払いの請求総額と月払いを同じ期間へそろえ、途中解約の未確認条件も分離します。",
      category: "SEOツール",
    },
    {
      href: "/pilot/usage-overage",
      number: "05",
      title: "利用上限と超過",
      body: "検索回数などの利用上限と、上限到達後の扱いを購入前に確認できます。",
      category: "SEOツール",
    },
    {
      href: "/pilot/migration-cost",
      number: "06",
      title: "移行にかかる人手費用",
      body: "実作業時間から算定した人手費用と、公式の移行支援費で未確認の部分を分けます。",
      category: "SEOツール",
    },
  ] as const;
  const moreTopics = [
    { href: "/pilot/alternatives", title: "他社SEOツールとの比較", note: "未確認の他社価格を混ぜずに比較" },
    { href: "/pilot/small-team-fit", title: "小規模チームの費用", note: "人数と運用条件を分けて確認" },
    { href: "/pilot/enterprise-fit", title: "Agencyプランの料金と上限", note: "追加利用者と利用上限を確認" },
    { href: "/pilot/addon-cost", title: "追加機能の費用", note: "基本料金に含まれない費用を分離" },
    { href: "/pilot/japan-tax", title: "通貨と税の表示", note: "換算せず公式画面の表示を確認" },
    { href: "/pilot/evidence-method", title: "料金根拠の確認方法", note: "出典・観測日・再確認日を検証" },
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
            12か月TCOと未確認条件を、公式サイトへ進む前に整理する独立メディアです。
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" href="/servers/business-server-pricing">
              サーバー契約時総額を見る <span aria-hidden="true">→</span>
            </Link>
            <Link className="button button-secondary" href="/pilot/pricing-calculator">
              SEOツール料金を見る
            </Link>
          </div>
          <p className="hero-helper"><Link href="/methodology">算定方法と情報の確認基準</Link></p>
        </div>
        <aside className="hero-proof" aria-label="公開運用の状態">
          <div className="proof-heading">
            <span className="signal" aria-hidden="true" />
            PUBLIC EDITORIAL
          </div>
          <dl className="proof-grid">
            <div><dt>対象</dt><dd>JP / ja</dd></div>
            <div><dt>算定</dt><dd>12か月TCO</dd></div>
            <div><dt>公開記事</dt><dd>{samples.length + moreTopics.length}本</dd></div>
            <div><dt>対象カテゴリ</dt><dd>2カテゴリ</dd></div>
          </dl>
          <p className="proof-note">
            公式画面を人が確認した数値だけを公開します。未確認項目は推測せず、紹介リンクより先に広告利用を表示します。
          </p>
        </aside>
      </section>

      <section className="shell decision-entry" aria-labelledby="decision-entry-title">
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">START BY PURPOSE</p>
            <h2 id="decision-entry-title">いま確認したい費用から選ぶ</h2>
          </div>
          <p>結果と未確認条件を先に見て、納得できた場合だけ公式サイトへ進めます。</p>
        </div>
        <div className="decision-entry-grid">
          <article>
            <p className="eyebrow">サーバー</p>
            <h3>初期費用を含む契約時総額</h3>
            <p>12・24・36か月の期間を切り替え、確認できない更新料や特典は順位から外します。</p>
            <Link className="button button-primary" href="/servers/business-server-pricing">確認済み総額を見る <span aria-hidden="true">→</span></Link>
          </article>
          <article>
            <p className="eyebrow">SEOツール</p>
            <h3>年払い・月払い・利用上限</h3>
            <p>確認済みの年次請求総額を起点に、プラン差、超過、税、移行費用を確認します。</p>
            <Link className="button button-secondary" href="/pilot/pricing-calculator">12か月TCOを見る <span aria-hidden="true">→</span></Link>
          </article>
        </div>
        <ul className="trust-points" aria-label="掲載情報の確認方針">
          <li>広告表示が紹介リンクより先</li>
          <li>出典・観測日・次回確認日を表示</li>
          <li>未確認値は総額や順位から除外</li>
        </ul>
      </section>

      <section className="process-section" aria-labelledby="public-process-title">
        <div className="shell">
          <div className="section-heading split-heading inverse">
            <div>
              <p className="eyebrow">EDITORIAL PROMISE</p>
              <h2 id="public-process-title">根拠がない比較は、公開しない。</h2>
            </div>
            <p>広告報酬ではなく、同じ利用条件と期限内の一次情報で比較します。</p>
          </div>
          <ol className="process-grid">
            <li><span>01</span><h3>比較条件を統一</h3><p>地域、税、通貨、契約期間、利用者数、利用量を先にそろえます。</p></li>
            <li><span>02</span><h3>公式情報を確認</h3><p>料金ページや購入直前画面を人が確認し、出典と日付を記録します。</p></li>
            <li><span>03</span><h3>総額を計算</h3><p>月額だけでなく、追加料金、移行、人手を含めて判断します。</p></li>
            <li><span>04</span><h3>古い情報を停止</h3><p>再確認期限を過ぎた数値や紹介リンクは、そのまま掲載し続けません。</p></li>
          </ol>
        </div>
      </section>

      <section className="shell section" aria-labelledby="sample-title">
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">EDITORIAL SAMPLES</p>
            <h2 id="sample-title">公開中の判断材料</h2>
          </div>
          <p>確認済み実額、出典、観測日、次回確認日をそろえた記事だけをご案内します。</p>
        </div>
        <div className="policy-cards">
          {samples.map((sample) => (
            <article key={sample.href}>
              <span>{sample.number} / {sample.category}</span>
              <h2><Link href={sample.href}>{sample.title}</Link></h2>
              <p>{sample.body}</p>
            </article>
          ))}
        </div>
        <div className="more-topics" aria-labelledby="more-topics-title">
          <h3 id="more-topics-title">ほかの判断テーマ</h3>
          <ul>
            {moreTopics.map((topic) => (
              <li key={topic.href}>
                <Link href={topic.href}>{topic.title}</Link>
                <span>{topic.note}</span>
              </li>
            ))}
          </ul>
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
              <Link className="button button-primary" href="/comparison">
                比較結果を見る <span aria-hidden="true">→</span>
              </Link>
              <Link className="text-link" href="/methodology">
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
            <Link className="button button-secondary" href="/comparison">
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
