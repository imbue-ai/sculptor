"""Tests for the one-time install of the bundled Claude Code registration."""

import tomllib
from pathlib import Path

import pytest

from sculptor.services.terminal_agent_registry import bundled as bundled_module
from sculptor.services.terminal_agent_registry import registry as registry_module
from sculptor.services.terminal_agent_registry.bundled import get_bundled_claude_code_dir
from sculptor.services.terminal_agent_registry.bundled import install_bundled_registrations
from sculptor.services.terminal_agent_registry.registry import load_registrations

_SENTINEL = ".claude-code.installed"


@pytest.fixture
def sculptor_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(registry_module, "get_sculptor_folder", lambda: tmp_path)
    return tmp_path


def test_bundled_sample_dir_resolves_from_source_checkout() -> None:
    source_dir = get_bundled_claude_code_dir()
    assert source_dir is not None
    assert (source_dir / "claude-code.toml").is_file()
    assert (source_dir / "claude-code-hooks.json").is_file()


def test_fresh_install_writes_files_and_loads(sculptor_folder: Path) -> None:
    install_bundled_registrations()

    registrations_dir = sculptor_folder / "terminal_agents"
    toml_path = registrations_dir / "claude-code.toml"
    hooks_path = registrations_dir / "claude-code-hooks.json"
    assert toml_path.is_file()
    assert hooks_path.is_file()
    assert (registrations_dir / _SENTINEL).is_file()

    # The hooks reference is rewritten to the actual destination (quoted for
    # the shell) and the result is still valid TOML.
    data = tomllib.loads(toml_path.read_text())
    assert f'"{hooks_path}"' in data["launch_command"]
    assert f'"{hooks_path}"' in data["resume_command_template"]
    assert "~/.sculptor" not in data["launch_command"]

    registrations = load_registrations()
    assert [r.registration_id for r in registrations] == ["claude-code"]


def test_deleting_the_registration_sticks_across_restarts(sculptor_folder: Path) -> None:
    install_bundled_registrations()
    registrations_dir = sculptor_folder / "terminal_agents"
    (registrations_dir / "claude-code.toml").unlink()
    (registrations_dir / "claude-code-hooks.json").unlink()

    install_bundled_registrations()

    assert not (registrations_dir / "claude-code.toml").exists()
    assert not (registrations_dir / "claude-code-hooks.json").exists()


def test_user_edits_are_never_overwritten(sculptor_folder: Path) -> None:
    registrations_dir = sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True)
    (registrations_dir / "claude-code.toml").write_text('display_name = "Mine"\nlaunch_command = "my-claude"\n')

    install_bundled_registrations()

    data = tomllib.loads((registrations_dir / "claude-code.toml").read_text())
    assert data["display_name"] == "Mine"
    # The companion hooks file (not present) is still installed alongside.
    assert (registrations_dir / "claude-code-hooks.json").is_file()
    assert (registrations_dir / _SENTINEL).is_file()


def test_missing_sample_is_not_fatal(sculptor_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bundled_module, "get_bundled_claude_code_dir", lambda: None)

    install_bundled_registrations()

    assert not (sculptor_folder / "terminal_agents" / _SENTINEL).exists()
