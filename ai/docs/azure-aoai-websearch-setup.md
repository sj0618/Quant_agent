# Azure OpenAI Web Search Tool 설정 안내

작성일: 2026-07-06
대상: 인프라/Azure 리소스를 관리하는 담당자. 이 문서는 "시황 및 경제 기사" 섹션(`MarketBrief`, `ai/ai_graph/llm/role_calls.py`의 `generate_market_brief`)이 AOAI Web search tool로 실시간 뉴스를 가져오기 위해 Azure 쪽에서 확인/구성해야 하는 항목만 정리한다. 코드 쪽 구현(요청 바디에 `tools` 추가, 실패 시 폴백)은 이미 완료됨.

## 1. 전제 확인 (Azure Portal / AOAI 리소스)

- [ ] 사용 중인 AOAI 리소스가 **Responses API**를 지원하는 리전/배포인지 확인 (Chat Completions API가 아니라 Responses API 엔드포인트를 쓴다 — 코드가 이미 `.../responses` 형태의 URL을 호출함).
- [ ] 해당 배포 모델이 **web search(내장 tool) 프리뷰**를 지원하는지 확인. 지원 모델/리전은 Azure 쪽에서 계속 업데이트되므로 Azure OpenAI 공식 문서의 "Built-in tools" 또는 "Web search" 섹션에서 최신 지원 리스트를 확인할 것 — **이 문서 작성 시점 기준으로 정확한 tool type 문자열이 확정되어 있지 않으므로 반드시 재확인 필요**.
- [ ] 프리뷰 기능이면 별도 신청/등록(allowlist) 절차가 있는지 확인.
- [ ] 리소스의 아웃바운드 네트워크 정책이 web search 기능(Bing 기반일 가능성이 높음)의 외부 호출을 막지 않는지 확인 — VNet/방화벽으로 제한된 환경이면 별도 예외 처리가 필요할 수 있음.

## 2. 코드가 기대하는 동작

`ai/ai_graph/llm/aoai.py`의 `AOAIResponsesClient`는 `LLMJsonRequest.enable_web_search=True`일 때 Responses API 요청 바디에 다음을 추가한다:

```json
{
  "tools": [{ "type": "<web_search_tool_type>" }]
}
```

- `<web_search_tool_type>`은 하드코딩되어 있지 않고 **환경변수로 주입**된다. Azure 쪽에서 실제 tool type 문자열이 확정되면(예: `web_search_preview` 등 프리뷰명이 바뀔 수 있음) 코드 변경 없이 환경변수 값만 바꾸면 된다.
- 응답 파싱(`_extract_nested_output_text`)은 `output` 배열에서 텍스트가 있는 항목만 뽑아내므로, 응답에 `web_search_call` 같은 도구 호출 항목이 섞여 있어도 무시하고 최종 텍스트만 사용한다 — 별도 파싱 로직 추가가 필요 없다.
- 웹서치 호출이 실패/타임아웃/미설정이면 `generate_market_brief`가 자동으로 빈 `items` + `fallback_reasons=["websearch_unavailable", ...]`로 안전하게 대체하므로, 이메일의 다른 섹션(전략 비교표, AI 코멘트 등)은 정상 발송된다.

## 3. 필요한 환경변수 (이름만 — 값은 배포 환경의 시크릿 매니저에 설정)

전역 AOAI 설정 (`ai/ai_graph/llm/factory.py`):

| 환경변수 | 용도 |
|---|---|
| `AI_LLM_PROVIDER` | `aoai`로 설정해야 실제 AOAI 호출 (기본값은 `mock`) |
| `AI_AOAI_RESPONSES_URL` | AOAI Responses API 엔드포인트 URL |
| `AI_AOAI_API_KEY` | AOAI API 키 |
| `AI_AOAI_MODEL` | 배포된 모델/deployment 이름 |
| `AI_AOAI_TIMEOUT_SECONDS` | (선택) 기본 30초 |
| `AI_AOAI_MAX_RETRIES` | (선택) 기본 2회 |
| `AI_AOAI_RETRY_BACKOFF_SECONDS` | (선택) 기본 0.25초 |
| `AI_AOAI_WEB_SEARCH_TOOL_TYPE` | (신규) Responses API에 넘길 web search tool의 `type` 문자열. 기본값 `web_search_preview` — Azure 쪽 확정 문자열로 교체 |

역할(role)별 오버라이드도 가능 (`_role_env_name` 규칙: `AI_LLM_<ROLE>_<SUFFIX>`). 시황 브리핑 호출은 역할명 `DIGEST_MARKET_BRIEF`로 실행되므로, 이 역할에만 다른 배포/모델을 쓰고 싶다면:

| 환경변수 | 용도 |
|---|---|
| `AI_LLM_DIGEST_MARKET_BRIEF_RESPONSES_URL` | 이 역할 전용 엔드포인트 (미설정 시 전역 값 사용) |
| `AI_LLM_DIGEST_MARKET_BRIEF_API_KEY` | 이 역할 전용 API 키 |
| `AI_LLM_DIGEST_MARKET_BRIEF_MODEL` | 이 역할 전용 모델 |
| `AI_LLM_DIGEST_MARKET_BRIEF_WEB_SEARCH_TOOL_TYPE` | 이 역할 전용 tool type |

다른 다이제스트 관련 역할(`DIGEST_STRATEGY_CARD`, `DIGEST_JUDGE`)은 web search가 필요 없으므로 위 오버라이드 대상이 아니다.

## 4. 비용/레이트리밋 주의

- 매일 08:00에 구독 유저 수만큼 `generate_market_brief` 호출이 몰릴 수 있다 (유저별 1회, 유저가 많아지면 배치/큐잉 고려). Azure 쪽 TPM/RPM 쿼터를 다이제스트 발송 규모에 맞춰 사전 확인할 것.
- Web search tool은 일반 텍스트 생성보다 과금이 더 붙을 수 있으므로(도구 호출 자체에 비용이 발생하는 모델/정책이 있음) 예산 담당자와 사전 확인 필요.
- `AI_AOAI_MAX_RETRIES`/`AI_AOAI_RETRY_BACKOFF_SECONDS`가 재시도 폭주로 쿼터를 소진하지 않도록 배치 발송 규모에 맞춰 보수적으로 설정.

## 5. 검증 방법

1. `AI_LLM_PROVIDER=aoai`와 위 환경변수를 실제 값으로 설정한 환경에서 `ai_graph.llm.role_calls.generate_market_brief`를 직접 호출해 `MarketBrief.items`가 채워지는지, `fallback_reasons`가 비어 있는지 확인.
2. 의도적으로 `AI_AOAI_API_KEY`를 잘못된 값으로 바꿔 실패 케이스에서 `fallback_reasons`에 에러가 기록되고 나머지 다이제스트 섹션은 정상 생성되는지 확인 (`ai/tests/test_daily_digest.py`의 mock-모드 폴백 테스트가 이 동작의 기준선).
