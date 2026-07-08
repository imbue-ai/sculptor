from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from typing import Final
from typing import Generator

import pytest
from loguru import logger
from playwright.sync_api import Playwright
from playwright.sync_api import expect
from pytest_playwright.pytest_playwright import ArtifactsRecorder

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.constants import ElementIDs
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.concurrency_group import ConcurrencyGroupState
from sculptor.primitives.ids import create_organization_id
from sculptor.primitives.ids import create_user_id
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import apply_stubs_from_request
from sculptor.testing.dependency_stubs import assert_no_stub_dependency_markers
from sculptor.testing.dependency_stubs import create_claude_stub_dir
from sculptor.testing.dependency_stubs import has_stub_dependency_marker_for
from sculptor.testing.dependency_stubs import install_default_claude_stub
from sculptor.testing.electron_frontend import ElectronFrontend
from sculptor.testing.frontend_utils import DEFAULT_TEST_LOCALE
from sculptor.testing.frontend_utils import DEFAULT_TEST_VIEWPORT
from sculptor.testing.frontend_utils import configure_page
from sculptor.testing.mock_repo import MockRepoState
from sculptor.testing.packaged_backend_frontend import PackagedBackendFrontend
from sculptor.testing.packaged_electron_frontend import PackagedElectronFrontend
from sculptor.testing.playwright_utils import expect_app_not_onboarding
from sculptor.testing.playwright_utils import navigate_to_frontend
from sculptor.testing.port_manager import PortManager
from sculptor.testing.repo_resources import get_test_project_state
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.sculptor_instance import create_packaged_electron_instance_factory
from sculptor.testing.sculptor_instance import create_sculptor_instance_factory
from sculptor.testing.server_utils import SculptorServer
from sculptor.testing.server_utils import get_sculptor_command_backend_only
from sculptor.testing.server_utils import get_testing_environment
from sculptor.testing.server_utils import start_server_process_and_validate_readiness
from sculptor.testing.subprocess_utils import Forwarder
from sculptor.testing.test_repo_factory import TestRepoFactory

# Timeout for the initial SPA render after server startup (shared + factory instances).
# Longer than the default 30s to allow headroom for cold Electron starts on CI.
# Cold Electron startup on the contended shared CI runners (the
# ``integration_tests_electron`` job) regularly takes 50-60s.
_INITIAL_RENDER_TIMEOUT_MS = 90_000


def invalidate_shared_instance(config: pytest.Config) -> None:
    """Tear down the cached shared instance so the next test recreates it.

    Use from session-scoped fixtures that modify process-level state (e.g. env
    vars) which the shared Electron/backend process reads at startup.  The next
    call to ``sculptor_instance_`` will call ``_get_or_create_shared_instance``
    which will see ``None`` and build a fresh process with the current env.
    """
    cached: SculptorInstance | None = getattr(config, "_sculptor_instance", None)
    if cached is not None:
        logger.info("invalidate_shared_instance: tearing down cached instance")
        cached._teardown()
        setattr(config, "_sculptor_instance", None)


@pytest.fixture
def sculptor_instance_(
    request: pytest.FixtureRequest,
) -> Generator[SculptorInstance, None, None]:
    """Provides a shared Sculptor instance for tests, with per-test cleanup.

    The underlying SculptorInstance is session-scoped (cached on request.config) so
    the backend process and browser stay alive across tests.  Each test gets a fresh
    repo and clean UI state via _pre_test / _post_test hooks.
    """
    # The shared fixture doesn't honour @stub_dependency markers (the backend
    # process is session-scoped with a baked-in claude stub, and _empty_fake_bin_dir
    # re-installs the default between tests).  Fail loudly rather than silently
    # ignore a test's explicit preference — such tests must use the factory fixture.
    assert_no_stub_dependency_markers(request)

    instance = _get_or_create_shared_instance(request)

    # Start artifact recording (including Playwright tracing) *before* _pre_test
    # so that setup failures produce a trace.zip with network/DOM diagnostics.
    artifacts_recorder: ArtifactsRecorder = request.getfixturevalue("_artifacts_recorder")
    artifacts_recorder.on_did_create_browser_context(instance._browser_context)
    try:
        # Group _pre_test actions so the Trace Viewer shows them as a
        # collapsible section separate from the test body.
        instance._browser_context.tracing.group("_pre_test cleanup")
        try:
            instance._pre_test(request)
        finally:
            instance._browser_context.tracing.group_end()
        yield instance
    finally:
        artifacts_recorder.on_will_close_browser_context(instance._browser_context)

    instance._post_test(request)


