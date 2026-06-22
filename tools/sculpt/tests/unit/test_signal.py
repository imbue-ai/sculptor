"""Unit tests for the sculpt signal command group."""

import json

import pytest
import respx
from httpx import Response
from sculpt.main import app
from typer.testing import CliRunner

_AGENT_ID = "tsk_signal_test_agent"
_BASE_URL = "http://localhost:5050"


@pytest.fixture
def runner() -> CliRunner:
    # click 8.2 (vendored by typer 0.26) removed the mix_stderr kwarg; stdout and
    # stderr are now always captured separately, which is the behavior these tests want.
    return CliRunner()


def _mock_session(base_url: str = _BASE_URL) -> None:
    respx.get(f"{base_url}/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )


def _mock_signal(base_url: str = _BASE_URL, agent_id: str = _AGENT_ID, status_code: int = 204) -> respx.Route:
    return respx.post(f"{base_url}/api/v1/agents/{agent_id}/signal").mock(return_value=Response(status_code))


@pytest.mark.parametrize(
    ("subcommand", "wire_event"),
    [
        ("busy", "busy"),
        ("idle", "idle"),
        ("waiting", "waiting-on-input"),
        ("files-changed", "files-changed"),
    ],
)
@respx.mock
def test_signal_posts_the_wire_event(runner: CliRunner, subcommand: str, wire_event: str) -> None:
    _mock_session()
    route = _mock_signal()

    result = runner.invoke(app, ["signal", subcommand, "--agent", _AGENT_ID])

    assert result.exit_code == 0, result.stderr
    # The happy path is silent — hooks shouldn't pollute the terminal.
    assert result.stdout == ""
    assert route.called
    assert json.loads(route.calls.last.request.content) == {"event": wire_event}


@respx.mock
def test_signal_session_id_posts_the_id(runner: CliRunner) -> None:
    _mock_session()
    route = _mock_signal()

    result = runner.invoke(app, ["signal", "session-id", "abc-123", "--agent", _AGENT_ID])

    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"event": "session-id", "sessionId": "abc-123"}


@respx.mock
def test_signal_reads_agent_id_from_env(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCULPT_AGENT_ID", _AGENT_ID)
    _mock_session()
    route = _mock_signal()

    result = runner.invoke(app, ["signal", "busy"])

    assert result.exit_code == 0, result.stderr
    assert route.called


@respx.mock
def test_signal_json_flag_reports_ok(runner: CliRunner) -> None:
    _mock_session()
    _mock_signal()

    result = runner.invoke(app, ["signal", "busy", "--agent", _AGENT_ID, "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}


def test_signal_without_agent_id_fails_clearly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCULPT_AGENT_ID", raising=False)

    result = runner.invoke(app, ["signal", "busy"])

    assert result.exit_code == 1
    assert "SCULPT_AGENT_ID" in result.stderr


@respx.mock
def test_signal_server_404_exits_nonzero(runner: CliRunner) -> None:
    _mock_session()
    _mock_signal(status_code=404)

    result = runner.invoke(app, ["signal", "busy", "--agent", _AGENT_ID])

    assert result.exit_code == 1
    assert "404" in result.stderr
