"""How the VCS seam runs git and gh.

Binaries come from a resolver callable: Sculptor's own calls pass the
dependency service's `resolve_binary_path`, so `dependency_paths.git` and
`dependency_paths.gh` are honoured, and agent-side calls pass their execution
environment's `get_tool_binary_path`. Agent-side calls also pass the
environment's `get_project_env_overrides`, so git sees the project's `.env`
variables as the agent's own processes do. Every failure, including a
timeout, is a `VcsCommandError`. Only read-only commands are retried.
Operands (refs, revisions, destinations) go after `--end-of-options` and paths
after `--`, so a value starting with `-` is never parsed as an option.
"""

import os
from pathlib import Path
from typing import Callable
from typing import Mapping
from typing import Sequence

from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.retry_utils import log_before_sleep
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.workspace_service.vcs.data_types import VcsCommandResult
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.errors import VcsCommandTimeoutError

DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS = 30.0

# Both `DependencyManagementService.resolve_binary_path` and
# `AgentExecutionEnvironment.get_tool_binary_path` have this shape.
BinaryResolver = Callable[[Dependency], str | None]

# Variables laid over the process environment for every command, read again as
# each command starts so that edits to their source reach later commands.
# Values may stay wrapped in `Secret` until then.
EnvOverridesReader = Callable[[], Mapping[str, str | Secret]]


def _no_env_overrides() -> Mapping[str, str | Secret]:
    return {}


_retry_read_only_command = retry(
    retry=retry_if_exception_type(VcsCommandExitError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before_sleep=log_before_sleep,
)


def find_jj_workspace_root(directory: Path) -> Path | None:
    """The jj workspace containing `directory`, or None if git owns it or neither does.

    Walks up as git's own repository discovery does, stopping at the first
    directory holding `.git` or `.jj`. Only a `.jj` with no `.git` beside it is a
    jj workspace: a colocated repository has both, and git works there.
    """
    for candidate in (directory, *directory.parents):
        has_git = (candidate / ".git").exists()
        has_jj = (candidate / ".jj").exists()
        if has_git:
            return None
        if has_jj:
            return candidate
    return None


class GitCli:
    """Runs git and gh with the user's configured binaries."""

    def __init__(
        self,
        concurrency_group: ConcurrencyGroup,
        resolve_binary: BinaryResolver,
        read_env_overrides: EnvOverridesReader = _no_env_overrides,
    ) -> None:
        self._concurrency_group = concurrency_group
        self._resolve_binary_path = resolve_binary
        self._read_env_overrides = read_env_overrides

    def run_git(
        self,
        options: Sequence[str],
        cwd: Path,
        *,
        is_read_only: bool,
        operands: Sequence[str] = (),
        paths: Sequence[str] = (),
        is_checked: bool = True,
        timeout: float | None = DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS,
        extra_env: Mapping[str, str] | None = None,
    ) -> VcsCommandResult:
        """Run `git <options> --end-of-options <operands> -- <paths>` in `cwd`.

        Raises `GitCommandInJjWorkspaceError` when `cwd` is inside a jj workspace.
        With `is_checked`, a non-zero exit raises `VcsCommandExitError`; without
        it, the result is returned whatever its exit code. `extra_env` is laid
        over the process environment and the env overrides, for callers that
        steer git with variables such as `GIT_INDEX_FILE`.
        """
        jj_workspace_root = find_jj_workspace_root(cwd)
        if jj_workspace_root is not None:
            raise GitCommandInJjWorkspaceError(["git", *options], cwd, jj_workspace_root)
        command = [
            self._resolve_binary(Dependency.GIT),
            *_build_arguments(options, operands, paths),
        ]
        return self._run(command, cwd, is_read_only, is_checked, timeout, extra_env)

    def run_gh(
        self,
        arguments: Sequence[str],
        cwd: Path,
        *,
        is_read_only: bool,
        is_checked: bool = True,
        timeout: float | None = DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS,
        extra_env: Mapping[str, str] | None = None,
    ) -> VcsCommandResult:
        """Run `gh <arguments>` in `cwd`.

        gh runs in jj workspaces too (it reads the repository from `GH_REPO`
        there), so no tripwire applies.
        """
        command = [self._resolve_binary(Dependency.GH), *arguments]
        return self._run(command, cwd, is_read_only, is_checked, timeout, extra_env)

    def _resolve_binary(self, tool: Dependency) -> str:
        binary = self._resolve_binary_path(tool)
        if binary is None:
            raise VcsBinaryNotFoundError(
                f"{tool.value.lower()} binary not found",
                command=(),
                returncode=None,
                stdout="",
                stderr="",
            )
        return binary

    def _run(
        self,
        command: Sequence[str],
        cwd: Path,
        is_read_only: bool,
        is_checked: bool,
        timeout: float | None,
        extra_env: Mapping[str, str] | None,
    ) -> VcsCommandResult:
        env = self._build_env(extra_env)
        if is_read_only:
            return _retry_read_only_command(self._run_once)(command, cwd, is_checked, timeout, env)
        return self._run_once(command, cwd, is_checked, timeout, env)

    def _build_env(self, extra_env: Mapping[str, str] | None) -> Mapping[str, str] | None:
        """The env overrides, then `extra_env`, over the process environment; None when neither adds anything."""
        overrides = {**self._read_env_overrides(), **(extra_env or {})}
        if not overrides:
            return None
        unwrapped_overrides = {
            name: value.unwrap() if isinstance(value, Secret) else value for name, value in overrides.items()
        }
        return {**os.environ, **unwrapped_overrides}

    def _run_once(
        self,
        command: Sequence[str],
        cwd: Path,
        is_checked: bool,
        timeout: float | None,
        env: Mapping[str, str] | None,
    ) -> VcsCommandResult:
        try:
            result = self._concurrency_group.run_process_to_completion(
                command=command,
                cwd=cwd,
                timeout=timeout,
                is_checked_after=False,
                env=env,
            )
        except ProcessSetupError as e:
            raise VcsCommandError(
                f"Failed to start {command} in {cwd}\nstderr: {e.stderr}",
                command=command,
                returncode=None,
                stdout=e.stdout,
                stderr=e.stderr,
            ) from e
        if result.is_timed_out:
            raise VcsCommandTimeoutError(
                f"Timed out after {timeout}s: {command}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        assert result.returncode is not None, "a process that ran to completion has an exit code"
        if is_checked and result.returncode != 0:
            raise VcsCommandExitError(
                f"Error running {command}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return VcsCommandResult(
            command=tuple(command), returncode=result.returncode, stdout=result.stdout, stderr=result.stderr
        )


def _build_arguments(options: Sequence[str], operands: Sequence[str], paths: Sequence[str]) -> list[str]:
    arguments = list(options)
    if operands:
        arguments.extend(["--end-of-options", *operands])
    if paths:
        arguments.extend(["--", *paths])
    return arguments
