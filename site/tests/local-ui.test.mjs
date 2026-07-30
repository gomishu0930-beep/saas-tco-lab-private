import assert from "node:assert/strict";
import test from "node:test";

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
    ["/operator/derivatives", /noteとXへ/],
    ["/embed/tco-calculator", /埋め込み用12か月TCO計算機/],
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

test("P01 article renders imported Human values and unknowns without placeholders", async () => {
  const response = await render("/pilot/pricing-calculator");
  const html = await response.text();

  assert.match(html, /P01[\s\S]{0,80}HUMAN INPUT/);
  assert.match(html, /6章の本文下書き/);
  assert.doesNotMatch(html, /\{\{contract:/);
  assert.match(html, /37\.70[\s\S]{0,40}\/ mo/);
  assert.match(html, /unknown（画面表記: \$）/);
  assert.match(html, /公式価格ページ上でBasicの超過単価を確認できない/);
  assert.match(html, /Human指定: 1名でブログ記事4〜5本\/月/);
  assert.match(html, /Human入力値/);
  assert.match(html, /https:\/\/mangools\.com\/plans-and-pricing/);
  assert.match(html, /観測日/);
  assert.match(html, /次回確認日/);
  assert.match(html, /12か月TCO計算機/);
  assert.match(html, /計算停止[\s\S]{0,80}UNKNOWN/);
  assert.match(html, /contract取込済み/);
  assert.match(html, /記事review[\s\S]{0,80}未承認/);
  assert.match(html, /PR・広告に関する表示/);
  assert.match(html, /CTA DISABLED/);
  assert.ok(html.indexOf("article-pr-disclosure") < html.indexOf("CTA DISABLED"));
  assert.doesNotMatch(html, /rel="sponsored|公式サイトへ/i);
});

test("P02 and P03 keep vendor-plan identities and explicit unknown reasons", async () => {
  const p02 = await (await render("/pilot/plan-comparison")).text();
  assert.doesNotMatch(p02, /\{\{contract:/);
  assert.match(p02, /mangools \/ basic/);
  assert.match(p02, /mangools \/ premium/);
  assert.match(p02, /mangools \/ agency/);
  assert.match(p02, /最低seat数を明示していない/);

  const p03 = await (await render("/pilot/alternatives")).text();
  assert.doesNotMatch(p03, /\{\{contract:/);
  assert.match(p03, /mangools \/ basic/);
  assert.match(p03, /se-ranking \/ core/);
  assert.match(p03, /semrush \/ seo/);
  assert.match(p03, /17455[\s\S]{0,40}¥ \/ mo/);
  assert.match(p03, /117\.33[\s\S]{0,40}\$ \/ mo/);
  assert.match(p03, /公式価格ページ上で移行費用を確認できない/);
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
  assert.match(html, /P01[\s\S]{0,80}料金計算[\s\S]{0,80}第1弾/);
  assert.match(html, /出典URL/);
  assert.match(html, /観測日/);
  assert.match(html, /次回確認日/);
  assert.match(html, /価格ページのコピーテキストを解析/);
  assert.match(html, /ローカルで候補を抽出/);
  assert.match(html, /vendor・planごとに行を分け/);
  assert.match(html, /Humanシナリオ/);
  assert.match(html, /Human確認して証拠contractを確定/);
  assert.match(html, /前回確定値とのside-by-side差分/);
  assert.doesNotMatch(html, /JSONをコピー/);
  assert.match(html, /article_approve: P01,P02/);
  assert.match(html, /CTA[^<]*DISABLED/);
  assert.doesNotMatch(html, /Google Adsを課金画面前まで進める/);
  assert.doesNotMatch(html, /HubSpot Impact契約・申請/);
  assert.doesNotMatch(html, /<form[^>]+action=/i);
});

test("calculator embed stays disclosed, sourced, and noindex before release GO", async () => {
  const response = await render("/embed/tco-calculator");
  const html = await response.text();
  assert.match(html, /PR・広告に関する表示/);
  assert.match(html, /12か月TCO計算機/);
  assert.match(html, /計算仕様・根拠の確認/);
  assert.ok(html.indexOf("article-pr-disclosure") < html.indexOf("tco-calculator-title"));
  assert.match(html, /name="robots"[^>]*content="noindex, nofollow, noarchive, nosnippet"/i);
  assert.doesNotMatch(html, /rel="sponsored|公式サイトへ/i);
});

test("local robots disallows the complete site", async () => {
  const response = await render("/robots.txt");
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /User-Agent: \*/i);
  assert.match(body, /Disallow: \/(?:\r?\n|$)/);
});
