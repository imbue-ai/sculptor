"""Integration tests for alpha chat keyboard prompt navigation.

Covers the ArrowUp/ArrowDown/Escape/Enter hijacking implemented by
``useAlphaPromptNav``. Plain arrow keys (no Alt modifier) — entering nav
from the chat input requires the caret to be at position 0.  Once nav is
active, the active cursor moves by ±1 per arrow press, anchored to the
dot-rail highlight (see ``useAlphaActivePromptIndex``), not always to the
last prompt.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_by
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_prompt_navigator import ALPHA_DOT
from sculptor.testing.elements.alpha_prompt_navigator import get_alpha_prompt_navigator
from sculptor.testing.elements.base import wait_for_tiptap_ready
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Each response is long enough to produce a scrollable chat so the scroll-spy
# can actually compute distinct active indices per prompt.
LONG_TEXT = "Lorem ipsum dolor sit amet. " * 100

HIGHLIGHT_CLASS = "alphaPromptHighlight"


def _wait_for_highlight_on(page, expected_index: int, *, timeout: int = 30_000) -> None:
    """Wait until the highlighted message has the expected data-index."""
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('.{HIGHLIGHT_CLASS}');
            if (!el) return false;
            const wrapper = el.closest('[data-index]');
            return wrapper && Number(wrapper.getAttribute('data-index')) === {expected_index};
        }}""",
        timeout=timeout,
    )


def _wait_for_no_highlight(page, *, timeout: int = 30_000) -> None:
    """Wait until no message is highlighted."""
    page.wait_for_function(
        f"() => document.querySelectorAll('.{HIGHLIGHT_CLASS}').length === 0",
        timeout=timeout,
    )


def _focus_chat_input_at_start(chat_input, page) -> None:
    """Click the chat input and wait for focus + caret-at-start to settle.

    ``useAlphaPromptNav`` requires ``window.getSelection()`` to be collapsed
    at offset 0 of the contenteditable before it accepts ArrowUp from the
    input.  On slow CI runners, ``click()`` returns before the browser has
    placed the caret, so a subsequent ``keyboard.press("ArrowUp")`` is
    dropped.  This helper blocks until both conditions hold.
    """
    chat_input.click()
    page.wait_for_function(
        """() => {
            const active = document.activeElement;
            if (!active || !active.isContentEditable) return false;
            const sel = window.getSelection();
            if (!sel || !sel.isCollapsed || sel.rangeCount === 0) return false;
            const r = sel.getRangeAt(0);
            // Caret at very first character of the editable
            const probe = document.createRange();
            probe.selectNodeContents(active);
            probe.setEnd(r.startContainer, r.startOffset);
            return probe.toString().length === 0;
        }""",
    )


