"""Right-click "Copy Image" context menu on chat-panel images.

Covers the scoping of the affordance: it is offered on the inline image in a
chat message and on the full-size lightbox image, but not on composer
attachments (which are app chrome from the copy-content perspective).
"""

import re
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.fixture
def test_image_() -> Generator[str, None, None]:
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    Image.new("RGB", (100, 100), (255, 0, 0)).save(temp_path)
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.mark.electron
@user_story("to right-click a chat image and copy it via a context menu")
def test_copy_image_context_menu_scoped_to_chat_content(
    sculptor_instance_: SculptorInstance,
    test_image_: str,
) -> None:
    """Right-click offers Copy Image on chat message images and the lightbox, not composer attachments."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Copy Image Test")
    chat_panel = task_page.get_chat_panel()

    # Composer attachments are excluded: no Copy Image item on right-click.
    chat_panel.attach_files(test_image_)
    composer_preview = chat_panel.get_file_previews()
    expect(composer_preview).to_have_count(1)
    composer_preview.nth(0).click(button="right")
    expect(page.get_by_test_id(ElementIDs.FILE_PREVIEW_COPY_IMAGE)).to_have_count(0)

    send_chat_message(chat_panel=chat_panel, message="Describe this image.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Inline image in the user message offers Copy Image on right-click.
    user_message = chat_panel.get_messages().nth(0)
    inline_image = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW)
    expect(inline_image).to_have_count(1)
    inline_image.nth(0).click(button="right")
    copy_item = page.get_by_test_id(ElementIDs.FILE_PREVIEW_COPY_IMAGE)
    expect(copy_item).to_be_visible()
    expect(copy_item).to_have_text("Copy Image")
    page.keyboard.press("Escape")

    # The full-size lightbox image (opened from chat) also offers Copy Image.
    inline_image.nth(0).click()
    lightbox_image = page.get_by_alt_text(re.compile(r"^Full size: "))
    expect(lightbox_image).to_be_visible()
    lightbox_image.click(button="right")
    expect(page.get_by_test_id(ElementIDs.FILE_PREVIEW_COPY_IMAGE)).to_be_visible()
