from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.utils import get_playwright_modifier_key


class PlaywrightAddRepoDialogElement(PlaywrightIntegrationTestElement):
    def add_local_repo(self, path: str) -> None:
        """Select the local source, fill the path, submit, and wait for the dialog to close.

        Ctrl/Cmd+Enter submits regardless of the autocomplete dropdown state,
        avoiding the Escape+Enter race with the debounced directory fetch. Assumes
        the path is a git repo with at least one commit, so no validation dialog
        interrupts the submit.
        """
        self.select_local_source()
        path_input = self.get_path_input()
        path_input.fill(path)
        path_input.press(f"{get_playwright_modifier_key()}+Enter")
        expect(self._locator).to_be_hidden(timeout=15000)

    def select_local_source(self) -> None:
        """Click the "Local" source radio card so the path-input form is shown.

        Local is the dialog's default source, so on a freshly opened dialog
        this click is an idempotent no-op (radio semantics: clicking the
        selected card keeps it selected). Tests still call it to make their
        precondition explicit — and it stays required for flows that switched
        to GitHub, where the Local form is mounted but hidden (`display:none`)
        and Playwright would time out waiting for the path input.
        """
        self.get_source_local_card().click()

    def get_path_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_PATH_INPUT)

    def get_path_autocomplete_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PATH_AUTOCOMPLETE_ITEM)

    def get_submit_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SUBMIT_BUTTON)

    def get_submit_hint(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PATH_AUTOCOMPLETE_SUBMIT_HINT)

    def get_source_github_card(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SOURCE_GITHUB)

    def get_source_local_card(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SOURCE_LOCAL)

    def get_remote_url_toggle(self) -> Locator:
        # The "I'll paste a URL instead" / "Search my repositories instead"
        # button. AddRepoDialog keeps each source's form mounted (display:none
        # on the hidden ones) so it preserves state across radio-card switches.
        # Filter to the visible match so we resolve the toggle inside the
        # currently shown form.
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_REMOTE_URL_TOGGLE.value}"]:visible')

    def get_remote_url_input(self) -> Locator:
        # Mirrors the toggle: the URL TextField lives in the GitHub form, which
        # stays mounted (display:none while another source is selected). Filter
        # to the visible one so we resolve it only while the form is shown.
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_REMOTE_URL_INPUT.value}"]:visible')

    def get_clone_progress_title(self) -> Locator:
        # CloneProgressView replaces the form with a "Cloning owner/repo…"
        # dialog title once the submit fires; the test uses this to confirm
        # the form → clone transition.
        return self._locator.get_by_role("heading", name="Cloning", exact=False)

    def get_clone_progress_link(self) -> Locator:
        """The owner/repo anchor inside the cloning title. Present only when
        deriveWebUrl could resolve a navigable URL (ssh or https inputs)."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_PROGRESS_LINK)

    def get_not_configured_section(self) -> Locator:
        """The "X CLI not configured" panel inside the GitHub form, which stays
        mounted (display:none when another source is selected), so filter to the
        visible one."""
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_NOT_CONFIGURED.value}"]:visible')

    def get_configure_cta_button(self) -> Locator:
        """The footer "Configure {provider}" button that replaces the submit
        button when the active remote provider isn't configured."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CONFIGURE_CTA)

    def get_clone_failed_path(self) -> Locator:
        """The proposed local path inside the clone-failed view's path box.
        Only mounted when localPathSuggestion is set (the 409 path)."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_FAILED_PATH)

    def get_clone_failed_copy_button(self) -> Locator:
        """Clipboard-copy icon button next to the proposed local path."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_FAILED_COPY)

    def get_clone_failed_add_local_button(self) -> Locator:
        """The "Add as local folder" primary CTA in the 409 clone-failed view."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_FAILED_ADD_LOCAL)

    def get_clone_failed_message(self) -> Locator:
        """The error-message text inside the clone-failed view."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_FAILED_MESSAGE)

    def get_clone_failed_close_button(self) -> Locator:
        """The Close button in the clone-failed view footer (always rendered)."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_CLONE_FAILED_CLOSE)

    def get_remote_name_input(self) -> Locator:
        """The Name TextField inside the GitHub RemoteRepoForm, which stays
        mounted via display:none, so filter to the visible input."""
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_REMOTE_NAME_INPUT.value}"]:visible')

    def get_repo_combobox_input(self) -> Locator:
        """The search input inside the active provider's RemoteRepoCombobox.
        Combobox lives inside the per-provider form so filter to visible."""
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_REPO_COMBOBOX_INPUT.value}"]:visible')

    def get_repo_combobox_items(self) -> Locator:
        """All rendered combobox rows in the visible provider's form."""
        return self._locator.locator(f'[data-testid="{ElementIDs.ADD_REPO_REPO_COMBOBOX_ITEM.value}"]:visible')

    def get_repo_combobox_item(self, full_name: str) -> Locator:
        """A specific combobox row by `owner/repo`. The row carries the slug as
        a custom data attribute so the locator doesn't have to rely on
        Radix-injected text positioning."""
        return self._locator.locator(
            f'[data-testid="{ElementIDs.ADD_REPO_REPO_COMBOBOX_ITEM.value}"]'
            f'[data-repo-full-name="{full_name}"]:visible'
        )
