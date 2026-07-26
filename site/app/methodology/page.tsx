import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "算定方法",
  description: "比較条件、権利検査、TCO算定、失効制御の方法。",
};

const steps = [
  ["入力を固定", "region・tax・currency・billing・commitment・seat・利用量をscenarioとして凍結します。"],
  ["根拠をfield化", "価格、請求周期、上限、追加費用ごとに取得元、取得時刻、許可範囲、期限を結びます。"],
  ["Pythonで算定", "月次・年次、per-seat、usage/overage、税、addonをcanonical実装で計算します。UIは再計算しません。"],
  ["適合を説明", "必要条件を満たすかを、結論だけでなく理由と一緒に残します。"],
  ["配信時に再検査", "data・rights・affiliateの最短期限をrequestごとに検査し、期限到達時は数値とCTAを隠します。"],
] as const;

export default function MethodologyPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header narrow">
        <p className="eyebrow">METHODOLOGY</p>
        <h1>比較の作り方を、結果より先に公開する。</h1>
        <p>
          安さの順位を作ることが目的ではありません。同じ利用条件で総費用と適合性を再現でき、
          根拠が失効したときに止められることを優先します。
        </p>
      </header>
      <section className="shell methodology-layout" aria-labelledby="method-steps">
        <h2 id="method-steps" className="sr-only">算定手順</h2>
        <ol className="method-steps">
          {steps.map(([title, body], index) => (
            <li key={title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><h3>{title}</h3><p>{body}</p></div>
            </li>
          ))}
        </ol>
        <aside className="method-note">
          <p className="eyebrow">FAIL-CLOSED</p>
          <h2>分からない値は、埋めない。</h2>
          <p>
            出所が競合する値、権利が未確認の値、期限切れの値は推測で補完せず、比較不能として隔離します。
          </p>
          <dl>
            <div><dt>価格計算</dt><dd>Pythonのみ</dd></div>
            <div><dt>画面計算</dt><dd>禁止</dd></div>
            <div><dt>期限検査</dt><dd>requestごと</dd></div>
            <div><dt>未確認値</dt><dd>非表示</dd></div>
          </dl>
        </aside>
      </section>
    </main>
  );
}
