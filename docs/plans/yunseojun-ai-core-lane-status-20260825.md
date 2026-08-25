# 윤서준 · AI core·백테스트 lane 상태 (2026-08-25 Quant_agent 기준선)

- 기준 SHA: `72da24067c54067989f58d0947271281c41d46c1` (tree `2359492`)
- 기준선 조상: `470d33e` (= `origin/main`, `sj0618/Quant_agent`)
- 실행 환경: [`docs/evidence/_RUNNER-20260825.md`](../evidence/_RUNNER-20260825.md)
- lane 범위: `LOCK-AI-CORE-01 · ai/ai_graph/**(llm 제외), backtest_module/**`
  및 `LOCK-QA-EVIDENCE-01 · WBS planning evidence`
- 담당 행: **34건 / 176h** (P0 31건 124h, P1 1건 24h, P2 2건 28h)
- 34건 전부의 WBS 지정 승인자는 **조은채**다. 이 lane은 자기 행을 승인할 수 없다.

## 이 기준선이 고장나 있었다

`origin`이 `sj0618/Quant_agent`로 옮겨지면서 `main`이 orphan 스냅샷(`470d33e`)이 됐다.
tree는 이전과 같은 `4b4f0f9`라 코드는 그대로지만, **계획 게이트 두 개가 새 root에서
통과하지 못하는 상태**였다. 아무 수정도 하지 않은 `origin/main` 체크아웃에서 실측:

| 명령 | pristine `470d33e` | 이 브랜치 |
|---|---|---|
| `node --test scripts/check-production-plan.test.mjs` | `pass 1 · fail 4` | `pass 5 · fail 0` |
| `node --test scripts/evaluate-release-trust.test.mjs` | `pass 4 · fail 2` | `pass 6 · fail 0` |
| `node scripts/check-production-plan.mjs` | `exit 1` (보드 SHA 도달 불가) | `exit 0 · PASS` |

## 고친 결함 4건

1. **release gate가 아무것도 검사하지 않았다** (`c8fb626`, `scripts/check-production-plan.mjs`).
   진입 가드가 `new URL(process.argv[1], "file:")`를 썼는데 Windows 드라이브 경로에서는
   `C:`가 URL scheme으로 해석되어 항상 불일치했다. CLI 블록이 통째로 실행되지 않아
   **출력 없이 exit 0**, malformed board도 exit 0이었다. 검사 없이 성공을 보고하는
   release gate는 없는 것보다 나쁘다.
2. **결정성 계약 테스트가 실행 자체가 불가했다** (`5efbbdb`,
   `ai/tests/test_backtest_optimization.py`). `Path.read_text()`를 인코딩 없이 호출해
   cp949 로케일에서 한글 소스에 `UnicodeDecodeError`. 테스트가 약해진 게 아니라
   `deterministic_no_rng` 주장이 그 환경에서 **검증되지 않은 채** 있었다.
3. **release-trust 계약 테스트가 POSIX 체크아웃을 가정했다** (`5fe0763`).
   `cwd`를 `"/repo/fe"` 리터럴과 비교했으나 프로덕션 코드는 `join()`을 쓴다. 워크플로
   단언은 LF 전용 정규식이라 CRLF 체크아웃에서 실패했다. 둘 다 프로덕션 결함이 아니라,
   게이트의 자기 계약 테스트가 Linux CI 밖에서 돌지 못하던 문제다.
4. **preflight fixture가 이전 히스토리의 SHA에 고정돼 있었다** (`72da240`).
   `assertReachableCommit`은 증적 SHA가 `HEAD`의 조상이기를 요구하는데, orphan root로
   옮긴 뒤 `c3a5bc46`은 도달 불가가 됐다. `git rev-parse HEAD`로 실행 시점 해석으로 바꿨다.

1·2는 lane 소유(`LOCK-AI-CORE-01`, `LOCK-QA-EVIDENCE-01`)다. 3은 `EV-GATE-01`(고준영 소유,
윤서준 backup) 영역이며 요청자 승인 아래 이번 이관 수리에 포함했다. 4는 이관이 만든 결함이다.

## 닫은 행: 2건

| 행 | 전이 | 근거 |
|---|---|---|
| `PM-GOAL-00` | `in_progress` → `evidence_pending` | [번들](../evidence/PM-GOAL-00/72da24067c54067989f58d0947271281c41d46c1.md) |
| `PM-GOAL-01` | `in_progress` → `evidence_pending` | [번들](../evidence/PM-GOAL-01/72da24067c54067989f58d0947271281c41d46c1.md), [명령 계약](quantagent-preflight-command-contract-20260825.md) |

