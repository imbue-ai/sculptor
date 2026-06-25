from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightReviewAllPanelElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the Review All panel.

    The Review All panel renders the combined multi-file diff with its own scope
    picker (All / Uncommitted). Both the Changes panel and the Review All panel
    render a ``DIFF_SCOPE_PICKER``, so this POM is scoped to the Review All
    panel's root (``REVIEW_ALL_PANEL``) to disambiguate the two pickers.
    """

    def get_scope_picker(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_PICKER)

    def get_scope_all(self) -> Locator:
        """The "All" (vs target branch) option of this panel's scope picker."""
        return self.get_by_test_id(ElementIDs.DIFF_SCOPE_ALL)

    def get_file_sections(self) -> Locator:
        """The combined-diff per-file section headers."""
        return self.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)

    def get_unified_diff_views(self) -> Locator:
        """The unified diff views — one per expanded file section."""
        return self.get_by_test_id(ElementIDs.DIFF_VIEW_UNIFIED)
