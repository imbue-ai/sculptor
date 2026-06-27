"""Tests for ``run_git_command_local`` — in particular that it routes git through
``os.posix_spawn`` (SCU-1624) by resolving an absolute git, folding ``cwd`` into
``git -C``, and opting into ``prefer_posix_spawn``.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.services.git_repo_service import git_commands
from sculptor.services.git_repo_service.git_commands import run_git_command_local
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.services.git_repo_service.git_errors import RetriableGitCommandFailure


def _captured_call(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch run_process_to_completion to capture how git is dispatched."""
    captured: dict[str, Any] = {}

    def fake_run_process_to_completion(self: ConcurrencyGroup, **kwargs: Any) -> FinishedProcess:
        captured.update(kwargs)
        return FinishedProcess(
            command=tuple(kwargs["command"]),
            returncode=0,
            stdout="ok",
            stderr="",
            is_timed_out=False,
            is_output_already_logged=False,
        )

    monkeypatch.setattr(ConcurrencyGroup, "run_process_to_completion", fake_run_process_to_completion)
    return captured


def test_git_command_with_cwd_uses_posix_spawn_and_dash_c(
    monkeypatch: pytest.MonkeyPatch, test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    captured = _captured_call(monkeypatch)

    run_git_command_local(test_root_concurrency_group, ["git", "rev-parse", "HEAD"], cwd=tmp_path)

    argv = list(captured["command"])
    # Absolute git executable so posix_spawn (which does not search PATH) can exec it.
    assert os.path.isabs(argv[0]) and argv[0].endswith("/git")
    # cwd folded into `git -C <dir>` so we can pass cwd=None and stay on posix_spawn.
    assert argv[1:4] == ["-C", str(tmp_path), "rev-parse"]
    assert captured["cwd"] is None
    assert captured["prefer_posix_spawn"] is True


def test_git_command_without_cwd_still_uses_posix_spawn(
    monkeypatch: pytest.MonkeyPatch, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    captured = _captured_call(monkeypatch)

    run_git_command_local(test_root_concurrency_group, ["git", "--version"], cwd=None)

    argv = list(captured["command"])
    assert os.path.isabs(argv[0]) and argv[0].endswith("/git")
    assert argv[1] == "--version"  # no -C inserted when there is no cwd
    assert captured["cwd"] is None
    assert captured["prefer_posix_spawn"] is True


def test_non_git_command_keeps_popen_path(
    monkeypatch: pytest.MonkeyPatch, test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    # Defensive: a command that is not git keeps the original cwd + Popen behavior.
    captured = _captured_call(monkeypatch)

    run_git_command_local(test_root_concurrency_group, ["not-git", "status"], cwd=tmp_path)

    assert list(captured["command"]) == ["not-git", "status"]
    assert captured["cwd"] == tmp_path
    assert captured["prefer_posix_spawn"] is False


def test_missing_cwd_fails_fast_and_non_retriable(
    monkeypatch: pytest.MonkeyPatch, test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    """A missing/moved repo directory must fail immediately and non-retriably.

    With cwd folded into ``git -C <dir>``, an absent directory would otherwise make
    git exit non-zero — which the retry path treats as transient and retries 3x with
    backoff. We preserve the old subprocess.Popen(cwd=...) contract: raise a plain
    ``GitCommandFailure`` (NOT ``RetriableGitCommandFailure``) before ever spawning.
    """
    captured = _captured_call(monkeypatch)  # records kwargs iff git is actually spawned
    missing = tmp_path / "moved-away"

    with pytest.raises(GitCommandFailure) as exc_info:
        run_git_command_local(test_root_concurrency_group, ["git", "status", "--porcelain"], cwd=missing)

    # Must be the non-retriable base type, so @git_retry does not retry a vanished repo.
    assert not isinstance(exc_info.value, RetriableGitCommandFailure)
    # And we never spawned (no non-zero-exit-then-retry path was taken).
    assert captured == {}, "missing cwd must fail before spawning git"


def test_non_directory_cwd_also_fails_fast(
    monkeypatch: pytest.MonkeyPatch, test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    # A cwd that exists but is a file (not a directory) is equally unusable; Popen
    # raised NotADirectoryError here, so we keep the same fast non-retriable failure.
    captured = _captured_call(monkeypatch)
    a_file = tmp_path / "not-a-dir"
    a_file.write_text("")

    with pytest.raises(GitCommandFailure) as exc_info:
        run_git_command_local(test_root_concurrency_group, ["git", "status"], cwd=a_file)

    assert not isinstance(exc_info.value, RetriableGitCommandFailure)
    assert captured == {}


def test_git_executable_is_absolute() -> None:
    git_path = git_commands._git_executable()
    assert os.path.isabs(git_path) and os.access(git_path, os.X_OK)
