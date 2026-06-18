"""Test inline image thumbnail strip: images in user messages render as a horizontal strip of thumbnails."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.lightbox import PlaywrightLightboxElement
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_test_image(size: tuple[int, int], color: tuple[int, int, int]) -> Generator[str, None, None]:
    """Create a temporary test image with the specified size and color."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    img = Image.new("RGB", size, color)
    img.save(temp_path)

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def landscape_image_() -> Generator[str, None, None]:
    """A wide landscape image (400x200)."""
    yield from _create_test_image((400, 200), (255, 0, 0))


@pytest.fixture
def portrait_image_() -> Generator[str, None, None]:
    """A tall portrait image (200x400)."""
    yield from _create_test_image((200, 400), (0, 255, 0))


@pytest.fixture
def square_image_() -> Generator[str, None, None]:
    """A square image (300x300)."""
    yield from _create_test_image((300, 300), (0, 0, 255))


def _attach_and_send(
    chat_panel: PlaywrightChatPanelElement,
    images: str | list[str],
    message: str = "Describe these images.",
) -> None:
    """Attach images, send a message, and wait for completion."""
    chat_panel.attach_files(images)
    expected_count = 1 if isinstance(images, str) else len(images)
    expect(chat_panel.get_file_previews()).to_have_count(expected_count)
    send_chat_message(chat_panel=chat_panel, message=message)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)


def _get_user_message_preview_list(chat_panel: PlaywrightChatPanelElement) -> Locator:
    """Get the FILE_PREVIEW_LIST container from the first user message."""
    messages = chat_panel.get_messages()
    user_message = messages.nth(0)
    expect_message_to_have_role(message=user_message, role=ElementIDs.USER_MESSAGE)
    preview_list = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW_LIST)
    expect(preview_list).to_have_count(1)
    return preview_list


def _get_user_message_thumbnails(chat_panel: PlaywrightChatPanelElement) -> Locator:
    """Get the FILE_PREVIEW image elements from the first user message."""
    messages = chat_panel.get_messages()
    user_message = messages.nth(0)
    thumbnails = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW)
    return thumbnails


@pytest.mark.electron
@user_story("to see multiple images rendered as a horizontal thumbnail strip instead of a vertical stack")
def test_thumbnail_strip_horizontal_layout(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
    square_image_: str,
) -> None:
    """Attaching multiple images should produce a horizontal strip layout.

    The FILE_PREVIEW_LIST container should use flex-direction: row so thumbnails
    appear side by side, not stacked vertically.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Thumbnail Strip Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_, square_image_])

    preview_list = _get_user_message_preview_list(chat_panel)
    expect(preview_list).to_have_css("flex-direction", "row")


@pytest.mark.electron
@user_story("to see a single image rendered as a thumbnail rather than a full-size inline image")
def test_single_image_renders_as_thumbnail(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
) -> None:
    """Even a single attached image should render as a compact thumbnail, not a large inline image.

    The image should be 110px tall (plus 4px for the transparent border), not the previous
    400px max-height.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Single Thumbnail Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, landscape_image_, message="Describe this image.")

    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(1)

    # 110px CSS height + 2px border top + 2px border bottom = 114px rendered height
    thumbnail = thumbnails.nth(0)
    expect(thumbnail).to_be_visible()
    bounding_box = thumbnail.bounding_box()
    assert bounding_box is not None
    assert bounding_box["height"] <= 120, (
        f"Thumbnail should be ~114px tall (110px + border), got {bounding_box['height']}px"
    )
    assert bounding_box["height"] >= 100, (
        f"Thumbnail should be at least 100px tall, got {bounding_box['height']}px — image may have reverted to compact mode"
    )


@pytest.mark.electron
@user_story("to see images with different aspect ratios rendered at consistent height in the strip")
def test_thumbnails_have_consistent_height(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
    square_image_: str,
) -> None:
    """Landscape, portrait, and square images should all render at the same height in the strip.

    This verifies object-fit: cover is working — the images fill a fixed height regardless
    of their natural aspect ratio.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Consistent Height Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_, square_image_])

    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(3)

    heights = []
    for i in range(3):
        thumb = thumbnails.nth(i)
        expect(thumb).to_be_visible()
        box = thumb.bounding_box()
        assert box is not None
        heights.append(box["height"])

    # All three should be the same height (within 1px for rounding)
    assert abs(heights[0] - heights[1]) <= 1, (
        f"Landscape ({heights[0]}px) and portrait ({heights[1]}px) thumbnails should have equal height"
    )
    assert abs(heights[1] - heights[2]) <= 1, (
        f"Portrait ({heights[1]}px) and square ({heights[2]}px) thumbnails should have equal height"
    )


@pytest.mark.electron
@user_story("to see the thumbnail strip persist after page reload")
def test_thumbnail_strip_persists_after_reload(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
) -> None:
    """The horizontal thumbnail strip layout should persist after a soft page reload.

    This guards against regressions where the layout reverts to vertical on reload.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Strip Persist Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_])

    # Verify strip layout before reload
    preview_list = _get_user_message_preview_list(chat_panel)
    expect(preview_list).to_have_css("flex-direction", "row")
    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(2)

    # Reload and verify strip layout persists
    soft_reload_page(task_page)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    preview_list = _get_user_message_preview_list(chat_panel)
    expect(preview_list).to_have_css("flex-direction", "row")
    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(2)


