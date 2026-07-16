#!/usr/bin/env node
// TEMP(dev-auth-gate): delete this script with SitePasswordGate.tsx.
//
// Mints a fresh, salted, time-limited VITE_SITE_PASSWORD_ENTRIES value for the
// landing-page password gate. Run it whenever the current batch is about to expire
// (see --lifetime-days) to rotate the hash without changing anyone's password.
// Passwords are only ever read from the terminal and are never written to disk,
// logged, or echoed back — only the resulting salt:hash:expiresAt entries are
// printed, ready to paste into fe/.env (local) and the deploy server's .env.
//
// Usage:
//   node fe/scripts/generate-site-gate-entries.mjs [--lifetime-days 14] [--count 5]

import { createHash, randomBytes } from "node:crypto";
import { createInterface } from "node:readline";

function parseArgs(argv) {
  const args = { lifetimeDays: 14, count: 5 };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--lifetime-days") {
      args.lifetimeDays = Number(argv[i + 1]);
      i += 1;
    } else if (argv[i] === "--count") {
      args.count = Number(argv[i + 1]);
      i += 1;
    }
  }
  if (!Number.isFinite(args.lifetimeDays) || args.lifetimeDays <= 0) {
    throw new Error("--lifetime-days must be a positive number");
  }
  if (!Number.isFinite(args.count) || args.count <= 0) {
    throw new Error("--count must be a positive integer");
  }
  return args;
}

// Node's readline has no public "masked input" API; rather than depend on the
// undocumented _writeToOutput hook (fragile across versions), this prompts in
// plain text. Run it in a private terminal — nothing typed here is ever written
// to disk, logged, or included in the generated output beyond the derived hash.
// Prompts are read via the async iterator (not repeated rl.question() calls):
// on piped/non-TTY stdin, readline can buffer multiple lines from one chunk and
// question()'s one-shot listener silently drops all but the first.
function makePrompter(rl) {
  const lines = rl[Symbol.asyncIterator]();
  return async function prompt(question) {
    process.stdout.write(question);
    const { value, done } = await lines.next();
    if (done) {
      throw new Error("input ended before all passwords were entered");
    }
    return value;
  };
}

function sha256Hex(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

async function main() {
  const { lifetimeDays, count } = parseArgs(process.argv.slice(2));
  const expiresAt = Math.floor(Date.now() / 1000) + lifetimeDays * 24 * 60 * 60;

  console.log(`Generating ${count} entries, valid until ${new Date(expiresAt * 1000).toISOString()}.`);
  console.log("Type each person's password (visible in this terminal, never written to disk):\n");

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const prompt = makePrompter(rl);
  const entries = [];
  try {
    for (let i = 1; i <= count; i += 1) {
      const password = await prompt(`  person ${i} password: `);
      if (!password) {
        throw new Error(`person ${i} password was empty`);
      }
      const salt = randomBytes(16).toString("hex");
      const hash = sha256Hex(`${salt}:${password}`);
      entries.push(`${salt}:${hash}:${expiresAt}`);
    }
  } finally {
    rl.close();
  }

  console.log("\nPaste this into fe/.env (local) and the deploy server's .env, then redeploy:\n");
  console.log(`VITE_SITE_PASSWORD_ENTRIES=${entries.join(",")}`);
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exitCode = 1;
});
