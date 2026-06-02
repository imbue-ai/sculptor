from __future__ import annotations

import abc
from pathlib import Path
from typing import Callable
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING
from typing import final

from pydantic import BaseModel
from pydantic import PrivateAttr

from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.interfaces.terminal_manager import TerminalManager

# https://github.com/python/typeshed/tree/main/stdlib/_typeshed
if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


STATE_DIRECTORY = "state"
ARTIFACTS_DIRECTORY = "artifacts"
ATTACHMENTS_DIRECTORY = "attachments"
TASKS_SUBDIRECTORY = "tasks"


class Environment(BaseModel, abc.ABC):
    environment_id: str
    project_id: ProjectID
    concurrency_group: ConcurrencyGroup
    _terminal_manager: TerminalManager | None = PrivateAttr(default=None)

    # ===== Capability Properties =====
    # These properties advertise which features each environment supports.
    # Code should check these properties instead of using isinstance() checks.

    @property
    @abc.abstractmethod
    def supports_terminal(self) -> bool:
        """Whether the environment supports a terminal/TTY."""
        ...

    @abc.abstractmethod
    def get_user_home_directory(self) -> Path:
        """Get the home directory of the user running code in this environment.

        Returns:
            The absolute path to the home directory inside the environment.
        """

    @abc.abstractmethod
    def get_root_path(self) -> Path:
        """Get the root path inside the environment.

        Returns the actual filesystem path to the environment root directory
        where state, artifacts, and other environment files are stored.
        """

    def get_state_path(self) -> Path:
        return self.get_root_path() / STATE_DIRECTORY

    @abc.abstractmethod
    def get_workspace_path(self) -> Path:
        """Get the workspace path for this environment.

        Returns the actual filesystem path to the workspace directory.
        """

    @abc.abstractmethod
    def get_working_directory(self) -> Path:
        """Get the directory where the agent should perform all work.

        This returns the directory containing the code the agent operates on.
        For environments that clone repositories, this may differ from
        get_workspace_path() which returns the environment's root directory.

        Returns:
            The absolute path to the working directory.
        """

    def get_artifacts_path(self) -> Path:
        return self.get_root_path() / ARTIFACTS_DIRECTORY

    def get_attachments_path(self) -> Path:
        return self.get_root_path() / ATTACHMENTS_DIRECTORY

    def get_project_env_var_names(self) -> list[str]:
        """Return the names of project-configured environment variables.

        Names come from `.env` files (`~/.sculptor/.env` and
        `<repo>/.sculptor/.env`) when the environment supports them.
        Default: no project env vars.
        """
        return []

    def get_system_prompt(self) -> str | None:
        """Get the environment-specific system prompt content.

        Returns environment-specific instructions that should be included in the
        agent's system prompt. Returns None if no environment-specific content
        is needed.

        Returns:
            A string containing environment-specific system prompt content,
            or None if no additional content is needed.
        """
        return None

    def start_terminal_manager(
        self,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        """Start the terminal manager for this environment.

        Creates and initializes a terminal manager. If a terminal for this
        environment is already running, it is reused.
        Only supported on environments where supports_terminal is True.

        Args:
            concurrency_group: Long-lived concurrency group for terminal thread/process
                lifecycle management. Should outlive individual agent runs.

        Raises:
            NotImplementedError: If this environment doesn't support terminals.
        """
        raise NotImplementedError(f"start_terminal_manager is not supported for {type(self).__name__}")

    def stop_terminal_manager(self) -> None:
        """Stop the terminal manager for this environment.

        Stops the terminal session and cleans up resources. Safe to call even if
        no terminal manager was started or if the environment doesn't support terminals.
        """
        if self._terminal_manager is not None:
            self._terminal_manager.stop()
            self._terminal_manager = None

    def to_host_path(self, path: Path) -> Path:
        """
        Resolve a path supplied by environment-side code to its absolute path on the host.

        For LocalEnvironment, paths under the workspace working directory are returned
        as-is; other absolute paths may be remapped to the workspace root by the
        concrete subclass.
        """
        return path

    def to_environment_path(self, path: Path) -> Path:
        """
        Inverse of to_host_path: return the path as it would be referred to from
        environment-side code.
        """
        return path

    @abc.abstractmethod
    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]: ...

    @abc.abstractmethod
    def _run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        shutdown_event: MutableEvent | None = None,
        timeout: float | None = None,
        is_checked: bool = False,
        on_output: Callable[[str, bool], None] | None = None,
        open_stdin: bool = False,
        isolate_process_group: bool = False,
    ) -> RunningProcess: ...

    def run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        shutdown_event: MutableEvent | None = None,
        timeout: float | None = None,
        is_checked_by_group: bool = False,
        on_output: Callable[[str, bool], None] | None = None,
        open_stdin: bool = False,
        isolate_process_group: bool = False,
    ) -> RunningProcess:
        """
        Run a process in the background, returning immediately.

        When `is_checked_by_group` is True, the process will be checked for failure when
        the environment's concurrency group exits or whenever the group's methods are called.
        (And also when waited on directly, the default is False)

        When ``isolate_process_group`` is True, the child is spawned with
        ``start_new_session=True`` and its shutdown signal is broadcast to the
        whole process group, so descendants are killed too. Used for the
        agent CLI so Stop cascades to the agent's foreground subprocesses
        (SCU-211).
        """
        return self.concurrency_group.start_background_process_from_factory(
            lambda: self._run_process_in_background(
                command=command,
                secrets=secrets,
                cwd=cwd,
                is_interactive=is_interactive,
                run_with_sudo_privileges=run_with_sudo_privileges,
                run_as_root=run_as_root,
                shutdown_event=shutdown_event,
                timeout=timeout,
                is_checked=is_checked_by_group,
                on_output=on_output,
                open_stdin=open_stdin,
                isolate_process_group=isolate_process_group,
            )
        )

    @final
    def run_process_to_completion(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        timeout: float | None = None,
        is_checked_after: bool = True,
        on_output: Callable[[str, bool], None] | None = None,
    ) -> FinishedProcess:
        """
        Run a process to completion, blocking until it finishes.

        When `is_checked_after` is True (the default), raise a ProcessError if the process exits with a non-zero exit code.

        """
        process = self.run_process_in_background(
            command,
            secrets,
            cwd,
            is_interactive,
            run_with_sudo_privileges,
            run_as_root,
            # Never mark the original background process as "checked".
            # Reason: the concurrency group would raise an exception even if the failure of the process was properly handled by the caller.
            is_checked_by_group=False,
            timeout=timeout,
            on_output=on_output,
        )
        _result = process.wait()
        if is_checked_after:
            process.check()
        return FinishedProcess(
            command=tuple(process.command),
            returncode=process.returncode,
            stdout=process.read_stdout(),
            stderr=process.read_stderr(),
            is_timed_out=process.get_timed_out(),
            is_output_already_logged=False,
        )

    @abc.abstractmethod
    def run_setup_subprocess(
        self,
        command: str,
        on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        shutdown_event: ReadOnlyEvent,
    ) -> int:
        """Run the workspace setup command as a non-interactive bash login subprocess.

        Streams combined stdout+stderr bytes through ``on_chunk``. cwd is the
        workspace repo root. stdin is closed. Cancel propagates when
        ``shutdown_event`` is set: SIGINT, then SIGTERM after ~2s, then SIGKILL
        after ~5s, all sent to the process group. Returns the process exit
        code (negative if the cancel ladder killed it via signal).

        ``on_pid`` is invoked exactly once with the OS PID of the bash
        subprocess, immediately after spawn succeeds and before any chunk is
        streamed. If subprocess creation (or the pgid sanity check) fails
        before a stable PID is obtained, ``on_pid`` is not invoked.
        Implementations must invoke ``on_pid`` on the calling thread, not on
        a background thread, so callers do not race on it.
        """

    @abc.abstractmethod
    def is_alive(self) -> bool: ...

    @abc.abstractmethod
    def exists(self, path: str) -> bool: ...

    @abc.abstractmethod
    def read_file(self, path: str, mode: "OpenTextModeReading" | "OpenBinaryModeReading" = "r") -> str | bytes:
        """
        Read a file from the environment.

        Raises:
            FileNotFoundEnvironmentError: if the file does not exist.
        """

    @abc.abstractmethod
    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: "OpenTextModeWriting" | "OpenBinaryModeWriting" = "w",
    ) -> None:
        """
        Write a file to the environment.

        Raises:
            EnvironmentFailure: if the file cannot be written.
        """

    @abc.abstractmethod
    def delete_file_or_directory(self, path: str) -> None:
        """
        Delete a file from the environment.

        Raises:
            EnvironmentFailure: if the file cannot be deleted.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """
        Close the environment, leaving it in a state where it can be opened again.

        In particular, all processes must be stopped, and all ephemeral data must be cleaned up.

        Volumes and images will not be deleted, as they may be reused in the future.
        """

    @abc.abstractmethod
    def destroy(self, is_killing: bool = False) -> None:
        """
        Destroy the environment, releasing any resources it holds.

        This calls close() as well, eg, is a superset of that cleanup behavior.
        """
