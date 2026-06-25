from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.constants import ElementIDs

# expand_section retries the toggle click across workspace-header re-render churn
# (see expand_section). Each attempt gets a short timeout so an unstable toggle
# fails fast and the loop can re-check the guard / clear an intercepting overlay.
_EXPAND_SECTION_CLICK_ATTEMPTS = 5
_EXPAND_SECTION_CLICK_TIMEOUT_MS = 5_000

# The four sections of the workspace grid. A sub-section id is either a section id
# (the unsplit "primary" half) or a section id suffixed with ":secondary" (e.g.
# "left:secondary") — the flat sub-section keyspace.
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


def section_of(sub_section: str) -> str:
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
        return self._page.get_by_test_id(_SECTION_ROOT_TEST_IDS[section_of(self._sub_section)])

    def get_header(self) -> Locator:
        """Get this sub-section's header (tab strip + add + maximize)."""
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_HEADER}-{self._sub_section}")

    def get_panel_tabs(self) -> Locator:
        """Get every panel tab in this sub-section's header.

        Panel-tab testids are suffixed with the panel id (e.g.
        ``f"{PANEL_TAB}-agent:<taskId>"``), so there is no single testid to match
        on; they are selected by a ``data-testid`` prefix (attribute) selector
        scoped under this sub-section's header. That CSS selector is encapsulated
        here so the integration tests (which the css-locator ratchet covers) keep
        querying tabs by testid through this POM rather than writing their own.
        """
        return self.get_header().locator(f'[data-testid^="{ElementIDs.PANEL_TAB}-"]')

    def get_panel_tab(self, panel_id: str) -> Locator:
        """Get the panel tab for a specific panel id (e.g. ``agent:<taskId>``)."""
        return self.get_header().get_by_test_id(f"{ElementIDs.PANEL_TAB}-{panel_id}")

    def get_active_tab(self) -> Locator:
        """Get the active (selected) panel tab in this sub-section.

        The panel tab itself carries ``aria-selected="true"`` (PanelTab sets it
        from ``isActive``), which is not a testid, so the tab locator is
        intersected with that attribute selector. That CSS-attribute selector is
        encapsulated here so the integration tests (which the css-locator ratchet
        covers) keep querying the active tab by testid through this POM.
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
        return self._page.get_by_test_id(f"{ElementIDs.SECTION_RESIZE_HANDLE}-{section_of(self._sub_section)}")

    def is_active(self) -> bool:
        """Whether this sub-section is the logical active section.

        Reads the ``data-active`` hook on the ring host (absent when not active,
        ``"true"`` when active). The attribute read is encapsulated here so test
        files get a boolean accessor and never reach for the raw ``data-*`` hook.
        """
        return self.get_active_ring().get_attribute("data-active") == "true"

    def is_ring_visible(self) -> bool:
        """Whether this sub-section's transient active-section ring is showing.

        Reads the ``data-ring-visible`` hook (absent until a deliberate jump pulses
        it, then ``"true"`` for the fade window). The attribute read is encapsulated
        here so test files get a boolean accessor and never reach for the raw
        ``data-*`` hook.
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
        count 0 (center cannot collapse).
        """
        toggle_id = _SECTION_TOGGLE_TEST_IDS.get(section_of(self._sub_section))
        if toggle_id is None:
            return self._page.get_by_test_id("CENTER_HAS_NO_SECTION_TOGGLE")
        return self._page.get_by_test_id(toggle_id)

    def expand_section(self) -> None:
        """Ensure this section is expanded so its header `+` / tabs render.

        A collapsed section renders no header (and therefore no `+`). Center is always
        expanded and has no toggle, so this just waits for its header. For the non-center
        sections the expand/collapse toggle lives in the workspace header, which only
        mounts once the workspace has loaded; wait for the toggle to be visible BEFORE
        reading the section's (non-auto-waiting) ``is_visible`` state, so a check that
        races a still-loading shell doesn't misfire the toggle and collapse a section
        that was already (about to be) expanded. Idempotent.

        The toggle click is made resilient to a transiently unstable workspace header:
        during per-test cleanup the previous workspace is being torn down, so its
        header (a Skeleton that resolves into the branch name) re-renders and the
        toggle's box keeps moving, tripping Playwright's "visible, enabled and stable"
        actionability check. Each attempt re-checks the idempotency guard (the header
        already showing means done) and dismisses a dismissible overlay that could
        intercept the click before retrying.
        """
        header = self.get_header()
        if section_of(self._sub_section) == "center":
            expect(header).to_be_visible()
            return
        toggle = self.get_section_toggle()
        expect(toggle).to_be_visible()
        if header.is_visible():
            return

        # Retry the toggle click across header re-render churn. A short per-attempt
        # click timeout lets a churning (never-stable) toggle fail fast so we can
        # re-check the guard and clear any intercepting overlay between attempts,
        # rather than burning the whole default timeout on a single unstable click.
        #
        # The toggle flips expand <-> collapse, so a landed click must never be
        # repeated: once the click itself succeeds the section is already expanding
        # and only the header render is pending, so re-clicking would collapse it
        # again. We therefore separate "the click did not land" (an exception FROM
        # the click — retry it) from "the header has not rendered yet" (the click
        # landed; keep waiting on the same expand without re-clicking).
        last_error: Exception | None = None
        for _ in range(_EXPAND_SECTION_CLICK_ATTEMPTS):
            if header.is_visible():
                return
            try:
                toggle.click(timeout=_EXPAND_SECTION_CLICK_TIMEOUT_MS)
            except PlaywrightTimeoutError as error:
                last_error = error
                # The click never landed (the toggle stayed unstable/unactionable,
                # or an open dismissible overlay — a lingering popover/tooltip/dialog
                # from the prior test — intercepted it); clear any overlay, then retry.
                self._page.keyboard.press("Escape")
                continue
            # The click landed, so this attempt already flipped the section to
            # expanded; only the header render is pending. Wait for it WITHOUT
            # re-clicking — a re-click here would toggle the section back to
            # collapsed. If the header never renders this re-raises out of the
            # method (it is a real failure, not a missed click), which is why the
            # forced-click fallback below is reachable only when no click landed.
            expect(header).to_be_visible(timeout=_EXPAND_SECTION_CLICK_TIMEOUT_MS)
            return

        # No click ever landed: every actionable attempt lost the stability race —
        # the workspace header is still churning (a mid-optimistic-delete navigation
        # remounts it, so its box keeps moving past the per-attempt budget). The
        # toggle is a fixed-position header button (only the branch-name text beside
        # it reflows), so a forced click lands on it without waiting for the box to
        # settle.
        if not header.is_visible():
            try:
                toggle.click(force=True, timeout=_EXPAND_SECTION_CLICK_TIMEOUT_MS)
                expect(header).to_be_visible(timeout=_EXPAND_SECTION_CLICK_TIMEOUT_MS)
                return
            except (PlaywrightTimeoutError, AssertionError) as error:
                last_error = error
        if header.is_visible():
            return
        if last_error is not None:
            raise last_error
        expect(header).to_be_visible()

    def collapse_section(self) -> None:
        """Ensure this section is collapsed so it no longer renders a header.

        Center has no toggle and never collapses, so this is a no-op there. The
        header toggle is a toggle, so this clicks it only when the section header
        is currently showing. Idempotent.
        """
        if section_of(self._sub_section) == "center":
            return
        header = self.get_header()
        if header.is_hidden():
            return
        toggle = self.get_section_toggle()
        expect(toggle).to_be_visible()
        toggle.click()
        expect(header).to_have_count(0)
