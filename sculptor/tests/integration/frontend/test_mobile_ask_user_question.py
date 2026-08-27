"""Integration test for AskUserQuestion on a short mobile viewport.

On a short phone viewport the Q&A card caps its height and scrolls its options
list internally while the footer (submit button) stays pinned and reachable, so
the user can always complete the flow.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.ask_user_question import get_first_ask_user_question_tool_block
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.mobile_workspace import SHORT_MOBILE_VIEWPORT
from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.mobile


@user_story("to answer a long list of options on a short phone screen with the submit still reachable")
def test_mobile_ask_user_question_scrollable_options_reachable_submit(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)
    # A deliberately short viewport, so the many-option list must scroll inside the
    # card while the footer stays pinned.
    shell = enter_mobile_workspace(page, viewport=SHORT_MOBILE_VIEWPORT)
    chat_panel = shell.get_chat_panel()

    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which of these languages have you shipped production code in? Pick the one you reach for first.",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile general-purpose language with a huge ecosystem"},
        {"label": "JavaScript", "description": "The language of the web, client and server"},
        {"label": "TypeScript", "description": "Typed JavaScript for larger codebases"},
        {"label": "Rust", "description": "Systems programming with memory safety and no GC"},
        {"label": "Go", "description": "Simple, fast, great for cloud infrastructure"},
        {"label": "Java", "description": "The long-standing enterprise workhorse"},
        {"label": "C++", "description": "Systems programming with fine-grained control"},
        {"label": "Ruby", "description": "Developer-friendly, expressive, great for web apps"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)

    # All options are present, and the last one is reachable by scrolling the list
    # inside the card (not the page).
    options = ask_panel.get_options()
    expect(options).to_have_count(8)
    options.last.scroll_into_view_if_needed()
    expect(options.last).to_be_visible()

    # The submit button stays reachable: select an option and submit successfully.
    submit_button = ask_panel.get_submit_button()
    expect(submit_button).to_be_disabled()
    options.first.click()
    expect(submit_button).to_be_enabled()
    submit_button.click()

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    # user message, assistant (AskUserQuestion), assistant follow-up after the answer.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    tool_block = get_first_ask_user_question_tool_block(page)
    tool_block.expect_submitted_state()
