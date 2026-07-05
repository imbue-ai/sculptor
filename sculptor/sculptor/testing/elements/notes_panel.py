"""Page Object Model for the Notes panel."""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightNotesPanelElement(PlaywrightIntegrationTestElement):
    """POM for the Notes side panel.

    Wraps the panel root locator and exposes a typed accessor for the TipTap
    editor inside the panel.
    """

    def get_editor(self) -> Locator:
        return self.get_by_test_id(ElementIDs.NOTES_PANEL_EDITOR)

    def open(self) -> None:
        """Reveal the Notes panel (a registered panel) via the add-panel dropdown."""
        if not self._locator.is_visible():
            open_panel(self._page, "notes", "right")
        expect(self._locator).to_be_visible()


def get_notes_panel(page: Page) -> PlaywrightNotesPanelElement:
    """Get the Notes panel element from the page."""
    locator = page.get_by_test_id(ElementIDs.NOTES_PANEL)
    return PlaywrightNotesPanelElement(locator=locator, page=page)
