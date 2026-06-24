import functools
import hashlib
import os
import re
import shutil
import signal
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from subprocess import TimeoutExpired
from typing import Any
from typing import assert_never

import httpx
from loguru import logger
from packaging.version import InvalidVersion
from packaging.version import Version
from pydantic import PrivateAttr

from sculptor.foundation.concurrency_group import InvalidConcurrencyGroupStateError
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.processes.local_process import run_background
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.service import Service
from sculptor.services.managed_tools import CLAUDE_VERSION_RANGE
from sculptor.services.managed_tools import ManagedTool
from sculptor.services.managed_tools import ResolvedDistribution
from sculptor.services.managed_tools import VersionRange
from sculptor.services.managed_tools import get_managed_tool
from sculptor.services.managed_tools import get_managed_tools
from sculptor.services.pi_version import PI_PINNED_VERSION
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.utils.build import get_internal_folder
from sculptor.web.data_types import AuthResult
from sculptor.web.data_types import AuthStartResult
from sculptor.web.data_types import BinaryMode
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import DependencyInfo
from sculptor.web.data_types import InstallProgress
from sculptor.web.data_types import VersionRangeInfo


class InstallResult(FrozenModel):
    success: bool
    in_progress: bool = False
    version: str | None = None
    path: str | None = None
    error: str | None = None


class DependencyCheckResult(FrozenModel):
    installed: bool
    path: str | None = None
    version: str | None = None


# Pinned-single-version range — Sculptor refuses to talk to a pi outside this pin
# so the RPC schema stays known. The version string lives in the dependency-free
# ``pi_version`` module so ``fake_pi`` can report it without importing this heavy
# module (see pi_version.py / SCU-1568).
PI_VERSION_RANGE = VersionRange(
    min_version=PI_PINNED_VERSION,
    max_version=PI_PINNED_VERSION,
    recommended_version=PI_PINNED_VERSION,
)

DEPENDENCIES_DIR_NAME = "dependencies"
_VERSION_DIR_PREFIX = "version-"
_TEMP_DIR_PREFIX = "tmp-"
_DOWNLOAD_CHUNK_SIZE_BYTES = 65536
# Versions to keep when a tool has no ManagedTool conformer to override it.
_DEFAULT_RETENTION_KEEP = 2


def _is_valid_custom_binary(value: str) -> bool:
    """Validate a custom binary value is either an absolute path or a bare command name."""
    if not value:
        return False
    if value.startswith("/"):
        return True
    # Bare command name: single word, no slashes or spaces
    return " " not in value and "/" not in value


def _parse_dependency_config(value: str) -> tuple[BinaryMode, str | None]:
    """Parse a ``dependency_paths`` field into a binary mode and optional custom path.

    Tool-agnostic — claude and pi share the exact same grammar: ``"MANAGED"`` and
    ``"CUSTOM"`` are mode keywords; any other value is a custom binary path (an
    absolute path or a bare command name resolved via PATH). There is deliberately no
    migration validator (REQ-MODE-4), so a persisted bare default such as the old pi
    ``"pi"`` parses as CUSTOM with that path — resolved via PATH, exactly as before a
    field's default flipped to MANAGED. A field default may also be overridden via its
    ``SCULPTOR_*_BINARY_DEFAULT_OVERRIDE`` env var on ``DependencyPaths``; an explicit
    value saved in Settings is persisted and takes precedence over that env var.
    """
    if value == "MANAGED":
        return BinaryMode.MANAGED, None
    if value == "CUSTOM":
        return BinaryMode.CUSTOM, None
    return BinaryMode.CUSTOM, value


def _parse_git_version(stdout: str) -> str | None:
    """Extract version from 'git version 2.44.0' output."""
    match = re.search(r"git version (\S+)", stdout)
    return match.group(1) if match else None


def parse_pi_version(stdout: str) -> str | None:
    """Extract version from pi CLI --version output."""
    match = re.search(r"(\d+\.\d+\.\d+\S*)", stdout)
    return match.group(1) if match else None


def _parse_version_for_tool(tool: Dependency, stdout: str) -> str | None:
    """Dispatch to the per-tool version parser.

    CLAUDE/PI route through their ``ManagedTool`` seam (one shared semver parse); GIT
    has no conformer and keeps its own ``git version`` parser.
    """
    managed_tool = get_managed_tool(tool)
    if managed_tool is not None:
        return managed_tool.parse_version(stdout)
    match tool:
        case Dependency.GIT:
            return _parse_git_version(stdout)
        case Dependency():
            raise ValueError(f"Unhandled dependency: {tool}")
        case _ as unreachable:
            assert_never(unreachable)


def _version_range_for_tool(tool: Dependency) -> "VersionRange | None":
    """Return the supported version range for a tool, or None when unbounded.

    Sourced from the tool's ``ManagedTool`` (Claude/pi each carry their own range,
    mirroring ``_retention_keep_for_tool``); an unmanaged tool (GIT) has no conformer
    and no bounded range.
    """
    managed_tool = get_managed_tool(tool)
    if managed_tool is not None:
        return managed_tool.version_range
    return None


def _get_tool_dir(tool: Dependency) -> Path:
    return get_internal_folder() / DEPENDENCIES_DIR_NAME / tool.value.lower()


