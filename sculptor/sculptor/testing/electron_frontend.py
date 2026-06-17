import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

from filelock import FileLock
from loguru import logger
from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import Playwright
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.port_manager import PortManager
from sculptor.testing.server_utils import get_v1_frontend_path
from sculptor.testing.subprocess_utils import Forwarder

ELECTRON_READY_MESSAGE = "Launched Electron app"

_FORGE_LOCK_TIMEOUT_SECONDS = 300
_SLOW_LOCK_WAIT_LOG_THRESHOLD_SECONDS = 1.0
_CDP_CONNECT_TIMEOUT_SECONDS = 120
_CDP_CONNECT_RETRY_INTERVAL_SECONDS = 1
_PROCESS_KILL_TIMEOUT_SECONDS = 5


def _is_known_harmless_electron_error(line: str) -> bool:
    harmless_substrings = [
        "Keychain lookup for suffixed key failed:",
        "Failed to connect to the bus:",
        "Could not bind NETLINK socket",
        "Failed to read /proc/sys/fs/inotify/max_user_watches",
        "X connection error received.",
    ]
    return any(substring in line for substring in harmless_substrings)


class ElectronFrontend:
    def __init__(
        self,
        playwright: Playwright,
        backend_port: int,
        port_manager: PortManager,
        timeout_ms: int,
        custom_backend_cmd: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.playwright = playwright
        self.backend_port = backend_port
        self.port_manager = port_manager
        self.timeout_ms = timeout_ms
        self.custom_backend_cmd = custom_backend_cmd
        self.extra_env = extra_env or {}
        self._electron_proc: subprocess.Popen | None = None
        self._forwarder: Forwarder | None = None
        self._user_data_dir: str | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> tuple[BrowserContext, Page]:
        cdp_port = self.port_manager.get_free_port()
        frontend_port = self.port_manager.get_free_port()
        self._user_data_dir = tempfile.mkdtemp(prefix="sculptor_electron_")

        is_headless = sys.platform == "linux" and "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ

        cmd: tuple[str, ...] = (
            "npm",
            "run",
            "electron:start",
            "--",
            "--",
            f"--remote-debugging-port={cdp_port}",
        )

        if os.getuid() == 0:
            cmd = cmd + ("--no-sandbox",)

        if is_headless:
            # Under xvfb there is no real GPU, and Chromium's GPU process then
            # crash-loops at init (gl_context_egl "Failed to get config for
            # surface 0" -> "Exiting GPU process due to errors during
            # initialization"). Force software rendering so frames are produced
            # deterministically instead of relying on that fallback recovering.
            cmd = cmd + ("--disable-gpu",)

        if is_headless:
            cmd = ("xvfb-run", "-a", "-e", "/tmp/xvfb-error.log", "-s", "-screen 0 1600x1000x16") + cmd

        electron_env: dict[str, str] = {
            "SCULPTOR_FRONTEND_PORT": str(frontend_port),
            "SCULPTOR_USER_DATA_DIR": self._user_data_dir,
            "SCULPTOR_ICON_LABEL": "pytest",
            # Load the renderer from the custom sculptor://app origin (the
            # protocol proxies to the Vite dev server) so integration tests
            # exercise the real packaged-app origin without a packaged build.
            "SCULPTOR_USE_APP_SCHEME": "1",
        }
        # In custom command mode, Electron spawns the backend itself via the
        # custom command — so we do NOT set SCULPTOR_API_PORT (the command
        # controls which port the backend listens on).  Instead we pass the
        # command string so Electron enters custom-command mode.
        if self.custom_backend_cmd:
            electron_env["SCULPTOR_CUSTOM_BACKEND_CMD"] = self.custom_backend_cmd
        else:
            electron_env["SCULPTOR_API_PORT"] = str(self.backend_port)
        full_env = {**os.environ, **self.extra_env, **electron_env}

        frontend_dir = get_v1_frontend_path()
        lock_path = Path("/tmp/sculptor_electron_forge.lock")

        is_launched = False
        # Keep the most recent Electron stdout/stderr (stderr is merged into
        # stdout below) so that, if Electron never reaches its ready message, we
        # can surface the actual crash output in the raised error. Offload only
        # streams the failure summary, not the per-sandbox logs, so without this
        # the real reason ("Check logs above") is invisible in CI.
        recent_output: deque[str] = deque(maxlen=50)
        file_lock = FileLock(str(lock_path), timeout=_FORGE_LOCK_TIMEOUT_SECONDS)
        t_lock = time.monotonic()
        file_lock.acquire()
        lock_wait = time.monotonic() - t_lock
        if lock_wait > _SLOW_LOCK_WAIT_LOG_THRESHOLD_SECONDS:
            logger.info("[timing] Electron forge lock wait: {:.2f}s", lock_wait)
        try:
            t_proc = time.monotonic()
            self._electron_proc = subprocess.Popen(
                cmd,
                cwd=frontend_dir,
                env=full_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=lambda: os.setpgid(0, 0),
            )
            assert self._electron_proc.stdout is not None
            for line in self._electron_proc.stdout:
                recent_output.append(line.rstrip())
                logger.info("[Electron stdout] {}", line.rstrip())
                if ELECTRON_READY_MESSAGE in line:
                    is_launched = True
                    self._forwarder = Forwarder(
                        self._electron_proc,
                        prefix="[Electron stdout] ",
                        known_harmless_func=_is_known_harmless_electron_error,
                    )
                    self._forwarder.start()
                    break
        finally:
            file_lock.release()
        logger.info(
            "[timing] Electron process launch (xvfb + Vite + Electron ready): {:.2f}s", time.monotonic() - t_proc
        )

        if not is_launched:
            self._kill_electron()
            exit_code = self._electron_proc.poll() if self._electron_proc is not None else None
            tail = "\n".join(recent_output) or "(no output captured)"
            message = f"Electron frontend failed to start (exit code {exit_code}). Last Electron output:\n{tail}"
            raise RuntimeError(message)

        t_cdp = time.monotonic()
        try:
            retry_connect = retry(
                stop=stop_after_delay(_CDP_CONNECT_TIMEOUT_SECONDS),
                wait=wait_fixed(_CDP_CONNECT_RETRY_INTERVAL_SECONDS),
                retry=retry_if_exception_type(PlaywrightError),
                reraise=True,
            )(lambda: self.playwright.chromium.connect_over_cdp(f"http://localhost:{cdp_port}"))
            browser = retry_connect()

            assert len(browser.contexts) == 1
            context = browser.contexts[0]
            pages = [p for p in context.pages if not p.url.startswith("devtools://")]
            assert len(pages) == 1, f"Expected exactly one non-devtools page, got {pages}"
            page = pages[0]
            configure_page(page, timeout_ms=self.timeout_ms)
        except Exception as exc:
            # Electron reached its ready message (so the launch-failure path
            # above didn't fire), but a later step failed — most often the CDP
            # connect, where the bare PlaywrightError ("connect ECONNREFUSED")
            # gives no hint as to why the debug port never opened. Offload
            # streams only the failure summary, not per-sandbox logs, so without
            # this the real reason is invisible in CI. The Forwarder has been
            # draining stdout (stderr is merged in) since launch, so its tail
            # holds Chromium's own startup output — including the "DevTools
            # listening on ws://..." line that appears iff --remote-debugging-port
            # took effect. Kill first so that tail captures everything up to exit
            # (the deque outlives the forwarder thread).
            self._kill_electron()
            exit_code = self._electron_proc.poll() if self._electron_proc is not None else None
            post_launch = list(self._forwarder.recent_output) if self._forwarder is not None else []
            tail = "\n".join([*recent_output, *post_launch]) or "(no output captured)"
            message = f"Electron launched but CDP setup on port {cdp_port} failed (exit code {exit_code}): {exc}. Last Electron output:\n{tail}"
            raise RuntimeError(message) from exc
        logger.info("[timing] CDP connect + page acquisition: {:.2f}s", time.monotonic() - t_cdp)

        self._browser_context = context
        self._page = page

        return (context, page)

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._kill_electron()
        if self._user_data_dir is not None:
            shutil.rmtree(self._user_data_dir, ignore_errors=True)

    def _kill_electron(self) -> None:
        if self._forwarder is not None:
            self._forwarder.stop()

        if self._electron_proc is None:
            return

        try:
            pgid = os.getpgid(self._electron_proc.pid)

            # Send SIGTERM first so xvfb-run's cleanup trap can remove the
            # X server lock file and socket.  SIGKILL would bypass the trap
            # and leave /tmp/.X{N}-lock behind, breaking subsequent starts.
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

            try:
                self._electron_proc.wait(timeout=_PROCESS_KILL_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                # Process didn't exit gracefully — force-kill as last resort.
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        except (ProcessLookupError, OSError):
            pass

        try:
            if self._electron_proc.stdout:
                self._electron_proc.stdout.close()
        except OSError:
            pass

        try:
            self._electron_proc.wait(timeout=_PROCESS_KILL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass
