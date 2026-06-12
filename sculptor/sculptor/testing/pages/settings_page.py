from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.settings_actions import PlaywrightActionsSettingsElement
from sculptor.testing.elements.settings_agent import PlaywrightAgentSettingsElement
from sculptor.testing.elements.settings_claude_cli import PlaywrightClaudeCliSettingsElement
from sculptor.testing.elements.settings_env_vars import PlaywrightEnvVarsSettingsElement
from sculptor.testing.elements.settings_experimental import PlaywrightExperimentalSettingsElement
from sculptor.testing.elements.settings_git import PlaywrightGitSettingsElement
from sculptor.testing.elements.settings_keybindings import PlaywrightKeybindingsSettingsElement
from sculptor.testing.elements.settings_panels import PlaywrightPanelsSettingsElement
from sculptor.testing.elements.settings_pi import PlaywrightPiSettingsElement
from sculptor.testing.elements.settings_privacy import PlaywrightPrivacySettingsElement
from sculptor.testing.elements.settings_repositories import PlaywrightRepositoriesSettingsElement
from sculptor.testing.elements.settings_theme_builder import PlaywrightThemeBuilderSettingsElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightSettingsPage(PlaywrightProjectLayoutPage):
    """Page Object Model for the Settings page."""

    def get_toast(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TOAST)

    def dismiss_toast(self) -> None:
        toast = self.get_toast()
        expect(toast).to_be_visible()
        toast.get_by_test_id(ElementIDs.TOAST_CLOSE_BUTTON).click()
        expect(toast).not_to_be_visible()

    def click_on_dependencies(self) -> PlaywrightClaudeCliSettingsElement:
        """Navigate to Dependencies settings and return the section element."""
        self._get_dependencies_nav().click()
        return PlaywrightClaudeCliSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_general(self) -> PlaywrightIntegrationTestElement:
        """Navigate to General settings and return the section element."""
        self._get_general_nav().click()
        return PlaywrightIntegrationTestElement(locator=self._get_settings_content(), page=self._page)

    def click_on_agent(self) -> PlaywrightAgentSettingsElement:
        """Navigate to Agent settings and return the section element."""
        self._get_agent_nav().click()
        return PlaywrightAgentSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_keybindings(self) -> PlaywrightKeybindingsSettingsElement:
        """Navigate to Keybindings settings and return the section element."""
        self._get_keybindings_nav().click()
        # Return the keybindings settings section scoped to the page
        return PlaywrightKeybindingsSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_panels(self) -> PlaywrightPanelsSettingsElement:
        """Navigate to Panels settings and return the section element."""
        self._get_panels_nav().click()
        return PlaywrightPanelsSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_pi(self) -> PlaywrightPiSettingsElement:
        """Navigate to Pi (experimental) settings and return the section element."""
        self._get_pi_nav().click()
        return PlaywrightPiSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_privacy(self) -> PlaywrightPrivacySettingsElement:
        """Navigate to Privacy settings and return the section element."""
        self._get_privacy_nav().click()
        return PlaywrightPrivacySettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_repositories(self) -> PlaywrightRepositoriesSettingsElement:
        """Navigate to Repositories settings and return the section element."""
        self._get_repositories_nav().click()
        return PlaywrightRepositoriesSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_actions(self) -> PlaywrightActionsSettingsElement:
        """Navigate to Actions settings and return the section element."""
        self._get_actions_nav().click()
        return PlaywrightActionsSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_git(self) -> PlaywrightGitSettingsElement:
        """Navigate to Git settings and return the section element."""
        self._get_git_nav().click()
        return PlaywrightGitSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_env_vars(self) -> PlaywrightEnvVarsSettingsElement:
        """Navigate to Environment Variables settings and return the section element."""
        self._get_env_vars_nav().click()
        return PlaywrightEnvVarsSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_experimental(self) -> PlaywrightExperimentalSettingsElement:
        """Navigate to Experimental settings and return the section element."""
        self._get_experimental_nav().click()
        return PlaywrightExperimentalSettingsElement(locator=self._get_settings_content(), page=self._page)

    def click_on_theme_builder(self) -> PlaywrightThemeBuilderSettingsElement:
        """Navigate to Theme Builder settings and return the section element."""
        self._get_theme_builder_nav().click()
        return PlaywrightThemeBuilderSettingsElement(locator=self._get_settings_content(), page=self._page)

    def _get_settings_content(self) -> Locator:
        """Get the main settings page container."""
        return self.get_by_test_id(ElementIDs.SETTINGS_CONTENT)

    def _get_general_nav(self) -> Locator:
        """Get the General navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_GENERAL)

    def _get_agent_nav(self) -> Locator:
        """Get the Agent navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_AGENT)

    def _get_keybindings_nav(self) -> Locator:
        """Get the Keybindings navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_KEYBINDINGS)

    def _get_panels_nav(self) -> Locator:
        """Get the Panels navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_PANELS)

    def _get_pi_nav(self) -> Locator:
        """Get the Pi (experimental) navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_PI)

    def _get_privacy_nav(self) -> Locator:
        """Get the Privacy navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_PRIVACY)

    def _get_repositories_nav(self) -> Locator:
        """Get the Repositories navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_REPOSITORIES)

    def _get_actions_nav(self) -> Locator:
        """Get the Actions navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_ACTIONS)

    def _get_git_nav(self) -> Locator:
        """Get the Git navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_GIT)

    def _get_env_vars_nav(self) -> Locator:
        """Get the Environment Variables navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_PROJECT_ENV_VARS)

    def _get_experimental_nav(self) -> Locator:
        """Get the Experimental navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_EXPERIMENTAL)

    def _get_dependencies_nav(self) -> Locator:
        """Get the Dependencies navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_DEPENDENCIES)

    def _get_theme_builder_nav(self) -> Locator:
        """Get the Theme Builder navigation item."""
        return self.get_by_test_id(ElementIDs.SETTINGS_NAV_THEME_BUILDER)
