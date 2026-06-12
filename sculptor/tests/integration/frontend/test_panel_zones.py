"""Integration tests for panel zone layout, visibility, and persistence.

Covers:
1. Zones auto-hide when the last panel is moved out.
2. Zones marked visible but with no panels auto-hide on load.
3. Stale (removed) panel IDs in localStorage are pruned on startup.
4. Newly registered panels appear for returning users with old localStorage.
5. Inner vertical split panel heights persist across navigation.
"""

import json

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_away_and_back
from sculptor.testing.playwright_utils import set_local_storage_items
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ── Zone auto-hide ────────────────────────────────────────────────────


@user_story("to have empty panel zones auto-hide when the last panel is moved out")
def test_zone_hides_when_last_panel_moved_out(sculptor_instance_: SculptorInstance) -> None:
    """Moving the last panel out of a top zone hides the zone when the bottom
    sibling has no panels to auto-promote upward.

    Steps:
    1. Create a workspace
    2. Move every default top-right panel (actions, skills) out to top-left
    3. Assert that the top-right zone is no longer visible
    4. Assert the actions icon is still accessible in the sidebar

    Bottom-right ships with no enabled panels in the default layout (notes
    is gated on ``defaultEnabled: false``), so the auto-promote invariant
    doesn't fire — no explicit setup needed.
    """
    page = sculptor_instance_.page
    zones = PlaywrightPanelZonesElement(page)

    # Step 1: Create a workspace
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Open the actions panel so we can verify the zone is visible
    # before we drain it, then move every top-right panel out one by one.
    actions_icon = zones.get_actions_icon()
    expect(actions_icon).to_be_visible()
    actions_icon.click()

    top_right = zones.get_top_right_zone()
    expect(top_right).to_be_visible()

    # The default top-right zone ships with both `actions` and `skills`
    # (browser/notes are gated on `defaultEnabled: false`). Drain both —
    # leaving either behind would keep the zone visible and defeat the test.
    zones.move_panel_to_zone(ElementIDs.PANEL_ICON_ACTIONS, "top-left")
    zones.move_panel_to_zone(ElementIDs.PANEL_ICON_SKILLS, "top-left")

    # Step 3: The top-right zone should now be hidden — it has no panels
    # and no bottom-right sibling to auto-promote into it.
    expect(top_right).not_to_be_visible()

    # Step 4: The actions icon should still be visible in the sidebar.
    expect(actions_icon).to_be_visible()


@user_story("to not see empty panel zones on startup")
def test_zone_with_no_panels_is_hidden_on_load(sculptor_instance_: SculptorInstance) -> None:
    """A zone marked visible in localStorage but with no panels should auto-hide.

    This covers a variant of the bug where, on a brand-new Sculptor install or
    after a state inconsistency, a zone's visibility is ``true`` in localStorage
    but no panels are assigned to it. The zone should not render as an empty,
    undismissable content area.

    Steps:
    1. Create a workspace (initializes panel state in localStorage)
    2. Inject inconsistent localStorage: bottom-right visible but no panels
    3. Navigate away and back to reinitialize from localStorage
    4. Assert the bottom-right zone is NOT visible (auto-healed)
    """
    page = sculptor_instance_.page
    zones = PlaywrightPanelZonesElement(page)

    # Step 1: Create a workspace so we have a valid workspace URL to return to
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Capture the workspace URL hash so we can reload to it after injecting localStorage
    current_url = page.url
    target_hash = "/#/" + current_url.split("#/", 1)[1] if "#/" in current_url else "/#/"

    # Step 2: Inject inconsistent localStorage state where bottom-right is
    # marked visible but has no panels assigned to it.  This simulates a
    # corrupted or stale state that can arise on fresh installs.
    zone_assignments = json.dumps(
        {
            "files": "top-right",
            "skills": "top-right",
            "terminal": "bottom",
            "actions": "top-right",  # actions moved away from bottom-right
        }
    )
    active_panel_per_zone = json.dumps(
        {
            "top-right": "files",
        }
    )
    zone_visibility = json.dumps(
        {
            "top-right": True,
            "bottom": False,
            "bottom-right": True,  # BUG: visible but has no panels
        }
    )
    zone_order = json.dumps(
        {
            "top-right": ["files", "skills", "actions"],
        }
    )

    set_local_storage_items(
        page,
        {
            "sculptor-zone-assignments": zone_assignments,
            "sculptor-active-panel-per-zone": active_panel_per_zone,
            "sculptor-zone-visibility": zone_visibility,
            "sculptor-zone-order": zone_order,
        },
    )

    # Step 3: Full SPA reload to tear down and recreate the page.
    # This forces Jotai atoms to reinitialize from the injected localStorage
    # values.  A hash-only SPA navigation would keep the old atom cache.
    full_spa_reload(page, target_hash)

    # Wait for the workspace page to load
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Step 4: The bottom-right zone should NOT be visible — it has no panels
    # assigned to it.  With the bug, this zone renders as an empty,
    # undismissable content area.
    bottom_right = zones.get_bottom_right_zone()
    expect(bottom_right).not_to_be_visible()

    # Cleanup: clear the injected localStorage so subsequent tests on this
    # xdist worker start with default panel state.  _reset_browser_state
    # (called by _pre_test) also clears localStorage and reloads, so this
    # is belt-and-suspenders.
    page.evaluate("localStorage.clear()")


