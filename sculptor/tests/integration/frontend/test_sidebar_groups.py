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
    2. Pointer-drag Group 1's header down through Group 2's box, parking on
       its top member row and then its bottom member row, and drop there.
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

    # Step 2: Drag Group 1's header down through Group 2's box — across its
    # top member row, then to its bottom member row. Finishing in the bottom
    # half of the box is what projects the group to the slot after it; a
    # pointer that finishes in the TOP half means "before the box" by design.
    member_rows = sidebar.get_group_member_rows(group_two)
    sidebar.drag_via_pointer(
        item=sidebar.get_group_header(sidebar.get_group_card_by_name("Group 1")),
        waypoints=[member_rows.first, member_rows.last],
    )

    # Step 3: The lane reads [Group 2, Group 1], every workspace intact.
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    expect(sidebar.get_group_member_rows(sidebar.get_group_card_by_name("Group 1"))).to_have_count(1)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)
    expect(sidebar.get_workspace_rows()).to_have_count(3)


@user_story("to drag a group below an adjacent group with the mouse")
def test_pointer_drag_moves_group_below_adjacent_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dragging a group's header into the bottom half of the next
    group's box lands it below that group — with NOTHING loose after it.

    This is the geometry where an over-driven side evaluation gets stuck: the
    dragged run's tall overlay leads the pointer, so the target box's inner
    droppables all fire while the pointer is still in its top half, and with
    no targets below the box no further over event re-evaluates the side. The
    level-triggered move-stream resolution must carry the crossing instead.

    Steps:
    1. Group 1 wraps WS Alpha + WS Bravo; Group 2 wraps WS Charlie + WS Delta;
       every workspace is grouped, so nothing sits below Group 2.
    2. Pointer-drag Group 1's header down to WS Delta's row (the bottom half
       of Group 2's box) and drop.
    3. The lane reads [Group 2, Group 1]; both groups keep their members.
    """
    page = sculptor_instance_.page

    # Step 1: Two adjacent two-member groups and no loose rows. Membership is
    # arranged through the row menu ("Add to group") — the member moves are
    # scaffolding here; the drag under test is the group-header drag below.
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie", "WS Delta"], "WS Alpha")
    group_one = sidebar.get_group_card_by_name("Group 1")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Bravo"), "Group 1")
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name("WS Charlie"))
    expect(sidebar.get_group_cards()).to_have_count(2)
    group_two = sidebar.get_group_card_by_name("Group 2")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Delta"), "Group 2")
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)

    # Step 2: Drag Group 1's header into the bottom half of Group 2's box.
    sidebar.drag_via_pointer(
        item=sidebar.get_group_header(group_one),
        waypoints=[sidebar.get_workspace_row_by_name("WS Delta")],
    )

    # Step 3: Group 1 landed below Group 2, memberships untouched.
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)


@user_story("to reorder a group's members by dragging them with the mouse")
def test_pointer_drag_reorders_members_within_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dragging a member to another member's bottom half reorders the
    run in place — same group, new order.

    The park aims at the MIDDLE member's bottom half: a bottom-half park on the
    box's last member sits in the box's edge inset, which deliberately reads as
    the loose slot below the box (REQ-DND-6), not a member slot.

    Steps:
    1. Group 1 wraps WS Alpha, WS Bravo, and WS Charlie.
    2. Pointer-drag Alpha to Bravo's bottom half and drop.
    3. Member order is Bravo, Alpha, Charlie; membership unchanged.
    """
    page = sculptor_instance_.page

    # Step 1: One group holding all three workspaces.
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie"], "WS Alpha")
    group_one = sidebar.get_group_card_by_name("Group 1")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Bravo"), "Group 1")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Charlie"), "Group 1")
    members = sidebar.get_group_member_rows(group_one)
    expect(members).to_have_count(3)
    expect(members).to_contain_text(["WS Alpha", "WS Bravo", "WS Charlie"])

    # Step 2: Park in Bravo's bottom half, inside the box.
    sidebar.drag_via_pointer(
        item=sidebar.get_workspace_row_by_name("WS Alpha"),
        waypoints=[sidebar.get_workspace_row_by_name("WS Bravo")],
        y_offsets=[8],
    )

    # Step 3: Reordered in place.
    expect(members).to_have_count(3)
    expect(members).to_contain_text(["WS Bravo", "WS Alpha", "WS Charlie"])
    expect(sidebar.get_workspace_rows()).to_have_count(3)


