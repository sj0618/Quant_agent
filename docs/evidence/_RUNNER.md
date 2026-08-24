# 로컬 증적 실행 환경 (2026-08-24)

`docs/evidence/<WBS-ID>/<tested_sha>.md` 번들이 공통으로 참조하는 실행 환경이다.

## 실행자·러너

- `tested_sha`: `29eaef2295d2e2c04c63bbfdd705cbf2d90ce61a` (= `origin/main`)
- `tested_tree`: `6fc637dab917ab70f924b80c2e19121c39f2638b`
- 실행 시각: 2026-08-24 KST
- 인터프리터: `ai/.venv/bin/python`, Python `3.11.15`
- 실행 위치: git worktree
  `.claude/worktrees/yunseojune-task-distribution-b66ffc`

## 어떤 소스가 실제로 import 됐는가

venv 자체는 primary checkout(`~/Desktop/한이음/Qaunt_agent`)에 있고 그 editable
설치도 primary checkout을 가리킨다. 그래서 `python -c "import ai_graph"`처럼
pytest를 거치지 않고 부르면 **worktree가 아니라 primary checkout 소스**가 로드된다.

그러나 `ai/pyproject.toml`은 `[tool.pytest.ini_options] pythonpath = [".", "../backtest_module"]`
를 두고 있고 이 경로는 rootdir 기준으로 해석된다. `cd ai && pytest`로 실행하면
rootdir이 worktree의 `ai/`가 되므로 editable 설치보다 worktree 경로가 앞선다.
실측으로 확인했다:

```
rootdir: .../worktrees/yunseojune-task-distribution-b66ffc/ai
configfile: pyproject.toml
probe ai_graph=.../worktrees/yunseojune-task-distribution-b66ffc/ai/ai_graph/__init__.py
probe backtest_module=.../worktrees/yunseojune-task-distribution-b66ffc/ai/../backtest_module/backtest_module/__init__.py
```

따라서 아래 번들의 pytest 결과는 **worktree(= `origin/main` 29eaef2) 소스**를
검증한 것이다. `node` 명령은 worktree 안의 `scripts/`를 직접 실행한다.

## 환경 변수

`ai/tests` 실행에는 다음을 적용했다.

```sh
env -u AI_DATABASE_DSN -u QUANT_DB_DSN -u DATABASE_URL \
    -u AI_AOAI_API_KEY -u AI_AOAI_ENDPOINT -u AI_AOAI_DEPLOYMENT \
    -u AI_LLM_API_KEY -u OPENAI_API_KEY -u AOAI_API_KEY \
    AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop
```

## 증적 등급의 한계

여기 담긴 결과는 mock provider·in-memory job store·fixture 입력에서 나온
**로컬 계약 검증**이다. 운영 DB, 운영 API, 실거래 데이터, 인증 세션에는
접근하지 않았다. 따라서 이 번들만으로 WBS `완료`를 주장하지 않으며,
각 번들의 "미커버" 절에 적힌 축은 서버 증적으로만 닫힌다.

## 승인

모든 번들의 reviewer는 **미지정(pending)** 이다. 산출물을 만든 주체가 같은
산출물을 승인하지 않는다. 승인은 WBS가 지정한 독립 reviewer가 한다.
