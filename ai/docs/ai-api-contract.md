# QuantAgent AI API Contract

## Swagger

The local FastAPI adapter exposes Swagger UI at `/docs` and OpenAPI JSON at
`/openapi.json`.

## API Status

`GET /health`

```json
{
  "status": "ok",
  "schema_version": "ai-mvp.v1"
}
```

`GET /api-status`

Returns the currently exposed local API surface, including `/analysis-jobs`.
The response includes data-source configuration status without exposing the
actual DSN value.

## Browser FE Integration

Set `AI_CORS_ALLOW_ORIGINS` on the AI API process to a comma-separated list of
allowed FE origins. The FastAPI adapter enables credentialed CORS only when this
environment variable is present. The FE points to this API with
`VITE_AI_API_BASE_URL` and calls `/analysis-jobs` directly.

## Data Sources

When `AI_DATABASE_DSN` is set, the AI pipeline loads production data from the
common PostgreSQL/TimescaleDB objects below:

| Pipeline input | DB object | Status in DE inventory |
|---|---|---|
| Backtest OHLCV/TA rows | `mart.kis_adjusted_feature_frame_asof` | 10-year KIS adjusted feature frame available |
| Tradable universe lookup | `meta.view_common_stock_universe` | common-stock helper view available |
| L4 analyst evidence | `raw.analyst_report_summary` | 10-year SEIBro raw rows available |

`mart.bok_macro_asof`, `mart.dart_financial_asof`, and `mart.seibro_universe_asof`
are not treated as production-grade AI inputs yet because the inventory marks
them as pilot-only or empty.

## LLM Provider

Default provider is `mock`. AOAI is enabled only when all required env values are
set:

| Env | Purpose |
|---|---|
| `AI_LLM_PROVIDER=mock|aoai` | provider selector |
| `AI_AOAI_RESPONSES_URL` | Azure OpenAI Responses preview REST URL |
| `AI_AOAI_API_KEY` | secret API key; never store in code, fixtures, snapshots, or logs |
| `AI_AOAI_MODEL` | deployment or model name |

The current implementation intentionally uses a thin `httpx` client because the
configured endpoint is the Azure preview REST path:
`/openai/responses?api-version=2025-04-01-preview`. If the deployment later
moves to an `/openai/v1/responses`-compatible surface, this client can be
replaced by an SDK-backed implementation behind the same `LLMClient` interface.

## Analysis Job

`POST /analysis-jobs`

```json
{
  "query": "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
}
```

`GET /analysis-jobs/{job_id}`

| Field | Values |
|---|---|
| `stage` | `interpreting`, `code_generation`, `backtest`, `debate`, `finalizing` |
| `stage_status` | `queued`, `running`, `succeeded`, `failed` |

## Strategy Description

`POST /api/strategies/descriptions`

```json
{
  "strategies": [
    {
      "strategy_id": "semiconductor-momentum",
      "name": "반도체 모멘텀 + 기관 매수",
      "universe": "KOSPI200 · 반도체",
      "timeframe": "daily",
      "entry_summary": "20일 상대강도 상위권이면서 외국인 순매수가 동반된 종목만 진입 후보로 올립니다.",
      "exit_summary": "상대강도 둔화 또는 외국인 수급 반전이 확인되면 비중을 축소합니다.",
      "risk_summary": "실적 발표와 환율 급등 구간에서는 신규 비중 확대를 늦춥니다.",
      "tags": ["모멘텀", "외국인 수급"]
    }
  ]
}
```

Response:

```json
{
  "items": [
    {
      "strategy_id": "semiconductor-momentum",
      "description": "반도체 업종 내 상대강도와 외국인 순매수 흐름이 동시에 강화되는 종목에 집중하는 모멘텀 전략입니다.",
      "fallback_reasons": []
    }
  ]
}
```

## Envelope

FE/BE public contract is frozen by `tests/contracts/test_api_envelope_contract.py`.

### `AnalysisJob`

| Field | FE-safe | Notes |
|---|---|---|
| `job_id` | yes | polling key |
| `trace_id` | yes | cross-service correlation id |
| `query` | yes | original user strategy text |
| `created_at` | yes | job creation time |
| `updated_at` | yes | latest job update time; completed jobs use this as completion time |
| `stages` | yes | polling stage list |
| `result` | yes | `APIEnvelope` or null before completion |

### `StageProgress`

| Field | Values |
|---|---|
| `stage` | `interpreting`, `code_generation`, `backtest`, `debate`, `finalizing` |
| `status` | `queued`, `running`, `succeeded`, `failed` |
| `updated_at` | ISO timestamp |
| `message` | optional human-readable stage detail |

### `APIEnvelope`

```json
{
  "status": "ready | need_clarification | rejected | failed",
  "trace_id": "trace id",
  "schema_version": "ai-mvp.v1",
  "user_payload": {},
  "strategy_spec": {},
  "debug_ref": "debug ref",
  "retryable": true
}
```

| Field | FE-safe | Notes |
|---|---|---|
| `status` | yes | final analysis status |
| `trace_id` | yes | response correlation id |
| `schema_version` | yes | currently `ai-mvp.v1` |
| `user_payload` | yes | FE-facing headline/message/actions/cards/report |
| `strategy_spec` | yes | validated StrategySpec when available |
| `debug_ref` | limited | opaque support/debug reference only; FE must not dereference directly |
| `retryable` | yes | whether user retry/refinement is appropriate |

`internal_payload`, raw LLM prompts, raw node outputs, fallback reasons, and
validation traces are never included in the normal FE envelope. QA/logging/BE
systems resolve them through `debug_ref`.

## Dual Output

| Payload | Audience | Fields |
|---|---|---|
| `internal_payload` | QA/logging | `trace_id`, `node_outputs`, `retrieval_hits`, `llm_prompts`, `validation`, `backtest_artifacts`, `risk_events` |
| `user_payload` | FE | `headline`, `message`, `next_actions`; optional candidate cards/report/performance and clarification cards |

## Public Report Fields

| Field | FE-safe | Storage target candidate |
|---|---|---|
| `user_payload.report.web_projection` | yes | `reports.content_md` / `reports.content_html` |
| `user_payload.report.email_projection` | yes | `reports.content_md` / `reports.content_html` |
| `strategy_spec` | yes | `strategies.spec_json` |
| `query` | yes | `strategies.description_nl` |
| `result.user_payload.candidate_cards` | yes | `agentic_search_cache` or candidate analysis cache |
| `result.user_payload.message` | yes | `llm_analyses` summary |
| `result.user_payload.question/options/recommended` | yes | FE clarification card state |
| `result.user_payload.report.risk_adjustments` | yes | `trade_signals.rationale_md` or risk audit log |
| `result.user_payload.performance` | yes | `backtest_runs`/`backtest_metrics` |
| `result.debug_ref` | limited | internal trace key for `llm_analyses`/debug records |

Future DB writers should map `backtest_artifacts` from internal payload and the
public `performance` summary to `backtest_runs`/`backtest_metrics`, and final
signal/rationale to `trade_signals`. This AI task does not create or mutate
those DB tables.

## StrategySpec

Canonical fields: `strategy_id`, `name`, `universe`, `market`, `timeframe`,
`entry_conditions`, `exit_conditions`, `indicators`, `risk_constraints`,
`assumptions`, `source_refs`, `confidence`.

## L4 Evidence

Required fields: `publisher`, `published_at`, `retrieved_at`, `freshness_days`,
`dedupe_group`, `access_status`, `quality_note`.
