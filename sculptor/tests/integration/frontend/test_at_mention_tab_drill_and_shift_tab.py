"""Integration tests for Tab-drill (into a folder) and Shift+Tab (up a folder).

Recent changes introduced a distinction between Enter and Tab in the @-mention
picker:
- Enter on a folder commits it as a mention chip (for folder reveal).
- Tab on a folder drills *into* it, switching the picker to path-mode on the
  selected directory — including gitignored entries that fuzzy search hides.
- Shift+Tab in path-mode walks *up* one directory.

These behaviors are load-bearing for @-mention discovery; a silent regression
would leave users unable to browse into folders from the picker at all.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to drill into a folder in the @-mention picker with Tab")
def test_tab_on_folder_drills_into_path_mode(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Tab on a folder rewrites the query to ``./folder/`` path-mode.

    Verifies the drill-in flow: the picker stays open with the narrowed list
    of entries *inside* that folder (app.py, helpers.py, main.py in the test
    project).  The chat input shows the rewritten query as plain text (not a
    chip yet).
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@src")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    # The first item is the src/ folder (exact filename match).  Waiting for
    # the first item to render guards against Tab firing before the
    # suggestion ``items`` promise resolves (which would no-op the key press).
    expect(chat_panel.get_mention_items().first).to_be_visible()

    # Using ``page.keyboard.press`` instead of ``chat_input.press`` keeps the
    # existing editor focus — ``Locator.press`` refocuses and can interfere
    # with Tab's browser-default focus semantics.
    page.keyboard.press("Tab")

    # Popover stays open with path-mode listing of entries in src/.
    expect(mention_list).to_be_visible()
    # The test project's src/ contains app.py, helpers.py, main.py. At least
    # one of them must appear in the narrowed list.
    expect(mention_list).to_contain_text("app.py")
    expect(mention_list).to_contain_text("main.py")
    # No mention chip was committed — the drill-in path rewrites the query
    # but doesn't produce a chip.
    expect(chat_panel.get_mention_spans()).to_have_count(0)


@user_story("to drill into a folder in the @-mention picker by clicking it")
def test_click_on_folder_drills_into_path_mode(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a folder row drills into it (path-mode), mirroring Tab/ArrowRight.

    SCU-1415 (follow-up to SCU-1296): the mouse must reach a folder's contents
    the same way the keyboard does. A folder row carries a folder affordance,
    so a click opens the next level (the entries inside it) instead of
    committing the folder as a chip. Before the fix a click committed the
    folder and closed the picker, leaving the folder's contents unreachable by
    mouse.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@src")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    # The first item is the src/ folder (exact filename match). Wait for it to
    # render so the click lands on a real row rather than racing the
    # suggestion items() promise.
    first_item = chat_panel.get_mention_items().first
    expect(first_item).to_be_visible()

    # Click the src/ folder row instead of pressing Tab.
    first_item.click()

    # Popover stays open with the path-mode listing of entries inside src/.
    expect(mention_list).to_be_visible()
    expect(mention_list).to_contain_text("app.py")
    expect(mention_list).to_contain_text("main.py")
    # No mention chip was committed — clicking a folder drills in, the same as
    # Tab; it does not commit the folder.
    expect(chat_panel.get_mention_spans()).to_have_count(0)


@user_story("to walk back up one folder in path-mode using Shift+Tab")
def test_shift_tab_walks_up_one_folder(sculptor_instance_: SculptorInstance) -> None:
    """Shift+Tab in path-mode rewrites the query to the parent directory.

    After drilling into ``./src/`` via Tab, Shift+Tab should walk back to
    ``./`` — the workspace root listing — which must include ``README.md``
    and the ``src/`` folder.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@src")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()

    # Drill into src/ so path-mode is active.  ``page.keyboard.press`` keeps
    # the current editor focus rather than re-focusing as ``chat_input.press``
    # would — the latter can interfere with Tab's browser-default focus
    # semantics.
    page.keyboard.press("Tab")
    # Wait for the path-mode drill to fully settle in MentionList's props
    # before firing Shift+Tab.  The editor text being rewritten to
    # ``@./src/`` is necessary but NOT sufficient: TipTap's items() promise
    # must resolve and propagate via updateProps so that
    # MentionList.handleStepBack's closure captures the new
    # ``props.query === "./src/"``.  If Shift+Tab fires before that commit,
    # navigateUpPathMode sees the stale fuzzy query ``"src"``, returns
    # false, and the keypress is silently swallowed (the imperative
    # handler always returns true for Shift+Tab regardless of step-back
    # success), leaving the popover stuck in src/ until the test times out.
    #
    # Path-mode ``./src/`` lists exactly app.py, helpers.py, main.py — once
    # we see 3 items, the new MentionList render has committed and the
    # step-back closure is fresh.  (Fuzzy ``@src`` returns 4: the ``src/``
    # folder itself plus its three contents, so a count of 3 unambiguously
    # marks the mode switch.)
    expect(chat_panel.get_mention_items()).to_have_count(3)

    # Shift+Tab walks up one folder: ``./src/`` → ``./``. Use the explicit
    # down/press/up sequence rather than the ``"Shift+Tab"`` chord — Playwright
    # occasionally dispatches the chord without shiftKey set on the Tab
    # keydown, which makes the popover see plain Tab (drill-in) instead of
    # the step-back signal.
    page.keyboard.down("Shift")
    page.keyboard.press("Tab")
    page.keyboard.up("Shift")

    # Workspace root listing: README.md and src/ are both present.
    expect(mention_list).to_be_visible()
    expect(mention_list).to_contain_text("README")
    # The src/ folder itself is listed at the root.  Use an item-scoped
    # matcher because "src" also appears as a substring elsewhere (e.g. in
    # parent-path hints).
    src_item = chat_panel.get_mention_items().filter(has_text="src").first
    expect(src_item).to_be_visible()


@user_story("to bail out of path-mode drilling by pressing Escape")
def test_escape_after_drill_closes_popover_without_chip(sculptor_instance_: SculptorInstance) -> None:
    """Escape after drilling into a folder dismisses the popover cleanly.

    Regression guard for the path-mode dismissal path.  If Escape failed to
    exit the popover during path-mode, the user would be trapped inside the
    folder browser until they deleted the query by hand.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@src")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()
    page.keyboard.press("Tab")
    expect(mention_list).to_contain_text("app.py")

    page.keyboard.press("Escape")
    expect(mention_list).not_to_be_visible()
    # No chip should have been inserted during the drill.
    expect(chat_panel.get_mention_spans()).to_have_count(0)


@user_story("to commit a folder as a chip with Enter (not Tab)")
def test_enter_on_folder_commits_chip(sculptor_instance_: SculptorInstance) -> None:
    """Enter on a folder commits it as a chip (not drill).

    This is the complement of the Tab-drill test: the two keys have distinct
    actions. Enter on a folder must produce a mention chip so the sent
    message can link back to the folder via the folder-reveal flow.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()

    chat_input.press_sequentially("@src")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    # Wait for the suggestion ``items`` promise to resolve before pressing
    # Enter, otherwise the keypress no-ops against an empty items list.
    expect(chat_panel.get_mention_items().first).to_be_visible()

    page.keyboard.press("Enter")

    # Popover closes and a chip is inserted.
    expect(mention_list).not_to_be_visible()
    mention_spans = chat_panel.get_mention_spans()
    expect(mention_spans).to_be_visible()
    # Chip shows the folder basename (trailing slash stripped).
    expect(mention_spans).to_contain_text("src")
