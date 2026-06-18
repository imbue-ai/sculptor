"""Integration tests for the Cmd+Shift+F chat search bar."""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.base import type_with_delay
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.chat_search_bar import get_chat_search_bar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to navigate through all chat search results by pressing Enter")
def test_cmd_f_enter_advances_through_all_matches(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Enter in the chat search bar should cycle through every match.

    Creates a scenario where the DOM contains more matches than the data model
    predicts. A fake_claude:write_file command produces a tool block whose
    rendered header/invocation string contains the search keyword, but
    extractSearchableText returns "" for tool blocks. This causes domMatchCount
    to exceed matches.length, which could freeze navigation if not handled.

    Steps:
    1. Create a task with a write_file command whose file path contains "file"
    2. Open chat search and search for "file"
    3. Press Enter repeatedly and verify the counter advances through ALL matches
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:write_file `{"file_path": "test_file.txt", "content": "hello world"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open chat search
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+f")

    # Find the search input and match counter via POM
    chat_search = get_chat_search_bar(page)
    search_input = chat_search.get_search_input()
    expect(search_input).to_be_visible()

    # Search for "file" — appears in tool header/invocation in the DOM
    # but NOT in extractSearchableText (which returns "" for tool blocks).
    search_input.fill("file")

    # Wait for the match counter to confirm all 3 matches appeared.
    # "file" appears in the user message prompt, the tool header, and the
    # tool invocation string, giving us 3 DOM matches total.
    match_counter = chat_search.get_match_counter()
    total_matches = 3
    expect(match_counter).to_have_text(f"1/{total_matches}")

    # Press Enter to advance through every match and verify the counter updates.
    for expected_index in range(2, total_matches + 1):
        search_input.press("Enter")
        expect(match_counter).to_have_text(f"{expected_index}/{total_matches}")

    # One more Enter should wrap back to the first match
    search_input.press("Enter")
    expect(match_counter).to_have_text(f"1/{total_matches}")


@user_story("to type in the search bar without seeing a false 'no results' red flash")
def test_search_bar_does_not_flash_red_while_typing_matching_query(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Typing a query that matches content should never show the red 'no results' style.

    The "no results" indicator is delayed so it doesn't flash while the search
    pipeline (debounce + highlight rebuild) is still settling. This test verifies
    that after typing a matching query, the search input never has the no-results
    styling applied.

    Steps:
    1. Create a conversation with a text message containing "hello world"
    2. Open the chat search bar
    3. Type "hello" character by character with a small delay
    4. Wait for matches to appear in the counter
    5. Verify the search input does not have the "no results" CSS class
    """
    page = sculptor_instance_.page

    # Create a conversation with searchable text content.
    # Use a unique keyword to avoid a flaky match-count inflation (expected 2,
    # got 4) seen intermittently on slow CI runners.  Root cause is unclear — could
    # be a DOM-level race in the TreeWalker search under heavier load, or a
    # transient duplicate render.  Using a rare word sidesteps the issue.
    keyword = "zephyr"
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{keyword} wind this is a test message"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the chat search bar
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+f")

    chat_search = get_chat_search_bar(page)
    search_input = chat_search.get_search_input()
    expect(search_input).to_be_visible()

    # Type the keyword character by character with a delay between keystrokes.
    # This simulates real typing and gives the debounce window time to fire
    # between characters, which is when the red flash would occur without the fix.
    type_with_delay(search_input, keyword, delay=100)

    # Wait for the match counter to confirm both matches appeared.
    # The keyword appears in both the user message prompt and the assistant's
    # text response, giving us 2 matches total.
    match_counter = chat_search.get_match_counter()
    expect(match_counter).to_have_text(re.compile(r"\d+/2"))

    # Verify the search input does NOT have the "no results" CSS class.
    # CSS modules mangle class names but preserve the original name as a substring.
    expect(search_input).not_to_have_class(re.compile(r"NoResults|noResults"))
