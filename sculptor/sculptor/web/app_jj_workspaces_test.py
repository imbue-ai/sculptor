"""The workspace routes for jj workspaces, against a real colocated repository and the real jj.

The checkout of a workspace is created when its first agent starts, so tests that
need one open the workspace's environment through the workspace service.
"""

import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import PrivateAttr

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.foundation.pydantic_serialization import model_dump
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.environment_manager import (
    default_implementation as environment_manager_default_implementation,
)
from sculptor.services.workspace_service.environment_manager.default_implementation import DefaultEnvironmentManager
from sculptor.services.workspace_service.environment_manager.environments import local_environment
from sculptor.services.workspace_service.vcs.data_types import BranchDeletionPolicy
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj
from sculptor.utils.shutdown import GLOBAL_SHUTDOWN_EVENT
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import CreateWorkspaceRequestV2
from sculptor.web.data_types import UpdateWorkspaceRequest


@pytest.fixture(autouse=True)
def _redirect_workspace_checkouts_to_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create environments under `tmp_path`; both environment-manager modules read the directory at import time."""
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir()
    monkeypatch.setattr(environment_manager_default_implementation, "LOCAL_WORKSPACE_DIR", workspaces_dir)
    monkeypatch.setattr(local_environment, "LOCAL_WORKSPACE_DIR", workspaces_dir)


def _resolve_jj_to(jj_value: str) -> None:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(update={"dependency_paths": DependencyPaths(jj=jj_value)})
    )


@pytest.fixture
def jj_resolved_to_the_pinned_binary(jj_binary: JjBinary) -> Iterator[None]:
    _resolve_jj_to(str(jj_binary.path))
    yield
    set_user_config_instance(None)


@pytest.fixture
def jj_not_installed() -> Iterator[None]:
    """jj configured as a custom binary with no path, so none resolves."""
    _resolve_jj_to("CUSTOM")
    yield
    set_user_config_instance(None)


def _register_project(
    test_services: CompleteServiceCollection, repo_path: Path, use_jj_for_new_workspaces: bool
) -> Project:
    """A project for `repo_path` that runs no setup command."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        initialized = test_services.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        assert initialized is not None
        project = transaction.update_project_fields(
            initialized.object_id, use_jj_for_new_workspaces=use_jj_for_new_workspaces, workspace_setup_command=""
        )
    assert project is not None
    return project


@pytest.fixture
def jj_project(
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    test_services: CompleteServiceCollection,
) -> Project:
    """A project for `jj_colocated_repo` that creates jj workspaces."""
    return _register_project(test_services, jj_colocated_repo.path, use_jj_for_new_workspaces=True)


def _post_jj_workspace(
    client: TestClient,
    project: Project,
    requested_branch_name: str | None = "feature",
    source_branch: str | None = None,
    target_branch: str | None = None,
) -> httpx.Response:
    return client.post(
        "/api/v1/workspaces",
        json=model_dump(
            CreateWorkspaceRequestV2(
                project_id=str(project.object_id),
                initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
                source_branch=source_branch,
                requested_branch_name=requested_branch_name,
                target_branch=target_branch,
            ),
            is_camel_case=True,
        ),
    )


def _create_jj_workspace_with_checkout(
    client: TestClient,
    project: Project,
    test_services: CompleteServiceCollection,
    concurrency_group: ConcurrencyGroup,
) -> tuple[WorkspaceID, Path]:
    """Create a jj workspace through the route, then open its environment as its first agent's start does."""
    response = _post_jj_workspace(client, project)
    assert response.status_code == 200, response.text
    workspace_id = WorkspaceID(response.json()["objectId"])
    with concurrency_group.make_concurrency_group("agent_environment") as agent_concurrency_group:
        with test_services.workspace_service.agent_environment_context(
            project=project,
            workspace_id=workspace_id,
            task_id=TaskID(),
            concurrency_group=agent_concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ) as agent_environment:
            return workspace_id, agent_environment.get_working_directory()


def _patch_target(client: TestClient, workspace_id: WorkspaceID, target_branch: str) -> httpx.Response:
    return client.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json=model_dump(UpdateWorkspaceRequest(target_branch=target_branch), is_camel_case=True),
    )


def _list_workspace_strategies(test_services: CompleteServiceCollection) -> list[WorkspaceInitializationStrategy]:
    with test_services.data_model_service.open_transaction(RequestID()) as transaction:
        return [workspace.initialization_strategy for workspace in transaction.get_workspaces()]


def _detail(response: httpx.Response) -> Any:
    return response.json()["detail"]


