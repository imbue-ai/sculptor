"""The workspace service's jj workspace state: its poller, its cache and its stale working-copy marks.

jj workspaces cannot be created through the service's create path yet, so the
workspace row is written through the service and its checkout built with jj's
seam directly. A service built here is never started, so its poller scans only
when a test asks it to.
"""

from collections.abc import Iterator
from pathlib import Path
from queue import Queue

import pytest

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches_test import record_logged_error_levels
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceJjStateInfo


@pytest.fixture
def unstarted_workspace_service(
    test_service_collection: CompleteServiceCollection, test_root_concurrency_group: ConcurrencyGroup
) -> Iterator[DefaultWorkspaceService]:
    """A workspace service whose processes can run but whose pollers never start."""
    service = DefaultWorkspaceService.build(
        concurrency_group=test_root_concurrency_group,
        settings=test_service_collection.settings,
        data_model_service=test_service_collection.data_model_service,
        project_service=test_service_collection.project_service,
        dependency_management_service=test_service_collection.dependency_management_service,
    )
    with service.concurrency_group:
        yield service


@pytest.fixture
def jj_workspace_row(
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    test_service_collection: CompleteServiceCollection,
    unstarted_workspace_service: DefaultWorkspaceService,
    tmp_path: Path,
) -> Workspace:
    """A jj workspace of `jj_colocated_repo`, starting from its default bookmark, with its checkout built."""
    environment_path = tmp_path / "environment"
    with test_service_collection.data_model_service.open_transaction(RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=jj_colocated_repo.path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        assert project is not None
        workspace = unstarted_workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
            source_branch=jj_colocated_repo.default_bookmark,
            requested_branch_name=None,
            description="jj workspace",
            transaction=transaction,
        )
        updated = transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_path))
        assert updated is not None
    unstarted_workspace_service.get_workspace_vcs(WorkspaceInitializationStrategy.JJ_WORKSPACE).create_checkout(
        CheckoutSpec(
            repo_path=jj_colocated_repo.path,
            checkout_path=environment_path / "code",
            base_ref=jj_colocated_repo.default_bookmark,
            new_ref_name=None,
            checkout_name=str(workspace.object_id),
        )
    )
    return updated


def _checkout(workspace: Workspace) -> Path:
    assert workspace.environment_id is not None
    return Path(workspace.environment_id) / "code"


def _scan_for_state(service: DefaultWorkspaceService, workspace_id: WorkspaceID) -> WorkspaceJjStateInfo:
    service._jj_workspace_poller._scan_once()
    state = service.get_cached_jj_state(workspace_id)
    assert state is not None
    return state


def test_a_jj_workspaces_state_reaches_the_services_observers_and_its_cache(
    unstarted_workspace_service: DefaultWorkspaceService, jj_workspace_row: Workspace
) -> None:
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    unstarted_workspace_service.add_observer(queue)

    state = _scan_for_state(unstarted_workspace_service, jj_workspace_row.object_id)

    published: list[StreamingUpdateSourceTypes] = []
    while not queue.empty():
        published.append(queue.get_nowait())
    assert [item for item in published if isinstance(item, WorkspaceJjStateInfo)] == [state]
    assert (state.workspace_id, state.is_working_copy_empty, state.is_working_copy_stale) == (
        jj_workspace_row.object_id,
        True,
        False,
    )


def test_get_cached_jj_state_does_not_create_the_jj_poller(
    unstarted_workspace_service: DefaultWorkspaceService,
) -> None:
    assert unstarted_workspace_service.get_cached_jj_state(WorkspaceID()) is None
    assert unstarted_workspace_service._jj_workspace_poller_instance is None


def test_a_diff_refresh_that_finds_the_working_copy_stale_marks_it_and_a_later_refresh_clears_it(
    unstarted_workspace_service: DefaultWorkspaceService,
    jj_workspace_row: Workspace,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    workspace_id = jj_workspace_row.object_id
    make_workspace_stale(jj_binary, jj_colocated_repo.path, _checkout(jj_workspace_row))

    with pytest.raises(JjWorkingCopyStaleError):
        unstarted_workspace_service.refresh_workspace_diff(workspace_id)
    marked = _scan_for_state(unstarted_workspace_service, workspace_id)
    run_jj(jj_binary, ("workspace", "update-stale"), cwd=_checkout(jj_workspace_row))
    unstarted_workspace_service.refresh_workspace_diff(workspace_id)
    cleared = _scan_for_state(unstarted_workspace_service, workspace_id)

    assert marked.is_working_copy_stale
    assert not cleared.is_working_copy_stale


def test_reading_the_revisions_of_a_stale_workspace_marks_it_stale(
    unstarted_workspace_service: DefaultWorkspaceService,
    test_service_collection: CompleteServiceCollection,
    jj_workspace_row: Workspace,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    workspace_id = jj_workspace_row.object_id
    make_workspace_stale(jj_binary, jj_colocated_repo.path, _checkout(jj_workspace_row))

    with test_service_collection.data_model_service.open_transaction(RequestID()) as transaction:
        with pytest.raises(JjWorkingCopyStaleError):
            unstarted_workspace_service.get_revision_history(workspace_id, transaction)

    assert _scan_for_state(unstarted_workspace_service, workspace_id).is_working_copy_stale


def test_the_jj_poller_rests_quietly_while_the_published_jj_readiness_has_a_blocker(
    unstarted_workspace_service: DefaultWorkspaceService,
    test_service_collection: CompleteServiceCollection,
    jj_workspace_row: Workspace,
    jj_binary: JjBinary,
    tmp_path: Path,
) -> None:
    poller = unstarted_workspace_service._jj_workspace_poller
    dependency_management_service = test_service_collection.dependency_management_service
    _point_jj_at(tmp_path / "missing" / "jj")
    dependency_management_service.get_status()

    with record_logged_error_levels() as levels:
        poller._scan_once()
    state_while_unavailable = unstarted_workspace_service.get_cached_jj_state(jj_workspace_row.object_id)
    _point_jj_at(jj_binary.path)
    dependency_management_service.get_status()

    assert (state_while_unavailable, levels) == (None, [])
    assert _scan_for_state(unstarted_workspace_service, jj_workspace_row.object_id).is_working_copy_empty


def _point_jj_at(binary: Path) -> None:
    """Resolve jj to `binary`, keeping the rest of the configuration the test runs with."""
    config = get_user_config_instance()
    dependency_paths = config.dependency_paths.model_copy(update={"jj": str(binary)})
    set_user_config_instance(config.model_copy(update={"dependency_paths": dependency_paths}))
