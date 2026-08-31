"""Re-run a freshness/lineage audit from an immutable server manifest."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quant_agent.data.freshness_lineage_audit import audit_freshness_lineage


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-run the freshness and lineage release audit")
    parser.add_argument("--input", type=Path, required=True, help="Immutable server manifest JSON")
    parser.add_argument("--output", type=Path, required=True, help="JSON audit report path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = _read_payload(args.input)
    report = audit_freshness_lineage(payload["samples"], payload["reviewer"])
    output = report.to_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report.passed else 1


def _read_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("samples"), list)
        or not isinstance(payload.get("reviewer"), dict)
    ):
        raise TypeError("input must contain a samples list and reviewer object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
