import Link from "next/link";

import { ComparisonTable } from "./components/ComparisonTable";
import { StatusStrip } from "./components/StatusStrip";
import { syntheticComparison } from "./lib/synthetic-data";

export default function Home() {
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
