"""The routes for a repository's jj configuration, against real git and jj repositories and no network."""

import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from queue import Empty
from queue import Queue

import httpx
import pytest
from fastapi.testclient import TestClient

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Project
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.jj_availability import describe_jj_unavailability
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import run_jj
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjColocationState
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import ProjectJjState
from sculptor.web.data_types import StreamingUpdateSourceTypes

_STATE_TIMEOUT_SECONDS = 30.0
# What every route answers while jj resolves to nothing, as `jj_unavailable` arranges.
_JJ_NOT_INSTALLED_REASON = describe_jj_unavailability(JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED))


def _resolve_jj_to(jj_value: str) -> None:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(update={"dependency_paths": DependencyPaths(jj=jj_value)})
    )


@pytest.fixture
def jj_available(jj_binary: JjBinary) -> Iterator[None]:
    _resolve_jj_to(str(jj_binary.path))
    yield
    set_user_config_instance(None)


@pytest.fixture
def jj_unavailable() -> Iterator[None]:
    _resolve_jj_to("CUSTOM")
    yield
    set_user_config_instance(None)


@pytest.fixture
def git_repo(jj_isolated_env: JjIsolatedEnv, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_blocking(["git", "init", "-q", "-b", "main"], cwd=repo)
    (repo / "file.txt").write_text("first\n")
    run_blocking(["git", "add", "file.txt"], cwd=repo)
    run_blocking(["git", "commit", "-q", "-m", "init"], cwd=repo)
    return repo


@pytest.fixture
def published_states(test_services: CompleteServiceCollection) -> Iterator[Queue[StreamingUpdateSourceTypes]]:
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    test_services.project_jj_state_service.add_observer(queue)
    yield queue
    test_services.project_jj_state_service.remove_observer(queue)


def _register_project(test_services: CompleteServiceCollection, repo_path: Path) -> Project:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = test_services.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
    test_services.project_service.activate_project(project)
    return project


def _store_use_jj_for_new_workspaces(test_services: CompleteServiceCollection, project: Project, value: bool) -> None:
    with test_services.data_model_service.open_transaction(RequestID()) as transaction:
        transaction.update_project_fields(project.object_id, use_jj_for_new_workspaces=value)


def _read_use_jj_for_new_workspaces(test_services: CompleteServiceCollection, project: Project) -> bool:
    with test_services.data_model_service.open_transaction(RequestID()) as transaction:
        stored = transaction.get_project(project.object_id)
    assert stored is not None
    return stored.use_jj_for_new_workspaces


def _wait_for_state(queue: Queue[StreamingUpdateSourceTypes], expected: ProjectJjState) -> None:
    deadline = time.monotonic() + _STATE_TIMEOUT_SECONDS
    seen: list[StreamingUpdateSourceTypes] = []
    while time.monotonic() < deadline:
        try:
            published = queue.get(timeout=max(deadline - time.monotonic(), 0.0))
        except Empty:
            break
        if published == expected:
            return
        seen.append(published)
    raise AssertionError(f"{expected} was never published; published instead: {seen}")


def _colocated_state(project: Project, creates_jj_workspaces: bool) -> ProjectJjState:
    return ProjectJjState(
        project_id=project.object_id,
        colocation=JjColocationState.COLOCATED,
        colocation_error=None,
        creates_jj_workspaces=creates_jj_workspaces,
    )


def _put_use_jj_for_new_workspaces(client: TestClient, project_id: ProjectID, value: bool) -> httpx.Response:
    return client.put(
        f"/api/v1/projects/{project_id}/use_jj_for_new_workspaces",
        json={"requestId": str(RequestID()), "useJjForNewWorkspaces": value},
    )


def test_the_preflight_lists_a_repository_s_blockers_warnings_and_uncommitted_changes(
    jj_available: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    (git_repo / ".gitmodules").write_text('[submodule "vendor"]\n\tpath = vendor\n\turl = ../vendor\n')
    (git_repo / ".husky").mkdir()
    project = _register_project(test_services, git_repo)

    response = client.get(f"/api/v1/projects/{project.object_id}/jj")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "blockers": ["SUBMODULES"],
        "warnings": ["HOOKS"],
        "hasUncommittedChanges": True,
        "jjUnavailableReason": None,
    }


def test_the_preflight_while_jj_is_unavailable_gives_the_reason_the_colocate_refusal_gives(
    jj_unavailable: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    project = _register_project(test_services, git_repo)

    preflight = client.get(f"/api/v1/projects/{project.object_id}/jj").json()
    refusal = client.post(f"/api/v1/projects/{project.object_id}/jj/colocate")

    assert refusal.status_code == 412, refusal.text
    assert preflight["blockers"] == ["JJ_UNAVAILABLE"]
    assert preflight["jjUnavailableReason"] == refusal.json()["detail"] == _JJ_NOT_INSTALLED_REASON


def test_reading_the_preflight_derives_the_repository_s_streamed_state_from_disk_again(
    jj_available: None,
    client: TestClient,
    test_services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path)
    assert _put_use_jj_for_new_workspaces(client, project.object_id, True).status_code == 200
    _wait_for_state(published_states, _colocated_state(project, creates_jj_workspaces=True))
    shutil.rmtree(jj_colocated_repo.path / ".jj")

    response = client.get(f"/api/v1/projects/{project.object_id}/jj")

    assert response.status_code == 200, response.text
    _wait_for_state(
        published_states,
        ProjectJjState(
            project_id=project.object_id,
            colocation=JjColocationState.ABSENT,
            colocation_error=None,
            creates_jj_workspaces=False,
        ),
    )
    assert _read_use_jj_for_new_workspaces(test_services, project) is False


def test_the_preflight_of_an_unknown_project_is_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/projects/{ProjectID()}/jj")

    assert response.status_code == 404, response.text


def test_colocating_answers_202_and_the_repository_becomes_a_colocation_that_creates_jj_workspaces(
    jj_available: None,
    client: TestClient,
    test_services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    git_repo: Path,
) -> None:
    project = _register_project(test_services, git_repo)

    response = client.post(f"/api/v1/projects/{project.object_id}/jj/colocate")

    assert response.status_code == 202, response.text
    _wait_for_state(published_states, _colocated_state(project, creates_jj_workspaces=True))
    assert _read_use_jj_for_new_workspaces(test_services, project) is True


def test_colocating_without_jj_is_a_failed_precondition(
    jj_unavailable: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    project = _register_project(test_services, git_repo)

    response = client.post(f"/api/v1/projects/{project.object_id}/jj/colocate")

    assert response.status_code == 412, response.text
    assert response.json()["detail"] == _JJ_NOT_INSTALLED_REASON
    assert not (git_repo / ".jj").exists()


def test_colocating_a_repository_with_a_blocker_conflicts(
    jj_available: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    (git_repo / ".gitmodules").write_text('[submodule "vendor"]\n\tpath = vendor\n\turl = ../vendor\n')
    project = _register_project(test_services, git_repo)

    response = client.post(f"/api/v1/projects/{project.object_id}/jj/colocate")

    assert response.status_code == 409, response.text
    assert "SUBMODULES" in response.json()["detail"]
    assert not (git_repo / ".jj").exists()


def test_colocating_an_unknown_project_is_not_found(jj_available: None, client: TestClient) -> None:
    response = client.post(f"/api/v1/projects/{ProjectID()}/jj/colocate")

    assert response.status_code == 404, response.text


def test_turning_use_jj_for_new_workspaces_on_in_a_colocated_repository_stores_it(
    jj_available: None,
    client: TestClient,
    test_services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path)

    response = _put_use_jj_for_new_workspaces(client, project.object_id, True)

    assert response.status_code == 200, response.text
    assert response.json() is True
    assert _read_use_jj_for_new_workspaces(test_services, project) is True
    _wait_for_state(published_states, _colocated_state(project, creates_jj_workspaces=True))


def test_turning_use_jj_for_new_workspaces_on_without_a_colocation_conflicts(
    jj_available: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    project = _register_project(test_services, git_repo)

    response = _put_use_jj_for_new_workspaces(client, project.object_id, True)

    assert response.status_code == 409, response.text
    assert _read_use_jj_for_new_workspaces(test_services, project) is False


def test_turning_use_jj_for_new_workspaces_on_without_jj_is_a_failed_precondition(
    jj_unavailable: None,
    client: TestClient,
    test_services: CompleteServiceCollection,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path)

    response = _put_use_jj_for_new_workspaces(client, project.object_id, True)

    assert response.status_code == 412, response.text
    assert response.json()["detail"] == _JJ_NOT_INSTALLED_REASON
    assert _read_use_jj_for_new_workspaces(test_services, project) is False


def test_turning_use_jj_for_new_workspaces_off_needs_neither_jj_nor_a_colocation(
    jj_unavailable: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    project = _register_project(test_services, git_repo)
    _store_use_jj_for_new_workspaces(test_services, project, True)

    response = _put_use_jj_for_new_workspaces(client, project.object_id, False)

    assert response.status_code == 200, response.text
    assert response.json() is False
    assert _read_use_jj_for_new_workspaces(test_services, project) is False


def test_turning_use_jj_for_new_workspaces_on_for_an_unknown_project_is_not_found(
    jj_available: None, client: TestClient
) -> None:
    response = _put_use_jj_for_new_workspaces(client, ProjectID(), True)

    assert response.status_code == 404, response.text


def _read_commit_id(jj_binary: JjBinary, repo: Path, revset: str) -> str:
    return run_jj(jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revset, "-T", "commit_id"), repo)


def _make_conflicted_bookmark(jj_binary: JjBinary, repo: Path, name: str) -> None:
    """Point `name` at two different commits in concurrent operations, which jj merges into a conflict."""
    for side in ("side a", "side b"):
        run_jj(jj_binary, ("--ignore-working-copy", "new", "--no-edit", "-m", side, "main"), repo)
    side_a = _read_commit_id(jj_binary, repo, 'children(main) & description(exact:"side a\\n")')
    side_b = _read_commit_id(jj_binary, repo, 'children(main) & description(exact:"side b\\n")')
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "create", name, "-r", "main"), repo)
    operation = run_jj(
        jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"), repo
    )
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "set", name, "-r", side_a), repo)
    run_jj(jj_binary, ("--ignore-working-copy", "--at-op", operation, "bookmark", "set", name, "-r", side_b), repo)


def test_the_bookmarks_of_a_colocated_repository_are_its_local_and_remote_ones_less_conflicted_ones(
    jj_available: None,
    jj_binary: JjBinary,
    client: TestClient,
    test_services: CompleteServiceCollection,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    _make_conflicted_bookmark(jj_binary, jj_colocated_repo.path, "contested")
    main_commit_id = _read_commit_id(jj_binary, jj_colocated_repo.path, "main")
    project = _register_project(test_services, jj_colocated_repo.path)

    response = client.get(f"/api/v1/projects/{project.object_id}/jj/bookmarks")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "bookmarks": [
            {"symbol": "main", "name": "main", "remote": None, "commitId": main_commit_id},
            {"symbol": "main@origin", "name": "main", "remote": "origin", "commitId": main_commit_id},
        ]
    }


def test_the_bookmarks_of_a_repository_that_is_not_colocated_conflict(
    jj_available: None, client: TestClient, test_services: CompleteServiceCollection, git_repo: Path
) -> None:
    project = _register_project(test_services, git_repo)

    response = client.get(f"/api/v1/projects/{project.object_id}/jj/bookmarks")

    assert response.status_code == 409, response.text


def test_the_bookmarks_without_jj_are_a_failed_precondition(
    jj_unavailable: None,
    client: TestClient,
    test_services: CompleteServiceCollection,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(test_services, jj_colocated_repo.path)

    response = client.get(f"/api/v1/projects/{project.object_id}/jj/bookmarks")

    assert response.status_code == 412, response.text
    assert response.json()["detail"] == _JJ_NOT_INSTALLED_REASON
