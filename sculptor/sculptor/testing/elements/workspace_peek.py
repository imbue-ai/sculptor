from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWorkspacePeekElement(PlaywrightIntegrationTestElement):
    def get_banner(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_BANNER)

    def get_header(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_HEADER)

    def get_agent_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_AGENT_ROW)

    def get_expand_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_EXPAND)

    def get_footer(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_PEEK_FOOTER)
