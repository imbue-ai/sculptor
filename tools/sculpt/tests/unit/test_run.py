"""Unit tests for the sculpt run command."""

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


def _workspace_response_dict(
    object_id: str = "ws_newrun123",
    project_id: str = "prj_test123",
    strategy: str = "CLONE",
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "projectId": project_id,
        "description": "My task",
        "initializationStrategy": strategy,
        "sourceBranch": "main",
        "targetBranch": None,
        "requestedBranchName": None,
        "environmentId": None,
        "isDeleted": False,
        "isOpen": True,
        "createdAt": "2025-01-01T00:00:00",
    }


def _task_response_dict(
    task_id: str = "tsk_abc123def456",
    workspace_id: str = "ws_newrun123",
) -> dict[str, Any]:
    return {
        "id": task_id,
        "projectId": "prj_test123",
        "workspaceId": workspace_id,
        "createdAt": "2024-01-15T10:30:00Z",
        "updatedAt": "2024-01-15T10:35:00Z",
        "taskStatus": "RUNNING",
        "isCompacting": False,
        "isClearingContext": False,
        "isAutoCompacting": False,
        "acceptsAutomatedPrompts": False,
        "artifactNames": [],
        "initialPrompt": "Fix the bug",
        "titleOrSomethingLikeIt": "Fix the bug",
        "interface": "TERMINAL",
        "systemPrompt": None,
        "model": "CLAUDE-4-OPUS",
        "harnessCapabilities": {
            "supportsChatInterface": True,
            "supportsInteractiveBackchannel": True,
            "supportsSkills": True,
            "supportsSubAgents": True,
            "supportsImageInput": True,
            "supportsFastMode": True,
            "supportsContextReset": True,
            "supportsCompaction": True,
            "supportsBackgroundTasks": True,
            "supportsSessionResume": True,
            "supportsToolUseRendering": True,
            "supportsFileAttachments": True,
            "supportsInterruption": True,
            "supportsFileReferences": True,
            "supportsModelSelection": True,
        },
        "availableModels": [],
        "selectedModelId": None,
        "sourcesBackendModels": False,
        "configurationSettingsSection": "DEPENDENCIES",
        "fastMode": False,
        "effort": "medium",
        "isSmoothStreamingSupported": True,
        "isDeleted": False,
        "title": "Fix the bug",
        "status": "RUNNING",
        "goal": "Fix the bug",
        "isDev": False,
        "lastReadAt": None,
        "workspacePeekStatus": "WORKING",
        "currentActivity": None,
        "lastActivity": None,
        "taskCompleted": 0,
        "taskTotal": 0,
        "currentTaskSubject": None,
        "waitingDetail": None,
        "errorDetail": None,
    }


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
        "workspaceIds": workspace_ids if workspace_ids is not None else ["ws_newrun123"],
    }


_GROUPS_DISABLED_BODY = {
    "detail": {
        "error": "workspace_groups_disabled",
        "message": "Workspace groups are an experimental feature; enable them in Settings first.",
    }
}


def _mock_auto_group(base_url: str = "http://localhost:5050") -> respx.Route:
    # Workspace-creating commands auto-group by default, so every happy-path
    # run needs the group-create endpoint mocked.
    return respx.post(f"{base_url}/api/v1/workspace-groups").mock(
        return_value=Response(200, json=_group_response_dict())
    )


def _mock_workspace_and_agent() -> None:
    _mock_preview_branch_name()
    _mock_auto_group()
    respx.post("http://localhost:5050/api/v1/workspaces").mock(
        return_value=Response(200, json=_workspace_response_dict())
    )
    respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
        return_value=Response(200, json=_task_response_dict())
    )


