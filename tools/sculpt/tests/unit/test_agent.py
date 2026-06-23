"""Unit tests for agent create and list commands."""

import asyncio
import json
import os
from typing import Any
from unittest.mock import patch

import pytest
import respx
from httpx import ConnectError
from httpx import Response
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
    model: str = "CLAUDE-4-SONNET",
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

        result = runner.invoke(
            app, ["agent", "create", "-w", "ws_test123", "-p", "Do something", "-m", "sonnet"]
        )

        assert result.exit_code == 0
        assert "tsk_abc123def456" in result.output

    @respx.mock
    def test_create_json(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            return_value=Response(200, json=_task_response_dict())
        )

        result = runner.invoke(
            app, ["agent", "create", "-w", "ws_test123", "-p", "Do something", "--json"]
        )

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
        result = runner.invoke(
            app, ["agent", "create", "-w", "ws_test123", "-m", "invalid", "-p", "Do something"]
        )

        assert result.exit_code == 1

    @respx.mock
    def test_create_connection_error(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/agents").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(
            app, ["agent", "create", "-w", "ws_test123", "-p", "Do something"]
        )

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

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123"])

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

        result = runner.invoke(
            app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123", "--json"]
        )

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

        result = runner.invoke(app, ["agent", "delete", "tsk_abc", "-w", "ws_test123"])

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

        result = runner.invoke(
            app, ["agent", "rename", "tsk_abc123def456", "New Title", "-w", "ws_test123"]
        )

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

        result = runner.invoke(
            app, ["agent", "rename", "tsk_abc123def456", "New Title", "-w", "ws_test123", "--json"]
        )

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

        result = runner.invoke(
            app, ["agent", "rename", "nonexistent", "New Title", "-w", "ws_test123"]
        )

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

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix the bug", "-w", "ws_test123", "--json"]
        )

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
                "agent", "send", "tsk_abc123def456", "Fix it",
                "-w", "ws_test123",
                "--file", "path/to/file1.py",
                "--file", "path/to/file2.py",
            ],
        )

        assert result.exit_code == 0

    def test_send_missing_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["agent", "send", "tsk_abc123", "hello"])

        assert result.exit_code == 1

    def test_send_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123", "hello", "-w", "ws_test123", "-m", "invalid"]
        )

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

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc", "Fix it", "-w", "ws_test123"]
        )

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

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123"]
        )

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

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123"]
        )

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

        result = runner.invoke(
            app, ["agent", "send", "tsk_abc123def456", "Fix it", "-w", "ws_test123", "--json"]
        )

        assert result.exit_code == 1
        assert "Message sent" not in result.output


def _make_snapshot(
    task_id: str = "tsk_abc123def456",
    status: str = "RUNNING",
    current_activity: str | None = None,
    last_activity: str | None = None,
    waiting_detail: str | None = None,
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
        error_detail=error_detail,
        updated_at="2026-01-15T10:35:00Z",
        title="Test task",
        model="CLAUDE-4-SONNET",
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
        def side_effect(_base_url: str, _token: str, _agent_id: str, on_status: Any, _on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
            on_status(_make_snapshot(status="READY"))
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 0
        assert "READY" in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_follow_waiting(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(_base_url: str, _token: str, _agent_id: str, on_status: Any, _on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
            on_status(_make_snapshot(status="WAITING", waiting_detail="User input needed"))
            return ExitReason.WAITING

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "status", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 2

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_status_follow_json(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(_base_url: str, _token: str, _agent_id: str, on_status: Any, _on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
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
        mock_fetch.return_value = _make_snapshot(messages=[
            _chat_message_dict(role="user", msg_id="msg_001", text="what is going on"),
            _chat_message_dict(role="assistant", msg_id="msg_002", text="I am working on it"),
        ])

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
                {"type": "tool_result", "toolUseId": "tu1", "toolName": "Read", "content": {"text": "file contents"}, "isError": False},
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
        def side_effect(_base_url: str, _token: str, _agent_id: str, _on_status: Any, on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
            on_messages([
                _chat_message_dict(role="user", msg_id="msg_001", text="hello"),
                _chat_message_dict(role="assistant", msg_id="msg_002", text="hi there"),
            ])
            return ExitReason.TERMINAL_STATE

        mock_follow.side_effect = side_effect

        result = runner.invoke(app, ["agent", "messages", "tsk_abc123def456", "--follow"])

        assert result.exit_code == 0
        assert "hello" in result.output
        assert "hi there" in result.output

    @patch("sculpt.commands.agent.follow_agent")
    @patch("sculpt.commands._follow_helpers.get_session_token", return_value="test-token")
    def test_messages_follow_json(self, _mock_token: Any, mock_follow: Any, runner: CliRunner) -> None:
        def side_effect(_base_url: str, _token: str, _agent_id: str, _on_status: Any, on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
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

        def side_effect(_base_url: str, _token: str, _agent_id: str, _on_status: Any, on_messages: Any, _on_reconnect: Any, **_kwargs: Any) -> ExitReason:
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

        result = runner.invoke(app, ["agent", "delete", "tsk_abc123def456", "-w", "ws_test123"])

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
