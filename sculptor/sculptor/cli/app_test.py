"""Tests for the CLI startup helpers (``sculptor.cli.app``)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer

from sculptor.cli.app import resolve_and_publish_backend_port
from sculptor.cli.app import typer_cli
from sculptor.config.settings import DEFAULT_BACKEND_PORT
from sculptor.web.middleware import get_settings


@pytest.fixture
def fresh_settings_cache() -> Iterator[None]:
    """Isolate these tests from any get_settings() call elsewhere in the
    pytest process, and leave no snapshot behind for later tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_explicit_port_is_published_and_visible_in_the_settings_snapshot(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SCULPTOR_API_PORT", raising=False)
    assert get_settings().BACKEND_PORT == DEFAULT_BACKEND_PORT

    port = resolve_and_publish_backend_port(14242)

    assert port == 14242
    assert os.environ["SCULPTOR_API_PORT"] == "14242"
    assert get_settings().BACKEND_PORT == 14242


def test_default_port_comes_from_settings_and_is_republished(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCULPTOR_API_PORT", "6060")

    port = resolve_and_publish_backend_port(None)

    assert port == 6060
    assert os.environ["SCULPTOR_API_PORT"] == "6060"
    assert get_settings().BACKEND_PORT == 6060


def test_explicit_port_zero_is_respected_not_treated_as_unset(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SCULPTOR_API_PORT", raising=False)
    assert get_settings().BACKEND_PORT == DEFAULT_BACKEND_PORT

    port = resolve_and_publish_backend_port(0)

    assert port == 0
    assert os.environ["SCULPTOR_API_PORT"] == "0"
    assert get_settings().BACKEND_PORT == 0


def test_the_cli_refuses_a_project_inside_a_jj_workspace_while_parsing_its_arguments(tmp_path: Path) -> None:
    jj_workspace = tmp_path / "jj-workspace"
    (jj_workspace / ".jj").mkdir(parents=True)
    command = typer.main.get_command(typer_cli)

    # Parsing runs the argument's callback without running the command, which would start the server.
    with pytest.raises(typer.BadParameter, match="jj workspace"):
        command.make_context("sculptor", [str(jj_workspace)])


def test_the_cli_accepts_a_project_outside_any_jj_workspace(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    command = typer.main.get_command(typer_cli)

    context = command.make_context("sculptor", [str(project)])

    assert Path(context.params["project"]) == project.resolve()
