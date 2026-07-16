"""Page Object Models for the Layouts feature: the switcher dialog, the save
dialog, the ⌘J / right-click actions, and the Tidy confirmation."""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement

# The undeletable System Default layout's stable id (mirrors SYSTEM_DEFAULT_LAYOUT_ID
# in the frontend); saved layouts get generated uuids, so tests key off names.
SYSTEM_DEFAULT_LAYOUT_ID = "system-default"


class PlaywrightSaveLayoutDialogElement(PlaywrightIntegrationTestElement):
    """POM for the "Save current arrangement as a layout" dialog."""

    def get_name_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_NAME_INPUT)

    def save(self, name: str, *, set_as_default: bool = False, tidy_on_apply: bool = False) -> None:
        """Name the layout, optionally flip the default / tidy-on-apply switches,
        submit, and wait for the dialog to close. The switch flips assume the create
        form's off-by-default starting state; use toggle_tidy_switch for editing."""
        self.get_name_input().fill(name)
        if set_as_default:
            self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DEFAULT_SWITCH).click()
        if tidy_on_apply:
            self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_TIDY_SWITCH).click()
        self.submit()

    def toggle_tidy_switch(self) -> None:
        """Flip the "Tidy panels when applying" switch from its current state (edit
        mode prefills it, so a plain click is a toggle rather than a set)."""
        self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_TIDY_SWITCH).click()

    def submit(self) -> None:
        """Submit the form and wait for the dialog to close."""
        self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_SUBMIT).click()
        expect(self._locator).to_be_hidden()


class PlaywrightLayoutTidyDialogElement(PlaywrightIntegrationTestElement):
    """POM for the Tidy confirmation."""

    def get_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_CONFIRM)

    def confirm(self, *, suppress_future: bool = False) -> None:
        """Confirm the close. When suppress_future is set, tick the global "Don't show
        this again" first so later tidying applies silently."""
        if suppress_future:
            self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_SUPPRESS_CHECKBOX).click()
        self.get_confirm_button().click()
        expect(self._locator).to_be_hidden()

    def cancel(self) -> None:
        self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_CANCEL).click()
        expect(self._locator).to_be_hidden()

    def edit_layout(self) -> None:
        """Follow the "Edit layout to turn off tidying" link, dismissing this dialog."""
        self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_EDIT_LINK).click()
        expect(self._locator).to_be_hidden()


class PlaywrightLayoutsSwitcherElement(PlaywrightIntegrationTestElement):
    """POM for the Layouts switcher dialog (⌘⇧L / sidebar Layouts)."""

    def get_search_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_SEARCH_INPUT)

    def get_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_ROW)

    def get_row_by_id(self, layout_id: str) -> Locator:
        # Kept in the POM to honour the integration-test css-locator ratchet.
        return self._locator.locator(
            f'[data-testid="{ElementIDs.LAYOUTS_SWITCHER_ROW.value}"][data-layout-id="{layout_id}"]'
        )

    def get_system_default_row(self) -> Locator:
        return self.get_row_by_id(SYSTEM_DEFAULT_LAYOUT_ID)

    def get_row_by_name(self, name: str) -> Locator:
        return self.get_rows().filter(has_text=name)

    def open_save_dialog(self) -> PlaywrightSaveLayoutDialogElement:
        # The Save button lives inside the switcher; the dialog it opens is a
        # separate portal-mounted PaletteDialog, so it stays page-scoped.
        self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_SAVE_BUTTON).click()
        dialog = self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DIALOG)
        expect(dialog).to_be_visible()
        return PlaywrightSaveLayoutDialogElement(locator=dialog, page=self._page)

    def open_more_options(self) -> Locator:
        # Both the trigger and its popover render inside the switcher dialog.
        self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_MORE_OPTIONS_BUTTON).click()
        popover = self.get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_POPOVER)
        expect(popover).to_be_visible()
        return popover

    def apply_by_name(self, name: str) -> None:
        """Apply a layout by clicking its row (the user's primary path). Closes the
        switcher; a Tidy confirmation follows only if the layout opts into tidy and
        something would close."""
        self.get_row_by_name(name).click()
        expect(self._locator).to_be_hidden()

    def open_row_context_menu(self, name: str) -> Locator:
        """Right-click a layout row to open its context menu (same actions as ⌘J)."""
        self.get_row_by_name(name).click(button="right")
        menu = self._page.get_by_test_id(ElementIDs.LAYOUTS_ROW_CONTEXT_MENU)
        expect(menu).to_be_visible()
        return menu

    def open_edit_dialog(self, name: str) -> PlaywrightSaveLayoutDialogElement:
        """Right-click a layout row and choose Edit, opening the save form prefilled on
        that layout (where its name / shortcut / tidy / default are changed)."""
        self.open_row_context_menu(name).get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_EDIT).click()
        dialog = self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DIALOG)
        expect(dialog).to_be_visible()
        return PlaywrightSaveLayoutDialogElement(locator=dialog, page=self._page)


def get_layout_tidy_dialog(page: Page) -> PlaywrightLayoutTidyDialogElement:
    dialog = page.get_by_test_id(ElementIDs.LAYOUT_TIDY_DIALOG)
    return PlaywrightLayoutTidyDialogElement(locator=dialog, page=page)
