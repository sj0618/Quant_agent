#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { constants } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
export const REPOSITORY_ROOT = resolve(scriptDirectory, "..");

const SENSITIVE_ENVIRONMENT_KEYS = [
  "AI_AOAI_API_KEY",
  "AI_AOAI_ENDPOINT",
  "AI_AOAI_RESPONSES_URL",
  "AI_DATABASE_DSN",
  "AOAI_API_KEY",
  "AZURE_OPENAI_API_KEY",
  "AZURE_OPENAI_ENDPOINT",
  "DATABASE_URL",
  "OPENAI_API_KEY",
  "QUANT_DB_DSN",
  "REDIS_URL",
  "SCREENING_PIPELINE_API_KEY",
  "TRADING_DATA_DATABASE_URL",
];

/**
 * The release gate is intentionally local-only. It strips potential live
 * provider and datastore configuration before each child test process.
 */
export function createOfflineTestEnvironment(source = process.env) {
  const environment = {
    ...source,
    AUTH_ENABLED: "0",
    AI_AUDIT_SINK: "noop",
    AI_JOB_STORE: "memory",
    AI_LLM_PROVIDER: "mock",
    AI_AOAI_LIVE_TEST: "0",
    SCREENING_PIPELINE_LIVE_API: "0",
  };

  for (const key of SENSITIVE_ENVIRONMENT_KEYS) {
    delete environment[key];
  }
  for (const key of Object.keys(environment)) {
    if (/^AI_LLM_[A-Z0-9_]+_(?:API_KEY|ENDPOINT|RESPONSES_URL|URL)$/u.test(key)) {
      delete environment[key];
    }
  }
  return environment;
}

function createBackendContractEnvironment(source = process.env) {
  const environment = createOfflineTestEnvironment(source);
  delete environment.AUTH_ENABLED;
  return environment;
}

export function resolveReleaseTrustPython({
  repositoryRoot = REPOSITORY_ROOT,
  environment = process.env,
  exists = existsSync,
} = {}) {
  const override = environment.RELEASE_TRUST_PYTHON?.trim();
  if (override) {
    return override;
  }

  const workspacePython = join(repositoryRoot, "ai", ".venv", "bin", "python");
  return exists(workspacePython) ? workspacePython : "python3.11";
}

export function buildReleaseTrustChecks({
  repositoryRoot = REPOSITORY_ROOT,
  environment = process.env,
  exists = existsSync,
} = {}) {
  const python = resolveReleaseTrustPython({ repositoryRoot, environment, exists });
  const aiTestEnvironment = createOfflineTestEnvironment(environment);
  const backendTestEnvironment = createBackendContractEnvironment(environment);

  return [
    {
      name: "ai-api-and-research-contracts",
      command: python,
      args: [
        "-m",
        "pytest",
        "-q",
        "ai/tests/test_api.py",
        "ai/tests/test_llm_aoai.py",
        "ai/tests/test_live_provider_fail_closed.py",
        "ai/tests/test_research_request_preflight.py",
        "ai/tests/test_research_contract.py",
        "ai/tests/test_research_contract_api.py",
      ],
      cwd: repositoryRoot,
      environment: aiTestEnvironment,
    },
    {
      name: "backtest-metric-contracts",
      command: python,
      args: [
        "-m",
        "pytest",
        "-q",
        "backtest_module/tests/test_backtest.py",
        "ai/tests/test_ai_graph_backtest_module_integration.py",
      ],
      cwd: repositoryRoot,
      environment: aiTestEnvironment,
    },
    {
      name: "backend-auth-report-and-deploy-contracts",
      command: python,
      args: [
        "-m",
        "pytest",
        "-q",
        "backend/tests/unit/test_auth_config.py",
        "backend/tests/unit/test_auth_core.py",
        "backend/tests/unit/test_auth_routes.py",
        "backend/tests/unit/test_fe_contract_routes.py",
        "backend/tests/unit/test_track_c_store.py",
        "backend/tests/unit/test_runtime_perf.py",
        "backend/tests/unit/test_deploy_workflow_contract.py",
      ],
      cwd: repositoryRoot,
      environment: backendTestEnvironment,
    },
    {
      name: "frontend-production-build-and-contracts",
      command: "npm",
      args: ["test"],
      cwd: join(repositoryRoot, "fe"),
      environment: backendTestEnvironment,
    },
  ];
}

export function exitCodeFromResult(result) {
  if (result.error) {
    return result.error.code === "ENOENT" ? 127 : 1;
  }
  if (typeof result.status === "number") {
    return result.status;
  }
  if (result.signal) {
    return 128 + (constants.signals[result.signal] ?? 1);
  }
  return 1;
}

export function runReleaseTrust({
  checks = buildReleaseTrustChecks(),
  environment = createOfflineTestEnvironment(),
  run = spawnSync,
} = {}) {
  for (const check of checks) {
    process.stdout.write(`\n[release-trust] ${check.name}\n`);
    const result = run(check.command, check.args, {
      cwd: check.cwd,
      env: check.environment ?? environment,
      shell: false,
      stdio: "inherit",
    });
    const exitCode = exitCodeFromResult(result);
    if (exitCode !== 0) {
      process.stderr.write(`[release-trust] failed: ${check.name} (exit ${exitCode})\n`);
      return exitCode;
    }
  }
  process.stdout.write("[release-trust] all offline gates passed\n");
  return 0;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  process.exitCode = runReleaseTrust();
}
