"""Shared helpers for real pi integration tests.

Real pi tests run a real ``pi --mode rpc`` subprocess driven by a real
upstream model. Helpers keep the per-test surface small.
"""

from __future__ import annotations

import pytest

from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance

# Pytest marker for real pi tests. Apply as ``@real_pi`` on every test.
real_pi = pytest.mark.real_pi

# Pi has no Sculptor-registered LLMModel entry; the chat panel's model picker
# is skipped (model_name=None). Pi reads its upstream-model choice from
# ``~/.pi/agent/models.json`` outside Sculptor.

# Single-turn responses against real pi can take a while (cold-start + model
# latency). Default to a roomy timeout so the suite isn't fighting noise.
RESPONSE_TIMEOUT_MS = 180_000

# Prefix every prompt so real pi recognises this as an automated test. Reads as
# a user instruction without conflicting with any pi system-prompt directive.
_TEST_PREFIX = "[SCULPTOR-UI-TEST] This is an automated integration test of Sculptor's UI, not a real user request. Follow the instructions exactly as given. "


def prefixed(prompt: str) -> str:
    return _TEST_PREFIX + prompt


def create_pi_workspace_and_send(
    sculptor_instance_: SculptorInstance,
    prompt: str,
    *,
    workspace_name: str = "Real Pi",
    wait_for_finish: bool = True,
) -> PlaywrightTaskPage:
    """Create a real-pi workspace and send the first prompt.

    With ``wait_for_finish`` (the default) waits for the turn to complete before
    returning. Pass ``wait_for_finish=False`` for turns that block mid-way — e.g.
    an ask-user-question or plan-approval dialog the test must answer. Pi's tool
    loop runs inside the pi subprocess; Sculptor's file-watching layer reflects
    workspace mutations into the diff sidebar.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        prompt=prefixed(prompt),
        model_name=None,
        harness=HarnessName.PI,
        wait_for_agent_to_finish=wait_for_finish,
    )
    if wait_for_finish:
        wait_for_completed_message_count(
            chat_panel=task_page.get_chat_panel(),
            expected_message_count=2,
            timeout=RESPONSE_TIMEOUT_MS,
        )
    return task_page
