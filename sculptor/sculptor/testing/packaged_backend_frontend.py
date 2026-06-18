import os
import secrets
import subprocess
from pathlib import Path

from loguru import logger
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright

from sculptor.testing.frontend_utils import DEFAULT_TEST_LOCALE
from sculptor.testing.frontend_utils import DEFAULT_TEST_VIEWPORT
from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.packaged_utils import kill_process_tree
from sculptor.testing.packaged_utils import register_project
from sculptor.testing.packaged_utils import wait_for_backend_health
from sculptor.testing.subprocess_utils import Forwarder
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG


class PackagedBackendFrontend:
    """Launches a packaged sculptor_backend binary directly and connects via headless Chromium.

    Unlike PackagedElectronFrontend, this class does not use Electron or CDP at all.
    It launches the backend binary, waits for it to become healthy, then opens
    a standalone headless Chromium browser pointed at the backend's HTTP server.

    The backend serves bundled frontend-dist assets via its catch-all route,
    so the full UI is available without Electron.
    """

    def __init__(
        self,
        playwright: Playwright,
        binary_path: Path,
        backend_port: int,
        sculptor_folder: Path,
        timeout_ms: int,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.playwright = playwright
        self.binary_path = binary_path
        self.backend_port = backend_port
        self.sculptor_folder = sculptor_folder
        self.timeout_ms = timeout_ms
        self.extra_env = extra_env or {}
        self.session_token: str = secrets.token_hex(32)
        self._backend_proc: subprocess.Popen | None = None
        self._forwarder: Forwarder | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> tuple[BrowserContext, Page]:
        cmd = [
            str(self.binary_path),
            "--port",
            str(self.backend_port),
            "--no-open-browser",
            "--packaged-entrypoint",
        ]

        env_overrides = {
            SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG: str(self.sculptor_folder),
            "SCULPTOR_SESSION_TOKEN": self.session_token,
            "PYTEST_CURRENT_TEST": "packaged_integration_test",
        }
        env_unset_keys = ("SESSION_TOKEN", "SENTRY_DSN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        full_env = {k: v for k, v in os.environ.items() if k not in env_unset_keys}
        full_env.update(env_overrides)
        full_env.update(self.extra_env)

        logger.info("Launching packaged backend: {}", " ".join(cmd))
        self._backend_proc = subprocess.Popen(
            cmd,
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=lambda: os.setpgid(0, 0),
        )
        assert self._backend_proc.stdout is not None

        self._forwarder = Forwarder(
            self._backend_proc,
            prefix="[Packaged Backend] ",
        )
        self._forwarder.start()

        try:
            wait_for_backend_health(self.backend_port, process=self._backend_proc)

            backend_url = f"http://127.0.0.1:{self.backend_port}/"
            logger.info("Backend healthy, launching headless Chromium → {}", backend_url)
            self._browser = self.playwright.chromium.launch(headless=True)
            context = self._browser.new_context(viewport=DEFAULT_TEST_VIEWPORT, locale=DEFAULT_TEST_LOCALE)
            page = context.new_page()
            # Headless Chromium reports the page as unfocused, which breaks
            # focus-sensitive UI: activeElement-based keyboard shortcuts, panel
            # focus zones, and Escape-to-close. Emulate focus so the page
            # behaves like a foreground window (as in the real Electron app).
            focus_cdp_session = context.new_cdp_session(page)
            focus_cdp_session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
            page.goto(backend_url, wait_until="domcontentloaded")
            logger.info("Chromium page loaded, URL: {}", page.url)

            configure_page(page, timeout_ms=self.timeout_ms)
        except Exception as e:
            logger.error("Packaged backend setup failed: {}", e)
            if self._backend_proc is not None:
                ret = self._backend_proc.poll()
                logger.error("Backend process alive: {}, returncode: {}", ret is None, ret)
            self._kill_packaged_app()
            raise

        self._browser_context = context
        self._page = page
        return (context, page)

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._kill_packaged_app()

    def register_project(self, project_path: Path) -> None:
        """Register a project with the backend so the frontend skips the setup page."""
        register_project(self.backend_port, self.session_token, project_path)

    def _kill_packaged_app(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception as e:
                logger.warning("Failed to close headless Chromium browser during teardown: {}", e)

        kill_process_tree(self._backend_proc, self._forwarder, self.backend_port)
