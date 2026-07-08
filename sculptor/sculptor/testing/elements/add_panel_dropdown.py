from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import open_radix_toggle
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.elements.workspace_section import section_of

# open_agent_type_submenu retries the sub-menu hover: a hover landing while Radix tears
# down a just-dismissed menu is swallowed and never opens the sub-content. Each attempt
# waits this long for the sub-menu before re-hovering.
_AGENT_TYPE_SUBMENU_HOVER_ATTEMPTS = 3
_AGENT_TYPE_SUBMENU_HOVER_TIMEOUT_MS = 3_000

# A seeded panel's tab can render a beat after its section expands, so the idempotent
# "is this panel already open here" checks wait this long for the tab before concluding
# it is closed. A bare snapshot count races the slow tab and falls through to a dropdown
# that won't offer a still-open single-instance panel.
_PANEL_TAB_RENDER_TIMEOUT_MS = 2_000


class PlaywrightAddPanelDropdownElement:
    """Page Object Model for the section `+` add-panel dropdown.

    The dropdown is opened by a section's header `+` (or an empty-section add
    button) and is scoped to the sub-section it was opened from: its content
    testid is ``f"{ADD_PANEL_DROPDOWN}-{subSection}"``, and the "New terminal" /
    static-panel options open into THAT sub-section (a new agent always lands in
    center). Items render in a Radix portal, so they are located page-wide.

    Carries the recent-agent row, the agent-type sub-menu (with the
    Radix-teardown retry), the new-terminal row, and the single-instance
    panel options.

    Constructed with the ``sub_section`` whose `+` opens it so the content root
    resolves uniquely even when two sub-sections both have an open dropdown id in
    the DOM.
    """

    def __init__(self, page: Page, sub_section: str = "center") -> None:
        self._page = page
        self._sub_section = sub_section

    def get_content(self) -> Locator:
        """Get the open dropdown's content root for this sub-section."""
        return self._page.get_by_test_id(f"{ElementIDs.ADD_PANEL_DROPDOWN}-{self._sub_section}")

    def get_add_panel_button(self) -> Locator:
        """Get this sub-section's header `+` button (the dropdown trigger)."""
        return PlaywrightWorkspaceSection(self._page, self._sub_section).get_add_panel_button()

    # New agent (recently-used type)

    def get_new_agent_item(self) -> Locator:
        """The pinned "New {recent} agent" row (creates the recently-used type)."""
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_AGENT)

    # Agent-type sub-menu

    def get_agent_type_submenu_trigger(self) -> Locator:
        """The "New agent of type…" sub-menu trigger."""
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_AGENT_TYPE_SUBMENU)

    def get_agent_type_submenu(self) -> Locator:
        """The open agent-type sub-menu content."""
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU)

    def get_agent_type_item_claude(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_CLAUDE)

    def get_agent_type_item_terminal(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_TERMINAL)

    def get_agent_type_item_pi(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_PI)

    def get_agent_type_item_registered(self, registration_id: str) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_REGISTERED).and_(
            self._page.locator(f'[data-registration-id="{registration_id}"]')
        )

    def open_agent_type_submenu(self) -> Locator:
        """Hover the agent-type sub-menu trigger and return the open sub-menu.

        Retries the hover: a hover landing while Radix is still tearing down a
        just-dismissed menu can be swallowed (or never open the sub-content), and
        ``expect`` alone cannot recover from a lost hover.
        """
        submenu = self.get_agent_type_submenu()
        trigger = self.get_agent_type_submenu_trigger()
        for _attempt in range(_AGENT_TYPE_SUBMENU_HOVER_ATTEMPTS):
            expect(trigger).to_be_visible()
            trigger.hover()
            try:
                expect(submenu).to_be_visible(timeout=_AGENT_TYPE_SUBMENU_HOVER_TIMEOUT_MS)
                return submenu
            except AssertionError:
                continue
        expect(submenu).to_be_visible()
        return submenu

    # New terminal

    def get_new_terminal_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_PANEL_NEW_TERMINAL)

    # Single-instance panel options

    def get_panel_option(self, panel_id: str) -> Locator:
        """Get a single-instance panel option row by its registry id (e.g. ``files``)."""
        return self._page.get_by_test_id(f"{ElementIDs.ADD_PANEL_PANEL_OPTION}-{panel_id}")

    # Open / select

    def open(self) -> None:
        """Open the dropdown by clicking this sub-section's header `+`.

        The trigger is a Radix dropdown, so opening is idempotent and retried
        (see ``open_radix_toggle``); the content renders in a portal, so success
        is confirmed on the content's visibility rather than the trigger state.
        """
        open_radix_toggle(self._page, self.get_add_panel_button())
        expect(self.get_content()).to_be_visible()

    def select_panel(self, panel_id: str) -> None:
        """Click a single-instance panel option, opening it into this sub-section."""
        option = self.get_panel_option(panel_id)
        expect(option).to_be_visible()
        option.click()


# Panels the default workspace layout seeds OPEN on a workspace's first visit:
# Files/Changes/Commits live in the left section, Files active.
# A single-instance panel can only live in ONE section at a time, and the add-panel
# dropdown only offers panels not already open anywhere, so to land a seeded panel in
# a DIFFERENT section the helper first closes it from its seeded section (which a
# single-instance close does silently, no confirmation) so the dropdown offers it
# again. Panels NOT seeded start closed and always open straight through the dropdown.
_DEFAULT_SEEDED_SECTION: dict[str, str] = {"files": "left", "changes": "left", "commits": "left"}


