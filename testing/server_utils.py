from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import attr
from loguru import logger
from playwright.sync_api import Page

from imbue_core.common import generate_id
from imbue_core.git import get_git_repo_root
from sculptor.agents.claude_code_sdk.agent import INTERRUPT_POST_SURGERY_FILEPATH
from sculptor.agents.claude_code_sdk.agent import INTERRUPT_POST_TERMINATE_FILEPATH
from sculptor.agents.claude_code_sdk.terminal_manager import TTYD_NGINX_PROXY_DIR
from sculptor.services.environment_service.providers.docker.environment_utils import stop_outdated_docker_containers
from sculptor.testing import synchronization
from sculptor.testing.caching_utils import save_caches_to_snapshot_directory
from sculptor.testing.container_utils import get_containers_with_tasks
from sculptor.testing.elements.task_list import wait_for_tasks_to_finish
from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.playwright_utils import navigate_to_frontend
from sculptor.utils.file_utils import copy_dir

LOCAL_HOST_URL = "http://127.0.0.1"
READY_MESSAGE_V1 = "Server is ready to accept requests!"


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
    """A factory for creating sculptor instances."""

    def __init__(
        self,
        command: tuple[str, ...],
        environment: dict[str, str | None],
        snapshot_path: Path | None,
        container_prefix: str,
        port: int,
        database_url: str,
        page: Page,
        update_snapshots: bool,
    ) -> None:
        self.command = command
        self.environment = environment
        self.snapshot_path = snapshot_path
        self.database_url = database_url
        self.port = port
        self.page = page
        self.container_prefix = container_prefix
        self.update_snapshots = update_snapshots
        self._sculptor_cache_id = 0
        self._tmp_snapshot_path = Path(tempfile.mkdtemp())
        self._tmp_artifacts_path = Path(tempfile.mkdtemp())

    @contextmanager
    def spawn_sculptor_instance(self) -> Generator[tuple[SculptorServer, PlaywrightHomePage], None, None]:
        environment = self.environment.copy()
        snapshot_parent = f"sculptor_snapshot_{self._sculptor_cache_id}"
        artifacts_parent = f"sculptor_artifacts_{self._sculptor_cache_id}"

        tmp_artifacts_path = self._tmp_artifacts_path / artifacts_parent

        if self.snapshot_path is not None:
            assert not self.update_snapshots, (
                "error in test: We can't update snapshot and provide them at the same time"
            )
            snapshot_path = self.snapshot_path / snapshot_parent
            environment["TESTING__SNAPSHOT_PATH"] = str(snapshot_path.absolute())

        logger.info("Starting sculptor server with command: {}", self.command)
        logger.info("Setting environment to: {}", environment)

        env = {k: str(v) for k, v in {**os.environ, **environment}.items() if v is not None}
        server = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        assert server.stdout, "Sculptor server stdout is always available in PIPE mode"

        server_output_lines = []

        forwarder = Forwarder(server)

        specimen_server: SculptorServer | None = None
        for line in server.stdout:
            server_output_lines.append(line.rstrip())
            print_colored_line(line.rstrip())
            if READY_MESSAGE_V1 in line:
                logger.info("Sculptor server is ready")
                forwarder.start()
                specimen_server = SculptorServer(process=server, port=self.port)
                sculptor_page = navigate_to_frontend(page=self.page, url=specimen_server.url)
                self._sculptor_cache_id += 1
                # adding this here so that we can note when we expect things to fail
                sculptor_page._imbue_server = specimen_server
                yield specimen_server, sculptor_page
                if self.update_snapshots:
                    logger.debug("Snapshotting, waiting for tasks to complete")
                    # TODO: This should really work by reading DB
                    wait_for_tasks_to_finish(task_list=sculptor_page.get_task_list())
                logger.debug("Test server fixture finished")
                break

        if specimen_server is None:
            # Server failed to start properly - provide detailed error information
            error_msg = "Sculptor server failed to start and never outputted ready message.\n"
            error_msg += f"Expected message containing: '{READY_MESSAGE_V1}'\n"
            error_msg += f"Command: {' '.join(self.command)}\n"
            error_msg += "Server output:\n" + "\n".join(server_output_lines)

            logger.error(error_msg)
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(2)

            raise RuntimeError(error_msg)

        # normal case -- we do NOT expect any containers to be missing
        if not specimen_server.is_unexpected_error_caused_by_test:
            containers_with_tasks = get_containers_with_tasks(database_url=self.database_url)
            if self.update_snapshots:
                if forwarder.first_failure_line is not None:
                    logger.info("Not updating snapshots due to earlier error: {}", forwarder.first_failure_line)
                else:
                    logger.info("Preserving snapshots to a temporary directory")
                    save_caches_to_snapshot_directory(
                        local_path=self._tmp_snapshot_path / snapshot_parent,
                        containers_with_tasks=containers_with_tasks,
                    )
        else:
            containers_with_tasks = ()

        logger.info("Preserving files from the tasks and sculptor to a temporary directory: {}", tmp_artifacts_path)
        diagnostics_output = "/tmp/diagnostics.txt"
        files_to_extract = {
            "/tmp/proxy_logs.txt": "proxy_logs.txt",
            "/tmp/imbue-cli.log": "imbue-cli.log",
            str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.access.log"): "nginx.access.log",
            str(Path(TTYD_NGINX_PROXY_DIR) / "nginx.error.log"): "nginx.error.log",
            INTERRUPT_POST_TERMINATE_FILEPATH: "interrupt-post-terminate-sessions",
            INTERRUPT_POST_SURGERY_FILEPATH: "interrupt-post-surgery-sessions",
            diagnostics_output: "diagnostic.txt",
        }

        tmp_artifacts_path.mkdir(parents=True, exist_ok=True)
        for i, (container_id, task_id) in enumerate(containers_with_tasks):
            try:
                # these have to be shell-safe!
                commands = [
                    "set -x",
                    "/bin/ps auxwf",
                    "du -s",
                    "ulimit -a",
                    "git --version",
                    "env",
                    "claude --version",
                    "uname -a",
                ]
                # re-directing to `cat` to hide exit code of the commands but have `docker exec` fail
                # if bash is not found or container is dead.
                bash_command = ["bash", "-c", f"({';'.join(commands)}) 2>&1 | cat >{shlex.quote(diagnostics_output)}"]

                subprocess.run(
                    ["docker", "exec", "--user", "root", container_id, *bash_command],
                    timeout=60,
                    capture_output=True,
                    check=True,
                )
            except Exception as e:
                logger.info("Container not available, or diagnostics command failed. Ignoring. Reason: {}", str(e))

            for source, destination in files_to_extract.items():
                output_file = tmp_artifacts_path / f"task.{i}.{task_id}-{destination}"
                try:
                    subprocess.run(
                        ["docker", "cp", f"{container_id}:{source}", output_file],
                        timeout=60,
                        capture_output=True,
                        check=True,
                    )
                except Exception as e:
                    logger.info("Could not extract {} from the container. Ignoring. Reason: {}", source, str(e))

        logger.info("Terminating sculptor server")
        # server_p = psutil.Process(server.pid)
        server.terminate()
        try:
            # TODO: we need to think a little deeply about what we want the timeout to be here, bumped to make sure we try and wait for a clean shutdown
            if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t"):
                # it can take a really long time for things to shut down on modal because we can be waiting for some containers to go away...
                server.wait(timeout=60 * 6)
            else:
                server.wait(timeout=60)
        except subprocess.TimeoutExpired:
            # logging as error so our tests will fail if we don't shut down cleanly
            logger.error("Sculptor server did not terminate gracefully, killing it.")
            server.kill()
            server.wait(2)

            stop_outdated_docker_containers(environment_prefix=self.container_prefix)

        # if there was an error in the logs, that is sufficient for us to mark this task as failed
        # (even if the test didn't realize it failed)
        if specimen_server.is_unexpected_error_caused_by_test:
            pass
        else:
            if forwarder.first_failure_line is not None:
                raise Exception(
                    f"Sculptor server encountered emitted a line with ERROR: {forwarder.first_failure_line}"
                )

    def copy_snapshots(self, new_snapshot_path: Path) -> None:
        if new_snapshot_path.exists():
            shutil.rmtree(new_snapshot_path)

        new_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        copy_dir(self._tmp_snapshot_path, new_snapshot_path)

    def copy_artifacts(self, new_artifacts_path: Path) -> None:
        new_artifacts_path.parent.mkdir(parents=True, exist_ok=True)
        copy_dir(self._tmp_artifacts_path, new_artifacts_path)


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class SculptorServerConfig:
    """Configuration for the server.

    This represents the different types of servers that we can run.
    """

    key: str


