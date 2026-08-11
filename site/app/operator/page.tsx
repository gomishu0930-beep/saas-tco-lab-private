import type { Metadata } from "next";
import Link from "next/link";

import { OperatorInputForm } from "../components/OperatorInputForm";

export const metadata: Metadata = {
  title: "あなたの操作",
  description: "記事実値の入力、GO/HOLD返信、月次確認を一画面へ集約したローカル運用UI。",
};

const remainingHumanWork = [
  {
    id: "H1",
    timing: "完了済み",
    title: "domain移行状態を維持",
    minutes: "通常は0分",
    status: "domain・SSL・GSC・GA4・redirect・Impact完了",
    why: "通常は操作不要です。domain、SSL、GSC、GA4、redirect、Impactの異常通知が出た場合だけrunbookを開きます。",
    steps: ["通常は何もしない", "異常通知時だけDOMAIN_MIGRATION_CHECKLISTを開く", "credentialやverification値は共有しない"],
    done: "domain_day: done saastcolab.jp",
    next: "月次read-backで維持状態だけ確認",
  },
  {
    id: "H2",
    timing: "記事準備時",
    title: "公式価格を見て、この画面へ入力",
    minutes: "記事ごと",
    status: "P01–P08・P10・P12承認・公開済み / P09・P11自データ待ち / SVR01は11項目確認済み・TCO条件待ち",
    why: "価格確認checklistの公式URLをHumanが開き、必要箇所を貼り付けて候補抽出できます。候補はHuman確認前にcontractへ入りません。",
    steps: ["記事とvendorを選ぶ", "料金表を貼り付けて候補を事前入力する", "出典・観測日・次回確認日と前回差分を確認する", "Human確認後のJSONを保存し、本文標本を確認する"],
    done: "article_approve: <P-ID,...>",
    next: "P09・P11の自データ取得と、SVR01の期間限定表示・更新額の再確認を継続",
  },
  {
    id: "H3",
    timing: "判断時だけ",
    title: "返信カードのGO/HOLDを返す",
    minutes: "1分以内",
    status: "既定HOLD",
    why: "domain、記事承認、index、partner CTA、Impact feed登録を別々のtokenで判断します。一つのGOから別のGOを推論しません。",
    steps: ["HUMAN_REPLY_CARDを開く", "必要時だけImpact feed checklistを画面で確認する", "対象ID・partner・domainを確認する", "exact tokenだけ返信する"],
    done: "GO / HOLD token",
    next: "承認scopeだけをCodexが反映",
  },
  {
    id: "H4",
    timing: "月1回",
    title: "5 KPIを15分で転記",
    minutes: "15分",
    status: "手順・CSV導線準備済み",
    why: "GSC、GA4、Impact、Mangoolsの指定画面だけを見て、dashboard用CSVへ件数と確定報酬を転記します。",
    steps: ["MONTHLY_15_MIN_ROUTINEを開く", "前月の同じ期間を選ぶ", "CSVを保存し、monthly_kpi_csv: doneを返す"],
    done: "monthly_kpi_csv: done / pending",
    next: "dashboardをrepo状態とCSVから再生成",
  },
] as const;

const p05FieldScopeCandidates = [
  {
    current: "旧field: Basic / 含まれる管理者数",
    observed: "Agency / 追加seat 5",
    handling: "総seat数や管理者数へ換算せず、extra seats availableとして扱う。",
  },
  {
    current: "旧field: Agency Pack料金",
    observed: "Mangools Agency / 年次checkout総額はP02承認済み証拠あり",
    handling: "存在を確認できないPackを作らず、同一planの承認済み年次総額だけを再利用候補にする。",
  },
  {
    current: "旧field: 毎月の監査ページ上限",
    observed: "Site analysis 150 requests / 24h",
    handling: "月間値や監査ページ数へ換算せず、公式の24時間単位を維持する。",
  },
  {
    current: "移行支援料金",
    observed: "料金ページでは確認できず",
    handling: "記載が見つからないことを0円や対象外の根拠にせず、unknownを維持する。",
  },
] as const;

