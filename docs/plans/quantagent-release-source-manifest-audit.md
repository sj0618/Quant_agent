# Release source manifest 표본 감사 계약

## 목적

release 데이터 입력의 표본이 `source`, `as_of`, `freshness`, `lineage_hash`를 모두 갖고
있는지 확인하고, 저장된 `lineage_hash`를 동일한 정규화 규칙으로 재계산해 일치 여부를
기록한다. release 감사에서는 `fixture`, `unknown` source와 `unknown` freshness를 유효한
증적으로 인정하지 않는다.

## 입력과 실행

샘플 파일 경로는 실행 인자로 전달한다. 파일은 JSON 배열 또는 `{ "samples": [...] }`
형식이어야 한다.

```powershell
python -m ai_graph.source_manifest_audit <sample-file.json>
```

출력은 JSON 감사 보고서이며 다음 QA 필드를 포함한다.

| 필드 | 의미 | 통과 조건 |
|---|---|---:|
| `sample_count` | 감사한 표본 수 | 1 이상 |
| `required_field_missing_count` | 필수 필드 누락 셀 수 | 0 |
| `hash_checked_count` | 재계산 가능한 표본 수 | 표본 수와 동일 |
| `hash_match_count` | 재계산 hash 일치 수 | `hash_checked_count`와 동일 |
| `hash_mismatch_count` | 재계산 hash 불일치 수 | 0 |
| `required_fields_present_rate` | 필수 필드 완비율 | 1.0 |
| `hash_match_rate` | 표본 hash 일치율 | 1.0 |
| `valid` | release 정책까지 포함한 종합 결과 | `true` |

## 해시 재계산 계약

`lineage_hash` 자체를 제외한 manifest의 정규화 JSON을 UTF-8로 직렬화하고 SHA-256을
계산한다. 필드 순서가 달라도 같은 값이면 같은 hash가 되며, `source_version`이나
`lineage_refs`가 변경되면 감사에서 불일치로 판정한다.

## QA 증적

`ai/tests/test_source_manifest_audit.py`는 완전한 postgres 표본의 100% 통과, freshness
누락, fixture source, 변조된 lineage 필드의 실패를 각각 검증한다.
