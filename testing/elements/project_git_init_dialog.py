from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightGitInitDialogElement(PlaywrightIntegrationTestElement):
    def get_confirm_button(self):
        return self.get_by_test_id(ElementIDs.PROJECT_GIT_INIT_CONFIRM)

    def get_cancel_button(self):
        return self.get_by_test_id(ElementIDs.PROJECT_GIT_INIT_CANCEL)

    def confirm(self) -> None:
        """Click the confirm button to initialize git."""
        self.get_confirm_button().click()

    def cancel(self) -> None:
        """Click the cancel button to cancel git initialization."""
        self.get_cancel_button().click()

    def handle(self, should_init: bool = True) -> None:
        """
        Handle the git initialization dialog when it appears.

        Args:
            should_init: Whether to initialize git (True) or cancel (False)
        """
        # Wait for dialog to be visible
        expect(self).to_be_visible()

        if should_init:
            self.confirm()
            # Wait for dialog to close
            expect(self).not_to_be_visible()
        else:
            self.cancel()
            # Wait for dialog to close
            expect(self).not_to_be_visible()
