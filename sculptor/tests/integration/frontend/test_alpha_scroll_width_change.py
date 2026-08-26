"""Integration tests for alpha-chat scroll behavior under viewport WIDTH changes.

The alpha-chat scroll system is an explicit state machine (see
``docs/development/scroll_state_unification.md``, SCU-1566).  At-bottom-ness is a
derived projection over the authority phase: ``following`` pins to the bottom,
``anchoringTurn`` sits a fresh user turn at the top, and every other phase
reflects the last sampled geometry; the jump-to-bottom button is hidden when at
the bottom.

These tests change only the viewport WIDTH (the height is held constant) via
``page.set_viewport_size`` and assert that each scroll state survives the reflow
that a width change forces on the long paragraph text (narrower => taller
content, wider => shorter).  A width change drives no scroll-authority or layout
transition, so ``data-scroll-settled`` does NOT flip for the resize itself — the
post-resize invariants are therefore asserted with retrying expectations on the
observable (the jump-to-bottom button's ``aria-hidden`` and message bounding-box
tops), not by awaiting a settle signal.  The initial state, before the resize, is
established with the usual settle/streaming waits.

The shared instance fixture resets the viewport to its default between tests, so
each test sets its own explicit viewport up front and does not restore it.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_button
from sculptor.testing.elements.alpha_chat_view import get_jump_to_bottom_wrapper
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A normal desktop viewport for establishing each state before the resize.
_INITIAL_WIDTH = 1200
# "Narrow" and "widen" stay in the desktop range so no responsive / mobile /
# panel-collapse layout kicks in, while clearly reflowing the long paragraph
# text (narrower => taller content, wider => shorter). "Desktop range" means
# ABOVE the 768px mobile breakpoint — at or below 767px the mobile shell
# remounts the whole chat, which resets the scroll state these tests assert on.
_NARROW_WIDTH = 800
_WIDE_WIDTH = 1400
# The height is held constant across every before/after, so only width changes.
_VIEWPORT_HEIGHT = 800

# Tolerance (px) for "a message holds its top offset across the resize".  Mirrors
# the small bounding-box tolerances used in test_alpha_scroll_to_top.py and
# test_alpha_scroll_prompt_nav.py.
_TOP_ANCHOR_TOLERANCE_PX = 30

# Short reply that fits the viewport without overflowing.
_SHORT_TEXT = "Hello, this is a short reply."
# Long initial response so the chat is scrollable.
_LONG_TEXT = "Lorem ipsum. " * 200
# Very long response that overflows even at the WIDE width (fewer wraps => still
# taller than the viewport), so a scrolled-up reading anchor stays off the
# bottom after widening.
_VERY_LONG_TEXT = "Lorem ipsum dolor sit amet. " * 400  # ~11k chars
# Long streaming response (~5k chars over ~10s) that overflows and pins to the
# bottom while it streams.
_STREAM_TEXT = "The quick brown fox jumps over the lazy dog. " * 112
# Short streaming response that fills below the anchored user message WITHOUT
# overflowing, so the turn stays in the anchoring/filling phase.
_ANCHOR_STREAM_TEXT = "The quick brown fox jumps over the lazy dog. " * 6  # ~270 chars


def _expect_jump_button_hidden(jump_btn: Locator) -> None:
    """Assert the jump button is in its hidden state (aria-hidden on wrapper).

    The button is always in the DOM (for focus-management), so we check the
    wrapper's aria-hidden attribute rather than Playwright's visibility check.
    """
    wrapper = get_jump_to_bottom_wrapper(jump_btn.page)
    expect(wrapper).to_have_attribute("aria-hidden", "true")


def _set_viewport_width(page: Page, width: int) -> None:
    """Set the viewport WIDTH, holding the height constant at ``_VIEWPORT_HEIGHT``."""
    page.set_viewport_size({"width": width, "height": _VIEWPORT_HEIGHT})


def _wait_for_message_in_upper_half(page: Page, data_index: int, *, timeout: int = 30_000) -> None:
    """Wait until the message at *data_index* sits in the upper half of the viewport.

    Mirrors the "near the top" tolerance of test_alpha_scroll_to_top.py: the
    exact offset depends on virtualizer corrections, so "upper half" is the
    robust signal that the message is anchored near the top (not pinned to the
    bottom or scrolled off-screen).  Inlined as a retrying ``wait_for_function``
    because the shared ``get_message_top_offset`` helper is a one-shot read.
    """
    page.wait_for_function(
        f"""(idx) => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW.value}"]');
            const item = container && container.querySelector('[data-index="' + idx + '"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return offset >= 0 && offset < container.clientHeight / 2;
        }}""",
        arg=data_index,
        timeout=timeout,
    )


def _wait_for_message_top_near(page: Page, data_index: int, expected_offset: float, *, timeout: int = 30_000) -> None:
    """Wait until the message at *data_index* holds *expected_offset* within tolerance.

    Inlined for the same reason as ``_wait_for_message_in_upper_half``: there is
    no shared retrying assertion for a message's bounding-box top offset.
    """
    page.wait_for_function(
        f"""(args) => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW.value}"]');
            const item = container && container.querySelector('[data-index="' + args.idx + '"]');
            if (!container || !item) return false;
            const offset = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return Math.abs(offset - args.expected) < {_TOP_ANCHOR_TOLERANCE_PX};
        }}""",
        arg={"idx": data_index, "expected": expected_offset},
        timeout=timeout,
    )


def _wait_for_following_pinned(page: Page, user_index: int, *, timeout: int = 30_000) -> None:
    """Wait until the just-sent user message has scrolled above the viewport top.

    Once a streaming response overflows, auto-scroll pins the latest (streaming)
    message to the bottom — ``following`` — and the user message that was briefly
    anchored at the top scrolls up off the top edge (eventually unmounting from
    the virtualized list).  That is the deterministic "we are following / pinned
    to the bottom" signal.  Inlined because no shared helper expresses it.
    """
    page.wait_for_function(
        f"""(idx) => {{
            const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW.value}"]');
            if (!container) return false;
            const item = container.querySelector('[data-index="' + idx + '"]');
            if (!item) return true;  // unmounted => scrolled well above the top
            return item.getBoundingClientRect().top - container.getBoundingClientRect().top < 0;
        }}""",
        arg=user_index,
        timeout=timeout,
    )


@user_story(
    "to verify an at-bottom completed turn grows the port and surfaces the jump button when the viewport narrows"
)
def test_at_bottom_shows_jump_on_narrow(sculptor_instance_: SculptorInstance) -> None:
    """Narrowing an at-bottom turn does NOT re-pin: the port grows and the jump button appears."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Drive a completed, overflowing turn that leaves the view at the bottom.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)
    wait_for_alpha_scroll_settled(page)
    # Baseline: at the bottom — the jump-to-bottom button is hidden.
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Narrow the viewport (width only) — content reflows taller.  A resize does NOT
    # re-pin to the bottom: the virtualizer preserves the visible content (the port
    # grows) and the jump-to-bottom button surfaces so the user can return.
    _set_viewport_width(page, _NARROW_WIDTH)

    expect(jump_btn).to_be_visible()


