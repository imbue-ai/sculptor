"""Unit tests for workspace create and list commands."""

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


def _mock_initialize_project(
    base_url: str = "http://localhost:5050",
    object_id: str = "prj_test123",
) -> None:
    respx.post(f"{base_url}/api/v1/projects/initialize").mock(
        return_value=Response(
            200,
            json={
                "objectId": object_id,
                "organizationReference": "org_test",
                "name": "test-project",
            },
        )
    )


def _mock_preview_branch_name(base_url: str = "http://localhost:5050") -> None:
    # The default strategy is WORKTREE, which resolves a branch name via this endpoint.
    respx.get(f"{base_url}/api/v1/workspaces/preview-branch-name").mock(
        return_value=Response(200, json={"branchName": "auto/generated"})
    )


def _mock_projects_list(base_url: str = "http://localhost:5050") -> None:
    respx.get(f"{base_url}/api/v1/projects").mock(
        return_value=Response(
            200,
            json=[
                {
                    "objectId": "prj_test123",
                    "organizationReference": "org_test",
                    "name": "test-project",
                    "userGitRepoUrl": "file:///Users/test/projects/test-project",
                    "isPathAccessible": True,
                    "isDeleted": False,
                }
            ],
        )
    )


def _workspace_response_dict(
    object_id: str = "ws_test123",
    project_id: str = "prj_test123",
    description: str = "Test workspace",
    strategy: str = "CLONE",
    source_branch: str | None = "main",
    target_branch: str | None = None,
    requested_branch_name: str | None = None,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "description": description,
        "initializationStrategy": strategy,
        "sourceBranch": source_branch,
        "targetBranch": target_branch,
        "requestedBranchName": requested_branch_name,
        "environmentId": None,
        "isDeleted": False,
        "isOpen": True,
        "createdAt": "2025-01-01T00:00:00",
    }


def _recent_workspace_dict(
    object_id: str = "ws_test123",
    project_id: str = "prj_test123",
    description: str = "Test workspace",
    project_name: str = "test-project",
    working_directory: str | None = None,
    current_branch: str | None = None,
) -> dict[str, Any]:
    response = {
        "objectId": object_id,
        "projectId": project_id,
        "description": description,
        "initializationStrategy": "CLONE",
        "sourceBranch": "main",
        "isDeleted": False,
        "createdAt": "2024-01-15T10:30:00Z",
        "projectName": project_name,
        "agentCount": 2,
        "isOpen": True,
        "lastActivityAt": "2024-01-15T11:00:00Z",
    }
    # Older servers omit these fields entirely (the client sees UNSET); only
    # include them when a test explicitly provides values.
    if working_directory is not None:
        response["workingDirectory"] = working_directory
    if current_branch is not None:
        response["currentBranch"] = current_branch
    return response


