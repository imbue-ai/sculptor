"""Test inline media display: <img> and <video> tags in assistant messages render as file previews."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import expect_message_to_have_role
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@pytest.fixture
def test_image_path_() -> Generator[str, None, None]:
    """Create a temporary test image and return its absolute path."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    img = Image.new("RGB", (100, 100), (255, 0, 0))
    img.save(temp_path)

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


@user_story("to see inline images rendered in agent responses")
def test_assistant_img_tag_renders_file_preview(
    sculptor_instance_: SculptorInstance,
    test_image_path_: str,
) -> None:
    """An <img> tag in assistant text should produce a visible file preview in the chat UI.

    Steps:
    1. Create a task with a FakeClaude text response containing an <img> tag
       pointing to a real local image file
    2. Wait for the assistant response to complete
    3. Assert that the assistant message contains a FILE_PREVIEW_CONTAINER element,
       confirming the FileBlock was delivered to the frontend and rendered
    """
    # Use HTML entities for angle brackets so TipTap's insertContent() treats
    # them as plain text instead of interpreting them as HTML.  FakeClaude calls
    # html.unescape() on stdin, restoring the real <img> tag before processing.
    # Use single quotes for HTML attributes to avoid breaking the JSON string.
    img_tag = f"&lt;img src='{test_image_path_}' alt='test screenshot'&gt;"
    task_text = f'fake_claude:text `{{"text": "Here is a screenshot:\\n\\n{img_tag}\\n\\nDone."}}`'

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=task_text,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()

    assistant_message = messages.nth(1)
    expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

    file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
    expect(file_preview_container).to_have_count(1)

    # The assistant text (without the img tag) should also be visible
    expect(assistant_message).to_contain_text("Here is a screenshot")
    expect(assistant_message).to_contain_text("Done.")


@user_story("to not see non-media files rendered as file previews")
def test_assistant_img_tag_with_html_file_does_not_render_file_preview(
    sculptor_instance_: SculptorInstance,
) -> None:
    """An <img> tag referencing a non-media file (e.g. .html) should NOT produce a file preview.

    This is a regression test: previously, extract_media_tags_from_text extracted
    any absolute local path from <img> tags regardless of file extension, causing
    .html files to appear as broken file previews in the chat.
    """
    img_tag = "&lt;img src='/tmp/mocks.html' alt='mocks'&gt;"
    task_text = f'fake_claude:text `{{"text": "Here are the mocks:\\n\\n{img_tag}\\n\\nDone."}}`'

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=task_text,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()

    assistant_message = messages.nth(1)
    expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

    # No FileBlock should be created for .html files — no file preview should appear
    file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
    expect(file_preview_container).to_have_count(0)

    # The text content should be preserved (the <img> tag is left in the text,
    # but react-markdown strips raw HTML so only the surrounding text is visible)
    expect(assistant_message).to_contain_text("Here are the mocks")
    expect(assistant_message).to_contain_text("Done.")


@user_story("to see only media files rendered as file previews when mixed with non-media")
def test_assistant_mixed_media_and_non_media_img_tags(
    sculptor_instance_: SculptorInstance,
    test_image_path_: str,
) -> None:
    """When text contains both a .png and a .html img tag, only the .png should render as a preview.

    This verifies that the file extension filter correctly separates media from non-media
    files in the same message.
    """
    png_tag = f"&lt;img src='{test_image_path_}' alt='screenshot'&gt;"
    html_tag = "&lt;img src='/tmp/mocks.html' alt='mocks'&gt;"
    task_text = f'fake_claude:text `{{"text": "Results:\\n\\n{png_tag}\\n\\n{html_tag}\\n\\nDone."}}`'

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=task_text,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()

    assistant_message = messages.nth(1)
    expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

    # Only one FILE_PREVIEW_CONTAINER should appear (for the .png, not the .html)
    file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
    expect(file_preview_container).to_have_count(1)

    expect(assistant_message).to_contain_text("Results")
    expect(assistant_message).to_contain_text("Done.")


