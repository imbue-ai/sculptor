from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightPlanArtifactElement(PlaywrightIntegrationTestElement):
    def get_plan_items(self) -> Locator:
        """Get all plan item locators."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_PLAN_ITEM)
