# QuantAgent AI API Contract

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

## Envelope

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

`internal_payload` is never included in the normal FE envelope. QA and logging systems
resolve it through `debug_ref`.

## Dual Output

| Payload | Audience | Fields |
|---|---|---|
| `internal_payload` | QA/logging | `trace_id`, `node_outputs`, `retrieval_hits`, `llm_prompts`, `validation`, `backtest_artifacts`, `risk_events` |
| `user_payload` | FE | `headline`, `message`, `next_actions`; optional candidate cards/report |

## StrategySpec

Canonical fields: `strategy_id`, `name`, `universe`, `market`, `timeframe`,
`entry_conditions`, `exit_conditions`, `indicators`, `risk_constraints`,
`assumptions`, `source_refs`, `confidence`.

## L4 Evidence

Required fields: `publisher`, `published_at`, `retrieved_at`, `freshness_days`,
`dedupe_group`, `access_status`, `quality_note`.
