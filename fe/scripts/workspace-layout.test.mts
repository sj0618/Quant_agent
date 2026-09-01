import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("workspace uses a top strategy composer and preserves the live analysis request contract", async () => {
  const [workspace, composer, styles] = await Promise.all([
    read("../src/features/app/StrategyWorkspace.tsx"),
    read("../src/features/app/StrategyInputPanel.tsx"),
    read("../src/styles/global.css"),
  ]);

  assert.match(workspace, /presentation="dashboard"/);
  assert.match(composer, /presentation\?: "sidebar" \| "dashboard"/);
  assert.match(composer, /if \(presentation === "dashboard"\)/);
  assert.match(composer, /onAnalyze\(trimmedQuery\)/);
  assert.match(composer, /onCancel\(\)/);
  assert.match(styles, /\.workspace-shell \{[^}]*flex-direction: column/);
  assert.match(styles, /\.strategy-composer \{[^}]*width: min\(1180px/);
  assert.match(styles, /\.workspace-main \{[^}]*width: min\(1180px/);
});
