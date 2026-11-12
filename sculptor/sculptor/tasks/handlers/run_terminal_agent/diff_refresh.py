"""Periodic diff refresh for terminal agents.

Sculptor cannot see what a terminal agent's shell does, so the task handler
polls a cheap fingerprint of the checkout and refreshes the workspace diff only
when it changes. Encapsulated as a class so a file watcher can replace the
polling without touching the handler loop.
"""

from __future__ import annotations

import time
from typing import Callable


class PeriodicDiffRefresher:
    """Calls ``on_change`` when the checkout's change fingerprint changes.

    ``tick()`` is cheap to call often (the handler calls it every poll step);
    it self-limits to one fingerprint check per ``interval_seconds``. The
    first successful check establishes the baseline without firing — the
    handler already marks the diff stale once at startup. A check that returns
    None is skipped, so a transient failure just waits for the next interval.
    """

    def __init__(
        self,
        compute_fingerprint: Callable[[], str | None],
        on_change: Callable[[], None],
        interval_seconds: float = 3.0,
    ) -> None:
        self._compute_fingerprint = compute_fingerprint
        self._on_change = on_change
        self._interval_seconds = interval_seconds
        self._last_check_at: float | None = None
        self._last_fingerprint: str | None = None

    def tick(self) -> None:
        now = time.monotonic()
        if self._last_check_at is not None and now - self._last_check_at < self._interval_seconds:
            return
        self._last_check_at = now

        fingerprint = self._compute_fingerprint()
        if fingerprint is None:
            return
        if self._last_fingerprint is None:
            self._last_fingerprint = fingerprint
            return
        if fingerprint != self._last_fingerprint:
            self._last_fingerprint = fingerprint
            self._on_change()
