"""Unit tests for agent create and list commands."""

import asyncio
import json
import os
from typing import Any
from unittest.mock import patch

import pytest
import respx
import typer
from httpx import ConnectError
from httpx import Response
from sculpt.auth import MODEL_MAPPING
from sculpt.commands.agent import _resolve_send_model
from sculpt.main import app
from sculpt.ws_client import AgentNotFoundError
from sculpt.ws_client import AgentSnapshot
from sculpt.ws_client import ExitReason
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _passthrough_resolve_agent_id() -> Any:
    """Treat the agent prefix arg as a full id during unit tests.

    Production code resolves the prefix via an HTTP endpoint; in unit tests
    we don't run the server, so we short-circuit the resolver to return its
    second positional arg unchanged.
    """
    with patch("sculpt.commands.agent.resolve_agent_id", side_effect=lambda _client, prefix, _json: prefix) as p:
        yield p


def _mock_session(base_url: str = "http://localhost:5050") -> None:
    respx.get(f"{base_url}/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )


def _task_response_dict(
    task_id: str = "tsk_abc123def456",
    workspace_id: str = "ws_test123",
    title: str = "Test task",
    status: str = "RUNNING",
    model: str | None = "CLAUDE-4-SONNET",
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
        "initialPrompt": "Test prompt",
        "titleOrSomethingLikeIt": "Test task title",
        "interface": "TERMINAL",
        "systemPrompt": None,
        "model": model,
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
        "title": title,
        "status": status,
        "goal": "Test goal",
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


def _mock_registrations(*registrations: dict[str, Any]) -> None:
    respx.get("http://localhost:5050/api/v1/terminal-agent-registrations").mock(
        return_value=Response(200, json={"registrations": list(registrations)})
    )


_CLAUDE_CLI_REGISTRATION = {
    "registrationId": "claude-code",
    "displayName": "Claude CLI",
    "launchCommand": "claude",
}


def _mock_workspaces(*object_ids: str) -> None:
    workspaces = [
        {
            "objectId": oid,
            "projectId": "prj_test123",
            "description": "Test",
            "initializationStrategy": "CLONE",
            "sourceBranch": "main",
            "isDeleted": False,
            "createdAt": "2024-01-15T10:30:00Z",
            "projectName": "test-project",
            "agentCount": 1,
            "isOpen": True,
            "lastActivityAt": "2024-01-15T11:00:00Z",
        }
        for oid in object_ids
    ]
    respx.get("http://localhost:5050/api/v1/workspaces/recent").mock(
        return_value=Response(200, json={"workspaces": workspaces})
    )


class TestAgentCreate:
    @respx.mock
    def test_create_with_prompt(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "-p", "Do something", "-m", "sonnet"])

        assert result.exit_code == 0
        assert "tsk_abc123def456" in result.output

    @respx.mock
    def test_create_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "-p", "Do something", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "tsk_abc123def456"
        assert data["status"] == "RUNNING"

    @respx.mock
    def test_create_without_prompt(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123"])

        assert result.exit_code == 0

    def test_create_missing_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "create", "-p", "Do something"])

        assert result.exit_code == 1

    @respx.mock
    def test_create_workspace_from_env(self, runner: CliRunner) -> None:
        os.environ["SCULPT_WORKSPACE_ID"] = "ws_test123"
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-p", "Do something"])

        assert result.exit_code == 0

    def test_create_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "-m", "invalid", "-p", "Do something"])

        assert result.exit_code == 1

    @respx.mock
    def test_create_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "-p", "Do something"])

        assert result.exit_code == 1


