import type { Metadata } from "next";
import Link from "next/link";

import { ServerObservationForm } from "../../components/ServerObservationForm";
import { serverArticleSlate } from "../../lib/pilot-pages";

const svr01BrowserCandidates = {
  observedOn: "2026-08-09",
  sourceLabel: "XServerビジネス公式機能一覧（Safariで開いている画面）",
  fields: [
    {
      label: "期間限定表示",
      candidate: "月額料金30%キャッシュバック／2026年10月13日17:00終了",
      handling: "time_limited_promo候補。終了日と適用条件をHuman確認する。",
    },
    {
      label: "共有スタンダード表示額",
      candidate: "月額3,762円、実質月額2,633円、初期費用16,500円",
      handling: "通常額・promo額・税込表示を分離してHuman確認する。",
    },
    {
      label: "ストレージ",
      candidate: "NVMe 700GB",
      handling: "用途判定へ採用する前にplan一致をHuman確認する。",
    },
    {
      label: "CPU",
      candidate: "共有スタンダード欄は「-」表示",
      handling: "0へ置換せず、not_applicableかunknownかをHumanが決める。",
    },
    {
      label: "転送量",
      candidate: "転送量課金なし・転送量無制限",
      handling: "数値上限を作らず、not_applicable候補としてHuman確認する。",
    },
    {
      label: "独自ドメイン特典",
      candidate: "永久無料2ドメイン、年間7,000円（税抜）までの管理費が契約中無料との表示",
      handling: "対象ドメイン・更新条件・契約継続条件をHuman確認する。",
    },
    {
      label: "1年無料特典",
      candidate: "1年目無料、2年目から更新費用が発生する旨の表示",
      handling: "2年目のexact更新額が確認できるまでTCOへ加えない。",
    },
    {
      label: "サイト移行",
      candidate: "10サイトまで無料、11サイト目以降16,500円（税込）",
      handling: "対象作業と適用単位をHuman確認する。",
    },
    {
      label: "バックアップ",
      candidate: "自動バックアップあり",
      handling: "保存期間・復元料金を別fieldとしてHuman確認する。",
    },
  ],
} as const;

export const metadata: Metadata = {
  title: "サーバー価格観測",
  description: "サーバー料金をHuman確認し、candidate-only contractへ変換するローカル入力画面。",
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
};

export default function ServerOperatorPage() {
  return (
    <main id="main-content" className="page-main">
      <header className="shell page-header">
        <p className="eyebrow">SERVERS / HUMAN INPUT</p>
        <h1>通常料金・更新料・特典を、<br />一つずつ分けて記録。</h1>
        <p>価格確認20分、入力20分、表示確認20分。値を推測せず、未確認は理由付きで残します。</p>
      </header>
      <div className="shell operator-input-wrap"><ServerObservationForm /></div>
      <section
        className="shell page-section"
        aria-labelledby="svr01-browser-candidates-title"
        data-candidate-authority="none"
      >
        <div className="section-heading">
          <p className="eyebrow">SVR01 / HUMAN確認前</p>
          <h2 id="svr01-browser-candidates-title">公式画面の確認候補</h2>
          <p>
            これはブラウザで見つけた事前チェックリストです。Human確認前はcontractへ保存せず、
            TCO・順位・記事・index・CTAへ流しません。
          </p>
        </div>
        <p>
          観測候補日: <time dateTime={svr01BrowserCandidates.observedOn}>{svr01BrowserCandidates.observedOn}</time>
          {" / "}
          確認画面: {svr01BrowserCandidates.sourceLabel}
        </p>
        <div className="route-grid" data-svr01-browser-candidate-count={svr01BrowserCandidates.fields.length}>
          {svr01BrowserCandidates.fields.map((field) => (
            <article key={field.label}>
              <span>未確認候補</span>
              <h3>{field.label}</h3>
              <p>{field.candidate}</p>
              <small>{field.handling}</small>
            </article>
          ))}
        </div>
        <p><strong>確定操作:</strong> 公式画面と一致する行だけをOperatorへ入力し、差分を確認してから確定します。</p>
      </section>
      <section className="shell page-section" aria-labelledby="server-candidate-list-title">
        <div className="section-heading">
          <p className="eyebrow">SVR01–SVR20</p>
          <h2 id="server-candidate-list-title">価格観測と承認の待ち行列</h2>
        </div>
        <div className="route-grid" data-server-candidate-index="20">
          {serverArticleSlate.map((article) => (
            <article key={article.id}>
              <span>{article.id}</span>
              <h3><Link href={`/servers/business-server-pricing/?candidate=${article.id}`}>{article.topic}</Link></h3>
              <p>{article.readerQuestion}</p>
              <small>candidate only / 競合性未観測 / 実価格0件</small>
            </article>
          ))}
        </div>
      </section>
      <section className="shell page-section"><Link className="text-link" href="/operator/">通常のOperatorへ戻る</Link></section>
    </main>
  );
}
