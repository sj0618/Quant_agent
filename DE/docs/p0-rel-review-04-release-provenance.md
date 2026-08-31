# P0-REL-REVIEW-04 release data provenance review

release manifest는 결과가 소비되기 전에 source, as-of, freshness, canonical lineage
hash와 fallback 0을 함께 증명해야 한다. 검토기는 manifest와 lineage hash를 다시
계산하고, 표본 전체가 통과할 때만 `valid=true`를 반환한다.

| 검토 항목 | 통과 조건 |
| --- | --- |
| source | fixture/mock/proxy/unknown이 아닌 source |
| as-of | ISO 날짜 |
| freshness | 비어 있거나 unknown/missing이 아님 |
| lineage hash | canonical manifest 재계산값과 일치 |
| fallback | `fallback_count == 0` |

로컬 테스트 manifest는 계약 검증용이며 실제 PostgreSQL release evidence를 대체하지
않는다.