@pytest.fixture
def sculptor_instance_empty_first_run_(
    sculptor_instance_: SculptorInstance,
) -> SculptorInstance:
    """Shared instance settled on the first-run auto-opened new-workspace dialog.

    The shared ``sculptor_instance_``'s per-test reset ends settled on Home
    with one repo and zero workspaces, having already waited out and dismissed
    the first-run offer so ordinary tests never race its modal overlay. The
    offer fires whenever Home mounts over an empty (loaded) workspace list,
    and the reset's dismissal spent this mount's offer — so remount Home by
    hopping through Settings and back. The hops are hash-only navigations
    within the running SPA (no reboot — a full reload would re-race the whole
    boot path for nothing), and the workspace list is already loaded and
    empty, so returning to Home re-offers the dialog immediately with the
    ``/sculptor:help`` onboarding prompt prefilled.
    """
    page = sculptor_instance_.page
    page.evaluate("window.location.hash = '/settings'")
    # Wait for Settings to render before hopping back: two back-to-back hash
    # assignments can coalesce into one router update, which would leave Home
    # mounted throughout and never re-fire its offer.
    expect(page.get_by_test_id(ElementIDs.SETTINGS_PAGE)).to_be_visible()
    page.evaluate("window.location.hash = '/home'")
    expect(page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)).to_be_visible(timeout=45_000)
    return sculptor_instance_


def _get_packaged_binary_path(config: pytest.Config) -> Path:
    """Return the verified ``--packaged-binary-path`` from the pytest config.

    Centralised so the option is only read from one spot; both the session-
    scoped packaged fixture and the per-test factory path go through here.
    Fails loudly if the option was not provided or the path doesn't exist.
    """
    binary_path_str = config.getoption("--packaged-binary-path")
    if not binary_path_str:
        pytest.fail("--packaged-binary-path is required when running against a packaged Sculptor build")
    binary_path = Path(binary_path_str)
    if not binary_path.exists():
        raise FileNotFoundError(f"Packaged binary not found at: {binary_path}")
    return binary_path


def _create_initial_repo(name: str, tmp_path: Path) -> MockRepoState:
    """Create the initial test git repo with a single commit on a branch and no remote."""
    repo_dir = tmp_path / "initial_repo"
    initial_state = get_test_project_state()
    with ConcurrencyGroup(name=name) as cg:
        repo = MockRepoState.build_locally(state=initial_state, local_dir=repo_dir, concurrency_group=cg)
    repo.create_reset_and_checkout_branch("testing")
    repo.write_file("src/app.py", "import flask\n\nflask.run()")
    repo.commit("app.py commit", commit_time="2025-01-01T00:00:01")
    repo.write_file("stuff.txt", "stuff")
    repo.commit("Stuff", commit_time="2025-01-01T00:00:02")
    return repo