@pytest.mark.electron
@user_story("to click a thumbnail in the strip and open the lightbox for full-size viewing")
def test_thumbnail_click_opens_lightbox(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
) -> None:
    """Clicking a thumbnail in the horizontal strip should open the image lightbox.

    This verifies the clickable cursor and lightbox integration work with the new
    thumbnail layout.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Thumbnail Lightbox Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_])

    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(2)

    # Click the first thumbnail — lightbox should open
    thumbnails.nth(0).click()

    # Verify lightbox is visible via the counter element (present when multiple images)
    lightbox = PlaywrightLightboxElement(page)
    lightbox_counter = lightbox.get_counter()
    expect(lightbox_counter).to_be_visible()
    expect(lightbox_counter).to_contain_text("(1/2)")

    # Close lightbox by pressing Escape
    page.keyboard.press("Escape")
    expect(lightbox_counter).to_have_count(0)


@pytest.mark.electron
@user_story("to see thumbnails use object-fit cover so images fill the thumbnail area")
def test_thumbnails_use_object_fit_cover(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
) -> None:
    """Inline image thumbnails should use object-fit: cover, not contain.

    Cover ensures images fill the thumbnail area without letterboxing, which looks
    better in a compact strip. The lightbox handles full-size viewing.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Object Fit Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, landscape_image_, message="Check this.")

    thumbnails = _get_user_message_thumbnails(chat_panel)
    expect(thumbnails).to_have_count(1)
    expect(thumbnails.nth(0)).to_have_css("object-fit", "cover")


# Alpha chat view tests
#
# Strategy: attach files and send in classic view (where _attach_and_send
# works with ASSISTANT_MESSAGE/USER_MESSAGE selectors), then switch to
# alpha view for layout assertions.  This verifies that AlphaUserMessage
# renders existing file blocks correctly.


def _get_alpha_preview_list(page: Page) -> Locator:
    """Get the FILE_PREVIEW_LIST from the alpha chat view."""
    alpha_view = get_alpha_chat_view(page)
    preview_list = alpha_view.get_file_preview_list()
    expect(preview_list).to_have_count(1)
    return preview_list


def _get_alpha_thumbnails(page: Page) -> Locator:
    """Get the FILE_PREVIEW image elements from the alpha chat view."""
    alpha_view = get_alpha_chat_view(page)
    return alpha_view.get_file_previews()


@pytest.mark.electron
@user_story("to see user message images as a horizontal thumbnail strip in the alpha chat view")
def test_alpha_view_thumbnail_strip_horizontal_layout(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
    square_image_: str,
) -> None:
    """In the alpha view, attaching multiple images should produce a horizontal strip.

    This mirrors the classic view test but verifies the alpha view's AlphaUserMessage
    component also passes displayMode='inline' to FilePreviewList.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Alpha Strip Test")
    chat_panel = task_page.get_chat_panel()

    # Send message in classic view where _attach_and_send works
    _attach_and_send(chat_panel, [landscape_image_, portrait_image_, square_image_])

    # Switch to alpha view and verify the strip layout

    preview_list = _get_alpha_preview_list(page)
    expect(preview_list).to_have_css("flex-direction", "row")


@pytest.mark.electron
@user_story("to see user message thumbnails at consistent height in the alpha chat view")
def test_alpha_view_thumbnails_have_consistent_height(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
    square_image_: str,
) -> None:
    """In the alpha view, thumbnails should all render at the same height regardless of aspect ratio."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Alpha Height Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_, square_image_])

    thumbnails = _get_alpha_thumbnails(page)
    expect(thumbnails).to_have_count(3)

    heights = []
    for i in range(3):
        thumb = thumbnails.nth(i)
        expect(thumb).to_be_visible()
        box = thumb.bounding_box()
        assert box is not None
        heights.append(box["height"])

    assert abs(heights[0] - heights[1]) <= 1, (
        f"Landscape ({heights[0]}px) and portrait ({heights[1]}px) should have equal height"
    )
    assert abs(heights[1] - heights[2]) <= 1, (
        f"Portrait ({heights[1]}px) and square ({heights[2]}px) should have equal height"
    )


@pytest.mark.electron
@user_story("to click a thumbnail in the alpha view and open the lightbox")
def test_alpha_view_thumbnail_click_opens_lightbox(
    sculptor_instance_: SculptorInstance,
    landscape_image_: str,
    portrait_image_: str,
) -> None:
    """Clicking a thumbnail in the alpha view strip should open the lightbox."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Alpha Lightbox Test")
    chat_panel = task_page.get_chat_panel()

    _attach_and_send(chat_panel, [landscape_image_, portrait_image_])

    thumbnails = _get_alpha_thumbnails(page)
    expect(thumbnails).to_have_count(2)

    thumbnails.nth(0).click()

    lightbox = PlaywrightLightboxElement(page)
    lightbox_counter = lightbox.get_counter()
    expect(lightbox_counter).to_be_visible()
    expect(lightbox_counter).to_contain_text("(1/2)")

    page.keyboard.press("Escape")
    expect(lightbox_counter).to_have_count(0)