def test_creating_a_jj_workspace_needs_jj_to_be_available(
    jj_not_installed: None,
    client: TestClient,
    jj_colocated_repo: JjColocatedRepo,
    test_services: CompleteServiceCollection,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path, use_jj_for_new_workspaces=True)

    response = _post_jj_workspace(client, project)

    assert response.status_code == 412, response.text
    assert "jj is not installed" in _detail(response)
    assert _list_workspace_strategies(test_services) == []


def test_creating_a_jj_workspace_needs_the_repository_to_create_jj_workspaces(
    jj_resolved_to_the_pinned_binary: None,
    client: TestClient,
    jj_colocated_repo: JjColocatedRepo,
    test_services: CompleteServiceCollection,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path, use_jj_for_new_workspaces=False)

    response = _post_jj_workspace(client, project)

    assert response.status_code == 400, response.text
    assert "does not create jj workspaces" in _detail(response)


def test_creating_a_jj_workspace_needs_a_colocated_repository(
    jj_resolved_to_the_pinned_binary: None,
    client: TestClient,
    test_project: Project,
    test_services: CompleteServiceCollection,
) -> None:
    """The flag alone is not enough: a plain git repository creates no jj workspaces."""
    project = _register_project(test_services, test_project.get_local_user_path(), use_jj_for_new_workspaces=True)

    response = _post_jj_workspace(client, project)

    assert response.status_code == 400, response.text
    assert "does not create jj workspaces" in _detail(response)


@pytest.mark.parametrize(
    ("requested_branch_name", "expected_status", "expected_detail"),
    [
        pytest.param(None, 400, "requested_branch_name is required for JJ_WORKSPACE workspaces", id="no-name"),
        pytest.param("  ", 400, "requested_branch_name is required for JJ_WORKSPACE workspaces", id="blank-name"),
        pytest.param("has space", 400, "'has space' is not a valid bookmark name", id="illegal-name"),
        pytest.param("feature@origin", 400, "'feature@origin' is not a valid bookmark name", id="remote-symbol"),
        pytest.param("main", 409, "A bookmark named 'main' already exists", id="existing-bookmark"),
    ],
)
def test_creating_a_jj_workspace_checks_its_bookmark_name(
    client: TestClient,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    requested_branch_name: str | None,
    expected_status: int,
    expected_detail: str,
) -> None:
    response = _post_jj_workspace(client, jj_project, requested_branch_name=requested_branch_name)

    assert response.status_code == expected_status, response.text
    assert expected_detail in _detail(response)
    assert _list_workspace_strategies(test_services) == []


def test_creating_a_jj_workspace_refuses_a_base_that_names_no_bookmark_or_commit(
    client: TestClient, jj_project: Project, test_services: CompleteServiceCollection
) -> None:
    """git's `origin/main` is not a jj symbol; jj spells it `main@origin`."""
    response = _post_jj_workspace(client, jj_project, source_branch="origin/main")

    assert response.status_code == 400, response.text
    assert "'origin/main' names no bookmark or commit" in _detail(response)
    assert _list_workspace_strategies(test_services) == []


def test_a_jj_workspace_is_created_on_the_trunk_bookmark_by_default(
    client: TestClient,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
) -> None:
    response = _post_jj_workspace(client, jj_project)

    assert response.status_code == 200, response.text
    body = response.json()
    trunk = f"{jj_colocated_repo.default_bookmark}@origin"
    assert body["initializationStrategy"] == "JJ_WORKSPACE"
    assert (body["sourceBranch"], body["targetBranch"]) == (trunk, trunk)
    assert body["requestedBranchName"] == "feature"
    # Creating the row creates no jj workspace: the checkout comes with the first agent.
    workspace_names = run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=jj_colocated_repo.path)
    assert workspace_names.split() == ["default"]


