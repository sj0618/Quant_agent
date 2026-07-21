"""In-process fan-out of live analysis activity from the worker to SSE readers.

The analysis runs in a background worker thread while SSE responses are served on
the event loop, so events cross a thread boundary. A lock-guarded per-job buffer is
enough here and, unlike a queue handed to one consumer, it lets a client that
connects late (page reload, second tab) replay what it missed.

Buffers are bounded: a single analysis can emit thousands of text deltas, and the
job store is in memory.
"""

from __future__ import annotations

import threading
from typing import Any

# Measured against a live run: one analysis drives well over a dozen provider calls
# (research, signal and report each debate three ways) and emits a few thousand text
# deltas in total. Sized so a whole run fits - at 1_200 the research voices were
# already evicted before the report finished - while still bounding a job to a few MB.
DEFAULT_MAX_EVENTS_PER_JOB = 20_000


class JobEventBuffer:
    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS_PER_JOB) -> None:
        self._max_events = max_events
        self._lock = threading.Lock()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._dropped: dict[str, int] = {}
        self._closed: set[str] = set()

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            events = self._events.setdefault(job_id, [])
            events.append(event)
            overflow = len(events) - self._max_events
            if overflow > 0:
                del events[:overflow]
                self._dropped[job_id] = self._dropped.get(job_id, 0) + overflow

    def close(self, job_id: str) -> None:
        """Mark the analysis finished so readers can stop without polling the store."""

        with self._lock:
            self._closed.add(job_id)

    def read_since(self, job_id: str, cursor: int) -> tuple[list[dict[str, Any]], int, bool]:
        """Return events published after `cursor`, the new cursor, and whether it is done.

        The cursor counts events ever published for the job, so it stays correct
        across trimming: a reader that fell behind resumes at the oldest kept event
        instead of silently re-reading.
        """

        with self._lock:
            events = self._events.get(job_id, [])
            dropped = self._dropped.get(job_id, 0)
            closed = job_id in self._closed
            total = dropped + len(events)
            start = max(cursor - dropped, 0)
            return list(events[start:]), total, closed

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._events.pop(job_id, None)
            self._dropped.pop(job_id, None)
            self._closed.discard(job_id)