@user_story("to drop a workspace onto a collapsed group and have it join")
def test_pointer_drop_on_collapsed_group_appends(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dropping a row on a collapsed group's header appends it to the
    group — the one projection with no visible gap to preview (REQ-DND-6).

    Steps:
    1. Group 1 wraps WS Bravo; WS Alpha stays loose. Collapse the group.
    2. Pointer-drag Alpha onto the collapsed header and drop.
    3. Expand: the members are Bravo then Alpha (appended at the tail).
    """
    page = sculptor_instance_.page

    # Step 1: A collapsed single-member group and a loose row.
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo"], "WS Bravo")
    group_one = sidebar.get_group_card_by_name("Group 1")
    members = sidebar.get_group_member_rows(group_one)
    sidebar.set_group_collapsed_via_chevron(group_one, collapsed=True)
    expect(members).to_have_count(0)

    # Step 2: Drop Alpha on the collapsed header.
    sidebar.drag_via_pointer(
        item=sidebar.get_workspace_row_by_name("WS Alpha"),
        waypoints=[sidebar.get_group_header(group_one)],
    )

    # Step 3: The append committed; expanding shows Alpha at the tail.
    sidebar.set_group_collapsed_via_chevron(group_one, collapsed=False)
    expect(members).to_have_count(2)
    expect(members).to_contain_text(["WS Bravo", "WS Alpha"])


@user_story("to drag a group above or below a loose workspace row with the mouse")
def test_pointer_drag_lands_group_beside_loose_row(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Parking a dragged group's pointer on a loose row's bottom/top half lands
    the group after/before that row — deterministically, without jitter.

    A loose row next to a group box is the geometry where two competing drag
    authorities used to disagree: over-slot taking is side-agnostic while the
    move stream resolves by midpoint, and each application re-slotted the lane
    and flipped the collision target, sliding the row back and forth under a
    stationary pointer (2-4 flips/second in hand-testing). The parked settles
    here sit exactly on that boundary; the drop must land by the pointer's
    side of the row's midpoint, and the parked lane must be stable enough for
    the drop to commit it.

    Steps:
    1. Group 1 (WS Alpha) and Group 2 (WS Bravo) above the loose WS Charlie.
    2. Drag Group 1's header down and park on WS Charlie's BOTTOM half; the
       group lands after the row: [Group 2, WS Charlie, Group 1].
    3. Drag Group 1's header back up and park on WS Charlie's TOP half; the
       group lands before the row: [Group 2, Group 1, WS Charlie].
    """
    page = sculptor_instance_.page

    # Step 1: Two single-member groups above one loose row.
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie"], "WS Alpha")
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name("WS Bravo"))
    expect(sidebar.get_group_cards()).to_have_count(2)

    # Step 2: Park in the row's bottom half (center +8px on a ~28px row) —
    # the group lands after the row.
    loose_row = sidebar.get_workspace_row_by_name("WS Charlie")
    sidebar.drag_via_pointer(
        item=sidebar.get_group_header(sidebar.get_group_card_by_name("Group 1")),
        waypoints=[loose_row],
        y_offsets=[8],
    )
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    group_one_box = sidebar.get_group_card_by_name("Group 1").bounding_box()
    loose_box = loose_row.bounding_box()
    assert group_one_box is not None and loose_box is not None
    assert loose_box["y"] < group_one_box["y"], "the group must land BELOW the loose row"

    # Step 3: Park in the row's top half — the group lands back above the row.
    sidebar.drag_via_pointer(
        item=sidebar.get_group_header(sidebar.get_group_card_by_name("Group 1")),
        waypoints=[loose_row],
        y_offsets=[-8],
    )
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    group_one_box = sidebar.get_group_card_by_name("Group 1").bounding_box()
    loose_box = loose_row.bounding_box()
    assert group_one_box is not None and loose_box is not None
    assert group_one_box["y"] < loose_box["y"], "the group must land back ABOVE the loose row"


