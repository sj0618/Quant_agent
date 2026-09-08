# 하단 시장 시세 바

모든 페이지 하단에 코스피, 코스닥, 나스닥 종합, S&P 500, 비트코인, 이더리움, 달러/원을 표시한다. 모바일과 키보드에서는 시세 목록을 좌우로 스크롤한다. 항목의 도움말과 스크린리더 설명에 출처, 원시세 기준시각(KST), 등락 기준, 제공된 지연 시간과 장 마감 상태를 표시한다.

`GET /api/v1/market-ticker`는 인증 없이 공개 시장 정보만 반환한다. 요청으로 URL이나 종목을 받지 않는다. 서버가 고정된 제공처 6개 요청을 병렬 조회하고 결과를 60초 동안 보관한다. 브라우저는 60초마다 갱신한다. 각 항목의 `asOf`는 제공처의 원시세 시각이며 `metadata.asOf`는 서버 조회 시각이다. `metadata.count`는 유효한 항목 수, `metadata.sources`는 성공한 제공처다.

데이터 출처:

- 국내·미국 지수와 환율: NAVER 금융 공개 웹 화면에서 사용하는 JSON 응답. 정식 OpenAPI 계약이 있는 인터페이스는 아니므로 제공처 변경 시 해당 항목은 조회 불가로 처리한다. 환율은 하나은행 고시환율이다. URL은 `backend/app/api/routes/market_ticker.py`의 고정 목록을 참조한다.
- 비트코인·이더리움: [업비트 현재가 API](https://docs.upbit.com/kr/reference/list-tickers)의 원화 시장. 등락은 UTC 00:00 기준 전일 종가 대비이며 24시간 수익률이 아니다.

HTTP 오류, 누락된 값, 유효하지 않은 숫자·기준시각은 해당 항목을 `unavailable`과 null로 반환한다. 갱신 실패 후 이전 가격이나 예시 값으로 대체하지 않는다. 미국 휴장일에는 마지막 거래일 값과 장 마감 상태가 유지될 수 있어 전체 바를 실시간으로 표시하지 않는다. 새 키, 환경변수, DB 테이블은 필요하지 않다.

로컬 검사: `cd fe && npm test`, `cd backend && python -m pytest tests/unit/test_market_ticker.py tests/unit/test_track_c_contract_policy.py tests/unit/test_fe_contract_routes.py -q`. 이 검사의 합성 응답은 화면·오류·캐시 동작 확인용이며 실제 시세 조회 증거가 아니다. 실제 외부 시세 연결은 서버 환경에서 별도로 확인해야 한다.
