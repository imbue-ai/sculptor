from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightProjectPathDialogElement(PlaywrightIntegrationTestElement):
    def get_close_button(self) -> Locator:
        """Get the close button in the dialog."""
        return self.get_by_test_id(ElementIDs.PROJECT_PATH_DIALOG_CLOSE_BUTTON)

    def close(self) -> None:
        """Close the dialog."""
        self.get_close_button().click()
