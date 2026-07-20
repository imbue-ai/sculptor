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

# A pointer drag aims at a point past the target's centre in the drag direction but
# still inside its rect, so `over` resolves to the target (pointerWithin sorts by
# distance to each containing droppable's centre) without overshooting past the rect
# into empty space. Expressed as a fraction of the target's height: three-quarters
# down when dragging downward, one-quarter down when dragging upward.
_POINTER_DRAG_TARGET_FRACTION_FORWARD = 0.75
_POINTER_DRAG_TARGET_FRACTION_BACKWARD = 0.25

# The pointer move is broken into this many steps so dnd-kit's PointerSensor clears
# its activation distance and recomputes `over` on each pointermove; a single jump to
# the end would skip the intermediate collisions the sensor needs.
_POINTER_DRAG_MOVE_STEPS = 24

# How far past the target's far edge an overshoot drag drives the pointer — enough to
# clear the list container so the drag exercises the "pointer past the container" path
# (where the pointer must be clamped back to the extreme item, since the dragged element
# is held inside the list but the pointer is not).
_POINTER_DRAG_OVERSHOOT_PX = 160


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

    def get_repo_group_by_project_id(self, project_id: str) -> Locator:
        """Get a repo-group header by its project id.

        Unambiguous where names could collide or a name is unknown (e.g. the
        harness's default repo). The header stamps ``data-project-id``; this raw
        CSS-attribute scope stays inside the POM so the css-locator ratchet is
        honoured at the call sites.
        """
        return self._page.locator(f'[data-testid="{ElementIDs.SIDEBAR_REPO_GROUP}"][data-project-id="{project_id}"]')

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

        ``item`` and ``target`` are drag activators of the same sortable list (two
        workspace rows of one repo group, or two repo-group headers); ``direction``
        is "up" or "down". Mirrors section_helpers' panel drag: pick the item up
        (``pickup_via_keyboard``), one arrow per slot until ``target``'s slot
        reports ``data-sidebar-drop-target``, Space to drop.

        Pass stably-identified locators (by-name helpers), not positional
        ``nth(...)`` ones: positional locators re-resolve against the post-drop
        order, so the closing guard would check the wrong element.
        """
        self.pickup_via_keyboard(item)

        arrow = {"up": "ArrowUp", "down": "ArrowDown"}[direction]
        # Each arrow press is confirmed applied before the next fires: every press
        # moves the drag exactly one slot, so a press fired while a slow re-render
        # is still applying the previous one overshoots the target — and in a
        # sortable list the target slot then never lights up. Right after pickup no
        # slot is lit (the drag sits over its own slot), so the first press is
        # confirmed by any slot lighting up; later presses by the lit slot's
        # identity changing (rows stamp data-workspace-id, group headers
        # data-project-id). A drag that exhausts its presses raises rather than
        # dropping blind, so the failure surfaces here and not as a downstream
        # order-assertion mismatch.
        lit_slot = self._page.locator('[data-sidebar-drop-target="true"]')
        for _press in range(_REORDER_MAX_ARROW_PRESSES):
            previous_slot_id = None
            if lit_slot.count() == 1:
                previous_slot_id = lit_slot.get_attribute("data-workspace-id") or lit_slot.get_attribute(
                    "data-project-id"
                )
            self._page.keyboard.press(arrow)
            if previous_slot_id is None:
                expect(lit_slot).to_have_count(1)
            else:
                moved_slot = self._page.locator(
                    f'[data-sidebar-drop-target="true"]'
                    f':not([data-workspace-id="{previous_slot_id}"]):not([data-project-id="{previous_slot_id}"])'
                )
                expect(moved_slot).to_have_count(1)
            if target.get_attribute("data-sidebar-drop-target") == "true":
                break
        else:
            raise AssertionError(
                f"keyboard drag never reached the target slot within {_REORDER_MAX_ARROW_PRESSES} presses"
            )
        self._page.keyboard.press("Space")  # drop

        # The drop clears the drag flag once the reorder commits; asserting it here
        # keeps callers from racing their order assertions against the commit.
        expect(item).not_to_have_attribute("data-sidebar-dragging", "true")

    def reorder_via_pointer_drag(self, item: Locator, target: Locator, *, overshoot: bool = False) -> None:
        """Drag one drag activator past another with a real mouse drag (PointerSensor).

        ``item`` and ``target`` are drag activators of the same sortable list (two
        repo-group headers, or two workspace rows). Unlike ``reorder_via_keyboard_drag``,
        this drives the PointerSensor: the pointer drags the element, whose (parent-clamped)
        rectangle resolves the drop. This is the only path that exercises a drag of a TALL
        sortable (e.g. an expanded repo group filled with workspaces) — the keyboard getter
        steps the dragged item's rect straight onto the target slot, so it never depends on
        the group's height, whereas a pointer drag of a tall group does (the group's
        collision rect is its full height).

        The move is stepped so dnd-kit's PointerSensor clears its 5px activation distance
        and recomputes ``over`` on each ``pointermove``. It drags the element far enough past
        the target's centre that the target's slot wins the collision, then waits for it to
        light up (``data-sidebar-drop-target``) before releasing — so a caller's order
        assertion can't race the drop.

        With ``overshoot=True`` the pointer is driven well past the target's far edge — past
        the list container — instead of landing inside it, to exercise a drag beyond the
        container: the dragged element is clamped inside the list, so its rectangle still
        overlaps ``target`` (the extreme item in the drag direction) and keeps it the drop
        target rather than dropping out.
        """
        # Both activators must be on-screen before their box is read: bounding_box() and
        # page.mouse operate on absolute viewport coordinates and do NOT scroll into view
        # or wait for actionability (unlike .click()/.drag_to()). A tall group can push an
        # activator out of the viewport, which would send the pointer to stale pixels.
        for activator in (item, target):
            activator.scroll_into_view_if_needed()
            expect(activator).to_be_visible()

        item_box = item.bounding_box()
        target_box = target.bounding_box()
        assert item_box is not None, "drag item has no bounding box (not visible?)"
        assert target_box is not None, "drag target has no bounding box (not visible?)"

        start_x = item_box["x"] + item_box["width"] / 2
        start_y = item_box["y"] + item_box["height"] / 2
        end_x = start_x
        # `target` is the header activator; the target's droppable rect is the whole group,
        # which extends further, so a point in the header is safely inside the droppable.
        is_dragging_down = target_box["y"] >= item_box["y"]
        if overshoot:
            end_y = (
                target_box["y"] + target_box["height"] + _POINTER_DRAG_OVERSHOOT_PX
                if is_dragging_down
                else target_box["y"] - _POINTER_DRAG_OVERSHOOT_PX
            )
        else:
            target_fraction = (
                _POINTER_DRAG_TARGET_FRACTION_FORWARD if is_dragging_down else _POINTER_DRAG_TARGET_FRACTION_BACKWARD
            )
            end_y = target_box["y"] + target_box["height"] * target_fraction

        mouse = self._page.mouse
        mouse.move(start_x, start_y)
        mouse.down()
        for step in range(1, _POINTER_DRAG_MOVE_STEPS + 1):
            mouse.move(end_x, start_y + (end_y - start_y) * step / _POINTER_DRAG_MOVE_STEPS)
        # The target slot lights up once `over` resolves to it; wait for it so the drop
        # commits against the intended slot (and the assertion below proves the drag
        # actually registered a target rather than releasing over empty space).
        expect(target).to_have_attribute("data-sidebar-drop-target", "true")
        mouse.up()

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

    def get_row_deleting_label(self, workspace_row: Locator) -> Locator:
        """Get the "Deleting…" label of a pending-delete workspace row.

        Like the delete icon, the label is a sibling of the row button inside
        the row container, so it is scoped to the row's parent.
        """
        return workspace_row.locator("..").get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW_DELETING)

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
