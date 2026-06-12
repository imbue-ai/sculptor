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
from sculptor.testing.elements.alpha_chat_view import get_alpha_container_height
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_height
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
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

    tables = page.get_by_test_id(ElementIDs.ALPHA_CHAT_TABLE)
    expect(tables).to_have_count(2)

    wrap_toggles = page.get_by_test_id(ElementIDs.ALPHA_CHAT_TABLE_WRAP_TOGGLE)
    expect(wrap_toggles).to_have_count(2)
    # Default per-table state is "scroll" — both toggles say "Switch to wrap".
    for toggle in wrap_toggles.all():
        expect(toggle).to_have_attribute("aria-label", "Switch to wrap")

    # Scroll up so we are not pinned at the bottom — only then can we see if
    # the toggle yanks the scroll.
    container_height = get_alpha_container_height(page)
    scroll_alpha_chat_by(page, -int(container_height))
    page.wait_for_timeout(400)

    scroll_top_before = get_alpha_scroll_position(page)
    assert scroll_top_before > 100, (
        f"Test setup failed: chat was not scrolled away from the bottom (scrollTop={scroll_top_before})."
    )

    # Dispatch the click directly so Playwright doesn't first scroll the
    # element into view (which would itself shift scrollTop).
    click_visible_in_chat_viewport(page, ElementIDs.ALPHA_CHAT_TABLE_WRAP_TOGGLE)

    # Exactly one toggle should have flipped — the other table's wrap state
    # must stay independent.
    labels = [t.get_attribute("aria-label") for t in wrap_toggles.all()]
    assert labels.count("Switch to scroll") == 1, (
        f"Expected exactly one toggle to flip after click; got labels={labels}"
    )
    assert labels.count("Switch to wrap") == 1, (
        f"Expected the other toggle to stay in scroll mode; got labels={labels}"
    )

    # Allow layout to settle and check scroll did not jump to the bottom.
    page.wait_for_timeout(400)
    scroll_top_after = get_alpha_scroll_position(page)
    scroll_height = get_alpha_scroll_height(page)
    distance_from_bottom_after = scroll_height - scroll_top_after - container_height
    assert distance_from_bottom_after > 200, (
        "Wrap toggle yanked the chat to the bottom: "
        + f"scrollTop went from {scroll_top_before:.0f} to {scroll_top_after:.0f}; "
        + f"final distance from bottom = {distance_from_bottom_after:.0f}px "
        + f"(scrollHeight={scroll_height:.0f}, clientHeight={container_height:.0f})."
    )
