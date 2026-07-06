"""Unit tests for `sculpt plugin` helpers: error shaping and renderer labels."""

import json

import pytest
import typer

from sculpt.client.models.plugin_command_response import PluginCommandResponse
from sculpt.client.models.plugin_command_result import PluginCommandResult
from sculpt.client.models.renderer_identity import RendererIdentity
from sculpt.client.models.renderer_identity_environment import RendererIdentityEnvironment
from sculpt.client.types import UNSET
from sculpt.commands.plugin import _parse_structured_error
from sculpt.commands.plugin import _renderer_label
from sculpt.commands.plugin import _results_or_exit
from sculpt.formatting import json_error


def _result_with_renderer(base: None | str = None, base_unset: bool = False) -> PluginCommandResult:
    renderer = RendererIdentity(
        renderer_id="0123456789abcdef",
        environment=RendererIdentityEnvironment.BROWSER,
        origin="https://sculptor.example.com",
        base=UNSET if base_unset else base,
    )
    return PluginCommandResult(correlation_id="c", renderer=renderer, op="list", ok=True)


class TestParseStructuredError:
    def test_extracts_code_and_message(self) -> None:
        body = json.dumps(
            {"detail": {"code": "agent_plugin_loading_disabled", "message": "Agent plugin loading is disabled."}}
        ).encode()
        assert _parse_structured_error(body) == (
            "agent_plugin_loading_disabled",
            "Agent plugin loading is disabled.",
        )

    def test_tolerates_missing_fields(self) -> None:
        assert _parse_structured_error(json.dumps({"detail": {"message": "just prose"}}).encode()) == (
            None,
            "just prose",
        )
        assert _parse_structured_error(json.dumps({"detail": {"code": "only_code"}}).encode()) == ("only_code", None)

    def test_rejects_unstructured_bodies(self) -> None:
        assert _parse_structured_error(b"<html>502</html>") == (None, None)
        assert _parse_structured_error(json.dumps({"detail": "a plain string"}).encode()) == (None, None)
        assert _parse_structured_error(json.dumps(["not", "a", "dict"]).encode()) == (None, None)
        assert _parse_structured_error(b"\xff\xfe") == (None, None)


class TestRendererLabel:
    def test_deployed_app_shows_bare_origin(self) -> None:
        label = _renderer_label(_result_with_renderer(base="/"))
        assert label == "browser 01234567 https://sculptor.example.com"

    def test_preview_base_is_appended_to_the_origin(self) -> None:
        label = _renderer_label(_result_with_renderer(base="/proxy/51042/"))
        assert label == "browser 01234567 https://sculptor.example.com/proxy/51042/"

    def test_old_bundles_without_base_stay_unchanged(self) -> None:
        for result in (_result_with_renderer(base=None), _result_with_renderer(base_unset=True)):
            assert _renderer_label(result) == "browser 01234567 https://sculptor.example.com"


class TestJsonErrorCode:
    def test_code_is_included_when_present(self) -> None:
        payload = json.loads(json_error("nope", "detail text", "some_code"))
        assert payload == {"error": "nope", "detail": "detail text", "code": "some_code"}

    def test_code_defaults_to_null(self) -> None:
        payload = json.loads(json_error("nope"))
        assert payload == {"error": "nope", "detail": "", "code": None}


class TestResultsOrExit:
    def test_empty_results_error_carries_the_condition_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        response = PluginCommandResponse(correlation_id="c", results=[])
        with pytest.raises(typer.Exit):
            _results_or_exit(response, json_output=True)
        payload = json.loads(capsys.readouterr().err)
        assert payload["code"] == "no_windows_connected"
