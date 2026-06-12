import os
from pathlib import Path
from unittest.mock import patch

from loguru import logger

from sculptor.utils.build import get_sculpt_bin_dir


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

    assert any("sculpt" in str(message).lower() for message in warnings), (
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
