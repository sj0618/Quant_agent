# QuantAgent 프로덕션 성숙도 재평가

## 판정과 기준선

- 평가일: 2026-08-24 KST
- source 기준 SHA: `390e0699a724df9135dd5fa952458a25ea0fe93a`
- 마지막 성공 애플리케이션 배포 SHA: `d97b96b3a8309305a354293ae60558e097f58676`
  ([deploy run 32738397042](https://github.com/sj0618/Qaunt_agent/actions/runs/32738397042))
- 판단: **배포 가능 No**. 이 문서는 source/테스트/제한된 운영 관찰을 분리한
  성숙도 원장이지, reviewer 승인이나 실거래/실데이터 백테스트 증적이 아니다.

점수는 다음 계약을 사용한다. `미평가`는 0점이 아니며, release blocker로
남는다.

| 점수 | 판정 |
|---:|---|
| 0 | 구현 또는 검증 계약이 없다. |
| 1 | 구현 또는 문서가 있으나 독립된 같은-SHA 검증/운영 증적이 없다. |
| 2 | 명시적 계약과 S-tier 회귀 검사는 있으나 R/O/C 중 필요한 증적이 빠졌다. |
| 3 | 계약, 같은-SHA 검증, 사용자 경로, 독립 검토가 연결됐다. |
| 4 | 3점 조건에 재현 가능한 운영 artifact와 반복 관찰 추세가 더해졌다. |

## 비교 기준

| 비교 대상 | 2026-08-24 확인 기준 | QuantAgent에 적용한 기준 | 적용 한계 |
|---|---|---|---|
| [Freqtrade stable](https://www.freqtrade.io/en/stable/) | 백테스트·전략 최적화·dry-run/live 경로를 분리한다. | 데이터, 백테스트, 사용자 실행을 서로 다른 증적으로 취급한다. | 암호자산 도구이므로 KRX 데이터·인증 모델의 증거가 아니다. |
| [Freqtrade look-ahead analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/) | 전체 데이터프레임 계산이 미래 참조를 만들 수 있음을 전제로 별도 분석을 둔다. | PIT/OOS/bias 결과물은 일반 graph green과 별도 계약이어야 한다. | 구현 방식이나 강제 옵션을 그대로 이식하지 않는다. |
| [Qlib 0.9.8.dev11 문서](https://qlib.readthedocs.io/en/latest/) | data layer, workflow, recorder를 분리한다. | 데이터 source·실행 기록·결과 계보를 함께 보존한다. | Qlib 기능 존재가 QuantAgent 품질을 보증하지 않는다. |
| [QuantConnect LEAN reconciliation](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) | 재시작 뒤 broker/runtime 상태 차이를 명시적으로 조정한다. | persistent job, restart, reconciliation은 health와 별도 증적을 요구한다. | brokerage/live-trading 범위는 이 프로젝트의 승인 범위를 넘는다. |

## 7축 재평가

| 축 | 점수 | 현재 근거와 재현 명령 | 아직 없는 필수 증적 |
|---|---:|---|---|
| 실데이터와 fixture 분리 | 2 | release fixture fence와 source-manifest 계약은 offline release-trust에 포함된다. `node scripts/evaluate-release-trust.mjs` | 같은 SHA의 PostgreSQL snapshot/as-of/freshness/result count R 증적 |
| provider 실패 투명성 | 2 | AOAI timeout/connection/HTTP subcause와 fail-closed 회귀가 있다. `ai/.venv/bin/python -m pytest -q ai/tests/test_llm_aoai.py ai/tests/test_live_provider_fail_closed.py` | 승인된 isolated real-provider O 증적과 reviewer 판정 |
| metric 정의·계보 | 2 | canonical metric registry와 unavailable projection 계약이 source에 있다. `ai/.venv/bin/python -m pytest -q ai/tests/test_quant_performance.py ai/tests/test_metric_registry.py` | 실제 PostgreSQL 결과의 version/as-of/provenance R 증적 |
| 백테스트 타당성 | 2 | OOS/bias/execution manifest의 S 계약과 Python 3.11 backtest/graph 회귀가 있다. `ai/.venv/bin/python -m pytest -q backtest_module/tests/test_backtest.py ai/tests/test_graph_e2e.py` | PIT server snapshot, OOS output, 비용/체결 assumption R/C 증적 |
| 인증·복구 UX | 1 | `/login`과 protected `/app` route 계약은 있으나 authenticated desktop/mobile browser 증적이 없다. `cd fe && npm test` | 실제 OAuth return, session expiry, mobile O 증적 |
| 배포 재현성·public topology | 1 | `d97b96b` 배포는 성공했고 `/trust` 200·unknown route 404을 관찰했다. 그러나 public `/ai-api/api-status`는 404이고 double-prefix만 AI app으로 도달한다. | Nginx prefix 보존, same-SHA deploy/health, rollback O 증적 |
| 관측성·증적 | 1 | persistent AI store와 readiness 계약은 노출되지만, restart trace·용량 baseline·assigned reviewer evidence bundle이 없다. | durable restart R, cgroup capacity C, 조은채 review bundle |

**총점: 11 / 28.** 숫자는 release 결정을 대체하지 않는다. 모든 축에 승인된
R/O/C 증적이 없고, public AI prefix topology 결함과 WBS reviewer 대기가 남아
있으므로 결과는 `No`다.

## 실제로 관찰한 범위

| 시나리오 | 등급 | 결과 | 경계 |
|---|---|---|---|
| frontend source/build/renderer contract | S | `cd fe && npm test` 58 passed, typecheck/build 통과 | fixture/SSR contract는 실제 browser job lifecycle가 아니다. |
| Python 3.11 backtest + graph | S | credential 제거 상태에서 56 passed | local test process이며 server DB/provider를 사용하지 않았다. |
| release-trust | S | SHA `390e069`의 GitHub offline release-trust job 성공 | mock/memory/noop 환경을 쓰므로 운영 증거가 아니다. |
| node3 deploy + public route | O (제한됨) | `d97b96b` deploy 성공, `/trust` 200, unknown route 404 | source SHA가 현재 `390e069`과 다르고, AI research flow를 검증하지 않는다. |
| public AI prefix | O (실패) | `/ai-api/api-status` 404, `/ai-api/ai-api/api-status`만 persistent status 반환 | Nginx가 `/ai-api/`를 strip하므로 browser research E2E는 차단됐다. |

## 다음 gate

1. Nginx `location /ai-api/`가 upstream에 prefix를 보존하도록 수정·reload하고
   single-prefix `api-status`, strategy parse, research job route를 최소 요청으로
   smoke 한다.
2. 수정 SHA에서 server-health, deploy, public route smoke를 다시 묶는다.
3. 실데이터/PIT와 persistent job restart는 disposable 또는 승인된 isolated 환경에서
   R/C artifact를 만든다. fixture/memory 결과를 이 항목의 운영 완료로 승격하지 않는다.
4. evidence bundle에 조은채의 명시적 review를 붙인 뒤에만 WBS `완료`를 검토한다.
