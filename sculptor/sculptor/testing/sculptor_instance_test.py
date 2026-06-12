"""Unit tests for helpers in :mod:`sculptor.testing.sculptor_instance`."""

import errno
import shutil
from pathlib import Path

import pytest

from sculptor.testing import sculptor_instance
from sculptor.testing.sculptor_instance import _rmtree_tolerating_concurrent_deletion
from sculptor.testing.sculptor_instance import _teardown_timeout_seconds


def test_teardown_timeout_default_when_trace_to_absent() -> None:
    """No tracing — the historical 10s budget is enough for a normal shutdown."""
    args = ("python", "-m", "sculptor.cli.main", "--no-open-browser", "--port=12345")
    assert _teardown_timeout_seconds(args) == 10


def test_teardown_timeout_extended_when_trace_to_equals_form() -> None:
    """``--trace-to=<path>`` triggers a viztracer save + JSON merge on shutdown
    that can run for tens of seconds at million-event scale. SIGKILLing at 10s
    would lose the trace file the developer asked for."""
    args = ("python", "-m", "sculptor.cli.main", "--trace-to=/tmp/x.json", "/some/repo")
    assert _teardown_timeout_seconds(args) > 10


def test_teardown_timeout_extended_when_trace_to_space_form() -> None:
    """Same as the equals form — the space form should also extend the timeout."""
    args = ("python", "-m", "sculptor.cli.main", "--trace-to", "/tmp/x.json")
    assert _teardown_timeout_seconds(args) > 10


def test_teardown_timeout_default_when_arg_merely_contains_trace_to_substring() -> None:
    """Pin that a random arg containing the substring 'trace-to' (e.g. a path)
    does NOT trip the extension — only the explicit flag matters."""
    args = ("python", "-m", "sculptor.cli.main", "/some/path/no-trace-to-here")
    assert _teardown_timeout_seconds(args) == 10


def test_rmtree_tolerating_concurrent_deletion_removes_tree(tmp_path: Path) -> None:
    """The happy path still fully removes a populated directory tree."""
    target = tmp_path / "repo"
    (target / ".git" / "worktrees" / "ws").mkdir(parents=True)
    (target / ".git" / "worktrees" / "ws" / "gitdir").write_text("x")
    (target / "file.txt").write_text("y")

    _rmtree_tolerating_concurrent_deletion(target)

    assert not target.exists()


def test_rmtree_tolerating_concurrent_deletion_swallows_already_gone(tmp_path: Path) -> None:
    """A path that has already vanished (the SCU-1374 race) is treated as success.

    This is the failure mode that broke the integration suite: a backgrounded
    workspace teardown pruned ``.git/worktrees/<name>`` while the between-test
    repo wipe was traversing it, so ``shutil.rmtree`` hit ``FileNotFoundError``.
    """
    missing = tmp_path / "never_existed"

    # Must not raise.
    _rmtree_tolerating_concurrent_deletion(missing)


def test_rmtree_tolerating_concurrent_deletion_reraises_other_errors(tmp_path: Path) -> None:
    """Only the concurrent-deletion race is swallowed; real errors still surface.

    Pointing the recursive delete at a regular file raises ``NotADirectoryError``
    (an ``OSError`` that is *not* ``FileNotFoundError``), which must propagate so
    genuine problems are not silently masked the way ``ignore_errors=True`` would.
    """
    a_file = tmp_path / "not_a_dir"
    a_file.write_text("z")

    with pytest.raises(OSError):
        _rmtree_tolerating_concurrent_deletion(a_file)


def test_rmtree_retries_when_directory_repopulated_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory repopulated mid-wipe (``ENOTEMPTY``) is retried, not re-raised.

    This is the second face of the SCU-1374 race: the backgrounded
    ``git worktree remove`` re-creates an entry inside ``.git`` after
    ``shutil.rmtree`` has emptied it, so the final ``os.rmdir`` fails with
    ``ENOTEMPTY``. The teardown is short-lived, so retrying the whole delete
    succeeds once it settles — which is what broke the integration suite when
    only the vanishing (``FileNotFoundError``) case was handled.
    """
    target = tmp_path / "repo"
    (target / ".git").mkdir(parents=True)
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main")

    real_rmtree = shutil.rmtree
    calls = {"count": 0}

    def flaky_rmtree(path: Path, onerror: object = None) -> None:
        # First attempt mimics the concurrent git process repopulating the
        # tree; subsequent attempts (after the "teardown" settles) succeed.
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError(errno.ENOTEMPTY, "Directory not empty", str(path))
        real_rmtree(path, onerror=onerror)

    monkeypatch.setattr(sculptor_instance.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(sculptor_instance, "_RMTREE_RETRY_INTERVAL_SECONDS", 0.0)

    _rmtree_tolerating_concurrent_deletion(target)

    assert calls["count"] == 2
    assert not target.exists()


def test_rmtree_reraises_when_repopulation_outlasts_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the repopulation never stops, the error surfaces once the budget runs out.

    The retry is a bounded safety net, not an infinite loop: a persistent
    ``ENOTEMPTY`` (a genuine bug rather than the transient teardown race) must
    still propagate so it is not silently swallowed.
    """
    target = tmp_path / "repo"
    (target / ".git").mkdir(parents=True)

    def always_repopulated(path: Path, onerror: object = None) -> None:
        raise OSError(errno.ENOTEMPTY, "Directory not empty", str(path))

    monkeypatch.setattr(sculptor_instance.shutil, "rmtree", always_repopulated)
    monkeypatch.setattr(sculptor_instance, "_RMTREE_RETRY_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(sculptor_instance, "_RMTREE_RETRY_BUDGET_SECONDS", 0.05)

    with pytest.raises(OSError) as excinfo:
        _rmtree_tolerating_concurrent_deletion(target)
    assert excinfo.value.errno == errno.ENOTEMPTY
