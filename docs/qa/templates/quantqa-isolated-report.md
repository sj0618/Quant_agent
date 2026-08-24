# QuantQA:v1 Isolated QA Report

- Status: **DRAFT FOR REVIEW**
- WBS: `QA-WBS-01`
- Approval: **PENDING**
- Report verdict: `UNVERIFIED`

이 template은 사람 검토용 초안이다. 빈 필드나 placeholder를 PASS 증적으로 해석하지 않는다.

## Contract identity

- Target WBS ID:
- Target WBS task:
- QuantQA version: `QuantQA:v1`
- Contract status: `DRAFT FOR REVIEW`
- Google Sheet reference:
  - Spreadsheet ID:
  - GID:
  - Sheet:
  - Observed at:
- Full Git SHA:
- Required tier:
- Required classes:
- Observed classes:

## Roles

- Owner:
- Executor:
- Reviewer:
- Approver:
- Reviewer differs from owner and executor: `UNVERIFIED`
- Approver differs from owner and executor: `UNVERIFIED`
- Reviewer equals approver: `UNVERIFIED`

## Execution boundary

- Scope: `NOT_EXECUTED | LOCAL | CI | ISOLATED_STAGING | DEPLOYED_READ_ONLY`
- Uses mock: `unknown`
- Uses memory store: `unknown`
- Uses noop: `unknown`
- Configuration/environment actual values recorded: `no`
- Secret values recorded: `no`
- Production/node3/PVE load performed: `no`

## Class coverage

| Class | Required | Scenario | PASS criteria | Actual result | Evidence URI | Status |
|---|---:|---|---|---|---|---|
| S | | | | | | UNVERIFIED |
| R | | | | | | UNVERIFIED |
| O | | | | | | UNVERIFIED |
| C | | | | | | UNVERIFIED |

## Execution

- Exact command or validation method:
- Exit code:
- Executed at:
- Executor:
- Artifact subject Git SHA:

수동 검토는 exit code를 `null`로 둘 수 있지만 재현 가능한 validation method를 기록해야 한다.

## Evidence

| Evidence ID | Class | Mock / memory / noop | URI | Artifact SHA-256 | Subject SHA | Available to reviewer | Reviewer result |
|---|---|---|---|---|---|---|---|
| | | unknown / unknown / unknown | | | | no | UNVERIFIED |

실제 artifact가 없으면 URI와 SHA-256을 비워 두고 `UNVERIFIED`로 기록한다. 가짜 URI를 만들지 않는다.
각 evidence item에서 mock, memory, noop 중 하나라도 `yes`이면 class는 반드시 `S`이고 limitation에 대체 경계를 기록한다.

## Negative evidence and counterexamples

- Failure scenarios tested:
- Unexpected success paths:
- Stale evidence detected:
- Missing required evidence:

## Limitations and blockers

- Limitations:
- Blockers:
- Unverified surfaces:

## Same-revision decision

- All evidence uses the same full Git SHA: `UNVERIFIED`
- Artifact hashes verified: `UNVERIFIED`
- Mock/memory/noop restricted to S: `UNVERIFIED`
- Required class coverage complete: `UNVERIFIED`

## Proposed verdict

`UNVERIFIED`

Rationale:

## Review

- Reviewer:
- Reviewed at:
- Reviewer decision: `PENDING`
- Review reference:

## Approval

- Approver:
- Approval status: `PENDING`
- Approval reference:
