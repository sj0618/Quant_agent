# SEIBro raw 리포트 기반 감성 점수 추출 및 유니버스 생성 계획서

## 1. 목적

현재 로컬 DB에는 SEIBro 애널리스트 리포트 원문 응답이 `raw.seibro_report_response`에 저장되어 있다.  
이 원문 JSON을 기반으로 다음 산출물을 만든다.

1. 리포트 단위 정규화 테이블: `feature.seibro_report_summary`
2. 리포트별 LLM 감성 점수: `feature.seibro_sentiment`
3. 기준일별 SEIBro 감성 유니버스: `feature.seibro_universe_daily`
4. 백테스트용 as-of 유니버스 뷰: `mart.seibro_universe_asof`

최종 목적은 전체 보통주 유니버스 백테스트와 별도로, **SEIBro 감성 점수 기반 유니버스 백테스트**를 한 번 더 실행해 성과를 비교하는 것이다.

---

## 2. 현재 상태

| 구분 | 상태 |
|---|---|
| 원문 응답 | `raw.seibro_report_response`에 저장됨 |
| 정규화 리포트 | `feature.seibro_report_summary` 테이블은 있으나 현재 비어 있음 |
| 감성 점수 | `feature.seibro_sentiment` 테이블은 있으나 현재 비어 있음 |
| 유니버스 | `feature.seibro_universe_daily`, `mart.seibro_universe_asof`는 있으나 점수 미생성 상태 |

현재 raw payload의 핵심 구조는 다음과 같다.

```text
raw.seibro_report_response.payload_jsonb
└── rows[]
    ├── STD_DT
    ├── REP_SECN
    ├── SHOTN_ISIN
    ├── ENTR_SUMM_CONTENT
    ├── INVST_OPINION_GRD_CONTENT
    ├── TARGET_PRICE
    ├── CPRI
    ├── WROT_ORG_NM
    └── WRITER_NM
```

---

## 3. 전체 처리 흐름

| 단계 | 입력 | 처리 | 출력 |
|---|---|---|---|
| 1 | `raw.seibro_report_response` | `payload_jsonb->rows[]` 펼치기 | 리포트 후보 row |
| 2 | 리포트 후보 row | 날짜/종목/요약문/투자의견/목표가/현재가 정규화 | `feature.seibro_report_summary` |
| 3 | `feature.seibro_report_summary` | LLM 감성 점수 추출 | `feature.seibro_sentiment` |
| 4 | 리포트별 감성 점수 | 기준일별 lookback 집계 | `feature.seibro_universe_daily` |
| 5 | included universe | 백테스트 조인 | `mart.seibro_universe_asof` |

---

## 4. Raw → `feature.seibro_report_summary` 정규화

여기서 말하는 “요약”은 LLM이 원문을 다시 줄이는 작업이 아니다.  
SEIBro raw JSON에서 리포트 단위 필드를 추출해, 분석 가능한 컬럼으로 정리하는 작업이다.

| raw 필드 | 정규화 컬럼 | 설명 |
|---|---|---|
| `STD_DT` | `report_date` | 리포트 기준일 |
| `REP_SECN` | `company_name`, ticker 추출 원천 | 회사명/종목명 문자열 |
| `SHOTN_ISIN` | ticker fallback | ticker 추출 실패 시 보조 식별값 |
| `ENTR_SUMM_CONTENT` | `summary` | SEIBro 제공 리포트 요약문 |
| `INVST_OPINION_GRD_CONTENT` | `opinion` | 투자의견 |
| `TARGET_PRICE` | `target_price` | 목표가 |
| `CPRI` | `close_price` | 현재가 |
| `WROT_ORG_NM` | `institution` | 작성 기관 |
| `WRITER_NM` | `author` | 작성자 |
| `payload_hash` | `source_payload_hash` | raw lineage |

정규화 시 필수 조건:

| 조건 | 처리 |
|---|---|
| `report_date` 없음 | 제외 |
| `summary` 없음 | 제외 |
| 종목 매핑 실패 | `symbol_id = NULL`로 보존하거나 별도 품질 로그 기록 |
| 중복 리포트 | `report_date + symbol_id + institution + author + summary hash` 기준 dedupe |
| 숫자 파싱 실패 | `target_price`, `close_price`는 `NULL` 허용 |

