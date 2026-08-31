"""Shared models for data ingestion and source pilots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class OhlcvBar:
    source: str
    symbol: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawSourcePayload:
    source: str
    endpoint_key: str
    request_date: date | None
    request: dict[str, Any]
    payload: dict[str, Any]


@dataclass(frozen=True)
class AnalystReportSummary:
    report_date: date
    ticker: str
    company_name: str
    summary: str
    opinion: str | None
    target_price: Decimal | None
    close_price: Decimal | None
    institution: str
    author: str
    source_payload_hash: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataQualityIssue:
    dataset: str
    severity: str
    rule_code: str
    message: str
    symbol: str | None = None
    trade_date: date | None = None


@dataclass(frozen=True)
class ApiRequestLog:
    source_id: str
    endpoint_key: str
    request: dict[str, Any]
    success: bool
    status_code: int | None
    elapsed_ms: int
    retry_count: int
    response: dict[str, Any] | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class LineageEvent:
    target_table: str
    target_key: str
    source_table: str
    source_key: str
    transform_version: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionRun:
    run_id: UUID
    dag_id: str
    task_id: str
    source_id: str
    started_at: datetime
    status: str
    params: dict[str, Any]
    ended_at: datetime | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class OhlcvIngestionResult:
    run_id: UUID
    source: str
    start_date: date
    end_date: date
    rows_fetched: int
    rows_written: int
    raw_payloads_written: int
    quality_issues: list[DataQualityIssue] = field(default_factory=list)
    release_manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PilotCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class SourcePilotReport:
    source: str
    configured: bool
    executed: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rows_observed: int = 0
    checks: list[PilotCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.configured and self.executed and bool(self.checks) and all(check.passed for check in self.checks)

    def add_check(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(PilotCheck(name=name, passed=passed, detail=detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "configured": self.configured,
            "executed": self.executed,
            "checked_at": self.checked_at.isoformat(),
            "rows_observed": self.rows_observed,
            "passed": self.passed,
            "checks": [check.__dict__ for check in self.checks],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
