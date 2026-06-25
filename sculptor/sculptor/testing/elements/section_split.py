"""Page Object Model for a section's split.

A section is split by right-clicking one of its panel tabs and choosing "Create
{direction} split and move panel": the panel moves into the section's SECONDARY
sub-section and the section renders two halves (primary + a resize divider +
secondary). Direction maps to an axis — "bottom" → horizontal (stacked), "right"
→ vertical (side-by-side) — and the per-section allowed axes are: left/right →
horizontal only, bottom → vertical only, center → both. A section holds at most
one split, so the create-split options disappear once a split exists.

Constructed with the SECTION id ("left" | "center" | "right" | "bottom"); the two
halves are reached via ``get_subsection`` ("primary" | "secondary").
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.panel_empty_state import PlaywrightEmptySectionState
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection

# The split's primary half keeps the section id; the secondary half suffixes it.
_HALF_SUFFIX: dict[str, str] = {"primary": "", "secondary": ":secondary"}

# The axis each user-facing direction word splits along, and the axis a per-section
# direction maps to in the panel context menu.
_DIRECTION_AXES = ("horizontal", "vertical")


class PlaywrightSectionSplit:
    """POM over one section's split affordances."""

    def __init__(self, page: Page, section: str) -> None:
        self._page = page
        self._section = section

    def _sub_section_for(self, half: str) -> str:
        return f"{self._section}{_HALF_SUFFIX[half]}"

    def get_subsection(self, half: str) -> PlaywrightWorkspaceSection:
        """Get the section POM for one half of the split ("primary" | "secondary")."""
        return PlaywrightWorkspaceSection(self._page, self._sub_section_for(half))

    def get_split_container(self) -> Locator:
        """Get the split container, which renders only while the section is split."""
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_SPLIT_SUBSECTION}-{self._section}")

    def get_create_option(self, axis: str) -> Locator:
        """Get the "Create {direction} split" context-menu item for an axis.

        The item is portalled by Radix, so it is located page-wide; it is present
        only while a tab's context menu is open and the section has no split yet.
        """
        return self._page.get_by_test_id(f"{ElementIDs.SPLIT_CREATE_OPTION}-{axis}")

    def create_split(self, panel_id: str, direction: str) -> None:
        """Split this section by moving ``panel_id`` into a new secondary half.

        Right-clicks the panel's tab (in whichever half it currently lives) to open
        the context menu, then clicks the "Create {direction} split" option.
        ``direction`` is the axis ("horizontal" → stacked / "vertical" →
        side-by-side). Verifies the panel lands in the secondary half.
        """
        if direction not in _DIRECTION_AXES:
            raise ValueError(f"unsupported split direction: {direction!r}; expected 'horizontal' or 'vertical'")
        primary_tabs = PlaywrightPanelTabElement(self._page, self._sub_section_for("primary"))
        tab = primary_tabs.get_panel_tab(panel_id)
        expect(tab).to_be_visible()
        primary_tabs.open_context_menu(tab)
        option = self.get_create_option(direction)
        expect(option).to_be_visible()
        option.click()
        secondary = PlaywrightWorkspaceSection(self._page, self._sub_section_for("secondary"))
        expect(secondary.get_panel_tab(panel_id)).to_be_visible()

    def close_split_from_empty_state(self, half: str) -> None:
        """Click "Close split" in the empty state of one half, merging the split back.

        Only an EMPTY half shows the close-split button; the caller is responsible
        for emptying the half first (e.g. closing its only panel).
        """
        empty_state = PlaywrightEmptySectionState(self._page, self._sub_section_for(half))
        button = empty_state.get_close_split_button()
        expect(button).to_be_visible()
        button.click()
        expect(self.get_split_container()).to_have_count(0)

    def assert_split_count(self, expected: int) -> None:
        """Assert the section has 0 (no split container) or 1 split container."""
        expect(self.get_split_container()).to_have_count(expected)

    def assert_directions_available(self, expected_axes: tuple[str, ...]) -> None:
        """Assert which "Create split" options the panel context menu offers.

        Opens the first panel tab's context menu, asserts each expected axis option
        is visible and each unexpected axis option is absent, then dismisses the
        menu. Use this BEFORE a split exists (the options vanish once one does).
        """
        primary_tabs = PlaywrightPanelTabElement(self._page, self._sub_section_for("primary"))
        tab = primary_tabs.get_panel_tabs().first
        expect(tab).to_be_visible()
        primary_tabs.open_context_menu(tab)
        for axis in _DIRECTION_AXES:
            option = self.get_create_option(axis)
            if axis in expected_axes:
                expect(option).to_be_visible()
            else:
                expect(option).to_have_count(0)
        # Dismiss the context menu so it does not intercept later interactions.
        self._page.keyboard.press("Escape")
