# L2 Signal Policy Evidence

L2 evidence converts a validated strategy specification and market snapshot into user-visible actions. Signals are BUY, SELL, HOLD, or WATCH.

Every ticker matching the requested conditions is evaluated directly by the technical entry and exit rules. Do not rank, truncate, or exclude matches using a research score.

Signal output must include trace_id and debug_ref for auditability, but raw internal_payload stays internal. Reasons should mention the matched entry or exit rule and the candidate snapshot id when research filtering was used.
