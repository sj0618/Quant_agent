# QuantAgent Production Control Board

이 문서는 상태 전이와 blocker를 증적으로 관리하는 내부 control board다.
진행률에는 증적 URI가 없는 작업을 포함하지 않는다.

## 필수 열 계약

### 상태 전이

`transition_id`, `work_item_id`, `previous_status`, `new_status`, `revision`,
`occurred_at`, `evidence_uri`, `actor`, `reason`

### Blocker

`blocker_id`, `status`, `discovered_at`, `discovery_evidence_uri`, `affected_work`,
`next_check_at`, `owner`, `recurrence_count`, `last_reviewer`,
`resolution_evidence_uri`

`recurrence_count`는 최초 발견을 제외한 재발 횟수다. 해제되지 않은 blocker도 현재 상태와 다음 확인 시점을 기록하며, 해제 증적 칸에는 해당 상태를 입증하는 board 증적 URI를 남긴다.

## 집계

| metric | value | definition |
|---|---:|---|
| state_transition_count | 1 | 상태 전이 행 수 |
| state_transition_evidence_uri_count | 1 | 유효한 상태 전이 증적 URI 수 |
| blocker_count | 1 | blocker 행 수 |
| blocker_evidence_uri_count | 2 | 발견·해제 증적 URI 수 |
| blocker_recurrence_total | 2 | 모든 blocker의 재발 횟수 합계 |
| recurring_blocker_count | 1 | 재발 횟수가 1 이상인 blocker 수 |
| max_blocker_recurrence_count | 2 | 단일 blocker의 최대 재발 횟수 |

## 상태 전이 증적

| transition_id | work_item_id | previous_status | new_status | revision | occurred_at | evidence_uri | actor | reason |
|---|---|---|---|---|---|---|---|---|
| ST-PM-BOARD-01-001 | PM-BOARD-01 | planned | implemented | branch:feat/control-board-evidence | 2026-08-21T00:00:00+09:00 | evidence://PM-BOARD-01-transition-001 | automation | 상태 전이·증적·재발 집계 계약 구현 |

## Blocker 원장

| blocker_id | status | discovered_at | discovery_evidence_uri | affected_work | next_check_at | owner | recurrence_count | last_reviewer | resolution_evidence_uri |
|---|---|---|---|---|---|---|---:|---|---|
| BLK-PM-BOARD-001 | open | 2026-08-21T00:00:00+09:00 | evidence://BLK-PM-BOARD-001-discovered | PM-BOARD-01 | 2026-08-22T00:00:00+09:00 | schedule-evidence-manager | 2 | independent-reviewer | evidence://BLK-PM-BOARD-001-current-state |

## 검증

```powershell
cd ai
python -m pytest -q tests/test_control_board.py
python scripts/validate_control_board.py --board ../docs/plans/quantagent-production-control-board.md
```

검증기는 필수 열 누락, 빈 증적 URI, 음수·비정수 재발 횟수, board에 표시된 집계와 원장 재계산 결과의 불일치를 실패로 처리한다.
