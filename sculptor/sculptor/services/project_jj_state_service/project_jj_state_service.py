"""Each repository's jj colocation and whether it creates jj workspaces, kept current on the stream.

Colocation is read from disk every time it is needed, never stored.
"""

import threading
from pathlib import Path
from queue import Queue
from typing import assert_never

from loguru import logger
from pydantic import PrivateAttr

from sculptor.database.models import Project
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.workspace_service.jj_workspace_creation import JjWorkspaceCreationFacts
from sculptor.services.workspace_service.jj_workspace_creation import creates_jj_workspaces
from sculptor.services.workspace_service.jj_workspace_creation import gather_jj_workspace_creation_facts
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import JjColocationState
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import ProjectJjState
from sculptor.web.data_types import StreamingUpdateSourceTypes


class _StopWorker(FrozenModel):
    """Asks the worker thread to return."""


# A project to recompute, or the dependency status, whose jj readiness may have changed.
_WorkItem = Project | DependenciesStatus | _StopWorker


def derive_project_jj_state(project_id: ProjectID, facts: JjWorkspaceCreationFacts) -> ProjectJjState:
    """The state of a repository, from the facts read from its disk."""
    return ProjectJjState(
        project_id=project_id,
        colocation=JjColocationState.COLOCATED if facts.is_colocated else JjColocationState.ABSENT,
        colocation_error=None,
        creates_jj_workspaces=creates_jj_workspaces(facts),
    )


def is_colocation_gone(facts: JjWorkspaceCreationFacts) -> bool:
    """The repository wants jj workspaces, and jj can see it is not colocated.

    Without jj, colocation cannot be read, so it is never taken to be gone.
    """
    return facts.use_jj_for_new_workspaces and facts.jj_readiness.blocker is None and not facts.is_colocated


class ProjectJjStateService(Service):
    """Derives each repository's `ProjectJjState` and publishes it to stream observers whenever it changes.

    It recomputes a project when the project is activated or refreshed on
    request, and every project when jj's readiness changes. Recomputing and
    publishing happen on one worker thread, so states are published in order.
    """

    data_model_service: DataModelService
    project_service: ProjectService
    dependency_management_service: DependencyManagementService
    vcs_runners: VcsRunners

    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _observers: tuple[Queue[StreamingUpdateSourceTypes], ...] = PrivateAttr(default=())
    _state_by_project_id: dict[ProjectID, ProjectJjState] = PrivateAttr(default_factory=dict)
    _work_queue: Queue[_WorkItem] = PrivateAttr(default_factory=Queue)

    def start(self) -> None:
        self.project_service.add_activation_observer(self.refresh_project)
        self.dependency_management_service.add_observer_queue(self._work_queue)
        self.concurrency_group.start_new_thread(target=self._run_worker, name="project-jj-state", is_checked=False)

    def stop(self) -> None:
        self.dependency_management_service.remove_observer_queue(self._work_queue)
        self.project_service.remove_activation_observer(self.refresh_project)
        self._work_queue.put(_StopWorker())

    def add_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        """Register a stream queue, and put every repository's current state into it at once."""
        with self._lock:
            self._observers = (*self._observers, queue)
            for state in self._state_by_project_id.values():
                queue.put(state)

    def remove_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        with self._lock:
            self._observers = tuple(observer for observer in self._observers if observer is not queue)

    def refresh_project(self, project: Project) -> None:
        """Recompute `project`'s state from disk soon, and publish it if it changed."""
        self._work_queue.put(project)

    def _run_worker(self) -> None:
        last_jj_readiness: JjReadiness | None = None
        while True:
            item = self._work_queue.get()
            if isinstance(item, _StopWorker):
                return
            elif isinstance(item, DependenciesStatus):
                if item.jj_readiness == last_jj_readiness:
                    continue
                last_jj_readiness = item.jj_readiness
                with self.data_model_service.open_transaction(RequestID()) as transaction:
                    projects = transaction.get_projects()
                for project in projects:
                    self._recompute_and_keep_going(project)
            elif isinstance(item, Project):
                self._recompute_and_keep_going(item)
            else:
                assert_never(item)

    def _recompute_and_keep_going(self, project: Project) -> None:
        """Recompute `project`; a failure is logged so the worker keeps serving every other project."""
        try:
            self._recompute(project)
        except Exception as e:
            log_exception(e, "Failed to recompute the jj state of project {project_id}", project_id=project.object_id)

    def _recompute(self, project: Project) -> None:
        try:
            facts = gather_jj_workspace_creation_facts(
                project, self.vcs_runners.jj, self.dependency_management_service
            )
        except VcsCommandError as e:
            logger.debug("Cannot read the jj colocation of {}: {}", project.object_id, e)
            return
        if is_colocation_gone(facts) and _is_repository_present(project.get_local_user_path()):
            logger.debug(
                "Turning use_jj_for_new_workspaces off for {}, which is no longer colocated", project.object_id
            )
            self._turn_off_use_jj_for_new_workspaces(project.object_id)
            facts = facts.model_copy(update={"use_jj_for_new_workspaces": False})
        self._publish(derive_project_jj_state(project.object_id, facts))

    def _turn_off_use_jj_for_new_workspaces(self, project_id: ProjectID) -> None:
        with self.data_model_service.open_transaction(RequestID()) as transaction:
            transaction.update_project_fields(project_id, use_jj_for_new_workspaces=False)

    def _publish(self, state: ProjectJjState) -> None:
        with self._lock:
            if self._state_by_project_id.get(state.project_id) == state:
                return
            self._state_by_project_id[state.project_id] = state
            for observer in self._observers:
                observer.put(state)


def _is_repository_present(repo_path: Path) -> bool:
    """Whether the repository is on disk at all, as opposed to on a drive that is not mounted."""
    return (repo_path / ".git").exists()
