"""Regression test: a pending ask_user_question must survive a Sculptor restart.

When the agent is blocked on an unanswered AskUserQuestion and Sculptor
restarts, the Claude CLI is SIGTERM'd (exit code 143) and the wrapper
persists a ``RequestStoppedAgentMessage`` for the in-flight turn. The
question's ToolUseBlock is already persisted in the chat history, so the
question is fully reconstructable — but the persisted RequestStopped must
not be treated as "the question is dead":

- ``message_conversion.convert_agent_messages_to_task_update`` must keep the
  reconstructed question pending (interactive panel, not just the collapsed
  historical block) instead of clearing it on the SIGTERM-induced stop.
- ``derived`` task status must keep reporting ``WAITING`` (yellow dot) so the
  user can tell the agent is still blocked on them.
- Submitting the answer post-restart must flow through the runner's
  answer-after-turn-ended continuation (``ClaudeProcessManager
  .process_input_message`` respawn path), resuming the agent so it can
  finish the turn.

A user-clicked Stop is different: it flows through the wrapper's success
branch (``RequestSuccessAgentMessage(interrupted=True)``), which still
dismisses the question — pressing Stop means the user is moving on.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.ask_user_question import get_ask_user_question_tool_blocks
from sculptor.testing.elements.ask_user_question import get_first_ask_user_question_tool_block
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SECONDS_MS = 1000

# An idle agent panel tab settles to a read/unread status dot once the user
# is viewing the workspace — the section shell exposes lifecycle as
# ``data-dot-status`` (the getAgentDotStatus vocabulary), not raw TaskStatus.
_IDLE_DOT_STATUS = re.compile(r"^(read|unread)$")

# Visibility gate for the post-restart page — generous because the Phase-2
# backend is restoring a previously-running task and CI can be slow.
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * _SECONDS_MS

# Before tearing down the first instance, wait this long for the agent to
# actually reach the AUQ-waiting state — otherwise the test exercises a
# different code path (SIGTERM mid-turn instead of SIGTERM during AUQ wait).
_INFLIGHT_OBSERVATION_TIMEOUT_MS = 30 * _SECONDS_MS

# Window for the post-restart answer's resumed turn to complete (spawn CLI
# with --resume, deliver the answer, emit the follow-up, settle to idle).
_SETTLE_TIMEOUT_MS = 60 * _SECONDS_MS

_AUQ_PROMPT = 'fake_claude:ask_user_question `{"questions": [{"question": "Pick a color", "header": "Color", "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}], "multiSelect": false}]}`'  # noqa: E501


def _open_workspace_after_restart(page: Page) -> None:
    """Click the persisted workspace's sidebar row on a fresh Sculptor instance."""
    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    expect(workspace_row).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_row.click()


def _agent_tab(page: Page) -> Locator:
    return PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs().first


@user_story("still be able to answer an agent's question after restarting Sculptor")
def test_pending_question_restored_and_answerable_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Restart during an AUQ wait must restore the interactive question, not drop it.

    Phase 1: drive the agent into the AUQ-waiting state, then SIGTERM the
    backend by exiting the instance context.

    Phase 2: reopen the workspace and assert the pending question is fully
    restored — the interactive panel is visible (not just the collapsed
    historical tool block), the agent tab dot reports "waiting", and there is
    exactly one AUQ tool block (restored, not re-emitted/duplicated).

    Phase 3: answer the restored question and assert the answer reaches the
    resumed agent — the panel dismisses, the tool block flips to its
    submitted state showing the chosen answer, and the agent completes the
    follow-up turn (dot settles to idle).
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(
            instance.page,
            prompt=_AUQ_PROMPT,
            wait_for_agent_to_finish=False,
        )
        # The agent must actually reach the waiting state before shutdown,
        # otherwise this exercises the mid-turn SIGTERM path instead.
        expect(get_ask_user_question_panel(instance.page)).to_be_visible(timeout=_INFLIGHT_OBSERVATION_TIMEOUT_MS)

    # Exiting the context SIGTERMs the backend, which propagates SIGTERM to
    # the fake-claude child; the wrapper persists RequestStopped for the
    # in-flight turn while the AUQ ToolUseBlock stays in the saved history.

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)

        # The interactive panel must be restored from the persisted history.
        auq_panel = get_ask_user_question_panel(instance.page)
        expect(auq_panel).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)

        # The task must still advertise that it is blocked on the user.
        expect(_agent_tab(instance.page)).to_have_attribute(
            "data-dot-status", "waiting", timeout=_RESTART_VISIBILITY_TIMEOUT_MS
        )

        # Restored, not duplicated: exactly one AUQ tool block in the chat.
        expect(get_ask_user_question_tool_blocks(instance.page)).to_have_count(1)

        # Answering the restored question must reach the resumed agent.
        auq_panel.select_first_option_and_submit()
        expect(auq_panel).not_to_be_visible(timeout=_SETTLE_TIMEOUT_MS)

        tool_block = get_first_ask_user_question_tool_block(instance.page)
        tool_block.expect_submitted_state()
        tool_block.expect_answer_visible("Red")

        # The resumed turn completes and the agent settles to idle
        # (read/unread dot), proving the answer actually drove a turn.
        expect(_agent_tab(instance.page)).to_have_attribute(
            "data-dot-status", _IDLE_DOT_STATUS, timeout=_SETTLE_TIMEOUT_MS
        )
