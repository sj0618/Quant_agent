# Point-in-time 유니버스와 상장폐지 처리 데이터 계약

작성일: 2026-08-20

## 1. 결론

이 프로젝트는 날짜별 종목 소속과 가격 데이터의 존재 여부를 분리해서 관리한다. 상장폐지 처리는 가격이 사라진 사실만으로 판단하지 않고, 공식 이벤트와 마지막 거래일을 우선 사용한다.

최종 정책은 다음과 같다.

| 항목 | 결정 |
|---|---|
| PIT 유니버스 | `core.symbol_listing_history`와 `core.trading_calendar`로 날짜별 상장 종목을 결정한다. |
| 가격 데이터 없음 | 유니버스에서 삭제하지 않는다. 가격 누락 상태를 별도로 기록한다. |
| 공식 상장폐지 이벤트 | `last_trade_date`와 공식 회수 가격을 우선 사용한다. |
| 공식 회수 가격 없음 | 마지막 실제 거래일 종가를 대체 가격으로 사용한다. |
| 이벤트 자체가 없음 | 20거래일 연속 가격이 없으면 `delisting_inferred`로 표시한다. 사실로 확정하지 않는다. |
| 0원 회수 | 기본 결과가 아니라 보수적 민감도 분석에서만 사용한다. |
| 합병·인수 | 일반 상장폐지와 분리하고 승계 종목과 교환비율을 별도로 처리한다. |
| 결과 품질 | 공식 가격, 마지막 종가 대체, 추정 상장폐지를 결과 메타데이터로 구분한다. |

현재 백테스트의 `20거래일 후 0원 상각`은 포지션이 영원히 남는 문제를 막는 fallback으로는 사용할 수 있다. 다만 정상 결과의 기본 정책으로는 공식 이벤트와 마지막 거래 가격을 먼저 사용해야 한다.

## 2. 왜 이 계약이 필요한가

백테스트에서 현재 상장된 종목만 과거 데이터에 넣으면 이미 사라진 종목이 빠진다. 이 상태에서는 과거에 실제로 투자할 수 있었던 종목군보다 성과가 좋아 보일 수 있다. 이것이 생존자 편향이다.

상장폐지 종목을 반대로 단순히 삭제해도 문제가 생긴다. 보유 중인 종목이 어느 날 가격 데이터에서 사라졌을 때, 그 이유가 휴장인지, 거래정지인지, 수집 실패인지, 실제 상장폐지인지 알 수 없기 때문이다.

따라서 다음 두 질문을 분리해야 한다.

1. 특정 거래일에 이 종목이 투자 대상이었는가?
2. 그 거래일에 실제 가격 bar를 사용할 수 있었는가?

첫 번째 질문은 PIT 유니버스가 답한다. 두 번째 질문은 가격 데이터 품질과 거래 가능성 데이터가 답한다.

## 3. 외부 백테스트 시스템 조사

### 3.1 QuantConnect LEAN

LEAN은 상장폐지 이벤트를 별도 데이터 객체로 전달한다. 이벤트에는 경고와 최종 상장폐지 유형이 있고, 상장폐지 전 마지막 가격도 함께 전달한다. 공식 문서는 마지막 거래일에 경고를 발생시켜 포지션을 정리할 시간을 주고, 이후 상장폐지 종목을 자동 청산한다고 설명한다.

프로젝트에 적용할 점은 두 가지다.

- 가격 데이터가 사라진 뒤 일정 기간을 기다리는 것보다 공식 이벤트를 먼저 사용한다.
- 상장폐지 이벤트와 마지막 가격을 하나의 처리 단위로 보존한다.

### 3.2 Zipline

Zipline은 날짜와 자산별로 해당 자산이 살아 있었는지 나타내는 `lifetimes` 행렬을 사용한다. 특정 날짜에 자산이 존재했는지와 가격을 조회할 수 있는지는 별도 개념이다. 상장폐지 후 가격을 무한정 채우지 않고, 가격이 없으면 `NaN`으로 돌려준다.

이 구조는 프로젝트가 유니버스 membership과 가격 bar 유무를 분리하는 근거가 된다.

### 3.3 Norgate Data

Norgate는 현재 종목과 상장폐지 종목을 모두 보존한다. 상장폐지는 해당 시장에서 더 이상 거래할 수 없는 상태로 정의하며, 미국 시장의 경우 OTC로 이동한 뒤에도 거래가 계속되면 최종 상장폐지로 확정하지 않는다.

