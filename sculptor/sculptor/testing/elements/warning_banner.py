from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWarningBannerElement(PlaywrightIntegrationTestElement):
    def get_message(self) -> str:
        """Get the warning message text."""
        return self._locator.text_content() or ""

    def get_link(self) -> Locator:
        """Get the link within the banner."""
        return self.get_by_test_id(ElementIDs.WARNING_STATUS_BANNER_LINK)

    def click_link(self) -> None:
        """Click the link in the warning banner."""
        link = self.get_link()
        link.click()
