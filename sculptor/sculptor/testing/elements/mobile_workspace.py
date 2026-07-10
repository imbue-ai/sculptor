"""Page Object Models for the mobile Workspace shell.

The mobile shell (``pages/workspace/mobile/``) replaces the whole desktop layout
below the 768px breakpoint — none of the desktop sidebar/section/panel POMs
render under it — so these POMs are the mobile counterparts. A test crosses into
the shell with :func:`enter_mobile_workspace` (resize to a phone viewport +
full SPA reload so ``useLayoutMode`` initializes narrow at first paint), then
drives the header, drawer, agent sheet, changes pill, and full-screen overlays
through the getters here.

Open/closed state for the sliding surfaces (drawer, agent sheet) is read from
``aria-hidden`` rather than Playwright visibility: those surfaces stay mounted
and are only translated off-screen when closed, so a translated element still
reports a bounding box (and would read as "visible"). ``aria-hidden`` mirrors the
component's ``isOpen`` exactly, so it is the reliable interactivity signal.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.playwright_utils import full_spa_reload

# A phone viewport comfortably under the 768px breakpoint (iPhone-14-class).
MOBILE_VIEWPORT = {"width": 390, "height": 844}
# A deliberately SHORT phone viewport, for exercising surfaces that must stay
# reachable when vertical space is scarce (e.g. the AskUserQuestion footer).
SHORT_MOBILE_VIEWPORT = {"width": 390, "height": 560}


def expect_mobile_layout(page: Page) -> None:
    """Assert the app is in the mobile layout.

    ``useLayoutMode`` mirrors its single mobile/desktop verdict onto
    ``html.mobileUx`` (which all mobile CSS keys off), so the class is the
    authoritative signal — and the mobile shell has swapped in for the desktop one.
    """
    expect(page.locator("html.mobileUx")).to_have_count(1)


def expect_desktop_layout(page: Page) -> None:
    """Assert the app stays on the desktop layout: no ``mobileUx`` class and the
    mobile shell never mounted. Used to prove the Electron renderer never flips to
    mobile no matter how narrow the window."""
    expect(page.locator("html.mobileUx")).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_SHELL)).to_have_count(0)


def enter_mobile_workspace(page: Page, viewport: dict[str, int] | None = None) -> "PlaywrightMobileWorkspaceShell":
    """Cross the 768px breakpoint into the mobile Workspace shell.

    Resizes to ``viewport`` (a phone width) and forces a full SPA reload so
    ``useLayoutMode`` re-initializes narrow at first paint — ``html.mobileUx`` set
    and ``WorkspacePage`` mounting ``MobileWorkspaceShell`` from the first render,
    rather than relying on the live media-query flip of an already-mounted desktop
    tree. The current agent route (URL hash) is preserved, so the shell mounts for
    the same agent. Call AFTER ``start_task_and_wait_for_ready`` (which creates the
    workspace/agent at the default desktop viewport).
    """
    page.set_viewport_size(viewport if viewport is not None else MOBILE_VIEWPORT)
    hash_parts = page.url.split("#", 1)
    target_hash = f"#{hash_parts[1]}" if len(hash_parts) > 1 else "#/"
    full_spa_reload(page, target_hash=target_hash)
    shell = PlaywrightMobileWorkspaceShell(page)
    expect(shell.root()).to_be_visible()
    return shell


class PlaywrightMobileWorkspaceShell(PlaywrightIntegrationTestElement):
    """The single-column, chat-first Workspace view for narrow viewports."""

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_SHELL), page=page)

    def root(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_SHELL)

    def get_header(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_HEADER)

    def get_chat_panel(self) -> PlaywrightChatPanelElement:
        """The reused desktop chat surface — the mobile shell mounts the same
        ``ChatPanelContent`` + ``ChatInput``, so the existing chat POM applies."""
        chat_panel = self._page.get_by_test_id(ElementIDs.CHAT_PANEL)
        return PlaywrightChatPanelElement(locator=chat_panel, page=self._page)

    # -- Status row --

    def get_agent_switcher_pill(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_AGENT_SWITCHER_PILL)

    def get_changes_pill(self) -> "PlaywrightMobileChangesPill":
        return PlaywrightMobileChangesPill(self._page)

    # -- Drawer (left) --

    def open_drawer(self) -> "PlaywrightMobileDrawer":
        self._page.get_by_test_id(ElementIDs.MOBILE_HEADER_MENU_BUTTON).click()
        drawer = PlaywrightMobileDrawer(self._page)
        drawer.expect_open()
        return drawer

    def get_drawer(self) -> "PlaywrightMobileDrawer":
        return PlaywrightMobileDrawer(self._page)

    # -- Agent sheet (bottom) --

    def open_agent_sheet(self) -> "PlaywrightMobileAgentSheet":
        self.get_agent_switcher_pill().click()
        sheet = PlaywrightMobileAgentSheet(self._page)
        sheet.expect_open()
        return sheet

    def get_agent_sheet(self) -> "PlaywrightMobileAgentSheet":
        return PlaywrightMobileAgentSheet(self._page)

    # -- Header ⋮ menu --

    def open_header_menu(self) -> None:
        self._page.get_by_test_id(ElementIDs.MOBILE_HEADER_ACTIONS_BUTTON).click()

    def open_terminal_overlay(self) -> "PlaywrightMobileOverlay":
        """Open the terminal overlay via the header ⋮ menu (its only entry point)."""
        self.open_header_menu()
        self._page.get_by_test_id(ElementIDs.MOBILE_HEADER_TERMINAL_ITEM).click()
        overlay = PlaywrightMobileOverlay(self._page, ElementIDs.MOBILE_TERMINAL_OVERLAY)
        expect(overlay.root()).to_be_visible()
        return overlay

    def open_review_overlay_via_header(self) -> "PlaywrightMobileOverlay":
        self.open_header_menu()
        self._page.get_by_test_id(ElementIDs.MOBILE_HEADER_REVIEW_ITEM).click()
        overlay = PlaywrightMobileOverlay(self._page, ElementIDs.MOBILE_REVIEW_ALL_OVERLAY)
        expect(overlay.root()).to_be_visible()
        return overlay

    def get_review_overlay(self) -> "PlaywrightMobileOverlay":
        return PlaywrightMobileOverlay(self._page, ElementIDs.MOBILE_REVIEW_ALL_OVERLAY)

    def get_terminal_overlay(self) -> "PlaywrightMobileOverlay":
        return PlaywrightMobileOverlay(self._page, ElementIDs.MOBILE_TERMINAL_OVERLAY)

    # -- Mobile ChatInput adaptations --

    def get_chat_options_button(self) -> Locator:
        """The ``SlidersHorizontal`` trigger the secondary controls collapse into."""
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHAT_INPUT_OPTIONS)

    def open_chat_options(self) -> None:
        self.get_chat_options_button().click()

    # The options menu (Radix DropdownMenu) portals to <body>, so its items are
    # resolved page-wide, not scoped to the shell.
    def get_options_plan_mode(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)

    def get_options_model_submenu(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHAT_INPUT_MODEL_SUBMENU)

    def get_options_effort_submenu(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHAT_INPUT_EFFORT_SUBMENU)

    def get_options_fast_mode(self) -> Locator:
        """Fast mode is capability-gated — only present when the model supports it."""
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHAT_INPUT_FAST_MODE_ITEM)

    def get_keyboard_hints(self) -> Locator:
        """The desktop-only keyboard-hint row (absent on mobile)."""
        return self._page.get_by_test_id(ElementIDs.CHAT_INPUT_KEYBOARD_HINTS)

    def get_desktop_model_selector(self) -> Locator:
        """The always-visible desktop model selector (absent on mobile)."""
        return self._page.get_by_test_id(ElementIDs.MODEL_SELECTOR)


def _long_press(row: Locator) -> None:
    """Trigger a row's long-press context menu deterministically.

    ``useLongPress`` opens the menu on either a 450ms touch-hold or a
    ``contextmenu`` event (right-click). Dispatching ``contextmenu`` is the
    deterministic path — synthetic touch-hold timing is flaky under Playwright.
    """
    row.dispatch_event("contextmenu")


class PlaywrightMobileDrawer(PlaywrightIntegrationTestElement):
    """The left drawer: Home/Settings nav, repo-grouped workspace rows, and the
    pinned "New workspace" button."""

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_DRAWER), page=page)

    def root(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_WORKSPACE_DRAWER)

    def expect_open(self) -> None:
        expect(self.root()).to_have_attribute("aria-hidden", "false")

    def expect_closed(self) -> None:
        expect(self.root()).to_have_attribute("aria-hidden", "true")

    def get_home_link(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_DRAWER_HOME_LINK)

    def get_settings_link(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_DRAWER_SETTINGS_LINK)

    def get_workspace_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_DRAWER_WORKSPACE_ROW)

    def get_current_workspace_row(self) -> Locator:
        return self.get_workspace_rows().and_(self._page.locator('[aria-current="true"]'))

    def get_other_workspace_row(self) -> Locator:
        """A workspace row other than the one currently being viewed."""
        return self.get_workspace_rows().and_(self._page.locator('[aria-current="false"]')).first

    def get_new_workspace_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_DRAWER_NEW_WORKSPACE_BUTTON)

    def long_press_workspace_row(self, row: Locator) -> None:
        _long_press(row)
        expect(self.get_rename_action()).to_be_visible()

    def get_rename_action(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_ROW_RENAME_ACTION)

    def get_delete_action(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_ROW_DELETE_ACTION)


class PlaywrightMobileAgentSheet(PlaywrightIntegrationTestElement):
    """The bottom sheet listing the workspace's agents + a "New agent" row."""

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.MOBILE_AGENT_SHEET), page=page)

    def root(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_AGENT_SHEET)

    def expect_open(self) -> None:
        expect(self.root()).to_have_attribute("aria-hidden", "false")

    def expect_closed(self) -> None:
        expect(self.root()).to_have_attribute("aria-hidden", "true")

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_AGENT_SHEET_ROW)

    def get_current_row(self) -> Locator:
        return self.get_rows().and_(self._page.locator('[aria-current="true"]'))

    def get_other_row(self) -> Locator:
        return self.get_rows().and_(self._page.locator('[aria-current="false"]')).first

    def get_new_agent_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_AGENT_SHEET_NEW_AGENT)

    def long_press_row(self, row: Locator) -> None:
        _long_press(row)
        expect(self.get_rename_action()).to_be_visible()

    def get_rename_action(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_ROW_RENAME_ACTION)

    def get_delete_action(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_ROW_DELETE_ACTION)


