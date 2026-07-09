"""Integration tests for workspace groups in the sidebar.

Workspace groups are an experimental feature (Settings → Experimental →
"Workspace Groups"): named, colored cards that collect related workspace rows
inside their repo section. These tests drive the load-bearing flows end to
end through the real UI — the flag gate, creating and joining groups through
the workspace row menu, managing a group through its header menu, the
dissolve rules (a group never exists empty), and drag-driven membership moves
via the same keyboard drag pipeline as test_sidebar_reorder.py.

The flag is always enabled through the Settings toggle rather than seeded
state; the sidebar persists across routes, so the tests act on it directly
from wherever the toggle leaves them.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import PlaywrightWorkspaceSidebarElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_workspaces(page: Page, names: list[str]) -> None:
    """Create one workspace per name (agent idle); rows render alphabetically."""
    for name in names:
        start_task_and_wait_for_ready(page, workspace_name=name)


def _enable_workspace_groups(page: Page) -> None:
    """Turn on the workspace-groups experiment through the real Settings toggle."""
    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_experimental().enable_workspace_groups()


def _create_single_group(page: Page, names: list[str], group_seed_name: str) -> PlaywrightWorkspaceSidebarElement:
    """Arrange the common precondition: workspaces, the flag on, and one group.

    Creates a workspace per name, enables the flag, and wraps the row named
    ``group_seed_name`` in a new group via "New group from workspace". Returns
    the sidebar with exactly one group card ("Group 1") present.
    """
    _create_workspaces(page, names)
    _enable_workspace_groups(page)
    sidebar = get_workspace_sidebar(page)
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name(group_seed_name))
    expect(sidebar.get_group_cards()).to_have_count(1)
    return sidebar


@user_story("to opt into workspace groups and collect my workspaces through the row menu")
def test_flag_gates_grouping_and_menu_creates_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The flag gates the grouping menu; the menu creates a group and adds to it.

    Steps:
    1. Create two workspaces; with the flag off, the row context menu offers no
       grouping items (REQ-FLAG-2).
    2. Enable the flag via the Settings toggle (REQ-FLAG-1).
    3. "New group from workspace" on row A wraps it in a card named with the
       indexed default "Group 1" (REQ-MENU-2, REQ-GROUP-6, REQ-UI-1).
    4. "Add to group" on row B moves it into that card (REQ-MENU-2).
    """
    page = sculptor_instance_.page

    # Step 1: Flag off — the menu opens (rename is a sentinel item that is
    # always present) but carries no grouping entries.
    _create_workspaces(page, ["Group Menu WS A", "Group Menu WS B"])
    sidebar = get_workspace_sidebar(page)
    row_a = sidebar.get_workspace_row_by_name("Group Menu WS A")
    sidebar.open_row_context_menu(row_a)
    expect(sidebar.get_context_menu_rename()).to_be_visible()
    expect(sidebar.get_workspace_menu_new_group()).to_have_count(0)
    expect(sidebar.get_workspace_menu_add_to_group_trigger()).to_have_count(0)
    page.keyboard.press("Escape")
    expect(sidebar.get_context_menu_rename()).not_to_be_visible()

    # Step 2: Enable the experiment through Settings.
    _enable_workspace_groups(page)

    # Step 3: New group from workspace — a card appears, named "Group 1",
    # containing exactly the seeding row.
    sidebar.create_group_from_workspace(row_a)
    group_cards = sidebar.get_group_cards()
    expect(group_cards).to_have_count(1)
    expect(sidebar.get_group_header(group_cards)).to_contain_text("Group 1")
    member_rows = sidebar.get_group_member_rows(group_cards)
    expect(member_rows).to_have_count(1)
    expect(member_rows).to_contain_text(["Group Menu WS A"])

    # Step 4: Add the second workspace via the "Add to group" submenu; both
    # rows are members now and no workspace was lost.
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("Group Menu WS B"), "Group 1")
    expect(member_rows).to_have_count(2)
    expect(member_rows).to_contain_text(["Group Menu WS A", "Group Menu WS B"])
    expect(sidebar.get_workspace_rows()).to_have_count(2)


