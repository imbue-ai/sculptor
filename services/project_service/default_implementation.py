import os
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

from loguru import logger
from pydantic import PrivateAttr
from pydantic import ValidationError

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.gitlab_management import GITLAB_TOKEN_NAME
from imbue_core.processes.local_process import run_blocking
from imbue_core.thread_utils import ObservableThread
from sculptor.config.settings import SculptorSettings
from sculptor.config.user_config import get_user_config_instance
from sculptor.constants import GatewayRemoteAPIEndpoints
from sculptor.database.models import Project
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import get_deterministic_typeid_suffix
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.project_service.api import ProjectService
from sculptor.utils.build import get_sculptor_folder


class DefaultProjectService(ProjectService):
    settings: SculptorSettings
    data_model_service: DataModelService

    _cached_projects: dict[tuple[OrganizationReference, Path], Project] = PrivateAttr(default_factory=dict)
    _project_initialization_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _initialized_project: Project | None = PrivateAttr(default=None)
    _current_project_path: Path | None = PrivateAttr(default=None)
    # Set of currently active projects, where the first one is the most recently activated
    _active_projects: tuple[Project, ...] = PrivateAttr(default_factory=tuple)
    _project_activation_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _on_project_activated_callbacks: list[Callable[[Project], None]] = PrivateAttr(default_factory=list)
    # Path monitoring thread fields
    _monitoring_thread: ObservableThread | None = PrivateAttr(default=None)
    _stop_event: threading.Event

    def start(self) -> None:
        self._start_path_monitoring_thread()

    def stop(self) -> None:
        logger.info("Stopping project path monitoring thread")
        self._stop_event.set()
        self._monitoring_thread.join(timeout=5)
        logger.info("Project path monitoring thread joined")

    def get_active_projects(self) -> tuple[Project, ...]:
        with self._project_activation_lock:
            return tuple(self._active_projects)

    def activate_project(self, project: Project) -> None:
        with self._project_activation_lock:
            update_most_recently_used_project(project_id=project.object_id)
            # move the project to the front of the list
            self._active_projects = (project,) + tuple(p for p in self._active_projects if p != project)
        for callback in self._on_project_activated_callbacks:
            callback(project)

    def initialize_project(
        self, project_path: Path, organization_reference: OrganizationReference, transaction: DataModelTransaction
    ) -> Project:
        project = self._ensure_project_is_initialized(project_path, organization_reference, transaction)
        self._setup_gitlab_mirroring(project_path)
        return project

    def register_on_project_activated(self, on_project_activated: Callable[[Project], None]) -> None:
        for project in self.get_active_projects():
            on_project_activated(project)
        self._on_project_activated_callbacks.append(on_project_activated)

    def _ensure_project_is_initialized(
        self, project_path: Path, organization_reference: OrganizationReference, transaction: DataModelTransaction
    ) -> Project:
        project_name = project_path.name
        project_id = self._get_project_id(transaction, project_path, organization_reference)

        user_git_repo_url = f"file://{project_path}"

        our_git_repo_url: str | None = os.environ.get("GITLAB_PROJECT_URL")
        logger.info("Mirror url {} loaded", our_git_repo_url)

        current_project = Project(
            object_id=project_id,
            organization_reference=organization_reference,
            name=project_name,
            user_git_repo_url=user_git_repo_url,
            our_git_repo_url=our_git_repo_url,
        )
        transaction.upsert_project(current_project)
        return current_project

    def _get_project_id(
        self, transaction: DataModelTransaction, project_path: Path, organization_reference: OrganizationReference
    ) -> ProjectID:
        existing_projects = transaction.get_projects(organization_reference)
        for existing_project in existing_projects:
            # Legacy projects can have IDs different from the current deterministic creation scheme.
            if existing_project.user_git_repo_url is None:
                continue
            if (
                Path(existing_project.user_git_repo_url.replace("file://", "")).absolute()
                == Path(project_path).absolute()
            ):
                return existing_project.object_id
        return ProjectID(get_deterministic_typeid_suffix(str(organization_reference) + str(project_path)))

    def _setup_gitlab_mirroring(self, project_path: Path) -> None:
        """Set up GitLab mirroring for the project if enabled."""
        user_config = get_user_config_instance()
        if not user_config or not user_config.is_repo_backup_enabled:
            return

        if not self.settings.is_imbue_gateway_configured:
            return

        try:
            logger.info("Setting up GitLab mirroring for project: {}", project_path)

            result = run_blocking(command=["git", "rev-parse", "HEAD"], cwd=project_path, is_output_traced=False)
            base_commit_hash = result.stdout.strip()
            logger.info("Base commit hash: {}", base_commit_hash)

            gateway_url = urljoin(
                self.settings.IMBUE_GATEWAY_BASE_URL, GatewayRemoteAPIEndpoints.GITLAB_ANONYMOUS_PAT_ENDPOINT
            )
            params = {"base_commit_hash": base_commit_hash, "user_id": user_config.anonymous_access_token}

            logger.info("Gateway url for PAT is {}", gateway_url)

            access_token = None
            gitlab_project_url = None

            # Disabling mirroring for now.
            if access_token and gitlab_project_url:
                logger.success("Successfully retrieved GitLab access token from imbue-gateway")
                os.environ[GITLAB_TOKEN_NAME] = access_token
                os.environ["GITLAB_PROJECT_URL"] = gitlab_project_url
                logger.info("Gitlab project url: {}", gitlab_project_url)

                if gitlab_project_url.startswith("https://"):
                    base_gitlab_url = gitlab_project_url.split("/", 3)[0] + "//" + gitlab_project_url.split("/", 3)[2]
                    os.environ["GITLAB_URL"] = base_gitlab_url
            else:
                logger.info("imbue-gateway response missing required fields")
                gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
                os.environ["GITLAB_URL"] = gitlab_url
        except Exception as e:
            logger.info("Failed to retrieve GitLab access token from imbue-gateway: {}", e)
            gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
            os.environ["GITLAB_URL"] = gitlab_url

    def _start_path_monitoring_thread(self) -> None:
        """Start the background thread that monitors project paths."""
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            logger.info("Project path monitoring thread is already running")
            return

        self._stop_event = threading.Event()
        self._monitoring_thread = ObservableThread(
            target=self._monitor_project_paths,
            name="ProjectPathMonitor",
            daemon=True,
            args=(self._stop_event,),
        )
        self._monitoring_thread.start()
        logger.info("Started project path monitoring thread")

    def _monitor_project_paths(self, stop_event: threading.Event, interval_in_seconds: int = 10.0) -> None:
        """Background thread that continuously monitors project path accessibility."""
        logger.info("Project path monitoring thread started")

        while not stop_event.is_set():
            try:
                active_projects = self.get_active_projects()

                for project in active_projects:
                    self._check_and_update_project_accessibility(project)

                # Wait for the monitoring interval or until stop event is set
                # wait() returns True if the event is set, False if timeout occurred
                if stop_event.wait(timeout=interval_in_seconds):
                    break  # Stop event was set, exit the loop

            except Exception as e:
                log_exception(e, "Error in project path monitoring")
                # Continue monitoring even if there's an error, but check for stop event
                if stop_event.wait(timeout=interval_in_seconds):
                    break  # Stop event was set, exit the loop

        logger.info("Project path monitoring thread stopped")

    def _check_and_update_project_accessibility(self, project: Project) -> None:
        """Check if a project's path exists and update its accessibility status if changed."""
        if not project.user_git_repo_url or not project.user_git_repo_url.startswith("file://"):
            return

        project_path = Path(project.user_git_repo_url.replace("file://", ""))
        # Check if the path exists and is accessible
        current_accessible = project_path.exists() and project_path.is_dir()

        # If the status changed, update the project in the database
        if current_accessible == project.is_path_accessible:
            return
        logger.info(
            "Project path accessibility changed for {}: {} -> {}",
            project.name,
            project.is_path_accessible,
            current_accessible,
        )

        try:
            # Create a new project instance with updated accessibility using evolve pattern
            updated_project = project.evolve(project.ref().is_path_accessible, current_accessible)

            # Open a transaction to update the project
            # Use is_user_request=True to ensure updates are broadcast to frontend
            with self.data_model_service.open_transaction(request_id=RequestID(), is_user_request=True) as transaction:
                # Update the project in the database
                transaction.upsert_project(updated_project)

                # Update our cached version
                with self._project_activation_lock:
                    # Find and update the project in active projects
                    updated_projects = []
                    for p in self._active_projects:
                        if p.object_id == project.object_id:
                            # Replace with the updated project instance
                            updated_projects.append(updated_project)
                        else:
                            updated_projects.append(p)
                    self._active_projects = tuple(updated_projects)

                logger.info("Successfully updated project {} accessibility to {}", project.name, current_accessible)
        except Exception as e:
            log_exception(e, "Failed to update project {} accessibility", project.name)


def get_most_recently_used_project_id() -> ProjectID | None:
    sculptor_folder = get_sculptor_folder()
    mru_file = sculptor_folder / "most_recently_used_project.txt"
    if mru_file.exists():
        with open(mru_file, "r") as f:
            project_id_str = f.read().strip()
            try:
                return ProjectID(project_id_str)
            except ValidationError:
                logger.error("Invalid project ID found in most_recently_used_project.txt: {}", project_id_str)
    return None


def update_most_recently_used_project(project_id: ProjectID) -> None:
    sculptor_folder = get_sculptor_folder()
    mru_file = sculptor_folder / "most_recently_used_project.txt"
    with open(mru_file, "w") as f:
        f.write(str(project_id))
