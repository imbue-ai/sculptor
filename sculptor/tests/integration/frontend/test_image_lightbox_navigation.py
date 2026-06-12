"""Test image lightbox navigation: clicking left/right arrow buttons to navigate between images."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.lightbox import PlaywrightLightboxElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_test_image(color: tuple[int, int, int]) -> Generator[str, None, None]:
    """Create a temporary test image with the specified color and clean it up after use."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    img = Image.new("RGB", (100, 100), color)
    img.save(temp_path)

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def test_image_red_() -> Generator[str, None, None]:
    yield from _create_test_image((255, 0, 0))


@pytest.fixture
def test_image_green_() -> Generator[str, None, None]:
    yield from _create_test_image((0, 255, 0))


@pytest.fixture
def test_image_blue_() -> Generator[str, None, None]:
    yield from _create_test_image((0, 0, 255))


def _attach_image_and_verify_preview(
    element: PlaywrightChatPanelElement,
    images: str | list[str],
    expected_count: int = 1,
) -> None:
    element.attach_files(images)
    image_previews = element.get_file_previews()
    expect(image_previews).to_have_count(expected_count)


@pytest.mark.electron
@pytest.mark.skip(reason="Flaky in CI — lightbox arrow not reliably visible")
@user_story("to navigate between images in the lightbox using arrow buttons")
def test_lightbox_arrow_navigation(
    sculptor_instance_: SculptorInstance,
    test_image_red_: str,
    test_image_green_: str,
    test_image_blue_: str,
) -> None:
    """Test that clicking left/right arrow buttons in the lightbox navigates between images.

    Steps:
    1. Create a workspace and attach three images via the chat panel
    2. Wait for the task to complete
    3. Click on the first image thumbnail to open the lightbox
    4. Verify the lightbox shows the first image
    5. Click the next arrow button and verify navigation
    6. Click through all images and verify wrap-around behavior
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Lightbox Nav Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(
        chat_panel, [test_image_red_, test_image_green_, test_image_blue_], expected_count=3
    )
    send_chat_message(chat_panel=chat_panel, message="Describe these images.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Find the image previews in the user message
    messages = chat_panel.get_messages()
    user_message = messages.nth(0)
    image_previews = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW)
    expect(image_previews).to_have_count(3)

    # Click the first image to open lightbox
    image_previews.nth(0).click()

    # Verify lightbox is open with navigation arrows
    lightbox = PlaywrightLightboxElement(page)
    nav_previous = lightbox.get_nav_previous()
    nav_next = lightbox.get_nav_next()
    expect(nav_previous).to_be_visible()
    expect(nav_next).to_be_visible()

    # Verify navigation using the counter element in the lightbox caption.
    # The counter text format is " (index/total)", e.g. " (1/3)".
    counter = lightbox.get_counter()
    expect(counter).to_contain_text("(1/3)")

    # Click next arrow -> should show second image
    nav_next.click()
    expect(counter).to_contain_text("(2/3)")

    # Click next arrow -> should show third image
    nav_next.click()
    expect(counter).to_contain_text("(3/3)")

    # Click next arrow -> should wrap to first image
    nav_next.click()
    expect(counter).to_contain_text("(1/3)")

    # Click previous arrow -> should wrap back to third image
    nav_previous.click()
    expect(counter).to_contain_text("(3/3)")


@pytest.mark.electron
@user_story("to not see navigation arrows when only one image is in the lightbox")
def test_lightbox_no_arrows_for_single_image(
    sculptor_instance_: SculptorInstance,
    test_image_red_: str,
) -> None:
    """Test that the lightbox does not show navigation arrows when there is only one image.

    Steps:
    1. Create a workspace and attach a single image via the chat panel
    2. Open the lightbox by clicking the image
    3. Verify no navigation arrows are shown
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Single Image Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(chat_panel, test_image_red_)
    send_chat_message(chat_panel=chat_panel, message="Describe this image.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Click the image to open lightbox
    messages = chat_panel.get_messages()
    user_message = messages.nth(0)
    image_preview = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW)
    expect(image_preview).to_have_count(1)
    image_preview.click()

    # Verify lightbox is open (image should be visible) but no arrows
    lightbox = PlaywrightLightboxElement(page)
    expect(lightbox.get_nav_previous()).to_have_count(0)
    expect(lightbox.get_nav_next()).to_have_count(0)