권장 추출 SQL 초안:

```sql
SELECT
  r.raw_id,
  r.payload_hash,
  row->>'STD_DT' AS report_date,
  row->>'REP_SECN' AS company_text,
  row->>'SHOTN_ISIN' AS ticker_fallback,
  row->>'ENTR_SUMM_CONTENT' AS summary,
  row->>'INVST_OPINION_GRD_CONTENT' AS opinion,
  row->>'TARGET_PRICE' AS target_price,
  row->>'CPRI' AS close_price,
  row->>'WROT_ORG_NM' AS institution,
  row->>'WRITER_NM' AS author
FROM raw.seibro_report_response r
CROSS JOIN LATERAL jsonb_array_elements(r.payload_jsonb->'rows') AS row;
```

---

## 5. LLM 감성 점수 추출 설계

### 5.1 점수 산출 단위

감성 점수는 **리포트 1개당 1개**를 산출한다.

| 단위 | 이유 |
|---|---|
| 리포트별 점수 | 기관/작성자/날짜별 의견 변화를 보존 가능 |
| 종목별 점수 | 리포트별 점수를 기준일별로 집계해서 산출 |
| 기준일별 유니버스 | 백테스트 시점마다 look-ahead bias 없이 사용 |

### 5.2 LLM 입력 필드

LLM에는 `feature.seibro_report_summary`의 정규화 row를 넣는다.

```json
{
  "report_id": 12345,
  "report_date": "2026-05-20",
  "company_name": "예시기업",
  "summary": "SEIBro 제공 요약문",
  "opinion": "매수",
  "target_price": 90000,
  "close_price": 72000,
  "institution": "예시증권",
  "author": "홍길동"
}
```

### 5.3 LLM 판단 기준

LLM은 다음 요소를 종합해 점수를 산출한다.

| 요소 | 판단 내용 |
|---|---|
| `summary` | 실적 개선/악화, 성장/둔화, 수익성, 리스크, 업황 |
| `opinion` | 매수/중립/매도, 상향/하향, 유지 |
| `target_price`, `close_price` | 목표가 괴리율의 긍정/부정 방향 |
| 표현 강도 | “강한 성장”, “급격한 둔화” 등 강도 표현 |
| 불확실성 | 조건부 긍정, 리스크 언급, 전망 불확실성 |

### 5.4 SEIBro 매수 의견 편향 보정

SEIBro 애널리스트 리포트는 구조적으로 `BUY`/`매수` 의견 비중이 높다.  
따라서 LLM이 투자의견을 강하게 반영하면 감성 점수가 대부분 긍정으로 쏠려, SEIBro 유니버스가 “긍정 종목”이 아니라 “리포트 커버리지 종목”에 가까워질 수 있다.

2026-05-30 로컬 DB의 `raw.seibro_report_response` 기준 집계 결과는 다음과 같다.

| 항목 | 관측 결과 |
|---|---:|
| `BUY` | 158,683건 |
| `매수` | 53,310건 |
| `Not Rated` | 21,232건 |
| 투자의견 empty | 17,588건 |
| `HOLD` | 11,348건 |
| `중립` | 3,179건 |
| `SELL`/`매도`/`REDUCE`/`비중축소`/`UNDERPERFORM` 계열 | 매우 적음 |
| 요약문에 부정 단어 포함 | 76,458건 |
| 요약문에 긍정·부정 단어 모두 포함 | 55,721건 |
| 목표가가 현재가보다 낮은 리포트 | 3,973건 |

이 결과는 다음을 의미한다.

| 설계 판단 | 이유 |
|---|---|
| `BUY = 무조건 강한 긍정` 매핑 금지 | 대부분의 리포트가 `BUY`/`매수`라 변별력이 사라짐 |
| `opinion`은 약한 prior로만 사용 | 투자의견보다 요약문의 리스크/실적 방향성이 더 중요 |
| 부정 감성은 충분히 가능 | `매수 유지`라도 실적 둔화, 마진 악화, 목표가 하향, 불확실성 확대가 있으면 중립~부정 가능 |
| 절대점수만으로 유니버스 구성하지 않음 | 매수 편향 때문에 기준일별 상대순위 필터가 필요 |

