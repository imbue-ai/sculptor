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


def _mock_workspace_and_agent() -> None:
    _mock_preview_branch_name()
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
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            return_value=Response(200, json=_workspace_response_dict(strategy="IN_PLACE"))
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_newrun123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "--strategy", "in-place"]
        )

        assert result.exit_code == 0

    @respx.mock
    def test_run_with_worktree_strategy_and_branch_name(self, runner: CliRunner) -> None:
        """sculpt run --strategy worktree --branch-name <name> forwards the name unchanged."""
        _mock_session()
        _mock_initialize_project()
        preview_route = respx.get(
            "http://localhost:5050/api/v1/workspaces/preview-branch-name"
        ).mock(return_value=Response(200, json={"branchName": "should-not-be-used"}))
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
        preview_route = respx.get(
            "http://localhost:5050/api/v1/workspaces/preview-branch-name"
        ).mock(return_value=Response(200, json={"branchName": "dev/auto-from-name"}))
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

        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "-m", "sonnet"]
        )

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
        respx.post("http://localhost:5050/api/v1/workspaces").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["run", "Fix the bug", "--repo", "/tmp/test"])

        assert result.exit_code == 1

    def test_run_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "-m", "invalid"]
        )

        assert result.exit_code == 1

    @respx.mock
    def test_run_invalid_strategy(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()

        result = runner.invoke(
            app, ["run", "Fix the bug", "--repo", "/tmp/test", "--strategy", "bogus"]
        )

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


class TestRunHarness:
    @respx.mock
    def test_run_with_harness_pi_sends_pi_agent_type(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
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

    @respx.mock
    def test_run_without_harness_omits_agent_type(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_initialize_project()
        _mock_preview_branch_name()
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


class TestWorkspaceCreateHelp:
    """SCU-1309: workspace create has the same --repo plumbing as run, and the same
    discoverability gap. Document SCULPT_PROJECT_ID there too."""

    def test_workspace_create_help_documents_sculpt_project_id(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["workspace", "create", "--help"])

        assert result.exit_code == 0
        assert "SCULPT_PROJECT_ID" in result.output