def _get_or_create_shared_instance(
    request: pytest.FixtureRequest,
) -> SculptorInstance:
    """Return the cached SculptorInstance, creating it on first call."""
    config = request.config
    cached: SculptorInstance | None = getattr(config, "_sculptor_instance", None)
    if cached is not None:
        return cached

    # -- First call: create all session-level resources --
    launch_mode = request.config.getoption("--sculptor-launch-mode", default="browser")
    use_electron = launch_mode in ("electron", "electron-custom-command")
    use_custom_command = launch_mode == "electron-custom-command"
    use_packaged = launch_mode in ("packaged-electron", "packaged-backend")

    port_manager = PortManager()
    backend_port = port_manager.get_free_port()

    sculptor_folder = Path(tempfile.mkdtemp(prefix="sculptor_test_"))
    tmp_path = Path(tempfile.mkdtemp(prefix="sculptor_tmp_"))
    default_timeout_ms = _DEFAULT_TIMEOUT_MS

    # Temp directories
    # Create a fake bin directory and prepend it to PATH before spawning the
    # backend subprocess, so tests can drop fake CLIs (e.g. gh) into the
    # directory at any time and have the running backend find them via PATH
    # lookup without needing a process restart.
    fake_bin_dir = tmp_path / "fake_bin"
    fake_bin_dir.mkdir()
    os.environ["PATH"] = f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    # Pre-install the default claude stub and configure the user config to
    # point at it via its absolute path.  Using an absolute path (not a bare
    # command name) avoids PATH-ordering races: the PTY process prepends dirs
    # to PATH when spawning agent tasks, which can push the real claude binary
    # ahead of the stub in the search order.
    claude_stub_path = str(install_default_claude_stub(fake_bin_dir))

    _default_sculptor_folder_populator(sculptor_folder, claude_path=claude_stub_path)

    # Create initial repo
    initial_repo = _create_initial_repo("shared_instance_repo", tmp_path)
    repo_path = initial_repo.base_path

    playwright: Playwright = request.getfixturevalue("playwright")

    if use_packaged:
        instance = _create_packaged_instance(
            config=config,
            request=request,
            playwright=playwright,
            port_manager=port_manager,
            backend_port=backend_port,
            sculptor_folder=sculptor_folder,
            tmp_path=tmp_path,
            fake_bin_dir=fake_bin_dir,
            default_timeout_ms=default_timeout_ms,
            initial_repo=initial_repo,
            repo_path=repo_path,
            launch_mode=launch_mode,
        )
        return instance

    database_url = f"sqlite:///{sculptor_folder / 'sculptor.db'}"

    environment = get_testing_environment(
        database_url=database_url,
        sculptor_folder=sculptor_folder,
        tmp_path=tmp_path,
        hide_keys=True,
    )

    if use_custom_command:
        instance = _create_custom_command_instance(
            config=config,
            request=request,
            playwright=playwright,
            port_manager=port_manager,
            backend_port=backend_port,
            sculptor_folder=sculptor_folder,
            tmp_path=tmp_path,
            fake_bin_dir=fake_bin_dir,
            default_timeout_ms=default_timeout_ms,
            initial_repo=initial_repo,
            repo_path=repo_path,
            environment=environment,
        )
        return instance

    # Build command
    command = get_sculptor_command_backend_only(repo_path, port=backend_port)
    # Opt-in tracing: only the shared-fixture path consults
    # ``--sculptor-trace-to`` because the ``just test-tracing`` recipe targets a
    # single test that uses ``sculptor_instance_``. If a future tracing scenario
    # needs the factory or packaged paths, plumb the flag through those
    # command-building sites the same way.
    trace_to_path = request.config.getoption("--sculptor-trace-to", default=None)
    if trace_to_path:
        command = command + (f"--trace-to={trace_to_path}",)

    # Start the backend process
    t0 = time.monotonic()
    env = {k: str(v) for k, v in {**os.environ, **environment}.items() if v is not None}
    server_process = start_server_process_and_validate_readiness(command, env)
    forwarder = Forwarder(server_process)
    forwarder.start()
    server = SculptorServer(process=server_process, port=backend_port)
    logger.info("[timing] Backend startup: {:.2f}s", time.monotonic() - t0)

    # Launch the frontend (browser or Electron)
    t1 = time.monotonic()
    if use_electron:
        electron_frontend = ElectronFrontend(
            playwright=playwright,
            backend_port=backend_port,
            port_manager=port_manager,
            timeout_ms=default_timeout_ms,
        )
        browser_context, page = electron_frontend.__enter__()
        browser = None
    else:
        electron_frontend = None
        browser = playwright.chromium.launch()
        browser_context = browser.new_context(viewport=DEFAULT_TEST_VIEWPORT, locale=DEFAULT_TEST_LOCALE)
        page = browser_context.new_page()
        configure_page(page, timeout_ms=default_timeout_ms)
        navigate_to_frontend(page=page, url=server.url)
    logger.info(
        "[timing] Frontend launch ({}): {:.2f}s", "electron" if use_electron else "browser", time.monotonic() - t1
    )

    # Wait for the React SPA to render before interacting with the UI.
    # Use a longer timeout than the default 30s for this initial check to
    # allow headroom for cold Electron starts on CI.
    t2 = time.monotonic()
    # The sidebar rail is rendered by AppShell on every in-app destination, but
    # not by the onboarding wizard — so it is the universal
    # "app rendered, not onboarding" signal in the new shell.
    app_ready = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    try:
        expect_app_not_onboarding(page, app_ready, timeout=_INITIAL_RENDER_TIMEOUT_MS)
    except Exception:
        logger.warning("[timing] SPA render failed after {:.2f}s", time.monotonic() - t2)
        if electron_frontend is not None:
            electron_frontend.__exit__(None, None, None)
        raise
    logger.info("[timing] SPA initial render: {:.2f}s", time.monotonic() - t2)
    logger.info("[timing] Total instance startup: {:.2f}s", time.monotonic() - t0)

    # Capture the SPA's own origin (sculptor://app in Electron, the backend URL
    # in browser mode) now that it has rendered, so between-test resets navigate
    # to the renderer rather than the backend API URL.
    frontend_url = page.url.split("#")[0].rstrip("/")

    # Build the instance
    instance = SculptorInstance(
        server=server,
        page=page,
        frontend_url=frontend_url,
        repo=initial_repo,
        sculptor_folder=sculptor_folder,
        fake_bin_dir=fake_bin_dir,
        project_path=repo_path,
        browser_context=browser_context,
        browser=browser,
        is_electron=use_electron,
        default_timeout_ms=default_timeout_ms,
        forwarder=forwarder,
    )

    # Cache on config for session reuse
    config._sculptor_instance = instance
    if use_electron:
        config._electron_frontend = electron_frontend

    # Register session-level teardown via pytest finalizer (not atexit) so it
    # runs while Playwright's session fixtures are still alive.
    def _session_teardown() -> None:
        # _teardown() closes the current page and browser context.
        instance._teardown()
        if browser is not None:
            try:
                browser.close()
            except Exception:
                logger.debug("Browser already closed during teardown")
        if use_electron:
            electron_frontend_instance = getattr(config, "_electron_frontend", None)
            if electron_frontend_instance is not None:
                try:
                    electron_frontend_instance.__exit__(None, None, None)
                except Exception:
                    logger.debug("ElectronFrontend cleanup error during teardown")
        shutil.rmtree(sculptor_folder, ignore_errors=True)
        shutil.rmtree(tmp_path, ignore_errors=True)

    request.session.addfinalizer(_session_teardown)

    return instance


