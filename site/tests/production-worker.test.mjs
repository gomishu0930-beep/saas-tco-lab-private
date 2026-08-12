import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile, readdir } from "node:fs/promises";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import test, { after, before } from "node:test";

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
  if (process.platform === "win32") {
    return serverProcess.exitCode === null && serverProcess.signalCode === null;
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
    assert.match(body, /G-TEST123456/, path);
    assert.match(body, /dataLayer\.push\(arguments\)/, path);
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
    const approvedArticlePaths = new Set([
      "/pilot/pricing-calculator",
      "/pilot/plan-comparison",
      "/pilot/alternatives",
      "/pilot/annual-vs-monthly",
      "/pilot/usage-overage",
    ]);
    if (approvedArticlePaths.has(path)) {
      assert.equal(response.headers.get("x-robots-tag"), "index, follow", path);
      assert.match(body, /<meta name="robots" content="index, follow">/i, path);
      assert.match(
        body,
        new RegExp(`<link rel="canonical" href="https://saastcolab\\.jp${path}">`, "i"),
        path,
      );
      const disclosurePosition = documentHtml.indexOf('data-affiliate-disclosure-status="enabled"');
      const ctaPosition = documentHtml.indexOf(
        '<a class="cta-active" data-affiliate-cta-partner="mangools"',
      );
      assert.ok(disclosurePosition >= 0, `${path}: active disclosure`);
      assert.ok(ctaPosition > disclosurePosition, `${path}: disclosure before CTA`);
      assert.match(documentHtml, /この記事にはMangoolsのアフィリエイトリンクが含まれます。/i, path);
      assert.match(documentHtml, /data-affiliate-cta-state="enabled">ACTIVE — MANGOOLS/i, path);
      assert.match(
        documentHtml,
        /<a\b[^>]*class="cta-active"[^>]*data-affiliate-cta-partner="mangools"[^>]*href="https:\/\/mangools\.com\/#a1234567890bcdef123456789"[^>]*rel="sponsored noopener noreferrer"[^>]*>Mangools公式サイトを見る<\/a>/i,
        path,
      );
      assert.match(documentHtml, /<script data-saastco-affiliate-cta>/i, path);
      const nextReadingPosition = documentHtml.indexOf('class="shell page-section next-reading"');
      assert.ok(nextReadingPosition > ctaPosition, `${path}: next-to-read after CTA`);
      const nextReading = documentHtml.slice(nextReadingPosition, documentHtml.indexOf("</section>", nextReadingPosition));
      assert.match(nextReading, /href="\/pilot\/(?:pricing-calculator|plan-comparison|alternatives|annual-vs-monthly|usage-overage)\/"/i, path);
      assert.doesNotMatch(nextReading, /small-team-fit|enterprise-fit|addon-cost|migration-cost/i, path);
      assert.doesNotMatch(
        documentHtml,
        /<span\b[^>]*data-affiliate-cta-placeholder|>CTA DISABLED</i,
        path,
      );
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
    "/pilot",
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

test("public trust pages describe the live ten-article affiliate state", async () => {
  const home = await (await fetch(`${baseUrl}/`)).text();
  assert.match(home, /PUBLIC EDITORIAL/);
  assert.match(home, /公開記事[\s\S]{0,80}10本/);
  assert.match(home, /広告導線[\s\S]{0,80}Mangools/);
  assert.match(home, /href="\/pilot\/pricing-calculator\//);
  assert.match(home, /href="\/pilot\/plan-comparison\//);
  assert.match(home, /href="\/pilot\/evidence-method\//);
  assert.doesNotMatch(home, /href="\/pilot\/migration-cost\//);
  assert.doesNotMatch(home, /PUBLIC PRELAUNCH|広告リンク[\s\S]{0,50}0件|実在サービスの価格・評価・送客リンクは表示していません/);

  const disclosure = await (await fetch(`${baseUrl}/disclosure/`)).text();
  assert.match(disclosure, /現在の広告状態: Mangoolsのみ有効/);
  assert.match(disclosure, /Human承認済みの10記事/);
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

test("production exposes a deterministic tracking-free calculator loader", async () => {
  const response = await fetch(`${baseUrl}/embed/tco-calculator.js`);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /application\/javascript/i);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
  const body = await response.text();
  assert.match(body, /\/embed\/tco-calculator\//);
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
      "Allow: /assets/\n" +
      "Allow: /favicon.svg$\n" +
      "Allow: /sitemap.xml$\n" +
      "Allow: /pilot/alternatives$\n" +
      "Allow: /pilot/annual-vs-monthly$\n" +
      "Allow: /pilot/plan-comparison$\n" +
      "Allow: /pilot/pricing-calculator$\n" +
      "Allow: /pilot/usage-overage$\n" +
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
    const disclosure = body.indexOf('data-affiliate-disclosure-status="enabled"');
    const cta = body.indexOf(
      '<a class="cta-active" data-affiliate-cta-partner="mangools"',
    );
    assert.ok(disclosure >= 0, `${path}: disclosure enabled`);
    assert.ok(cta > disclosure, `${path}: disclosure before CTA`);
    assert.match(body, /rel="sponsored noopener noreferrer"/i, path);
  }

  for (const path of held) {
    const response = await worker.fetch(new Request(`https://saastcolab.jp${path}`), env, ctx);
    assert.equal(response.status, 200, path);
    assert.match(response.headers.get("x-robots-tag") ?? "", /noindex, nofollow/i, path);
    const body = await response.text();
    assert.doesNotMatch(body, /<link\s+rel=["']canonical["']/i, path);
    assert.doesNotMatch(body, /data-affiliate-cta-partner|rel=["'][^"']*sponsored/i, path);
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
  const disclosure = p05Body.indexOf('data-affiliate-disclosure-status="enabled"');
  const cta = p05Body.indexOf('<a class="cta-active" data-affiliate-cta-partner="mangools"');
  assert.ok(disclosure >= 0);
  assert.ok(cta > disclosure);
  assert.match(p05Body, /rel="sponsored noopener noreferrer"/i);

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
    const targets = [...nextReading.matchAll(/href="(\/pilot\/[^"]+)\/"/gi)].map((match) => match[1]);
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
    assert.match(response.headers.get("x-robots-tag") ?? "", /noindex, nofollow/i, path);
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

test("missing or invalid index approval stays fail-closed", async () => {
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
  assert.equal(await robots.text(), "User-agent: *\nDisallow: /\n");

  const sitemap = await worker.fetch(new Request("https://saastcolab.jp/sitemap.xml"), env, ctx);
  assert.equal(sitemap.status, 503);
  assert.match(sitemap.headers.get("x-robots-tag"), /\bnoindex\b/i);
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
  const disclosurePosition = body.indexOf('data-affiliate-disclosure-status="enabled"');
  const xserverPosition = body.indexOf('data-server-affiliate-cta-partner="a8net-xserver-business"');
  const conohaPosition = body.indexOf('data-server-affiliate-cta-partner="moshimo-conoha-wing"');
  const lolipopPosition = body.indexOf('data-server-affiliate-cta-partner="moshimo-lolipop-rental-server"');
  const onamaePosition = body.indexOf('data-server-affiliate-cta-partner="moshimo-onamae-rental-server"');
  const shinPosition = body.indexOf('data-server-affiliate-cta-partner="moshimo-shin-rental-server"');
  const ablenetPosition = body.indexOf('data-server-affiliate-cta-partner="valuecommerce-ablenet-shared-server"');
  assert.ok(disclosurePosition >= 0);
  assert.ok(xserverPosition > disclosurePosition);
  assert.ok(conohaPosition > disclosurePosition);
  assert.ok(lolipopPosition > disclosurePosition);
  assert.ok(onamaePosition > disclosurePosition);
  assert.ok(shinPosition > disclosurePosition);
  assert.ok(ablenetPosition > disclosurePosition);
  assert.match(body, /data-server-cta-mode="comparison"/);
  assert.match(body, /href="https:\/\/px\.a8\.net\/svt\/ejp\?a8mat=synthetic"/);
  assert.match(body, /a_id=synthetic-conoha/);
  assert.match(body, /href="https:\/\/af\.moshimo\.com\/af\/c\/click\?a_id=synthetic&amp;p_id=synthetic&amp;pc_id=synthetic&amp;pl_id=synthetic"/);
  assert.match(body, /a_id=synthetic-onamae/);
  assert.match(body, /a_id=synthetic-shin/);
  assert.match(body, /href="https:\/\/ck\.jp\.ap\.valuecommerce\.com\/servlet\/referral\?sid=synthetic&amp;pid=synthetic"/);
  assert.equal((body.match(/rel="sponsored noopener noreferrer"/g) ?? []).length, 6);
  assert.doesNotMatch(body, /data-affiliate-cta-partner="mangools"/);
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
    new Request("https://saastcolab.jp/servers/business-server-pricing?candidate=SVR02"),
    baseEnv,
    ctx,
  );
  assert.match(variant.headers.get("x-robots-tag") ?? "", /noindex, nofollow/i);
  assert.doesNotMatch(await variant.text(), /rel="sponsored noopener noreferrer"/);

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
