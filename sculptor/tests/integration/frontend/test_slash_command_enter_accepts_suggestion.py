"""Regression tests for SCU-1134: the slash-command popover must accept the
highlighted suggestion on Enter whenever it is visible, regardless of the
user's configured send-message keybinding.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.user_config import _set_user_config_flag
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _create_skill_in_directory(project_path: Path, skill_name: str, description: str) -> None:
    """Create a committed skill in the project's .claude/skills/ directory."""
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


def _open_skill_popover_with_filter(
    page: Page,
    chat_panel: PlaywrightChatPanelElement,
    skill_name: str,
) -> None:
    """Type `/<skill_name>` to surface the workspace skill in the autocomplete
    popover. Retry up to 5 times to tolerate slow skill discovery on CI
    runners (mirrors the pattern in ``test_skill_autocomplete.py``).
    """
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()
    mod_key = get_playwright_modifier_key()

    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially(skill_name)

        try:
            expect(mention_list).to_be_visible()
            expect(mention_list).to_contain_text(skill_name)
            return
        except AssertionError:
            if attempt == 4:
                raise
            page.keyboard.press("Escape")
            chat_input.focus()
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)


def _assert_suggestion_was_accepted(
    chat_panel: PlaywrightChatPanelElement,
    skill_name: str,
    initial_message_count: int,
) -> None:
    """Assert the popover closed, a mention chip with ``skill_name`` was
    inserted into the chat input, and no new chat message was sent.
    """
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).not_to_be_visible()

    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    expect(mention_span).to_contain_text(skill_name)

    expect(chat_panel.get_messages()).to_have_count(initial_message_count)


def _prepare_task_with_skill(
    sculptor_instance_: SculptorInstance,
    skill_name: str,
) -> PlaywrightTaskPage:
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        skill_name,
        "Skill for SCU-1134 regression test",
    )
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )


@user_story("to have Enter accept the highlighted slash-command suggestion when Enter is bound to send")
def test_enter_accepts_skill_suggestion_when_enter_is_send_binding(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When ``send_message`` is bound to Enter, pressing Enter with the
    slash-command popover open must accept the highlighted suggestion as a
    chip, NOT submit the typed text as a chat message.

    Regression for SCU-1134: with the default Meta+Enter binding the popover
    consumes Enter (because the editor's ``useModifiedEnter`` handler ignores
    bare Enter), so the suggestion plugin runs and accepts the row. With
    Enter rebound to send, the editor's ``editorProps.handleKeyDown`` consumed
    the event first — submitting ``/<filter>`` as a literal user message
    before the suggestion plugin's ``handleKeyDown`` could see it.
    """
    skill_name = "scu1134-enter-skill"
    task_page = _prepare_task_with_skill(sculptor_instance_, skill_name)
    page = sculptor_instance_.page

    # Configure Enter as the send-message keybinding. This triggers a page
    # reload, so do it AFTER start_task_and_wait_for_ready — the helper
    # waits for the TipTap editor to re-initialize.
    _set_user_config_flag(page, "keybindings", {"send_message": "Enter"})

    chat_panel = task_page.get_chat_panel()
    _open_skill_popover_with_filter(page, chat_panel, skill_name)

    initial_message_count = chat_panel.get_messages().count()
    page.keyboard.press("Enter")
    _assert_suggestion_was_accepted(chat_panel, skill_name, initial_message_count)


@user_story("to have Cmd+Enter accept the highlighted slash-command suggestion when the popover is open")
def test_modifier_enter_accepts_skill_suggestion_under_default_binding(
    sculptor_instance_: SculptorInstance,
) -> None:
    """With the default ``Meta+Enter`` (Cmd+Enter on macOS, Ctrl+Enter
    elsewhere) send-message binding, pressing the modified Enter with the
    slash-command popover open must accept the highlighted suggestion — not
    submit the typed text as a chat message.

    SCU-1134's wording is "regardless of configured keybindings": once the
    popover is visible, it owns Enter. This test locks in that contract so a
    future change to ``useModifiedEnter`` (which previously did consume
    Meta+Enter even when the popover was open) cannot silently regress the
    modifier path.
    """
    skill_name = "scu1134-cmdenter-skill"
    task_page = _prepare_task_with_skill(sculptor_instance_, skill_name)
    page = sculptor_instance_.page

    chat_panel = task_page.get_chat_panel()
    _open_skill_popover_with_filter(page, chat_panel, skill_name)

    initial_message_count = chat_panel.get_messages().count()
    # `get_playwright_modifier_key` returns "Meta" on macOS and "Control" on
    # Linux/Windows — matches the default `send_message` binding's
    # platform-specific resolution.
    page.keyboard.press(f"{get_playwright_modifier_key()}+Enter")
    _assert_suggestion_was_accepted(chat_panel, skill_name, initial_message_count)
