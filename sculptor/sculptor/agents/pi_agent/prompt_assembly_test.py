"""Unit tests for pi prompt assembly: the image predicate, attachment saving,
the image/path split, image-block encoding, and the prompt-text instructions.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sculptor.agents.pi_agent import prompt_assembly
from sculptor.agents.pi_agent.prompt_assembly import build_attachment_instructions
from sculptor.agents.pi_agent.prompt_assembly import build_image_block
from sculptor.agents.pi_agent.prompt_assembly import image_mime_type
from sculptor.agents.pi_agent.prompt_assembly import is_image_attachment
from sculptor.agents.pi_agent.prompt_assembly import save_attachments_to_environment
from sculptor.agents.pi_agent.prompt_assembly import split_image_and_path_attachments
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment


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


def _mock_environment(attachments_dir: Path) -> AgentExecutionEnvironment:
    environment = MagicMock(spec=AgentExecutionEnvironment)
    environment.get_attachments_path.return_value = attachments_dir
    return environment


def test_save_attachments_resolves_absolute_path_and_copies_into_environment(tmp_path: Path) -> None:
    source = tmp_path / "picture.png"
    source.write_bytes(b"image-bytes")
    attachments_dir = tmp_path / "attachments"
    environment = _mock_environment(attachments_dir)

    saved = save_attachments_to_environment(environment, [str(source)])

    assert saved == (str(attachments_dir / "picture.png"),)
    environment.write_file.assert_called_once_with(
        path=str(attachments_dir / "picture.png"), content=b"image-bytes", mode="wb"
    )


def test_save_attachments_resolves_upload_id_under_internal_uploads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal = tmp_path / "internal"
    uploads = internal / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "uuid-123.txt").write_bytes(b"text-bytes")
    monkeypatch.setattr(prompt_assembly, "get_internal_folder", lambda: internal)
    attachments_dir = tmp_path / "attachments"
    environment = _mock_environment(attachments_dir)

    saved = save_attachments_to_environment(environment, ["uuid-123.txt"])

    assert saved == (str(attachments_dir / "uuid-123.txt"),)
    environment.write_file.assert_called_once_with(
        path=str(attachments_dir / "uuid-123.txt"), content=b"text-bytes", mode="wb"
    )


def test_save_attachments_skips_missing_source_without_failing(tmp_path: Path) -> None:
    present = tmp_path / "present.png"
    present.write_bytes(b"ok")
    missing = tmp_path / "gone.png"  # never created
    attachments_dir = tmp_path / "attachments"
    environment = _mock_environment(attachments_dir)

    saved = save_attachments_to_environment(environment, [str(missing), str(present)])

    # The missing source is skipped (not fatal); the present one still saves.
    assert saved == (str(attachments_dir / "present.png"),)
    environment.write_file.assert_called_once_with(path=str(attachments_dir / "present.png"), content=b"ok", mode="wb")
