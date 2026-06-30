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
from tenacity import RetryCallState
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.port_manager import PortManager
from sculptor.testing.server_utils import get_v1_frontend_path
from sculptor.testing.subprocess_utils import Forwarder

# electron-forge 7.10+ stopped printing its "Launched Electron app" task
# title when stdout is not a TTY, so key on the first line the app's own main
# process logs instead (src/electron/logger.ts emits it at module load).
ELECTRON_READY_MESSAGE = "Logging to temp file:"

_FORGE_LOCK_TIMEOUT_SECONDS = 300
_SLOW_LOCK_WAIT_LOG_THRESHOLD_SECONDS = 1.0
_CDP_CONNECT_TIMEOUT_SECONDS = 120
_CDP_CONNECT_RETRY_INTERVAL_SECONDS = 1
_PROCESS_KILL_TIMEOUT_SECONDS = 5
# Relaunch a few times so a transient esbuild crash doesn't fail the test's setup.
_MAX_ELECTRON_LAUNCH_ATTEMPTS = 3
# esbuild's Go crash dump spans many goroutines; keep enough of the tail that its
# bundler frames survive both for the raised error and the relaunch decision.
_RECENT_OUTPUT_LINES = 200


class _TransientElectronStartError(RuntimeError):
    """Electron exited before its ready message with a transient esbuild dev-bundle crash."""


def _is_known_harmless_electron_error(line: str) -> bool:
    harmless_substrings = [
        "Keychain lookup for suffixed key failed:",
        "Failed to connect to the bus:",
        "Could not bind NETLINK socket",
        "Failed to read /proc/sys/fs/inotify/max_user_watches",
        "X connection error received.",
    ]
    return any(substring in line for substring in harmless_substrings)


def _is_transient_electron_start_crash(output: str) -> bool:
    """Whether the captured Electron output shows esbuild's Go binary crashing at startup.

    ``electron-forge start`` drives the renderer's background dependency
    optimization and the main/preload bundle build over a single shared esbuild
    service. Under that concurrent load — and the CI sandbox's limited CPU/memory —
    the esbuild process intermittently dies with a Go runtime crash dump whose
    goroutine traces name ``github.com/evanw/esbuild``, so the renderer never
    reaches its ready message and forge exits non-zero. Such a launch recovers on a
    fresh attempt.
    """
    return "github.com/evanw/esbuild" in output


def _log_electron_relaunch(retry_state: RetryCallState) -> None:
    """Warn before each relaunch (tenacity ``before_sleep`` hook)."""
    logger.warning(
        "[Electron] dev bundler (esbuild) crashed on launch attempt {}/{}; relaunching",
        retry_state.attempt_number,
        _MAX_ELECTRON_LAUNCH_ATTEMPTS,
    )


class ElectronFrontend:
    def __init__(
        self,
        playwright: Playwright,
        backend_port: int,
        port_manager: PortManager,
        timeout_ms: int,
        custom_backend_cmd: str | None = None,
        extra_env: dict[str, str] | None = None,
        env_unset_keys: tuple[str, ...] = (),
    ) -> None:
        self.playwright = playwright
        self.backend_port = backend_port
        self.port_manager = port_manager
        self.timeout_ms = timeout_ms
        self.custom_backend_cmd = custom_backend_cmd
        self.extra_env = extra_env or {}
        # Keys to drop from the inherited ``os.environ`` before launching Electron.
        # ``extra_env`` can only add/override, so unsetting a parent var (e.g. a
        # SESSION_TOKEN inherited from a Sculptor-spawned terminal) requires
        # excluding it here.
        self.env_unset_keys = env_unset_keys
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
            # Under xvfb there is no real GPU and Chromium's GPU process
            # crash-loops at init; force software rendering so frames are
            # produced deterministically.
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
        inherited_env = {k: v for k, v in os.environ.items() if k not in self.env_unset_keys}
        full_env = {**inherited_env, **self.extra_env, **electron_env}

        frontend_dir = get_v1_frontend_path()
        lock_path = Path("/tmp/sculptor_electron_forge.lock")
        file_lock = FileLock(str(lock_path), timeout=_FORGE_LOCK_TIMEOUT_SECONDS)

        recent_output = self._launch_electron_with_retries(cmd, full_env, frontend_dir, file_lock)

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
            # CDP setup (usually the connect) failed after Electron launched;
            # the bare PlaywrightError gives no hint why the debug port never
            # opened, so attach the process's recent output to the error. Kill
            # first so the tail captures everything up to exit.
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

    @retry(
        stop=stop_after_attempt(_MAX_ELECTRON_LAUNCH_ATTEMPTS),
        retry=retry_if_exception_type(_TransientElectronStartError),
        before_sleep=_log_electron_relaunch,
        reraise=True,
    )
    def _launch_electron_with_retries(
        self,
        cmd: tuple[str, ...],
        full_env: dict[str, str],
        frontend_dir: Path,
        file_lock: FileLock,
    ) -> deque[str]:
        """Launch electron-forge once, returning its recent output when it is ready.

        A transient esbuild dev-bundle crash raises ``_TransientElectronStartError``, which
        the ``@retry`` decorator relaunches on; other startup failures raise a plain
        ``RuntimeError`` and surface immediately.
        """
        is_launched, recent_output = self._start_electron_process(cmd, full_env, frontend_dir, file_lock)
        if is_launched:
            return recent_output
        self._kill_electron()
        exit_code = self._electron_proc.poll() if self._electron_proc is not None else None
        tail = "\n".join(recent_output) or "(no output captured)"
        message = f"Electron frontend failed to start (exit code {exit_code}). Last Electron output:\n{tail}"
        if _is_transient_electron_start_crash(tail):
            raise _TransientElectronStartError(message)
        raise RuntimeError(message)

    def _start_electron_process(
        self,
        cmd: tuple[str, ...],
        full_env: dict[str, str],
        frontend_dir: Path,
        file_lock: FileLock,
    ) -> tuple[bool, deque[str]]:
        """Launch electron-forge once and read stdout until its ready message or exit.

        Returns whether the ready message was seen and the most recent output
        captured. The forge lock serialises this across concurrent test workers.
        """
        recent_output: deque[str] = deque(maxlen=_RECENT_OUTPUT_LINES)
        is_launched = False
        t_lock = time.monotonic()
        file_lock.acquire()
        lock_wait = time.monotonic() - t_lock
        if lock_wait > _SLOW_LOCK_WAIT_LOG_THRESHOLD_SECONDS:
            logger.info("[timing] Electron forge lock wait: {:.2f}s", lock_wait)
        t_proc = time.monotonic()
        try:
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
        return is_launched, recent_output

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
