"""Integration test for the workspace switcher's attention + recency ordering.

The command-palette workspace switcher (`workspaces.switch` sub-page) sorts
workspaces attention-first, then by recency within each attention tier:

    WAITING  ->  UNACKED_ERROR  ->  IDLE

This drives five real workspaces so the expected order is neither creation order
nor pure recency — it can only be produced by sorting on tier first and recency
second:

  - one WAITING workspace (an agent asking a question) — the current, focused
    workspace; see the note below on why waiting is exercised focused-only;
  - two UNACKED_ERROR workspaces (agents that crashed while unfocused), to
    check recency ordering within the error tier;
  - two IDLE workspaces (empty, no agent), to check recency within the idle
    tier.

Note on the single waiting workspace: the FakeClaude harness only holds a
pending AskUserQuestion (TaskStatus.WAITING) while its workspace is focused —
backgrounding it tears the fake agent down and the task settles to READY. So a
second, unfocused waiting workspace can't be reproduced here. The tier ranking
itself (including multiple waiting workspaces) is covered by the
``getWorkspaceAttentionRank`` unit tests; this test verifies the end-to-end DOM
ordering with the states the harness reliably produces.
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import create_zero_agent_workspace
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import wait_for_workspace_list_loaded
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# FakeClaude fires the crash this many seconds after the turn starts. The test
# navigates home immediately after creating an error workspace, so the crash
# lands while that workspace is unfocused and therefore stays UN-ACKED (tier
# UNACKED_ERROR rather than the acked-error IDLE tier; viewing an error
# acknowledges it). It also settles the crash (via the peek popover) before
# continuing, so a pending crash never disrupts the next creation.
_ERROR_DELAY_SECONDS = 4

# An AskUserQuestion leaves the agent in WAITING (it never completes the turn),
# which is the top attention tier.
_WAITING_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Proceed?",
      "header": "Confirm",
      "options": [
        {"label": "Yes", "description": "Go ahead"},
        {"label": "No", "description": "Stop"}
      ],
      "multiSelect": false
    }
  ]
}`"""


def _current_workspace_id(page: Page) -> str:
    """The workspace id in the current URL (``/ws/<id>/agent/<id>``)."""
    match = re.search(r"/ws/([^/?#]+)", page.url)
    assert match is not None, f"no workspace id in url: {page.url}"
    return match.group(1)


def _make_idle_workspace(page: Page, name: str) -> str:
    """An empty (no-agent) workspace → the IDLE tier.

    A workspace with no tasks ranks as idle, so an empty workspace is the
    lightest way to populate that tier — and it sidesteps the modal
    create-flow entirely (the backend API path dedupes branch names on its
    own). Recency within the tier still comes from the workspace's createdAt.
    """
    return create_zero_agent_workspace(page, description=name)


def _make_waiting_workspace(page: Page, name: str) -> str:
    """A workspace whose agent is asking a question → the WAITING tier."""
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_WAITING_PROMPT,
        workspace_name=name,
        # AUQ never finishes the turn, so wait for the panel itself as the
        # WAITING signal rather than for completion.
        wait_for_agent_to_finish=False,
    )
    expect(get_ask_user_question_panel(page)).to_be_visible(timeout=30_000)
    return _current_workspace_id(page)


def _make_error_workspace(page: Page, layout: PlaywrightProjectLayoutPage, name: str) -> str:
    """A workspace whose agent crashes while unfocused → the UNACKED_ERROR tier.

    Starts a delayed crash, then immediately navigates home so the crash lands
    while the workspace is unfocused (un-acked). Settles the crash here — via
    the peek popover, which hovering does NOT acknowledge — so the switcher
    order is already stable when we assert it, and no pending crash disrupts a
    later creation.
    """
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:crash `{{"delay_seconds": {_ERROR_DELAY_SECONDS}}}`',
        workspace_name=name,
        wait_for_agent_to_finish=False,
    )
    workspace_id = _current_workspace_id(page)

    navigate_to_home_page(page)
    # Hover (not click) the sidebar row so the crash is observed without
    # navigating into — and thereby acknowledging — the workspace.
    get_workspace_sidebar(page).get_workspace_row_by_name(name).hover()
    peek = layout.get_workspace_peek_popover()
    expect(peek).to_be_visible()
    expect(peek.get_header()).to_contain_text(name)
    expect(peek.get_banner()).to_contain_text("error", timeout=30_000)
    page.mouse.move(0, 0)  # Dismiss the popover before the next action.
    return workspace_id


@user_story("to see the workspaces that need my attention sorted to the top of the switcher")
def test_workspace_switcher_orders_by_attention_then_recency(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Oldest -> newest, interleaved across the tiers. Names are kept short and
    # distinct: the branch-name preview slugifies the workspace name and caps it
    # at 20 chars on a word boundary, so longer names could collide on the
    # generated worktree branch. The first creation is a real (modal) workspace
    # so the project is initialised before the API-based idle creations.
    error_a = _make_error_workspace(page, layout, "Error A")
    idle_a = _make_idle_workspace(page, "Idle A")
    error_b = _make_error_workspace(page, layout, "Error B")
    idle_b = _make_idle_workspace(page, "Idle B")
    waiting = _make_waiting_workspace(page, "Waiting")  # last created → current + focused

    # Expected top-to-bottom order: the waiting (current) workspace leads, then
    # the error tier (newer "B" first), then the idle tier (newer "B" first).
    # Note the names are alphabetically A-before-B, the OPPOSITE of the recency
    # expectation — so a broken recency sort would fail rather than pass by luck.
    expected_ids = [waiting, error_b, error_a, idle_b, idle_a]

    wait_for_workspace_list_loaded(page)
    palette = layout.open_command_palette()
    palette.select_by_command_id("workspaces.switch")
    expect(palette.get_breadcrumb()).to_be_visible()

    rows = palette.get_items_in_group("workspaces")
    expect(rows).to_have_count(len(expected_ids))

    labels = {waiting: "waiting", error_b: "error_b", error_a: "error_a", idle_b: "idle_b", idle_a: "idle_a"}
    expected_labels = [labels[ws_id] for ws_id in expected_ids]
    actual_ids = [
        (rows.nth(i).get_attribute("data-command-id") or "").removeprefix("workspaces.page.")
        for i in range(rows.count())
    ]
    actual_labels = [labels.get(ws_id, ws_id) for ws_id in actual_ids]
    assert actual_labels == expected_labels, f"switcher order {actual_labels} != expected {expected_labels}"

    # The current workspace (last created) is the leading waiting row, marked
    # "Current workspace" and disabled so selecting it can't self-navigate.
    current_row = palette.get_item_in_group_by_command_id("workspaces", f"workspaces.page.{waiting}")
    expect(current_row).to_contain_text("Current workspace")
    expect(current_row).to_have_attribute("aria-disabled", "true")
