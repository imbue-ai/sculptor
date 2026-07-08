"""Integration tests for the Command Palette (Cmd+K).

These tests cover the high-level UX of the rebuilt palette:
- opening via the sidebar Cmd+K link + keyboard shortcut
- closing via Escape
- typing to filter the list
- executing a navigation command and confirming the route changes
- pushing and popping a sub-page (Theme picker)
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.base import dismiss_with_escape
from sculptor.testing.elements.base import wait_for_one_frame
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import wait_for_workspace_list_loaded
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _layout(sculptor_instance: SculptorInstance) -> PlaywrightProjectLayoutPage:
    # Every palette open path (sidebar Cmd+K link, keyboard shortcut) no-ops
    # while the workspace list is still loading, and ensure_workspace_exists's
    # momentary first-run probe misreads that window as "workspaces exist".
    # Wait for the list before any test drives the palette.
    wait_for_workspace_list_loaded(sculptor_instance.page)
    return PlaywrightProjectLayoutPage(page=sculptor_instance.page)


@pytest.mark.release
@user_story("to open the command palette via the sidebar Cmd+K link")
def test_open_command_palette_via_sidebar_cmdk_link(sculptor_instance_: SculptorInstance) -> None:
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()
    expect(palette).to_be_visible()
    expect(palette.get_input()).to_be_focused()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to open the command palette via Cmd+K")
def test_open_command_palette_via_keyboard_shortcut(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    blur_active_element(page)
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette_with_keyboard()
    expect(palette).to_be_visible()
    expect(palette.get_input()).to_be_focused()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to filter the command list as I type")
def test_command_palette_filters_on_input(sculptor_instance_: SculptorInstance) -> None:
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # The "Open Settings" command (nav.settings) is a real entry; the
    # "asdfgh..." query matches nothing. Use the title that the command
    # actually carries — the page-opener `settings.open` is now titled
    # "Go to Settings...", so "Open Settings" uniquely matches nav.settings.
    palette.type_query("Open Settings")
    expect(palette.get_item_by_command_id("nav.settings")).to_be_visible()

    palette.type_query("asdfghqwerty")
    expect(palette.get_empty_state()).to_be_visible()

    palette.clear_search()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to navigate to Settings via the command palette")
def test_command_palette_navigates_to_settings(sculptor_instance_: SculptorInstance) -> None:
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # `nav.settings`'s title is "Open Settings" — typing "Go to Settings"
    # would match the page-opener `settings.open` ("Go to Settings...")
    # instead.
    palette.type_query("Open Settings")
    palette.select_by_command_id("nav.settings")

    expect(palette).not_to_be_visible()
    expect(layout.get_settings_page_locator()).to_be_visible()


@pytest.mark.release
@user_story("to push and pop sub-pages in the command palette")
def test_command_palette_subpage_push_pop(sculptor_instance_: SculptorInstance) -> None:
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # The "Switch theme..." command pushes a sub-page.
    palette.type_query("Switch theme")
    palette.select_by_command_id("theme.switch")

    # Breadcrumb appears, indicating we are on a sub-page.
    expect(palette.get_breadcrumb()).to_be_visible()

    # The Light / Dark / System rows are now visible (page-scoped).
    expect(palette.get_item_by_command_id("theme.appearance.light")).to_be_visible()

    # Backspace on an empty input pops the sub-page.
    palette.get_input().fill("")
    palette.press_backspace()
    expect(palette.get_breadcrumb()).to_have_count(0)

    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to have keep-open commands stay open after running")
def test_command_palette_keep_open_command(sculptor_instance_: SculptorInstance) -> None:
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # `theme.toggle` has keepOpen: true. We avoid `developer.dev_panel`
    # here because opening the dev panel introduces an overlay that
    # captures the next Escape, so an Escape would fail to close the
    # palette. Theme toggle has no overlay side-effect.
    palette.type_query("Toggle Theme")
    palette.select_by_command_id("theme.toggle")

    expect(palette).to_be_visible()

    # Flip the theme back so the test doesn't leave a lasting side effect
    # on subsequent tests sharing the same instance.
    palette.select_by_command_id("theme.toggle")
    expect(palette).to_be_visible()

    palette.clear_search()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to close the command palette with Escape")
def test_command_palette_escape_closes(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    blur_active_element(page)
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette_with_keyboard()
    expect(palette.get_input()).to_be_focused()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to ignore Cmd+K when an unrelated dismissible overlay is open")
def test_command_palette_keyboard_suppressed_when_overlay_open(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()
    layout = _layout(sculptor_instance_)
    # Cmd+/ (help) and Cmd+K are suppressed in the empty first-run state, so
    # create a workspace before exercising them.
    layout.ensure_workspace_exists()
    blur_active_element(page)

    # Open the help dialog so the overlay-suppression rule kicks in.
    layout.press_keyboard_shortcut(f"{mod}+/")
    dialog = layout.get_keyboard_shortcuts_dialog()
    expect(dialog).to_be_visible()

    # Cmd+K should not open the palette while the help dialog is up.
    layout.press_keyboard_shortcut(f"{mod}+k")
    palette = layout.get_command_palette()
    expect(palette).not_to_be_visible()

    dismiss_with_escape(dialog)


@pytest.mark.release
@user_story("to see the command palette open affordance in the sidebar")
def test_command_palette_open_button_visible_in_sidebar(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: the legacy SearchModal was removed in favour of the
    # Command Palette. The open affordance moved off the old top bar onto the
    # sidebar Cmd+K link, which must continue to render.
    layout = _layout(sculptor_instance_)
    expect(layout.get_workspace_sidebar().get_cmdk_link()).to_be_visible()


@pytest.mark.release
@user_story("to file a bug report from the command palette")
def test_command_palette_report_problem_opens_popover(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: the new help.report_problem command must trigger the
    # ReportProblemPopover (opened via runtime.ui.openReportProblem).
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    palette.type_query("Report a problem")
    palette.select_by_command_id("help.report_problem")

    # The palette closes after a non-keepOpen command, and the bug-report
    # popover surfaces with its REPORT_PROBLEM_POPOVER test id.
    expect(palette).not_to_be_visible()
    expect(layout.get_report_problem_popover()).to_be_visible()


@pytest.mark.release
@user_story("to fuzzy-find a Settings sub-page command from the palette root")
def test_command_palette_cross_page_reveal_finds_subpage_item(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: typing a query at the root must surface page-scoped
    # commands (those with `onPage`), so the user can fuzzy-find a Settings
    # section without first opening the Settings sub-page.
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # The "Theme builder" Settings section command lives on the
    # `settings.section` sub-page (id "settings.page.theme_builder"). It
    # must NOT appear when the query is empty (root list only).
    palette.type_query("")
    expect(palette.get_item_by_command_id("settings.page.theme_builder")).not_to_be_visible()

    # Typing a matching query reveals it via cross-page fuzzy search.
    palette.type_query("Theme builder")
    expect(palette.get_item_by_command_id("settings.page.theme_builder")).to_be_visible()

    palette.clear_search()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to keep the palette open after running a command via Cmd+Enter")
def test_command_palette_cmd_enter_keeps_palette_open(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: Cmd+Enter forces keepOpen=true even for commands that
    # would otherwise close the palette. We use `nav.home` (non-keepOpen,
    # auto-closes normally) to prove the modifier is what's keeping it open.
    # `nav.home` is also a no-op when the user is already at home, so the
    # test has no observable side-effects.
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    palette.type_query("Open Home")
    expect(palette.get_item_by_command_id("nav.home")).to_be_visible()

    mod = get_playwright_modifier_key()
    palette.get_input().press(f"{mod}+Enter")

    # The palette should remain visible because Cmd+Enter forces keepOpen.
    expect(palette).to_be_visible()
    dismiss_with_escape(palette)


@pytest.mark.release
@user_story("to keep the top-scored result visible after typing into the palette")
def test_command_palette_top_result_is_not_scrolled_past(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: typing into the palette must leave the highest-scored
    # row visible at the top of the list. cmdk schedules a `scrollIntoView`
    # on the auto-selected item from a follow-up render via its internal
    # scheduler; if our scroll-reset isn't deferred to a rAF, cmdk wins the
    # race and the list ends up scrolled past the top row. Original report:
    # typing "set" picks "Open settings" (word-prefix on "Settings", score
    # 200) as the auto-selected row, but the list scrolled so only the
    # sub-page rows below it (Account, Actions, Agent, ...) were visible.
    page = sculptor_instance_.page
    # Shrink the viewport so the palette's max-height (`min(72vh, 560px)`)
    # forces the list to overflow with the 13 settings sub-pages + the
    # "Open settings" row that match "set". Without overflow the
    # scroll-reset race is unobservable: cmdk's scrollIntoView is a no-op
    # when the list fits in the visible area. Restored after the test
    # so subsequent shared-instance tests get the default 1400x900.
    original_viewport = page.viewport_size
    try:
        page.set_viewport_size({"width": 1400, "height": 480})
        layout = _layout(sculptor_instance_)
        palette = layout.open_command_palette()

        # Type one character at a time. The race only manifests with per-
        # keystroke renders: each keystroke triggers cmdk's deferred
        # scrollIntoView from a follow-up render. `fill()` sets the value
        # in a single render and would short-circuit the race.
        palette.get_input().press_sequentially("set")

        # Sanity: nav.settings is auto-selected (highest score for "set").
        expect(palette.get_item_by_command_id("nav.settings")).to_have_attribute("data-selected", "true")

        # The auto-selected row must not be clipped at the top of the list. In
        # the bug, cmdk's scrollIntoView ran after our scroll-reset and the
        # row's bounding-box top sat above the list's top edge. Both callbacks
        # are scheduled via requestAnimationFrame, so pump two animation frames
        # to drain them before measuring — one to flush the current RAF queue
        # and one as headroom against a chained RAF callback.
        wait_for_one_frame(page)
        wait_for_one_frame(page)

        list_box = palette.get_list().bounding_box()
        row_box = palette.get_item_by_command_id("nav.settings").bounding_box()
        assert list_box is not None
        assert row_box is not None
        assert row_box["y"] >= list_box["y"], (
            f"Top-scored row scrolled past list top: row.y={row_box['y']:.1f} list.y={list_box['y']:.1f}"
        )

        palette.clear_search()
        dismiss_with_escape(palette)
    finally:
        if original_viewport is not None:
            page.set_viewport_size(original_viewport)


@pytest.mark.release
@user_story("to not see animated scroll motion in the command palette while searching")
def test_command_palette_list_does_not_animate_scrolls(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock: typing into the palette must not trigger a smooth/
    # animated scroll on the list. Two paths scroll the list while the
    # user is typing:
    #   1. cmdk's internal `selectedItem.scrollIntoView({block: "nearest"})`
    #      fires when filtering re-ranks rows.
    #   2. CommandPalette.tsx resets `listRef.current.scrollTop = 0` on
    #      every search change.
    # Both inherit the list's CSS `scroll-behavior`. With `smooth`, every
    # keystroke turns into a visible animated scroll the user perceives
    # as the modal "jumping". The list must use the browser default
    # (auto/instant) so these resets snap without motion.
    layout = _layout(sculptor_instance_)
    palette = layout.open_command_palette()

    # `to_have_css` reads computed style — the same value cmdk's scrollIntoView
    # and the React scrollTop-reset both inherit when they request a scroll.
    list_locator = palette.get_list()
    expect(list_locator).to_have_css("scroll-behavior", "auto")

    dismiss_with_escape(palette)


@user_story("to find a Minimize section command in the palette while a section is maximized")
def test_command_palette_maximize_command_reads_minimize_while_maximized(
    sculptor_instance_: SculptorInstance,
) -> None:
    # Regression lock for the `view.maximize_section` copy: the command toggles
    # maximize/restore, so while a section is maximized its row must read
    # "Minimize section" (state-aware getTitle) and be findable by typing
    # "minimize" — a user staring at a maximized section searches for the way
    # OUT, not the way in. Not @release-marked: start_task_and_wait_for_ready
    # selects the Fake Claude model, which is gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cmd+K Minimize WS")
    center = PlaywrightWorkspaceSection(page, "center")

    # Before maximizing, the row reads "Maximize section".
    palette = task_page.open_command_palette()
    palette.type_query("maximize")
    row = palette.get_item_by_command_id("view.maximize_section")
    expect(row).to_be_visible()
    expect(row).to_contain_text("Maximize section")

    # Run it — the active (center) section maximizes and the palette closes.
    palette.select_by_command_id("view.maximize_section")
    expect(palette).not_to_be_visible()
    expect(center.get_active_ring()).to_have_attribute("data-maximized", "true")

    # While maximized, searching "minimize" must surface the same command, and
    # its copy must flip to "Minimize section".
    blur_active_element(page)
    palette = task_page.open_command_palette_with_keyboard()
    palette.type_query("minimize")
    expect(row).to_be_visible()
    expect(row).to_contain_text("Minimize section")

    # Running it again restores the section.
    palette.select_by_command_id("view.maximize_section")
    expect(center.get_active_ring()).not_to_have_attribute("data-maximized", "true")


@user_story("to reveal a panel from the palette without ever closing it")
def test_command_palette_show_panel_is_jump_only(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock for the view.toggle_panel.* commands: "Show X" reveals the
    # panel (activates it, expands its section, jumps there) and must NEVER close
    # it — running it again while the panel is already visible and active is just
    # a jump to its section. Not @release-marked: start_task_and_wait_for_ready
    # selects the Fake Claude model, which is gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cmd+K Show Panel WS")
    left = PlaywrightWorkspaceSection(page, "left")

    # First run: reveals the Files panel (seeded, open in the left section).
    palette = task_page.open_command_palette()
    palette.type_query("Show Files")
    palette.select_by_command_id("view.toggle_panel.files")
    expect(palette).not_to_be_visible()
    expect(left.get_panel_tab("files")).to_be_visible()
    expect(task_page.get_file_browser()).to_be_visible()

    # Second run while the panel is open, active, and its section expanded — the
    # panel must stay visible (a smart-toggle would close it here).
    blur_active_element(page)
    palette = task_page.open_command_palette_with_keyboard()
    palette.type_query("Show Files")
    palette.select_by_command_id("view.toggle_panel.files")
    expect(palette).not_to_be_visible()
    expect(left.get_panel_tab("files")).to_be_visible()
    expect(task_page.get_file_browser()).to_be_visible()


@user_story("to have the palette close after I toggle a section from Cmd+K")
def test_command_palette_section_toggle_closes_palette(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock for the view.toggle_{left,right,bottom}_panel commands: unlike
    # the jump-only "Show X" panel reveals, the section toggles act on chrome behind
    # the palette, so the palette must CLOSE to reveal the result. The right section
    # starts collapsed; toggling it from Cmd+K opens it and dismisses the palette.
    # Not @release-marked: start_task_and_wait_for_ready selects the Fake Claude model,
    # which is gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cmd+K Toggle Section WS")
    right = PlaywrightWorkspaceSection(page, "right")

    palette = task_page.open_command_palette()
    palette.type_query("Toggle right section")
    expect(palette.get_item_by_command_id("view.toggle_right_panel")).to_be_visible()
    palette.select_by_command_id("view.toggle_right_panel")
    expect(palette).not_to_be_visible()
    expect(right.get_header()).to_be_visible()


@user_story("to create and land on a new agent via the palette's Add panel flow")
def test_command_palette_add_panel_agent_create_navigates(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock for the addpanel.panels.new_agent row: it must share the
    # add-panel dropdown's create flow — create the agent, then NAVIGATE to it —
    # rather than creating it in the background and leaving the user on the old
    # agent. An empty prompt creates a single waiting agent with no LLM run.
    # Not @release-marked: the helper selects the Fake Claude model, which is
    # gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="", workspace_name="Cmd+K Add Panel Agent WS")

    tabs = PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()
    expect(tabs).to_have_count(1)
    url_before = page.url

    palette = task_page.open_command_palette()
    palette.select_by_command_id("addpanel.open")
    # Location page: put the new agent in the center.
    palette.select_by_command_id("addpanel.location.center")
    # Panel page: the pinned "New {recent} agent" row.
    palette.select_by_command_id("addpanel.panels.new_agent")

    # A second agent tab appears AND the route now points at the new agent —
    # the create navigated, exactly like the section "+" dropdown's flow.
    expect(palette).not_to_be_visible()
    expect(tabs).to_have_count(2)
    expect(page).not_to_have_url(url_before)


@user_story("to rename the current agent from the command palette")
def test_command_palette_agent_rename_starts_inline_edit(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock for the palette → inline-rename focus handoff: running the
    # agent "Rename" command must leave the tab's rename input mounted AND focused
    # after the palette closes. The palette suppresses its close-time focus restore
    # while a rename is pending — without that, the restore focuses whatever held
    # focus before the palette opened, and the resulting blur cancels the rename
    # instantly. An empty prompt creates a single waiting agent with no LLM run.
    # Not @release-marked: the helper selects the Fake Claude model, which is
    # gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="", workspace_name="Cmd+K Agent Rename WS")

    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    task_id = task_page.get_task_id()

    palette = task_page.open_command_palette()
    # "Agent actions..." pushes the agent.actions sub-page listing the current
    # agent's actions; the per-action command ids embed the agent's task id.
    palette.select_by_command_id("agents.actions.open")
    palette.select_by_command_id(f"agents.action.{task_id}.rename")

    expect(palette).not_to_be_visible()
    rename_input = panel_tabs.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    # Focus is the load-bearing assertion: a blur cancels the rename, and a bare
    # visibility check could pass transiently even if focus were stolen.
    expect(rename_input).to_be_focused()
    rename_input.fill("Palette Renamed Agent")
    rename_input.press("Enter")
    expect(rename_input).not_to_be_visible()
    expect(tabs.first).to_contain_text("Palette Renamed Agent")


@user_story("to create a new agent in the current workspace from the command palette")
def test_command_palette_creates_new_agent(sculptor_instance_: SculptorInstance) -> None:
    # Regression lock for the `nav.new_agent` command: inside a workspace it
    # must run the same create-agent path as the "+" tab button / the
    # `new_agent` keybinding (via runtime.ui.createAgent), adding a new agent
    # and navigating to it. An empty prompt creates a single waiting agent
    # with no LLM run, so the test stays fast and deterministic.
    # Not @release-marked: the helper selects the Fake Claude model, which
    # is gated off in packaged-release runs.
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="", workspace_name="Cmd+K New Agent")

    # Agents render as panel tabs in the center section (PANEL_TAB-agent:<id>).
    tabs = PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()
    expect(tabs).to_have_count(1)

    palette = task_page.open_command_palette()
    palette.type_query("New agent")
    # The command is gated on an active workspace, so it surfaces here.
    expect(palette.get_item_by_command_id("nav.new_agent")).to_be_visible()
    palette.select_by_command_id("nav.new_agent")

    # The palette auto-closes (not a keep-open command) and a second agent
    # tab appears — the command created and navigated to the new agent.
    expect(palette).not_to_be_visible()
    expect(tabs).to_have_count(2)
