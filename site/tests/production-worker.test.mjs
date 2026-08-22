import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile, readdir } from "node:fs/promises";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import test, { after, before } from "node:test";
import vm from "node:vm";

const siteRoot = fileURLToPath(new URL("../", import.meta.url));
const verifyProductionBuild = fileURLToPath(
  new URL("../scripts/verify-production-build.mjs", import.meta.url),
);
const wranglerCli = fileURLToPath(
  new URL("../node_modules/wrangler/bin/wrangler.js", import.meta.url),
);
let baseUrl;
let serverProcess;
let serverOutput = "";

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
].map((slug, index) => index === 0 ? "/servers/business-server-pricing" : `/servers/${slug}`);

function visibleMarkup(html) {
  return html.replace(/<script\b[\s\S]*?<\/script>/gi, "");
}

function robotsMetaCount(html) {
  return (
    html.match(/<meta\b(?=[^>]*\bname\s*=\s*["']robots["'])[^>]*>/gi) ?? []
  ).length;
}

function robotsAllows(robotsText, targetPath) {
  const rules = robotsText
    .split("\n")
    .map((line) => line.match(/^(Allow|Disallow):\s*(\S*)$/i))
    .filter(Boolean)
    .map((match) => ({ kind: match[1].toLowerCase(), pattern: match[2] }));
  const matches = rules.filter(({ pattern }) => {
    const anchored = pattern.endsWith("$");
    const source = anchored ? pattern.slice(0, -1) : pattern;
    return anchored ? targetPath === source : targetPath.startsWith(source);
  });
  matches.sort((left, right) => {
    const specificity = right.pattern.length - left.pattern.length;
    if (specificity !== 0) return specificity;
    return left.kind === "allow" ? -1 : 1;
  });
  return matches[0]?.kind === "allow";
}

function signalServerGroup(signal) {
  if (!serverProcess?.pid) return;
  try {
    if (process.platform === "win32") {
      serverProcess.kill(signal);
    } else {
      process.kill(-serverProcess.pid, signal);
    }
  } catch (error) {
    if (error?.code !== "ESRCH") throw error;
  }
}

function serverGroupIsRunning() {
  if (!serverProcess?.pid) return false;
  if (serverProcess.exitCode !== null || serverProcess.signalCode !== null) return false;
  if (process.platform === "win32") {
    return true;
  }
  try {
    process.kill(-serverProcess.pid, 0);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return false;
    throw error;
  }
}

async function waitForServerGroupToStop(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!serverGroupIsRunning()) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return !serverGroupIsRunning();
}

async function availablePort() {
  const probe = createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const address = probe.address();
  assert.notEqual(address, null);
  assert.equal(typeof address, "object");
  const port = address.port;
  probe.close();
  await once(probe, "close");
  return port;
}

async function waitForServer(url) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (serverProcess.exitCode !== null) {
      throw new Error(`production server exited early:\n${serverOutput}`);
    }
    try {
      const response = await fetch(`${url}/healthz`);
      if (response.status === 200) return;
    } catch {
      // Startup races are expected; retry until the bounded deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`production server did not become ready:\n${serverOutput}`);
}

before(async () => {
  const port = await availablePort();
  baseUrl = `http://127.0.0.1:${port}`;
  const verification = spawn(
    process.execPath,
    [verifyProductionBuild],
    {
      cwd: siteRoot,
      env: { ...process.env, SAAS_RUNTIME_MODE: "production" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let verificationOutput = "";
  verification.stdout.on("data", (chunk) => {
    verificationOutput += chunk.toString();
  });
  verification.stderr.on("data", (chunk) => {
    verificationOutput += chunk.toString();
  });
  const [verificationExitCode] = await once(verification, "exit");
  assert.equal(
    verificationExitCode,
    0,
    `production build verification failed:\n${verificationOutput}`,
  );
  serverProcess = spawn(
    process.execPath,
    [
      wranglerCli,
      "dev",
      "--config",
      "dist/server/wrangler.json",
      "--port",
      String(port),
      "--ip",
      "127.0.0.1",
      "--var",
      "IMPACT_SITE_VERIFICATION:test-impact-verification-value",
      "--var",
      "GOOGLE_SITE_VERIFICATION:test-google-site-verification-value",
      "--var",
      "GA4_ANALYTICS_ENABLED:true",
      "--var",
      "GA4_MEASUREMENT_ID:G-TEST123456",
      "--var",
      "INDEX_GO:GO",
      "--var",
      "INDEX_APPROVED_ARTICLES:P01,P02,P03,P06,P07",
      "--var",
      "CTA_GO:GO",
      "--var",
      "CTA_APPROVED_PARTNER:mangools",
      "--var",
      "MANGOOLS_AFFILIATE_APPROVAL_CURRENT:true",
      "--var",
      "MANGOOLS_AFFILIATE_DESTINATION:https://mangools.com/#a1234567890bcdef123456789",
    ],
    {
      cwd: siteRoot,
      env: { ...process.env, SAAS_RUNTIME_MODE: "production" },
      stdio: ["ignore", "pipe", "pipe"],
      detached: process.platform !== "win32",
    },
  );
  serverProcess.stdout.on("data", (chunk) => {
    serverOutput += chunk.toString();
  });
  serverProcess.stderr.on("data", (chunk) => {
    serverOutput += chunk.toString();
  });
  await waitForServer(baseUrl);
});

after(async () => {
  if (!serverProcess) return;
  signalServerGroup("SIGTERM");
  if (!(await waitForServerGroupToStop(3_000))) {
    signalServerGroup("SIGKILL");
  }
  assert.equal(
    await waitForServerGroupToStop(3_000),
    true,
    `production server process group did not stop:\n${serverOutput}`,
  );
});

test("built production config exposes only the public-prelaunch allowlist", async () => {
  const config = JSON.parse(
    await readFile(new URL("../dist/server/wrangler.json", import.meta.url), "utf8"),
  );
  assert.equal(config.assets.run_worker_first, true);

  const assetNames = await readdir(
    new URL("../dist/client/assets/", import.meta.url),
  );
  const javascriptAsset = assetNames.find((name) => name.endsWith(".js"));
  assert.ok(javascriptAsset, "production build must contain a real JS asset");

  for (const path of [
    "/",
    "/methodology",
    "/disclosure",
    "/pilot",
    "/pilot/annual-vs-monthly",
    "/pilot/migration-cost",
    "/pilot/evidence-method",
    "/pilot/pricing-calculator",
    "/pilot/plan-comparison",
    "/pilot/alternatives",
    "/pilot/small-team-fit",
    "/pilot/enterprise-fit",
    "/pilot/usage-overage",
    "/pilot/addon-cost",
    "/pilot/japan-tax",
    "/pilot/break-even",
    "/about",
    "/operator-information",
    "/privacy",
    "/contact",
    "/advertising-policy",
    "/embed/tco-calculator",
    ...SERVER_CANDIDATE_PATHS,
  ]) {
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 200, path);
    const body = await response.text();
    const documentHtml = body.slice(0, body.lastIndexOf("</html>") + "</html>".length);
    assert.match(body, /SaaS TCO Lab/i, path);
    assert.match(
      body,
      /<meta name="impact-site-verification" value="test-impact-verification-value">/i,
      path,
    );
    assert.match(
      body,
      /<meta name="google-site-verification" content="test-google-site-verification-value">/i,
      path,
    );
    assert.match(body, /<script data-saastco-analytics-consent>/i, path);
    assert.match(body, /<script data-saastco-funnel-measurement>/i, path);
    assert.match(body, /G-TEST123456/, path);
    assert.match(body, /dataLayer\.push\(arguments\)/, path);
    assert.match(body, /calculator_result_view/, path);
    assert.match(body, /cta_view/, path);
    assert.match(body, /cta_eligible_session/, path);
    assert.match(body, /server_internal_funnel/, path);
    assert.match(body, /同意するまでGoogleへの通信は行いません/, path);
    const head = body.match(/<head(?:\s[^>]*)?>([\s\S]*?)<\/head>/i);
    assert.ok(head, `${path}: head`);
    const firstMeta = head[1].match(/<meta\b[^>]*>/i);
    assert.ok(firstMeta, `${path}: first meta`);
    assert.match(
      firstMeta[0],
      /name="impact-site-verification" value="test-impact-verification-value"/i,
      `${path}: verification must be the first meta tag`,
    );
    assert.ok(
      body.indexOf('name="impact-site-verification"') <
        body.indexOf('name="google-site-verification"'),
      `${path}: Impact verification must stay before GSC verification`,
    );
    assert.doesNotMatch(body, /href=["']\/(?:comparison|learning|readiness|operator|pilot)\/?["']/i, path);
    assert.doesNotMatch(body, /href=["']\/operator(?:\/|["'])/i, path);
    const approvedArticlePaths = new Set([
      "/pilot/pricing-calculator",
      "/pilot/plan-comparison",
      "/pilot/alternatives",
      "/pilot/annual-vs-monthly",
      "/pilot/usage-overage",
    ]);
    const followableNonArticlePaths = new Set([
      "/",
      "/pilot",
      "/methodology",
      "/disclosure",
      "/about",
      "/operator-information",
      "/privacy",
      "/contact",
      "/advertising-policy",
      "/embed/tco-calculator",
    ]);
    const heldArticlePaths = new Set([
      "/servers/business-server-pricing",
      "/servers/server-renewal-cost",
      "/servers/server-first-year-total",
      "/servers/server-migration-cost",
      "/servers/business-rental-server",
      "/servers/small-business-server",
      "/servers/ec-server-cost",
      "/servers/business-mail-server",
      "/servers/ec-server-requirements",
      "/pilot/small-team-fit",
      "/pilot/enterprise-fit",
      "/pilot/addon-cost",
      "/pilot/migration-cost",
      "/pilot/japan-tax",
      "/pilot/break-even",
      "/pilot/evidence-method",
    ]);
    if (approvedArticlePaths.has(path)) {
      assert.equal(response.headers.get("x-robots-tag"), "index, follow", path);
      assert.match(body, /<meta name="robots" content="index, follow">/i, path);
      assert.match(
        body,
        new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${path}">`, "i"),
        path,
      );
      const visible = visibleMarkup(documentHtml);
      const disclosurePosition = visible.indexOf('data-affiliate-disclosure-status="disabled"');
      const ctaPosition = visible.indexOf('data-affiliate-cta-placeholder="mangools"');
      assert.ok(disclosurePosition >= 0, `${path}: fail-closed disclosure before hydration`);
      assert.ok(ctaPosition > disclosurePosition, `${path}: disclosure before CTA placeholder`);
      assert.match(documentHtml, /この記事にはMangoolsのアフィリエイトリンクが含まれます。/i, path);
      assert.match(visible, /data-affiliate-cta-state="disabled"/i, path);
      assert.match(
        documentHtml,
        /data-saastco-affiliate-cta>[\s\S]*https:\/\/mangools\.com\/#a1234567890bcdef123456789[\s\S]*sponsored noopener noreferrer/i,
        path,
      );
      assert.match(documentHtml, /<script data-saastco-affiliate-cta>/i, path);
      assert.match(documentHtml, /compareDocumentPosition\(c\)&Node\.DOCUMENT_POSITION_FOLLOWING/i, path);
      assert.match(documentHtml, /d\.textContent!==dt/i, path);
      assert.match(documentHtml, /s\.textContent!==st/i, path);
      assert.doesNotMatch(visible, /data-affiliate-cta-partner|rel="sponsored noopener noreferrer"/i, path);
      const nextReadingPosition = documentHtml.indexOf('class="shell page-section next-reading"');
      assert.ok(nextReadingPosition > ctaPosition, `${path}: next-to-read after CTA`);
      const nextReading = documentHtml.slice(nextReadingPosition, documentHtml.indexOf("</section>", nextReadingPosition));
      assert.match(nextReading, /href="\/pilot\/(?:pricing-calculator|plan-comparison|alternatives|annual-vs-monthly|usage-overage)"/i, path);
      assert.doesNotMatch(nextReading, /small-team-fit|enterprise-fit|addon-cost|migration-cost/i, path);
      assert.doesNotMatch(visible, />CTA DISABLED</i, path);
    } else if (followableNonArticlePaths.has(path) || heldArticlePaths.has(path)) {
      assert.equal(
        response.headers.get("x-robots-tag"),
        "noindex, follow, noarchive, nosnippet",
        path,
      );
      assert.match(
        body,
        /<meta name="robots" content="noindex, follow, noarchive, nosnippet">/i,
        path,
      );
      assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i, path);
      assert.doesNotMatch(visibleMarkup(documentHtml), /rel=["'][^"']*sponsored|data-affiliate-cta-partner/i, path);
      assert.doesNotMatch(documentHtml, /data-saastco-affiliate-cta/i, path);
      if (path === "/servers/business-server-pricing") {
        const externalEvidenceLinks = [
          ...documentHtml.matchAll(/<a\b[^>]*href="(https?:\/\/[^"#?]+)"[^>]*>/gi),
        ];
        assert.ok(externalEvidenceLinks.length > 0, `${path}: official evidence links`);
        for (const [, href] of externalEvidenceLinks) {
          const evidenceUrl = new URL(href);
          assert.equal(evidenceUrl.hostname, "business.xserver.ne.jp", `${path}: evidence host`);
          assert.equal(evidenceUrl.search, "", `${path}: evidence query`);
          assert.equal(evidenceUrl.hash, "", `${path}: evidence fragment`);
        }
        for (const [anchor] of externalEvidenceLinks) {
          const rel = anchor.match(/\brel="([^"]*)"/i)?.[1]?.split(/\s+/) ?? [];
          assert.ok(rel.includes("noopener") && rel.includes("noreferrer"), `${path}: evidence rel`);
          assert.equal(rel.includes("sponsored"), false, `${path}: evidence is not CTA`);
        }
      }
      if (path === "/") {
        for (const approvedPath of [
          "/pilot/pricing-calculator",
          "/pilot/plan-comparison",
          "/pilot/alternatives",
          "/pilot/annual-vs-monthly",
          "/pilot/usage-overage",
        ]) {
          assert.match(documentHtml, new RegExp(`href=["']${approvedPath}["']`, "i"), approvedPath);
        }
        for (const heldPath of [
          "/servers/business-server-pricing",
          "/pilot/small-team-fit",
          "/pilot/enterprise-fit",
          "/pilot/addon-cost",
          "/pilot/migration-cost",
          "/pilot/japan-tax",
          "/pilot/break-even",
          "/pilot/evidence-method",
        ]) {
          assert.doesNotMatch(documentHtml, new RegExp(`href=["']${heldPath}["']`, "i"), heldPath);
        }
      }
    } else {
      assert.equal(
        response.headers.get("x-robots-tag"),
        "noindex, nofollow, noarchive, nosnippet",
        path,
      );
      assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i, path);
      assert.doesNotMatch(documentHtml, /rel=["'][^"']*sponsored|data-affiliate-cta-partner/i, path);
      assert.doesNotMatch(documentHtml, /<a\b[^>]*href=["']https?:\/\//i, path);
      assert.doesNotMatch(documentHtml, /data-saastco-affiliate-cta/i, path);
    }
    const csp = response.headers.get("content-security-policy");
    assert.match(csp, /script-src[^;]*https:\/\/www\.googletagmanager\.com/i, path);
    assert.match(csp, /connect-src[^;]*https:\/\/www\.google-analytics\.com/i, path);
    if (path === "/embed/tco-calculator") {
      assert.match(csp, /frame-ancestors https:/i, path);
    } else {
      assert.match(csp, /frame-ancestors 'none'/i, path);
    }
  }

  for (const path of [`/assets/${javascriptAsset}`, "/favicon.svg"]) {
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get("cache-control"), "no-store", path);
  }

  for (const path of [
    "/comparison",
    "/learning",
    "/readiness",
    "/operator",
    "/missing",
  ]) {
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 503, path);
    const body = await response.text();
    assert.equal(body, "Service Unavailable\n", path);
    assert.doesNotMatch(body, /JPY|SaaS|synthetic|affiliate/i, path);
    assert.doesNotMatch(body, /google-site-verification|googletagmanager|G-TEST123456/i, path);
    assert.equal(response.headers.get("cache-control"), "no-store", path);
  }
});

test("public trust pages derive their article and CTA state from runtime gates", async () => {
  const homeResponse = await (await fetch(`${baseUrl}/`)).text();
  const home = homeResponse.slice(0, homeResponse.lastIndexOf("</html>") + "</html>".length);
  assert.match(home, /PUBLIC EDITORIAL/);
  assert.match(home, /公開記事[\s\S]{0,80}5[\s\S]{0,20}本/);
  assert.match(home, /対象カテゴリ[\s\S]{0,80}1カテゴリ/);
  assert.match(home, /紹介導線[\s\S]{0,80}1カテゴリ稼働/);
  assert.doesNotMatch(home, /href="\/servers\/business-server-pricing"/);
  assert.match(home, /href="\/pilot\/pricing-calculator"/);
  assert.match(home, /href="\/pilot\/plan-comparison"/);
  assert.doesNotMatch(home, /href="\/pilot\/evidence-method"/);
  assert.doesNotMatch(home, /href="\/pilot\/migration-cost"/);
  assert.match(home, /href="\/pilot\/alternatives"/);
  assert.doesNotMatch(home, /href="\/pilot\/small-team-fit"/);
  assert.doesNotMatch(home, /href="\/pilot\/enterprise-fit"/);
  assert.doesNotMatch(home, /href="\/pilot\/addon-cost"/);
  assert.doesNotMatch(home, /href="\/pilot\/japan-tax"/);
  assert.doesNotMatch(home, /PUBLIC PRELAUNCH|広告リンク[\s\S]{0,50}0件|実在サービスの価格・評価・送客リンクは表示していません/);

  const disclosure = await (await fetch(`${baseUrl}/disclosure/`)).text();
  assert.match(disclosure, /広告状態は記事ごとに表示/);
  assert.match(disclosure, /全条件が一致した記事だけで紹介リンクを有効/);
  assert.doesNotMatch(disclosure, /実アフィリエイトリンクを含みません|公開承認済みAffiliate CTA 0件/);

  const about = await (await fetch(`${baseUrl}/about/`)).text();
  assert.match(about, /Human承認済みの記事を公開/);
  assert.doesNotMatch(about, /現在は公開前のnoindex運用/);

  const operator = await (await fetch(`${baseUrl}/operator-information/`)).text();
  assert.match(operator, /2026年8月9日/);
  assert.doesNotMatch(operator, /審査・公開前確認用/);

  const privacy = await (await fetch(`${baseUrl}/privacy/`)).text();
  assert.match(privacy, /有効な広告リンクの遷移先事業者/);
  assert.doesNotMatch(privacy, /将来、有効な広告リンクを利用する場合/);
});

test("current release home links every approved article and reports two live CTA categories", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("home-current-release", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
    SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01",
    SERVER_CTA_GO: "a8net-xserver-business",
    A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
    A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
  };
  const response = await worker.fetch(
    new Request("https://saastcolab.jp/"),
    env,
    { waitUntil() {}, passThroughOnException() {} },
  );
  const raw = await response.text();
  const home = raw.slice(0, raw.lastIndexOf("</html>") + "</html>".length);
  assert.match(home, /公開記事[\s\S]{0,80}12本/);
  assert.match(home, /対象カテゴリ[\s\S]{0,80}2カテゴリ/);
  assert.match(home, /紹介導線[\s\S]{0,80}2カテゴリ稼働/);
  const expectedPaths = [
    "/servers/business-server-pricing",
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
    "/pilot/evidence-method",
  ];
  for (const path of expectedPaths) {
    assert.match(home, new RegExp(`data-public-article-path=["']${path}["']`), path);
    assert.match(home, new RegExp(`href=["']${path}["']`), path);
  }
  assert.doesNotMatch(home, /href=["']\/pilot\/break-even["']/);
});

test("production exposes a deterministic tracking-free calculator loader", async () => {
  const response = await fetch(`${baseUrl}/embed/tco-calculator.js`);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /application\/javascript/i);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
  const body = await response.text();
  assert.match(body, /\/embed\/tco-calculator"/);
  assert.match(body, /document\.currentScript/);
  assert.doesNotMatch(body, /utm_|affiliate|partner|clickid|subid|cookie/i);
});

test("Googlebot can fetch every asset referenced by an approved article", async () => {
  const article = await fetch(`${baseUrl}/pilot/pricing-calculator`);
  assert.equal(article.status, 200);
  const html = await article.text();
  const assetPaths = [...new Set(
    [...html.matchAll(/(?:href|src)=["'](\/assets\/[^"']+)["']/g)].map((match) => match[1]),
  )];
  assert.ok(assetPaths.some((path) => path.endsWith(".css")), "approved article must reference CSS");
  assert.ok(assetPaths.some((path) => path.endsWith(".js")), "approved article must reference JavaScript");

  for (const path of [...assetPaths, "/favicon.svg"]) {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: { "User-Agent": "Googlebot" },
    });
    assert.equal(response.status, 200, path);
    assert.match(
      response.headers.get("content-type") ?? "",
      path.endsWith(".css")
        ? /text\/css/i
        : path.endsWith(".js")
          ? /(?:text|application)\/javascript/i
          : /image\/svg\+xml/i,
      path,
    );
  }
});

test("actual production health exposes only a fixed non-sensitive response", async () => {
  const response = await fetch(`${baseUrl}/healthz`);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "ok\n");
  assert.equal(response.headers.get("x-index-approval-active"), "true");
  assert.equal(response.headers.get("x-index-articles-config-valid"), "true");
  assert.equal(response.headers.get("x-index-server-articles-config-valid"), "true");
  assert.equal(
    response.headers.get("x-robots-tag"),
    "noindex, nofollow, noarchive, nosnippet",
  );
});

test("legacy public origin redirects once to the canonical host without changing route data", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("legacy-redirect", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request(
      "https://saas-tco-lab-jp.shukun0930.chatgpt.site/pilot/pricing-calculator?view=source",
    ),
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

  assert.equal(response.status, 301);
  assert.equal(
    response.headers.get("location"),
    "https://saastcolab.jp/pilot/pricing-calculator?view=source",
  );
  assert.match(response.headers.get("x-robots-tag"), /\bnoindex\b/i);
});

test("production robots and sitemap expose only the five approved articles", async () => {
  const response = await fetch(`${baseUrl}/robots.txt`);
  assert.equal(response.status, 200);
  assert.equal(
    await response.text(),
    "User-agent: *\n" +
      "Allow: /$\n" +
      "Allow: /assets/\n" +
      "Allow: /favicon.svg$\n" +
      "Allow: /sitemap.xml$\n" +
      "Allow: /about$\n" +
      "Allow: /advertising-policy$\n" +
      "Allow: /contact$\n" +
      "Allow: /disclosure$\n" +
      "Allow: /embed/tco-calculator$\n" +
      "Allow: /methodology$\n" +
      "Allow: /operator-information$\n" +
      "Allow: /pilot$\n" +
      "Allow: /pilot/alternatives$\n" +
      "Allow: /pilot/annual-vs-monthly$\n" +
      "Allow: /pilot/plan-comparison$\n" +
      "Allow: /pilot/pricing-calculator$\n" +
      "Allow: /pilot/usage-overage$\n" +
      "Allow: /privacy$\n" +
      "Disallow: /\n" +
      "Sitemap: https://saastcolab.jp/sitemap.xml\n",
  );

  const sitemap = await fetch(`${baseUrl}/sitemap.xml`);
  assert.equal(sitemap.status, 200);
  assert.match(sitemap.headers.get("content-type"), /application\/xml/i);
  const xml = await sitemap.text();
  const locations = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  assert.deepEqual(locations, [
    "https://saastcolab.jp/pilot/pricing-calculator",
    "https://saastcolab.jp/pilot/plan-comparison",
    "https://saastcolab.jp/pilot/alternatives",
    "https://saastcolab.jp/pilot/annual-vs-monthly",
    "https://saastcolab.jp/pilot/usage-overage",
  ]);
  assert.doesNotMatch(xml, /embed|small-team-fit|enterprise-fit|addon-cost|migration-cost|japan-tax|break-even|evidence-method|about|privacy|operator/i);
});

test("crawl permission and index permission remain separate release blockers", async () => {
  const robotsResponse = await fetch(`${baseUrl}/robots.txt`);
  const robotsText = await robotsResponse.text();
  const crawlableNoindexRoutes = [
    "/",
    "/about",
    "/advertising-policy",
    "/contact",
    "/disclosure",
    "/embed/tco-calculator",
    "/methodology",
    "/operator-information",
    "/pilot",
    "/privacy",
  ];
  for (const path of crawlableNoindexRoutes) {
    assert.equal(robotsAllows(robotsText, path), true, `${path}: crawl allowed`);
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 200, path);
    assert.equal(
      response.headers.get("x-robots-tag"),
      "noindex, follow, noarchive, nosnippet",
      `${path}: remains noindex follow`,
    );
    assert.match(
      await response.text(),
      /<meta name="robots" content="noindex, follow, noarchive, nosnippet">/i,
      path,
    );
  }

  const approvedPath = "/pilot/pricing-calculator";
  assert.equal(robotsAllows(robotsText, approvedPath), true, "approved article crawl allowed");
  const approved = await fetch(`${baseUrl}${approvedPath}`);
  assert.equal(approved.headers.get("x-robots-tag"), "index, follow");
  assert.match(await approved.text(), /<meta name="robots" content="index, follow">/i);

  const heldPath = "/pilot/break-even";
  assert.equal(robotsAllows(robotsText, heldPath), false, "unapproved article crawl blocked");
  const held = await fetch(`${baseUrl}${heldPath}`);
  assert.equal(held.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");
  assert.match(
    await held.text(),
    /<meta name="robots" content="noindex, follow, noarchive, nosnippet">/i,
  );

  const heldServerPath = "/servers/server-renewal-cost";
  assert.equal(robotsAllows(robotsText, heldServerPath), false, "approved but unreleased server article crawl blocked");
  const heldServer = await fetch(`${baseUrl}${heldServerPath}`);
  assert.equal(heldServer.status, 200);
  assert.equal(heldServer.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");
  const heldServerBody = await heldServer.text();
  assert.match(heldServerBody, /data-server-article-review="approved"/);
  assert.match(heldServerBody, /data-server-candidate-batch="M3"/);
  assert.match(heldServerBody, /4(?:<!-- -->)?社・(?:<!-- -->)?44(?:<!-- -->)?項目/);
  assert.equal((heldServerBody.match(/data-ranking-eligible="true"/g) ?? []).length, 3);
  assert.match(heldServerBody, /JPY 48840/);
  assert.match(heldServerBody, /JPY 11220/);
  assert.doesNotMatch(heldServerBody, /rel="sponsored noopener noreferrer"/);

  const queryPath = `${approvedPath}?candidate=unapproved`;
  assert.equal(robotsAllows(robotsText, queryPath), false, "query variant crawl blocked");
  const queryVariant = await fetch(`${baseUrl}${queryPath}`);
  assert.equal(
    queryVariant.headers.get("x-robots-tag"),
    "noindex, nofollow, noarchive, nosnippet",
  );
  assert.match(
    await queryVariant.text(),
    /<meta name="robots" content="noindex,[^"]*"\s*\/?>/i,
  );
});

test("the approved nine-article release candidate stays scoped and disclosure-first", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("nine-article-release", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    IMPACT_SITE_VERIFICATION: "test-impact-verification-value",
    GOOGLE_SITE_VERIFICATION: "test-google-site-verification-value",
    GA4_ANALYTICS_ENABLED: "true",
    GA4_MEASUREMENT_ID: "G-TEST123456",
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P06,P07,P08,P10,P12",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };
  const released = [
    "/pilot/pricing-calculator",
    "/pilot/plan-comparison",
    "/pilot/alternatives",
    "/pilot/small-team-fit",
    "/pilot/annual-vs-monthly",
    "/pilot/usage-overage",
    "/pilot/addon-cost",
    "/pilot/japan-tax",
    "/pilot/evidence-method",
  ];
  const held = [
    "/pilot/enterprise-fit",
    "/pilot/migration-cost",
    "/pilot/break-even",
  ];

  for (const path of released) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get("x-robots-tag"), "index, follow", path);
    const body = await response.text();
    assert.match(body, new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${path}">`, "i"), path);
    assert.match(body, new RegExp(`<meta property="og:url" content="https://saastcolab\\.jp${path}"`, "i"), path);
    for (const match of body.matchAll(/href="(\/[^"#?]*)(?:[#?][^"]*)?"/gi)) {
      assert.ok(match[1] === "/" || !match[1].endsWith("/"), `${path}: redirecting internal link ${match[1]}`);
    }
    const visible = visibleMarkup(body);
    const disclosure = visible.indexOf('data-affiliate-disclosure-status="disabled"');
    const cta = visible.indexOf('data-affiliate-cta-placeholder="mangools"');
    assert.ok(disclosure >= 0, `${path}: fail-closed disclosure before hydration`);
    assert.ok(cta > disclosure, `${path}: disclosure before CTA placeholder`);
    assert.match(body, /data-saastco-affiliate-cta>[\s\S]*rel="sponsored noopener noreferrer"/i, path);
    assert.doesNotMatch(visible, /data-affiliate-cta-partner|rel="sponsored noopener noreferrer"/i, path);
  }

  for (const path of held) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet", path);
    const body = await response.text();
    assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i, path);
    assert.doesNotMatch(visibleMarkup(body), /data-affiliate-cta-partner|rel=["'][^"']*sponsored/i, path);
  }

  const robots = await worker.fetch(new Request("https://saastcolab.jp/robots.txt"), env, ctx);
  const robotsText = await robots.text();
  for (const path of released) assert.match(robotsText, new RegExp(`Allow: ${path}\\$`));
  for (const path of held) assert.doesNotMatch(robotsText, new RegExp(`Allow: ${path}\\$`));
  assert.match(robotsText, /Allow: \/assets\//);
  assert.match(robotsText, /Allow: \/favicon\.svg\$/);
  assert.match(robotsText, /Disallow: \/$/m);

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  const xml = await sitemap.text();
  const locations = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  assert.equal(locations.length, released.length);
  assert.deepEqual(new Set(locations), new Set(released.map((path) => `https://saastcolab.jp${path}`)));
});

test("approved P05 is ready for an exact ten-article release without widening P09 or P11", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("p05-ten-article-release", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P10,P12",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  const p05Path = "/pilot/enterprise-fit";
  const p05 = await worker.fetch(new Request(`https://saastcolab.jp${p05Path}`), env, ctx);
  assert.equal(p05.status, 200);
  assert.equal(p05.headers.get("x-robots-tag"), "index, follow");
  const p05Body = await p05.text();
  assert.match(p05Body, new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${p05Path}">`, "i"));
  const p05Visible = visibleMarkup(p05Body);
  const disclosure = p05Visible.indexOf('data-affiliate-disclosure-status="disabled"');
  const cta = p05Visible.indexOf('data-affiliate-cta-placeholder="mangools"');
  assert.ok(disclosure >= 0);
  assert.ok(cta > disclosure);
  assert.match(p05Body, /data-saastco-affiliate-cta>[\s\S]*rel="sponsored noopener noreferrer"/i);
  assert.doesNotMatch(p05Visible, /data-affiliate-cta-partner|rel="sponsored noopener noreferrer"/i);

  const releasedPaths = [
    "/pilot/pricing-calculator",
    "/pilot/plan-comparison",
    "/pilot/alternatives",
    "/pilot/small-team-fit",
    "/pilot/enterprise-fit",
    "/pilot/annual-vs-monthly",
    "/pilot/usage-overage",
    "/pilot/addon-cost",
    "/pilot/japan-tax",
    "/pilot/evidence-method",
  ];
  const inboundCounts = new Map(releasedPaths.map((path) => [path, 0]));
  for (const path of releasedPaths) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    const body = await response.text();
    const nextReading = body.match(/<section\b[^>]*class="[^"]*next-reading[^"]*"[\s\S]*?<\/section>/i)?.[0] ?? "";
    const targets = [...nextReading.matchAll(/href="(\/pilot\/[^"/]+)"/gi)].map((match) => match[1]);
    assert.equal(targets.length, 3, `${path}: three next-reading links`);
    assert.ok(!targets.includes(path), `${path}: no self-link`);
    for (const target of targets) {
      assert.ok(inboundCounts.has(target), `${path}: only released targets`);
      inboundCounts.set(target, (inboundCounts.get(target) ?? 0) + 1);
    }
  }
  for (const [path, count] of inboundCounts) assert.ok(count > 0, `${path}: has inbound link`);

  for (const path of ["/pilot/migration-cost", "/pilot/break-even"]) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    assert.equal(response.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet", path);
    const body = await response.text();
    assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i, path);
    assert.doesNotMatch(body, /data-affiliate-cta-partner|rel=["'][^"']*sponsored/i, path);
  }

  const robots = await worker.fetch(new Request("https://saastcolab.jp/robots.txt"), env, ctx);
  const robotsText = await robots.text();
  assert.match(robotsText, /Allow: \/pilot\/enterprise-fit\$/);
  assert.doesNotMatch(robotsText, /Allow: \/pilot\/(migration-cost|break-even)\$/);

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  const xml = await sitemap.text();
  const locations = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  assert.equal(locations.length, 10);
  assert.ok(locations.includes("https://saastcolab.jp/pilot/enterprise-fit"));
  assert.ok(!locations.includes("https://saastcolab.jp/pilot/migration-cost"));
  assert.ok(!locations.includes("https://saastcolab.jp/pilot/break-even"));
});

test("approved P09 widens the release to exactly eleven articles while P11 stays fail-closed", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("p09-eleven-article-release", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  const p09Path = "/pilot/migration-cost";
  const p09 = await worker.fetch(new Request(`https://saastcolab.jp${p09Path}`), env, ctx);
  assert.equal(p09.status, 200);
  assert.equal(p09.headers.get("x-robots-tag"), "index, follow");
  const p09Body = await p09.text();
  assert.match(p09Body, new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${p09Path}">`, "i"));
  assert.match(p09Body, /JPY 2,006\.67/);
  assert.match(p09Body, /公式移行支援費は未確認/);
  const p09Visible = visibleMarkup(p09Body);
  const disclosure = p09Visible.indexOf('data-affiliate-disclosure-status="disabled"');
  const cta = p09Visible.indexOf('data-affiliate-cta-placeholder="mangools"');
  assert.ok(disclosure >= 0);
  assert.ok(cta > disclosure);
  assert.match(p09Body, /data-saastco-affiliate-cta>[\s\S]*rel="sponsored noopener noreferrer"/i);
  assert.doesNotMatch(p09Visible, /data-affiliate-cta-partner|rel="sponsored noopener noreferrer"/i);

  const p11Path = "/pilot/break-even";
  const p11 = await worker.fetch(new Request(`https://saastcolab.jp${p11Path}`), env, ctx);
  assert.equal(p11.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");
  const p11Body = await p11.text();
  assert.doesNotMatch(p11Body, /<link\s+rel=["']canonical["']/i);
  assert.doesNotMatch(p11Body, /data-affiliate-cta-partner|rel=["'][^"']*sponsored/i);

  const robots = await worker.fetch(new Request("https://saastcolab.jp/robots.txt"), env, ctx);
  const robotsText = await robots.text();
  assert.match(robotsText, /Allow: \/pilot\/migration-cost\$/);
  assert.match(robotsText, /Allow: \/\$/);
  assert.doesNotMatch(robotsText, /Allow: \/pilot\/break-even\$/);

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  const locations = [...((await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g))].map((match) => match[1]);
  assert.equal(locations.length, 11);
  assert.ok(locations.includes("https://saastcolab.jp/pilot/migration-cost"));
  assert.ok(!locations.includes("https://saastcolab.jp/pilot/break-even"));
});

test("runtime approval cannot promote source-unreviewed P11", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("p11-source-fail-closed", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P11",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
  };
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  const path = "/pilot/break-even";
  const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
  const body = await response.text();
  assert.equal(response.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");
  assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i);
  assert.doesNotMatch(body, /data-affiliate-cta-partner|rel=["'][^"']*sponsored/i);
  const robots = await worker.fetch(new Request("https://saastcolab.jp/robots.txt"), env, ctx);
  assert.doesNotMatch(await robots.text(), /Allow: \/pilot\/break-even\$/);
  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  assert.doesNotMatch(await sitemap.text(), /\/pilot\/break-even/);
});

test("missing or invalid index approval stays fail-closed while public navigation remains crawlable", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("fail-closed-index", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  const robots = await worker.fetch(new Request("https://saastcolab.jp/robots.txt"), env, ctx);
  const robotsText = await robots.text();
  assert.equal(robotsAllows(robotsText, "/"), true);
  assert.equal(robotsAllows(robotsText, "/methodology"), true);
  assert.equal(robotsAllows(robotsText, "/pilot/pricing-calculator"), false);

  const article = await worker.fetch(
    new Request("https://saastcolab.jp/pilot/pricing-calculator"),
    env,
    ctx,
  );
  assert.equal(article.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  assert.equal(sitemap.status, 503);
  assert.match(sitemap.headers.get("x-robots-tag"), /\bnoindex\b/i);

  const invalidEnv = {
    ...env,
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P01",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01,SVR01",
  };
  const health = await worker.fetch(new Request("https://saastcolab.jp/healthz"), invalidEnv, ctx);
  assert.equal(await health.text(), "ok\n");
  assert.equal(health.headers.get("x-index-approval-active"), "true");
  assert.equal(health.headers.get("x-index-articles-config-valid"), "false");
  assert.equal(health.headers.get("x-index-server-articles-config-valid"), "false");
  const invalidRobots = await worker.fetch(
    new Request("https://saastcolab.jp/robots.txt"),
    invalidEnv,
    ctx,
  );
  assert.equal(robotsAllows(await invalidRobots.text(), "/pilot/pricing-calculator"), false);
});

test("missing, expired, or malformed Mangools approval stays CTA fail-closed", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("fail-closed-cta", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const baseEnv = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01",
    CTA_GO: "GO",
    CTA_APPROVED_PARTNER: "mangools",
    MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "true",
    MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/#a1234567890bcdef123456789",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  for (const override of [
    { CTA_GO: "HOLD" },
    { CTA_APPROVED_PARTNER: "semrush" },
    {
      CTA_APPROVED_PARTNER: "a8net",
      A8NET_AFFILIATE_APPROVAL_CURRENT: "true",
      A8NET_AFFILIATE_DESTINATION: "configured-in-runtime-only",
    },
    { MANGOOLS_AFFILIATE_APPROVAL_CURRENT: "false" },
    { MANGOOLS_AFFILIATE_DESTINATION: "https://example.com/#a1234567890bcdef123456789" },
    { MANGOOLS_AFFILIATE_DESTINATION: "https://mangools.com/?ref=not-approved" },
  ]) {
    const response = await worker.fetch(
      new Request("https://saastcolab.jp/pilot/pricing-calculator"),
      { ...baseEnv, ...override },
      ctx,
    );
    assert.equal(response.status, 200);
    const body = await response.text();
    assert.match(body, /data-affiliate-cta-placeholder="mangools"/);
    assert.match(body, /data-affiliate-disclosure-status="disabled"/);
    assert.doesNotMatch(body, /rel=["'][^"']*sponsored|data-affiliate-cta-partner/i);
  }
});

test("approved SVR01 can expose only runtime-validated server partners", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("server-cta", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01",
    CTA_GO: "GO",
    SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01",
    SERVER_CTA_GO: "a8net-xserver-business,moshimo-conoha-wing,moshimo-lolipop-rental-server,moshimo-onamae-rental-server,moshimo-shin-rental-server,valuecommerce-ablenet-shared-server",
    A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
    A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
    MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-onamae&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-shin&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT: "true",
    VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION: "https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=synthetic&pid=synthetic",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  const response = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    env,
    ctx,
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-robots-tag"), "index, follow");
  const body = await response.text();
  const visible = visibleMarkup(body);
  const bootstrap = body.match(/<script data-saastco-server-affiliate-cta>[\s\S]*?<\/script>/i)?.[0] ?? "";
  const disclosurePosition = visible.indexOf('data-affiliate-disclosure-status="disabled"');
  const xserverPosition = visible.indexOf('data-server-affiliate-cta-placeholder="a8net-xserver-business"');
  const conohaPosition = visible.indexOf('data-server-affiliate-cta-placeholder="moshimo-conoha-wing"');
  assert.ok(disclosurePosition >= 0);
  assert.ok(xserverPosition > disclosurePosition);
  assert.ok(conohaPosition > disclosurePosition);
  assert.match(visible, /data-server-cta-mode="disabled"/);
  assert.match(bootstrap, /m="comparison"/);
  assert.match(body, /class="server-cta-primary"/);
  assert.match(body, /class="server-cta-secondary"/);
  assert.match(body, /代替候補を1社/);
  assert.match(body, /最大1社だけ表示/);
  assert.ok(xserverPosition < conohaPosition, "既存のHuman確認順で主CTAを代替CTAより先に表示する");
  assert.match(bootstrap, /https:\/\/px\.a8\.net\/svt\/ejp\?a8mat=synthetic/);
  assert.match(bootstrap, /a_id=synthetic-conoha/);
  assert.match(bootstrap, /"position":"primary"/);
  assert.match(bootstrap, /"position":"alternative"/);
  assert.match(bootstrap, /"vendorId":"xserver-business"/);
  assert.match(bootstrap, /"vendorId":"conoha-wing"/);
  assert.match(bootstrap, /a\.rel="sponsored noopener noreferrer"/);
  assert.match(bootstrap, /compareDocumentPosition\(n\)&Node\.DOCUMENT_POSITION_FOLLOWING/);
  assert.match(bootstrap, /d\.textContent!==dt/);
  assert.match(bootstrap, /s\.textContent!==st/);
  assert.match(bootstrap, /c\.dataset\.serverCtaMode!==m/);
  assert.doesNotMatch(bootstrap, /"id":"(?:moshimo-lolipop-rental-server|moshimo-onamae-rental-server|moshimo-shin-rental-server|valuecommerce-ablenet-shared-server)"/);
  assert.doesNotMatch(visible, /data-server-affiliate-cta-partner|rel="sponsored noopener noreferrer"/);
  assert.doesNotMatch(visible, /data-affiliate-cta-partner="mangools"/);

  const singleResponse = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    { ...env, SERVER_CTA_GO: "a8net-xserver-business" },
    ctx,
  );
  const singleBody = await singleResponse.text();
  const singleVisible = visibleMarkup(singleBody);
  const singleBootstrap = singleBody.match(/<script data-saastco-server-affiliate-cta>[\s\S]*?<\/script>/i)?.[0] ?? "";
  assert.match(singleVisible, /data-server-cta-mode="disabled"/);
  assert.match(singleBootstrap, /m="single"/);
  assert.match(singleBody, /各紹介リンクの有効状態は下に表示/);
  assert.match(singleBootstrap, /a\.rel="sponsored noopener noreferrer"/);
  assert.match(singleBootstrap, /"id":"a8net-xserver-business"/);
  assert.doesNotMatch(singleVisible, /data-server-affiliate-cta-partner|rel="sponsored noopener noreferrer"/);
  assert.doesNotMatch(singleBody, /紹介できる公式サイトが確認できていない/);

  const alternativeOnlyResponse = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    { ...env, SERVER_CTA_GO: "moshimo-conoha-wing" },
    ctx,
  );
  const alternativeOnlyBody = await alternativeOnlyResponse.text();
  assert.match(alternativeOnlyBody, /data-server-affiliate-cta-state="disabled"/);
  assert.doesNotMatch(alternativeOnlyBody, /rel="sponsored noopener noreferrer"/);
});

test("revenue analytics owns affiliate outbound events and keeps safe bounded dimensions", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("revenue-analytics-contract", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
      GA4_ANALYTICS_ENABLED: "true",
      GA4_MEASUREMENT_ID: "G-TEST123456",
      INDEX_GO: "GO",
      INDEX_APPROVED_ARTICLES: "P01",
      INDEX_APPROVED_SERVER_ARTICLES: "SVR01",
      CTA_GO: "GO",
      SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01",
      SERVER_CTA_GO: "a8net-xserver-business,moshimo-conoha-wing",
      A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
      A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
      MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "true",
      MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
  const body = await response.text();
  const consent = body.match(/<script data-saastco-analytics-consent>[\s\S]*?<\/script>/)?.[0] ?? "";
  const funnel = body.match(/<script data-saastco-funnel-measurement>[\s\S]*?<\/script>/)?.[0] ?? "";
  assert.ok(consent);
  assert.ok(funnel);
  assert.doesNotMatch(consent, /"outbound_click"/);
  assert.match(consent, /"external_link_click"/);
  assert.match(consent, /analytics_storage:"denied"/);
  assert.match(consent, /if\(a\(\)\)g\("event"/);
  assert.equal((funnel.match(/"outbound_click"/g) ?? []).length, 1);
  for (const dimension of [
    "article_id", "revenue_cell_id", "revenue_cell_version", "vendor_id", "cta_position", "cta_type",
    "channel", "source_class", "medium_class", "campaign_id", "environment", "traffic_scope", "test_flag",
  ]) assert.match(funnel, new RegExp(dimension), dimension);
  assert.match(funnel, /saas_tco_lab_cta_eligible_v3/);
  assert.match(funnel, /current\.article_id,current\.revenue_cell_id,current\.revenue_cell_version/);
  assert.match(funnel, /saas_tco_lab_outbound_session_v1/);
  assert.match(funnel, /"referral"/);
  assert.match(funnel, /new URLSearchParams\(current\.hash\.startsWith\("#"\)/);
  assert.doesNotMatch(funnel, /current\.searchParams\.get\("(?:ch|cid)"\)/);
  assert.doesNotMatch(funnel, /saas_tco_lab_cta_eligible_v2/);
  assert.match(funnel, /new WeakSet\(\)/);
  assert.match(funnel, /new WeakMap\(\)/);
  assert.match(funnel, /now-last<750/);
  assert.match(funnel, /threshold:\.5/);
  assert.match(funnel, /setTimeout\(\(\)=>\{pendingCtaViews\.delete\(target\);showCta\(target\)\},1000\)/);
  assert.ok(funnel.indexOf("showCta(link)") < funnel.indexOf('emit("outbound_click"'));
  assert.match(funnel, /const markSessionOnce=.*catch\{return false\}/s);
  assert.match(funnel, /new Set\(\["mangools\.com","px\.a8\.net","af\.moshimo\.com","ck\.jp\.ap\.valuecommerce\.com"\]\)/);
  assert.doesNotMatch(funnel, /raw_referrer_query|raw_search_query|affiliate_url|tracking_parameters/);
});

test("revenue funnel runtime records view and cell eligibility before one outbound session", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("revenue-runtime-semantics", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
      GA4_ANALYTICS_ENABLED: "true",
      GA4_MEASUREMENT_ID: "G-TEST123456",
      INDEX_GO: "GO",
      INDEX_APPROVED_ARTICLES: "P01",
      INDEX_APPROVED_SERVER_ARTICLES: "SVR01,SVR04",
      CTA_GO: "GO",
      SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01,SVR04",
      SERVER_CTA_GO: "a8net-xserver-business,moshimo-conoha-wing",
      A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
      A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
      MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "true",
      MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
  const body = await response.text();
  const source = body
    .match(/<script data-saastco-funnel-measurement>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(source);

  const listeners = new Map();
  const local = new Map([["saas_tco_lab_analytics_consent_v1", "granted"]]);
  const session = new Map();
  let article = { article: "SVR01", cell: "server-comparison-a", version: "v2" };
  class FakeElement {
    constructor(attributes = {}) { this.attributes = attributes; }
    getAttribute(name) { return this.attributes[name] ?? null; }
    hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
    matches(selector) { return selector.includes("data-server-affiliate-cta-partner"); }
    closest(selector) { return selector.includes("data-server-affiliate-cta-partner") ? this : null; }
  }
  class FakeAnchor extends FakeElement {
    constructor(href, attributes) { super(attributes); this.href = href; }
  }
  const makeLink = (position) => new FakeAnchor(
    "https://px.a8.net/svt/ejp?a8mat=synthetic",
    {
      "data-server-affiliate-cta-partner": "a8net-xserver-business",
      "data-vendor-id": "xserver-business",
      "data-server-cta-position": position,
      "data-server-cta-type": position === "single" ? "affiliate_single" : "affiliate_comparison",
    },
  );
  const firstLink = makeLink("primary");
  const context = {
    URL,
    URLSearchParams,
    Element: FakeElement,
    HTMLAnchorElement: FakeAnchor,
    MutationObserver: class { observe() {} },
    IntersectionObserver: class { observe() {} },
    navigator: { webdriver: false },
    location: {
      href: "https://saastcolab.jp/servers/business-server-pricing",
      origin: "https://saastcolab.jp",
      hostname: "saastcolab.jp",
      pathname: "/servers/business-server-pricing",
    },
    localStorage: {
      getItem: (key) => local.get(key) ?? null,
      setItem: (key, value) => local.set(key, value),
    },
    sessionStorage: {
      getItem: (key) => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, value),
    },
    document: {
      referrer: "https://www.google.com/",
      documentElement: {},
      querySelector: (selector) => selector === "main[data-article-id]" ? {
        getAttribute(name) {
          return {
            "data-article-id": article.article,
            "data-revenue-cell-id": article.cell,
            "data-revenue-cell-version": article.version,
          }[name] ?? null;
        },
      } : null,
      querySelectorAll: (selector) => selector.startsWith("a[data-affiliate") ? [firstLink] : [],
      addEventListener: (name, handler) => listeners.set(name, handler),
    },
    window: { dataLayer: [] },
    addEventListener() {},
    queueMicrotask: (callback) => callback(),
    setTimeout,
    clearTimeout,
    Date,
  };
  vm.runInNewContext(source, context);
  const click = listeners.get("click");
  assert.equal(typeof click, "function");
  click({ target: firstLink });
  click({ target: firstLink });

  article = { article: "SVR04", cell: "server-high-intent-b", version: "v2" };
  const secondLink = makeLink("single");
  click({ target: secondLink });

  const events = context.window.dataLayer
    .map((entry) => Array.from(entry))
    .filter(([kind]) => kind === "event");
  assert.deepEqual(
    events.map(([, name]) => name),
    [
      "cta_view", "cta_eligible_session", "outbound_click",
      "cta_view", "cta_eligible_session", "outbound_click",
    ],
  );
  assert.deepEqual(events.map(([, , value]) => value.revenue_cell_id), [
    "server-comparison-a", "server-comparison-a", "server-comparison-a",
    "server-high-intent-b", "server-high-intent-b", "server-high-intent-b",
  ]);
  assert.ok(events.every(([, , value]) => value.channel === "organic"));

  context.sessionStorage.getItem = () => { throw new Error("storage unavailable"); };
  context.sessionStorage.setItem = () => { throw new Error("storage unavailable"); };
  click({ target: makeLink("alternative") });
  const afterStorageFailure = context.window.dataLayer
    .map((entry) => Array.from(entry))
    .filter(([kind]) => kind === "event");
  assert.equal(afterStorageFailure.length, 7);
  assert.equal(afterStorageFailure.at(-1)?.[1], "cta_view");

  local.set("saas_tco_lab_analytics_consent_v1", "denied");
  click({ target: makeLink("alternative") });
  assert.equal(context.window.dataLayer.length, 7);
});

test("server index release cannot widen CTA beyond the exact article allowlist", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("server-index-without-cta-widening", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const serverIds = ["SVR01", "SVR05", "SVR04", "SVR06", "SVR07", "SVR02", "SVR03", "SVR09", "SVR08"];
  const serverPaths = [
    "/servers/business-server-pricing",
    "/servers/server-renewal-cost",
    "/servers/server-first-year-total",
    "/servers/server-migration-cost",
    "/servers/business-rental-server",
    "/servers/small-business-server",
    "/servers/ec-server-cost",
    "/servers/business-mail-server",
    "/servers/ec-server-requirements",
  ];
  const env = {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
    INDEX_APPROVED_SERVER_ARTICLES: serverIds.join(","),
    CTA_GO: "GO",
    SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01",
    SERVER_CTA_GO: "a8net-xserver-business",
    A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
    A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
  };
  const ctx = { waitUntil() {}, passThroughOnException() {} };

  for (const [index, path] of serverPaths.entries()) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    assert.equal(response.headers.get("x-robots-tag"), "index, follow", serverIds[index]);
    const body = await response.text();
    assert.equal(robotsMetaCount(body), 1, `${serverIds[index]}: one robots meta`);
    assert.match(body, /<meta name="robots" content="index, follow">/i, serverIds[index]);
    const visible = visibleMarkup(body);
    if (serverIds[index] === "SVR01") {
      assert.match(body, /<script data-saastco-server-affiliate-cta>/);
      assert.match(body, /"id":"a8net-xserver-business"/);
      assert.match(body, /a\.rel="sponsored noopener noreferrer"/);
      assert.match(visible, /data-server-affiliate-cta-placeholder="a8net-xserver-business"/);
      assert.doesNotMatch(visible, /data-server-affiliate-cta-partner|rel="sponsored noopener noreferrer"/);
    } else {
      assert.match(visible, /data-server-affiliate-cta-state="disabled"/, serverIds[index]);
      assert.doesNotMatch(body, /data-saastco-server-affiliate-cta/, serverIds[index]);
      assert.doesNotMatch(visible, /rel="sponsored noopener noreferrer"/, serverIds[index]);
    }
  }

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  const locations = [...((await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g))];
  assert.equal(locations.length, 20);

  for (const invalidArticleScope of [undefined, "", "SVR01,SVR01", "SVR02"]) {
    const response = await worker.fetch(
      new Request("https://saastcolab.jp/servers/business-server-pricing"),
      { ...env, SERVER_CTA_APPROVED_SERVER_ARTICLES: invalidArticleScope },
      ctx,
    );
    const body = await response.text();
    assert.match(body, /data-server-affiliate-cta-state="disabled"/);
    assert.doesNotMatch(body, /rel="sponsored noopener noreferrer"/);
  }
});

test("SVR04 Cell B activates only the Human-selected XServer single CTA", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("server-cell-b-single", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const baseEnv = {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01,SVR02,SVR03,SVR04,SVR05,SVR06,SVR07,SVR08,SVR09",
    CTA_GO: "GO",
    SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01,SVR04",
    SERVER_CTA_GO: "a8net-xserver-business,moshimo-conoha-wing",
    A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
    A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
    MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
  };
  const ctx = { waitUntil() {}, passThroughOnException() {} };

  const response = await worker.fetch(
    new Request("https://saastcolab.jp/servers/server-first-year-total"),
    baseEnv,
    ctx,
  );
  const body = await response.text();
  const disclosurePosition = body.indexOf('id="article-pr-disclosure"');
  const placeholderPosition = body.indexOf('data-server-affiliate-cta-placeholder="a8net-xserver-business"');
  assert.ok(disclosurePosition >= 0 && disclosurePosition < placeholderPosition);
  assert.match(body, /<script data-saastco-server-affiliate-cta>/);
  assert.match(body, /"id":"a8net-xserver-business"/);
  assert.match(body, /"position":"single"/);
  assert.match(body, /"ctaType":"affiliate_single"/);
  assert.doesNotMatch(body, /"id":"moshimo-conoha-wing"/);
  assert.match(body, /a\.rel="sponsored noopener noreferrer"/);

  const missingApproval = await worker.fetch(
    new Request("https://saastcolab.jp/servers/server-first-year-total"),
    { ...baseEnv, A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "false" },
    ctx,
  );
  const missingApprovalBody = await missingApproval.text();
  assert.match(missingApprovalBody, /data-server-affiliate-cta-state="disabled"/);
  assert.doesNotMatch(missingApprovalBody, /data-saastco-server-affiliate-cta/);

  const unrelatedArticle = await worker.fetch(
    new Request("https://saastcolab.jp/servers/server-renewal-cost"),
    baseEnv,
    ctx,
  );
  const unrelatedBody = await unrelatedArticle.text();
  assert.match(unrelatedBody, /data-server-affiliate-cta-state="disabled"/);
  assert.doesNotMatch(unrelatedBody, /data-saastco-server-affiliate-cta/);

  const unapprovedTrackingExtension = await worker.fetch(
    new Request("https://saastcolab.jp/servers/server-first-year-total"),
    {
      ...baseEnv,
      A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION:
        "https://px.a8.net/svt/ejp?a8mat=synthetic&subid=not-approved",
    },
    ctx,
  );
  const unapprovedTrackingExtensionBody = await unapprovedTrackingExtension.text();
  assert.match(unapprovedTrackingExtensionBody, /data-server-affiliate-cta-state="disabled"/);
  assert.doesNotMatch(unapprovedTrackingExtensionBody, /data-saastco-server-affiliate-cta/);
});

test("SVR01 approved source exposes gross contract charge while index and CTA stay runtime-held", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("server-public-preview", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("https://saastcolab.jp/servers/business-server-pricing"),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
      INDEX_GO: "GO",
      INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
      CTA_GO: "GO",
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-robots-tag"), "noindex, follow, noarchive, nosnippet");
  const body = await response.text();
  const disclosurePosition = body.indexOf('id="article-pr-disclosure"');
  const evidencePosition = body.indexOf("新規12か月契約で確認できた契約時請求額は66,660円");
  assert.ok(disclosurePosition >= 0 && disclosurePosition < evidencePosition);
  assert.match(body, /data-server-article-review="approved"/);
  assert.match(body, /期間限定キャッシュバックを控除する前の金額/);
  assert.match(body, /66,660円/);
  assert.match(body, /"@type":"Product"/);
  assert.match(body, /"@type":"FAQPage"/);
  assert.match(body, /"@type":"BreadcrumbList"/);
  assert.match(body, /"price":"66660","priceCurrency":"JPY"/);
  assert.match(body, /data-ranking-eligible="false"[\s\S]{0,400}<strong>未確認<\/strong>/);
  assert.match(body, /data-server-affiliate-cta-state="disabled"/);
  assert.doesNotMatch(body, /rel="sponsored noopener noreferrer"/);
});

test("server query variants and incomplete partner gates remain fail-closed", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("server-cta-fail-closed", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const baseEnv = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01",
    CTA_GO: "GO",
    SERVER_CTA_APPROVED_SERVER_ARTICLES: "SVR01",
    SERVER_CTA_GO: "a8net-xserver-business,moshimo-conoha-wing,moshimo-lolipop-rental-server,moshimo-onamae-rental-server,moshimo-shin-rental-server,valuecommerce-ablenet-shared-server",
    A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "true",
    A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://px.a8.net/svt/ejp?a8mat=synthetic",
    MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-onamae&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT: "true",
    MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION: "https://af.moshimo.com/af/c/click?a_id=synthetic-shin&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT: "true",
    VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION: "https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=synthetic&pid=synthetic",
  };
  const ctx = {
    waitUntil() {},
    passThroughOnException() {},
  };

  const variant = await worker.fetch(
    new Request("https://saastcolab.jp/servers/small-business-server"),
    baseEnv,
    ctx,
  );
  assert.match(variant.headers.get("x-robots-tag") ?? "", /noindex, follow/i);
  assert.doesNotMatch(await variant.text(), /rel="sponsored noopener noreferrer"/);

  const runtimeOnlyApproval = await worker.fetch(
    new Request("https://saastcolab.jp/servers/managed-server-cost"),
    { ...baseEnv, INDEX_APPROVED_SERVER_ARTICLES: "SVR01,SVR10" },
    ctx,
  );
  assert.match(runtimeOnlyApproval.headers.get("x-robots-tag") ?? "", /noindex, nofollow/i);
  assert.doesNotMatch(await runtimeOnlyApproval.text(), /rel="sponsored noopener noreferrer"/);

  for (const override of [
    { INDEX_APPROVED_SERVER_ARTICLES: "" },
    { CTA_GO: "HOLD" },
    { SERVER_CTA_GO: "a8net-xserver-business,a8net-xserver-business" },
    {
      A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
      MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
      MOSHIMO_LOLIPOP_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
      MOSHIMO_ONAMAE_SERVER_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
      MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
      VALUECOMMERCE_ABLENET_AFFILIATE_DESTINATION: "https://example.com/redirect?x=1",
    },
    {
      A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT: "false",
      MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT: "false",
      MOSHIMO_LOLIPOP_AFFILIATE_APPROVAL_CURRENT: "false",
      MOSHIMO_ONAMAE_SERVER_AFFILIATE_APPROVAL_CURRENT: "false",
      MOSHIMO_SHIN_RENTAL_SERVER_AFFILIATE_APPROVAL_CURRENT: "false",
      VALUECOMMERCE_ABLENET_AFFILIATE_APPROVAL_CURRENT: "false",
    },
  ]) {
    const response = await worker.fetch(
      new Request("https://saastcolab.jp/servers/business-server-pricing"),
      { ...baseEnv, ...override },
      ctx,
    );
    const body = await response.text();
    assert.match(body, /data-server-affiliate-cta-state="disabled"/);
    assert.doesNotMatch(body, /rel="sponsored noopener noreferrer"/);
  }
});

test("Human-approved home and SEO tools hub index only behind exact runtime gates", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("hub-index-gate", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const env = {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
    INDEX_GO: "GO",
    INDEX_APPROVED_ARTICLES: "P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
    INDEX_APPROVED_SERVER_ARTICLES: "SVR01,SVR02,SVR03,SVR04,SVR05,SVR06,SVR07,SVR08,SVR09",
    HUB_INDEX_GO: "GO",
    INDEX_APPROVED_HUBS: "HOME,SEO_TOOLS",
  };
  const ctx = { waitUntil() {}, passThroughOnException() {} };

  for (const path of ["/", "/pilot"]) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    const body = await response.text();
    assert.equal(response.headers.get("x-robots-tag"), "index, follow", path);
    assert.match(body, /<meta name="robots" content="index, follow">/i, path);
    assert.equal(robotsMetaCount(body), 1, `${path}: one robots meta`);
    assert.match(
      body,
      new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${path === "/" ? "/" : path}">`, "i"),
      path,
    );
    assert.doesNotMatch(body, /href=["']\/pilot\/break-even["']/i, path);
  }

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  const locations = [...((await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g))]
    .map((match) => match[1]);
  assert.equal(locations.length, 22);
  assert.ok(locations.includes("https://saastcolab.jp/"));
  assert.ok(locations.includes("https://saastcolab.jp/pilot"));
  assert.ok(!locations.includes("https://saastcolab.jp/pilot/break-even"));

  for (const override of [
    { HUB_INDEX_GO: "HOLD" },
    { INDEX_APPROVED_HUBS: "HOME,HOME" },
    { INDEX_APPROVED_HUBS: "HOME,UNKNOWN" },
    { INDEX_APPROVED_ARTICLES: "P01" },
    { INDEX_APPROVED_SERVER_ARTICLES: "SVR01" },
  ]) {
    const response = await worker.fetch(
      new Request("https://saastcolab.jp/"),
      { ...env, ...override },
      ctx,
    );
    assert.equal(
      response.headers.get("x-robots-tag"),
      "noindex, follow, noarchive, nosnippet",
    );
  }
});
