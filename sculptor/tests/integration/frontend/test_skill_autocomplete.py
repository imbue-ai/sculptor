"""Tests for skill autocomplete discovering skills from the workspace code directory."""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _create_skill_in_directory(project_path: Path, skill_name: str, description: str) -> None:
    """Create a committed skill in the project's .claude/skills/ directory.

    The skill files must be committed to git so that CLONE-mode workspaces
    (which clone the repo) include them.
    """
    skill_dir = project_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n---\nSkill instructions.\n"
    )
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add skill {skill_name}"],
        cwd=project_path,
        check=True,
    )


@user_story("to see skills created in workspace in autocomplete popover")
def test_workspace_skill_appears_in_autocomplete_popover(sculptor_instance_: SculptorInstance) -> None:
    """Skills in the workspace should appear in the slash-command autocomplete popover.

    Steps:
    1. Write a skill to the project's .claude/skills/ directory
    2. Create a workspace and agent (clone includes the skill)
    3. Type "/" in the chat input to trigger the autocomplete popover
    4. Verify the popover lists the skill
    """
    # Create the skill BEFORE starting the task so the workspace clone includes it
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        "ws-autocomplete-skill",
        "Skill for autocomplete popover test",
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    page = sculptor_instance_.page
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()
    mod_key = get_playwright_modifier_key()

    # Type "/" in the chat input to trigger skill autocomplete, then type a
    # filter query so the workspace skill isn't pushed out of the top-10 limit
    # by user-level skills from ~/.claude/skills/.
    #
    # On slow CI runners the backend may not have finished discovering skills
    # from the workspace clone yet, so retry the interaction if the popover
    # doesn't contain the expected skill.
    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially("ws-autocomplete")

        try:
            expect(mention_list).to_be_visible()
            expect(mention_list).to_contain_text("ws-autocomplete-skill")
            break
        except AssertionError:
            if attempt == 4:
                raise
            # Clear the input and retry — Escape dismisses the popover,
            # then select-all + delete clears the text.
            page.keyboard.press("Escape")
            expect(mention_list).not_to_be_visible()
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")


@user_story("to see Sculptor plugin skills in autocomplete popover")
def test_plugin_skill_appears_in_autocomplete_with_sculptor_badge(sculptor_instance_: SculptorInstance) -> None:
    """Plugin skills should appear in the autocomplete popover with a "Sculptor" badge.

    Steps:
    1. Create a workspace and agent (no custom skill setup needed — plugin skills are always available)
    2. Type "/" in the chat input to trigger the autocomplete popover
    3. Filter by "sculptor" to find the plugin skill
    4. Verify the popover lists sculptor:sculpt-cli with a "Sculptor" badge
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    page = sculptor_instance_.page
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()
    mod_key = get_playwright_modifier_key()

    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially("sculptor")

        try:
            expect(mention_list).to_be_visible()
            expect(mention_list).to_contain_text("sculptor:sculpt-cli")
            expect(mention_list).to_contain_text("Sculptor")
            break
        except AssertionError:
            if attempt == 4:
                raise
            page.keyboard.press("Escape")
            expect(mention_list).not_to_be_visible()
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")


@user_story("to see skills created in workspace in autocomplete")
def test_skill_autocomplete_not_triggered_inside_inline_code(sculptor_instance_: SculptorInstance) -> None:
    """Typing '/' inside backtick-delimited inline code should not open the skill suggestion popup.

    Steps:
    1. Create a workspace and agent
    2. Type text with a slash command inside backticks in the chat input
    3. Verify the skill autocomplete popover does NOT appear
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    # Type "hello `/command`" — the space before the backtick means the /
    # would normally trigger skill suggestions (allowedPrefixes includes
    # space). The backticks create inline code, so / should be suppressed.
    chat_input.press_sequentially("hello `/command`")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).not_to_be_visible()


@user_story("to see a selected slash command still rendered as a chip after reloading the app")
def test_slash_command_persists_as_chip_after_reload(sculptor_instance_: SculptorInstance) -> None:
    """A /skill chip in the chat input draft must still render as a chip after a page reload.

    Regression test: skill mentions were serialized to markdown as plain
    text (e.g. "/my-skill") while file mentions were wrapped in
    <span data-sculptor-node>.  When the draft was restored from
    localStorage on reload, the plain text could not be parsed back into a
    mention node, so the chip degraded to literal "/my-skill" text.  File
    mentions persist correctly because their wrapper span is preserved.
    """
    skill_name = "persist-reload-skill"
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        skill_name,
        "Skill for reload persistence test",
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    page = sculptor_instance_.page
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()
    mod_key = get_playwright_modifier_key()

    # Type / + filter to surface the custom skill, then press Enter to insert
    # it as a chip.  Retry because on slow CI the workspace clone may not
    # have finished skill discovery yet.
    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially("persist-reload")

        try:
            expect(mention_list).to_be_visible()
            expect(mention_list).to_contain_text(skill_name)
            break
        except AssertionError:
            if attempt == 4:
                raise
            page.keyboard.press("Escape")
            expect(mention_list).not_to_be_visible()
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")

    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    # The skill chip should be rendered as a mention span.
    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    expect(mention_span).to_contain_text(skill_name)

    # Wait for the debounced localStorage write so the draft is persisted
    # before we leave the agent page.
    page.wait_for_function(
        """(name) => {
            for (const value of Object.values(localStorage)) {
                if (value.includes(name)) return true;
            }
            return false;
        }""",
        arg=skill_name,
    )

    # Navigate to Home then back to the workspace so the ChatInput is
    # unmounted and remounted, forcing the TipTap editor to be rebuilt from
    # the markdown draft in localStorage.  This is the same pattern used by
    # ``test_at_mention_persists_as_styled_span_after_workspace_switch``.
    navigate_to_home_page(page)
    workspace_tab = task_page.get_workspace_tabs()
    expect(workspace_tab).to_be_visible()
    workspace_tab.click()

    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # After round-tripping the draft through markdown, the skill must still
    # render as a chip — not as the literal plain text "/persist-reload-skill".
    mention_span_after = chat_panel.get_mention_spans()
    expect(mention_span_after).to_be_visible()
    expect(mention_span_after).to_contain_text(skill_name)
