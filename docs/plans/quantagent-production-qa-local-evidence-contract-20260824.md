# 2026-08-24 QA·계획 로컬 증적 계약

## 판정 범위

이 문서는 `c3a5bc46822e0fa7f34d39060302d279293613f1`을 기준 SHA로 삼아 만든
**로컬 검증 계약**이다. 실행 당시 공유 작업공간에는 미커밋 변경이 있었으므로,
아래 PASS는 그 SHA만으로 재현되는 immutable completion evidence가 아니다.
운영 DB, 운영 API, 실제 거래 데이터, 배포 환경, 인증 세션에는 접근하지 않았다.

따라서 이 문서는 WBS `완료`의 근거가 아니며, 다음 실행의 입력·기대 결과·한계를
고정하는 데만 쓴다.

## 실행 결과와 상태 제안

| WBS ID | 고정 명령 | 관찰 결과 | 상태 제안 | 완료 전 필수 증거 |
|---|---|---|---|---|
| PM-GOAL-00 | `node scripts/check-production-plan.mjs` | control-board JSON 구조가 PASS여야 한다. | 진행 | 같은 SHA에 board·preflight output·독립 검토를 묶은 immutable bundle |
| PM-GOAL-01 | `node --test scripts/check-production-plan.test.mjs` | 유효 board PASS 및 malformed board/recurrence 미기재 FAIL을 함께 검사한다. | 진행 | PASS/FAIL 로그와 독립 reviewer record |
| PM-BOARD-01 | `node scripts/check-production-plan.mjs` | 상태 전이·evidence URI·recurrence count·reviewer·limitation을 기계 검증한다. | 진행 | WBS 상태와 맞는 same-SHA board revision 및 reviewer record |
| QA-DATA-AUDIT-01~04 | `cd DE && ../ai/.venv/bin/python -m pytest -q tests -k '…'` | collection 단계에서 `pandas_ta_classic`와 `pandas_ta` 모두 `MODULE_NOT_FOUND`로 종료한다. | 대기 | 실행 가능한 isolation된 audit command, PostgreSQL `source/as_of/freshness/lineage` bundle, 독립 검토 |
| QA-DATA-AUDIT-05 | `node DE/scripts/replay-strategy-validation-report.mjs --input-manifest release --runs 2 --assert-identical-output-hash` | 두 output hash가 같더라도 input source는 `fixture`, `release_eligible:false`다. | 증적대기 후보만 가능 | source=`postgres`, immutable extract hash, server-side replay, reviewer approval |
| MR-REG-01 | `./ai/.venv/bin/python -m pytest -q ai/tests/test_source_manifest.py ai/tests/contracts/test_metric_api_serialization_contract.py ai/tests/test_quant_performance.py` | 17 PASS는 source-manifest/serialized detail의 형태를 검증한다. | 대기 | label·formula·formula version·implementation hash·input window·as-of·null policy가 있는 registry 및 row-level contract |
| MR-PF-01 | 위 metric command + engine/prose 대조 | prose와 engine의 profit-factor 의미가 다르다. | 차단 | one definition·unit·denominator·clip policy 승인 후 engine/API/registry agreement |
| MR-ALL-01 | MR-REG-01 완료 뒤 registry coverage test | 전체 공개 metric registry와 implementation hash가 없다. | 대기 | 100% coverage manifest와 public API/UI rows의 row-level test |
| OD-E2E-01 | `cd fe && npm test` | offline evaluator의 frontend gate가 PASS여도 브라우저/서버 E2E와 independent approval은 별도다. | 증적대기 후보만 가능 | actual browser run metadata, route inventory 결과, same-SHA independent review |

## 재현한 최소 검증

```sh
# replay contract: 5 tests pass; fixture source is explicitly non-production
node --test DE/scripts/replay-strategy-validation-report.test.mjs
node DE/scripts/replay-strategy-validation-report.mjs \
  --input-manifest release --runs 2 --assert-identical-output-hash

# source-manifest / serialized metric detail contract: 17 tests pass
./ai/.venv/bin/python -m pytest -q \
  ai/tests/test_source_manifest.py \
  ai/tests/contracts/test_metric_api_serialization_contract.py \
  ai/tests/test_quant_performance.py
```

`QA-DATA-AUDIT-05` replay의 fixture output은 deterministic serialization만 보인다.
그 output의 `release_eligible:false`와 limitation 문구는 반드시 보존한다.

## profit-factor 불일치의 수리 전 요구사항

- `ai/ai_graph/quant_explanations.py`는 profit factor를 "총이익 / 총손실"의
  period-return 값이라고 설명한다.
- `ai/ai_graph/nodes/backtest.py`의 `_profit_factor`는 `win_rate / (1 - win_rate)`를
  0~3 범위로 clip한다. 이는 설명한 총이익/총손실 계산과 동일하지 않다.
- 수리 PR은 정의·단위·분모·zero-loss 처리·clip policy를 하나로 고정하고,
  engine summary, API serialization, registry row, 공개 설명을 같은 test fixture에서
  대조해야 한다. 설명만 수정하거나 engine만 수정해선 안 된다.

## 종료 조건

로컬 테스트는 구현 회귀를 좁히는 데만 사용한다. 완료 증거에는 같은 SHA의 command
output, immutable evidence URI, 지정 reviewer의 independent record가 필요하다.
실데이터 또는 release 판정에는 PostgreSQL source, as-of, freshness, lineage hash와
서버 실행 결과를 추가해야 하며, fixture·mock·cache는 대체할 수 없다.
