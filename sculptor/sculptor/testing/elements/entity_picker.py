"""Helpers for driving the `+` prefilter / entity-mention picker in tests.

Keep these driver helpers keyboard-only — typing query text and pressing
Enter — so tests don't depend on rendered text content (which would also
trip the ``integration_test_non_testid_queries`` ratchet) and to mirror the
way a real user reaches a chip with the keyboard.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


class PlaywrightEntityPickerElement:
    """Page Object Model for the entity-mention sub-picker (``+`` prefilter drill-down)."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def get_mention_list(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MENTION_LIST)

    def get_entity_list(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ENTITY_MENTION_LIST)

    def get_entity_items(self) -> Locator:
        return self.get_entity_list().get_by_test_id(ElementIDs.ENTITY_MENTION_ITEM)

    def get_category_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MENTION_PICKER_CATEGORY_ITEM)

    def get_file_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.FILE_MENTION_SUGGESTION_ITEM)

    def get_toolbar_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MENTION_PICKER_TOOLBAR_BUTTON)


def open_workspace_entity_drill(page: Page, chat_input: Locator) -> Locator:
    """Open the ``+`` picker and drill into the workspace-pinned entity list.

    The ``+`` picker is a two-step prefilter: typing ``+`` opens the category
    list (Files & folders / Skills / Workspaces and Agents / Repositories /
    Images); typing ``wor`` uniquely matches the "Workspaces and Agents" row;
    Enter drills into the entity sub-picker pinned to workspaces.

    Returns the entity-item locator, left on the pinned-workspace list with at
    least one row rendered, so callers can filter and commit (or drill further).

    Gating on the category list having settled to the single matching row
    *before* pressing Enter is what keeps the drill deterministic: the
    suggestion plugin's selected index lags a beat behind the filtered items
    (see ``MentionPickerList.test.tsx``), so an Enter fired while the list is
    still mid-filter can commit the wrong category — or, when the list is
    momentarily empty, fall through to a newline that closes the picker
    entirely, leaving the entity list to never appear.
    """
    chat_input.press_sequentially("+wor")

    expect(page.get_by_test_id(ElementIDs.MENTION_LIST)).to_be_visible()
    # Wait for "+wor" to narrow the category list to the single
    # "Workspaces and Agents" row so Enter commits a settled selection.
    category_items = page.get_by_test_id(ElementIDs.MENTION_PICKER_CATEGORY_ITEM)
    expect(category_items).to_have_count(1, timeout=10_000)

    chat_input.press("Enter")

    entity_list = page.get_by_test_id(ElementIDs.ENTITY_MENTION_LIST)
    expect(entity_list).to_be_visible()
    # The drill-in fetches entity rows in an effect, so wait for at least
    # one row to be present before callers start typing — otherwise the next
    # keystroke can race the items() refresh.
    entity_items = entity_list.get_by_test_id(ElementIDs.ENTITY_MENTION_ITEM)
    expect(entity_items.first).to_be_visible(timeout=10_000)
    return entity_items


def insert_workspace_entity_mention(page: Page, chat_input: Locator, workspace_name: str) -> None:
    """Open the ``+`` picker, drill into Workspaces, and commit a workspace.

    Drills into the workspace-pinned list (``open_workspace_entity_drill``),
    types the workspace name to filter to that row, and presses Enter to commit
    an entity-mention node into the editor.
    """
    entity_items = open_workspace_entity_drill(page, chat_input)

    # Type slowly so each keystroke gets a full transaction + items() refresh
    # cycle before the next char arrives. Without the delay, fast successive
    # keystrokes race the picker's effect-driven item refetch — under CI load
    # the picker can briefly drop to 0 rows mid-stream and the suggestion
    # plugin tears down its render before the filtered list re-resolves.
    chat_input.press_sequentially(workspace_name, delay=30)
    # Wait for the filter to settle to a single matching workspace row
    # before committing, so Enter doesn't race the next items() refresh
    # and commit a stale item (or fall through to a newline when items
    # is momentarily empty).
    expect(entity_items).to_have_count(1, timeout=10_000)
    chat_input.press("Enter")
