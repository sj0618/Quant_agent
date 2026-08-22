import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("protected-route fallback has an accessible heading, return target, and safe escape", async () => {
  const [authRequiredPage, asyncState, appSource, styles] = await Promise.all([
    readFile(new URL("../src/pages/AuthRequiredPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/common/AsyncState.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/styles/global.css", import.meta.url), "utf8"),
  ]);

  assert.match(authRequiredPage, /pageHeading/);
  assert.match(authRequiredPage, /<main>/);
  assert.match(asyncState, /pageHeading \? <h1>\{title\}<\/h1>/);
  assert.match(authRequiredPage, /withReturnTo\(ROUTES\.login, returnTo\)/);
  assert.match(authRequiredPage, /로그인한 뒤 원래 보려던 페이지로 돌아옵니다/);
  assert.match(authRequiredPage, /href=\{ROUTES\.home\}/);
  assert.match(authRequiredPage, /홈으로 돌아가기/);
  assert.match(appSource, /getCurrentPathWithSearch\(\)/);
  assert.match(authRequiredPage, /className="auth-required-state"/);
  assert.match(authRequiredPage, /auth-required-state__actions/);
  assert.match(styles, /\.auth-required-state \{ align-items: flex-start; \}/);
  assert.match(styles, /\.auth-required-state \.async-state__dot \{ margin-top: 8px; \}/);
  assert.match(styles, /auth-required-state__actions \{[^}]*gap: 12px;[^}]*margin-top: 16px;/);
  assert.match(styles, /auth-required-state__actions \.async-state__action \{ margin-top: 0; \}/);
});