def _setup_three_prompt_chat(sculptor_instance_: SculptorInstance):
    """Create a 3-prompt alpha chat and return (page, chat_panel).

    Messages land at filteredMessage indices 0, 2, 4 (user), 1, 3, 5 (assistant).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:text `{{"text": "First response. {LONG_TEXT}"}}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(chat_panel, f'fake_claude:text `{{"text": "Second response. {LONG_TEXT}"}}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    send_chat_message(chat_panel, f'fake_claude:text `{{"text": "Third response. {LONG_TEXT}"}}`')
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6)

    # Reload so the chat renders from the persisted messages rather than from
    # the streaming pipeline.  Without this, auto-scroll-to-bottom during
    # streaming leaves scrollTop past the last prompt's start, and the
    # dot-click normalization below doesn't reliably land the virtualizer
    # where the prompt-nav hook expects.  Prior to alpha-default, the
    # equivalent reload happened inside ``switch_to_alpha_view``.
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    wait_for_tiptap_ready(page)

    expect(get_alpha_chat_view(page)).to_be_visible()
    # Wait for the non-virtualized dot rail to reflect all 3 user prompts —
    # the chat view itself is virtualized, so the [data-index] count only
    # covers visible items and can't be used as a readiness signal.
    alpha_nav = get_alpha_prompt_navigator(page)
    dots = alpha_nav.get_dots()
    expect(dots).to_have_count(3)

    # Normalize scroll state: click the last dot so the virtualizer lands
    # scrollTop ≈ start[lastUserMessage], then immediately exit navigation by
    # focusing the chat input.  Without this, the auto-scroll-to-bottom after
    # the 3rd response leaves scrollTop past the last prompt's start — on
    # slow CI runners that trips ``isScrolledPastActive()`` in the app's keydown
    # hook, so the first ArrowUp from a test becomes "scroll current turn
    # to top" instead of "decrement to previous prompt".
    dots.nth(2).click()
    # Focus the chat input via the dot-rail focusout path: pressing Escape
    # exits navigation cleanly (clears highlight, restores scroll-suppression,
    # focuses input) without racing an extra scroll.
    page.keyboard.press("Escape")
    _wait_for_no_highlight(page)
    # The dot-2 click issued an async scrollToIndex to the last user prompt;
    # Escape clears the highlight synchronously but does NOT wait for that scroll
    # to land. The prompt-nav keydown hook reads live scrollTop against a 20px
    # tolerance (isScrolledPastActive), so a first ArrowUp fired before the
    # scroll settles is misread as "scroll current turn to top" instead of "go to
    # previous prompt", and the highlight lands on the wrong message. Wait until
    # the last user prompt (message data-index 4) is pinned at the viewport top,
    # well within that tolerance, before handing back to the test.
    page.wait_for_function(
        """() => {
            const container = document.querySelector('[data-testid="ALPHA_CHAT_VIEW"]');
            const item = container && container.querySelector('[data-index="4"]');
            if (!container || !item) return false;
            return Math.abs(item.getBoundingClientRect().top - container.getBoundingClientRect().top) < 10;
        }"""
    )
    return page, chat_panel


@user_story("to cycle backward through user prompts with plain ArrowUp")
def test_plain_arrow_up_cycles_backward(sculptor_instance_: SculptorInstance) -> None:
    """ArrowUp from input at caret 0 enters nav at active-1, continues backward."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    _wait_for_no_highlight(page)

    # Click the alpha chat view to ensure it has focus for keyboard events.
    # _setup_three_prompt_chat already waited for the non-virtualized dot
    # rail to reflect all 3 prompts, so the view is ready for interaction.
    alpha_view = get_alpha_chat_view(page)
    alpha_view.click()
    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    # At bottom, active = last (index 2 into userPromptIndices). First
    # ArrowUp navigates to active - 1 = 1 → message index 2.
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)

    # Second ArrowUp: 1 - 1 = 0 → message index 0.
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 0)

    # Third ArrowUp at index 0: no-op (still highlighted at 0).
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 0)


@user_story("to exit nav by pressing Escape and return focus to the chat input")
def test_escape_exits_and_refocuses_input(sculptor_instance_: SculptorInstance) -> None:
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)

    page.keyboard.press("Escape")
    _wait_for_no_highlight(page)
    expect(chat_input).to_be_focused()


@user_story("to exit nav by pressing Enter and return focus to the chat input")
def test_enter_exits_and_refocuses_input(sculptor_instance_: SculptorInstance) -> None:
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)

    page.keyboard.press("Enter")
    _wait_for_no_highlight(page)
    expect(chat_input).to_be_focused()


