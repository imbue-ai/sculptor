"""Interrupt-and-continue for the pi harness (supports_interruption).

Mirrors the core of ``test_interrupt_and_continue.py`` against FakePi: a turn
that streams some text and then blocks on a sentinel file is interrupted via
the Stop button, the chat resolves as ``Stopped``, and a follow-up turn
completes on the same long-lived pi process. The sentinel-file pause is a
deterministic busy window (no wall-clock racing).
"""

import tempfile
import uuid
from pathlib import Path

from playwright.sync_api import expect

from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to stop a running pi turn and then continue with a follow-up message")
def test_pi_interrupt_during_turn_then_continue(sculptor_instance_: SculptorInstance) -> None:
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page
    release_path = Path(tempfile.gettempdir()) / f"pi_interrupt_{uuid.uuid4().hex}"
    try:
        # Stream some text, then block on a sentinel file: a deterministic busy
        # window in which the Stop button is live (no wall-clock dependence).
        prompt = f'fake_pi:stream_text `{{"text": "Working on it..."}}` fake_pi:wait_for_file `{{"path": "{release_path}"}}`'
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Interrupt",
            model_name=None,
            harness=HarnessName.PI,
            prompt=prompt,
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # Wait for the turn to be busy, then Stop it.
        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=15000)
        stop_button = chat_panel.get_stop_button()
        expect(stop_button).to_be_visible()
        stop_button.click()

        # The interrupted turn resolves: the Stopped marker shows and the agent
        # is no longer busy.
        expect(chat_panel.get_messages().last).to_contain_text("Stopped", timeout=15000)
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=15000)

        # A follow-up turn completes on the same pi process.
        send_chat_message(chat_panel=chat_panel, message='fake_pi:emit_text `{"text": "Follow-up done."}`')
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30000)
        expect(chat_panel.get_messages().last).to_contain_text("Follow-up done.")
    finally:
        # Harmless if the turn already ended via Stop; releases a still-blocked
        # turn if a pre-Stop assertion failed.
        release_path.touch()
