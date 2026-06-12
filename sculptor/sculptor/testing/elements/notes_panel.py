"""Page Object Model for the Notes panel."""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightNotesPanelElement(PlaywrightIntegrationTestElement):
    """POM for the Notes side panel.

    Wraps the panel root locator and exposes typed accessors for the
    sidebar icon and the TipTap editor inside the panel.
    """

    def get_icon(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_NOTES)

    def get_editor(self) -> Locator:
        return self.get_by_test_id(ElementIDs.NOTES_PANEL_EDITOR)

    def open(self) -> None:
        """Reveal and activate the Notes panel (idempotent).

        The sidebar icon's onClick toggles the panel, so blindly clicking
        when the panel is already visible would close it.
        """
        icon = self.get_icon()
        expect(icon).to_be_visible()
        if not self._locator.is_visible():
            icon.click()


def get_notes_panel(page: Page) -> PlaywrightNotesPanelElement:
    """Get the Notes panel element from the page."""
    locator = page.get_by_test_id(ElementIDs.NOTES_PANEL)
    return PlaywrightNotesPanelElement(locator=locator, page=page)
