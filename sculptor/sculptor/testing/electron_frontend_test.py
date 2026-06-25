"""Unit tests for the Electron launch helpers in :mod:`sculptor.testing.electron_frontend`."""

from collections import deque
from collections.abc import Sequence
from pathlib import Path

import pytest
from filelock import FileLock

from sculptor.testing.electron_frontend import ElectronFrontend
from sculptor.testing.electron_frontend import _MAX_ELECTRON_LAUNCH_ATTEMPTS
from sculptor.testing.electron_frontend import _TransientElectronStartError
from sculptor.testing.electron_frontend import _is_transient_electron_start_crash

_READY_OUTPUT = ["Logging to temp file: /tmp/sculptor.log"]

# Real "Last Electron output" tails captured from the offload electron lane when
# esbuild's Go binary crashed during dev-bundle startup — one in a plugin onLoad
# callback, one in the linker.
_ESBUILD_ONLOAD_CRASH_TAIL = """\
github.com/evanw/esbuild/pkg/api.(*pluginImpl).onLoad.func1({{0x0, 0x0}, {{0xc00012fdb0, 0x4f...
	github.com/evanw/esbuild/internal/bundler/bundler.go:1193 +0xcf5
github.com/evanw/esbuild/internal/bundler.parseFile(...)
	github.com/evanw/esbuild/internal/bundler/bundler.go:163 +0x2b5
created by github.com/evanw/esbuild/internal/bundler.(*scanner).maybeParseFile in goroutine 386
main.(*serviceType).sendRequest(0xc000182390, {0x9973a0, 0xc0034a9020})
	github.com/evanw/esbuild/cmd/esbuild/service.go:192 +0x12b"""

_ESBUILD_LINKER_CRASH_TAIL = """\
	runtime/malloc.go:1349 +0x54 fp=0xc0003c76d0 sp=0xc0003c76a8 pc=0x40d554
runtime.mallocgc(0x20, 0x9e9800, 0x1)
runtime.newobject(0x9e9800?)
github.com/evanw/esbuild/internal/linker.(*linkerContext).createExportsForFile(0xc0005e2420, 0x1916b0?)
	github.com/evanw/esbuild/internal/linker/linker.go:2311 +0x691
created by github.com/evanw/esbuild/internal/linker.(*linkerContext).scanImportsAndExports in goroutine 159"""

# A non-esbuild start failure (the renderer port was already taken), which must not
# be mistaken for a transient bundler crash.
_PORT_IN_USE_TAIL = """\
Proxying frontend: target=http://127.0.0.1:5050 SCULPTOR_FRONTEND_PORT=5173
error when starting dev server:
Error: Port 5173 is already in use
    at Server.onError (node_modules/vite/dist/node/chunks/dep.js:78010:28)"""


def test_is_transient_electron_start_crash_detects_esbuild_onload_panic() -> None:
    """The esbuild onLoad/bundler crash variant is recognised as transient."""
    assert _is_transient_electron_start_crash(_ESBUILD_ONLOAD_CRASH_TAIL)


def test_is_transient_electron_start_crash_detects_esbuild_linker_panic() -> None:
    """The esbuild linker crash variant is recognised as transient."""
    assert _is_transient_electron_start_crash(_ESBUILD_LINKER_CRASH_TAIL)


def test_is_transient_electron_start_crash_ignores_unrelated_failure() -> None:
    """A non-esbuild start failure is not mistaken for the transient bundler crash."""
    assert not _is_transient_electron_start_crash(_PORT_IN_USE_TAIL)


def test_is_transient_electron_start_crash_ignores_empty_output() -> None:
    """No captured output is not a transient esbuild crash."""
    assert not _is_transient_electron_start_crash("")


class _FakeElectronProcess:
    """Stand-in for a dead forge process; the launch path only reads its exit code."""

    def poll(self) -> int:
        return 1


class _ScriptedElectronFrontend(ElectronFrontend):
    """Drives ``_launch_electron_with_retries`` with scripted per-attempt outcomes — no real Electron."""

    def __init__(self, attempts: Sequence[tuple[bool, Sequence[str]]]) -> None:
        self._scripted_attempts = list(attempts)
        self.start_call_count = 0
        self.kill_call_count = 0
        self._electron_proc = _FakeElectronProcess()  # type: ignore[assignment]
        self._forwarder = None

    def _start_electron_process(
        self,
        cmd: tuple[str, ...],
        full_env: dict[str, str],
        frontend_dir: Path,
        file_lock: FileLock,
    ) -> tuple[bool, deque[str]]:
        is_launched, lines = self._scripted_attempts[self.start_call_count]
        self.start_call_count += 1
        return is_launched, deque(lines)

    def _kill_electron(self) -> None:
        self.kill_call_count += 1


def test_launch_retries_after_transient_esbuild_crash_then_succeeds(tmp_path: Path) -> None:
    """A transient esbuild crash on the first attempt is relaunched, and the retry succeeds."""
    frontend = _ScriptedElectronFrontend(
        [
            (False, _ESBUILD_ONLOAD_CRASH_TAIL.splitlines()),
            (True, _READY_OUTPUT),
        ]
    )
    file_lock = FileLock(str(tmp_path / "forge.lock"))

    output = frontend._launch_electron_with_retries((), {}, tmp_path, file_lock)

    assert frontend.start_call_count == 2
    assert frontend.kill_call_count == 1
    assert list(output) == _READY_OUTPUT


def test_launch_raises_on_non_transient_failure_without_retrying(tmp_path: Path) -> None:
    """A non-transient start failure raises immediately and is never relaunched."""
    frontend = _ScriptedElectronFrontend(
        [
            (False, _PORT_IN_USE_TAIL.splitlines()),
            (True, _READY_OUTPUT),
        ]
    )
    file_lock = FileLock(str(tmp_path / "forge.lock"))

    with pytest.raises(RuntimeError) as exc_info:
        frontend._launch_electron_with_retries((), {}, tmp_path, file_lock)

    assert not isinstance(exc_info.value, _TransientElectronStartError)
    assert frontend.start_call_count == 1


def test_launch_gives_up_after_max_attempts_of_transient_crashes(tmp_path: Path) -> None:
    """Persistent transient crashes are retried up to the cap, then surface the error."""
    frontend = _ScriptedElectronFrontend([(False, _ESBUILD_LINKER_CRASH_TAIL.splitlines())] * 5)
    file_lock = FileLock(str(tmp_path / "forge.lock"))

    with pytest.raises(_TransientElectronStartError, match="Electron frontend failed to start"):
        frontend._launch_electron_with_retries((), {}, tmp_path, file_lock)

    assert frontend.start_call_count == _MAX_ELECTRON_LAUNCH_ATTEMPTS
    assert frontend.kill_call_count == _MAX_ELECTRON_LAUNCH_ATTEMPTS
