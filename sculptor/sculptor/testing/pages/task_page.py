import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.actions_panel import PlaywrightActionsPanelElement
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.browser_panel import PlaywrightBrowserPanelElement
from sculptor.testing.elements.changes_panel import PlaywrightChangesPanelElement
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.compaction_header import PlaywrightCompactionBarElement
from sculptor.testing.elements.compaction_panel import PlaywrightCompactionPanelElement
from sculptor.testing.elements.diff_panel import PlaywrightDiffPanelElement
from sculptor.testing.elements.file_browser import PlaywrightFileBrowserElement
from sculptor.testing.elements.history_panel import PlaywrightHistoryPanelElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightTaskPage(PlaywrightProjectLayoutPage):
    def get_chat_panel(self) -> PlaywrightChatPanelElement:
        chat_panel = self.get_by_test_id(ElementIDs.CHAT_PANEL)
        return PlaywrightChatPanelElement(locator=chat_panel, page=self._page)

    def get_agent_tab_bar(self) -> PlaywrightAgentTabBarElement:
        return PlaywrightAgentTabBarElement(page=self._page)

    def get_branch_name_element(self) -> Locator:
        branch_name = self.get_by_test_id(ElementIDs.BRANCH_NAME)
        expect(branch_name).to_be_visible()
        expect(branch_name, "to be generated").not_to_have_attribute("data-is-skeleton", "true")
        return branch_name

    def get_branch_name(self) -> str:
        return self.get_branch_name_element().text_content()

    def get_workspace_banner(self) -> Locator:
        """Get the workspace banner (the repo/branch/target header strip)."""
        return self.get_by_test_id(ElementIDs.WORKSPACE_BANNER)

    def get_repo_segment_button(self) -> Locator:
        """Get the repo-segment button in the banner (collapse priority 2).

        This is unmounted when the banner is too narrow and the
        progressive-collapse logic hides it, so it doubles as a reliable
        signal that the banner has entered its collapsed state.
        """
        return self.get_workspace_banner().get_by_test_id(ElementIDs.REPO_PATH_DROPDOWN_TRIGGER)

    def get_workspace_banner_overflow(self) -> Locator:
        """Locate the collapsed-banner overflow ("...") menu region.

        When the banner is too narrow to show every item, the progressive
        collapse logic hides the lowest-priority items. This locator targets
        the overflow region (marked with ``data-overflow``) that used to render
        an inert "..." menu in their place — tests assert it is not shown.
        """
        return self.get_workspace_banner().locator("[data-overflow]")

    def get_pr_button_create(self) -> Locator:
        """Get the Create PR button locator."""
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_CREATE)

    def get_pr_button_open(self) -> Locator:
        """Get the Open PR button locator."""
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_OPEN)

    def get_pr_button_error(self) -> Locator:
        """Get the Error PR button locator."""
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_ERROR)

    def get_pr_button_error_popover(self) -> Locator:
        """Get the Error PR button popover content (rendered in portal)."""
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_ERROR_POPOVER)

    def get_pr_button_error_details(self) -> Locator:
        """Get the Details summary toggle inside the error popover."""
        return self._page.get_by_test_id(ElementIDs.PR_BUTTON_ERROR_DETAILS)

    def wait_for_pr_button(self, element_id: str, *, timeout: int = 120_000) -> None:
        """Wait for a PR button (create/open/error) to become visible."""
        self._page.get_by_test_id(element_id).wait_for(state="visible", timeout=timeout)

    def get_target_branch_selector(self) -> Locator:
        """Get the target branch selector locator."""
        return self._page.get_by_test_id(ElementIDs.TARGET_BRANCH_SELECTOR)

    def get_task_id(self) -> str:
        """Extract the task ID from the current URL.

        The URL format is: /ws/{workspaceID}/agent/{agentID}
        """
        current_url = self._page.url
        match = re.search(r"/agent/([a-zA-Z0-9_-]+)", current_url)
        if not match:
            raise ValueError(f"Could not extract task ID from URL: {current_url}")
        return match.group(1)

    def activate_file_browser(self) -> None:
        """Ensure the file browser panel is visible by clicking its sidebar icon if needed."""
        file_browser = self._page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
        if not file_browser.is_visible():
            self._page.get_by_test_id(ElementIDs.PANEL_ICON_FILES).click()
            expect(file_browser).to_be_visible()

    def activate_history_panel(self) -> None:
        """Ensure the history panel is visible by opening the file browser and switching to the History tab."""
        self.activate_file_browser()
        file_browser = self.get_file_browser()
        history_tab = file_browser.get_tab_history()
        expect(history_tab).to_be_visible()
        history_tab.click()

    def get_history_panel(self) -> PlaywrightHistoryPanelElement:
        history_panel = self._page.get_by_test_id(ElementIDs.HISTORY_PANEL)
        return PlaywrightHistoryPanelElement(locator=history_panel, page=self._page)

    def activate_changes_panel(self, scope: str = "all") -> None:
        """Ensure the changes panel is visible by opening the File Browser and switching to Changes tab.

        Args:
            scope: Which diff scope to activate — "all" (default, vs target branch)
                   or "uncommitted" (HEAD → working tree).
        """
        file_browser = self._page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
        if not file_browser.is_visible():
            self._page.get_by_test_id(ElementIDs.PANEL_ICON_FILES).click()
            expect(file_browser).to_be_visible()
        changes_tab = self._page.get_by_test_id(ElementIDs.FILE_BROWSER_TAB_CHANGES)
        expect(changes_tab).to_be_visible()
        changes_tab.click()
        if scope == "uncommitted":
            changes_panel = self._page.get_by_test_id(ElementIDs.CHANGES_PANEL)
            scope_btn = changes_panel.get_by_test_id(ElementIDs.DIFF_SCOPE_UNCOMMITTED)
            expect(scope_btn).to_be_visible()
            scope_btn.click()

    def get_commit_button(self) -> Locator:
        """Get the commit button in the changes panel."""
        return self._page.get_by_test_id(ElementIDs.CHANGES_COMMIT_BUTTON)

    def click_review_all(self) -> None:
        """Click the Review All button in the changes panel."""
        review_all_btn = self._page.get_by_test_id(ElementIDs.CHANGES_REVIEW_ALL_BTN)
        expect(review_all_btn).to_be_visible()
        review_all_btn.click()

    def activate_actions_panel(self) -> None:
        """Ensure the actions panel is visible by clicking its tab icon if needed."""
        actions_panel = self._page.get_by_test_id(ElementIDs.ACTIONS_PANEL)
        if not actions_panel.is_visible():
            icon = self._page.locator('[data-panel-icon="actions"]')
            icon.click()
            expect(actions_panel).to_be_visible()

    def get_actions_panel(self) -> PlaywrightActionsPanelElement:
        """Get the actions panel from the docking layout."""
        self.activate_actions_panel()
        actions_panel = self._page.get_by_test_id(ElementIDs.ACTIONS_PANEL)
        return PlaywrightActionsPanelElement(locator=actions_panel, page=self._page)

    def get_browser_panel_icon(self) -> Locator:
        """Return the Browser panel sidebar icon locator."""
        return self._page.get_by_test_id(ElementIDs.PANEL_ICON_BROWSER)

    def get_browser_panel_root(self) -> Locator:
        """Return the Browser panel root locator without opening it."""
        return self._page.get_by_test_id(ElementIDs.BROWSER_PANEL)

    def activate_browser_panel(self) -> None:
        """Ensure the Browser panel is visible by clicking its sidebar icon if needed.

        The panel icon is a toggle whose state persists across workspace
        switches, so a blind click would close an already-open panel.
        """
        icon = self.get_browser_panel_icon()
        expect(icon).to_be_visible()
        panel = self.get_browser_panel_root()
        if panel.is_visible():
            return
        icon.click()
        expect(panel).to_be_visible()

    def get_browser_panel(self, workspace_id: str | None = None) -> PlaywrightBrowserPanelElement:
        """Get the Browser panel, opening it via its sidebar icon if needed.

        When ``workspace_id`` is omitted, returns the currently-visible panel
        (which always belongs to the active workspace).  When set, scopes
        the locator to ``[data-workspace-id="..."]`` — useful for asserting
        which workspace's chrome is rendered without relying on the active
        tab being a side effect of an earlier click.
        """
        self.activate_browser_panel()
        if workspace_id is None:
            browser_panel = self._page.get_by_test_id(ElementIDs.BROWSER_PANEL)
        else:
            browser_panel = self._page.locator(
                f'[data-testid="{ElementIDs.BROWSER_PANEL}"][data-workspace-id="{workspace_id}"]'
            )
        return PlaywrightBrowserPanelElement(locator=browser_panel, page=self._page)

    def get_file_browser(self) -> PlaywrightFileBrowserElement:
        file_browser = self._page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
        return PlaywrightFileBrowserElement(locator=file_browser, page=self._page)

    def get_changes_panel(self) -> PlaywrightChangesPanelElement:
        changes_panel = self._page.get_by_test_id(ElementIDs.CHANGES_PANEL)
        return PlaywrightChangesPanelElement(locator=changes_panel, page=self._page)

    def get_diff_panel(self) -> PlaywrightDiffPanelElement:
        diff_panel = self._page.get_by_test_id(ElementIDs.DIFF_PANEL)
        return PlaywrightDiffPanelElement(locator=diff_panel, page=self._page)

    def get_compaction_bar(self) -> PlaywrightCompactionBarElement:
        compaction_bar = self._page.get_by_test_id(ElementIDs.COMPACTION_BAR)
        return PlaywrightCompactionBarElement(locator=compaction_bar, page=self._page)

    def get_compaction_panel(self) -> PlaywrightCompactionPanelElement:
        # Use page-level locator since Radix popover content renders in a portal
        compaction_panel = self._page.get_by_test_id(ElementIDs.COMPACTION_PANEL)
        return PlaywrightCompactionPanelElement(locator=compaction_panel, page=self._page)

    def get_diff_summary(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DIFF_SUMMARY)

    def get_mode_badge(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_MODE_BADGE)

    def get_thinking_indicator(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.THINKING_INDICATOR)

    def get_error_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ERROR_INPUT)
