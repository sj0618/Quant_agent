import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { createBackendProxyConfig } from "../vite.config.ts";

test("split proxy keeps independent backend targets and strips the ai-api prefix", () => {
  const config = createBackendProxyConfig({
    BACKEND_PROXY_TARGET: "http://127.0.0.1:18002/",
    AI_BACKEND_PROXY_TARGET: "http://127.0.0.1:18001/",
  });

  assert.equal(config.mode, "split");
  assert.equal(config.proxy["/api/v1"].target, "http://127.0.0.1:18002");
  assert.equal(config.proxy["/ai-api"].target, "http://127.0.0.1:18001");
  assert.equal(config.proxy["/api/v1"].xfwd, true);
  assert.equal(config.proxy["/ai-api"].xfwd, true);
  assert.equal(config.proxy["/ai-api"].rewrite?.("/ai-api/analysis-jobs"), "/analysis-jobs");
});

test("combined proxy keeps both paths on the shared target and preserves /ai-api", () => {
  const config = createBackendProxyConfig({
    COMBINED_BACKEND_PROXY_TARGET: "http://127.0.0.1:18003",
  });

  assert.equal(config.mode, "combined");
  assert.equal(config.proxy["/api/v1"].target, "http://127.0.0.1:18003");
  assert.equal(config.proxy["/ai-api"].target, "http://127.0.0.1:18003");
  assert.equal(config.proxy["/api/v1"].xfwd, true);
  assert.equal(config.proxy["/ai-api"].xfwd, true);
  assert.equal(config.proxy["/ai-api"].rewrite, undefined);
});

test("production deploy starts one non-reloading combined backend", async () => {
  const source = await readFile(new URL("../../.github/workflows/deploy.yml", import.meta.url), "utf8");

  assert.match(source, /pkill -TERM -f .*uvicorn combined_main:app/);
  assert.doesNotMatch(source, /--reload/);
});

test("production deploy serves the built frontend instead of Vite development assets", async () => {
  const [source, serverHealth] = await Promise.all([
    readFile(new URL("../../.github/workflows/deploy.yml", import.meta.url), "utf8"),
    readFile(new URL("../../.github/workflows/server-health.yml", import.meta.url), "utf8"),
  ]);

  assert.match(source, /VITE_AI_API_BASE_URL="\/ai-api" npm run build/);
  assert.match(source, /npm run preview -- --host 0\.0\.0\.0 --port 18000/);
  assert.match(source, /Frontend bundle contains Vite development assets/);
  assert.doesNotMatch(source, /npm run dev/);
  assert.match(serverHealth, /Frontend bundle contains Vite development assets/);
  assert.match(serverHealth, /http:\/\/127\.0\.0\.1:\$FE_PORT\//);
});
