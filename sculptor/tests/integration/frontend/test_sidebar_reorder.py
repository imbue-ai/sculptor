"""Integration tests for drag-to-reorder in the workspace sidebar.

Workspace rows (within their repo group) and repo groups are dnd-kit sortables.
The drags are driven through the KeyboardSensor (focus → Space → arrows → Space),
the same Playwright-drivable pipeline as panel drags. The custom order persists
in the global layout snapshot, and keyboard workspace cycling (Meta+] / Meta+[)
follows the visible order.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import PlaywrightWorkspaceSidebarElement
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import create_zero_agent_workspace
from sculptor.testing.playwright_utils import get_active_project_id_by_name
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _create_workspaces(page: Page, names: list[str]) -> None:
    """Create one workspace per name (agent idle); rows render alphabetically."""
    for name in names:
        start_task_and_wait_for_ready(page, workspace_name=name)


@user_story("to re-order my workspaces in the sidebar by dragging a row")
def test_reorder_workspace_row_via_keyboard_drag(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Dragging a workspace row one slot down re-orders the list.

    Persistence of the custom order across sessions is covered at the unit level
    (sidebarWorkspaceOrder.test.ts drives the layout-persistence adapter); this
    test proves the drag pipeline and the rendered order.

    Steps:
    1. Create three workspaces; they render alphabetically (A, B, C).
    2. Drag row A one slot down via the keyboard sensor.
    3. Verify the rendered order is B, A, C.
    """
    page = sculptor_instance_.page

    # Step 1: Three workspaces, alphabetical by name.
    _create_workspaces(page, ["Reorder WS A", "Reorder WS B", "Reorder WS C"])

    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(3)
    expect(rows).to_contain_text(["Reorder WS A", "Reorder WS B", "Reorder WS C"])

    # Step 2: Drag A below B.
    sidebar.reorder_via_keyboard_drag(
        item=sidebar.get_workspace_row_by_name("Reorder WS A"),
        target=sidebar.get_workspace_row_by_name("Reorder WS B"),
        direction="down",
    )

    # Step 3: The rendered order reflects the drop.
    expect(rows).to_contain_text(["Reorder WS B", "Reorder WS A", "Reorder WS C"])


@user_story("to re-order my workspaces in the sidebar by dragging a row with the mouse")
def test_reorder_workspace_row_via_pointer_drag(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dragging a row to another row's bottom/top half re-orders the list.

    The pointer path resolves the slot geometrically on the move stream — the
    row lands on whichever side of the target row's midpoint the pointer rests
    on — so both parks aim off-center: the midpoint itself is the ambiguous
    point the rule splits on.

    Steps:
    1. Create three workspaces; they render alphabetically (A, B, C).
    2. Pointer-drag row A to row B's bottom half and drop → B, A, C.
    3. Pointer-drag row A back to row B's top half and drop → A, B, C.
    """
    page = sculptor_instance_.page

    # Step 1: Three workspaces, alphabetical by name.
    _create_workspaces(page, ["Pointer WS A", "Pointer WS B", "Pointer WS C"])
    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(3)
    expect(rows).to_contain_text(["Pointer WS A", "Pointer WS B", "Pointer WS C"])

    # Step 2: Park in B's bottom half — A lands after B.
    sidebar.drag_via_pointer(
        item=sidebar.get_workspace_row_by_name("Pointer WS A"),
        waypoints=[sidebar.get_workspace_row_by_name("Pointer WS B")],
        y_offsets=[8],
    )
    expect(rows).to_contain_text(["Pointer WS B", "Pointer WS A", "Pointer WS C"])

    # Step 3: Park in B's top half — A lands back before B.
    sidebar.drag_via_pointer(
        item=sidebar.get_workspace_row_by_name("Pointer WS A"),
        waypoints=[sidebar.get_workspace_row_by_name("Pointer WS B")],
        y_offsets=[-8],
    )
    expect(rows).to_contain_text(["Pointer WS A", "Pointer WS B", "Pointer WS C"])


@user_story("to cancel a sidebar drag with Escape without changing anything")
def test_escape_cancels_drag_and_releases_drag_state(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Escape mid-drag leaves the order unchanged and releases the drag state.

    The release matters beyond the drag itself: the hover peek is suppressed
    while a drag is active, so a cancel that stranded the drag flag would
    silently disable the peek for the rest of the session.

    Steps:
    1. Create two workspaces and pick up the first row (Space).
    2. Press Escape and verify the drag flag clears and the order is unchanged.
    3. Hover a row and verify the peek popover still opens.
    """
    page = sculptor_instance_.page

    # Step 1: Two workspaces; pick up row A.
    _create_workspaces(page, ["Cancel WS A", "Cancel WS B"])
    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)
    row_a = sidebar.get_workspace_row_by_name("Cancel WS A")
    sidebar.pickup_via_keyboard(row_a)

    # Step 2: Escape cancels — flag cleared, order unchanged.
    page.keyboard.press("Escape")
    expect(row_a).not_to_have_attribute("data-sidebar-dragging", "true")
    expect(rows).to_contain_text(["Cancel WS A", "Cancel WS B"])

    # Step 3: The peek popover still opens on hover (drag suppression released).
    sidebar.get_workspace_row_by_name("Cancel WS B").hover()
    peek = PlaywrightProjectLayoutPage(page=page).get_workspace_peek_popover()
    expect(peek).to_be_visible()


