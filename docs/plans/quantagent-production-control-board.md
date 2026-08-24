# QuantAgent production control board

이 보드는 WBS 자체가 아니라, 상태 전이와 차단 사유를 같은 SHA에 묶어
추적하기 위한 보조 증적이다. 구조 검사는 `node scripts/check-production-plan.mjs`로
실행한다. 이 파일의 PASS는 문서 구조의 PASS일 뿐, 운영·실데이터·배포 완료가 아니다.

<!-- control-board:v1
{
  "schemaVersion": "quantagent-control-board.v1",
  "snapshot": {
    "gitSha": "f02672878f10ee038133b917a18d333e061187bc",
    "localOnly": true,
    "limitation": "This board is a local planning snapshot. It cannot establish production, live-data, deployment, or human-approval completion.",
    "scope": "PM-GOAL-00, PM-GOAL-01, PM-BOARD-01 planning preflight and current QA evidence blockers"
  },
  "transitions": [
    {
      "id": "TR-PLAN-001",
      "taskId": "PM-GOAL-00",
      "from": "not_started",
      "to": "in_progress",
      "at": "2026-08-24 10:00 KST",
      "gitSha": "f02672878f10ee038133b917a18d333e061187bc",
      "evidence": ["repo:scripts/check-production-plan.mjs@f02672878f10ee038133b917a18d333e061187bc", "repo:scripts/check-production-plan.test.mjs@f02672878f10ee038133b917a18d333e061187bc"],
      "owner": "윤서준",
      "reviewer": "pending-independent-reviewer",
      "limitation": "A structural PASS creates a reproducible planning preflight only. No human independent review has occurred, and the WBS row remains subject to its own evidence and reviewer requirements."
    },
    {
      "id": "TR-PLAN-002",
      "taskId": "PM-GOAL-01",
      "from": "not_started",
      "to": "in_progress",
      "at": "2026-08-24 10:00 KST",
      "gitSha": "f02672878f10ee038133b917a18d333e061187bc",
      "evidence": ["repo:docs/plans/quantagent-production-qa-local-evidence-contract-20260824.md@f02672878f10ee038133b917a18d333e061187bc", "repo:scripts/check-production-plan.test.mjs@f02672878f10ee038133b917a18d333e061187bc"],
      "owner": "윤서준",
      "reviewer": "pending-independent-reviewer",
      "limitation": "The PASS/FAIL behavior is tested locally. No human independent review has occurred; independent review and same-SHA immutable execution evidence are still required before any terminal WBS status."
    }
  ],
  "blockers": [
    {
      "id": "BL-PLAN-001",
      "owner": "윤서준",
      "reason": "The legacy production-readiness evaluator reports seven QA gates not PASS and 84 P0 rows without completed immutable evidence.",
      "impactedTaskIds": ["PM-GOAL-00", "PM-GOAL-01", "PM-BOARD-01"],
      "openedAt": "2026-08-24 10:00 KST",
      "nextReviewAt": "2026-08-25 10:00 KST",
      "recurrenceCount": 1,
      "lastReviewer": "Codex local verifier (not independent approval)",
      "evidence": ["repo:docs/plans/quantagent-production-qa-local-evidence-contract-20260824.md@f02672878f10ee038133b917a18d333e061187bc", "repo:scripts/check-production-plan.mjs@f02672878f10ee038133b917a18d333e061187bc"],
      "releaseDisposition": "blocked",
      "limitation": "This is a legacy-goal blocker. The requested 8/31 research MVP is a separate scope and does not inherit production completion."
    },
    {
      "id": "BL-DATA-001",
      "owner": "윤민호",
      "reason": "The four QA-DATA audit commands stop at collection because neither pandas_ta_classic nor pandas_ta is installed in the selected local test environment.",
      "impactedTaskIds": ["QA-DATA-AUDIT-01", "QA-DATA-AUDIT-02", "QA-DATA-AUDIT-03", "QA-DATA-AUDIT-04"],
      "openedAt": "2026-08-24 10:00 KST",
      "nextReviewAt": "2026-08-25 10:00 KST",
      "recurrenceCount": 1,
      "lastReviewer": "Codex local verifier (not independent approval)",
      "evidence": ["repo:DE/docs/point-in-time-universe-evidence-contract.md@f02672878f10ee038133b917a18d333e061187bc", "repo:docs/plans/quantagent-production-qa-local-evidence-contract-20260824.md@f02672878f10ee038133b917a18d333e061187bc"],
      "releaseDisposition": "blocked",
      "limitation": "Installing an optional local dependency alone cannot substitute for a PostgreSQL source/as-of/freshness/lineage evidence run."
    },
    {
      "id": "BL-METRIC-001",
      "owner": "윤민호",
      "reason": "Profit-factor prose describes gross-profit/gross-loss period returns, while the current engine computes a bounded ratio from win rate; the registry contract therefore cannot be approved.",
      "impactedTaskIds": ["MR-REG-01", "MR-PF-01", "MR-ALL-01"],
      "openedAt": "2026-08-24 10:00 KST",
      "nextReviewAt": "2026-08-25 10:00 KST",
      "recurrenceCount": 1,
      "lastReviewer": "Codex local verifier (not independent approval)",
      "evidence": ["repo:ai/ai_graph/quant_explanations.py@f02672878f10ee038133b917a18d333e061187bc", "repo:ai/ai_graph/nodes/backtest.py@f02672878f10ee038133b917a18d333e061187bc", "repo:docs/plans/quantagent-profit-factor-contract.md@f02672878f10ee038133b917a18d333e061187bc"],
      "releaseDisposition": "blocked",
      "limitation": "Local serialization tests can prove shape consistency but cannot choose the business definition or approve a repaired formula."
    }
  ]
}
-->