# ── Stale panel pruning ───────────────────────────────────────────────


@user_story("to not see empty zones after a panel is removed in a new release")
def test_stale_panel_id_pruned_from_persisted_layout(sculptor_instance_: SculptorInstance) -> None:
    """A removed panel's ID lingering in localStorage should be pruned on startup.

    When a panel is deleted from the codebase (e.g. the "changes" panel),
    returning users still have its ID in their saved layout.  Without pruning,
    the zone reports having a panel (so it stays visible) but the registry
    can't find a component for it, rendering an empty zone.

    Steps:
    1. Create a workspace (initializes panel state in localStorage)
    2. Inject localStorage with a stale "changes" panel assigned to top-right
    3. Full SPA reload so the frontend reinitializes from the injected state
    4. Assert the stale panel is gone: top-right shows only registered panels
    5. Assert no empty zones are visible
    """
    page = sculptor_instance_.page
    zones = PlaywrightPanelZonesElement(page)

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    current_url = page.url
    target_hash = "/#/" + current_url.split("#/", 1)[1] if "#/" in current_url else "/#/"

    # Inject localStorage with a stale "changes" panel that no longer exists
    # in the registry, alongside the real panels.
    zone_assignments = json.dumps(
        {
            "files": "top-right",
            "changes": "top-right",  # stale — no longer registered
            "skills": "top-right",
            "terminal": "bottom",
            "actions": "bottom-right",
        }
    )
    active_panel_per_zone = json.dumps(
        {
            "top-right": "changes",  # active panel is the stale one
            "bottom-right": "actions",
        }
    )
    zone_visibility = json.dumps(
        {
            "top-right": True,
            "bottom": False,
            "bottom-right": True,
        }
    )
    zone_order = json.dumps(
        {
            "top-right": ["files", "changes", "skills"],
            "bottom-right": ["actions"],
        }
    )

    set_local_storage_items(
        page,
        {
            "sculptor-zone-assignments": zone_assignments,
            "sculptor-active-panel-per-zone": active_panel_per_zone,
            "sculptor-zone-visibility": zone_visibility,
            "sculptor-zone-order": zone_order,
        },
    )

    full_spa_reload(page, target_hash)

    # The files icon should still be visible — top-right has real panels.
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Top-right should be visible and showing a real panel (files or skills),
    # not an empty zone.  The pruning code falls back to the first remaining
    # panel in zone order, which is "files".
    top_right = zones.get_top_right_zone()
    expect(top_right).to_be_visible()

    # The File Browser panel should already be visible — after pruning the
    # stale "changes" active panel, the fallback activates "files" (the first
    # remaining panel in zone order).  Do NOT click the files icon here: since
    # files is already active, clicking would toggle the zone off.
    file_browser = zones.get_file_browser_panel()
    expect(file_browser).to_be_visible()

    # Bottom-right should also be visible with the actions panel (unaffected).
    bottom_right = zones.get_bottom_right_zone()
    expect(bottom_right).to_be_visible()


# ── New panel reconciliation ──────────────────────────────────────────


@user_story("to see newly added panels after updating Sculptor")
def test_new_panel_visible_after_loading_with_old_layout(sculptor_instance_: SculptorInstance) -> None:
    """A newly registered panel should be accessible even when the user has pre-existing panel state.

    Steps:
    1. Create a workspace and navigate to the agent page (initializes default panel layout)
    2. Inject old-format localStorage state that omits the "actions" panel
       (simulates an existing user whose layout was saved before the actions panel was added)
    3. Navigate away and back so the frontend re-initializes with the stale localStorage
    4. Assert that the actions panel icon is present in the sidebar
    """
    page = sculptor_instance_.page
    zones = PlaywrightPanelZonesElement(page)

    # Step 1: Create a workspace and navigate to the agent page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Wait for the workspace page to load — the "files" panel icon is always
    # visible (it's in the default layout's visible top-right zone).
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Step 2: Inject old localStorage state that is missing the "actions" panel.
    # This simulates an existing user who initialized their layout before
    # the actions panel was added.  The current panels are: files, skills,
    # terminal, actions.  We omit "actions" from the zone assignments.
    old_zone_assignments = json.dumps(
        {
            "files": "top-right",
            "skills": "top-right",
            "terminal": "bottom",
        }
    )
    old_active_panel_per_zone = json.dumps(
        {
            "top-right": "files",
        }
    )
    old_zone_visibility = json.dumps(
        {
            "top-right": True,
            "bottom": False,
        }
    )
    old_zone_order = json.dumps(
        {
            "top-right": ["files", "skills"],
        }
    )

    set_local_storage_items(
        page,
        {
            "sculptor-zone-assignments": old_zone_assignments,
            "sculptor-active-panel-per-zone": old_active_panel_per_zone,
            "sculptor-zone-visibility": old_zone_visibility,
            "sculptor-zone-order": old_zone_order,
        },
    )

    # Step 3: Navigate away and back so the frontend re-initializes with the stale localStorage
    navigate_away_and_back(page)

    # Wait for the workspace page to load again
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Step 4: Assert that the actions panel icon is present.
    # With the bug, the actions panel icon will NOT be present because
    # the old localStorage state doesn't include it, and there's no
    # reconciliation to add missing panels.
    actions_icon = zones.get_actions_icon()
    expect(actions_icon).to_be_visible()

    # Cleanup: clear injected localStorage so subsequent tests on this
    # xdist worker start with default panel state.
    page.evaluate("localStorage.clear()")


