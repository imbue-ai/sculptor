"""UI-refresh shim: the legacy agent-tab-bar API mapped onto the new panel surfaces.

Agents render as panel tabs in the **center** section (``PANEL_TAB-agent:<taskId>``),
created from that section's add-panel ``+`` dropdown. This class keeps the old
``PlaywrightAgentTabBarElement`` surface (so its many importers keep working) while
delegating to the new POMs:

- reads / switch → :class:`PlaywrightWorkspaceSection` (center)
- rename / close / context menu / diagnostics / status dot → :class:`PlaywrightPanelTabElement`
- creation → the add-panel dropdown (``create_agent_panel`` / the agent-type submenu)

Behavioural notes (documented decisions):
- There is no bare "terminal" agent type anymore (Decision B2): create a plain
  terminal via ``create_terminal_panel`` (bottom section) and a registered
  terminal-agent via ``add_agent(agent_type="registered", ...)``. So this shim does
  not expose a terminal agent-type item or a context-menu "Delete" / "Mark unread"
  item — those affordances moved (delete → the tab's close button) or are deferred
  (mark-unread / AGENT-07). Tests that used them are rewritten directly.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection


def _panel_id_of(tab: Locator) -> str:
    """Extract a panel tab's panel id from its ``PANEL_TAB-<panelId>`` testid."""
    testid = tab.get_attribute("data-testid")
    prefix = f"{ElementIDs.PANEL_TAB}-"
    assert testid is not None and testid.startswith(prefix), f"unexpected tab testid: {testid!r}"
    return testid[len(prefix) :]


class PlaywrightAgentTabBarElement:
    """Shim over the center-section panel tabs + add-panel dropdown."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._section = PlaywrightWorkspaceSection(page, "center")
        self._tabs = PlaywrightPanelTabElement(page, sub_section="center")
        self._dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    # ── Tab reads / switch ──────────────────────────────────────────────────────

    def get_agent_tabs(self) -> Locator:
        return self._section.get_panel_tabs()

    def get_agent_tab_by_name(self, name: str) -> Locator:
        return self._tabs.get_panel_tab_by_name(name)

    def get_panel_tab(self, panel_id: str) -> Locator:
        return self._section.get_panel_tab(panel_id)

    def get_active_tab(self) -> Locator:
        return self._section.get_active_tab()

    def get_section(self) -> PlaywrightWorkspaceSection:
        return self._section

    def get_tab_dot_status(self, tab: Locator) -> Locator:
        return self._tabs.get_tab_dot_status(tab)

    # ── Creation (add-panel dropdown) ───────────────────────────────────────────

    def add_agent(self, agent_type: str | None = None) -> None:
        """Create a new agent in center via the add-panel dropdown.

        ``agent_type`` is ``None`` (the pinned "New {recent} agent"), ``"claude"``,
        or ``"pi"``.
        """
        create_agent_panel(self._page, "center", agent_type)

    def get_add_agent_button(self) -> Locator:
        """The center section's add-panel ``+`` button (the dropdown trigger)."""
        return self._section.get_add_panel_button()

    def open_agent_type_menu(self) -> Locator:
        """Open the add-panel dropdown and its agent-type sub-menu; return the sub-menu."""
        self._dropdown.open()
        return self._dropdown.open_agent_type_submenu()

    def get_agent_type_menu(self) -> Locator:
        return self._dropdown.get_agent_type_submenu()

    def get_agent_type_menu_item_claude(self) -> Locator:
        return self._dropdown.get_agent_type_item_claude()

    def get_agent_type_menu_item_pi(self) -> Locator:
        return self._dropdown.get_agent_type_item_pi()

    def get_agent_type_menu_item_registered(self, registration_id: str) -> Locator:
        return self._dropdown.get_agent_type_item_registered(registration_id)

    # ── Rename ──────────────────────────────────────────────────────────────────

    def get_inline_rename_input(self) -> Locator:
        return self._tabs.get_inline_rename_input()

    def rename_tab(self, tab: Locator, new_name: str) -> None:
        self._tabs.rename_tab_via_context_menu(tab, new_name)

    # ── Context menu ────────────────────────────────────────────────────────────

    def open_context_menu(self, tab: Locator) -> None:
        self._tabs.open_context_menu(tab)

    def get_context_menu_rename_item(self) -> Locator:
        return self._tabs.get_context_menu_rename_item()

    # ── Diagnostics copy items (flat items, matched by label) ───────────────────

    def open_diagnostics_submenu(self, tab: Locator) -> None:
        """Open the tab's context menu (the diagnostics items are flat, not a sub-menu)."""
        self._tabs.open_context_menu(tab)

    def get_copy_agent_id_item(self) -> Locator:
        return self._tabs.get_diagnostics_item_by_text("Copy agent id")

    def get_copy_agent_name_item(self) -> Locator:
        return self._tabs.get_diagnostics_item_by_text("Copy agent name")

    def get_copy_session_id_item(self) -> Locator:
        return self._tabs.get_diagnostics_item_by_text("Copy claude session id")

    def get_copy_transcript_path_item(self) -> Locator:
        return self._tabs.get_diagnostics_item_by_text("Copy claude transcript file path")

    def get_copy_sculptor_transcript_item(self) -> Locator:
        return self._tabs.get_diagnostics_item_by_text("Copy Sculptor transcript file path")

    # ── Close / delete (via the tab's close button + confirmation) ──────────────

    def get_tab_close_button(self, tab: Locator) -> Locator:
        """The tab's always-visible close (X) button (scoped under the tab)."""
        return tab.locator(f'[data-testid^="{ElementIDs.PANEL_TAB_CLOSE}-"]')

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._tabs.get_delete_confirmation_dialog()

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._tabs.get_delete_confirmation_confirm_button()

    def delete_agent_via_close_button(self, agent_tab_index: int = 0) -> None:
        """Click an agent tab's close button and confirm the delete."""
        tab = self.get_agent_tabs().nth(agent_tab_index)
        self._tabs.delete_panel_via_close_button(_panel_id_of(tab))
