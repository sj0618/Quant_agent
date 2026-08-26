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

test("archive and strategy-workspace CTAs preserve their distinct login return paths", async () => {
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
    const workspaceLinks = [...landingMarkup.matchAll(/<a\b(?=[^>]*aria-describedby="workspace-access-note")(?=[^>]*href="([^"]+)")[^>]*>([\s\S]*?)<\/a>/g)]
      .map(([, href, label]) => ({ href, label: label.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim() }));
    const descriptor = landingMarkup.match(/<small id="archive-access-note">([^<]+)<\/small>/);

    const archiveOnlyLinks = links.filter(({ describedBy }) => describedBy === "archive-access-note");
    assert.deepEqual(
      archiveOnlyLinks.map(({ label }) => label),
      ["로그인 후 리포트 보관함 열기 →"],
    );
    assert.ok(descriptor);
    assert.match(descriptor[1], /로그인 후 읽기 전용 리포트 보관함으로 이동합니다\./);

    for (const { describedBy, href } of archiveOnlyLinks) {
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

    assert.deepEqual(workspaceLinks.map(({ label }) => label), ["전략 분석 시작", "자연어 전략 분석 시작 →", "전략 검증 시작 →"]);
    for (const { href } of workspaceLinks) {
      const destination = new URL(href, browserWindow.location.origin);
      assert.equal(destination.pathname, "/login");
      assert.equal(destination.searchParams.get("returnTo"), "/app");
    }
  } finally {
    await vite.close();
    Object.defineProperty(globalThis, "window", { configurable: true, value: priorWindow });
  }
});
