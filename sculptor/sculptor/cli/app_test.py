"""Tests for the CLI startup helpers (``sculptor.cli.app``)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer

from sculptor.cli.app import resolve_and_publish_backend_port
from sculptor.cli.app import typer_cli
from sculptor.config.settings import DEFAULT_BACKEND_PORT
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj
from sculptor.web.middleware import get_settings


@pytest.fixture
def fresh_settings_cache() -> Iterator[None]:
    """Isolate these tests from any get_settings() call elsewhere in the
    pytest process, and leave no snapshot behind for later tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def jj_too_old(tmp_path: Path, silly_global_config: UserConfig) -> Iterator[Path]:
    """Make Sculptor's own dependency resolution find a jj older than the one Sculptor supports."""
    old_jj = tmp_path / "old-jj" / "jj"
    old_jj.parent.mkdir()
    old_jj.write_text("#!/bin/sh\necho 'jj 0.28.2-b9ebe2f03c976515d2a155a411a368ae773c5493'\n")
    old_jj.chmod(0o755)
    dependency_paths = silly_global_config.dependency_paths.model_copy(update={"jj": str(old_jj)})
    set_user_config_instance(silly_global_config.model_copy(update={"dependency_paths": dependency_paths}))
    yield old_jj
    set_user_config_instance(None)


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


def test_the_cli_takes_the_colocated_repository_as_the_project_for_a_path_inside_its_jj_workspace(
    jj_resolved_to_the_pinned_binary: None, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    subdirectory = jj_workspace.path / "src"
    subdirectory.mkdir()
    command = typer.main.get_command(typer_cli)

    context = command.make_context("sculptor", [str(subdirectory)])

    assert Path(context.params["project"]) == jj_colocated_repo.path.resolve()


def test_the_cli_refuses_a_jj_workspace_of_a_repository_not_colocated_with_git(
    jj_resolved_to_the_pinned_binary: None, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repository = tmp_path / "not-colocated"
    repository.mkdir()
    run_jj(jj_binary, ("git", "init", "--no-colocate", str(repository)), cwd=tmp_path)
    jj_workspace = tmp_path / "secondary"
    run_jj(jj_binary, ("workspace", "add", "--no-colocate", "--name", "secondary", str(jj_workspace)), cwd=repository)
    command = typer.main.get_command(typer_cli)

    with pytest.raises(typer.BadParameter, match="jj workspace"):
        command.make_context("sculptor", [str(jj_workspace)])


def test_the_cli_names_the_jj_it_found_when_that_jj_is_too_old_to_find_a_jj_workspace_s_repository(
    jj_workspace: JjWorkspace, jj_too_old: Path
) -> None:
    command = typer.main.get_command(typer_cli)

    with pytest.raises(typer.BadParameter) as refusal:
        command.make_context("sculptor", [str(jj_workspace.path)])

    message = str(refusal.value)
    assert "Sculptor needs a working jj to find that workspace's repository" in message
    assert f"jj 0.28.2 at {jj_too_old} is not supported" in message
