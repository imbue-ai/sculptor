from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


class PlaywrightAgentTasksPopoverElement:
    """Page Object Model for the agent-tasks popover triggered from the status pill."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def open(self, *, timeout: int | None = None) -> None:
        """Click the StatusPill to pin the tasks popover open."""
        status_pill = self._page.get_by_test_id(ElementIDs.STATUS_PILL)
        kwargs = {"timeout": timeout} if timeout is not None else {}
        expect(status_pill).to_be_visible(**kwargs)
        status_pill.click()

    def get_empty_state(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_EMPTY_STATE)

    def get_rows(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_ROW)

    def get_row_details(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_ROW_DETAIL)

    def get_waiting_badges(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_WAITING_BADGE)

    def get_graph_toggle(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_GRAPH_TOGGLE)

    def get_graph(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_GRAPH)

    def get_graph_nodes(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.AGENT_TASKS_GRAPH_NODE)
