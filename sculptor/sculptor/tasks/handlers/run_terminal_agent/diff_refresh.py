"""Periodic diff refresh for terminal agents.

Sculptor cannot see what a terminal agent's shell does, so the task handler
polls cheap git state and refreshes the workspace diff only when it changes
(REQ-TERM-3). Encapsulated as a class so a file watcher can replace the
polling without touching the handler loop.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Callable

from loguru import logger

from imbue_core.processes.local_process import run_blocking
from imbue_core.subprocess_utils import ProcessError

_GIT_TIMEOUT_SECONDS = 5.0


class PeriodicDiffRefresher:
    """Calls ``on_change`` when the working tree's git fingerprint changes.

    ``tick()`` is cheap to call often (the handler calls it every poll step);
    it self-limits to one fingerprint check per ``interval_seconds``. The
    first successful check establishes the baseline without firing — the
    handler already marks the diff stale once at startup.
    """

    def __init__(
        self,
        working_directory: Path,
        on_change: Callable[[], None],
        interval_seconds: float = 3.0,
    ) -> None:
        self._working_directory = working_directory
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

    def force(self) -> None:
        """Fire ``on_change`` now and rebase the fingerprint on current state."""
        self._last_fingerprint = self._compute_fingerprint()
        self._last_check_at = time.monotonic()
        self._on_change()

    def _compute_fingerprint(self) -> str | None:
        """Hash of `git status --porcelain` + HEAD, or None on git failure.

        A transient git failure (index lock, repo mid-rewrite) must not kill
        the agent loop — swallow and retry on the next interval.
        """
        try:
            status = run_blocking(
                command=["git", "status", "--porcelain"],
                cwd=self._working_directory,
                timeout=_GIT_TIMEOUT_SECONDS,
                is_checked=False,
            )
            head = run_blocking(
                command=["git", "rev-parse", "HEAD"],
                cwd=self._working_directory,
                timeout=_GIT_TIMEOUT_SECONDS,
                is_checked=False,
            )
        except (OSError, ProcessError) as e:
            logger.debug("Diff-refresh fingerprint failed in {}: {}", self._working_directory, e)
            return None
        if status.returncode != 0 or head.returncode != 0 or status.is_timed_out or head.is_timed_out:
            logger.debug(
                "Diff-refresh git commands failed in {} (status rc={}, rev-parse rc={})",
                self._working_directory,
                status.returncode,
                head.returncode,
            )
            return None
        return hashlib.sha256((status.stdout + "\x00" + head.stdout).encode()).hexdigest()
