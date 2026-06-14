from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightWelcomeStepElement(PlaywrightIntegrationTestElement):
    """Element representing the email/welcome step of onboarding."""

    def get_full_name_input(self) -> Locator:
        """Get the full name input field."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_FULL_NAME_INPUT)

    def get_email_input(self) -> Locator:
        """Get the email input field."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_EMAIL_INPUT)

    def get_marketing_checkbox(self) -> Locator:
        """Get the marketing opt-in checkbox."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_MARKETING_CHECKBOX)

    def get_telemetry_checkbox(self) -> Locator:
        """Get the telemetry consent checkbox (checked by default)."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_TELEMETRY_CHECKBOX)

    def get_skip_account_link(self) -> Locator:
        """Get the "Continue without an account" link."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_SKIP_ACCOUNT_LINK)

    def get_submit_button(self) -> Locator:
        """Get the email submit button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_EMAIL_SUBMIT)

    def get_error_message(self) -> Locator:
        """Get the inline error message shown when email submission fails."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_EMAIL_ERROR)

    def enter_email(self, email: str) -> None:
        """Enter email in the input field."""
        email_input = self.get_email_input()
        email_input.click()
        email_input.type(email)

    def set_marketing_opt_in(self, opt_in: bool) -> None:
        """Set the marketing opt-in checkbox state."""
        checkbox = self.get_marketing_checkbox()
        if opt_in:
            checkbox.check()
        else:
            checkbox.uncheck()

    def set_telemetry_opt_in(self, opt_in: bool) -> None:
        """Set the telemetry consent checkbox state."""
        checkbox = self.get_telemetry_checkbox()
        if opt_in:
            checkbox.check()
        else:
            checkbox.uncheck()

    def skip_account_setup(self) -> None:
        """Continue without an account via the skip link."""
        self.get_skip_account_link().click()

    def submit(self) -> None:
        """Submit the email form."""
        self.get_submit_button().click()

    def complete_step(self, email: str, opt_in_to_marketing: bool = False) -> None:
        """Complete the entire email step."""
        self.enter_email(email)
        self.set_marketing_opt_in(opt_in_to_marketing)
        self.submit()


class PlaywrightDependencyCardElement:
    """Element for a dependency card, scoped by data-dependency attribute."""

    def __init__(self, page: Locator, dependency_name: str) -> None:
        self._card = page.locator(f'[data-dependency="{dependency_name}"]')

    @property
    def locator(self) -> Locator:
        return self._card

    def get_status(self) -> Locator:
        return self._card.locator('[data-role="status"]')

    def get_install_button(self) -> Locator:
        return self._card.locator('[data-role="install-button"]')

    def get_path(self) -> Locator:
        return self._card.locator('[data-role="path"]')

    def get_version(self) -> Locator:
        return self._card.locator('[data-role="version"]')

    def get_override_link(self) -> Locator:
        return self._card.locator('[data-role="override-link"]')

    def get_override_input(self) -> Locator:
        return self._card.locator('[data-role="override-input"]')

    def get_override_apply(self) -> Locator:
        return self._card.locator('[data-role="override-apply"]')

    def get_override_cancel(self) -> Locator:
        return self._card.locator('[data-role="override-cancel"]')

    def get_override_error(self) -> Locator:
        return self._card.locator('[data-role="override-error"]')

    def get_authenticate_button(self) -> Locator:
        return self._card.locator('[data-role="authenticate-button"]')

    def get_mode_switch(self) -> Locator:
        return self._card.locator('[data-role="mode-switch"]')


class PlaywrightInstallationStepElement(PlaywrightIntegrationTestElement):
    """Element representing the installation step of onboarding."""

    def get_dependency_card(self, dependency_name: str) -> PlaywrightDependencyCardElement:
        """Get a dependency card element by name (e.g. 'claude', 'git')."""
        return PlaywrightDependencyCardElement(self._page, dependency_name)

    def get_claude_card(self) -> PlaywrightDependencyCardElement:
        return self.get_dependency_card("claude")

    def get_git_card(self) -> PlaywrightDependencyCardElement:
        return self.get_dependency_card("git")

    def get_complete_button(self) -> Locator:
        """Get the onboarding complete button."""
        return self.get_by_test_id(ElementIDs.ONBOARDING_COMPLETE_BUTTON)

    def submit(self) -> None:
        """Submit the installation step."""
        self.get_complete_button().click()

    def complete_step(self) -> None:
        """Complete the installation step by clicking Continue."""
        self.submit()


class PlaywrightAddRepoStepElement(PlaywrightIntegrationTestElement):
    """Element representing the add-repo step of onboarding."""

    def get_local_source_card(self) -> Locator:
        """Get the 'Local Folder' source radio card."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SOURCE_LOCAL)

    def get_path_input(self) -> Locator:
        """Get the repo path input field."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_PATH_INPUT)

    def get_submit_button(self) -> Locator:
        """Get the 'Add' submit button."""
        return self._page.get_by_test_id(ElementIDs.ADD_REPO_SUBMIT_BUTTON)

    def select_local_source(self) -> None:
        """Select the Local Folder source. Required before entering a path since
        the step defaults to GitHub (the path input is hidden in remote modes).
        """
        self.get_local_source_card().click()

    def enter_path(self, path: str) -> None:
        """Enter a repo path in the input field."""
        path_input = self.get_path_input()
        path_input.click()
        path_input.fill(path)

    def submit(self) -> None:
        """Submit the path by pressing Enter."""
        self.get_path_input().press("Enter")

    def complete_step(self, repo_path: str) -> None:
        """Complete the add-repo step by entering a local path and submitting."""
        self.select_local_source()
        self.enter_path(repo_path)
        self.submit()
