# 공식 KOSPI/KOSDAQ TR 벤치마크 데이터 계약

`ai/ai_graph/nodes/backtest.py`의 primary 벤치마크(`PRIMARY_BENCHMARK_METHOD =
official_kospi_kosdaq_total_return`)가 읽는 warehouse 계약이다.
automatic 모드의 수용 게이트(`_passes_objective_floor`)는 primary 벤치마크가 available일
때만 통과 판정을 낼 수 있으므로, 이 계약이 채워지지 않으면 automatic 요청은 성과와 무관하게
`strategy_validated=False`로 끝난다.

DDL: `DE/migrations/013_krx_official_benchmark_tr.sql`
Reader: `ai/ai_graph/data_sources/db.py` → `PostgresPipelineDataSource._fetch_official_benchmark`

## 1. 읽는 객체

| 객체 | 컬럼 | 의미 |
| --- | --- | --- |
| `mart.krx_index_total_return_daily` | `index_code TEXT` | `KOSPI_TR` / `KOSDAQ_TR`. KRX가 공표하는 총수익(TR) 지수 코드 |
| | `trade_date DATE` | KRX 세션일. `core.trading_calendar`와 정렬되어야 한다 |
| | `tr_value NUMERIC` | TR 지수 **레벨**(수익률 아님). 양수여야 하며 base 값은 자유 |
| `mart.krx_benchmark_monthly_weights` | `month DATE` | 관측 월의 1일 |
| | `kospi_weight NUMERIC` | 그 달 말 기준 KOSPI 비중 |
| | `kosdaq_weight NUMERIC` | 그 달 말 기준 KOSDAQ 비중 |
| | `basis TEXT` | 비중 산출 기준(기본 `month_end_market_capitalization`) |

두 mart 객체는 `core.index_total_return_daily` / `core.index_benchmark_weight_monthly`
위의 얇은 view다. 적재는 core 테이블에 하고, AI는 mart 이름만 읽는다.

### 왜 price index가 아니라 TR인가
배당을 뺀 price index는 전략이 이겨야 할 기준을 구조적으로 낮춘다. 계약은 TR만 받는다.
`index_code`에 `KOSPI`/`KOSDAQ`(price return)를 적재해도 reader가 조회하지 않는다.

### 왜 비중을 lag된 상태로 저장하지 않는가
저장값은 **관측 월 그대로**다. 한 달 lag는 reader
(`ai/ai_graph/nodes/backtest.py::_lagged_official_benchmark_weights`)가 적용한다.
이미 lag된 값을 저장하면 어느 달의 관측인지가 사라져 재검증이 불가능해진다.

## 2. reader가 내는 값

`PipelineDataBundle.official_benchmark` (metadata가 아니라 전용 필드 — metadata는 응답
envelope에 그대로 재발행되는데, 이 시계열은 세션×지수 단위라 payload를 부풀린다):

```
{
  "available": bool,
  "unavailable_reason": str | None,
  "level_source": "mart.krx_index_total_return_daily",
  "weight_source": "mart.krx_benchmark_monthly_weights",
  "index_codes": {"kospi_tr": "KOSPI_TR", "kosdaq_tr": "KOSDAQ_TR"},
  "window_start": "YYYY-MM-DD", "window_end": "YYYY-MM-DD",
  "weight_lag_months": 1,
  "kospi_tr":  {"YYYY-MM-DD": float, ...},
  "kosdaq_tr": {"YYYY-MM-DD": float, ...},
  "monthly_weights": {"YYYY-MM": [kospi_weight, kosdaq_weight], ...}
}
```

`PipelineDataBundle.metadata["official_benchmark"]`에는 시계열을 뺀 요약(available,
reason, source, 각 시계열 세션 수, 월 수)만 실린다.

전달 경로: `data_node` → `state["official_benchmark"]` → `backtest_node` →
`_CandidateBacktestSession(official_benchmark=...)` → `_build_benchmark_context`.

### 조회 창
- TR 레벨: 백테스트 창(`BACKTEST_WINDOW_POLICY_ID = krx_pit_common_stock_5y_kst_session_v1`)의
  `start..end`.
- 월별 비중: 창 시작월의 **한 달 전**부터 창 종료월까지. 첫 거래월이 그 앞 달의 비중을
  필요로 하기 때문이다.

### 실패는 예외가 아니다
테이블 부재·권한 오류·statement timeout은 모두 `available=False` + 사유 문자열로 내려간다.
실패한 statement는 트랜잭션을 INERROR로 두므로 `_rollback_quietly` 후
`_set_statement_timeout`을 복구한다(indicator family 로딩과 동일 관행).
값이 비유한/비양수인 행은 버려지고, 그만큼 커버리지가 낮아져 아래 규칙이 판정한다.

## 3. 커버리지 판정 규칙

`ai/ai_graph/nodes/backtest.py::_official_benchmark_total_return`이 적용한다. 기준은
**백테스트가 실제로 가격을 보유한 세션 집합**이다(캘린더 전체가 아니다).

1. **양 끝 세션 필수** — 창의 첫 세션과 마지막 세션 모두 두 지수의 레벨을 가져야 한다.
   총수익률은 이 두 점만으로 결정되고, 그 값이 게이트가 비교하는 숫자이므로 추정된 끝점은
   숫자를 날조하는 것과 같다.
2. **세션 커버리지 ≥ 99%** (`OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE = 0.99`) — 두 지수
   모두를 가진 세션 수 / 백테스트 세션 수. 긴 결측 구간이 전 구간 비교로 둔갑하지 못하게
   한다.
3. **모든 거래월에 직전월 비중 존재** — `_official_krx_tr_benchmark_curve`가 비중 없는 월에
   대해 `ValueError`를 던지고, `_official_benchmark_total_return`이 이를 사유로 변환한다.
   50/50 fallback은 없다.

허용 범위 안의 결측 세션은 **채우지 않고 건너뛴다**. TR은 레벨이므로 건너뛰면 곡선의
표본 간격만 성기어질 뿐이지만, forward-fill은 지수에 없던 보합일을 만들어낸다.

판정 결과는 `backtest_payload["benchmark"]["primary"]["session_coverage"]`로 공개된다
(거부된 경우에도 얼마나 모자랐는지 볼 수 있게 남긴다).

## 4. 게이트와의 관계

이 작업은 게이트 의미론을 바꾸지 않는다. `_passes_objective_floor`는 그대로
`payload["benchmark"]["primary"]["available"]`과 `["return"]`을 읽는다. 바뀐 것은
`available`이 참이 될 수 있는 경로가 생겼다는 점뿐이다.

보조 벤치마크(동일가중 매수-보유 프록시)의 `daily_returns`·`selection_return`은 손대지
않았다. 공식 시계열은 primary total return에만 쓰인다 — 그래서 데이터가 들어와도 기존에
비교하던 숫자들이 움직이지 않는다.

## 5. 아직 안 된 것

실데이터 적재(백필)는 이 계약의 범위 밖이다. `core.index_total_return_daily`와
`core.index_benchmark_weight_monthly`가 비어 있는 한 primary는
`"mart.krx_index_total_return_daily has no usable rows for KOSPI_TR, KOSDAQ_TR between ..."`
사유로 unavailable로 남는다.
