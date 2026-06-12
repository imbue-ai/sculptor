"""Integration tests for the alpha chat prompt navigator dot rail.

Focuses on interactions with ``AlphaPromptNavigator``: dot clicks, active
highlight tracking the scroll position, keyboard nav continuing from a
clicked dot, and popover tooltip on hover.  The non-alpha dot rail
(``PromptNavigator.tsx``) is covered separately by
``test_prompt_navigator.py``.
"""

import json

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_prompt_navigator import ALPHA_DOT
from sculptor.testing.elements.alpha_prompt_navigator import ALPHA_TOOLTIP
from sculptor.testing.elements.alpha_prompt_navigator import get_alpha_prompt_navigator
from sculptor.testing.elements.base import _FIND_TIPTAP_EDITOR_JS
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

HIGHLIGHT_CLASS = "alphaPromptHighlight"

# Long enough to make the scroll container taller than the viewport so the
# scroll-spy can distinguish between prompts.
_LONG_RESPONSE_TEXT = "\n".join(
    f"Response line {i + 1}: Lorem ipsum dolor sit amet, consectetur adipiscing elit." for i in range(50)
)


def _long_prompt(label: str) -> str:
    body = label + "\n" + _LONG_RESPONSE_TEXT
    return f"fake_claude:text `{json.dumps({'text': body})}`"


def _setup_alpha_chat(
    sculptor_instance_: SculptorInstance,
    prompt_count: int = 3,
) -> tuple[Page, PlaywrightChatPanelElement]:
    """Create a workspace with `prompt_count` user prompts."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_long_prompt("First prompt"))
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    for i in range(1, prompt_count):
        send_chat_message(chat_panel=chat_panel, message=_long_prompt(f"Prompt {i + 1}"))
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2 + i * 2)

    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)).to_be_visible()
    expect(page.get_by_test_id(ALPHA_DOT)).to_have_count(prompt_count)
    return page, chat_panel


def _wait_for_highlight_on(page: Page, expected_index: int, *, timeout: int = 30_000) -> None:
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('.{HIGHLIGHT_CLASS}');
            if (!el) return false;
            const wrapper = el.closest('[data-index]');
            return wrapper && Number(wrapper.getAttribute('data-index')) === {expected_index};
        }}""",
        timeout=timeout,
    )


def _wait_for_active_dot_index(page: Page, expected_index: int) -> None:
    """Wait until the active dot index matches ``expected_index``."""
    page.wait_for_function(
        f"""() => {{
            const dots = Array.from(document.querySelectorAll('[data-testid="{ALPHA_DOT}"]'));
            const idx = dots.findIndex(d => d.getAttribute('data-is-active') === 'true');
            return idx === {expected_index};
        }}"""
    )


@user_story("to see a dot per user prompt in the alpha dot rail")
def test_dot_rail_shows_one_dot_per_user_prompt(sculptor_instance_: SculptorInstance) -> None:
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    expect(navigator.get_dots()).to_have_count(3)


@user_story("to navigate to a prompt by clicking its dot")
def test_clicking_dot_scrolls_and_highlights_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a dot highlights the corresponding user message."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Click the first dot — corresponds to userPromptIndices[0] = message index 0.
    navigator.get_dot(0).click()
    _wait_for_highlight_on(page, 0)

    # Click the third dot — userPromptIndices[2] = message index 4.
    navigator.get_dot(2).click()
    _wait_for_highlight_on(page, 4)


@user_story("active dot tracks scroll position")
def test_active_dot_tracks_scroll_position(sculptor_instance_: SculptorInstance) -> None:
    """When at the bottom, the last dot is active; when scrolled to top, the
    first dot is active."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)

    # At the bottom (initial state after sending messages), the last dot is active.
    _wait_for_active_dot_index(page, 2)

    # Scroll to top — scroll-spy should eventually set active = 0.
    scroll_alpha_chat_to_top(page)
    _wait_for_active_dot_index(page, 0)


@user_story("keyboard nav continues after clicking a dot")
def test_arrow_keys_continue_after_dot_click(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a dot enters nav mode; subsequent ArrowUp/Down works even
    though focus moved off the chat input."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Click the middle dot — message index 2.
    navigator.get_dot(1).click()
    _wait_for_highlight_on(page, 2)

    # ArrowUp: active 1 → 0 → message index 0.
    page.keyboard.press("ArrowUp")
    _wait_for_highlight_on(page, 0)

    # ArrowDown: active 0 → 1 → message index 2.
    page.keyboard.press("ArrowDown")
    _wait_for_highlight_on(page, 2)


@user_story("to preview a prompt by hovering its dot")
def test_hovering_dot_shows_popover(sculptor_instance_: SculptorInstance) -> None:
    """Hovering a dot shows a popover containing the prompt text."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Hover the first dot. The popover opens after ~420ms.
    navigator.get_dot(0).hover()

    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()
    # Should include the prompt label text.
    expect(tooltip).to_contain_text("First prompt")


