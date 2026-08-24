import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

test("production bundle contains no report resend write path", async () => {
  const assetsDirectory = new URL("../dist/assets/", import.meta.url);
  const assetNames = await readdir(assetsDirectory);
  const scripts = await Promise.all(
    assetNames
      .filter((name) => name.endsWith(".js"))
      .map((name) => readFile(new URL(name, assetsDirectory), "utf8")),
  );
  const bundle = scripts.join("\n");

  assert.doesNotMatch(bundle, /\/resend/);
});
