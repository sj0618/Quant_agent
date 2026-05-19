# L2 Signal Policy Evidence

L2 evidence converts a validated strategy specification and market snapshot into user-visible actions. Signals are BUY, SELL, HOLD, WATCH, or FILTERED_OUT.

Candidate filters are applied before technical entry rules. A ticker not present in the research candidate snapshot must be FILTERED_OUT even when RSI, moving average, MACD, or breakout conditions match.

Signal output must include trace_id and debug_ref for auditability, but raw internal_payload stays internal. Reasons should mention the matched entry or exit rule and the candidate snapshot id when research filtering was used.
