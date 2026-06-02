"""Tests for CodingAgentTaskView.task_completed / task_total / current_task_subject.

These are computed from the latest UpdatedArtifactAgentMessage(PLAN) whose
file URL points at a v2 TaskListArtifact on disk. Legacy TodoListArtifact
files and version != 2 files are ignored.
"""

from pathlib import Path

from pydantic import AnyUrl

from sculptor.foundation.agents.data_types.ids import AgentMessageID
from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import FileAgentArtifact
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.artifacts import AgentTaskStatus
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import Task as TaskArtifactItem
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import create_initial_task_view


def _make_task_view() -> CodingAgentTaskView:
    workspace_id = WorkspaceID()
    task = Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
        outcome=TaskState.RUNNING,
    )
    view = create_initial_task_view(task, SculptorSettings())
    assert isinstance(view, CodingAgentTaskView)
    view.update_task(task)
    return view


def _plan_artifact_message(file_path: Path) -> UpdatedArtifactAgentMessage:
    return UpdatedArtifactAgentMessage(
        message_id=AgentMessageID(),
        artifact=FileAgentArtifact(name=ArtifactType.PLAN, url=AnyUrl(f"file://{file_path}")),
    )


def _write_v2_artifact(path: Path, tasks: list[TaskArtifactItem]) -> None:
    path.write_text(TaskListArtifact(tasks=tasks).model_dump_json(indent=2))


def test_no_artifact_messages_returns_zero() -> None:
    view = _make_task_view()
    assert view.task_completed == 0
    assert view.task_total == 0
    assert view.current_task_subject is None


def test_task_counts_from_latest_v2_artifact(tmp_path: Path) -> None:
    view = _make_task_view()
    plan_path = tmp_path / "PLAN-abc.json"
    _write_v2_artifact(
        plan_path,
        [
            TaskArtifactItem(id="1", subject="A", status=AgentTaskStatus.COMPLETED),
            TaskArtifactItem(id="2", subject="B", status=AgentTaskStatus.IN_PROGRESS),
            TaskArtifactItem(id="3", subject="C", status=AgentTaskStatus.PENDING),
        ],
    )
    view.add_message(_plan_artifact_message(plan_path))

    assert view.task_completed == 1
    assert view.task_total == 3
    assert view.current_task_subject == "B"


def test_no_in_progress_returns_none_subject(tmp_path: Path) -> None:
    view = _make_task_view()
    plan_path = tmp_path / "PLAN-abc.json"
    _write_v2_artifact(
        plan_path,
        [
            TaskArtifactItem(id="1", subject="A", status=AgentTaskStatus.COMPLETED),
            TaskArtifactItem(id="2", subject="B", status=AgentTaskStatus.COMPLETED),
        ],
    )
    view.add_message(_plan_artifact_message(plan_path))

    assert view.task_completed == 2
    assert view.task_total == 2
    assert view.current_task_subject is None


def test_legacy_todo_artifact_is_ignored(tmp_path: Path) -> None:
    view = _make_task_view()
    plan_path = tmp_path / "PLAN-legacy.json"
    plan_path.write_text(
        '{"object_type": "TodoListArtifact", "todos": [{"id": "1", "content": "x", "status": "completed"}]}'
    )
    view.add_message(_plan_artifact_message(plan_path))

    assert view.task_completed == 0
    assert view.task_total == 0
    assert view.current_task_subject is None


def test_unsupported_version_is_ignored(tmp_path: Path) -> None:
    view = _make_task_view()
    plan_path = tmp_path / "PLAN-v1.json"
    plan_path.write_text('{"object_type": "TaskListArtifact", "version": 1, "tasks": []}')
    view.add_message(_plan_artifact_message(plan_path))

    assert view.task_completed == 0
    assert view.task_total == 0


def test_latest_message_wins(tmp_path: Path) -> None:
    view = _make_task_view()
    first = tmp_path / "PLAN-1.json"
    _write_v2_artifact(first, [TaskArtifactItem(id="1", subject="A", status=AgentTaskStatus.PENDING)])
    view.add_message(_plan_artifact_message(first))

    second = tmp_path / "PLAN-2.json"
    _write_v2_artifact(
        second,
        [
            TaskArtifactItem(id="1", subject="A", status=AgentTaskStatus.COMPLETED),
            TaskArtifactItem(id="2", subject="B", status=AgentTaskStatus.IN_PROGRESS),
        ],
    )
    view.add_message(_plan_artifact_message(second))

    assert view.task_completed == 1
    assert view.task_total == 2
    assert view.current_task_subject == "B"
