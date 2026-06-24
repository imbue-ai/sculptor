from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs

# The four sections of the workspace grid. A sub-section id is either a section id
# (the unsplit "primary" half) or a section id suffixed with ":secondary" (e.g.
# "left:secondary") — the flat sub-section keyspace from state_design.md.
_SECTION_ROOT_TEST_IDS: dict[str, ElementIDs] = {
    "left": ElementIDs.SECTION_LEFT,
    "center": ElementIDs.SECTION_CENTER,
    "right": ElementIDs.SECTION_RIGHT,
    "bottom": ElementIDs.SECTION_BOTTOM,
}

# The workspace-header toggle that expands/collapses each non-center section. Center
# is always expanded, so it has no toggle.
_SECTION_TOGGLE_TEST_IDS: dict[str, ElementIDs] = {
    "left": ElementIDs.HEADER_SECTION_TOGGLE_LEFT,
    "right": ElementIDs.HEADER_SECTION_TOGGLE_RIGHT,
    "bottom": ElementIDs.HEADER_SECTION_TOGGLE_BOTTOM,
}


def _section_of(sub_section: str) -> str:
    """Return the section id ("left"/"center"/"right"/"bottom") for a sub-section.

    The primary half's sub-section id IS the section id; a split's secondary half
    suffixes it with ":secondary".
    """
    return sub_section.split(":", 1)[0]


