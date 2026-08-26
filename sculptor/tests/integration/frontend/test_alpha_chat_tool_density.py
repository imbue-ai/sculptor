"""Integration tests for the chat-alpha tool density toggle.

The density atom (`chat.toolDensity`) flips the tool pill row between a
horizontal `pillRow` layout and a stacked `expandedRowList` layout. The
choice is persisted to localStorage so it survives reloads. The toggle
is bound to Cmd+Shift+E.
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

# FakeClaude prompt that triggers a turn with two parallel tools (Read + Grep)
# followed by a closing text message. Copied from test_alpha_tool_pill_popover
# so both tests exercise the same shape of pill row.
_PARALLEL_TOOLS_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Read", "tool_input": {"file_path": "/tmp/pill_test_a.txt"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "hello_pill_test", "path": "/tmp"}}
    ]}},
    {"command": "text", "args": {"text": "Done with both tools."}}
  ]
}`"""

# CSS modules append a hash suffix to class names (e.g. `pillRow_a1b2c3`),
# so match by substring. Word-boundary anchors keep `pillRow` from
# accidentally matching `expandedRowList` (or vice versa).
_PILL_ROW_CLASS_RE = re.compile(r"\bpillRow\b|pillRow_")
_EXPANDED_ROW_LIST_CLASS_RE = re.compile(r"\bexpandedRowList\b|expandedRowList_")


@user_story("to see tool calls rendered as inline pills in default density")
def test_default_density_renders_pills_inline(
    sculptor_instance_: SculptorInstance,
) -> None:
    """In default density, the tool row uses the horizontal `pillRow` layout."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt=_PARALLEL_TOOLS_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    pill_row = chat_panel.get_tool_pill_rows().first
    expect(pill_row).to_be_visible()

    pills = pill_row.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)
    expect(pills).to_have_count(2)

    expect(pill_row).to_have_attribute("class", _PILL_ROW_CLASS_RE)


@user_story("to expand tool calls into stacked rows via the density toggle")
def test_toggle_to_expanded_density_stacks_rows(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing the density toggle keybinding switches the row container to `expandedRowList`."""
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt=_PARALLEL_TOOLS_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    pill_row = chat_panel.get_tool_pill_rows().first
    expect(pill_row).to_be_visible()
    expect(pill_row).to_have_attribute("class", _PILL_ROW_CLASS_RE)

    # Move focus out of the chat input so the keyboard shortcut is handled
    # by the page-level listener.
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+E")

    expect(pill_row).to_have_attribute("class", _EXPANDED_ROW_LIST_CLASS_RE)

    pills = pill_row.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)
    expect(pills).to_have_count(2)


@user_story("to keep my tool density preference across page reloads")
def test_density_persists_across_reload(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A density preference saved by the toggle survives a full page reload."""
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt=_PARALLEL_TOOLS_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    pill_row = chat_panel.get_tool_pill_rows().first
    expect(pill_row).to_be_visible()

    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+E")
    expect(pill_row).to_have_attribute("class", _EXPANDED_ROW_LIST_CLASS_RE)

    # `soft_reload_page` re-navigates to page.url instead of using the raw
    # reload API — avoids the Chromium ERR_INSUFFICIENT_RESOURCES that hits
    # the dev server on CI when reloading an unbundled Vite page.
    soft_reload_page(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    pill_row = chat_panel.get_tool_pill_rows().first
    expect(pill_row).to_be_visible()
    expect(pill_row).to_have_attribute("class", _EXPANDED_ROW_LIST_CLASS_RE)
