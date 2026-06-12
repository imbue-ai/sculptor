"""Integration test: the diff loading bar must not appear when no file is open.

Regression for SCU-1329 ("Diff loading state appears when I have no file open").
The DiffPanel's top progress bar was gated only on the workspace-level diff
``isFetching`` flag, which is true during any background or forced diff fetch
regardless of whether a file tab is open. As a result the loading bar flashed
over the empty "Open a file to view it" placeholder.

This test holds a forced diff fetch in flight (so ``isFetching`` stays true)
while a file is open — the bar correctly shows — then closes the tab so the
panel falls back to the empty placeholder *without* the fetch completing. The
bar must disappear once no file is open. Before the fix it stayed visible.
"""

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A single file write so the workspace has an uncommitted diff to open.
_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""

_DIFF_URL_GLOB = "**/workspaces/*/diff*"


@user_story("to not see the diff loading bar when no file is open")
def test_diff_loading_bar_hidden_when_no_file_open(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes tab (Uncommitted scope) and open hello.py in the diff viewer.
    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    changes_panel = task_page.get_changes_panel()
    changes_panel.get_scope_uncommitted().click()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    changes_tree.get_tree_rows().filter(has_text="hello.py").click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    expect(diff_panel.get_tab_by_name("hello.py")).to_be_visible()

    # Hold every forced workspace-diff fetch in flight until the test releases
    # it. This keeps ``isFetching`` true across the tab-close transition we
    # assert on, so the bar's visibility is decided purely by the file-open
    # gate, not by a race against a fast fetch completing.
    release = {"now": False}

    def _hold_diff(route: Route) -> None:
        if "/diff" in route.request.url:
            while not release["now"]:
                page.wait_for_timeout(50)
        route.continue_()

    page.route(_DIFF_URL_GLOB, _hold_diff)
    try:
        # Force a diff refetch; the route hold keeps it in flight.
        file_browser.get_refresh_button().click()

        # While a file is open and its diff is fetching, the bar correctly shows.
        # (This is preserved behaviour — it passes both before and after the fix.)
        expect(diff_panel.get_loading_bar()).to_be_visible()

        # Close the only open tab. The panel stays open and falls back to the
        # empty "Open a file to view it" placeholder while the diff fetch is
        # STILL in flight.
        diff_panel.close_tab("hello.py")
        expect(diff_panel).to_contain_text("Open a file to view it")

        # The loading bar must now be gone: no file is open, so there is nothing
        # to load in the panel — even though the workspace diff fetch is still
        # in flight. Before the SCU-1329 fix the bar stayed visible here.
        expect(diff_panel.get_loading_bar()).to_have_count(0)
    finally:
        release["now"] = True
        # Let the held request continue before tearing down the route.
        page.wait_for_timeout(100)
        page.unroute(_DIFF_URL_GLOB, _hold_diff)