Norgate는 별도의 상장폐지 수익률을 제공하지 않는 경우가 많고, 시뮬레이션에서는 남은 포지션을 최종 거래 bar에서 종료하는 방식을 사용자 관행으로 소개한다. 또 과거 날짜의 지수 구성 종목을 날짜별 참·거짓 값으로 조회할 수 있도록 한다.

프로젝트에 적용할 점은 다음과 같다.

- 단순히 현재 상장 여부를 조회하지 않는다.
- 종목의 lifecycle과 마지막 거래일을 관리한다.
- 공식 회수 가격이 없으면 마지막 거래 bar를 명시적인 proxy로 사용할 수 있다.

### 3.4 CRSP와 Shumway 연구

Tyler Shumway의 1997년 연구는 CRSP 데이터에서 상장폐지 수익률이 빠질 경우 성과가 왜곡될 수 있다고 지적한다. 특히 파산이나 부정적인 사유로 상장폐지된 종목의 누락 수익률이 큰 경우가 많다고 설명한다.

따라서 상장폐지 수익률을 무시하거나 종목을 데이터에서 삭제하는 방식은 적절하지 않다. 회수 가격의 출처와 추정 여부를 결과에 남겨야 한다.

## 4. 현재 프로젝트의 관련 구현

### 4.1 PIT 유니버스

`DE/migrations/007_common_stock_mart_views.sql:3-26`은 다음 조건으로 `mart.common_stock_universe_asof`를 만든다.

- `core.trading_calendar`의 개장 거래일
- `core.symbol_listing_history`의 상장 구간
- KOSPI 또는 KOSDAQ
- `security_type = '보통주'`
- `valid_from <= trade_date <= valid_to`

이 구현은 현재 상장 목록이 아니라 날짜별 lifecycle을 사용한다는 점에서 PIT 계약의 기반으로 적합하다.

### 4.2 가격 데이터와 PIT membership

AI 데이터 소스는 `ai/ai_graph/data_sources/db.py:389-412`에서 PIT 유니버스를 조회한다. 같은 파일의 `:350-364`는 PIT 유니버스 멤버 수와 가격 bar가 없는 멤버 수를 별도로 기록한다.

이 구조는 다음 원칙과 맞는다.

```text
유니버스에 포함됨
!=
해당 날짜에 가격 bar가 있음
```

### 4.3 현재 상장폐지 fallback

`backtest_module/backtest_module/backtest.py:983-1051`은 보유 종목의 가격 bar가 없으면 누락 거래일을 누적한다. 기본 20거래일이 지나면 포지션을 제거하고 다음 계산을 수행한다.

```text
exit_price = last_price * delisting_recovery_rate
```

설정 기본값은 `delisting_recovery_rate = 0.0`이다. 이 방식은 포지션이 영원히 남는 문제를 방지하지만, 공식 상장폐지 이벤트나 실제 회수 가격을 사용하지 않는다.

### 4.4 현재 계약의 빈틈

현재 저장소에는 다음과 같은 불일치가 있다.

| 위치 | 내용 |
|---|---|
| `DE/migrations/007_common_stock_mart_views.sql:3-38` | lifecycle 기준 PIT membership. 가격 누락이 membership을 제거하지 않는다. |
| `DE/docs/DE.md:127-134` | 가격 row가 있는 날짜와 종목만 유니버스에 포함한다고 설명한다. |
| `ai/ai_graph/data_sources/db.py:711-721` | `core.symbol_master.listing_status`가 잘못 적재된 사례 때문에 직접 조회를 우회한다. |
| `backtest_module/backtest_module/models.py:184-205` | `delist` 이벤트와 회수 가격은 있지만 합병 승계와 공시 시점 정보는 부족하다. |

이번 계약은 migration 007의 lifecycle 기준을 canonical 기준으로 채택하고, 가격 데이터 존재 여부를 별도 상태로 분리한다.

## 5. PIT 유니버스 계약

### 5.1 객체와 행 단위

canonical 객체는 다음과 같다.

```text
mart.common_stock_universe_asof
```

행 단위는 다음이다.

```text
(as_of_date, symbol_id)
```

ticker 문자열은 표시용으로 사용하고, 조인과 lifecycle 연결에는 `symbol_id`를 사용한다.

