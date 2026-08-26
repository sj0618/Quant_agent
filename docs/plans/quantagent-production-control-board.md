# QuantAgent production control board (2026-08-25, Quant_agent 기준선)

이 보드는 2026-08-24 보드를 **덮어쓰지 않았다**. 그 내용은 바이트 그대로
[`…-20260824.md`](quantagent-production-control-board-20260824.md)에 남아 있고, 이 파일은
새 root(`470d33e`)의 새 snapshot이다.

파일명이 아니라 정본 경로를 이 snapshot이 차지하는 이유는 하나다. `PM-GOAL-00`의 고정
명령은 `--board` 인자 없이 이 경로를 읽어야 하는데, 이전 보드의 `snapshot.gitSha`
(`f026728`)는 이관 후 `HEAD`의 조상이 아니라 자동으로 exit 1이 된다. 도달 불가 SHA를
거부하는 것은 preflight의 설계된 동작이며, 새 snapshot을 열라는 신호다.

```sh
node scripts/check-production-plan.mjs
```

계약은 [preflight 명령 계약](quantagent-preflight-command-contract-20260825.md)에 고정돼 있다.
이 파일의 PASS는 문서 구조의 PASS일 뿐, 운영·실데이터·배포 완료가 아니다.

<!-- control-board:v1
{
  "schemaVersion": "quantagent-control-board.v1",
  "snapshot": {
    "gitSha": "aa318206aa684389a4c5a11255cb0658f70cbcc7",
    "localOnly": true,
    "limitation": "This board is a local planning snapshot on the sj0618/Quant_agent root. It cannot establish production, live-data, deployment, or human-approval completion.",
    "scope": "PM-GOAL-00 and PM-GOAL-01 re-verification after the repository migration, and the blockers that keep the AI-core lane short of completion"
  },
  "transitions": [
    {
      "id": "TR-BASE-001",
      "taskId": "PM-GOAL-00",
      "from": "in_progress",
      "to": "evidence_pending",
      "at": "2026-08-25 10:00 KST",
      "gitSha": "aa318206aa684389a4c5a11255cb0658f70cbcc7",
      "evidence": [
        "repo:docs/evidence/PM-GOAL-00/72da24067c54067989f58d0947271281c41d46c1.md@aa318206aa684389a4c5a11255cb0658f70cbcc7",
        "repo:scripts/check-production-plan.mjs@aa318206aa684389a4c5a11255cb0658f70cbcc7"
      ],
      "owner": "윤서준",
      "reviewer": "pending-조은채",
      "limitation": "The preflight CLI now honours both halves of its exit contract; on the previous root it exited 0 without reading the board. A structural PASS is still document structure only, and no independent review has occurred."
    },
    {
      "id": "TR-BASE-002",
      "taskId": "PM-GOAL-01",
      "from": "in_progress",
      "to": "evidence_pending",
      "at": "2026-08-25 10:00 KST",
      "gitSha": "aa318206aa684389a4c5a11255cb0658f70cbcc7",
      "evidence": [
        "repo:docs/evidence/PM-GOAL-01/72da24067c54067989f58d0947271281c41d46c1.md@aa318206aa684389a4c5a11255cb0658f70cbcc7",
        "repo:docs/plans/quantagent-preflight-command-contract-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7",
        "repo:scripts/check-production-plan.test.mjs@aa318206aa684389a4c5a11255cb0658f70cbcc7"
      ],
      "owner": "윤서준",
      "reviewer": "pending-조은채",
      "limitation": "The exact commands and their exit 0/non-zero examples are measured and frozen. The document freezes observed behaviour, not the correctness of the rules it records, and carries no reviewer verdict."
    }
  ],
  "blockers": [
    {
      "id": "BL-PLAN-001",
      "owner": "윤서준",
      "reason": "The legacy production-readiness evaluator reports seven QA gates not PASS and 84 P0 rows without completed immutable evidence. Re-checked on this root: still open.",
      "impactedTaskIds": [
        "PM-GOAL-00",
        "PM-GOAL-01",
        "PM-BOARD-01"
      ],
      "openedAt": "2026-08-24 10:00 KST",
      "nextReviewAt": "2026-08-26 10:00 KST",
      "recurrenceCount": 2,
      "lastReviewer": "Claude local verifier (not independent approval)",
      "evidence": [
        "repo:docs/evidence/_RUNNER-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7",
        "repo:scripts/check-production-plan.mjs@aa318206aa684389a4c5a11255cb0658f70cbcc7"
      ],
      "releaseDisposition": "blocked",
      "limitation": "Repairing the preflight narrows how this blocker can hide but does not clear it. The gate and P0 evidence counts are unchanged."
    },
    {
      "id": "BL-BASE-001",
      "owner": "윤서준",
      "reason": "This runner has no CI run and no deployed-server probe, so AI-core lane rows cannot reach completion regardless of local results. The 8/24 bundles included read-only probes of the deployed service; this baseline includes none.",
      "impactedTaskIds": [
        "PM-GOAL-00",
        "PM-GOAL-01"
      ],
      "openedAt": "2026-08-25 10:00 KST",
      "nextReviewAt": "2026-08-26 10:00 KST",
      "recurrenceCount": 0,
      "lastReviewer": "Claude local verifier (not independent approval)",
      "evidence": [
        "repo:docs/evidence/_RUNNER-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7",
        "repo:docs/plans/yunseojun-ai-core-lane-status-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7"
      ],
      "releaseDisposition": "blocked",
      "limitation": "Opening this blocker records a missing evidence axis. It does not schedule the CI or server run that would close it."
    }
  ]
}
-->

