"""Minimum-interface conformance suite parametrized over Claude and pi.

Both harnesses must satisfy two invariants:

- Turn-boundary signalling: a user message produces a user-then-assistant
  pair and the thinking indicator settles after the turn ends.
- Structured failure reporting: a subprocess-side failure surfaces as an
  error block, not a silent drop.

The exact streaming-frame schemas differ between Claude and pi, so the
assertions stick to the harness-agnostic chat surface — the minimum
interface every harness must honour.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from tests.integration.frontend.conftest import HarnessTestConfig

_TEXT_DIRECTIVE_BY_HARNESS: dict[str, str] = {
    "claude": 'fake_claude:text `{"text": "TURN-OK-91827"}`',
    "pi": 'fake_pi:emit_text `{"text": "TURN-OK-91827"}`',
}

_ERROR_DIRECTIVE_BY_HARNESS: dict[str, str] = {
    "claude": 'fake_claude:api_error `{"message": "FAIL-OK-66341"}`',
    "pi": 'fake_pi:error `{"message": "FAIL-OK-66341"}`',
}


def _open_workspace_for(
    sculptor_instance_: SculptorInstance,
    harness: HarnessTestConfig,
    workspace_name: str,
) -> PlaywrightTaskPage:
    """Create a workspace for the parametrized harness and return the task page.

    Pi-side skips the model selector (no Fake Pi entry in the LLMModel enum)
    and pre-installs the FakePi binary; Claude-side uses Fake Claude.
    """
    if harness.first_agent_type == "pi":
        install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
        model_name = None
    else:
        model_name = FAKE_CLAUDE_MODEL_NAME
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        model_name=model_name,
        agent_type=harness.first_agent_type,
    )


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to see every harness round-trip a turn (user message in, assistant text out, turn ends)")
def test_turn_boundary_signalling(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    task_page = _open_workspace_for(sculptor_instance_, harness, "Conformance: turn boundary")
    chat_panel = task_page.get_chat_panel()

    send_chat_message(chat_panel, _TEXT_DIRECTIVE_BY_HARNESS[harness.first_agent_type])
    wait_for_completed_message_count(chat_panel, expected_message_count=2)
    expect(chat_panel.get_assistant_messages().last).to_contain_text("TURN-OK-91827")


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to see a structured failure surface (not a silent drop) when the agent subprocess errors")
def test_structured_failure_reporting(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    task_page = _open_workspace_for(sculptor_instance_, harness, "Conformance: failure reporting")
    chat_panel = task_page.get_chat_panel()

    send_chat_message(chat_panel, _ERROR_DIRECTIVE_BY_HARNESS[harness.first_agent_type])
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_error_block().first).to_be_visible()