def test_the_name_preview_for_a_jj_workspace_takes_the_user_from_jj(
    client: TestClient, jj_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """jj and git can name the user differently, and a bookmark name follows jj."""
    monkeypatch.setenv("JJ_USER", "Jordan Bookmarker")

    previews = {
        mode: client.get(
            "/api/v1/workspaces/preview-branch-name",
            params={"project_id": str(jj_project.object_id), "mode": mode, "workspace_name": "Fix the parser"},
        )
        for mode in ("WORKTREE", "JJ_WORKSPACE")
    }

    assert {mode: response.json()["branchName"] for mode, response in previews.items()} == {
        "WORKTREE": "sculptor/fix-the-parser",
        "JJ_WORKSPACE": "jordan/fix-the-parser",
    }


def test_a_jj_workspace_target_changes_only_to_a_bookmark_the_repository_lists(
    client: TestClient,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    workspace_id, _ = _create_jj_workspace_with_checkout(
        client, jj_project, test_services, test_root_concurrency_group
    )

    accepted = _patch_target(client, workspace_id, "main")
    refused = _patch_target(client, workspace_id, "origin/main")

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["targetBranch"] == "main"
    assert refused.status_code == 400, refused.text
    assert "'origin/main' is not a bookmark" in _detail(refused)
    assert client.get(f"/api/v1/workspaces/{workspace_id}").json()["targetBranch"] == "main"


def _get_ok(client: TestClient, url: str, **params: str) -> Any:
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _post_ok(client: TestClient, url: str, body: dict[str, str]) -> Any:
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_an_agents_file_change_in_a_jj_workspace_reaches_every_data_route_and_can_be_discarded(
    client: TestClient,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    workspace_id, checkout = _create_jj_workspace_with_checkout(
        client, jj_project, test_services, test_root_concurrency_group
    )
    workspace_url = f"/api/v1/workspaces/{workspace_id}"
    (checkout / "parser.py").write_text("parse = None\n")
    (checkout / "README.md").write_text("# edited by the agent\n")

    diff = _get_ok(client, f"{workspace_url}/diff", force_refresh="true", scope="vs-target-branch")["diff"]
    files = [entry["path"] for entry in _get_ok(client, f"{workspace_url}/files")["files"]]
    working_copy, *older_revisions = _get_ok(client, f"{workspace_url}/revisions")["revisions"]
    commit_diff = _get_ok(client, f"{workspace_url}/commit-diff", commit_hash=working_copy["commitId"])
    readme_at_base = _post_ok(
        client, f"{workspace_url}/read-file-at-ref", {"path": "README.md", "gitRef": diff["uncommittedDiffBase"]}
    )

    assert "+parse = None" in diff["uncommittedDiff"]
    assert "+parse = None" in diff["targetBranchDiff"]
    assert diff["uncommittedDiffBase"] == _read_jj(jj_binary, jj_colocated_repo.path, "main@origin")
    assert {"parser.py", "README.md"} <= set(files)
    assert older_revisions == []
    assert working_copy["isWorkingCopy"] is True
    assert {file["path"] for file in working_copy["files"]} == {"parser.py", "README.md"}
    assert "+parse = None" in commit_diff["diff"]
    assert commit_diff["parentHash"] == diff["uncommittedDiffBase"]
    assert readme_at_base["content"] == "# jj fixture repo\n"

    discarded = _post_ok(client, f"{workspace_url}/discard-file", {"filePath": "parser.py"})
    diff_after_discard = _get_ok(client, f"{workspace_url}/diff", force_refresh="true")["diff"]

    assert discarded["result"]["success"] is True
    assert not (checkout / "parser.py").exists()
    assert "parser.py" not in diff_after_discard["uncommittedDiff"]
    assert "README.md" in diff_after_discard["uncommittedDiff"]


def _read_jj(jj_binary: JjBinary, repo_path: Path, revision: str) -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revision, "-T", "commit_id"), cwd=repo_path
    ).strip()


def test_the_jj_data_routes_refuse_a_git_revision_name(
    client: TestClient,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """A jj workspace has no `HEAD`, and its revisions are named by full commit id only."""
    workspace_id, _ = _create_jj_workspace_with_checkout(
        client, jj_project, test_services, test_root_concurrency_group
    )
    workspace_url = f"/api/v1/workspaces/{workspace_id}"

    commit_diff = client.get(f"{workspace_url}/commit-diff", params={"commit_hash": "HEAD"})
    file_at_ref = client.post(f"{workspace_url}/read-file-at-ref", json={"path": "README.md", "gitRef": "HEAD"})

    assert commit_diff.status_code == 400, commit_diff.text
    assert file_at_ref.status_code == 404, file_at_ref.text


def test_turning_the_repository_switch_off_leaves_an_existing_jj_workspace_working(
    client: TestClient,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    workspace_id, checkout = _create_jj_workspace_with_checkout(
        client, jj_project, test_services, test_root_concurrency_group
    )
    with test_services.data_model_service.open_transaction(RequestID()) as transaction:
        transaction.update_project_fields(jj_project.object_id, use_jj_for_new_workspaces=False)
        project_with_switch_off = transaction.get_project(jj_project.object_id)
    assert project_with_switch_off is not None

    with test_root_concurrency_group.make_concurrency_group("agent_environment") as agent_concurrency_group:
        with test_services.workspace_service.agent_environment_context(
            project=project_with_switch_off,
            workspace_id=workspace_id,
            task_id=TaskID(),
            concurrency_group=agent_concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ) as resumed_environment:
            assert resumed_environment.get_working_directory() == checkout
    (checkout / "parser.py").write_text("parse = None\n")
    diff = _get_ok(client, f"/api/v1/workspaces/{workspace_id}/diff", force_refresh="true")["diff"]
    new_workspace = _post_jj_workspace(client, project_with_switch_off, requested_branch_name="another-feature")

    assert "+parse = None" in diff["uncommittedDiff"]
    assert _get_ok(client, f"/api/v1/workspaces/{workspace_id}")["initializationStrategy"] == "JJ_WORKSPACE"
    assert new_workspace.status_code == 400, new_workspace.text


class _TeardownSignallingEnvironmentManager(DefaultEnvironmentManager):
    """Signals once a deleted workspace's environment directory is gone; deletion finishes on a background thread."""

    _teardown_done: threading.Event = PrivateAttr(default_factory=threading.Event)

    def delete_environment(self, environment_id: str) -> None:
        super().delete_environment(environment_id)
        self._teardown_done.set()


def _list_jj_workspace_names(jj_binary: JjBinary, repo_path: Path) -> list[str]:
    return run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=repo_path).split()


def _list_local_bookmark_names(jj_binary: JjBinary, repo_path: Path) -> list[str]:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "bookmark", "list", "-T", 'name ++ "\\n"'), cwd=repo_path
    ).split()


