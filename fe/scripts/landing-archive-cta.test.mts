import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

interface BrowserWindow {
  location: {
    hash: string;
    origin: string;
    pathname: string;
    search: string;
  };
  localStorage: {
    getItem(key: string): string | null;
  };
}

function archiveLinks(markup: string) {
  return [...markup.matchAll(/<a\b(?=[^>]*aria-describedby="([^"]+)")(?=[^>]*href="([^"]+)")[^>]*>([\s\S]*?)<\/a>/g)]
    .map(([, describedBy, href, label]) => ({
      describedBy,
      href,
      label: label.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim(),
    }));
}

test("each rendered archive CTA leads unauthenticated visitors to login and preserves the reports return path", async () => {
  const browserWindow: BrowserWindow = {
    location: {
      hash: "",
      origin: "https://quantagent.test",
      pathname: "/",
      search: "",
    },
    localStorage: { getItem: () => null },
  };
  const priorWindow = globalThis.window;
  Object.defineProperty(globalThis, "window", { configurable: true, value: browserWindow });

  const vite = await createServer({
    configFile: new URL("../vite.config.ts", import.meta.url).pathname,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true },
    optimizeDeps: { noDiscovery: true },
  });

  try {
    const { LandingPage } = await vite.ssrLoadModule("/src/pages/LandingPage.tsx");
    const { default: App } = await vite.ssrLoadModule("/src/App.tsx");
    const landingMarkup = renderToStaticMarkup(createElement(LandingPage));
    const links = archiveLinks(landingMarkup);
    const descriptor = landingMarkup.match(/<small id="archive-access-note">([^<]+)<\/small>/);

    assert.deepEqual(
      links.map(({ label }) => label),
      ["리포트 로그인", "리포트 보관함 보기 →", "로그인 후 리포트 보관함 열기 →"],
    );
    assert.ok(descriptor);
    assert.match(descriptor[1], /로그인 후 읽기 전용 리포트 보관함으로 이동합니다\./);

    for (const { describedBy, href } of links) {
      assert.equal(describedBy, "archive-access-note");
      const destination = new URL(href, browserWindow.location.origin);
      assert.equal(destination.pathname, "/login");
      assert.equal(destination.searchParams.get("returnTo"), "/reports");

      browserWindow.location.pathname = destination.pathname;
      browserWindow.location.search = destination.search;
      const loginMarkup = renderToStaticMarkup(createElement(App));

      assert.match(loginMarkup, /<h1>Google 계정으로 시작<\/h1>/);
      assert.ok(loginMarkup.includes("로그인 후 요청하신 화면으로 이동합니다."));
    }
  } finally {
    await vite.close();
    Object.defineProperty(globalThis, "window", { configurable: true, value: priorWindow });
  }
});
