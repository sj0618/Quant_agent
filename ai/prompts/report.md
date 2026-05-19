# Report Prompt

Render a concise investment-strategy report from validated JSON state.

Inputs:
- strategy summary
- backtest metrics
- risk-manager decision
- trace metadata (`trace_id`, `debug_ref`)

Rules:
- Treat JSON as canonical and Markdown as render-only.
- Do not expose raw `internal_payload` to frontend consumers.
- Always include `trace_id` and `debug_ref` in public responses.
- State whether the strategy is approved, needs review, or is rejected.
