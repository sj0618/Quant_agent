# QuantQA:v1 WBS QA Contract

- Status: **DRAFT FOR REVIEW**
- WBS: `QA-WBS-01`
- Approval: **PENDING**
- Canonical WBS source: [팀 Google Spreadsheet](https://docs.google.com/spreadsheets/d/1V7SnG_x-cLIFbrSurDIadtx5GCY9HfL9jRqdyAl70Ks/edit?gid=2030261433#gid=2030261433), `2_WBS`, ID `QA-WBS-01`
- Intended commit: `[QA] generalize QuantQA WBS contract`

이 문서는 승인 전 구현 초안이다. Google Spreadsheet의 상태를 변경하거나 승인 결정을 대신하지 않는다.

## 1. Google Sheet에서 직접 확인된 요구사항

다음 항목만 현재 WBS 원문에서 직접 확인된 계약이다.

- 모든 WBS 변경을 `QuantQA:v1`의 S/R/O/C evidence class, required tier, reviewer, artifact URI에 연결한다.
- sample 3건은 class/tier, scenario, PASS 기준, evidence URI, reviewer를 가진다.
- S evidence만으로 R/O/C 완료를 인정하는 경우는 0건이어야 한다.
- mock, memory, noop은 S로만 표기한다.
- 검증 방식은 WBS row sampling과 isolated QA report template이다.
- evidence bundle에는 contract version, sample manifest URI, reviewer 기록이 필요하다.
- application source를 수정하지 않는다.
- configuration/environment 실제 값을 직접 참조하지 않는다.
- production, node3, PVE 부하 검증을 수행하지 않는다.

WBS 원문은 S/R/O/C의 의미, tier 이름, canonical manifest 형식, reviewer와 approver의 관계, artifact hash 알고리즘을 직접 정의하지 않는다.

## 2. QuantQA:v1 implementation definition

아래 항목은 Google Sheet의 축약된 요구를 구현 가능하게 만든 **승인 전 설계 결정**이다. Google Sheet 원문에 직접 정의된 내용으로 인용하면 안 된다.

### 2.1 Evidence classes

| Class | Implementation definition | 허용 범위 | 이 class만으로 증명하지 못하는 것 |
|---|---|---|---|
| S | Static / Structural | source·문서·schema 검토, lint/typecheck/build, bundle 검사, unit test, mock/memory/noop 기반 검사 | 실제 runtime, 운영 lifecycle, cross-process 동작 |
| R | Runtime | 평가 SHA의 실제 프로세스·API·browser를 실행해 관찰한 non-mock runtime 증적 | restart·migration·rollback·내구성 및 cross-process 경쟁 |
| O | Operational | isolated staging 또는 승인된 CI에서 readiness, restart, durable state, migration, rollback, 관측성을 검증한 증적 | 다중 프로세스 경쟁과 장애 격리 |
| C | Cross-process Concurrency & Containment | API/worker 다중 프로세스, SSE/cancel, retry/fencing, lease·migration race, fault injection, resource blast-radius 격리 증적 | 해당 없음. 단, C도 S/R/O를 자동 대체하지 않는다. |

`C`의 명칭은 QA-NODE3-SFX-01의 cross-process SSE/cancel, retry/fencing, migration race, cgroup blast radius를 함께 표현하기 위한 implementation definition이다.

### 2.2 Cumulative tiers

| Tier | Required classes | 표시 |
|---|---|---|
| T1 | S | `required=S` |
| T2 | S, R | `required=S+R` |
| T3 | S, R, O | `required=S+R+O` |
| T4 | S, R, O, C | `required=S+R+O+C` |

v1은 누적 tier만 사용한다. custom/non-cumulative tier는 후속 정책이다.

### 2.3 Canonical manifest

- Canonical machine-readable format은 JSON이다.
- Schema는 [`schemas/quantqa-v1-manifest.schema.json`](schemas/quantqa-v1-manifest.schema.json)이다.
- 사람 검토 문서는 [`templates/quantqa-isolated-report.md`](templates/quantqa-isolated-report.md)를 사용한다.
- JSON manifest와 사람 검토 보고서의 WBS ID, full Git SHA, required classes, verdict는 일치해야 한다.

### 2.4 Roles

| Role | 책임 |
|---|---|
| owner | WBS 작업과 계약 충족에 대한 책임 |
| executor | 검증을 수행하고 artifact를 생성 |
| reviewer | artifact, scenario, PASS 기준, 반증, SHA를 독립 재검사 |
| approver | 최종 수용과 WBS 상태 전환 결정 |

v1 역할 규칙은 다음과 같다.

- reviewer는 owner 또는 executor와 같을 수 없다.
- approver는 owner 또는 executor와 같을 수 없다.
- reviewer와 approver는 v1에서 같은 사람일 수 있다.
- backup이 실제 executor로 참여하면 같은 증적의 reviewer 또는 approver가 될 수 없다.
- JSON Schema는 사람 식별자 간 부등식을 표현하지 못하므로 v1에서는 보고서 검토로 확인한다.

이 역할 규칙은 승인 전 implementation definition이다.

## 3. Evidence classification and tier decision

WBS row는 `required_tier`와 `required_classes`를 모두 선언한다. Evidence item은 자신이 실제로 관찰한 class 하나를 선언한다.

PASS 후보가 되려면 다음을 모두 만족해야 한다.

1. 모든 required class에 최소 하나의 유효한 PASS evidence가 있다.
2. 모든 evidence의 `artifact_subject_sha`가 manifest의 `full_git_sha`와 같다.
3. evidence URI가 실제 artifact로 해소되고 SHA-256이 일치한다.
4. reviewer가 artifact와 반증을 검토했다.
5. unresolved blocker가 없다.
6. mock/memory/noop 증적이 S 외 class에 사용되지 않았다.

Evidence 개수는 class 승격 조건이 아니다. S evidence 여러 건은 R/O/C 한 건을 대신하지 못한다.

## 4. Mock, memory, and noop

- 핵심 검증 경계에 mock, in-memory/memory, noop 중 하나라도 사용되면 해당 evidence의 effective class는 S다.
- 프로세스를 실제로 실행했더라도 위 대체 경계를 사용했다면 R/O/C로 분류하지 않는다.
- R/O/C 충족 계산에서 제외한다.
- `uses_mock`, `uses_memory`, `uses_noop`을 manifest에 기록한다.
- 실제 provider, DB, durable store, operational environment를 검증하지 않았다는 limitation을 기록한다.
- 사용 여부를 확인할 수 없으면 non-mock으로 추정하지 않고 `UNVERIFIED`로 둔다.

## 5. Same-revision provenance

- `full_git_sha`는 40자리 Git commit SHA를 사용한다. short SHA만 있으면 PASS할 수 없다.
- 모든 artifact는 `artifact_subject_sha`로 검증 대상 revision을 기록한다.
- 서로 다른 SHA의 S/R/O/C evidence를 조합할 수 없다.
- source 변경 뒤 이전 runtime artifact를 현재 PASS에 재사용할 수 없다.
- configuration/environment 실제 값과 secret은 manifest나 artifact에 기록하지 않는다.
- 실행 범위는 `NOT_EXECUTED`, `LOCAL`, `CI`, `ISOLATED_STAGING`, `DEPLOYED_READ_ONLY` 같은 비밀값 없는 범주로만 기록한다.

Google Sheet는 Git revision이 아니므로 WBS 계약 출처는 spreadsheet ID, gid, sheet, WBS ID, 관찰 시각으로 별도 기록한다. Normalized row hash는 v1 필수가 아닌 후속 확장이다.

## 6. Evidence URI and artifact hash

- 실제 artifact가 없으면 `evidence_uri`와 `artifact_sha256`은 `null`이다.
- `실행 후 URI`, `TBD`, 임의의 `evidence://...` 값은 실제 URI가 아니다.
- URI만 있고 artifact가 없거나 reviewer가 열 수 없으면 PASS할 수 없다.
- artifact가 있더라도 SHA-256이 없거나 불일치하면 PASS할 수 없다.
- mutable latest URL은 immutable run ID 또는 content hash 없이 PASS 근거로 사용하지 않는다.
- local temporary path는 장기 evidence URI로 사용하지 않는다.
- URI scheme과 retention 기간의 표준화는 v1 후속 정책이다.

Artifact SHA-256은 Google Sheet 원문의 직접 필수 조건이 아니라 same-revision provenance를 강화하는 QuantQA:v1 implementation definition이다.

## 7. Status model

| Status | 의미 |
|---|---|
| PASS | 모든 required class와 provenance·reviewer 조건 충족 |
| FAIL | 실행된 시나리오가 PASS 기준을 명확히 위반 |
| BLOCKED | 필요한 권한·격리 환경·선행 결정 또는 artifact 접근이 없어 진행 불가 |
| UNVERIFIED | 검증·artifact·reviewer 중 하나 이상이 아직 없음 |

테스트 exit 0만으로 PASS가 되지 않는다. `증적대기`, placeholder URI, short SHA 또는 reviewer 부재는 `UNVERIFIED`다.

## 8. v1 scope boundary

### v1에 포함

- S/R/O/C implementation definition
- 누적 T1~T4
- JSON canonical manifest와 Markdown isolated report
- sample manifest 3건
- same-revision, artifact SHA-256, 역할 분리
- mock/memory/noop S-only 규칙

### 후속 개선

- Google Sheet normalized row hash
- URI scheme 표준화
- artifact retention/expiry
- 자동 validator
- T3/T4 복수 reviewer
- 서명, attestation, SBOM, evidence supersede 이력

## 9. Approval gate

이 초안은 다음 결정 전까지 승인된 계약이 아니다.

- C 명칭과 범위
- 누적 tier 정책
- reviewer/approver 동일인 허용
- JSON canonical manifest와 artifact SHA-256
- sample 3건의 대표성

승인자는 원문 요구와 implementation definition을 분리해 검토해야 한다.
