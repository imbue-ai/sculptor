from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import attr
import pytest
from loguru import logger
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright
from pytest_playwright.pytest_playwright import ArtifactsRecorder

from sculptor.foundation.git import get_git_repo_root
from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.playwright_utils import navigate_to_frontend
from sculptor.testing.port_manager import PortManager
from sculptor.testing.subprocess_utils import Forwarder
from sculptor.testing.subprocess_utils import print_colored_line
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG

if TYPE_CHECKING:
    # ``electron_frontend`` imports ``get_v1_frontend_path`` from this module, so the
    # runtime import lives inside ``_make_electron_frontend`` to avoid an import cycle.
    from sculptor.testing.electron_frontend import ElectronFrontend

LOCAL_HOST_URL = "http://127.0.0.1"
READY_MESSAGE_V1 = "Server is ready to accept requests!"

_ANTHROPIC_API_KEY_FILE = Path.home() / ".anthropic_api_key"

# How long to wait for the server to exit gracefully after SIGTERM before escalating to SIGKILL.
_SERVER_TERMINATION_TIMEOUT_SECONDS = 60
# How long to wait for the server to exit gracefully during startup-failure cleanup before SIGKILL.
_STARTUP_KILL_TERMINATION_TIMEOUT_SECONDS = 5
# Short grace period to reap the process after sending SIGKILL.
_SERVER_KILL_GRACE_SECONDS = 2
# Size of each os.read() chunk when draining the server's stdout pipe.
_STDOUT_READ_CHUNK_BYTES = 4096


