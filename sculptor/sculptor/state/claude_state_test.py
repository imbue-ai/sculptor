import json

from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import TextBlock
from sculptor.state.claude_state import ParsedAssistantResponse
from sculptor.state.claude_state import extract_media_tags_from_text
from sculptor.state.claude_state import get_tool_invocation_string
from sculptor.state.claude_state import parse_claude_code_json_lines_simple
from sculptor.state.claude_state import split_text_and_media


def test_extract_img_tags_no_img_tags_returns_text_unchanged() -> None:
    text = "Hello, this is plain text with no images."
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_img_tags_single_local_path() -> None:
    text = '<img src="/workspace/attachments/screenshot.png" alt="full page">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/workspace/attachments/screenshot.png"]


def test_extract_img_tags_self_closing_tag() -> None:
    text = '<img src="/path/to/image.jpg" alt="test" />'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/to/image.jpg"]


def test_extract_img_tags_multiple_images() -> None:
    text = '<img src="/path/one.png" alt="first"> <img src="/path/two.jpg" alt="second">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/one.png", "/path/two.jpg"]


def test_extract_img_tags_http_url_left_untouched() -> None:
    text = '<img src="https://example.com/image.png" alt="remote">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_img_tags_data_url_left_untouched() -> None:
    text = '<img src="data:image/png;base64,abc123" alt="inline">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_img_tags_mixed_prose_and_img() -> None:
    text = 'Here is a screenshot:\n\n<img src="/tmp/screenshot.png" alt="screenshot">\n\nWhat do you think?'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == "Here is a screenshot:\n\n\n\nWhat do you think?"
    assert paths == ["/tmp/screenshot.png"]


def test_extract_img_tags_only_img_tag_returns_empty_cleaned_text() -> None:
    text = '  <img src="/path/image.png" alt="test">  '
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/image.png"]


def test_extract_img_tags_mixed_local_and_http() -> None:
    text = '<img src="/local/path.png" alt="local"> <img src="https://example.com/img.png" alt="remote">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert '<img src="https://example.com/img.png" alt="remote">' in cleaned
    assert paths == ["/local/path.png"]


def test_extract_img_tags_single_quotes() -> None:
    text = "<img src='/path/to/image.png' alt='test'>"
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/to/image.png"]


def test_extract_video_tag_single_local_path() -> None:
    text = '<video src="/workspace/attachments/screenshots/recording.webm" controls></video>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/workspace/attachments/screenshots/recording.webm"]


def test_extract_video_tag_self_closing() -> None:
    text = '<video src="/path/to/video.mp4" />'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/to/video.mp4"]


def test_extract_video_tag_http_url_left_untouched() -> None:
    text = '<video src="https://example.com/video.mp4" controls></video>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_mixed_img_and_video_tags() -> None:
    text = '<img src="/path/screenshot.png" alt="ss"> <video src="/path/recording.webm" controls></video>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/screenshot.png", "/path/recording.webm"]


def test_extract_video_tag_with_prose() -> None:
    text = 'Here is the recording:\n\n<video src="/tmp/recording.mp4" controls></video>\n\nDone.'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == "Here is the recording:\n\n\n\nDone."
    assert paths == ["/tmp/recording.mp4"]


def test_extract_video_tag_multiline_closing_tag() -> None:
    text = '<video src="/path/video.webm" controls>\n</video>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/video.webm"]


def test_extract_img_tag_multiline_closing_tag() -> None:
    text = '<img src="/path/image.png" alt="test">\n</img>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/image.png"]


def test_extract_img_tag_html_file_left_untouched() -> None:
    text = '<img src="/path/to/mocks.html" alt="test">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_img_tag_txt_file_left_untouched() -> None:
    text = '<img src="/path/to/readme.txt" alt="test">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_video_tag_html_file_left_untouched() -> None:
    text = '<video src="/path/to/page.html" controls></video>'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_img_tag_no_extension_left_untouched() -> None:
    text = '<img src="/path/to/file" alt="test">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == text
    assert paths == []


