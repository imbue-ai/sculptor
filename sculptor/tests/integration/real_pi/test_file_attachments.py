"""Real pi integration test: non-image file attachments.

A non-image attachment is delivered as a file path in the prompt text, and pi
reads its contents with its own ``read`` tool within the turn — the same loop
that backs ``supports_file_references``. A text file carrying a unique sentinel
is attached and the model is asked for the sentinel; it can only answer
correctly by reading the file.

The file is uploaded through the harness-agnostic upload API because the
frontend picker accepts images only — that is exactly the transport a non-image
attachment travels.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import send_message_via_api
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import upload_file_via_api
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi

# A sentinel the model cannot guess — it must read the attached file to find it.
_SENTINEL = "ATTACH-SENTINEL-70413"


@real_pi
@pytest.mark.timeout(300)
def test_attached_text_file_is_readable_that_turn(sculptor_instance_: SculptorInstance) -> None:
    """Real pi reads an attached text file and reports its sentinel that same turn."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name="Real Pi Attachment",
        model_name=None,
        harness=HarnessName.PI,
    )
    text_id = upload_file_via_api(
        sculptor_instance_.page,
        name="secret.txt",
        mime_type="text/plain",
        content=f"The secret code is {_SENTINEL}.\n".encode(),
    )
    send_message_via_api(
        sculptor_instance_.page,
        message=prefixed(
            "Read the attached text file and reply with the exact secret code it contains. Reply with only the code."
        ),
        files=[text_id],
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_assistant_messages().last).to_contain_text(_SENTINEL)
    expect(chat_panel.get_error_block()).to_have_count(0)
