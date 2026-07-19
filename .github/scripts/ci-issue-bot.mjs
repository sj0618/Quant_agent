import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const ACTIONABLE_CONCLUSIONS = new Set([
  "action_required",
  "failure",
  "startup_failure",
  "timed_out",
]);
const AUTOMATED_LABEL = "automated";

function markerFor(workflowId, jobName) {
  const key = `${workflowId}:${jobName}`;
  const digest = createHash("sha256").update(key).digest("hex").slice(0, 16);
  return `<!-- ci-issue-bot:${digest} -->`;
}

function shorten(value, limit = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function githubApi({ apiUrl, repository, token }) {
  return async (path, options = {}) => {
    const response = await fetch(`${apiUrl}/repos/${repository}${path}`, {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "quant-agent-ci-issue-bot",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { message: text };
      }
    }
    if (!response.ok) {
      const error = new Error(
        `GitHub API ${response.status}: ${payload?.message ?? "unknown error"}`,
      );
      error.status = response.status;
      throw error;
    }
    return payload;
  };
}

async function listOpenIssuesWithMarker(api, marker) {
  for (let page = 1; page <= 10; page += 1) {
    const issues = await api(`/issues?state=open&per_page=100&page=${page}`);
    const match = issues.find(
      (issue) => !issue.pull_request && String(issue.body ?? "").includes(marker),
    );
    if (match) return match;
    if (issues.length < 100) return null;
  }
  return null;
}

async function ensureAutomatedLabel(api) {
  try {
    await api(`/labels/${encodeURIComponent(AUTOMATED_LABEL)}`);
  } catch (error) {
    if (error.status !== 404) throw error;
    try {
      await api("/labels", {
        method: "POST",
        body: { name: AUTOMATED_LABEL, color: "6f42c1", description: "자동화가 생성한 이슈" },
      });
    } catch (createError) {
      // 두 워크플로가 동시에 첫 라벨을 만들 때의 422 경합은 안전하게 무시한다.
      if (createError.status !== 422) throw createError;
    }
  }
}

function jobDetails(job) {
  const failedSteps = (job.steps ?? [])
    .filter((step) => step.conclusion && step.conclusion !== "success")
    .map((step) => `- ${shorten(step.name)} (${step.conclusion})`);
  return failedSteps.length > 0 ? failedSteps.join("\n") : "- 실패한 작업 단계 정보를 찾지 못했습니다.";
}

function issueBody({ marker, run, job }) {
  const workflowName = run.name ?? "알 수 없는 워크플로";
  const branch = run.head_branch ?? "알 수 없는 브랜치";
  const sha = run.head_sha ?? "알 수 없는 커밋";
  const runUrl = run.html_url ?? "(실행 URL 없음)";
  const jobUrl = job.html_url ?? runUrl;
  return `${marker}

## 자동 감지된 CI 실패

GitHub Actions 실행이 성공하지 못해 자동으로 생성된 이슈입니다.

- 워크플로: **${shorten(workflowName)}**
- 작업: **${shorten(job.name ?? "알 수 없는 작업")}**
- 결과: **${job.conclusion ?? run.conclusion ?? "알 수 없음"}**
- 브랜치: \`${shorten(branch, 120)}\`
- 커밋: \`${sha}\`
- 워크플로 실행: [실행 로그](${runUrl})
- 작업 로그: [작업 상세](${jobUrl})

### 실패 단계
${jobDetails(job)}

실행 로그에서 원인을 확인하고 수정 후 같은 커밋을 재실행하거나 새 커밋을 푸시하세요.`;
}

export async function runBot({ event, api }) {
  const run = event?.workflow_run;
  if (!run || !ACTIONABLE_CONCLUSIONS.has(run.conclusion)) {
    return { created: 0, updated: 0, skipped: true };
  }

  const jobsPayload = await api(`/actions/runs/${run.id}/jobs?per_page=100`);
  const jobs = (jobsPayload?.jobs ?? []).filter((job) =>
    ACTIONABLE_CONCLUSIONS.has(job.conclusion),
  );
  const reports = jobs.length > 0 ? jobs : [{ name: "workflow", conclusion: run.conclusion, steps: [] }];
  let created = 0;
  let updated = 0;

  for (const job of reports) {
    const workflowId = run.workflow_id ?? run.name ?? "unknown-workflow";
    const marker = markerFor(workflowId, job.name ?? "workflow");
    const body = issueBody({ marker, run, job });
    const existing = await listOpenIssuesWithMarker(api, marker);
    if (existing) {
      await api(`/issues/${existing.number}/comments`, {
        method: "POST",
        body: { body },
      });
      updated += 1;
      continue;
    }

    await ensureAutomatedLabel(api);
    await api("/issues", {
      method: "POST",
      body: {
        title: `[CI] ${shorten(run.name ?? "워크플로")} 실패: ${shorten(job.name ?? "workflow")}`,
        body,
        labels: [AUTOMATED_LABEL],
      },
    });
    created += 1;
  }

  return { created, updated, skipped: false };
}

async function main() {
  const token = process.env.GITHUB_TOKEN;
  const repository = process.env.GITHUB_REPOSITORY;
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!token || !repository || !eventPath) {
    throw new Error("GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_PATH가 필요합니다.");
  }

  const event = JSON.parse(await readFile(eventPath, "utf8"));
  const api = githubApi({
    apiUrl: process.env.GITHUB_API_URL ?? "https://api.github.com",
    repository,
    token,
  });
  const result = await runBot({ event, api });
  console.log(JSON.stringify(result));
}

if (process.env.CI_ISSUE_BOT_TEST !== "1" && process.env.GITHUB_EVENT_PATH) {
  await main();
}
