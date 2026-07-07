from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightCommandPaletteElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Command Palette (Cmd+K)."""

    def get_input(self) -> Locator:
        """Get the search input element."""
        return self.get_by_test_id(ElementIDs.COMMAND_PALETTE_INPUT)

    def type_query(self, text: str) -> None:
        """Type a search query into the palette input. Replaces any existing text."""
        self.get_input().fill(text)

    def get_items(self) -> Locator:
        """All visible command rows."""
        return self._page.get_by_test_id(ElementIDs.COMMAND_PALETTE_ITEM)

    def get_item_by_command_id(self, command_id: str) -> Locator:
        """Locate a row by its registered command id.

        Keyed on ``data-command-id`` alone, which every row carries — including
        the few commands that override the shared ``COMMAND_PALETTE_ITEM`` test
        id with a dedicated one (e.g. ``view.reset_layout``).
        """
        # The POM is exempt from the integration-test css-locator ratchet, but
        # the test files that consume it are not — keep all CSS selector usage
        # within this module.
        return self._page.locator(f'[data-command-id="{command_id}"]')

    def get_group_by_id(self, group_id: str) -> Locator:
        """Locate a command group by its registered group id (e.g. 'workspaces')."""
        return self._page.locator(f'[data-testid="{ElementIDs.COMMAND_PALETTE_GROUP}"][data-group-id="{group_id}"]')

    def get_items_in_group(self, group_id: str) -> Locator:
        """All command rows scoped to a specific group (e.g. 'workspaces')."""
        # Scope a CSS descendant selector under the group so callers can count
        # only the items rendered inside that group's <Command.Group>. Kept in
        # the POM to honour the integration-test css-locator ratchet.
        return self.get_group_by_id(group_id).locator(f'[data-testid="{ElementIDs.COMMAND_PALETTE_ITEM}"]')

    def get_item_in_group_by_command_id(self, group_id: str, command_id: str) -> Locator:
        """Locate a specific command row inside a specific group."""
        return self.get_group_by_id(group_id).locator(
            f'[data-testid="{ElementIDs.COMMAND_PALETTE_ITEM}"][data-command-id="{command_id}"]'
        )

    def get_breadcrumb(self) -> Locator:
        """Sub-page breadcrumb (only visible when on a sub-page)."""
        return self._page.get_by_test_id(ElementIDs.COMMAND_PALETTE_PAGE_BREADCRUMB)

    def get_list(self) -> Locator:
        """The scrollable list container."""
        return self._page.get_by_test_id(ElementIDs.COMMAND_PALETTE_LIST)

    def get_empty_state(self) -> Locator:
        """The 'no matches' empty state element."""
        return self._page.get_by_test_id(ElementIDs.COMMAND_PALETTE_EMPTY)

    def press_arrow_down(self) -> None:
        self.get_input().press("ArrowDown")

    def press_arrow_up(self) -> None:
        self.get_input().press("ArrowUp")

    def press_enter(self) -> None:
        self.get_input().press("Enter")

    def press_backspace(self) -> None:
        self.get_input().press("Backspace")

    def clear_search(self) -> None:
        """Clear the search box.

        The palette uses a two-stage Escape: with text in the input, the first
        Escape clears it (Radix's close is preventDefault'd), so a single Escape
        would not close the dialog. Call this before ``dismiss_with_escape``
        when a test has typed a query, so one Escape closes the palette.
        """
        self.get_input().fill("")

    def select_by_command_id(self, command_id: str) -> None:
        """Click a specific command row by its registered id."""
        self.get_item_by_command_id(command_id).click()
