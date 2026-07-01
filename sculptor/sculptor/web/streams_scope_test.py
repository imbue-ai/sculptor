import pytest
from fastapi import HTTPException

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import TaskUpdate
from sculptor.web.derived import UserUpdate
from sculptor.web.derived import create_initial_task_view
from sculptor.web.streams import ScopeAgent
from sculptor.web.streams import ScopeAll
from sculptor.web.streams import ScopeProject
from sculptor.web.streams import ScopeWorkspace
from sculptor.web.streams import StreamingUpdate
from sculptor.web.streams import _scope_subscribed_entity_was_deleted
from sculptor.web.streams import parse_scope_query_param
from sculptor.web.streams import project_for_scope

# Tracks every field of StreamingUpdate that the scope-narrowing logic needs to
# consider. Lives next to the test so an added field forces a deliberate update
# to `project_for_scope` and this set together — preventing a new field from
# silently leaking past the narrow-scope filter.
_EXPECTED_STREAMING_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "task_update_by_task_id",
        "task_views_by_task_id",
        "user_update",
        "workspace_branch_by_workspace_id",
        "workspace_target_branches_by_workspace_id",
        "pr_status_by_workspace_id",
        "finished_request_ids",
        "dependencies_status",
        "workspace_setup_status_by_workspace_id",
        "workspace_setup_output_by_workspace_id",
        "btw_update",
        "ui_open_file_by_workspace_id",
        "ui_webview_command_by_workspace_id",
        "ui_plugin_command_by_workspace_id",
    }
)


def test_parse_scope_none_returns_all() -> None:
    assert parse_scope_query_param(None) == ScopeAll()


def test_parse_scope_empty_string_returns_all() -> None:
    assert parse_scope_query_param("") == ScopeAll()


def test_parse_scope_all_returns_all() -> None:
    assert parse_scope_query_param("all") == ScopeAll()


def test_parse_scope_agent() -> None:
    agent_id = TaskID()
    parsed = parse_scope_query_param(f"agent:{agent_id}")
    assert isinstance(parsed, ScopeAgent)
    assert parsed.agent_id == agent_id


def test_parse_scope_workspace() -> None:
    workspace_id = WorkspaceID()
    parsed = parse_scope_query_param(f"workspace:{workspace_id}")
    assert isinstance(parsed, ScopeWorkspace)
    assert parsed.workspace_id == workspace_id


def test_parse_scope_project() -> None:
    project_id = ProjectID()
    parsed = parse_scope_query_param(f"project:{project_id}")
    assert isinstance(parsed, ScopeProject)
    assert parsed.project_id == project_id


@pytest.mark.parametrize(
    "value",
    [
        "agent",
        "agent:",
        "foo:bar",
        ":bar",
        "all:foo",
        "workspace:",
        "project:",
        "agent:not-a-typeid",
    ],
)
def test_parse_scope_malformed_raises_400(value: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_scope_query_param(value)
    assert exc_info.value.status_code == 400


def _make_task_update(task_id: TaskID) -> TaskUpdate:
    return TaskUpdate(
        task_id=task_id,
        chat_messages=(),
        updated_artifacts=(),
        in_progress_chat_message=None,
        queued_chat_messages=(),
        in_progress_user_message_id=None,
        streaming_start_index=0,
    )


def _make_task(*, project_id: ProjectID, workspace_id: WorkspaceID) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=project_id,
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
    )


def _make_view(task: Task) -> CodingAgentTaskView:
    settings = SculptorSettings()
    view = create_initial_task_view(task, settings)
    assert isinstance(view, CodingAgentTaskView)
    view.update_task(task)
    return view


def _build_synthetic_update() -> tuple[
    StreamingUpdate,
    ProjectID,
    ProjectID,
    WorkspaceID,
    WorkspaceID,
    WorkspaceID,
    Task,
    Task,
    Task,
]:
    project_a = ProjectID()
    project_b = ProjectID()
    workspace_a1 = WorkspaceID()
    workspace_a2 = WorkspaceID()
    workspace_b1 = WorkspaceID()

    task_a1 = _make_task(project_id=project_a, workspace_id=workspace_a1)
    task_a2 = _make_task(project_id=project_a, workspace_id=workspace_a2)
    task_b1 = _make_task(project_id=project_b, workspace_id=workspace_b1)

    view_a1 = _make_view(task_a1)
    view_a2 = _make_view(task_a2)
    view_b1 = _make_view(task_b1)

    update = StreamingUpdate(
        task_update_by_task_id={
            task_a1.object_id: _make_task_update(task_a1.object_id),
            task_a2.object_id: _make_task_update(task_a2.object_id),
            task_b1.object_id: _make_task_update(task_b1.object_id),
        },
        task_views_by_task_id={
            task_a1.object_id: view_a1,
            task_a2.object_id: view_a2,
            task_b1.object_id: view_b1,
        },
        user_update=UserUpdate(),
        workspace_branch_by_workspace_id={workspace_a1: None, workspace_a2: None, workspace_b1: None},
        pr_status_by_workspace_id={workspace_a1: None, workspace_a2: None, workspace_b1: None},
        finished_request_ids=(RequestID(),),
        dependencies_status=None,
    )
    return update, project_a, project_b, workspace_a1, workspace_a2, workspace_b1, task_a1, task_a2, task_b1


def test_unmapped_field_guard() -> None:
    assert set(StreamingUpdate.model_fields.keys()) == set(_EXPECTED_STREAMING_UPDATE_FIELDS)


