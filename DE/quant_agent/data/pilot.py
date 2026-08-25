"""OHLCV source pilot runner for M1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quant_agent.data.config import KisConfig, KrxConfig, PilotConfig
from quant_agent.data.models import OhlcvBar, SourcePilotReport
from quant_agent.data.quality import summarize_ohlcv_quality
from quant_agent.data.sources.kis import KisOhlcvClient
from quant_agent.data.sources.krx import KrxOhlcvClient


@dataclass(frozen=True)
class PilotSuiteReport:
    primary_recommendation: str | None
    reports: list[SourcePilotReport]

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_recommendation": self.primary_recommendation,
            "reports": [report.to_dict() for report in self.reports],
        }


class OhlcvSourcePilotRunner:
    def __init__(
        self,
        pilot_config: PilotConfig,
        krx_config: KrxConfig | None = None,
        kis_config: KisConfig | None = None,
    ) -> None:
        self.pilot_config = pilot_config
        self.krx_config = krx_config or KrxConfig.from_env()
        self.kis_config = kis_config or KisConfig.from_env()

    def run(self, sources: Iterable[str]) -> PilotSuiteReport:
        requested = {source.lower() for source in sources}
        reports: list[SourcePilotReport] = []
        if "krx" in requested:
            reports.append(self._run_krx())
        if "kis" in requested:
            reports.append(self._run_kis())
        return PilotSuiteReport(
            primary_recommendation=recommend_primary_source(reports),
            reports=reports,
        )

    def _run_krx(self) -> SourcePilotReport:
        report = SourcePilotReport(source="KRX", configured=self.krx_config.is_configured, executed=False)
        if not self.krx_config.is_configured:
            report.warnings.append("KRX_API_KEY is not configured; KRX pilot was not executed.")
            return report
        try:
            bars = KrxOhlcvClient(self.krx_config).fetch_market_day(self.pilot_config.krx_trade_date)
            report.executed = True
            report.rows_observed = len(bars)
            _add_common_checks(report, bars, self.pilot_config.max_price_issue_ratio)
            report.add_check(
                "market breadth",
                len({bar.symbol for bar in bars}) >= 1000,
                f"observed {len({bar.symbol for bar in bars})} symbols for {self.pilot_config.krx_trade_date}",
            )
        except Exception as exc:  # noqa: BLE001 - pilot must report source failures
            report.errors.append(str(exc))
        return report

    def _run_kis(self) -> SourcePilotReport:
        report = SourcePilotReport(source="KIS", configured=self.kis_config.is_configured, executed=False)
        if not self.kis_config.is_configured:
            report.warnings.append("KIS_APP_KEY/KIS_APP_SECRET are not configured; KIS pilot was not executed.")
            return report
        try:
            bars = KisOhlcvClient(self.kis_config).fetch_daily_price(
                symbol=self.pilot_config.sample_symbol,
                start_date=self.pilot_config.start_date,
                end_date=self.pilot_config.end_date,
            )
            report.executed = True
            report.rows_observed = len(bars)
            _add_common_checks(report, bars, self.pilot_config.max_price_issue_ratio)
            report.add_check(
                "sample symbol daily history",
                len({bar.trade_date for bar in bars}) > 0,
                f"observed {len({bar.trade_date for bar in bars})} dates for {self.pilot_config.sample_symbol}",
            )
        except Exception as exc:  # noqa: BLE001 - pilot must report source failures
            report.errors.append(str(exc))
        return report


def _add_common_checks(report: SourcePilotReport, bars: list[OhlcvBar], max_price_issue_ratio: float) -> None:
    summary = summarize_ohlcv_quality(bars)
    issue_denominator = max(summary["rows"], 1)
    non_positive_ratio = summary["non_positive_price_rows"] / issue_denominator
    order_issue_ratio = summary["ohlc_order_issue_rows"] / issue_denominator
    report.add_check("rows present", summary["rows"] > 0, f"{summary['rows']} normalized OHLCV rows")
    report.add_check(
        "no duplicate symbol/date keys",
        summary["duplicate_key_rows"] == 0,
        f"{summary['duplicate_key_rows']} duplicate keys",
    )
    report.add_check(
        "positive prices detectable",
        summary["non_positive_price_rows"] < summary["rows"],
        f"{summary['non_positive_price_rows']} rows with non-positive OHLC price ({non_positive_ratio:.2%})",
    )
    report.add_check(
        "valid OHLC ordering detectable",
        summary["ohlc_order_issue_rows"] < summary["rows"],
        f"{summary['ohlc_order_issue_rows']} rows with OHLC ordering issues ({order_issue_ratio:.2%})",
    )
    if non_positive_ratio > max_price_issue_ratio:
        report.warnings.append(
            "Non-positive OHLC ratio exceeds pilot tolerance; classify halted/non-tradable rows before mart exposure."
        )
    elif summary["non_positive_price_rows"] > 0:
        report.warnings.append("Some rows have non-positive OHLC values and must be classified during DQ.")
    if order_issue_ratio > max_price_issue_ratio:
        report.warnings.append("OHLC ordering issue ratio exceeds pilot tolerance; affected rows must be excluded or flagged.")
    elif summary["ohlc_order_issue_rows"] > 0:
        report.warnings.append("Some rows have OHLC ordering issues and must be flagged during DQ.")


def recommend_primary_source(reports: list[SourcePilotReport]) -> str | None:
    passed = [report.source for report in reports if report.passed]
    if "KRX" in passed:
        return "KRX"
    if "KIS" in passed:
        return "KIS"
    return None
