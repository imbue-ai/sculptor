"""Periodic diff refresh for terminal agents.

Sculptor cannot see what a terminal agent's shell does, so the task handler
polls cheap git state and refreshes the workspace diff only when it changes.
Encapsulated as a class so a file watcher can replace the polling without
touching the handler loop.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Callable

from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.services.git_repo_service.git_commands import run_git_command_local
from sculptor.services.git_repo_service.git_errors import GitCommandFailure

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
        concurrency_group: ConcurrencyGroup,
        interval_seconds: float = 3.0,
    ) -> None:
        self._working_directory = working_directory
        self._on_change = on_change
        self._concurrency_group = concurrency_group
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

    def _compute_fingerprint(self) -> str | None:
        """Hash of `git status --porcelain` + HEAD, or None on git failure.

        Runs git through ``run_git_command_local`` so each spawn goes via
        ``os.posix_spawn`` (cost independent of backend RSS, SCU-1624/SCU-1627) with
        the working directory folded into ``git -C``. ``check_output=False`` returns
        the exit code instead of raising on non-zero (e.g. a repo with no commits),
        and ``is_retry_safe=False`` keeps this 3s poll from retrying. A transient git
        failure (index lock, repo mid-rewrite, moved working dir) must not kill the
        agent loop — swallow and retry on the next interval.
        """
        try:
            status_rc, status_stdout, _status_stderr = run_git_command_local(
                self._concurrency_group,
                ["git", "status", "--porcelain"],
                cwd=self._working_directory,
                check_output=False,
                is_retry_safe=False,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            head_rc, head_stdout, _head_stderr = run_git_command_local(
                self._concurrency_group,
                ["git", "rev-parse", "HEAD"],
                cwd=self._working_directory,
                check_output=False,
                is_retry_safe=False,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
        except (OSError, ProcessError, GitCommandFailure) as e:
            logger.debug("Diff-refresh fingerprint failed in {}: {}", self._working_directory, e)
            return None
        if status_rc != 0 or head_rc != 0:
            logger.debug(
                "Diff-refresh git commands failed in {} (status rc={}, rev-parse rc={})",
                self._working_directory,
                status_rc,
                head_rc,
            )
            return None
        return hashlib.sha256((status_stdout + "\x00" + head_stdout).encode()).hexdigest()
