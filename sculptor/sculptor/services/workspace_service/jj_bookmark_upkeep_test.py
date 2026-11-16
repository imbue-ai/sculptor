"""The workspace service's upkeep of a jj workspace's bookmarks, and what it tells the workspace's agents about them.

jj workspaces cannot be created through the service's create path yet, so the
workspace row is written through the service and its checkout built with jj's
seam directly. A service built here is never started, so its poller scans only
when a test asks it to.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.jj_bookmark_facts import JjBookmarkFacts
from sculptor.services.workspace_service.jj_bookmark_facts import JjStackBookmarks
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo

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
            source_branch=f"{jj_colocated_repo.default_bookmark}@origin",
            requested_branch_name=_REQUESTED_BOOKMARK,
            description="jj workspace",
            transaction=transaction,
            target_branch=f"{jj_colocated_repo.default_bookmark}@origin",
        )
        updated = transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_path))
        assert updated is not None
    unstarted_workspace_service.get_workspace_vcs(WorkspaceInitializationStrategy.JJ_WORKSPACE).create_checkout(
        CheckoutSpec(
            repo_path=jj_colocated_repo.path,
            checkout_path=environment_path / "code",
            base_ref=f"{jj_colocated_repo.default_bookmark}@origin",
            new_ref_name=_REQUESTED_BOOKMARK,
            checkout_name=str(workspace.object_id),
        )
    )
    return updated


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
