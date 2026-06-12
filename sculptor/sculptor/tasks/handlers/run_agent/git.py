from typing import Mapping
from typing import Sequence

from imbue_core.secrets_utils import Secret
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.git_repo_service.git_commands import git_retry
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.services.git_repo_service.git_errors import RetriableGitCommandFailure


# TODO(SCU-138): Move run_git_command_in_environment to git_repo_service alongside run_git_command_local.
@git_retry
def run_git_command_in_environment(
    environment: AgentExecutionEnvironment,
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
