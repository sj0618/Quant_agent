from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_graph.on_demand_retirement import validate_on_demand_retirement_inventory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the ten-item on-demand analysis retirement inventory Markdown file."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        required=True,
        help="Path to the on-demand retirement inventory Markdown file.",
    )
    args = parser.parse_args()

    try:
        markdown = args.inventory.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2

    result = validate_on_demand_retirement_inventory(markdown)
    print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
