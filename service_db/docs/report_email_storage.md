# Report and Email Storage

`014_create_report_email_tables.sql` supports the report pages and email
history routes currently represented by FE mocks.

## Route Mapping

| FE route | Storage |
| --- | --- |
| `/reports` | `app.strategy_report_summary_v` |
| `/reports/strategies/:strategyId` | `app.strategy_report_profile`, `app.strategy_email_report` |
| `/reports/:reportId` | `app.strategy_email_report`, `app.strategy_email_report_news`, `app.strategy_email_report_candidate` |
| `/me` email history | `app.email_digest_history_v` |

## Tables

- `app.strategy_report_profile`: display profile for one strategy report.
- `app.strategy_email_report`: one generated report for one strategy/date.
- `app.strategy_email_report_news`: ranked news items in a report.
- `app.strategy_email_report_candidate`: ticker candidates in a report.
- `app.email_digest_subscription`: user-selected strategies for daily digest email.
- `app.email_delivery_history`: per-recipient delivery audit trail.

`app.email_digest_subscription` enforces a maximum of three strategies per user
with a trigger, matching the FE daily digest selection rule.

`app.strategy_email_report.backtest_run_id` and `ai_report_id` are nullable
source references. They link an email report to the backtest run and AI report
that produced it when those records exist. `performance_jsonb` remains the
immutable display snapshot used to reproduce the delivered report.
