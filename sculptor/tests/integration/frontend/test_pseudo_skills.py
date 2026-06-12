"""Integration tests for pseudo skills (/clear, /copy)."""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_committed_skills(project_path: Path, skill_names: list[str]) -> None:
    """Create several committed skills in the project's .claude/skills/ directory.

    The skills are committed to git so CLONE-mode workspaces include them.
    Used to crowd the slash-command autocomplete with custom skills that sort
    alphabetically before the built-in pseudo skills (see SCU-1316).
    """
    skills_dir = project_path / ".claude" / "skills"
    for skill_name in skill_names:
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: Crowding skill {skill_name}.\n---\nSkill instructions.\n"
        )
    subprocess.run(["git", "add", str(skills_dir)], cwd=project_path, check=True)
    subprocess.run(["git", "commit", "-m", "Add crowding skills"], cwd=project_path, check=True)


def _select_pseudo_skill_from_autocomplete(chat_panel: PlaywrightChatPanelElement, skill_name: str) -> None:
    """Type / to trigger autocomplete, filter to skill_name, and press Enter to select."""
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")
    chat_input.press_sequentially(skill_name)
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible(timeout=60_000)
    # The MENTION_LIST div is rendered whenever the suggestion is open, even
    # while its async filter still reports zero matching items (in which
    # case SkillList shows "No matching skills" instead of the skill rows).
    # Pressing Enter while items is empty falls through to the editor
    # (SkillList's onKeyDown returns false), no pill is inserted, and the
    # subsequent send goes out as plain "/skill" text. Wait for the list to
    # render skill_name before committing.
    expect(mention_list).to_contain_text(skill_name)
    chat_panel._page.keyboard.press("Enter")
    # Confirm the selection by waiting for the autocomplete to close — if
    # Enter raced the filter and fell through, the list would still be open.
    expect(mention_list).not_to_be_visible()


@user_story("to see built-in pseudo skills in autocomplete with badges")
def test_builtin_skills_appear_in_autocomplete_with_badges(sculptor_instance_: SculptorInstance) -> None:
    """Built-in pseudo skills should appear in the autocomplete popover with a built-in badge."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")
    # Filter to a built-in skill before asserting its badge. The autocomplete
    # renders the type badge only for the selected row, and selection defaults
    # to the alphabetically-first item. Without filtering, custom skills from
    # ~/.claude/skills/ (or the repo) that sort before the built-ins get
    # selected and the badge reads "custom", so "built-in" never renders
    # (SCU-1316). Typing "clear" makes the built-in skill the top match
    # regardless of what custom skills exist on the host.
    chat_input.press_sequentially("clear")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible(timeout=60_000)
    expect(mention_list).to_contain_text("clear", timeout=60_000)
    expect(mention_list).to_contain_text("built-in", timeout=60_000)


@user_story("to see the built-in badge even when many custom skills crowd the autocomplete")
def test_builtin_badge_appears_with_many_custom_skills(sculptor_instance_: SculptorInstance) -> None:
    """A built-in skill's badge must stay reachable when many custom skills crowd the list.

    Regression for SCU-1316: the autocomplete renders the type badge only for
    the *selected* row (the detail pane), and selection defaults to the
    alphabetically-first item. Custom skills (from the repo or
    ``~/.claude/skills/``) that sort before the built-in pseudo skills push the
    built-ins down, so a custom skill is selected and an unfiltered snapshot of
    the popover never contains the "built-in" badge text.
    """
    _create_committed_skills(
        sculptor_instance_.project_path,
        [f"aaa-crowd-skill-{index:02d}" for index in range(12)],
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible(timeout=60_000)
    # Confirm the seeded custom skills crowd the top of the unfiltered list
    # (they sort before the built-ins) — this is the SCU-1316 condition.
    expect(mention_list).to_contain_text("aaa-crowd-skill-00", timeout=60_000)
    # Filtering to a built-in skill surfaces its "built-in" badge regardless of
    # how many custom skills crowd the unfiltered list.
    chat_input.press_sequentially("clear")
    expect(mention_list).to_contain_text("clear", timeout=60_000)
    expect(mention_list).to_contain_text("built-in", timeout=60_000)


@user_story("to filter pseudo skills in autocomplete")
def test_autocomplete_filters_pseudo_skills(sculptor_instance_: SculptorInstance) -> None:
    """Typing a filter query should narrow down pseudo skills in autocomplete."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")
    chat_input.press_sequentially("cl")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible(timeout=60_000)
    expect(mention_list).to_contain_text("clear", timeout=60_000)
    expect(mention_list).not_to_contain_text("copy")


@user_story("to clear context using /clear pseudo skill")
def test_clear_pseudo_skill_clears_context(sculptor_instance_: SculptorInstance) -> None:
    """/clear should clear the agent context and show a context cleared block."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello from agent"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _select_pseudo_skill_from_autocomplete(chat_panel, "clear")
    chat_panel.get_send_button().click()

    expect(chat_panel.get_context_summary_messages()).to_be_visible(timeout=60_000)
    expect(chat_panel.get_chat_input()).to_have_text("")


@user_story("to copy last response using /copy pseudo skill")
def test_copy_pseudo_skill_shows_toast(sculptor_instance_: SculptorInstance) -> None:
    """/copy should attempt to copy the last assistant message and show a toast."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello from agent"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _select_pseudo_skill_from_autocomplete(chat_panel, "copy")
    chat_panel.get_send_button().click()

    # Playwright may not grant clipboard permissions, so either toast message proves interception worked.
    toast = PlaywrightToastElement(sculptor_instance_.page)
    expect(toast.get_toasts()).to_contain_text("clipboard")
    expect(chat_panel.get_chat_input()).to_have_text("")

    # Messages should still be visible (conversation state unchanged)
    expect(chat_panel.get_messages()).to_have_count(2)


@user_story("to verify pseudo skills are not intercepted when mixed with other text")
def test_pseudo_skill_mixed_with_text_is_not_intercepted(sculptor_instance_: SculptorInstance) -> None:
    """A pseudo skill name mixed with other text should be sent to the agent normally."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello from agent"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    send_chat_message(chat_panel, "please /clear the cache")

    wait_for_completed_message_count(chat_panel, 4)
