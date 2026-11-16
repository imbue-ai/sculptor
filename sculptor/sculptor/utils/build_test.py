import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG
from sculptor.utils.build import get_internal_folder
from sculptor.utils.build import get_jj_bin_dir
from sculptor.utils.build import get_sculpt_bin_dir
from sculptor.utils.build import get_sculptor_folder


@pytest.fixture
def isolated_sculptor_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    sculptor_folder = tmp_path / "sculptor"
    monkeypatch.setenv(SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG, str(sculptor_folder))
    get_sculptor_folder.cache_clear()
    yield sculptor_folder
    get_sculptor_folder.cache_clear()


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_get_sculpt_bin_dir_does_not_create_dangling_symlink_when_target_missing(tmp_path: Path) -> None:
    """In dev mode, if the source ``sculpt`` target is missing, no symlink should be created.

    Regression test for SCU-1360: a dangling symlink in ``sculpt-bin/`` is silently
    skipped by PATH lookup, so ``sculpt`` falls through to the stale packaged binary
    with no signal. The directory must not contain a broken symlink.
    """
    internal = tmp_path / "internal"
    executable_parent = tmp_path / "venv-bin"
    executable_parent.mkdir()
    # NOTE: intentionally do NOT create executable_parent / "sculpt" — the target is missing,
    # exactly as in a dev venv where the source sculpt was never installed.

    with patch("sculptor.utils.build.get_internal_folder", return_value=internal):
        result = get_sculpt_bin_dir(executable_parent=executable_parent, packaged=False)

    sculpt_link = result / "sculpt"
    assert not sculpt_link.is_symlink(), "must not create a dangling symlink when the sculpt target is missing"


def test_get_sculpt_bin_dir_removes_stale_dangling_symlink_when_target_disappears(tmp_path: Path) -> None:
    """A previously-valid symlink whose target later disappears must be removed, not left dangling.

    Regression test for SCU-1360: ``uv sync`` can prune the editable ``sculpt`` install,
    leaving the materialized symlink pointing at a now-missing target. The next call must
    clean it up rather than leaving a broken PATH entry.
    """
    internal = tmp_path / "internal"
    executable_parent = tmp_path / "venv-bin"
    executable_parent.mkdir()

    sculpt_bin_dir = internal / "sculpt-bin"
    sculpt_bin_dir.mkdir(parents=True)
    stale_link = sculpt_bin_dir / "sculpt"
    stale_link.symlink_to(executable_parent / "sculpt")  # target does not exist
    assert stale_link.is_symlink() and not stale_link.exists()

    with patch("sculptor.utils.build.get_internal_folder", return_value=internal):
        result = get_sculpt_bin_dir(executable_parent=executable_parent, packaged=False)

    sculpt_link = result / "sculpt"
    assert not sculpt_link.is_symlink(), "must remove a stale dangling symlink when the target disappears"


def test_get_sculpt_bin_dir_warns_loudly_when_target_missing(tmp_path: Path) -> None:
    """When the source ``sculpt`` target is missing, a warning must be emitted.

    Regression test for SCU-1360: the failure mode was silent. The fix must make it
    diagnosable by logging a loud warning instead of quietly falling back.
    """
    internal = tmp_path / "internal"
    executable_parent = tmp_path / "venv-bin"
    executable_parent.mkdir()

    warnings: list[str] = []
    handler_id = logger.add(warnings.append, level="WARNING")
    try:
        with patch("sculptor.utils.build.get_internal_folder", return_value=internal):
            get_sculpt_bin_dir(executable_parent=executable_parent, packaged=False)
    finally:
        logger.remove(handler_id)

    assert any("sculpt" in message.lower() for message in warnings), (
        "must log a loud warning when the sculpt target is missing"
    )


def test_get_sculpt_bin_dir_creates_symlink_when_target_present(tmp_path: Path) -> None:
    """The happy path is unchanged: when the source ``sculpt`` exists, link to it."""
    internal = tmp_path / "internal"
    executable_parent = tmp_path / "venv-bin"
    executable_parent.mkdir()
    target = executable_parent / "sculpt"
    target.write_text("#!/bin/sh\n")

    with patch("sculptor.utils.build.get_internal_folder", return_value=internal):
        result = get_sculpt_bin_dir(executable_parent=executable_parent, packaged=False)

    sculpt_link = result / "sculpt"
    assert sculpt_link.is_symlink()
    assert os.readlink(sculpt_link) == str(target)


def test_jj_bin_dir_holds_only_a_jj_link_to_the_resolved_binary(
    isolated_sculptor_folder: Path, tmp_path: Path
) -> None:
    jj_binary = _make_executable(tmp_path / "managed" / "jj")

    jj_bin_dir = get_jj_bin_dir(jj_binary)

    assert jj_bin_dir == get_internal_folder() / "jj-bin"
    assert [entry.name for entry in jj_bin_dir.iterdir()] == ["jj"]
    assert (jj_bin_dir / "jj").readlink() == jj_binary


def test_jj_bin_dir_relinks_jj_when_the_resolved_binary_changes(
    isolated_sculptor_folder: Path, tmp_path: Path
) -> None:
    get_jj_bin_dir(_make_executable(tmp_path / "old" / "jj"))
    new_binary = _make_executable(tmp_path / "new" / "jj")

    jj_bin_dir = get_jj_bin_dir(new_binary)

    assert [entry.name for entry in jj_bin_dir.iterdir()] == ["jj"]
    assert (jj_bin_dir / "jj").readlink() == new_binary


def test_jj_bin_dir_drops_the_jj_link_when_jj_is_unresolvable(isolated_sculptor_folder: Path, tmp_path: Path) -> None:
    get_jj_bin_dir(_make_executable(tmp_path / "managed" / "jj"))

    jj_bin_dir = get_jj_bin_dir(None)

    assert jj_bin_dir.is_dir()
    assert list(jj_bin_dir.iterdir()) == []
