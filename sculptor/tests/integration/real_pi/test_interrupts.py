"""Real pi integration test: interrupt scenarios.

Mirrors the stop case of ``real_claude/test_interrupts.py`` against a real
``pi --mode rpc`` subprocess: a long generation is interrupted via the Stop
button, the chat resolves as Stopped, and a follow-up turn completes on the
same pi process.

Divergence from the Claude suite (REQ-TEST-1): pi runs ``--no-session`` and
has no session resume (``supports_session_resume=False``), so there is no
transcript file to inspect and the Claude suite's transcript/"no amnesia"
assertions do not apply here. The force-kill escalation ladder (no
``agent_end`` within the grace window → SIGTERM) is a pathological-pi path
covered deterministically by the unit tests (``agent_wrapper_test.py``) and the
fake_pi integration test, not exercised against a real model here.
"""

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import assert_interrupted
from tests.integration.real_pi.helpers import assert_last_assistant_message_contains
from tests.integration.real_pi.helpers import assert_no_errors
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import interrupt_agent
from tests.integration.real_pi.helpers import real_pi
from tests.integration.real_pi.helpers import send_no_wait
from tests.integration.real_pi.helpers import wait_for_streaming_text


@real_pi
@pytest.mark.timeout(300)
def test_pi_interrupt_during_streaming_then_continue(sculptor_instance_: SculptorInstance) -> None:
    """Graceful stop of a long generation, then a follow-up turn on the same agent."""
    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        "Reply with exactly the text PI-READY-71245. Do not add any other text.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_assistant_message_contains(chat_panel, "PI-READY-71245")

    # Start a long generation (gives time to interrupt mid-stream).
    send_no_wait(
        chat_panel,
        "Write a very long, detailed essay about the history of computing. It must be at least 2000 words. Start your essay with exactly: PI-ESSAY-BEGINS:",
    )
    wait_for_streaming_text(chat_panel, "PI-ESSAY-BEGINS")

    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)
    assert_no_errors(chat_panel)

    # The same pi process serves a follow-up turn after the interrupt.
    send_no_wait(chat_panel, "Reply with exactly the text PI-RECOVERED-OK-30518. Do not add any other text.")
    assert_last_assistant_message_contains(chat_panel, "PI-RECOVERED-OK-30518")
    assert_no_errors(chat_panel)