@user_story("to drop a workspace into the group box my pointer is actually over")
def test_pointer_drag_row_lands_in_box_under_pointer(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A row drag released with the pointer inside a group's box joins THAT
    group — even when the drag passed through another group on the way.

    Passing through the first group leaves its slot as the projection's last
    over-driven state, and the eject/re-enter transitions between adjacent
    boxes could re-attach the row to the box ABOVE the pointer's gap rather
    than the one the pointer went on to enter — with the edge-triggered over
    stream silent, the stale parent survived to the drop (the hand-tested
    symptom: a row released over the second group's header landing in the
    first group). The pointer's box must win.

    Steps:
    1. Loose WS Alpha above Group 1 (WS Bravo, WS Charlie) above Group 2
       (WS Delta).
    2. Drag WS Alpha down through Group 1 (parking on its last member) and on
       to Group 2's header, parking INSIDE Group 2's box, then drop.
    3. WS Alpha is a member of Group 2, not Group 1.
    """
    page = sculptor_instance_.page

    # Step 1: [WS Alpha loose, Group 1 (Bravo, Charlie), Group 2 (Delta)].
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie", "WS Delta"], "WS Bravo")
    group_one = sidebar.get_group_card_by_name("Group 1")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Charlie"), "Group 1")
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name("WS Delta"))
    expect(sidebar.get_group_cards()).to_have_count(2)
    group_two = sidebar.get_group_card_by_name("Group 2")
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(1)
    # The optimistic group writes race their server heals: on a loaded run, a
    # stale workspace refetch can momentarily revert a membership AFTER the
    # counts above pass, corrupting the lane mid-drag (the drag snapshots the
    # lane at pickup). Give the heals a beat to land and re-check, so the
    # drag below starts from a lane that has stopped moving.
    page.wait_for_timeout(750)
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(1)

    # Step 2: Down through Group 1's tail, then park on Group 2's header —
    # squarely inside Group 2's box — and drop there.
    sidebar.drag_via_pointer(
        item=sidebar.get_workspace_row_by_name("WS Alpha"),
        waypoints=[sidebar.get_workspace_row_by_name("WS Charlie"), sidebar.get_group_header(group_two)],
    )

    # Step 3: The row joined the group under the pointer.
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_contain_text(["WS Alpha", "WS Delta"])
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_workspace_rows()).to_have_count(4)


@user_story("to drag a group below another by dropping in the empty space beneath it")
def test_pointer_drag_moves_group_past_bottom_edge(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pointer-dragging a group's header PAST the bottom of the next group's
    box — releasing in the empty space beneath the lane — still lands it below
    that group.

    This is the flaky case from hand-testing: the pointer is dragged clear
    below the target box rather than parked in its bottom half. The group's
    before/after side must resolve for a pointer OUTSIDE every box (a rule
    total over the whole rail), not only while the pointer sits within a box's
    vertical extent — otherwise the drop is a silent no-op and the group snaps
    back above.

    Steps:
    1. Group 1 (WS Alpha + WS Bravo) above Group 2 (WS Charlie + WS Delta);
       nothing loose below.
    2. Pointer-drag Group 1's header down onto Group 2's bottom member, then
       push well past the box's bottom edge into empty space, and drop.
    3. The lane reads [Group 2, Group 1]; both groups keep their members.
    """
    page = sculptor_instance_.page

    # Step 1: Two adjacent two-member groups and no loose rows (membership via
    # the row menu — the drag under test is the group-header drag below).
    sidebar = _create_single_group(page, ["WS Alpha", "WS Bravo", "WS Charlie", "WS Delta"], "WS Alpha")
    group_one = sidebar.get_group_card_by_name("Group 1")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Bravo"), "Group 1")
    sidebar.create_group_from_workspace(sidebar.get_workspace_row_by_name("WS Charlie"))
    expect(sidebar.get_group_cards()).to_have_count(2)
    group_two = sidebar.get_group_card_by_name("Group 2")
    sidebar.add_workspace_to_group_via_menu(sidebar.get_workspace_row_by_name("WS Delta"), "Group 2")
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)

    # Step 2: Flick Group 1's header straight down past every box in one jump
    # and drop in the empty space beneath — never dwelling in Group 2's bottom
    # half, so the drop side must resolve for a pointer below every box.
    sidebar.flick_group_below_all_via_pointer(sidebar.get_group_header(group_one))

    # Step 3: Group 1 landed below Group 2, memberships untouched.
    cards = sidebar.get_group_cards()
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Group 2")
    expect(cards.nth(1)).to_contain_text("Group 1")
    expect(sidebar.get_group_member_rows(group_one)).to_have_count(2)
    expect(sidebar.get_group_member_rows(group_two)).to_have_count(2)
