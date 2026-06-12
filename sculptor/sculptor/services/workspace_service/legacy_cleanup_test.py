"""Tests for the obsolete-MRU-file sweep run from the FastAPI lifespan."""

from pathlib import Path

import pytest

from sculptor.services.workspace_service import legacy_cleanup
from sculptor.services.workspace_service.legacy_cleanup import cleanup_obsolete_mru_files


@pytest.fixture
def fake_sculptor_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Redirect get_internal_folder/get_workspaces_folder to tmp_path subdirectories."""
    internal = tmp_path / "internal"
    workspaces = tmp_path / "workspaces"
    internal.mkdir()
    workspaces.mkdir()
    monkeypatch.setattr(legacy_cleanup, "get_internal_folder", lambda: internal)
    monkeypatch.setattr(legacy_cleanup, "get_workspaces_folder", lambda: workspaces)
    return internal, workspaces


def test_removes_workspace_and_agent_mru_files(fake_sculptor_dirs: tuple[Path, Path]) -> None:
    internal, workspaces = fake_sculptor_dirs
    workspace_mru = internal / "most_recently_used_workspace.txt"
    workspace_mru.write_text("ws_abc")
    agent_a = workspaces / "most_recently_used_agent_aaa.txt"
    agent_b = workspaces / "most_recently_used_agent_bbb.txt"
    agent_a.write_text("tsk_a")
    agent_b.write_text("tsk_b")

    cleanup_obsolete_mru_files()

    assert not workspace_mru.exists()
    assert not agent_a.exists()
    assert not agent_b.exists()


def test_is_idempotent(fake_sculptor_dirs: tuple[Path, Path]) -> None:
    internal, workspaces = fake_sculptor_dirs
    (internal / "most_recently_used_workspace.txt").write_text("ws_abc")

    cleanup_obsolete_mru_files()
    # Second call must not raise even though the files are already gone.
    cleanup_obsolete_mru_files()


def test_preserves_unrelated_files(fake_sculptor_dirs: tuple[Path, Path]) -> None:
    internal, workspaces = fake_sculptor_dirs
    unrelated = workspaces / "something_else.txt"
    unrelated.write_text("keep me")
    sibling = internal / "other_settings.txt"
    sibling.write_text("keep me too")

    cleanup_obsolete_mru_files()

    assert unrelated.exists()
    assert sibling.exists()


def test_no_files_present_does_not_raise(fake_sculptor_dirs: tuple[Path, Path]) -> None:
    cleanup_obsolete_mru_files()


def test_workspaces_directory_missing_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    internal = tmp_path / "internal"
    internal.mkdir()
    monkeypatch.setattr(legacy_cleanup, "get_internal_folder", lambda: internal)
    monkeypatch.setattr(legacy_cleanup, "get_workspaces_folder", lambda: tmp_path / "missing")

    cleanup_obsolete_mru_files()