def test_extract_mixed_media_and_non_media_files() -> None:
    """Only extract supported media files; leave non-media img tags untouched."""
    text = '<img src="/path/screenshot.png" alt="ss"> <img src="/path/mocks.html" alt="mock">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert '<img src="/path/mocks.html" alt="mock">' in cleaned
    assert paths == ["/path/screenshot.png"]


def test_extract_img_tag_supported_extensions() -> None:
    """All supported image extensions should be extracted."""
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
        text = f'<img src="/path/to/file{ext}" alt="test">'
        cleaned, paths = extract_media_tags_from_text(text)
        assert paths == [f"/path/to/file{ext}"], f"Failed for extension {ext}"
        assert cleaned == ""


def test_extract_video_tag_supported_extensions() -> None:
    """All supported video extensions should be extracted."""
    for ext in [".mp4", ".webm", ".mov"]:
        text = f'<video src="/path/to/file{ext}" controls></video>'
        cleaned, paths = extract_media_tags_from_text(text)
        assert paths == [f"/path/to/file{ext}"], f"Failed for extension {ext}"
        assert cleaned == ""


def test_extract_img_tag_case_insensitive_extension() -> None:
    text = '<img src="/path/to/image.PNG" alt="test">'
    cleaned, paths = extract_media_tags_from_text(text)
    assert cleaned == ""
    assert paths == ["/path/to/image.PNG"]


def test_split_text_and_media_no_media() -> None:
    text = "Hello, this is plain text."
    result = split_text_and_media(text)
    assert result == [TextBlock(text=text)]


def test_split_text_and_media_single_image() -> None:
    text = 'Here is a screenshot:\n\n<img src="/tmp/screenshot.png" alt="ss">\n\nWhat do you think?'
    result = split_text_and_media(text)
    assert result == [
        TextBlock(text="Here is a screenshot:"),
        FileBlock(source="/tmp/screenshot.png"),
        TextBlock(text="What do you think?"),
    ]


def test_split_text_and_media_multiple_interleaved_images() -> None:
    """Multiple images with labels should preserve interleaved order."""
    text = (
        "Image 1 — Chat UI:\n"
        '<img src="/tmp/image1.png" alt="first">\n'
        "Image 2 — Bug analysis:\n"
        '<img src="/tmp/image2.png" alt="second">\n'
        "Image 3 — Workspace:\n"
        '<img src="/tmp/image3.png" alt="third">\n'
        "The three images show the progression."
    )
    result = split_text_and_media(text)
    assert result == [
        TextBlock(text="Image 1 — Chat UI:"),
        FileBlock(source="/tmp/image1.png"),
        TextBlock(text="Image 2 — Bug analysis:"),
        FileBlock(source="/tmp/image2.png"),
        TextBlock(text="Image 3 — Workspace:"),
        FileBlock(source="/tmp/image3.png"),
        TextBlock(text="The three images show the progression."),
    ]


def test_split_text_and_media_consecutive_images_no_empty_text() -> None:
    """Consecutive images without text between them should not produce empty TextBlocks."""
    text = '<img src="/tmp/a.png" alt="a"> <img src="/tmp/b.png" alt="b">'
    result = split_text_and_media(text)
    assert result == [
        FileBlock(source="/tmp/a.png"),
        FileBlock(source="/tmp/b.png"),
    ]


def test_split_text_and_media_http_url_stays_in_text() -> None:
    text = '<img src="https://example.com/img.png" alt="remote"> <img src="/local/img.png" alt="local">'
    result = split_text_and_media(text)
    assert result == [
        TextBlock(text='<img src="https://example.com/img.png" alt="remote">'),
        FileBlock(source="/local/img.png"),
    ]


