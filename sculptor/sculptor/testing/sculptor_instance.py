"""Wraps a running Sculptor instance (backend + browser page) for integration testing.

A SculptorInstance holds all the resources a test needs: the backend server process,
a Playwright page, and the test's git repository. Tests interact with this single
object rather than juggling multiple fixtures.
"""

from __future__ import annotations

import errno
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Generator
from typing import Sequence

import attr
import psutil
import pytest
from loguru import logger
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright

from sculptor.constants import ElementIDs
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.testing.dependency_stubs import install_default_claude_stub
from sculptor.testing.frontend_utils import DEFAULT_TEST_VIEWPORT
from sculptor.testing.mock_repo import MockRepoState
from sculptor.testing.packaged_electron_frontend import PackagedElectronFactory
from sculptor.testing.playwright_utils import delete_all_workspaces_via_ui
from sculptor.testing.playwright_utils import delete_project_via_settings
from sculptor.testing.playwright_utils import expect_app_not_onboarding
from sculptor.testing.playwright_utils import reset_active_panel_to_files
from sculptor.testing.port_manager import PortManager
from sculptor.testing.repo_resources import get_test_project_state
from sculptor.testing.server_utils import SculptorFactory
from sculptor.testing.server_utils import SculptorServer
from sculptor.testing.subprocess_utils import Forwarder

# Default budget the teardown waits for SIGTERM to take effect before
# escalating to SIGKILL on the backend process group. Picked years ago for
# a non-tracing backend that exits within ~1s; we keep it for the common
# path so a hung backend doesn't stall test runs.
_DEFAULT_TEARDOWN_TIMEOUT_SECONDS = 10

# Extended budget when ``--trace-to`` is in the backend's argv. Modeled as
# the time to write out the entire viztracer buffer with a safety factor.
_TEARDOWN_TIMEOUT_SECONDS_WITH_TRACE = 300

# Budget for retrying the between-test repo wipe while a backgrounded workspace
# teardown (SCU-1374) is still mutating `.git`. A worktree teardown finishes in
# well under a second; the generous ceiling is a safety net that stays far below
# the 120s _PRE_TEST_TIMEOUT_SECONDS so a genuinely stuck wipe still surfaces.
_RMTREE_RETRY_BUDGET_SECONDS = 15.0
_RMTREE_RETRY_INTERVAL_SECONDS = 0.05

# errnos that mean the tree was concurrently *repopulated* underneath the
# delete rather than that the delete genuinely failed: a directory we just
# emptied is non-empty again (ENOTEMPTY/EEXIST) or briefly locked (EBUSY)
# because the background ``git worktree remove`` re-created entries inside it.
# These are the mirror image of the FileNotFoundError (entry *vanished*) case
# and, like it, are transient — see _rmtree_tolerating_concurrent_deletion.
_CONCURRENT_REPOPULATION_ERRNOS = frozenset({errno.ENOTEMPTY, errno.EEXIST, errno.EBUSY})


def _teardown_timeout_seconds(args: Sequence[str]) -> int:
    """Pick the SIGTERM→SIGKILL wait budget based on whether the backend was
    launched with ``--trace-to``.

    Extracted as a pure function so it can be unit-tested without standing
    up a real subprocess. Looks for the literal flag (``--trace-to`` or
    ``--trace-to=...``) rather than any arg merely containing the substring,
    so a project path or other arg that happens to include ``trace-to`` does
    not trip the extension.
    """
    for arg in args:
        if arg == "--trace-to" or arg.startswith("--trace-to="):
            return _TEARDOWN_TIMEOUT_SECONDS_WITH_TRACE
    return _DEFAULT_TEARDOWN_TIMEOUT_SECONDS


def _reraise_unless_file_not_found(
    _func: object, _path: str, exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
) -> None:
    """``shutil.rmtree`` ``onerror`` handler that swallows only missing-file errors.

    Used by :func:`_rmtree_tolerating_concurrent_deletion`.  A file that is
    already gone is success for a delete, so ``FileNotFoundError`` is ignored
    (at any depth) while every other error is re-raised so genuine failures are
    not silently masked the way ``ignore_errors=True`` would be.
    """
    exception = exc_info[1]
    if not isinstance(exception, FileNotFoundError):
        raise exception


