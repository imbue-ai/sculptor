from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


class PlaywrightAgentTabBarElement:
    """Page Object Model for the agent tab bar and tab context menus."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_agent_tabs(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TAB)

    def get_agent_tab_by_name(self, name: str) -> Locator:
        return self.get_agent_tabs().filter(has_text=name)

    def get_add_agent_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)

    def get_add_agent_chevron_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ADD_AGENT_CHEVRON_BUTTON)

    def get_agent_type_menu(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU)

    def get_agent_type_menu_item_claude(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_CLAUDE)

    def get_agent_type_menu_item_pi(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_PI)

    def get_agent_type_menu_item_terminal(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TYPE_MENU_ITEM_TERMINAL)

    def open_agent_type_menu(self) -> Locator:
        """Click the chevron next to the `+` button and return the open menu."""
        self.get_add_agent_chevron_button().click()
        menu = self.get_agent_type_menu()
        expect(menu).to_be_visible()
        return menu

    def open_diagnostics_submenu(self, tab: Locator) -> None:
        """Right-click a tab and hover on Diagnostics to open the submenu."""
        tab.click(button="right")
        trigger = self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DIAGNOSTICS)
        expect(trigger).to_be_visible()
        trigger.hover()

    def get_copy_session_id_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_SESSION_ID)

    def get_copy_transcript_path_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_TRANSCRIPT_PATH)

    def get_copy_sculptor_transcript_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_COPY_SCULPTOR_TRANSCRIPT_PATH)

    def open_context_menu(self, tab: Locator) -> None:
        """Right-click a tab to open the context menu."""
        tab.click(button="right")

    def get_context_menu_close_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_CLOSE)

    def get_context_menu_rename_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_RENAME)

    def get_context_menu_delete_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)

    def get_context_menu_mark_unread_item(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_MARK_UNREAD)

    def mark_tab_unread(self, tab: Locator) -> None:
        self.open_context_menu(tab)
        mark_unread_item = self.get_context_menu_mark_unread_item()
        expect(mark_unread_item).to_be_visible()
        mark_unread_item.click()

    def get_inline_rename_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.INLINE_RENAME_INPUT)

    def rename_tab(self, tab: Locator, new_name: str) -> None:
        self.open_context_menu(tab)
        rename_item = self.get_context_menu_rename_item()
        expect(rename_item).to_be_visible()
        rename_item.click()
        rename_input = self.get_inline_rename_input()
        expect(rename_input).to_be_visible()
        rename_input.fill(new_name)
        rename_input.press("Enter")
        expect(rename_input).not_to_be_visible()

    def get_tab_close_button(self, tab: Locator) -> Locator:
        return tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)

    def get_delete_confirmation_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    def get_delete_confirmation_confirm_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)

    def delete_agent_via_close_button(self, agent_tab_index: int = 0) -> None:
        """Click the close button on an agent tab and confirm deletion."""
        tab = self.get_agent_tabs().nth(agent_tab_index)
        tab.click()
        close_button = self.get_tab_close_button(tab)
        close_button.click()
        confirm_button = self.get_delete_confirmation_confirm_button()
        expect(confirm_button).to_be_visible()
        confirm_button.click()