def _managed_binary_subpath(tool: Dependency) -> str:
    """Relative location of a managed tool's executable inside its version dir.

    Sourced from the tool's ``ManagedTool`` static ``binary_subpath`` (pi → ``pi/pi``,
    Claude → ``claude``), so this offline read path stays put without resolving a
    (possibly network-bound) distribution. Only managed tools reach this path; an
    unmanaged tool falls back to its bare name, mirroring ``_retention_keep_for_tool``.
    """
    managed_tool = get_managed_tool(tool)
    if managed_tool is not None:
        return managed_tool.binary_subpath
    return tool.value.lower()


def _retention_keep_for_tool(tool: Dependency) -> int:
    """Number of installed versions to keep for a managed tool.

    Sourced from the tool's ``ManagedTool`` (Claude → 2, pi → 1). The default of 2
    only applies to a tool with no conformer, which has no installed versions to
    prune anyway.
    """
    managed_tool = get_managed_tool(tool)
    if managed_tool is not None:
        return managed_tool.retention_keep
    return _DEFAULT_RETENTION_KEEP


def _is_version_dir(name: str) -> bool:
    """Check if a directory name is a prefixed version directory (e.g. 'version-2.1.81')."""
    if not name.startswith(_VERSION_DIR_PREFIX):
        return False
    try:
        Version(name[len(_VERSION_DIR_PREFIX) :])
        return True
    except InvalidVersion:
        return False


def _version_from_dir_name(name: str) -> Version:
    """Extract the Version from a prefixed directory name."""
    return Version(name[len(_VERSION_DIR_PREFIX) :])


# Regex for the sign-in URL the CLI prints to stdout/stderr.
_AUTH_URL_RE = re.compile(r"(https://\S+)")
# How long to wait for the CLI to emit its sign-in URL before giving up on start.
_AUTH_URL_WAIT_SECONDS = 30.0
# Overall cap on the spawned 'auth login' process (it idles waiting on stdin).
_AUTH_PROCESS_TIMEOUT_SECONDS = 600.0
# How long to wait for the CLI to finish after the user submits their code.
_AUTH_COMPLETE_WAIT_SECONDS = 120.0


def _await_auth_url(process: RunningProcess) -> str | None:
    """Poll a still-running ``auth login`` process for the first sign-in URL it prints.

    Returns the URL only while the process is still running and waiting for a
    pasted code. Returns ``None`` if the process has already exited (a
    self-completing local browser-loopback login, or an early failure — either
    way there is no code to paste, so the URL is moot) or if no URL appears
    within ``_AUTH_URL_WAIT_SECONDS``.

    The caller must NOT hold ``_claude_auth_lock`` here: this blocks for up to
    ``_AUTH_URL_WAIT_SECONDS`` on a misbehaving CLI.
    """
    deadline = time.monotonic() + _AUTH_URL_WAIT_SECONDS
    while True:
        if process.is_finished():
            return None
        match = _AUTH_URL_RE.search(process.read_stdout() + process.read_stderr())
        if match:
            return match.group(1)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


def _terminate_process(process: RunningProcess) -> None:
    """Best-effort terminate a process; a no-op if it already finished.

    Bounded (a few seconds at most), so it is safe to call under a lock.
    """
    if process.is_finished():
        return
    try:
        process.terminate(force_kill_seconds=2.0)
    except Exception:
        try:
            process.kill_now(signal.SIGKILL)
        except Exception:
            pass


def _auth_error_text(process: RunningProcess, fallback: str = "Authentication failed") -> str:
    """Best-effort human-readable error text from a finished auth process."""
    return (process.read_stderr() or process.read_stdout() or fallback).strip()


