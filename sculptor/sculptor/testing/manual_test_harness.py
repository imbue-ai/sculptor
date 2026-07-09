"""Non-pytest harness for launching Sculptor with a live Playwright browser.

Wraps the existing test infrastructure (SculptorServer, MockRepoState, config
setup) into a standalone class that can be used outside of pytest — for example,
by the auto-qa-changes skill's BrowserController HTTP server.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from loguru import logger
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright
from playwright.sync_api import sync_playwright

import sculptor.primitives.ids
from sculptor.config.user_config import UserConfig
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.frontend_utils import get_v1_frontend_path
from sculptor.testing.mock_repo import MockRepoState
from sculptor.testing.playwright_utils import navigate_to_frontend
from sculptor.testing.port_manager import PortManager
from sculptor.testing.repo_resources import get_test_project_state
from sculptor.testing.server_utils import SculptorServer
from sculptor.testing.server_utils import get_sculptor_command_backend_only
from sculptor.testing.server_utils import get_testing_environment
from sculptor.testing.server_utils import start_server_process_and_validate_readiness
from sculptor.testing.subprocess_utils import Forwarder

_DEFAULT_TIMEOUT_MS = 30_000
_DEFAULT_VIEWPORT = {"width": 1400, "height": 900}
_VITE_POLL_INTERVAL_SECONDS = 1
_VITE_POLL_REQUEST_TIMEOUT_SECONDS = 2
_BACKEND_SHUTDOWN_TIMEOUT_SECONDS = 10
_VITE_SHUTDOWN_TIMEOUT_SECONDS = 5

# Below this /dev/shm size, Chromium's renderer is prone to exhausting shared
# memory and crashing during long sessions, so we redirect it to disk (see
# _chromium_shared_memory_args). Docker's default /dev/shm is 64MB; a normal
# Linux host has half of RAM (gigabytes), so this threshold cleanly separates
# the two without a container-detection heuristic.
_SMALL_DEV_SHM_THRESHOLD_BYTES = 256 * 1024 * 1024


def _chromium_shared_memory_args() -> list[str]:
    """Return ``--disable-dev-shm-usage`` only when /dev/shm is too small to trust.

    Containers mount a tiny (~64MB) /dev/shm. Chromium's renderer uses /dev/shm
    for shared memory and crashes with "Target/Page crashed" once it fills during
    a long session (especially at device_scale_factor=2). Redirecting that memory
    to disk-backed /tmp avoids the crash, but disk is slower than tmpfs, so we
    only pay that cost where /dev/shm is actually constrained — not on macOS
    (no /dev/shm) or a normally-provisioned Linux host.
    """
    try:
        stats = os.statvfs("/dev/shm")
    except (FileNotFoundError, OSError):
        return []
    total_bytes = stats.f_frsize * stats.f_blocks
    if total_bytes < _SMALL_DEV_SHM_THRESHOLD_BYTES:
        return ["--disable-dev-shm-usage"]
    return []


def _make_test_user_config() -> UserConfig:
    """Create a UserConfig with test defaults (mirrors resources.py)."""
    test_email = "test@imbue.com"
    return UserConfig(
        user_email=test_email,
        user_id=sculptor.primitives.ids.create_user_id(test_email),
        organization_id=sculptor.primitives.ids.create_organization_id(test_email),
        instance_id=hashlib.md5(os.urandom(64)).hexdigest(),
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_session_recording_enabled=True,
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
    )


def _populate_sculptor_folder(folder_path: Path) -> None:
    """Write a pre-filled config.toml so onboarding is already complete."""
    internal_dir = folder_path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config_path = internal_dir / "config.toml"
    config = _make_test_user_config()
    save_config(config, config_path)


def _create_test_repo(tmp_path: Path) -> MockRepoState:
    """Create a canonical test git repository (same layout as integration tests)."""
    repo_dir = tmp_path / "manual_test_repo"
    initial_state = get_test_project_state()
    with ConcurrencyGroup(name="manual_test_repo") as cg:
        repo = MockRepoState.build_locally(state=initial_state, local_dir=repo_dir, concurrency_group=cg)
    repo.create_reset_and_checkout_branch("testing")
    repo.write_file("src/app.py", "import flask\n\nflask.run()")
    repo.commit("app.py commit", commit_time="2025-01-01T00:00:01")
    repo.write_file("stuff.txt", "stuff")
    repo.commit("Stuff", commit_time="2025-01-01T00:00:02")
    return repo


class ManualTestHarness:
    """Launch a Sculptor instance with a live Playwright browser for manual testing.

    Starts Sculptor's backend, opens a headless Chromium browser, and navigates
    to the home page. The agent then clicks through the UI to reach whatever
    page it needs to test — just like a real user.

    Usage::

        harness = ManualTestHarness()
        harness.start()
        # harness.page is now a live Playwright Page on the home screen
        harness.page.screenshot(path="screenshot.png")
        harness.stop()
    """

    def __init__(
        self,
        screenshots_dir: Path | None = None,
        viewport: dict[str, int] | None = None,
        project_path: Path | None = None,
    ) -> None:
        self._screenshots_dir = screenshots_dir or Path(tempfile.mkdtemp(prefix="sculptor_screenshots_"))
        self._viewport = viewport or _DEFAULT_VIEWPORT
        self._project_path = project_path

        # Populated during start()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None
        self._server: SculptorServer | None = None
        self._forwarder: Forwarder | None = None
        self._sculptor_folder: Path | None = None
        self._tmp_path: Path | None = None
        self._repo: MockRepoState | None = None
        self._port: int | None = None
        self._vite_port: int | None = None
        self._vite_process: subprocess.Popen[bytes] | None = None
        self._port_manager: PortManager | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Harness not started — call start() first")
        return self._page

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Harness not started — call start() first")
        return self._server.url

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("Harness not started — call start() first")
        return self._port

    @property
    def screenshots_dir(self) -> Path:
        return self._screenshots_dir

    @property
    def project_path(self) -> Path:
        if self._project_path is not None:
            return self._project_path
        if self._repo is not None:
            return self._repo.base_path
        raise RuntimeError("Harness not started — call start() first")

    def start(self) -> None:
        """Start the backend, Vite dev server, browser, and navigate to the home page."""
        logger.info("Starting ManualTestHarness")

        self._screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Create temp directories
        self._sculptor_folder = Path(tempfile.mkdtemp(prefix="sculptor_manual_test_"))
        self._tmp_path = Path(tempfile.mkdtemp(prefix="sculptor_manual_tmp_"))

        # Pre-populate config so onboarding is skipped
        _populate_sculptor_folder(self._sculptor_folder)

        # Create test repo (unless the user provided their own project path)
        if self._project_path is None:
            self._repo = _create_test_repo(self._tmp_path)

        # Get free ports and start the backend + Vite dev server
        self._port_manager = PortManager()
        self._start_backend_and_vite()

        # Launch Playwright browser
        self._playwright = sync_playwright().start()
        # Disable WebGL so xterm.js falls back to its canvas renderer, which renders
        # correctly in headless Chromium (the WebGL addon produces a blank canvas
        # when Chromium's GPU compositor is stubbed out, as it is in --headless=new).
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-webgl",
                "--disable-webgl2",
                *_chromium_shared_memory_args(),
            ],
        )
        self._browser_context = self._browser.new_context(viewport=self._viewport, device_scale_factor=2)
        self._page = self._browser_context.new_page()
        configure_page(self._page, timeout_ms=_DEFAULT_TIMEOUT_MS)

        # Navigate to the Vite dev server (lands on the home page)
        vite_url = f"http://127.0.0.1:{self._vite_port}"
        navigate_to_frontend(page=self._page, url=vite_url)

        logger.info("ManualTestHarness ready — vite_url={}, backend_url={}", vite_url, self.base_url)

    def _wait_for_vite(self, timeout_seconds: int = 120) -> None:
        """Poll until the Vite dev server is accepting connections."""
        vite_url = f"http://127.0.0.1:{self._vite_port}"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                resp = requests.get(vite_url, timeout=_VITE_POLL_REQUEST_TIMEOUT_SECONDS)
                if resp.status_code == 200:
                    logger.info("Vite dev server ready at {}", vite_url)
                    return
            except requests.ConnectionError:
                pass
            if self._vite_process is not None and self._vite_process.poll() is not None:
                raise RuntimeError(f"Vite process exited with code {self._vite_process.returncode}")
            time.sleep(_VITE_POLL_INTERVAL_SECONDS)
        raise TimeoutError(f"Vite dev server did not start within {timeout_seconds}s")

    def _start_backend_and_vite(self) -> None:
        """Allocate ports and start the backend and Vite dev server.

        Requires ``_sculptor_folder``, ``_tmp_path``, and ``_port_manager`` to
        already be initialized (done in ``start()``).  Safe to call again after
        ``_stop_backend()`` / ``_stop_vite()`` / ``_release_ports()`` — used by
        both initial ``start()`` and ``restart()``.
        """
        assert self._port_manager is not None
        assert self._sculptor_folder is not None
        assert self._tmp_path is not None

        repo_path = self.project_path

        self._port = self._port_manager.get_free_port()
        self._vite_port = self._port_manager.get_free_port()

        # Build environment and command
        database_url = f"sqlite:///{self._sculptor_folder / 'sculptor.db'}"
        environment = get_testing_environment(
            database_url=database_url,
            sculptor_folder=self._sculptor_folder,
            tmp_path=self._tmp_path,
            hide_keys=False,
        )
        # Opt-out used by /update-help-docs so screenshots don't include the
        # "Fake Claude" and "Fake Claude 2" test-only models in the model picker.
        # The frontend gates those models on TESTING__INTEGRATION_ENABLED.
        if os.environ.get("SCULPTOR_MANUAL_TEST_HIDE_FAKE_MODELS", "").lower() in ("1", "true", "yes"):
            environment["TESTING__INTEGRATION_ENABLED"] = "false"
        command = get_sculptor_command_backend_only(repo_path, port=self._port)

        # Start the backend
        env = {k: str(v) for k, v in {**os.environ, **environment}.items() if v is not None}
        logger.info("Starting backend on port {}", self._port)
        server_process = start_server_process_and_validate_readiness(command, env)
        self._forwarder = Forwarder(server_process)
        self._forwarder.start()
        self._server = SculptorServer(process=server_process, port=self._port)

        # Start the Vite dev server (proxies API/WS requests to the backend)
        frontend_dir = get_v1_frontend_path()
        vite_env = {
            **os.environ,
            "SCULPTOR_API_PORT": str(self._port),
            "SCULPTOR_FRONTEND_PORT": str(self._vite_port),
        }
        logger.info("Starting Vite dev server on port {} (proxying to backend port {})", self._vite_port, self._port)
        self._vite_process = subprocess.Popen(
            ["pnpm", "run", "dev"],
            cwd=str(frontend_dir),
            env=vite_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
        self._wait_for_vite()

    def _release_ports(self) -> None:
        """Release the backend and Vite ports back to the port manager."""
        if self._port is not None and self._port_manager is not None:
            self._port_manager.release_port(self._port)
            self._port = None
        if self._vite_port is not None and self._port_manager is not None:
            self._port_manager.release_port(self._vite_port)
            self._vite_port = None

    def restart(self) -> None:
        """Restart the backend and Vite dev server, preserving the browser and persisted state.

        Stops the backend and Vite processes, releases their ports, then starts
        fresh instances on new ports. The browser stays open and is navigated to
        the new Vite URL. The database, config, and repo are preserved — this
        simulates a real application restart for testing persistence features.
        """
        logger.info("Restarting ManualTestHarness (preserving browser + data)")

        self._stop_backend()
        self._stop_vite()
        self._release_ports()
        self._start_backend_and_vite()

        # Navigate the existing browser to the new Vite URL
        vite_url = f"http://127.0.0.1:{self._vite_port}"
        navigate_to_frontend(page=self.page, url=vite_url)

        logger.info("ManualTestHarness restarted — vite_url={}, backend_url={}", vite_url, self.base_url)

    def _stop_backend(self) -> None:
        """Stop the backend process and forwarder."""
        if self._server is not None:
            process = self._server.process
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            if self._forwarder is not None:
                self._forwarder.stop()
                self._forwarder = None
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    logger.debug("Failed to close backend stdout during teardown")
            try:
                process.wait(timeout=_BACKEND_SHUTDOWN_TIMEOUT_SECONDS)
            except Exception:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._server = None

    def _stop_vite(self) -> None:
        """Stop the Vite dev server process."""
        if self._vite_process is not None:
            try:
                os.killpg(os.getpgid(self._vite_process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self._vite_process.wait(timeout=_VITE_SHUTDOWN_TIMEOUT_SECONDS)
            except Exception:
                try:
                    os.killpg(os.getpgid(self._vite_process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._vite_process = None

    def stop(self) -> None:
        """Kill the backend and close the browser."""
        logger.info("Stopping ManualTestHarness")

        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                logger.debug("Page already closed")
            self._page = None

        if self._browser_context is not None:
            try:
                self._browser_context.close()
            except Exception:
                logger.debug("Browser context already closed")
            self._browser_context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                logger.debug("Browser already closed")
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                logger.debug("Playwright already stopped")
            self._playwright = None

        self._stop_vite()
        self._stop_backend()
        self._release_ports()

        # Clean up temp directories
        if self._sculptor_folder is not None:
            shutil.rmtree(self._sculptor_folder, ignore_errors=True)
        if self._tmp_path is not None:
            shutil.rmtree(self._tmp_path, ignore_errors=True)

        logger.info("ManualTestHarness stopped")
