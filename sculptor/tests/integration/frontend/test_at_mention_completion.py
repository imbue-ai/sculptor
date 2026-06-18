"""Integration tests for the at-mention file completion feature.

These tests verify that typing '@' in the chat input opens a file suggestion
popup, that typing additional characters filters the suggestions, and that
selecting a suggestion inserts a mention into the editor.

The mention feature uses directory-based listing: typing '@' lists root
directory contents, and selecting a folder navigates into it rather than
inserting a mention.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Inline HTML that should never appear as visible text in the chat input
_SCULPTOR_NODE_SPAN = "data-sculptor-node"


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    """Create a task via API, wait for it to finish, and navigate to the task page."""
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_opens_suggestion_popup(sculptor_instance_: SculptorInstance) -> None:
    """Typing '@' in the chat input should open the file suggestion popup."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    chat_input.press_sequentially("@")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()

    items = chat_panel.get_mention_items()
    expect(items.first).to_be_visible()


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_filters_by_query(sculptor_instance_: SculptorInstance) -> None:
    """Typing characters after '@' should filter the suggestion list."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # The test repo has a root-level 'stuff.txt' file.
    chat_input.press_sequentially("@stuff")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()

    items = chat_panel.get_mention_items()
    expect(items.first).to_be_visible()
    expect(items.first).to_contain_text("stuff")


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_select_with_enter(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Enter on a suggestion should insert it as a mention."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Type '@stuff' to filter to a file (not a folder, which would navigate)
    chat_input.press_sequentially("@stuff")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()

    chat_input.press("Enter")

    expect(mention_list).not_to_be_visible()

    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    expect(mention_span).to_contain_text("stuff")


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_select_with_click(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file suggestion should insert it as a mention."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Type '@stuff' to filter to a file (clicking a folder would navigate
    # into it rather than inserting a mention)
    chat_input.press_sequentially("@stuff")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()

    items = chat_panel.get_mention_items()
    expect(items.first).to_be_visible()

    # Remember the text of the first suggestion
    first_item_text = items.first.inner_text()

    items.first.click()

    expect(mention_list).not_to_be_visible()

    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    expect(mention_span).to_contain_text(first_item_text)


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_escape_closes_popup(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Escape should close the suggestion popup without inserting anything."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    chat_input.press_sequentially("@")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()

    chat_input.press("Escape")

    expect(mention_list).not_to_be_visible()

    # No mention should have been inserted
    expect(chat_panel.get_mention_spans()).to_have_count(0)


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_not_triggered_inside_inline_code(sculptor_instance_: SculptorInstance) -> None:
    """Typing '@' inside backtick-delimited inline code should not open the suggestion popup."""
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Type `@stuff` — the backticks create inline code, so @ should not
    # trigger the file mention suggestion popup.
    chat_input.press_sequentially("`@stuff`")

    mention_list = chat_panel.get_mention_list()
    expect(mention_list).not_to_be_visible()


@user_story("to reference a file in a chat message using @-mention")
def test_at_mention_persists_as_styled_span_after_workspace_switch(
    sculptor_instance_: SculptorInstance,
) -> None:
    """An @-mention draft should still render as a styled span after navigating away and back.

    Regression test: when a mention was stored in localStorage as markdown
    (containing a raw <span data-sculptor-node> tag) and then restored after
    navigating to the Home page and back, the TipTap editor displayed the
    literal HTML text instead of rendering it as a styled mention node.
    """
    page = sculptor_instance_.page

    # Create a single workspace
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    chat_input.press_sequentially("@stuff")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()
    chat_input.press("Enter")
    expect(mention_list).not_to_be_visible()

    # Confirm the mention span is showing (not raw HTML)
    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    expect(mention_span).to_contain_text("stuff")

    # Navigate to Home, then click the workspace tab to go back
    navigate_to_home_page(page)
    workspace_tab = task_page.get_workspace_tabs()
    expect(workspace_tab).to_be_visible()
    workspace_tab.click()

    # After switching back the mention span must still render correctly —
    # the bug caused the raw "<span data-sculptor-node>…</span>" HTML to appear
    # as visible text instead of a styled node.
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    mention_span_after = chat_panel.get_mention_spans()
    expect(mention_span_after).to_be_visible()
    expect(mention_span_after).to_contain_text("stuff")

    # The input must not contain the literal HTML tag text
    expect(chat_input).not_to_contain_text(_SCULPTOR_NODE_SPAN)
