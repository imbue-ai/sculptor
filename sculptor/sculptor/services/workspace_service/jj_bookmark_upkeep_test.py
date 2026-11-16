"""The workspace service's upkeep of a jj workspace's bookmarks, and what it tells the workspace's agents about them.

A service built here is never started, so its poller scans only when a test
asks it to.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Workspace
from sculptor.foundation.async_monkey_patches_test import record_logged_error_levels
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.jj_bookmark_facts import JjBookmarkFacts
from sculptor.services.workspace_service.jj_bookmark_facts import JjStackBookmarks
from sculptor.services.workspace_service.vcs.jj_data_types import JjInitialBookmarkOutcome
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.jj_workspace_rows import create_jj_workspace_row

_REQUESTED_BOOKMARK = "dev/graph-view"


@pytest.fixture
def jj_resolved_to_the_pinned_binary(jj_binary: JjBinary) -> Iterator[None]:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(
            update={"dependency_paths": DependencyPaths(jj=str(jj_binary.path))}
        )
    )
    yield
    set_user_config_instance(None)


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
    """A jj workspace of `jj_colocated_repo` that requested `_REQUESTED_BOOKMARK`, with its checkout built."""
    return create_jj_workspace_row(
        test_service_collection.data_model_service,
        test_service_collection.project_service,
        unstarted_workspace_service,
        jj_colocated_repo,
        tmp_path / "environment",
        _REQUESTED_BOOKMARK,
    )


def test_the_jj_bookmark_facts_carry_the_requested_bookmark_and_the_cached_jj_state(
    unstarted_workspace_service: DefaultWorkspaceService, jj_workspace_row: Workspace
) -> None:
    provider = unstarted_workspace_service.make_jj_bookmark_facts_provider(jj_workspace_row.object_id)
    before_scan = provider.get_jj_bookmark_facts()
    unstarted_workspace_service._jj_workspace_poller._scan_once()
    after_scan = provider.get_jj_bookmark_facts()

    cached_state = unstarted_workspace_service.get_cached_jj_state(jj_workspace_row.object_id)
    assert cached_state is not None
    assert (before_scan.requested_bookmark, before_scan.stack) == (_REQUESTED_BOOKMARK, None)
    assert after_scan == JjBookmarkFacts(
        requested_bookmark=_REQUESTED_BOOKMARK,
        stack=JjStackBookmarks(
            working_copy_change_id=cached_state.working_copy_change_id,
            bookmarks=(),
            primary_bookmark=None,
            unbookmarked_revision_count=0,
        ),
    )


def test_the_jj_bookmark_facts_of_a_missing_workspace_have_no_requested_bookmark(
    unstarted_workspace_service: DefaultWorkspaceService,
) -> None:
    facts = unstarted_workspace_service.make_jj_bookmark_facts_provider(WorkspaceID()).get_jj_bookmark_facts()

    assert facts == JjBookmarkFacts(requested_bookmark=None, stack=None)


def _checkout(workspace: Workspace) -> Path:
    assert workspace.environment_id is not None
    return Path(workspace.environment_id) / "code"


def _commit_change(jj_binary: JjBinary, checkout: Path, message: str) -> None:
    (checkout / f"{uuid4().hex}.txt").write_text(message)
    run_jj(jj_binary, ("commit", "-m", message), cwd=checkout)


def test_attempt_initial_bookmark_creates_the_requested_bookmark_and_publishes_it_at_once(
    unstarted_workspace_service: DefaultWorkspaceService, jj_workspace_row: Workspace, jj_binary: JjBinary
) -> None:
    unstarted_workspace_service._jj_workspace_poller._scan_once()
    _commit_change(jj_binary, _checkout(jj_workspace_row), "first")

    outcome = unstarted_workspace_service.attempt_initial_bookmark(jj_workspace_row.object_id)

    assert outcome is JjInitialBookmarkOutcome.CREATED
    state = unstarted_workspace_service.get_cached_jj_state(jj_workspace_row.object_id)
    assert state is not None
    assert (state.bookmarks, state.primary_bookmark, state.unbookmarked_revision_count) == (
        (_REQUESTED_BOOKMARK,),
        _REQUESTED_BOOKMARK,
        0,
    )


def test_attempt_initial_bookmark_leaves_a_workspace_whose_published_state_has_a_bookmark(
    unstarted_workspace_service: DefaultWorkspaceService, jj_workspace_row: Workspace, jj_binary: JjBinary
) -> None:
    checkout = _checkout(jj_workspace_row)
    _commit_change(jj_binary, checkout, "first")
    run_jj(jj_binary, ("bookmark", "create", "mine", "-r", "@-"), cwd=checkout)
    unstarted_workspace_service._jj_workspace_poller._scan_once()

    outcome = unstarted_workspace_service.attempt_initial_bookmark(jj_workspace_row.object_id)

    assert outcome is None


def test_attempt_initial_bookmark_marks_a_stale_workspace_stale_and_creates_nothing(
    unstarted_workspace_service: DefaultWorkspaceService,
    jj_workspace_row: Workspace,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    unstarted_workspace_service._jj_workspace_poller._scan_once()
    checkout = _checkout(jj_workspace_row)
    _commit_change(jj_binary, checkout, "first")
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout)

    with record_logged_error_levels() as logged_error_levels:
        outcome = unstarted_workspace_service.attempt_initial_bookmark(jj_workspace_row.object_id)

    assert outcome is None
    assert logged_error_levels == []
    state = unstarted_workspace_service.get_cached_jj_state(jj_workspace_row.object_id)
    assert state is not None
    assert state.is_working_copy_stale
    assert state.bookmarks == ()


def test_attempt_initial_bookmark_does_nothing_for_a_missing_workspace(
    unstarted_workspace_service: DefaultWorkspaceService,
) -> None:
    assert unstarted_workspace_service.attempt_initial_bookmark(WorkspaceID()) is None
