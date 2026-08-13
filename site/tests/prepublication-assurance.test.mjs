import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test, { before } from "node:test";

const SERVER_CANDIDATE_ROUTES = [
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

const ROUTES = [
  "/",
  "/comparison",
  "/methodology",
  "/learning",
  "/pilot",
  "/pilot/pricing-calculator",
  "/pilot/plan-comparison",
  "/pilot/alternatives",
  "/pilot/small-team-fit",
  "/pilot/enterprise-fit",
  "/pilot/annual-vs-monthly",
  "/pilot/usage-overage",
  "/pilot/addon-cost",
  "/pilot/migration-cost",
  "/pilot/japan-tax",
  "/pilot/break-even",
  "/pilot/evidence-method",
  "/disclosure",
  "/readiness",
  "/operator",
  "/operator/servers",
  "/operator/derivatives",
  ...SERVER_CANDIDATE_ROUTES,
  "/embed/tco-calculator",
  "/about",
  "/operator-information",
  "/privacy",
  "/contact",
  "/advertising-policy",
];
const ARTICLE_ROUTES = ROUTES.filter((path) => path.startsWith("/pilot/"));
const ROUTE_PATHS = new Set(ROUTES.map(normalizedRoute));
const SVR01_ROUTE = "/servers/business-server-pricing?candidate=SVR01";
const ALLOWED_EVIDENCE_HOSTS = new Set([
  "saastcolab.jp",
  "mangools.com",
  "seranking.com",
  "www.semrush.com",
  "business.xserver.ne.jp",
]);
const pages = new Map();

async function render(path) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("assurance", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
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
  assert.equal(response.status, 200, path);
  return response.text();
}

function openingTags(html, tagName) {
  return [...html.matchAll(new RegExp(`<${tagName}\\b[^>]*>`, "gi"))].map(
    (match) => match[0],
  );
}

function pairedContents(html, tagName) {
  return [
    ...html.matchAll(
      new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)</${tagName}>`, "gi"),
    ),
  ].map((match) => match[1]);
}

function attributes(tag) {
  const result = new Map();
  const body = tag.replace(/^<[^\s>]+|\/?\s*>$/g, "");
  const pattern = /([^\s=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  for (const match of body.matchAll(pattern)) {
    result.set(match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? "");
  }
  return result;
}

function textContent(value) {
  return value
    .replace(/<script\b[\s\S]*?<\/script>/gi, "")
    .replace(/<style\b[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(?:nbsp|#x20);/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizedRoute(href) {
  const path = href.split(/[?#]/, 1)[0];
  if (path === "/") return path;
  return path.replace(/\/+$/, "");
}

before(async () => {
  for (const path of ROUTES) {
    pages.set(path, await render(path));
  }
});

test("all public-prelaunch and local routes expose deterministic accessible document metadata", () => {
  const titles = new Set();
  const descriptions = new Set();
  const headings = new Set();

  for (const path of ROUTES) {
    const html = pages.get(path);
    assert.equal(typeof html, "string", path);

    const htmlTags = openingTags(html, "html");
    assert.equal(htmlTags.length, 1, `${path}: html`);
    assert.equal(attributes(htmlTags[0]).get("lang"), "ja", `${path}: lang`);

    assert.equal(openingTags(html, "main").length, 1, `${path}: main`);
    assert.equal(
      openingTags(html, "main").filter(
        (tag) => attributes(tag).get("id") === "main-content",
      ).length,
      1,
      `${path}: skip target`,
    );

    const h1 = pairedContents(html, "h1").map(textContent);
    assert.equal(h1.length, 1, `${path}: h1 count`);
    assert.notEqual(h1[0], "", `${path}: h1 content`);
    assert.equal(headings.has(h1[0]), false, `${path}: unique h1`);
    headings.add(h1[0]);

    const title = pairedContents(html, "title").map(textContent);
    assert.equal(title.length, 1, `${path}: title count`);
    assert.notEqual(title[0], "", `${path}: title content`);
    assert.equal(titles.has(title[0]), false, `${path}: unique title`);
    titles.add(title[0]);

    const meta = openingTags(html, "meta").map(attributes);
    const viewport = meta.find(
      (item) => item.get("name")?.toLowerCase() === "viewport",
    );
    assert.ok(viewport, `${path}: viewport`);
    assert.match(viewport.get("content"), /\bwidth=device-width\b/i, path);

    const robots = meta.find(
      (item) => item.get("name")?.toLowerCase() === "robots",
    );
    assert.ok(robots, `${path}: robots`);
    for (const directive of ["noindex", "nofollow", "noarchive", "nosnippet"]) {
      assert.match(robots.get("content"), new RegExp(`\\b${directive}\\b`, "i"), path);
    }

    const description = meta.find(
      (item) => item.get("name")?.toLowerCase() === "description",
    );
    assert.ok(description, `${path}: description`);
    const descriptionText = description.get("content")?.trim();
    assert.ok(descriptionText, `${path}: non-empty description`);
    assert.equal(
      descriptions.has(descriptionText),
      false,
      `${path}: unique description`,
    );
    descriptions.add(descriptionText);
  }
});

test("every P01-P12 article renders PR disclosure before a disabled CTA", () => {
  assert.equal(ARTICLE_ROUTES.length, 12);
  for (const path of ARTICLE_ROUTES) {
    const html = pages.get(path);
    const disclosurePosition = html.indexOf('id="article-pr-disclosure"');
    const ctaPosition = html.indexOf('data-affiliate-cta-placeholder="mangools"');
    assert.ok(disclosurePosition >= 0, `${path}: PR disclosure`);
    assert.match(html, /記事制作に生成AIを補助的に使用する場合があります/, `${path}: AI assistance disclosure`);
    assert.ok(ctaPosition > disclosurePosition, `${path}: disclosure before CTA`);
    assert.doesNotMatch(html, /rel=["'][^"']*sponsored/i, path);
  }
});

test("every servers candidate stays noindex, unranked, CTA-disabled, and disclosure-first", () => {
  assert.equal(SERVER_CANDIDATE_ROUTES.length, 20);
  for (const path of SERVER_CANDIDATE_ROUTES) {
    const html = pages.get(path);
    const disclosurePosition = html.indexOf('id="article-pr-disclosure"');
    const calculatorPosition = html.indexOf('data-server-template-step="calculator"');
    const ctaPosition = html.indexOf('data-server-template-step="cta_slot"');
    assert.ok(disclosurePosition >= 0 && disclosurePosition < calculatorPosition, `${path}: disclosure first`);
    assert.match(html, /記事制作に生成AIを補助的に使用する場合があります/, `${path}: AI assistance disclosure`);
    assert.ok(calculatorPosition < ctaPosition, `${path}: calculator before CTA`);
    if (path === SVR01_ROUTE) {
      assert.match(html, /確認済み(?:<!-- -->)?4(?:<!-- -->)?項目、未確認(?:<!-- -->)?6(?:<!-- -->)?項目、[\s\S]{0,40}該当なし(?:<!-- -->)?1(?:<!-- -->)?項目/, path);
      assert.match(html, /data-ranking-eligible="false"[\s\S]{0,400}<strong>未確認<\/strong>/, path);
      assert.match(html, /期間限定表示と更新額未確認が残るため、総額・順位・推奨は表示しません/, path);
    } else {
      assert.match(html, /承認済みのservers価格contractはまだありません/, path);
    }
    assert.match(html, /公開条件をすべて通過したpartnerがないためCTAは無効/, path);
    assert.doesNotMatch(html, /data-server-cta-mode="(?:single|comparison)"|rel=["'][^"']*sponsored/i, path);
  }
});

test("structured data includes only Human-approved known prices while every article remains noindex", () => {
  assert.equal(ARTICLE_ROUTES.length, 12);
  const approvedOfferCounts = new Map([
    ["/pilot/pricing-calculator", 1],
    ["/pilot/plan-comparison", 3],
    ["/pilot/alternatives", 1],
  ]);
  for (const path of ARTICLE_ROUTES) {
    const html = pages.get(path);
    const payloads = [...html.matchAll(
      /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi,
    )].map((match) => JSON.parse(match[1]));
    assert.equal(payloads.length, 1, `${path}: JSON-LD count`);
    const graph = payloads[0]["@graph"];
    assert.deepEqual(
      graph.map((item) => item["@type"]),
      ["Product", "FAQPage", "BreadcrumbList"],
      `${path}: required structured-data types`,
    );
    const expectedOffers = approvedOfferCounts.get(path) ?? 0;
    if (expectedOffers > 0) {
      assert.equal(graph[0].offers.length, expectedOffers, `${path}: approved price count`);
      assert.ok(graph[0].offers.every((offer) => offer.price && offer.priceCurrency), `${path}: known approved prices only`);
    } else {
      assert.equal("offers" in graph[0], false, `${path}: unapproved price excluded`);
      assert.doesNotMatch(JSON.stringify(payloads[0]), /"price"\s*:/i, `${path}: no price markup`);
    }
  }
});

test("navigation, skip links, and every rendered link stay internal and valid", () => {
  for (const path of ROUTES) {
    const html = pages.get(path);
    const navs = openingTags(html, "nav");
    assert.ok(navs.length >= 2, `${path}: labelled header and footer navigation`);
    for (const nav of navs) {
      assert.ok(attributes(nav).get("aria-label")?.trim(), `${path}: nav label`);
    }

    const anchors = openingTags(html, "a");
    const skipLinks = anchors.filter((tag) =>
      (attributes(tag).get("class") ?? "").split(/\s+/).includes("skip-link"),
    );
    assert.equal(skipLinks.length, 1, `${path}: skip link count`);
    assert.equal(attributes(skipLinks[0]).get("href"), "#main-content", path);

    for (const anchor of anchors) {
      const href = attributes(anchor).get("href");
      assert.ok(href, `${path}: link without href`);
      if (href.startsWith("#")) {
        const target = href.slice(1);
        assert.match(html, new RegExp(`\\bid=["']${target}["']`, "i"), `${path}: ${href}`);
        continue;
      }
      if (/^https:\/\//i.test(href)) {
        const external = new URL(href);
        assert.equal(path, SVR01_ROUTE, `${path}: unexpected external evidence link`);
        assert.equal(ALLOWED_EVIDENCE_HOSTS.has(external.hostname), true, `${path}: external evidence host`);
        assert.equal(external.search, "", `${path}: evidence link query`);
        assert.equal(external.hash, "", `${path}: evidence link fragment`);
        const rel = (attributes(anchor).get("rel") ?? "").split(/\s+/);
        assert.ok(rel.includes("noopener") && rel.includes("noreferrer"), `${path}: external evidence rel`);
        assert.equal(rel.includes("sponsored"), false, `${path}: evidence link is not CTA`);
        continue;
      }
      assert.equal(href.startsWith("/"), true, `${path}: non-internal link ${href}`);
      assert.equal(href.startsWith("//"), false, `${path}: protocol-relative link`);
      assert.equal(
        ROUTE_PATHS.has(normalizedRoute(href)),
        true,
        `${path}: broken internal link ${href}`,
      );
    }
  }
});

