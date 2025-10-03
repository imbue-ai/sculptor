from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightCompactionPanelElement(PlaywrightIntegrationTestElement):
    def get_compaction_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.COMPACTION_BUTTON)
