"""Perf scenario: switching between two workspaces.

Parametrized across two axes — a *blend* (setup variant) and a
*temperature* (warm/cold). Pytest stacks the parametrize decorators
into a matrix, e.g. ``test_workspace_switch[default-warm]``. The
matrix id becomes the JSONL ``variant`` so downstream analysis can
group by either axis.
"""

import json
from collections.abc import Callable

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _wait_for_workspace_active(page: Page, tab_locator) -> None:
    """End-signal for a workspace switch: tab selected, chat + file tree visible.

    Either the ``All`` tree (FILE_BROWSER_FILE_TREE) or the ``Changes`` tree
    (FILE_BROWSER_CHANGES_TREE) counts as a rendered file panel — they're
    distinct DOM nodes for the same panel surface, and the active one
    depends on which tab was previously selected on that workspace.
    The inactive tree stays mounted under ``display: none``, so we filter
    via the ``:visible`` engine rather than ``.or_().first`` (which would
    snap to whichever node the DOM happens to iterate first — usually the
    hidden one).
    """
    expect(tab_locator).to_have_attribute("aria-selected", "true")
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible()
    tree_selector = ", ".join(
        f"[data-testid='{tid}']:visible"
        for tid in (ElementIDs.FILE_BROWSER_FILE_TREE, ElementIDs.FILE_BROWSER_CHANGES_TREE)
    )
    expect(page.locator(tree_selector)).to_be_visible()


# ---- Blends ---------------------------------------------------------------
# Each blend lays out the state the action will operate on. Blends are
# plain functions; compose them by calling one from another rather than
# threading config through a dataclass.


def blend_default(page: Page) -> None:
    """Two workspaces, each with one Fake Claude turn. Leaves page on B."""
    start_task_and_wait_for_ready(page, prompt="hi from A", workspace_name="Perf Workspace A")
    start_task_and_wait_for_ready(page, prompt="hi from B", workspace_name="Perf Workspace B")
    expect(page.get_by_test_id(ElementIDs.WORKSPACE_TAB)).to_have_count(2)


# Size knobs for the heavy blend. ~20 files × 100 lines per workspace gives
# the diff panel something non-trivial to render and populates the file
# browser changes tab with plenty of rows.
_HEAVY_BLEND_FILES_PER_WS = 20
_HEAVY_BLEND_LINES_PER_FILE = 100


def _write_many_files_prompt(seed: str) -> str:
    """fake_claude:multi_step prompt that writes N files with content seeded
    by ``seed`` so each workspace produces a distinct on-disk state and a
    distinct diff vs. its base branch."""
    steps = []
    for i in range(_HEAVY_BLEND_FILES_PER_WS):
        # Lines are short but unique so the diff renderer has real per-line
        # content to draw, not collapse-able blank lines.
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


def _open_first_changed_file(page: Page, seed: str) -> None:
    """Open the file browser Changes tab and click the first generated file
    so the diff panel renders. ``seed`` selects the file unique to this
    workspace (alpha_file_000 vs beta_file_000).

    Don't toggle the files-panel icon — it's a TOGGLE button, and the panel
    is already active by default after ``start_task_and_wait_for_ready``.
    Clicking would close the panel and hide all the tabs we're about to use.
    """
    expect(page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)).to_be_visible()
    page.get_by_test_id(ElementIDs.FILE_BROWSER_TAB_CHANGES).click()
    changes_tree = page.get_by_test_id(ElementIDs.FILE_BROWSER_CHANGES_TREE)
    expect(changes_tree).to_be_visible()
    # Expand ``generated/`` if collapsed.
    folder_row = changes_tree.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW).filter(has_text="generated").first
    expect(folder_row).to_be_visible()
    if folder_row.get_attribute("aria-expanded") != "true":
        folder_row.click()
    # Click the seed-named file. ``filter(has_text=...)`` matches any row
    # containing this substring; ``_file_000`` is unique to the first file.
    file_row = changes_tree.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW).filter(has_text=f"{seed}_file_000").first
    expect(file_row).to_be_visible()
    file_row.click()
    expect(page.get_by_test_id(ElementIDs.DIFF_PANEL)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.DIFF_FILE_HEADER)).to_contain_text(f"{seed}_file_000")


def blend_with_diff_and_files(page: Page) -> None:
    """Two workspaces, each with ~20 uncommitted files in ``generated/`` and
    a big diff open on a selected file. The two workspaces have *different*
    files (``alpha_*`` vs ``beta_*``), so switching genuinely retargets the
    file tree, the changes list, and the diff render.

    Leaves the page on workspace B with B's diff open.
    """
    start_task_and_wait_for_ready(page, prompt=_write_many_files_prompt("alpha"), workspace_name="Perf Heavy WS A")
    _open_first_changed_file(page, seed="alpha")

    start_task_and_wait_for_ready(page, prompt=_write_many_files_prompt("beta"), workspace_name="Perf Heavy WS B")
    _open_first_changed_file(page, seed="beta")


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

    tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    tab_a, tab_b = tabs.first, tabs.last

    if temperature == "warm":
        # Warm both workspaces' caches: switch A → B → A.
        tab_a.click()
        _wait_for_workspace_active(page, tab_a)
        tab_b.click()
        _wait_for_workspace_active(page, tab_b)
    else:
        # Cold: tear down the SPA so the next click runs against empty caches.
        full_spa_reload(page)
        perf_recorder.assert_hook_wired()

    variant = request.node.callspec.id
    with perf_recorder.window(scenario="workspace_switch", variant=variant):
        tab_a.click()
        _wait_for_workspace_active(page, tab_a)
