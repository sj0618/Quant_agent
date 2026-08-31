# CORE-DATA-01 real-data admission

분석·백테스트의 release 경계는 `AI_RELEASE_PROFILE=release|production`뿐 아니라
배포 런타임의 `APP_ENV=production|release`도 인식해야 한다. 이 경계에서는 다음
provenance가 모두 검증되지 않으면 downstream 실행을 시작하지 않는다.

| 증적 | 실패 시 처리 |
| --- | --- |
| PostgreSQL source | fixture/unknown이면 terminal unavailable |
| EOD/PIT source manifest | lineage·snapshot hash 불일치이면 unavailable |
| as-of coverage | required ticker의 마지막 행이 manifest as-of보다 이전이면 unavailable |
| freshness | stale/unknown이면 unavailable |
| DB 연결·조회 | fallback 없이 database unavailable |

개발 환경의 fixture loader 자체는 로컬 단위·계약 테스트를 위해 유지하지만, release
경계에서 fixture 데이터를 분석·백테스트 결과로 승격하지 않는다.