class Forwarder(threading.Thread):
    """Thread to forward output from the sculptor server to the logger.

    While the sculptor server is running, there might be useful output that we want to log.
    """

    def __init__(self, sculptor_server: subprocess.Popen) -> None:
        super().__init__(daemon=True)
        self.sculptor_server = sculptor_server
        self.first_failure_line = None

    def run(self) -> None:
        assert self.sculptor_server.stdout, "Sculptor server stdout is always available in PIPE mode"
        for line in self.sculptor_server.stdout:
            # Note: the print(line) here routes to pytest junit due to an issue with how pytest hides stdout
            #       the logger actually displays to the user
            print_colored_line(line.rstrip())
            if "|ERROR" in line or "Cache miss" in line:
                # note that we do NOT blow up here -- that's because we want to capture all the output!
                self.first_failure_line = line.rstrip()
                # raise RuntimeError(line.strip())


SERVERS = [
    # FIXME: it's not clear to me that it's worth running all of our tests twice right now
    #  currently just running dist tests in normal CI
    #  but it feels stupid to run those in modal since it's so much more setup time
    *(
        [SculptorServerConfig(key="v1")]
        if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t")
        else [SculptorServerConfig(key="dist"), SculptorServerConfig(key="v1")]
    )
]

TEST_ENVIRONMENT_PREFIX = "sculptortesting"


