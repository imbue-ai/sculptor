"""Unit tests for the sculpt group command family."""

import json
from typing import Any

import pytest
import respx
from httpx import Response
from sculpt.main import app
from typer.testing import CliRunner

_BASE_URL = "http://localhost:5050"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_session(base_url: str = _BASE_URL) -> None:
    respx.get(f"{base_url}/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )


def _mock_initialize_project(
    base_url: str = _BASE_URL,
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


def _group_response_dict(
    object_id: str = "wsg_test123",
    project_id: str = "prj_test123",
    name: str = "Group 1",
    color: str = "blue",
    created_via_cli: bool = False,
    workspace_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "name": name,
        "color": color,
        "createdViaCli": created_via_cli,
        "createdAt": "2025-01-01T00:00:00",
        "workspaceIds": workspace_ids if workspace_ids is not None else ["ws_member1"],
    }


_DISABLED_ERROR_BODY = {
    "detail": {
        "error": "workspace_groups_disabled",
        "message": "Workspace groups are an experimental feature; enable them in Settings first.",
    }
}


def _mock_list_groups(*groups: dict[str, Any], base_url: str = _BASE_URL) -> respx.Route:
    return respx.get(f"{base_url}/api/v1/workspace-groups").mock(
        return_value=Response(200, json={"groups": list(groups), "palette": ["blue", "green"]})
    )


def _recent_workspace_dict(
    object_id: str = "ws_member1",
    project_id: str = "prj_test123",
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "description": "Test workspace",
        "initializationStrategy": "CLONE",
        "sourceBranch": "main",
        "isDeleted": False,
        "createdAt": "2024-01-15T10:30:00Z",
        "projectName": "test-project",
        "agentCount": 1,
        "isOpen": True,
        "lastActivityAt": "2024-01-15T11:00:00Z",
    }


def _mock_recent_workspaces(*workspaces: dict[str, Any], base_url: str = _BASE_URL) -> None:
    respx.get(f"{base_url}/api/v1/workspaces/recent").mock(
        return_value=Response(200, json={"workspaces": list(workspaces)})
    )


class TestGroupCreate:
    @respx.mock
    def test_create_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(_recent_workspace_dict())
        create_route = respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(
            return_value=Response(200, json=_group_response_dict(created_via_cli=True, workspace_ids=["ws_member1"]))
        )

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_member1"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "wsg_test123" in result.output
        request_body = json.loads(create_route.calls.last.request.content)
        assert request_body["projectId"] == "prj_test123"
        assert request_body["workspaceIds"] == ["ws_member1"]
        assert request_body["createdViaCli"] is True

    @respx.mock
    def test_create_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(_recent_workspace_dict())
        respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(
            return_value=Response(200, json=_group_response_dict(created_via_cli=True, workspace_ids=["ws_member1"]))
        )

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_member1", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data["id"] == "wsg_test123"
        assert data["repo_id"] == "prj_test123"
        assert data["name"] == "Group 1"
        assert data["color"] == "blue"
        assert data["created_via_cli"] is True
        assert data["workspace_ids"] == ["ws_member1"]

    @respx.mock
    def test_create_with_name_and_color(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(_recent_workspace_dict())
        create_route = respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(
            return_value=Response(200, json=_group_response_dict(name="Refactor", color="teal"))
        )

        result = runner.invoke(
            app,
            ["group", "create", "--workspace", "ws_member1", "--name", "Refactor", "--color", "teal"],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        request_body = json.loads(create_route.calls.last.request.content)
        assert request_body["name"] == "Refactor"
        assert request_body["color"] == "teal"

    @respx.mock
    def test_create_resolves_workspace_prefixes(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(
            _recent_workspace_dict(object_id="ws_alpha111"),
            _recent_workspace_dict(object_id="ws_beta2222"),
        )
        create_route = respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(
            return_value=Response(200, json=_group_response_dict(workspace_ids=["ws_alpha111", "ws_beta2222"]))
        )

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_alpha", "--workspace", "ws_beta"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        request_body = json.loads(create_route.calls.last.request.content)
        assert request_body["workspaceIds"] == ["ws_alpha111", "ws_beta2222"]

    def test_create_requires_at_least_one_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["group", "create"])

        assert result.exit_code == 2

    @respx.mock
    def test_create_rejects_members_from_different_repos(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(
            _recent_workspace_dict(object_id="ws_alpha111", project_id="prj_one"),
            _recent_workspace_dict(object_id="ws_beta2222", project_id="prj_two"),
        )

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_alpha", "--workspace", "ws_beta"])

        assert result.exit_code == 1
        assert "different repos" in result.stderr

    @respx.mock
    def test_create_disabled_flag_errors(self, runner: CliRunner) -> None:
        """Explicit group intent surfaces the disabled-experiment error (REQ-FLAG-4)."""
        _mock_session()
        _mock_recent_workspaces(_recent_workspace_dict())
        respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(return_value=Response(409, json=_DISABLED_ERROR_BODY))

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_member1"])

        assert result.exit_code == 1
        assert "disabled" in result.stderr
        assert "Settings" in result.stderr

    @respx.mock
    def test_create_disabled_flag_errors_json_carries_code(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_recent_workspaces(_recent_workspace_dict())
        respx.post(f"{_BASE_URL}/api/v1/workspace-groups").mock(return_value=Response(409, json=_DISABLED_ERROR_BODY))

        result = runner.invoke(app, ["group", "create", "--workspace", "ws_member1", "--json"])

        assert result.exit_code == 1
        error = json.loads(result.stderr)
        assert error["code"] == "workspace_groups_disabled"


class TestGroupList:
    @respx.mock
    def test_list_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_list_groups(
            _group_response_dict(),
            _group_response_dict(object_id="wsg_other456", name="Group 2", color="green", created_via_cli=True),
        )

        result = runner.invoke(app, ["group", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "wsg_test123" in result.output
        assert "Group 1" in result.output
        assert "wsg_other456" in result.output
        assert "yes" in result.output

    @respx.mock
    def test_list_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_a", "ws_b"]))

        result = runner.invoke(app, ["group", "list", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["id"] == "wsg_test123"
        assert data[0]["workspace_ids"] == ["ws_a", "ws_b"]

    @respx.mock
    def test_list_scopes_to_resolved_project(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        list_route = _mock_list_groups(_group_response_dict())

        result = runner.invoke(app, ["group", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert list_route.calls.last.request.url.params["project_id"] == "prj_test123"

    @respx.mock
    def test_list_empty(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_list_groups()

        result = runner.invoke(app, ["group", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "No workspace groups found." in result.output

    @respx.mock
    def test_list_disabled_flag_errors(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.get(f"{_BASE_URL}/api/v1/workspace-groups").mock(return_value=Response(409, json=_DISABLED_ERROR_BODY))

        result = runner.invoke(app, ["group", "list", "--repo", "/tmp/test"])

        assert result.exit_code == 1
        assert "disabled" in result.stderr


class TestGroupShow:
    @respx.mock
    def test_show_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_a", "ws_b"]))

        result = runner.invoke(app, ["group", "show", "wsg_test123"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "wsg_test123" in result.output
        assert "Group 1" in result.output
        assert "ws_a, ws_b" in result.output

    @respx.mock
    def test_show_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(created_via_cli=True))

        result = runner.invoke(app, ["group", "show", "wsg_test123", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data["id"] == "wsg_test123"
        assert data["created_via_cli"] is True

    @respx.mock
    def test_show_resolves_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(), _group_response_dict(object_id="xyz_unrelated"))

        result = runner.invoke(app, ["group", "show", "wsg_"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "wsg_test123" in result.output

    @respx.mock
    def test_show_unknown_group_errors(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict())

        result = runner.invoke(app, ["group", "show", "wsg_missing"])

        assert result.exit_code == 1


class TestGroupRename:
    @respx.mock
    def test_rename_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict())
        patch_route = respx.patch(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123").mock(
            return_value=Response(200, json=_group_response_dict(name="New Name"))
        )

        result = runner.invoke(app, ["group", "rename", "wsg_test", "New Name"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "New Name" in result.output
        request_body = json.loads(patch_route.calls.last.request.content)
        assert request_body["name"] == "New Name"

    @respx.mock
    def test_rename_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict())
        respx.patch(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123").mock(
            return_value=Response(200, json=_group_response_dict(name="New Name"))
        )

        result = runner.invoke(app, ["group", "rename", "wsg_test", "New Name", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data == {"id": "wsg_test123", "name": "New Name"}


class TestGroupAdd:
    @respx.mock
    def test_add_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1"]))
        _mock_recent_workspaces(
            _recent_workspace_dict(),
            _recent_workspace_dict(object_id="ws_newbie99"),
        )
        add_route = respx.post(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123/workspaces").mock(
            return_value=Response(200, json=_group_response_dict(workspace_ids=["ws_member1", "ws_newbie99"]))
        )

        result = runner.invoke(app, ["group", "add", "wsg_test", "ws_newbie"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        request_body = json.loads(add_route.calls.last.request.content)
        assert request_body["workspaceId"] == "ws_newbie99"

    @respx.mock
    def test_add_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1"]))
        _mock_recent_workspaces(
            _recent_workspace_dict(),
            _recent_workspace_dict(object_id="ws_newbie99"),
        )
        respx.post(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123/workspaces").mock(
            return_value=Response(200, json=_group_response_dict(workspace_ids=["ws_member1", "ws_newbie99"]))
        )

        result = runner.invoke(app, ["group", "add", "wsg_test", "ws_newbie", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data["group_id"] == "wsg_test123"
        assert data["workspace_id"] == "ws_newbie99"
        assert data["workspace_ids"] == ["ws_member1", "ws_newbie99"]

    @respx.mock
    def test_add_rejects_cross_repo_workspace(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict())
        _mock_recent_workspaces(_recent_workspace_dict(object_id="ws_other", project_id="prj_other"))

        result = runner.invoke(app, ["group", "add", "wsg_test", "ws_other"])

        assert result.exit_code == 1
        assert "different repos" in result.stderr


class TestGroupRemove:
    @respx.mock
    def test_remove_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1", "ws_member2"]))
        remove_route = respx.delete(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123/workspaces/ws_member1").mock(
            return_value=Response(200, content=b"null")
        )

        result = runner.invoke(app, ["group", "remove", "wsg_test", "ws_member1"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert remove_route.called
        assert "removed" in result.output
        assert "dissolved" not in result.output

    @respx.mock
    def test_remove_last_member_notes_dissolution(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1"]))
        respx.delete(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123/workspaces/ws_member1").mock(
            return_value=Response(200, content=b"null")
        )

        result = runner.invoke(app, ["group", "remove", "wsg_test", "ws_member1"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "dissolved" in result.output

    @respx.mock
    def test_remove_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1", "ws_member2"]))
        respx.delete(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123/workspaces/ws_member1").mock(
            return_value=Response(200, content=b"null")
        )

        result = runner.invoke(app, ["group", "remove", "wsg_test", "ws_member1", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data == {"removed": True, "group_id": "wsg_test123", "workspace_id": "ws_member1"}

    @respx.mock
    def test_remove_non_member_errors(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_member1"]))

        result = runner.invoke(app, ["group", "remove", "wsg_test", "ws_stranger"])

        assert result.exit_code == 1


class TestGroupUngroup:
    @respx.mock
    def test_ungroup_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_a", "ws_b"]))
        ungroup_route = respx.delete(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123").mock(
            return_value=Response(200, content=b"null")
        )

        result = runner.invoke(app, ["group", "ungroup", "wsg_test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert ungroup_route.called
        assert "released 2 workspace(s)" in result.output

    @respx.mock
    def test_ungroup_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_list_groups(_group_response_dict(workspace_ids=["ws_a", "ws_b"]))
        respx.delete(f"{_BASE_URL}/api/v1/workspace-groups/wsg_test123").mock(
            return_value=Response(200, content=b"null")
        )

        result = runner.invoke(app, ["group", "ungroup", "wsg_test", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data["ungrouped"] is True
        assert data["id"] == "wsg_test123"
        assert data["released_workspace_ids"] == ["ws_a", "ws_b"]

    @respx.mock
    def test_ungroup_disabled_flag_errors(self, runner: CliRunner) -> None:
        _mock_session()
        respx.get(f"{_BASE_URL}/api/v1/workspace-groups").mock(return_value=Response(409, json=_DISABLED_ERROR_BODY))

        result = runner.invoke(app, ["group", "ungroup", "wsg_test"])

        assert result.exit_code == 1
        assert "disabled" in result.stderr
