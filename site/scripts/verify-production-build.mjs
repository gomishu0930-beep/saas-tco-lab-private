import { readFile } from "node:fs/promises";

const configUrl = new URL("../dist/server/wrangler.json", import.meta.url);

function fail(message) {
  process.stderr.write(`production build verification failed: ${message}\n`);
  process.exitCode = 1;
}

let config;
try {
  config = JSON.parse(await readFile(configUrl, "utf8"));
} catch {
  fail("dist/server/wrangler.json is missing or invalid; run npm run build");
}

if (config) {
  if (config.assets?.run_worker_first !== true) {
    fail("assets.run_worker_first must be true; synthetic-local builds cannot start");
  } else if (typeof config.main !== "string" || !config.main.trim()) {
    fail("worker main entry is missing");
  } else if (process.env.SAAS_RUNTIME_MODE !== "production") {
    fail("SAAS_RUNTIME_MODE must be production");
  }
}
