from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightAlphaChatViewElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the alpha (new) chat view."""

    def get_messages(self) -> Locator:
        """Get all message containers in the alpha view."""
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_MESSAGE)

    def get_user_messages(self) -> Locator:
        """Get all user message containers in the alpha view."""
        return self._locator.locator(f"[data-testid='{ElementIDs.ALPHA_CHAT_MESSAGE.value}'][data-role='user']")

    def get_assistant_messages(self) -> Locator:
        """Get all assistant message containers in the alpha view."""
        return self._locator.locator(f"[data-testid='{ElementIDs.ALPHA_CHAT_MESSAGE.value}'][data-role='assistant']")

    def get_text_blocks(self) -> Locator:
        """Get all text block elements in the alpha view."""
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TEXT)

    def get_turn_footers(self) -> Locator:
        """Get all turn footer elements."""
        return self.get_by_test_id(ElementIDs.TURN_FOOTER)

    def get_turn_footer_token_count(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TURN_FOOTER_TOKEN_COUNT)

    def get_token_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TOKEN_POPOVER)

    def get_turn_footer_file_count(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TURN_FOOTER_FILE_COUNT)

    def get_turn_footer_file_row(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TURN_FOOTER_FILE_ROW)

    def get_tool_lines(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_LINE)

    def get_bash_blocks(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_BLOCK)

    def get_bash_output(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_OUTPUT)

    def get_chip_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_ROW)

    def get_file_chips(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_FILE_CHIP)

    def get_intro(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_INTRO)

    def get_chip_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_POPOVER)

    def get_chip_view_full_diff_btn(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN)

    def get_subagent_pills(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)

    def get_tool_pill_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL_ROW)

    def get_tool_pills(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)

    def get_tool_pill_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL_POPOVER)

    def get_copy_buttons(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_COPY_BUTTON)

    def get_file_path_links(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_FILE_PATH_LINK)

    def get_streaming_cursor(self) -> Locator:
        return self.get_by_test_id(ElementIDs.STREAMING_CURSOR)

    def get_exit_plan_mode_block(self) -> Locator:
        return self.get_by_test_id(ElementIDs.EXIT_PLAN_MODE_TOOL_BLOCK)

    def get_file_preview_list(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_PREVIEW_LIST)

    def get_file_previews(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FILE_PREVIEW)


def get_jump_to_bottom_button(page: Page) -> Locator:
    """Locator for the jump-to-bottom button."""
    return page.get_by_test_id(ElementIDs.ALPHA_JUMP_TO_BOTTOM_BUTTON)


def get_alpha_scroll_position(page: Page) -> float:
    """Read the scrollTop of the alpha chat scroll container."""
    return page.evaluate(
        f"""() => {{
        const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        return el ? el.scrollTop : 0;
    }}"""
    )


def get_message_top_offset(page: Page, data_index: int) -> float:
    """Return the top offset of a message relative to the scroll container viewport.

    Finds the virtual item wrapper with ``data-index`` and returns the distance
    from the scroll container's top edge to the message's top edge in pixels.
    """
    return page.evaluate(
        f"""(idx) => {{
        const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        const item = container && container.querySelector('[data-index="' + idx + '"]');
        if (!container || !item) return -1;
        return item.getBoundingClientRect().top - container.getBoundingClientRect().top;
    }}""",
        data_index,
    )


def get_alpha_container_height(page: Page) -> float:
    """Read the clientHeight of the alpha chat scroll container."""
    return page.evaluate(
        f"""() => {{
        const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        return el ? el.clientHeight : 0;
    }}"""
    )


def get_alpha_scroll_height(page: Page) -> float:
    """Read the scrollHeight of the alpha chat scroll container."""
    return page.evaluate(
        f"""() => {{
        const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        return el ? el.scrollHeight : 0;
    }}"""
    )


def scroll_alpha_chat_to_top(page: Page) -> None:
    """Scroll the alpha chat to the top.

    Dispatches a wheel event first so the auto-scroll hook recognises this as a
    user-initiated scroll and disengages.  Then enforces scrollTop = 0 across
    several animation frames to outlast any queued TanStack Virtual scroll
    corrections (scrollToIndex calls schedule async rAF-based scrolls).
    """
    page.evaluate(
        f"""() => new Promise(resolve => {{
        const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        if (!el) {{ resolve(); return; }}
        el.dispatchEvent(new Event('wheel'));
        el.scrollTop = 0;
        el.dispatchEvent(new Event('scroll'));
        let frames = 5;
        const enforce = () => {{
            el.scrollTop = 0;
            if (--frames > 0) {{
                requestAnimationFrame(enforce);
            }} else {{
                resolve();
            }}
        }};
        requestAnimationFrame(enforce);
    }})"""
    )


def scroll_alpha_chat_by(page: Page, delta: int) -> None:
    """Scroll the alpha chat by a pixel delta (negative = up, positive = down)."""
    page.evaluate(
        f"""(delta) => {{
        const el = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        if (el) {{
            el.dispatchEvent(new Event('wheel'));
            el.scrollTop += delta;
            el.dispatchEvent(new Event('scroll'));
        }}
    }}""",
        delta,
    )


def click_visible_in_chat_viewport(page: Page, test_id: str) -> None:
    """Dispatch a synthetic click on the first element with ``test_id`` that is
    fully inside the alpha chat scroll viewport.

    Uses ``dispatchEvent`` rather than Playwright's ``locator.click()`` so the
    test can avoid Playwright's automatic scroll-into-view, which would shift
    ``scrollTop`` before the click and mask the behaviour we want to assert
    against. Raises if no matching element is currently in view.
    """
    page.evaluate(
        f"""(testId) => {{
        const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        const elements = document.querySelectorAll('[data-testid="' + testId + '"]');
        if (!container) throw new Error("alpha chat view not found");
        const cRect = container.getBoundingClientRect();
        for (const el of elements) {{
            const r = el.getBoundingClientRect();
            if (r.top >= cRect.top && r.bottom <= cRect.bottom) {{
                el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
                return;
            }}
        }}
        throw new Error("no element with testId=" + testId + " is currently visible in the chat viewport");
    }}""",
        test_id,
    )


class PlaywrightDebugChatViewElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the debug chat view."""

    def get_blocks(self) -> Locator:
        """Get all block entries in the debug view."""
        return self.get_by_test_id(ElementIDs.DEBUG_CHAT_BLOCK)


