"""Unit tests for project resolution and prefix matching."""

import os
from typing import Any

import pytest
import respx
import typer
from httpx import ConnectError
from httpx import Response
from sculpt.client import Client
from sculpt.resolve import resolve_by_prefix
from sculpt.resolve import resolve_project
from sculpt.resolve import resolve_workspace_id


def _make_client(base_url: str = "http://localhost:5050") -> Client:
    return Client(base_url=base_url).with_headers({"x-session-token": "test-token"})


def _make_project_response(
    object_id: str = "prj_test123",
    name: str = "test-project",
    user_git_repo_url: str | None = None,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "organizationReference": "org_test",
        "name": name,
        "userGitRepoUrl": user_git_repo_url,
    }


class TestResolveProject:
    @respx.mock
    def test_repo_provided_initializes_project(self) -> None:
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(200, json=_make_project_response())
        )

        result = resolve_project(repo="/tmp/my-repo", client=client)

        assert result == "prj_test123"

    @respx.mock
    def test_repo_provided_server_error(self) -> None:
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(500)
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/my-repo", client=client)

    @respx.mock
    def test_repo_provided_connection_error(self) -> None:
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            side_effect=ConnectError("Connection refused")
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/my-repo", client=client)

    @respx.mock
    def test_repo_provided_already_added_returns_existing_project(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """SCU-1309: When --repo points at a path the server already has registered, the
        server returns 409 'This repository is already added to Sculptor.' Previously
        the CLI printed 'Failed to initialize repo (no response)' and exited 1. With
        the fix, the CLI looks up the existing project and returns its id so that
        `sculpt run --repo X` and `sculpt workspace create --repo X` are idempotent."""
        client = _make_client()
        target_path = "/tmp/my-already-registered-repo"
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(
                409,
                json={"detail": "This repository is already added to Sculptor."},
            )
        )
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(
                200,
                json=[
                    _make_project_response(
                        object_id="prj_existing",
                        user_git_repo_url=f"file://{target_path}",
                    )
                ],
            )
        )

        result = resolve_project(repo=target_path, client=client)

        assert result == "prj_existing"
        captured = capsys.readouterr()
        assert "no response" not in captured.err

    @respx.mock
    def test_repo_provided_already_added_no_match_surfaces_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Defensive: if the server says 409 'already added' but no project matches the
        path in list_projects, surface the server's detail rather than the misleading
        'no response' message — the user gets something actionable to debug."""
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(
                409,
                json={"detail": "This repository is already added to Sculptor."},
            )
        )
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[]),
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/my-repo", client=client)
        captured = capsys.readouterr()
        assert "already added" in captured.err
        assert "no response" not in captured.err

    @respx.mock
    def test_repo_provided_400_not_git_repo_surfaces_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """4xx errors from /projects/initialize must surface the server's detail
        instead of the misleading 'no response' (SCU-1309)."""
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(
                400,
                json={
                    "detail": (
                        "Selected directory is not a git repository."
                        + " Please initialize it first using /api/v1/projects/init-git"
                    )
                },
            )
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/not-a-repo", client=client)
        captured = capsys.readouterr()
        assert "not a git repository" in captured.err
        assert "no response" not in captured.err

    @respx.mock
    def test_repo_provided_404_path_missing_surfaces_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """404 'Project path does not exist' must surface the detail (SCU-1309)."""
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(
                404,
                json={"detail": "Project path does not exist: /tmp/missing"},
            )
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/missing", client=client)
        captured = capsys.readouterr()
        assert "does not exist" in captured.err
        assert "no response" not in captured.err

    @respx.mock
    def test_repo_provided_409_no_commits_surfaces_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The other 409 path ('no commits') is a real error and must surface the
        detail, not be mistakenly funneled through the idempotent 'already added'
        branch."""
        client = _make_client()
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(
                409,
                json={
                    "detail": (
                        "Selected git repository has no commits."
                        + " Please create an initial commit first."
                    )
                },
            )
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo="/tmp/empty-repo", client=client)
        captured = capsys.readouterr()
        assert "no commits" in captured.err
        assert "no response" not in captured.err

    def test_env_var_returns_project_id(self) -> None:
        client = _make_client()
        os.environ["SCULPT_PROJECT_ID"] = "prj_from_env"

        result = resolve_project(repo=None, client=client)

        assert result == "prj_from_env"

    @respx.mock
    def test_repo_overrides_env_var(self) -> None:
        client = _make_client()
        os.environ["SCULPT_PROJECT_ID"] = "prj_from_env"
        respx.post("http://localhost:5050/api/v1/projects/initialize").mock(
            return_value=Response(200, json=_make_project_response(object_id="prj_from_repo"))
        )

        result = resolve_project(repo="/tmp/my-repo", client=client)

        assert result == "prj_from_repo"

    @respx.mock
    def test_cwd_fallback_project_exists(self) -> None:
        client = _make_client()
        cwd = os.getcwd()
        cwd_uri = f"file:///{cwd.lstrip('/')}"
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(
                200,
                json=[_make_project_response(object_id="prj_cwd", user_git_repo_url=cwd_uri)],
            )
        )

        result = resolve_project(repo=None, client=client)

        assert result == "prj_cwd"

    @respx.mock
    def test_cwd_fallback_no_project(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(
                200,
                json=[_make_project_response(user_git_repo_url="file:///some/other/path")],
            )
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo=None, client=client)

    @respx.mock
    def test_cwd_fallback_empty_project_list(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[])
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo=None, client=client)

    @respx.mock
    def test_cwd_no_match_error_mentions_env_var(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """SCU-1309: When _resolve_from_cwd can't match the current directory to any
        registered project, the error message must also mention SCULPT_PROJECT_ID.
        Otherwise agents (and humans) are funneled into `--repo`, which then 409s
        against any already-registered repo — the SCU-1309 footgun."""
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[]),
        )

        with pytest.raises(typer.Exit):
            resolve_project(repo=None, client=client)
        captured = capsys.readouterr()
        assert "SCULPT_PROJECT_ID" in captured.err