@user_story("popover content swaps when hovering a different dot")
def test_popover_swaps_content_between_dots(sculptor_instance_: SculptorInstance) -> None:
    """Hover dot A, open popover, then hover dot B — content updates to B."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Open popover for the first dot.
    navigator.get_dot(0).hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()
    expect(tooltip).to_contain_text("First prompt")

    # Move to the third dot. Since the popover is already visible, the
    # content swaps instantly (no additional open delay).
    navigator.get_dot(2).hover()
    expect(tooltip).to_contain_text("Prompt 3")
    # And the old prompt's label is gone.
    expect(tooltip).not_to_contain_text("First prompt")


@user_story("popover dismisses shortly after the mouse leaves the rail")
def test_popover_dismisses_on_mouse_leave(sculptor_instance_: SculptorInstance) -> None:
    """Moving the mouse away from the rail closes the popover."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    navigator.get_dot(0).hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()

    # Move the mouse to a neutral element far from the rail.
    get_alpha_chat_view(page).hover(position={"x": 50, "y": 50})
    expect(tooltip).not_to_be_visible()


@user_story("right-clicking a dot opens a Copy prompt context menu")
def test_right_click_dot_opens_copy_context_menu(sculptor_instance_: SculptorInstance) -> None:
    """Radix ContextMenu exposes a Copy prompt item on right-click."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Right-click the first dot.  The dot wrapper is the ContextMenu.Trigger.
    navigator.get_dot(0).click(button="right")

    # The Copy prompt menu item should appear. Radix ContextMenu items have
    # role="menuitem"; we check via evaluate() to stay ElementIDs-free.
    page.wait_for_function(
        """() => {
            const items = document.querySelectorAll('[role="menuitem"]');
            return Array.from(items).some(el => (el.textContent || '').trim() === 'Copy prompt');
        }"""
    )

    # Dismiss the menu so it does not interfere with later tests.
    page.keyboard.press("Escape")


@user_story("popover exposes a copy button and the prompt label")
def test_popover_contains_copy_button_and_prompt_label(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The popover renders the `PROMPT N` header and an in-tooltip copy button."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    navigator.get_dot(1).hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()
    # `PROMPT N` label is 1-indexed.
    expect(tooltip).to_contain_text("PROMPT 2")

    # The inline copy button (title="Copy prompt") is present inside the
    # tooltip. Use wait_for_function so Playwright polls until the button
    # renders, instead of a one-shot evaluate.
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ALPHA_TOOLTIP}"]');
            if (!el) return false;
            const btn = el.querySelector('button[title="Copy prompt"]');
            return btn !== null && !btn.disabled;
        }}"""
    )


