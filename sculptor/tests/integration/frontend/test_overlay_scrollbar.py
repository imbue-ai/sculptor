"""Integration tests for the overlay scrollbar (SCU-1321).

The alpha chat and file browser replace their native scrollbar with
``<VerticalOverlayScrollbar>``, whose thumb renders as an overlay above the
adjacent panel resize handle. This fixes the splitter stealing the
scrollbar's clicks: the thumb stays draggable, and a pointer over the thumb is
owned by the scrollbar rather than the resize handle behind it.

These cover the behavioural core:
- dragging the thumb scrolls the chat (the scrollbar is a usable target), and
- at the panel edge the thumb — not the resize handle — receives the pointer.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import get_alpha_scrollbar_thumb
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import close_bottom_panel
from sculptor.testing.elements.panels import ensure_right_area_visible
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_LONG_TEXT = " ".join(["This is a longer response that should take up some space."] * 20)


def _long_prompt(index: int) -> str:
    """A long FakeClaude prompt, unique per turn. Identical consecutive user
    messages can be dropped by the queued-message dedup, stalling the turn
    count, so each turn carries a distinct prefix."""
    return f'fake_claude:text `{{"text": "Turn {index}. {_LONG_TEXT}"}}`'


def _fill_chat_until_overflow(page, chat_panel) -> None:
    """Send a few long turns so the chat overflows and the overlay thumb appears."""
    expected = 2
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=expected)
    for index in range(1, 3):
        send_chat_message(chat_panel, _long_prompt(index))
        expected += 2
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=expected)
    wait_for_alpha_scroll_settled(page)


@user_story("to scroll the chat by dragging the overlay scrollbar thumb")
def test_overlay_thumb_drag_scrolls_chat(sculptor_instance_: SculptorInstance) -> None:
    """Dragging the overlay thumb downward scrolls the chat downward — proving the
    scrollbar is a usable, draggable target rather than an inert sliver."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt=_long_prompt(0))
    chat_panel = task_page.get_chat_panel()
    close_bottom_panel(page)
    _fill_chat_until_overflow(page, chat_panel)

    expect(get_alpha_chat_view(page)).to_be_visible()
    scroll_alpha_chat_to_top(page)
    wait_for_alpha_scroll_settled(page)

    thumb = get_alpha_scrollbar_thumb(page)
    expect(thumb).to_be_visible()
    box = thumb.bounding_box()
    assert box is not None, "scrollbar thumb has no bounding box"

    scroll_before = get_alpha_scroll_position(page)

    # Grab the thumb and drag it down; the chat should follow.
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y + 150, steps=10)
    page.mouse.up()

    page.wait_for_function(
        f"""(before) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollTop > before + 20;
        }}""",
        arg=scroll_before,
    )


@user_story("to use the chat scrollbar even where it overlaps the panel resize handle")
def test_overlay_thumb_wins_over_adjacent_resize_handle(sculptor_instance_: SculptorInstance) -> None:
    """With the right panel open, the resize handle sits on the chat's right edge,
    its hit area overlapping the scrollbar thumb — the exact conflict from the bug.

    Dragging the thumb diagonally (down and toward the chat) must scroll the chat
    and leave the panel width unchanged. If the splitter were still stealing the
    gesture, the opposite would happen: the chat wouldn't scroll and the panel
    would widen from the horizontal component."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt=_long_prompt(0))
    chat_panel = task_page.get_chat_panel()
    close_bottom_panel(page)
    ensure_right_area_visible(page)
    _fill_chat_until_overflow(page, chat_panel)

    right_area = page.get_by_test_id(ElementIDs.PANEL_RIGHT_AREA)
    expect(right_area).to_be_visible()

    scroll_alpha_chat_to_top(page)
    wait_for_alpha_scroll_settled(page)

    thumb = get_alpha_scrollbar_thumb(page)
    expect(thumb).to_be_visible()
    box = thumb.bounding_box()
    assert box is not None, "scrollbar thumb has no bounding box"

    width_before = right_area.bounding_box()["width"]
    scroll_before = get_alpha_scroll_position(page)

    # The thumb sits at the chat's right edge, inside the resize handle's hit area.
    # Drag it down (to scroll) and toward the chat (which would widen the right
    # panel if the handle caught the gesture).
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x - 80, start_y + 150, steps=10)
    page.mouse.up()

    # Wait until the gesture has visibly landed on EITHER side — the chat scrolls
    # (the thumb won) or the panel resizes (the handle won) — so the assertion
    # reads a settled layout instead of a one-shot snapshot, and a regression
    # fails fast rather than timing out.
    page.wait_for_function(
        f"""([before, widthBefore]) => {{
            const chat = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            const panel = document.querySelector('[data-testid="{ElementIDs.PANEL_RIGHT_AREA}"]');
            if (!chat || !panel) return false;
            const scrolled = chat.scrollTop > before + 20;
            const resized = Math.abs(panel.getBoundingClientRect().width - widthBefore) >= 4;
            return scrolled || resized;
        }}""",
        arg=[scroll_before, width_before],
    )

    # The thumb owned the gesture: the chat scrolled and the panel did not resize.
    scrolled_by = get_alpha_scroll_position(page) - scroll_before
    width_after = right_area.bounding_box()["width"]
    assert scrolled_by > 20 and abs(width_after - width_before) < 4, (
        "expected the thumb to scroll the chat without resizing the panel "
        + f"(scrolled {scrolled_by:.0f}px; panel width {width_before:.0f} -> {width_after:.0f}); "
        + "the resize handle stole the gesture."
    )