권장 점수 가중치는 MVP 기준 다음과 같다.

| 구성 요소 | 권장 가중치 | 설명 |
|---|---:|---|
| `text_sentiment_score` | 60% | 요약문 내 실적/업황/리스크 문맥 |
| `opinion_score` | 20% | 매수/중립/매도, 상향/하향/유지 |
| `target_upside_score` | 20% | 목표가 대비 현재가 괴리율 |

LLM 프롬프트에는 다음 규칙을 명시한다.

```text
BUY/매수라는 투자의견만으로 positive 판정을 내리지 마라.
투자의견이 BUY/매수여도 요약문에 실적 둔화, 마진 악화, 목표가 하향, 업황 부진, 불확실성 확대가 명확하면 sentiment_score를 중립 또는 부정으로 낮춰라.
Not Rated/HOLD/중립이어도 요약문에 실적 개선, 수주 증가, 업황 회복, 목표가 상승여력이 명확하면 긍정 점수를 줄 수 있다.
```

### 5.5 점수 범위

| 점수 구간 | 라벨 | 의미 |
|---:|---|---|
| `0.70 ~ 1.00` | `very_positive` | 강한 긍정 |
| `0.30 ~ 0.69` | `positive` | 긍정 |
| `-0.29 ~ 0.29` | `neutral` | 중립 |
| `-0.69 ~ -0.30` | `negative` | 부정 |
| `-1.00 ~ -0.70` | `very_negative` | 강한 부정 |

---

## 6. LLM 출력 포맷

LLM 출력은 반드시 JSON object 하나만 반환하도록 한다.  
마크다운, 설명문, 코드블록은 금지한다.

### 6.1 필수 JSON Schema

```json
{
  "report_id": 12345,
  "sentiment_score": 0.62,
  "sentiment_label": "positive",
  "confidence": 0.84,
  "text_sentiment_score": 0.55,
  "opinion_score": 0.70,
  "target_upside_score": 0.65,
  "investment_signal": "constructive",
  "positive_factors": [
    "실적 개선 전망",
    "목표가 대비 상승여력"
  ],
  "negative_factors": [
    "원가 부담"
  ],
  "risk_flags": [
    "margin_pressure"
  ],
  "reasoning_short": "요약문은 실적 개선과 목표가 상승여력을 강조하지만 원가 부담 리스크가 일부 존재한다."
}
```

### 6.2 필드 정의

| 필드 | 타입 | 필수 | 저장 위치 | 설명 |
|---|---|---:|---|---|
| `report_id` | integer | 예 | 검증용 | 입력 `report_id`와 동일해야 함 |
| `sentiment_score` | number | 예 | `feature.seibro_sentiment.sentiment_score` | 최종 감성 점수, `-1.0 ~ 1.0` |
| `sentiment_label` | string | 예 | 로그/추후 확장 | 점수 라벨 |
| `confidence` | number | 예 | 로그/추후 확장 | 판단 신뢰도, `0.0 ~ 1.0` |
| `text_sentiment_score` | number | 예 | 로그/추후 확장 | 요약문 기반 점수 |
| `opinion_score` | number/null | 예 | 로그/추후 확장 | 투자의견 기반 점수 |
| `target_upside_score` | number/null | 예 | 로그/추후 확장 | 목표가/현재가 기반 점수 |
| `investment_signal` | string | 예 | 로그/추후 확장 | 투자 시그널 요약 |
| `positive_factors` | string[] | 예 | 로그/추후 확장 | 긍정 근거 최대 3개 |
| `negative_factors` | string[] | 예 | 로그/추후 확장 | 부정 근거 최대 3개 |
| `risk_flags` | string[] | 예 | 로그/추후 확장 | 표준화된 리스크 태그 |
| `reasoning_short` | string | 예 | 로그/추후 확장 | 1문장 근거 |

