from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Generator

import pytest
from loguru import logger
from playwright.sync_api import Page
from syrupy.assertion import SnapshotAssertion
from xdist import get_xdist_worker_id
from xdist import is_xdist_worker

from sculptor.config.user_config_fixture import populate_config_file_for_test
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.default_implementation import populate_credentials_file
from sculptor.testing.caching_utils import get_cache_dir_from_snapshot
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import GitCommitSnapshot
from sculptor.testing.mock_repo import MockRepoState
from sculptor.testing.multi_tab_page_factory import MultiTabPageFactory
from sculptor.testing.repo_resources import generate_test_project_repo
from sculptor.testing.server_utils import SERVERS
from sculptor.testing.server_utils import SculptorFactory
from sculptor.testing.server_utils import build_or_wait_for_dist
from sculptor.testing.server_utils import get_sculptor_command_v1
from sculptor.testing.server_utils import get_testing_container_prefix
from sculptor.testing.server_utils import get_testing_environment
from sculptor.testing.server_utils import get_v1_frontend_path
from sculptor.testing.test_repo_factory import TestRepoFactory


@pytest.fixture(
    params=[pytest.param(server.key, marks=[getattr(pytest.mark, server.key)]) for server in SERVERS], scope="session"
)
def sculptor_server_key_(request: pytest.FixtureRequest, worker_id: str) -> Generator[str]:
    # setup_once() in tests/conftest.py takes care of building a clean install.
    # Here, we just take care of building the dist if we should.

    dist_needed = "dist" in request.param
    if dist_needed:
        if request.config.getoption("--skip-build-artifacts"):
            logger.info("Your tests required a dist and this cannot be skipped", request.param)

        with build_or_wait_for_dist(worker_id):
            yield request.param
    else:
        yield request.param
    # No cleanup here. If we should cleanup, teardown_once() will take care of it.


class TestingMode(StrEnum):
    ACCEPTANCE = "acceptance"
    INTEGRATION = "integration"


@pytest.fixture(
    params=[
        *(
            []
            if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t")
            else [pytest.param(TestingMode.ACCEPTANCE, marks=pytest.mark.acceptance)]
        ),
        pytest.param(TestingMode.INTEGRATION, marks=[pytest.mark.integration]),
    ],
    scope="session",
)
def testing_mode_(request: pytest.FixtureRequest) -> Generator[TestingMode]:
    yield request.param


@pytest.fixture
def pure_local_repo_(request: pytest.FixtureRequest) -> Generator[MockRepoState, None, None]:
    """Creates a local repository with a single commit on a branch and no remote.

    The repo is constructed from scratch, so it's actually very fast."""
    with generate_test_project_repo(request) as repo:
        repo.create_reset_and_checkout_branch("testing")
        repo.write_file("src/app.py", "import flask\n\nflask.run()")
        repo.commit("app.py commit", commit_time="2025-01-01T00:00:01")
        # make a second commit to make sure we don't try to run stuff on a commit without the config files..
        repo.write_file("stuff.txt", "stuff")
        repo.commit("Stuff", commit_time="2025-01-01T00:00:02")
        yield repo
        logger.info("Cleaning up repo at {}", repo.base_path)


@pytest.fixture
def pure_local_repo_with_checks_(request: pytest.FixtureRequest) -> Generator[MockRepoState, None, None]:
    """Creates a local repository with checks configuration included.

    Use this fixture for tests that need checks to be available."""
    with tempfile.TemporaryDirectory() as tempdir:
        checks_repo_contents = {
            ".gitignore": "node_modules\n",
            "README.md": "# Test Project\n\nThis is a test project\n",
            ".sculptor/checks.toml": """[successful_check]
command = "echo 'Hello World'"
is_enabled = true

[failing_check]
command = "echo 'Test failed' && exit 1"
is_enabled = true

[slow_check]
command = "sleep 10 && echo 'Slow check completed'"
is_enabled = true

[pytest_check]
command = "pytest tests/"
is_enabled = true

[lint_check]
command = "python -m flake8 src/"
is_enabled = true
""",
        }

        checks_file_contents = {
            "data/something.txt": "some data\n",
            "src/main.py": "print('hello world')\nprint('goodbye')\n",
        }

        initial_state = FullLocalGitRepo(
            git_user_email="product@imbue.com",
            git_user_name="imbue",
            git_diff=None,
            git_branch="main",
            main_history=(
                GitCommitSnapshot(
                    contents_by_path=checks_repo_contents,
                    commit_message="initial commit",
                    commit_time="2025-01-01T00:00:01",
                ),
                GitCommitSnapshot(
                    contents_by_path=checks_file_contents,
                    commit_message="add some cool data",
                    commit_time="2025-01-01T00:00:01",
                ),
            ),
        )

        test_project_name = (
            "test_project_checks"
            if not is_xdist_worker(request)
            else "test_project_checks_" + get_xdist_worker_id(request)
        )
        repo_dir = Path(tempdir) / test_project_name
        logger.info("Creating test project repo with checks in {}", str(repo_dir))
        repo = MockRepoState.build_locally(state=initial_state, local_dir=repo_dir)
        subprocess.run(["git", "remote", "add", "origin", str(repo_dir)])

        repo.create_reset_and_checkout_branch("testing")
        repo.write_file("stuff.txt", "stuff")
        repo.commit("Stuff", commit_time="2025-01-01T00:00:02")
        yield repo


