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
    [wranglerCli, "dev", "--config", "dist/server/wrangler.json", "--port", String(port), "--ip", "127.0.0.1"],
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

test("built production config routes assets through the fail-closed worker", async () => {
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
    "/comparison",
    "/methodology",
    "/disclosure",
    "/readiness",
    "/operator",
    `/assets/${javascriptAsset}`,
    "/favicon.svg",
    "/_vinext/image?url=%2Ffavicon.svg&w=32&q=75",
    "/missing",
  ]) {
    const response = await fetch(`${baseUrl}${path}`);
    assert.equal(response.status, 503, path);
    const body = await response.text();
    assert.equal(body, "Service Unavailable\n", path);
    assert.doesNotMatch(body, /JPY|SaaS|synthetic|affiliate/i, path);
    assert.equal(response.headers.get("cache-control"), "no-store", path);
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

test("actual production robots disallows the complete site", async () => {
  const response = await fetch(`${baseUrl}/robots.txt`);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "User-agent: *\nDisallow: /\n");
});
