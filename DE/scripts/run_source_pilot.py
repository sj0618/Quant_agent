"""Run the M1 OHLCV source pilot.

This script reads credentials only from the process environment. It does not
read .env files.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import PilotConfig  # noqa: E402
from quant_agent.data.pilot import OhlcvSourcePilotRunner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run KRX/KIS OHLCV source pilot.")
    parser.add_argument("--source", choices=["krx", "kis", "both"], default="both")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--krx-trade-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    base = PilotConfig.from_env()
    pilot_config = PilotConfig(
        sample_symbol=args.symbol or base.sample_symbol,
        start_date=date.fromisoformat(args.start_date) if args.start_date else base.start_date,
        end_date=date.fromisoformat(args.end_date) if args.end_date else base.end_date,
        krx_trade_date=date.fromisoformat(args.krx_trade_date) if args.krx_trade_date else base.krx_trade_date,
        min_symbol_coverage=base.min_symbol_coverage,
        max_price_issue_ratio=base.max_price_issue_ratio,
    )

    sources = ["krx", "kis"] if args.source == "both" else [args.source]
    report = OhlcvSourcePilotRunner(pilot_config).run(sources)
    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")

    return 0 if payload["primary_recommendation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
