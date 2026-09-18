"""Unit tests for the ``os.posix_spawn``-backed local process primitive.

These prove the handle behaves like ``subprocess.Popen`` for the surface the
backend spawn machinery uses, so it can be dropped in without touching the
delicate ``run_local_command_modern_version`` loop semantics.
"""

import os
import signal
import subprocess
from pathlib import Path

import pytest

from sculptor.foundation.processes.posix_spawn_process import EXIT_CODE_REAPED_ELSEWHERE
from sculptor.foundation.processes.posix_spawn_process import LocalProcessHandle
from sculptor.foundation.processes.posix_spawn_process import PosixSpawnedProcess
from sculptor.foundation.processes.posix_spawn_process import spawn_via_posix_spawn


def _read_all(process: PosixSpawnedProcess) -> tuple[bytes, bytes]:
    assert process.stdout is not None and process.stderr is not None
    out = process.stdout.read()
    err = process.stderr.read()
    return out, err


def test_captures_stdout_and_zero_exit() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "printf hello"])
    assert process.wait(timeout=10) == 0
    out, err = _read_all(process)
    assert out == b"hello"
    assert err == b""
    assert process.returncode == 0


def test_captures_stderr_and_nonzero_exit() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "printf oops 1>&2; exit 3"])
    assert process.wait(timeout=10) == 3
    out, err = _read_all(process)
    assert out == b""
    assert err == b"oops"
    assert process.returncode == 3


def test_resolves_relative_executable_via_path() -> None:
    # "sh" is relative; the primitive must resolve it on PATH (posix_spawn does not).
    process = spawn_via_posix_spawn(["sh", "-c", "exit 0"])
    assert process.wait(timeout=10) == 0


def test_missing_executable_raises_oserror() -> None:
    # Matches subprocess.Popen, whose OSError the caller maps to ProcessSetupError.
    with pytest.raises(OSError):
        spawn_via_posix_spawn(["this-command-does-not-exist-xyzzy"])


def test_empty_command_raises_value_error() -> None:
    # ValueError (not IndexError) so the caller's (OSError, ValueError) handler
    # maps it to ProcessSetupError, like subprocess.Popen([]).
    with pytest.raises(ValueError):
        spawn_via_posix_spawn([])


def test_relative_executable_resolved_against_env_path(tmp_path: Path) -> None:
    # A relative exe must resolve against the caller-provided PATH (matching
    # subprocess.Popen(env=...)), not the parent process's PATH.
    helper = tmp_path / "sctest-helper"
    helper.write_text("#!/bin/sh\nprintf from-env-path\n")
    helper.chmod(0o755)
    process = spawn_via_posix_spawn(["sctest-helper"], env={"PATH": str(tmp_path)})
    assert process.wait(timeout=10) == 0
    out, _err = _read_all(process)
    assert out == b"from-env-path"


def test_env_is_passed_through() -> None:
    process = spawn_via_posix_spawn(
        ["sh", "-c", 'printf %s "$SCTEST_VAR"'], env={"SCTEST_VAR": "from-env", "PATH": os.environ["PATH"]}
    )
    assert process.wait(timeout=10) == 0
    out, _err = _read_all(process)
    assert out == b"from-env"


def test_stdin_pipe_round_trips() -> None:
    process = spawn_via_posix_spawn(["cat"], stdin_mode=subprocess.PIPE)
    assert process.stdin is not None
    process.stdin.write(b"piped-input")
    process.stdin.close()
    assert process.wait(timeout=10) == 0
    out, _err = _read_all(process)
    assert out == b"piped-input"


def test_poll_returns_none_then_exit_code() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "sleep 0.3; exit 7"])
    assert process.poll() is None  # still running
    assert process.wait(timeout=10) == 7
    assert process.poll() == 7  # idempotent after reaping


def test_poll_returns_sentinel_when_child_reaped_elsewhere() -> None:
    # If something else reaps the child first, our waitpid raises ECHILD. poll()
    # must then report a non-None sentinel rather than looping on None forever.
    process = spawn_via_posix_spawn(["sh", "-c", "exit 0"])
    os.waitpid(process.pid, 0)  # steal the child's exit status out from under it
    assert process.poll() == EXIT_CODE_REAPED_ELSEWHERE
    assert process.returncode == EXIT_CODE_REAPED_ELSEWHERE


def test_wait_returns_sentinel_when_child_reaped_elsewhere() -> None:
    # Same race via wait(): it must return the sentinel, not assert on a None
    # returncode (the default timeout=None path used to do exactly that).
    process = spawn_via_posix_spawn(["sh", "-c", "exit 0"])
    os.waitpid(process.pid, 0)
    assert process.wait() == EXIT_CODE_REAPED_ELSEWHERE
    assert process.wait(timeout=10) == EXIT_CODE_REAPED_ELSEWHERE  # idempotent


def test_wait_times_out_then_kill() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "sleep 30"])
    with pytest.raises(subprocess.TimeoutExpired):
        process.wait(timeout=0.2)
    process.kill()
    # SIGKILL → negative returncode, like subprocess.Popen.
    assert process.wait(timeout=10) == -signal.SIGKILL


def test_terminate_delivers_sigterm() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "sleep 30"])
    process.terminate()
    assert process.wait(timeout=10) == -signal.SIGTERM


def test_satisfies_local_process_handle_protocol() -> None:
    process = spawn_via_posix_spawn(["sh", "-c", "exit 0"])
    assert isinstance(process, LocalProcessHandle)
    process.wait(timeout=10)
    # subprocess.Popen must satisfy the same protocol (so callers accept either).
    popen = subprocess.Popen(["sh", "-c", "exit 0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert isinstance(popen, LocalProcessHandle)
    finally:
        popen.wait(timeout=10)
