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

# The built-in layouts a fresh workspace always shows, before any user layout is saved:
# System Default plus the Chat / Review / Terminal / Browser presets. Mirrors
# SYSTEM_LAYOUTS in systemDefaultLayout.ts — keep in sync if presets are added/removed.
BUILT_IN_LAYOUT_COUNT = 5


class PlaywrightSaveLayoutDialogElement(PlaywrightIntegrationTestElement):
    """POM for the "Save current arrangement as a layout" dialog."""

    def get_name_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_NAME_INPUT)

    def get_tidy_switch(self) -> Locator:
        """The "Tidy panels when applying" switch (checked when the layout tidies)."""
        return self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_TIDY_SWITCH)

    def get_shortcut_control(self) -> Locator:
        """The inline keyboard-shortcut recorder row (wraps the HotkeyChip)."""
        return self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_SHORTCUT)

    def record_shortcut(self, chord: str) -> None:
        """Record a keyboard shortcut for this layout: arm the recorder, press the
        chord, and wait for the chip to show the captured value.

        ``chord`` is a Playwright key expression (e.g. ``"Meta+Shift+G"``). The
        recorder maps the platform's primary modifier to a ``Meta``-prefixed chord
        on both macOS and Linux, so pass the platform modifier
        (``get_playwright_modifier_key``) as the first segment. The captured value
        is held locally until the form is saved; the chip's clear button appearing
        confirms the recording completed."""
        control = self.get_shortcut_control()
        control.get_by_test_id(ElementIDs.SETTINGS_HOTKEY_SET_BUTTON).click()
        # Wait for the recorder to arm before pressing: it attaches its capture-phase
        # keydown listener when it shows this prompt, so a chord pressed earlier is lost.
        expect(control).to_contain_text("Press keys")
        self._page.keyboard.press(chord)
        expect(control.get_by_test_id(ElementIDs.SETTINGS_HOTKEY_CLEAR_BUTTON)).to_be_visible()

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

    def get_submit_button(self) -> Locator:
        """The submit button. Its label doubles as the visible mode marker — "Save
        layout" when creating, "Save changes" when editing (the dialog's actual title
        is visually hidden, outside the content node this POM is rooted at)."""
        return self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_SUBMIT)

    def submit(self) -> None:
        """Submit the form and wait for the dialog to close."""
        self.get_submit_button().click()
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

    def get_current_row(self) -> Locator:
        """The row for the workspace's currently-applied layout. The current marker is
        an accent-tinted row icon with no "Current" text, exposed to assertions and
        assistive tech via aria-current, so tests key off the attribute rather than row
        copy. Exactly one row carries it at a time."""
        # Kept in the POM to honour the integration-test css-locator ratchet.
        return self._locator.locator(f'[data-testid="{ElementIDs.LAYOUTS_SWITCHER_ROW.value}"][aria-current="true"]')

    def get_row_by_name(self, name: str) -> Locator:
        return self.get_rows().filter(has_text=name)

    def get_row_shortcut_hint(self, name: str) -> Locator:
        """The keyboard-shortcut hint (kbd) on a layout's row. Rendered only once the
        layout has a bound shortcut — the same binding the runtime dispatcher reads —
        so its visibility gates callers on a registered per-layout shortcut."""
        return self.get_row_by_name(name).locator("kbd")

    def open_save_dialog(self) -> PlaywrightSaveLayoutDialogElement:
        # The Save button lives inside the switcher; the dialog it opens is a
        # separate portal-mounted PaletteDialog, so it stays page-scoped.
        self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_SAVE_BUTTON).click()
        dialog = self._page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DIALOG)
        expect(dialog).to_be_visible()
        return PlaywrightSaveLayoutDialogElement(locator=dialog, page=self._page)

    def open_more_options(self) -> Locator:
        """Open the ⌘J more-options menu (a Radix DropdownMenu) for the highlighted
        layout. The trigger lives in the switcher's bar, but the menu content is
        portaled to the document body, so it is looked up page-scoped."""
        self.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_MORE_OPTIONS_BUTTON).click()
        menu = self._page.get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_POPOVER)
        expect(menu).to_be_visible()
        return menu

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


def get_save_layout_dialog(page: Page) -> PlaywrightSaveLayoutDialogElement:
    """POM for an already-open Save/Edit layout dialog — e.g. the one the tidy
    confirmation's "Edit layout" link opens, rather than the switcher's Save button."""
    dialog = page.get_by_test_id(ElementIDs.SAVE_LAYOUT_DIALOG)
    return PlaywrightSaveLayoutDialogElement(locator=dialog, page=page)
