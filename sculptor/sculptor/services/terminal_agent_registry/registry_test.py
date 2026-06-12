"""Tests for the terminal-agent registration loader."""

from pathlib import Path

import pytest

from sculptor.services.terminal_agent_registry import registry as registry_module
from sculptor.services.terminal_agent_registry.registry import get_registration
from sculptor.services.terminal_agent_registry.registry import load_registrations


@pytest.fixture
def registrations_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(registry_module, "get_sculptor_folder", lambda: tmp_path)
    directory = tmp_path / "terminal_agents"
    directory.mkdir()
    return directory


def test_minimal_registration_loads_with_defaults(registrations_dir: Path) -> None:
    (registrations_dir / "claude-code.toml").write_text('display_name = "Claude Code"\nlaunch_command = "claude"\n')

    registrations = load_registrations()

    assert len(registrations) == 1
    registration = registrations[0]
    assert registration.registration_id == "claude-code"
    assert registration.display_name == "Claude Code"
    assert registration.launch_command == "claude"
    assert registration.resume_command_template is None
    assert registration.accepts_automated_prompts is False


def test_full_registration_loads_all_fields(registrations_dir: Path) -> None:
    (registrations_dir / "claude-code.toml").write_text(
        """\
display_name = "Claude Code"
launch_command = "claude"
resume_command_template = "claude --resume {session_id}"
accepts_automated_prompts = true
"""
    )

    registration = load_registrations()[0]

    assert registration.resume_command_template == "claude --resume {session_id}"
    assert registration.accepts_automated_prompts is True


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        ("broken.toml", "not [valid toml"),
        ("missing-keys.toml", 'display_name = "No launch command"\n'),
        ("Bad Stem.toml", 'display_name = "Bad"\nlaunch_command = "x"\n'),
        (
            "two-placeholders.toml",
            'display_name = "Two"\nlaunch_command = "x"\nresume_command_template = "x {session_id} {session_id}"\n',
        ),
        (
            "unknown-placeholder.toml",
            'display_name = "Unknown"\nlaunch_command = "x"\nresume_command_template = "x {other}"\n',
        ),
    ],
)
def test_invalid_files_are_skipped_and_valid_ones_still_load(
    registrations_dir: Path, filename: str, body: str
) -> None:
    (registrations_dir / filename).write_text(body)
    (registrations_dir / "good.toml").write_text('display_name = "Good"\nlaunch_command = "good"\n')

    registrations = load_registrations()

    assert [r.registration_id for r in registrations] == ["good"]


def test_registrations_sorted_by_id(registrations_dir: Path) -> None:
    (registrations_dir / "zeta.toml").write_text('display_name = "Z"\nlaunch_command = "z"\n')
    (registrations_dir / "alpha.toml").write_text('display_name = "A"\nlaunch_command = "a"\n')

    assert [r.registration_id for r in load_registrations()] == ["alpha", "zeta"]


def test_missing_directory_yields_empty_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "get_sculptor_folder", lambda: tmp_path / "nonexistent")
    assert load_registrations() == []


def test_get_registration_finds_by_id(registrations_dir: Path) -> None:
    (registrations_dir / "foo.toml").write_text('display_name = "Foo"\nlaunch_command = "foo"\n')

    found = get_registration("foo")
    assert found is not None
    assert found.display_name == "Foo"
    assert get_registration("missing") is None


def test_bundled_claude_code_sample_round_trips_through_loader(registrations_dir: Path) -> None:
    # THE regression test for "we changed the registration schema and broke
    # the shipped example": the sample TOML must always load verbatim.
    sample = Path(__file__).parents[4] / "samples" / "terminal_agents" / "claude-code" / "claude-code.toml"
    assert sample.is_file(), f"bundled sample missing at {sample}"
    (registrations_dir / "claude-code.toml").write_text(sample.read_text())

    registrations = load_registrations()

    assert len(registrations) == 1
    registration = registrations[0]
    assert registration.registration_id == "claude-code"
    assert registration.display_name == "Claude CLI"
    # Machine-specific paths come from shell-expanded env vars the
    # terminal-agent PTY injects — never baked-in absolutes.
    assert '"$SCULPT_CLAUDE_BIN"' in registration.launch_command
    assert "$SCULPT_PLUGINS_DIR" in registration.launch_command
    assert "--dangerously-skip-permissions" in registration.launch_command
    assert registration.resume_command_template is not None
    assert "{session_id}" in registration.resume_command_template
    # A resumed session must come back with exactly the launch flags.
    assert registration.resume_command_template == f"{registration.launch_command} --resume {{session_id}}"
    assert registration.accepts_automated_prompts is True
