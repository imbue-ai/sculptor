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


def _group_response_dict(
    object_id: str = "wsg_auto123",
    project_id: str = "prj_test123",
    workspace_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "name": "Group 1",
        "color": "blue",
        "createdViaCli": True,
        "createdAt": "2025-01-01T00:00:00",
        "workspaceIds": workspace_ids if workspace_ids is not None else ["ws_test123"],
    }


_GROUPS_DISABLED_BODY = {
    "detail": {
        "error": "workspace_groups_disabled",
        "message": "Workspace groups are an experimental feature; enable them in Settings first.",
    }
}


def _mock_auto_group(base_url: str = "http://localhost:5050") -> respx.Route:
    # Workspace-creating commands auto-group by default, so every happy-path
    # create needs the group-create endpoint mocked.
    return respx.post(f"{base_url}/api/v1/workspace-groups").mock(
        return_value=Response(200, json=_group_response_dict())
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
) -> dict[str, Any]:
    return {
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


class TestWorkspaceCreate:
    @respx.mock
    def test_create_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        _mock_auto_group()
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
        _mock_auto_group()
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
        _mock_auto_group()
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
        _mock_auto_group()
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
        _mock_auto_group()
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
        _mock_auto_group()
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


class TestWorkspaceCreateGrouping:
    """Grouping behavior of `sculpt workspace create` (REQ-CLI-2/3/4, REQ-FLAG-4)."""

    @respx.mock
    def test_create_auto_creates_cli_group_by_default(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        group_route = _mock_auto_group()

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert group_route.called
        request_body = json.loads(group_route.calls.last.request.content)
        assert request_body["projectId"] == "prj_test123"
        assert request_body["workspaceIds"] == ["ws_test123"]
        assert request_body["createdViaCli"] is True
        data = json.loads(result.stdout)
        assert data["group_id"] == "wsg_auto123"

    @respx.mock
    def test_create_no_group_skips_grouping(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        group_route = _mock_auto_group()

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test", "--no-group", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert not group_route.called
        data = json.loads(result.stdout)
        assert data["group_id"] is None

    @respx.mock
    def test_create_group_joins_existing_group(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.get("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(
                200,
                json={"groups": [_group_response_dict(object_id="wsg_existing1", workspace_ids=["ws_sibling"])]},
            )
        )
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        add_route = respx.post("http://localhost:5050/api/v1/workspace-groups/wsg_existing1/workspaces").mock(
            return_value=Response(
                200,
                json=_group_response_dict(object_id="wsg_existing1", workspace_ids=["ws_sibling", "ws_test123"]),
            )
        )

        result = runner.invoke(
            app, ["workspace", "create", "--repo", "/tmp/test", "--group", "wsg_existing", "--json"]
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert add_route.called
        request_body = json.loads(add_route.calls.last.request.content)
        assert request_body["workspaceId"] == "ws_test123"
        data = json.loads(result.stdout)
        assert data["group_id"] == "wsg_existing1"

    def test_create_group_and_no_group_are_mutually_exclusive(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["workspace", "create", "--repo", "/tmp/test", "--group", "wsg_x", "--no-group"]
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stderr

    @respx.mock
    def test_create_proceeds_loose_when_groups_disabled(self, runner: CliRunner) -> None:
        """Implicit auto-group swallows the disabled-experiment 409 (REQ-FLAG-4)."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(409, json=_GROUPS_DISABLED_BODY)
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "ws_test123" in result.output
        assert "ungrouped" in result.stderr
        assert "Group:" not in result.output

    @respx.mock
    def test_create_explicit_group_fails_when_groups_disabled(self, runner: CliRunner) -> None:
        """Explicit --group surfaces the disabled error before creating anything."""
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(409, json=_GROUPS_DISABLED_BODY)
        )
        ws_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )

        result = runner.invoke(app, ["workspace", "create", "--repo", "/tmp/test", "--group", "wsg_x"])

        assert result.exit_code == 1
        assert "disabled" in result.stderr
        assert not ws_route.called


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