test("comparison tables expose captions, scoped headers, adjacent disclosure, and disabled CTA", () => {
  for (const path of ["/", "/comparison"]) {
    const html = pages.get(path);
    const tables = pairedContents(html, "table");
    assert.equal(tables.length, 1, `${path}: table count`);

    const captions = pairedContents(tables[0], "caption").map(textContent);
    assert.equal(captions.length, 1, `${path}: caption count`);
    assert.notEqual(captions[0], "", `${path}: caption content`);

    const headers = openingTags(tables[0], "th").map(attributes);
    assert.ok(headers.filter((item) => item.get("scope") === "col").length >= 5, path);
    assert.ok(headers.filter((item) => item.get("scope") === "row").length >= 1, path);
    assert.equal(
      headers.every((item) => ["col", "row"].includes(item.get("scope"))),
      true,
      `${path}: every th has scope`,
    );

    const scroller = openingTags(html, "div").find((tag) =>
      (attributes(tag).get("class") ?? "").split(/\s+/).includes("table-scroll"),
    );
    assert.ok(scroller, `${path}: table scroller`);
    assert.equal(attributes(scroller).get("tabindex"), "0", path);
    assert.match(attributes(scroller).get("aria-label"), /横スクロール/, path);

    const disclosure = openingTags(html, "p").find(
      (tag) => attributes(tag).get("id") === "comparison-ad-disclosure",
    );
    assert.ok(disclosure, `${path}: adjacent affiliate disclosure`);
    assert.ok(html.indexOf(disclosure) < html.indexOf("<table"), path);
    assert.match(html, /アフィリエイトリンクはなく/);
    assert.match(html, /送客CTAは無効/);

    const disabledCtas = openingTags(html, "span").filter((tag) =>
      (attributes(tag).get("class") ?? "").split(/\s+/).includes("cta-disabled"),
    );
    assert.ok(disabledCtas.length >= 1, `${path}: disabled CTA`);
    for (const cta of disabledCtas) {
      assert.equal(
        attributes(cta).get("aria-describedby"),
        "comparison-ad-disclosure",
        `${path}: CTA disclosure binding`,
      );
    }
  }
});