def switch_to_debug_view(page: Page, agent_tab_name: str = "Agent 1") -> None:
    """Toggle debug view on for an agent via the tab context menu.

    Right-clicks the agent tab, opens the Diagnostics submenu, and clicks
    the Debug View toggle.
    """
    tab = page.get_by_role("tab", name=agent_tab_name)
    tab.click(button="right")
    page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DIAGNOSTICS).click()
    page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DEBUG_VIEW).click()


def get_intro_bottom_offset(page: Page) -> float:
    """Return the intro block's bottom edge relative to the scroll container's top.

    Returns -1 if either the scroll container or the intro element is not found.
    """
    return page.evaluate(
        f"""() => {{
        const container = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_VIEW}"]');
        const intro = document.querySelector('[data-testid="{ElementIDs.ALPHA_CHAT_INTRO}"]');
        if (!container || !intro) return -1;
        return intro.getBoundingClientRect().bottom - container.getBoundingClientRect().top;
    }}"""
    )


def get_alpha_chat_view(page: Page) -> PlaywrightAlphaChatViewElement:
    """Get the alpha chat view element from the page."""
    locator = page.get_by_test_id(ElementIDs.ALPHA_CHAT_VIEW)
    return PlaywrightAlphaChatViewElement(locator=locator, page=page)


def get_debug_chat_view(page: Page) -> PlaywrightDebugChatViewElement:
    """Get the debug chat view element from the page."""
    locator = page.get_by_test_id(ElementIDs.DEBUG_CHAT_VIEW)
    return PlaywrightDebugChatViewElement(locator=locator, page=page)