# ── Panel height persistence ──────────────────────────────────────────


@user_story("to have sidebar panel heights persist after resizing them")
def test_inner_vertical_split_height_persists_after_navigation(sculptor_instance_: SculptorInstance) -> None:
    """Inner vertical split sizes should persist in localStorage and be restored after navigation.

    Steps:
    1. Create a workspace and navigate to the agent page
    2. Ensure both top-right and bottom-right zones are visible
    3. Use keyboard to resize the vertical split between top-right and
       bottom-right panels, making bottom-right taller
    4. Navigate away and back so the frontend re-initializes from localStorage
    5. Assert that the bottom-right panel is still taller than the top-right
       panel (i.e. the resized heights were persisted and restored)
    """
    page = sculptor_instance_.page
    zones = PlaywrightPanelZonesElement(page)

    # Step 1: Create a workspace and navigate to the agent page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    # Step 2: Ensure both top-right and bottom-right zones are visible.
    # Move files to top-right and actions to bottom-right via the UI so
    # the test works regardless of the default panel layout.
    files_icon = zones.get_files_icon()
    actions_icon = zones.get_actions_icon()
    expect(files_icon).to_be_visible()
    expect(actions_icon).to_be_visible()

    # Open files and move it to top-right.
    files_icon.click()
    zones.move_panel_to_zone(ElementIDs.PANEL_ICON_FILES, "top-right")

    # Open actions and move it to bottom-right.
    actions_icon.click()
    zones.move_panel_to_zone(ElementIDs.PANEL_ICON_ACTIONS, "bottom-right")

    top_right_panel = zones.get_top_right_zone()
    bottom_right_panel = zones.get_bottom_right_zone()
    expect(top_right_panel).to_be_visible()
    expect(bottom_right_panel).to_be_visible()

    # Find the vertical resize handle inside the right-area panel.
    # react-resizable-panels renders handles with role="separator" and
    # tabIndex=0, supporting keyboard-based resize via arrow keys.
    resize_handle = zones.get_right_resize_handle()
    expect(resize_handle).to_be_visible()

    # Focus the resize handle and press ArrowUp 3 times to move it upward
    # by ~30%, making bottom-right significantly taller than top-right.
    resize_handle.focus()
    for _ in range(3):
        page.keyboard.press("ArrowUp")

    # Verify the resize took effect — bottom-right should now be taller
    resized_top_box = top_right_panel.bounding_box()
    resized_bottom_box = bottom_right_panel.bounding_box()
    assert resized_top_box is not None
    assert resized_bottom_box is not None
    assert resized_bottom_box["height"] > resized_top_box["height"], (
        "After keyboard resize, bottom-right panel should be taller than top-right panel."
        + f" top={resized_top_box['height']:.0f}, bottom={resized_bottom_box['height']:.0f}"
    )

    # Record the height ratio after resize to compare after navigation
    resized_ratio = resized_bottom_box["height"] / (resized_top_box["height"] + resized_bottom_box["height"])

    # Step 3: Navigate away and back to force the Jotai store to
    # reinitialize and re-read the updated values from localStorage.
    navigate_away_and_back(page)

    # Wait for the workspace page to fully load
    files_icon = zones.get_files_icon()
    expect(files_icon).to_be_visible()

    # Step 4: Assert that the panel heights were restored from localStorage.
    # With the bug, the DockingLayout component always renders inner panels
    # at 50/50 regardless of what was saved, because there is no onLayout
    # handler and defaultSize is hardcoded to 50.
    top_right_panel = zones.get_top_right_zone()
    bottom_right_panel = zones.get_bottom_right_zone()

    expect(top_right_panel).to_be_visible()
    expect(bottom_right_panel).to_be_visible()

    restored_top_box = top_right_panel.bounding_box()
    restored_bottom_box = bottom_right_panel.bounding_box()

    assert restored_top_box is not None, "top-right panel should have a bounding box"
    assert restored_bottom_box is not None, "bottom-right panel should have a bounding box"

    # The restored ratio should be close to what we set via keyboard resize.
    # Allow some tolerance for rounding and resize handle size.
    restored_ratio = restored_bottom_box["height"] / (restored_top_box["height"] + restored_bottom_box["height"])
    assert abs(restored_ratio - resized_ratio) < 0.1, (
        f"Expected restored height ratio (~{resized_ratio:.0%}) to match"
        + f" the resized ratio, but got {restored_ratio:.0%}."
        + f" top-right height={restored_top_box['height']:.0f},"
        + f" bottom-right height={restored_bottom_box['height']:.0f}"
    )
