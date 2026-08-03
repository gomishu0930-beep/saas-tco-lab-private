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

test("P01 article renders the Human-confirmed annual checkout TCO", async () => {
  const response = await render("/pilot/pricing-calculator");
  const html = await response.text();

  assert.match(html, /P01[\s\S]{0,80}HUMAN INPUT/);
  assert.match(html, /APPROVED/);
  assert.match(html, /承認済み6章本文/);
  assert.doesNotMatch(html, /\{\{contract:/);
  assert.match(html, /Human確認済み12か月TCO/);
  assert.match(html, /USD 452\.40/);
  assert.match(html, /USD 37\.70 \/ mo/);
  assert.match(html, /USD 61\.00 \/ mo/);
  assert.match(html, /月払い比で約38%割安/);
  assert.match(html, /通貨[\s\S]{0,80}USD/);
  assert.match(html, /billing toggle[\s\S]{0,80}年払い選択/);
  assert.match(html, /価格表示の分類[\s\S]{0,100}年払い恒常割引（計算可）/);
  assert.match(html, /価格の一次観測[\s\S]{0,80}checkout請求総額/);
  assert.match(html, /月額換算（派生値）[\s\S]{0,80}37\.70/);
  assert.match(html, /24時間ごとに更新されると説明し、従量超過課金を提示していない/);
  assert.match(html, /VAT \$0\.00かつSubtotalとTotalが同額/);
  assert.match(html, /Human指定: 1名でブログ記事4〜5本\/月/);
  assert.match(html, /Human入力値/);
  assert.match(html, /https:\/\/mangools\.com\/subscriptions\/checkout/);
  assert.match(html, /観測日/);
  assert.match(html, /次回確認日/);
  assert.match(html, /12か月TCO計算機/);
  assert.doesNotMatch(html, /checkout_values token未受領/);
  assert.match(html, /contract取込済み/);
  assert.match(html, /記事review[\s\S]{0,80}承認済み・公開候補/);
  assert.match(html, /PR・広告に関する表示/);
  assert.match(html, /CTA DISABLED/);
  assert.ok(html.indexOf("article-pr-disclosure") < html.indexOf("CTA DISABLED"));
  assert.doesNotMatch(html, /rel="sponsored|公式サイトへ/i);
});

test("P02 and P03 keep vendor-plan identities and explicit unknown reasons", async () => {
  const p02 = await (await render("/pilot/plan-comparison")).text();
  assert.doesNotMatch(p02, /\{\{contract:/);
  assert.match(p02, /Mangools \/ Basic/);
  assert.match(p02, /Mangools \/ Premium/);
  assert.match(p02, /Mangools \/ Agency/);
  assert.match(p02, /keyword検索回数 \/ 24h/);
  assert.match(p02, /最低seat数を明示していない/);
  assert.match(p02, /USD 452\.40[\s\S]*USD 632\.40[\s\S]*USD 1172\.40/);
  assert.match(p02, /約38%割安[\s\S]*約35%割安[\s\S]*約31%割安/);

  const p03 = await (await render("/pilot/alternatives")).text();
  assert.doesNotMatch(p03, /\{\{contract:/);
  assert.match(p03, /Mangools \/ Basic/);
  assert.match(p03, /SE Ranking \/ Core/);
  assert.match(p03, /Semrush \/ SEO/);
  assert.match(p03, /追跡keyword数（候補別単位）/);
  assert.match(p03, /SE Ranking \/ Core[\s\S]{0,500}checkout請求総額が未観測/);
  assert.match(p03, /Semrush \/ SEO[\s\S]{0,500}checkout請求総額が未観測/);
  assert.match(p03, /Mangools Basicの12か月総額だけを確定/);
  assert.match(p03, /横断価格順位を付けません/);
  assert.match(p03, /年次請求/);
  assert.match(p03, /unknown（税込・税別未確認）/);
  assert.match(p03, /billing toggle[\s\S]{0,80}年払い選択/);
  assert.match(p03, /Mangools \/ Basic[\s\S]{0,1200}価格表示の分類[\s\S]{0,100}年払い恒常割引（計算可）/);
  assert.match(p03, /SE Ranking \/ Core[\s\S]{0,1200}価格表示の分類[\s\S]{0,100}unknown（分類未確認・計算HOLD）/);
  assert.match(p03, /公式価格ページ上で移行費用を確認できない/);
  assert.match(p03, /記事単位の出典・更新状態/);
  assert.match(p03, /2026-07-30/);
  assert.match(p03, /2026-08-29/);
  assert.match(p03, /記事状態[\s\S]{0,80}approved/);
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
  assert.doesNotMatch(html, /JSONをコピー/);
  assert.match(html, /article_approve: P01,P02,P03/);
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
