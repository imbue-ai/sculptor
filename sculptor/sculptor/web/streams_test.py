from unittest.mock import MagicMock

import pytest

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import Project
from sculptor.database.models import UserSettings
from sculptor.database.models import Workspace
from sculptor.database.models import WorkspaceInitializationStrategy
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import UserUpdateSourceTypes
from sculptor.web.streams import LEGACY_SETUP_PLACEHOLDER_BYTES
from sculptor.web.streams import _convert_to_streaming_update
from sculptor.web.streams import _convert_to_user_update
from sculptor.web.streams import _snapshot_setup_state


def test_convert_to_user_update_collects_models_and_overwrites_duplicates() -> None:
    organization = OrganizationReference("org-ref")
    user_reference = UserReference("user-ref")
    project_id = ProjectID()

    initial_project = Project(object_id=project_id, organization_reference=organization, name="Initial")
    updated_project = initial_project.model_copy(update={"name": "Updated"})

    user_settings = UserSettings(
        object_id=UserSettingsID(),
        user_reference=user_reference,
    )

    server_settings = SculptorSettings()

    notification = Notification(
        object_id=NotificationID(),
        user_reference=user_reference,
        message="Streaming notification",
    )

    transactions: list[UserUpdateSourceTypes | None] = [
        None,
        CompletedTransaction(request_id=None, updated_models=(initial_project,)),
        server_settings,
        CompletedTransaction(request_id=None, updated_models=(updated_project, user_settings, notification)),
    ]

    update = _convert_to_user_update(transactions)

    assert update.user_settings == user_settings
    assert update.projects == (updated_project,)
    assert update.settings == server_settings
    assert update.notifications == (notification,)


def test_convert_to_user_update_raises_for_unexpected_models() -> None:
    with pytest.raises(AssertionError):
        # deliberately passes the wrong type to exercise the runtime assertion
        # pyrefly: ignore [bad-argument-type]
        _convert_to_user_update(["unexpected model"])


def _make_terminal_workspace(*, setup_run_id: str | None, setup_log_path: str | None) -> Workspace:
    return Workspace(
        object_id=WorkspaceID(),
        project_id=ProjectID(),
        organization_reference=OrganizationReference("org-1"),
        description="ws",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        environment_id="env-1",
        setup_status="succeeded",
        setup_run_id=setup_run_id,
        setup_log_path=setup_log_path,
    )


def _services_with_workspaces(workspaces: list[Workspace]) -> MagicMock:
    services = MagicMock()
    transaction = services.data_model_service.open_transaction.return_value.__enter__.return_value
    transaction.get_workspaces.return_value = workspaces
    return services


def _empty_runner() -> MagicMock:
    runner = MagicMock()
    runner.iter_states.return_value = []
    return runner


def test_snapshot_emits_synthetic_placeholder_for_migrated_workspaces() -> None:
    """Workspaces backfilled from the legacy PTY-based setup have terminal
    status but no captured log. The snapshot should still emit a chunk with
    a synthetic placeholder so the user can see the run happened.
    """
    workspace = _make_terminal_workspace(setup_run_id=None, setup_log_path=None)

    out = _snapshot_setup_state(services=_services_with_workspaces([workspace]), runner=_empty_runner())

    assert len(out) == 1
    status, chunk = out[0]
    assert status.status == "succeeded"
    assert status.run_id is None
    assert chunk is not None
    assert chunk.data == LEGACY_SETUP_PLACEHOLDER_BYTES
    # The chunk must carry a deterministic synthetic run_id so the frontend
    # can dedupe re-emissions across reconnects.
    assert chunk.run_id == f"persisted-{workspace.object_id}"


def test_snapshot_skips_terminal_workspace_with_known_run_but_lost_log() -> None:
    """A run completed under the new runner (so a run_id is recorded) but the
    log file is gone. This is not a "migrated" workspace — fabricating output
    would be misleading. Skip it.
    """
    workspace = _make_terminal_workspace(setup_run_id="some-run-uuid", setup_log_path=None)

    out = _snapshot_setup_state(services=_services_with_workspaces([workspace]), runner=_empty_runner())

    assert out == []


def _empty_settings() -> SculptorSettings:
    return SculptorSettings()


def test_convert_includes_ui_open_file() -> None:
    workspace_id = WorkspaceID()
    action = OpenFileUiAction(workspace_id=workspace_id, file_path="/tmp/a.txt", mode="auto")
    all_data: list[StreamingUpdateSourceTypes | None] = [action]

    update = _convert_to_streaming_update(
        all_data=all_data,
        task_views_by_task_id={},
        task_update_state_by_task_id={},
        processed_message_by_task_id={},
        settings=_empty_settings(),
    )

    assert update.ui_open_file_by_workspace_id == {workspace_id: action}


def test_convert_ui_open_file_last_write_wins_for_same_workspace() -> None:
    workspace_id = WorkspaceID()
    first = OpenFileUiAction(workspace_id=workspace_id, file_path="/tmp/a.txt", mode="auto")
    second = OpenFileUiAction(workspace_id=workspace_id, file_path="/tmp/b.txt", mode="diff")
    all_data: list[StreamingUpdateSourceTypes | None] = [first, second]

    update = _convert_to_streaming_update(
        all_data=all_data,
        task_views_by_task_id={},
        task_update_state_by_task_id={},
        processed_message_by_task_id={},
        settings=_empty_settings(),
    )

    assert update.ui_open_file_by_workspace_id == {workspace_id: second}


def test_convert_ui_open_file_keeps_distinct_workspaces() -> None:
    workspace_a = WorkspaceID()
    workspace_b = WorkspaceID()
    action_a = OpenFileUiAction(workspace_id=workspace_a, file_path="/tmp/a.txt", mode="auto")
    action_b = OpenFileUiAction(workspace_id=workspace_b, file_path="/tmp/b.txt", mode="file")
    all_data: list[StreamingUpdateSourceTypes | None] = [action_a, action_b]

    update = _convert_to_streaming_update(
        all_data=all_data,
        task_views_by_task_id={},
        task_update_state_by_task_id={},
        processed_message_by_task_id={},
        settings=_empty_settings(),
    )

    assert update.ui_open_file_by_workspace_id == {workspace_a: action_a, workspace_b: action_b}