@user_story(
    "to verify an at-bottom completed turn grows the port and surfaces the jump button when the viewport widens"
)
def test_at_bottom_shows_jump_on_widen(sculptor_instance_: SculptorInstance) -> None:
    """Widening an at-bottom turn does NOT re-pin: the port grows and the jump button appears."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Drive a completed, overflowing turn that leaves the view at the bottom.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)
    wait_for_alpha_scroll_settled(page)
    # Baseline: at the bottom — the jump-to-bottom button is hidden.
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Widen the viewport (width only) — content reflows shorter.  A resize does NOT
    # re-pin to the bottom: the virtualizer preserves the visible content and the
    # jump-to-bottom button surfaces so the user can return.
    _set_viewport_width(page, _WIDE_WIDTH)

    expect(jump_btn).to_be_visible()


@user_story("to verify a scrolled-up reading anchor holds its top position when the viewport narrows")
def test_scrolled_up_holds_reading_anchor_on_narrow(sculptor_instance_: SculptorInstance) -> None:
    """A message read at the top stays at the top (and stays off the bottom) on narrow."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_VERY_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()
    wait_for_alpha_scroll_settled(page)

    # Scroll up so the first message sits at the top — a reading anchor, away
    # from the bottom (jump button shown).
    scroll_alpha_chat_to_top(page)
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()
    anchor_offset = get_message_top_offset(page, data_index=0)

    # Narrow the viewport (width only).
    _set_viewport_width(page, _NARROW_WIDTH)

    # The same message holds its top offset, and we stay scrolled off the bottom.
    _wait_for_message_top_near(page, data_index=0, expected_offset=anchor_offset)
    expect(jump_btn).to_be_visible()


