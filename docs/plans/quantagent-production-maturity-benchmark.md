# QuantAgent 프로덕션 성숙도 재평가

## 평가 범위

이 문서는 2026-08-18 KST에 다시 확인한 기준선이다. 대상은 현재 작업 트리와 `077555d6d545c3131e3c1af47264944161ecd66c` HEAD다. 작업 트리에 아직 커밋되지 않은 변경이 있으므로, 이 문서는 배포 승인이나 불변 증적을 대신하지 않는다.

점수는 구현, 자동 검사, 사용자 노출, 독립 재검증이 얼마나 연결되어 있는지 나타낸다.

| 점수 | 판정 |
|---:|---|
| 0 | 구현이나 증적이 없거나 공개 경로가 반대 동작을 한다. |
| 1 | 일부 구현 또는 문서가 있으나 release gate와 독립 재검증이 없다. |
| 2 | 명시적 계약과 자동 검사는 있으나 핵심 실패 경로, 배포, 브라우저 검증 중 하나 이상이 빠졌다. |
| 3 | 계약, 자동 검사, 사용자 노출, 증적이 같은 revision에서 연결되고 독립 재검증이 가능하다. |
| 4 | 3점 조건에 재현 가능한 release artifact와 운영 재검증 추세가 더해졌다. |

`미평가`는 0점이 아니다. 필요한 입력이나 실행 증적이 없어서 점수를 줄 수 없다는 뜻이며, release에서는 blocker로 남는다.

## 비교 대상

| 비교 대상 | 2026-08-18 확인 기준 | 채택한 기준 | 적용 한계 |
|---|---|---|---|
| Freqtrade | [stable 문서](https://www.freqtrade.io/en/stable/)와 [look-ahead analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/) | backtest와 look-ahead 검사를 분리하고 결과 범위를 남긴다. | 암호자산 거래 도구이므로 KRX 데이터와 인증 UX의 근거가 되지 않는다. |
| Qlib | [Qlib 0.9.8.dev11 문서](https://qlib.readthedocs.io/en/latest/)의 workflow, data layer, recorder 구조 | 데이터, 설정, 실행 기록을 함께 보관하고 재현 가능성을 확인한다. | Qlib의 기능 존재가 QuantAgent의 구현 품질을 보증하지 않는다. |
| QuantConnect LEAN | [LEAN backtest 문서](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-backtest)와 [reconciliation 문서](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) | versioned runtime과 backtest output을 묶고, live 차이와 상태 복구를 검증한다. | 실행 환경과 운용 모델이 QuantAgent와 다르다. |

## 2026-08-18 점수

| 축 | 점수 | 이번 확인의 근거 | 확인 명령 | 남은 P0 조건 |
|---|---:|---|---|---|
| 실데이터와 fixture 분리 | 1 | 테스트는 명시적 mock 환경에서 격리되지만 release profile의 DB·provider 의존성 gate는 아직 닫히지 않았다. | `cd ai && AI_LLM_PROVIDER=mock AI_AUDIT_SINK=noop pytest -q` | FT-RLS-01, FT-DB-02, FT-FIX-08 |
| provider 실패 투명성 | 2 | 라이브 AOAI 보조 호출 7종이 provider 오류를 fallback으로 바꾸지 않고 전파하는 회귀 검사를 추가했다. | `cd ai && pytest -q tests/test_live_provider_fail_closed.py` | FT-RLS-01과 internal evaluator, 독립 검토 |
| 지표 정의와 계보 | 1 | archived report의 source 검사는 있으나 registry, formula version, as-of 계약이 release gate로 묶이지 않았다. | `cd fe && npm test` | MR-REG-01, MR-PF-01, MR-API-01 |
| 백테스트 타당성 | 미평가 | fixture graph와 job 테스트는 통과했지만 point-in-time, OOS, 비용, look-ahead 결과물을 현재 revision에서 확보하지 못했다. | `cd ai && pytest -q tests/test_graph_e2e.py tests/test_jobs.py` | QV-PTI-01, QV-OOS-01, QV-EXE-01, QV-BIAS-01 |
| 인증과 복구 UX | 1 | source 수준에서 heading, returnTo, home action을 확인했으나 인증된 desktop·mobile 브라우저 증적은 없다. | `cd fe && npm test` | UX-AUTH-02~05, P0-SUP-AUTH-RECOVERY-UX-01 |
| 배포 재현성 | 1 | frontend production build와 backend 404 contract는 통과했지만 배포 환경 smoke와 rollback 증적은 없다. | `cd fe && npm test`; `cd backend && PYTHONPATH=.:.. ../ai/.venv/bin/python -m pytest -q tests/unit/test_backend_hosted_pages.py tests/unit/test_combined_main.py` | UX-BUILD-01, QA-REL, P0-REL-01 |
| 관측성과 증적 | 1 | graph와 job 단위 검사는 통과했지만 durable store, restart proof, control board의 불변 증적이 없다. | `cd ai && pytest -q tests/test_graph_e2e.py tests/test_jobs.py` | FT-JOB-07, EV-GATE-01, EV-QA-01 |

산술 점수는 `6 / 24 + 미평가 1축`이다. 점수는 출시 가능 판정이 아니다. QA gate 7개가 모두 PASS가 아니고, P0 정책 승인과 배포·인증 증적도 없으므로 현재 배포 가능 판정은 `No`다.

## 실행 결과 기록

- `cd fe && npm test`: 33 passed, typecheck 통과, production build 통과
- `cd backend && PYTHONPATH=.:.. ../ai/.venv/bin/python -m pytest -q tests/unit/test_backend_hosted_pages.py tests/unit/test_combined_main.py`: 21 passed
- `cd ai && AI_LLM_PROVIDER=mock AI_AUDIT_SINK=noop pytest -q`: 479 passed, 6 skipped
- `cd ai && AI_LLM_PROVIDER=mock AI_AUDIT_SINK=noop pytest -q tests/test_graph_e2e.py tests/test_jobs.py`: 35 passed

이 기록은 로컬 검증 결과다. 실데이터 결과, 배포 검증, 정책 승인으로 해석하지 않는다.