class TestAgentCreateHarness:
    @respx.mock
    def test_create_with_harness_pi_sends_pi_agent_type(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        route = respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "--harness", "Pi"])

        assert result.exit_code == 0
        body = json.loads(route.calls.last.request.content)
        assert body["agentType"] == "pi"

    @respx.mock
    def test_create_with_harness_terminal_sends_terminal_agent_type(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        route = respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "--harness", "Terminal"])

        assert result.exit_code == 0
        body = json.loads(route.calls.last.request.content)
        assert body["agentType"] == "terminal"

    @respx.mock
    def test_create_with_harness_claude_cli_resolves_registered_agent(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        _mock_registrations(_CLAUDE_CLI_REGISTRATION)
        route = respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "--harness", "Claude CLI"])

        assert result.exit_code == 0
        body = json.loads(route.calls.last.request.content)
        assert body["agentType"] == "registered"
        assert body["registrationId"] == "claude-code"

    @respx.mock
    def test_create_without_harness_omits_agent_type_so_server_uses_mru(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        route = respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123"])

        assert result.exit_code == 0
        # With no --harness, the CLI sends nothing and lets the server apply the
        # user's most-recently-used harness; the request must not pin a type.
        body = json.loads(route.calls.last.request.content)
        assert "agentType" not in body
        assert "registrationId" not in body

    @respx.mock
    def test_create_with_invalid_harness_errors_and_lists_valid_options(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        _mock_registrations()

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "--harness", "Bogus"])

        assert result.exit_code == 1
        assert "Claude" in result.stderr
        assert "Terminal" in result.stderr

    @respx.mock
    def test_create_terminal_harness_with_prompt_is_rejected(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")

        result = runner.invoke(
            app, ["agent", "create", "-w", "ws_test123", "--harness", "Terminal", "-p", "Do something"]
        )

        assert result.exit_code == 1
        assert "prompt" in result.stderr


class TestAgentList:
    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_for_workspace(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = [_make_snapshot()]

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])

        assert result.exit_code == 0
        assert "tsk_abc123d" in result.output
        assert "RUNNING" in result.output

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_json(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = [_make_snapshot()]

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["id"] == "tsk_abc123def456"

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_terminal_agent_reports_no_model(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        """Terminal agents carry no model (SCU-1580): the list must not invent one."""
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = [_make_snapshot(model=None)]

        # Table output renders a placeholder, never a model name.
        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])
        assert result.exit_code == 0
        assert "opus" not in result.output
        assert "sonnet" not in result.output

        # JSON output reports the model as null.
        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["model"] is None

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_list_all(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = [_make_snapshot()]

        result = runner.invoke(app, ["agent", "list", "--all"])

        assert result.exit_code == 0
        assert "tsk_abc123d" in result.output

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_status_filter(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = [
            _make_snapshot(task_id="tsk_running1", status="RUNNING"),
            _make_snapshot(task_id="tsk_ready1", status="READY"),
        ]

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123", "--status", "READY"])

        assert result.exit_code == 0
        assert "tsk_ready1" in result.output
        assert "tsk_running" not in result.output

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_status_filter_case_insensitive(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = [_make_snapshot(status="RUNNING")]

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123", "--status", "running"])

        assert result.exit_code == 0
        assert "RUNNING" in result.output

    def test_list_status_filter_invalid(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123", "--status", "BOGUS"])

        assert result.exit_code == 1
        assert "Invalid status" in (result.output + result.stderr)

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_list_empty(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        mock_fetch.return_value = []

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])

        assert result.exit_code == 0
        assert "No agents found." in result.output

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_list_connection_error(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = Exception("Connection refused")

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])

        assert result.exit_code == 1


class TestAgentShow:
    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_by_exact_id(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "tsk_abc123def456" in result.output
        assert "RUNNING" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_by_prefix(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "show", "tsk_abc"])

        assert result.exit_code == 0
        assert "tsk_abc123def456" in result.output
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[0][2] == "tsk_abc"

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_json(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "tsk_abc123def456"
        assert data["status"] == "RUNNING"
        assert data["workspace_id"] == "ws_test123"
        assert "last_activity" in data
        assert "current_activity" in data
        assert "task_completed" in data

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_ambiguous_prefix(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = AgentNotFoundError("Ambiguous prefix 'tsk_abc'")

        result = runner.invoke(app, ["agent", "show", "tsk_abc"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_not_found(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = AgentNotFoundError("No agent matches prefix 'nonexistent'")

        result = runner.invoke(app, ["agent", "show", "nonexistent"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_with_artifacts(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(artifact_names=["logs", "diff"])

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "logs, diff" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_with_activity_fields(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            current_activity="Editing main.py",
            task_completed=2,
            task_total=5,
            current_task_subject="Add tests",
            waiting_detail="Waiting for user input",
        )

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Activity: Editing main.py" in result.output
        assert "2/5 tasks" in result.output
        assert "Add tests" in result.output
        assert "Waiting: Waiting for user input" in result.output


class TestAgentDelete:
    @respx.mock
    def test_delete_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123", "-y"])

        assert result.exit_code == 0
        assert "deleted" in result.output

    @respx.mock
    def test_delete_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123", "--json", "-y"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["deleted"] is True
        assert data["id"] == "tsk_abc123def456"

    @respx.mock
    def test_delete_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "delete", "tsk_abc", "-w", "ws_test123", "-y"])

        assert result.exit_code == 0

    @respx.mock
    def test_delete_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )

        result = runner.invoke(app, ["agent", "delete", "nonexistent", "-w", "ws_test123"])

        assert result.exit_code == 1

    def test_delete_missing_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "delete", "tsk_abc123"])

        assert result.exit_code == 1


class TestAgentRename:
    @respx.mock
    def test_rename_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, json=_task_response_dict(title="New Title"))
        )

        result = runner.invoke(app, ["agent", "rename", "tsk_abc123def456", "New Title", "-w", "ws_test123"])

        assert result.exit_code == 0
        assert "renamed" in result.output
        assert "New Title" in result.output

    @respx.mock
    def test_rename_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, json=_task_response_dict(title="New Title"))
        )

        result = runner.invoke(app, ["agent", "rename", "tsk_abc123def456", "New Title", "-w", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "tsk_abc123def456"
        assert data["title"] == "New Title"

    @respx.mock
    def test_rename_by_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.patch("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456").mock(
            return_value=Response(200, json=_task_response_dict(title="New Title"))
        )

        result = runner.invoke(app, ["agent", "rename", "tsk_abc", "New Title", "-w", "ws_test123"])

        assert result.exit_code == 0

    @respx.mock
    def test_rename_not_found(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )

        result = runner.invoke(app, ["agent", "rename", "nonexistent", "New Title", "-w", "ws_test123"])

        assert result.exit_code == 1

    def test_rename_missing_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "rename", "tsk_abc123", "New Title"])

        assert result.exit_code == 1


class TestAgentSend:
    @respx.mock
    def test_send_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix the bug", "-w", "ws_test123", "-m", "sonnet"]
        )

        assert result.exit_code == 0
        assert "Message sent" in result.output

    @respx.mock
    def test_send_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "Fix the bug", "-w", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["sent"] is True
        assert data["agent_id"] == "tsk_abc123def456"

    @respx.mock
    def test_send_with_files(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(
            app,
            [
                "agent",
                "send",
                "tsk_abc123def456",
                "Fix it",
                "-w",
                "ws_test123",
                "--file",
                "path/to/file1.py",
                "--file",
                "path/to/file2.py",
            ],
        )

        assert result.exit_code == 0

    def test_send_missing_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "send", "tsk_abc123", "hello"])

        assert result.exit_code == 1

    def test_send_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "send", "tsk_abc123", "hello", "-w", "ws_test123", "-m", "invalid"])

        assert result.exit_code == 1

    @respx.mock
    def test_send_prefix_matching(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc", "Fix it", "-w", "ws_test123"])

        assert result.exit_code == 0

    @respx.mock
    def test_send_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123"])

        assert result.exit_code == 1

    @respx.mock
    def test_send_http_error_exits_nonzero(self, runner: CliRunner) -> None:
        """When the backend returns a non-200 status (e.g. 409), the CLI must fail."""
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(
                409,
                json={"detail": "Cannot send a message while the agent is waiting for a response to AskUserQuestion."},
            )
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123"])

        assert result.exit_code == 1, f"Expected exit code 1 but got {result.exit_code}; output: {result.output}"
        assert "Message sent" not in result.output

    @respx.mock
    def test_send_http_error_json_mode(self, runner: CliRunner) -> None:
        """In --json mode, HTTP errors should produce structured JSON on stderr."""
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(
                409,
                json={"detail": "Cannot send a message while the agent is waiting for a response to AskUserQuestion."},
            )
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123", "--json"])

        assert result.exit_code == 1
        assert "Message sent" not in result.output


def _make_snapshot(
    task_id: str = "tsk_abc123def456",
    status: str = "RUNNING",
    model: str | None = "CLAUDE-4-SONNET",
    current_activity: str | None = None,
    last_activity: str | None = None,
    waiting_detail: str | None = None,
    waiting_options: list[str] | None = None,
    error_detail: str | None = None,
    task_completed: int = 0,
    task_total: int = 0,
    current_task_subject: str | None = None,
    artifact_names: list[str] | None = None,
    messages: list[dict[str, Any]] | None = None,
    workspace_id: str = "ws_test123",
    project_id: str = "prj_test123",
) -> AgentSnapshot:
    return AgentSnapshot(
        task_id=task_id,
        status=status,
        task_status="RUNNING",
        current_activity=current_activity,
        last_activity=last_activity,
        task_completed=task_completed,
        task_total=task_total,
        current_task_subject=current_task_subject,
        waiting_detail=waiting_detail,
        waiting_options=waiting_options,
        error_detail=error_detail,
        updated_at="2026-01-15T10:35:00Z",
        title="Test task",
        model=model,
        interface="TERMINAL",
        project_id=project_id,
        workspace_id=workspace_id,
        created_at="2026-01-15T10:30:00Z",
        is_deleted=False,
        artifact_names=artifact_names or [],
        messages=messages or [],
    )


class TestAgentStatus:
    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_success(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "RUNNING" in result.output
        assert "tsk_abc123def456" in result.output
        assert "Updated:" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_json(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "tsk_abc123def456"
        assert data["status"] == "RUNNING"
        assert "last_activity" in data

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_with_activity(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(current_activity="Writing tests")

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Writing tests" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_prefix_matching(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "status", "tsk_abc"])

        assert result.exit_code == 0
        assert "tsk_abc123def456" in result.output
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[0][2] == "tsk_abc"

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_agent_not_found(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = AgentNotFoundError("No agent matches prefix 'tsk_nope'")

        result = runner.invoke(app, ["agent", "status", "tsk_nope"])

        assert result.exit_code == 1
        assert "Agent not found" in result.stderr

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_timeout(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = asyncio.TimeoutError()

        result = runner.invoke(app, ["agent", "status", "tsk_abc"])

        assert result.exit_code == 1
        assert "timed out" in result.stderr

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_progress_formatting(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            task_completed=3, task_total=7, current_task_subject="Implementing feature"
        )

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "3/7 tasks" in result.output
        assert "Implementing feature" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_conditional_fields(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Activity:" not in result.output
        assert "Waiting:" not in result.output
        assert "Error:" not in result.output
        assert "Progress:" not in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_follow_terminal_state(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            on_status: Any,
            _on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_status(_make_snapshot(status="READY"))
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 0
        assert "READY" in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_follow_waiting(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            on_status: Any,
            _on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_status(_make_snapshot(status="WAITING", waiting_detail="User input needed"))
            return ExitReason.WAITING

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 2

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_follow_json(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            on_status: Any,
            _on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_status(_make_snapshot(status="RUNNING"))
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--follow", "--json"])

        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        status_line = json.loads(lines[0])
        assert status_line["type"] == "status"
        assert status_line["data"]["status"] == "RUNNING"
        exit_line = json.loads(lines[-1])
        assert exit_line["type"] == "exit"


def _chat_message_dict(
    role: str = "assistant",
    msg_id: str = "msg_001",
    text: str = "Hello",
    timestamp: str = "2026-03-20T19:31:00Z",
    content: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "id": msg_id,
        "content": content if content is not None else [{"type": "text", "text": text}],
        "approximateCreationTime": timestamp,
        "turnMetrics": None,
        "stopped": False,
    }


class TestAgentMessages:
    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_success(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            messages=[
                _chat_message_dict(role="user", msg_id="msg_001", text="what is going on"),
                _chat_message_dict(role="assistant", msg_id="msg_002", text="I am working on it"),
            ]
        )

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "[user]" in result.output
        assert "[assistant]" in result.output
        assert "what is going on" in result.output
        assert "I am working on it" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_empty(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "No messages." in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_json(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        msgs = [
            _chat_message_dict(role="user", msg_id="msg_001", text="hello"),
            _chat_message_dict(role="assistant", msg_id="msg_002", text="hi"),
        ]
        mock_fetch.return_value = _make_snapshot(messages=msgs)

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "assistant"
        assert "approximateCreationTime" in data[0]

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_limit(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        msgs = [_chat_message_dict(msg_id=f"msg_{i}", text=f"Message {i}") for i in range(5)]
        mock_fetch.return_value = _make_snapshot(messages=msgs)

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--limit", "2"])

        assert result.exit_code == 0
        assert "Message 3" in result.output
        assert "Message 4" in result.output
        assert "Message 0" not in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_tail(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        msgs = [_chat_message_dict(msg_id=f"msg_{i}", text=f"Message {i}") for i in range(5)]
        mock_fetch.return_value = _make_snapshot(messages=msgs)

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--tail", "2"])

        assert result.exit_code == 0
        assert "Message 3" in result.output
        assert "Message 4" in result.output
        assert "Message 0" not in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_not_found(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = AgentNotFoundError("No agent matches prefix 'tsk_nope'")

        result = runner.invoke(app, ["agent", "messages", "tsk_nope"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_timeout(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.side_effect = asyncio.TimeoutError()

        result = runner.invoke(app, ["agent", "messages", "tsk_abc"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_with_tool_use(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        msg = _chat_message_dict(
            role="assistant",
            content=[
                {"type": "text", "text": "Let me read that file."},
                {"type": "tool_use", "name": "Read", "id": "tu1", "input": {"file_path": "src/main.py"}},
            ],
        )
        mock_fetch.return_value = _make_snapshot(messages=[msg])

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "[Read] src/main.py" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_tool_result_hidden(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        msg = _chat_message_dict(
            role="assistant",
            content=[
                {"type": "tool_use", "name": "Read", "id": "tu1", "input": {"file_path": "src/main.py"}},
                {
                    "type": "tool_result",
                    "toolUseId": "tu1",
                    "toolName": "Read",
                    "content": {"text": "file contents"},
                    "isError": False,
                },
            ],
        )
        mock_fetch.return_value = _make_snapshot(messages=[msg])

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "[Read] src/main.py" in result.output
        assert "tool_result" not in result.output
        assert "file contents" not in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_follow(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            _on_status: Any,
            on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_messages(
                [
                    _chat_message_dict(role="user", msg_id="msg_001", text="hello"),
                    _chat_message_dict(role="assistant", msg_id="msg_002", text="hi there"),
                ]
            )
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 0
        assert "hello" in result.output
        assert "hi there" in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_follow_json(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            _on_status: Any,
            on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_messages([_chat_message_dict(role="assistant", msg_id="msg_001", text="hi")])
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--follow", "--json"])

        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        msg_line = json.loads(lines[0])
        assert msg_line["type"] == "message"
        assert msg_line["data"]["role"] == "assistant"


class TestAgentInterrupt:
    @respx.mock
    def test_interrupt_success(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/interrupt").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "interrupt", "tsk_abc123def456", "-w", "ws_test123"])

        assert result.exit_code == 0
        assert "interrupted" in result.output

    @respx.mock
    def test_interrupt_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/interrupt").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "interrupt", "tsk_abc123def456", "-w", "ws_test123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["interrupted"] is True
        assert data["id"] == "tsk_abc123def456"

    @respx.mock
    def test_interrupt_prefix_matching(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/interrupt").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "interrupt", "tsk_abc", "-w", "ws_test123"])

        assert result.exit_code == 0

    @respx.mock
    def test_interrupt_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/interrupt").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["agent", "interrupt", "tsk_abc123def456", "-w", "ws_test123"])

        assert result.exit_code == 1


class TestAgentSendFollow:
    @respx.mock
    @patch("sculpt.commands._follow_helpers.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_send_follow(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        def side_effect(
            _base_url: str,
            _token: str,
            _agent_id: str,
            _on_status: Any,
            on_messages: Any,
            _on_reconnect: Any,
            **_kwargs: Any,
        ) -> ExitReason:
            on_messages([_chat_message_dict(role="assistant", msg_id="msg_001", text="Done!")])
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix the bug", "-w", "ws_test123", "--follow"]
        )

        assert result.exit_code == 0
        assert "Message sent" in result.stderr
        assert "Done!" in result.output

    @respx.mock
    @patch("sculpt.commands._follow_helpers.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_send_follow_waiting_exit_code(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        mock_follow.return_value = ExitReason.WAITING

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix the bug", "-w", "ws_test123", "--follow"]
        )

        assert result.exit_code == 2


class TestWorkspacePrefixResolution:
    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_agent_list_workspace_prefix(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123abc456")
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_test123abc456")]

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])

        assert result.exit_code == 0
        assert "tsk_abc123d" in result.output

    @respx.mock
    def test_agent_create_workspace_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123abc456")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123abc456/agents").mock(
            return_value=Response(200, json=_task_response_dict(workspace_id="ws_test123abc456"))
        )

        result = runner.invoke(app, ["agent", "create", "-w", "ws_test123", "-p", "test"])

        assert result.exit_code == 0

    @respx.mock
    def test_agent_delete_workspace_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123abc456")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123abc456/agents").mock(
            return_value=Response(200, json=[_task_response_dict(workspace_id="ws_test123abc456")])
        )
        respx.delete("http://localhost:5050/api/v1/workspaces/ws_test123abc456/agents/tsk_abc123def456").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123", "-y"])

        assert result.exit_code == 0

    @respx.mock
    def test_agent_send_workspace_prefix(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123abc456")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123abc456/agents").mock(
            return_value=Response(200, json=[_task_response_dict(workspace_id="ws_test123abc456")])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123abc456/agents/tsk_abc123def456/messages").mock(
            return_value=Response(200, text="null", headers={"content-type": "application/json"})
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_test123"])

        assert result.exit_code == 0

    @respx.mock
    def test_workspace_prefix_no_match(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_other789")

        result = runner.invoke(app, ["agent", "list", "-w", "ws_nonexistent"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_workspace_prefix_ambiguous(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123abc", "ws_test123def")
        mock_fetch.return_value = []

        result = runner.invoke(app, ["agent", "list", "-w", "ws_test123"])

        assert result.exit_code == 1

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    @respx.mock
    def test_workspace_env_var_prefix_resolution(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        os.environ["SCULPT_WORKSPACE_ID"] = "ws_test123"
        _mock_session()
        _mock_workspaces("ws_test123abc456")
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_test123abc456")]

        result = runner.invoke(app, ["agent", "list"])

        assert result.exit_code == 0
        assert "tsk_abc123d" in result.output


class TestAgentCrossWorkspaceResolution:
    """Workspace scoping for agent actions (send/interrupt/rename/delete).

    An explicit --workspace is authoritative: an agent living elsewhere is an
    error. SCULPT_WORKSPACE_ID is only a disambiguation scope: an agent with no
    match there is looked up across all workspaces, so full IDs work from any
    Sculptor agent shell.
    """

    @patch("sculpt.commands.agent.fetch_all_agents")
    @respx.mock
    def test_send_env_workspace_miss_falls_back_to_actual_workspace(
        self, mock_fetch: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_env123")
        _mock_session()
        _mock_workspaces("ws_env123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_env123/agents").mock(
            return_value=Response(200, json=[])
        )
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_actual456")]
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_actual456/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert route.called
        # The widened lookup goes across all workspaces...
        assert mock_fetch.call_args.kwargs.get("scope") == "all"
        # ...and the cross-workspace action is never silent.
        assert "Agent tsk_abc123def456 is in workspace ws_actual456" in result.stderr

    @patch("sculpt.commands.agent.fetch_all_agents")
    @respx.mock
    def test_send_agent_in_env_workspace_stays_local(
        self, mock_fetch: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_env123")
        _mock_session()
        _mock_workspaces("ws_env123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_env123/agents").mock(
            return_value=Response(200, json=[_task_response_dict(workspace_id="ws_env123")])
        )
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_env123/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert route.called
        mock_fetch.assert_not_called()
        assert "is in workspace" not in result.stderr

    @patch("sculpt.commands.agent.fetch_all_agents")
    @respx.mock
    def test_send_explicit_workspace_mismatch_is_an_error(
        self, mock_fetch: Any, runner: CliRunner
    ) -> None:
        _mock_session()
        _mock_workspaces("ws_other789")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_other789/agents").mock(
            return_value=Response(200, json=[])
        )
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_actual456")]

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_other789"])

        assert result.exit_code == 1
        assert "Agent tsk_abc123def456 is in workspace ws_actual456, not ws_other789" in result.stderr

    @patch("sculpt.commands.agent.fetch_all_agents")
    @respx.mock
    def test_interrupt_env_workspace_miss_hits_actual_workspace(
        self, mock_fetch: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_WORKSPACE_ID", "ws_env123")
        _mock_session()
        _mock_workspaces("ws_env123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_env123/agents").mock(
            return_value=Response(200, json=[])
        )
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_actual456")]
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_actual456/agents/tsk_abc123def456/interrupt"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "interrupt", "tsk_abc123def456"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert route.called
        assert "Agent tsk_abc123def456 is in workspace ws_actual456" in result.stderr

    @patch("sculpt.commands.agent.fetch_all_agents")
    @respx.mock
    def test_send_without_workspace_context_resolves_globally(
        self, mock_fetch: Any, runner: CliRunner
    ) -> None:
        _mock_session()
        mock_fetch.return_value = [_make_snapshot(workspace_id="ws_actual456")]
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_actual456/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        # A prefix (not just a full id) resolves through the global snapshot list.
        result = runner.invoke(app, ["agent", "send", "tsk_abc", "hello"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert route.called
        # Without an env workspace there is nothing to contrast against — no note.
        assert "is in workspace" not in result.stderr


class TestAgentSendModelDefault:
    """`send` without --model reuses the agent's current model, so a plain
    follow-up never switches the agent to a different model."""

    @respx.mock
    def test_send_defaults_to_agents_current_model(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict(model="CLAUDE-4-HAIKU")])
        )
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_test123"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        body = json.loads(route.calls.last.request.content)
        assert body["model"] == "CLAUDE-4-HAIKU"

    @respx.mock
    def test_send_explicit_model_overrides_current(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict(model="CLAUDE-4-HAIKU")])
        )
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_test123", "-m", "opus"]
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        body = json.loads(route.calls.last.request.content)
        assert body["model"] == MODEL_MAPPING["opus"].value

    @respx.mock
    def test_send_null_current_model_falls_back_to_opus(self, runner: CliRunner) -> None:
        """Terminal agents carry no model; the request field still needs a value."""
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict(model=None)])
        )
        route = respx.post(
            "http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_test123"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        body = json.loads(route.calls.last.request.content)
        assert body["model"] == MODEL_MAPPING["opus"].value

    def test_resolve_send_model_unrecognized_current_model_requires_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A current model this sculpt version doesn't know must not be silently
        swapped for a different one — the user has to pass --model."""
        with pytest.raises(typer.Exit):
            _resolve_send_model(None, "CLAUDE-99-FUTURE", False)
        captured = capsys.readouterr()
        assert "not recognized" in captured.err
        assert "--model" in captured.err

    def test_resolve_send_model_explicit_wins_over_current(self) -> None:
        assert _resolve_send_model("haiku", "CLAUDE-4-SONNET", False) == MODEL_MAPPING["haiku"]

    def test_resolve_send_model_no_flag_no_current_defaults_to_opus(self) -> None:
        assert _resolve_send_model(None, None, False) == MODEL_MAPPING["opus"]


class TestAgentDeleteConfirmation:
    @respx.mock
    def test_delete_prompt_declined_sends_no_request(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        route = respx.delete(
            "http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123"], input="n\n")

        assert result.exit_code != 0
        assert not route.called

    @respx.mock
    def test_delete_prompt_accepted_sends_delete(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        route = respx.delete(
            "http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456"
        ).mock(return_value=Response(200, text="null", headers={"content-type": "application/json"}))

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123"], input="y\n")

        assert result.exit_code == 0
        assert route.called
        assert "deleted" in result.output


class TestAgentIdentityDefaults:
    """show/status/messages with no AGENT_ID argument target the shell's own agent."""

    @pytest.mark.parametrize("command", ["show", "status", "messages"])
    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_no_arg_defaults_to_env_agent(
        self,
        _mock_token: Any,
        mock_fetch: Any,
        command: str,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SCULPT_AGENT_ID", "tsk_abc123def456")
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", command])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "Using agent from SCULPT_AGENT_ID" in result.stderr
        assert mock_fetch.call_args[0][2] == "tsk_abc123def456"

    @pytest.mark.parametrize("command", ["show", "status", "messages"])
    def test_no_arg_without_env_errors(self, command: str, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", command])

        assert result.exit_code == 1
        assert "SCULPT_AGENT_ID" in result.stderr


class TestAgentSelfMarker:
    """`agent list` flags the calling shell's own agent (SCULPT_AGENT_ID)."""

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_list_json_flags_only_own_agent(
        self, _mock_token: Any, mock_fetch: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_AGENT_ID", "tsk_abc123def456")
        mock_fetch.return_value = [
            _make_snapshot(task_id="tsk_abc123def456"),
            _make_snapshot(task_id="tsk_zzz999xyz888"),
        ]

        result = runner.invoke(app, ["agent", "list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        flags = {item["id"]: item["is_self"] for item in data}
        assert flags == {"tsk_abc123def456": True, "tsk_zzz999xyz888": False}

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_list_table_marks_own_agent_with_legend(
        self, _mock_token: Any, mock_fetch: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCULPT_AGENT_ID", "tsk_abc123def456")
        mock_fetch.return_value = [
            _make_snapshot(task_id="tsk_abc123def456"),
            _make_snapshot(task_id="tsk_zzz999xyz888"),
        ]

        result = runner.invoke(app, ["agent", "list", "--all"])

        assert result.exit_code == 0
        assert "tsk_abc123d *" in result.output
        assert "tsk_zzz999x *" not in result.output
        assert "* = this agent (SCULPT_AGENT_ID)" in result.stderr

    @patch("sculpt.commands.agent.fetch_all_agents")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_list_without_env_has_no_marker_or_legend(
        self, _mock_token: Any, mock_fetch: Any, runner: CliRunner
    ) -> None:
        mock_fetch.return_value = [_make_snapshot()]

        result = runner.invoke(app, ["agent", "list", "--all"])

        assert result.exit_code == 0
        assert "*" not in result.output
        assert "* = this agent" not in result.stderr


class TestAgentWaitingOptions:
    """A pending AskUserQuestion's answer options surface in status/show output."""

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_text_renders_options(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            status="WAITING", waiting_detail="Choose a color", waiting_options=["Red", "Blue"]
        )

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Options: Red | Blue" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_json_includes_options(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            status="WAITING", waiting_detail="Choose a color", waiting_options=["Red", "Blue"]
        )

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["waiting_options"] == ["Red", "Blue"]

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_without_pending_question_omits_options(
        self, _mock_token: Any, mock_fetch: Any, runner: CliRunner
    ) -> None:
        mock_fetch.return_value = _make_snapshot()

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Options:" not in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_text_renders_options(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            status="WAITING", waiting_detail="Choose a color", waiting_options=["Red", "Blue"]
        )

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456"])

        assert result.exit_code == 0
        assert "Options: Red | Blue" in result.output

    @patch("sculpt.commands.agent.fetch_agent_state")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_show_json_includes_options(self, _mock_token: Any, mock_fetch: Any, runner: CliRunner) -> None:
        mock_fetch.return_value = _make_snapshot(
            status="WAITING", waiting_detail="Choose a color", waiting_options=["Red", "Blue"]
        )

        result = runner.invoke(app, ["agent", "show", "tsk_abc123def456", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["waiting_options"] == ["Red", "Blue"]


class TestConnectionErrorHint:
    @respx.mock
    def test_send_connection_error_mentions_base_url_and_port_hint(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.get("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=[_task_response_dict()])
        )
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents/tsk_abc123def456/messages").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["agent", "send", "tsk_abc123def456", "hello", "-w", "ws_test123"])

        assert result.exit_code == 1
        assert "http://localhost:5050" in result.stderr
        assert "SCULPT_API_PORT" in result.stderr
        assert "--base-url" in result.stderr
