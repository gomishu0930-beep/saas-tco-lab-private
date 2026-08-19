import type { Metadata } from "next";
import Link from "next/link";
import editorialLaunchState from "../../../../docs/EDITORIAL_LAUNCH_STATE.json";

import { ServerObservationForm } from "../../components/ServerObservationForm";
import {
  serverArticleSlate,
  serverLaunchArticleBriefs,
  serverLaunchPriorityArticles,
  serverObservationPage,
} from "../../lib/pilot-pages";
import savedSvr01Candidate from "../../../../artifacts/category-expansion-inputs/SVR01-servers-category-expansion-input-v3-2026-08-14.json";

const svr01BrowserCandidates = {
  observedOn: "2026-08-09",
  reviewStatus: "human_approved",
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

const vendorObservationGuides = [
  {
    id: "conoha-wing",
    vendor: "ConoHa WING",
    officialUrl: "https://www.conoha.jp/pricing/",
    screen: "料金ページでWINGパックまたは通常料金を選び、契約期間と対象プラン名が同時に見える状態にする。",
    caution: "月額換算と実際の請求総額、通常料金と期間限定表示を分ける。",
  },
  {
    id: "sakura-rental-server",
    vendor: "さくらのレンタルサーバ",
    officialUrl: "https://rs.sakura.ad.jp/plan/",
    screen: "料金プラン画面で対象プランを一つ選び、月払い・年払いのどちらを観測するか固定する。",
    caution: "無料期間や初期費用の表示を、更新時の通常請求へ流用しない。",
  },
  {
    id: "kagoya-rental-server",
    vendor: "KAGOYAレンタルサーバー",
    officialUrl: "https://www.kagoya.jp/kir/price/",
    screen: "料金・スペック画面でservice種別と対象プランを一つ選び、月払いまたは12か月一括を固定する。",
    caution: "共有・VPS・managed等の異なるservice種別を同じ比較行にしない。",
  },
] as const;

const m3FollowupReview = {
  observedOn: "2026-08-18",
  authority: "human_confirmed_2026-08-18",
  vendors: [
    {
      id: "conoha-wing",
      vendor: "ConoHa WING Standard（WINGパック12か月）",
      officialSources: [
        "https://www.conoha.jp/pricing/",
        "https://www.conoha.jp/wing/pdf/conoha_wing_spec_ja.pdf",
      ],
      findings: [
        "通常料金は4.4円/時、月額上限2,640円（税込）の時間課金で、WINGパック12か月の更新総額とは別料金タイプ。",
        "WINGパックの自動更新は契約満了30日前に決済される。将来のexact更新総額は契約画面でしか確認できないためunknownを維持。",
        "StandardはSSD 600GB、転送量無制限。自動バックアップは無料で1日1回・過去14日分、無料SSLあり。",
      ],
      useCaseCandidate: "small_siteに適合。法人・ECはplan単位の追加根拠がないため除外。",
    },
    {
      id: "sakura-rental-server",
      vendor: "さくらのレンタルサーバ Business（12か月）",
      officialSources: [
        "https://rs.sakura.ad.jp/plan/",
      ],
      findings: [
        "12か月一括を選んだ申込カートの請求総額は29,040円（税込）。月額換算2,420円、毎月払い2,970円の恒常年払い差。",
        "将来のexact更新額は契約中サービスの概算見積で確認する仕様で、初回更新前には発行できないためunknownを維持。",
        "BusinessはSSD 600GB、転送量無制限、バックアップ＆ステージング、複数人管理に対応。",
      ],
      useCaseCandidate: "small_site・corporate_siteに適合。ECはplan単位の追加根拠がないため除外。",
    },
    {
      id: "kagoya",
      vendor: "KAGOYA Light（1コア/4GB・12か月）",
      officialSources: [
        "https://www.kagoya.jp/kir/price/",
        "https://www.kagoya.jp/kir/rentalserver/",
        "https://www.kagoya.jp/kir/function/",
      ],
      findings: [
        "12か月一括の請求総額は17,820円（税込）。途中解約返金なし。初月無料は終了日付きcampaignではない候補。",
        "仮想専用1コア/4GB、Web・MySQL合計100GB、転送量無制限・従量課金なし。",
        "最大10GBの自動バックアップが無料。無料SSL、独自ドメイン1個初年度無料を公式画面で確認できる。",
      ],
      useCaseCandidate: "small_site・corporate_siteに適合。公式画面では高負荷/ECを上位planへ対応付けるためLightはecommerceから除外。",
    },
  ],
  requirements: {
    small_site: "ストレージ100GB以上・転送量無制限・バックアップ利用可・無料SSL",
    corporate_site: "small_site条件に加え、複数人管理またはmanaged運用をplan単位で公式確認",
    ecommerce: "small_site条件に加え、EC用途またはECアプリ対応を対象plan単位で公式確認",
  },
} as const;

const requiredVendorObservationFields = [
  "初期費用と税表示",
  "更新時請求額・請求周期・更新月",
  "キャンペーン終了日（表示がない場合も、その画面状態を記録）",
  "ドメイン特典の対象・期間・終了後料金",
  "最低契約期間",
] as const;

const serverLaunchQueue = serverLaunchPriorityArticles();
const serverLaunchApprovalToken = `article_approve: ${serverLaunchQueue.map((article) => article.id).join(",")}`;
const serverLaunchApproved = serverLaunchQueue.every(
  (article) => editorialLaunchState.server_articles[article.id as keyof typeof editorialLaunchState.server_articles] === "approved",
);
const serverLaunchDeployed = serverLaunchQueue.every(
  (article) => editorialLaunchState.deployed_server_articles.includes(article.id),
);
const serverLaunchDeployToken = `deploy_update: GO ${serverLaunchQueue.map((article) => article.id).join(",")} / HOLD`;
const serverLaunchIndexToken = `index_go: GO ${serverLaunchQueue.map((article) => article.id).join(",")} / HOLD`;

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
      <section className="shell page-section" aria-labelledby="vendor-observation-guides-title">
        <div className="section-heading">
          <p className="eyebrow">M3 / 1画面ずつ確認</p>
          <h2 id="vendor-observation-guides-title">比較に追加する3社の価格確認</h2>
          <p>1社につき一つの公式画面だけを開き、対象planと契約期間を固定してから同じ5項目を記録します。</p>
        </div>
        <div className="route-grid" data-server-vendor-observation-guide-count={vendorObservationGuides.length}>
          {vendorObservationGuides.map((guide) => (
            <article key={guide.id} data-server-vendor-guide={guide.id}>
              <span>公式画面 1枚</span>
              <h3>{guide.vendor}</h3>
              <ol>
                <li><a href={guide.officialUrl} rel="noopener noreferrer" target="_blank">公式料金ページを開く</a></li>
                <li>{guide.screen}</li>
                <li>下の5項目を読み、見つからない項目は理由付きでunknownにする。</li>
                <li>共通情報をOperatorへ入力し、候補JSONをダウンロードする。</li>
              </ol>
              <ul>{requiredVendorObservationFields.map((field) => <li key={field}>{field}</li>)}</ul>
              <small>{guide.caution}</small>
            </article>
          ))}
        </div>
        <p>Human確認前の抽出候補はcontractへ保存しません。候補JSONがない状態では、価格確認完了tokenだけで記事・順位・indexへ昇格させません。</p>
      </section>
      <section
        className="shell page-section"
        aria-labelledby="m3-followup-review-title"
        data-m3-followup-authority={m3FollowupReview.authority}
      >
        <div className="section-heading">
          <p className="eyebrow">M3 / HUMAN CONFIRMED</p>
          <h2 id="m3-followup-review-title">checkout・更新・用途条件の最終確認</h2>
          <p>
            公式画面から整理した候補値と用途条件はHuman確認済みです。価格artifactはcandidate-onlyのまま維持し、
            未確認価格をTCO・順位・記事・index・CTAへ昇格させません。
          </p>
        </div>
        <div className="route-grid" data-m3-followup-vendor-count={m3FollowupReview.vendors.length}>
          {m3FollowupReview.vendors.map((vendor) => (
            <article key={vendor.id} data-m3-followup-vendor={vendor.id}>
              <span>Human確認済み</span>
              <h3>{vendor.vendor}</h3>
              <ul>{vendor.findings.map((finding) => <li key={finding}>{finding}</li>)}</ul>
              <p><strong>用途判定:</strong> {vendor.useCaseCandidate}</p>
              <details>
                <summary>確認した公式ページ</summary>
                <ul>{vendor.officialSources.map((source) => (
                  <li key={source}><a href={source} rel="noopener noreferrer" target="_blank">公式ページを開く</a></li>
                ))}</ul>
              </details>
            </article>
          ))}
        </div>
        <h3>Human確認済みの用途条件</h3>
        <ul>
          <li><strong>小規模サイト:</strong> {m3FollowupReview.requirements.small_site}</li>
          <li><strong>法人サイト:</strong> {m3FollowupReview.requirements.corporate_site}</li>
          <li><strong>ECサイト:</strong> {m3FollowupReview.requirements.ecommerce}</li>
        </ul>
        <p>
          観測日: <time dateTime={m3FollowupReview.observedOn}>{m3FollowupReview.observedOn}</time>。
          exact更新総額を公開前に観測できない項目は、0円や表示価格へ置き換えずunknownで確定します。
        </p>
      </section>
      <div className="shell operator-input-wrap"><ServerObservationForm savedCandidate={savedSvr01Candidate} /></div>
      <section
        className="shell page-section"
        aria-labelledby="svr01-browser-candidates-title"
        data-candidate-authority={svr01BrowserCandidates.reviewStatus}
      >
        <div className="section-heading">
          <p className="eyebrow">SVR01 / HUMAN確認済み</p>
          <h2 id="svr01-browser-candidates-title">公式画面の確認記録</h2>
          <p>
            9項目の画面表示はHuman確認済みです。値へ一意に変換できないキャンペーン、更新、特典、CPUは
            unknownを維持し、TCO・順位・記事・index・CTAへ流しません。
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
              <span>Human確認済み候補</span>
              <h3>{field.label}</h3>
              <p>{field.candidate}</p>
              <small>{field.handling}</small>
            </article>
          ))}
        </div>
        <p><strong>確認結果:</strong> <code>svr01_candidates: confirm_all</code>。一意に写せるfieldだけをcandidate-only contractへ反映しました。</p>
      </section>
      <section className="shell page-section" aria-labelledby="server-launch-queue-title">
        <div className="section-heading">
          <p className="eyebrow">M4 / 20本到達キュー</p>
          <h2 id="server-launch-queue-title">次に確認する8記事</h2>
          <p>公開済み12本から20本へ進む順序です。価格確認20分・入力20分・確認20分を維持します。</p>
        </div>
        <ol className="readiness-board" data-server-launch-queue-count={serverLaunchQueue.length}>
          {serverLaunchQueue.map((article, index) => (
            <li key={article.id} data-server-launch-priority={index + 1}>
              <span className="gate-id">{index + 1}</span>
              <div>
                <span className="gate-name">{article.id}</span>
                <strong><Link href={`/servers/${article.slug}/`}>{article.topic}</Link></strong>
              </div>
              <p>{article.readerQuestion}</p>
              <small>共通価格候補取込済み / 記事固有unknownあり / {serverLaunchApproved ? "article approval済み" : "article approval待ち"} / {serverLaunchDeployed ? "production反映済み" : "deploy待ち"} / noindex / CTA無効</small>
            </li>
          ))}
        </ol>
        <aside
          className="review-summary"
          data-server-launch-approval-state={serverLaunchApproved ? "approved" : "pending"}
          data-server-launch-deploy-state={serverLaunchDeployed ? "deployed" : "pending"}
          data-server-launch-approval-token={serverLaunchApprovalToken}
        >
          <h3>{serverLaunchDeployed ? "8記事をproductionへ反映済み" : serverLaunchApproved ? "8記事のHuman承認を記録済み" : "8記事を標本確認した後の返信"}</h3>
          <p>
            公式価格から確定できない更新額、移行作業、mail・EC固有条件はunknownのままです。
            {serverLaunchDeployed
              ? "productionには反映済みですが、検索登録とCTAは無効です。次は8記事を列挙したindex releaseの別GOです。"
              : serverLaunchApproved
              ? "80点公開scopeの承認は記録済みです。index・CTA・deployはまだ変更していません。次はproduction releaseの別GOです。"
              : "それを明示した80点公開でよい場合だけ、次のtokenを返してください。記事承認だけではindex・CTA・deployは変わりません。"}
          </p>
          <code>{serverLaunchDeployed ? serverLaunchIndexToken : serverLaunchApproved ? serverLaunchDeployToken : serverLaunchApprovalToken}</code>
        </aside>
      </section>
      <section className="shell page-section" aria-labelledby="server-launch-input-matrix-title">
        <div className="section-heading">
          <p className="eyebrow">M4 / INPUT MATRIX</p>
          <h2 id="server-launch-input-matrix-title">8記事へ使うfieldと追加確認</h2>
          <p>共通のvendor価格は一度だけ入力し、同じ意味のfieldだけを各記事へ再利用します。記事固有の条件は別にHuman確認します。</p>
        </div>
        <div className="route-grid" data-server-launch-input-matrix={serverLaunchArticleBriefs.length}>
          {serverLaunchArticleBriefs.map((brief) => {
            const article = serverLaunchQueue.find((candidate) => candidate.id === brief.articleId);
            return <article key={brief.articleId} data-server-launch-input-brief={brief.articleId}>
              <span>{brief.articleId}</span>
              <h3>{article?.topic}</h3>
              <p>{brief.decisionRule}</p>
              <details>
                <summary>入力対応を確認</summary>
                <h4>共通価格から再利用</h4>
                <ul>{brief.reusableObservationFields.map((field) => {
                  const definition = serverObservationPage.numericFields.find((candidate) => candidate.key === field);
                  return <li key={field}>{definition?.label}: <code>{field}</code></li>;
                })}</ul>
                <h4>記事固有のHuman確認</h4>
                <ul>{brief.additionalHumanChecks.map((check) => <li key={check}>{check}</li>)}</ul>
                <p><strong>承認前:</strong> {brief.approvalQuestion}</p>
              </details>
            </article>;
          })}
        </div>
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
              <h3><Link href={article.id === "SVR01" ? "/servers/business-server-pricing/" : `/servers/${article.slug}/`}>{article.topic}</Link></h3>
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
