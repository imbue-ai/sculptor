"""Regression test for SCU-925.

Bug: Restarting Sculptor while an AskUserQuestion is pending surfaces a
misleading red ``AgentClientError: Agent died with exit code 143`` block in
the chat history.

SIGTERM (exit code 143) is the normal signal sent to the Claude CLI when
Sculptor's process group is torn down for a restart. The wrapper translates
the resulting ``AgentClientError`` into a ``RequestStoppedAgentMessage``;
the message-conversion layer then renders the wrapped error as a chat
``ErrorBlock``, which the frontend draws as a red "AgentClientError" badge.
The "Stopped" footer already communicates that the turn was interrupted —
the red error makes a normal restart look like a crash.

Fix: in ``sculptor/web/message_conversion.py``, suppress the chat
``ErrorBlock`` for ``RequestStoppedAgentMessage`` (the message is still
marked ``stopped=True`` via ``_mark_stopped``).
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SECONDS_MS = 1000

# Visibility gate for the post-restart page. Generous because the restored
# task races with the workspace-snapshot WebSocket push under CI load.
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * _SECONDS_MS

# Time to wait for the AUQ panel to appear before tearing down the first
# instance — the agent must actually reach the waiting state, otherwise this
# test exercises a different code path.
_INFLIGHT_OBSERVATION_TIMEOUT_MS = 30 * _SECONDS_MS

_AUQ_PROMPT = 'fake_claude:ask_user_question `{"questions": [{"question": "Pick a color", "header": "Color", "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}], "multiSelect": false}]}`'  # noqa: E501


def _open_workspace_after_restart(page: Page) -> None:
    workspace_tab = page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW).first
    expect(workspace_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_tab.click()


@user_story("not see a misleading 'Agent died' error after restarting Sculptor mid-question")
def test_no_error_block_after_restart_during_pending_auq(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """SCU-925: restart-during-AUQ must not surface 'Agent died with exit code 143'.

    Phase 1: drive the agent into the AUQ-waiting state, then SIGTERM the
    backend by exiting the instance context. The wrapper emits
    ``RequestStoppedAgentMessage(AgentClientError("Agent died with exit code
    143"))`` for the in-flight chat.

    Phase 2: reopen the workspace and assert no ``ERROR_BLOCK`` is rendered
    (the misleading red error).
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(
            instance.page,
            prompt=_AUQ_PROMPT,
            wait_for_agent_to_finish=False,
        )
        expect(instance.page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)).to_be_visible(
            timeout=_INFLIGHT_OBSERVATION_TIMEOUT_MS
        )

    # Exiting the context SIGTERMs the backend, which propagates SIGTERM to
    # the fake-claude child. The wrapper's ``except AgentClientError`` branch
    # at agent_wrapper.py emits a ``RequestStoppedAgentMessage`` carrying the
    # "Agent died with exit code 143" error.

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)

        # Wait on a positive signal that persisted messages have rendered
        # before asserting absence of the error block. The AUQ ToolUseBlock
        # is in the persisted ResponseBlockAgentMessage and re-renders on
        # restart; the block may be collapsed (hidden) by default, so check
        # existence via to_have_count(1) rather than visibility. Without this
        # gate, asserting "error block absent" would pass spuriously before
        # any messages have hydrated.
        task_page_after = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page_after.get_chat_panel()
        expect(instance.page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)).to_have_count(
            1, timeout=_RESTART_VISIBILITY_TIMEOUT_MS
        )

        # With the fix, the ErrorBlock for the SIGTERM-induced
        # RequestStoppedAgentMessage is suppressed. Use to_have_count(0) so
        # the assertion retries until no matching elements exist (rather
        # than relying on "not visible" semantics for an absent element).
        expect(chat_panel.get_error_block()).to_have_count(0)
