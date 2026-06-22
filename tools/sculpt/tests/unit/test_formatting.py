"""Unit tests for formatting helpers."""

import json

import pytest
import typer
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.formatting import json_error


class TestJsonError:
    def test_returns_valid_json(self) -> None:
        result = json_error("Not found", "No workspace matches prefix 'abc'")
        parsed = json.loads(result)
        assert parsed == {"error": "Not found", "detail": "No workspace matches prefix 'abc'"}

    def test_empty_detail(self) -> None:
        result = json_error("Server error")
        parsed = json.loads(result)
        assert parsed == {"error": "Server error", "detail": ""}


class TestCliError:
    def test_text_mode_raises_exit(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            cli_error("fail")
        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert "Error: fail" in captured.err

    def test_text_mode_with_detail(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            cli_error("fail", detail="extra info")
        captured = capsys.readouterr()
        assert "Error: fail" in captured.err
        assert "extra info" in captured.err

    def test_json_mode_raises_exit(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            cli_error("fail", detail="extra", json_output=True)
        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed == {"error": "fail", "detail": "extra"}

    def test_custom_exit_code(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            cli_error("fail", exit_code=3)
        assert exc_info.value.exit_code == 3

    def test_custom_exit_code_in_json_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            cli_error("fail", json_output=True, exit_code=4)
        assert exc_info.value.exit_code == 4
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed == {"error": "fail", "detail": ""}


class TestHandleConnectionError:
    def test_text_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            handle_connection_error()
        captured = capsys.readouterr()
        assert "Could not connect to Sculptor server" in captured.err

    def test_json_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            handle_connection_error(json_output=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed["error"] == "Could not connect to Sculptor server"
