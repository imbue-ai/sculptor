import os
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

    try:
        result = concurrency_group.run_process_to_completion(
            command=command,
            cwd=Path(cwd) if cwd else None,
            timeout=timeout,
            is_checked_after=True,
            env=new_env,
            log_command=log_command,
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
        # Should not be possible given we passed no timeout to run_process_to_completion
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
