import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { AUTH_SESSION_STORAGE_KEY } from "../src/utils/userScopedStorage.ts";
import { ROUTES, sanitizeReturnTo } from "../src/config/routes.ts";

const VITE_ROOT = fileURLToPath(new URL("..", import.meta.url));
const VITE_CONFIG_FILE = fileURLToPath(new URL("../vite.config.ts", import.meta.url));

interface StorageMap {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function createStorage(initial: Record<string, string> = {}): StorageMap {
  const entries = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return entries.has(key) ? entries.get(key)! : null;
    },
    setItem(key, value) {
      entries.set(key, value);
    },
    removeItem(key) {
      entries.delete(key);
    },
  };
}

function installBrowserGlobals(storage: StorageMap, fetchImpl?: typeof fetch) {
  const priorWindow = globalThis.window;
  const priorFetch = globalThis.fetch;
  const testWindow = {
    location: {
      hash: "",
      origin: "https://quantagent.test",
      pathname: "/login",
      search: "?returnTo=%2Fapp",
    },
    localStorage: storage,
    sessionStorage: createStorage(),
  } as typeof window;

  Object.defineProperty(globalThis, "window", { configurable: true, value: testWindow });
  if (fetchImpl) {
    globalThis.fetch = fetchImpl;
  }

  return () => {
    Object.defineProperty(globalThis, "window", { configurable: true, value: priorWindow });
    globalThis.fetch = priorFetch;
  };
}

async function withVite<T>(run: (vite: Awaited<ReturnType<typeof createServer>>) => Promise<T>) {
  const vite = await createServer({
    configFile: VITE_CONFIG_FILE,
    root: VITE_ROOT,
    logLevel: "error",
    server: { middlewareMode: true },
    optimizeDeps: { noDiscovery: true },
  });

  try {
    return await run(vite);
  } finally {
    await vite.close();
  }
}

