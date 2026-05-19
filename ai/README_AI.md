# QuantAgent AI MVP

이 디렉터리는 QuantAgent AI/LLM MVP의 mock/fixture 기반 실행 표면이다.
현재 구현은 외부 LLM 키, 증권 API, 네트워크 호출 없이 worker-3 범위의
백테스트 코드 생성, AST 검증, 백테스트 실행, 리스크 판단, 리포트 생성을
검증한다.

## Worker-3 범위

| 영역 | 파일 | 계약 |
|---|---|---|
| 백테스트 코드 생성 | `nodes/backtest_code.py` | `LLMClient` 인터페이스와 `MockLLMClient` 기본값으로 fixture 코드를 생성한다. |
| 코드 보안 | `security/ast_validator.py` | `build_signals(prices)` 진입점과 allowlist import만 허용한다. |
| 백테스트 | `nodes/backtest.py` | 검증된 코드를 제한된 builtins로 실행하고 기본 3회 루프 지표를 만든다. |
| 리스크 | `risk_manager.py` | 최대 낙폭과 승률 기준으로 승인 여부와 포지션 크기를 산출한다. |
| 리포트 | `report.py` | FE 공개 payload에서 `internal_payload`를 제외하고 `trace_id`/`debug_ref`를 유지한다. |

## 검증

```bash
PYTHONPATH=ai python3 -m pytest ai/tests
PYTHONPATH=ai python3 -m compileall ai
```

## 보안/운영 원칙

- 기본 경로는 fixture/mock 전용이며 외부 자격증명을 요구하지 않는다.
- LLM 응답 코드는 실행 전 `validate_backtest_code`로 검사한다.
- `internal_payload`는 내부 추적용이며 정상 FE 응답에는 포함하지 않는다.
- JSON/Pydantic 상태가 canonical이며 Markdown prompt는 렌더/가이드 전용이다.
