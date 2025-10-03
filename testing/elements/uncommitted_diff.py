from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.file_artifact import PlaywrightFileArtifactElement


class PlaywrightUncommittedDiffElement(PlaywrightIntegrationTestElement):
    def get_file_artifacts(self) -> Locator:
        """Get all file dropdown elements in the uncommitted section."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_FILE)

    def get_nth_file_artifact_element(self, n: int) -> PlaywrightFileArtifactElement:
        """Get the nth file artifact element in the uncommitted section."""
        file_locators = self.get_by_test_id(ElementIDs.ARTIFACT_FILE)
        expect(file_locators.nth(n)).to_be_visible()
        return PlaywrightFileArtifactElement(locator=file_locators.nth(n), page=self._page)
