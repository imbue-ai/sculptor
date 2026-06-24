from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection


class PlaywrightAddPanelDropdownElement:
    """Page Object Model for the section `+` add-panel dropdown (PANEL-01..06).

    The dropdown is opened by a section's header `+` (or an empty-section add
    button) and is scoped to the sub-section it was opened from: its content
    testid is ``f"{ADD_PANEL_DROPDOWN}-{subSection}"``, and the "New terminal" /
    static-panel options open into THAT sub-section (a new agent always lands in
    center). Items render in a Radix portal, so they are located page-wide.

    Carries the add affordances consolidated out of ``agent_tab.py``
    (recent-agent + agent-type sub-menu, with the Radix-teardown retry) and
    ``terminal.py`` (new-terminal), plus the single-instance panel options.

    Constructed with the ``sub_section`` whose `+` opens it so the content root
    resolves uniquely even when two sub-sections both have an open dropdown id in
    the DOM.
    """

    def __init__(self, page: Page, sub_section: str = "center") -> None:
        self._page = page
        self._sub_section = sub_section

    def get_content(self) -> Locator:
        """Get the open dropdown's content root for this sub-section."""
        return self._page.get_by_test_id(f"{ElementIDs.ADD_PANEL_DROPDOWN}-{self._sub_section}")

    def get_add_panel_button(self) -> Locator:
        """Get this sub-section's header `+` button (the dropdown trigger)."""
        return PlaywrightWorkspaceSection(self._page, self._sub_section).get_add_panel_button()

    # ── New agent (recent type) ─────────────────────────────────────────────────

    def get_new_agent_item(self) -> Locator:
        """The pinned "New {recent} agent" row (creates the recently-used type)."""
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_AGENT)

    # ── Agent-type sub-menu ─────────────────────────────────────────────────────

    def get_agent_type_submenu_trigger(self) -> Locator:
        """The "New agent of type…" sub-menu trigger."""
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_AGENT_TYPE_SUBMENU)

    def get_agent_type_submenu(self) -> Locator:
        """The open agent-type sub-menu content."""
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU)

    def get_agent_type_item_claude(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_CLAUDE)

    def get_agent_type_item_pi(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_PI)

    def get_agent_type_item_registered(self, registration_id: str) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_REGISTERED).and_(
            self._page.locator(f'[data-registration-id="{registration_id}"]')
        )

    def open_agent_type_submenu(self) -> Locator:
        """Hover the agent-type sub-menu trigger and return the open sub-menu.

        Retries the hover: a hover landing while Radix is still tearing down a
        just-dismissed menu can be swallowed (or never open the sub-content), and
        ``expect`` alone cannot recover from a lost hover. (Salvaged from
        ``agent_tab.open_agent_type_menu``'s Radix-teardown retry.)
        """
        submenu = self.get_agent_type_submenu()
        trigger = self.get_agent_type_submenu_trigger()
        for _attempt in range(3):
            expect(trigger).to_be_visible()
            trigger.hover()
            try:
                expect(submenu).to_be_visible(timeout=3_000)
                return submenu
            except AssertionError:
                continue
        expect(submenu).to_be_visible()
        return submenu

    # ── New terminal ────────────────────────────────────────────────────────────

    def get_new_terminal_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_TERMINAL)

    # ── Single-instance panel options ───────────────────────────────────────────

    def get_panel_option(self, panel_id: str) -> Locator:
        """Get a single-instance panel option row by its registry id (e.g. ``files``)."""
        return self._page.get_by_test_id(f"{ElementIDs.ADD_PANEL_PANEL_OPTION}-{panel_id}")

    # ── Open / select ───────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the dropdown by clicking this sub-section's header `+`.

        Idempotent and retried: a Radix trigger toggles, and a click landing in the
        brief settle window right after a previous close can be swallowed, so gate on
        the trigger's ``data-state`` and retry until the dropdown content is visible.
        """
        add_button = self.get_add_panel_button()
        expect(add_button).to_be_visible()
        content = self.get_content()
        for _attempt in range(5):
            if add_button.get_attribute("data-state") == "open":
                expect(content).to_be_visible()
                return
            add_button.click()
            try:
                expect(content).to_be_visible(timeout=2_000)
                return
            except AssertionError:
                self._page.wait_for_timeout(250)
        expect(content).to_be_visible()

    def select_panel(self, panel_id: str) -> None:
        """Click a single-instance panel option, opening it into this sub-section."""
        option = self.get_panel_option(panel_id)
        expect(option).to_be_visible()
        option.click()


def open_panel(page: Page, panel_id: str, sub_section: str = "center") -> Locator:
    """Open a single-instance panel via the add-panel dropdown and return its section root.

    Brings a panel (e.g. ``files`` / ``changes`` / ``commits``) on screen the way
    a user does — clicking the section `+`, then the panel option — instead of
    seeding layout / localStorage state. Returns the owning section's root locator
    so callers can construct the panel's POM scoped to it (the Files / Changes /
    Commits list and viewer are siblings under the section).
    """
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section)
    dropdown.open()
    dropdown.select_panel(panel_id)
    section = PlaywrightWorkspaceSection(page, sub_section)
    section_root = section.get_section()
    expect(section_root).to_be_visible()
    return section_root


def create_agent_panel(page: Page, section: str = "center", agent_type: str | None = None) -> None:
    """Create a new agent via the section `+` add-panel dropdown.

    New agents ALWAYS land in the center section (PANEL-06), regardless of the
    ``section`` the dropdown was opened from. ``agent_type`` picks a specific type
    from the agent-type sub-menu (``"claude"`` / ``"pi"``); ``None`` uses the pinned
    "New {recent} agent" row.
    """
    dropdown = PlaywrightAddPanelDropdownElement(page, section)
    dropdown.open()
    if agent_type is None:
        item = dropdown.get_new_agent_item()
        expect(item).to_be_visible()
        item.click()
        return
    dropdown.open_agent_type_submenu()
    if agent_type == "claude":
        item = dropdown.get_agent_type_item_claude()
    elif agent_type == "pi":
        item = dropdown.get_agent_type_item_pi()
    else:
        raise ValueError(f"unsupported agent_type: {agent_type!r}; expected None, 'claude', or 'pi'")
    expect(item).to_be_visible()
    item.click()


def create_terminal_panel(page: Page, section: str = "bottom") -> None:
    """Create a new terminal panel via the section `+` add-panel dropdown.

    The terminal lands in the requesting ``section`` (its sub-section). A collapsed
    section renders no header `+`, so the section is expanded first via the workspace
    header section toggle (idempotent).
    """
    PlaywrightWorkspaceSection(page, section).expand_section()
    dropdown = PlaywrightAddPanelDropdownElement(page, section)
    dropdown.open()
    item = dropdown.get_new_terminal_item()
    expect(item).to_be_visible()
    item.click()
