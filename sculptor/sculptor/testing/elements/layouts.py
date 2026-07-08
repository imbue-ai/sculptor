"""Page Object Models for the Layouts feature: the switcher dialog, the save
dialog, and the Apply & tidy confirmation."""

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

    def save(self, name: str, *, set_as_default: bool = False) -> None:
        """Name the layout, optionally flip the default switch, submit, and wait
        for the dialog to close."""
        self.get_name_input().fill(name)
        if set_as_default:
            self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DEFAULT_SWITCH).click()
        self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_SUBMIT).click()
        expect(self._locator).to_be_hidden()


class PlaywrightLayoutTidyDialogElement(PlaywrightIntegrationTestElement):
    """POM for the Apply & tidy confirmation."""

    def get_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_CONFIRM)

    def confirm(self) -> None:
        self.get_confirm_button().click()
        expect(self._locator).to_be_hidden()

    def cancel(self) -> None:
        self._page.get_by_test_id(ElementIDs.LAYOUT_TIDY_CANCEL).click()
        expect(self._locator).to_be_hidden()


class PlaywrightLayoutsSwitcherElement(PlaywrightIntegrationTestElement):
    """POM for the Layouts switcher dialog (⌘⇧L / sidebar Layouts)."""

    def get_search_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_SEARCH_INPUT)

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_ROW)

    def get_row_by_id(self, layout_id: str) -> Locator:
        # Kept in the POM to honour the integration-test css-locator ratchet.
        return self._page.locator(f'[data-testid="{ElementIDs.LAYOUTS_SWITCHER_ROW}"][data-layout-id="{layout_id}"]')

    def get_system_default_row(self) -> Locator:
        return self.get_row_by_id(SYSTEM_DEFAULT_LAYOUT_ID)

    def get_row_by_name(self, name: str) -> Locator:
        return self.get_rows().filter(has_text=name)

    def open_save_dialog(self) -> PlaywrightSaveLayoutDialogElement:
        self._page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_SAVE_BUTTON).click()
        dialog = self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DIALOG)
        expect(dialog).to_be_visible()
        return PlaywrightSaveLayoutDialogElement(locator=dialog, page=self._page)

    def open_more_options(self) -> Locator:
        self._page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_MORE_OPTIONS_BUTTON).click()
        popover = self._page.get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_POPOVER)
        expect(popover).to_be_visible()
        return popover

    def apply_and_tidy_highlighted(self) -> None:
        """Open the ⌘J popover and choose Apply & tidy for the highlighted layout.
        Applies immediately and closes the switcher; a Tidy confirmation follows
        only when something would close."""
        self.open_more_options()
        self._page.get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_APPLY_TIDY).click()
        expect(self._locator).to_be_hidden()


def get_layout_tidy_dialog(page: Page) -> PlaywrightLayoutTidyDialogElement:
    dialog = page.get_by_test_id(ElementIDs.LAYOUT_TIDY_DIALOG)
    return PlaywrightLayoutTidyDialogElement(locator=dialog, page=page)
