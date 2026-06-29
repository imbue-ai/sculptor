"""Integration tests for zen mode and focus mode."""

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.elements.panels import ensure_right_area_visible
from sculptor.testing.elements.zen_mode import PlaywrightZenModeElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import dispatch_modified_shortcuts_in_one_task
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to maximize chat space by hiding all UI chrome and panels with zen mode")
def test_zen_mode_hides_chrome_and_panels(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+Shift+\\ should hide TopBar, BottomBar, AgentTabs, and panels.

    Steps:
    1. Create a workspace (default layout has panels visible)
    2. Assert UI chrome elements are visible
    3. Press Cmd+Shift+\\ to enter zen mode
    4. Assert all UI chrome is hidden
    5. Assert the exit zen mode button appears
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create a workspace
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Verify UI chrome is visible. Ensure the right area is open
    # (the default layout may not have it visible).
    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)
    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    agent_tab = agent_tab_bar.get_agent_tabs()
    right_area = panel_zones.get_right_area()

    ensure_right_area_visible(page)

    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()
    expect(agent_tab.first).to_be_visible()
    expect(right_area).to_be_visible()

    # Step 3: Press Cmd+Shift+\\ to enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")

    # Step 4: All chrome and panels should be hidden
    expect(top_bar).not_to_be_visible()
    expect(bottom_bar).not_to_be_visible()
    expect(agent_tab.first).not_to_be_visible()
    expect(right_area).not_to_be_visible()

    # Step 5: Exit button should appear when hovering the top-left hot zone
    exit_button = zen.get_exit_button()
    zen.hover_exit_hot_zone()
    expect(exit_button).to_be_visible()


