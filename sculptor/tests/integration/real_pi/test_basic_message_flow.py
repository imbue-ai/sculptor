"""Real pi integration test: basic message flow.

Verifies a single-turn round-trip through the real ``pi --mode rpc``
subprocess + the real upstream model.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import real_pi


@real_pi
@pytest.mark.timeout(300)
def test_single_message_response(sculptor_instance_: SculptorInstance) -> None:
    """Real pi answers a simple prompt with a text response containing the sentinel."""
    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        "Reply with exactly the text PONG-50284. Do not add any other text, formatting, or explanation.",
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().last).to_contain_text("PONG-50284")
    expect(chat_panel.get_error_block()).to_have_count(0)
