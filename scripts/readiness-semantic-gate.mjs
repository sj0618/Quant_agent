#!/usr/bin/env node

import { stdin, stderr, stdout } from "node:process";
import { pathToFileURL } from "node:url";

export const REQUIRED_READINESS_CHECKS = Object.freeze([
  "auth_runtime",
  "main_db",
  "trading_data_db",
  "redis",
]);

function parseCliArguments(argv) {
  const options = {
    label: "readiness",
    requiredChecks: [...REQUIRED_READINESS_CHECKS],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!argument.startsWith("--")) {
      throw new Error(`Unexpected argument: ${argument}`);
    }
    const key = argument.slice(2).replace(/-([a-z])/gu, (_, letter) => letter.toUpperCase());
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }

  if (typeof options.checks === "string" && options.checks.trim()) {
    options.requiredChecks = options.checks
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }
  if (typeof options.label !== "string" || !options.label.trim()) {
    options.label = "readiness";
  }
  if (options.requiredChecks.length === 0) {
    throw new Error("readiness semantic gate requires at least one check name");
  }
  return options;
}

export function parseReadinessPayload(rawText) {
  if (typeof rawText !== "string" || !rawText.trim()) {
    throw new Error("readiness semantic gate requires JSON on stdin");
  }
  try {
    return JSON.parse(rawText);
  } catch (error) {
    throw new Error(`readiness semantic gate received invalid JSON: ${error.message}`);
  }
}

export function validateReadinessPayload(payload, { requiredChecks = REQUIRED_READINESS_CHECKS } = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("readiness payload must be an object");
  }
  if (payload.status !== "ready") {
    throw new Error(`readiness payload status must be ready, got ${String(payload.status)}`);
  }
  if (!Array.isArray(payload.checks) || payload.checks.length === 0) {
    throw new Error("readiness payload must contain checks");
  }

  const required = [...requiredChecks];
  const requiredSet = new Set(required);
  const seen = new Set();

  for (const [index, check] of payload.checks.entries()) {
    if (!check || typeof check !== "object" || Array.isArray(check)) {
      throw new Error(`readiness check ${index} must be an object`);
    }
    if (typeof check.name !== "string" || !check.name.trim()) {
      throw new Error(`readiness check ${index} must name a dependency`);
    }
    if (seen.has(check.name)) {
      throw new Error(`readiness payload repeats check ${check.name}`);
    }
    seen.add(check.name);
    if (check.ready !== true) {
      throw new Error(`readiness check is not ready: ${check.name}`);
    }
    if (check.reason != null) {
      throw new Error(`readiness check ${check.name} should not carry a reason when ready`);
    }
  }

  const missing = required.filter((name) => !seen.has(name));
  if (missing.length > 0) {
    throw new Error(`readiness payload is missing required checks: ${missing.join(", ")}`);
  }

  const unexpected = [...seen].filter((name) => !requiredSet.has(name));
  if (unexpected.length > 0) {
    throw new Error(`readiness payload includes unexpected checks: ${unexpected.join(", ")}`);
  }

  return {
    status: "ready",
    checks: payload.checks.map((check) => ({
      name: check.name,
      ready: true,
      reason: null,
    })),
  };
}

async function readAllStdin() {
  return await new Promise((resolve, reject) => {
    let input = "";
    stdin.setEncoding("utf8");
    stdin.on("data", (chunk) => {
      input += chunk;
    });
    stdin.once("end", () => {
      resolve(input);
    });
    stdin.once("error", reject);
  });
}

export async function runReadinessSemanticGateCli(
  argv = process.argv.slice(2),
  { readInput = readAllStdin, writeOutput = (value) => stdout.write(value) } = {},
) {
  const options = parseCliArguments(argv);
  const payload = parseReadinessPayload(await readInput());
  const result = validateReadinessPayload(payload, { requiredChecks: options.requiredChecks });

  writeOutput(
    `${JSON.stringify(
      {
        label: options.label,
        status: result.status,
        checks: result.checks.map((check) => check.name),
      },
      null,
      2,
    )}\n`,
  );
  return 0;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    process.exitCode = await runReadinessSemanticGateCli();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    stderr.write(`${message}\n`);
    process.exitCode = 1;
  }
}