class PlaywrightWorkspaceSection:
    """Page Object Model for a single workspace section / sub-section.

    Constructed with a ``sub_section`` id from the flat sub-section keyspace
    ("left" | "center" | "right" | "bottom", or one suffixed with ":secondary").
    The primary and secondary halves run through the same methods.

    The section ROOT (``SECTION_LEFT`` etc.) is keyed by the section id only, but
    the header, panel tabs, add-panel "+", and maximize toggle are suffixed with
    the sub-section id (e.g. ``f"{SECTION_HEADER}-left:secondary"``).

    This is the basic accessor POM. Splits, the empty state, and the full
    ``PanelTab`` POM land in later tasks.
    """

    def __init__(self, page: Page, sub_section: str) -> None:
        self._page = page
        self._sub_section = sub_section

    def get_section(self) -> Locator:
        """Get the section root container (keyed by section id, not sub-section)."""
        return self._page.get_by_test_id(_SECTION_ROOT_TEST_IDS[_section_of(self._sub_section)])

    def get_header(self) -> Locator:
        """Get this sub-section's header (tab strip + add + maximize)."""
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_HEADER}-{self._sub_section}")

    def get_panel_tabs(self) -> Locator:
        """Get every panel tab in this sub-section's header.

        Panel-tab testids are suffixed with the panel id (e.g.
        ``f"{PANEL_TAB}-agent:<taskId>"``), so they are matched by a
        ``data-testid`` prefix selector scoped under this sub-section's header.
        The CSS selector is kept inside the POM to honour the integration-test
        css-locator ratchet.
        """
        return self.get_header().locator(f'[data-testid^="{ElementIDs.PANEL_TAB}-"]')

    def get_panel_tab(self, panel_id: str) -> Locator:
        """Get the panel tab for a specific panel id (e.g. ``agent:<taskId>``)."""
        return self.get_header().get_by_test_id(f"{ElementIDs.PANEL_TAB}-{panel_id}")

    def get_active_tab(self) -> Locator:
        """Get the active (selected) panel tab in this sub-section.

        The panel tab itself carries ``aria-selected="true"`` (PanelTab sets it
        from ``isActive``), so the tab locator is intersected with that
        attribute. CSS-attribute scoping stays inside the POM to honour the
        integration-test css-locator ratchet.
        """
        return self.get_panel_tabs().and_(self._page.locator('[aria-selected="true"]'))

    def get_add_panel_button(self) -> Locator:
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_ADD_PANEL_BUTTON}-{self._sub_section}")

    def get_maximize_button(self) -> Locator:
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_MAXIMIZE_BUTTON}-{self._sub_section}")

    def get_active_ring(self) -> Locator:
        """Get this sub-section's PanelSection root (the active-section ring host).

        Carries the behavioural ring/active hooks (``data-active`` /
        ``data-ring-visible``) and is the click target that sets the section
        active (a plain pointer-down sets it active silently).
        """
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_ACTIVE_RING}-{self._sub_section}")

    def get_resize_handle(self) -> Locator:
        """Get this section's resize divider (the grid border, not the split divider).

        Keyed by the SECTION id (e.g. ``SECTION_RESIZE_HANDLE-right``); the split
        divider between a split's halves is suffixed ``:secondary`` and is reached
        via the ``PlaywrightSectionSplit`` POM instead.
        """
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_RESIZE_HANDLE}-{_section_of(self._sub_section)}")

    def is_active(self) -> bool:
        """Whether this sub-section is the logical active section.

        Reads the ``data-active`` hook on the ring host (absent when not active,
        ``"true"`` when active). The CSS-attribute read stays inside the POM to
        honour the integration-test css-locator ratchet.
        """
        return self.get_active_ring().get_attribute("data-active") == "true"

    def is_ring_visible(self) -> bool:
        """Whether this sub-section's transient active-section ring is showing.

        Reads the ``data-ring-visible`` hook (absent until a deliberate jump pulses
        it, then ``"true"`` for the fade window). The CSS-attribute read stays
        inside the POM to honour the integration-test css-locator ratchet.
        """
        return self.get_active_ring().get_attribute("data-ring-visible") == "true"

    def maximize(self) -> None:
        """Maximize this section by clicking its header maximize toggle.

        The toggle flips maximize on/off; this clicks it only when the section is
        not already maximized so it is idempotent. While maximized the workspace
        header is hidden but this section's own header (and toggle) stay visible.
        """
        button = self.get_maximize_button()
        expect(button).to_be_visible()
        if self.get_active_ring().get_attribute("data-maximized") == "true":
            return
        button.click()
        expect(self.get_active_ring()).to_have_attribute("data-maximized", "true")

    def restore(self) -> None:
        """Restore this section from maximized by clicking its header maximize toggle.

        Idempotent: clicks the toggle only when the section is currently maximized.
        """
        button = self.get_maximize_button()
        expect(button).to_be_visible()
        if self.get_active_ring().get_attribute("data-maximized") != "true":
            return
        button.click()
        expect(self.get_active_ring()).not_to_have_attribute("data-maximized", "true")

    def get_section_toggle(self) -> Locator:
        """Get this section's workspace-header expand/collapse toggle.

        Only the non-center sections have a toggle (center is always expanded), so for
        the center this returns a never-matching locator — callers can assert it has
        count 0 (SEC-08: center cannot collapse).
        """
        toggle_id = _SECTION_TOGGLE_TEST_IDS.get(_section_of(self._sub_section))
        if toggle_id is None:
            return self._page.get_by_test_id("CENTER_HAS_NO_SECTION_TOGGLE")
        return self._page.get_by_test_id(toggle_id)

    def expand_section(self) -> None:
        """Ensure this section is expanded so its header `+` / tabs render.

        A collapsed section renders no header (and therefore no `+`); the header
        toggle is a toggle, so this clicks it only when the section header is not
        already showing. Idempotent.
        """
        header = self.get_header()
        if header.is_visible():
            return
        toggle = self.get_section_toggle()
        expect(toggle).to_be_visible()
        toggle.click()
        expect(header).to_be_visible()

    def collapse_section(self) -> None:
        """Ensure this section is collapsed so it no longer renders a header.

        Center has no toggle and never collapses, so this is a no-op there. The
        header toggle is a toggle, so this clicks it only when the section header
        is currently showing. Idempotent.
        """
        if _section_of(self._sub_section) == "center":
            return
        header = self.get_header()
        if header.is_hidden():
            return
        toggle = self.get_section_toggle()
        expect(toggle).to_be_visible()
        toggle.click()
        expect(header).to_have_count(0)
