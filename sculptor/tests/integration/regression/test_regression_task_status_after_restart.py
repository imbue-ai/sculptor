"""Regression test: Task status should not show ERROR after restart.

Bug: When Sculptor restarts in the middle of an agent turn, the task status
shows ERROR instead of BUILDING/RUNNING/READY.

Root causes:
1. During graceful shutdown, multiple exceptions (AgentPaused + background process
   failures) are collected into a ConcurrencyExceptionGroup. The exception handler
   only unwraps single-exception groups, so multi-exception groups fall through to
   AgentTaskFailure, making the task FAILED instead of QUEUED.
2. RequestStoppedAgentMessage (emitted when the agent receives SIGTERM during
   shutdown) is a subclass of PersistentRequestCompleteAgentMessage. The status
   computation in CodingAgentTaskView.status counts it as a completed request,
   making the task appear READY instead of RUNNING while re-processing.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000
# Visibility gate for the post-restart page. Generous because in this test
# the Phase 2 backend is also restoring a mid-turn task, which competes
# with the workspace-snapshot WebSocket push that the sidebar workspace
# row depends on; under CI load the snapshot can land well after a few
# seconds (SCU-570).
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * SECONDS_MS
_BUILD_TIMEOUT_MS = 90 * SECONDS_MS

# Agent panel tabs in the section shell expose their lifecycle as ``data-dot-status``
# (the status-dot vocabulary from getAgentDotStatus), not the raw TaskStatus. The
# ERROR TaskStatus maps to the "error" dot; every other status the agent can land in
# after a clean restart maps to running (RUNNING/BUILDING), waiting (WAITING), or
# read/unread (READY). So "not ERROR" is "any dot status that is not 'error'".
_NON_ERROR_DOT_STATUS = re.compile(r"^(running|waiting|read|unread)$")


@user_story("to see correct task status after restarting Sculptor mid-turn")
def test_task_status_shows_running_after_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Task status should not be ERROR after restarting mid-agent-turn.

    Steps:
    1. Start a task with a long-running command (sleep 120) so the agent is mid-turn
    2. Wait for the agent to begin running
    3. Shut down Sculptor (exit context), which sends SIGTERM to the agent
    4. Restart Sculptor and navigate to the workspace
    5. Verify the task status is not ERROR (should be BUILDING, RUNNING, or READY)
    """
    # Phase 1: Start a long-running task and then shut down mid-turn.
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(
            instance.page,
            prompt='fake_claude:sleep `{"seconds": 120}`',
            wait_for_agent_to_finish=False,
        )

        # Verify the agent tab shows the running dot before we shut down.
        first_tab = PlaywrightPanelTabElement(instance.page, sub_section="center").get_panel_tabs().first
        expect(first_tab).to_have_attribute("data-dot-status", "running", timeout=_BUILD_TIMEOUT_MS)

    # Exiting the context sends SIGTERM to the entire process group. FakeClaude's
    # SIGTERM handler exits with code 143, causing the agent wrapper to emit a
    # RequestStoppedAgentMessage. The task should be finalized as QUEUED.

    # Phase 2: Restart and verify the task is not in ERROR state.
    with sculptor_instance_factory_.spawn_instance() as instance:
        # Navigate to the workspace (click its persisted sidebar row).
        workspace_row = get_workspace_sidebar(instance.page).get_workspace_rows().first
        expect(workspace_row).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
        workspace_row.click()

        # After restart, the agent dot should show running (re-acquiring
        # environment / re-processing the message) or read/unread (re-processing
        # completed). If the shutdown failed to produce QUEUED (task ended up
        # FAILED instead), the dot would be "error".
        first_tab = PlaywrightPanelTabElement(instance.page, sub_section="center").get_panel_tabs().first
        expect(first_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
        expect(first_tab).to_have_attribute("data-dot-status", _NON_ERROR_DOT_STATUS, timeout=_BUILD_TIMEOUT_MS)
