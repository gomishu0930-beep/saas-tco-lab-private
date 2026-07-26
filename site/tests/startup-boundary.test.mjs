import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import test from "node:test";

const siteRoot = fileURLToPath(new URL("../", import.meta.url));
const verifyProductionBuild = fileURLToPath(
  new URL("../scripts/verify-production-build.mjs", import.meta.url),
);

test("a synthetic-local dist is rejected by the built production starter", async () => {
  const child = spawn(process.execPath, [verifyProductionBuild], {
    cwd: siteRoot,
    env: { ...process.env, SAAS_RUNTIME_MODE: "production" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (chunk) => {
    output += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    output += chunk.toString();
  });
  const [exitCode] = await once(child, "exit");

  assert.notEqual(exitCode, 0);
  assert.match(output, /assets\.run_worker_first must be true/);
  assert.doesNotMatch(output, /Ready on|localhost:/i);
});
