import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { accessSync, constants } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import test, { after, before } from "node:test";

import { chromium } from "playwright-core";

const siteRoot = fileURLToPath(new URL("../", import.meta.url));
const wranglerCli = fileURLToPath(new URL("../node_modules/wrangler/bin/wrangler.js", import.meta.url));
const verifyProductionBuild = fileURLToPath(new URL("../scripts/verify-production-build.mjs", import.meta.url));

const PILOT_PATHS = [
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

const SERVER_PATHS = [
  "/servers/business-server-pricing",
  "/servers/small-business-server",
  "/servers/ec-server-cost",
  "/servers/server-first-year-total",
  "/servers/server-renewal-cost",
  "/servers/server-migration-cost",
  "/servers/business-rental-server",
  "/servers/ec-server-requirements",
  "/servers/business-mail-server",
];

const INDEX_PATHS = ["/", "/pilot", ...PILOT_PATHS, ...SERVER_PATHS];
const HELD_P11_PATH = "/pilot/break-even";
const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

let baseUrl;
let browser;
let serverOutput = "";
let serverProcess;

function chromeExecutable() {
  for (const candidate of CHROME_CANDIDATES) {
    try {
      accessSync(candidate, constants.X_OK);
      return candidate;
    } catch {
      // Check the next fixed, local browser path.
    }
  }
  throw new Error(`Chrome/Chromium executable not found. Checked: ${CHROME_CANDIDATES.join(", ")}`);
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
  const deadline = Date.now() + 20_000;
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

function signalServerGroup(signal) {
  if (!serverProcess?.pid) return;
  try {
    if (process.platform === "win32") serverProcess.kill(signal);
    else process.kill(-serverProcess.pid, signal);
  } catch (error) {
    if (error?.code !== "ESRCH") throw error;
  }
}

async function stopServer() {
  if (!serverProcess) return;
  signalServerGroup("SIGTERM");
  const deadline = Date.now() + 3_000;
  while (
    Date.now() < deadline
    && serverProcess.exitCode === null
    && serverProcess.signalCode === null
  ) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (serverProcess.exitCode === null && serverProcess.signalCode === null) signalServerGroup("SIGKILL");
}

async function pageHead(page) {
  return page.evaluate(() => ({
    canonical: [...document.head.querySelectorAll('link[rel="canonical"]')]
      .map((element) => element.href),
    robots: [...document.head.querySelectorAll('meta[name="robots"]')]
      .map((element) => element.content),
  }));
}

async function expectHydratedIndexHead(page, path) {
  await page.waitForFunction(() => document.readyState === "complete");
  await page.waitForTimeout(80);
  const head = await pageHead(page);
  assert.deepEqual(head.robots, ["index, follow"], `${path}: robots`);
  assert.deepEqual(head.canonical, [`https://saastcolab.jp${path}`], `${path}: canonical`);
}

before(async () => {
  const verification = spawn(process.execPath, [verifyProductionBuild], {
    cwd: siteRoot,
    env: { ...process.env, SAAS_RUNTIME_MODE: "production" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let verificationOutput = "";
  verification.stdout.on("data", (chunk) => { verificationOutput += chunk.toString(); });
  verification.stderr.on("data", (chunk) => { verificationOutput += chunk.toString(); });
  const [verificationExitCode] = await once(verification, "exit");
  assert.equal(verificationExitCode, 0, `production build verification failed:\n${verificationOutput}`);

  const port = await availablePort();
  baseUrl = `http://127.0.0.1:${port}`;
  serverProcess = spawn(
    process.execPath,
    [
      wranglerCli,
      "dev",
      "--config", "dist/server/wrangler.json",
      "--port", String(port),
      "--ip", "127.0.0.1",
      "--var", "GA4_ANALYTICS_ENABLED:true",
      "--var", "GA4_MEASUREMENT_ID:G-TEST123456",
      "--var", "INDEX_GO:GO",
      "--var", "INDEX_APPROVED_ARTICLES:P01,P02,P03,P04,P05,P06,P07,P08,P09,P10,P12",
      "--var", "INDEX_APPROVED_SERVER_ARTICLES:SVR01,SVR02,SVR03,SVR04,SVR05,SVR06,SVR07,SVR08,SVR09",
      "--var", "HUB_INDEX_GO:GO",
      "--var", "INDEX_APPROVED_HUBS:HOME,SEO_TOOLS",
      "--var", "CTA_GO:GO",
      "--var", "CTA_APPROVED_PARTNER:mangools",
      "--var", "MANGOOLS_AFFILIATE_APPROVAL_CURRENT:true",
      "--var", "MANGOOLS_AFFILIATE_DESTINATION:https://mangools.com/#a1234567890bcdef123456789",
      "--var", "SERVER_CTA_APPROVED_SERVER_ARTICLES:SVR01,SVR04",
      "--var", "SERVER_CTA_GO:a8net-xserver-business,moshimo-conoha-wing",
      "--var", "A8NET_XSERVER_BUSINESS_AFFILIATE_APPROVAL_CURRENT:true",
      "--var", "A8NET_XSERVER_BUSINESS_AFFILIATE_DESTINATION:https://px.a8.net/svt/ejp?a8mat=synthetic",
      "--var", "MOSHIMO_CONOHA_WING_AFFILIATE_APPROVAL_CURRENT:true",
      "--var", "MOSHIMO_CONOHA_WING_AFFILIATE_DESTINATION:https://af.moshimo.com/af/c/click?a_id=synthetic-conoha&p_id=synthetic&pc_id=synthetic&pl_id=synthetic",
    ],
    {
      cwd: siteRoot,
      detached: process.platform !== "win32",
      env: { ...process.env, SAAS_RUNTIME_MODE: "production" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  serverProcess.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
  serverProcess.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });
  await waitForServer(baseUrl);
  browser = await chromium.launch({
    executablePath: chromeExecutable(),
    headless: true,
    args: process.platform === "linux" ? ["--no-sandbox"] : [],
  });
});

after(async () => {
  await browser?.close();
  await stopServer();
});

test("hydration preserves the exact 22-route index policy and held P11 boundary", { timeout: 120_000 }, async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.route("https://saastcolab.jp/**", (route) => route.abort());

  for (const path of INDEX_PATHS) {
    const response = await page.goto(`${baseUrl}${path}`, { waitUntil: "load" });
    assert.equal(response?.status(), 200, `${path}: HTTP status`);
    await expectHydratedIndexHead(page, path);
    const expectedCtas = PILOT_PATHS.includes(path)
      ? 1
      : path === "/servers/business-server-pricing" ? 2
        : path === "/servers/server-first-year-total" ? 1 : 0;
    if (expectedCtas > 0) {
      await page.waitForFunction(
        (expected) => document.querySelectorAll(
          'a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]',
        ).length === expected,
        expectedCtas,
      );
    } else {
      await page.waitForTimeout(80);
    }
    const ctaState = await page.evaluate(() => {
      const disclosure = document.querySelector("#article-pr-disclosure");
      const ctas = [...document.querySelectorAll(
        'a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]',
      )];
      return {
        count: ctas.length,
        disclosureBeforeEveryCta: ctas.every((cta) => Boolean(
          disclosure && (disclosure.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING),
        )),
        rels: ctas.map((cta) => cta.getAttribute("rel")),
      };
    });
    assert.equal(ctaState.count, expectedCtas, `${path}: active CTA count`);
    if (expectedCtas > 0) {
      assert.equal(ctaState.disclosureBeforeEveryCta, true, `${path}: disclosure order`);
      assert.deepEqual(
        ctaState.rels,
        Array(expectedCtas).fill("sponsored noopener noreferrer"),
        `${path}: affiliate rel`,
      );
    }
  }

  const heldResponse = await page.goto(`${baseUrl}${HELD_P11_PATH}`, { waitUntil: "load" });
  assert.equal(heldResponse?.status(), 200);
  await page.waitForTimeout(80);
  assert.deepEqual((await pageHead(page)).robots, ["noindex, follow, noarchive, nosnippet"]);
  assert.deepEqual((await pageHead(page)).canonical, []);
  assert.equal(await page.locator(
    'a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]',
  ).count(), 0);
  await context.close();
});

test("hydration cannot remove the analytics consent controls", { timeout: 60_000 }, async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.route("https://www.googletagmanager.com/**", (route) => route.abort());
  await page.route("https://www.google-analytics.com/**", (route) => route.abort());
  await page.route("https://region1.google-analytics.com/**", (route) => route.abort());

  const response = await page.goto(`${baseUrl}/servers/server-first-year-total`, { waitUntil: "load" });
  assert.equal(response?.status(), 200);
  await page.waitForTimeout(1_000);
  const analyticsState = await page.evaluate(() => ({
    consentScript: document.querySelectorAll("script[data-saastco-analytics-consent]").length,
    readyState: document.readyState,
    settings: document.querySelectorAll("button[data-analytics-settings]").length,
  }));
  const settings = page.locator("button[data-analytics-settings]");
  assert.equal(analyticsState.consentScript, 1, JSON.stringify(analyticsState));
  assert.equal(analyticsState.settings, 1, JSON.stringify(analyticsState));
  await settings.waitFor({ state: "visible" });
  await settings.click();
  const banner = page.locator('[role="dialog"][aria-label="アクセス解析の同意"]');
  await banner.waitFor({ state: "visible" });
  assert.equal(await banner.count(), 1);
  assert.equal(await page.locator('button[data-consent="granted"]').count(), 1);
  assert.equal(await page.locator('button[data-consent="denied"]').count(), 1);
  assert.equal(await page.evaluate(() => Array.isArray(window.dataLayer)), false);

  await context.close();
});

test("client navigation and browser history cannot revive stale robots or canonical tags", { timeout: 60_000 }, async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.route("https://saastcolab.jp/**", (route) => route.abort());

  await page.goto(`${baseUrl}${HELD_P11_PATH}`, { waitUntil: "load" });
  assert.deepEqual((await pageHead(page)).canonical, []);
  await page.locator(
    'nav[aria-label="主要ナビゲーション"] a[href="/servers/business-server-pricing"]',
  ).click();
  await expectHydratedIndexHead(page, "/servers/business-server-pricing");
  await page.locator(
    'nav[aria-label="主要ナビゲーション"] a[href="/pilot/pricing-calculator"]',
  ).click();
  await expectHydratedIndexHead(page, "/pilot/pricing-calculator");
  await page.goBack({ waitUntil: "load" });
  await expectHydratedIndexHead(page, "/servers/business-server-pricing");
  await context.close();
});

test("mobile and JavaScript-disabled views preserve disclosure and CTA fail-closed behavior", { timeout: 60_000 }, async () => {
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mobilePage = await mobile.newPage();
  await mobilePage.route("https://saastcolab.jp/**", (route) => route.abort());
  await mobilePage.goto(`${baseUrl}/servers/server-first-year-total`, { waitUntil: "load" });
  const mobileCta = mobilePage.locator(
    'a[data-server-affiliate-cta-partner="a8net-xserver-business"]',
  );
  await mobileCta.waitFor();
  await mobileCta.scrollIntoViewIfNeeded();
  assert.equal(await mobileCta.isVisible(), true);
  await expectHydratedIndexHead(mobilePage, "/servers/server-first-year-total");
  await mobile.close();

  const noJavaScript = await browser.newContext({ javaScriptEnabled: false });
  const noJavaScriptPage = await noJavaScript.newPage();
  await noJavaScriptPage.route("https://saastcolab.jp/**", (route) => route.abort());
  await noJavaScriptPage.goto(`${baseUrl}/servers/server-first-year-total`, { waitUntil: "load" });
  assert.equal(await noJavaScriptPage.locator(
    'a[data-affiliate-cta-partner],a[data-server-affiliate-cta-partner]',
  ).count(), 0);
  assert.deepEqual((await pageHead(noJavaScriptPage)).robots, ["index, follow"]);
  assert.deepEqual(
    (await pageHead(noJavaScriptPage)).canonical,
    ["https://saastcolab.jp/servers/server-first-year-total"],
  );
  await noJavaScript.close();
});
