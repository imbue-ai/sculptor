"""AgentExecutionEnvironment protocol for agent-facing environment access.

This module defines the minimal interface that agents need to interact with their
execution environment. It hides lifecycle operations and provides per-task
namespaced paths for state and artifacts.
"""

from enum import auto
from pathlib import Path
from typing import Callable
from typing import Mapping
from typing import Protocol
from typing import Sequence
from typing import TYPE_CHECKING
from typing import runtime_checkable

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.foundation.upper_case_str_enum import UpperCaseStrEnum

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


class Dependency(UpperCaseStrEnum):
    """A tool binary the environment can resolve via `get_tool_binary_path`.

    Lives in the environment-interface layer so the protocol method that
    consumes it can be typed without an interface→service dependency
    inversion.
    """

    CLAUDE = auto()
    GIT = auto()
    PI = auto()
    GH = auto()
    GLAB = auto()


@runtime_checkable
class AgentExecutionEnvironment(Protocol):
    """Minimal interface for agent execution.

    This protocol defines the methods that agents need to interact with their
    execution environment. It intentionally hides environment lifecycle operations
    (creation, destruction, snapshotting) which are managed by WorkspaceService.

    Key features:
    - Path management with per-task namespacing for state and artifacts
    - File operations for reading/writing within the environment
    - Process execution for running commands
    - Terminal management for interactive sessions

    Path namespacing:
    - get_working_directory(): The code directory (git repo root) where the agent operates
    - get_state_path(): Per-task state directory: {root}/state/tasks/{task_id}/
    - get_artifacts_path(): Per-task artifacts directory: {root}/artifacts/tasks/{task_id}/
    """

    @property
    def supports_terminal(self) -> bool:
        """Whether the environment supports a terminal/TTY."""
        ...

    @property
    def concurrency_group(self) -> ConcurrencyGroup:
        """The concurrency group for process and thread management."""
        ...

    def get_state_path(self) -> Path:
        """Get the per-task state directory path.

        For multi-agent workspaces, this returns a task-namespaced path:
        {workspace_root}/state/tasks/{task_id}/
        """
        ...

    def get_artifacts_path(self) -> Path:
        """Get the per-task artifacts directory path.

        For multi-agent workspaces, this returns a task-namespaced path:
        {workspace_root}/artifacts/tasks/{task_id}/
        """
        ...

    def get_attachments_path(self) -> Path:
        """Get the attachments directory path for uploaded files."""
        ...

    def get_user_home_directory(self) -> Path:
        """Get the home directory of the user running code in this environment."""
        ...

    def get_root_path(self) -> Path:
        """Get the root path of the environment."""
        ...

    def get_working_directory(self) -> Path:
        """Get the directory containing the code the agent operates on.

        In clone mode this is the cloned repository (e.g. {workspace_root}/code/).
        In in-place mode this is the user's original repository path.

        This may differ from get_root_path() which returns the
        environment's root directory.
        """
        ...

    def to_host_path(self, path: Path) -> Path:
        """Convert an environment path to a host filesystem path."""
        ...

    def to_environment_path(self, path: Path) -> Path:
        """Convert a host filesystem path to an environment path."""
        ...

    def exists(self, path: str) -> bool:
        """Check if a path exists in the environment."""
        ...

    def read_file(self, path: str, mode: "OpenTextModeReading | OpenBinaryModeReading" = "r") -> str | bytes:
        """Read a file from the environment.

        Raises:
            FileNotFoundEnvironmentError: if the file does not exist.
        """
        ...

    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: "OpenTextModeWriting | OpenBinaryModeWriting" = "w",
    ) -> None:
        """Write a file to the environment.

        Raises:
            EnvironmentFailure: if the file cannot be written.
        """
        ...

    def delete_file_or_directory(self, path: str) -> None:
        """Delete a file or directory from the environment.

        Raises:
            EnvironmentFailure: if the file cannot be deleted.
        """
        ...

    def run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        shutdown_event: MutableEvent | None = None,
        timeout: float | None = None,
        is_checked_by_group: bool = False,
        on_output: Callable[[str, bool], None] | None = None,
        open_stdin: bool = False,
        isolate_process_group: bool = False,
    ) -> RunningProcess:
        """Run a process in the background, returning immediately.

        Note: run_with_sudo_privileges and run_as_root are not exposed to agents
        as they should not need privileged execution.

        Args:
            command: The command to run as a sequence of strings.
            secrets: Environment variables to set for the process.
            cwd: Working directory for the process.
            is_interactive: Whether the process needs a TTY.
            shutdown_event: Event to signal shutdown.
            timeout: Maximum time to wait for the process.
            is_checked_by_group: Whether to check for failure via concurrency group.
            on_output: Callback for process output.
            isolate_process_group: If True, spawn the child with
                ``start_new_session=True`` and broadcast shutdown signals to
                its whole process group so descendants are killed too. Used
                for the agent CLI so Stop cascades to foreground subprocesses
                (SCU-211).

        Returns:
            A RunningProcess that can be waited on or terminated.
        """
        ...

    def run_process_to_completion(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        timeout: float | None = None,
        is_checked_after: bool = True,
        on_output: Callable[[str, bool], None] | None = None,
    ) -> FinishedProcess:
        """Run a process to completion, blocking until it finishes.

        Args:
            command: The command to run as a sequence of strings.
            secrets: Environment variables to set for the process.
            cwd: Working directory for the process.
            is_interactive: Whether the process needs a TTY.
            timeout: Maximum time to wait for the process.
            is_checked_after: Whether to raise on non-zero exit code.
            on_output: Callback for process output.

        Returns:
            A FinishedProcess with the results.

        Raises:
            ProcessError: If is_checked_after is True and the process fails.
        """
        ...

    def get_tool_binary_path(self, tool: Dependency) -> str | None:
        """Resolve the path to a tool binary.

        Args:
            tool: The dependency to resolve.

        Returns:
            The resolved path to the binary, or None if not found.
        """
        ...

    def get_system_prompt(self) -> str | None:
        """Get the environment-specific system prompt content.

        Returns environment-specific instructions (e.g., mode-specific guidance)
        that should be included in the agent's system prompt.
        """
        ...

    def get_project_env_var_names(self) -> list[str]:
        """Return the names of project-configured environment variables.

        Names come from `.env` files (`~/.sculptor/.env` and
        `<repo>/.sculptor/.env`) that the user explicitly configured for the
        agent. Values are intentionally not exposed.
        """
        ...

    def start_terminal_manager(
        self,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        """Start the terminal manager for this environment.

        Only supported on environments where supports_terminal is True.
        If a terminal is already running, it is reused.

        Args:
            concurrency_group: Long-lived concurrency group for terminal thread/process
                lifecycle management. Should outlive individual agent runs.
        """
        ...

    def stop_terminal_manager(self) -> None:
        """Stop the terminal manager for this environment.

        Safe to call even if no terminal manager was started.
        """
        ...
