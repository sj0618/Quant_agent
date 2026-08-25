import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import type { ResearchResultV1 } from "../src/types/researchContract";

const expectedHeadings = {
  ready: "조건 일치 결과",
  need_clarification: "입력 확인이 필요합니다",
  no_match: "조건 일치 항목이 없습니다",
  unavailable: "결과를 표시할 수 없습니다",
  failed: "처리에 실패했습니다",
  dev_preview: "개발 검증 미리보기",
} as const;

test("research workspace and every ResearchResultV1 status render a safe visible contract", async () => {
  const vite = await createServer({
    configFile: false,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: { port: 24679 } },
    optimizeDeps: { noDiscovery: true },
    resolve: { alias: { "@": new URL("../src", import.meta.url).pathname } },
  });

  try {
    const workspaceModule = (await vite.ssrLoadModule(
      "/src/features/research-contract/ResearchWorkspace.tsx",
    )) as unknown as typeof import("../src/features/research-contract/ResearchWorkspace");
    const { ResearchWorkspace } = workspaceModule;
    const markup = renderToStaticMarkup(createElement(ResearchWorkspace));

    assert.match(markup, /<h1 id="research-workspace-title">한국 주식 EOD 리서치<\/h1>/);
    assert.match(markup, /<label for="research-rule-input">검토할 일반 조건식<\/label>/);
    assert.match(markup, /일반 조건식의 일치 여부만 검토합니다/);
    assert.doesNotMatch(markup, /매수\/매도|BUY|SELL|HOLD/);
    const [rendererModule, fixturesModule] = await Promise.all([
      vite.ssrLoadModule("/src/features/research-contract/ResearchResultRenderer.tsx"),
      vite.ssrLoadModule("/src/features/research-contract/researchResultFixtures.ts"),
    ]);
    const { ResearchResultRenderer } = rendererModule as typeof import("../src/features/research-contract/ResearchResultRenderer");
    const { researchResultFixtures } = fixturesModule as typeof import("../src/features/research-contract/researchResultFixtures");
    const renderedByStatus = new Map<ResearchResultV1["status"], string>();

    for (const result of researchResultFixtures) {
      const resultMarkup = renderToStaticMarkup(createElement(ResearchResultRenderer, { result }));

      renderedByStatus.set(result.status, resultMarkup);
      assert.match(resultMarkup, new RegExp(`<h2 id="research-result-title">${expectedHeadings[result.status]}<\\/h2>`));
      assert.doesNotMatch(resultMarkup, /매수|매도|보유|추천|BUY|SELL|HOLD|debug_ref|trace_id/);
    }

    assert.equal(researchResultFixtures.length, Object.keys(expectedHeadings).length);
    assert.equal(renderedByStatus.size, Object.keys(expectedHeadings).length);
    assert.deepEqual([...renderedByStatus.keys()].sort(), Object.keys(expectedHeadings).sort());

    const readyMarkup = renderedByStatus.get("ready") ?? "";
    assert.match(readyMarkup, /출처 PostgreSQL · 기준일 2026-08-20 · 조회 범위 2개 · 조건 일치 1개/);
    assert.match(readyMarkup, /검증용 항목/);

    const clarificationMarkup = renderedByStatus.get("need_clarification") ?? "";
    assert.match(clarificationMarkup, /조건을 더 구체적으로 입력해 주세요/);
    assert.match(clarificationMarkup, /진입 조건 추가/);

    const noMatchMarkup = renderedByStatus.get("no_match") ?? "";
    assert.match(noMatchMarkup, /현재 기준일에는 조건과 일치한 항목이 없습니다/);
    assert.match(noMatchMarkup, /조건 일치 수는 0개입니다/);

    const unavailableMarkup = renderedByStatus.get("unavailable") ?? "";
    assert.match(unavailableMarkup, /운영 데이터 기준일과 출처가 확인되지 않았습니다/);
    assert.match(unavailableMarkup, /운영 데이터 상태가 확인된 뒤 다시 시도할 수 있습니다/);

    const failedMarkup = renderedByStatus.get("failed") ?? "";
    assert.match(failedMarkup, /검증 중 처리 오류가 발생했습니다/);
    assert.match(failedMarkup, /문의 시 참조 번호: fixture-support-reference/);

    const previewMarkup = renderedByStatus.get("dev_preview") ?? "";
    assert.match(previewMarkup, /이 fixture는 renderer 검증 전용입니다/);
    assert.match(previewMarkup, /운영 데이터 결과가 아니며 공개 화면에서 사용하지 않습니다/);
  } finally {
    await vite.close();
  }
});