def _create_packaged_instance(
    config: pytest.Config,
    request: pytest.FixtureRequest,
    playwright: Playwright,
    port_manager: PortManager,
    backend_port: int,
    sculptor_folder: Path,
    tmp_path: Path,
    fake_bin_dir: Path,
    default_timeout_ms: int,
    initial_repo: MockRepoState,
    repo_path: Path,
    launch_mode: str,
) -> SculptorInstance:
    """Create a SculptorInstance backed by a packaged Sculptor binary.

    When launch_mode is 'packaged-electron', launches the full Electron binary
    with CDP (Linux). When 'packaged-backend', launches sculptor_backend directly
    with a standalone headless Chromium (macOS / headless environments).
    """
    binary_path = _get_packaged_binary_path(config)

    # Place a stub `claude` binary on PATH so the packaged app's dependency
    # check sees claude as installed and gets past the onboarding screen.
    claude_stub_dir = create_claude_stub_dir(tmp_path)
    original_path = os.environ.get("PATH", "")
    extra_env = {"PATH": f"{claude_stub_dir}{os.pathsep}{original_path}"}

    packaged_frontend: PackagedElectronFrontend | PackagedBackendFrontend
    if launch_mode == "packaged-electron":
        cdp_port = port_manager.get_free_port()
        user_data_dir = Path(tempfile.mkdtemp(prefix="sculptor_packaged_"))
        packaged_frontend = PackagedElectronFrontend(
            playwright=playwright,
            binary_path=binary_path,
            backend_port=backend_port,
            cdp_port=cdp_port,
            sculptor_folder=sculptor_folder,
            user_data_dir=user_data_dir,
            timeout_ms=default_timeout_ms,
            extra_env=extra_env,
        )
    else:
        packaged_frontend = PackagedBackendFrontend(
            playwright=playwright,
            binary_path=binary_path,
            backend_port=backend_port,
            sculptor_folder=sculptor_folder,
            timeout_ms=default_timeout_ms,
            extra_env=extra_env,
        )

    browser_context, page = packaged_frontend.__enter__()

    # Add the session token as a cookie so that Playwright's page.request API
    # (used by SculptorInstance._pre_test for cleanup) authenticates correctly.
    browser_context.add_cookies(
        [
            {
                "name": "x-session-token",
                "value": packaged_frontend.session_token,
                "url": f"http://127.0.0.1:{backend_port}",
            }
        ]
    )

    # Create a SculptorServer wrapping the primary process.
    # For packaged-electron, this is the Electron process (which manages the backend).
    # For packaged-backend, this is the backend process itself.
    if isinstance(packaged_frontend, PackagedElectronFrontend):
        server = SculptorServer(process=packaged_frontend._electron_proc, port=backend_port)
        is_electron = True
    else:
        server = SculptorServer(process=packaged_frontend._backend_proc, port=backend_port)
        is_electron = False

    # Register the test project. Without this the app lands on /setup (no projects).
    packaged_frontend.register_project(repo_path)

    # Full-reload to the root URL so the SPA rootLoader re-evaluates routing.
    # It will call getActiveProjects(), find the newly registered project,
    # and redirect to /ws/new.  We navigate to the bare URL (no hash) so
    # the hash router starts at "/" and the rootLoader fires.  The previous
    # approach of page.goto("#/ws/new") + page.reload() was unreliable in
    # CDP mode: the hash-only goto could race with reload, leaving the page
    # stuck on #/setup.
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto(base_url, wait_until="networkidle")

    # Wait for the SPA to render — raise if onboarding shows instead of the main app.
    logger.info("Waiting for SPA to render (checking for the sidebar rail or onboarding)")
    app_ready = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    try:
        expect_app_not_onboarding(page, app_ready, timeout=_INITIAL_RENDER_TIMEOUT_MS)
    except Exception:
        logger.error("SPA render failed. Page URL: {}", page.url)
        logger.error("Page content preview: {}", page.content()[:2000])
        packaged_frontend.__exit__(None, None, None)
        raise
    logger.info("SPA rendered successfully")

    instance = SculptorInstance(
        server=server,
        page=page,
        # base_url above was derived from page.url, so it is the SPA's origin.
        frontend_url=base_url,
        repo=initial_repo,
        sculptor_folder=sculptor_folder,
        fake_bin_dir=fake_bin_dir,
        project_path=repo_path,
        browser_context=browser_context,
        browser=None,
        is_electron=is_electron,
        default_timeout_ms=default_timeout_ms,
        forwarder=None,
        # Packaged-electron enforces the session token, so page.request cleanup and
        # test-body API calls authenticate via the x-session-token cookie set above.
        # _reset_browser_state clears all cookies before every test and relies on
        # _restore_session_cookie to re-add this one — which no-ops unless the token
        # is threaded in here. Without it the cookie is gone for the whole test body
        # and every page.request 403s.
        session_token=packaged_frontend.session_token,
    )

    setattr(config, "_sculptor_instance", instance)
    setattr(config, "_packaged_frontend", packaged_frontend)

    request.session.addfinalizer(
        lambda: _packaged_session_teardown(instance, packaged_frontend, sculptor_folder, tmp_path)
    )

    return instance