@user_story("to verify a scrolled-up reading anchor holds its top position when the viewport widens")
def test_scrolled_up_holds_reading_anchor_on_widen(sculptor_instance_: SculptorInstance) -> None:
    """A message read at the top stays at the top (and stays off the bottom) on widen."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_VERY_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()
    wait_for_alpha_scroll_settled(page)

    # Scroll up so the first message sits at the top — a reading anchor, away
    # from the bottom (jump button shown).
    scroll_alpha_chat_to_top(page)
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()
    anchor_offset = get_message_top_offset(page, data_index=0)

    # Widen the viewport (width only).
    _set_viewport_width(page, _WIDE_WIDTH)

    # The same message holds its top offset, and we stay scrolled off the bottom.
    _wait_for_message_top_near(page, data_index=0, expected_offset=anchor_offset)
    expect(jump_btn).to_be_visible()


@user_story("to verify a following stream stays pinned to the bottom when the viewport narrows")
def test_following_stays_pinned_on_narrow(sculptor_instance_: SculptorInstance) -> None:
    """A streaming, pinned-to-bottom turn stays pinned (button hidden) on narrow."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Stream a long response and let it overflow so auto-scroll pins to the
    # bottom (following): the just-sent user message (data-index 2) scrolls off
    # the top.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    _wait_for_following_pinned(page, user_index=2)
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Narrow the viewport (width only) while streaming continues.
    _set_viewport_width(page, _NARROW_WIDTH)

    # Still pinned to the bottom: let it stream on, then re-assert hidden.
    chat_panel.wait_for_agent_progress()
    _expect_jump_button_hidden(jump_btn)

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)


@user_story("to verify a following stream stays pinned to the bottom when the viewport widens")
def test_following_stays_pinned_on_widen(sculptor_instance_: SculptorInstance) -> None:
    """A streaming, pinned-to-bottom turn stays pinned (button hidden) on widen."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Stream a long response and let it overflow so auto-scroll pins to the
    # bottom (following): the just-sent user message (data-index 2) scrolls off
    # the top.
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    _wait_for_following_pinned(page, user_index=2)
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Widen the viewport (width only) while streaming continues.
    _set_viewport_width(page, _WIDE_WIDTH)

    # Still pinned to the bottom: let it stream on, then re-assert hidden.
    chat_panel.wait_for_agent_progress()
    _expect_jump_button_hidden(jump_btn)

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)


@user_story("to verify a scrolled-away stream stays disengaged when the viewport narrows")
def test_scrolled_away_streaming_stays_disengaged_on_narrow(sculptor_instance_: SculptorInstance) -> None:
    """Narrowing must not silently re-engage auto-scroll on a scrolled-away stream."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Scroll to the top while streaming so auto-scroll disengages (jump shown).
    scroll_alpha_chat_to_top(page)
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()

    # Narrow the viewport (width only) while streaming continues.
    _set_viewport_width(page, _NARROW_WIDTH)

    # A width change must not re-engage auto-scroll: let it stream on, then
    # re-assert the button is still shown (the view is not snapped to the bottom).
    chat_panel.wait_for_agent_progress()
    expect(jump_btn).to_be_visible()

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)


