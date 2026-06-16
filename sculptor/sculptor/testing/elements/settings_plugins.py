from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightPluginsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Plugins settings section.

    Plugins are added by source (a URL or path containing a ``manifest.json``).
    Each source renders a row whose ``data-status`` reflects the load outcome
    (``loading`` -> ``loaded`` | ``error``); error rows also carry a
    ``data-phase`` naming the stage that failed (``manifest``/``validate``/
    ``import``/``activate``/``load``).
    """

    def get_source_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PLUGINS_SOURCE_INPUT)

    def get_add_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PLUGINS_ADD_BUTTON)

    def get_empty_state(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PLUGINS_EMPTY)

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_PLUGINS_SOURCE_ROW)

    def get_source_row(self, source: str) -> Locator:
        """Locate the row for a given source by its ``data-source`` attribute."""
        return self._page.locator(
            f'[data-testid="{ElementIDs.SETTINGS_PLUGINS_SOURCE_ROW.value}"][data-source="{source}"]'
        )

    def add_source(self, source: str) -> None:
        """Type a source into the input, click Add, and wait for its row to appear.

        The add resolves whether the load succeeds or fails (a failed load
        settles the row into an error state rather than throwing), so the input
        clears either way; we wait on that as the sync point before returning.
        """
        self.get_source_input().fill(source)
        add_button = self.get_add_button()
        expect(add_button).to_be_enabled()
        add_button.click()
        expect(self.get_source_input()).to_have_value("")
        expect(self.get_source_row(source)).to_have_count(1)

    def remove_source(self, source: str) -> None:
        """Click the remove (trash) button on a source's row."""
        self.get_source_row(source).get_by_test_id(ElementIDs.SETTINGS_PLUGINS_SOURCE_REMOVE).click()

    def expect_loaded(self, source: str, *, name: str | None = None, version: str | None = None) -> None:
        """Assert a source finished loading (optionally showing name/version)."""
        row = self.get_source_row(source)
        expect(row).to_have_attribute("data-status", "loaded")
        if name is not None:
            expect(row).to_contain_text(name)
        if version is not None:
            expect(row).to_contain_text(f"v{version}")

    def expect_failed(self, source: str, *, phase: str) -> None:
        """Assert a source settled into an error state at the given load phase."""
        row = self.get_source_row(source)
        expect(row).to_have_attribute("data-status", "error")
        expect(row).to_have_attribute("data-phase", phase)