def _packaged_session_teardown(
    instance: SculptorInstance,
    packaged_frontend: PackagedElectronFrontend | PackagedBackendFrontend,
    sculptor_folder: Path,
    tmp_path: Path,
) -> None:
    instance._teardown()
    try:
        packaged_frontend.__exit__(None, None, None)
    except Exception:
        logger.debug("Packaged frontend cleanup error during teardown")
    shutil.rmtree(sculptor_folder, ignore_errors=True)
    shutil.rmtree(tmp_path, ignore_errors=True)


def _create_custom_command_instance(
    config: pytest.Config,
    request: pytest.FixtureRequest,
    playwright: Playwright,
    port_manager: PortManager,
    backend_port: int,
    sculptor_folder: Path,
    tmp_path: Path,
    fake_bin_dir: Path,
    default_timeout_ms: int,
    initial_repo: MockRepoState,
    repo_path: Path,
    environment: dict[str, str | None],
) -> SculptorInstance:
    """Create a SculptorInstance where Electron manages the backend via a custom command.

    Instead of starting the backend separately, we pass a shell command to
    Electron via SCULPTOR_CUSTOM_BACKEND_CMD.  Electron spawns the command,
    reads a URL from its stdout, and enters custom-command mode where file
    uploads use HTTP instead of Electron IPC.
    """
    # Build a custom command that prints the URL then execs the backend.
    # Use sys.executable so the custom command runs in the same virtualenv
    # as the test process (the Electron child inherits a different PATH).
    python = sys.executable
    custom_backend_cmd = f"echo http://localhost:{backend_port} && exec {python} -m sculptor.cli.main --no-open-browser --port {backend_port} {repo_path}"

    # Convert the testing environment dict to strings, filtering out None
    # values (which represent env vars to unset).  These are passed as
    # extra_env so the custom command inherits them.
    extra_env = {k: str(v) for k, v in environment.items() if v is not None}

    # Generate a known session token so Playwright's page.request calls can
    # authenticate against the backend (which requires the token in custom
    # command mode).  Electron will use this instead of generating a random one.
    session_token = os.urandom(32).hex()
    extra_env["SCULPTOR_SESSION_TOKEN"] = session_token

    electron_frontend = ElectronFrontend(
        playwright=playwright,
        backend_port=backend_port,
        port_manager=port_manager,
        timeout_ms=default_timeout_ms,
        custom_backend_cmd=custom_backend_cmd,
        extra_env=extra_env,
    )
    browser_context, page = electron_frontend.__enter__()

    # Add the session token as a cookie so that Playwright's page.request API
    # (used by SculptorInstance._pre_test for cleanup) authenticates correctly.
    browser_context.add_cookies(
        [
            {
                "name": "x-session-token",
                "value": session_token,
                "url": f"http://127.0.0.1:{backend_port}",
            }
        ]
    )

    # Wait for the React SPA to render (the sidebar rail is the new shell's universal
    # "app rendered" signal — present on every in-app route).
    try:
        expect(page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)).to_be_visible()
    except Exception:
        electron_frontend.__exit__(None, None, None)
        raise

    # The backend is a child of the Electron process.  Wrap the Electron
    # process in SculptorServer so teardown kills the entire tree.
    assert electron_frontend._electron_proc is not None
    server = SculptorServer(process=electron_frontend._electron_proc, port=backend_port)

    instance = SculptorInstance(
        server=server,
        page=page,
        frontend_url=page.url.split("#")[0].rstrip("/"),
        repo=initial_repo,
        sculptor_folder=sculptor_folder,
        fake_bin_dir=fake_bin_dir,
        project_path=repo_path,
        browser_context=browser_context,
        browser=None,
        is_electron=True,
        default_timeout_ms=default_timeout_ms,
        forwarder=None,
        session_token=session_token,
    )

    setattr(config, "_sculptor_instance", instance)
    setattr(config, "_electron_frontend", electron_frontend)

    request.session.addfinalizer(
        lambda: _custom_command_session_teardown(instance, electron_frontend, sculptor_folder, tmp_path)
    )

    return instance


