# Planning-goal preflight 명령 계약 (2026-08-25 기준선)

`PM-GOAL-01`의 Done 계약은 다음이다.

> `scripts/check-production-plan.*`의 exact command와 exit 0/비0 예시를 문서화

이 문서가 그 고정본이다. 2026-08-24의
[로컬 증적 계약](quantagent-production-qa-local-evidence-contract-20260824.md)을
대체하지 않는다. 그 문서는 명령의 **목록**을 기록했고, 이 문서는 각 명령의
**exit code와 출력**을 기록한다.

- 기준 SHA: `72da24067c54067989f58d0947271281c41d46c1`
- 기준 tree: `235949293d5b58629b2c7777b0c384ade3b01d3d`
- 실행 환경: [`docs/evidence/_RUNNER-20260825.md`](../evidence/_RUNNER-20260825.md)

## WBS 셀과 실제 경로의 불일치

`PM-GOAL-00`·`PM-GOAL-01`의 `실행·검증` 셀은 `node .omx/scripts/verify-production-readiness-plan.mjs`
를 적고 있다. 이 SHA에 최상위 `.omx/` 디렉터리는 없다(`fe/.omx/`는 무관한 frontend state다).
살아 있는 preflight는 `scripts/check-production-plan.mjs`이며 control board의 증적 URI도
이미 그쪽을 가리킨다. **아래 계약은 살아 있는 경로를 기준으로 고정한다.** WBS 셀은 다음
재기준화 때 정정 대상이다.

## 고정 명령 1 — 보드 검사

```sh
node scripts/check-production-plan.mjs [--board <path>]
```

`--board`를 생략하면 `docs/plans/quantagent-production-control-board.md`를 읽는다.

### exit 0 (PASS)

필수 필드가 모두 채워지고 snapshot SHA가 `HEAD`에서 도달 가능한 보드:

```json
{
  "blockerCount": 1,
  "gitSha": "72da24067c54067989f58d0947271281c41d46c1",
  "result": "PASS",
  "transitionCount": 1
}
```

PASS는 **stdout에 JSON을 쓰고** exit 0이다. 출력이 비어 있는 exit 0은 PASS가 아니라
고장이다 — 이 기준선 직전 `origin/main`의 증상이 정확히 그것이었다.

### 비0 (FAIL)

FAIL은 stderr에 `[production-plan] ` 접두사와 위반 필드를 쓰고 exit 1이다.
보드 사본에서 한 필드씩 무너뜨려 관측한 값:

| 입력 | exit | stderr |
|---|---:|---|
| 정상 보드 | 0 | — (stdout에 JSON) |
| `control-board:v1` 마커 없음 | 1 | `control-board:v1 JSON marker is missing` |
| `blockers[].recurrenceCount` 없음 | 1 | `BL-001.recurrenceCount must be a non-negative integer` |
| `transitions[].reviewer` == `owner` | 1 | `TR-001.reviewer must be independent from owner` |
| `transitions[].to` == `complete` (localOnly) | 1 | `TR-001 cannot transition to complete in a local-only snapshot` |
| `snapshot.gitSha` == 40×`0` | 1 | `snapshot.gitSha must be a non-zero 40-character lowercase Git SHA` |
| `snapshot.gitSha`가 도달 불가 커밋 | 1 | `git merge-base --is-ancestor <sha> HEAD failed` |
| 인자 오용 | 1 | `usage: node scripts/check-production-plan.mjs [--board <path>]` |

## 고정 명령 2 — 계약 테스트

```sh
node --test scripts/check-production-plan.test.mjs
```

exit 0, `tests 5 · pass 5 · fail 0`.

이 스위트는 PASS 경로만이 아니라 **FAIL 경로를 spawn으로** 검사한다
(`the command reports a malformed board as non-passing`은 자식 프로세스의 `status === 1`과
stderr 문자열을 함께 단언한다). 그래서 CLI 진입이 통째로 죽은 상태를 잡아낼 수 있는
유일한 테스트이기도 하다.

## 이식성 조건

세 가지가 지켜져야 위 표가 재현된다. 셋 다 이 기준선에서 실제로 깨져 있었다.

1. **CLI 진입 가드는 `pathToFileURL`을 써야 한다.**

   ```js
   if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
   ```

   `new URL(process.argv[1], "file:")`는 POSIX 절대경로에서만 우연히 맞고, Windows
   드라이브 경로에서는 `C:`를 URL scheme으로 해석해 항상 불일치한다. 그 형태로 되돌리면
   Windows에서 두 고정 명령이 **조용히 exit 0**이 되고 위 FAIL 표 전체가 검증력을 잃는다.
   `scripts/evaluate-release-trust.mjs`도 같은 가드를 쓴다.

2. **테스트 fixture의 SHA를 상수로 박지 않는다.** preflight는 모든 증적 SHA가 `HEAD`의
   조상일 것을 요구한다(`assertReachableCommit`). 리포지터리가 새 root 위로 옮겨지면
   과거 SHA는 도달 불가가 되고 스위트가 무너진다. `git rev-parse HEAD`로 실행 시점에
   해석한다.

3. **보드의 `snapshot.gitSha`도 같은 제약을 받는다.** 새 root로 이전한 뒤에는 이전
   히스토리를 가리키는 보드가 자동으로 FAIL이 된다. 이는 결함이 아니라 설계된 동작이며,
   새 snapshot을 여는 신호다.

## 이 계약이 증명하지 않는 것

exit 0은 **문서 구조**의 PASS다. 운영 배포, 실데이터, 사람 승인 중 어느 것도 이 명령으로
확립되지 않으며, 잘 채워진 거짓 보드와 참인 보드를 구분하지 못한다. `localOnly: true`인
동안 이 명령의 PASS로 `완료`를 선언하지 않는다.
