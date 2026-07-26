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
    ["/pilot", /高意図記事を、公開せずに12本検証する。/],
    ["/disclosure", /広告収益と、比較判断を混ぜない。/],
    ["/readiness", /現在の総合判定/],
    ["/operator", /あなたの操作だけ/],
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

test("operator route stays in card-free mode and shows SE Ranking inquiry as sent", async () => {
  const response = await render("/operator");
  const html = await response.text();

  assert.match(html, /カード不要モード/);
  assert.match(html, /カード登録、有料trial、課金開始は月末まで停止/);
  assert.match(html, /送信済み・回答待ち/);
  assert.match(html, /登録済み・Affiliate有効/);
  assert.match(html, /紹介IDは公開・repo保存しない/);
  assert.match(html, /2026-07-23に公式Affiliate窓口へ送信済み/);
  assert.doesNotMatch(html, /se_ranking_support_mail: GO \/ STOP/);
  assert.doesNotMatch(html, /SE Rankingを本人登録・有効化/);
});

test("local robots disallows the complete site", async () => {
  const response = await render("/robots.txt");
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /User-Agent: \*/i);
  assert.match(body, /Disallow: \/(?:\r?\n|$)/);
});