class TestResolveByPrefix:
    def test_exact_match(self) -> None:
        items = ["abc123", "abc456", "def789"]
        result = resolve_by_prefix("abc123", items, lambda x: x)
        assert result == "abc123"

    def test_unique_prefix(self) -> None:
        items = ["abc123", "def456"]
        result = resolve_by_prefix("abc", items, lambda x: x)
        assert result == "abc123"

    def test_ambiguous_prefix(self) -> None:
        items = ["abc123", "abc456"]
        with pytest.raises(typer.Exit):
            resolve_by_prefix("abc", items, lambda x: x)

    def test_no_match(self) -> None:
        items = ["abc123", "def456"]
        with pytest.raises(typer.Exit):
            resolve_by_prefix("xyz", items, lambda x: x)

    def test_with_id_getter(self) -> None:
        items = [{"id": "abc123", "name": "first"}, {"id": "def456", "name": "second"}]
        result = resolve_by_prefix("abc", items, lambda x: x["id"])
        assert result == {"id": "abc123", "name": "first"}

    def test_exact_match_takes_priority_over_prefix(self) -> None:
        items = ["abc", "abcdef"]
        result = resolve_by_prefix("abc", items, lambda x: x)
        assert result == "abc"


def _make_workspace_response(
    object_id: str,
    project_id: str = "prj_test123",
    description: str = "Test",
    initialization_strategy: str = "CLONE",
    source_branch: str = "main",
    is_deleted: bool = False,
    created_at: str = "2024-01-15T10:30:00Z",
    project_name: str = "test-project",
    agent_count: int = 1,
    is_open: bool = True,
    last_activity_at: str = "2024-01-15T11:00:00Z",
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "description": description,
        "initializationStrategy": initialization_strategy,
        "sourceBranch": source_branch,
        "isDeleted": is_deleted,
        "createdAt": created_at,
        "projectName": project_name,
        "agentCount": agent_count,
        "isOpen": is_open,
        "lastActivityAt": last_activity_at,
    }


def _mock_workspaces_response(*object_ids: str) -> dict[str, Any]:
    return {"workspaces": [_make_workspace_response(oid) for oid in object_ids]}


class TestResolveWorkspaceId:
    @respx.mock
    def test_exact_match(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json=_mock_workspaces_response("ws_abc123full", "ws_abc456full"))
        )

        result = resolve_workspace_id(client, "ws_abc123full")

        assert result == "ws_abc123full"

    @respx.mock
    def test_unique_prefix_match(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json=_mock_workspaces_response("ws_abc123full", "ws_def456full"))
        )

        result = resolve_workspace_id(client, "ws_abc")

        assert result == "ws_abc123full"

    @respx.mock
    def test_no_match(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json=_mock_workspaces_response("ws_abc123full", "ws_def456full"))
        )

        with pytest.raises(typer.Exit):
            resolve_workspace_id(client, "ws_xyz")

    @respx.mock
    def test_ambiguous_match(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json=_mock_workspaces_response("ws_abc123", "ws_abc456"))
        )

        with pytest.raises(typer.Exit):
            resolve_workspace_id(client, "ws_abc")

    @respx.mock
    def test_connection_error(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            side_effect=ConnectError("Connection refused")
        )

        with pytest.raises(typer.Exit):
            resolve_workspace_id(client, "ws_abc")

    @respx.mock
    def test_no_response(self) -> None:
        client = _make_client()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(500)
        )

        with pytest.raises(typer.Exit):
            resolve_workspace_id(client, "ws_abc")
