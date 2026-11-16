"""How the VCS seam runs jj.

The binary comes from a resolver callable, as for `GitCli`: Sculptor's own calls
pass the dependency service's `resolve_binary_path` and agent-side calls pass
their execution environment's `get_tool_binary_path`, so jj is never looked up on
PATH here. jj snapshots the working copy at the start of any command not given
`--ignore-working-copy`, and Sculptor's background reads must never snapshot an
agent's edits, so every call names a `JjSnapshotPolicy`. Every failure, including
a timeout, is a `VcsCommandError`. Nothing is retried: jj merges concurrent
operations itself.
"""

import os
import re
from enum import StrEnum
from pathlib import Path
from typing import Mapping
from typing import Sequence
from typing import assert_never

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.workspace_service.vcs.data_types import VcsCommandResult
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.errors import VcsCommandTimeoutError
from sculptor.services.workspace_service.vcs.git_cli import BinaryResolver
from sculptor.services.workspace_service.vcs.git_cli import DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS
from sculptor.services.workspace_service.vcs.git_cli import EnvOverridesReader

_STALE_WORKING_COPY_MESSAGE = "The working copy is stale"
_REFUSED_SNAPSHOT_HEADER = "Warning: Refused to snapshot some files:"
# `  <path>: 4.9KiB (5000 bytes); the maximum size allowed is ...`. The path may itself
# contain ": ", so it ends at the first ": " followed by a size in bytes.
_REFUSED_SNAPSHOT_FILE_LINE = re.compile(r"  (?P<path>.+?): (?P<message>\S+ \(\d+ bytes\).*)")


class JjSnapshotPolicy(StrEnum):
    """Whether a jj command may snapshot the working copy before it runs."""

    SNAPSHOT = "SNAPSHOT"
    IGNORE_WORKING_COPY = "IGNORE_WORKING_COPY"


def _no_env_overrides() -> Mapping[str, str | Secret]:
    return {}


class JjCli:
    """Runs jj with the user's configured binary."""

    def __init__(
        self,
        concurrency_group: ConcurrencyGroup,
        resolve_binary: BinaryResolver,
        read_env_overrides: EnvOverridesReader = _no_env_overrides,
    ) -> None:
        self._concurrency_group = concurrency_group
        self._resolve_binary_path = resolve_binary
        self._read_env_overrides = read_env_overrides

    def run(
        self,
        arguments: Sequence[str],
        repo_dir: Path,
        *,
        snapshot: JjSnapshotPolicy,
        is_checked: bool = True,
        timeout: float | None = DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS,
        config_overrides: Mapping[str, str] | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> VcsCommandResult:
        """Run `jj -R <repo_dir> <arguments>` with cwd at `repo_dir`, a workspace root or the main repository.

        With `is_checked`, a non-zero exit raises `VcsCommandExitError`; without it,
        the result is returned whatever its exit code. A stale working copy raises
        `JjWorkingCopyStaleError` either way. `config_overrides` become `--config`
        options for this command only.
        """
        global_options = ["-R", str(repo_dir), *_snapshot_options(snapshot), *_config_options(config_overrides)]
        return self._run([*global_options, *arguments], repo_dir, is_checked, timeout, extra_env)

    def run_outside_repository(
        self,
        arguments: Sequence[str],
        cwd: Path,
        *,
        timeout: float | None = DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS,
    ) -> VcsCommandResult:
        """Run a jj command that has no repository yet, such as `git init --colocate <path>` or `--version`.

        A non-zero exit raises `VcsCommandExitError`.
        """
        return self._run(arguments, cwd, is_checked=True, timeout=timeout, extra_env=None)

    def _run(
        self,
        arguments: Sequence[str],
        cwd: Path,
        is_checked: bool,
        timeout: float | None,
        extra_env: Mapping[str, str] | None,
    ) -> VcsCommandResult:
        command = [self._resolve_binary(), "--no-pager", "--color=never", *arguments]
        env = self._build_env(extra_env)
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
        if result.returncode != 0 and _STALE_WORKING_COPY_MESSAGE in result.stderr:
            raise JjWorkingCopyStaleError(
                f"Working copy in {cwd} is stale: {command}\nstderr: {result.stderr}",
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
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

    def _resolve_binary(self) -> str:
        binary = self._resolve_binary_path(Dependency.JJ)
        if binary is None:
            raise VcsBinaryNotFoundError("jj binary not found", command=(), returncode=None, stdout="", stderr="")
        return binary

    def _build_env(self, extra_env: Mapping[str, str] | None) -> Mapping[str, str] | None:
        """The env overrides, then `extra_env`, over the process environment; None when neither adds anything."""
        overrides = {**self._read_env_overrides(), **(extra_env or {})}
        if not overrides:
            return None
        unwrapped_overrides = {
            name: value.unwrap() if isinstance(value, Secret) else value for name, value in overrides.items()
        }
        return {**os.environ, **unwrapped_overrides}


def parse_refused_snapshot_files(stderr: str) -> dict[str, str]:
    """The files jj's snapshot warning says it refused to snapshot, each mapped to jj's reason.

    Paths are relative to the command's cwd, which `JjCli.run` sets to the
    workspace root.
    """
    refused_files: dict[str, str] = {}
    is_in_refused_list = False
    for line in stderr.splitlines():
        match = _REFUSED_SNAPSHOT_FILE_LINE.fullmatch(line)
        if line == _REFUSED_SNAPSHOT_HEADER:
            is_in_refused_list = True
        elif is_in_refused_list and match is not None:
            refused_files[match["path"]] = match["message"]
        else:
            is_in_refused_list = False
    return refused_files


def _snapshot_options(snapshot: JjSnapshotPolicy) -> list[str]:
    match snapshot:
        case JjSnapshotPolicy.SNAPSHOT:
            return []
        case JjSnapshotPolicy.IGNORE_WORKING_COPY:
            return ["--ignore-working-copy"]
        case _ as unreachable:
            assert_never(unreachable)


def _config_options(config_overrides: Mapping[str, str] | None) -> list[str]:
    options: list[str] = []
    for key, value in (config_overrides or {}).items():
        options.extend(["--config", f"{key}={value}"])
    return options
