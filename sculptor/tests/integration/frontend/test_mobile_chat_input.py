"""Integration tests for the mobile ChatInput adaptations and message round-trip.

On mobile the ChatInput collapses its secondary controls into a single options
menu, drops the keyboard hints, and does not auto-focus (so the virtual keyboard
doesn't pop on an agent switch). Sending a message still works and produces a
FakeClaude reply.
"""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.elements.user_config import enable_default_fast_mode
from sculptor.testing.elements.user_config import enable_night_mode
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.mobile


@user_story("to see a compact, keyboard-friendly chat toolbar on my phone")
def test_mobile_chat_input_collapses_secondary_controls(sculptor_instance_: SculptorInstance) -> None:
    """The mobile ChatInput collapses model/effort/plan/fast into one options menu,
    drops the keyboard hints, and does not auto-focus the editor."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)
    chat_panel = shell.get_chat_panel()

    # No auto-focus on mobile: the editor stays unfocused until the user taps it.
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()
    expect(chat_input).not_to_be_focused()
    chat_input.click()
    expect(chat_input).to_be_focused()

    # No keyboard hints on mobile.
    expect(shell.get_keyboard_hints()).to_have_count(0)

    # The always-visible desktop controls (e.g. the model selector) are gone; a
    # single options trigger takes their place.
    expect(shell.get_desktop_model_selector()).to_have_count(0)
    expect(shell.get_chat_options_button()).to_be_visible()

    # The secondary controls live inside that options menu.
    shell.open_chat_options()
    expect(shell.get_options_plan_mode()).to_be_visible()
    expect(shell.get_options_model_submenu()).to_be_visible()
    expect(shell.get_options_effort_submenu()).to_be_visible()


@user_story("to chat with the agent from the mobile shell")
def test_mobile_send_message_and_receive_reply(sculptor_instance_: SculptorInstance) -> None:
    """Sending a message in the mobile shell produces a FakeClaude reply."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)
    chat_panel = shell.get_chat_panel()

    send_chat_message(chat_panel=chat_panel, message="Hello from the mobile shell")

    # User message + FakeClaude's default reply.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    expect(chat_panel.get_messages().last).to_contain_text("Task completed")


@user_story("to not be offered fast mode on my phone while night mode is holding it off")
def test_mobile_options_fast_mode_is_suppressed_by_night_mode(sculptor_instance_: SculptorInstance) -> None:
    """Night mode overrides fast mode at launch, so every control that offers it has to
    say so — the mobile options menu as much as the desktop toggle."""
    page = sculptor_instance_.page

    enable_default_fast_mode(page)
    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    shell.open_chat_options()
    expect(shell.get_options_fast_mode()).to_be_enabled()

    enable_night_mode(page)
    shell = enter_mobile_workspace(page)
    shell.open_chat_options()

    fast_mode_item = shell.get_options_fast_mode()
    expect(fast_mode_item).to_be_disabled()
    # The check mark claims fast mode is on; under night mode the turn runs standard.
    expect(fast_mode_item.get_by_test_id(ElementIDs.MOBILE_CHAT_INPUT_FAST_MODE_CHECK)).to_have_count(0)
