"""Shared helpers for CLI-based PR status checks.

Provides an error class, error classifier, and the retrying gh runner used by
pr_status.py.
"""

import re
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from loguru import logger

from sculptor.services.workspace_service.vcs.data_types import VcsCommandResult
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli

CliErrorCategory = Literal[
    "cli_missing", "not_authenticated", "no_access", "network_error", "rate_limited", "transient"
]

# Runs `gh <arguments>` for one workspace; pr_status.py builds the arguments.
GhRunner = Callable[[Sequence[str]], VcsCommandResult]

# Errors we never retry immediately. The first three are permanent (a retry
# would fail the same way); ``rate_limited`` is temporary but a retry would
# only deepen the throttling, so the poller backs off via a host-level
# cooldown instead (see PrPollingService).
NON_RETRYABLE_CLI_ERRORS = frozenset({"not_authenticated", "no_access", "network_error", "rate_limited"})


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


def strip_remote_prefix(branch: str, remote_names: frozenset[str]) -> str:
    """The branch a target ref names on its remote: "origin/feature/foo" → "feature/foo".

    Only a first path segment that names one of `remote_names` is stripped, so a
    local branch such as "release/1.0" is returned unchanged.
    """
    remote_name, separator, remote_branch = branch.partition("/")
    if separator and remote_name in remote_names:
        return remote_branch
    return branch


def run_gh_with_retry(
    git_cli: GitCli, arguments: Sequence[str], cwd: Path, extra_env: Mapping[str, str]
) -> VcsCommandResult:
    """Run the configured gh in `cwd`, retrying once on a transient failure.

    `extra_env` is laid over the process environment. Raises
    CliStatusError("cli_missing", ...) when gh cannot be found, and
    CliStatusError("transient", ...) when it cannot start or times out (e.g. the
    workspace was deleted while a poll was in flight).
    """
    result = _run_gh(git_cli, arguments, cwd, extra_env)
    if result.returncode == 0:
        return result
    category = classify_cli_error(result.stderr)
    if category in NON_RETRYABLE_CLI_ERRORS:
        logger.debug("gh command failed ({}), not retrying: {}", category, result.stderr.strip())
        return result
    logger.debug("gh command failed ({}), retrying: {}", category, result.stderr.strip())
    return _run_gh(git_cli, arguments, cwd, extra_env)


def _run_gh(git_cli: GitCli, arguments: Sequence[str], cwd: Path, extra_env: Mapping[str, str]) -> VcsCommandResult:
    try:
        return git_cli.run_gh(arguments, cwd, is_read_only=True, is_checked=False, extra_env=extra_env)
    except VcsBinaryNotFoundError as e:
        raise CliStatusError("cli_missing", "gh CLI not found in PATH") from e
    except VcsCommandError as e:
        raise CliStatusError("transient", str(e)) from e
