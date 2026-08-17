import assert from "node:assert/strict";
import test from "node:test";

const SERVER_CANDIDATE_PATHS = [
  "business-server-pricing",
  "small-business-server",
  "ec-server-cost",
  "server-first-year-total",
  "server-renewal-cost",
  "server-migration-cost",
  "business-rental-server",
  "ec-server-requirements",
  "business-mail-server",
  "managed-server-cost",
  "business-rental-server-comparison",
  "small-business-server-comparison",
  "ec-server-comparison",
  "business-mail-server-comparison",
  "managed-server-comparison",
  "wordpress-server-cost",
  "server-transfer-cost",
  "server-backup-cost",
  "small-corporate-server",
  "server-cancellation-terms",
].map((_, index) => `/servers/business-server-pricing?candidate=SVR${String(index + 1).padStart(2, "0")}`);

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("renders the noindex evidence-first local home without starter residue", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /<html[^>]*lang="ja"/i);
  assert.match(html, /SaaS選定を/);
  assert.match(html, /合成データのみ/);
  assert.match(html, /NOINDEX/);
  assert.match(
    html,
    /name="robots"[^>]*content="noindex, nofollow, noarchive, nosnippet"/i,
  );
  assert.doesNotMatch(
    html,
    /codex-preview|Your site is taking shape|react-loading-skeleton/i,
  );
  assert.doesNotMatch(html, /synthetic-affiliate|rel="sponsored/i);
});

test("renders every synthetic-only local decision route with landmarks", async () => {
  const expectations = [
    ["/comparison", /同じ条件で、総額と適合を比べる。/],
    ["/methodology", /比較の作り方を、結果より先に公開する。/],
    ["/learning", /学習・施策・文章・収益導線を、同じ証拠鎖でつなぐ。/],
    ["/pilot", /高意図記事を、公開前に12本組み立てる。/],
    ["/about", /SaaS TCO Labについて/],
    ["/operator-information", /運営者情報/],
    ["/privacy", /プライバシーポリシー/],
    ["/contact", /お問い合わせ/],
    ["/advertising-policy", /広告掲載ポリシー/],
    ["/disclosure", /広告収益と、比較判断を混ぜない。/],
    ["/readiness", /現在の総合判定/],
    ["/operator", /見る・入力する・/],
    ["/operator/servers", /通常料金・更新料・特典を/],
    ["/operator/derivatives", /noteとXへ/],
    ["/servers/business-server-pricing", /XServerビジネス料金/],
    ["/embed/tco-calculator", /埋め込み用TCO表示/],
  ];

  for (const [path, expected] of expectations) {
    const response = await render(path);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.match(html, /<main\b/i, path);
    assert.match(html, /<nav\b/i, path);
    assert.match(html, /<footer\b/i, path);
    assert.match(html, expected, path);
    assert.match(
      html,
      /name="robots"[^>]*content="noindex, nofollow, noarchive, nosnippet"/i,
      path,
    );
  }
});

test("operator and pilot index report eleven live articles while P11 remains held", async () => {
  const operator = await (await render("/operator")).text();
  assert.match(operator, /P01–P10・P12（11\/12）/);
  assert.match(operator, /P01–P10・P12承認・公開済み/);
  assert.match(operator, /SVR01は11項目確認済み・TCO条件待ち/);
  assert.match(operator, /P11は作業timerを開始・停止/);
  assert.match(operator, /作業timerを開始・停止/);
  assert.match(operator, /端末内append-only台帳/);
  assert.doesNotMatch(operator, /release待ち|P01–P03 公開中/);

  const pilot = await (await render("/pilot")).text();
  assert.match(pilot, /P01–P10・P12の11本はHuman承認後に公開済み/);
  assert.match(pilot, /P11は完全暦月/);
  assert.match(pilot, /noindex・CTA無効を維持/);
  assert.doesNotMatch(pilot, /index GO未受領/);
});

