from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from typing import Sequence

import attr
import pytest
from loguru import logger
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page

from imbue_core.git import get_git_repo_root
from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.playwright_utils import navigate_to_frontend
from sculptor.testing.subprocess_utils import Forwarder
from sculptor.testing.subprocess_utils import print_colored_line
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG

LOCAL_HOST_URL = "http://127.0.0.1"
READY_MESSAGE_V1 = "Server is ready to accept requests!"

_ANTHROPIC_API_KEY_FILE = Path.home() / ".anthropic_api_key"


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

    process: subprocess.Popen
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
    ) -> None:
        self.environment = environment
        self.database_url = database_url
        self.port = port
        self.default_timeout_ms = default_timeout_ms
        self.request = request
        self.sculptor_folder = sculptor_folder

    @contextmanager
    def spawn_sculptor_instance(
        self,
        *,
        project_path: Path | None = None,
        wait_until_ready: bool = True,
    ) -> Generator[tuple[SculptorServer, Page, BrowserContext, str | None], None, None]:
        """Start a backend process and yield ``(server, page, context, session_token)``.

        The session_token is always None for the raw-backend path (there's no
        Electron main process issuing its own token).

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
        environment = self.environment.copy()
        command = get_sculptor_command_backend_only(project_path, port=self.port)

        env = {k: str(v) for k, v in {**os.environ, **environment}.items() if v is not None}
        server = _start_server_process_and_validate_readiness(command, env)
        forwarder = Forwarder(server)
        forwarder.start()
        specimen_server = SculptorServer(process=server, port=self.port)

        page: "Page" = self.request.getfixturevalue("page")
        configure_page(page, timeout_ms=self.default_timeout_ms)
        # Land on /home directly. The bare URL would route through the
        # rootLoader at "/", which restores the persisted MRU tab and could
        # drop the test onto a workspace route instead of a deterministic
        # Home; going straight to /#/home keeps every spawn starting from the
        # same place (test_restarts/persistence/etc. rely on that).
        #
        # Going through about:blank first forces a full SPA reload between
        # spawns. Hash-only navigation (e.g. from /#/ws/<id> to /#/home)
        # leaves the prior React app instance running, so its in-memory
        # tabsAtom would re-sync to localStorage on the next write and
        # clobber any state the test wrote between spawns
        # (test_restart_clears_pointer_when_workspace_deleted depends on
        # the bogus localStorage state surviving into the next spawn).
        page.goto("about:blank")
        navigate_to_frontend(page=page, url=f"http://127.0.0.1:{self.port}/#/home")

        yield specimen_server, page, page.context, None

        # Snapshot any error the backend logged *during the test* before we start
        # tearing down. Killing the process group below also kills whatever child
        # subprocess happens to be in flight — e.g. a `git rev-parse --abbrev-ref
        # HEAD` from PR-status polling — and the backend logs an "Unexpected
        # exception in inner subprocess wrapper thread" ERROR as that child dies.
        # That ERROR is an artifact of our own forced teardown, not a test
        # failure, so the pass/fail decision below must use this pre-teardown
        # snapshot rather than whatever the Forwarder records while we kill.
        failure_line_during_test = forwarder.first_failure_line

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
            except Exception:
                pass
        try:
            server.wait(timeout=60)
        except subprocess.TimeoutExpired:
            logger.warning("Sculptor server did not terminate gracefully, killing process group.")
            try:
                os.killpg(os.getpgid(server.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            server.wait(2)

        # If there was an error in the logs *during the test*, that is sufficient for us to mark this task as failed
        # (even if the test didn't realize it failed). Teardown-induced errors are excluded via the snapshot above.
        if specimen_server.is_unexpected_error_caused_by_test:
            pass
        elif failure_line_during_test is not None:
            raise Exception(f"Sculptor server encountered emitted a line with ERROR: {failure_line_during_test}")


def get_v1_frontend_path() -> Path:
    """Returns the path to the frontend directory in v1"""
    return get_git_repo_root() / "sculptor" / "frontend"


def get_testing_environment(
    database_url: str,
    sculptor_folder: Path,
    tmp_path: Path,
    static_files_path: Path,
    hide_keys: bool = True,
) -> dict[str, str | None]:
    environment: dict[str, str | None] = {}

    environment["STATIC_FILES_PATH"] = str(static_files_path.absolute())

    environment[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = sculptor_folder
    environment["DATABASE_URL"] = database_url
    environment["TESTING__INTEGRATION_ENABLED"] = "true"
    environment["SENTRY_DSN"] = None
    # Unset SESSION_TOKEN to prevent inheriting it from the parent environment (e.g., when
    # running tests from a terminal spawned by Sculptor). If inherited, the backend would
    # require session token authentication, but the Electron frontend generates its own token.
    environment["SESSION_TOKEN"] = None
    # Unset CLAUDECODE to prevent inheriting it from the parent environment (e.g., when
    # running tests from within a Claude Code session). If inherited, Claude CLI refuses to
    # start with "Claude Code cannot be launched inside another Claude Code session."
    environment["CLAUDECODE"] = None

    # Unset CLAUDECODE and CLAUDE_CODE_ENTRYPOINT to prevent the nested claude CLI from
    # detecting it's inside an existing Claude Code session and refusing to start.
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


def _start_server_process_and_validate_readiness(command: Sequence[str], env: dict[str, str]) -> subprocess.Popen[str]:
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

            raw_bytes = os.read(stdout_fd, 4096)
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
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        server.wait(2)

    raise RuntimeError(error_msg)