## 상태 전이 기록

| Record ID | 대상 ID | 이전 → 현재 | 시각 | Git SHA | 증적 URI | Owner | Independent reviewer | 한계 |
|---|---|---|---|---|---|---|---|---|
| TR-BASE-001 | PM-GOAL-00 | in_progress → evidence_pending | 2026-08-25 10:00 KST | `aa31820` | `repo:docs/evidence/PM-GOAL-00/72da24067c54067989f58d0947271281c41d46c1.md@aa318206aa684389a4c5a11255cb0658f70cbcc7` | 윤서준 | pending-조은채 | The preflight CLI now honours both halves of its exit contract; on the previous root it exited 0 without reading the board. A structural PASS is still document structure only, and no independent review has occurred. |
| TR-BASE-002 | PM-GOAL-01 | in_progress → evidence_pending | 2026-08-25 10:00 KST | `aa31820` | `repo:docs/evidence/PM-GOAL-01/72da24067c54067989f58d0947271281c41d46c1.md@aa318206aa684389a4c5a11255cb0658f70cbcc7` | 윤서준 | pending-조은채 | The exact commands and their exit 0/non-zero examples are measured and frozen. The document freezes observed behaviour, not the correctness of the rules it records, and carries no reviewer verdict. |

## 차단·재발 기록

| Blocker ID | Git SHA | 영향 작업 | Owner | 다음 확인 | 재발 횟수 | 마지막 검토자 | 해제 증적 URI | Release disposition |
|---|---|---|---|---:|---|---|---|---|
| BL-PLAN-001 | `aa31820` | PM-GOAL-00, PM-GOAL-01, PM-BOARD-01 | 윤서준 | 2026-08-26 10:00 KST | 2 | Claude local verifier (not independent approval) | `repo:docs/evidence/_RUNNER-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7` | blocked |
| BL-BASE-001 | `aa31820` | PM-GOAL-00, PM-GOAL-01 | 윤서준 | 2026-08-26 10:00 KST | 0 | Claude local verifier (not independent approval) | `repo:docs/evidence/_RUNNER-20260825.md@aa318206aa684389a4c5a11255cb0658f70cbcc7` | blocked |

## 이 snapshot이 이전과 다른 점

- `origin`이 `sj0618/Quant_agent`로 이동했다. 새 `main`(`470d33e`)은 orphan 스냅샷이지만
  tree는 이전과 같은 `4b4f0f9`다. 코드는 이동하지 않았고 커밋 그래프만 새로 시작했다.
- `PM-GOAL-00`·`PM-GOAL-01`이 `in_progress` → `evidence_pending`으로 옮겨졌다. `complete`가
  아니다. `localOnly: true`인 동안 preflight 자체가 `complete` 전이를 거부한다.
- `BL-PLAN-001`의 재발 횟수가 1에서 2로 올랐다. 2026-08-25 확인 결과 해제 근거가 없다.
- `BL-BASE-001`이 새로 열렸다. 이 기준선에는 CI 실행과 서버 probe가 모두 없다.
- `BL-METRIC-001`과 `BL-DATA-001`(소유자 윤민호)은 이 snapshot의 scope 밖이라 옮기지 않았다.
  8/24 보드에 그대로 있으며 해소된 것으로 읽지 않는다.