test("P01 renders reader copy and approved evidence without an input calculator", async () => {
  const response = await render("/pilot/pricing-calculator");
  const html = await response.text();

  assert.match(html, /P01[\s\S]{0,80}確認済み/);
  assert.match(html, /Mangools料金\(2026年8月確認\): USD 452\.40と12か月TCO/);
  assert.doesNotMatch(html, /\{\{contract:/);
  assert.match(html, /class="shell article-decision-summary"[\s\S]*Mangools Basicの確認済み実額はUSD 452\.40（年次請求）で、/);
  const readerBody = html.match(/<section[^>]*aria-labelledby="P01-article-structure"[\s\S]*?<\/section>/)?.[0] ?? "";
  assert.doesNotMatch(readerBody, /vendor|billing toggle|価格表示分類|Human scenario|contract/i);
  assert.match(readerBody, /href="\/methodology#detailed-calculator"/);
  assert.match(html, />12か月TCO<\/h2>/);
  assert.match(html, /USD 452\.40/);
  assert.match(html, /USD 37\.70 \/ mo/);
  assert.match(html, /USD 61\.00 \/ mo/);
  assert.match(html, /月払い比で約38%割安/);
  assert.match(html, /通貨[\s\S]{0,80}USD/);
  assert.match(html, /画面の支払周期[\s\S]{0,80}年払い選択/);
  assert.match(html, /価格表示の扱い[\s\S]{0,100}通常の年払い割引/);
  assert.match(html, /価格を確認した場所[\s\S]{0,80}checkout請求総額/);
  assert.match(html, /月あたりの参考額[\s\S]{0,80}37\.70/);
  assert.match(html, /24時間ごとに更新されると説明し、従量超過課金を提示していない/);
  assert.match(html, /VAT \$0\.00かつSubtotalとTotalが同額/);
  assert.match(html, /Human指定: 1名でブログ記事4〜5本\/月/);
  assert.match(html, /確認値/);
  assert.match(html, /https:\/\/mangools\.com\/subscriptions\/checkout/);
  assert.match(html, /観測日/);
  assert.match(html, /次回確認日/);
  assert.doesNotMatch(html, /12か月TCO計算機|data-calculator-prefill-source="approved-evidence"/);
  assert.doesNotMatch(html, /<input\b|<select\b/i);
  assert.match(html, /観測日<\/dt><dd>2026-08-02/);
  assert.match(html, /次回確認日<\/dt><dd>2026-08-31/);
  assert.match(html, /PR・広告に関する表示/);
  assert.match(html, /記事制作に生成AIを補助的に使用する場合があります/);
  assert.match(html, /data-affiliate-cta-placeholder="mangools"/);
  assert.ok(html.indexOf("article-pr-disclosure") < html.indexOf('data-affiliate-cta-placeholder="mangools"'));
  assert.match(html, /class="shell article-decision-summary"/);
  assert.match(html, /公式サイトの案内を見る/);
  assert.match(html, /class="evidence-details"/);
  assert.match(html, /出典・観測日・未確認理由を詳しく見る/);
  assert.match(html, /購入画面の最終請求額/);
  assert.match(html, /更新・解約・返金条件/);
  assert.match(html, /税・割引・上限超過の適用条件/);
  assert.match(html, /確認済み条件と紹介リンク欄へ戻る/);
  assert.ok(
    html.indexOf('data-affiliate-cta-placeholder="mangools"') < html.indexOf('class="evidence-details"'),
    "紹介リンク枠を詳細な証拠表より先に表示する",
  );
  assert.ok(
    html.indexOf('class="evidence-details"') < html.indexOf("確認済み条件と紹介リンク欄へ戻る"),
    "詳細根拠を確認した読者に行動枠への戻り導線を表示する",
  );
  assert.doesNotMatch(html, /rel="sponsored|公式サイトへ/i);
});

test("P02 and P03 keep vendor-plan identities and explicit unknown reasons", async () => {
  const p02 = await (await render("/pilot/plan-comparison")).text();
  assert.doesNotMatch(p02, /\{\{contract:/);
  assert.match(p02, /Mangools \/ Basic/);
  assert.match(p02, /Mangools \/ Premium/);
  assert.match(p02, /Mangools \/ Agency/);
  assert.match(p02, /キーワード検索回数 \/ 24時間/);
  assert.match(p02, /最低seat数を明示していない/);
  assert.match(p02, /USD 452\.40[\s\S]*USD 632\.40[\s\S]*USD 1172\.40/);
  assert.match(p02, /約38%割安[\s\S]*約35%割安[\s\S]*約31%割安/);

  const p03 = await (await render("/pilot/alternatives")).text();
  assert.doesNotMatch(p03, /\{\{contract:/);
  assert.match(p03, /Mangools \/ Basic/);
  assert.match(p03, /SE Ranking \/ Core/);
  assert.match(p03, /Semrush \/ SEO/);
  assert.match(p03, /追跡キーワード数（候補別単位）/);
  assert.match(p03, /SE Ranking \/ Core[\s\S]{0,500}checkout請求総額が未観測/);
  assert.match(p03, /Semrush \/ SEO[\s\S]{0,500}checkout請求総額が未観測/);
  assert.match(p03, /Mangools Basicの12か月総額だけを確認/);
  assert.match(p03, /横断価格順位を付けません/);
  assert.match(p03, /年次請求/);
  assert.match(p03, /unknown（税込・税別未確認）/);
  assert.match(p03, /画面の支払周期[\s\S]{0,80}年払い選択/);
  assert.match(p03, /Mangools \/ Basic[\s\S]{0,1200}価格表示の扱い[\s\S]{0,100}通常の年払い割引/);
  assert.match(p03, /SE Ranking \/ Core[\s\S]{0,1200}価格表示の扱い[\s\S]{0,100}表示条件を未確認/);
  assert.match(p03, /公式価格ページ上で移行費用を確認できない/);
  assert.match(p03, /記事単位の出典・更新状態/);
  assert.match(p03, /2026-07-30/);
  assert.match(p03, /2026-08-29/);
  assert.match(p03, /記事状態[\s\S]{0,80}approved/);
});

test("P06 and P07 render approved evidence while remaining local noindex candidates", async () => {
  const p06 = await (await render("/pilot/annual-vs-monthly")).text();
  assert.match(p06, /P06[\s\S]{0,80}確認済み/);
  assert.doesNotMatch(p06, /記事レビュー待ち/);
  assert.doesNotMatch(p06, /\{\{contract:/);
  assert.match(p06, /Mangools \/ Basic: USD 61\.00 \/ mo/);
  assert.match(p06, /Mangools \/ Basic: USD 452\.40 \/ yr/);
  assert.match(p06, /月払い比で約(?:<!-- -->)?38(?:<!-- -->)?%割安/);
  assert.match(p06, /途中解約時の返金・残存支払・解約費用/);

  const p07 = await (await render("/pilot/usage-overage")).text();
  assert.match(p07, /P07[\s\S]{0,80}確認済み/);
  assert.doesNotMatch(p07, /記事レビュー待ち/);
  assert.doesNotMatch(p07, /\{\{contract:/);
  assert.match(p07, /100 keyword research req\. \/ 24h/);
  assert.match(p07, /400 ルックアップ\/月/);
  assert.match(p07, /従量超過課金を提示していない/);
});

test("local comparison contains precomputed conditions and no active CTA", async () => {
  const response = await render("/comparison?scenario=fixture");
  const html = await response.text();

  assert.match(html, /JPY 13,200/);
  assert.match(html, /Python算定済み/);
  assert.match(html, /data期限/);
  assert.match(html, /rights期限/);
  assert.match(html, /広告に関する表示/);
  assert.match(html, /実提携なし/);
  assert.doesNotMatch(html, /公式サイトへ|synthetic-affiliate|rel="sponsored/i);
});

test("operator route reduces Human work to form input and exact reply tokens", async () => {
  const response = await render("/operator");
  const html = await response.text();

  assert.match(html, /見る・入力する・/);
  assert.match(html, /記事の実値を入力/);
  assert.match(html, /EDITORIAL INPUT 2\.3/);
  assert.match(html, /P01[\s\S]{0,80}料金計算[\s\S]{0,80}第1弾/);
  assert.match(html, /出典URL/);
  assert.match(html, /観測日/);
  assert.match(html, /次回確認日/);
  assert.match(html, /価格ページのコピーテキストを解析/);
  assert.match(html, /ローカルで候補を抽出/);
  assert.match(html, /vendor・planごとに行を分け/);
  assert.match(html, /billing toggle位置/);
  assert.match(html, /価格表示の分類/);
  assert.match(html, /年払い恒常割引/);
  assert.match(html, /期間限定promo/);
  assert.match(html, /checkout請求総額/);
  assert.match(html, /月額換算は12で最小通貨単位まで完全に割り切れる場合だけ派生表示/);
  assert.match(html, /Humanシナリオ/);
  assert.match(html, /Human確認して証拠contractを確定/);
  assert.match(html, /前回確定値とのside-by-side差分/);
  assert.match(html, /価格確認20分 → 入力20分 → 確認20分/);
  assert.match(html, /60分セッション開始/);
  assert.match(html, /80点で公開候補へ進め/);
  assert.doesNotMatch(html, /JSONをコピー/);
  assert.match(html, /article_approve: P01,P02,P03/);
  assert.match(html, /CTA[^<]*DISABLED/);
  assert.doesNotMatch(html, /Google Adsを課金画面前まで進める/);
  assert.doesNotMatch(html, /HubSpot Impact契約・申請/);
  assert.doesNotMatch(html, /<form[^>]+action=/i);
  assert.match(html, /href="\/operator\/servers\//);
  assert.match(html, /href="\/servers\/business-server-pricing\//);
  assert.match(html, /data-p05-candidate-authority="human_approved"/);
  assert.match(html, /data-p05-field-scope="approved"/);
  assert.match(html, /data-p05-field-candidate-count="4"/);
  assert.match(html, /p05_field_scope: approve mangools_agency_actual_fields/);
  assert.match(html, /Site analysis 150 requests \/ 24h/);
});

test("servers operator and all twenty article routes remain candidate-only and fail closed", async () => {
  const operator = await (await render("/operator/servers")).text();
  assert.match(operator, /SERVERS \/ CANDIDATE ONLY/);
  assert.match(operator, /Human確認してservers候補contractを確定/);
  assert.match(operator, /TCO: HOLD/);
  assert.match(operator, /用途判定: HOLD/);
  assert.match(operator, /contract昇格: HOLD/);
  assert.match(operator, /記事承認・index・CTAは別のHuman gate/);
  assert.match(operator, /共通の画面情報を11 fieldへ一括適用/);
  assert.match(operator, /共通情報を全fieldへ適用/);
  assert.match(operator, /値、通貨、税、請求周期、確認状態は変更しません/);
  assert.match(operator, /保存済みSVR01候補から再開/);
  assert.match(operator, /repositoryのSVR01候補を読込/);
  assert.match(operator, /Humanがボタンを押した後だけブラウザメモリへ読み/);
  assert.match(operator, /候補JSONをローカル読込/);
  assert.match(operator, /Human選択後だけブラウザメモリへ読み/);
  assert.match(operator, /公式価格ページの必要行だけを解析/);
  assert.match(operator, /抽出値は事前入力だけです/);
  assert.match(operator, /pricing\.initial_fee/);
  assert.match(operator, /servers\.campaign_period_months/);
  assert.match(operator, /SVR01 \/ HUMAN確認済み/);
  assert.match(operator, /data-candidate-authority="human_approved"/);
  assert.match(operator, /data-svr01-browser-candidate-count="9"/);
  assert.match(operator, /2026年10月13日17:00終了/);
  assert.match(operator, /転送量課金なし・転送量無制限/);
  assert.match(operator, /unknownを維持し/);
  assert.match(operator, /TCO・順位・記事・index・CTAへ流しません/);
  assert.match(operator, /svr01_candidates: confirm_all/);
  assert.doesNotMatch(operator, /候補JSONを保存/);

  assert.match(operator, /data-server-candidate-index="20"/);
  assert.match(operator, /href="\/servers\/business-server-pricing\/\?candidate=SVR01"/);
  assert.match(operator, /href="\/servers\/business-server-pricing\/\?candidate=SVR20"/);

  assert.equal(SERVER_CANDIDATE_PATHS.length, 20);
  for (const path of SERVER_CANDIDATE_PATHS) {
    const article = await (await render(path)).text();
    assert.match(article, /data-server-article-state="candidate_only"/, path);
    if (path.endsWith("candidate=SVR01")) {
      assert.match(article, /確認済み(?:<!-- -->)?4(?:<!-- -->)?項目、未確認(?:<!-- -->)?6(?:<!-- -->)?項目、[\s\S]{0,40}該当なし(?:<!-- -->)?1(?:<!-- -->)?項目/, path);
      assert.match(article, /data-ranking-eligible="false"[\s\S]{0,400}<strong>未確認<\/strong>/, path);
      assert.match(article, /JPY 50160 \/ yr/, path);
      assert.match(article, /data-server-article-review="approved"/, path);
      assert.match(article, /契約時に確認できた請求額は(?:<!-- -->)?66,660/, path);
      assert.match(article, /期間限定キャッシュバックを控除する前の金額/, path);
      assert.match(article, /66,660円/, path);
      assert.match(article, /24\/36か月総額・順位・推奨は表示しません/, path);
      assert.match(article, /他社より安いとは断定せず/, path);
      assert.match(article, /キャッシュバックの確定額と受取条件/, path);
      assert.match(article, /href="https:\/\/business\.xserver\.ne\.jp\//, path);
    } else {
      assert.match(article, /承認済みのservers価格contractはまだありません/, path);
      assert.doesNotMatch(article, /https:\/\/business\.xserver\.ne\.jp\//, path);
    }
    assert.match(article, /各紹介リンクの有効状態は下に表示/, path);
    assert.ok(article.indexOf("article-pr-disclosure") < article.indexOf("data-server-template-step=\"calculator\""), path);
    assert.ok(article.indexOf("data-server-template-step=\"calculator\"") < article.indexOf("data-server-template-step=\"cta_slot\""), path);
    assert.match(article, /href="\/operator\/servers\//, path);
    assert.doesNotMatch(article, /rel="sponsored|https?:\/\/[^\s<]*affiliate/i, path);
  }
});

test("calculator embed is zero-input gated and links to the methodology detail mode", async () => {
  const response = await render("/embed/tco-calculator");
  const html = await response.text();
  assert.match(html, /PR・広告に関する表示/);
  assert.match(html, /埋め込み用TCO表示/);
  assert.match(html, /承認済み価格を待っています/);
  assert.match(html, /href="\/methodology#detailed-calculator"/);
  assert.doesNotMatch(html, /<input\b|<select\b/i);
  assert.ok(html.indexOf("article-pr-disclosure") < html.indexOf("embed-zero-input-title"));
  assert.match(html, /name="robots"[^>]*content="noindex, nofollow, noarchive, nosnippet"/i);
  assert.doesNotMatch(html, /rel="sponsored|公式サイトへ/i);
});

test("methodology owns the only detailed input calculator", async () => {
  const html = await (await render("/methodology")).text();
  assert.match(html, /id="detailed-calculator"/);
  assert.match(html, /詳細計算モード/);
  assert.match(html, /12か月TCO計算機/);
  assert.match(html, /<input\b/i);
  assert.match(html, /<select\b/i);
});

test("local robots disallows the complete site", async () => {
  const response = await render("/robots.txt");
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /User-Agent: \*/i);
  assert.match(body, /Disallow: \/(?:\r?\n|$)/);
});