@user_story("opening the right-click context menu dismisses the hover popover")
def test_context_menu_dismisses_popover(sculptor_instance_: SculptorInstance) -> None:
    """Opening the right-click menu closes any currently open hover popover."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Open the hover popover first.
    dot = navigator.get_dot(0)
    dot.hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()

    # Now right-click — the context menu should open and the popover should
    # dismiss (isContextMenuOpen effect calls dismissPopover).
    dot.click(button="right")
    page.wait_for_function(
        """() => {
            const items = document.querySelectorAll('[role="menuitem"]');
            return Array.from(items).some(el => (el.textContent || '').trim() === 'Copy prompt');
        }"""
    )
    expect(tooltip).not_to_be_visible()

    page.keyboard.press("Escape")


@user_story("clicking the popover copy button copies prompt text and flips the icon to a check")
def test_popover_copy_button_copies_and_flips_icon(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the in-popover copy button writes the prompt text to the
    clipboard and flips the copy icon to a check for the confirmation window."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    # Grant clipboard permissions so we can read back what the button wrote.
    # Playwright's clipboard permissions are supported in Chromium.
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        clipboard_available = True
    except Exception:
        # Fall back to asserting only the icon flip if the harness/browser
        # does not support granting clipboard permissions.
        clipboard_available = False

    # Open the popover on the second dot so we have deterministic label text.
    navigator.get_dot(1).hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()
    expect(tooltip).to_contain_text("Prompt 2")

    # Before click: the check icon is not yet present inside the copy button.
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ALPHA_TOOLTIP}"]');
            if (!el) return false;
            const btn = el.querySelector('button[title="Copy prompt"]');
            return btn !== null && btn.querySelector('svg.lucide-check') === null;
        }}"""
    )

    # Click the copy button inside the popover.
    navigator.get_copy_button().click()

    # Icon should flip to a check mark (lucide-check svg inside the button).
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="{ALPHA_TOOLTIP}"]');
            if (!el) return false;
            const btn = el.querySelector('button[title="Copy prompt"]');
            return btn !== null && btn.querySelector('svg.lucide-check') !== null;
        }}"""
    )

    if clipboard_available:
        # The clipboard should contain the second prompt's text. getMessageText
        # strips HTML; the "Prompt 2" label is on the first line followed by
        # the long response body.
        clipboard_text = page.evaluate("navigator.clipboard.readText()")
        assert "Prompt 2" in clipboard_text, f"Clipboard should contain the prompt body, got: {clipboard_text[:200]!r}"


@user_story("hovering onto the popover body keeps it open past the close delay")
def test_hovering_popover_body_keeps_it_open(sculptor_instance_: SculptorInstance) -> None:
    """Moving the mouse off the dot and onto the popover body must keep the
    popover visible (the popover's mouseenter clears the close timer).  Only
    leaving the popover entirely closes it after the 80ms close delay."""
    page, _ = _setup_alpha_chat(sculptor_instance_, prompt_count=3)
    navigator = get_alpha_prompt_navigator(page)

    navigator.get_dot(1).hover()
    tooltip = navigator.get_tooltip()
    expect(tooltip).to_be_visible()

    # Move the mouse onto the popover body (its bounding-box center). Use
    # page.mouse.move so we simulate an actual cursor transit that will fire
    # mouseleave on the dot and mouseenter on the popover.
    box = tooltip.bounding_box()
    assert box is not None, "popover should have a bounding box when visible"
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    # Well beyond the 80ms CLOSE_DELAY_MS. The popover must still be visible.
    page.wait_for_timeout(300)
    expect(tooltip).to_be_visible()

    # Now leave the popover entirely by moving to empty space far away.
    page.mouse.move(5, 5)
    expect(tooltip).not_to_be_visible()


@user_story("ArrowUp from inside a code block with a leading empty line moves the caret, not the prompt navigator")
def test_arrow_up_inside_code_block_with_leading_empty_line_does_not_enter_nav(
    sculptor_instance_: SculptorInstance,
) -> None:
    """SCU-517 regression: an empty paragraph above a code block must not trick
    the "very start of editor" check into engaging prompt navigation.

    The DOM range from the editor's start to a caret inside the code block
    has zero rendered characters (the leading empty paragraph contributes
    none), so a text-length-based "is at very start" check returned true
    incorrectly. ArrowUp must instead let the browser move the caret up to
    the leading empty line.
    """
    page, chat_panel = _setup_alpha_chat(sculptor_instance_, prompt_count=2)

    chat_input = chat_panel.get_chat_input()
    chat_input.click()

    # Build the document programmatically: <p></p> followed by a code block
    # containing "blahblahbla", then position the caret inside the code text.
    # Going through TipTap's API avoids depending on input-rule details.
    chat_input.evaluate(
        f"""(el) => {{
            const findEditor = (el) => {{ {_FIND_TIPTAP_EDITOR_JS} }};
            const editor = findEditor(el);
            editor.chain()
              .focus()
              .clearContent()
              .insertContent([
                {{ type: 'paragraph' }},
                {{ type: 'codeBlock', content: [{{ type: 'text', text: 'blahblahbla' }}] }},
              ])
              .run();
            let codeTextStart = null;
            editor.state.doc.descendants((node, pos) => {{
                if (node.type.name === 'codeBlock' && codeTextStart === null) {{
                    codeTextStart = pos + 1;
                }}
            }});
            editor.commands.focus(codeTextStart);
        }}"""
    )

    page.keyboard.press("ArrowUp")

    # When prompt navigation engages it blurs the chat input; the default
    # browser ArrowUp leaves the caret inside the editor, so focus is
    # retained. Use that as a single-signal regression check. The CHAT_INPUT
    # test id sits on the contenteditable itself.
    expect(chat_input).to_be_focused()
