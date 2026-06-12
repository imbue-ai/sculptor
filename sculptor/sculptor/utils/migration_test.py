from pathlib import Path
from unittest.mock import patch

import pytest

from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.migration import ensure_sculptor_folder_ready


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