class PlaywrightMobileChangesPill(PlaywrightIntegrationTestElement):
    """The right pill of the status row; expands a file list with a
    "Review all changes" affordance. Renders only when there are changes."""

    def __init__(self, page: Page) -> None:
        super().__init__(locator=page.get_by_test_id(ElementIDs.MOBILE_CHANGES_PILL), page=page)

    def root(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHANGES_PILL)

    def get_toggle(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHANGES_PILL_TOGGLE)

    def get_review_all_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MOBILE_CHANGES_PILL_REVIEW_ALL)

    def open_review_all(self) -> "PlaywrightMobileOverlay":
        self.get_toggle().click()
        self.get_review_all_button().click()
        overlay = PlaywrightMobileOverlay(self._page, ElementIDs.MOBILE_REVIEW_ALL_OVERLAY)
        expect(overlay.root()).to_be_visible()
        return overlay


class PlaywrightMobileOverlay(PlaywrightIntegrationTestElement):
    """A full-screen overlay over the chat (review-all or terminal). ``back``
    closes it (in-shell state; not a router navigation)."""

    def __init__(self, page: Page, overlay_test_id: str) -> None:
        self._overlay_test_id = overlay_test_id
        super().__init__(locator=page.get_by_test_id(overlay_test_id), page=page)

    def root(self) -> Locator:
        return self._page.get_by_test_id(self._overlay_test_id)

    def get_back_button(self) -> Locator:
        return self.root().get_by_test_id(ElementIDs.MOBILE_OVERLAY_BACK_BUTTON)

    def back(self) -> None:
        self.get_back_button().click()
        expect(self.root()).to_have_count(0)

    # -- Review-all overlay specifics (CombinedDiffView) --

    def get_diff_file_sections(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.COMBINED_DIFF_FILE_SECTION)

    def get_diff_toolbar(self) -> Locator:
        """The desktop diff toolbar — hidden (not rendered) in the mobile overlay."""
        return self._page.get_by_test_id(ElementIDs.COMBINED_DIFF_TOOLBAR)

    def get_commit_button(self) -> Locator:
        """The pinned commit footer's button (shown for the uncommitted scope)."""
        return self._page.get_by_test_id(ElementIDs.CHANGES_COMMIT_BUTTON)

    # -- Terminal overlay specifics --

    def get_terminal_panel(self) -> Locator:
        """The reused ``TerminalPanelView`` mounted inside the terminal overlay."""
        return self._page.get_by_test_id(ElementIDs.TERMINAL_PANEL_VIEW)


# -- Module-level getters for surfaces the drawer nav lands on / shares --


def get_mobile_home_header(page: Page) -> Locator:
    """The mobile Home header (the drawer's Home nav lands here)."""
    return page.get_by_test_id(ElementIDs.MOBILE_HOME_HEADER)


def get_mobile_settings_header(page: Page) -> Locator:
    """The mobile Settings header (the drawer's Settings nav lands here)."""
    return page.get_by_test_id(ElementIDs.MOBILE_SETTINGS_HEADER)


def get_inline_rename_input(page: Page) -> Locator:
    """The inline rename ``<input>`` a drawer/agent row swaps to while renaming."""
    return page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)


def get_delete_confirm_button(page: Page) -> Locator:
    """The confirm button of the shared delete-confirmation dialog."""
    return page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
