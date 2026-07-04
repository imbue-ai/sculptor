"""Tests for the plugin command correlation bus.

The bus matches renderer replies (POSTed to the result endpoint) back to the
``sculpt plugin`` request blocked on the command endpoint. These exercise the
register / deliver / close lifecycle directly, without HTTP.
"""

from sculptor.web.data_types import PluginCommandResult
from sculptor.web.data_types import RendererIdentity
from sculptor.web.plugin_command_bus import close_correlation
from sculptor.web.plugin_command_bus import open_correlation
from sculptor.web.plugin_command_bus import submit_result


def _result(correlation_id: str) -> PluginCommandResult:
    return PluginCommandResult(
        correlation_id=correlation_id,
        renderer=RendererIdentity(renderer_id="r1", environment="electron", origin="http://localhost:8000"),
        op="list",
        ok=True,
        plugins=[],
    )


def test_submit_delivers_to_the_waiting_queue() -> None:
    result_queue = open_correlation("c1")
    try:
        assert submit_result("c1", _result("c1")) is True
        assert result_queue.get_nowait().correlation_id == "c1"
    finally:
        close_correlation("c1")


def test_submit_returns_false_when_nobody_is_waiting() -> None:
    # A late reply for an already-timed-out request must not raise; the result
    # endpoint relies on this to stay quiet.
    assert submit_result("never-opened", _result("never-opened")) is False


def test_close_stops_further_delivery() -> None:
    open_correlation("c2")
    close_correlation("c2")
    assert submit_result("c2", _result("c2")) is False
