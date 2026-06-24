"""Unit tests for the sculpt trace and debug command groups."""

import json

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


@respx.mock
def test_trace_start_prints_output_path(runner: CliRunner) -> None:
    _mock_session()
    route = respx.post(f"{_BASE_URL}/api/v1/trace/start").mock(
        return_value=Response(200, json={"enabled": True, "outputPath": "/logs/traces/t.json", "bufferedExternalEvents": 0})
    )

    result = runner.invoke(app, ["debug", "trace", "start"])

    assert result.exit_code == 0, result.stderr
    assert route.called
    # No tracer_entries provided → empty body, so the backend default applies.
    assert json.loads(route.calls.last.request.content) == {}
    assert "/logs/traces/t.json" in result.stdout


@respx.mock
def test_trace_start_forwards_tracer_entries(runner: CliRunner) -> None:
    _mock_session()
    route = respx.post(f"{_BASE_URL}/api/v1/trace/start").mock(
        return_value=Response(200, json={"enabled": True, "outputPath": "/x.json", "bufferedExternalEvents": 0})
    )

    result = runner.invoke(app, ["debug", "trace", "start", "--tracer-entries", "12345"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"tracer_entries": 12345}


@respx.mock
def test_trace_stop_reports_counts(runner: CliRunner) -> None:
    _mock_session()
    respx.post(f"{_BASE_URL}/api/v1/trace/stop").mock(
        return_value=Response(
            200, json={"outputPath": "/logs/traces/t.json", "backendEventCount": 42, "externalEventCount": 7}
        )
    )

    result = runner.invoke(app, ["debug", "trace", "stop"])

    assert result.exit_code == 0, result.stderr
    assert "/logs/traces/t.json" in result.stdout
    assert "42 backend events" in result.stdout
    assert "7 external events" in result.stdout


@respx.mock
def test_trace_stop_surfaces_409_detail(runner: CliRunner) -> None:
    _mock_session()
    respx.post(f"{_BASE_URL}/api/v1/trace/stop").mock(
        return_value=Response(409, json={"detail": "No trace is running."})
    )

    result = runner.invoke(app, ["debug", "trace", "stop"])

    assert result.exit_code == 1
    assert "409" in result.stderr
    assert "No trace is running." in result.stderr


@respx.mock
def test_trace_status_json_passthrough(runner: CliRunner) -> None:
    _mock_session()
    payload = {"enabled": True, "outputPath": "/x.json", "bufferedExternalEvents": 3}
    respx.get(f"{_BASE_URL}/api/v1/trace/status").mock(return_value=Response(200, json=payload))

    result = runner.invoke(app, ["debug", "trace", "status", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == payload


@respx.mock
def test_debug_threads_prints_dump(runner: CliRunner) -> None:
    _mock_session()
    dump = "Thread dump at 2026-01-01\nThread 1 (MainThread):\n"
    respx.get(f"{_BASE_URL}/api/v1/debug/threads").mock(return_value=Response(200, text=dump))

    result = runner.invoke(app, ["debug", "threads"])

    assert result.exit_code == 0, result.stderr
    assert "Thread dump at" in result.stdout
    assert "MainThread" in result.stdout