class TestWorkspaceCreate:
    @respx.mock
    def test_create_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test"])

        assert result.exit_code == 0
        assert "ws_test123" in result.output

    @respx.mock
    def test_create_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "ws_test123"
        assert data["repo_id"] == "prj_test123"
        assert data["strategy"] == "CLONE"

    @respx.mock
    def test_create_in_place_strategy(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="IN_PLACE"))
        )

        result = runner.invoke(
            app, ["workspace", "create", "--repo", "/tmp/test", "--strategy", "in-place"]
        )

        assert result.exit_code == 0

    @respx.mock
    def test_create_worktree_strategy_with_branch_name(self, runner: CliRunner) -> None:
        """When --branch-name is supplied, the CLI sends it through unchanged and skips the preview call."""
        _mock_session()
        _mock_initialize_project()
        preview_route = respx.get(
            "http://localhost:5050/api/v1/workspaces/preview-branch-name"
        ).mock(return_value=Response(200, json={"branchName": "should-not-be-used"}))
        create_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="WORKTREE"))
        )

        result = runner.invoke(
            app,
            [
                "workspace",
                "create",
                "--repo",
                "/tmp/test",
                "--strategy",
                "worktree",
                "--branch",
                "main",
                "--branch-name",
                "dev/fix-thing",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert not preview_route.called, "preview-branch-name should not be called when --branch-name is provided"
        assert create_route.called
        request_body = json.loads(create_route.calls[0].request.content)
        assert request_body["initializationStrategy"] == "WORKTREE"
        assert request_body["sourceBranch"] == "main"
        assert request_body["requestedBranchName"] == "dev/fix-thing"
        data = json.loads(result.stdout)
        assert data["strategy"] == "WORKTREE"

    @respx.mock
    def test_create_worktree_strategy_autogenerates_branch_name(self, runner: CliRunner) -> None:
        """When --branch-name is omitted for worktree, the CLI auto-fills it via preview-branch-name."""
        _mock_session()
        _mock_initialize_project()
        preview_route = respx.get(
            "http://localhost:5050/api/v1/workspaces/preview-branch-name"
        ).mock(return_value=Response(200, json={"branchName": "dev/auto-generated"}))
        create_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="WORKTREE"))
        )

        result = runner.invoke(
            app,
            [
                "workspace",
                "create",
                "--repo",
                "/tmp/test",
                "--strategy",
                "worktree",
                "--branch",
                "main",
                "--name",
                "Fix Thing",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert preview_route.called
        assert create_route.called
        request_body = json.loads(create_route.calls[0].request.content)
        assert request_body["requestedBranchName"] == "dev/auto-generated"

    @respx.mock
    def test_create_passes_target_branch(self, runner: CliRunner) -> None:
        """--target-branch is forwarded in the create request body."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        create_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )

        result = runner.invoke(
            app,
            [
                "workspace",
                "create",
                "--repo",
                "/tmp/test",
                "--branch",
                "feature",
                "--target-branch",
                "feature",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert create_route.called
        request_body = json.loads(create_route.calls[0].request.content)
        assert request_body["targetBranch"] == "feature"

    @respx.mock
    def test_create_invalid_strategy(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()

        result = runner.invoke(
            app, ["workspace", "create", "--repo", "/tmp/test", "--strategy", "bogus"]
        )

        assert result.exit_code == 1
        assert "Invalid strategy 'bogus'" in (result.stderr or result.output)

    @respx.mock
    def test_create_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test"])

        assert result.exit_code == 1

    @respx.mock
    def test_create_validation_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(422, json={"detail": [{"msg": "error"}]})
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test"])

        assert result.exit_code == 1


class TestWorkspaceList:
    @respx.mock
    def test_list_all(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 0
        assert "ws_test123" in result.output
        assert "/Users/test/projects/test-p" in result.output

    @respx.mock
    def test_list_scoped(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/projects/prj_test123/workspaces").mock(
            return_value=Response(200, json=[_workspace_response_dict()])
        )

        result = runner.invoke(app, ["workspace", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 0
        assert "ws_test123" in result.output

    @respx.mock
    def test_list_scoped_json_exposes_stack_fields(self, runner: CliRunner) -> None:
        """The per-project list surfaces target_branch and requested_branch_name
        so callers (e.g. the restack skill) can reconstruct the stack graph."""
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/projects/prj_test123/workspaces").mock(
            return_value=Response(
                200,
                json=[
                    _workspace_response_dict(
                        strategy="WORKTREE",
                        source_branch="parent-branch",
                        target_branch="parent-branch",
                        requested_branch_name="child-branch",
                    )
                ],
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0
        # Parse stdout (not result.output): the --repo flow writes "Initialized
        # repo ..." to stderr, which the bumped typer/click CliRunner folds into
        # result.output. Matches the other --json assertions in this file.
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["target_branch"] == "parent-branch"
        assert data[0]["requested_branch_name"] == "child-branch"

    @respx.mock
    def test_list_all_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["id"] == "ws_test123"
        assert data[0]["repo_path"] == "/Users/test/projects/test-project"

    @respx.mock
    def test_list_empty(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": []})
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 0
        assert "No workspaces found." in result.output

    @respx.mock
    def test_list_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 1


class TestWorkspaceShow:
    @respx.mock
    def test_show_by_exact_id(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test123"])

        assert result.exit_code == 0
        assert "ws_test123" in result.output
        assert "/Users/test/projects/test-project" in result.output

    @respx.mock
    def test_show_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test"])

        assert result.exit_code == 0
        assert "ws_test123" in result.output

    @respx.mock
    def test_show_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "ws_test123"
        assert data["repo_path"] == "/Users/test/projects/test-project"

    @respx.mock
    def test_show_ambiguous_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(object_id="ws_abc123"),
                        _recent_workspace_dict(object_id="ws_abc456"),
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "show", "ws_abc"])

        assert result.exit_code == 1

    @respx.mock
    def test_show_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show", "nonexistent"])

        assert result.exit_code == 1


class TestWorkspaceShowDefault:
    """`workspace show` with no argument targets the shell's own workspace."""

    @respx.mock
    def test_show_no_arg_uses_env_workspace(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_test123")
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "ws_test123" in result.output
        assert "Using workspace from SCULPT_WORKSPACE_ID" in result.stderr

    @respx.mock
    def test_show_no_arg_without_env_errors(self, runner: CliRunner) -> None:
        # Client auth happens before the env check, so the session endpoint
        # must respond for the test to reach the WORKSPACE_ID error.
        _mock_session()

        result = runner.invoke(app, ["workspace", "show"])

        assert result.exit_code == 1
        assert "SCULPT_WORKSPACE_ID" in result.stderr


class TestWorkspacePathAndBranch:
    """show/list surface the live checkout location and branch when the server provides them."""

    @respx.mock
    def test_show_renders_path_and_current_branch(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(
                            working_directory="/tmp/worktrees/foo",
                            current_branch="dev/feature-x",
                        )
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test123"])

        assert result.exit_code == 0
        assert "Path: /tmp/worktrees/foo" in result.output
        assert "Current Branch: dev/feature-x" in result.output

    @respx.mock
    def test_show_json_includes_path_and_branch(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(
                            working_directory="/tmp/worktrees/foo",
                            current_branch="dev/feature-x",
                        )
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["working_directory"] == "/tmp/worktrees/foo"
        assert data["current_branch"] == "dev/feature-x"

    @respx.mock
    def test_show_tolerates_older_server_without_fields(self, runner: CliRunner) -> None:
        """A server that doesn't send workingDirectory/currentBranch yields nulls, not a crash."""
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "show", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["working_directory"] is None
        assert data["current_branch"] is None

        result = runner.invoke(app, ["workspace", "show", "ws_test123"])
        assert result.exit_code == 0
        assert "Path:" not in result.output

    @respx.mock
    def test_list_all_prefers_current_branch_over_source(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={"workspaces": [_recent_workspace_dict(current_branch="dev/live-branch")]},
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 0
        assert "dev/live-branch" in result.output
        # The source branch ("main") is only the fallback when no live branch is known.
        assert "main" not in result.output

    @respx.mock
    def test_list_all_json_includes_path_and_branch(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(
                            working_directory="/tmp/worktrees/foo",
                            current_branch="dev/feature-x",
                        )
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["working_directory"] == "/tmp/worktrees/foo"
        assert data[0]["current_branch"] == "dev/feature-x"

    @respx.mock
    def test_list_project_json_includes_path_and_branch(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        workspace = _workspace_response_dict()
        workspace["workingDirectory"] = "/tmp/worktrees/foo"
        workspace["currentBranch"] = "dev/feature-x"
        respx.get("http://localhost:5050/api/v1/projects/prj_test123/workspaces").mock(
            return_value=Response(200, json=[workspace])
        )

        result = runner.invoke(app, ["workspace", "list", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["working_directory"] == "/tmp/worktrees/foo"
        assert data[0]["current_branch"] == "dev/feature-x"


class TestWorkspaceSelfMarker:
    """`workspace list` flags the calling shell's own workspace (SCULPT_WORKSPACE_ID)."""

    @respx.mock
    def test_list_all_json_flags_only_own_workspace(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_test123")
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(object_id="ws_test123"),
                        _recent_workspace_dict(object_id="ws_other456"),
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        flags = {item["id"]: item["is_self"] for item in data}
        assert flags == {"ws_test123": True, "ws_other456": False}

    @respx.mock
    def test_list_all_table_marks_own_workspace_with_legend(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_test123")
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(
                200,
                json={
                    "workspaces": [
                        _recent_workspace_dict(object_id="ws_test123"),
                        _recent_workspace_dict(object_id="ws_other456"),
                    ]
                },
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 0
        assert "ws_test123 *" in result.output
        assert "ws_other456 *" not in result.output
        assert "* = this workspace (SCULPT_WORKSPACE_ID)" in result.stderr

    @respx.mock
    def test_list_project_json_flags_only_own_workspace(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_test123")
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/projects/prj_test123/workspaces").mock(
            return_value=Response(
                200,
                json=[
                    _workspace_response_dict(object_id="ws_test123"),
                    _workspace_response_dict(object_id="ws_other456"),
                ],
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        flags = {item["id"]: item["is_self"] for item in data}
        assert flags == {"ws_test123": True, "ws_other456": False}

    @respx.mock
    def test_list_project_table_marks_own_workspace_with_legend(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_test123")
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/projects/prj_test123/workspaces").mock(
            return_value=Response(
                200,
                json=[
                    _workspace_response_dict(object_id="ws_test123"),
                    _workspace_response_dict(object_id="ws_other456"),
                ],
            )
        )

        result = runner.invoke(app, ["workspace", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 0
        assert "ws_test123 *" in result.output
        assert "ws_other456 *" not in result.output
        assert "* = this workspace (SCULPT_WORKSPACE_ID)" in result.stderr

    @respx.mock
    def test_list_all_without_env_has_no_marker_or_legend(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_projects_list()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 0
        assert "*" not in result.output
        assert "* = this workspace" not in result.stderr


class TestWorkspaceConnectionErrorHint:
    @respx.mock
    def test_list_connection_error_mentions_port_hint(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["workspace", "list", "--all"])

        assert result.exit_code == 1
        assert "SCULPT_API_PORT" in result.stderr
        assert "--base-url" in result.stderr


class TestWorkspaceRename:
    @respx.mock
    def test_rename_success(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(
                200, json=_workspace_response_dict(description="New description")
            )
        )

        result = runner.invoke(app, ["workspace", "rename", "ws_test123", "New description"])

        assert result.exit_code == 0
        assert "renamed" in result.output
        assert "New description" in result.output

    @respx.mock
    def test_rename_json(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(
                200, json=_workspace_response_dict(description="New description")
            )
        )

        result = runner.invoke(app, ["workspace", "rename", "ws_test123", "New description", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "ws_test123"
        assert data["description"] == "New description"

    @respx.mock
    def test_rename_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(
                200, json=_workspace_response_dict(description="Updated")
            )
        )

        result = runner.invoke(app, ["workspace", "rename", "ws_test", "Updated"])

        assert result.exit_code == 0

    @respx.mock
    def test_rename_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "rename", "nonexistent", "New name"])

        assert result.exit_code == 1

    @respx.mock
    def test_rename_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["workspace", "rename", "ws_test123", "New name"])

        assert result.exit_code == 1

    @respx.mock
    def test_rename_validation_error(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(422, json={"detail": [{"msg": "error"}]})
        )

        result = runner.invoke(app, ["workspace", "rename", "ws_test123", "New name"])

        assert result.exit_code == 1


class TestWorkspaceDelete:
    @respx.mock
    def test_delete_with_yes(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["workspace", "delete", "ws_test123", "--yes"])

        assert result.exit_code == 0
        assert "deleted" in result.output

    @respx.mock
    def test_delete_json(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["workspace", "delete", "ws_test123", "--yes", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["deleted"] is True
        assert data["id"] == "ws_test123"

    @respx.mock
    def test_delete_prompt_aborted(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "delete", "ws_test123"], input="n\n")

        assert result.exit_code == 1

    @respx.mock
    def test_delete_prompt_accepted(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["workspace", "delete", "ws_test123"], input="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.output

    @respx.mock
    def test_delete_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["workspace", "delete", "ws_test", "--yes"])

        assert result.exit_code == 0

    @respx.mock
    def test_delete_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
            return_value=Response(200, json={"workspaces": [_recent_workspace_dict()]})
        )

        result = runner.invoke(app, ["workspace", "delete", "nonexistent", "--yes"])

        assert result.exit_code == 1
