from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.search_modal import PlaywrightSearchModalElement
from sculptor.testing.elements.sidebar import PlaywrightSidebarElement
from sculptor.testing.elements.task_list import PlaywrightTaskListElement
from sculptor.testing.elements.task_modal import PlaywrightTaskModalElement
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage


class PlaywrightProjectLayoutPage(PlaywrightIntegrationTestPage):
    """Page object for the ProjectLayout that contains the sidebar and main content."""

    def get_sidebar(self) -> PlaywrightSidebarElement:
        """Get the sidebar element."""
        sidebar = self.get_by_test_id(ElementIDs.SIDEBAR)
        return PlaywrightSidebarElement(locator=sidebar, page=self._page)

    def get_sidebar_toggle_button(self) -> Locator:
        """Get the sidebar toggle button (located in the header/main content area)."""
        return self.get_by_test_id(ElementIDs.TOGGLE_SIDEBAR_BUTTON)

    def is_sidebar_visible(self) -> bool:
        """Check if the sidebar is currently visible."""
        toggle_button = self.get_sidebar_toggle_button()
        return toggle_button.get_attribute("data-state") == "open"

    def ensure_sidebar_is_open(self) -> PlaywrightSidebarElement:
        """Ensure the sidebar is open, opening it if necessary. Returns the sidebar element."""
        if not self.is_sidebar_visible():
            self.get_sidebar_toggle_button().click()
            # Wait for sidebar to become visible
        sidebar = self.get_sidebar()
        expect(sidebar).to_be_visible()
        return sidebar

    def ensure_sidebar_is_closed(self) -> None:
        """Ensure the sidebar is closed, closing it if necessary."""
        if self.is_sidebar_visible():
            self.get_sidebar_toggle_button().click()
            # Wait for sidebar to become hidden
            sidebar = self.get_sidebar()
            expect(sidebar).not_to_be_visible()

    def get_task_list(self) -> PlaywrightTaskListElement:
        """Get the task list from the sidebar. Ensures sidebar is open first."""
        self.ensure_sidebar_is_open()
        return self.get_sidebar().get_task_list()

    def toggle_sidebar(self) -> None:
        """Toggle the sidebar visibility."""
        self.get_sidebar_toggle_button().click()

    def get_search_modal(self) -> PlaywrightSearchModalElement:
        """Get the search modal element if it exists."""
        search_modal = self.get_by_test_id(ElementIDs.SEARCH_MODAL)
        return PlaywrightSearchModalElement(locator=search_modal, page=self._page)

    def ensure_search_modal_is_open(self) -> PlaywrightSearchModalElement:
        """Get the search modal element."""
        search_modal = self.get_search_modal()
        if search_modal.is_visible():
            return PlaywrightSearchModalElement(locator=search_modal, page=self._page)
        # If not visible, open it via the sidebar button
        sidebar = self.ensure_sidebar_is_open()
        sidebar.get_by_test_id(ElementIDs.SEARCH_MODAL.SEARCH_MODAL_OPEN_BUTTON).click()
        return self.get_search_modal()

    def open_search_modal_with_keyboard(self) -> PlaywrightSearchModalElement:
        """Open the search modal using keyboard shortcut (Cmd+P / Ctrl+P)."""
        # Press the keyboard shortcut
        self._page.keyboard.press("Meta+p")
        # Wait for modal to be visible
        search_modal = self.ensure_search_modal_is_open()
        expect(search_modal).to_be_visible()
        return search_modal

    def press_keyboard_shortcut(self, shortcut: str) -> None:
        self._page.keyboard.press(shortcut)

    def get_task_modal(self) -> PlaywrightTaskModalElement:
        return PlaywrightTaskModalElement(self.get_by_test_id(ElementIDs.TASK_MODAL), page=self._page)