현재 DB 스키마 기준으로는 `sentiment_score`, `model_version`, `prompt_version`, `run_id`만 `feature.seibro_sentiment`에 직접 저장한다.  
그 외 상세 필드는 다음 중 하나로 관리한다.

| 방식 | 권장도 | 설명 |
|---|---:|---|
| JSONL 실행 로그로 보존 | MVP 권장 | 스키마 변경 없이 검증 가능 |
| `feature.seibro_sentiment_detail` 추가 | 추후 권장 | 근거/신뢰도/세부 점수까지 DB 분석 가능 |
| 기존 `feature.seibro_sentiment`에 JSONB 컬럼 추가 | 조건부 | 단순하지만 기존 스키마 변경 필요 |

### 6.3 허용 enum

```text
sentiment_label:
- very_negative
- negative
- neutral
- positive
- very_positive

investment_signal:
- strongly_constructive
- constructive
- neutral
- cautious
- strongly_cautious

risk_flags:
- demand_slowdown
- margin_pressure
- earnings_miss
- valuation_burden
- target_price_cut
- opinion_downgrade
- sector_downturn
- execution_risk
- liquidity_risk
- uncertainty_high
```

### 6.4 출력 검증 규칙

| 검증 항목 | 실패 시 처리 |
|---|---|
| JSON parse 실패 | 재시도 |
| `report_id` 불일치 | 실패 처리 |
| `sentiment_score` 범위 초과 | 실패 처리 |
| `sentiment_label` enum 불일치 | 실패 처리 |
| `confidence` 범위 초과 | 실패 처리 |
| 필수 필드 누락 | 재시도 후 실패 처리 |
| 같은 `report_id` 재처리 | model/prompt version이 같으면 skip |

---

## 7. 프롬프트 초안

### 7.1 System Prompt

```text
너는 한국 주식 애널리스트 리포트 요약문을 분석하는 금융 NLP 분류기다.
목표는 리포트가 해당 종목의 향후 투자 매력도에 대해 긍정적인지 부정적인지를 -1.0부터 1.0까지의 점수로 산출하는 것이다.

규칙:
1. 반드시 JSON object 하나만 출력한다.
2. 마크다운, 코드블록, 추가 설명을 출력하지 않는다.
3. sentiment_score는 -1.0 이상 1.0 이하 숫자다.
4. confidence는 0.0 이상 1.0 이하 숫자다.
5. summary, opinion, target_price, close_price를 모두 고려한다.
6. 목표가 상승여력이 있더라도 본문이 명확히 부정적이면 중립 또는 부정으로 조정한다.
7. 투자의견이 매수여도 목표가 하향, 실적 둔화, 마진 악화가 뚜렷하면 점수를 낮춘다.
8. BUY/매수라는 단어만으로 positive 판정을 내리지 않는다.
9. Not Rated/HOLD/중립이어도 요약문과 목표가 정보가 긍정적이면 긍정 점수를 줄 수 있다.
10. 불확실성이 크거나 근거가 부족하면 confidence를 낮춘다.
11. 입력에 없는 사실을 추론해 추가하지 않는다.
```

### 7.2 User Prompt Template

```text
다음 SEIBro 애널리스트 리포트 요약 정보를 감성 점수로 변환하라.

입력:
{
  "report_id": {{report_id}},
  "report_date": "{{report_date}}",
  "company_name": "{{company_name}}",
  "summary": "{{summary}}",
  "opinion": "{{opinion}}",
  "target_price": {{target_price_or_null}},
  "close_price": {{close_price_or_null}},
  "institution": "{{institution}}",
  "author": "{{author}}"
}

반드시 아래 JSON schema와 동일한 key를 가진 JSON object 하나만 출력하라.

{
  "report_id": {{report_id}},
  "sentiment_score": number,
  "sentiment_label": "very_negative|negative|neutral|positive|very_positive",
  "confidence": number,
  "text_sentiment_score": number,
  "opinion_score": number|null,
  "target_upside_score": number|null,
  "investment_signal": "strongly_constructive|constructive|neutral|cautious|strongly_cautious",
  "positive_factors": ["string"],
  "negative_factors": ["string"],
  "risk_flags": ["demand_slowdown|margin_pressure|earnings_miss|valuation_burden|target_price_cut|opinion_downgrade|sector_downturn|execution_risk|liquidity_risk|uncertainty_high"],
  "reasoning_short": "string"
}
```

