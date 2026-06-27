import os
import shutil
from functools import cache
from pathlib import Path
from typing import Sequence

from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.retry_utils import log_before_sleep
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.foundation.subprocess_utils import ProcessTimeoutError
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.services.git_repo_service.git_errors import RetriableGitCommandFailure
from sculptor.utils.build import get_internal_folder


@cache
def _git_executable() -> str:
    """Path to the ``git`` binary, resolved once (absolute when git is on ``PATH``).

    ``os.posix_spawn`` does not search ``PATH``, so the spawn path needs an
    absolute executable. Falls back to bare ``git`` if it is somehow not on PATH
    (the spawn will then surface a clear error like Popen would).
    """
    return shutil.which("git") or "git"


def _should_retry_git_error(exception: BaseException) -> bool:
    return isinstance(exception, RetriableGitCommandFailure) and exception.is_transient


git_retry = retry(
    retry=retry_if_exception(_should_retry_git_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before_sleep=log_before_sleep,
)


@git_retry
def run_git_command_local(
    concurrency_group: ConcurrencyGroup,
    command: Sequence[str],
    cwd: str | Path | None = None,
    check_output: bool = True,
    timeout: float | None = None,
    is_retry_safe: bool = True,
    log_command: bool = True,
) -> tuple[int, str, str]:
    """Run a git command locally with automatic retry for transient errors."""
    new_env = os.environ.copy()
    new_env["GIT_SSH_COMMAND"] = str(get_internal_folder() / "ssh" / "ssh")

    # Spawn git via posix_spawn (cost independent of backend RSS, SCU-1624) rather
    # than fork()+exec(). That requires an absolute executable and cwd=None, so we
    # resolve git's path and fold any working directory into `git -C <dir>` (which
    # is equivalent for git's purposes). Only applies when the command really is
    # git; anything else keeps the original Popen behavior.
    argv = list(command)
    spawn_via_git = bool(argv) and argv[0] == "git"
    if spawn_via_git:
        argv[0] = _git_executable()
        if cwd is not None:
            argv = [argv[0], "-C", str(cwd), *argv[1:]]

    try:
        result = concurrency_group.run_process_to_completion(
            command=argv,
            cwd=None if spawn_via_git else (Path(cwd) if cwd else None),
            timeout=timeout,
            is_checked_after=True,
            env=new_env,
            log_command=log_command,
            prefer_posix_spawn=spawn_via_git,
        )
        assert result.returncode is not None, "returncode should never be None for completed process"
        return result.returncode, result.stdout, result.stderr
    except ProcessSetupError as e:
        # likely cwd is invalid, ie the repo has moved
        raise GitCommandFailure(
            f"Failed to start git command: {command}\nstdout: {e.stdout}\nstderr: {e.stderr}",
            command=command,
            returncode=e.returncode,
            stdout=e.stdout,
            stderr=e.stderr,
        ) from e
    except ProcessTimeoutError:
        # Re-raise timeouts unchanged so the broad ProcessError handler below does not wrap them:
        # ProcessTimeoutError always carries returncode=None, which would trip that handler's assert.
        raise
    except ProcessError as e:
        assert e.returncode is not None, f"Only ProcessTimeoutError should be throwable with a None returncode: {e}"
        if not check_output:
            return e.returncode, e.stdout, e.stderr
        Failure = RetriableGitCommandFailure if is_retry_safe else GitCommandFailure
        raise Failure(
            f"Error running git command: {command}\nstdout: {e.stdout}\nstderr: {e.stderr}",
            command=command,
            returncode=e.returncode,
            stdout=e.stdout,
            stderr=e.stderr,
        ) from e
