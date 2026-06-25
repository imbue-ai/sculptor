import re
from typing import Literal

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.actions_panel import PlaywrightActionsPanelElement
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.changes_panel import PlaywrightChangesPanelElement
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.compaction_header import PlaywrightCompactionBarElement
from sculptor.testing.elements.compaction_panel import PlaywrightCompactionPanelElement
from sculptor.testing.elements.diff_panel import PlaywrightDiffPanelElement
from sculptor.testing.elements.file_browser import PlaywrightFileBrowserElement
from sculptor.testing.elements.review_all_panel import PlaywrightReviewAllPanelElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightTaskPage(PlaywrightProjectLayoutPage):
    def get_chat_panel(self) -> PlaywrightChatPanelElement:
        chat_panel = self.get_by_test_id(ElementIDs.CHAT_PANEL)
        return PlaywrightChatPanelElement(locator=chat_panel, page=self._page)

    def get_agent_tab_bar(self) -> PlaywrightAgentTabBarElement:
        """Get the agent-tab-bar shim over the center section's panel tabs.

        Agents render as panel tabs in the center section header
        (``PANEL_TAB-agent:<id>``), created from the section's add-panel dropdown.
        The returned shim maps the legacy agent-tab-bar API (reads / creation /
        rename / close / diagnostics / status dot) onto the new panel-tab POMs.
        """
        return PlaywrightAgentTabBarElement(self._page)

    def get_branch_name_element(self) -> Locator:
        branch_name = self.get_by_test_id(ElementIDs.BRANCH_NAME)
        expect(branch_name).to_be_visible()
        expect(branch_name, "to be generated").not_to_have_attribute("data-is-skeleton", "true")
        return branch_name

    def get_branch_name(self) -> str:
        return self.get_branch_name_element().text_content() or ""

    def get_workspace_header(self) -> Locator:
        """Get the workspace header (the branch/target strip above the section grid).

        This is the successor to the old ``WORKSPACE_BANNER`` strip; the
        progressive-collapse banner is gone, replaced by the simpler
        ``WorkspaceHeader`` (section toggles + branch pill + target-branch
        selector + the re-homed diff summary / PR button).
        """
        return self.get_by_test_id(ElementIDs.WORKSPACE_HEADER)

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

    def get_target_branch_options(self) -> Locator:
        """Get the branch option items inside the open target-branch selector."""
        return self._page.get_by_test_id(ElementIDs.BRANCH_OPTION)

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
        """Reveal the Files panel (a registered panel seeded in the left section)."""
        open_panel(self._page, "files", "left")

    def activate_changes_panel(self, scope: Literal["all", "uncommitted"] = "all") -> None:
        """Reveal the Changes panel (a registered panel seeded in the left section).

        Args:
            scope: Which diff scope to activate — "all" (default, vs target branch)
                   or "uncommitted" (HEAD → working tree).
        """
        open_panel(self._page, "changes", "left")
        if scope == "uncommitted":
            changes_panel = self._page.get_by_test_id(ElementIDs.CHANGES_PANEL)
            scope_btn = changes_panel.get_by_test_id(ElementIDs.DIFF_SCOPE_UNCOMMITTED)
            expect(scope_btn).to_be_visible()
            scope_btn.click()

    def get_commit_button(self) -> Locator:
        """Get the commit button in the changes panel."""
        return self._page.get_by_test_id(ElementIDs.CHANGES_COMMIT_BUTTON)

    def click_review_all(self) -> None:
        """Reveal the Review All panel (the combined multi-file diff).

        In the section shell there is no "Review all" button on the Changes panel:
        review-all is its own no-default-section registered panel, opened from a
        section's add-panel ``+`` dropdown like any other single-instance panel.
        Open it into the left section (where the review surfaces live) and wait for
        its root so callers can interact with the combined diff.
        """
        section_root = open_panel(self._page, "review-all", "left")
        expect(section_root.get_by_test_id(ElementIDs.REVIEW_ALL_PANEL)).to_be_visible()

    def activate_actions_panel(self) -> None:
        """Reveal the Actions panel (a registered panel) in the right section."""
        open_panel(self._page, "actions", "right")

    def get_actions_panel(self) -> PlaywrightActionsPanelElement:
        """Get the actions panel, revealing it first."""
        self.activate_actions_panel()
        actions_panel = self._page.get_by_test_id(ElementIDs.ACTIONS_PANEL)
        return PlaywrightActionsPanelElement(locator=actions_panel, page=self._page)

    def get_file_browser(self) -> PlaywrightFileBrowserElement:
        file_browser = self._page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
        return PlaywrightFileBrowserElement(locator=file_browser, page=self._page)

    def get_changes_panel(self) -> PlaywrightChangesPanelElement:
        changes_panel = self._page.get_by_test_id(ElementIDs.CHANGES_PANEL)
        return PlaywrightChangesPanelElement(locator=changes_panel, page=self._page)

    def get_review_all_panel(self) -> PlaywrightReviewAllPanelElement:
        """Get the Review All panel POM, scoped to ``REVIEW_ALL_PANEL``.

        The Review All panel embeds ``CombinedDiffView`` directly under
        ``REVIEW_ALL_PANEL`` with no ``DIFF_PANEL`` wrapper, so its scope picker,
        file sections, and diff views are reached from the panel root itself
        rather than via ``get_diff_viewer_in`` (which resolves ``DIFF_PANEL``).
        """
        review_all_panel = self._page.get_by_test_id(ElementIDs.REVIEW_ALL_PANEL)
        return PlaywrightReviewAllPanelElement(locator=review_all_panel, page=self._page)

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
