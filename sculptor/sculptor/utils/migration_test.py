from pathlib import Path
from unittest.mock import patch

import pytest

from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.migration import ensure_sculptor_folder_ready
from sculptor.utils.migration import get_extensions_directory


@pytest.fixture(autouse=True)
def _clear_sculptor_folder_cache():
    get_sculptor_folder.cache_clear()
    yield
    get_sculptor_folder.cache_clear()


def test_fresh_install_creates_internal_workspaces_and_format_version(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        ensure_sculptor_folder_ready()

    assert (sculptor_path / "internal").is_dir()
    assert (sculptor_path / "workspaces").is_dir()
    assert (sculptor_path / ".format_version").is_file()
    assert (sculptor_path / ".format_version").read_text().strip() == "1"


def test_normal_startup_returns_without_side_effects(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    sculptor_path.mkdir()
    (sculptor_path / ".format_version").write_text("1\n")

    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        ensure_sculptor_folder_ready()

    # Should not have created internal/ or workspaces/
    assert not (sculptor_path / "internal").exists()
    assert not (sculptor_path / "workspaces").exists()


def test_existing_folder_without_format_version_bootstraps(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    sculptor_path.mkdir()
    # Folder exists but no .format_version — should bootstrap, not error
    (sculptor_path / "some_existing_file.txt").write_text("data")

    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        ensure_sculptor_folder_ready()

    assert (sculptor_path / "internal").is_dir()
    assert (sculptor_path / "workspaces").is_dir()
    assert (sculptor_path / ".format_version").is_file()
    assert (sculptor_path / ".format_version").read_text().strip() == "1"
    # Existing file should still be there
    assert (sculptor_path / "some_existing_file.txt").is_file()


def test_get_extensions_directory_renames_the_legacy_plugins_dir(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    legacy_dir = sculptor_path / "plugins"
    (legacy_dir / "my-extension").mkdir(parents=True)
    (legacy_dir / "my-extension" / "manifest.json").write_text("{}")

    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        extensions_dir = get_extensions_directory()

    assert extensions_dir == sculptor_path / "extensions"
    assert not legacy_dir.exists()
    assert (extensions_dir / "my-extension" / "manifest.json").is_file()


def test_get_extensions_directory_never_clobbers_an_existing_dir(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    (sculptor_path / "extensions" / "new-extension").mkdir(parents=True)
    (sculptor_path / "plugins" / "old-extension").mkdir(parents=True)

    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        extensions_dir = get_extensions_directory()

    # Both directories are left untouched: extensions/ keeps its contents and
    # the legacy plugins/ dir is ignored rather than merged or deleted.
    assert (extensions_dir / "new-extension").is_dir()
    assert not (extensions_dir / "old-extension").exists()
    assert (sculptor_path / "plugins" / "old-extension").is_dir()


def test_get_extensions_directory_serves_the_legacy_dir_when_the_rename_fails(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    legacy_dir = sculptor_path / "plugins"
    (legacy_dir / "my-extension").mkdir(parents=True)

    with (
        patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path),
        patch.object(Path, "rename", side_effect=OSError("device or resource busy")),
    ):
        extensions_dir = get_extensions_directory()

    # The legacy directory keeps serving in place so its drop-ins stay loaded;
    # extensions/ is not reported (callers would create it, blocking the
    # rename retry on the next resolve).
    assert extensions_dir == legacy_dir
    assert (legacy_dir / "my-extension").is_dir()
    assert not (sculptor_path / "extensions").exists()


def test_get_extensions_directory_resolves_without_creating(tmp_path: Path) -> None:
    sculptor_path = tmp_path / ".sculptor"
    sculptor_path.mkdir()

    with patch("sculptor.utils.build.get_sculptor_folder", return_value=sculptor_path):
        extensions_dir = get_extensions_directory()

    assert extensions_dir == sculptor_path / "extensions"
    assert not extensions_dir.exists()
