"""Unit tests for pi prompt assembly: the image predicate, attachment saving,
the image/path split, image-block encoding, and the prompt-text instructions.
"""

from __future__ import annotations

import base64

import pytest

from sculptor.agents.pi_agent.prompt_assembly import build_attachment_instructions
from sculptor.agents.pi_agent.prompt_assembly import build_image_block
from sculptor.agents.pi_agent.prompt_assembly import image_mime_type
from sculptor.agents.pi_agent.prompt_assembly import is_image_attachment
from sculptor.agents.pi_agent.prompt_assembly import split_image_and_path_attachments


@pytest.mark.parametrize(
    "path",
    [
        "a.png",
        "a.PNG",
        "/abs/b.jpg",
        "c.jpeg",
        "shot.webp",
        "anim.gif",
        "UPPER.GIF",
    ],
)
def test_is_image_attachment_true_for_accepted_image_formats(path: str) -> None:
    assert is_image_attachment(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "notes.txt",
        "report.pdf",
        "README.md",
        "data.json",
        "no_extension",
        "archive.png.zip",
    ],
)
def test_is_image_attachment_false_for_non_images(path: str) -> None:
    assert is_image_attachment(path) is False


@pytest.mark.parametrize(
    "path,expected",
    [
        ("x.png", "image/png"),
        ("x.PNG", "image/png"),
        ("x.jpg", "image/jpeg"),
        ("x.jpeg", "image/jpeg"),
        ("x.webp", "image/webp"),
        ("x.gif", "image/gif"),
    ],
)
def test_image_mime_type_maps_each_accepted_format(path: str, expected: str) -> None:
    assert image_mime_type(path) == expected


def test_split_image_and_path_attachments_partitions_exclusively() -> None:
    paths = ["/a/one.png", "/a/two.txt", "/a/three.jpeg", "/a/four.pdf"]
    images, others = split_image_and_path_attachments(paths)
    assert images == ("/a/one.png", "/a/three.jpeg")
    assert others == ("/a/two.txt", "/a/four.pdf")
    # Exclusive: no path appears in both partitions.
    assert set(images).isdisjoint(others)


def test_split_handles_empty() -> None:
    assert split_image_and_path_attachments([]) == ((), ())


def test_build_image_block_base64_encodes_with_mime_type() -> None:
    data = b"\x89PNG\r\n\x1a\nfake-bytes"
    block = build_image_block("/saved/abc.png", data)
    assert block == {
        "type": "image",
        "data": base64.b64encode(data).decode("ascii"),
        "mimeType": "image/png",
    }
    # Base64 is unwrapped — no embedded newlines that would break the JSONL line.
    assert "\n" not in block["data"]


def test_build_attachment_instructions_empty_when_no_paths() -> None:
    assert build_attachment_instructions([]) == ""


def test_build_attachment_instructions_renders_claude_style_block() -> None:
    text = build_attachment_instructions(["/env/attachments/notes.txt", "/env/attachments/data.csv"])
    assert "<system-instructions>" in text
    assert "The user has attached these files. Read them before proceeding." in text
    assert "/env/attachments/notes.txt" in text
    assert "/env/attachments/data.csv" in text
    assert text.endswith("</system-instructions>\n\n")
