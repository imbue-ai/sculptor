"""Unit tests for the HTTP-based agent prefix resolver."""

from typing import Any

import pytest
import respx
from click.exceptions import Exit
from httpx import Response
from sculpt.resolve import resolve_agent_id


def _mock_session(base_url: str = "http://localhost:5050") -> None:
    respx.get(f"{base_url}/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )


@respx.mock
def test_resolve_agent_id_full_id_passthrough() -> None:
    _mock_session()
    full_id = "tsk_01h0123456789abcdef0123456"
    respx.get(f"http://localhost:5050/api/v1/agents/by-prefix/{full_id}").mock(
        return_value=Response(200, json={"agentId": full_id})
    )
    assert resolve_agent_id("http://localhost:5050", full_id, json_output=False) == full_id


@respx.mock
def test_resolve_agent_id_short_prefix_resolves() -> None:
    _mock_session()
    full_id = "tsk_01h0123456789abcdef0123456"
    respx.get("http://localhost:5050/api/v1/agents/by-prefix/abc").mock(
        return_value=Response(200, json={"agentId": full_id})
    )
    assert resolve_agent_id("http://localhost:5050", "abc", json_output=False) == full_id


@respx.mock
def test_resolve_agent_id_404_calls_cli_error(capsys: Any) -> None:
    _mock_session()
    respx.get("http://localhost:5050/api/v1/agents/by-prefix/nope").mock(
        return_value=Response(404, json={"detail": "no agent"})
    )
    with pytest.raises(Exit):
        resolve_agent_id("http://localhost:5050", "nope", json_output=False)


@respx.mock
def test_resolve_agent_id_409_calls_cli_error(capsys: Any) -> None:
    _mock_session()
    respx.get("http://localhost:5050/api/v1/agents/by-prefix/tsk_").mock(
        return_value=Response(409, json={"detail": "ambiguous"})
    )
    with pytest.raises(Exit):
        resolve_agent_id("http://localhost:5050", "tsk_", json_output=False)


def test_resolve_agent_id_empty_prefix_short_circuits(capsys: Any) -> None:
    """An empty prefix would hit the SPA static handler (HTML 200) instead of
    the typed route. Short-circuit before the HTTP call.
    """
    with pytest.raises(Exit):
        resolve_agent_id("http://localhost:5050", "", json_output=False)
    captured = capsys.readouterr()
    assert "Agent not found" in captured.err


@respx.mock
def test_resolve_agent_id_409_surfaces_match_list(capsys: Any) -> None:
    """The 409 response includes the matching ids in the detail string; the
    client surfaces the full message so the user can pick a longer prefix
    instead of seeing a generic 'ambiguous' line.
    """
    _mock_session()
    detail = "ambiguous prefix 'tsk_' matches 3 agents: tsk_a, tsk_b, tsk_c"
    respx.get("http://localhost:5050/api/v1/agents/by-prefix/tsk_").mock(
        return_value=Response(409, json={"detail": detail})
    )
    with pytest.raises(Exit):
        resolve_agent_id("http://localhost:5050", "tsk_", json_output=False)
    captured = capsys.readouterr()
    assert "tsk_a" in captured.err
    assert "tsk_b" in captured.err
    assert "tsk_c" in captured.err