test("pre-public HTML contains no canonical, runtime origin, tracking URL, or active CTA", () => {
  for (const path of ROUTES) {
    const html = pages.get(path);
    assert.doesNotMatch(
      html,
      /google-site-verification|googletagmanager|google-analytics|data-saastco-analytics-consent/i,
      `${path}: runtime measurement controls must be absent without approved env`,
    );
    for (const link of openingTags(html, "link").map(attributes)) {
      const rel = (link.get("rel") ?? "").toLowerCase().split(/\s+/);
      assert.equal(rel.includes("canonical"), false, `${path}: canonical`);
    }
    const htmlWithoutScripts = html.replace(/<script\b[\s\S]*?<\/script>/gi, "");
    const externalTextUrls = [...htmlWithoutScripts.matchAll(/https:\/\/([^\s<]+)/gi)];
    for (const match of externalTextUrls) {
      const host = match[1].replace(/\/$/, "").split("/")[0];
      assert.equal(ALLOWED_EVIDENCE_HOSTS.has(host), true, `${path}: unapproved external evidence host ${host}`);
    }
    assert.doesNotMatch(html, /saas-tco-lab-jp\.shukun0930\.chatgpt\.site/i, `${path}: runtime origin`);
    assert.doesNotMatch(html, /[?&](?:utm_|ref|aff|partner|clickid|subid)/i, `${path}: tracking URL`);
    assert.doesNotMatch(html, /\brel=["'][^"']*sponsored/i, `${path}: sponsored link`);
    assert.doesNotMatch(html, /公式サイトへ|affiliate[_-]?url/i, `${path}: active CTA`);
  }
});

test("every article exposes text-only Open Graph and Twitter metadata", () => {
  for (const path of ARTICLE_ROUTES) {
    const html = pages.get(path);
    assert.match(html, /<meta property="og:title" content="[^"]+"\/>/i, path);
    assert.match(html, /<meta property="og:description" content="[^"]+"\/>/i, path);
    assert.match(html, /<meta property="og:url" content="https:\/\/saastcolab\.jp\/pilot\/[^"/]+"\/>/i, path);
    assert.match(html, /<meta property="og:site_name" content="SaaS TCO Lab"\/>/i, path);
    assert.match(html, /<meta property="og:type" content="article"\/>/i, path);
    assert.match(html, /<meta name="twitter:card" content="summary"\/>/i, path);
    assert.match(html, /<meta name="twitter:title" content="[^"]+"\/>/i, path);
    assert.match(html, /<meta name="twitter:description" content="[^"]+"\/>/i, path);
    assert.doesNotMatch(html, /property="og:image"|name="twitter:image"/i, path);
  }
});

test("article metadata and internal links use the canonical no-trailing-slash form", () => {
  for (const path of ARTICLE_ROUTES) {
    const html = pages.get(path);
    const ogUrl = html.match(/<meta property="og:url" content="([^"]+)"\/>/i)?.[1];
    assert.equal(ogUrl, `https://saastcolab.jp${path}`, `${path}: Open Graph URL`);

    for (const anchor of openingTags(html, "a")) {
      const href = attributes(anchor).get("href");
      if (!href?.startsWith("/") || href === "/") continue;
      const pathname = href.split(/[?#]/, 1)[0];
      assert.equal(pathname.endsWith("/"), false, `${path}: redirecting internal link ${href}`);
    }
  }
});

test("static CSS preserves mobile reflow, keyboard focus, and reduced motion", async () => {
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  const at900 = css.indexOf("@media (max-width: 900px)");
  const at620 = css.indexOf("@media (max-width: 620px)");
  const atReduced = css.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.ok(at900 >= 0 && at620 > at900 && atReduced > at620, "ordered media guards");

  const desktopToTablet = css.slice(at900, at620);
  assert.match(desktopToTablet, /\.hero\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(desktopToTablet, /\.methodology-layout\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(desktopToTablet, /\.readiness-board li\s*\{[^}]*grid-template-columns:/s);

  const mobile = css.slice(at620, atReduced);
  assert.match(mobile, /\.shell\s*\{[^}]*width:\s*min\(100% - 28px, 1180px\)/s);
  assert.match(mobile, /\.comparison-toolbar\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(mobile, /\.process-grid\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(mobile, /\.conditions-grid\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(mobile, /\.policy-cards\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(mobile, /\.target-band dl\s*\{[^}]*grid-template-columns:\s*1fr/s);

  const minWidthRules = [...css.matchAll(/([^{}]+)\{([^{}]*\bmin-width\s*:[^{}]*)\}/g)].map(
    (match) => match[1].trim(),
  );
  assert.deepEqual(minWidthRules, ["table", "tbody th", "td"]);
  assert.doesNotMatch(css, /(?:html|body)\s*\{[^}]*overflow-x\s*:\s*hidden/is);
  assert.match(css, /\.table-scroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.table-scroll\s*\{[^}]*overscroll-behavior-inline:\s*contain/s);

  assert.match(
    css,
    /:where\(a, button, \[tabindex\]\):focus-visible\s*\{[^}]*outline:\s*3px solid/s,
  );
  assert.match(css, /\.skip-link:focus\s*\{[^}]*transform:\s*translateY\(0\)/s);

  const reducedMotion = css.slice(atReduced);
  assert.match(reducedMotion, /html\s*\{[^}]*scroll-behavior:\s*auto/s);
  assert.match(reducedMotion, /animation-duration:\s*0\.01ms\s*!important/);
  assert.match(reducedMotion, /animation-iteration-count:\s*1\s*!important/);
  assert.match(reducedMotion, /transition-duration:\s*0\.01ms\s*!important/);
});