def _custom_command_session_teardown(
    instance: SculptorInstance,
    electron_frontend: ElectronFrontend,
    sculptor_folder: Path,
    tmp_path: Path,
) -> None:
    instance._teardown()
    try:
        electron_frontend.__exit__(None, None, None)
    except Exception:
        logger.debug("ElectronFrontend cleanup error during teardown")
    shutil.rmtree(sculptor_folder, ignore_errors=True)
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def sculptor_instance_factory_(
    request: pytest.FixtureRequest,
    playwright: Playwright,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[SculptorInstanceFactory, None, None]:
    """Provides a factory for creating isolated Sculptor instances.

    Each test gets fully independent resources (database, sculptor folder, repo,
    backend port).  Use this when a test needs to stop/restart Sculptor or
    requires custom configuration that cannot be shared.

    Mutually exclusive with sculptor_instance_.
    """
    if hasattr(request, "fixturenames") and "sculptor_instance_" in request.fixturenames:
        pytest.fail("Cannot use both sculptor_instance_ and sculptor_instance_factory_ in the same test")

    launch_mode = request.config.getoption("--sculptor-launch-mode", default="browser")
    if launch_mode == "packaged-backend":
        pytest.fail(
            "sculptor_instance_factory_ is not supported in packaged-backend mode."
            + " Use sculptor_instance_ instead, or run with"
            + " --sculptor-launch-mode=packaged-electron if the platform and environment support it."
        )

    port_manager = PortManager()
    backend_port = port_manager.get_free_port()

    sculptor_folder = Path(tempfile.mkdtemp(prefix="sculptor_factory_test_"))
    folder_populator: CustomFolderPopulator = (
        _extract_marker_arg(request, custom_sculptor_folder_populator) or _default_sculptor_folder_populator
    )
    folder_populator(sculptor_folder)

    # Align the DB path with where the packaged backend looks
    # ({SCULPTOR_FOLDER}/internal/database.db, derived in
    # get_sculptor_folder) so populators that pre-seed a database work in
    # both browser and packaged-electron modes.
    database_url = f"sqlite:///{sculptor_folder / 'internal' / 'database.db'}"

    default_timeout_ms = _DEFAULT_TIMEOUT_MS

    base_repo = _create_initial_repo("factory_instance_repo", tmp_path)

    # Fake bin directory for test-owned CLI stubs; prepended to PATH so the
    # backend subprocesses this factory spawns find anything tests drop in.
    # The subprocesses (raw backend in browser mode, packaged binary in
    # packaged-electron mode) inherit PATH from os.environ when spawned, so
    # we actually do need to mutate the process-global value rather than
    # just building a local dict.  monkeypatch.setenv restores the
    # previous value at test teardown, so this is pollution-safe.
    fake_bin_dir = tmp_path / "fake_bin"
    fake_bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    # Pre-install the default claude stub so factory instances always see a
    # valid version, regardless of what's on PATH (the real binary may be
    # version-mismatched on CI runners).  Skip when the test overrides via
    # @stub_dependency("claude", ...) — apply_stubs_from_request installs its
    # own stub further down, and we must not clobber it.
    if not has_stub_dependency_marker_for(request, "claude"):
        install_default_claude_stub(fake_bin_dir)

    if launch_mode == "packaged-electron":
        binary_path = _get_packaged_binary_path(request.config)
        # The packaged binary inherits PATH via extra_env, so its dependency
        # check sees the claude stub just like raw backend subprocesses do.
        extra_env = {"PATH": os.environ["PATH"]}
        factory = create_packaged_electron_instance_factory(
            playwright=playwright,
            binary_path=binary_path,
            port_manager=port_manager,
            backend_port=backend_port,
            sculptor_folder=sculptor_folder,
            default_timeout_ms=default_timeout_ms,
            base_repo=base_repo,
            fake_bin_dir=fake_bin_dir,
            extra_env=extra_env,
        )
        yield factory
        return

    environment = get_testing_environment(
        database_url=database_url,
        sculptor_folder=sculptor_folder,
        tmp_path=tmp_path,
        hide_keys=True,
    )

    # Apply @stub_dependency markers to the environment
    apply_stubs_from_request(request, environment, tmp_path)

    factory = create_sculptor_instance_factory(
        environment=environment,
        port=backend_port,
        database_url=database_url,
        default_timeout_ms=default_timeout_ms,
        request=request,
        sculptor_folder=sculptor_folder,
        base_repo=base_repo,
        fake_bin_dir=fake_bin_dir,
    )

    yield factory


CustomFolderPopulator = Callable[[Path], None]
custom_sculptor_folder_populator = pytest.mark.custom_sculptor_folder


def _make_test_user_config(claude_path: str = "claude") -> UserConfig:
    """Create a UserConfig with test defaults."""
    test_email = "test@imbue.com"
    return UserConfig(
        user_email=test_email,
        user_id=create_user_id(test_email),
        organization_id=create_organization_id(test_email),
        instance_id=hashlib.md5(os.urandom(64)).hexdigest(),
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_session_recording_enabled=True,
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
        # Pin pi to CUSTOM (bare "pi") so it resolves the FakePi stub on PATH without touching the managed-copy directory.
        dependency_paths=DependencyPaths(claude=claude_path, pi="pi"),
    )


def _default_sculptor_folder_populator(folder_path: Path, claude_path: str = "claude") -> None:
    internal_dir = folder_path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    config_path = internal_dir / "config.toml"
    config = _make_test_user_config(claude_path=claude_path)
    save_config(config, config_path)


def _extract_marker_arg(request: pytest.FixtureRequest, marker: pytest.MarkDecorator) -> Callable | None:
    marker = request.node.get_closest_marker(marker.name)
    return marker.args[0] if marker else None


@pytest.fixture
def test_repo_factory_(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> Generator[TestRepoFactory, None, None]:
    """
    Factory fixture for creating test repositories on demand.

    This fixture provides a function that tests can call multiple times
    to create separate test repositories with different configurations.
    Each repository is created in a temporary directory that's automatically
    cleaned up after the test.

    Usage:
        def test_something(test_repo_factory):
            repo1 = test_repo_factory("project1", "main")
            repo2 = test_repo_factory("project2", "develop")
    """
    factory = TestRepoFactory(base_path=tmp_path, concurrency_group=test_root_concurrency_group)
    yield factory


_DEFAULT_TIMEOUT_MS: Final[int] = 30_000


class AlreadyRunningServiceCollection(CompleteServiceCollection):
    """Wraps an existing already-started CompleteServiceCollection to prevent multiple run_all calls.

    This makes re-using the same service collection in the same process through the FastAPI mock client possible,
    as otherwise the app's lifespan middleware would restart it repeatedly & fail due to our db lock (among other things).

    For single-process integration tests. For more e2e tests use sculptor_factory_ instead.
    """

    @classmethod
    def build(cls, from_collection: CompleteServiceCollection) -> "AlreadyRunningServiceCollection":
        assert from_collection.data_model_service.concurrency_group._state == ConcurrencyGroupState.ACTIVE
        return cls(
            settings=from_collection.settings,
            data_model_service=from_collection.data_model_service,
            dependency_management_service=from_collection.dependency_management_service,
            workspace_service=from_collection.workspace_service,
            git_repo_service=from_collection.git_repo_service,
            task_service=from_collection.task_service,
            project_service=from_collection.project_service,
            pr_polling_service=from_collection.pr_polling_service,
            btw_service=from_collection.btw_service,
            ci_babysitter_service=from_collection.ci_babysitter_service,
            pi_login_service=from_collection.pi_login_service,
        )

    @contextmanager
    def run_all(self) -> Generator[None, None, None]:
        yield
