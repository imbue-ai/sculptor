import threading
from pathlib import Path

from loguru import logger
from pydantic import PrivateAttr
from typeid.errors import InvalidTypeIDStringException

from sculptor.database.models import Project
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TypeIDPrefixMismatchError
from sculptor.primitives.ids import get_deterministic_typeid_suffix
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.project_service.api import ProjectService
from sculptor.utils.build import get_internal_folder

_PATH_MONITORING_INTERVAL_IN_SECONDS: float = 10.0
_MONITORING_THREAD_JOIN_TIMEOUT_IN_SECONDS: float = 5.0


class DefaultProjectService(ProjectService):
    """
    Default implementation of ProjectService.

    Note: Workspace methods have been moved to WorkspaceService.
    """

    data_model_service: DataModelService

    # Set of currently active projects, where the first one is the most recently activated
    _active_projects: tuple[Project, ...] = PrivateAttr(default_factory=tuple)
    _project_activation_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    # Path monitoring thread fields
    _monitoring_thread: ObservableThread | None = PrivateAttr(default=None)
    _stop_event: threading.Event | None = PrivateAttr(default=None)

    def start(self) -> None:
        self._stop_event = threading.Event()
        self._start_path_monitoring_thread()

    def stop(self) -> None:
        logger.info("Stopping project path monitoring thread")
        if self._stop_event is not None:
            self._stop_event.set()
        if self._monitoring_thread is not None:
            self._monitoring_thread.join(timeout=_MONITORING_THREAD_JOIN_TIMEOUT_IN_SECONDS)
        logger.info("Project path monitoring thread joined")

    def get_active_projects(self) -> tuple[Project, ...]:
        with self._project_activation_lock:
            return tuple(p for p in self._active_projects if not p.is_deleted)

    def activate_project(self, project: Project) -> None:
        with self._project_activation_lock:
            # move the project to the front of the list
            self._active_projects = (project,) + tuple(
                p for p in self._active_projects if p.object_id != project.object_id
            )

    def initialize_project(
        self, project_path: Path, organization_reference: OrganizationReference, transaction: DataModelTransaction
    ) -> Project:
        return self._ensure_project_is_initialized(project_path, organization_reference, transaction)

    def _ensure_project_is_initialized(
        self, project_path: Path, organization_reference: OrganizationReference, transaction: DataModelTransaction
    ) -> Project:
        project_name = project_path.name
        project_id = self._get_project_id(transaction, project_path, organization_reference)

        user_git_repo_url = f"file://{project_path}"

        existing_project = transaction.get_project(project_id)
        if existing_project is not None:
            # IMPORTANT: This method only owns name, user_git_repo_url, and
            # is_deleted. All other Project fields (workspace_setup_command,
            # default_system_prompt, etc.) are user-configured and must be
            # preserved. If you add a new field to Project that should be set
            # during initialization, add an evolve call here; otherwise leave
            # it alone so existing values survive server restarts.
            current_project = existing_project.evolve(existing_project.ref().name, project_name)
            current_project = current_project.evolve(current_project.ref().user_git_repo_url, user_git_repo_url)
            current_project = current_project.evolve(current_project.ref().is_deleted, False)
        else:
            current_project = Project(
                object_id=project_id,
                organization_reference=organization_reference,
                name=project_name,
                user_git_repo_url=user_git_repo_url,
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
            if Path(existing_project.get_local_user_path()).absolute() == Path(project_path).absolute():
                return existing_project.object_id
        return ProjectID(get_deterministic_typeid_suffix(str(organization_reference) + str(project_path)))

    def _start_path_monitoring_thread(self) -> None:
        """Start the background thread that monitors project paths."""
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            logger.info("Project path monitoring thread is already running")
            return

        self._monitoring_thread = self.concurrency_group.start_new_thread(
            target=self._monitor_project_paths,
            name="ProjectPathMonitor",
            daemon=True,
            args=(self._stop_event,),
        )
        logger.info("Started project path monitoring thread")

    def _monitor_project_paths(
        self, stop_event: threading.Event, interval_in_seconds: float = _PATH_MONITORING_INTERVAL_IN_SECONDS
    ) -> None:
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
        try:
            is_currently_accessible = project_path.exists() and project_path.is_dir()
        except OSError:
            is_currently_accessible = False

        # If the status changed, update the project in the database
        if is_currently_accessible == project.is_path_accessible:
            return
        logger.info(
            "Project path accessibility changed for {}: {} -> {}",
            project.name,
            project.is_path_accessible,
            is_currently_accessible,
        )

        try:
            # SCU-474: targeted field-level update — only writes is_path_accessible,
            # so this background thread cannot clobber disjoint fields
            # (default_system_prompt, workspace_setup_command, name, user_git_repo_url)
            # set by concurrent HTTP writers while we held a stale in-memory copy
            # of `project`.
            with self.data_model_service.open_transaction(request_id=RequestID(), is_user_request=True) as transaction:
                updated_project = transaction.update_project_fields(
                    project.object_id, is_path_accessible=is_currently_accessible
                )
                if updated_project is None:
                    # Project was deleted between the active-projects snapshot and
                    # this write; nothing to update.
                    return

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

                logger.info(
                    "Successfully updated project {} accessibility to {}", project.name, is_currently_accessible
                )
        except Exception as e:
            log_exception(e, "Failed to update project {project} accessibility", project=project.name)

    def delete_project(self, project: Project, transaction: DataModelTransaction) -> None:
        # Re-read the project inside this transaction instead of trusting the
        # in-memory copy passed in: the caller read it before deleting all of the
        # project's tasks and workspaces (app.py), so a full-object upsert of that
        # stale copy could clobber disjoint fields (default_system_prompt,
        # workspace_setup_command, name, ...) written by a concurrent request.
        # is_deleted is a protected column (see ProjectFieldUpdate), so it can't go
        # through update_project_fields; flipping it on a freshly-read copy is the
        # soft-delete pattern used elsewhere. The residual write-after-read TOCTOU
        # is tracked in SCU-168.
        latest_project = transaction.get_project(project.object_id)
        if latest_project is not None:
            updated_project = latest_project.evolve(latest_project.ref().is_deleted, True)
            transaction.upsert_project(updated_project)
        with self._project_activation_lock:
            # Find and update the project in active projects
            self._active_projects = tuple(p for p in self._active_projects if p.object_id != project.object_id)


def get_most_recently_used_project_id() -> ProjectID | None:
    sculptor_folder = get_internal_folder()
    mru_file = sculptor_folder / "most_recently_used_project.txt"
    try:
        if mru_file.exists():
            with open(mru_file, "r") as f:
                project_id_str = f.read().strip()
                try:
                    return ProjectID(project_id_str)
                except (TypeIDPrefixMismatchError, InvalidTypeIDStringException):
                    logger.info("Invalid project ID found in most_recently_used_project.txt: {}", project_id_str)
    except OSError:
        logger.debug("Failed to read most_recently_used_project.txt (transient OS error)")
    return None


def update_most_recently_used_project(project_id: ProjectID) -> None:
    sculptor_folder = get_internal_folder()
    mru_file = sculptor_folder / "most_recently_used_project.txt"
    with open(mru_file, "w") as f:
        f.write(str(project_id))
