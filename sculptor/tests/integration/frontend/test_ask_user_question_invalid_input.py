"""Integration test for the agent sending malformed input to
``mcp__sculptor__ask_user_question``.

The MCP server is supposed to validate the agent's arguments against the
advertised schema and respond with a JSON-RPC ``-32602 INVALID_PARAMS``
error. Without that response, three things would happen — and this test
asserts none of them do:

1. The agent's ``tools/call`` would dangle forever (no JSON-RPC response).
2. A chat-visible AskUserQuestion panel would render for input that was
   rejected, leaving a phantom question with no live call behind it.
3. The workspace would get stuck in a yellow ``Waiting for input`` state.

FakeClaude drives the test by emitting a tool_use with deliberately
malformed arguments and asserting an MCP error response comes back, then
emitting a follow-up text message simulating the agent recovering.

``mcp__sculptor__exit_plan_mode`` advertises an empty input schema (the
plan content is harness-injected from disk, not supplied by the model), so
there is no way to construct an invalid input the MCP server would reject;
no exit-plan-mode counterpart to this test is possible.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("the agent recovers cleanly when it sends malformed AskUserQuestion arguments")
def test_ask_user_question_invalid_input_returns_mcp_error_and_does_not_stick(
    sculptor_instance_: SculptorInstance,
) -> None:
    """End-to-end check that malformed ``mcp__sculptor__ask_user_question``
    arguments are handled correctly:

    - FakeClaude sends ``multiSelect: 'false'`` (string, not bool) — the
      MCP server's strict validator rejects it with a JSON-RPC error.
    - FakeClaude expects that error envelope and proceeds to a follow-up
      assistant message; if the JSON-RPC response never arrived, FakeClaude
      would block in its read loop and the agent's request would never
      complete (thinking indicator never hides, message count stays at 1).
    - No AskUserQuestion panel is rendered — strict validation in the
      output processor and message-conversion layers stops the malformed
      tool_use from materializing as a pending question.
    - The workspace is NOT in the yellow ``Waiting for input`` state once
      the agent has finished recovering.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="fake_claude:ask_user_question_invalid_input",
        workspace_name="Malformed AUQ WS",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The agent's request completes only if FakeClaude received the JSON-RPC
    # error and emitted its follow-up message. A dangling tools/call would
    # leave the thinking indicator visible and the message count at 1.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=30_000)

    # No AskUserQuestion panel ever appeared — pending_user_question stayed
    # None throughout because all three validation surfaces (output
    # processor, MCP server, message_conversion reload path) reject the
    # malformed input in lockstep.
    ask_panel = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    expect(ask_panel).not_to_be_visible()

    # The chat input is back — the user can type the next message rather
    # than being trapped behind a phantom AUQ panel.
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Workspace is NOT stuck in the yellow ``Waiting for input`` state.
    # The peek popover is the surface the user sees; an unanswered AUQ
    # would surface there as an orange waiting banner.
    navigate_to_home_page(page)
    workspace_tab = page.get_by_test_id(ElementIDs.WORKSPACE_TAB).first
    workspace_tab.hover()
    popover = page.get_by_test_id(ElementIDs.WORKSPACE_PEEK_POPOVER)
    expect(popover).to_be_visible()
    waiting_banner = page.get_by_test_id(ElementIDs.WORKSPACE_PEEK_BANNER)
    expect(waiting_banner).to_be_hidden()
