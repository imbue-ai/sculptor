"""Real pi integration test: file edits land via pi's own tool loop.

Pi internally invokes Read/Edit/Write/Bash against the workspace — Sculptor
takes no part in pi's tool plumbing. Sculptor's file-watching layer notices
the mutations and surfaces them in the diff sidebar. This test exercises
that pi-side-tool-loop → Sculptor-side-watcher path end-to-end.
"""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import real_pi

_NEW_FILE_NAME = "pi_real_edit_92740.txt"


@real_pi
@pytest.mark.timeout(600)
def test_pi_creates_file_visible_in_changes_panel(sculptor_instance_: SculptorInstance) -> None:
    prompt = (
        f"Use your file-writing tool to create a new file named '{_NEW_FILE_NAME}' at the workspace root,"
        + " with the single-line contents 'hello-pi-92740'. After the file exists, reply with exactly DONE-92740."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().last).to_contain_text("DONE-92740")
    expect(chat_panel.get_error_block()).to_have_count(0)

    task_page.activate_changes_panel(scope="uncommitted")
    changes_tree = sculptor_instance_.page.get_by_test_id(ElementIDs.FILE_BROWSER_CHANGES_TREE)
    expect(changes_tree).to_contain_text(_NEW_FILE_NAME)
