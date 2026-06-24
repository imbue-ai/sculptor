"""Shared helpers for CLI-based PR status checks.

Provides an error class, error classifier, and retry runner used by
pr_status.py (gh).
"""

import re
from pathlib import Path
from typing import Literal

from loguru import logger

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.foundation.subprocess_utils import ProcessSetupError

CliErrorCategory = Literal["not_authenticated", "no_access", "network_error", "rate_limited", "transient"]

# Errors we never retry immediately. The first three are permanent (a retry
# would fail the same way); ``rate_limited`` is temporary but a retry would
# only deepen the throttling, so the poller backs off via a host-level
# cooldown instead (see PrPollingService).
NON_RETRYABLE_CLI_ERRORS = frozenset({"not_authenticated", "no_access", "network_error", "rate_limited"})

_CLI_COMMAND_TIMEOUT = 30.0


class CliStatusError(Exception):
    """Raised when a CLI command (gh) fails with a classifiable error."""

    def __init__(self, category: CliErrorCategory, stderr: str) -> None:
        super().__init__(stderr)
        self.category = category


def classify_cli_error(stderr: str) -> CliErrorCategory:
    """Classify a CLI error based on its stderr output."""
    lower = stderr.lower()
    # Usage errors are checked first: an unknown ``--json`` field, an unknown
    # flag, or a malformed query makes gh print a help blurb listing valid
    # field names. That list contains tokens like "author" that would otherwise
    # trip the auth check below and mislabel a programming error as
    # "not authenticated". A usage error fails identically on retry and is
    # neither an auth, network, nor rate problem, so classify it as a
    # non-actionable transient failure rather than letting the help text decide.
    if any(keyword in lower for keyword in ("unknown json field", "unknown flag", "available fields:")):
        return "transient"
    # Rate limits are checked next: GitHub returns them as an HTTP 403 ("API
    # rate limit exceeded") and the secondary-limit message mentions neither
    # "auth" nor a bare status code, so without this they'd be misclassified
    # as "no_access" (permanent, shown to the user as an access problem) when
    # they are really a temporary throttle to wait out.
    if any(keyword in lower for keyword in ("rate limit", "ratelimit", "secondary rate")):
        return "rate_limited"
    # Match authentication failures without matching the literal field name
    # "author" (gh lists it in its --json help text): a bare "auth" token, the
    # "authentic"/"authoriz" stems (authentication, authorization, unauthorized),
    # an explicit 401, a token problem, or a "log in" prompt.
    if re.search(r"\bauth\b", lower) or any(
        keyword in lower
        for keyword in ("authentic", "authoriz", "not logged into", "not logged", "log in", "token", "401")
    ):
        return "not_authenticated"
    if any(keyword in lower for keyword in ("403", "forbidden", "access denied", "permission")):
        return "no_access"
    if any(keyword in lower for keyword in ("could not resolve", "no such host", "dns")):
        return "network_error"
    if (
        re.search(r"(?:HTTP[/ ]|status[: ]*)5\d{2}\b", stderr, re.IGNORECASE)
        or "timeout" in lower
        or "connection refused" in lower
    ):
        return "transient"
    return "transient"


def strip_remote_prefix(branch: str) -> str:
    """Strip a single remote prefix (e.g. "origin/", "local/") from a branch ref.

    Returns the branch unchanged if it has no slash. Only strips the first
    path segment, so nested branch names like "feature/foo" are preserved
    (e.g. "origin/feature/foo" → "feature/foo").
    """
    return branch.split("/", 1)[-1] if "/" in branch else branch


def run_cli_with_retry(cmd: list[str], working_dir: Path) -> FinishedProcess:
    """Run a CLI command with a single retry on transient failures only.

    Raises CliStatusError("transient", ...) if the working directory no longer
    exists (e.g. workspace was deleted while a poll was in-flight).
    """
    try:
        result = run_blocking(cmd, timeout=_CLI_COMMAND_TIMEOUT, is_checked=False, cwd=working_dir)
    except ProcessSetupError as e:
        raise CliStatusError("transient", f"CLI process failed to start: {e}") from e
    if result.returncode != 0:
        category = classify_cli_error(result.stderr)
        if category in NON_RETRYABLE_CLI_ERRORS:
            logger.debug("{} command failed ({}), not retrying: {}", cmd[0], category, result.stderr.strip())
            return result
        logger.debug("{} command failed ({}), retrying: {}", cmd[0], category, result.stderr.strip())
        try:
            result = run_blocking(cmd, timeout=_CLI_COMMAND_TIMEOUT, is_checked=False, cwd=working_dir)
        except ProcessSetupError as e:
            raise CliStatusError("transient", f"CLI process failed to start: {e}") from e
    return result
