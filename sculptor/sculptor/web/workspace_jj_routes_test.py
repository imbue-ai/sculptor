"""Routes that serve a jj workspace's own data, and the git routes that refuse one.

jj workspaces cannot be created through any route yet, so the workspace row is
written through the workspace service and its checkout built with jj directly.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.web.auth import authenticate_anonymous


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
def jj_workspace_row(
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> Workspace:
    """A jj workspace of `jj_colocated_repo`, starting from its default bookmark, with its checkout built."""
    user_session = authenticate_anonymous(test_services, RequestID())
    environment_path = tmp_path / "environment"
    with user_session.open_transaction(test_services) as transaction:
        project = test_services.project_service.initialize_project(
            project_path=jj_colocated_repo.path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        assert project is not None
        workspace = test_services.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
            source_branch=jj_colocated_repo.default_bookmark,
            requested_branch_name=None,
            description="jj workspace",
            transaction=transaction,
        )
        updated = transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_path))
        assert updated is not None
    test_services.workspace_service.get_workspace_vcs(WorkspaceInitializationStrategy.JJ_WORKSPACE).create_checkout(
        CheckoutSpec(
            repo_path=jj_colocated_repo.path,
            checkout_path=environment_path / "code",
            base_ref=jj_colocated_repo.default_bookmark,
            new_ref_name=None,
            checkout_name=str(workspace.object_id),
        )
    )
    return updated


def test_the_commits_of_a_jj_workspace_conflict(client: TestClient, jj_workspace_row: Workspace) -> None:
    response = client.get(f"/api/v1/workspaces/{jj_workspace_row.object_id}/commits")

    assert response.status_code == 409, response.text
    assert "revisions" in response.json()["detail"]
