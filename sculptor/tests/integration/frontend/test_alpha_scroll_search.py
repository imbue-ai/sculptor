"""Integration tests for alpha chat in-chat search."""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.chat_search_bar import get_chat_search_bar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

FILLER = "The quick brown fox jumps over the lazy dog. " * 20


@user_story("to search for text in the alpha chat and navigate between matches")
def test_alpha_search_flow(sculptor_instance_: SculptorInstance) -> None:
    """Test search finds matches, displays counter, navigates, and closes cleanly."""
    page = sculptor_instance_.page

    # Create conversation with the rare word "zymurgy" spread across messages
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{FILLER} zymurgy {FILLER}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Second message with multiple matches
    send_chat_message(
        chat_panel,
        f'fake_claude:text `{{"text": "zymurgy {FILLER} zymurgy {FILLER} zymurgy"}}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_chat_view = get_alpha_chat_view(page)
    expect(alpha_chat_view).to_be_visible()

    # Open search with Cmd+Shift+F (Meta on macOS, Control on Linux)
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+f")

    search_bar = get_chat_search_bar(page)
    search_input = search_bar.get_search_input()
    expect(search_input).to_be_visible()

    # Type search query
    search_input.fill("zymurgy")

    # Verify match counter shows matches
    # 8 total: 1 in first user msg + 1 in first response + 3 in second user msg + 3 in second response
    counter = search_bar.get_match_counter()
    expect(counter).to_contain_text("/8")

    # Navigate to next match with Enter
    search_input.press("Enter")

    # Verify counter updated
    expect(counter).to_contain_text("2/")

    # Close search with Escape
    search_input.press("Escape")

    # Search bar should be hidden
    expect(search_input).not_to_be_visible()