@user_story("to verify a scrolled-away stream stays disengaged when the viewport widens")
def test_scrolled_away_streaming_stays_disengaged_on_widen(sculptor_instance_: SculptorInstance) -> None:
    """Widening must not silently re-engage auto-scroll on a scrolled-away stream."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    expect(get_alpha_chat_view(page)).to_be_visible()

    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 50, "delay_seconds": 0.1}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Scroll to the top while streaming so auto-scroll disengages (jump shown).
    scroll_alpha_chat_to_top(page)
    jump_btn = get_jump_to_bottom_button(page)
    expect(jump_btn).to_be_visible()

    # Widen the viewport (width only) while streaming continues.
    _set_viewport_width(page, _WIDE_WIDTH)

    # A width change must not re-engage auto-scroll: let it stream on, then
    # re-assert the button is still shown (the view is not snapped to the bottom).
    chat_panel.wait_for_agent_progress()
    expect(jump_btn).to_be_visible()

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)


@user_story("to verify an anchored (filling) turn keeps its user message at the top when the viewport narrows")
def test_anchored_turn_holds_top_on_narrow(sculptor_instance_: SculptorInstance) -> None:
    """A just-anchored user message stays near the top through a narrow resize."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Maximize chat height so the short streaming response fills below the
    # anchored user message without overflowing into the following phase.
    PlaywrightWorkspaceSection(page, "bottom").collapse_section()

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a short streaming message: scroll-to-top anchors the user message
    # (data-index 2) at the top while the response fills below (anchoringTurn).
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_ANCHOR_STREAM_TEXT}", "chunk_size": 20, "delay_seconds": 0.15}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    _wait_for_message_in_upper_half(page, data_index=2)
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Narrow the viewport (width only) during the filling phase.
    _set_viewport_width(page, _NARROW_WIDTH)

    # The anchored user message stays near the top and the jump button stays
    # hidden/suppressed.
    _wait_for_message_in_upper_half(page, data_index=2)
    _expect_jump_button_hidden(jump_btn)

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)


@user_story("to verify an anchored (filling) turn keeps its user message at the top when the viewport widens")
def test_anchored_turn_holds_top_on_widen(sculptor_instance_: SculptorInstance) -> None:
    """A just-anchored user message stays near the top through a widen resize."""
    page = sculptor_instance_.page
    _set_viewport_width(page, _INITIAL_WIDTH)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "{_SHORT_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Maximize chat height so the short streaming response fills below the
    # anchored user message without overflowing into the following phase.
    PlaywrightWorkspaceSection(page, "bottom").collapse_section()

    expect(get_alpha_chat_view(page)).to_be_visible()

    # Send a short streaming message: scroll-to-top anchors the user message
    # (data-index 2) at the top while the response fills below (anchoringTurn).
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_ANCHOR_STREAM_TEXT}", "chunk_size": 20, "delay_seconds": 0.15}}`',
    )
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    _wait_for_message_in_upper_half(page, data_index=2)
    jump_btn = get_jump_to_bottom_button(page)
    _expect_jump_button_hidden(jump_btn)

    # Widen the viewport (width only) during the filling phase.
    _set_viewport_width(page, _WIDE_WIDTH)

    # The anchored user message stays near the top and the jump button stays
    # hidden/suppressed.
    _wait_for_message_in_upper_half(page, data_index=2)
    _expect_jump_button_hidden(jump_btn)

    # Let streaming finish before cleanup.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)
