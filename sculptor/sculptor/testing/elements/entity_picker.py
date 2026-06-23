"""Helpers for driving the `+` prefilter / entity-mention picker in tests.

Keep these driver helpers keyboard-only — typing query text and pressing
Enter — so tests don't depend on rendered text content (which would also
trip the ``integration_test_non_testid_queries`` ratchet) and to mirror the
way a real user reaches a chip with the keyboard.
"""

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import get_tiptap_doc
from sculptor.testing.elements.base import set_tiptap_doc

# Per-attempt budget for one open-and-drill try. Short on purpose: combined with
# the _DRILL_TOTAL_TIMEOUT retry budget below it replaces a single 30s expect()
# wait rather than tightening it (the dismiss_with_escape pattern in
# docs/development/review/integration_tests.md), so it is not a no_lowered_timeouts
# violation.
_DRILL_ATTEMPT_TIMEOUT_MS = 4_000
_DRILL_TOTAL_TIMEOUT_S = 30.0


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


@retry(
    stop=stop_after_delay(_DRILL_TOTAL_TIMEOUT_S),
    wait=wait_fixed(0.2),
    retry=retry_if_exception_type((AssertionError, PlaywrightError)),
    reraise=True,
)
def _attempt_open_workspace_drill(
    chat_input: Locator,
    snapshot: list[object],
    mention_list: Locator,
    category_items: Locator,
    entity_list: Locator,
) -> None:
    """One open-and-drill try: type ``+wor`` and Enter into the workspace list.

    Retried as a unit by the decorator so either race below recovers on a later
    attempt. ``snapshot`` is a one-element box: the first attempt that can read
    the editor records its pre-drill document into it; later attempts restore
    that document, dropping a failed attempt's leftover ``+wor`` *without* wiping
    content a caller already inserted (e.g. an earlier mention chip — a blanket
    ``clearContent`` would erase it, which broke two-mention drafts).
    """
    if snapshot:
        set_tiptap_doc(chat_input, snapshot[0])
    else:
        snapshot.append(get_tiptap_doc(chat_input))
    chat_input.press_sequentially("+wor")
    expect(mention_list).to_be_visible(timeout=_DRILL_ATTEMPT_TIMEOUT_MS)
    # Wait for "+wor" to narrow the category list to the single
    # "Workspaces and Agents" row so Enter commits a settled selection.
    expect(category_items).to_have_count(1, timeout=_DRILL_ATTEMPT_TIMEOUT_MS)
    chat_input.press("Enter")
    expect(entity_list).to_be_visible(timeout=_DRILL_ATTEMPT_TIMEOUT_MS)


def open_workspace_entity_drill(page: Page, chat_input: Locator) -> Locator:
    """Open the ``+`` picker and drill into the workspace-pinned entity list.

    The ``+`` picker is a two-step prefilter: typing ``+`` opens the category
    list (Files & folders / Skills / Workspaces and Agents / Repositories /
    Images); typing ``wor`` uniquely matches the "Workspaces and Agents" row;
    Enter drills into the entity sub-picker pinned to workspaces.

    Returns the entity-item locator, left on the pinned-workspace list with at
    least one row rendered, so callers can filter and commit (or drill further).

    The whole open-and-drill is retried as a unit, because two independent races
    each break a single-shot attempt (both confirmed via offload-repro traces):

    1. The ``+wor`` keystrokes can land in the chat input before its Tiptap
       editor is wired after an agent/workspace switch, so the picker never
       opens (or its category filter resolves to zero rows).
    2. Even with the category list settled to the single "Workspaces and Agents"
       row, the Enter that should drill in occasionally commits-and-closes the
       picker instead — the suggestion plugin's keydown handler races the
       filtered render — so the entity sub-list never appears.

    Re-issuing the whole sequence (restore the pre-drill content, retype,
    re-press Enter) recovers from either: a later attempt types into the
    now-ready editor and its Enter lands the drill. Each attempt is short; the
    retry budget supplies the overall wait.
    """
    entity_list = page.get_by_test_id(ElementIDs.ENTITY_MENTION_LIST)
    _attempt_open_workspace_drill(
        chat_input=chat_input,
        # One-element box: the pre-drill editor doc is captured into it on the
        # first attempt and restored on retries (see _attempt_open_workspace_drill).
        snapshot=[],
        mention_list=page.get_by_test_id(ElementIDs.MENTION_LIST),
        category_items=page.get_by_test_id(ElementIDs.MENTION_PICKER_CATEGORY_ITEM),
        entity_list=entity_list,
    )

    # The drill-in fetches entity rows in an effect, so wait for at least
    # one row to be present before callers start typing — otherwise the next
    # keystroke can race the items() refresh.
    entity_items = entity_list.get_by_test_id(ElementIDs.ENTITY_MENTION_ITEM)
    expect(entity_items.first).to_be_visible()
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
    expect(entity_items).to_have_count(1)
    chat_input.press("Enter")