export default function OperatorPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">HUMAN EASE TRACK</p>
        <h1>見る・入力する・<br />GO/HOLDを返す。</h1>
        <p>
          あなたの残作業は、公式価格の確認と入力、必要時の再認証、token返信、月次確認だけです。
          JSON編集、値の推測、外部への自動送信はありません。
        </p>
        <p>credential、個人情報、tracking ID、非公開報酬は入力しないでください。</p>
      </header>

      <section className="shell operator-summary" aria-labelledby="operator-summary-title">
        <div>
          <p className="eyebrow">CURRENT HANDOFF</p>
          <h2 id="operator-summary-title">Human作業を4種類へ集約</h2>
        </div>
        <dl>
          <div><dt>本番公開</dt><dd>P01–P08・P10・P12（10/12）</dd></div>
          <div><dt>この入力画面</dt><dd>NOINDEX</dd></div>
          <div><dt>CTA</dt><dd>本番Mangoolsのみ / ローカル候補DISABLED</dd></div>
        </dl>
      </section>

      <section
        className="shell page-section"
        aria-labelledby="p05-field-scope-title"
        data-p05-candidate-authority="human_approved"
        data-p05-field-scope="approved"
      >
        <div className="operator-section-heading">
          <div>
            <p className="eyebrow">P05 FIELD CORRECTION</p>
            <h2 id="p05-field-scope-title">公式表記に合わせて修正済み</h2>
          </div>
          <p>
            2026-08-09の公式料金画面と承認済みP02 checkout証拠に基づき、P05 contractと本文へ反映しました。
            2026-08-11に限定releaseし、index・既存Mangools CTA対象へ追加済みです。
          </p>
        </div>
        <div className="route-grid" data-p05-field-candidate-count={p05FieldScopeCandidates.length}>
          {p05FieldScopeCandidates.map((candidate) => (
            <article className="route-card" key={candidate.current}>
              <small>現在: {candidate.current}</small>
              <h3>{candidate.observed}</h3>
              <p>{candidate.handling}</p>
            </article>
          ))}
        </div>
        <p><strong>確認済み:</strong> <code>p05_field_scope: approve mangools_agency_actual_fields</code></p>
        <p><small>出典表示: mangools.com/plans-and-pricing（外部link・Affiliate識別子なし）</small></p>
      </section>

      <div className="shell operator-input-wrap">
        <OperatorInputForm />
        <p className="operator-derivative-link"><Link className="text-link" href="/operator/servers/">servers価格観測を開く</Link></p>
        <p className="operator-derivative-link"><Link className="text-link" href="/servers/business-server-pricing/">servers第1記事のnoindex標本を確認</Link></p>
        <p className="operator-derivative-link"><Link className="text-link" href="/operator/derivatives/">note・X再配信templateを確認</Link></p>
      </div>

      <section className="shell operator-table-card" aria-labelledby="operator-table-title">
        <div className="operator-section-heading">
          <div>
            <p className="eyebrow">ONLY FOUR TASKS</p>
            <h2 id="operator-table-title">残る本人作業</h2>
          </div>
          <p>価格dataの自動取得、公開、CTA、課金は、この画面の入力だけでは実行されません。</p>
        </div>
        <div className="table-scroll" tabIndex={0} aria-label="残る本人作業を横スクロール">
          <table className="operator-table">
            <caption>本人が見る画面、返すtoken、Codexが続ける作業</caption>
            <thead><tr><th scope="col">ID</th><th scope="col">時期 / 作業</th><th scope="col">現在地</th><th scope="col">本人所要</th><th scope="col">返信</th><th scope="col">次の自動作業</th></tr></thead>
            <tbody>
              {remainingHumanWork.map((action) => (
                <tr key={action.id}>
                  <th scope="row"><span className="action-id">{action.id}</span></th>
                  <td><strong>{action.title}</strong><small>{action.timing}</small></td>
                  <td><span className="action-status">{action.status}</span></td>
                  <td>{action.minutes}</td>
                  <td><code>{action.done}</code></td>
                  <td>{action.next}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="shell operator-manual" aria-labelledby="operator-manual-title">
        <div className="operator-section-heading">
          <div><p className="eyebrow">WHAT TO DO</p><h2 id="operator-manual-title">迷った時だけ開く</h2></div>
          <p>不明値は埋めず、そのfieldを止めます。HOLDは失敗ではなく既定の安全動作です。</p>
        </div>
        <div className="manual-list">
          {remainingHumanWork.map((action) => (
            <details key={action.id} open={action.id === "H2"}>
              <summary><span>{action.id}</span><strong>{action.title}</strong><small>{action.status}</small></summary>
              <div className="manual-body">
                <p>{action.why}</p>
                <ol>{action.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                <p><b>次:</b> {action.next}</p>
              </div>
            </details>
          ))}
        </div>
      </section>

      <section className="shell operator-reply" aria-labelledby="reply-title">
        <div>
          <p className="eyebrow">REPLY CARD</p>
          <h2 id="reply-title">承認は記事単位</h2>
          <p>複数記事はカンマ区切りで返せます。indexとCTAは記事承認から自動では有効になりません。</p>
        </div>
        <pre>{`記事承認:
article_approve: P01,P02,P03

domain:
domain: GO <domain> / HOLD

index:
index_go: GO / HOLD

partner CTA:
affiliate_cta: GO Mangools / HOLD Mangools

Impact feed:
impact_feed_a1: GO <partner> / HOLD <partner>`}</pre>
      </section>
    </main>
  );
}