def _rmtree_tolerating_concurrent_deletion(path: Path) -> None:
    """Recursively delete ``path``, tolerating a concurrent git teardown.

    The between-test repo wipe (``_create_fresh_repo``) races with the
    background workspace-environment teardown introduced in SCU-1374: deleting a
    workspace now runs ``git worktree remove`` (and ``branch -d``) on a
    background thread against ``<project>/.git`` while we are recursively
    removing it here.  That race surfaces two ways, both transient:

    * an entry **vanishes** mid-traversal — ``FileNotFoundError`` at the top
      level or any depth, swallowed by :func:`_reraise_unless_file_not_found`
      (an already-gone file is success for a delete); and
    * a directory we just emptied is **repopulated** by the concurrent git
      process before we can ``rmdir`` it — ``OSError`` with ``ENOTEMPTY`` (and,
      defensively, ``EEXIST``/``EBUSY``).  This is the failure that still broke
      the suite after the first fix only handled the vanishing case.

    The background teardown is short-lived, so we retry the whole delete until
    it succeeds, the tree is gone, or a bounded budget is exhausted — re-raising
    any error outside this race so genuine failures are not masked the way
    ``ignore_errors=True`` would.
    """
    deadline = time.monotonic() + _RMTREE_RETRY_BUDGET_SECONDS
    while True:
        try:
            shutil.rmtree(path, onerror=_reraise_unless_file_not_found)
            return
        except OSError as exception:
            if exception.errno not in _CONCURRENT_REPOPULATION_ERRNOS:
                raise
            # The concurrent git process may have finished the job for us.
            if not path.exists():
                return
            if time.monotonic() >= deadline:
                raise
            time.sleep(_RMTREE_RETRY_INTERVAL_SECONDS)


