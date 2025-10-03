from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.git_panel_popover import PlaywrightGitPanelPopoverElement
from sculptor.testing.elements.merge_panel import PlaywrightMergePanel


class PlaywrightTaskHeaderElement(PlaywrightIntegrationTestElement):
    def get_sync_button(self) -> Locator:
        """Get the sync button in the task header."""
        return self.get_by_test_id(ElementIDs.SYNC_BUTTON)

    def get_sync_button_tooltip(self) -> Locator:
        """Get the sync button tooltip in the task header."""
        return self._page.get_by_test_id(ElementIDs.SYNC_BUTTON_TOOLTIP)

    def get_mcp_servers_button(self) -> Locator:
        """Get the MCP servers button in the task header."""
        return self.get_by_test_id(ElementIDs.MCP_SERVERS_BUTTON)

    def open_mcp_server_modal(self) -> Locator:
        """Get the MCP server popover element."""
        self.get_mcp_servers_button().click()
        modal = self._page.get_by_test_id(ElementIDs.MCP_SERVERS_MODAL)

        expect(modal).to_be_visible()
        expect(modal).to_have_attribute("data-state", "open")

        return modal

    def get_git_panel_button(self) -> Locator:
        """Get the git panel in the task header."""
        return self.get_by_test_id(ElementIDs.GIT_PANEL_BUTTON)

    def get_git_panel_content(self) -> PlaywrightGitPanelPopoverElement:
        """Get the git panel content in the task header."""
        return PlaywrightGitPanelPopoverElement(self._page.get_by_test_id(ElementIDs.GIT_PANEL_CONTENT), self._page)

    def get_merge_panel_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MERGE_PANEL_BUTTON)

    def open_and_get_merge_panel_content(self) -> PlaywrightMergePanel:
        button = self.get_merge_panel_button()
        button.click()

        panel = self._page.get_by_test_id(ElementIDs.MERGE_PANEL_CONTENT)
        expect(panel).to_be_visible(timeout=10000)
        expect(panel).to_have_attribute("data-state", "open")

        return PlaywrightMergePanel(panel, self._page)