custom_sculptor_config_path = pytest.mark.custom_sculptor_config_path


@pytest.fixture
def sculptor_config_path_(request: pytest.FixtureRequest) -> Generator[Path, None, None]:
    config_path = request.node.get_closest_marker(custom_sculptor_config_path.name)
    if config_path:
        yield Path(config_path.args[0])
        return

    with tempfile.NamedTemporaryFile(suffix=".toml", delete=True) as file:
        config_path = Path(file.name)
        populate_config_file_for_test(config_path)
        yield config_path


@pytest.fixture
def anthropic_api_key_(snapshot: SnapshotAssertion, testing_mode_: TestingMode) -> str:
    if snapshot.session.update_snapshots or testing_mode_ == TestingMode.ACCEPTANCE:
        return os.environ["ANTHROPIC_API_KEY"]
    return "sk-ant-fake-api-key"


custom_sculptor_folder_populator = pytest.mark.custom_sculptor_folder


@pytest.fixture
def sculptor_folder_(request: pytest.FixtureRequest, anthropic_api_key_: str) -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as dir:
        folder_path = Path(dir)
        folder_populator = request.node.get_closest_marker(custom_sculptor_folder_populator)
        logger.info("Setting ant key: {}", custom_sculptor_folder_populator)
        if folder_populator:
            folder_populator(folder_path)
        else:
            populate_config_file_for_test(folder_path / "config.toml")
            populate_credentials_file(
                folder_path / "credentials.json",
                AnthropicApiKey(anthropic_api_key=anthropic_api_key_, generated_from_oauth=False),
            )
        yield folder_path


@pytest.fixture(scope="function")
def container_prefix_() -> Generator[str, None, None]:
    yield get_testing_container_prefix()


no_auto_project = pytest.mark.no_auto_project


@pytest.fixture
def auto_select_project_(request: pytest.FixtureRequest) -> Generator[bool, None, None]:
    if request.node.get_closest_marker(no_auto_project.name):
        yield False
        return

    yield True


