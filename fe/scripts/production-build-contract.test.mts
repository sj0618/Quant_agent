import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";

function run(command: string, args: string[], cwd: string) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: "pipe" });
    let stderr = "";
    child.stderr.on("data", (chunk) => { stderr += String(chunk); });
    child.once("error", reject);
    child.once("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`production build exited ${code}: ${stderr}`));
    });
  });
}

async function filesUnder(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  }));
  return nested.flat();
}

function isTextBundle(path: string) {
  return /\.(?:css|html|js|json|map)$/i.test(path);
}

test("production build contains no Vite development client, source module, or localhost HMR endpoint", async () => {
  const outputDirectory = await mkdtemp(join(tmpdir(), "quantagent-fe-production-"));
  try {
    await run(process.execPath, ["./node_modules/vite/bin/vite.js", "build", "--outDir", outputDirectory], process.cwd());
    const textAssets = (await filesUnder(outputDirectory)).filter(isTextBundle);
    assert.ok(textAssets.length > 0, "production build did not produce inspectable text assets");
    const output = await Promise.all(textAssets.map((path) => readFile(path, "utf8")));
    const joined = output.join("\n");

    assert.doesNotMatch(joined, /\/@vite\/client/);
    assert.doesNotMatch(joined, /\/src\/main\.(?:tsx|ts|jsx|js)/);
    assert.doesNotMatch(joined, /localhost:\d+/i);
  } finally {
    await rm(outputDirectory, { force: true, recursive: true });
  }
});