@user_story("to exit nav by pressing ArrowDown past the last prompt")
def test_arrow_down_past_last_exits_and_scrolls_to_bottom(sculptor_instance_: SculptorInstance) -> None:
    """ArrowDown past last prompt exits nav + scrolls to bottom + re-focuses input."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    # First ArrowUp: active goes from 2 → 1 (message index 2).
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)

    # ArrowDown: active 1 → 2 (message index 4).
    page.keyboard.press("ArrowDown")
    _wait_for_highlight_on(page, 4)

    # ArrowDown again: past last → exit, scroll to bottom, focus input.
    page.keyboard.press("ArrowDown")
    _wait_for_no_highlight(page)
    expect(chat_input).to_be_focused()


@user_story("to navigate prompts when focus is outside the chat input")
def test_arrow_up_works_without_input_focus(sculptor_instance_: SculptorInstance) -> None:
    """Keyboard handler lives on window, so blurring the input still works."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    # Click the alpha view and then blur so the keypress isn't consumed as text.
    # _setup_three_prompt_chat already waited for dot-rail readiness.
    alpha_view = get_alpha_chat_view(page)
    alpha_view.click()
    blur_active_element(page)
    # Verify focus actually left the chat input — on slower machines, React
    # may asynchronously restore focus (e.g. via focusChatInput callbacks).
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).not_to_be_focused()

    # ArrowUp with no input focus: since isNavigating=false and not in an
    # editable, the guard requires input focus for entry. So this must NOT
    # hijack the key. The hook only enters nav from the input.
    # But once we've entered nav (via input click + ArrowUp), subsequent
    # presses work regardless of focus.
    # To prove the "continues after focus leaves" path, enter nav via input
    # first, then blur, then press ArrowUp again.
    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)

    blur_active_element(page)
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 0)


@user_story("modifier keys do not hijack ArrowUp for prompt navigation")
def test_modifier_keys_do_not_trigger_nav(sculptor_instance_: SculptorInstance) -> None:
    """Alt/Ctrl/Meta/Shift + ArrowUp should NOT enter prompt navigation."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    _wait_for_no_highlight(page)

    for mod in ("Alt", "Control", "Meta", "Shift"):
        page.keyboard.press(f"{mod}+ArrowUp")
        _wait_for_no_highlight(page)

    # Plain ArrowUp must still work after the modifier attempts.
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 2)


@user_story("ArrowUp nav anchors to current scroll position, not always last")
def test_arrow_up_anchors_to_scroll_position(sculptor_instance_: SculptorInstance) -> None:
    """Scroll up past a prompt, then ArrowUp should start from the visible
    region (scroll-spy active index), not always jump to the last prompt."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    # Scroll to the top so the scroll-spy sets active = 0 (first prompt).
    scroll_alpha_chat_to_top(page)
    page.wait_for_function(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            return dots.findIndex(d => d.getAttribute('data-is-active') === 'true') === 0;
        }}"""
    )

    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)
    # With active = 0, ArrowUp should decrement to -1 → no-op (NO highlight).
    # That proves the nav is anchored to the active dot, not always starting
    # at last. If we hit this path and nothing highlights, the anchoring works.
    page.keyboard.press("ArrowUp")
    _wait_for_no_highlight(page)


@user_story("ArrowUp with caret mid-text stays in the editor and does not enter nav")
def test_arrow_up_with_caret_midtext_does_not_enter_nav(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the caret is NOT at position 0, ArrowUp must not hijack."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)
    _wait_for_no_highlight(page)

    chat_input = chat_panel.get_chat_input()
    chat_input.click()
    # Put a couple of characters in the editor so the caret is not at position 0.
    chat_input.fill("hi")

    page.keyboard.press("ArrowUp")
    _wait_for_no_highlight(page)


def _get_active_dot_index(page) -> int:
    """Return the 0-based index of the currently active dot, or -1 if none."""
    return page.evaluate(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            return dots.findIndex(d => d.getAttribute('data-is-active') === 'true');
        }}"""
    )


