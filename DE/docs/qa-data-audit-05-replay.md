# QA-DATA-AUDIT-05 deterministic replay audit

동일한 immutable release manifest를 두 번 재생해 전략 검증 리포트의 output hash와
provenance trace가 보존되는지 확인한다. `fixture` 입력은 로컬 결정론 계약일 뿐 운영
실데이터 증적이 아니며, `postgres` 입력도 독립적인 서버 실행 검토가 필요하다.

## 검증 항목

| 항목 | 통과 조건 |
| --- | --- |
| immutable input hash | 두 실행이 동일 |
| Git SHA / environment hash | 두 실행이 동일 |
| formula version / seed hash | 두 실행이 동일 |
| output hash | 두 실행이 동일 |
| provenance trace | trace hash와 단계별 source/as-of/lineage가 동일 |
| limitation record | 두 실행이 동일 |

## 실행

```bash
node DE/scripts/replay-strategy-validation-report.mjs \
  --input-manifest release --runs 2 --assert-identical-output-hash
```

`equality`의 모든 값이 `true`여야 감사가 통과한다.
