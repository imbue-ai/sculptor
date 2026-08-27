"""Unit tests for `sculpt ui` commands."""

import json
import os
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


class TestUiOpenFile:
    def test_help_documents_exit_codes(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["ui", "open-file", "--help"])
        assert result.exit_code == 0
        assert "Exit codes" in result.output
        assert "auto" in result.output
        assert "diff" in result.output
        assert "file" in result.output

    def test_missing_workspace_returns_2(self, runner: CliRunner) -> None:
        os.environ.pop("SCULPT_WORKSPACE_ID", None)
        result = runner.invoke(app, ["ui", "open-file", "/tmp/something.txt"])
        assert result.exit_code == 2

    def test_invalid_mode_returns_2(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123", "--mode", "bogus"])
        assert result.exit_code == 2

    @respx.mock
    def test_success_exits_0(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(return_value=Response(204))

        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123"])
        assert result.exit_code == 0

    @respx.mock
    def test_workspace_not_open_exits_3(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(
            return_value=Response(
                409,
                json={
                    "detail": {
                        "code": "workspace_not_open",
                        "message": "workspace ws_test123 is not open",
                    }
                },
            )
        )

        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123"])
        assert result.exit_code == 3
        assert "is not open" in result.stderr

    @respx.mock
    def test_file_not_found_exits_4(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(
            return_value=Response(
                404,
                json={
                    "detail": {
                        "code": "file_not_found",
                        "message": "/tmp/nope.txt",
                    }
                },
            )
        )

        result = runner.invoke(app, ["ui", "open-file", "/tmp/nope.txt", "-w", "ws_test123"])
        assert result.exit_code == 4

    @respx.mock
    def test_5xx_exits_5(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123"])
        assert result.exit_code == 5

    @respx.mock
    def test_connection_error_exits_5(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")
        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(
            side_effect=ConnectError("Connection refused")
        )

        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123"])
        assert result.exit_code == 5

    @respx.mock
    def test_relative_path_is_resolved_to_absolute(self, runner: CliRunner, tmp_path: Any) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")

        captured: dict[str, Any] = {}

        def _capture(request: Any) -> Response:
            captured["body"] = json.loads(request.content)
            return Response(204)

        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(side_effect=_capture)

        cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = runner.invoke(app, ["ui", "open-file", "relative.txt", "-w", "ws_test123"])
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0
        sent_path = captured["body"]["filePath"]
        assert sent_path != "relative.txt"
        assert os.path.isabs(sent_path)
        assert sent_path.endswith("relative.txt")

    @respx.mock
    def test_mode_passthrough(self, runner: CliRunner) -> None:
        _mock_session()
        _mock_workspaces("ws_test123")

        captured: dict[str, Any] = {}

        def _capture(request: Any) -> Response:
            captured["body"] = json.loads(request.content)
            return Response(204)

        respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(side_effect=_capture)

        result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt", "-w", "ws_test123", "--mode", "diff"])
        assert result.exit_code == 0
        assert captured["body"]["mode"] == "diff"

    @respx.mock
    def test_workspace_from_env(self, runner: CliRunner) -> None:
        os.environ["SCULPT_WORKSPACE_ID"] = "ws_test123"
        try:
            _mock_session()
            _mock_workspaces("ws_test123")
            respx.post("http://localhost:5050/api/v1/workspaces/ws_test123/ui/open-file").mock(
                return_value=Response(204)
            )

            result = runner.invoke(app, ["ui", "open-file", "/tmp/x.txt"])
        finally:
            os.environ.pop("SCULPT_WORKSPACE_ID", None)

        assert result.exit_code == 0
