"""Page Object Model for an empty section / split-half's empty state.

An empty sub-section renders a centered "Add panel" button (which opens the same
add-panel dropdown) plus up to five quick actions: always "New {recent} agent" and
"New terminal", then up to three most-recently-closed single-instance panels. When
the empty pane is a split half it also renders a "Close split" button that merges
the split back into one section.

Constructed with the ``sub_section`` whose empty state is shown ("left" |
"center" | "right" | "bottom", or one suffixed ":secondary").
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page

from sculptor.constants import ElementIDs


class PlaywrightEmptySectionState:
    """POM over one sub-section's empty-state launcher."""

    def __init__(self, page: Page, sub_section: str = "center") -> None:
        self._page = page
        self._sub_section = sub_section

    def get_add_panel_button(self) -> Locator:
        """Get the centered "Add panel" button (opens the add-panel dropdown)."""
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_EMPTY_STATE}-{self._sub_section}")

    def get_quick_action(self, key: str) -> Locator:
        """Get a quick-action row by its action key.

        Keys are "new-agent", "new-terminal", or a static panel id (e.g. "files")
        for a recently-closed panel row. The testid carries this pane's sub-section so
        simultaneously-empty panes (e.g. both halves of a split) stay distinguishable.
        """
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_EMPTY_QUICK_ACTION}-{self._sub_section}-{key}")

    def get_quick_actions(self) -> Locator:
        """Get every quick-action row in this empty state.

        The quick-action rows share one testid suffixed with this pane's sub-section
        and the action key, so they are matched by a ``data-testid`` prefix selector
        scoped to the sub-section. The CSS selector is kept inside the POM to honour
        the integration-test css-locator ratchet.
        """
        return self._page.locator(f'[data-testid^="{ElementIDs.SECTION_EMPTY_QUICK_ACTION}-{self._sub_section}-"]')

    def get_close_split_button(self) -> Locator:
        """Get the "Close split" button (rendered only when this pane is a split half)."""
        return self._page.get_by_test_id(f"{ElementIDs.SPLIT_CLOSE_OPTION}-{self._sub_section}")