@user_story("to restore all UI chrome and panels when exiting zen mode")
def test_zen_mode_toggle_restores_everything(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+Shift+\\ twice should restore the UI to its original state.

    Steps:
    1. Create a workspace
    2. Enter zen mode
    3. Press Cmd+Shift+\\ again to exit
    4. Assert all chrome and panels are restored
    5. Exit button should disappear
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    right_area = panel_zones.get_right_area()

    # Ensure right area is visible before testing zen mode save/restore.
    ensure_right_area_visible(page)
    expect(right_area).to_be_visible()

    # Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()

    # Exit zen mode
    page.keyboard.press(f"{mod}+Shift+\\")

    # Everything restored
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()
    expect(right_area).to_be_visible()

    # Exit button should disappear
    exit_zen_button = zen.get_exit_button()
    expect(exit_zen_button).not_to_be_visible()


@user_story("to exit both zen mode and focus mode via Cmd+\\ (full escape)")
def test_focus_mode_toggle_exits_zen_mode(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+\\ while in zen mode should exit both zen and focus mode.

    Steps:
    1. Create a workspace
    2. Enter zen mode (Cmd+Shift+\\)
    3. Press Cmd+\\ (focus mode toggle)
    4. Assert everything is restored — both zen and focus mode exited
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    right_area = panel_zones.get_right_area()

    # Ensure right area is visible before testing zen mode save/restore.
    ensure_right_area_visible(page)
    expect(right_area).to_be_visible()

    # Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()

    # Press Cmd+\\ to fully exit
    page.keyboard.press(f"{mod}+\\")

    # Everything should be restored
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()
    expect(right_area).to_be_visible()

    # Exit zen button should not be visible
    exit_zen_button = zen.get_exit_button()
    expect(exit_zen_button).not_to_be_visible()


@user_story("to keep focus mode active when exiting zen mode that was entered on top of it")
def test_zen_mode_preserves_preexisting_focus_mode(sculptor_instance_: SculptorInstance) -> None:
    """If focus mode was active before entering zen, exiting zen should leave focus mode active.

    Steps:
    1. Create a workspace
    2. Enter focus mode (Cmd+\\) — panels hidden, chrome visible
    3. Enter zen mode (Cmd+Shift+\\) — chrome also hidden
    4. Exit zen mode (Cmd+Shift+\\)
    5. Assert chrome is restored but panels remain hidden (focus mode still active)
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    right_area = panel_zones.get_right_area()

    # Step 2: Enter focus mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+\\")

    # Panels hidden, chrome still visible
    expect(right_area).not_to_be_visible()
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()

    # Step 3: Enter zen mode on top of focus mode
    page.keyboard.press(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()

    # Step 4: Exit zen mode
    page.keyboard.press(f"{mod}+Shift+\\")

    # Step 5: Chrome restored, panels still hidden (focus mode persists)
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()
    expect(right_area).not_to_be_visible()


@user_story("to use the exit zen mode button to leave zen mode")
def test_exit_zen_mode_button_works(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the 'Exit zen mode' button should exit zen mode.

    Steps:
    1. Create a workspace
    2. Enter zen mode
    3. Click the exit button
    4. Assert all chrome is restored
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()

    # Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()

    # Hover hot zone to reveal exit button, then click it
    exit_button = zen.get_exit_button()
    zen.hover_exit_hot_zone()
    expect(exit_button).to_be_visible()
    exit_button.click(force=True)

    # Chrome should be restored
    expect(top_bar).to_be_visible()
    expect(exit_button).not_to_be_visible()


@user_story("to use focus mode independently to hide only panels")
def test_focus_mode_hides_panels_but_keeps_chrome(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+\\ should hide panels but keep TopBar, BottomBar, and AgentTabs.

    Steps:
    1. Create a workspace
    2. Press Cmd+\\ to enter focus mode
    3. Assert panels are hidden but chrome is visible
    4. Press Cmd+\\ again to exit
    5. Assert panels are restored
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    right_area = panel_zones.get_right_area()

    # Ensure right area is visible before testing focus mode save/restore.
    ensure_right_area_visible(page)
    expect(right_area).to_be_visible()

    # Enter focus mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+\\")

    # Panels hidden, chrome visible
    expect(right_area).not_to_be_visible()
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()

    # Exit focus mode
    page.keyboard.press(f"{mod}+\\")

    # Everything restored
    expect(right_area).to_be_visible()


@user_story("to toggle panels in zen mode and have changes persist on exit")
def test_panel_toggle_in_zen_mode_persists_on_exit(sculptor_instance_: SculptorInstance) -> None:
    """Toggling a panel while in zen mode should show/hide it immediately,
    and the change should persist when exiting zen mode.

    Steps:
    1. Create a workspace (bottom panel visible by default)
    2. Enter zen mode (all panels hidden)
    3. Press Cmd+Shift+B (toggle bottom panel) — panel appears
    4. Verify still in zen mode
    5. Exit zen mode
    6. Assert bottom panel is still visible (change persisted)
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    layout = PlaywrightProjectLayoutPage(page)
    panel_zones = PlaywrightPanelZonesElement(page)

    top_bar = layout.get_top_bar_locator()
    bottom_bar = layout.get_bottom_bar()
    right_area = panel_zones.get_right_area()

    # Ensure right area is visible before entering zen mode.
    ensure_right_area_visible(page)
    expect(right_area).to_be_visible()

    # Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()
    expect(right_area).not_to_be_visible()

    # Toggle the right panel open during zen mode
    page.keyboard.press(f"{mod}+Alt+ArrowRight")
    expect(right_area).to_be_visible()

    # Still in zen mode (chrome still hidden)
    expect(top_bar).not_to_be_visible()

    # Exit zen mode
    page.keyboard.press(f"{mod}+Shift+\\")

    # Chrome is restored and the right panel is still visible (change persisted)
    expect(top_bar).to_be_visible()
    expect(bottom_bar).to_be_visible()
    expect(right_area).to_be_visible()


@user_story("to navigate between workspace tabs using Cmd+[ and Cmd+] while in zen mode")
def test_workspace_tab_navigation_works_in_zen_mode(sculptor_instance_: SculptorInstance) -> None:
    """Workspace tab shortcuts (Cmd+] / Cmd+[) must still work when zen mode is active.

    The TopBar (which hosts the keyboard listeners for tab cycling) must stay
    mounted even though it is visually hidden in zen mode.

    Steps:
    1. Create two workspaces
    2. Enter zen mode
    3. Press Cmd+] to cycle to the next workspace tab
    4. Assert the URL changed to the other workspace
    5. Press Cmd+[ to cycle back
    6. Assert the URL returned to the first workspace
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create two workspaces
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Task A", workspace_name="WS A")
    first_workspace_url = page.url

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Task B", workspace_name="WS B")
    second_workspace_url = page.url

    # Sanity: we're on the second workspace and URLs differ
    assert first_workspace_url != second_workspace_url

    layout = PlaywrightProjectLayoutPage(page)
    top_bar = layout.get_top_bar_locator()

    # Step 2: Enter zen mode. Use press_keyboard_shortcut (not raw keyboard.press)
    # for every chord here: macOS Chromium occasionally drops the modifier keyup
    # between back-to-back chords, leaving Cmd "held" so the next chord arrives
    # malformed and is swallowed. press_keyboard_shortcut releases the modifier
    # after each chord.
    blur_active_element(page)
    layout.press_keyboard_shortcut(f"{mod}+Shift+\\")
    expect(top_bar).not_to_be_visible()

    # Step 3: Press Cmd+] to cycle to next tab (wraps to first workspace)
    layout.press_keyboard_shortcut(f"{mod}+]")
    page.wait_for_url(f"**{first_workspace_url.split('#')[-1]}**")

    # Step 5: Press Cmd+[ to cycle back to second workspace
    layout.press_keyboard_shortcut(f"{mod}+[")
    page.wait_for_url(f"**{second_workspace_url.split('#')[-1]}**")


@user_story("to rapidly cycle workspace tabs in zen mode without a stale-route no-op")
def test_rapid_tab_navigation_reads_live_route_in_zen_mode(sculptor_instance_: SculptorInstance) -> None:
    """Two tab-cycle keypresses fired back-to-back must each cycle from the
    *current* route, not a stale one.

    Regression test for SCU-1633. The tab-cycle keydown listener computed the
    active tab from React route state, which lags ``window.location`` because the
    listener (a passive effect) only re-registers with a fresh closure after React
    commits and flushes effects — and react-router defers the route-state update
    into a transition. ``navigate()`` to a loaderless agent route updates
    ``window.location.hash`` synchronously, so a second keypress arriving before
    React catches up cycled from the *previous* active tab and landed back where it
    started, hanging ``wait_for_url``.

    We reproduce that timing deterministically by dispatching both keydown events
    synchronously in a single task (via ``dispatch_modified_shortcuts_in_one_task``)
    — React cannot re-render between them, so the listener's closure is guaranteed
    stale for the second press. With the bug present, the back-press is a no-op;
    with the fix (reading the live hash) it returns to the starting workspace.

    Steps:
    1. Create two workspaces (ending on the second).
    2. Enter zen mode.
    3. Synchronously dispatch Cmd+] then Cmd+[ on ``window``.
    4. The forward press must change the route (proves the events are handled).
    5. The back press must return to the starting route (the fix).
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create two workspaces; we end up on the second.
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Task A", workspace_name="WS A")
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Task B", workspace_name="WS B")

    # Step 2: Enter zen mode.
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")

    layout = PlaywrightProjectLayoutPage(page)
    expect(layout.get_top_bar_locator()).not_to_be_visible()

    # Step 3: fire Cmd+] then Cmd+[ back-to-back, before React can re-render and
    # re-register the keydown listener with a fresh closure.
    blur_active_element(page)
    before, after_forward, after_back = dispatch_modified_shortcuts_in_one_task(
        page, [("]", "BracketRight"), ("[", "BracketLeft")]
    )

    # Step 4: the forward press must have actually navigated; otherwise the
    # synthetic events were not handled and the back-press assertion below would
    # pass vacuously.
    assert after_forward != before, (
        f"Cmd+] did not change the route — the synthetic events were not handled: {(before, after_forward, after_back)}"
    )
    # Step 5: the back press must return to the starting workspace. With the
    # stale-closure bug it cycles from the previous active tab and stays on the
    # forward tab.
    assert after_back == before, (
        f"Cmd+[ did not return to the starting workspace (stale-route cycle): {(before, after_forward, after_back)}"
    )


@user_story("to verify the exit button is hidden by default when entering zen mode")
def test_exit_button_hidden_by_default_in_zen_mode(sculptor_instance_: SculptorInstance) -> None:
    """The exit zen mode button should be in the DOM but not visible without hovering.

    Steps:
    1. Create a workspace
    2. Enter zen mode
    3. Assert the exit button is attached to the DOM
    4. Assert the exit button is NOT visible (opacity 0, pointer-events none)
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create a workspace
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")

    layout = PlaywrightProjectLayoutPage(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    expect(top_bar).not_to_be_visible()

    # Step 3: The exit button element exists in the DOM
    exit_button = zen.get_exit_button()
    expect(exit_button).to_be_attached()

    # Step 4: But it is not visible (opacity: 0)
    expect(exit_button).not_to_be_visible()


@user_story("to reveal the exit button by hovering over the top-left hot zone")
def test_exit_button_appears_on_hover(sculptor_instance_: SculptorInstance) -> None:
    """Hovering over the top-left hot zone should reveal the exit zen mode button.

    Steps:
    1. Create a workspace
    2. Enter zen mode
    3. Move the mouse into the top-left hot zone area
    4. Assert the exit button becomes visible
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create a workspace
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")

    layout = PlaywrightProjectLayoutPage(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    expect(top_bar).not_to_be_visible()

    exit_button = zen.get_exit_button()
    expect(exit_button).not_to_be_visible()

    # Step 3: Hover the top-left hot zone (200x80px area)
    zen.hover_exit_hot_zone()

    # Step 4: The exit button should now be visible
    expect(exit_button).to_be_visible()


@user_story("to auto-hide the exit button when the mouse leaves the hot zone")
def test_exit_button_disappears_on_mouse_leave(sculptor_instance_: SculptorInstance) -> None:
    """Moving the mouse away from the hot zone should hide the exit button again.

    Steps:
    1. Create a workspace
    2. Enter zen mode
    3. Hover the top-left hot zone to reveal the exit button
    4. Move the mouse far away from the hot zone
    5. Assert the exit button becomes not visible again
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Create a workspace
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Enter zen mode
    blur_active_element(page)
    page.keyboard.press(f"{mod}+Shift+\\")

    layout = PlaywrightProjectLayoutPage(page)
    zen = PlaywrightZenModeElement(page)

    top_bar = layout.get_top_bar_locator()
    expect(top_bar).not_to_be_visible()

    # Step 3: Hover the hot zone to reveal the button
    zen.hover_exit_hot_zone()
    exit_button = zen.get_exit_button()
    expect(exit_button).to_be_visible()

    # Step 4: Move the mouse far away from the hot zone
    page.mouse.move(500, 500)

    # Step 5: The exit button should hide again (after 150ms delay)
    expect(exit_button).not_to_be_visible()
