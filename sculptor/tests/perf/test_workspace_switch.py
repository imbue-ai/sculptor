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
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.alpha_chat_view import wait_for_alpha_scroll_settled
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
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
        # ~1 min on offload — cheap enough to stay in the per-PR fast lane.
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


# ---- long-chat scroll-restore variant -------------------------------------
# Revisiting a workspace whose chat holds many messages and a saved, non-bottom
# scroll position exercises the alpha chat view's scroll restore + pre-paint
# settle (the surface SCU-1686 reworks). It is its own test rather than a blend
# of the matrix above because the measured action differs: it primes a saved
# scroll, and its end-signal is the scroll state machine settling
# (``data-scroll-settled``), not just the chat panel mounting. It reports under
# the same ``workspace_switch`` scenario as the ``long_chat_scrolled`` variant.

# Turns built up in the long workspace (one user + one assistant message each,
# so ~2*N messages). Sized so the virtualized list is many viewports tall
# (scroll restore is only meaningful when scrollHeight >> viewport) while
# keeping Fake Claude setup wall-time bounded. This makes the scenario heavy
# (see the perf_heavy marker), so it runs on main/nightly, not every PR.
_LONG_CHAT_TURNS = 50

# A multi-line assistant reply so each message occupies real vertical space and
# the list scrolls deeply (variable row heights are what the settle sweep
# re-measures).
_LONG_CHAT_PARA = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt. " * 3

# Top-of-list marker (turn 1) and the trivial second workspace's marker, used to
# confirm a switch actually landed (both workspaces share ALPHA_CHAT_VIEW).
_SCROLL_MARKER_A = "SCROLLMARKALPHA"
_SCROLL_MARKER_B = "SCROLLMARKBRAVO"
_SCROLL_A_NAME = "Perf Scroll Long A"
_SCROLL_B_NAME = "Perf Scroll Short B"


def _text_prompt(text: str) -> str:
    return f"fake_claude:text `{json.dumps({'text': text})}`"


def _build_long_chat(page: Page) -> PlaywrightChatPanelElement:
    """Workspace A with ``_LONG_CHAT_TURNS`` completed turns; turn 1 carries the
    top-of-list marker so a restore-to-top is detectable after a revisit."""
    task_page: PlaywrightTaskPage = start_task_and_wait_for_ready(
        page, prompt=_text_prompt(f"{_SCROLL_MARKER_A} response 1. {_LONG_CHAT_PARA}"), workspace_name=_SCROLL_A_NAME
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    queue_bar = chat_panel.get_queued_message_bar()
    thinking = chat_panel.get_thinking_indicator()
    for i in range(2, _LONG_CHAT_TURNS + 1):
        send_chat_message(chat_panel=chat_panel, message=_text_prompt(f"response {i}. {_LONG_CHAT_PARA}"))
        # Idle signal between sends (empty queue + no thinking indicator); the
        # per-turn wait grows with history, so give it headroom.
        expect(queue_bar).to_have_count(0, timeout=90_000)
        expect(thinking).not_to_be_visible(timeout=90_000)
    return chat_panel


@pytest.mark.perf_heavy
@user_story("perf: revisiting a long-chat workspace should restore scroll without excess render/settle")
def test_workspace_switch_long_chat_scroll(
    sculptor_instance_: SculptorInstance,
    perf_recorder: MeasurementRecorder,
) -> None:
    page = sculptor_instance_.page

    # Build the long workspace A and a trivial workspace B. Page ends on B.
    _build_long_chat(page)
    start_task_and_wait_for_ready(
        page, prompt=_text_prompt(f"{_SCROLL_MARKER_B} only turn"), workspace_name=_SCROLL_B_NAME
    )
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(2)

    # Prime A's saved scroll to the top (a non-bottom position the revisit must
    # restore), then leave to B. The first visit restores to the bottom, so the
    # marker only becomes visible after we scroll to the top.
    navigate_to_workspace(page, _SCROLL_A_NAME)
    wait_for_alpha_scroll_settled(page)
    scroll_alpha_chat_to_top(page)
    expect(get_alpha_chat_view(page)).to_contain_text(_SCROLL_MARKER_A)
    # Let the rAF-debounced scroll save record the top position.
    page.wait_for_timeout(1200)

    navigate_to_workspace(page, _SCROLL_B_NAME)
    expect(get_alpha_chat_view(page)).to_contain_text(_SCROLL_MARKER_B)
    wait_for_alpha_scroll_settled(page)

    # Measured action: revisit A. The switch remounts A's chat, restores the
    # saved top scroll, and settles the virtualizer's measurements. The
    # ``mounted`` checkpoint marks the target content arriving, so the remaining
    # commits/DOM up to the settled signal are the restore+settle phase.
    with perf_recorder.window(scenario="workspace_switch", variant="long_chat_scrolled") as w:
        navigate_to_workspace(page, _SCROLL_A_NAME)
        w.checkpoint("mounted", wait_for=lambda: expect(get_alpha_chat_view(page)).to_contain_text(_SCROLL_MARKER_A))
        wait_for_alpha_scroll_settled(page)
