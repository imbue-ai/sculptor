import re

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.artifacts_panel import PlaywrightArtifactsPanelElement
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.compaction_header import PlaywrightCompactionBarElement
from sculptor.testing.elements.compaction_panel import PlaywrightCompactionPanelElement
from sculptor.testing.elements.task_header import PlaywrightTaskHeaderElement
from sculptor.testing.elements.task_modal import PlaywrightTaskModalElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage


class PlaywrightTaskPage(PlaywrightProjectLayoutPage):
    def get_chat_panel(self) -> PlaywrightChatPanelElement:
        chat_panel = self.get_by_test_id(ElementIDs.CHAT_PANEL)
        return PlaywrightChatPanelElement(locator=chat_panel, page=self._page)

    def get_task_header(self) -> PlaywrightTaskHeaderElement:
        task_header = self.get_by_test_id(ElementIDs.TASK_HEADER)
        return PlaywrightTaskHeaderElement(locator=task_header, page=self._page)

    def get_branch_name_element(self) -> Locator:
        branch_name = self.get_by_test_id(ElementIDs.BRANCH_NAME)
        expect(branch_name).to_be_visible()
        expect(branch_name, "to be generated").not_to_have_attribute("data-is-skeleton", "true")
        return branch_name

    def get_branch_name(self) -> str:
        return self.get_branch_name_element().text_content()

    def get_source_branch_name(self) -> str:
        element = self.get_branch_name_element()
        # await for the data to be non-emtpy as a sanity check
        expect(element, "to have internal attribute").to_have_attribute("data-source-branch", re.compile("."))
        return element.get_attribute("data-source-branch")

    def get_artifacts_panel(self) -> PlaywrightArtifactsPanelElement:
        artifacts_panel = self.get_by_test_id(ElementIDs.ARTIFACT_PANEL)
        return PlaywrightArtifactsPanelElement(locator=artifacts_panel, page=self._page)

    def navigate_to_home(self) -> None:
        """Navigate to home page via the sidebar home button."""
        sidebar = self.ensure_sidebar_is_open()
        sidebar.navigate_to_home()

    def get_task_modal(self) -> PlaywrightTaskModalElement:
        task_modal = self._page.get_by_test_id(ElementIDs.TASK_MODAL)
        return PlaywrightTaskModalElement(locator=task_modal, page=self._page)

    def get_compaction_bar(self) -> PlaywrightCompactionBarElement:
        compaction_bar = self._page.get_by_test_id(ElementIDs.COMPACTION_BAR)
        return PlaywrightCompactionBarElement(locator=compaction_bar, page=self._page)

    def get_compaction_panel(self) -> PlaywrightCompactionPanelElement:
        compaction_panel = self.get_by_test_id(ElementIDs.COMPACTION_PANEL)
        return PlaywrightCompactionPanelElement(locator=compaction_panel, page=self._page)
