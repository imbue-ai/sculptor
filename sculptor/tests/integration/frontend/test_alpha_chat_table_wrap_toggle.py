"""Integration test for the AlphaTable wrap toggle (SCU-490).

The wrap toggle is per-table, component-local state — toggling one table's
mode must not affect any other table's mode and must not jump the chat
scroll position. (Wrap state is intentionally not persisted; it resets on
remount.)
"""

import json

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import click_visible_in_chat_viewport
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import scroll_test_id_into_chat_viewport
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A markdown table with cells wide enough that nowrap forces horizontal
# overflow, and lots of surrounding paragraph text so the conversation is
# tall enough to require scrolling within the chat panel.
_FILLER_PARAGRAPH = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 30


_DESCRIPTION_CELL = "description column padded with extra text so the cell would overflow horizontally in nowrap mode"
_NOTES_CELL = "trailing notes column also long enough to push the table beyond the chat width"


def _wide_table_markdown(label: str) -> str:
    rows = "\n".join(f"| {label}-{i} | {_DESCRIPTION_CELL} | status-{i} | {_NOTES_CELL} |" for i in range(1, 7))
    header = "| Component | Description (wide) | Status | Notes (wide) |"
    separator = "| --- | --- | --- | --- |"
    return f"### {label.title()} table\n\n{header}\n{separator}\n{rows}"


def _two_wide_tables_markdown() -> str:
    return "\n\n".join(
        [
            _FILLER_PARAGRAPH,
            _wide_table_markdown("alpha"),
            _FILLER_PARAGRAPH,
            _wide_table_markdown("beta"),
            _FILLER_PARAGRAPH,
        ]
    )


@user_story("to verify each table's wrap toggle is independent and doesn't yank the chat")
def test_table_wrap_toggle_is_per_table_and_does_not_scroll_chat(sculptor_instance_: SculptorInstance) -> None:
    """A chat with two AlphaTables: toggling one must not flip the other and must not jump the scroll."""
    page = sculptor_instance_.page

    response_text = _two_wide_tables_markdown()
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"fake_claude:text `{json.dumps({'text': response_text})}`",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    tables = alpha_view.get_tables()
    expect(tables).to_have_count(2)

    wrap_toggles = alpha_view.get_table_wrap_toggles()
    expect(wrap_toggles).to_have_count(2)
    # Default per-table state is "wrap" — both toggles say "Switch to scroll".
    expect(wrap_toggles.nth(0)).to_have_attribute("aria-label", "Switch to scroll")
    expect(wrap_toggles.nth(1)).to_have_attribute("aria-label", "Switch to scroll")

    # Bring the first table's wrap toggle into the viewport, positioned near the
    # top. Because that table sits high in the (tall) response, plenty of content
    # remains below it — so we are not pinned at the bottom, and any scroll yank
    # caused by the toggle would be observable. Scrolling a specific toggle into
    # view is robust to how tall the wrapped tables render; a fixed pixel delta
    # from the bottom is not.
    scroll_test_id_into_chat_viewport(page, ElementIDs.ALPHA_CHAT_TABLE_WRAP_TOGGLE)
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            if (!el) return false;
            return (el.scrollHeight - el.scrollTop - el.clientHeight) > 200;
        }}"""
    )

    scroll_before = get_alpha_scroll_position(page)

    # Dispatch the click directly so Playwright doesn't first scroll the
    # element into view (which would itself shift scrollTop).
    click_visible_in_chat_viewport(page, ElementIDs.ALPHA_CHAT_TABLE_WRAP_TOGGLE)

    # Exactly one toggle should have flipped — the other table's wrap state
    # must stay independent.
    switched = alpha_view.get_table_wrap_toggles_with_label("Switch to wrap")
    expect(switched).to_have_count(1)
    unchanged = alpha_view.get_table_wrap_toggles_with_label("Switch to scroll")
    expect(unchanged).to_have_count(1)

    # The toggle changes the table's height, which the virtualizer would
    # normally compensate for by bumping scrollTop; the per-item skip flag must
    # suppress that so the view stays put. Confirm scrollTop held steady (and we
    # did not get yanked toward the bottom) after layout settles.
    page.wait_for_function(
        f"""(before) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            if (!el) return false;
            return Math.abs(el.scrollTop - before) < 100 &&
                   (el.scrollHeight - el.scrollTop - el.clientHeight) > 200;
        }}""",
        arg=scroll_before,
    )
