# P1-DE-01 lineage quality fail-closed

ingest는 downstream 결과를 만들기 전에 `core.ohlcv_daily` 대상 행과
`meta.lineage_event` 행의 coverage를 조회한다. 기본 SLO는 100%이며, 누락·빈 입력·
과다 보고는 `LineageQualitySLOViolation`으로 실패한다.

실패 시 ingestion run은 `failed`로 종료되고 `OhlcvIngestionResult`가 반환되지 않는다.
따라서 lineage quality breach가 부분 결과나 성공 상태로 downstream에 전파되지 않는다.
