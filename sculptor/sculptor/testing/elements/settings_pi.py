import re

from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightPiSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Pi (experimental) section in Settings.

    Mirrors ``PlaywrightClaudeCliSettingsElement``: the controls (mode selector,
    install/retry, progress) parallel Claude's.
    """

    def get_mode_selector(self) -> Locator:
        """Get the Binary-Source (MANAGED/CUSTOM) selector."""
        return self.get_by_test_id(ElementIDs.PI_MODE_SELECTOR)

    def get_mode_option_managed(self) -> Locator:
        """Get the Managed option in the selector dropdown."""
        # Radix Select options render in a page-level portal, not inside the
        # section, so they are reached via the page rather than this element.
        return self._page.get_by_test_id(ElementIDs.PI_MODE_OPTION_MANAGED)

    def get_mode_option_custom(self) -> Locator:
        """Get the Custom option in the selector dropdown."""
        return self._page.get_by_test_id(ElementIDs.PI_MODE_OPTION_CUSTOM)

    def get_status(self) -> Locator:
        """Get the status row element."""
        return self.get_by_test_id(ElementIDs.PI_STATUS)

    def get_up_to_date(self) -> Locator:
        """Get the in-range 'Pinned' status text (shown when the binary is installed and in range)."""
        return self.get_by_test_id(ElementIDs.PI_UP_TO_DATE)

    def get_install_button(self) -> Locator:
        """Get the managed Install/Retry button."""
        return self.get_by_test_id(ElementIDs.PI_INSTALL_BUTTON)

    def get_install_progress(self) -> Locator:
        """Get the managed install progress block."""
        return self.get_by_test_id(ElementIDs.PI_INSTALL_PROGRESS)

    def get_binary_path_input(self) -> Locator:
        """Get the CUSTOM-mode binary-path input field."""
        return self.get_by_test_id(ElementIDs.PI_BINARY_PATH_INPUT)

    def get_pinned_version(self) -> Locator:
        """Get the pinned-version display."""
        return self.get_by_test_id(ElementIDs.PI_PINNED_VERSION)

    def get_disabled_banner(self) -> Locator:
        """Get the pi-agent-disabled callout banner."""
        return self.get_by_test_id(ElementIDs.PI_SETTINGS_DISABLED_BANNER)

    def get_install_commands_block(self) -> Locator:
        """Get the CUSTOM-only manual npm install block.

        The block carries no test id; the npm command text is the only place it
        renders, so its text identifies it (and its absence under MANAGED).
        """
        return self.get_by_text(re.compile(r"npm install -g @earendil-works"))

    def get_auth_surface(self) -> Locator:
        """Locator for any sign-in / auth affordance.

        pi authenticates via env-var injection, never an interactive login, so
        the section must never render a sign-in surface. Used only for absence
        assertions.
        """
        return self.get_by_text(re.compile(r"sign in", re.IGNORECASE))
