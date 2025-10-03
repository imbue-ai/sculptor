from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightFeedbackDialogElement(PlaywrightIntegrationTestElement):
    def get_submit_button(self) -> Locator:
        """Get the git pull button in the task header."""
        return self.get_by_test_id(ElementIDs.FEEDBACK_DIALOG_SUBMIT_BUTTON)

    def get_cancel_button(self) -> Locator:
        """Get the git commit message input in the task header."""
        return self.get_by_test_id(ElementIDs.FEEDBACK_DIALOG_CANCEL_BUTTON)

    def get_issue_type_dropdown(self) -> Locator:
        """Get the issue type dropdown in the feedback dialog."""
        return self.get_by_test_id(ElementIDs.FEEDBACK_DIALOG_ISSUE_TYPE_DROPDOWN)