---

## 8. 감성 유니버스 생성 규칙

감성 유니버스는 리포트별 점수를 그대로 쓰지 않고, 백테스트 기준일마다 과거 리포트만 사용해 집계한다.

### 8.1 기본 규칙

| 항목 | 기본값 |
|---|---|
| lookback 기간 | 최근 12개월 |
| 최소 리포트 수 | 1개 |
| positive threshold | `avg_sentiment_score >= 0.30` |
| 상대순위 threshold | 기준일별 `sentiment_percentile >= 0.60` 권장 |
| 기준일 조건 | `report_date <= as_of_date` |
| 미래 데이터 사용 | 금지 |
| 집계 방식 | 단순 평균 MVP, 추후 시간가중 평균 |

SEIBro는 매수 의견 편향이 강하므로, 절대점수 기준만 쓰면 유니버스가 과도하게 넓어질 수 있다.  
따라서 MVP에서는 `avg_sentiment_score >= 0.30`을 기본 필터로 두되, 실전 백테스트 비교에서는 기준일별 상위 30~40% 같은 상대순위 필터를 함께 검토한다.

### 8.2 유니버스 포함 조건

```text
included = true
if
  report_count >= min_reports
  and avg_sentiment_score >= positive_threshold
  and sentiment_percentile >= relative_threshold
```

단, 특정 기준일의 SEIBro 커버리지 종목 수가 너무 적으면 상대순위 필터가 과도하게 작동할 수 있다. 이 경우에는 `report_count`와 절대점수 기준만 적용하고, 리포트에는 “상대순위 필터 미적용”을 명시한다.

### 8.3 제외 사유

| exclusion_reason | 의미 |
|---|---|
| `insufficient_reports` | lookback 기간 내 리포트 수 부족 |
| `sentiment_below_threshold` | 평균 감성 점수 미달 |
| `sentiment_percentile_below_threshold` | 기준일별 상대순위 미달 |
| `symbol_mapping_failed` | 종목 매핑 실패 |
| `llm_score_missing` | 감성 점수 미생성 |

### 8.4 기준 SQL 초안

```sql
WITH recent_reports AS (
  SELECT
    d.as_of_date,
    r.symbol_id,
    s.sentiment_score,
    r.report_date
  FROM dim.calendar d
  JOIN feature.seibro_report_summary r
    ON r.report_date <= d.as_of_date
   AND r.report_date > d.as_of_date - INTERVAL '12 months'
  JOIN feature.seibro_sentiment s
    ON s.report_id = r.report_id
  WHERE r.symbol_id IS NOT NULL
),
aggregated AS (
  SELECT
    as_of_date,
    symbol_id,
    AVG(sentiment_score)::numeric(6,4) AS avg_sentiment_score,
    COUNT(*)::int AS report_count
  FROM recent_reports
  GROUP BY as_of_date, symbol_id
),
ranked AS (
  SELECT
    *,
    PERCENT_RANK() OVER (
      PARTITION BY as_of_date
      ORDER BY avg_sentiment_score
    )::numeric(6,4) AS sentiment_percentile
  FROM aggregated
)
INSERT INTO feature.seibro_universe_daily (
  as_of_date,
  symbol_id,
  avg_sentiment_score,
  report_count,
  included,
  exclusion_reason,
  run_id
)
SELECT
  as_of_date,
  symbol_id,
  avg_sentiment_score,
  report_count,
  avg_sentiment_score >= 0.30
    AND report_count >= 1
    AND sentiment_percentile >= 0.60 AS included,
  CASE
    WHEN report_count < 1 THEN 'insufficient_reports'
    WHEN avg_sentiment_score < 0.30 THEN 'sentiment_below_threshold'
    WHEN sentiment_percentile < 0.60 THEN 'sentiment_percentile_below_threshold'
    ELSE NULL
  END AS exclusion_reason,
  :run_id
FROM ranked;
```

