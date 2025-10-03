from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightFeedbackButtonsElement(PlaywrightIntegrationTestElement):
    def get_thumbs_up_button(self) -> Locator:
        """Get the git pull button in the task header."""
        return self.get_by_test_id(ElementIDs.THUMBS_UP_BUTTON)

    def get_thumbs_down_button(self) -> Locator:
        """Get the git commit message input in the task header."""
        return self.get_by_test_id(ElementIDs.THUMBS_DOWN_BUTTON)

    def get_fork_button(self) -> Locator:
        """Get the fork button to fork a task from a message."""
        return self.get_by_test_id(ElementIDs.FORK_BUTTON)
