import os
import secrets
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from loguru import logger
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import Playwright
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.packaged_utils import kill_process_tree
from sculptor.testing.packaged_utils import register_project as _register_project
from sculptor.testing.packaged_utils import wait_for_backend_health
from sculptor.testing.port_manager import PortManager
from sculptor.testing.server_utils import SculptorServer
from sculptor.testing.subprocess_utils import Forwarder
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG

# tenacity delays are in seconds; Playwright timeouts are in milliseconds.
_CDP_CONNECT_TIMEOUT_SECONDS = 120
_CDP_CONNECT_RETRY_INTERVAL_SECONDS = 1
_CDP_CONNECT_ATTEMPT_TIMEOUT_MS = 10_000
_BLANK_PAGE_NAVIGATION_TIMEOUT_MS = 60_000

_KNOWN_HARMLESS_ELECTRON_SUBSTRINGS = (
    "Keychain lookup for suffixed key failed:",
    "Failed to connect to the bus:",
    "Could not bind NETLINK socket",
    "Failed to read /proc/sys/fs/inotify/max_user_watches",
    "X connection error received.",
)


def _is_known_harmless_electron_error(line: str) -> bool:
    return any(substring in line for substring in _KNOWN_HARMLESS_ELECTRON_SUBSTRINGS)