`완료`가 아니다. `localOnly: true`인 동안 preflight가 `complete` 전이를 거부하고,
두 행 모두 독립 검토 판정이 없다.

## control board 이관

`f026728` 보드는 이전 히스토리를 가리켜 새 root에서 자동 FAIL이 된다. 사용 규칙 2가
덮어쓰기를 금지하므로 **내용을 그대로 둔 채 파일명만**
[`…-20260824.md`](quantagent-production-control-board-20260824.md)로 옮기고,
정본 경로에는 이 기준선의 새 snapshot을 뒀다. 고정 명령이 `--board` 없이 동작해야 한다는
`PM-GOAL-00`의 계약을 지키기 위한 조치다.

## 남은 32건이 왜 아직 열려 있는가

### (가) 증적이 이전 SHA에만 있는 10건

`FT-RLS-01`, `FT-DB-02`, `FT-SCH-04`, `OD-API-01`, `OD-DIG-01`, `FT-EMPTY-05`,
`FT-L4-06`, `FT-JOB-07`, `MT-NF-02`, `QV-BIAS-01`.

번들이 `29eaef2`(tree `6fc637d`)에만 있다. 이 기준선의 tree는 `2359492`다. **전체 스위트가
green이라는 사실은 각 행의 대상 테스트가 이 tree에서도 통과함을 뜻하지만, 번들을 대체하지
않는다.** 8/24 번들은 테스트 결과 외에 acceptance-axis 매핑과 배포 서버 read-only probe를
포함했고 이 러너는 서버에 접근하지 않았다. 재발행은 probe가 가능한 러너에서 해야 손실이 없다.

### (나) 코드가 끝났고 CI·배포·QA 축만 남은 9건

`P0-SUP-OD-API-01`, `P0-SUP-L4-PROVENANCE-01`, `P0-SUP-FIXTURE-GATE-01`,
`P0-SUP-METRIC-UNAVAILABLE-01`, `P0-SUP-REPORT-REPLAY-01`, `P0-SUP-METRIC-CONTRACT-01`,
`P0-SUP-PIT-UNIVERSE-AI-01`, `P0-SUP-RELEASE-DATASOURCE-01`, `P0-SUP-LOOKAHEAD-SAMPLE-01`.

WBS 상태가 이미 `검증 완료·<축> 대기`다. 남은 축(CI 실행, 배포 증적, release data/profile QA,
look-ahead QA)이 **전부 이 러너 밖에 있다**. 로컬에서 더 밀어도 상태가 바뀌지 않는다.

### (다) 구현이 남은 12건

`RS-LED-01`, `QV-WRM-01`, `OD-JOB-01`, `FT-FIX-08`, `MT-STALE-01`, `MT-DATA-03`,
`QV-OOS-01`, `QV-EXE-01`, `MR-ENG-01`, `P1-JOB-01`, `P2-PERF-01`, `P2-AI-VERIFY-01`.

각 ID는 이미 소스·테스트에 참조가 있으나(`P1-JOB-01`·`P2-PERF-01`·`P2-AI-VERIFY-01`은 0건),
이 기준선에서 acceptance 문구 대조를 수행하지 않았다. 동시 쓰기 WIP는 1이므로 한 행씩 연다.

### (라) 자기 승인이 불가능한 1건

`P0-REL-REVIEW-02` — 이 lane이 만든 산출물을 이 lane이 검토하는 구성이다. 실행자와 검토자를
분리하지 않으면 열 수 없다. backup은 육은서다.

## 사람이 결정해야 하는 것

1. **조은채의 검토** — 34건 전부의 승인자. `PM-GOAL-00`·`PM-GOAL-01`이 지금 대기 중이다.
2. **CI·서버 러너** — (나) 9건과 (가) 10건 재발행에 필요하다. 배포 키는 GitHub Actions
   시크릿이며 로컬에는 없다.
3. **`P0-REL-REVIEW-02`의 검토자 지정** — 실행자와 분리되어야 한다.
4. **`.gitattributes` 도입 여부** — 이 리포지터리에는 없다. `core.autocrlf=true`인 클론은
   모든 텍스트가 CRLF가 되며, 결함 3이 그 결과였다. 테스트 쪽에서 흡수했으나 근본 처방은 아니다.

## 이 문서가 주장하지 않는 것

로컬 계약 검증 결과다. 운영 DB·운영 API·실거래 데이터·인증 세션에 접근하지 않았고,
어떤 행도 `완료`로 전이시키지 않았다.
