from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWorkspacePeekElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the workspace peek panel."""

    def get_banner(self) -> Locator:
        """Get the workspace peek banner."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_BANNER)

    def get_header(self) -> Locator:
        """Get the workspace peek header."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_HEADER)

    def get_agent_rows(self) -> Locator:
        """Get the agent rows listed in the workspace peek panel."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_AGENT_ROW)

    def get_expand_button(self) -> Locator:
        """Get the button that expands the workspace peek panel."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_EXPAND)

    def get_footer(self) -> Locator:
        """Get the workspace peek footer."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_FOOTER)