@user_story("to see inline images persist after a tool call in the same message")
def test_assistant_img_tag_persists_after_tool_call(
    sculptor_instance_: SculptorInstance,
    test_image_path_: str,
) -> None:
    """An <img> tag rendered as a FileBlock should remain visible after a subsequent tool call.

    Regression test: during streaming, when text containing an <img> tag was followed
    by a tool_use block, the FileBlock was lost because _handle_partial_response replaced
    content from streaming_start_index onwards without preserving FileBlocks that arrived
    via ResponseBlockAgentMessage.

    Steps:
    1. Use fake_claude:multi_step to produce text with an <img> tag, then a bash tool call
    2. Wait for the response to complete
    3. Assert the FILE_PREVIEW_CONTAINER is still visible in the assistant message
    """
    img_tag = f"&lt;img src='{test_image_path_}' alt='test screenshot'&gt;"
    prompt = (
        "fake_claude:multi_step `{"
        '"steps": ['
        f'{{"command": "text", "args": {{"text": "Here is a screenshot:\\n\\n{img_tag}\\n\\nDone."}}}},'
        '{"command": "bash", "args": {"command": "echo hello"}}'
        "]}`"
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=prompt,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()

    assistant_message = messages.nth(1)
    expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

    # The FileBlock should still be present after the tool call
    file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
    expect(file_preview_container).to_have_count(1)

    expect(assistant_message).to_contain_text("Here is a screenshot")
    expect(assistant_message).to_contain_text("Done.")


@user_story("to see an inline image stay after a preceding tool call in the same streamed message")
def test_assistant_img_after_tool_in_same_message_keeps_order(
    sculptor_instance_: SculptorInstance,
    test_image_path_: str,
) -> None:
    """A tool_use FOLLOWED by text containing an <img>, in ONE streamed assistant message, must
    render the image AFTER the tool (next to its source text) — not jump in front of the tool.

    Regression for the streaming reorder/disappearing bug: output_processor._materialize_content
    splices every extracted <img>/<video> FileBlock before the FIRST ToolUseBlock. When the
    image's source text comes AFTER a tool, the image (and the text following it) are mis-ordered
    in front of the tool, so already-streamed blocks visibly move and content appears to disappear
    and be replaced by other content.

    Uses fake_claude:interleaved_tools to stream [Bash tool, then text with an <img>] as a single
    assistant message — the block order real Claude can produce but the text-first tool commands
    (write_file/bash/etc.) cannot.
    """
    img_tag = f"&lt;img src='{test_image_path_}' alt='test screenshot'&gt;"
    blocks_json = json.dumps(
        {
            "blocks": [
                {"type": "tool", "tool_name": "Bash", "tool_input": {"command": "echo hello"}},
                {"type": "text", "text": f"look {img_tag} done"},
            ]
        }
    )
    prompt = f"fake_claude:interleaved_tools `{blocks_json}`"

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt=prompt,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    messages = chat_panel.get_messages()
    assistant_message = messages.nth(1)
    expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

    # Both the bash block and the inline image should be present.
    expect(assistant_message.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_BLOCK)).to_have_count(1)
    expect(assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)).to_have_count(1)

    # The source text "look <img> done" splits into "look " (before the image) and " done"
    # (after it), both AFTER the tool. So in document order the first assistant text block is
    # "look" and the second is "done". The bug splices the image and its trailing text in front
    # of the tool, which reverses these (" done" renders before "look ").
    text_blocks = assistant_message.get_by_test_id(ElementIDs.ALPHA_CHAT_TEXT)
    expect(text_blocks).to_have_count(2)
    expect(text_blocks.nth(0)).to_contain_text("look")
    expect(text_blocks.nth(1)).to_contain_text("done")


@user_story("to see inline images persist after restarting Sculptor")
def test_assistant_img_tag_persists_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
    test_image_path_: str,
) -> None:
    """An <img> tag rendered as a FileBlock should remain visible after a full restart.

    Regression test: images would disappear after restarting Sculptor because the
    persisted messages were replayed without extracting FileBlocks from text.

    Steps:
    1. Start Sculptor, create a task with text containing an <img> tag
    2. Wait for the assistant response and verify the image is visible
    3. Shut down Sculptor (exit context)
    4. Restart Sculptor (new spawn_instance)
    5. Navigate to the workspace and verify the image is still visible
    """
    # Phase 1: Start a task with an image and verify it displays
    with sculptor_instance_factory_.spawn_instance() as instance:
        img_tag = f"&lt;img src='{test_image_path_}' alt='test screenshot'&gt;"
        task_text = f'fake_claude:text `{{"text": "Here is a screenshot:\\n\\n{img_tag}\\n\\nDone."}}`'

        task_page = start_task_and_wait_for_ready(
            instance.page,
            prompt=task_text,
        )

        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        messages = chat_panel.get_messages()
        assistant_message = messages.nth(1)
        expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

        # Verify the image is visible before restart
        file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
        expect(file_preview_container).to_have_count(1)

    # Phase 2: Restart and verify the image persisted
    with sculptor_instance_factory_.spawn_instance() as instance:
        new_task_page = PlaywrightTaskPage(page=instance.page)
        workspace_tab = new_task_page.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        chat_panel = new_task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        messages = chat_panel.get_messages()
        assistant_message = messages.nth(1)
        expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

        # The FileBlock should still be visible after restart
        file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
        expect(file_preview_container).to_have_count(1)

        expect(assistant_message).to_contain_text("Here is a screenshot")
        expect(assistant_message).to_contain_text("Done.")


