# P2-DE-01 ingestion capacity/recovery benchmark

이 benchmark는 실제 `normalize_krx_market_day` 변환 함수와 full-pipeline의
`summary_is_successful` resume 판정 경로를 실행한다. 로컬 synthetic workload의
처리량·freshness artifact와 failed-record recovery control flow를 남기며, PostgreSQL
실데이터 용량이나 운영 freshness를 주장하지 않는다.

```bash
PYTHONPATH=DE python DE/scripts/benchmark_ingestion_capacity.py \
  --rows 10000 \
  --as-of 2026-08-21 \
  --output DE/.omx/artifacts/ingestion-capacity-benchmark.json
```

artifact에는 `load`, `freshness`, `recovery` 세 영역이 포함된다. 운영 capacity
판단에는 실제 서버 입력을 별도 측정해야 한다.
