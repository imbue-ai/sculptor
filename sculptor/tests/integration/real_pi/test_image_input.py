"""Real pi integration test: image input.

A small solid-blue PNG is attached and the model is asked its color. A real
multimodal model answers "blue" only if the image actually reached and was
seen by it — base64 on the `prompt` command's ``images[]`` field, end to end
through the real ``pi --mode rpc`` subprocess.

The file is delivered through the harness-agnostic upload API rather than the
image-only frontend picker, so the assertion is about transport + model vision,
not the UI attach widget (covered by ``frontend/test_image_upload.py``).
"""

from __future__ import annotations

import io
import re

import pytest
from PIL import Image
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import send_message_via_api
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import upload_file_via_api
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi


def _solid_png_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


@real_pi
@pytest.mark.timeout(300)
def test_attached_image_is_seen_by_the_model(sculptor_instance_: SculptorInstance) -> None:
    """Real pi answers the color of an attached solid-blue PNG — the image was seen."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name="Real Pi Image",
        model_name=None,
        agent_type="pi",
    )
    image_id = upload_file_via_api(
        sculptor_instance_.page, name="blue.png", mime_type="image/png", content=_solid_png_bytes((0, 0, 255))
    )
    send_message_via_api(
        sculptor_instance_.page,
        message=prefixed(
            "What is the dominant color of the attached image? Reply with exactly one word naming the color."
        ),
        files=[image_id],
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_assistant_messages().last).to_contain_text(re.compile(r"blue", re.IGNORECASE))
    expect(chat_panel.get_error_block()).to_have_count(0)