@user_story("to see multiple assistant images rendered as a horizontal thumbnail strip")
def test_assistant_multiple_images_render_as_thumbnail_strip(
    sculptor_instance_: SculptorInstance,
    test_image_path_: str,
) -> None:
    """Multiple <img> tags in one assistant message should render as a horizontal thumbnail strip.

    The FILE_PREVIEW_LIST container should use flex-direction: row so images appear
    side by side, matching the layout used in user messages.
    """
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    second_image_path = temp_file.name
    temp_file.close()
    img = Image.new("RGB", (200, 100), (0, 0, 255))
    img.save(second_image_path)

    try:
        img_tag_1 = f"&lt;img src='{test_image_path_}' alt='first'&gt;"
        img_tag_2 = f"&lt;img src='{second_image_path}' alt='second'&gt;"
        task_text = (
            f'fake_claude:text `{{"text": "Here are screenshots:\\n\\n{img_tag_1}\\n\\n{img_tag_2}\\n\\nDone."}}`'
        )

        task_page = start_task_and_wait_for_ready(
            sculptor_instance_.page,
            prompt=task_text,
        )

        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        messages = chat_panel.get_messages()
        assistant_message = messages.nth(1)
        expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

        # Both images should be rendered as file previews
        file_preview_containers = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
        expect(file_preview_containers).to_have_count(2)

        # The FILE_PREVIEW_LIST should use horizontal row direction for the strip layout
        preview_list = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_LIST)
        expect(preview_list).to_have_count(1)
        expect(preview_list).to_have_css("flex-direction", "row")
    finally:
        Path(second_image_path).unlink(missing_ok=True)


@user_story("to see inline images persist after tool call and restart")
def test_assistant_img_tag_persists_after_tool_call_and_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
    test_image_path_: str,
) -> None:
    """An <img> tag in a single message with a tool call should survive a full restart.

    Uses text_and_bash to produce a SINGLE assistant message containing both text with
    an <img> tag AND a tool_use block (matching real Claude Code behavior where text and
    tool calls are in the same message), then restarts Sculptor to test replay.

    Steps:
    1. Start Sculptor, create a task with text_and_bash: text containing <img> tag + bash
    2. Wait for the response to complete and verify the image is visible
    3. Shut down Sculptor (exit context)
    4. Restart Sculptor (new spawn_instance)
    5. Navigate to the workspace and verify the image is still visible
    """
    # Phase 1: Start a task with image + tool call in a SINGLE message and verify it displays
    with sculptor_instance_factory_.spawn_instance() as instance:
        img_tag = f"&lt;img src='{test_image_path_}' alt='test screenshot'&gt;"
        prompt = (
            "fake_claude:text_and_bash `{"
            f'"text": "Here is a screenshot:\\n\\n{img_tag}\\n\\nDone.", '
            '"command": "echo hello"'
            "}`"
        )

        task_page = start_task_and_wait_for_ready(
            instance.page,
            prompt=prompt,
        )

        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        messages = chat_panel.get_messages()
        assistant_message = messages.nth(1)
        expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

        # Verify the image is visible before restart
        file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
        expect(file_preview_container).to_have_count(1)

        # Verify the text is visible before restart
        expect(assistant_message).to_contain_text("Here is a screenshot")
        expect(assistant_message).to_contain_text("Done.")

    # Phase 2: Restart and verify the image persisted
    with sculptor_instance_factory_.spawn_instance() as instance:
        new_task_page = PlaywrightTaskPage(page=instance.page)
        workspace_tab = new_task_page.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        chat_panel = new_task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        messages = chat_panel.get_messages()
        assistant_message = messages.nth(1)
        expect_message_to_have_role(message=assistant_message, role=ElementIDs.ASSISTANT_MESSAGE)

        # The FileBlock should still be visible after restart
        file_preview_container = assistant_message.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)
        expect(file_preview_container).to_have_count(1)

        expect(assistant_message).to_contain_text("Here is a screenshot")
        expect(assistant_message).to_contain_text("Done.")