def get_anthropic_api_key() -> str | None:
    """Get the Anthropic API key from the environment or a file.

    Checks the ANTHROPIC_API_KEY environment variable first, then falls back to
    reading from ~/.anthropic_api_key.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key
    try:
        return _ANTHROPIC_API_KEY_FILE.read_text().strip()
    except FileNotFoundError:
        return None


@attr.s(auto_attribs=True, kw_only=True)
class SculptorServer:
    """A sculptor server holds a sculptor process for testing."""

    process: subprocess.Popen[str]
    port: int
    is_unexpected_error_caused_by_test: bool = False

    @property
    def url(self) -> str:
        return f"{LOCAL_HOST_URL}:{self.port}"


class SculptorFactory:
    """A factory for spawning Sculptor backend processes during integration tests.

    Used internally by SculptorInstanceFactory to start fresh backend processes.
    """

    def __init__(
        self,
        environment: dict[str, str | None],
        port: int,
        database_url: str,
        default_timeout_ms: int,
        request: pytest.FixtureRequest,
        sculptor_folder: Path | None = None,
        launch_mode: str = "browser",
        playwright: "Playwright | None" = None,
        port_manager: "PortManager | None" = None,
    ) -> None:
        self.environment = environment
        self.database_url = database_url
        self.port = port
        self.default_timeout_ms = default_timeout_ms
        self.request = request
        self.sculptor_folder = sculptor_folder
        # ``launch_mode`` selects the per-spawn frontend: "browser" (default)
        # drives the shared pytest-playwright page; "electron" /
        # "electron-custom-command" launch a real, non-packaged Electron shell
        # over CDP. ``playwright`` / ``port_manager`` are only consulted by the
        # electron paths (and asserted present there).
        self.launch_mode = launch_mode
        self.playwright = playwright
        self.port_manager = port_manager

    @property
    def is_electron(self) -> bool:
        """Whether spawned instances render in a real (non-packaged) Electron shell."""
        return self.launch_mode in ("electron", "electron-custom-command")

    @contextmanager
    def spawn_sculptor_instance(
        self,
        *,
        project_path: Path | None = None,
        wait_until_ready: bool = True,
    ) -> Generator[tuple[SculptorServer, Page, BrowserContext, str | None], None, None]:
        """Start a backend process and yield ``(server, page, context, session_token)``.

        In ``browser`` mode the session_token is always None (there's no Electron
        main process issuing its own token) and the frontend is the shared
        pytest-playwright page. In ``electron`` mode the backend is started the
        same way but the frontend is a real Electron shell launched over CDP. In
        ``electron-custom-command`` mode Electron spawns the backend itself, so
        that flow is delegated to ``_spawn_custom_command_electron_instance``.

        Args:
            project_path: If provided, the backend starts with this repo as
                its initial project. If None, the backend starts with no
                project (useful for onboarding / project-selection tests).
            wait_until_ready: Only the default (True) is supported here;
                passing False is reserved for the packaged-electron delegate
                that can observe the renderer via CDP before the backend is
                healthy.
        """
        if not wait_until_ready:
            raise NotImplementedError("wait_until_ready=False is only supported in packaged-electron mode")

        if self.launch_mode == "electron-custom-command":
            with self._spawn_custom_command_electron_instance(project_path) as result:
                yield result
            return

        environment = self.environment.copy()
        command = get_sculptor_command_backend_only(project_path, port=self.port)

        env = {k: str(v) for k, v in {**os.environ, **environment}.items() if v is not None}
        server = start_server_process_and_validate_readiness(command, env)
        forwarder = Forwarder(server)
        forwarder.start()
        specimen_server = SculptorServer(process=server, port=self.port)

        # Acquire the frontend. Browser mode drives the shared pytest-playwright
        # page; electron mode launches a real Electron shell over CDP pointed at
        # the just-started backend, mirroring the shared-instance electron path
        # in resources.py.
        electron_frontend: "ElectronFrontend | None" = None
        artifacts_recorder: "ArtifactsRecorder | None" = None
        if self.launch_mode == "electron":
            electron_frontend, page, context = self._launch_electron_frontend()
            # Register the CDP-acquired context so ``--tracing`` captures it; the
            # browser path gets this for free via the ``page`` fixture's context.
            artifacts_recorder = self.request.getfixturevalue("_artifacts_recorder")
            artifacts_recorder.on_did_create_browser_context(context)
        else:
            page = self.request.getfixturevalue("page")
            configure_page(page, timeout_ms=self.default_timeout_ms)
            navigate_to_frontend(page=page, url=f"http://127.0.0.1:{self.port}")
            context = page.context

        # On a test-body failure, reclaim the heavy Electron shell (Electron + Vite
        # dev server + xvfb) before re-raising. Browser mode has nothing to do here,
        # and the backend teardown below stays success-path-only — preserving the
        # original behavior where a failing test leaves the raw backend for the
        # worker/session to reap.
        try:
            yield specimen_server, page, context, None
        except BaseException:
            if electron_frontend is not None:
                assert artifacts_recorder is not None
                self._teardown_electron_factory_frontend(electron_frontend, artifacts_recorder, context, page)
            raise

        # Snapshot any error the backend logged *during the test* before we start
        # tearing down. Killing the process group below also kills whatever child
        # subprocess happens to be in flight — e.g. a `git rev-parse --abbrev-ref
        # HEAD` from PR-status polling — and the backend logs an "Unexpected
        # exception in inner subprocess wrapper thread" ERROR as that child dies.
        # That ERROR is an artifact of our own forced teardown, not a test
        # failure, so the pass/fail decision below must use this pre-teardown
        # snapshot rather than whatever the Forwarder records while we kill.
        # Electron teardown happens *after* this snapshot for the same reason:
        # tearing the shell down disconnects its websocket, which the backend may
        # log, and that must not be misattributed to the test.
        failure_line_during_test = forwarder.first_failure_line

        if electron_frontend is not None:
            assert artifacts_recorder is not None
            self._teardown_electron_factory_frontend(electron_frontend, artifacts_recorder, context, page)

        logger.info("Terminating sculptor server and its process group")
        # Kill the entire process group to clean up any child processes.
        # This is necessary because child processes inherit the stdout pipe and block the Forwarder thread
        # from exiting if not properly terminated.
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGTERM)
        except ProcessLookupError:
            # Process already terminated
            pass
        forwarder.stop()
        if server.stdout:
            try:
                server.stdout.close()
            except OSError:
                pass
        try:
            server.wait(timeout=_SERVER_TERMINATION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning("Sculptor server did not terminate gracefully, killing process group.")
            try:
                os.killpg(os.getpgid(server.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            server.wait(_SERVER_KILL_GRACE_SECONDS)

        # If there was an error in the logs *during the test*, that is sufficient for us to mark this task as failed
        # (even if the test didn't realize it failed). Teardown-induced errors are excluded via the snapshot above.
        if not specimen_server.is_unexpected_error_caused_by_test and failure_line_during_test is not None:
            raise RuntimeError(f"Sculptor server emitted a line with ERROR: {failure_line_during_test}")

    def _launch_electron_frontend(self) -> "tuple[ElectronFrontend, Page, BrowserContext]":
        """Launch a non-packaged Electron shell over CDP against the running backend.

        Returns ``(frontend, page, context)``. The Electron main process is told
        to connect to the already-started backend via ``SCULPTOR_API_PORT``; the
        renderer is served by an Electron-managed Vite dev server.
        """
        electron_frontend = self._make_electron_frontend()
        context, page = electron_frontend.__enter__()
        return electron_frontend, page, context

    def _make_electron_frontend(
        self,
        *,
        custom_backend_cmd: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> "ElectronFrontend":
        """Construct an ``ElectronFrontend`` for this factory's backend port.

        The import is function-local because ``electron_frontend`` imports
        ``get_v1_frontend_path`` from this module (a module-level import cycles).
        """
        from sculptor.testing.electron_frontend import ElectronFrontend

        assert self.playwright is not None, "electron launch mode requires a Playwright instance"
        assert self.port_manager is not None, "electron launch mode requires a PortManager"
        return ElectronFrontend(
            playwright=self.playwright,
            backend_port=self.port,
            port_manager=self.port_manager,
            timeout_ms=self.default_timeout_ms,
            custom_backend_cmd=custom_backend_cmd,
            extra_env=extra_env,
        )

    def _teardown_electron_factory_frontend(
        self,
        electron_frontend: "ElectronFrontend",
        artifacts_recorder: "ArtifactsRecorder",
        context: BrowserContext,
        page: Page,
    ) -> None:
        """Stop tracing, close the CDP page/context, then kill the Electron shell.

        Order matters: ``on_will_close_browser_context`` writes the trace via the
        live CDP connection, so it must run before the Electron process (and its
        CDP endpoint) is killed.
        """
        try:
            artifacts_recorder.on_will_close_browser_context(context)
        except Exception:
            logger.debug("Artifacts recorder close failed during electron factory teardown")
        for closer, what in ((page.close, "page"), (context.close, "browser context")):
            try:
                closer()
            except Exception:
                logger.debug("{} already closed during electron factory teardown", what)
        try:
            electron_frontend.__exit__(None, None, None)
        except Exception:
            logger.debug("ElectronFrontend cleanup error during electron factory teardown")

    @contextmanager
    def _spawn_custom_command_electron_instance(
        self,
        project_path: Path | None,
    ) -> Generator[tuple[SculptorServer, Page, BrowserContext, str | None], None, None]:
        """Spawn a per-test Electron instance where Electron manages the backend.

        Mirrors the shared-instance custom-command path
        (``_create_custom_command_instance`` in resources.py): instead of
        starting the backend separately, Electron spawns it via
        ``SCULPTOR_CUSTOM_BACKEND_CMD``, exercising the HTTP-upload code path.
        Per-test isolation is preserved by the factory's own backend port and
        sculptor folder. Yields ``(server, page, context, session_token)`` where
        ``server`` wraps the Electron process (which owns the backend child).
        """
        # Print the URL then exec the backend, matching the shared path. Use
        # sys.executable so the backend runs in the test virtualenv (the Electron
        # child otherwise inherits a different PATH).
        project_arg = f" {project_path}" if project_path is not None else ""
        backend_exec = f"exec {sys.executable} -m sculptor.cli.main --no-open-browser --port {self.port}{project_arg}"
        custom_backend_cmd = f"echo http://localhost:{self.port} && {backend_exec}"
        # The testing environment (DATABASE_URL, sculptor folder, hidden keys,
        # unset SESSION_TOKEN/CLAUDECODE, ...) reaches the backend as Electron's
        # extra_env, since the custom command is the backend's parent.
        extra_env = {k: str(v) for k, v in self.environment.items() if v is not None}
        # A known session token lets Playwright's page.request calls authenticate
        # against the backend (which requires the token in custom-command mode).
        session_token = os.urandom(32).hex()
        extra_env["SCULPTOR_SESSION_TOKEN"] = session_token

        electron_frontend = self._make_electron_frontend(custom_backend_cmd=custom_backend_cmd, extra_env=extra_env)
        context, page = electron_frontend.__enter__()
        artifacts_recorder: "ArtifactsRecorder" = self.request.getfixturevalue("_artifacts_recorder")
        artifacts_recorder.on_did_create_browser_context(context)
        try:
            context.add_cookies(
                [
                    {
                        "name": "x-session-token",
                        "value": session_token,
                        "url": f"http://127.0.0.1:{self.port}",
                    }
                ]
            )
            assert electron_frontend._electron_proc is not None
            server = SculptorServer(process=electron_frontend._electron_proc, port=self.port)
            yield server, page, context, session_token
        finally:
            self._teardown_electron_factory_frontend(electron_frontend, artifacts_recorder, context, page)


def get_v1_frontend_path() -> Path:
    """Returns the path to the frontend directory in v1"""
    return get_git_repo_root() / "sculptor" / "frontend"


def get_testing_environment(
    database_url: str,
    sculptor_folder: Path,
    tmp_path: Path,
    hide_keys: bool = True,
) -> dict[str, str | None]:
    environment: dict[str, str | None] = {}

    environment[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = str(sculptor_folder)
    environment["DATABASE_URL"] = database_url
    environment["TESTING__INTEGRATION_ENABLED"] = "true"
    environment["SENTRY_DSN"] = None
    # Unset SESSION_TOKEN to prevent inheriting it from the parent environment (e.g., when
    # running tests from a terminal spawned by Sculptor). If inherited, the backend would
    # require session token authentication, but the Electron frontend generates its own token.
    environment["SESSION_TOKEN"] = None
    # Unset CLAUDECODE and CLAUDE_CODE_ENTRYPOINT to prevent the nested claude CLI from detecting
    # it's inside an existing Claude Code session (e.g., when running tests from within one) and
    # refusing to start with "Claude Code cannot be launched inside another Claude Code session."
    environment["CLAUDECODE"] = None
    environment["CLAUDE_CODE_ENTRYPOINT"] = None

    if hide_keys:
        environment["ANTHROPIC_API_KEY"] = "sk-HIDDEN-FOR-TESTING"
        environment["OPENAI_API_KEY"] = "sk-HIDDEN-FOR-TESTING"
    else:
        # When not hiding keys (snapshot update mode), ensure the API key is available
        # even if it comes from a file rather than the environment variable.
        api_key = get_anthropic_api_key()
        if api_key:
            environment["ANTHROPIC_API_KEY"] = api_key

    return environment


def get_sculptor_command_backend_only(
    repo_path: Path | None,
    port: int,
) -> tuple[str, ...]:
    command = [
        "python",
        "-m",
        "sculptor.cli.main",
        "--no-open-browser",
        f"--port={port}",
    ]
    if repo_path is not None:
        command.append(str(repo_path))
    return tuple(command)


_SERVER_STARTUP_TIMEOUT_SECONDS = 120


def start_server_process_and_validate_readiness(command: Sequence[str], env: dict[str, str]) -> subprocess.Popen[str]:
    # Use start_new_session=True so we can terminate the entire process group during cleanup.
    server = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, start_new_session=True
    )
    assert server.stdout, "Sculptor server stdout is always available in PIPE mode"
    server_output_lines: list[str] = []
    deadline = time.monotonic() + _SERVER_STARTUP_TIMEOUT_SECONDS

    # Read stdout with a timeout so a hung backend doesn't block a worker
    # indefinitely.  Uses selectors to poll the pipe with a per-iteration
    # timeout derived from the remaining budget.
    #
    # We use os.read() on the raw FD instead of server.stdout.read() because
    # Python's BufferedReader.read(n) loops trying to accumulate exactly n
    # bytes, which blocks after select() returns if fewer than n bytes are
    # available.  os.read() returns immediately with whatever data is ready.
    #
    # HACK: text=True wraps stdout in a TextIOWrapper, but startup reads bypass
    # it via os.read() on the raw FD. This works only because nothing reads
    # through the TextIOWrapper before startup completes — adding a
    # server.stdout.readline() call before this loop would silently lose data.
    stdout_fd = server.stdout.fileno()
    sel = selectors.DefaultSelector()
    sel.register(stdout_fd, selectors.EVENT_READ)
    remainder = ""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            events = sel.select(timeout=remaining)
            if not events:
                break  # timeout

            raw_bytes = os.read(stdout_fd, _STDOUT_READ_CHUNK_BYTES)
            if not raw_bytes:
                break  # EOF — process exited

            remainder += raw_bytes.decode("utf-8", errors="replace")
            while "\n" in remainder:
                line, remainder = remainder.split("\n", 1)
                server_output_lines.append(line.rstrip())
                print_colored_line(line.rstrip())
                if READY_MESSAGE_V1 in line:
                    logger.info("Sculptor server is ready")
                    return server
    finally:
        sel.unregister(stdout_fd)
        sel.close()

    # Server failed to start properly - provide detailed error information
    elapsed = _SERVER_STARTUP_TIMEOUT_SECONDS - max(0, deadline - time.monotonic())
    timed_out = elapsed >= _SERVER_STARTUP_TIMEOUT_SECONDS
    if timed_out:
        error_msg = f"Sculptor server startup timed out after {_SERVER_STARTUP_TIMEOUT_SECONDS}s.\n"
    else:
        error_msg = "Sculptor server failed to start and never outputted ready message.\n"
    error_msg += f"Expected message containing: '{READY_MESSAGE_V1}'\n"
    error_msg += f"Command: {' '.join(command)}\n"
    error_msg += "Server output:\n" + "\n".join(server_output_lines)

    logger.error(error_msg)
    try:
        os.killpg(os.getpgid(server.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        server.wait(timeout=_STARTUP_KILL_TERMINATION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        server.wait(_SERVER_KILL_GRACE_SECONDS)

    raise RuntimeError(error_msg)
