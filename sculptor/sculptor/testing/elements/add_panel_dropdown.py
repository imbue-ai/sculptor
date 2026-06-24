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

    def get_new_agent_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_AGENT)

    def get_agent_type_submenu(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_AGENT_TYPE_SUBMENU)

    def get_new_terminal_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_TERMINAL)

    def get_panel_option(self, panel_id: str) -> Locator:
        """Get a single-instance panel option row by its registry id (e.g. ``files``)."""
        return self._page.get_by_test_id(f"{ElementIDs.ADD_PANEL_PANEL_OPTION}-{panel_id}")

    def open(self) -> None:
        """Open the dropdown by clicking this sub-section's header `+`."""
        add_button = PlaywrightWorkspaceSection(self._page, self._sub_section).get_add_panel_button()
        expect(add_button).to_be_visible()
        add_button.click()
        expect(self.get_content()).to_be_visible()

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
