# P2-DE-QA-01 freshness/lineage audit

동일한 immutable release manifest를 두 번 감사해 source, as-of, freshness, lineage
hash와 결과/provenance trace hash가 일치하는지 확인한다. 독립 reviewer 기록은
`조은채`가 확인한 증적으로 남긴다.

| 조건 | 통과 기준 |
| --- | --- |
| source | `postgres`인 서버 manifest |
| as-of | 모든 표본이 ISO 날짜 |
| freshness | `fresh` 또는 `within_slo` |
| lineage hash | canonical source/as-of/freshness 입력 재계산값과 일치 |
| 재실행 | 결과 hash와 provenance trace hash가 모두 동일 |
| reviewer | reviewer_id, reviewed_at, decision=approved, evidence 보유 |

```bash
PYTHONPATH=DE python DE/scripts/rerun_freshness_lineage_audit.py \
  --input /path/to/server-release-manifest.json \
  --output /path/to/freshness-lineage-audit.json
```

입력은 운영 PostgreSQL pipeline이 생성한 immutable manifest여야 한다. fixture, mock,
proxy 입력은 감사가 실패하므로 로컬 테스트 결과를 실데이터 감사 결과로 대체하지
않는다.

```json
{
  "reviewer_id": "조은채",
  "reviewed_at": "YYYY-MM-DD",
  "decision": "approved",
  "evidence": "server manifest freshness and lineage hash rerun"
}
```
