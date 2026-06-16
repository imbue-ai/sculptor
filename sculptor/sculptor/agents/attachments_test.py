"""Unit tests for the shared attachment-saving helper used by both harnesses."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sculptor.agents import attachments
from sculptor.agents.attachments import save_attachments_to_environment
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment


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
    # pyrefly: ignore [missing-attribute]
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
    monkeypatch.setattr(attachments, "get_internal_folder", lambda: internal)
    attachments_dir = tmp_path / "attachments"
    environment = _mock_environment(attachments_dir)

    saved = save_attachments_to_environment(environment, ["uuid-123.txt"])

    assert saved == (str(attachments_dir / "uuid-123.txt"),)
    # pyrefly: ignore [missing-attribute]
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
    # pyrefly: ignore [missing-attribute]
    environment.write_file.assert_called_once_with(path=str(attachments_dir / "present.png"), content=b"ok", mode="wb")
