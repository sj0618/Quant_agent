from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_graph.control_board import validate_control_board


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a QuantAgent control board Markdown file.")
    parser.add_argument("--board", type=Path, required=True, help="Path to the control board Markdown file.")
    args = parser.parse_args()

    try:
        markdown = args.board.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2

    result = validate_control_board(markdown)
    print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