@attr.s(auto_attribs=True, kw_only=True)
class SculptorInstance:
    """A running Sculptor instance for integration tests.

    Consolidates the backend server, Playwright page, git repo, and data directory
    into a single object.
    """

    server: SculptorServer
    page: Page
    repo: MockRepoState
    sculptor_folder: Path
    fake_bin_dir: Path
    _project_path: Path
    _browser_context: BrowserContext
    _browser: Browser | None = None
    _is_electron: bool = False
    _default_timeout_ms: int = 30_000
    _forwarder: Forwarder | None = None
    _session_token: str | None = None

    @property
    def project_path(self) -> Path:
        """The project directory path the server was started with."""
        return self._project_path

    @property
    def base_url(self) -> str:
        """The base URL of the running Sculptor backend."""
        return self.server.url

    # ------------------------------------------------------------------
    # Between-test cleanup
    # ------------------------------------------------------------------

    def _create_fresh_repo(self) -> None:
        """Reset the project repo to a known state for the next test.

        Rebuilds the repo *in-place* at ``self._project_path`` so the running
        server's file-watchers continue to observe the correct directory.
        """
        repo_dir = self._project_path

        # Wipe existing contents (but keep the directory itself).  A previous
        # test's workspace deletion may still be tearing its environment down on
        # a background thread (SCU-1374) and pruning `.git/worktrees/<name>`, so
        # entries can vanish underneath us — tolerate that rather than crashing
        # the next test's setup.
        for child in repo_dir.iterdir():
            if child.is_dir() and not child.is_symlink():
                _rmtree_tolerating_concurrent_deletion(child)
            else:
                child.unlink(missing_ok=True)

        # Re-initialise from the canonical test project state
        with ConcurrencyGroup(name="fresh_repo") as concurrency_group:
            initial_state = get_test_project_state()
            repo = MockRepoState.build_locally(
                state=initial_state, local_dir=repo_dir, concurrency_group=concurrency_group
            )
        repo.create_reset_and_checkout_branch("testing")
        repo.write_file("src/app.py", "import flask\n\nflask.run()")
        repo.commit("app.py commit", commit_time="2025-01-01T00:00:01")
        repo.write_file("stuff.txt", "stuff")
        repo.commit("Stuff", commit_time="2025-01-01T00:00:02")
        self.repo = repo

    def _delete_extra_projects_via_ui(self) -> None:
        """Delete projects registered by previous tests via the Settings UI.

        Checks the backend API for extra projects (those whose path differs
        from ``self._project_path``), then removes each one through the
        Settings > Repositories UI.
        """
        base_url = self.page.url.split("#")[0].rstrip("/")
        try:
            response = self.page.request.get(f"{base_url}/api/v1/projects/active")
        except Exception:
            return
        if not response.ok:
            return

        initial_path = str(self._project_path.resolve())
        projects = response.json()
        for project in projects:
            project_path = project.get("userGitRepoUrl", "")
            # The initial project's URL is "file://<path>" when started via CLI,
            # but may be stored without a "file://" prefix when re-registered
            # via the UI setup page.  On macOS /var is a symlink to /private/var,
            # so we must resolve both sides to compare actual filesystem paths.
            normalized_project_path = str(Path(project_path.removeprefix("file://")).resolve())
            if normalized_project_path == initial_path:
                continue
            project_name = project.get("name", "")
            if not project_name:
                continue
            delete_project_via_settings(self.page, project_name)

    def _restore_session_cookie(self) -> None:
        """Re-add the session token cookie after clear_cookies() wipes it.

        In custom-command mode the backend requires a session token for API
        calls.  The token is set as a cookie so Playwright's page.request
        calls (used by _pre_test cleanup) authenticate correctly.
        """
        if self._session_token is None:
            return
        self._browser_context.add_cookies(
            [
                {
                    "name": "x-session-token",
                    "value": self._session_token,
                    "url": self.base_url,
                }
            ]
        )

    def _reset_browser_state(self) -> None:
        """Clear all client-side state and reload the SPA.

        Clears localStorage/sessionStorage and reloads the page to destroy
        all in-memory state (Jotai atoms, React Query cache, WebSocket
        connections).  The reload also acts as a natural barrier, giving the
        backend time to finish environment teardown (terminal cleanup, fd
        release) before the next test creates new workspaces.
        """
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

        # Restore the viewport in case a previous test resized it and forgot to
        # restore (as test_prompt_navigator once did, leaking 1600x500 into
        # every later test on the same worker — SCU-481). In Electron/CDP mode
        # this applies an emulation override rather than resizing the native
        # window, but DEFAULT_TEST_VIEWPORT matches the Electron BrowserWindow
        # size so the effect is a no-op at steady state.
        try:
            if self.page.viewport_size != DEFAULT_TEST_VIEWPORT:
                self.page.set_viewport_size(DEFAULT_TEST_VIEWPORT)
        except Exception:
            logger.debug("Failed to restore viewport during reset")

        try:
            self.page.evaluate("localStorage.clear()")
            self.page.evaluate("sessionStorage.clear()")
        except Exception:
            logger.debug("Failed to clear browser storage during reset")

        self._browser_context.clear_cookies()
        self._restore_session_cookie()

        # Navigate through about:blank to fully unload the SPA before
        # loading it fresh.  A direct goto + reload causes the /ws/new
        # redirect loader to fire twice (once on goto, once on reload
        # before the first redirect completes), creating duplicate
        # new-workspace tabs.
        self.page.goto("about:blank")

        # Reset persistent user-config flags only after the previous SPA
        # has been unloaded.  If we PUT the reset while the old page is
        # still alive, a debounced sync hook (e.g. usePanelLayoutSync)
        # can fire afterwards and PUT the full stale config back —
        # silently re-enabling flags like enableInPlaceWorkspaces and
        # breaking the next test.  about:blank tears down the React
        # tree, which cancels those pending timers.
        self._reset_user_config_defaults()

        self.page.goto(f"{self.base_url}#/ws/new")

        # Wait for the Add Workspace page to render — raise if onboarding
        # shows instead (no shared-instance test should trigger onboarding).
        start_task_button = self.page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
        expect_app_not_onboarding(self.page, start_task_button)

        # Verify no workspace tabs leaked through via stale WebSocket updates.
        workspace_tabs = self.page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
        if workspace_tabs.count() > 0:
            logger.debug("Stale workspace tab(s) after reset — deleting via UI")
            delete_all_workspaces_via_ui(self.page)

    # Hard upper bound on _pre_test duration.  If cleanup takes longer than
    # this, something is stuck and we should fail fast rather than hang the
    # entire xdist worker for the rest of the CI session.
    _PRE_TEST_TIMEOUT_SECONDS: float = 120

    def _check_pre_test_timeout(self, step: str, start: float, test_id: str) -> None:
        """Raise if ``_pre_test`` has exceeded its time budget."""
        elapsed = time.monotonic() - start
        if elapsed > self._PRE_TEST_TIMEOUT_SECONDS:
            logger.error(
                "_pre_test timed out after {:.1f}s during '{}' for test {}",
                elapsed,
                step,
                test_id,
            )
            raise RuntimeError(f"_pre_test timed out after {elapsed:.1f}s during '{step}' for test {test_id}")

    def _empty_fake_bin_dir(self) -> None:
        """Remove any fake CLI scripts a previous test dropped into fake_bin_dir.

        The directory itself stays in place so it remains on the backend
        subprocess's PATH; only its contents are cleared.  The default
        ``claude`` stub is re-installed afterwards so the dependency check
        keeps passing.  This runs only on the shared-instance path, which
        rejects ``@stub_dependency`` markers — so unconditional reinstall
        can never clobber a test-owned override.
        """
        for child in self.fake_bin_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        install_default_claude_stub(self.fake_bin_dir)

    def _reset_user_config_defaults(self) -> None:
        """Reset persistent user-config flags that tests may have mutated.

        User config lives on disk and is shared across tests in the same
        instance, so any flag a test enables (enableInPlaceWorkspaces,
        enableCloneWorkspaces, ...) leaks into the next test unless
        reset here. Each flag listed below must default to False in the
        shipping config; add new entries when a test starts toggling a
        new flag.

        Transient PUT failures under load would silently leave a flag stuck,
        so we retry and raise loudly if the reset never succeeds — a leaked
        flag is better caught here than as a failure later.

        After a successful PUT we reload the page so the frontend's in-memory
        userConfigAtom picks up the reset values.  Without the reload, the
        frontend's debounced sync hooks (e.g. usePanelLayoutSync, which fires
        ~2s after any panel change) can write the stale userConfigAtom — still
        carrying the previous test's flags — back to the backend, undoing the
        reset before the test body runs.  See SCU-541 for the original failure.
        """
        base_url = self.base_url.rstrip("/")
        timeout = self._default_timeout_ms
        try:
            response = self.page.request.get(f"{base_url}/api/v1/config", timeout=timeout)
        except Exception:
            logger.warning("Failed to GET /api/v1/config during pre-test cleanup", exc_info=True)
            return
        if not response.ok:
            logger.warning("GET /api/v1/config returned {} during pre-test cleanup", response.status)
            return
        config = response.json()
        # Persistent flags that tests can mutate. Each must be reset between
        # tests because the user config lives on disk in the shared instance.
        flags_to_reset_to_false = (
            "enableInPlaceWorkspaces",
            "enableCloneWorkspaces",
        )
        needs_reset = any(config.get(flag) is not False for flag in flags_to_reset_to_false)
        if not needs_reset:
            return
        for flag in flags_to_reset_to_false:
            config[flag] = False
        last_status: int | None = None
        for attempt in range(3):
            try:
                put_response = self.page.request.put(
                    f"{base_url}/api/v1/config", data={"userConfig": config}, timeout=timeout
                )
                last_status = put_response.status
                if put_response.ok:
                    self.page.reload()
                    self.page.wait_for_load_state("networkidle")
                    return
            except Exception:
                logger.warning("PUT /api/v1/config raised on attempt {}", attempt + 1, exc_info=True)
            self.page.wait_for_timeout(500)
        raise RuntimeError(
            f"Failed to reset experimental flags to False after 3 attempts (last status={last_status}). "
            + "Subsequent tests would run with stale flags; failing fast here."
        )

    def _delete_all_workspaces_via_api(self) -> None:
        """Delete every workspace via direct HTTP calls to the backend.

        Using the API instead of clicking through the UI avoids a race
        condition: when the browser navigates or reloads before the UI-
        triggered DELETE response arrives, the request is aborted (the
        backend may still be mid-transaction), and the subsequent page
        load can hit a transient SQLite error that permanently disables
        the "Create Workspace" button.

        Direct ``page.request`` calls block until the backend responds (with
        an explicit timeout of ``_default_timeout_ms`` per call), guaranteeing
        the transaction is fully committed before we proceed.
        """
        base_url = self.base_url.rstrip("/")
        timeout = self._default_timeout_ms
        try:
            # /workspaces/recent returns all non-deleted workspaces (open and
            # closed) — the underlying SQL query filters ``is_deleted = 0``.
            response = self.page.request.get(f"{base_url}/api/v1/workspaces/recent", timeout=timeout)
        except Exception:
            logger.debug("Failed to list workspaces via API during pre-test cleanup", exc_info=True)
            return
        if not response.ok:
            return

        workspaces = response.json().get("workspaces", [])
        for ws in workspaces:
            ws_id = ws.get("objectId", "")
            if not ws_id or ws.get("isDeleted"):
                continue
            self.page.request.delete(f"{base_url}/api/v1/workspaces/{ws_id}", timeout=timeout)

    def _pre_test(self, request: pytest.FixtureRequest) -> None:
        """Run before each test to set up clean state.

        1. Workspaces: delete all workspaces via direct API calls so we
           block until the backend transaction commits.
        2. Extra projects: delete any projects registered by previous tests
           via Settings > Repositories.
        3. Filesystem state: rebuild the git repo in-place so the running
           server's file-watchers see a clean directory.
        4. Browser reset: clear storage and reload to destroy in-memory atoms
           and give the backend time to finish environment teardown.
        """
        test_id = request.node.nodeid
        logger.info("_pre_test starting for {}", test_id)
        start = time.monotonic()

        # Dismiss any open popover/context menu/dialog left by the previous test.
        self.page.keyboard.press("Escape")
        reset_active_panel_to_files(self.page)
        self._check_pre_test_timeout("reset_active_panel_to_files", start, test_id)

        self._delete_all_workspaces_via_api()
        self._check_pre_test_timeout("delete_all_workspaces_via_api", start, test_id)

        # Note: _reset_user_config_defaults() runs inside _reset_browser_state
        # below, after about:blank has unloaded the previous page's JS.
        # Resetting earlier races with debounced config syncs (e.g.
        # usePanelLayoutSync) that PUT the full stale config and undo the
        # reset.

        self._empty_fake_bin_dir()
        self._check_pre_test_timeout("empty_fake_bin_dir", start, test_id)

        self._delete_extra_projects_via_ui()
        self._check_pre_test_timeout("delete_extra_projects_via_ui", start, test_id)

        self._create_fresh_repo()
        self._check_pre_test_timeout("create_fresh_repo", start, test_id)

        self._reset_browser_state()

        elapsed = time.monotonic() - start
        logger.info("_pre_test completed for {} in {:.1f}s", test_id, elapsed)

    def _post_test(self, request: pytest.FixtureRequest) -> None:
        """If the test failed, kill this instance so a fresh one is created for the next test."""
        call_report = getattr(request.node, "report_call", None)
        if call_report is not None and call_report.failed:
            logger.warning("Test {} failed — tearing down shared instance for recreation", request.node.nodeid)
            self._teardown()
            request.config._sculptor_instance = None

    def hard_kill(self) -> None:
        """SIGKILL the backend process tree with no graceful shutdown.

        Simulates a crash / OOM-kill / power loss: no SIGTERM is delivered, so
        the backend gets no chance to persist a terminal completion for an
        in-flight agent turn. Restart-recovery tests
        call this inside a ``spawn_instance`` block and then spawn a fresh
        instance against the same shared database; the block exit's normal
        teardown tolerates the already-dead tree (its kill/wait calls catch
        ``ProcessLookupError`` / ``NoSuchProcess``).

        Like ``_teardown``, signals each PID in the tree individually via
        psutil rather than using os.killpg, so children that escaped the
        process group (e.g. the agent CLI spawned with
        ``isolate_process_group=True``) are reached too.
        """
        process = self.server.process
        try:
            root = psutil.Process(process.pid)
            victims = [root] + root.children(recursive=True)
        except psutil.NoSuchProcess:
            victims = []
        for p in victims:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        # Wait for the tree to die so the next spawn_instance() never races a
        # half-dead backend on the shared database and port. Fail loudly on
        # survivors -- a silent half-dead tree would surface later as an opaque
        # database/port conflict in the restarted instance.
        _, alive = psutil.wait_procs(victims, timeout=10)
        assert not alive, f"backend processes survived SIGKILL after 10s: {alive}"

    def _teardown(self) -> None:
        """Kill the backend process tree and clean up resources at session end.

        Walks the process tree with psutil and signals each PID individually
        rather than using os.killpg. The Electron AppImage launcher detaches
        its Python sculptor_backend child into its own process group via
        setpgid, so a killpg on the launcher's group does not reach the
        backend. The backend then keeps its end of the stdout pipe open,
        the Forwarder thread's readline() never sees EOF, and
        process.stdout.close() deadlocks against the BufferedReader lock —
        the ~15-minute hang previously observed on arm64 in
        test_release_artifacts_linux_arm64. Killing by PID across the
        whole subtree reaches the backend regardless of its pgid escape;
        waiting for the subtree to exit before closing stdout ensures the
        Forwarder has received EOF and released the lock.
        """
        process = self.server.process
        try:
            root = psutil.Process(process.pid)
            victims = [root] + root.children(recursive=True)
        except psutil.NoSuchProcess:
            victims = []

        for p in victims:
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass

        # SIGTERM→SIGKILL grace period. Extended when the backend is tracing so the
        # full viztracer buffer can flush during graceful shutdown before we escalate
        # to SIGKILL (see _teardown_timeout_seconds).
        teardown_timeout = _teardown_timeout_seconds(process.args)
        _, alive = psutil.wait_procs(victims, timeout=teardown_timeout)
        if alive:
            logger.warning("Teardown: {}/{} processes survived SIGTERM, sending SIGKILL", len(alive), len(victims))
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=5)

        if self._forwarder is not None:
            self._forwarder.stop()

        if process.stdout:
            try:
                process.stdout.close()
            except Exception:
                pass

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

        try:
            self.page.close()
        except Exception:
            logger.debug("Page already closed during teardown")
        try:
            self._browser_context.close()
        except Exception:
            logger.debug("Browser context already closed during teardown")
        # Close the Playwright Browser to kill the Chromium (headless_shell) process.
        # Without this, a test failure that triggers instance recreation via _post_test
        # would leave the old Chromium process alive until session end, leaking ~10
        # processes per failure.
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                logger.debug("Browser already closed during teardown")