class DependencyManagementService(Service):
    # Serializes the download+verify+stage operation. Held by the background
    # download thread for the entire duration of _download_verify_stage.
    _install_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _claude_auth_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    # The live 'auth login' process between start_auth_login() and
    # submit_auth_code(), kept alive (idling on stdin) so the user's pasted code
    # can be written to it. Only the brief reads and swaps of this field hold
    # _claude_auth_lock — never the blocking subprocess waits.
    _claude_auth_session: RunningProcess | None = PrivateAttr(default=None)
    # Guards _install_progress, _installing, _install_error, and
    # _progress_notifier_thread.
    # Acquired briefly, never held during I/O.
    # Lock ordering (strict): _install_lock → _progress_lock (never reversed).
    _progress_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    # Per-tool install state, keyed by Dependency, so a Claude install and a pi
    # install track independently and never clobber each other. Absence of a key
    # means that tool has no in-flight progress / no recorded error.
    _install_progress: dict[Dependency, InstallProgress] = PrivateAttr(default_factory=dict)
    _installing: dict[Dependency, bool] = PrivateAttr(default_factory=dict)
    # Reason each tool's most recent managed install failed, if any. Guarded by
    # _progress_lock alongside _install_progress/_installing.
    _install_error: dict[Dependency, str] = PrivateAttr(default_factory=dict)
    # Pushes status to observers while any install is in flight, so the download
    # thread never computes status itself. Guarded by _progress_lock.
    _progress_notifier_thread: ObservableThread | None = PrivateAttr(default=None)
    _observer_queues: set[Queue[Any]] = PrivateAttr(default_factory=set)
    # Cooperative cancellation: set by stop() so the background install thread
    # can wrap up at the next chunk boundary instead of being interrupted by
    # the concurrency group's EXITING state.
    _stop_requested: threading.Event = PrivateAttr(default_factory=threading.Event)
    # Per-tool reference to the in-flight install thread so stop() can wait for
    # each one's finally block to complete before the concurrency group exits.
    _install_thread: dict[Dependency, ObservableThread] = PrivateAttr(default_factory=dict)

    def start(self) -> None:
        self._cleanup_stale_state()
        self._auto_install_if_needed()

    def stop(self) -> None:
        """Signal any in-flight install to wrap up before the concurrency group exits.

        ``Service.run()`` calls ``stop()`` while the concurrency group is still
        ACTIVE. We set the cancellation event so the download loop returns at the
        next chunk boundary (and the progress notifier wakes from its wait), then
        wait for each thread to finish — including the download thread's
        ``finally`` block — so the group's ``__exit__`` doesn't race with that
        cleanup. Bounded by a timeout so a stuck install can't block shutdown.
        """
        self._stop_requested.set()
        threads = list(self._install_thread.values())
        with self._progress_lock:
            if self._progress_notifier_thread is not None:
                threads.append(self._progress_notifier_thread)
        for thread in threads:
            if not thread.is_alive():
                continue
            try:
                thread.join(timeout=4.0)
            except Exception:
                logger.opt(exception=True).debug("Thread {} raised during shutdown join", thread.name)
            if thread.is_alive():
                logger.warning("Thread {} did not stop within timeout during shutdown", thread.name)

        # Tear down any in-flight Claude sign-in so its `auth login` subprocess
        # doesn't outlive the service. Left running it idles on stdin until its
        # process timeout, and its isolated process group shields it from the
        # signals that take down the rest of the app. Bounded acquire so a
        # sign-in that is mid-start can't block shutdown.
        if self._claude_auth_lock.acquire(timeout=4.0):
            try:
                self._terminate_auth_session_locked()
            finally:
                self._claude_auth_lock.release()
        else:
            logger.warning("Could not acquire auth lock during shutdown; sign-in subprocess may linger")

    def _auto_install_if_needed(self) -> None:
        """Auto-install each managed tool whose pinned binary is missing or out of range.

        Loops the ManagedTool registry; for every tool with a MANAGED binary mode that
        is not already installed-and-in-range, it spawns an install. Claude always
        auto-installs when MANAGED. pi additionally requires the ``enable_pi_agent``
        experiment to be on, so a Claude-only user (the default) never auto-downloads pi.
        They can still trigger a manual install from the Pi settings section, which routes
        through ``install_managed`` and is not gated here.
        """
        try:
            config = get_user_config_instance()
        except Exception:
            logger.opt(exception=True).warning("Auto-install check failed")
            return

        # Mode lives in a per-tool config field, so reading it is the one place
        # auto-install still dispatches on the tool (not on the install path).
        managed_mode_tools: list[Dependency] = []
        for tool in get_managed_tools():
            if tool == Dependency.CLAUDE:
                mode, _ = _parse_dependency_config(config.dependency_paths.claude)
            elif tool == Dependency.PI:
                # pi is dark-launched: only auto-provision it for users who opted into
                # the pi-agent experiment. Without this gate every Claude-only user
                # would download the pinned pi build on startup.
                if not config.enable_pi_agent:
                    continue
                mode, _ = _parse_dependency_config(config.dependency_paths.pi)
            else:
                continue
            if mode == BinaryMode.MANAGED:
                managed_mode_tools.append(tool)

        # Probe concurrently so one slow binary's --version timeout doesn't serialize startup.
        checks = self._check_installed_concurrently(managed_mode_tools)

        for tool in managed_mode_tools:
            check = checks.get(tool)
            if check is None:
                continue
            try:
                if check.installed and check.version and self.is_version_in_range(check.version, tool):
                    continue

                self.concurrency_group.start_new_thread(
                    target=self._run_auto_install,
                    args=(tool,),
                    name="dependency-management-auto-install",
                    is_checked=False,
                )
            except Exception:
                logger.opt(exception=True).warning("Auto-install check failed for {}", tool.value)

    def _run_auto_install(self, tool: Dependency) -> None:
        """Background thread target for auto-installing a managed binary.

        ``install_managed`` is fire-and-forget — it returns success once the download
        thread is spawned, not when the binary is on disk. The actual outcome is
        logged by the download thread.
        """
        try:
            logger.info("Starting auto-install of managed {} binary on startup", tool.value)
            result = self.install_managed(tool)
            if not result.success:
                # The background download surfaces its own failure via
                # _install_error; this branch only covers synchronous failures
                # (manifest fetch, unsupported platform) that never start a
                # download thread, so capture them here too.
                logger.warning("Failed to start auto-install of managed {} binary: {}", tool.value, result.error)
                with self._progress_lock:
                    self._install_error[tool] = result.error or "Installation failed"
                self._notify_observers()
        except Exception:
            logger.opt(exception=True).warning("Failed to start auto-install of managed {} binary", tool.value)

    def add_observer_queue(self, queue: Queue[Any]) -> None:
        """Register a stream queue for pushing status updates."""
        self._observer_queues.add(queue)

    def remove_observer_queue(self, queue: Queue[Any]) -> None:
        """Unregister a stream queue."""
        self._observer_queues.discard(queue)

    def _notify_observers(self, status: DependenciesStatus | None = None) -> None:
        """Push status to all registered observer queues.

        If *status* is ``None``, calls ``_get_status()`` to compute it.
        Delta detection is handled by the stream layer (``stream_everything``),
        not here — this method pushes unconditionally.
        """
        if status is None:
            status = self._get_status()
        for queue in self._observer_queues:
            queue.put(status)

    def resolve_binary_path(self, tool: Dependency) -> str | None:
        """Resolve the binary path for a dependency based on the active mode."""
        match tool:
            case Dependency.CLAUDE:
                return self._resolve_claude_path()
            case Dependency.GIT:
                return self._resolve_git_path()
            case Dependency.PI:
                return self._resolve_pi_path()
            case Dependency():
                raise ValueError(f"Unhandled dependency: {tool}")
            case _ as unreachable:
                assert_never(unreachable)

    def _resolve_git_path(self) -> str | None:
        config = get_user_config_instance()
        if config.dependency_paths.git:
            return config.dependency_paths.git
        return shutil.which("git")

    def _resolve_pi_path(self) -> str | None:
        config = get_user_config_instance()
        mode, custom_path = _parse_dependency_config(config.dependency_paths.pi)

        if mode == BinaryMode.MANAGED:
            return self._find_managed_binary(Dependency.PI)

        # CUSTOM: an absolute path or bare command name, resolved via PATH —
        # unchanged from the pre-managed behaviour (a "CUSTOM" keyword or empty
        # value carries no path and resolves to None).
        value = custom_path
        if not value:
            return None
        if not _is_valid_custom_binary(value):
            logger.info("Invalid custom pi binary path: {!r}, ignoring", value)
            return None
        return shutil.which(value)

    def _resolve_claude_path(self) -> str | None:
        config = get_user_config_instance()
        mode, custom_path = _parse_dependency_config(config.dependency_paths.claude)

        match mode:
            case BinaryMode.MANAGED:
                return self._find_managed_binary(Dependency.CLAUDE)
            case BinaryMode.CUSTOM:
                custom_value = custom_path or "claude"
                if not _is_valid_custom_binary(custom_value):
                    logger.info("Invalid custom Claude binary path: {!r}, ignoring", custom_value)
                    return None
                return shutil.which(custom_value)
            case BinaryMode():
                raise ValueError(f"Unhandled claude binary mode: {mode}")
            case _ as unreachable:
                assert_never(unreachable)

    def _find_managed_binary(self, tool: Dependency) -> str | None:
        """Find the managed binary, preferring the tool's recommended version."""
        tool_dir = _get_tool_dir(tool)
        if not tool_dir.is_dir():
            return None

        binary_subpath = _managed_binary_subpath(tool)

        # Prefer the recommended version for this tool (CLAUDE/PI each have their own
        # range; behaviour-identical to the prior CLAUDE_VERSION_RANGE hard-coding).
        version_range = _version_range_for_tool(tool)
        if version_range is not None:
            recommended_dir = tool_dir / f"{_VERSION_DIR_PREFIX}{version_range.recommended_version}"
            recommended_binary = recommended_dir / binary_subpath
            if recommended_binary.is_file():
                return str(recommended_binary)

        # Fall back to the highest installed version
        versions: list[tuple[Version, Path]] = []
        for entry in tool_dir.iterdir():
            if entry.is_dir() and _is_version_dir(entry.name):
                binary_path = entry / binary_subpath
                if binary_path.is_file():
                    versions.append((_version_from_dir_name(entry.name), binary_path))

        if not versions:
            return None

        versions.sort(key=lambda x: x[0], reverse=True)
        return str(versions[0][1])

    def check_installed(self, tool: Dependency) -> DependencyCheckResult:
        """Check whether a dependency is installed and get its version."""
        binary = self.resolve_binary_path(tool)
        if binary is None:
            return DependencyCheckResult(installed=False)

        try:
            result = self.concurrency_group.run_process_to_completion(
                [binary, "--version"],
                timeout=5.0,
            )
            # WHY: real pi emits --version to stderr, not stdout; feed both channels.
            version_text = f"{result.stdout}\n{result.stderr}" if tool == Dependency.PI else result.stdout
            version = _parse_version_for_tool(tool, version_text)
            return DependencyCheckResult(installed=True, path=binary, version=version)
        except ProcessError:
            return DependencyCheckResult(installed=False, path=binary)

    def _check_installed_concurrently(self, tools: Sequence[Dependency]) -> dict[Dependency, DependencyCheckResult]:
        """Probe several tools' installed version concurrently, returning the result per tool.

        Each probe runs a ``<binary> --version`` subprocess with a multi-second timeout,
        so probing tools one at a time would serialize those timeouts. The subprocesses
        stay concurrency-group-managed inside ``check_installed``; a tool whose probe
        raises is omitted (and logged) rather than failing the whole batch.
        """
        if not tools:
            return {}
        with ThreadPoolExecutor(max_workers=len(tools), thread_name_prefix="check-installed") as executor:
            future_by_tool = {tool: executor.submit(self.check_installed, tool) for tool in tools}
        results: dict[Dependency, DependencyCheckResult] = {}
        for tool, future in future_by_tool.items():
            try:
                results[tool] = future.result()
            except Exception:
                logger.opt(exception=True).warning("Failed to check installed version of {}", tool.value)
        return results

    def check_authenticated(self, tool: Dependency) -> bool | None:
        """Check whether a dependency is authenticated.

        Currently only Claude supports authentication checks. Returns None for
        unsupported tools or when the tool is not installed.
        """
        if tool != Dependency.CLAUDE:
            return None
        binary = self.resolve_binary_path(tool)
        if binary is None:
            return None
        try:
            self.concurrency_group.run_process_to_completion(
                [binary, "auth", "status"],
                timeout=10.0,
            )
            return True
        except ProcessError:
            return False

    def start_auth_login(self, tool: Dependency) -> AuthStartResult:
        """Begin interactive authentication for a dependency.

        Spawns ``<binary> auth login`` and reads its output until the sign-in URL
        appears, then returns immediately with that URL — leaving the process
        alive and waiting on stdin. The caller surfaces the URL to the user, who
        signs in and pastes the resulting code back via :meth:`submit_auth_code`.

        On a machine with a usable local browser the CLI completes a
        localhost-loopback login on its own and needs no pasted code; that case
        returns ``success=True`` with ``needs_code=False``.

        Currently only Claude supports authentication. Other tools return an error.
        """
        if tool != Dependency.CLAUDE:
            return AuthStartResult(error=f"Authentication not supported for {tool.value}")
        binary = self.resolve_binary_path(tool)
        if binary is None:
            return AuthStartResult(error=f"{tool.value} CLI not installed")

        # Spawn the new session (abandoning any prior one) under the lock, then
        # release it before the blocking URL wait so a slow CLI can't tie the
        # lock up. The concurrency group owns the process, so it isn't orphaned
        # even though it outlives this call.
        with self._claude_auth_lock:
            self._terminate_auth_session_locked()
            process = self._spawn_auth_process(binary)
            self._claude_auth_session = process

        auth_url = _await_auth_url(process)

        if process.is_finished():
            # A local browser-loopback login self-completed (or failed early):
            # no pasted code is needed.
            success = process.returncode == 0
            with self._claude_auth_lock:
                self._terminate_auth_session_locked(process)
            if success:
                return AuthStartResult(success=True)
            return AuthStartResult(error=_auth_error_text(process))

        if auth_url is None:
            # Still running but never surfaced a sign-in URL within the window.
            with self._claude_auth_lock:
                self._terminate_auth_session_locked(process)
            return AuthStartResult(error="Timed out waiting for the sign-in URL")

        # Running with a URL: leave the process waiting for the pasted code.
        # Best-effort browser open for the local case; a no-op when headless.
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        return AuthStartResult(auth_url=auth_url, needs_code=True)

    def _spawn_auth_process(self, binary: str) -> RunningProcess:
        """Spawn ``<binary> auth login`` as a concurrency-group-tracked process.

        Going through the group means the process is owned and reaped by it, so a
        sign-in left in flight can't be orphaned. ``open_stdin`` keeps the CLI
        waiting for the pasted code.
        """
        return self.concurrency_group.start_background_process_from_factory(
            lambda: run_background(
                [binary, "auth", "login"],
                open_stdin=True,
                timeout=_AUTH_PROCESS_TIMEOUT_SECONDS,
                isolate_process_group=True,
            )
        )

    def submit_auth_code(self, tool: Dependency, code: str) -> AuthResult:
        """Feed the code the user pasted from the sign-in page to the live auth session.

        Writes the code to the waiting ``auth login`` process's stdin and waits
        for it to finish. Returns success when the CLI exits cleanly.
        """
        if tool != Dependency.CLAUDE:
            return AuthResult(success=False, error=f"Authentication not supported for {tool.value}")

        # Claim the session under the lock, then release it before the (bounded
        # but potentially slow) wait so a hung CLI can't keep the lock held.
        with self._claude_auth_lock:
            process = self._claude_auth_session
            if process is None or process.is_finished():
                return AuthResult(success=False, error="No sign-in is in progress. Start sign-in again.")
            self._claude_auth_session = None

        try:
            process.write_stdin(code.strip() + "\n")
            returncode = process.wait(timeout=_AUTH_COMPLETE_WAIT_SECONDS)
            if returncode == 0:
                return AuthResult(success=True)
            return AuthResult(success=False, error=_auth_error_text(process, fallback=f"Exit code {returncode}"))
        except TimeoutExpired:
            return AuthResult(success=False, error="Authentication timed out")
        except Exception as e:
            return AuthResult(success=False, error=str(e))
        finally:
            _terminate_process(process)

    def _terminate_auth_session_locked(self, process: RunningProcess | None = None) -> None:
        """Tear down an auth session and clear the stored handle.

        Must be called while holding ``_claude_auth_lock``. With no argument it
        tears down the currently-stored session; with an explicit process it
        tears that one down and clears the stored handle only if it matches.
        The terminate itself is bounded, so holding the lock across it is fine —
        unlike the sign-in waits, which run unlocked.
        """
        session = process if process is not None else self._claude_auth_session
        if session is not None:
            _terminate_process(session)
        if process is None or process is self._claude_auth_session:
            self._claude_auth_session = None

    def _get_status(self) -> DependenciesStatus:
        """Compute the current status of all dependencies (no side effects)."""
        git_check = self.check_installed(Dependency.GIT)
        claude_check = self.check_installed(Dependency.CLAUDE)
        pi_check = self.check_installed(Dependency.PI)

        config = get_user_config_instance()
        effective_mode, _ = _parse_dependency_config(config.dependency_paths.claude)

        claude_version_range = VersionRangeInfo(
            min_version=CLAUDE_VERSION_RANGE.min_version,
            max_version=CLAUDE_VERSION_RANGE.max_version,
            recommended_version=CLAUDE_VERSION_RANGE.recommended_version,
        )

        claude_in_range = None
        if claude_check.version:
            claude_in_range = self.is_version_in_range(claude_check.version)

        managed_version = self._get_managed_version()

        # Snapshot per-tool install state under the lock; each DependencyInfo
        # below carries its own tool's progress/error.
        with self._progress_lock:
            progress_by_tool = dict(self._install_progress)
            error_by_tool = dict(self._install_error)

        git_info = DependencyInfo(
            installed=git_check.installed,
            path=git_check.path,
            version=git_check.version,
        )

        is_authenticated = self.check_authenticated(Dependency.CLAUDE) if claude_check.installed else None

        claude_info = DependencyInfo(
            installed=claude_check.installed,
            path=claude_check.path,
            version=claude_check.version,
            mode=effective_mode,
            version_range=claude_version_range,
            is_version_in_range=claude_in_range,
            managed_version=managed_version,
            is_authenticated=is_authenticated,
            install_progress=progress_by_tool.get(Dependency.CLAUDE),
            install_error=error_by_tool.get(Dependency.CLAUDE),
        )

        pi_version_range = VersionRangeInfo(
            min_version=PI_VERSION_RANGE.min_version,
            max_version=PI_VERSION_RANGE.max_version,
            recommended_version=PI_VERSION_RANGE.recommended_version,
        )
        pi_mode, _ = _parse_dependency_config(config.dependency_paths.pi)
        pi_in_range = None
        if pi_check.version:
            pi_in_range = self.is_version_in_range(pi_check.version, Dependency.PI)
        pi_info = DependencyInfo(
            installed=pi_check.installed,
            path=pi_check.path,
            version=pi_check.version,
            mode=pi_mode,
            version_range=pi_version_range,
            is_version_in_range=pi_in_range,
            install_progress=progress_by_tool.get(Dependency.PI),
            install_error=error_by_tool.get(Dependency.PI),
        )

        return DependenciesStatus(
            git=git_info,
            claude=claude_info,
            pi=pi_info,
        )

    def get_status(self) -> DependenciesStatus:
        """Get the status of all dependencies and push to observers if changed."""
        status = self._get_status()
        self._notify_observers(status)
        return status

    def _get_managed_version(self, tool: Dependency = Dependency.CLAUDE) -> str | None:
        """Get the highest installed managed version for a tool (defaults to Claude)."""
        tool_dir = _get_tool_dir(tool)
        if not tool_dir.is_dir():
            return None

        versions: list[Version] = []
        for entry in tool_dir.iterdir():
            if entry.is_dir() and _is_version_dir(entry.name):
                versions.append(_version_from_dir_name(entry.name))

        if not versions:
            return None

        versions.sort(reverse=True)
        return str(versions[0])

    def is_version_in_range(self, version: str, tool: Dependency = Dependency.CLAUDE) -> bool:
        """Check whether a version string falls within the supported range and is not blocked."""
        version_range = _version_range_for_tool(tool)
        if version_range is None:
            return True
        try:
            v = Version(version)
            if not (Version(version_range.min_version) <= v <= Version(version_range.max_version)):
                return False
            for blocked in version_range.blocked_versions:
                if Version(blocked.min_version) <= v <= Version(blocked.max_version):
                    return False
            return True
        except InvalidVersion:
            return False

    _PROGRESS_NOTIFY_INTERVAL_SECONDS = 0.5

    def _on_install_progress(self, tool: Dependency, bytes_downloaded: int, total_bytes: int | None) -> None:
        """Record this tool's install progress (download-thread hot path).

        Runs between chunk reads, so it must stay cheap: anything slow here
        (status computation spawns subprocesses) stalls the download. Status
        pushes belong to the progress-notifier thread, never this callback.
        """
        with self._progress_lock:
            self._install_progress[tool] = InstallProgress(
                tool=tool.value,
                bytes_downloaded=bytes_downloaded,
                total_bytes=total_bytes,
            )

    def _ensure_progress_notifier_running(self) -> None:
        """Start the progress-notifier thread unless one is already running.

        Call only after the tool is marked installing, so the notifier cannot
        exit before noticing the new install. One notifier serves all tools.
        """
        with self._progress_lock:
            thread = self._progress_notifier_thread
            if thread is not None and thread.is_alive():
                return
            self._progress_notifier_thread = self.concurrency_group.start_new_thread(
                target=self._run_progress_notifier,
                name="dependency-management-progress-notifier",
                is_checked=False,
            )

    def _run_progress_notifier(self) -> None:
        """Push a fresh status to observers periodically while any install is in flight.

        Keeps status computation, which spawns subprocesses, off the download
        thread (see _on_install_progress).
        """
        has_warned_push_failure = False
        while not self._stop_requested.wait(self._PROGRESS_NOTIFY_INTERVAL_SECONDS):
            with self._progress_lock:
                if not any(self._installing.values()):
                    # Cleared in the same lock hold as the exit decision so
                    # _ensure_progress_notifier_running never races a dying notifier.
                    self._progress_notifier_thread = None
                    return
            try:
                self._notify_observers()
                has_warned_push_failure = False
            except InvalidConcurrencyGroupStateError:
                # The handle stays set; new installs are refused during shutdown.
                logger.debug("Stopping progress notifier: concurrency group is exiting")
                return
            except Exception:
                # Drop the tick but keep the notifier alive: a transient status
                # failure must not freeze progress for the rest of the install.
                # Warn (with traceback) only on the first failure of a streak so
                # a persistently failing push does not spam every interval.
                if has_warned_push_failure:
                    logger.debug("Progress notifier failed to push status (repeat)")
                else:
                    logger.opt(exception=True).warning("Progress notifier failed to push status")
                    has_warned_push_failure = True

    def install_managed(self, tool: Dependency) -> InstallResult:
        """Trigger installation of a managed binary.

        Resolves the tool's distribution synchronously (Claude fetches + validates
        its GCP manifest here; pi reads its static pin), then spawns the background
        download thread; the download, checksum verification, and activation continue
        on that thread. Progress is pushed to observers via _notify_observers() and
        can be polled via get_status(). An unmanaged tool (e.g. git) has no seam entry
        → "not supported".
        """
        managed_tool = get_managed_tool(tool)
        if managed_tool is None:
            return InstallResult(success=False, error=f"Installation not supported for tool: {tool}")
        return self._install_managed_tool(managed_tool)

    def _install_managed_tool(self, managed_tool: ManagedTool) -> InstallResult:
        """Start a background managed install for a ManagedTool via the shared seam.

        Resolves the distribution synchronously (Claude fetches + validates its GCP
        manifest; pi reads its static pin) so resolution failures surface from this
        call. Then seeds initial progress and spawns the tracked download thread,
        which runs ``_download_verify_stage`` on the already-resolved distribution.
        """
        tool = managed_tool.tool

        # Refuse to start new installs once stop() has been called (mirrors Claude).
        if self._stop_requested.is_set():
            return InstallResult(success=False, error="Service is shutting down")

        # If a download for this tool is already in progress, return immediately.
        with self._progress_lock:
            if self._installing.get(tool, False):
                return InstallResult(success=True, in_progress=True)

        # Resolve synchronously so a resolution failure (Claude's manifest fetch, an
        # unsupported platform, a bad pin) is returned to this caller rather than only
        # surfacing async via install_error. ``str(e)`` preserves each tool's native
        # message (e.g. Claude's "Failed to fetch manifest: ...").
        try:
            distribution = managed_tool.resolve_distribution()
        except Exception as e:
            return InstallResult(success=False, error=str(e))

        # Mark as installing (re-check under lock in case another thread raced).
        with self._progress_lock:
            if self._installing.get(tool, False):
                return InstallResult(success=True, in_progress=True)
            self._installing[tool] = True
            # Starting a fresh attempt clears this tool's error from a prior one.
            self._install_error.pop(tool, None)
            # pi's pin carries no size (total_bytes stays None until the stream's
            # content-length lands); Claude's manifest size seeds it up front.
            self._install_progress[tool] = InstallProgress(
                tool=tool.value, bytes_downloaded=0, total_bytes=distribution.size
            )

        self._ensure_progress_notifier_running()

        # Spawn the background download, tracked so stop() can join it cooperatively.
        self._install_thread[tool] = self.concurrency_group.start_new_thread(
            target=self._run_managed_install_download,
            args=(managed_tool, distribution),
            name="dependency-management-install-download",
            is_checked=False,
        )
        self._notify_observers()

        return InstallResult(success=True)

    def _run_managed_install_download(self, managed_tool: ManagedTool, distribution: ResolvedDistribution) -> None:
        """Background thread: drive a ManagedTool install through the shared orchestrator.

        Owns the per-tool bookkeeping (installing flag, progress clear, error
        record/clear, best-effort notify under shutdown) and calls
        ``_download_verify_stage`` with the distribution already resolved by
        ``_install_managed_tool``.
        """
        tool = managed_tool.tool
        error: str | None = None
        try:
            # Serialize with any other install via the shared install lock.
            with self._install_lock:
                result = self._download_verify_stage(
                    managed_tool, functools.partial(self._on_install_progress, tool), distribution
                )
            if result.success:
                logger.info("Background install of {} {} succeeded", tool.value, result.version)
            else:
                error = result.error or "Installation failed"
                logger.info("Background install failed: {}", result.error)
        except Exception as e:
            error = f"Installation failed: {e}"
            logger.opt(exception=True).warning("Background install failed")
        finally:
            with self._progress_lock:
                self._installing[tool] = False
                self._install_progress.pop(tool, None)
                # Record this tool's failure reason (or clear it on success) so the
                # status stream can explain a failed update.
                if error is None:
                    self._install_error.pop(tool, None)
                else:
                    self._install_error[tool] = error
            # A status push here is best-effort. During shutdown the observer queues
            # are being torn down anyway, and _get_status() probes `<tool> --version`
            # as concurrency-group strands that can outlast the group's bounded
            # teardown wait (and would otherwise raise from an already-exiting group).
            # So skip the push once shutdown is requested; the except guards the
            # residual race where the group begins exiting mid-notify.
            if not self._stop_requested.is_set():
                try:
                    self._notify_observers()
                except InvalidConcurrencyGroupStateError:
                    logger.debug("Skipping status notify: concurrency group is exiting")

    def _download_verify_stage(
        self,
        tool: ManagedTool,
        progress_callback: Callable[[int, int | None], None] | None,
        distribution: ResolvedDistribution | None = None,
    ) -> InstallResult:
        """Shared download -> verify -> stage -> activate flow for any ``ManagedTool``.

        Tool-agnostic: it consumes only the ``ManagedTool`` hooks and the normalized
        ``ResolvedDistribution``, so both Claude and pi install through it. The wired
        path passes a *distribution* already resolved by ``_install_managed_tool``;
        when called directly (without one) it resolves the distribution itself.
        """
        dependency = tool.tool
        if distribution is None:
            try:
                distribution = tool.resolve_distribution()
            except Exception as e:
                return InstallResult(success=False, error=f"Failed to resolve distribution: {e}")

        version = distribution.version
        tool_dir = _get_tool_dir(dependency)
        tool_dir.mkdir(parents=True, exist_ok=True)

        # Two temp dirs: one holds the raw download, the other the staged tree that is
        # atomic-renamed into the versioned slot. The staged dir is created by stage().
        download_dir = tool_dir / f"{_TEMP_DIR_PREFIX}{uuid.uuid4()}"
        download_dir.mkdir()
        staging_dir = tool_dir / f"{_TEMP_DIR_PREFIX}{uuid.uuid4()}"

        try:
            # Keep a meaningful on-disk name (the release asset) for the download.
            asset_name = distribution.url.rsplit("/", 1)[-1] or "download"
            downloaded = download_dir / asset_name

            try:
                bytes_downloaded = 0
                # GitHub Releases download URLs 302 to a CDN; follow the redirect to the asset.
                with httpx.stream("GET", distribution.url, timeout=300.0, follow_redirects=True) as stream:
                    stream.raise_for_status()
                    total_bytes = int(stream.headers.get("content-length", 0)) or distribution.size
                    with open(downloaded, "wb") as f:
                        for chunk in stream.iter_bytes(chunk_size=_DOWNLOAD_CHUNK_SIZE_BYTES):
                            if self._stop_requested.is_set():
                                return InstallResult(success=False, error="Install cancelled during shutdown")
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(bytes_downloaded, total_bytes)
            except httpx.HTTPError as e:
                return InstallResult(success=False, error=f"Download failed: {e}")

            # Verify against the pinned checksum BEFORE staging — a mismatch aborts with
            # no activation and (for a tarball) no extraction of untrusted bytes.
            sha256 = hashlib.sha256()
            with open(downloaded, "rb") as f:
                for chunk in iter(lambda: f.read(_DOWNLOAD_CHUNK_SIZE_BYTES), b""):
                    sha256.update(chunk)
            actual_checksum = sha256.hexdigest()
            if actual_checksum != distribution.checksum_sha256:
                return InstallResult(
                    success=False,
                    error=f"Checksum mismatch: expected {distribution.checksum_sha256}, got {actual_checksum}",
                )

            if self._stop_requested.is_set():
                return InstallResult(success=False, error="Install cancelled during shutdown")

            try:
                staged_binary = tool.stage(downloaded, staging_dir)
            except Exception as e:
                return InstallResult(success=False, error=f"Staging failed: {e}")

            # Verify the staged binary runs before activating it.
            try:
                result = self.concurrency_group.run_process_to_completion(
                    [str(staged_binary), "--version"],
                    timeout=10.0,
                )
                # Some managed tools (pi) print --version to stderr; feed both channels.
                parsed_version = tool.parse_version(f"{result.stdout}\n{result.stderr}")
                if not parsed_version:
                    return InstallResult(success=False, error="Binary --version produced no parseable version")
            except ProcessError as e:
                return InstallResult(success=False, error=f"Binary --version check failed: {e}")

            # Activate via atomic rename of the staged tree into the versioned slot.
            final_dir = tool_dir / f"{_VERSION_DIR_PREFIX}{version}"
            if final_dir.exists():
                shutil.rmtree(final_dir)
            os.rename(str(staging_dir), str(final_dir))

            final_binary = final_dir / distribution.binary_subpath
            self.cleanup_old_versions(dependency, keep=tool.retention_keep)

            return InstallResult(success=True, version=version, path=str(final_binary))

        finally:
            # Remove the download dir and any un-activated staging dir. On success the
            # rename consumed staging_dir, so that rmtree only fires on failure paths.
            shutil.rmtree(download_dir, ignore_errors=True)
            shutil.rmtree(staging_dir, ignore_errors=True)

    def cleanup_old_versions(self, tool: Dependency, keep: int = 2) -> None:
        """Remove old versions, keeping the newest `keep` versions."""
        tool_dir = _get_tool_dir(tool)
        if not tool_dir.is_dir():
            return

        # Clean stale temp dirs
        for entry in tool_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(_TEMP_DIR_PREFIX):
                shutil.rmtree(entry, ignore_errors=True)

        # Find and sort version dirs
        version_dirs: list[tuple[Version, Path]] = []
        for entry in tool_dir.iterdir():
            if entry.is_dir() and _is_version_dir(entry.name):
                version_dirs.append((_version_from_dir_name(entry.name), entry))

        if len(version_dirs) <= keep:
            return

        version_dirs.sort(key=lambda x: x[0], reverse=True)

        # Determine the active version dir to protect it. Compare on path ancestry
        # (not substring) so e.g. an active "version-2.1.81" doesn't shield the
        # distinct "version-2.1.8" dir, whose path is a string prefix of it.
        active_binary = self.resolve_binary_path(tool)
        active_dir = Path(active_binary) if active_binary else None

        for _, dir_path in version_dirs[keep:]:
            # Never delete the version dir that contains the active binary.
            if active_dir is not None and dir_path in active_dir.parents:
                continue
            shutil.rmtree(dir_path, ignore_errors=True)

    def _cleanup_stale_state(self) -> None:
        """Remove stale temp dirs and old versions from previous runs, per managed tool."""
        for tool in get_managed_tools():
            tool_dir = _get_tool_dir(tool)
            if not tool_dir.is_dir():
                continue
            for entry in tool_dir.iterdir():
                if entry.is_dir() and entry.name.startswith(_TEMP_DIR_PREFIX):
                    logger.info("Cleaning up stale temp dir: {}", entry)
                    shutil.rmtree(entry, ignore_errors=True)
            self.cleanup_old_versions(tool, keep=_retention_keep_for_tool(tool))
