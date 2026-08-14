import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "学習と施策",
  description: "証拠を学習・施策・編集・収益導線へ安全に接続する公開前の運用構造。",
};

const capabilities = [
  [
    "01",
    "共通セマンティック層",
    "property・content・query cluster・campaign・CTA・cohortをhash IDで接続し、modeledとobservedを分離します。",
  ],
  [
    "02",
    "5領域Gold Set",
    "field精度、施策判断、brief、claim引用、CTA変換をHuman label付きの期限ある評価集合にします。",
  ],
  [
    "03",
    "3案の施策メモ",
    "保守・均衡・攻めの3案を作り、権利・法務・securityをEVIの外側に置いて先に停止判定します。",
  ],
  [
    "04",
    "3視点の編集監査",
    "analyst・editor・skeptical buyerの3稿とclaim-evidence mapを照合し、期限切れならHuman review前にSTOPします。",
  ],
  [
    "05",
    "因果付き収益feedback",
    "検索表示からpaidまでを親eventで接続し、confirmed EPC・qualified session単価・純利益をobservedだけで算出します。",
  ],
  [
    "06",
    "CTAフェイルクローズ",
    "提携承認、field権利、link、遷移先、広告表示、期限が完全一致した時だけenabledになります。",
  ],
] as const;

const kpis = [
  ["A", "Confirmed EPC", "未定義", "実送客0", "pendingではなくconfirmed / paidの最新状態だけを採用"],
  ["B", "純営業利益", "未観測", "外部入力待ち", "settled revenueから運用TCOを差し引いて月20万円を判定"],
  ["C", "自動化率", "fixtureのみ", "30日未実施", "routine taskの80%以上と人手720分以下を実測"],
  ["D", "Job成功率", "fixture合格", "実運用前", "30日で99%以上、重大誤記0を維持"],
  ["E", "CTA状態", "DISABLED", "正しいSTOP", "提携・権利・destination・disclosureの全一致が必要"],
] as const;

export default function LearningPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">LOCAL GROWTH CONTROL PLANE</p>
        <h1>学習・施策・文章・収益導線を、同じ証拠鎖でつなぐ。</h1>
        <p>
          ここにあるのは外部AIや広告管理画面ではなく、ローカルで再実行できる契約と停止条件です。
          現在値は合成fixtureまたは未観測で、公開・送客・外部書込みの権限を持ちません。
        </p>
      </header>

      <section className="shell page-section" aria-labelledby="capability-title">
        <div className="section-heading split-heading">
          <div>
            <p className="eyebrow">IMPLEMENTED CAPABILITIES</p>
            <h2 id="capability-title">6つのローカル制御</h2>
          </div>
          <p>入力はsanitize済み集計値とhashだけ。raw prompt、本文、URL、tracking ID、credentialは契約外です。</p>
        </div>
        <div className="policy-cards">
          {capabilities.map(([number, title, description]) => (
            <article key={number}>
              <span>{number}</span>
              <h2>{title}</h2>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="shell readiness-board" aria-labelledby="growth-kpi-title">
        <div className="readiness-summary">
          <div><p>現在の収益導線判定</p><strong>STOP</strong></div>
          <p>仕組みは実装済みですが、実データ・提携・権利が0のためCTAは正しく無効です。</p>
        </div>
        <h2 id="growth-kpi-title" className="sr-only">学習と収益のKPI</h2>
        <ol>
          {kpis.map(([letter, name, measure, state, rule]) => (
            <li key={letter}>
              <span className="gate-letter">{letter}</span>
              <div className="gate-name"><small>METRIC {letter}</small><h2>{name}</h2></div>
              <div><small>現在値</small><strong>{measure}</strong></div>
              <div><small>状態</small><strong>{state}</strong></div>
              <p>{rule}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="shell target-band" aria-labelledby="growth-target-title">
        <div><p className="eyebrow">MONTHLY TARGET</p><h2 id="growth-target-title">月20万円への判定式</h2></div>
        <dl>
          <div><dt>Confirmed EPC</dt><dd>60円以上</dd></div>
          <div><dt>Valid outbound</dt><dd>3,334 / 月</dd></div>
          <div><dt>Human share</dt><dd>20%以下</dd></div>
        </dl>
        <p>目標値であり実績ではありません。observed evidenceが揃うまで収益達成とは表示しません。</p>
      </section>
      <section className="shell page-section">
        <Link className="button button-secondary" href="/pilot">12本の合成noindex pilotを見る</Link>
      </section>
    </main>
  );
}
