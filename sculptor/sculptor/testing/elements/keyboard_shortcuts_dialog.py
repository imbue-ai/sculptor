from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.base import dismiss_with_escape


class PlaywrightKeyboardShortcutsDialogElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Keyboard Shortcuts help dialog."""

    def get_shortcut_row(self, shortcut_id: str) -> Locator:
        """Find a shortcut row by its test ID suffix."""
        return self._locator.get_by_test_id(f"{ElementIDs.HELP_SHORTCUT_ROW}-{shortcut_id}")

    def close(self) -> None:
        """Close the dialog by pressing Escape."""
        dismiss_with_escape(self._locator)