### 5.2 포함 조건

특정 `as_of_date`에 종목을 포함하려면 아래 조건을 모두 만족해야 한다.

```text
as_of_date가 KRX 개장 거래일이고
listing_status = 'listed'이며
valid_from <= as_of_date <= valid_to이고
market_segment가 KOSPI 또는 KOSDAQ이고
security_type가 보통주이다.
```

`valid_to`는 마지막 유효 거래일로 정의한다. 원천 데이터의 `delisted_at`이 상장폐지 발효일을 의미한다면, 적재 전에 마지막 거래일로 정규화한다. 현재 migration이 `trade_date <= valid_to`를 사용하기 때문에 이 의미를 명확히 하지 않으면 상장폐지일에 종목이 하루 더 포함되거나 하루 빠질 수 있다.

### 5.3 가격 데이터 분리

| 상태 | 의미 |
|---|---|
| `universe_member` | 해당 날짜의 PIT 유니버스에 속함 |
| `price_available` | 해당 날짜의 유효 OHLCV bar가 있음 |
| `tradable_for_signal` | 유니버스, 가격, 필수 feature를 모두 만족함 |
| `stale_valuation` | 보유 중이나 새 가격이 없어 마지막 가격으로 평가 중임 |

가격이 없다는 이유만으로 PIT membership을 삭제하지 않는다. 대신 `pit_members_without_price_rows`와 같은 품질 지표를 결과에 남긴다.

## 6. 상장폐지 이벤트 계약

상장폐지 관련 데이터는 최소한 다음 필드를 가져야 한다.

| 필드 | 의미 |
|---|---|
| `symbol_id` | 안정적인 종목 식별자 |
| `event_type` | `delisted`, `merger`, `acquisition`, `bankruptcy`, `relisted` 등 |
| `announced_at` | 이벤트가 공시된 시점. 없으면 null |
| `last_trade_date` | 실제 마지막 거래일 |
| `effective_date` | 상장폐지 효력일 |
| `recovery_price` | 공식 청산 또는 회수 가격 |
| `recovery_price_type` | `official_settlement`, `final_close`, `zero_imputed` |
| `recovery_verified` | 공식 출처 검증 여부 |
| `source_id` | KRX, KIS, DART 등 원천 출처 |
| `source_url` 또는 `document_hash` | 근거 추적 정보 |

상장폐지 이벤트는 `last_trade_date`를 기준으로 유니버스의 마지막 날짜를 결정한다. `effective_date`만 사용하면 실제 거래 가능일과 법적 효력일이 어긋날 수 있다.

## 7. 상장폐지 처리 순서

### 7.1 공식 이벤트가 있는 경우

```text
공식 상장폐지 이벤트 확인
  -> 공식 회수 가격이 있으면 해당 가격 사용
  -> 회수 가격이 없으면 마지막 실제 거래일 종가 사용
  -> 결과에 가격 품질과 출처 기록
```

회수 가격은 다음 순서로 선택한다.

| 순위 | 가격 | 품질 등급 |
|---:|---|---|
| 1 | 공식 정리매매, 청산, 회수 가격 | `official` |
| 2 | 마지막 실제 거래일 종가 | `proxy` |
| 3 | 마지막 가격의 0% | `zero_imputed`, 민감도 분석 전용 |

공식 회수 가격을 사용하는 경우에는 해당 가격이 이미 정산 가격인지 확인한다. 정산 가격에 일반적인 슬리피지를 다시 적용하면 비용을 이중으로 계산할 수 있다.

### 7.2 공식 이벤트가 없는 경우

20거래일 연속 가격 bar가 없다는 사실만으로 상장폐지를 확정하지 않는다. 거래정지와 데이터 수집 실패가 남아 있기 때문이다.

다만 백테스트가 끝나지 않는 것을 막기 위해 fallback을 둔다.

```text
20거래일 연속 유효 가격 bar 없음
  -> delisting_inferred = true
  -> 마지막 종가를 proxy 회수 가격으로 사용
  -> 결과 품질을 degraded로 표시
  -> 0원 회수 결과를 별도 민감도 분석으로 계산
```

이 fallback은 사실을 복원하는 규칙이 아니라, 불완전한 데이터에서 계산을 계속하기 위한 모델링 규칙이다.