@pytest.mark.parametrize(
    ("deletion_policy", "is_bookmark_kept"),
    [pytest.param("never", True, id="never"), pytest.param("always", False, id="always")],
)
def test_deleting_a_jj_workspace_forgets_it_and_applies_the_deletion_policy_to_its_bookmark(
    client: TestClient,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_services: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    deletion_policy: BranchDeletionPolicy,
    is_bookmark_kept: bool,
) -> None:
    workspace_id, checkout = _create_jj_workspace_with_checkout(
        client, jj_project, test_services, test_root_concurrency_group
    )
    (checkout / "parser.py").write_text("parse = None\n")
    run_jj(jj_binary, ("describe", "-m", "add the parser"), cwd=checkout)
    run_jj(jj_binary, ("bookmark", "create", "feature", "-r", "@"), cwd=checkout)
    workspace_config_directory = Path(
        run_jj(jj_binary, ("config", "path", "--workspace"), cwd=checkout).strip()
    ).parent
    set_user_config_instance(
        get_user_config_instance().model_copy(update={"workspace_branch_deletion_policy": deletion_policy})
    )
    workspace_service = test_services.workspace_service
    assert isinstance(workspace_service, DefaultWorkspaceService)
    existing_manager = workspace_service.environment_manager
    assert isinstance(existing_manager, DefaultEnvironmentManager)
    signalling_manager = _TeardownSignallingEnvironmentManager(data_model_service=existing_manager.data_model_service)
    workspace_service.environment_manager = signalling_manager

    response = client.delete(f"/api/v1/workspaces/{workspace_id}")

    assert response.status_code == 200, response.text
    assert signalling_manager._teardown_done.wait(timeout=30.0), "environment teardown never ran"
    assert not checkout.exists()
    assert str(workspace_id) not in _list_jj_workspace_names(jj_binary, jj_colocated_repo.path)
    assert not workspace_config_directory.exists()
    assert ("feature" in _list_local_bookmark_names(jj_binary, jj_colocated_repo.path)) == is_bookmark_kept


@pytest.fixture
def orphaned_jj_workspace_name(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_project: Project, tmp_path: Path
) -> str:
    """A jj workspace named like a Sculptor workspace that this database does not have, and whose directory is gone."""
    name = str(WorkspaceID())
    lost_environment = tmp_path / "lost-environment"
    lost_environment.mkdir()
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", name, "-r", "main", str(lost_environment / "code")),
        cwd=jj_colocated_repo.path,
    )
    shutil.rmtree(lost_environment)
    return name


def test_startup_forgets_a_jj_workspace_whose_sculptor_workspace_and_directory_are_gone(
    orphaned_jj_workspace_name: str, client: TestClient, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    """The orphan exists before `client` starts the app, whose startup forgets it."""
    assert _list_jj_workspace_names(jj_binary, jj_colocated_repo.path) == ["default"]
