from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# Keyboard pickup (focus → Space) is retried: an async focus restore from a menu
# that just closed can steal the Space press, so it lands on the menu trigger
# instead of the drag activator (mirrors section_helpers' panel-drag pickup).
_REORDER_PICKUP_ATTEMPTS = 3

# A reorder drag presses one arrow per slot; the loop stops as soon as the target
# slot lights up as the drop target, and this bounds a drag that never gets there.
_REORDER_MAX_ARROW_PRESSES = 6


class PlaywrightWorkspaceSidebarElement(PlaywrightIntegrationTestElement):
    """Page Object Model for the workspace navigation sidebar.

    The sidebar is the global chrome rail that replaces the old top bar + tab
    strip: top links (Home / Cmd+K / New workspace), repos as collapsible groups
    with their workspaces, then Settings / report-a-bug / version at the bottom.

    Workspace rows are the successor to the home page's ``WORKSPACE_ROW`` surface,
    so the row helpers below mirror ``PlaywrightHomePage.get_workspace_rows()``
    rather than inventing a new row model.
    """

    # -- Top links --

    def get_home_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_HOME_LINK)

    def get_cmdk_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_CMDK_LINK)

    def get_new_workspace_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_NEW_WORKSPACE_BUTTON)

    def get_add_repo_button(self) -> Locator:
        """The persistent "Add repo" button that opens the add-repo dialog."""
        return self.get_by_test_id(ElementIDs.SIDEBAR_ADD_REPO_BUTTON)

    def open_add_repo_dialog(self) -> PlaywrightAddRepoDialogElement:
        """Click the "Add repo" button and return the opened add-repo dialog POM."""
        self.get_add_repo_button().click()
        dialog_locator = self._page.get_by_test_id(ElementIDs.ADD_REPO_DIALOG)
        expect(dialog_locator).to_be_visible()
        return PlaywrightAddRepoDialogElement(locator=dialog_locator, page=self._page)

    # -- Repo groups --

    def get_repo_groups(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_REPO_GROUP)

    def get_repo_group_by_name(self, name: str) -> Locator:
        """Get a repo-group header by its repo name.

        Prefer this over positional ``get_repo_groups().nth(...)`` when the
        list order is about to change (e.g. drag-to-reorder): a positional
        locator re-resolves against the post-change order, so guards on it
        check the wrong element.
        """
        return self.get_repo_groups().filter(has_text=name)

    def get_no_workspaces_hint(self) -> Locator:
        """The "No workspaces yet" hint shown under a repo group with no workspaces."""
        return self.get_by_test_id(ElementIDs.SIDEBAR_NO_WORKSPACES_HINT)

    def get_repo_add_workspace(self, project_id: str) -> Locator:
        # The add-workspace icon is stamped with ``data-project-id``; this raw
        # CSS-attribute scope stays inside the POM so the integration-test
        # css-locator ratchet is honoured at the call sites.
        return self._page.locator(
            f'[data-testid="{ElementIDs.SIDEBAR_REPO_ADD_WORKSPACE}"][data-project-id="{project_id}"]'
        )

    # -- Drag-to-reorder (keyboard-driven) --

    def pickup_via_keyboard(self, item: Locator) -> None:
        """Pick up a workspace row or repo-group header (focus → Space) and leave
        the drag parked.

        Pickup is retried per ``_REORDER_PICKUP_ATTEMPTS``: an async focus
        restore from a menu that just closed can steal the Space press, so each
        retry dismisses whatever it opened with Escape and re-focuses the item.
        The sensor marks the activator with ``data-sidebar-dragging`` on drag
        start, which doubles as the "keydown listeners are live" signal — the
        KeyboardSensor attaches them on a deferred tick, so an arrow pressed
        before the flag appears would be silently dropped.
        """
        for attempt in range(_REORDER_PICKUP_ATTEMPTS):
            item.focus()
            self._page.keyboard.press("Space")  # pick up
            try:
                expect(item).to_have_attribute("data-sidebar-dragging", "true", timeout=5_000)
                return
            except AssertionError:
                if attempt == _REORDER_PICKUP_ATTEMPTS - 1:
                    raise
                self._page.keyboard.press("Escape")

    def reorder_via_keyboard_drag(self, item: Locator, target: Locator, direction: str) -> None:
        """Drag a workspace row or repo-group header to another slot via the KeyboardSensor.

        ``item`` and ``target`` are drag activators of the same drag context (two
        rows of one repo section's flat lane, or two repo-group headers);
        ``direction`` is "up" or "down". Picks the item up
        (``pickup_via_keyboard``), presses one arrow per slot until the drag has
        arrived at ``target``'s slot, then Space to drop.

        Arrival shows up through one of two signals, matching the sidebar's two
        preview regimes: a same-container press previews via transforms and
        lights the targeted slot with ``data-sidebar-drop-target``, while a
        press that crosses a group boundary (a membership change, or the
        tail-of-group slot) re-renders the lane with the dragged row's
        placeholder AT the projected slot — nothing lights, because the drag now
        hovers its own row; the row's geometry passing the target is the signal
        instead.

        Pass stably-identified locators (by-name helpers), not positional
        ``nth(...)`` ones: positional locators re-resolve against the post-drop
        order, so the closing guard would check the wrong element.
        """
        self.pickup_via_keyboard(item)

        arrow = {"up": "ArrowUp", "down": "ArrowDown"}[direction]

        # Each arrow press is confirmed applied before the next fires: every
        # press moves the drag exactly one slot, so a press fired while a slow
        # re-render is still applying the previous one overshoots the target. A
        # drag that exhausts its presses raises rather than dropping blind, so
        # the failure surfaces here and not as a downstream order-assertion
        # mismatch.
        for _press in range(_REORDER_MAX_ARROW_PRESSES):
            before = self._drag_snapshot(item)
            self._page.keyboard.press(arrow)
            for _wait in range(40):
                if self._drag_snapshot(item) != before:
                    break
                self._page.wait_for_timeout(50)
            # The arrival check is retried over a settle window: a re-slot
            # moves the dragged placeholder instantly, but its displaced
            # neighbor FLIP-animates from its old position — an instant
            # geometry read right after press-confirmation can catch the
            # neighbor mid-flight and wrongly conclude the target wasn't
            # reached, firing an overshoot press.
            is_reached = False
            for _settle in range(8):
                if self._has_drag_reached_target(item, target, direction):
                    is_reached = True
                    break
                self._page.wait_for_timeout(50)
            if is_reached:
                break
        else:
            raise AssertionError(
                f"keyboard drag never reached the target slot within {_REORDER_MAX_ARROW_PRESSES} presses"
            )
        self._page.keyboard.press("Space")  # drop

        # The drop clears the drag flag once the reorder commits; asserting it here
        # keeps callers from racing their order assertions against the commit.
        expect(item).not_to_have_attribute("data-sidebar-dragging", "true")

    def _drag_snapshot(self, item: Locator) -> float | None:
        """The dragged row's own position, for press confirmation.

        Geometry ONLY, deliberately: in both drag contexts an applied press
        moves the dragged element (the repo list transforms it toward the
        targeted slot; the flat lane re-renders its placeholder at the
        projected slot), whereas the lit drop-target slot can flash BEFORE the
        lane re-render lands — counting it would confirm a press whose layout
        effect hasn't applied yet, and the arrival check would then read stale
        geometry and overshoot with an extra press.
        """
        box = item.bounding_box()
        return None if box is None else round(box["y"])

    def _has_drag_reached_target(self, item: Locator, target: Locator, direction: str) -> bool:
        """Whether the parked drag has arrived at ``target``'s slot (either preview regime)."""
        if target.get_attribute("data-sidebar-drop-target") == "true":
            return True
        item_box = item.bounding_box()
        target_box = target.bounding_box()
        if item_box is None or target_box is None:
            return False
        return item_box["y"] > target_box["y"] if direction == "down" else item_box["y"] < target_box["y"]

    def drag_workspace_into_group_via_keyboard(self, item: Locator, group_card: Locator, direction: str) -> None:
        """Drag a workspace row from outside a group into that group via the
        KeyboardSensor.

        The same drive as ``reorder_via_keyboard_drag`` (pickup, one arrow per
        slot, Space to drop), but the stop condition is the group's membership
        affordance: ``group_card`` stamps ``data-drop-active`` while the active
        drag's projected drop would land inside the group, and it stays lit for
        as long as the projection holds — so watching the card is agnostic to
        which slot inside the run the arrow reached.
        """
        self.pickup_via_keyboard(item)

        arrow = {"up": "ArrowUp", "down": "ArrowDown"}[direction]
        # Same press-confirmation discipline as reorder_via_keyboard_drag: a
        # press fired while a slow re-render is still applying the previous one
        # would overshoot — stepping straight through a small group's run
        # without its affordance ever being observed lit.
        for _press in range(_REORDER_MAX_ARROW_PRESSES):
            before = self._drag_snapshot(item)
            self._page.keyboard.press(arrow)
            for _wait in range(40):
                if self._drag_snapshot(item) != before:
                    break
                self._page.wait_for_timeout(50)
            if group_card.get_attribute("data-drop-active") == "true":
                break
        else:
            raise AssertionError(
                f"keyboard drag never lit the group card's drop affordance within {_REORDER_MAX_ARROW_PRESSES} presses"
            )
        self._page.keyboard.press("Space")  # drop

        # The drop clears the drag flag; asserting it here keeps callers from
        # racing their membership assertions against the drop commit.
        expect(item).not_to_have_attribute("data-sidebar-dragging", "true")

    def drag_via_pointer(self, item: Locator, waypoints: list[Locator]) -> None:
        """Drag ``item`` with the real PointerSensor: press on its center, move
        through each waypoint's center, release.

        Each waypoint re-resolves against the LIVE lane right before the move —
        the drag's own projections re-slot rows mid-flight, so a position
        captured up front would aim at where a row used to be. The pointer
        parks briefly at every waypoint: the sidebar's flat lane previews by
        re-rendering real layout under a measuring drag context, so a parked
        pointer is exactly where a projection feedback loop would spin, and
        pausing there gives one time to surface as a crash instead of being
        skated over.
        """
        box = item.bounding_box()
        if box is None:
            raise AssertionError("pointer drag item is not visible")
        self._page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        self._page.mouse.down()
        for waypoint in waypoints:
            waypoint_box = waypoint.bounding_box()
            if waypoint_box is None:
                raise AssertionError("pointer drag waypoint is not visible")
            # Multiple steps so the sensor's activation-distance constraint is
            # crossed by real intermediate pointermove events.
            self._page.mouse.move(
                waypoint_box["x"] + waypoint_box["width"] / 2,
                waypoint_box["y"] + waypoint_box["height"] / 2,
                steps=8,
            )
            self._page.wait_for_timeout(250)
        self._page.mouse.up()

        # The drop clears the drag flag once the reorder commits; asserting it
        # here keeps callers from racing their order assertions against it.
        expect(item).not_to_have_attribute("data-sidebar-dragging", "true")

    # -- Workspace rows (mirrors PlaywrightHomePage.get_workspace_rows) --

    def get_workspace_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)

    def get_workspace_row_by_name(self, name: str) -> Locator:
        return self.get_workspace_rows().filter(has_text=name)

    def get_row_delete_icon(self, workspace_row: Locator) -> Locator:
        """Get the hover-revealed delete icon scoped to a workspace row.

        The delete icon sits in the row's sibling actions cluster (revealed on
        hover), so it is scoped to the row's parent rather than the row button
        itself.
        """
        return workspace_row.locator("..").get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW_DELETE)

    def get_row_menu_icon(self, workspace_row: Locator) -> Locator:
        """Get the hover-revealed "..." actions menu icon scoped to a workspace row."""
        return workspace_row.locator("..").get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW_MENU)

    def open_row_context_menu(self, workspace_row: Locator) -> None:
        """Right-click a workspace row to open its context menu."""
        workspace_row.click(button="right")

    def open_row_dropdown_menu(self, workspace_row: Locator) -> None:
        """Hover a row and click its "..." actions dropdown trigger."""
        workspace_row.hover()
        menu_icon = self.get_row_menu_icon(workspace_row)
        expect(menu_icon).to_be_visible()
        menu_icon.click()

    # -- Workspace-row context menu items + inline rename --
    #
    # The sidebar workspace row shares the workspace-action context menu (the
    # ``TAB_CONTEXT_MENU_*`` ids), reached by right-clicking the row or via the
    # row's "..." dropdown. Rename commits through the shared InlineRenameInput;
    # delete opens the shared DeleteConfirmationDialog, and confirming runs the
    # optimistic removal (the row vanishes before the backend confirms).

    def get_context_menu_rename(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_context_menu_delete(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)

    def get_copy_workspace_name_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME)

    def get_copy_branch_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_BRANCH)

    def get_copy_workspace_id_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_WORKSPACE_ID)

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)

    def get_delete_confirmation_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CANCEL)

    def confirm_delete(self) -> None:
        """Click the confirm button in the workspace delete-confirmation dialog."""
        confirm_button = self.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()

    def cancel_delete(self) -> None:
        """Click the cancel button in the workspace delete-confirmation dialog."""
        cancel_button = self.get_delete_confirmation_cancel_button()
        expect(cancel_button).to_be_visible()
        cancel_button.click()

    def open_diagnostics_submenu(self, workspace_row: Locator) -> None:
        """Right-click a row and hover Diagnostics to open the copy-id submenu."""
        self.open_row_context_menu(workspace_row)
        trigger = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DIAGNOSTICS)
        expect(trigger).to_be_visible()
        trigger.hover()

    def rename_workspace_via_context_menu(self, workspace_row: Locator, new_name: str) -> None:
        """Right-click a row, click Rename, then fill and commit the inline input."""
        self.open_row_context_menu(workspace_row)
        rename_item = self.get_context_menu_rename()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def delete_workspace_via_context_menu(self, workspace_row: Locator) -> None:
        """Right-click a row, click Delete, and confirm in the delete dialog.

        Deleting a workspace is destructive, so it is confirmed first; the delete
        itself is then optimistic (the row vanishes before the backend confirms).
        """
        self.open_row_context_menu(workspace_row)
        delete_item = self.get_context_menu_delete()
        expect(delete_item).to_be_visible()
        delete_item.click()
        self.confirm_delete()

    def delete_workspace_via_row_icon(self, workspace_row: Locator) -> None:
        """Hover a row, click its trash icon, and confirm in the delete dialog."""
        workspace_row.hover()
        delete_icon = self.get_row_delete_icon(workspace_row)
        expect(delete_icon).to_be_visible()
        delete_icon.click()
        self.confirm_delete()

    # -- Workspace-group cards --
    #
    # A workspace group (the experimental workspace-groups feature) renders
    # Dia-style inside its repo section: a header row (chevron + color swatch +
    # name + hover "⋯" menu trigger) with the member workspace rows — ordinary
    # ``SIDEBAR_WORKSPACE_ROW`` elements — indented beneath it. The wrapper
    # "card" element paints the hover/drop container surface and stamps the
    # group's identity and state as data attributes (``data-group-id``,
    # ``data-accent-color``, ``data-collapsed``, ``data-drop-active``), so
    # tests assert state through attributes rather than styles.

    def get_group_cards(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_GROUP_CARD)

    def get_group_card_by_name(self, name: str) -> Locator:
        """Get a group card by its header name.

        Filters on the header's text (not the whole card's) so a member
        workspace whose name contains ``name`` can never match the card.
        """
        header = self._page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_GROUP_HEADER).filter(has_text=name)
        return self.get_group_cards().filter(has=header)

    def get_group_header(self, group_card: Locator) -> Locator:
        """The card's header button: the drag activator and collapse toggle."""
        return group_card.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_GROUP_HEADER)

    def get_group_chevron(self, group_card: Locator) -> Locator:
        """The collapse chevron; it sits inside the header button, so clicking it toggles collapse."""
        return group_card.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_GROUP_CHEVRON)

    def get_group_member_rows(self, group_card: Locator) -> Locator:
        """The workspace rows rendered inside the card (its members; empty while collapsed)."""
        return group_card.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)

    def get_group_menu_trigger(self, group_card: Locator) -> Locator:
        """The hover-revealed "⋯" trigger on the group header."""
        return group_card.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_GROUP_MENU_TRIGGER)

    def open_group_menu(self, group_card: Locator) -> None:
        """Hover the group header and click its "⋯" trigger to open the group menu."""
        self.get_group_header(group_card).hover()
        trigger = self.get_group_menu_trigger(group_card)
        expect(trigger).to_be_visible()
        trigger.click()

    # -- Group menu items (portaled to the page, like the row context menu) --

    def get_group_menu_rename(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_GROUP_MENU_RENAME)

    def get_group_menu_collapse(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_GROUP_MENU_COLLAPSE)

    def get_group_menu_ungroup(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_GROUP_MENU_UNGROUP)

    def get_group_menu_swatch(self, color: str) -> Locator:
        # The swatch row renders one item per palette color, each stamped with
        # ``data-color``; this raw CSS-attribute scope stays inside the POM so
        # the integration-test css-locator ratchet is honoured at call sites.
        return self._page.locator(f'[data-testid="{ElementIDs.WORKSPACE_GROUP_MENU_SWATCH}"][data-color="{color}"]')

    # -- Workspace-row grouping menu items --
    #
    # The workspace row's context/dropdown menu gains a grouping section while
    # the workspace-groups flag is on: "New group from workspace", the "Add to
    # group" submenu (one entry per existing group plus "New group…"), and
    # "Remove from group" on member rows.

    def get_workspace_menu_new_group(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_MENU_NEW_GROUP)

    def get_workspace_menu_add_to_group_trigger(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_MENU_ADD_TO_GROUP)

    def get_workspace_menu_add_to_group_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_MENU_ADD_TO_GROUP_ITEM)

    def get_workspace_menu_remove_from_group(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.WORKSPACE_MENU_REMOVE_FROM_GROUP)

    def create_group_from_workspace(self, workspace_row: Locator) -> None:
        """Right-click a row and pick "New group from workspace"."""
        self.open_row_context_menu(workspace_row)
        new_group_item = self.get_workspace_menu_new_group()
        expect(new_group_item).to_be_visible()
        new_group_item.click()

    def add_workspace_to_group_via_menu(self, workspace_row: Locator, group_name: str) -> None:
        """Right-click a row, hover "Add to group", and pick the named group from the submenu."""
        self.open_row_context_menu(workspace_row)
        trigger = self.get_workspace_menu_add_to_group_trigger()
        expect(trigger).to_be_visible()
        trigger.hover()
        group_item = self.get_workspace_menu_add_to_group_items().filter(has_text=group_name)
        expect(group_item).to_be_visible()
        group_item.click()

    def remove_workspace_from_group_via_menu(self, workspace_row: Locator) -> None:
        """Right-click a member row and pick "Remove from group"."""
        self.open_row_context_menu(workspace_row)
        remove_item = self.get_workspace_menu_remove_from_group()
        expect(remove_item).to_be_visible()
        remove_item.click()

    # -- Bottom links + chrome --

    def get_settings_link(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_SETTINGS_LINK)

    def get_version(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_VERSION)

    def get_collapse_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_COLLAPSE_TOGGLE)

    def get_resize_handle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SIDEBAR_RESIZE_HANDLE)

    def get_expand_icon(self) -> Locator:
        """Get the collapsed-sidebar expand toggle.

        Rendered only when the sidebar is collapsed, in place of the sidebar
        rail, so it is located page-wide rather than scoped to the sidebar root.
        """
        return self._page.get_by_test_id(ElementIDs.SIDEBAR_EXPAND_ICON)

    def collapse(self) -> None:
        """Collapse the sidebar to its expand-icon-only rail."""
        toggle = self.get_collapse_toggle()
        expect(toggle).to_be_visible()
        toggle.click()

    def expand(self) -> None:
        """Expand a collapsed sidebar back to the full rail."""
        expand_icon = self.get_expand_icon()
        expect(expand_icon).to_be_visible()
        expand_icon.click()


def get_workspace_sidebar(page: Page) -> PlaywrightWorkspaceSidebarElement:
    """Return the sidebar POM rooted at the ``WORKSPACE_SIDEBAR`` element.

    The sidebar renders on the workspace route's shell layout. When collapsed,
    the rail is replaced by the expand icon, so the root locator is hidden — use
    ``get_expand_icon()`` / ``expand()`` in that state.
    """
    sidebar = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    return PlaywrightWorkspaceSidebarElement(locator=sidebar, page=page)
