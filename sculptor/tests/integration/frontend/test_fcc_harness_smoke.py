"""Smoke test for the shared Files/Changes/Commits (FCC) test harness (Task 3.6a).

Proves the harness foundation works end-to-end so the per-panel content tests
(Tasks 3.6b-e) can build on it:

- the shared open-a-panel helper opens a panel via the section `+` add-panel
  dropdown (no layout / localStorage seeding);
- the opened Files panel renders the ExplorerLayout list + the embedded DiffViewer
  (FCC-04/06).

No content assertions — only that the harness brings the panel on screen and the
list + viewer scaffold renders.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to open the Files panel from the add-panel dropdown and see its list and viewer")
def test_open_files_panel_renders_list_and_viewer(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The open-a-panel helper opens Files; its list + embedded viewer render.

    Steps:
    1. Create a workspace (lands on the workspace shell with the center agent).
    2. Open the Files panel via the shared add-panel-dropdown helper.
    3. Verify the ExplorerLayout list renders.
    4. Verify the embedded DiffViewer renders (its empty placeholder is fine).
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace + first agent.
    start_task_and_wait_for_ready(page, prompt="FCC harness smoke", workspace_name="FCC Smoke WS")

    # Step 2: Open Files through the UI (section `+` -> add-panel dropdown).
    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)

    # Step 3: The ExplorerLayout list (file tree) renders.
    expect(files_panel.get_list()).to_be_visible()

    # Step 4: The embedded DiffViewer renders (nothing selected -> empty body).
    expect(files_panel.get_diff_viewer()).to_be_visible()
