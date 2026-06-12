from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightChatSearchBarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the in-chat search bar."""

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_SEARCH_INPUT)

    def get_match_counter(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_SEARCH_MATCH_COUNTER)


def get_chat_search_bar(page: Page) -> PlaywrightChatSearchBarElement:
    locator = page.get_by_test_id(ElementIDs.CHAT_SEARCH_BAR)
    return PlaywrightChatSearchBarElement(locator=locator, page=page)
