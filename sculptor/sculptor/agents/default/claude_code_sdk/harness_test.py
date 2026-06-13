"""Tests for the Claude harness's on-disk session-directory sanitization."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.harness import compute_claude_jsonl_directory
from sculptor.agents.hello_agent.harness import HELLO_HARNESS
from sculptor.interfaces.agents.harness import HarnessCapabilities


def test_compute_claude_jsonl_directory_simple_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    result = compute_claude_jsonl_directory(Path("/Users/foo"), Path("/Users/foo/my-project"))
    assert result == Path("/Users/foo/.claude/projects/./-Users-foo-my-project")


def test_compute_claude_jsonl_directory_replaces_dots_and_underscores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    result = compute_claude_jsonl_directory(Path("/Users/foo"), Path("/Users/foo/my_project.v2"))
    assert result == Path("/Users/foo/.claude/projects/./-Users-foo-my-project-v2")


def test_compute_claude_jsonl_directory_replaces_spaces_and_parens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    result = compute_claude_jsonl_directory(
        Path("/Users/foo"), Path("/Users/foo/Dropbox (Personal)/coding/logseq-mobile")
    )
    assert result == Path("/Users/foo/.claude/projects/./-Users-foo-Dropbox--Personal--coding-logseq-mobile")


def test_compute_claude_jsonl_directory_replaces_special_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    result = compute_claude_jsonl_directory(Path("/Users/foo"), Path("/tmp/test @special#chars"))
    assert result == Path("/Users/foo/.claude/projects/./-tmp-test--special-chars")


def test_compute_claude_jsonl_directory_honors_claude_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the user sets $CLAUDE_CONFIG_DIR, Claude writes session JSONLs under
    that directory rather than $HOME/.claude. Sculptor must read from the same
    place — otherwise the StatusPill popover sees an empty TaskListArtifact
    even when the agent is happily emitting TaskCreate/TaskUpdate (SCU-1295).
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/opt/claude-config")
    result = compute_claude_jsonl_directory(Path("/Users/foo"), Path("/Users/foo/my-project"))
    assert result == Path("/opt/claude-config/projects/./-Users-foo-my-project")


def test_compute_claude_jsonl_directory_empty_claude_config_dir_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty $CLAUDE_CONFIG_DIR is treated as unset, matching Claude Code's
    own resolution behavior."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")
    result = compute_claude_jsonl_directory(Path("/Users/foo"), Path("/Users/foo/my-project"))
    assert result == Path("/Users/foo/.claude/projects/./-Users-foo-my-project")


def test_claude_harness_get_tasks_path_returns_home_relative_session_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    env = MagicMock()
    env.get_user_home_directory.return_value = Path("/Users/foo")
    tasks_path = CLAUDE_CODE_HARNESS.get_tasks_path(env, "test-session-uuid")
    assert tasks_path == Path("/Users/foo/.claude/tasks/test-session-uuid")


def test_claude_harness_get_tasks_path_honors_claude_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the user sets $CLAUDE_CONFIG_DIR, Claude writes per-task JSON files
    under that directory rather than $HOME/.claude (SCU-1295)."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/opt/claude-config")
    env = MagicMock()
    env.get_user_home_directory.return_value = Path("/Users/foo")
    tasks_path = CLAUDE_CODE_HARNESS.get_tasks_path(env, "test-session-uuid")
    assert tasks_path == Path("/opt/claude-config/tasks/test-session-uuid")


def test_claude_harness_get_jsonl_path_for_working_directory_matches_helper() -> None:
    """`get_jsonl_path_for_working_directory` is the env-less call shape used
    by `web/app.py`; it must compute the same path as the module-level
    helper used by `fake_claude.py`."""
    home = Path("/Users/foo")
    working_dir = Path("/Users/foo/my-project")
    assert CLAUDE_CODE_HARNESS.get_jsonl_path_for_working_directory(
        home, working_dir
    ) == compute_claude_jsonl_directory(home, working_dir)


def test_hello_harness_get_jsonl_path_for_working_directory_returns_none() -> None:
    """Harnesses without an on-disk session layout (the base trivial default)
    return None — the contract `web/app.py` relies on to skip transcript
    path computation for non-Claude tasks."""
    assert (
        HELLO_HARNESS.get_jsonl_path_for_working_directory(Path("/Users/foo"), Path("/Users/foo/my-project")) is None
    )


def test_claude_harness_capabilities() -> None:
    assert CLAUDE_CODE_HARNESS.capabilities() == HarnessCapabilities(
        supports_chat_interface=True,
        supports_interactive_backchannel=True,
        supports_skills=True,
        supports_sub_agents=True,
        supports_image_input=True,
        supports_fast_mode=True,
        supports_context_reset=True,
        supports_compaction=True,
        supports_background_tasks=True,
        supports_session_resume=True,
        supports_tool_use_rendering=True,
        supports_file_attachments=True,
        supports_interruption=True,
        supports_file_references=True,
    )


def test_hello_harness_capabilities_are_all_false() -> None:
    # Hello is a chat agent (its main panel is the chat interface); every
    # per-affordance capability is false.
    assert HELLO_HARNESS.capabilities() == HarnessCapabilities(
        supports_chat_interface=True,
        supports_interactive_backchannel=False,
        supports_skills=False,
        supports_sub_agents=False,
        supports_image_input=False,
        supports_fast_mode=False,
        supports_context_reset=False,
        supports_compaction=False,
        supports_background_tasks=False,
        supports_session_resume=False,
        supports_tool_use_rendering=False,
        supports_file_attachments=False,
        supports_interruption=False,
        supports_file_references=False,
    )


def test_harness_capabilities_rejects_partial_construction() -> None:
    # Defends the no-default invariant: a new capability must force an edit at
    # every constructor site so `grep <field>` stays grep-complete.
    with pytest.raises(ValidationError):
        HarnessCapabilities.model_validate(
            {
                "supports_chat_interface": True,
                "supports_interactive_backchannel": False,
                "supports_skills": False,
                "supports_sub_agents": False,
            }
        )
