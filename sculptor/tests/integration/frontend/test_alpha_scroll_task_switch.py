"""Integration tests for alpha chat scroll position persistence across task switch."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_alpha_scroll_position
from sculptor.testing.elements.alpha_chat_view import get_chat_task_id
from sculptor.testing.elements.alpha_chat_view import read_scroll_top_sampler
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_chat_view import start_scroll_top_sampler
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.alpha_chat_view import wait_for_chat_task_changed
from sculptor.testing.elements.alpha_chat_view import wait_for_scroll_save_debounce
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

LONG_TEXT = "Lorem ipsum dolor sit amet. " * 150

# How much the view may move after the first observable post-switch frame. The
# restore settles pre-paint against synchronously swept measurements
# (SCU-1686), so a revisit must not produce a visible correction scroll — only
# sub-pixel rounding is tolerated.
_SETTLE_DRIFT_TOLERANCE_PX = 8


@user_story("to have scroll position preserved when switching between tasks")
def test_scroll_position_restored_on_task_switch(sculptor_instance_: SculptorInstance) -> None:
    """Test that scroll position is saved and restored when switching tasks."""
    page = sculptor_instance_.page

    # Create both tasks and wait for their messages to complete.
    task_page_a = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task A response. {LONG_TEXT}"}}`',
    )
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    task_page_b = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task B response. {LONG_TEXT}"}}`',
    )
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    # We're on task B.  Navigate to task A first.
    workspace_tabs = task_page_b.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)
    outgoing_task_id = get_chat_task_id(page)
    workspace_tabs.first.click()

    alpha_chat_view = get_alpha_chat_view(page)
    expect(alpha_chat_view).to_be_visible()
    wait_for_chat_task_changed(page, outgoing_task_id)

    # Switching to task A restores its saved scroll position (the bottom)
    # asynchronously.  Wait for the scroll machine to report it has settled
    # before scrolling — otherwise a late restore frame can clobber the
    # scroll-to-top below, which is the source of the CI flake.
    wait_for_alpha_scroll_settled(page)

    # Scroll to the top in task A and wait for scroll to settle
    scroll_alpha_chat_to_top(page)
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollTop < 10;
        }}"""
    )

    pos_a = get_alpha_scroll_position(page)

    # Switch to task B via workspace tab (no reload)
    workspace_tabs.last.click()
    expect(alpha_chat_view).to_be_visible()

    # Navigate back to task A
    workspace_tabs.first.click()

    # Verify scroll position is restored (within 200px tolerance to account for
    # the virtualizer's dynamic paddingStart plus settling adjustments).
    page.wait_for_function(
        f"""(expectedPos) => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && Math.abs(el.scrollTop - expectedPos) < 200;
        }}""",
        arg=pos_a,
    )


@user_story("to not see the chat shift or jump after switching back to a task")
def test_revisit_settles_without_post_switch_scroll_movement(sculptor_instance_: SculptorInstance) -> None:
    """Switching back to a task must not visibly move the view after its first frame.

    The restore applies the saved anchor, synchronously sweeps the mounted rows'
    real measurements, and re-applies — all before the switch commit paints
    (SCU-1686). Any later movement (a deferred correction scroll, an item-reflow
    drift, TanStack's scroll-reconcile clobbering the saved pixel offset) is what
    this guards against. The window is resized while the task is in the
    background so its cached row heights are genuinely stale — the case where an
    unsettled restore corrects itself visibly, frames after paint.
    """
    page = sculptor_instance_.page

    task_page_a = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task A response. {LONG_TEXT}"}}`',
    )
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    task_page_b = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Task B response. {LONG_TEXT}"}}`',
    )
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    workspace_tabs = task_page_b.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # On task A: park at a mid-history reading position with a non-trivial pixel
    # offset into the anchor message (the offset is what a reconcile regression
    # clobbers), and let the rAF-debounced save record it.
    outgoing_task_id = get_chat_task_id(page)
    workspace_tabs.first.click()
    wait_for_chat_task_changed(page, outgoing_task_id)
    wait_for_alpha_scroll_settled(page)
    scroll_alpha_chat_to_top(page)
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
            return el && el.scrollTop < 10;
        }}"""
    )
    scroll_alpha_chat_by(page, 600)
    wait_for_scroll_save_debounce(page)

    # Away on task B, resize the window so task A's cached row heights go stale
    # (text re-wraps to different heights at the new width).
    outgoing_task_id = get_chat_task_id(page)
    workspace_tabs.last.click()
    wait_for_chat_task_changed(page, outgoing_task_id)
    wait_for_alpha_scroll_settled(page)
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    page.set_viewport_size({"width": viewport["width"] - 300, "height": viewport["height"]})
    wait_for_alpha_scroll_settled(page)

    # Back to task A. Arm the sampler as soon as the chat is showing task A's
    # content, then let the settle window (including the deferred safety-net
    # re-assert frames) elapse while sampling.
    task_id_b = get_chat_task_id(page)
    workspace_tabs.first.click()
    wait_for_chat_task_changed(page, task_id_b)
    start_scroll_top_sampler(page)
    wait_for_alpha_scroll_settled(page)
    # Sampling window, not a readiness wait: cover the frames where a deferred
    # correction would land (the double-rAF safety net plus late re-measures).
    page.wait_for_timeout(500)

    sample = read_scroll_top_sampler(page)
    assert sample["first"] is not None and sample["min"] is not None and sample["max"] is not None, (
        "alpha chat view not found while sampling the post-switch scroll"
    )
    drift = sample["max"] - sample["min"]
    assert drift <= _SETTLE_DRIFT_TOLERANCE_PX, (
        f"the view moved {drift}px after switching back (scrollTop range "
        + f"[{sample['min']}, {sample['max']}], first {sample['first']}, final {sample['final']}); "
        + "the restore must settle pre-paint, not correct itself after the fact"
    )