class PackagedElectronFrontend:
    """Launches a packaged Sculptor Electron binary and connects Playwright over CDP.

    This class is designed for Linux, where Electron runs under xvfb and CDP
    reliably provides a page. For macOS (headless CI without WindowServer),
    use PackagedBackendFrontend instead.
    """

    def __init__(
        self,
        playwright: Playwright,
        binary_path: Path,
        backend_port: int,
        cdp_port: int,
        sculptor_folder: Path,
        user_data_dir: Path,
        timeout_ms: int,
        extra_env: dict[str, str] | None = None,
        wait_until_ready: bool = True,
    ) -> None:
        self.playwright = playwright
        self.binary_path = binary_path
        self.backend_port = backend_port
        self.cdp_port = cdp_port
        self.sculptor_folder = sculptor_folder
        self.user_data_dir = user_data_dir
        self.timeout_ms = timeout_ms
        self.extra_env = extra_env or {}
        # Governs the whole "wait for the app to reach a happy steady state
        # before yielding" contract. When True (default): wait for the
        # backend health endpoint and for the renderer to navigate away
        # from about:blank. When False: skip both waits and yield as soon
        # as CDP is reachable, so callers can assert on whatever the
        # renderer shows (e.g. BACKEND_ERROR_PAGE when the backend exits
        # by design during startup).
        self.wait_until_ready = wait_until_ready
        self.session_token: str = secrets.token_hex(32)
        self._electron_proc: subprocess.Popen | None = None
        self._forwarder: Forwarder | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> tuple[BrowserContext, Page]:
        cmd: tuple[str, ...] = (
            str(self.binary_path),
            f"--remote-debugging-port={self.cdp_port}",
        )

        if os.getuid() == 0:
            cmd = cmd + ("--no-sandbox",)

        is_headless = "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ
        if is_headless:
            # Under xvfb there is no real GPU and Chromium's GPU process
            # crash-loops at init (more readily under Electron 42); force
            # software rendering so webview/screenshot frames are produced
            # deterministically. Mirrors the dev launcher in electron_frontend.py.
            cmd = cmd + ("--disable-gpu",)
            cmd = ("xvfb-run", "-a", "-e", "/tmp/xvfb-error.log", "-s", "-screen 0 1600x1000x16") + cmd

        env_overrides = {
            "SCULPTOR_API_PORT": str(self.backend_port),
            "SCULPTOR_USER_DATA_DIR": str(self.user_data_dir),
            SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG: str(self.sculptor_folder),
            "SCULPTOR_SESSION_TOKEN": self.session_token,
            "PYTEST_CURRENT_TEST": "packaged_integration_test",
            "ELECTRON_ENABLE_LOGGING": "1",
        }
        env_unset_keys = ("SESSION_TOKEN", "SENTRY_DSN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        full_env = {k: v for k, v in os.environ.items() if k not in env_unset_keys}
        full_env.update(env_overrides)
        full_env.update(self.extra_env)

        logger.info("Launching packaged Sculptor: {}", " ".join(cmd))
        self._electron_proc = subprocess.Popen(
            cmd,
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=lambda: os.setpgid(0, 0),
        )
        assert self._electron_proc.stdout is not None

        self._forwarder = Forwarder(
            self._electron_proc,
            prefix="[Packaged Electron] ",
            known_harmless_func=_is_known_harmless_electron_error,
        )
        self._forwarder.start()

        try:
            if self.wait_until_ready:
                wait_for_backend_health(self.backend_port, process=self._electron_proc)

            browser = self._connect_playwright_cdp()
            logger.info("CDP connection established on port {}", self.cdp_port)

            assert len(browser.contexts) == 1
            context = browser.contexts[0]
            pages = [p for p in context.pages if not p.url.startswith("devtools://")]

            assert len(pages) == 1, f"Expected exactly one non-devtools page, got {pages}"
            page = pages[0]
            logger.info("Connected page URL: {}", page.url)

            # If the page is blank, the load hasn't completed yet — wait.
            # Skip when we're not awaiting the backend: the renderer may
            # legitimately stay on about:blank / render the error page from
            # the bundled SPA without navigating.
            if self.wait_until_ready and (not page.url or page.url == "about:blank"):
                logger.info("Page is blank, waiting for navigation to complete...")
                page.wait_for_url("**/*", timeout=_BLANK_PAGE_NAVIGATION_TIMEOUT_MS)

            configure_page(page, timeout_ms=self.timeout_ms)
        except Exception as e:
            logger.error("Packaged app setup failed: {}", e)
            if self._electron_proc is not None:
                ret = self._electron_proc.poll()
                logger.error("Electron process alive: {}, returncode: {}", ret is None, ret)
            self._kill_packaged_app()
            raise

        self._browser_context = context
        self._page = page
        return (context, page)

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._kill_packaged_app()
        shutil.rmtree(self.user_data_dir, ignore_errors=True)

    def register_project(self, project_path: Path) -> None:
        """Register a project with the backend so the frontend skips the setup page."""
        _register_project(self.backend_port, self.session_token, project_path)

    def _connect_playwright_cdp(self) -> Browser:
        retry_connect = retry(
            stop=stop_after_delay(_CDP_CONNECT_TIMEOUT_SECONDS),
            wait=wait_fixed(_CDP_CONNECT_RETRY_INTERVAL_SECONDS),
            retry=retry_if_exception_type(PlaywrightError),
            reraise=True,
        )(self._connect_cdp)
        return retry_connect()

    def _connect_cdp(self) -> Browser:
        logger.debug("Attempting CDP connection on port {}", self.cdp_port)
        return self.playwright.chromium.connect_over_cdp(
            f"http://localhost:{self.cdp_port}", timeout=_CDP_CONNECT_ATTEMPT_TIMEOUT_MS
        )

    def _kill_packaged_app(self) -> None:
        kill_process_tree(self._electron_proc, self._forwarder, self.backend_port)


class PackagedElectronFactory:
    """Per-test spawner for packaged Sculptor Electron instances.

    Parallels ``SculptorFactory`` (which spawns raw backend subprocesses):
    each ``spawn_sculptor_instance`` call starts a fresh packaged Electron
    binary against a stable ``sculptor_folder``, enabling restart tests and
    tests that need pre-seeded on-disk state (via
    ``custom_sculptor_folder_populator``) to run under the real shipped UI.
    """

    def __init__(
        self,
        playwright: Playwright,
        binary_path: Path,
        port_manager: PortManager,
        backend_port: int,
        sculptor_folder: Path,
        default_timeout_ms: int,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.playwright = playwright
        self.binary_path = binary_path
        self.port_manager = port_manager
        self.backend_port = backend_port
        self.sculptor_folder = sculptor_folder
        self.default_timeout_ms = default_timeout_ms
        self.extra_env = extra_env or {}

    @contextmanager
    def spawn_sculptor_instance(
        self,
        *,
        project_path: Path | None = None,
        wait_until_ready: bool = True,
    ) -> Generator[tuple[SculptorServer, Page, BrowserContext, str | None], None, None]:
        """Start a packaged Electron instance and yield ``(server, page, context, session_token)``.

        Args:
            project_path: If set and ``wait_until_ready`` is True, the project
                at this path is registered with the backend before yielding
                so the SPA lands on the main app rather than /setup.
                If ``wait_until_ready`` is False the registration is skipped
                (no healthy backend to register against).
            wait_until_ready: If False, skip the backend health check and the
                blank-page navigation wait, and observe the renderer via CDP
                as-is. Use when the test expects the backend to exit during
                startup (fatal error scenarios).
        """
        cdp_port = self.port_manager.get_free_port()
        user_data_dir = Path(tempfile.mkdtemp(prefix="sculptor_packaged_factory_"))
        frontend = PackagedElectronFrontend(
            playwright=self.playwright,
            binary_path=self.binary_path,
            backend_port=self.backend_port,
            cdp_port=cdp_port,
            sculptor_folder=self.sculptor_folder,
            user_data_dir=user_data_dir,
            timeout_ms=self.default_timeout_ms,
            extra_env=self.extra_env,
            wait_until_ready=wait_until_ready,
        )

        context, page = frontend.__enter__()
        try:
            context.add_cookies(
                [
                    {
                        "name": "x-session-token",
                        "value": frontend.session_token,
                        "url": f"http://127.0.0.1:{self.backend_port}",
                    }
                ]
            )
            if wait_until_ready and project_path is not None:
                frontend.register_project(project_path)

            assert frontend._electron_proc is not None
            server = SculptorServer(process=frontend._electron_proc, port=self.backend_port)
            yield server, page, context, frontend.session_token
        finally:
            # Close the Playwright page and browser context before killing the
            # Electron process so CDP releases its references cleanly. The
            # session-scoped path does this via SculptorInstance._teardown();
            # per-spawn teardown has to do it explicitly.
            try:
                page.close()
            except Exception:
                logger.debug("Page already closed during packaged factory teardown")
            try:
                context.close()
            except Exception:
                logger.debug("Browser context already closed during packaged factory teardown")
            try:
                frontend.__exit__(None, None, None)
            except Exception:
                logger.debug("Packaged frontend cleanup error during spawn teardown")
