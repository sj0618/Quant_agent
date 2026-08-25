"""What earlier analyses of the same strategy learned, carried into the next one.

Every run started from nothing: the same strategy analysed a hundred times produced a
hundred identical first attempts, and a screen that had already proved too tight was
written the same way again. This keeps a small, bounded record of what each run did and
how it turned out, so the next one can start from it.

The store is deliberately modest - a per-strategy ring buffer of outcomes, not a
learning system. It answers "has this been tried, and what happened" and nothing more.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

AI_MEMORY_PATH_ENV = "AI_MEMORY_PATH"
DEFAULT_MEMORY_FILENAME = "analysis_memory.json"
# Enough to see a pattern across recent attempts without growing without bound.
MAX_ENTRIES_PER_STRATEGY = 5
MAX_STRATEGIES = 200


class AnalysisMemory:
    """Recent outcomes per strategy, persisted as a single JSON document."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AnalysisMemory":
        env = environ if environ is not None else os.environ
        raw = (env.get(AI_MEMORY_PATH_ENV) or "").strip()
        return cls(Path(raw) if raw else None)

    @property
    def enabled(self) -> bool:
        """Off unless a path is configured, so tests and fixture runs stay stateless."""

        return self._path is not None

    def recall(self, strategy_id: str) -> list[dict[str, Any]]:
        if not self.enabled or not strategy_id:
            return []
        return self._read().get(strategy_id, [])

    def record(
        self,
        strategy_id: str,
        *,
        query: str,
        outcome: str,
        candidate_count: int,
        metrics: Mapping[str, Any] | None = None,
        relaxation_rounds: int = 0,
        unmet_requirements: list[str] | None = None,
        note: str | None = None,
    ) -> None:
        if not self.enabled or not strategy_id:
            return
        entry = {
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "query": query,
            "outcome": outcome,
            "candidate_count": candidate_count,
            "metrics": dict(metrics or {}),
            "relaxation_rounds": relaxation_rounds,
            "unmet_requirements": list(unmet_requirements or []),
            "note": note,
        }
        with self._lock:
            store = self._read()
            entries = [*store.get(strategy_id, []), entry][-MAX_ENTRIES_PER_STRATEGY:]
            store[strategy_id] = entries
            if len(store) > MAX_STRATEGIES:
                # Drop the least recently touched strategies rather than growing forever.
                ordered = sorted(
                    store.items(),
                    key=lambda item: item[1][-1].get("recorded_at", ""),
                    reverse=True,
                )
                store = dict(ordered[:MAX_STRATEGIES])
            self._write(store)

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Memory is an optimisation; a corrupt file must not fail an analysis.
            _logger.warning("analysis memory unreadable; continuing without it", exc_info=True)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _write(self, store: Mapping[str, Any]) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            _logger.warning("could not persist analysis memory", exc_info=True)


def summarize_recall(entries: list[dict[str, Any]]) -> str:
    """Render past outcomes as a short briefing for a prompt."""

    if not entries:
        return ""
    lines = []
    for entry in entries[-MAX_ENTRIES_PER_STRATEGY:]:
        metrics = entry.get("metrics") or {}
        performance = ", ".join(f"{key}={value}" for key, value in list(metrics.items())[:3])
        detail = [f"{entry.get('recorded_at', '?')}: {entry.get('outcome')}"]
        detail.append(f"후보 {entry.get('candidate_count', 0)}개")
        if entry.get("relaxation_rounds"):
            detail.append(f"조건 완화 {entry['relaxation_rounds']}회 필요")
        if performance:
            detail.append(performance)
        if entry.get("unmet_requirements"):
            detail.append(f"검증 불가: {', '.join(entry['unmet_requirements'][:2])}")
        lines.append(" · ".join(detail))
    return "\n".join(lines)