@attr.s(auto_attribs=True, kw_only=True)
class SculptorInstanceFactory:
    """Creates isolated Sculptor instances for tests needing restart or custom config.

    Resources (database, sculptor folder, git repo) are shared across all instances
    spawned within a single test. Each spawn_instance() call starts a fresh backend
    process against those shared resources, enabling restart testing while preserving
    data across restarts.

    The underlying spawner can be either a raw backend ``SculptorFactory`` (for
    ``browser`` / ``electron`` launch modes) or a ``PackagedElectronFactory``
    that launches the shipped Electron binary via CDP. Most options behave
    identically; exceptions are documented on individual methods.
    """

    _delegate: SculptorFactory | PackagedElectronFactory
    base_repo: MockRepoState
    fake_bin_dir: Path

    def update_environment(self, sculptor_folder: Path | None = None, **env_overrides: str | None) -> None:
        """Update the environment for subsequent spawn_instance() calls.

        Environment variable overrides are only honoured by the raw backend
        delegate; the packaged-electron delegate freezes its environment at
        construction (the packaged binary launches its own backend child
        process whose env is set once up front).
        """
        if sculptor_folder is not None:
            self._delegate.sculptor_folder = sculptor_folder
        if isinstance(self._delegate, SculptorFactory):
            self._delegate.environment.update(env_overrides)
        elif env_overrides:
            raise NotImplementedError("update_environment env overrides are not supported in packaged-electron mode")

    @contextmanager
    def spawn_instance(
        self,
        *,
        auto_project: bool = True,
        wait_until_ready: bool = True,
    ) -> Generator[SculptorInstance, None, None]:
        """Start a new Sculptor instance and yield a ``SculptorInstance`` wrapping it.

        Args:
            auto_project: When True (default), the backend is started with the
                test repo as its initial project. When False, the backend
                starts with no project — useful for testing onboarding /
                project selection.
            wait_until_ready: When True (default), wait for the app to reach
                a happy steady state (backend healthy + page navigated)
                before yielding. When False, yield as soon as the renderer
                is reachable — use for fatal-startup-error tests that assert
                on renderer state when the backend has exited by design.
                Only supported in packaged-electron mode.
        """
        project_path = self.base_repo.base_path if auto_project else None
        is_electron = isinstance(self._delegate, PackagedElectronFactory)
        with self._delegate.spawn_sculptor_instance(
            project_path=project_path,
            wait_until_ready=wait_until_ready,
        ) as (server, sculptor_page, browser_context, session_token):
            instance = SculptorInstance(
                server=server,
                page=sculptor_page,
                repo=self.base_repo,
                sculptor_folder=self._delegate.sculptor_folder,
                fake_bin_dir=self.fake_bin_dir,
                project_path=self.base_repo.base_path,
                browser_context=browser_context,
                is_electron=is_electron,
                session_token=session_token,
            )
            yield instance


