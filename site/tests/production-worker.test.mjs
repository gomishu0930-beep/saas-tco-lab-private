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
