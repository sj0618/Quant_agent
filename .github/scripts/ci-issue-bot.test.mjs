process.env.CI_ISSUE_BOT_TEST = "1";
import assert from "node:assert/strict";
const { runBot } = await import("./ci-issue-bot.mjs");

const event = {
  workflow_run: {
    id: 123,
    workflow_id: 456,
    name: "Code checks",
    conclusion: "failure",
    head_branch: "main",
    head_sha: "abc123",
    html_url: "https://github.com/example/repo/actions/runs/123",
  },
};

let createdBody = null;
const firstCalls = [];
const firstApi = async (path, options = {}) => {
  firstCalls.push({ path, options });
  if (path.startsWith("/actions/runs/")) {
    return {
      jobs: [{
        name: "Python checks",
        conclusion: "failure",
        html_url: "https://github.com/example/repo/actions/runs/123/job/1",
        steps: [{ name: "Run tests", conclusion: "failure" }],
      }],
    };
  }
  if (path.startsWith("/issues?")) return [];
  if (path === "/labels/automated") {
    const error = new Error("not found");
    error.status = 404;
    throw error;
  }
  if (path === "/labels" && options.method === "POST") return {};
  if (path === "/issues" && options.method === "POST") {
    createdBody = options.body.body;
    return { number: 7 };
  }
  throw new Error(`unexpected API call: ${path}`);
};

assert.deepEqual(await runBot({ event, api: firstApi }), {
  created: 1,
  updated: 0,
  skipped: false,
});
assert.match(createdBody, /<!-- ci-issue-bot:/);
assert.match(createdBody, /Run tests \(failure\)/);
assert.equal(firstCalls.filter(({ path }) => path === "/labels").length, 1);

const secondCalls = [];
const secondApi = async (path, options = {}) => {
  secondCalls.push({ path, options });
  if (path.startsWith("/actions/runs/")) {
    return { jobs: [{ name: "Python checks", conclusion: "failure", steps: [] }] };
  }
  if (path.startsWith("/issues?")) return [{ number: 7, body: createdBody }];
  if (path === "/issues/7/comments" && options.method === "POST") return {};
  throw new Error(`unexpected API call: ${path}`);
};

assert.deepEqual(await runBot({ event, api: secondApi }), {
  created: 0,
  updated: 1,
  skipped: false,
});
assert.equal(secondCalls.some(({ path }) => path === "/issues/7/comments"), true);

let apiCalled = false;
const skipped = await runBot({
  event: { workflow_run: { conclusion: "cancelled" } },
  api: async () => {
    apiCalled = true;
  },
});
assert.deepEqual(skipped, { created: 0, updated: 0, skipped: true });
assert.equal(apiCalled, false);

console.log("ci-issue-bot tests passed");