def create_sculptor_instance_factory(
    environment: dict[str, str | None],
    port: int,
    database_url: str,
    default_timeout_ms: int,
    request: pytest.FixtureRequest,
    sculptor_folder: Path,
    base_repo: MockRepoState,
    fake_bin_dir: Path,
) -> SculptorInstanceFactory:
    """Build a SculptorInstanceFactory from fixture-provided parameters."""
    delegate = SculptorFactory(
        environment=environment,
        port=port,
        database_url=database_url,
        default_timeout_ms=default_timeout_ms,
        request=request,
        sculptor_folder=sculptor_folder,
    )
    return SculptorInstanceFactory(
        delegate=delegate,
        base_repo=base_repo,
        fake_bin_dir=fake_bin_dir,
    )


def create_packaged_electron_instance_factory(
    playwright: Playwright,
    binary_path: Path,
    port_manager: PortManager,
    backend_port: int,
    sculptor_folder: Path,
    default_timeout_ms: int,
    base_repo: MockRepoState,
    fake_bin_dir: Path,
    extra_env: dict[str, str] | None = None,
) -> SculptorInstanceFactory:
    """Build a SculptorInstanceFactory backed by the packaged Electron binary."""
    delegate = PackagedElectronFactory(
        playwright=playwright,
        binary_path=binary_path,
        port_manager=port_manager,
        backend_port=backend_port,
        sculptor_folder=sculptor_folder,
        default_timeout_ms=default_timeout_ms,
        extra_env=extra_env,
    )
    return SculptorInstanceFactory(
        delegate=delegate,
        base_repo=base_repo,
        fake_bin_dir=fake_bin_dir,
    )
