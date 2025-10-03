import os
from pathlib import Path
from typing import Mapping
from typing import Sequence

from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from imbue_core.processes.local_process import run_blocking
from imbue_core.retry_utils import log_before_sleep
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.tasks.handlers.run_agent.errors import GitCommandFailure
from sculptor.tasks.handlers.run_agent.errors import RetriableGitCommandFailure
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.secret import Secret


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
def run_git_command_in_environment(
    environment: Environment,
    command: Sequence[str],
    secrets: Mapping[str, str | Secret] | None = None,
    cwd: str | None = None,
    check_output: bool = True,
    timeout: float | None = None,
    is_retry_safe: bool = True,
) -> tuple[int, str, str]:
    """Run a git command in an environment with automatic retry for transient errors."""
    if not secrets:
        secrets = {}

    process = environment.run_process_in_background(command, secrets, cwd)
    stdout, stderr = process.wait_and_read(timeout=timeout)
    returncode = process.returncode
    assert returncode is not None

    if check_output and returncode != 0:
        # TODO: one thing to consider is that for docker environments, the returncode might be non-zero because of docker reasons
        # and not because of git reasons. we should figure out a way to handle this but probably in DockerRunningProcess/Environment and not here.
        if is_retry_safe:
            raise RetriableGitCommandFailure(
                f"Error running git command: {command}\nstdout: {stdout}\nstderr: {stderr}",
                command=command,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )
        else:
            raise GitCommandFailure(
                f"Error running git command: {command}\nstdout: {stdout}\nstderr: {stderr}",
                command=command,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

    return returncode, stdout, stderr


@git_retry
def run_git_command_local(
    command: Sequence[str],
    cwd: str | Path | None = None,
    check_output: bool = True,
    timeout: float | None = None,
    is_retry_safe: bool = True,
) -> tuple[int, str, str]:
    """Run a git command locally with automatic retry for transient errors."""
    new_env = os.environ.copy()
    new_env["GIT_SSH_COMMAND"] = str(get_sculptor_folder() / "ssh" / "ssh")

    result = run_blocking(
        command=command,
        cwd=Path(cwd) if cwd else None,
        timeout=timeout,
        is_checked=False,
        is_output_traced=False,
        env=new_env,
    )

    if check_output and result.returncode != 0:
        if is_retry_safe:
            raise RetriableGitCommandFailure(
                f"Error running git command: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        else:
            raise GitCommandFailure(
                f"Error running git command: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

    return result.returncode, result.stdout, result.stderr
