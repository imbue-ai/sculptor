from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.utils import get_playwright_modifier_key

_REMOVE_BUTTON_NAME = "Remove repo & agents"


class PlaywrightRepositoriesSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Repositories Settings section."""

    def add_repo(self, path: str) -> None:
        """Add a repository via the Settings > Repositories UI dialog.

        Clicks the "Add repository" button, fills in the path, submits,
        and waits for the dialog to close.
        """
        self._page.get_by_test_id(ElementIDs.SETTINGS_ADD_REPO_BUTTON).click()

        dialog = self._page.get_by_test_id(ElementIDs.ADD_REPO_DIALOG)
        expect(dialog).to_be_visible()

        # Local is the dialog's default source; select it explicitly anyway
        # (an idempotent radio click) so the path input's visibility doesn't
        # silently depend on the default.
        self._page.get_by_test_id(ElementIDs.ADD_REPO_SOURCE_LOCAL).click()

        path_input = self._page.get_by_test_id(ElementIDs.ADD_REPO_PATH_INPUT)
        path_input.fill(path)
        # Use Ctrl/Cmd+Enter to submit — PathAutocomplete handles this as
        # submit-regardless-of-dropdown, avoiding the Escape+Enter dance that
        # raced with the debounced fetchDirectories re-render on slow CI.
        path_input.press(f"{get_playwright_modifier_key()}+Enter")

        expect(dialog).to_be_hidden(timeout=15000)

    def expand_repo_config(self, repo_name: str | None = None) -> None:
        """Expand the per-repo Configure section so its inputs are interactable.

        Per-repo settings (workspace setup command, branch-naming pattern) are
        collapsed by default and only render once Configure is clicked. Tests
        that interact with those inputs must call this first.

        When *repo_name* is None, expands the first repo row — convenient for
        tests that only have a single repo.
        """
        if repo_name is None:
            toggle = self._page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW_CONFIG_TOGGLE).first
        else:
            row = self._get_repo_row(repo_name).first
            toggle = row.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW_CONFIG_TOGGLE)
        expect(toggle).to_be_visible()
        # If already expanded (link text == "Collapse"), avoid re-clicking and re-collapsing.
        if toggle.text_content() != "Collapse":
            toggle.click()

    def remove_repo(self, repo_name: str, path_contains: str | None = None) -> None:
        """Remove a repo via the Settings > Repositories UI.

        Finds the repo row by name (and optionally path substring),
        clicks "Remove repo & agents", confirms in the dialog, and
        waits for the row to disappear.
        """
        row = self._get_repo_row(repo_name, path_contains=path_contains)
        expect(row).to_be_visible()

        row.get_by_role("button", name=_REMOVE_BUTTON_NAME).click()

        # The confirmation dialog appears as a page-level overlay
        dialog = self._page.get_by_role("dialog")
        confirm_button = dialog.get_by_role("button", name=_REMOVE_BUTTON_NAME)
        expect(confirm_button).to_be_visible()
        confirm_button.click()

        # After confirming, the frontend deletes the repo and stays on the
        # settings page.  Wait for the row to disappear.
        expect(row).to_be_hidden()

    def get_first_repo_remove_button(self) -> Locator:
        """Get the remove button for the first repository row."""
        row = self._page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW).first
        return row.get_by_role("button", name=_REMOVE_BUTTON_NAME)

    def remove_first_repo(self) -> None:
        """Remove the first repository in the list."""
        row = self._page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW).first
        expect(row).to_be_visible()
        row.get_by_role("button", name=_REMOVE_BUTTON_NAME).click()
        dialog = self._page.get_by_role("dialog")
        confirm_button = dialog.get_by_role("button", name=_REMOVE_BUTTON_NAME)
        expect(confirm_button).to_be_visible()
        confirm_button.click()
        expect(row).to_be_hidden()

    def get_add_repo_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_ADD_REPO_BUTTON)

    def open_add_repo_dialog(self) -> PlaywrightAddRepoDialogElement:
        self.get_add_repo_button().click()
        dialog_locator = self._page.get_by_test_id(ElementIDs.ADD_REPO_DIALOG)
        expect(dialog_locator).to_be_visible()
        return PlaywrightAddRepoDialogElement(locator=dialog_locator, page=self._page)

    def get_repo_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW)

    def get_setup_command_input(self) -> Locator:
        """Get the workspace setup command textarea for the first (expanded) repo."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_WORKSPACE_SETUP_COMMAND_INPUT).first

    def set_setup_command(self, command: str) -> None:
        """Fill the setup command textarea, blur to trigger the save, and — when
        the value actually changes — wait for the save request to complete before
        returning.

        Blur fires a ``PUT /api/v1/projects/{id}/workspace_setup_command`` only
        when the trimmed value differs from what is currently shown (the saved
        value, or the default while tracking it). When it does change, we wait for
        that response so callers can immediately re-navigate or re-read the
        persisted value without racing the in-flight save — a fixed
        ``wait_for_timeout`` could not guarantee the round-trip had landed.

        When the value is unchanged no request is sent, so we must NOT wait
        (``expect_response`` would hang until timeout). This matters on shared
        instances, where an earlier test may have already saved the same value.
        """
        setup_input = self.get_setup_command_input()
        expect(setup_input).to_be_visible()
        current_value = setup_input.input_value()
        setup_input.fill(command)
        if command.strip() == current_value.strip():
            # No change → blur triggers no save request; nothing to wait for.
            setup_input.blur()
            return
        with self._page.expect_response(
            lambda response: "workspace_setup_command" in response.url and response.request.method == "PUT"
        ):
            setup_input.blur()

    def _get_repo_row(self, repo_name: str, path_contains: str | None = None) -> Locator:
        """Find a repo row containing the given name and optional path substring."""
        rows = self._page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW).filter(has_text=repo_name)

        if path_contains is not None:
            rows = rows.filter(has_text=path_contains)

        return rows
