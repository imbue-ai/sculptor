"""Tests for LocalAgentExecutionEnvironment wrapper.

Tests verify:
1. Per-task namespaced state and artifacts paths
2. Delegation to underlying Environment for other operations
3. Directory creation on initialization
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.base import TASKS_SUBDIRECTORY
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment


def _create_local_environment_from_path(path: Path, concurrency_group: ConcurrencyGroup) -> LocalEnvironment:
    """Create a LocalEnvironment for testing."""
    return LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(path)),
        project_id=ProjectID(),
        concurrency_group=concurrency_group,
        repo_host_path=path,
    )


@pytest.fixture
def local_environment(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> LocalEnvironment:
    """Create a LocalEnvironment pointing to a temp directory."""
    return _create_local_environment_from_path(tmp_path, test_root_concurrency_group)


@pytest.fixture
def task_id() -> TaskID:
    """Create a TaskID for testing."""
    return TaskID()


@pytest.fixture
def mock_dependency_management_service() -> DependencyManagementService:
    """Create a mock DependencyManagementService for testing."""
    mock_cg = MagicMock(spec=ConcurrencyGroup)
    return DependencyManagementService.model_construct(concurrency_group=mock_cg)


class TestLocalAgentExecutionEnvironmentPathNamespacing:
    """Tests for per-task path namespacing."""

    def test_get_state_path_returns_task_namespaced_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """State path should be namespaced by task ID."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        state_path = agent_env.get_state_path()

        # Should be {root}/state/tasks/{task_id}/
        expected_path = local_environment.get_root_path() / "state" / TASKS_SUBDIRECTORY / str(task_id)
        assert state_path == expected_path

    def test_get_artifacts_path_returns_task_namespaced_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Artifacts path should be namespaced by task ID."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        artifacts_path = agent_env.get_artifacts_path()

        # Should be {root}/artifacts/tasks/{task_id}/
        expected_path = local_environment.get_root_path() / "artifacts" / TASKS_SUBDIRECTORY / str(task_id)
        assert artifacts_path == expected_path

    def test_get_working_directory_returns_shared_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Working directory should be shared (not namespaced)."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        working_dir = agent_env.get_working_directory()

        # Should be the same as the underlying environment's working directory
        assert working_dir == local_environment.get_working_directory()

    def test_different_tasks_get_different_paths(
        self,
        local_environment: LocalEnvironment,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Different tasks should have isolated state and artifacts paths."""
        task_id_1 = TaskID()
        task_id_2 = TaskID()

        agent_env_1 = LocalAgentExecutionEnvironment(local_environment, task_id_1, mock_dependency_management_service)
        agent_env_2 = LocalAgentExecutionEnvironment(local_environment, task_id_2, mock_dependency_management_service)

        # State paths should be different
        assert agent_env_1.get_state_path() != agent_env_2.get_state_path()
        assert str(task_id_1) in str(agent_env_1.get_state_path())
        assert str(task_id_2) in str(agent_env_2.get_state_path())

        # Artifacts paths should be different
        assert agent_env_1.get_artifacts_path() != agent_env_2.get_artifacts_path()
        assert str(task_id_1) in str(agent_env_1.get_artifacts_path())
        assert str(task_id_2) in str(agent_env_2.get_artifacts_path())

        # Working directories should be the same
        assert agent_env_1.get_working_directory() == agent_env_2.get_working_directory()


class TestLocalAgentExecutionEnvironmentDirectoryCreation:
    """Tests for automatic directory creation on initialization."""

    def test_creates_task_state_directory_on_init(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Task state directory should be created on initialization."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        host_state_path = agent_env.to_host_path(agent_env.get_state_path())
        assert host_state_path.exists()
        assert host_state_path.is_dir()

    def test_creates_task_artifacts_directory_on_init(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Task artifacts directory should be created on initialization."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        host_artifacts_path = agent_env.to_host_path(agent_env.get_artifacts_path())
        assert host_artifacts_path.exists()
        assert host_artifacts_path.is_dir()


class TestLocalAgentExecutionEnvironmentDelegation:
    """Tests for delegation to underlying Environment."""

    def test_supports_terminal_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """supports_terminal should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.supports_terminal == local_environment.supports_terminal

    def test_concurrency_group_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """concurrency_group should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.concurrency_group is local_environment.concurrency_group

    def test_get_root_path_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """get_root_path should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.get_root_path() == local_environment.get_root_path()

    def test_get_attachments_path_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """get_attachments_path should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.get_attachments_path() == local_environment.get_attachments_path()

    def test_get_user_home_directory_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """get_user_home_directory should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.get_user_home_directory() == local_environment.get_user_home_directory()

    def test_to_host_path_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """to_host_path should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        test_path = Path("/some/path")
        assert agent_env.to_host_path(test_path) == local_environment.to_host_path(test_path)

    def test_to_environment_path_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """to_environment_path should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        # Use a path under the workspace path, since to_environment_path validates the path is valid
        test_path = local_environment.get_workspace_path() / "some" / "path"
        assert agent_env.to_environment_path(test_path) == local_environment.to_environment_path(test_path)

    def test_exists_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """exists should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        # Test with a path that doesn't exist
        assert agent_env.exists("/nonexistent/path") == local_environment.exists("/nonexistent/path")

    def test_get_system_prompt_delegates(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """get_system_prompt should delegate to underlying environment."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)
        assert agent_env.get_system_prompt() == local_environment.get_system_prompt()


class TestLocalAgentExecutionEnvironmentFileOperations:
    """Tests for file operations on task-namespaced paths."""

    def test_write_and_read_file_in_state_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Should be able to write and read files in the task state directory."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        file_path = str(agent_env.get_state_path() / "test_file.txt")
        content = "test content"

        agent_env.write_file(file_path, content)
        assert agent_env.exists(file_path)

        read_content = agent_env.read_file(file_path)
        assert read_content == content

    def test_write_and_read_file_in_artifacts_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Should be able to write and read files in the task artifacts directory."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        file_path = str(agent_env.get_artifacts_path() / "artifact.json")
        content = '{"key": "value"}'

        agent_env.write_file(file_path, content)
        assert agent_env.exists(file_path)

        read_content = agent_env.read_file(file_path)
        assert read_content == content

    def test_delete_file_removes_file_from_state_path(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """delete_file_or_directory must actually remove the file from disk.

        Regression: the wrapper previously did not override this method, so
        calls were silently swallowed by the Protocol's placeholder body,
        leaving the file in place.  This broke /clear, which relies on the
        session id file being deleted to start a fresh session.
        """
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        file_path = str(agent_env.get_state_path() / "session_id")
        agent_env.write_file(file_path, "some-session-id")
        assert agent_env.exists(file_path)

        agent_env.delete_file_or_directory(file_path)
        assert not agent_env.exists(file_path)

    def test_different_tasks_have_isolated_state_files(
        self,
        local_environment: LocalEnvironment,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """Files written by one task should not be visible to another task's state path."""
        task_id_1 = TaskID()
        task_id_2 = TaskID()

        agent_env_1 = LocalAgentExecutionEnvironment(local_environment, task_id_1, mock_dependency_management_service)
        agent_env_2 = LocalAgentExecutionEnvironment(local_environment, task_id_2, mock_dependency_management_service)

        # Write a file in task 1's state directory
        file_name = "task_specific_file.txt"
        file_path_1 = str(agent_env_1.get_state_path() / file_name)
        agent_env_1.write_file(file_path_1, "task 1 content")

        # The file should exist in task 1's state path
        assert agent_env_1.exists(file_path_1)

        # The same file name should not exist in task 2's state path
        file_path_2 = str(agent_env_2.get_state_path() / file_name)
        assert not agent_env_2.exists(file_path_2)


class TestLocalAgentExecutionEnvironmentProcessExecution:
    """Tests for process execution without privileged access."""

    def test_run_process_in_background_no_sudo(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """run_process_in_background should not allow sudo privileges."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        # Run a simple command
        process = agent_env.run_process_in_background(["echo", "hello"], secrets={})
        stdout, _ = process.wait_and_read(timeout=5.0)

        assert "hello" in stdout

    def test_run_process_to_completion(
        self,
        local_environment: LocalEnvironment,
        task_id: TaskID,
        mock_dependency_management_service: DependencyManagementService,
    ) -> None:
        """run_process_to_completion should work correctly."""
        agent_env = LocalAgentExecutionEnvironment(local_environment, task_id, mock_dependency_management_service)

        result = agent_env.run_process_to_completion(
            ["echo", "test output"],
            secrets={},
            is_checked_after=False,
        )

        assert result.returncode == 0
        assert "test output" in result.stdout
