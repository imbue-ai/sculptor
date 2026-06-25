"""Tests for the terminal-agent registration loader."""

import json
import re
from pathlib import Path

import pytest

from sculptor.services.terminal_agent_registry import registry as registry_module
from sculptor.services.terminal_agent_registry.bundled import get_bundled_claude_code_dir
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
    # The hooks path uses the {terminal_agents_directory} placeholder, resolved
    # at command-render time (not baked in), and the loader accepts it verbatim.
    assert "{terminal_agents_directory}" in registration.launch_command
    assert registration.resume_command_template is not None
    assert "{session_id}" in registration.resume_command_template
    # A resumed session must come back with exactly the launch flags.
    assert registration.resume_command_template == f"{registration.launch_command} --resume {{session_id}}"
    assert registration.accepts_automated_prompts is True


def test_loader_validates_command_placeholders(registrations_dir: Path) -> None:
    # Known placeholders load; an unknown {…} token and a {session_id} in
    # launch_command (no session exists at first launch) are both rejected.
    good = registry_module.TerminalAgentRegistration(
        registration_id="good",
        display_name="Good",
        launch_command='c --settings "{terminal_agents_directory}/h.json" --root "{sculptor_directory}"',
        resume_command_template="c --resume {session_id}",
    )
    assert good.registration_id == "good"

    with pytest.raises(ValueError, match="unsupported placeholder"):
        registry_module.TerminalAgentRegistration(
            registration_id="bad", display_name="Bad", launch_command="c {not_a_real_variable}"
        )
    with pytest.raises(ValueError, match="unsupported placeholder"):
        registry_module.TerminalAgentRegistration(
            registration_id="bad", display_name="Bad", launch_command="c --resume {session_id}"
        )


def test_bundled_claude_cli_hooks_only_signal_waiting_for_genuine_attention() -> None:
    """The shipped hooks must not turn the tab yellow without a question.

    The TUI's Notification hook fires for every notification type it emits --
    including the after-60s-idle ``idle_prompt`` reminder. That reminder may map
    to ``idle`` (it confirms the agent has settled), but it must NEVER map to
    ``waiting``: an unfiltered Notification->waiting mapping would show the
    attention dot with nothing to answer. Questions themselves never fire a
    Notification at all: the AskUserQuestion / ExitPlanMode tool lifecycle is the
    question signal (PreToolUse = question shown -> waiting; PostToolUse =
    answered -> busy).
    """
    sample_dir = get_bundled_claude_code_dir()
    assert sample_dir is not None, "bundled claude-code sample not found"
    hooks = json.loads((sample_dir / "claude-code-hooks.json").read_text())["hooks"]

    notification_groups = hooks["Notification"]
    waiting_matchers = []
    idle_matchers = []
    for group in notification_groups:
        matcher = group.get("matcher")
        assert matcher, "Notification hooks must filter by notification type"
        if any("signal waiting" in hook["command"] for hook in group["hooks"]):
            waiting_matchers.append(matcher)
        if any("signal idle" in hook["command"] for hook in group["hooks"]):
            idle_matchers.append(matcher)
    # The after-60s idle reminder must never raise the attention (waiting) dot...
    for matcher in waiting_matchers:
        assert re.search(matcher, "idle_prompt") is None, (
            f"matcher {matcher!r} must not signal waiting on the idle reminder"
        )
    # ...though it is allowed (and expected) to drive the tab to idle.
    assert any(matcher and re.search(matcher, "idle_prompt") for matcher in idle_matchers), (
        "idle_prompt should signal idle (it confirms the agent has settled)"
    )
    for notification_type in ("permission_prompt", "worker_permission_prompt"):
        assert any(re.search(matcher, notification_type) for matcher in waiting_matchers), (
            f"permission notifications must signal waiting: {notification_type}"
        )

    question_groups = [
        group for group in hooks["PreToolUse"] if any("signal waiting" in hook["command"] for hook in group["hooks"])
    ]
    answered_groups = [
        group for group in hooks["PostToolUse"] if any("signal busy" in hook["command"] for hook in group["hooks"])
    ]
    for tool_name in ("AskUserQuestion", "ExitPlanMode"):
        assert any(re.search(group["matcher"], tool_name) for group in question_groups), (
            f"{tool_name} must signal waiting when the question/plan UI appears"
        )
        assert any(re.search(group["matcher"], tool_name) for group in answered_groups), (
            f"{tool_name} must signal busy once answered"
        )


def test_bundled_claude_cli_hooks_report_session_id_on_first_prompt_not_startup() -> None:
    """The session id must be reported only once a conversation exists.

    Claude does not persist a resumable transcript for a session that never
    received a message, so an id reported from SessionStart (TUI startup)
    can point at nothing: a Sculptor restart then relaunches with
    ``--resume <id>`` and the TUI dies with "No conversation found with
    session ID". Reporting from UserPromptSubmit instead means a
    message-less agent persists no id and restarts fall back to the plain
    launch command (a fresh TUI in the same tab), while every prompt
    re-reports the current id (e.g. fresh after /clear).
    """
    sample_dir = get_bundled_claude_code_dir()
    assert sample_dir is not None, "bundled claude-code sample not found"
    hooks = json.loads((sample_dir / "claude-code-hooks.json").read_text())["hooks"]

    def commands_for(event_name: str) -> list[str]:
        return [hook["command"] for group in hooks.get(event_name, ()) for hook in group["hooks"]]

    assert not any("session-id" in command for command in commands_for("SessionStart")), (
        "SessionStart fires before any message exists — an id reported there may not be resumable"
    )
    assert any("session-id" in command for command in commands_for("UserPromptSubmit")), (
        "UserPromptSubmit must report the session id (first moment a resumable conversation exists)"
    )


def test_bundled_claude_cli_session_start_idles_on_real_starts_not_compaction() -> None:
    """SessionStart signals idle for a genuine (re)start but not a compaction.

    A mid-turn auto-compaction re-fires SessionStart with source=compact while
    the agent is still working, so the hook must not signal idle then. The
    filtering is done by Claude's ``source`` matcher (startup|resume|clear), so
    we assert the matcher semantics rather than executing a command.
    """
    sample_dir = get_bundled_claude_code_dir()
    assert sample_dir is not None, "bundled claude-code sample not found"
    groups = json.loads((sample_dir / "claude-code-hooks.json").read_text())["hooks"]["SessionStart"]
    idle_matchers = [
        group["matcher"] for group in groups if any("signal idle" in hook["command"] for hook in group["hooks"])
    ]

    assert idle_matchers, "SessionStart must signal idle on a real start"
    for source in ("startup", "resume", "clear"):
        assert any(re.search(matcher, source) for matcher in idle_matchers), (
            f"SessionStart must idle on source={source}"
        )
    assert not any(re.search(matcher, "compact") for matcher in idle_matchers), (
        "SessionStart must NOT idle on a mid-turn compaction"
    )
