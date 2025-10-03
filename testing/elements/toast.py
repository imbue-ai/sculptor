from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightToastElement(PlaywrightIntegrationTestElement):
    def maybe_close(self):
        if not self.is_visible():
            return
        close_button = self.get_by_test_id(ElementIDs.TOAST_CLOSE_BUTTON)
        close_button.click()