## 상태 전이 기록

| Record ID | 대상 ID | 이전 → 현재 | 시각 | Git SHA | 증적 URI | Owner | Independent reviewer | 한계 |
|---|---|---|---|---|---|---|---|---|
| TR-PLAN-001 | PM-GOAL-00 | not_started → in_progress | 2026-08-24 10:00 KST | `f026728` | `repo:scripts/check-production-plan.mjs@f026728` | 윤서준 | pending-independent-reviewer | 구조 검증만 수행했으며 사람 검토는 아직 없다. |
| TR-PLAN-002 | PM-GOAL-01 | not_started → in_progress | 2026-08-24 10:00 KST | `f026728` | `repo:docs/plans/quantagent-production-qa-local-evidence-contract-20260824.md@f026728` | 윤서준 | pending-independent-reviewer | local PASS/FAIL 계약만 기록했으며 사람 검토는 아직 없다. |

## 차단·재발 기록

| Blocker ID | 영향 작업 | 발견 근거 | Owner | 다음 확인 | 재발 횟수 | 마지막 검토자 | 해제 증적 | Release disposition |
|---|---|---|---|---|---:|---|---|---|
| BL-PLAN-001 | PM-GOAL-00, PM-GOAL-01, PM-BOARD-01 | legacy evaluator의 7 gate/84 P0 failure | 윤서준 | 2026-08-25 10:00 KST | 1 | Codex local verifier (not independent approval) | 같은 SHA의 evaluator PASS + 독립 APPROVE | blocked |
| BL-DATA-001 | QA-DATA-AUDIT-01~04 | pandas TA import collection failure | 윤민호 | 2026-08-25 10:00 KST | 1 | Codex local verifier (not independent approval) | executable audit + PostgreSQL manifest bundle | blocked |
| BL-METRIC-001 | MR-REG-01, MR-PF-01, MR-ALL-01 | profit-factor formula/implementation disagreement | 윤민호 | 2026-08-25 10:00 KST | 1 | Codex local verifier (not independent approval) | approved definition + engine/registry/API test | blocked |

## 사용 규칙

1. 새 상태 전이는 JSON marker와 표를 함께 갱신한다. `Git SHA`, 증적 URI, owner,
   독립 reviewer, limitation이 하나라도 비면 preflight는 FAIL이다.
2. 한 validation bundle 안의 전이와 증적은 모두 `snapshot.gitSha`와 같아야 한다.
   새 SHA를 검증할 때는 새 snapshot을 만들고 이전 보드를 덮어쓰지 않는다.
3. `localOnly: true` 상태에서는 `complete`나 운영 완료를 선언하지 않는다. 서버의
   PostgreSQL source/as-of/freshness/lineage, 배포 artifact, 독립 승인까지 갖춘
   immutable bundle만 그 제한을 바꿀 수 있다.
