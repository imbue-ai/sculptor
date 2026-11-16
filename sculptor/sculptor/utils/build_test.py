import os
from pathlib import Path
from unittest.mock import patch

from loguru import logger

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.sculptor_folder import isolated_sculptor_folder  # noqa: F401
from sculptor.utils.build import _get_repo_root
from sculptor.utils.build import get_internal_folder
from sculptor.utils.build import get_jj_bin_dir
from sculptor.utils.build import get_sculpt_bin_dir


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
    isolated_sculptor_folder: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    jj_binary = _make_executable(tmp_path / "managed" / "jj")

    jj_bin_dir = get_jj_bin_dir(jj_binary)

    assert jj_bin_dir == get_internal_folder() / "jj-bin"
    assert [entry.name for entry in jj_bin_dir.iterdir()] == ["jj"]
    assert (jj_bin_dir / "jj").readlink() == jj_binary


def test_jj_bin_dir_relinks_jj_when_the_resolved_binary_changes(
    isolated_sculptor_folder: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    get_jj_bin_dir(_make_executable(tmp_path / "old" / "jj"))
    new_binary = _make_executable(tmp_path / "new" / "jj")

    jj_bin_dir = get_jj_bin_dir(new_binary)

    assert [entry.name for entry in jj_bin_dir.iterdir()] == ["jj"]
    assert (jj_bin_dir / "jj").readlink() == new_binary


def test_jj_bin_dir_drops_the_jj_link_when_jj_is_unresolvable(
    isolated_sculptor_folder: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    get_jj_bin_dir(_make_executable(tmp_path / "managed" / "jj"))

    jj_bin_dir = get_jj_bin_dir(None)

    assert jj_bin_dir.is_dir()
    assert list(jj_bin_dir.iterdir()) == []


def test_repo_root_is_the_nearest_git_checkout_above_the_source(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    source_directory = checkout / "sculptor" / "sculptor" / "utils"
    source_directory.mkdir(parents=True)
    run_blocking(["git", "init", "-q"], cwd=checkout)

    assert _get_repo_root(source_directory) == checkout


def test_repo_root_is_a_jj_workspace_nested_in_another_checkout_not_the_checkout_around_it(
    tmp_path: Path, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    enclosing_checkout = tmp_path / "enclosing_checkout"
    enclosing_checkout.mkdir()
    run_blocking(["git", "init", "-q"], cwd=enclosing_checkout)
    jj_workspace = enclosing_checkout / ".dev_sculptor" / "workspaces" / "ws" / "code"
    jj_workspace.parent.mkdir(parents=True)
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", "ws", "-r", "main@origin", str(jj_workspace)),
        cwd=jj_colocated_repo.path,
    )
    source_directory = jj_workspace / "sculptor" / "sculptor" / "utils"
    source_directory.mkdir(parents=True)

    assert _get_repo_root(source_directory) == jj_workspace
