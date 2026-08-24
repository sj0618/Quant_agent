import { expect, test, type Page } from "@playwright/test";

interface BrowserSignals {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
}

function browserSignals(page: Page): BrowserSignals {
  const signals: BrowserSignals = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") {
      signals.consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => signals.pageErrors.push(error.message));
  page.on("requestfailed", (request) => signals.failedRequests.push(`${request.method()} ${request.url()}`));
  return signals;
}

function expectNoClientFailures(signals: BrowserSignals) {
  expect(signals.pageErrors).toEqual([]);
  expect(signals.failedRequests).toEqual([]);
}

async function expectKeyboardFocusVisible(page: Page) {
  await expect(page.locator(":focus")).toHaveCount(1);
  await expect(page.locator(":focus")).toBeVisible();
  await expect(page.locator(":focus")).toHaveCSS("outline-style", /^(auto|solid|dotted|dashed)$/);
}

test.describe("public recovery paths", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("mobile landing has no horizontal overflow and exposes a keyboard focus target", async ({ page }) => {
    const signals = browserSignals(page);

    const response = await page.goto("/", { waitUntil: "networkidle" });

    expect(response?.ok()).toBe(true);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("수익률보다 먼저");
    expect(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);

    await page.keyboard.press("Tab");
    await expectKeyboardFocusVisible(page);
    expectNoClientFailures(signals);
    expect(signals.consoleErrors).toEqual([]);
  });

  test("signed-out app route preserves returnTo at the login recovery wall", async ({ page }) => {
    const signals = browserSignals(page);

    const response = await page.goto("/app", { waitUntil: "networkidle" });

    expect(response?.ok()).toBe(true);
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fapp$/);
    await expect(page.getByRole("heading", { name: "Google 계정으로 시작" })).toBeVisible();
    await expect(page.getByText("로그인 후 요청하신 화면으로 이동합니다.")).toBeVisible();
    await expect(page.getByRole("link", { name: "홈으로" })).toHaveAttribute("href", "/");

    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "QuantAgent" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Google로 로그인" })).toBeFocused();
    await expectKeyboardFocusVisible(page);
    expectNoClientFailures(signals);
    expect(signals.consoleErrors).toEqual([]);
  });

  test("unknown route is an actual 404 with a keyboard-accessible home recovery action", async ({ page }) => {
    const signals = browserSignals(page);

    const response = await page.goto("/this-route-should-not-exist-20260825", { waitUntil: "networkidle" });

    expect(response?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "페이지를 찾을 수 없습니다" })).toBeVisible();

    const home = page.getByRole("link", { name: "홈으로 가기" });
    await expect(home).toHaveAttribute("href", "/");
    await home.focus();
    await expectKeyboardFocusVisible(page);

    await home.click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("수익률보다 먼저");
    expectNoClientFailures(signals);
    expect(signals.consoleErrors).toEqual([
      "Failed to load resource: the server responded with a status of 404 (Not Found)",
    ]);
  });
});
