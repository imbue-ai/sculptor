import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Sequence

import pytest
from PIL import Image
from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import soft_reload_page
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
    images: str | Sequence[str],
    expected_count: int = 1,
) -> Locator:
    element.attach_files(images)
    image_previews = element.get_file_previews()
    expect(image_previews).to_have_count(expected_count)
    return image_previews


def _verify_image_in_message(
    chat_panel: PlaywrightChatPanelElement, message_index: int, expected_image_count: int = 1
) -> Locator:
    messages = chat_panel.get_messages()
    user_message = messages.nth(message_index)
    expect_message_to_have_role(message=user_message, role=ElementIDs.USER_MESSAGE)

    image_in_message = user_message.get_by_test_id(ElementIDs.FILE_PREVIEW)
    expect(image_in_message).to_have_count(expected_image_count)
    return image_in_message


@pytest.mark.electron
@pytest.mark.electron_custom_command
@user_story("to attach images from the chat input")
def test_image_upload_from_create_task_form(sculptor_instance_: SculptorInstance, test_image_red_: str) -> None:
    """Test that users can attach images when sending messages in a workspace."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Image Upload Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(chat_panel, test_image_red_)
    send_chat_message(chat_panel=chat_panel, message="Describe this image in detail.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    _verify_image_in_message(chat_panel, message_index=0)


@pytest.mark.electron
@pytest.mark.electron_custom_command
@user_story("to attach images from the chat input")
def test_image_upload_from_chat_input(sculptor_instance_: SculptorInstance, test_image_green_: str) -> None:
    """Test that users can attach images when sending messages in an existing task."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Say hello!")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _attach_image_and_verify_preview(chat_panel, test_image_green_)
    send_chat_message(chat_panel=chat_panel, message="What's in this image?")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    _verify_image_in_message(chat_panel, message_index=2)


@pytest.mark.electron
@user_story("to upload multiple images in a single message")
def test_multiple_image_upload(
    sculptor_instance_: SculptorInstance,
    test_image_red_: str,
    test_image_blue_: str,
    test_image_green_: str,
) -> None:
    """Test that users can attach multiple images to a single message."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Multi Image Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(
        chat_panel, [test_image_red_, test_image_blue_, test_image_green_], expected_count=3
    )
    send_chat_message(chat_panel=chat_panel, message="Compare these three images.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    _verify_image_in_message(chat_panel, message_index=0, expected_image_count=3)


@pytest.mark.electron
@pytest.mark.electron_custom_command
@user_story("to see uploaded images persist in chat history")
def test_image_persistence_in_chat_history(sculptor_instance_: SculptorInstance, test_image_red_: str) -> None:
    """Test that uploaded images persist in chat history after page reload."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Image Persist Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(chat_panel, test_image_red_)
    send_chat_message(chat_panel=chat_panel, message="Describe this image.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    _verify_image_in_message(chat_panel, message_index=0)

    soft_reload_page(task_page)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    _verify_image_in_message(chat_panel, message_index=0)


@pytest.mark.electron
@user_story("to attach images from a second agent in the same workspace")
def test_image_upload_from_second_agent(sculptor_instance_: SculptorInstance, test_image_blue_: str) -> None:
    """Test that users can attach images when chatting in a second agent of the same workspace."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt="Initial task")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Add a second agent to the workspace
    agent_tab_bar = task_page.get_agent_tab_bar()
    agent_tab_bar.get_add_agent_button().click()

    expect(agent_tab_bar.get_agent_tabs()).to_have_count(2)

    # The new agent's chat panel should be visible
    new_task_page = PlaywrightTaskPage(page=page)
    new_chat_panel = new_task_page.get_chat_panel()

    _attach_image_and_verify_preview(new_chat_panel, test_image_blue_)
    send_chat_message(chat_panel=new_chat_panel, message="Analyze this image")
    wait_for_completed_message_count(chat_panel=new_chat_panel, expected_message_count=2)
    _verify_image_in_message(new_chat_panel, message_index=0)


@pytest.mark.electron
@user_story("to remove attached images before sending")
def test_remove_attached_image(
    sculptor_instance_: SculptorInstance,
    test_image_red_: str,
    test_image_green_: str,
) -> None:
    """Test that users can remove attached images before sending a message."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Remove Image Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(chat_panel, [test_image_red_, test_image_green_], expected_count=2)
    chat_panel.remove_file(index=0)
    expect(chat_panel.get_file_previews()).to_have_count(1)

    send_chat_message(chat_panel=chat_panel, message="Describe this image.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    _verify_image_in_message(chat_panel, message_index=0, expected_image_count=1)


@pytest.mark.electron
@pytest.mark.electron_custom_command
@user_story("to have images deleted when a task is deleted")
def test_images_deleted_when_task_deleted(
    sculptor_instance_: SculptorInstance,
    test_image_red_: str,
    test_image_green_: str,
) -> None:
    """Test that image files are deleted from disk when a task is deleted."""
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, workspace_name="Delete Images Test")
    chat_panel = task_page.get_chat_panel()

    _attach_image_and_verify_preview(chat_panel, [test_image_red_, test_image_green_], expected_count=2)
    send_chat_message(chat_panel=chat_panel, message="Describe these images.")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    images = _verify_image_in_message(chat_panel, message_index=0, expected_image_count=2)

    # Extract image paths from data-path attributes
    image_paths = []
    for i in range(2):
        image_path = images.nth(i).get_attribute("data-path")
        image_paths.append(Path(image_path))

    # Verify images exist on disk before deletion
    assert len(image_paths) == 2, "Should have extracted 2 image paths"
    for image_path in image_paths:
        assert image_path.exists(), f"Image should exist at {image_path}"

    # Delete the workspace via the API
    base_url = page.url.split("#")[0].rstrip("/")
    response = page.request.get(f"{base_url}/api/v1/workspaces/recent")
    assert response.ok, f"Failed to list workspaces: {response.status}"
    workspaces = response.json().get("workspaces", [])
    assert len(workspaces) == 1, f"Expected 1 workspace, got {len(workspaces)}"
    ws_id = workspaces[0]["objectId"]
    delete_resp = page.request.delete(f"{base_url}/api/v1/workspaces/{ws_id}")
    assert delete_resp.ok, f"Failed to delete workspace: {delete_resp.status}"

    # Verify images no longer exist on disk
    for image_path in image_paths:
        assert not image_path.exists(), f"Image should be deleted at {image_path}"