@user_story("to cycle workspaces with the keyboard in the same order the sidebar shows")
def test_keyboard_cycling_follows_custom_order(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After a drag re-order, Meta+] steps through the sidebar's visible order.

    Steps:
    1. Create three workspaces (alphabetical: A, B, C) and drag A below B.
    2. Navigate to the top row's workspace (B).
    3. Press next-workspace twice and verify it visits A then C — the visible
       order, not the alphabetical one.
    """
    page = sculptor_instance_.page
    mod = get_playwright_modifier_key()

    # Step 1: Three workspaces, then drag A below B (visible order: B, A, C).
    _create_workspaces(page, ["Cycle Order WS A", "Cycle Order WS B", "Cycle Order WS C"])
    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(3)
    sidebar.reorder_via_keyboard_drag(
        item=sidebar.get_workspace_row_by_name("Cycle Order WS A"),
        target=sidebar.get_workspace_row_by_name("Cycle Order WS B"),
        direction="down",
    )
    expect(rows).to_contain_text(["Cycle Order WS B", "Cycle Order WS A", "Cycle Order WS C"])

    # The rows stamp their workspace ids; cycling is asserted against the URL.
    # expect() each attribute first so the one-shot reads below can't race a
    # re-render.
    for index in range(3):
        expect(rows.nth(index)).to_have_attribute("data-workspace-id", re.compile(r".+"))
    row_ids = [rows.nth(index).get_attribute("data-workspace-id") for index in range(3)]

    # Step 2: Anchor on the top row's workspace (B).
    navigate_to_workspace(page, "Cycle Order WS B")
    expect(page).to_have_url(re.compile(re.escape(f"/ws/{row_ids[0]}")))

    # Step 3: Next-workspace follows the visible order: B → A → C.
    blur_active_element(page)
    page.keyboard.press(f"{mod}+]")
    expect(page).to_have_url(re.compile(re.escape(f"/ws/{row_ids[1]}")))
    blur_active_element(page)
    page.keyboard.press(f"{mod}+]")
    expect(page).to_have_url(re.compile(re.escape(f"/ws/{row_ids[2]}")))


@user_story("to re-order the repo groups in the sidebar by dragging a repo header")
def test_reorder_repo_groups_via_keyboard_drag(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """Dragging the bottom repo-group header one slot up swaps the group order.

    Steps:
    1. Create a workspace in the default repo, then add a second repo and create
       a workspace in it (a repo group only renders once it has a workspace).
    2. Drag the bottom group's header above the top group's.
    3. Verify the group order is swapped.
    """
    page = sculptor_instance_.page

    # Step 1: A workspace in each of two repos.
    start_task_and_wait_for_ready(page, workspace_name="Group Reorder WS A")
    second_repo = test_repo_factory_.create_repo(name="sidebar-reorder-repo", branch="main")
    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_repositories().add_repo(str(second_repo.base_path.resolve()))
    open_new_workspace_form(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name("sidebar-reorder-repo")
    start_task_and_wait_for_ready(page, workspace_name="Group Reorder WS B")

    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    groups = sidebar.get_repo_groups()
    expect(groups).to_have_count(2)
    # The initial (alphabetical) order depends on the harness repo's name, so
    # capture it and assert the drag swaps whatever it was. The drag itself uses
    # name-scoped locators: the positional nth(...) locators re-resolve against
    # the post-drop order, so the helper's guards would check the wrong element.
    top_name = groups.nth(0).inner_text()
    bottom_name = groups.nth(1).inner_text()

    # Step 2: Drag the bottom group above the top one.
    sidebar.reorder_via_keyboard_drag(
        item=sidebar.get_repo_group_by_name(bottom_name),
        target=sidebar.get_repo_group_by_name(top_name),
        direction="up",
    )

    # Step 3: The group order is swapped.
    expect(groups).to_contain_text([bottom_name, top_name])


# Repo groups render expanded by default (isRepoCollapsedAtomFamily defaults to false),
# independent of workspace count; the count only affects the group's height. This many
# rows makes the expanded group tall enough that its collision-rect centre sits far past
# a single-workspace neighbour's — the condition under which closestCenter can never make
# `over` leave the dragged group, so it never reorders. Eight clears the
# ~3x-neighbour-height margin with room to spare, without slowing the test by creating
# needless workspaces.
_TALL_GROUP_WORKSPACE_COUNT = 8


def _build_short_and_tall_repo_groups(
    page: Page, test_repo_factory: TestRepoFactory, tall_repo_name: str
) -> tuple[PlaywrightWorkspaceSidebarElement, Locator, str, str, list[str]]:
    """Build a short repo group (default repo, one workspace) and a tall one.

    The tall group is a second repo piled with ``_TALL_GROUP_WORKSPACE_COUNT`` agent-less
    workspaces (created straight through the API so it stays cheap), expanded by default so
    its height dwarfs the short group's. Returns the sidebar POM, the repo-group locator,
    the tall and short project ids, and the initial top→bottom group-id order.
    """
    create_zero_agent_workspace(page, description="Short Repo WS")

    tall_repo = test_repo_factory.create_repo(name=tall_repo_name, branch="main")
    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_repositories().add_repo(str(tall_repo.base_path.resolve()))
    tall_project_id = get_active_project_id_by_name(page, tall_repo_name)
    for index in range(_TALL_GROUP_WORKSPACE_COUNT):
        create_zero_agent_workspace(page, description=f"Tall Repo WS {index}", project_id=tall_project_id)

    sidebar = PlaywrightTaskPage(page).get_workspace_sidebar()
    groups = sidebar.get_repo_groups()
    expect(groups).to_have_count(2)
    # Pin each group's id before the drag (expect() first so the one-shot reads can't race a
    # re-render). The short group is simply whichever isn't the tall one.
    for index in range(2):
        expect(groups.nth(index)).to_have_attribute("data-project-id", re.compile(r".+"))
    initial_ids = [groups.nth(index).get_attribute("data-project-id") for index in range(2)]
    short_project_id = initial_ids[0] if initial_ids[1] == tall_project_id else initial_ids[1]
    return sidebar, groups, tall_project_id, short_project_id, initial_ids


@user_story("to re-order a big expanded repo group by dragging it with the mouse")
def test_reorder_tall_expanded_repo_group_via_pointer_drag(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """A pointer drag reorders a repo group that is expanded and full of workspaces.

    This is the pointer-drag counterpart to ``test_reorder_repo_groups_via_keyboard_drag``.
    The keyboard sensor steps the dragged item's rect straight onto the target slot, so a
    keyboard drag never depends on the group's height. A mouse drag does — the group's
    collision rect is its full expanded height — so only this path exercises the collision
    detection a tall group's reorder relies on. A tall group whose ``over`` never leaves
    itself can be dragged but never reordered.

    Steps:
    1. Create a short repo group (default repo, one workspace) and a tall one (a second
       repo piled with many workspaces, expanded by default).
    2. Drag the tall group past the short one with the mouse.
    3. Verify the two groups swapped — the reorder registered.
    """
    page = sculptor_instance_.page

    # Step 1: A short group and a tall one.
    sidebar, groups, tall_project_id, short_project_id, initial_ids = _build_short_and_tall_repo_groups(
        page, test_repo_factory_, "tall-reorder-repo"
    )

    # Step 2: Drag the tall group past the short one with the mouse.
    sidebar.reorder_via_pointer_drag(
        item=sidebar.get_repo_group_by_project_id(tall_project_id),
        target=sidebar.get_repo_group_by_project_id(short_project_id),
    )

    # Step 3: The two groups swapped — dragging the tall group past the short one moved
    # it into the other slot.
    expect(groups.nth(0)).to_have_attribute("data-project-id", initial_ids[1])
    expect(groups.nth(1)).to_have_attribute("data-project-id", initial_ids[0])


@user_story("to re-order a big expanded repo group even when I drag past the sidebar")
def test_reorder_tall_group_when_dragged_past_the_container_edge(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """A pointer drag that overshoots past the container still reorders (no snap-back).

    The drop resolves from the dragged element's rectangle, which restrictToParentElement
    holds inside the list, so it always overlaps some group — even when the pointer runs
    well past the container edge. That keeps ``over`` pinned to the extreme group rather than
    dropping out; a null ``over`` would zero dnd-kit's active-item transform (it only offsets
    the dragged item while ``overIndex`` is valid) and snap the item back to its origin.

    Steps:
    1. Create a short repo group and a tall one.
    2. Drag the tall group and overshoot well past the short group, beyond the container.
    3. Verify the two groups still swapped — ``over`` stayed pinned to the extreme group.
    """
    page = sculptor_instance_.page

    # Step 1: A short group and a tall one.
    sidebar, groups, tall_project_id, short_project_id, initial_ids = _build_short_and_tall_repo_groups(
        page, test_repo_factory_, "tall-overshoot-repo"
    )

    # Step 2: Drag the tall group and overshoot past the short group / container edge.
    sidebar.reorder_via_pointer_drag(
        item=sidebar.get_repo_group_by_project_id(tall_project_id),
        target=sidebar.get_repo_group_by_project_id(short_project_id),
        overshoot=True,
    )

    # Step 3: The groups still swapped — the clamped pointer kept the extreme group as the
    # drop target instead of dropping out and snapping the dragged group back.
    expect(groups.nth(0)).to_have_attribute("data-project-id", initial_ids[1])
    expect(groups.nth(1)).to_have_attribute("data-project-id", initial_ids[0])