def print_colored_line(line: str, level: str | None = None) -> None:
    # FIXME: make this the only case ASAP -- the else is just there because these lines end up being too long for the old dumb runner...
    if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t"):
        if "|ERROR" in line or level == "ERROR":
            logger.error(line)
        elif "|WARNING" in line or level == "WARNING":
            logger.warning(line)
        elif "|INFO" in line or level == "INFO":
            logger.info(line)
        elif "|DEBUG" in line or level == "DEBUG":
            logger.debug(line)
        else:
            logger.info(line)
    else:
        if "|ERROR" in line or level == "ERROR":
            # needs to be logged so that the test can pick it up
            logger.error(line)
            # Red
            print(f"\033[31m{line}\033[0m")
        elif "|WARNING" in line or level == "WARNING":
            # Yellow
            print(f"\033[33m{line}\033[0m")
        elif "|INFO" in line or level == "INFO":
            # Green
            print(f"\033[32m{line}\033[0m")
        elif "|DEBUG" in line or level == "DEBUG":
            # Cyan
            print(f"\033[36m{line}\033[0m")
        elif "|TRACE" in line or level == "TRACE":
            # Gray
            # print(f"\033[90m{line}\033[0m")
            pass
        else:
            print(line)


@contextmanager
def build_or_wait_for_dist(worker_id: str) -> Generator[None]:
    """Build the dist using flock file locking to coordinate between workers.

    Uses a named flock file to determine which worker becomes the "primary" worker.
    The primary worker builds the dist, while other workers wait for completion.
    This ensures the dist is built exactly once regardless of which workers get tests.
    """
    lock_filename = synchronization.get_dist_lockfile_path()

    # Try to acquire the lock to become the primary worker
    with synchronization.request_lock(str(lock_filename)) as is_locked:
        if is_locked:
            logger.info("Worker {} acquired lock, building dist for sculptor server", worker_id)
            # Note: This will run the Makefile in the sculptor directory. Do not
            # clean because we rely on the make installed files.
            subprocess.run(["make", "dist-test"], check=True, cwd=get_git_repo_root() / "sculptor")
            subprocess.run(["touch", "sculptor-build-completed"], check=True, cwd=get_git_repo_root() / "dist")
            yield
        else:
            # This worker didn't get the lock, so wait for the primary to finish
            logger.info(
                "Worker {} waiting for dist build of sculptor server at {!s}", worker_id, get_git_repo_root() / "dist"
            )
            synchronization.wait_for_file_existence(
                path=get_git_repo_root() / "dist",
                pattern="*/sculptor-build-completed",
                timeout=None,  # No timeout specified here, because the test runner will timeout for us.
            )
            logger.info("Worker {} received dist, proceeding with test", worker_id)
            yield


def get_testing_container_prefix() -> str:
    return f"{TEST_ENVIRONMENT_PREFIX}-{generate_id()}"


def get_v1_frontend_path() -> Path:
    """Returns the path to the frontend directory in v1"""
    return get_git_repo_root() / "sculptor" / "frontend"


def get_testing_environment(
    container_prefix: str,
    database_url: str,
    sculptor_folder: Path,
    static_files_path: Path | None = None,
    hide_anthropic_key: bool = True,
    is_checks_enabled: bool = False,
) -> dict[str, str | None]:
    environment = {}

    if static_files_path is not None:
        environment["STATIC_FILES_PATH"] = str(static_files_path.absolute())

    environment["SCULPTOR_FOLDER"] = sculptor_folder
    environment["DATABASE_URL"] = database_url
    environment["TESTING__INTEGRATION_ENABLED"] = "true"
    environment["TESTING__CONTAINER_PREFIX"] = container_prefix
    environment["SENTRY_DSN"] = None
    environment["IS_CHECKS_ENABLED"] = "true" if is_checks_enabled else "false"
    environment["IS_FORKING_ENABLED"] = "true"
    environment["LOCAL_PROVIDER_ENABLED"] = "true"

    if hide_anthropic_key:
        environment["ANTHROPIC_API_KEY"] = "sk-HIDDEN-FOR-TESTING"

    environment["GITLAB_DEFAULT_TOKEN"] = "test-gitlab-token-for-integration-tests"

    return environment


def get_sculptor_command_v1(
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
