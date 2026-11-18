"""Routes that serve a jj workspace's own data, and the git routes that refuse one.

The fixture writes the workspace row through the workspace service and builds
its checkout with jj directly, so these tests do not depend on how jj
workspaces are created.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj
from sculptor.web.auth import authenticate_anonymous


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


def _create_in_place_workspace(test_services: CompleteServiceCollection, project: Project) -> Workspace:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        return test_services.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="git workspace",
            transaction=transaction,
        )


def _read_jj(jj_binary: JjBinary, directory: Path, revision: str, template: str) -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revision, "-T", template), cwd=directory
    ).strip()


def test_the_revisions_of_a_jj_workspace_run_newest_first_from_its_fork_point(
    client: TestClient,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace_row: Workspace,
) -> None:
    assert jj_workspace_row.environment_id is not None
    checkout = Path(jj_workspace_row.environment_id) / "code"
    (checkout / "parser.py").write_text("parse = None\n")
    run_jj(jj_binary, ("describe", "-m", "add the parser"), cwd=checkout)
    run_jj(jj_binary, ("new",), cwd=checkout)
    run_jj(jj_binary, ("bookmark", "create", "-r", "@-", "feature"), cwd=checkout)
    fork_point = _read_jj(
        jj_binary, jj_colocated_repo.path, f"{jj_colocated_repo.default_bookmark}@origin", "commit_id"
    )

    response = client.get(f"/api/v1/workspaces/{jj_workspace_row.object_id}/revisions")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["forkPoint"] == fork_point
    working_copy, described = body["revisions"]
    assert (working_copy["isWorkingCopy"], working_copy["isEmpty"]) == (True, True)
    assert working_copy["parentCommitIds"] == [described["commitId"]]
    assert described["description"] == "add the parser"
    assert described["bookmarks"] == ["feature"]
    assert described["parentCommitIds"] == [fork_point]
    assert described["files"] == [
        {"path": "parser.py", "status": "A", "oldPath": None, "additions": 1, "deletions": 0}
    ]
    assert (described["isWorkingCopy"], described["isEmpty"]) == (False, False)
    assert (described["hasConflict"], described["isDivergent"]) == (False, False)
    assert described["changeId"] == _read_jj(jj_binary, checkout, "@-", "change_id")
    prefix = _read_jj(jj_binary, checkout, "@-", "change_id.shortest().prefix()")
    assert described["changeIdPrefixLength"] == len(prefix)


def test_the_revisions_of_a_git_workspace_conflict(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    workspace = _create_in_place_workspace(test_services, test_project)

    response = client.get(f"/api/v1/workspaces/{workspace.object_id}/revisions")

    assert response.status_code == 409, response.text
    assert "commits" in response.json()["detail"]


def test_the_revisions_of_an_unknown_workspace_are_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/workspaces/{WorkspaceID()}/revisions")

    assert response.status_code == 404, response.text


def test_the_commits_of_a_jj_workspace_conflict(client: TestClient, jj_workspace_row: Workspace) -> None:
    response = client.get(f"/api/v1/workspaces/{jj_workspace_row.object_id}/commits")

    assert response.status_code == 409, response.text
    assert "revisions" in response.json()["detail"]
