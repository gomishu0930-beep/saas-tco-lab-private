import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "公開準備",
  description: "権利・提携・需要・運用の段階ゲートと現在地。",
};

const gates = [
  ["A", "権利", "0 / 3社", "外部回答待ち", "公開fieldの取得・派生・引用・公開・履歴権利を確定"],
  ["B", "提携", "0 / 3社", "申請前", "対象site、CTA、商標、cookie、報酬、失効条件を確定"],
  ["C", "需要", "未実証", "入力待ち", "重複除去済みJP/ja clusterから保守ケースを実測"],
  ["D", "運用", "fixture合格", "30日未実施", "job成功率99%、例外24件以下、人手720分以下を実証"],
] as const;

export default function ReadinessPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">GO / STOP CONTROL</p>
        <h1>公開できることと、稼げることを分けて検証する。</h1>
        <p>
          画面が完成しても公開はしません。権利・3社提携・需要・30日運用の4ゲートを通過して、
          HumanがGOを署名した時だけ次の段階へ進みます。
        </p>
      </header>
      <section className="shell readiness-board" aria-labelledby="gate-title">
        <div className="readiness-summary">
          <div><p>現在の総合判定</p><strong>STOP</strong></div>
          <p>これは失敗ではなく、外部証拠が未取得のための正しいフェイルクローズ状態です。</p>
        </div>
        <h2 id="gate-title" className="sr-only">公開準備ゲート</h2>
        <ol>
          {gates.map(([letter, name, measure, state, exit]) => (
            <li key={letter}>
              <span className="gate-letter">{letter}</span>
              <div className="gate-name"><small>GATE {letter}</small><h2>{name}</h2></div>
              <div><small>現在値</small><strong>{measure}</strong></div>
              <div><small>状態</small><strong>{state}</strong></div>
              <p>{exit}</p>
            </li>
          ))}
        </ol>
      </section>
      <section className="shell target-band" aria-labelledby="target-title">
        <div><p className="eyebrow">ECONOMIC TARGET</p><h2 id="target-title">月20万円の必要条件</h2></div>
        <dl>
          <div><dt>目標EPC</dt><dd>60円以上</dd></div>
          <div><dt>必要送客</dt><dd>3,334 clicks / 月</dd></div>
          <div><dt>必要qualified sessions</dt><dd>約22,227–27,783 / 月</dd></div>
        </dl>
        <p>いずれも目標式であり、実績値ではありません。</p>
      </section>
    </main>
  );
}
