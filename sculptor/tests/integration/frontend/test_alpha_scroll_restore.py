"""Integration test: reopening a task keeps a bottom-pinned reader at the bottom.

Alpha-chat scroll positions persist in ``localStorage``
(``sculptor-alpha-scroll:<taskId>``) so a full app restart restores where the
reader left off (see ``common/state/atoms/alphaScroll.ts``). On a cold reload the
virtualizer starts every off-screen row at its *estimated* height, so the content
is far shorter than its measured size. A restore that resolves "the bottom"
against that cold estimate lands short; the real rows then measure taller and grow
the content underneath, stranding a reader who was at the bottom pages above it.
The bottom restore must chase the growing bottom until the content converges (the
re-pin loop in ``useAlphaScrollPersistence``), rather than applying once and
settling mid-convergence.
"""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_last_turn_footer_viewport_gaps
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.alpha_chat_view import wait_for_last_turn_footer_near_bottom
from sculptor.testing.elements.alpha_chat_view import wait_for_scroll_save_debounce
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Tall responses (far above the cold 120px per-row estimate,
# ESTIMATED_MESSAGE_HEIGHT in useAlphaVirtualizer) so a few turns overflow the
# viewport by several screens and there is a real bottom to restore to.
_TURN_TEXT = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 80
# Extra turns after the opening one. The FakeClaude harness reliably completes
# only a few turns per task, so this stays small; the transcript is made tall by
# the per-turn size rather than the turn count.
_EXTRA_TURNS = 2

# The pin gap the bottom sits above the viewport bottom (PIN_BOTTOM_GAP in
# chat-alpha/scroll/geometry.ts).
_PIN_BOTTOM_GAP_PX = 64
# "At the bottom" == the last turn footer's bottom edge sits within the pin gap
# plus one standard margin of the viewport bottom. A stranded restore leaves the
# footer hundreds of px below the fold, so this generous band still separates
# "at the bottom" from the bug cleanly.
_FOOTER_BOTTOM_MARGIN_PX = _PIN_BOTTOM_GAP_PX + 72
# Sub-pixel tolerance for "is this edge inside the viewport".
_EDGE_TOLERANCE_PX = 6


@user_story("to reopen a task I left at the bottom and still be at the bottom after a full reload")
def test_reload_restores_scroll_to_bottom(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "Turn 0. {_TURN_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    PlaywrightWorkspaceSection(page, "bottom").collapse_section()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Many more turns so the transcript is a long list of rows (a short chat's rows
    # all mount at once and converge in a frame, hiding the bug). Each prompt is
    # made unique (a turn index) so no two turns dedupe, and each turn completes
    # before the next is sent so the count advances deterministically.
    expected_count = 2
    for turn in range(1, _EXTRA_TURNS + 1):
        send_chat_message(chat_panel, f'fake_claude:text `{{"text": "Turn {turn}. {_TURN_TEXT}"}}`')
        expected_count += 2
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=expected_count)

    view = get_alpha_chat_view(page)
    expect(view).to_be_visible()
    wait_for_alpha_scroll_settled(page)

    # Persist an at-bottom position: a user scroll to (past) the bottom records
    # distanceFromBottom at the pin — the -64 signature — into localStorage.
    scroll_alpha_chat_by(page, 2000)
    wait_for_scroll_save_debounce(page)

    # Precondition: the chat is at the bottom before the reload (retry until the
    # footer settles there, rather than snapshotting a single frame).
    wait_for_last_turn_footer_near_bottom(page, max_bottom_gap=_FOOTER_BOTTOM_MARGIN_PX)

    # The coldest possible restore: a full SPA teardown wipes the in-memory scroll
    # atom, so the saved position is re-read from localStorage and resolved against
    # a cold virtualizer whose rows re-measure taller after mount.
    current_hash = page.url.split("#", 1)[1] if "#" in page.url else "/"
    full_spa_reload(page, target_hash=f"#{current_hash}")

    reloaded_chat_panel = task_page.get_chat_panel()
    expect(get_alpha_chat_view(page)).to_be_visible()
    wait_for_completed_message_count(chat_panel=reloaded_chat_panel, expected_message_count=expected_count)
    wait_for_alpha_scroll_settled(page)

    # The reload must land back at the bottom: the last turn footer in view and
    # close to the viewport bottom, not stranded pages above it. A retrying wait
    # (per use_expect_not_assert) so a footer that renders — or a chase that
    # converges — a beat late does not read as a failure; the one-shot read only
    # runs on timeout, to turn the raw wait error into an actionable geometry.
    try:
        wait_for_last_turn_footer_near_bottom(
            page, max_bottom_gap=_FOOTER_BOTTOM_MARGIN_PX, min_bottom_gap=-_EDGE_TOLERANCE_PX
        )
    except PlaywrightTimeoutError:
        gaps = get_last_turn_footer_viewport_gaps(page)
        raise AssertionError(
            f"after the reload the last turn footer did not land at the bottom (gaps={gaps}); "
            + f"expected bottom_gap in [{-_EDGE_TOLERANCE_PX}, {_FOOTER_BOTTOM_MARGIN_PX}] px — the "
            + "restore stranded the reader above the bottom or cut the footer off below the fold"
        )
