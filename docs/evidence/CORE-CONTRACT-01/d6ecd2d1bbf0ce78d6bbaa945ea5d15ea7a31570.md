# CORE-CONTRACT-01 evidence bundle — `d6ecd2d`

- `wbs_id`: `CORE-CONTRACT-01`
- `tested_sha`: `d6ecd2d1bbf0ce78d6bbaa945ea5d15ea7a31570`
- `tested_tree`: `4b4f0f94a535733ffb5dc6c7cfc84c1f028bb971`
- `executed_at`: `2026-08-28 KST`
- `executed_by`: implementation lane (윤서준). 실행 기록이며 판정이 아니다.
- 선행 번들 대비: 이전 번들은 `29eaef2`에서 실행됐고, 그 이후 `ai/ai_graph/` 소스가
  바뀌었다(`git diff --stat 29eaef2..main -- ai/ai_graph/` 기준 13개 파일, +931/-81).
  그래서 같은 SHA 규칙에 맞추어 다시 실행했다.

## Acceptance wording under test

> canonicalization/hash·stage/subcause·idempotency·V1/V2 dual-read 계약을 고정하고, raw create·research POST의 전환 규칙과 no-secret public envelope를 명시한다.

## 고정 명령

WBS 행의 `실행·검증` 원문:

```
cd ai && python3.11 -m pytest -q tests/contracts tests/test_api.py
```

`_RUNNER.md`가 요구하는 오프라인 환경으로 실행한 형태:

```sh
cd ai && env -u AI_DATABASE_DSN -u QUANT_DB_DSN -u DATABASE_URL -u AI_AOAI_API_KEY -u AI_AOAI_ENDPOINT \
    -u AI_AOAI_DEPLOYMENT -u AI_LLM_API_KEY -u OPENAI_API_KEY -u AOAI_API_KEY \
    AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop \
    ai/.venv/bin/python -m pytest -q
```

`exit_code=0` — `791 passed, 9 skipped, 1 warning in 28.73s`.

## 이 행의 대상 부분집합

```sh
cd ai && … -m pytest -q tests/contracts tests/test_api.py
```

`exit=0` — `49 passed, 1 warning in 2.73s`.

## PASS가 이 행의 산출물을 증명하지 않는다

고정 명령은 `exit=0`이지만, 그 PASS는 **기존** contract/API 테스트가 통과했다는
뜻일 뿐이다. 이 행의 산출물인 `StrategyExecutionSpecV1`과 `ParseOutcomeV1`은
저장소에 존재하지 않는다. 확인 범위는 이 머신의 worktree 12개와 원격 197개 ref
전부이며 일치 0건이고, WBS가 적은 커밋 `e2050ce`는 `git cat-file -t` 기준
`Not a valid object name`이다.

즉 고정 명령이 산출물 부재와 무관하게 통과한다. 이 번들은 **행을 닫는 근거가 아니라
행의 계약 명령이 느슨하다는 기록**이다.

## 실제로 import된 소스

```
python 3.11.15
ai_graph        -> .../worktrees/github-actions-error-609d90/ai/ai_graph/__init__.py
backtest_module -> .../worktrees/github-actions-error-609d90/backtest_module/backtest_module/__init__.py
```

`ai/pyproject.toml`의 `pythonpath = [".", "../backtest_module"]`가 rootdir 기준으로
해석되므로, primary checkout의 editable 설치보다 이 worktree가 앞선다. 따라서 위 결과는
`d6ecd2d`의 소스를 검증한 것이다.

## 수용 축 대응

**축 대응 미완료.** 이 행에는 이전 번들이 없고, Done 계약의 문구를 개별 테스트에
1:1로 대응시키는 작업을 아직 하지 않았다. 아래 실행 결과는 사실이지만, 그것만으로
수용 축이 덮였다고 주장하지 않는다. 승인 전에 축 대응표를 채워야 한다.

## 미커버

- mock provider, in-memory job store, fixture 입력에서만 실행했다. 운영 DB·운영 API·
  실거래 데이터·인증 세션에 접근하지 않았다.
- 이 번들은 로컬 계약 검증이며 WBS `완료`를 주장하지 않는다.
- 배포 서버에서의 실행·재시작·실데이터 재현은 이 번들에 없다.

## 환경

- 인터프리터: `ai/.venv/bin/python`, Python `3.11.15`, pandas `3.0.3`, pytest `9.1.1`
- 체크아웃: linked worktree `.claude/worktrees/github-actions-error-609d90`

## Review record

- Reviewer: **윤서준 (저자 본인)** — 2026-08-28 소유자 결정으로 검토를 직접 수행한다.
- Reviewer kind: **`author_review` — 독립 검토가 아니다.**
- 이 행의 WBS 지정 승인자는 조은채이고, capacity matrix는 primary가 자기 행의 완료를
  승인하지 않는다고 규정한다. 저자 검토는 그 규정을 대체하지 않으며, 독립 검토가 필요하다는
  사실을 지우지 않는다. 이 기록은 그 차이를 남기기 위한 것이다.
- Verdict: **미기재.** 저자 검토 수행 시 이 줄을 갱신한다.