@user_story("to rename, recolor, collapse, and ungroup a workspace group from its menu")
def test_group_menu_rename_recolor_collapse_ungroup(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The group header menu manages the group; the chevron collapses the card.

    Steps:
    1. Group two workspaces ("Group 1" seeds with the palette's first color, blue).
    2. Rename via the hover "⋯" menu (REQ-MENU-1) and the inline input.
    3. Recolor via a swatch — the card's accent attribute retints (REQ-MENU-4,
       REQ-GROUP-7).
    4. The chevron collapses the card to header-only and re-expands it (REQ-UI-3).
    5. Ungroup dissolves the card and releases both rows intact (REQ-GROUP-4).
    """
    page = sculptor_instance_.page

    # Step 1: One group holding both workspaces.
    sidebar = _create_single_group(page, ["Group Mgmt WS A", "Group Mgmt WS B"], "Group Mgmt WS A")
    card = sidebar.get_group_cards()
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("Group Mgmt WS B"), "Group 1")
    member_rows = sidebar.get_group_member_rows(card)
    expect(member_rows).to_have_count(2)
    # The first group in a fresh repo takes the palette's first color.
    expect(card).to_have_attribute("data-accent-color", "blue")

    # Step 2: Rename through the "⋯" menu's inline input.
    sidebar.open_group_menu(card)
    rename_item = sidebar.get_group_menu_rename()
    expect(rename_item).to_be_visible()
    rename_item.click()
    rename_input = sidebar.get_inline_rename_input()
    expect(rename_input).to_be_visible()
    rename_input.fill("Surf Crew")
    rename_input.press("Enter")
    expect(rename_input).not_to_be_visible()
    expect(sidebar.get_group_header(card)).to_contain_text("Surf Crew")

    # Step 3: Recolor via a swatch; the card retints through its accent attribute.
    sidebar.open_group_menu(card)
    swatch = sidebar.get_group_menu_swatch("pink")
    expect(swatch).to_be_visible()
    swatch.click()
    expect(card).to_have_attribute("data-accent-color", "pink")

    # Step 4: The chevron collapses the card to its header only, and expands it back.
    sidebar.get_group_chevron(card).click()
    expect(card).to_have_attribute("data-collapsed", "true")
    expect(member_rows).to_have_count(0)
    sidebar.get_group_chevron(card).click()
    expect(card).not_to_have_attribute("data-collapsed", "true")
    expect(member_rows).to_have_count(2)

    # Step 5: Ungroup dissolves the card; the workspaces return to the loose list.
    sidebar.open_group_menu(card)
    ungroup_item = sidebar.get_group_menu_ungroup()
    expect(ungroup_item).to_be_visible()
    ungroup_item.click()
    expect(sidebar.get_group_cards()).to_have_count(0)
    expect(sidebar.get_workspace_rows()).to_have_count(2)
    expect(sidebar.get_workspace_rows()).to_contain_text(["Group Mgmt WS A", "Group Mgmt WS B"])


@user_story("to have a group dissolve on its own when its last member leaves")
def test_single_member_group_dissolves_on_remove_and_delete(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A group whose last member leaves auto-dissolves; it never exists empty.

    Steps:
    1. Group a single workspace.
    2. "Remove from group" on that member dissolves the card; the workspace
       survives as a loose row (REQ-GROUP-8).
    3. Re-group it, then DELETE the workspace: the card dissolves with it and
       the other workspace is untouched (REQ-GROUP-5, REQ-GROUP-8).
    """
    page = sculptor_instance_.page

    # Step 1: A single-member group around workspace A.
    sidebar = _create_single_group(page, ["Dissolve WS A", "Dissolve WS B"], "Dissolve WS A")
    row_a = sidebar.get_workspace_row_by_name("Dissolve WS A")

    # Step 2: Removing the last member dissolves the group; the workspace lives on.
    sidebar.remove_workspace_from_group_via_menu(row_a)
    expect(sidebar.get_group_cards()).to_have_count(0)
    expect(sidebar.get_workspace_rows()).to_have_count(2)
    expect(row_a).to_be_visible()

    # Step 3: Re-group A, then delete the workspace itself — the card goes with
    # it, and B is untouched.
    sidebar.create_group_from_workspace(row_a)
    expect(sidebar.get_group_cards()).to_have_count(1)
    sidebar.delete_workspace_via_context_menu(row_a)
    expect(sidebar.get_group_cards()).to_have_count(0)
    expect(sidebar.get_workspace_rows()).to_have_count(1)
    expect(sidebar.get_workspace_rows()).to_contain_text(["Dissolve WS B"])


@user_story("to drag a workspace into and out of a group in the sidebar")
def test_keyboard_drag_moves_workspace_into_and_out_of_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Keyboard drags change group membership without losing any workspace.

    The workspace names sort after "Group 1", so the never-dragged (alphabetical)
    lane renders the card on top and the loose rows below it — making the drag
    directions deterministic: up moves a loose row into the card, down moves a
    member out onto the loose row below.

    Steps:
    1. Group WS Alpha; WS Bravo and WS Charlie stay loose below the card.
    2. Keyboard-drag Bravo up onto the card: it becomes a member (REQ-DND-1,
       keyboard path per REQ-DND-5).
    3. Keyboard-drag Bravo down onto loose row Charlie: it is released from the
       group — not deleted (REQ-DND-3).
    """
    page = sculptor_instance_.page

    # Step 1: One group (WS Alpha) above two loose rows (WS Bravo, WS Charlie).
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie"], "WS Alpha")
    card = sidebar.get_group_cards()
    member_rows = sidebar.get_group_member_rows(card)
    all_rows = sidebar.get_workspace_rows()
    expect(member_rows).to_have_count(1)
    expect(all_rows).to_have_count(3)

    # Step 2: Drag loose Bravo up into the card; membership commits and no
    # workspace is lost.
    sidebar.drag_workspace_into_group_via_keyboard(
        item=sidebar.get_workspace_row_by_name("WS Bravo"),
        group_card=card,
        direction="up",
    )
    # Membership is asserted order-agnostically: the keyboard drop lands at
    # whichever slot inside the group's run the arrow reached, which decides
    # the insert position but not membership.
    expect(member_rows).to_have_count(2)
    expect(member_rows.filter(has_text="WS Alpha")).to_have_count(1)
    expect(member_rows.filter(has_text="WS Bravo")).to_have_count(1)
    expect(all_rows).to_have_count(3)

    # Step 3: Drag member Bravo down onto the loose row below the card; it is
    # released back to the loose list, intact.
    sidebar.reorder_via_keyboard_drag(
        item=sidebar.get_workspace_row_by_name("WS Bravo"),
        target=sidebar.get_workspace_row_by_name("WS Charlie"),
        direction="down",
    )
    expect(member_rows).to_have_count(1)
    expect(member_rows).to_contain_text(["WS Alpha"])
    expect(all_rows).to_have_count(3)
    expect(sidebar.get_workspace_row_by_name("WS Bravo")).to_be_visible()


@user_story("to drag a whole group above or below another group with the mouse")
def test_pointer_drag_reorders_group_past_another_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dragging a group header past another group lands it beside that
    group's box, chosen by the pointer's side of the box midpoint (REQ-DND-4).

    The middle waypoint parks the pointer INSIDE the taller group's box: the
    dragged header's placeholder is one row tall while the target box is
    three, which is the geometry where an over-slot projection would re-slot
    the lane under the stationary pointer and loop until React aborts
    ("Maximum update depth exceeded") — the pause is the regression trap.

    Steps:
    1. Group 1 wraps WS Alpha; Group 2 wraps WS Bravo and gains WS Charlie, so
       Group 2's box is taller than the dragged header's placeholder.
    2. Pointer-drag Group 1's header onto WS Bravo's row (parked inside Group
       2's box), then on past the box midpoint to WS Charlie's row, and drop.
    3. Group 1 lands after Group 2; both groups keep their members.
    """
    page = sculptor_instance_.page

    # Step 1: Group 1 (WS Alpha) above Group 2 (WS Bravo + WS Charlie).
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie"], "WS Alpha")
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name("WS Bravo"))
    expect(sidebar.get_group_cards()).to_have_count(2)
    group_two = sidebar.get_group_card_by_name("Group 2")
    sidebar.drag_workspace_into_group_via_keyboard(
        item=sidebar.get_workspace_row_by_name("WS Charlie"),
        group_card=group_two,
        direction="up",
    )
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)

    # Step 2: Drag Group 1's header through Group 2's box with the pointer.
    sidebar.drag_via_pointer(
        item=sidebar.get_group_header(sidebar.get_group_card_by_name("Group 1")),
        waypoints=[
            sidebar.get_workspace_row_by_name("WS Bravo"),
            sidebar.get_workspace_row_by_name("WS Charlie"),
        ],
    )

    # Step 3: The lane reads [Group 2, Group 1], every workspace intact.
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    expect(sidebar.get_group_member_rows(sidebar.get_group_card_by_name("Group 1"))).to_have_count(1)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)
    expect(sidebar.get_workspace_rows()).to_have_count(3)
