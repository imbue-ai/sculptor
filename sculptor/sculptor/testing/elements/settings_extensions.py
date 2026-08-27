from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightExtensionsSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Extensions settings section.

    Extensions are added by source (a URL or path containing a ``manifest.json``).
    Each source renders a row whose ``data-status`` reflects the load outcome
    (``loading`` -> ``loaded`` | ``error``); error rows also carry a
    ``data-phase`` naming the stage that failed (``manifest``/``validate``/
    ``import``/``activate``/``load``).
    """

    def get_extensions_toggle(self) -> Locator:
        """Return the extensions master switch (the kill switch for the
        whole extension system). It lives at the top of this section rather than in
        Experimental so the section stays reachable to flip the system back on."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_ENABLE_EXTENSIONS_TOGGLE)

    def set_extensions(self, *, enabled: bool) -> None:
        """Set the extensions master switch to the desired state (idempotent)."""
        toggle = self.get_extensions_toggle()
        expect(toggle).to_be_visible()
        target_state = "checked" if enabled else "unchecked"
        if toggle.get_attribute("data-state") != target_state:
            toggle.click()
        expect(toggle).to_have_attribute("data-state", target_state)

    def get_source_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_INPUT)

    def get_add_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_ADD_BUTTON)

    def get_empty_state(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_EMPTY)

    def get_refresh_button(self) -> Locator:
        """The manual 're-scan the extensions directory' control next to Add."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_REFRESH_BUTTON)

    def get_directory_label(self) -> Locator:
        """The code chip in the description showing where drop-in extensions load from.

        Reflects the backend's display-formatted directory (home collapsed to
        ``~``), not a hardcoded path."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_DIRECTORY)

    def refresh(self) -> None:
        """Click the refresh control to re-scan local extensions on demand."""
        button = self.get_refresh_button()
        expect(button).to_be_enabled()
        button.click()

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_ROW)

    def get_source_row(self, source: str) -> Locator:
        """Locate the row for a given source by its ``data-source`` attribute."""
        return self._page.locator(
            f'[data-testid="{ElementIDs.SETTINGS_EXTENSIONS_SOURCE_ROW.value}"][data-source="{source}"]'
        )

    def get_rows_by_kind(self, kind: str) -> Locator:
        """Locate rows by origin: ``builtin`` (bundled), ``local``
        (``~/.sculptor/extensions/``), or ``url`` (user-added). Useful when the
        exact ``data-source`` isn't known up front — a local extension's source is
        an absolute backend URL whose port varies per instance."""
        return self._page.locator(
            f'[data-testid="{ElementIDs.SETTINGS_EXTENSIONS_SOURCE_ROW.value}"][data-kind="{kind}"]'
        )

    def get_rows_by_kind_and_status(self, *, kind: str, status: str) -> Locator:
        """Locate rows by both origin (``kind``) and load ``status`` (e.g.
        ``loaded`` vs ``shadowed``) — used to assert which of two competing
        same-id sources won without knowing their exact ``data-source`` URLs."""
        return self._page.locator(
            f'[data-testid="{ElementIDs.SETTINGS_EXTENSIONS_SOURCE_ROW.value}"][data-kind="{kind}"][data-status="{status}"]'
        )

    def get_remove_button_in(self, row: Locator) -> Locator:
        """The remove (trash) control within a given source row — present only on
        user-removable (``url``) rows."""
        return row.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_REMOVE)

    def get_toggle_in(self, row: Locator) -> Locator:
        """The enable/disable switch within a given source row (use when the row
        was located by kind/status rather than by source)."""
        return row.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_TOGGLE)

    def get_reload_in(self, row: Locator) -> Locator:
        """The reload/retry control within a source row. Present on a loaded row
        and on an errored row, where it re-attempts the failed load in place."""
        return row.get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_RELOAD)

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
        self.get_source_row(source).get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_REMOVE).click()

    def retry(self, source: str) -> None:
        """Click the reload/retry control on a source's row to re-attempt its load."""
        self.get_source_row(source).get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_RELOAD).click()

    def open_source_settings(self, source: str) -> None:
        """Reveal a source's extension-rendered settings component (clicks the gear).

        The settings component is the extension's own React, mounted under the
        extension error boundary, so revealing it exercises the bundle's render
        path — not just whether it loaded. Its content then appears inside the
        source's row (see ``get_source_row``).
        """
        self.get_source_row(source).get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_SETTINGS).click()

    def set_source_text_setting(self, source: str, value: str, *, placeholder: str | None = None) -> None:
        """Open a source's extension-rendered settings and fill a text input.

        The settings component is extension-authored, so its fields carry no host
        testids. A extension whose settings render a single ``<input>`` needs no
        disambiguation; when they render several (e.g. the Linear extension's API
        key beside its template fields), pass the target field's ``placeholder``
        — Playwright's canonical locator for a label-less input. Used e.g. to
        enter the Linear extension's API key, which the extension persists via the
        settings SDK and applies reactively (no reload needed).
        """
        self.open_source_settings(source)
        row = self.get_source_row(source)
        field = row.get_by_placeholder(placeholder) if placeholder is not None else row.locator("input")
        expect(field).to_be_visible()
        field.fill(value)

    def get_toggle(self, source: str) -> Locator:
        """Locate the enable/disable switch on a source's row."""
        return self.get_source_row(source).get_by_test_id(ElementIDs.SETTINGS_EXTENSIONS_SOURCE_TOGGLE)

    def set_enabled(self, source: str, *, enabled: bool) -> None:
        """Flip a source's enable/disable switch to the desired state (idempotent)."""
        toggle = self.get_toggle(source)
        expect(toggle).to_be_visible()
        target_state = "checked" if enabled else "unchecked"
        if toggle.get_attribute("data-state") != target_state:
            toggle.click()
        expect(toggle).to_have_attribute("data-state", target_state)

    def expect_disabled(self, source: str) -> None:
        """Assert a source is on the list but disabled (parked, not loaded)."""
        expect(self.get_source_row(source)).to_have_attribute("data-status", "disabled")

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