def test_project_for_scope_all_returns_unchanged() -> None:
    update, *_ = _build_synthetic_update()
    result = project_for_scope(update, ScopeAll())
    assert result == update


def test_project_for_scope_project() -> None:
    update, project_a, project_b, workspace_a1, workspace_a2, _, task_a1, task_a2, task_b1 = _build_synthetic_update()
    result = project_for_scope(
        update,
        ScopeProject(project_id=project_a),
        project_workspace_ids=frozenset({workspace_a1, workspace_a2}),
    )
    assert set(result.task_views_by_task_id.keys()) == {task_a1.object_id, task_a2.object_id}
    assert set(result.task_update_by_task_id.keys()) == {task_a1.object_id, task_a2.object_id}
    assert set(result.workspace_branch_by_workspace_id.keys()) == {workspace_a1, workspace_a2}
    assert set(result.pr_status_by_workspace_id.keys()) == {workspace_a1, workspace_a2}
    assert result.finished_request_ids == ()
    assert result.dependencies_status is None
    assert result.user_update == UserUpdate()


def test_project_for_scope_workspace() -> None:
    update, project_a, _, workspace_a1, workspace_a2, _, task_a1, _, _ = _build_synthetic_update()
    result = project_for_scope(update, ScopeWorkspace(workspace_id=workspace_a1, project_id=project_a))
    assert set(result.task_views_by_task_id.keys()) == {task_a1.object_id}
    assert set(result.task_update_by_task_id.keys()) == {task_a1.object_id}
    assert set(result.workspace_branch_by_workspace_id.keys()) == {workspace_a1}
    assert set(result.pr_status_by_workspace_id.keys()) == {workspace_a1}
    assert workspace_a2 not in result.workspace_branch_by_workspace_id
    assert result.finished_request_ids == ()
    assert result.dependencies_status is None
    assert result.user_update == UserUpdate()


def test_project_for_scope_agent() -> None:
    update, project_a, _, workspace_a1, _, _, task_a1, _, _ = _build_synthetic_update()
    result = project_for_scope(
        update,
        ScopeAgent(agent_id=task_a1.object_id, workspace_id=workspace_a1, project_id=project_a),
    )
    assert set(result.task_views_by_task_id.keys()) == {task_a1.object_id}
    assert set(result.task_update_by_task_id.keys()) == {task_a1.object_id}
    assert result.workspace_branch_by_workspace_id == {}
    assert result.pr_status_by_workspace_id == {}
    assert result.finished_request_ids == ()
    assert result.dependencies_status is None
    assert result.user_update == UserUpdate()


def _make_project(*, project_id: ProjectID, is_deleted: bool = False) -> Project:
    return Project(
        object_id=project_id,
        organization_reference=OrganizationReference("test-org"),
        name="test-project",
        is_deleted=is_deleted,
    )


def _make_workspace(*, workspace_id: WorkspaceID, project_id: ProjectID, is_deleted: bool = False) -> Workspace:
    return Workspace(
        object_id=workspace_id,
        project_id=project_id,
        organization_reference=OrganizationReference("test-org"),
        description="test",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        is_deleted=is_deleted,
    )


def test_close_on_delete_is_false_for_scope_all() -> None:
    project_id = ProjectID()
    deletion = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_project(project_id=project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(ScopeAll(), [deletion]) is False


def test_close_on_delete_fires_for_scope_project() -> None:
    """A CompletedTransaction marking the subscribed project as
    deleted MUST trigger the close signal under ScopeProject.
    """
    project_id = ProjectID()
    other_project_id = ProjectID()
    scope = ScopeProject(project_id=project_id)

    # Deleting a different project should NOT trigger close.
    other = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_project(project_id=other_project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [other]) is False

    # Deleting the subscribed project DOES trigger close.
    target = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_project(project_id=project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [target]) is True

    # Project still alive (is_deleted=False) → no close.
    alive = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_project(project_id=project_id, is_deleted=False),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [alive]) is False


def test_close_on_delete_fires_for_scope_workspace() -> None:
    project_id = ProjectID()
    workspace_id = WorkspaceID()
    scope = ScopeWorkspace(workspace_id=workspace_id, project_id=project_id)

    # Workspace deleted → close.
    ws_deleted = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_workspace(workspace_id=workspace_id, project_id=project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [ws_deleted]) is True

    # Parent project deleted → close (cascade).
    project_deleted = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_project(project_id=project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [project_deleted]) is True

    # Some other workspace deleted → no close.
    other_ws_deleted = CompletedTransaction(
        request_id=RequestID(),
        updated_models=(_make_workspace(workspace_id=WorkspaceID(), project_id=project_id, is_deleted=True),),
    )
    assert _scope_subscribed_entity_was_deleted(scope, [other_ws_deleted]) is False


def test_close_on_delete_fires_for_scope_agent() -> None:
    project_id = ProjectID()
    workspace_id = WorkspaceID()
    agent_id = TaskID()
    scope = ScopeAgent(agent_id=agent_id, workspace_id=workspace_id, project_id=project_id)

    deleted_task = Task(
        object_id=agent_id,
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=project_id,
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
            git_hash="abc",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
        is_deleted=True,
    )
    container = TaskMessageContainer(tasks=(deleted_task,), messages=())
    assert _scope_subscribed_entity_was_deleted(scope, [container]) is True

    alive_task = deleted_task.model_copy(update={"is_deleted": False})
    container_alive = TaskMessageContainer(tasks=(alive_task,), messages=())
    assert _scope_subscribed_entity_was_deleted(scope, [container_alive]) is False
