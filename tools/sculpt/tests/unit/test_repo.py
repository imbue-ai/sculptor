"""Unit tests for the sculpt repo commands."""

import json
from typing import Any

import pytest
import respx
from httpx import ConnectError
from httpx import Response
from sculpt.main import app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_session(base_url: str = "http://localhost:5050") -> None:
    respx.get(f"{base_url}/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )


def _project_response_dict(
    object_id: str = "prj_test123",
    name: str = "my-repo",
    user_git_repo_url: str = "file:///Users/test/projects/my-repo",
    is_path_accessible: bool = True,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "organizationReference": "org_test",
        "name": name,
        "createdAt": "2024-01-15T10:30:00Z",
        "userGitRepoUrl": user_git_repo_url,
        "isLoggable": False,
        "isPathAccessible": is_path_accessible,
        "isDeleted": False,
        "defaultSystemPrompt": None,
    }


class TestRepoList:
    @respx.mock
    def test_list_success(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "list"])

        assert result.exit_code == 0
        assert "prj_test123" in result.output
        assert "my-repo" in result.output
        assert "/Users/test/projects/my-repo" in result.output

    @respx.mock
    def test_list_json(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["id"] == "prj_test123"
        assert data[0]["name"] == "my-repo"
        assert data[0]["path"] == "/Users/test/projects/my-repo"
        assert data[0]["accessible"] is True

    @respx.mock
    def test_list_empty(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[])
        )

        result = runner.invoke(app, ["repo", "list"])

        assert result.exit_code == 0
        assert "No repos found." in result.output

    @respx.mock
    def test_list_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["repo", "list"])

        assert result.exit_code == 1

    @respx.mock
    def test_list_multiple(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(
                200,
                json=[
                    _project_response_dict(object_id="prj_aaa", name="repo-a", user_git_repo_url="file:///a"),
                    _project_response_dict(object_id="prj_bbb", name="repo-b", user_git_repo_url="file:///b"),
                ],
            )
        )

        result = runner.invoke(app, ["repo", "list"])

        assert result.exit_code == 0
        assert "repo-a" in result.output
        assert "repo-b" in result.output


class TestRepoShow:
    @respx.mock
    def test_show_by_exact_id(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "show", "prj_test123"])

        assert result.exit_code == 0
        assert "prj_test123" in result.output
        assert "/Users/test/projects/my-repo" in result.output

    @respx.mock
    def test_show_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "show", "prj_test"])

        assert result.exit_code == 0
        assert "prj_test123" in result.output

    @respx.mock
    def test_show_json(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "show", "prj_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "prj_test123"
        assert data["name"] == "my-repo"
        assert data["path"] == "/Users/test/projects/my-repo"

    @respx.mock
    def test_show_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict()])
        )

        result = runner.invoke(app, ["repo", "show", "nonexistent"])

        assert result.exit_code == 1

    @respx.mock
    def test_show_inaccessible(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/projects").mock(
            return_value=Response(200, json=[_project_response_dict(is_path_accessible=False)])
        )

        result = runner.invoke(app, ["repo", "show", "prj_test123"])

        assert result.exit_code == 0
        assert "no" in result.output
