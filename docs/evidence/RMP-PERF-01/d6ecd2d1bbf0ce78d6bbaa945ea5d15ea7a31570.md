# RMP-PERF-01 evidence bundle — `d6ecd2d`

- `wbs_id`: `RMP-PERF-01`
- `tested_sha`: `d6ecd2d1bbf0ce78d6bbaa945ea5d15ea7a31570`
- `tested_tree`: `4b4f0f94a535733ffb5dc6c7cfc84c1f028bb971`
- `executed_at`: `2026-08-28 KST`
- `executed_by`: implementation lane (윤서준). 실행 기록이며 판정이 아니다.
- 재실행 사유: `ai/ai_graph/quant_performance.py`가 `29eaef2` 이후 +153줄 변경됐다.
  이 행이 다루는 바로 그 모듈이므로 이전 번들의 PASS는 현재 HEAD의 진술이 아니다.

## Acceptance wording under test

> 필수 metadata 누락 또는 신뢰도 부족이면 모든 성과 숫자/chart가 unavailable이고 proxy는 공식 benchmark로 표시되지 않는다.

## 고정 명령 — 두 부분 모두 실행

WBS 행의 `실행·검증`은 pytest와 npm typecheck를 `&&`로 묶은 한 명령이다. 두 부분을
모두 실행했다.

### (1) pytest

```sh
env -u AI_DATABASE_DSN -u QUANT_DB_DSN -u DATABASE_URL -u AI_AOAI_API_KEY \
    -u AI_AOAI_ENDPOINT -u AI_AOAI_DEPLOYMENT -u AI_LLM_API_KEY -u OPENAI_API_KEY \
    ai/.venv/bin/python -m pytest -q \
    ai/tests/test_quant_performance.py ai/tests/test_jobs.py ai/tests/test_report.py \
    ai/tests/contracts/test_api_envelope_contract.py ai/tests/test_api.py \
    backtest_module/tests/test_backtest.py backtest_module/tests/test_models.py \
    backtest_module/tests/test_strategy.py
```

`exit_code=0` — `116 passed, 1 warning in 3.50s`.

### (2) frontend typecheck

```sh
cd backend/fe-api-preview && npm run typecheck
```

`exit_code=0` — `tsc -b --pretty false`, 진단 출력 없음.

**주의**: 이 디렉터리에는 `node_modules`가 없었고 `tsc: command not found`로 실패했다.
`npm install --no-audit --no-fund`(24 packages)를 먼저 실행한 뒤에야 통과했다. 즉 이
고정 명령은 **깨끗한 체크아웃에서 그대로는 실행되지 않는다.** 재현하려면 install이
선행돼야 한다는 사실을 여기 남긴다.

## 전체 스위트 참고

같은 SHA에서 `cd ai && pytest -q` 전체도 실행했다 — `exit_code=0`,
`791 passed, 9 skipped, 1 warning in 28.73s`.

## 실제로 import된 소스

```
rootdir: .../worktrees/github-actions-error-609d90/ai
ai_graph        -> .../worktrees/github-actions-error-609d90/ai/ai_graph/__init__.py
backtest_module -> .../worktrees/github-actions-error-609d90/backtest_module/backtest_module/__init__.py
```

## 수용 축 대응

이전 번들(`29eaef2…`)의 축 대응표 3행을 이 SHA로 이월한다. 같은 테스트가 여기서도
통과했다.

| Axis | Evidence |
|---|---|
| 신뢰도 부족 → 숫자·chart 전부 unavailable | `test_public_projection_removes_every_metric_and_chart_for_insufficient_data` |
| metadata 누락 → complete value 미노출 | `test_public_projection_requires_engine_manifest_before_exposing_complete_values` |
| unavailable state가 클라이언트 타입과 일치 | `backend/fe-api-preview` typecheck 통과 |

## 미커버

- fixture와 in-memory job store에서만 실행했다. 운영 DB·live provider·배포 환경 없음.
- 공개 계약 구현 게이트이며, 실수익·시장 데이터 결과·릴리스 판정이 아니다.
- `proxy는 공식 benchmark로 표시되지 않는다`는 문구의 **proxy 표시 축은 위 3행에
  직접 대응된 테스트가 없다.** 승인 전에 이 축의 대응 테스트를 지목하거나 추가해야 한다.

## 환경

- 인터프리터: `ai/.venv/bin/python`, Python `3.11.15`, pandas `3.0.3`, pytest `9.1.1`
- Node `v22.22.2`, npm `10.9.7`
- 체크아웃: linked worktree `.claude/worktrees/github-actions-error-609d90`

## Review record

- Reviewer: **윤서준 (저자 본인)** — 2026-08-28 소유자 결정.
- Reviewer kind: **`author_review` — 독립 검토가 아니다.**
- WBS 지정 승인자는 조은채이며 capacity matrix의 자기승인 금지 규정은 그대로다.
  저자 검토는 그 규정을 대체하지 않는다.
- Verdict: **미기재.**