def _panel_tab_is_open(tab: Locator) -> bool:
    """Whether a panel tab is open in its section, tolerating a slow-rendering tab.

    A seeded panel's tab can render a beat after its section expands, so a bare
    snapshot count right after ``expand_section`` reads zero for a tab that is about
    to appear. Waits a bounded window for the tab and treats one that never renders as
    not open, keeping the "is it already here" checks idempotent without racing the
    render — a false "not open" falls through to a dropdown that won't offer a
    still-open single-instance panel and then times out.
    """
    try:
        expect(tab).to_be_visible(timeout=_PANEL_TAB_RENDER_TIMEOUT_MS)
        return True
    except AssertionError:
        return False


def open_panel(page: Page, panel_id: str, sub_section: str = "center") -> Locator:
    """Bring a single-instance panel into ``sub_section`` and return its section root.

    Seeded panels (Files/Changes/Commits — seeded into the left section) are
    never center panels, so a request for their seeded section OR the default ``center``
    means "reveal it where it lives": expand the seeded section and activate its tab,
    waiting for the tab (never the dropdown). Only an explicit request for a DIFFERENT
    real section (right/bottom) moves a seeded panel — closing it from its home first so
    the dropdown offers it again. Non-seeded panels always open via the section `+`.
    Returns the owning section's root locator so callers can scope the panel's POM to it.
    """
    seeded_section = _DEFAULT_SEEDED_SECTION.get(panel_id)
    target_section = section_of(sub_section)

    # Reveal a seeded panel in its home section (the common case: callers pass the seeded
    # section or the default ``center``, neither of which moves it). Waiting on the tab —
    # not a non-blocking count() right after expand — avoids a race where a slow-rendering
    # tab falls through to a dropdown that won't offer a still-open panel.
    if seeded_section is not None and target_section in (seeded_section, "center"):
        home = PlaywrightWorkspaceSection(page, seeded_section)
        home.expand_section()
        tab = home.get_panel_tab(panel_id)
        expect(tab).to_be_visible()
        tab.click()
        home_root = home.get_section()
        expect(home_root).to_be_visible()
        return home_root

    # Open into an explicitly-requested section. A collapsed section's PanelSection —
    # and its header `+` / tabs — aren't mounted; expand first (idempotent).
    section = PlaywrightWorkspaceSection(page, sub_section)
    section.expand_section()
    existing_tab = section.get_panel_tab(panel_id)
    if _panel_tab_is_open(existing_tab):
        existing_tab.click()
        section_root = section.get_section()
        expect(section_root).to_be_visible()
        return section_root

    # A seeded panel can't be duplicated and the dropdown won't offer it while it is open,
    # so close it from its seeded section before re-adding it here.
    if seeded_section is not None and seeded_section != target_section:
        close_seeded_panel(page, panel_id)

    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section)
    dropdown.open()
    dropdown.select_panel(panel_id)
    expect(section.get_panel_tab(panel_id)).to_be_visible()
    section_root = section.get_section()
    expect(section_root).to_be_visible()
    return section_root


def close_seeded_panel(page: Page, panel_id: str) -> None:
    """Close a default-seeded single-instance panel from its seeded section.

    The default layout seeds Files/Changes/Commits OPEN in the left section, so
    they are not offered by the add-panel dropdown until closed.
    Expands the seeded section to render the tab's close button (page-wide by panel id)
    and clicks it; a single-instance close removes the panel silently (no confirmation),
    which both returns it to the dropdown's re-add list and records it as recently-closed
    for the empty-state quick actions. Idempotent: a no-op if the panel is not open.
    """
    seeded_section = _DEFAULT_SEEDED_SECTION.get(panel_id)
    if seeded_section is None:
        return
    origin = PlaywrightWorkspaceSection(page, seeded_section)
    origin.expand_section()
    origin_tab = origin.get_panel_tab(panel_id)
    if not _panel_tab_is_open(origin_tab):
        return
    close_button = page.get_by_test_id(f"{ElementIDs.PANEL_TAB_CLOSE}-{panel_id}")
    expect(close_button).to_be_visible()
    close_button.click()
    expect(origin_tab).to_have_count(0)


def create_agent_panel(page: Page, section: str = "center", agent_type: str | None = None) -> None:
    """Create a new agent via the section `+` add-panel dropdown.

    New agents ALWAYS land in the center section, regardless of the
    ``section`` the dropdown was opened from. ``agent_type`` picks a specific type
    from the agent-type sub-menu (``"claude"`` / ``"pi"``); ``None`` uses the pinned
    "New {recent} agent" row.

    A collapsed section renders no header `+`, so the section is expanded first
    (idempotent) even though the new agent still lands in center.
    """
    PlaywrightWorkspaceSection(page, section).expand_section()
    dropdown = PlaywrightAddPanelDropdownElement(page, section)
    dropdown.open()
    if agent_type is None:
        item = dropdown.get_new_agent_item()
        expect(item).to_be_visible()
        item.click()
        return
    dropdown.open_agent_type_submenu()
    if agent_type == "claude":
        item = dropdown.get_agent_type_item_claude()
    elif agent_type == "pi":
        item = dropdown.get_agent_type_item_pi()
    else:
        raise ValueError(f"unsupported agent_type: {agent_type!r}; expected None, 'claude', or 'pi'")
    expect(item).to_be_visible()
    item.click()


def create_terminal_panel(page: Page, section: str = "bottom") -> None:
    """Create a new terminal panel via the section `+` add-panel dropdown.

    The terminal lands in the requesting ``section`` (its sub-section). A collapsed
    section renders no header `+`, so the section is expanded first via the workspace
    header section toggle (idempotent).
    """
    PlaywrightWorkspaceSection(page, section).expand_section()
    dropdown = PlaywrightAddPanelDropdownElement(page, section)
    dropdown.open()
    item = dropdown.get_new_terminal_item()
    expect(item).to_be_visible()
    item.click()