@pytest.fixture
def sculptor_factory_(
    sculptor_server_key_: str,
    testing_mode_: TestingMode,
    request: pytest.FixtureRequest,
    pure_local_repo_: MockRepoState,
    auto_select_project_: bool,
    database_url_: str,
    sculptor_folder_: Path,
    port_: int,
    container_prefix_: str,
    snapshot_path_: Path,
    snapshot: SnapshotAssertion,
    page: Page,
    output_path: str,
) -> Generator[SculptorFactory]:
    """This fixture provides a running sculptor server."""
    page.set_default_timeout(2 * 60 * 1000)

    update_snapshots = snapshot.session.update_snapshots
    repo_path = pure_local_repo_.base_path if auto_select_project_ else None

    assert (testing_mode_, update_snapshots) != (TestingMode.ACCEPTANCE, True), (
        "Updating snapshots is not implemented for acceptance tests"
    )

    if update_snapshots or testing_mode_ == TestingMode.ACCEPTANCE:
        hide_anthropic_key = False
        existing_snapshot_path = None
    else:
        hide_anthropic_key = True
        existing_snapshot_path = snapshot_path_

    is_checks_enabled = "pure_local_repo_with_checks_" in request.fixturenames

    match (testing_mode_, sculptor_server_key_):
        case (TestingMode.INTEGRATION, s) if s.startswith("v1"):
            sculptor_command = get_sculptor_command_v1(
                repo_path,
                port=port_,
            )
            sculptor_environment = get_testing_environment(
                database_url=database_url_,
                container_prefix=container_prefix_,
                sculptor_folder=sculptor_folder_,
                hide_anthropic_key=hide_anthropic_key,
                static_files_path=(get_v1_frontend_path() / "dist").absolute(),
                is_checks_enabled=is_checks_enabled,
            )
        case (TestingMode.INTEGRATION, s) if s.startswith("dist"):
            sculptor_command = get_sculptor_command_v1(
                repo_path,
                port=port_,
            )
            sculptor_environment = get_testing_environment(
                database_url=database_url_,
                container_prefix=container_prefix_,
                sculptor_folder=sculptor_folder_,
                hide_anthropic_key=hide_anthropic_key,
                is_checks_enabled=is_checks_enabled,
            )
        case (TestingMode.ACCEPTANCE, s) if s.startswith("dist"):
            sculptor_command = get_sculptor_command_v1(
                repo_path,
                port=port_,
            )
            sculptor_environment = get_testing_environment(
                database_url=database_url_,
                container_prefix=container_prefix_,
                sculptor_folder=sculptor_folder_,
                hide_anthropic_key=hide_anthropic_key,
                is_checks_enabled=is_checks_enabled,
            )
        case (TestingMode.ACCEPTANCE, s) if s.startswith("v1"):
            pytest.skip("Acceptance tests only run on dist server")
        case _:
            raise ValueError(f"Unknown sculptor server key: {sculptor_server_key_}")

    sculptor_factory = SculptorFactory(
        command=sculptor_command,
        environment=sculptor_environment,
        snapshot_path=existing_snapshot_path,
        container_prefix=container_prefix_,
        port=port_,
        page=page,
        database_url=database_url_,
        update_snapshots=update_snapshots,
    )
    yield sculptor_factory

    # Must update snapshots before the server is shut down.
    if snapshot.session.update_snapshots:
        logger.info("Copying in saved snapshots")
        sculptor_factory.copy_snapshots(new_snapshot_path=snapshot_path_)

    failed = not hasattr(request.node, "rep_call") or request.node.rep_call.failed
    if failed:
        logger.info(f"Copying out preserved files for a failed test run to: {output_path}")
        sculptor_factory.copy_artifacts(new_artifacts_path=Path(output_path))
        # might as well stick the logs and DB in there too:
        database_file = "/" + database_url_.replace("sqlite:///", "").lstrip("/")
        db_path = Path(database_file)
        if db_path.exists():
            shutil.copy(db_path, Path(output_path) / "sculptor.db")


@pytest.fixture(scope="function")
def database_url_() -> str:
    db_file = tempfile.NamedTemporaryFile(suffix="db").name
    return f"sqlite:///{db_file}"


@pytest.fixture(scope="function")
def sculptor_page_(sculptor_factory_: SculptorFactory) -> Generator[Page]:
    """Fixture to launch a Playwright page for test purposes with retry."""
    with sculptor_factory_.spawn_sculptor_instance() as (sculptor_server, sculptor_page):
        yield sculptor_page


@pytest.fixture
def snapshot_path_(snapshot: SnapshotAssertion) -> Generator[Path, None, None]:
    snapshot_path = get_cache_dir_from_snapshot(snapshot=snapshot)
    yield snapshot_path


@pytest.fixture
def multi_tab_page_factory_(
    sculptor_factory_: SculptorFactory,
) -> Generator[MultiTabPageFactory, None, None]:
    """
    Factory for creating multiple browser tabs in the same context for cross-tab testing.

    Returns a MultiTabPageFactory that can create pages on demand.
    All created pages share the same browser context (cookies, localStorage, etc.)
    but are separate tabs that can navigate independently.

    Usage:
        def test_cross_tab(multi_tab_page_factory):
            factory = multi_tab_page_factory

            # Primary page is already available
            factory.primary_page.do_something()

            # Create additional pages as needed
            secondary_page = factory.create_page()
            secondary_page.do_something_else()
    """
    with sculptor_factory_.spawn_sculptor_instance() as (server, primary_page):
        # Create the factory with the primary page and server URL
        factory = MultiTabPageFactory(primary_page, server.url)

        yield factory

        factory.cleanup()


@pytest.fixture
def test_repo_factory_(tmp_path: Path) -> Generator[TestRepoFactory, None, None]:
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
    factory = TestRepoFactory(base_path=tmp_path)
    yield factory