class TestRun:
    @respx.mock
    def test_run_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 0
        assert "ws_newrun123" in result.output
        assert "tsk_abc123def456" in result.output

    @respx.mock
    def test_run_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["workspace_id"] == "ws_newrun123"
        assert data["agent_id"] == "tsk_abc123def456"
        assert data["prompt"] == "Fix the bug"

    @respx.mock
    def test_run_with_strategy(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_auto_group()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="IN_PLACE"))
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--strategy", "in-place"])

        assert result.exit_code == 0

    @respx.mock
    def test_run_with_worktree_strategy_and_branch_name(self, runner: CliRunner) -> None:
        """sculpt run --strategy worktree --branch-name <name> forwards the name unchanged."""
        _mock_session()
        _mock_initialize_project()
        _mock_auto_group()
        preview_route = respx.get("http://localhost:5050/api/v1/workspaces/preview-branch-name").mock(
            return_value=Response(200, json={"branchName": "should-not-be-used"})
        )
        ws_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="WORKTREE"))
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(
            app,
            [
                "run",
                "Fix the bug",
                "--repo",
                "/tmp/test",
                "--strategy",
                "worktree",
                "--branch",
                "main",
                "--branch-name",
                "dev/fix-bug",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert not preview_route.called
        assert ws_route.called
        request_body = json.loads(ws_route.calls[0].request.content)
        assert request_body["initializationStrategy"] == "WORKTREE"
        assert request_body["sourceBranch"] == "main"
        assert request_body["requestedBranchName"] == "dev/fix-bug"
        data = json.loads(result.stdout)
        assert data["strategy"] == "WORKTREE"

    @respx.mock
    def test_run_with_worktree_strategy_autogenerates_branch_name(self, runner: CliRunner) -> None:
        """sculpt run --strategy worktree without --branch-name auto-fills via preview-branch-name."""
        _mock_session()
        _mock_initialize_project()
        _mock_auto_group()
        preview_route = respx.get("http://localhost:5050/api/v1/workspaces/preview-branch-name").mock(
            return_value=Response(200, json={"branchName": "dev/auto-from-name"})
        )
        ws_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="WORKTREE"))
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(
            app,
            [
                "run",
                "Fix the bug",
                "--repo",
                "/tmp/test",
                "--strategy",
                "worktree",
                "--branch",
                "main",
                "--name",
                "Fix Bug",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert preview_route.called
        request_body = json.loads(ws_route.calls[0].request.content)
        assert request_body["requestedBranchName"] == "dev/auto-from-name"

    @respx.mock
    def test_run_passes_target_branch(self, runner: CliRunner) -> None:
        """sculpt run --target-branch forwards the value in the workspace create body."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        _mock_auto_group()
        ws_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(
            app,
            [
                "run",
                "Fix the bug",
                "--repo",
                "/tmp/test",
                "--branch",
                "feature",
                "--target-branch",
                "feature",
            ],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert ws_route.called
        request_body = json.loads(ws_route.calls[0].request.content)
        assert request_body["targetBranch"] == "feature"

    @respx.mock
    def test_run_with_model(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "-m", "sonnet"])

        assert result.exit_code == 0

    @respx.mock
    def test_run_with_files(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(
            app,
            ["run", "Fix the bug", "--repo", "/tmp/test", "--file", "a.py", "--file", "b.py"],
        )

        assert result.exit_code == 0

    @respx.mock
    def test_run_with_branch_and_name(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(
            app,
            ["run", "Fix the bug", "--repo", "/tmp/test", "--branch", "dev", "--name", "My Agent"],
        )

        assert result.exit_code == 0

    @respx.mock
    def test_run_workspace_creation_fails(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(422, json={"detail": [{"msg": "error"}]})
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 1

    @respx.mock
    def test_run_agent_creation_fails(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_auto_group()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(422, json={"detail": [{"msg": "error"}]})
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 1

    @respx.mock
    def test_run_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(side_effect=ConnectError("Connection refused"))

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 1

    def test_run_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "-m", "invalid"])

        assert result.exit_code == 1

    @respx.mock
    def test_run_invalid_strategy(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--strategy", "bogus"])

        assert result.exit_code == 1
        assert "Invalid strategy 'bogus'" in (result.stderr or result.output)

    def test_run_help_documents_sculpt_project_id(self, runner: CliRunner) -> None:
        """SCU-1309: `sculpt run --help` must surface SCULPT_PROJECT_ID so agents and
        users can discover the env-var resolution path. Without this, the only
        documented input is --repo, which funnels callers into the 409 'already
        added' bug whenever the target repo is registered. Discoverability lives
        in --help — if it's not there, callers cannot find it."""
        result = runner.invoke(app, ["run", "--help"])

        assert result.exit_code == 0
        assert "SCULPT_PROJECT_ID" in result.output


def _mock_registrations(*registrations: dict[str, Any]) -> None:
    respx.get("http://localhost:5050/api/v1/terminal-agent-registrations").mock(
        return_value=Response(200, json={"registrations": list(registrations)})
    )


_CLAUDE_CLI_REGISTRATION = {
    "registrationId": "claude-code",
    "displayName": "Claude CLI",
    "launchCommand": "claude",
}


_PI_MODEL_DICT = {"provider": "anthropic", "modelId": "claude-opus-4-8", "displayName": "Claude Opus 4.8"}


def _mock_pi_models(available: list[dict[str, Any]], default: dict[str, Any] | None) -> None:
    respx.get("http://localhost:5050/api/v1/pi/models").mock(
        return_value=Response(200, json={"availableModels": available, "defaultModel": default})
    )


class TestRunHarness:
    @respx.mock
    def test_run_with_harness_pi_sends_backend_model(self, runner: CliRunner) -> None:
        """A pi prompt carries a backend_model from pi's own catalog — never a
        placeholder Claude model."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        _mock_auto_group()
        _mock_pi_models([_PI_MODEL_DICT], _PI_MODEL_DICT)
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        agent_route = respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Pi"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        body = json.loads(agent_route.calls.last.request.content)
        assert body["agentType"] == "pi"
        assert body["backendModel"]["modelId"] == "claude-opus-4-8"
        assert body["backendModel"]["provider"] == "anthropic"
        assert "model" not in body

    @respx.mock
    def test_run_with_harness_pi_errors_when_no_usable_model(self, runner: CliRunner) -> None:
        """An empty pi catalog (no authenticated provider) fails up front with the
        authenticate pointer — before any workspace is created."""
        _mock_session()
        _mock_initialize_project()
        _mock_pi_models([], None)

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Pi"])

        assert result.exit_code != 0
        assert "authenticate a provider" in result.output + (result.stderr or "")

    @respx.mock
    def test_run_with_harness_pi_rejects_claude_model_flag(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()

        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Pi", "--model", "sonnet"]
        )

        assert result.exit_code != 0
        assert "does not apply to the Pi harness" in result.output + (result.stderr or "")

    @respx.mock
    def test_run_with_harness_pi_rejects_explicit_default_model_flag(self, runner: CliRunner) -> None:
        """--model is rejected for pi even when it names the flag's default —
        an explicit choice is never silently ignored."""
        _mock_session()
        _mock_initialize_project()

        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Pi", "--model", "opus"]
        )

        assert result.exit_code != 0
        assert "does not apply to the Pi harness" in result.output + (result.stderr or "")

    @respx.mock
    def test_run_without_harness_omits_agent_type(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        _mock_auto_group()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        agent_route = respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        # No --harness: the CLI sends no agent type, so the server applies the MRU.
        body = json.loads(agent_route.calls.last.request.content)
        assert "agentType" not in body

    @respx.mock
    def test_run_with_terminal_harness_is_rejected(self, runner: CliRunner) -> None:
        _mock_session()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Terminal"])

        assert result.exit_code == 1
        assert "sculpt run" in result.stderr

    @respx.mock
    def test_run_with_registered_harness_is_rejected(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_registrations(_CLAUDE_CLI_REGISTRATION)

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Claude CLI"])

        assert result.exit_code == 1
        assert "sculpt run" in result.stderr

    @respx.mock
    def test_run_with_invalid_harness_errors(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_registrations()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--harness", "Bogus"])

        assert result.exit_code == 1
        assert "Invalid harness" in result.stderr


class TestRunGrouping:
    """Grouping behavior of `sculpt run` (REQ-CLI-2/3/4, REQ-FLAG-4)."""

    @respx.mock
    def test_run_auto_creates_cli_group_by_default(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        group_route = _mock_auto_group()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert group_route.called
        request_body = json.loads(group_route.calls.last.request.content)
        assert request_body["projectId"] == "prj_test123"
        assert request_body["workspaceIds"] == ["ws_newrun123"]
        assert request_body["createdViaCli"] is True
        data = json.loads(result.stdout)
        assert data["group_id"] == "wsg_auto123"

    @respx.mock
    def test_run_text_output_includes_group(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_workspace_and_agent()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "Group: wsg_auto123" in result.output

    @respx.mock
    def test_run_no_group_skips_grouping(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        group_route = _mock_auto_group()

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--no-group", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert not group_route.called
        data = json.loads(result.stdout)
        assert data["group_id"] is None

    @respx.mock
    def test_run_group_joins_existing_group(self, runner: CliRunner) -> None:
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
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        create_group_route = respx.post("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(200, json=_group_response_dict())
        )
        add_route = respx.post("http://localhost:5050/api/v1/workspace-groups/wsg_existing1/workspaces").mock(
            return_value=Response(
                200,
                json=_group_response_dict(object_id="wsg_existing1", workspace_ids=["ws_sibling", "ws_newrun123"]),
            )
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--group", "wsg_existing", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert add_route.called
        assert not create_group_route.called
        request_body = json.loads(add_route.calls.last.request.content)
        assert request_body["workspaceId"] == "ws_newrun123"
        data = json.loads(result.stdout)
        assert data["group_id"] == "wsg_existing1"

    def test_run_group_and_no_group_are_mutually_exclusive(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--group", "wsg_x", "--no-group"])

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stderr

    @respx.mock
    def test_run_proceeds_loose_when_groups_disabled(self, runner: CliRunner) -> None:
        """Implicit auto-group swallows the disabled-experiment 409 (REQ-FLAG-4)."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        agent_route = respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(409, json=_GROUPS_DISABLED_BODY)
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert agent_route.called
        assert "ungrouped" in result.stderr
        assert "Group:" not in result.output

    @respx.mock
    def test_run_json_proceeds_loose_when_groups_disabled(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(409, json=_GROUPS_DISABLED_BODY)
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--json"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = json.loads(result.stdout)
        assert data["group_id"] is None
        assert "ungrouped" not in (result.stderr or "")

    @respx.mock
    def test_run_survives_group_create_failure(self, runner: CliRunner) -> None:
        """A grouping failure after workspace creation degrades to a loose
        workspace with a warning — it must never abort before the agent is
        created and the ids are printed."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        agent_route = respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(500, json={"detail": "boom"})
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert agent_route.called
        assert "ws_newrun123" in result.output
        assert "grouping failed" in result.stderr
        assert "Group:" not in result.output

    @respx.mock
    def test_run_survives_group_join_failure(self, runner: CliRunner) -> None:
        """The explicit --group path degrades the same way once the workspace
        exists (the target is pre-resolved, but it can dissolve in between)."""
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
        respx.get("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(200, json={"groups": [_group_response_dict()]})
        )
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )
        agent_route = respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )
        respx.post("http://localhost:5050/api/v1/workspace-groups/wsg_auto123/workspaces").mock(
            return_value=Response(404, json={"detail": "Workspace group not found"})
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--group", "wsg_auto123"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert agent_route.called
        assert "ws_newrun123" in result.output
        assert "grouping failed" in result.stderr

    @respx.mock
    def test_run_explicit_group_fails_when_groups_disabled(self, runner: CliRunner) -> None:
        """Explicit --group surfaces the disabled error before creating anything."""
        _mock_session()
        _mock_initialize_project()
        respx.get("http://localhost:5050/api/v1/workspace-groups").mock(
            return_value=Response(409, json=_GROUPS_DISABLED_BODY)
        )
        ws_route = respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict())
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test", "--group", "wsg_x"])

        assert result.exit_code == 1
        assert "disabled" in result.stderr
        assert not ws_route.called


class TestWorkspaceCreateHelp:
    """SCU-1309: workspace create has the same --repo plumbing as run, and the same
    discoverability gap. Document SCULPT_PROJECT_ID there too."""

    def test_workspace_create_help_documents_sculpt_project_id(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["workspace", "create", "--help"])

        assert result.exit_code == 0
        assert "SCULPT_PROJECT_ID" in result.output