---

## 9. 백테스트 연결 방식

전체 보통주 백테스트:

```sql
SELECT *
FROM mart.common_stock_feature_frame_asof;
```

SEIBro 감성 유니버스 백테스트:

```sql
SELECT
  f.*
FROM mart.common_stock_feature_frame_asof f
JOIN core.symbol_master sm
  ON sm.symbol = f.symbol
JOIN mart.seibro_universe_asof su
  ON su.as_of_date = f.as_of_date
 AND su.symbol_id = sm.symbol_id;
```

성과 비교 리포트에는 최소 다음 항목을 포함한다.

| 항목 | 전체 보통주 | SEIBro 감성 유니버스 |
|---|---:|---:|
| 기간 | 필요 | 필요 |
| universe 평균 종목 수 | 필요 | 필요 |
| 누적 수익률 | 필요 | 필요 |
| CAGR | 필요 | 필요 |
| MDD | 필요 | 필요 |
| Sharpe | 필요 | 필요 |
| 거래 수 | 필요 | 필요 |
| 제외 종목/사유 | 선택 | 필요 |

---

## 10. 품질 검증

| 검증 | 기준 |
|---|---|
| raw 펼치기 검증 | `raw rows[]` 수와 정규화 후보 row 수 비교 |
| 필수 컬럼 검증 | `report_date`, `summary` null 비율 확인 |
| 종목 매핑 검증 | `symbol_id IS NULL` 비율 확인 |
| LLM 출력 검증 | JSON schema, 범위, enum 검증 |
| 중복 검증 | 동일 리포트 중복 삽입 방지 |
| look-ahead 검증 | `report_date <= as_of_date` 위반 0건 |
| 유니버스 검증 | 기준일별 included 종목 수 분포 확인 |
| 백테스트 검증 | 전체 유니버스와 SEIBro 유니버스 결과 각각 재현 |

---

## 11. 구현 순서

| 순서 | 작업 | 완료 조건 |
|---:|---|---|
| 1 | raw payload 구조 샘플링 | raw key/row 구조 문서화 |
| 2 | raw → summary 정규화 로직 작성 | `feature.seibro_report_summary` 적재 |
| 3 | 정규화 품질 리포트 작성 | null/매핑 실패/중복 현황 확인 |
| 4 | LLM prompt/version 고정 | `prompt_version` 확정 |
| 5 | LLM JSON 출력 검증기 작성 | schema validation 통과 |
| 6 | 리포트별 감성 점수 적재 | `feature.seibro_sentiment` 적재 |
| 7 | 기준일별 유니버스 생성 | `feature.seibro_universe_daily` 적재 |
| 8 | as-of bias 검증 | 미래 리포트 사용 0건 |
| 9 | 백테스트 입력 조립 | SEIBro universe OHLCV CSV 생성 |
| 10 | 전체 vs SEIBro 백테스트 비교 | 비교 리포트 생성 |

---

## 12. MVP 결정사항

| 항목 | 결정 |
|---|---|
| LLM 재요약 | 하지 않음 |
| LLM 역할 | 정규화된 리포트 row의 감성 점수 산출 |
| 저장 점수 | `feature.seibro_sentiment.sentiment_score` |
| 점수 범위 | `-1.0 ~ 1.0` |
| 투자의견 처리 | `BUY`/`매수`는 약한 prior로만 사용, 단독 positive 판정 금지 |
| 점수 가중치 | 요약문 60%, 투자의견 20%, 목표가 괴리율 20% |
| 유니버스 절대 threshold | 기본 `avg_sentiment_score >= 0.30` |
| 유니버스 상대 threshold | 기준일별 상위 40% 이상, 즉 `sentiment_percentile >= 0.60` 권장 |
| lookback | 기본 최근 12개월 |
| 최소 리포트 수 | MVP `1`, 안정화 후 `2` 검토 |
| 상세 LLM 출력 | MVP는 JSONL 로그 보존, 추후 DB 컬럼/테이블 확장 |
| 백테스트 비교 | 전체 보통주 1회 + SEIBro positive universe 1회 |