def test_split_text_and_media_mixed_img_and_video() -> None:
    text = 'Screenshot:\n<img src="/tmp/ss.png" alt="ss">\nRecording:\n<video src="/tmp/rec.webm" controls></video>'
    result = split_text_and_media(text)
    assert result == [
        TextBlock(text="Screenshot:"),
        FileBlock(source="/tmp/ss.png"),
        TextBlock(text="Recording:"),
        FileBlock(source="/tmp/rec.webm"),
    ]


def test_parse_assistant_message_extracts_img_tags_into_file_blocks() -> None:
    """Verify that img tags in assistant text blocks are extracted as FileBlocks."""
    data = {
        "type": "assistant",
        "message": {
            "id": "msg_123",
            "content": [
                {
                    "type": "text",
                    "text": 'Here is the screenshot:\n\n<img src="/workspace/attachments/screenshot.png" alt="full page">\n\nLooks good!',
                }
            ],
        },
    }
    line = json.dumps(data)
    result = parse_claude_code_json_lines_simple(line)
    assert result is not None
    message_type, parsed = result
    assert message_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)

    blocks = parsed.content_blocks
    assert len(blocks) == 2
    text_block = blocks[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "Here is the screenshot:\n\n\n\nLooks good!"
    file_block = blocks[1]
    assert isinstance(file_block, FileBlock)
    assert file_block.source == "/workspace/attachments/screenshot.png"


def test_parse_assistant_message_only_img_tag_produces_only_file_block() -> None:
    """When assistant text is only an img tag, only a FileBlock should be produced (no empty TextBlock)."""
    data = {
        "type": "assistant",
        "message": {
            "id": "msg_456",
            "content": [
                {
                    "type": "text",
                    "text": '<img src="/workspace/attachments/result.png" alt="result">',
                }
            ],
        },
    }
    line = json.dumps(data)
    result = parse_claude_code_json_lines_simple(line)
    assert result is not None
    message_type, parsed = result
    assert message_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)

    blocks = parsed.content_blocks
    assert len(blocks) == 1
    file_block = blocks[0]
    assert isinstance(file_block, FileBlock)
    assert file_block.source == "/workspace/attachments/result.png"


def test_parse_assistant_message_no_img_tags_produces_text_block_only() -> None:
    """Normal text without img tags should produce a single TextBlock."""
    data = {
        "type": "assistant",
        "message": {
            "id": "msg_789",
            "content": [
                {
                    "type": "text",
                    "text": "This is normal text with no images.",
                }
            ],
        },
    }
    line = json.dumps(data)
    result = parse_claude_code_json_lines_simple(line)
    assert result is not None
    message_type, parsed = result
    assert message_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)

    blocks = parsed.content_blocks
    assert len(blocks) == 1
    text_block = blocks[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "This is normal text with no images."


def test_parse_assistant_message_extracts_video_tag_into_file_block() -> None:
    """Verify that video tags in assistant text blocks are extracted as FileBlocks."""
    data = {
        "type": "assistant",
        "message": {
            "id": "msg_vid",
            "content": [
                {
                    "type": "text",
                    "text": 'Here is the recording:\n\n<video src="/workspace/attachments/screenshots/recording.webm" controls></video>\n\nDone.',
                }
            ],
        },
    }
    line = json.dumps(data)
    result = parse_claude_code_json_lines_simple(line)
    assert result is not None
    message_type, parsed = result
    assert message_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)

    blocks = parsed.content_blocks
    assert len(blocks) == 2
    text_block = blocks[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "Here is the recording:\n\n\n\nDone."
    file_block = blocks[1]
    assert isinstance(file_block, FileBlock)
    assert file_block.source == "/workspace/attachments/screenshots/recording.webm"


def test_get_tool_invocation_string_skill_returns_skill_name() -> None:
    """The Skill tool should display the skill name, not 'tool invocation'."""
    result = get_tool_invocation_string("Skill", {"skill": "fix-bug", "args": "some description"})
    assert result == "fix-bug"


def test_get_tool_invocation_string_skill_without_args() -> None:
    result = get_tool_invocation_string("Skill", {"skill": "commit"})
    assert result == "commit"
