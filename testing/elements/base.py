from playwright.sync_api import Locator
from playwright.sync_api import Page


class PlaywrightIntegrationTestElement(Locator):
    """
    Represents an element on the page. This subclasses Locator for tooltips/type inference, but all calls are
    caught by __getattr__ and rerouted the self._locator, which is the real object. Internal locator methods or instance
    vars should never reach the actual Locator class being extended here.
    """

    def __init__(self, locator: Locator, page: Page) -> None:
        # Playwright page object stored for when HTML outside this element need to be accessed (e.g. dropdowns)
        self._page = page
        self._locator = locator

    def __getattr__(self, attr):
        return getattr(self._locator, attr)
