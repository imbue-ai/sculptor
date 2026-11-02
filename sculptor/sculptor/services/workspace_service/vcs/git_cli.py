"""The single runner for every git and gh command the VCS seam issues.

Binaries come from the dependency service, so `dependency_paths.git` and
`dependency_paths.gh` are honoured. Every failure, including a timeout, is a
`VcsCommandError`. Only read-only commands are retried. Operands (refs,
revisions, destinations) go after `--end-of-options` and paths after `--`, so
a value starting with `-` is never parsed as an option.
"""

import os
from pathlib import Path
from typing import Mapping
from typing import Sequence

from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.retry_utils import log_before_sleep
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.vcs.data_types import VcsCommandResult
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.errors import VcsCommandTimeoutError

DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS = 30.0


class _RetriableVcsCommandError(VcsCommandError):
    """A read-only command exited non-zero; safe to run again."""


_retry_read_only_command = retry(
    retry=retry_if_exception_type(_RetriableVcsCommandError),
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


def validate_operand(operand: str) -> str:
    """Return `operand` if it is safe to pass to git as a ref, revision or path operand."""
    if operand == "" or any(character in operand for character in ("\0", "\n", "\r")):
        raise InvalidRevisionError(f"Invalid git operand: {operand!r}")
    return operand


class GitCli:
    """Runs git and gh with the user's configured binaries."""

    def __init__(
        self,
        concurrency_group: ConcurrencyGroup,
        dependency_management_service: DependencyManagementService,
    ) -> None:
        self._concurrency_group = concurrency_group
        self._dependency_management_service = dependency_management_service

    @property
    def concurrency_group(self) -> ConcurrencyGroup:
        return self._concurrency_group

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
    ) -> VcsCommandResult:
        """Run `git <options> --end-of-options <operands> -- <paths>` in `cwd`.

        Raises `GitCommandInJjWorkspaceError` when `cwd` is inside a jj workspace.
        With `is_checked`, a non-zero exit raises `VcsCommandError`; without it,
        the result is returned whatever its exit code.
        """
        jj_workspace_root = find_jj_workspace_root(cwd)
        if jj_workspace_root is not None:
            raise GitCommandInJjWorkspaceError(["git", *options], cwd, jj_workspace_root)
        command = [
            self._resolve_binary(Dependency.GIT),
            *_build_arguments(options, operands, paths),
        ]
        return self._run(command, cwd, is_read_only, is_checked, timeout, extra_env=None)

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
        binary = self._dependency_management_service.resolve_binary_path(tool)
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
        env = None if extra_env is None else {**os.environ, **extra_env}
        if is_read_only:
            return _retry_read_only_command(self._run_once)(command, cwd, is_read_only, is_checked, timeout, env)
        return self._run_once(command, cwd, is_read_only, is_checked, timeout, env)

    def _run_once(
        self,
        command: Sequence[str],
        cwd: Path,
        is_read_only: bool,
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
        except ProcessError as e:
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
        if result.returncode is None:
            raise VcsCommandError(
                f"{command} finished without an exit code",
                command=command,
                returncode=None,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        if is_checked and result.returncode != 0:
            error_type = _RetriableVcsCommandError if is_read_only else VcsCommandError
            raise error_type(
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
        arguments.extend(["--end-of-options", *(validate_operand(operand) for operand in operands)])
    if paths:
        arguments.extend(["--", *(validate_operand(path) for path in paths)])
    return arguments
