"""Perf scenario: switching between two workspaces.

Parametrized across two axes — a *blend* (setup variant) and a
*temperature* (warm/cold). Pytest stacks the parametrize decorators
into a matrix, e.g. ``test_workspace_switch[default-warm]``. The
matrix id becomes the JSONL ``variant`` so downstream analysis can
group by either axis.

Workspaces are switched through the sidebar (``navigate_to_workspace``);
the file browser is the Files panel opened into the left section.
"""

import json
from collections.abc import Callable

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _wait_for_workspace_active(page: Page) -> None:
    """End-signal for a workspace switch: the destination's chat panel renders.

    ``navigate_to_workspace`` already settles on the workspace shell (it waits
    for the section ring host), so this only needs to confirm the chat panel
    for the newly active workspace is up.
    """
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible(timeout=60_000)


# ---- Blends ---------------------------------------------------------------
# Each blend lays out the state the action will operate on. Blends are
# plain functions; compose them by calling one from another rather than
# threading config through a dataclass.


def blend_default(page: Page) -> None:
    """Two workspaces, each with one Fake Claude turn. Leaves page on B."""
    start_task_and_wait_for_ready(page, prompt="hi from A", workspace_name="Perf Workspace A")
    start_task_and_wait_for_ready(page, prompt="hi from B", workspace_name="Perf Workspace B")
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(2)


# Size knobs for the heavy blend. ~20 files × 100 lines per workspace gives
# the diff viewer something non-trivial to render and populates the file
# browser with plenty of rows.
_HEAVY_BLEND_FILES_PER_WS = 20
_HEAVY_BLEND_LINES_PER_FILE = 100


def _write_many_files_prompt(seed: str) -> str:
    """fake_claude:multi_step prompt that writes N files with content seeded
    by ``seed`` so each workspace produces a distinct on-disk state and a
    distinct diff vs. its base branch."""
    steps = []
    for i in range(_HEAVY_BLEND_FILES_PER_WS):
        lines = [
            f"# {seed} file {i:03d} line {j:03d}: " + "abcdefghij" * 4 for j in range(_HEAVY_BLEND_LINES_PER_FILE)
        ]
        steps.append(
            {
                "command": "write_file",
                "args": {
                    "file_path": f"generated/{seed}_file_{i:03d}.py",
                    "content": "\n".join(lines) + "\n",
                },
            }
        )
    return f"fake_claude:multi_step `{json.dumps({'steps': steps})}`"


def _open_files_panel_and_first_file(page: Page, seed: str) -> None:
    """Open the Files panel into the left section, expand ``generated/``, and
    open the seed-specific first file so its diff renders in the embedded
    viewer. ``seed`` selects the file unique to this workspace."""
    section_root = open_panel(page, "files", sub_section="left")
    files_panel = get_files_panel_in(section_root, page)
    # Expand ``generated/`` so the file rows under it become visible.
    folder_row = files_panel.get_tree_rows().filter(has_text="generated").first
    expect(folder_row).to_be_visible()
    if folder_row.get_attribute("aria-expanded") != "true":
        folder_row.click()
    viewer = files_panel.open_file(f"generated/{seed}_file_000.py")
    viewer.assert_diff_shows(f"{seed}_file_000.py")


def blend_with_diff_and_files(page: Page) -> None:
    """Two workspaces, each with ~20 uncommitted files in ``generated/`` and a
    file open in the Files-panel diff viewer. The two workspaces have
    *different* files (``alpha_*`` vs ``beta_*``), so switching genuinely
    retargets the file tree and the diff render.

    Leaves the page on workspace B with B's file open.
    """
    start_task_and_wait_for_ready(page, prompt=_write_many_files_prompt("alpha"), workspace_name="Perf Heavy WS A")
    _open_files_panel_and_first_file(page, seed="alpha")

    start_task_and_wait_for_ready(page, prompt=_write_many_files_prompt("beta"), workspace_name="Perf Heavy WS B")
    _open_files_panel_and_first_file(page, seed="beta")


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("temperature", ["warm", "cold"])
@pytest.mark.parametrize(
    "blend",
    [
        pytest.param(blend_default, id="default"),
        pytest.param(blend_with_diff_and_files, id="with_diff_and_files"),
    ],
)
@user_story("perf: switching between workspaces should not over-fetch or over-render")
def test_workspace_switch(
    sculptor_instance_: SculptorInstance,
    perf_recorder: MeasurementRecorder,
    blend: Callable[[Page], None],
    temperature: str,
    request: pytest.FixtureRequest,
) -> None:
    page = sculptor_instance_.page
    blend(page)

    # The two workspaces created by the blend, named per blend. Switching is by
    # visible name (substring) via the sidebar.
    if blend is blend_default:
        name_a, name_b = "Perf Workspace A", "Perf Workspace B"
    else:
        name_a, name_b = "Perf Heavy WS A", "Perf Heavy WS B"

    if temperature == "warm":
        # Warm both workspaces' caches: switch A -> B -> A.
        navigate_to_workspace(page, name_a)
        _wait_for_workspace_active(page)
        navigate_to_workspace(page, name_b)
        _wait_for_workspace_active(page)
    else:
        # Cold: tear down the SPA so the next switch runs against empty caches.
        full_spa_reload(page)
        perf_recorder.assert_hook_wired()

    variant = request.node.callspec.id
    with perf_recorder.window(scenario="workspace_switch", variant=variant):
        navigate_to_workspace(page, name_a)
        _wait_for_workspace_active(page)
