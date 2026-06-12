from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.pages.base import PlaywrightIntegrationTestPage


class PlaywrightErrorPage(PlaywrightIntegrationTestPage):
    """Page Object Model for the backend error page."""

    def get_backend_error_page(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BACKEND_ERROR_PAGE)
