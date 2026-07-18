# Quant_agent

## 커밋 메세지 양식

```
[TYPE] 간결한 제목
ex. [DOCS] README 커밋 컨벤션 추가
```
GitHub Issues는 CI 실패 자동화에 사용하므로 커밋 메시지에는 이슈 번호를 강제하지 않습니다.

| TYPE         |                               | 
| ------------ | ------------------------------------ | 
| **FEAT**     | 새로운 기능 추가                            | 
| **FIX**      | 버그 수정                                |
| **DOCS**     | 문서 수정(README, 가이드, 주석 등)             |  
| **STYLE**    | 코드 포맷/세미콜론/공백 등, 로직 변경 없음        |
| **REFACTOR** | 리팩터링(동작 동일, 구조 개선/성능 향상)             | 
| **TEST**     | 테스트 코드 추가/수정                         | 
| **CHORE**    | 빌드/배포/의존성/스크립트 등 개발환경(패키지 매니저 포함) 변경 |

---
## CI 실패 자동 이슈 봇

`.github/workflows/ci-issue-bot.yml`은 `Code checks`, 배포, 서버 헬스체크 워크플로가 실패하거나 시간 초과하면 GitHub Issue를 자동 생성한다.

- 실패 작업과 실패 단계, 브랜치, 커밋, 실행 로그 링크를 이슈에 기록한다.
- 같은 워크플로 작업의 미해결 이슈가 있으면 새 이슈 대신 최신 실패를 댓글로 남긴다.
- `automated` 라벨이 없을 경우 자동 생성한다.
- 봇이 동작하려면 저장소의 Actions가 기본 `GITHUB_TOKEN`에 Issues 쓰기 권한을 허용해야 한다.

CI 실패 자체가 아닌 취소(`cancelled`) 실행은 이슈로 만들지 않는다.

---

## 목적(현재 이 README scope)
`README`는 **Rocky Linux 8.10 Native Bash MVP spine** 실행 재현성과 안전 계약을 최상위 단에서 정리한다.
AI/FE 상세 절차는 각각 `ai/README_AI.md`, `fe/README.md`에 두고, 여기는 핵심 순서와 검증 명령만 둔다.

## 정확한 선행 조건
- Rocky Linux 8.10 x86_64
- Bash(권장 4.4+), Python 3.11.13, Node 24.15.0, npm 11.12.1
  (`/etc/rocky-release` 및 `--version`으로 고정값 확인)
- Docker/Compose 미사용
- 외부 DB/Redis/OAuth/LLM credential 사용 금지
- 저장소 바깥 작업공간 사용(안전성 상의 이유)

## MVP Spine
`fe`(직접 Vite) → `/backend-api`·`/ai-api` 프록시 → Backend FE read API·`ai/ai_graph/api.py` → PostgreSQL·`backtest_module` → 공개 `AnalysisJob/APIEnvelope` → FE 표시

## 실행 전제: parent/child topology
- AI와 FE는 같은 쉘에서 섞어 실행하지 않는다.
- 실행은 parent Bash가 수행하고 child가 AI/FE 런타임을 독점으로 띄운다.
- child는 canonical `FE_ROOT`와 `env -i`, bounded curl, 시간축/identity 검증을 통과해야 한다.
- loopback 포트 점검/종료 후 listener 정리는 `ss`와 bounded `curl`만으로 수행한다.

## 로컬 점검용 fixture 환경
- venv는 반드시 저장소 경로 밖 생성
- 로컬 테스트는 `AI_LLM_PROVIDER=mock`, `AI_JOB_STORE=memory`, `AI_AUDIT_SINK=noop`와 데이터 fixture를 사용한다.
- 배포 Workflow는 이 fixture 설정을 사용하지 않으며 `AI_LLM_PROVIDER=aoai`, `AI_REQUIRE_LIVE_DATA=1`, `BACKEND_FE_DATA_SOURCE=database`, `DATABASE_URL`을 요구한다.

## 참고
- AI 상세 실행/테스트 가드: `ai/README_AI.md`
- FE 실행/설정 상세: `fe/README.md`
