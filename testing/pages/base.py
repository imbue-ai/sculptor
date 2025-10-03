from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.toast import PlaywrightToastElement


class PlaywrightIntegrationTestPage(Page):
    """
    Represents a page. This subclasses Page for tooltips/type inference, but all calls are
    caught by __getattr__ and rerouted the self._page, which is the real object. Internal page methods or instance
    vars should never reach the actual Page class being extended here.
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    def __getattr__(self, attr):
        return getattr(self._page, attr)

    def get_toast(self) -> PlaywrightToastElement:
        return PlaywrightToastElement(self.get_by_test_id(ElementIDs.TOAST), page=self._page)
