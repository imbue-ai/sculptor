"""Tests that a file @-mention chip with a ``~/`` path opens the home-dir file.

Regression test for SCU-1528: the file viewer treated a leading ``~`` literally
and resolved it against the workspace (opening ``<workspace>/~/<file>``) instead
of expanding ``~`` to the environment's home directory.  This drives the full
pipeline: ``@~/<file>`` path-mode mention -> committed file chip -> click on the
rendered chip -> ``openFileViewTabAtom`` -> the ``read-file`` endpoint ->
``ReadOnlyPreview`` showing the home file's content.

Sibling to ``test_at_mention_file_chip_click_opens_tab.py`` (the workspace-relative
branch of the same chip-click flow) and ``test_at_mention_path_mode.py`` (the
``@~/`` path-mode picker).  The home-sentinel fixture mirrors
``test_path_tilde_display.py``.
"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.fixture
def _home_marker_file() -> Generator[str, None, None]:
    """Create a uniquely-named file under HOME and yield its basename.

    The file viewer resolves a ``~/`` path against the environment's home
    directory, which for the local test environment is the real ``$HOME`` the
    server inherits.  We need a real, readable file there to prove the fix reads
    the home file rather than ``<workspace>/~/<file>``.  The pid-suffixed name
    keeps parallel test workers from colliding; mirrors the home-sentinel
    pattern in ``test_path_tilde_display.py``.
    """
    marker = Path.home() / f"scu1528_home_marker_{os.getpid()}.txt"
    marker.write_text("SCU-1528 home file contents\n")
    try:
        yield marker.name
    finally:
        marker.unlink(missing_ok=True)


@user_story("to open a ~/ file chip and read the file from my home directory")
def test_file_chip_with_tilde_path_opens_home_file(
    sculptor_instance_: SculptorInstance,
    _home_marker_file: str,
) -> None:
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    # Typing ``@~/<name>`` switches the picker into path mode (a live filesystem
    # listing of $HOME) and filters to the marker file.  Enter commits a file
    # chip whose id carries the literal ``~/`` path.
    chat_input.press_sequentially(f"@~/{_home_marker_file}")
    expect(mention_list).to_be_visible()
    # Wait for the filtered entry to render before pressing Enter, otherwise the
    # keypress no-ops against an empty list.
    expect(chat_panel.get_mention_items().first).to_be_visible()
    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    editor_chip = chat_panel.get_mention_spans()
    expect(editor_chip).to_be_visible()

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()
    latest_user_message = alpha_view.get_user_messages().last
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chip).to_be_visible()

    # Clicking the rendered ``~/`` chip must open the file viewer on the home
    # file.  Before the fix the viewer resolved ``<workspace>/~/<file>`` -> 404
    # -> "Could not load file content"; after the fix ``~`` expands to $HOME and
    # the read-only preview renders the file.
    rendered_chip.click()

    diff_panel = get_diff_panel_from_page(page)
    diff_panel.expect_shows_file(_home_marker_file)
