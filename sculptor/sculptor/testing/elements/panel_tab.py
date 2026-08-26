"""Page Object Model for a panel tab and its affordances.

Agents and terminals render as panel tabs in a section header
(``PANEL_TAB-agent:<taskId>`` / ``PANEL_TAB-terminal:<wsId>:<n>``), created from the
same section ``+`` add-panel dropdown. This POM consolidates the affordances shared by
agent and terminal tabs: rename (double-click or context menu), close (→ delete/close
confirmation via the X button OR the menu's destructive row), and the agent's
diagnostics copy actions. The tabs use the shared affordance ids ``TAB_CONTEXT_MENU_*``,
``INLINE_RENAME_INPUT``, and ``DELETE_CONFIRMATION_*``.

The panel-tab context menu has a clear hierarchy: Rename, then the agent's own actions
(Mark as unread, Copy agent name, and a ``Diagnostics`` submenu tucking away the id /
session id / transcript-path copy items), then the section split options, then a
destructive row — ``Delete`` for agents, ``Close`` for terminals. Every actionable row
carries a ``TAB_CONTEXT_MENU_*`` testid; the diagnostics copy items sit behind the
Diagnostics submenu and render disabled (Radix ``data-disabled``) until their value
exists. Constructed with the ``sub_section`` whose header hosts the tabs.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection

# A native double-click is occasionally dropped when the browser's main thread is
# saturated: under heavy CI contention the gap between the two synthetic clicks
# stretches past the double-click threshold, so the browser registers two single
# clicks and no ``dblclick`` fires — the inline rename never starts. Retry the gesture
# this many times, waiting this long for the input each time, before giving up. Mirrors
# the hover/menu-open retries the sibling add-panel POM uses for Radix teardown races.
# The context-menu rename path needs no such retry: the menu enters rename mode via
# its onCloseAutoFocus handler, which is deterministic once the Rename row's click
# lands.
_DOUBLE_CLICK_RENAME_ATTEMPTS = 4
_DOUBLE_CLICK_RENAME_TIMEOUT_MS = 3_000


class PlaywrightPanelTabElement:
    """POM over the panel tabs in one sub-section's header + their affordances."""

    def __init__(self, page: Page, sub_section: str = "center") -> None:
        self._page = page
        self._sub_section = sub_section
        self._section = PlaywrightWorkspaceSection(page, sub_section)

    # Tab getters

    def get_panel_tabs(self) -> Locator:
        """Get every panel tab in this sub-section's header."""
        return self._section.get_panel_tabs()

    def get_panel_tab(self, panel_id: str) -> Locator:
        """Get the panel tab for a specific panel id (e.g. ``agent:<taskId>``).

        Agent (and terminal-agent) panel tabs stamp ``data-dot-status`` on the tab
        element itself (read/unread/running/waiting/error), so callers can assert
        ``to_have_attribute("data-dot-status", …)`` directly on the returned locator.
        """
        return self._section.get_panel_tab(panel_id)

    def get_panel_tab_by_name(self, name: str) -> Locator:
        """Get the panel tab(s) whose label contains ``name``."""
        return self.get_panel_tabs().filter(has_text=name)

    def get_agent_tabs(self) -> Locator:
        """Get every agent panel tab in this sub-section's header (excludes terminals/static)."""
        return self._section.get_agent_tabs()

    def get_active_tab(self) -> Locator:
        """Get the active (selected) panel tab in this sub-section."""
        return self._section.get_active_tab()

    def get_tab_status_dot(self, tab: Locator) -> Locator:
        """Get the rendered status-dot element inside a panel tab.

        Agent tabs render a visible dot whose ``data-panel-tab-dot`` attribute carries
        the same status as the tab's ``data-dot-status``, so tests can assert the dot is
        actually rendered (visible) with the expected status — not just that the tab
        carries the data attribute.
        """
        return tab.get_by_test_id(ElementIDs.PANEL_TAB_STATUS_DOT)

    # Close (→ delete/close confirmation)

    def get_tab_close_button(self, panel_id: str) -> Locator:
        """Get a panel tab's always-visible close (X) button by panel id."""
        return self._page.get_by_test_id(f"{ElementIDs.PANEL_TAB_CLOSE}-{panel_id}")

    def get_tab_close_button_of(self, tab: Locator) -> Locator:
        """Get the close (X) button scoped under a tab locator.

        For callers holding a positional/by-name tab locator without its panel id
        (the testid is panel-id-suffixed, so a prefix match is required).
        """
        return tab.locator(f'[data-testid^="{ElementIDs.PANEL_TAB_CLOSE}-"]')

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)

    def get_delete_confirmation_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CANCEL)

    def delete_panel_via_close_button(self, panel_id: str) -> None:
        """Click a panel tab's close button and confirm in the delete/close dialog.

        Keyed by panel id and usable for both agent (delete) and terminal (close)
        confirmations.
        """
        tab = self.get_panel_tab(panel_id)
        tab.click()
        close_button = self.get_tab_close_button(panel_id)
        expect(close_button).to_be_visible()
        close_button.click()
        confirm_button = self.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    # Context menu

    def open_context_menu(self, tab: Locator) -> None:
        """Right-click a tab to open its context menu."""
        tab.click(button="right")

    def get_menu_item(self, test_id: str) -> Locator:
        """Get an open context-menu row (or submenu trigger) by its testid."""
        return self._page.get_by_test_id(test_id)

    def get_context_menu_rename_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_context_menu_mark_unread_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_MARK_UNREAD)

    def get_context_menu_delete_item(self) -> Locator:
        """Get the destructive Delete row shown on an agent tab's context menu."""
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)

    def get_context_menu_close_item(self) -> Locator:
        """Get the destructive Close row shown on a terminal tab's context menu."""
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE)

    def open_diagnostics_submenu(self, tab: Locator) -> None:
        """Right-click a tab and hover Diagnostics to reveal its copy submenu.

        The id / session id / transcript-path copy items live behind this submenu, so
        callers open it before locating them by testid.
        """
        self.open_context_menu(tab)
        trigger = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DIAGNOSTICS)
        expect(trigger).to_be_visible()
        trigger.hover()

    # Rename

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def rename_tab_via_context_menu(self, tab: Locator, new_name: str) -> None:
        """Open the context menu, click Rename, and commit a new label.

        A single attempt suffices: the menu defers entering rename mode to its
        onCloseAutoFocus handler, so the inline input mounts (and keeps focus)
        deterministically once the Rename row's click lands.
        """
        self.open_context_menu(tab)
        rename_item = self.get_context_menu_rename_item()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        # Assert focus explicitly: a blur cancels the rename, and ``fill`` would mask
        # a focus loss by refocusing the input itself.
        expect(rename_input).to_be_focused()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def start_inline_rename_via_double_click(self, tab: Locator) -> Locator:
        """Double-click ``tab`` to begin an inline rename and return the visible input.

        Retries the double-click (see the module note on dropped double-clicks under
        contention). Once the rename has started the input stays mounted, so a retry
        after an earlier gesture already opened it just re-clicks the open row —
        harmless — and the visibility check passes.
        """
        rename_input = self.get_inline_rename_input()
        for _ in range(_DOUBLE_CLICK_RENAME_ATTEMPTS):
            tab.dblclick()
            try:
                expect(rename_input).to_be_visible(timeout=_DOUBLE_CLICK_RENAME_TIMEOUT_MS)
                return rename_input
            except AssertionError:
                continue
        # Out of retries: assert once more so the failure carries the standard message.
        expect(rename_input).to_be_visible()
        return rename_input

    def dblclick_rename(self, tab: Locator, new_name: str) -> None:
        """Double-click a tab to begin renaming, then commit a new label."""
        rename_input = self.start_inline_rename_via_double_click(tab)
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()
