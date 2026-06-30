from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightExperimentalSettingsElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Experimental Settings section."""

    def enable_always_interrupt(self) -> None:
        """Enable the 'Always interrupt and send' setting.

        Opens the Radix Select dropdown, waits for the "Enabled" option to
        appear, clicks it, and verifies the trigger shows "Enabled".

        This is idempotent: if the setting is already enabled, clicking the
        same option is a no-op but the verification still passes.
        """
        select_trigger = self._page.get_by_test_id(ElementIDs.SETTINGS_ALWAYS_INTERRUPT_SELECT)
        select_trigger.click()

        option = self._page.get_by_test_id(ElementIDs.SETTINGS_ALWAYS_INTERRUPT_OPTION)
        expect(option).to_be_visible()
        option.click()

        # Verify the select now shows "Enabled" (works even if the value
        # was already "true" and onValueChange didn't fire).
        expect(select_trigger).to_contain_text("Enabled")

    def get_review_all_toggle(self) -> Locator:
        """Return the Review All toggle locator."""
        return self._page.get_by_test_id(ElementIDs.SETTINGS_ENABLE_REVIEW_ALL_TOGGLE)

    def enable_review_all(self) -> None:
        """Enable the 'Review All' toggle (idempotent)."""
        toggle = self.get_review_all_toggle()
        expect(toggle).to_be_visible()
        if toggle.get_attribute("data-state") != "checked":
            toggle.click()

    def disable_always_interrupt(self) -> None:
        """Disable the 'Always interrupt and send' setting."""
        select_trigger = self._page.get_by_test_id(ElementIDs.SETTINGS_ALWAYS_INTERRUPT_SELECT)
        select_trigger.click()

        option = self._page.get_by_test_id(ElementIDs.SETTINGS_ALWAYS_INTERRUPT_DISABLED_OPTION)
        expect(option).to_be_visible()
        option.click()

        expect(select_trigger).to_contain_text("Disabled")

    def set_rich_markdown_rendering(self, *, enabled: bool) -> None:
        """Set the rich-markdown-rendering toggle to the desired state (idempotent)."""
        toggle = self._page.get_by_test_id(ElementIDs.SETTINGS_ENABLE_RICH_MARKDOWN_RENDERING_TOGGLE)
        expect(toggle).to_be_visible()
        target_state = "checked" if enabled else "unchecked"
        if toggle.get_attribute("data-state") != target_state:
            toggle.click()
        expect(toggle).to_have_attribute("data-state", target_state)