@user_story("a mouse wheel cancels the programmatic-scroll freeze after a dot click")
def test_wheel_cancels_programmatic_scroll_freeze(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a dot opens a 500ms window where scroll-spy updates are
    frozen so the async scrollToIndex can't clobber the cursor.  A user
    wheel/touch event must immediately cancel that freeze so the dot rail
    resumes tracking the user's new scroll position."""
    page, _ = _setup_three_prompt_chat(sculptor_instance_)

    # Click the first dot — triggers setIndex(0) + scrollToIndex, opening the
    # 500ms programmatic-scroll window with active dot pinned to index 0.
    get_alpha_prompt_navigator(page).get_dot(0).click()
    # Wait for the click to register (setIndex fires synchronously in React).
    page.wait_for_function(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            return dots.findIndex(d => d.getAttribute('data-is-active') === 'true') === 0;
        }}""",
    )

    # Within the 500ms freeze, fire a wheel event that scrolls far down.  This
    # must clear the freeze via onUserScrollInput and let the scroll-spy move
    # the active dot off of index 0.
    scroll_alpha_chat_by(page, 5000)

    # The active dot should update away from 0 as scroll-spy re-engages.
    page.wait_for_function(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            const idx = dots.findIndex(d => d.getAttribute('data-is-active') === 'true');
            return idx > 0;
        }}""",
    )


@user_story("ArrowUp first scrolls the current turn to the top, then moves to the previous prompt")
def test_arrow_up_scrolls_current_turn_to_top_first(sculptor_instance_: SculptorInstance) -> None:
    """When scrolled partway into the current turn (past the top of the active
    user message by more than the 20px tolerance), the first ArrowUp scrolls
    the current turn's user message back to the top instead of decrementing
    the cursor.  A second ArrowUp then moves to the previous prompt."""
    page, chat_panel = _setup_three_prompt_chat(sculptor_instance_)

    # The scroll loop below walks the virtualizer through every item, which
    # populates measurementsCache entries as items enter the viewport —
    # isScrolledPastActive relies on that cache.  No need to pre-wait for
    # all 6 items to be in the DOM (they won't be: the list is virtualized).
    page.wait_for_timeout(300)

    # Position the scroll so idx=4 (the last user message) is above the
    # viewport's top by > 20px (outside the isScrolledPastActive tolerance).
    # Starting from the top and scrolling DOWN incrementally is robust across
    # viewport sizes — we don't assume any particular starting scroll position.
    # scroll_alpha_chat_to_top already settles across several animation frames
    # (it awaits its own rAF chain), and the incremental loop below re-reads and
    # self-corrects, so no extra fixed wait is needed here.
    scroll_alpha_chat_to_top(page)
    last_user_top = get_message_top_offset(page, 4)
    attempts = 0
    while last_user_top > -50 and attempts < 40:
        scroll_alpha_chat_by(page, 300)
        page.wait_for_timeout(100)
        last_user_top = get_message_top_offset(page, 4)
        attempts += 1
    assert last_user_top < -20, (
        f"Expected last user message top to be above the viewport by >20px, got {last_user_top} "
        + f"after {attempts} scroll iterations. Precondition isn't met."
    )

    active_before = _get_active_dot_index(page)

    # Focus the chat input with the caret at position 0, then press ArrowUp.
    chat_input = chat_panel.get_chat_input()
    _focus_chat_input_at_start(chat_input, page)

    page.keyboard.press("ArrowUp")

    # First ArrowUp: should scroll the current-turn user message to the top
    # (offset becomes ~0, within tolerance) — NOT decrement to the previous
    # prompt. Allow a modest tolerance for sub-pixel rendering.
    page.wait_for_function(
        """() => {
            const container = document.querySelector('[data-testid="ALPHA_CHAT_VIEW"]');
            const item = container && container.querySelector('[data-index="4"]');
            if (!container || !item) return false;
            const delta = item.getBoundingClientRect().top - container.getBoundingClientRect().top;
            return Math.abs(delta) < 30;
        }"""
    )

    # Active dot should NOT have changed — we scrolled, didn't nav backward.
    active_after_first = _get_active_dot_index(page)
    assert active_after_first == active_before, (
        "First ArrowUp should scroll the current turn to the top, not decrement. "
        + f"active before={active_before}, after={active_after_first}."
    )

    # Second ArrowUp: now aligned with the active prompt's top, so this one
    # should decrement to the previous prompt.
    page.keyboard.press("ArrowUp")
    page.wait_for_function(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            const idx = dots.findIndex(d => d.getAttribute('data-is-active') === 'true');
            return idx === {active_before - 1};
        }}"""
    )
