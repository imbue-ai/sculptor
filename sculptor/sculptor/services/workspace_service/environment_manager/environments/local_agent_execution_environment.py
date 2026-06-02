"""LocalAgentExecutionEnvironment wraps LocalEnvironment for agent use.

This module provides a wrapper around LocalEnvironment that implements the
AgentExecutionEnvironment protocol. It provides per-task namespaced paths for
state and artifacts while delegating all other operations to the underlying
environment.
"""

from pathlib import Path
from typing import Callable
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING

from loguru import logger

from sculptor.foundation.agents.data_types.ids import TaskID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.interfaces.environments.base import ARTIFACTS_DIRECTORY
from sculptor.interfaces.environments.base import Environment
from sculptor.interfaces.environments.base import STATE_DIRECTORY
from sculptor.interfaces.environments.base import TASKS_SUBDIRECTORY
from sculptor.services.dependency_management_service import DependencyManagementService

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


class LocalAgentExecutionEnvironment(AgentExecutionEnvironment):
    """Wrapper around LocalEnvironment that provides per-task namespaced paths.

    This class implements the AgentExecutionEnvironment protocol by wrapping a
    LocalEnvironment and providing task-specific directories for state and artifacts.

    Per-task namespacing:
    - State path: {workspace_root}/state/tasks/{task_id}/
    - Artifacts path: {workspace_root}/artifacts/tasks/{task_id}/

    All other operations are delegated directly to the underlying environment.
    """

    def __init__(
        self,
        environment: Environment,
        task_id: TaskID,
        dependency_management_service: DependencyManagementService,
    ) -> None:
        """Initialize the agent execution environment wrapper.

        Args:
            environment: The underlying Environment to wrap.
            task_id: The task ID for namespacing state and artifacts.
            dependency_management_service: Service for resolving tool binary paths.
        """
        self._environment = environment
        self._task_id = task_id
        self._dependency_management_service = dependency_management_service

        # Create task-specific directories on initialization
        self._ensure_task_directories_exist()

    def _ensure_task_directories_exist(self) -> None:
        """Create the per-task state and artifacts directories."""
        state_path = self.get_state_path()
        artifacts_path = self.get_artifacts_path()

        host_state_path = self._environment.to_host_path(state_path)
        host_artifacts_path = self._environment.to_host_path(artifacts_path)

        logger.debug(
            "Creating task directories for task {}: state={}, artifacts={}",
            self._task_id,
            host_state_path,
            host_artifacts_path,
        )

        host_state_path.mkdir(parents=True, exist_ok=True)
        host_artifacts_path.mkdir(parents=True, exist_ok=True)

    # ===== Properties =====

    # TODO(SCU-135): Remove this property when git/diff operations move to workspace level.
    # This property exists to support EnvironmentAcquiredRunnerMessage.environment field,
    # which will be removed when workspace-level API endpoints replace task-level access.
    @property
    def underlying_environment(self) -> Environment:
        """Get the underlying Environment instance.

        This is useful for internal operations that need access to the actual
        environment rather than the wrapper (e.g., for logging/serialization).
        """
        return self._environment

    @property
    def supports_terminal(self) -> bool:
        """Whether the environment supports a terminal/TTY."""
        return self._environment.supports_terminal

    @property
    def concurrency_group(self) -> ConcurrencyGroup:
        """The concurrency group for process and thread management."""
        return self._environment.concurrency_group

    # ===== Path Management =====

    def get_state_path(self) -> Path:
        """Get the per-task state directory path.

        Returns: {workspace_root}/state/tasks/{task_id}/
        """
        return self._environment.get_root_path() / STATE_DIRECTORY / TASKS_SUBDIRECTORY / str(self._task_id)

    def get_artifacts_path(self) -> Path:
        """Get the per-task artifacts directory path.

        Returns: {workspace_root}/artifacts/tasks/{task_id}/
        """
        return self._environment.get_root_path() / ARTIFACTS_DIRECTORY / TASKS_SUBDIRECTORY / str(self._task_id)

    def get_attachments_path(self) -> Path:
        """Get the attachments directory path for uploaded files."""
        return self._environment.get_attachments_path()

    def get_user_home_directory(self) -> Path:
        """Get the home directory of the user running code in this environment."""
        return self._environment.get_user_home_directory()

    def get_root_path(self) -> Path:
        """Get the root path of the environment."""
        return self._environment.get_root_path()

    def get_working_directory(self) -> Path:
        """Get the directory containing the code the agent operates on."""
        return self._environment.get_working_directory()

    def to_host_path(self, path: Path) -> Path:
        """Convert an environment path to a host filesystem path."""
        return self._environment.to_host_path(path)

    def to_environment_path(self, path: Path) -> Path:
        """Convert a host filesystem path to an environment path."""
        return self._environment.to_environment_path(path)

    # ===== File Operations =====

    def exists(self, path: str) -> bool:
        """Check if a path exists in the environment."""
        return self._environment.exists(path)

    def read_file(self, path: str, mode: "OpenTextModeReading | OpenBinaryModeReading" = "r") -> str | bytes:
        """Read a file from the environment."""
        return self._environment.read_file(path, mode)

    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: "OpenTextModeWriting | OpenBinaryModeWriting" = "w",
    ) -> None:
        """Write a file to the environment."""
        return self._environment.write_file(path, content, mode)

    def delete_file_or_directory(self, path: str) -> None:
        """Delete a file or directory from the environment."""
        return self._environment.delete_file_or_directory(path)

    # ===== Process Management =====

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

        Note: This method intentionally does not expose run_with_sudo_privileges
        and run_as_root parameters, as agents should not need privileged execution.
        """
        return self._environment.run_process_in_background(
            command=command,
            secrets=secrets,
            cwd=cwd,
            is_interactive=is_interactive,
            # Agents don't get privileged execution
            run_with_sudo_privileges=False,
            run_as_root=False,
            shutdown_event=shutdown_event,
            timeout=timeout,
            is_checked_by_group=is_checked_by_group,
            on_output=on_output,
            open_stdin=open_stdin,
            isolate_process_group=isolate_process_group,
        )

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
        """Run a process to completion, blocking until it finishes."""
        return self._environment.run_process_to_completion(
            command=command,
            secrets=secrets,
            cwd=cwd,
            is_interactive=is_interactive,
            # Agents don't get privileged execution
            run_with_sudo_privileges=False,
            run_as_root=False,
            timeout=timeout,
            is_checked_after=is_checked_after,
            on_output=on_output,
        )

    # ===== Tool Binary Resolution =====

    def get_tool_binary_path(self, tool: Dependency) -> str | None:
        """Resolve the path to a tool binary."""
        return self._dependency_management_service.resolve_binary_path(tool)

    # ===== System Configuration =====

    def get_system_prompt(self) -> str | None:
        """Get the environment-specific system prompt content."""
        return self._environment.get_system_prompt()

    def get_project_env_var_names(self) -> list[str]:
        return self._environment.get_project_env_var_names()

    # ===== Terminal Management =====

    def start_terminal_manager(
        self,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        """Start the terminal manager for this environment."""
        return self._environment.start_terminal_manager(concurrency_group)

    def stop_terminal_manager(self) -> None:
        """Stop the terminal manager for this environment."""
        return self._environment.stop_terminal_manager()
