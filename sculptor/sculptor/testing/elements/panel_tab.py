"""Page Object Model for a panel tab and its affordances (the agent/terminal analog
of FCC's shared viewer POMs).

Agents and terminals render as panel tabs in a section header
(``PANEL_TAB-agent:<taskId>`` / ``PANEL_TAB-terminal:<wsId>:<n>``), created from the
same section ``+`` add-panel dropdown. This POM consolidates the tab-model affordances
that used to live in ``agent_tab.py`` and the tab half of ``terminal.py``:
rename (double-click or context menu), close (→ delete/close confirmation),
diagnostics copy actions, the ``data-dot-status`` reader, and the close button.

Only the **host** testid moved (``AGENT_TAB`` / ``TERMINAL_TAB`` → ``PANEL_TAB``);
the shared affordance ids (``TAB_CONTEXT_MENU_*``, ``INLINE_RENAME_INPUT``,
``DELETE_CONFIRMATION_*``) are reused unchanged.

The panel-tab context menu in the redesigned shell offers Rename (for multi-instance
panels only) plus the agent's flat diagnostics copy items (rendered by label, with
Radix ``data-disabled`` on items that have nothing to copy). Constructed with the
``sub_section`` whose header hosts the tabs.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection


class PlaywrightPanelTabElement:
    """POM over the panel tabs in one sub-section's header + their affordances."""

    def __init__(self, page: Page, sub_section: str = "center") -> None:
        self._page = page
        self._sub_section = sub_section
        self._section = PlaywrightWorkspaceSection(page, sub_section)

    # ── Tab getters ────────────────────────────────────────────────────────────

    def get_panel_tabs(self) -> Locator:
        """Get every panel tab in this sub-section's header."""
        return self._section.get_panel_tabs()

    def get_panel_tab(self, panel_id: str) -> Locator:
        """Get the panel tab for a specific panel id (e.g. ``agent:<taskId>``)."""
        return self._section.get_panel_tab(panel_id)

    def get_panel_tab_by_name(self, name: str) -> Locator:
        """Get the panel tab(s) whose label contains ``name``."""
        return self.get_panel_tabs().filter(has_text=name)

    def get_active_tab(self) -> Locator:
        """Get the active (selected) panel tab in this sub-section."""
        return self._section.get_active_tab()

    def get_tab_dot_status(self, tab: Locator) -> Locator:
        """Read a tab's status-dot value via its ``data-dot-status`` attribute.

        The CSS-attribute scoping stays inside the POM to honour the integration-test
        css-locator ratchet.
        """
        return tab.locator("[data-dot-status]")

    # ── Close (→ delete/close confirmation) ─────────────────────────────────────

    def get_tab_close_button(self, panel_id: str) -> Locator:
        """Get a panel tab's always-visible close (X) button by panel id."""
        return self._page.get_by_test_id(f"{ElementIDs.PANEL_TAB_CLOSE}-{panel_id}")

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)

    def get_delete_confirmation_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CANCEL)

    def delete_panel_via_close_button(self, panel_id: str) -> None:
        """Click a panel tab's close button and confirm in the delete/close dialog.

        Mirrors today's ``delete_agent_via_close_button`` but keyed by panel id and
        usable for both agent (delete) and terminal (close) confirmations.
        """
        tab = self.get_panel_tab(panel_id)
        tab.click()
        close_button = self.get_tab_close_button(panel_id)
        expect(close_button).to_be_visible()
        close_button.click()
        confirm_button = self.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    # ── Context menu ────────────────────────────────────────────────────────────

    def open_context_menu(self, tab: Locator) -> None:
        """Right-click a tab to open its context menu."""
        tab.click(button="right")

    def get_context_menu_rename_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_context_menu_close_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE)

    def get_context_menu_close_others_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE_OTHERS)

    def get_context_menu_mark_unread_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_MARK_UNREAD)

    def get_diagnostics_item_by_text(self, text: str) -> Locator:
        """Get a flat diagnostics copy item (rendered by label) inside an open menu.

        The redesigned panel-tab context menu renders the agent diagnostics copy
        actions as flat menu items by label (no per-item testid / no submenu), so
        they are matched by their visible text — preferred over brittle row
        selectors per the integration-test guidance.
        """
        return self._page.get_by_role("menuitem", name=text)

    # ── Rename ──────────────────────────────────────────────────────────────────

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def rename_tab_via_context_menu(self, tab: Locator, new_name: str) -> None:
        """Open the context menu, click Rename, and commit a new label."""
        self.open_context_menu(tab)
        rename_item = self.get_context_menu_rename_item()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def dblclick_rename(self, tab: Locator, new_name: str) -> None:
        """Double-click a tab to begin renaming, then commit a new label."""
        tab.dblclick()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()