### 7.3 보유 중 거래정지

공식 상장폐지 이벤트가 없는 단기 가격 누락은 상장폐지로 처리하지 않는다.

- 신규 매수와 신규 매도 체결은 발생시키지 않는다.
- 보유 포지션은 마지막 가격으로 평가할 수 있다.
- 평가 가격이 오래되었다는 사실을 `stale_valuation`으로 기록한다.
- 공식 이벤트가 확인되면 상장폐지 처리 규칙으로 전환한다.

## 8. 합병과 인수

합병·인수로 종목이 사라지는 경우는 파산성 상장폐지와 다르다.

| 상황 | 처리 |
|---|---|
| 승계 법인과 교환비율 확인 | 승계 종목으로 포지션과 원가를 이전 |
| 승계 법인은 있지만 교환비율 없음 | `corporate_action_unresolved`로 표시 |
| 승계 법인 없음 | 공식 회수 가격 또는 마지막 종가 사용 |
| 단순 ticker 변경 | 안정적인 종목 식별자와 매핑 정보로 연결 |

승계 정보가 있는데 이를 0원 상장폐지로 처리하면 손실을 과대평가한다. 반대로 승계 정보가 없는데 임의로 연결하면 미래 정보를 사용하는 문제가 생긴다.

## 9. 결과 메타데이터

백테스트 결과에는 상장폐지 처리 방식이 드러나야 한다.

```json
{
  "pit_universe_source": "mart.common_stock_universe_asof",
  "pit_universe_start": "2021-01-04",
  "pit_universe_end": "2025-12-31",
  "pit_member_count": 0,
  "price_missing_member_count": 0,
  "official_delisting_count": 0,
  "inferred_delisting_count": 0,
  "official_recovery_count": 0,
  "final_close_proxy_count": 0,
  "zero_imputed_count": 0,
  "delisting_policy_version": "v1"
}
```

특히 다음 두 결과를 구분해야 한다.

```text
공식 상장폐지 데이터로 계산한 손실
!=
가격 누락을 상장폐지로 추정해 계산한 손실
```

## 10. 구현 전 확인할 사항

이번 문서는 계약을 정한 것이며 코드를 변경하지 않았다. 실제 반영 전에는 다음 사항을 확인해야 한다.

1. 공용 DB의 `core.symbol_listing_history`에 `last_trade_date` 의미가 일관되게 적재되어 있는지 확인한다.
2. KRX 또는 KIS에서 공식 회수 가격을 제공하는지 확인한다.
3. 합병·인수 승계 종목과 교환비율을 어느 데이터 소스에서 가져올지 결정한다.
4. `mart.common_stock_universe_asof`와 `DE/docs/DE.md`의 가격 row 기준을 하나로 맞춘다.
5. 상장폐지 이벤트가 있는 종목, 장기 거래정지 종목, 가격 수집 누락 종목을 각각 포함한 회귀 테스트를 추가한다.
6. 공식 가격, 마지막 종가 proxy, 0원 stress 결과를 같은 데이터셋으로 비교한다.

현재 저장소만으로는 운영 서버의 실제 KRX 상장폐지 원천 데이터와 회수 가격 적재 상태를 확인할 수 없다. 따라서 계약의 구조는 확정할 수 있지만, 실제 종목별 회수 가격의 완전성은 서버 DB 검증이 필요하다.

## 참고 출처

1. QuantConnect, "Corporate Actions: Delistings"
   https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions#05-Delistings
2. QuantConnect LEAN, `DelistingEventProvider.cs`
   https://raw.githubusercontent.com/QuantConnect/Lean/master/Engine/DataFeeds/Enumerators/DelistingEventProvider.cs
3. Zipline, API Reference: asset lifetimes
   https://zipline.ml4trading.io/api-reference.html
4. Norgate Data, Data Package FAQ
   https://norgatedata.com/data-package-faq.php
5. Tyler Shumway, "The Delisting Bias in CRSP Data", Journal of Finance, 1997
   https://scholarsarchive.byu.edu/facpub/9278/
6. 프로젝트 근거
   - `DE/migrations/007_common_stock_mart_views.sql:3-38`
   - `ai/ai_graph/data_sources/db.py:350-412,711-721`
   - `backtest_module/backtest_module/backtest.py:983-1051`
   - `backtest_module/backtest_module/models.py:184-205`
