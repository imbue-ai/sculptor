from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightFileArtifactElement(PlaywrightIntegrationTestElement):
    def get_file_dropdown(self) -> Locator:
        """Get file dropdown for file artifact."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_FILE_DROPDOWN)

    def toggle_body(self) -> None:
        """Toggle file body visibility."""
        self.get_file_dropdown().click()

    def get_file_name(self) -> Locator:
        """Get filename for file artifact."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_FILE_NAME)

    def get_file_body(self) -> Locator:
        """Get file body for file artifact."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_FILE_BODY)

    def ensure_body_visible(self) -> None:
        """Ensure file body is visible. Opens it if closed, does nothing if already open."""
        file_body = self.get_file_body()
        if not file_body.is_visible():
            self.toggle_body()