test("login session reconciliation validates cached identity against the live backend", async () => {
  await withVite(async (vite) => {
    const { reconcileLoginSession } = await vite.ssrLoadModule("/src/api/authClient.ts");
    const liveUser = {
      avatarUrl: "https://example.test/avatar.png",
      email: "live@example.com",
      id: "123",
      name: "Live Name",
      provider: "google",
    };
    const storage = createStorage({
      [AUTH_SESSION_STORAGE_KEY]: JSON.stringify({
        user: { ...liveUser, name: "Cached Name", email: "cached@example.com" },
        validatedAt: 0,
      }),
    });
    const restore = installBrowserGlobals(
      storage,
      async () =>
        new Response(JSON.stringify({ user: liveUser }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
    );

    try {
      const session = await reconcileLoginSession();
      assert.ok(session);
      assert.equal(session.user.id, liveUser.id);
      assert.equal(session.user.name, liveUser.name);
      assert.equal(session.user.email, liveUser.email);
      assert.equal(typeof session.validatedAt, "number");
      assert.match(storage.getItem(AUTH_SESSION_STORAGE_KEY) ?? "", /"email":"live@example.com"/);
      assert.match(storage.getItem(AUTH_SESSION_STORAGE_KEY) ?? "", /"validatedAt":/);
    } finally {
      restore();
    }
  });
});

test("expired backend session clears cached login metadata and returns unauthenticated", async () => {
  await withVite(async (vite) => {
    const { reconcileLoginSession } = await vite.ssrLoadModule("/src/api/authClient.ts");
    const storage = createStorage({
      [AUTH_SESSION_STORAGE_KEY]: JSON.stringify({
        user: { email: "stale@example.com", id: "123", name: "Stale Name", provider: "google" },
        validatedAt: 0,
      }),
    });
    const restore = installBrowserGlobals(
      storage,
      async () =>
        new Response(JSON.stringify({ error: { code: "not_authenticated" } }), {
          headers: { "Content-Type": "application/json" },
          status: 401,
        }),
    );

    try {
      const session = await reconcileLoginSession();
      assert.equal(session, null);
      assert.equal(storage.getItem(AUTH_SESSION_STORAGE_KEY), null);
    } finally {
      restore();
    }
  });
});

test("valid backend cookie bootstraps login state when localStorage is empty", async () => {
  await withVite(async (vite) => {
    const { reconcileLoginSession } = await vite.ssrLoadModule("/src/api/authClient.ts");
    const liveUser = {
      avatarUrl: null,
      email: "cookie@example.com",
      id: "777",
      name: "Cookie User",
      provider: "google",
    };
    const storage = createStorage();
    const restore = installBrowserGlobals(
      storage,
      async () =>
        new Response(JSON.stringify({ user: liveUser }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
    );

    try {
      const session = await reconcileLoginSession();
      assert.ok(session);
      assert.equal(session.user.id, liveUser.id);
      assert.equal(storage.getItem(AUTH_SESSION_STORAGE_KEY) !== null, true);
      assert.match(storage.getItem(AUTH_SESSION_STORAGE_KEY) ?? "", /"email":"cookie@example.com"/);
    } finally {
      restore();
    }
  });
});

test("transient current-user failures do not falsely authenticate stale login state", async () => {
  await withVite(async (vite) => {
    const { reconcileLoginSession } = await vite.ssrLoadModule("/src/api/authClient.ts");
    const staleSession = JSON.stringify({
      user: { email: "stale@example.com", id: "123", name: "Stale Name", provider: "google" },
      validatedAt: 0,
    });
    const storage = createStorage({ [AUTH_SESSION_STORAGE_KEY]: staleSession });
    const restore = installBrowserGlobals(
      storage,
      async () =>
        new Response("server error", {
          headers: { "Content-Type": "text/plain" },
          status: 500,
        }),
    );

    try {
      await assert.rejects(reconcileLoginSession(), /Backend request failed: 500/);
      assert.equal(storage.getItem(AUTH_SESSION_STORAGE_KEY), staleSession);
    } finally {
      restore();
    }
  });
});

test("login page initial render hides stale identity until reconciliation completes", async () => {
  await withVite(async (vite) => {
    const { LoginPage } = await vite.ssrLoadModule("/src/pages/LoginPage.tsx");
    const staleSession = JSON.stringify({
      user: { email: "stale@example.com", id: "123", name: "Stale Name", provider: "google" },
      validatedAt: 0,
    });
    const storage = createStorage({ [AUTH_SESSION_STORAGE_KEY]: staleSession });
    const restore = installBrowserGlobals(storage);

    try {
      const markup = renderToStaticMarkup(createElement(LoginPage, { returnTo: "/app" }));
      assert.match(markup, /로그인 상태를 확인하는 중/);
      assert.match(markup, /Google로 로그인/);
      assert.doesNotMatch(markup, /Stale Name|stale@example\.com|계속하기/);
    } finally {
      restore();
    }
  });
});

test("login page source keeps reconciliation, retry, Google sign-in, and sanitized returnTo wiring", async () => {
  const source = await readFile(new URL("../src/pages/LoginPage.tsx", import.meta.url), "utf8");

  assert.match(source, /reconcileLoginSession/);
  assert.match(source, /const nextPath = sanitizeReturnTo\(returnTo\)/);
  assert.match(source, /showAuthenticatedSession \? <a className="button button--dark" href=\{nextPath\}>계속하기<\/a> : null/);
  assert.match(source, /status === "error" \?/);
  assert.match(source, /Button onClick=\{reconcileSession\} variant="secondary">/);
  assert.match(source, /Button disabled=\{submitting\} onClick=\{handleGoogleSignIn\} variant="dark">/);
  assert.doesNotMatch(source, /getCurrentSession\(/);
});

test("auth client exposes cookie bootstrap and login reconciliation helpers", async () => {
  const source = await readFile(new URL("../src/api/authClient.ts", import.meta.url), "utf8");

  assert.match(source, /bootstrapSessionFromCookie/);
  assert.match(source, /reconcileLoginSession/);
  assert.match(source, /validateCurrentSession/);
});

test("sanitizeReturnTo preserves safe internal paths and normalizes unsafe targets", () => {
  assert.equal(sanitizeReturnTo("/app"), "/app");
  assert.equal(sanitizeReturnTo("/reports/abc"), "/reports/abc");
  assert.equal(sanitizeReturnTo("//evil.example"), ROUTES.app);
  assert.equal(sanitizeReturnTo("https://evil.example"), ROUTES.app);
});
