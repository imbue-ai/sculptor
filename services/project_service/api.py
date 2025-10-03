from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Callable

from sculptor.database.models import Project
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.data_types import DataModelTransaction


class ProjectService(Service, ABC):
    """
    Handle initialization, retrieval and the lifecycle of the server project in the current sculptor session.

    """

    @abstractmethod
    def get_active_projects(self) -> tuple[Project, ...]:
        """
        Get all active projects in the running sculptor session.

        """

    @abstractmethod
    def activate_project(self, project: Project) -> None:
        """Activate a project."""

    @abstractmethod
    def initialize_project(
        self, project_path: Path, organization_reference: OrganizationReference, transaction: DataModelTransaction
    ) -> Project:
        """
        Initialize a project in the database if it does not exist.

        This method does not set the project as the current project in the session.

        """

    @abstractmethod
    def register_on_project_activated(self, on_project_activated: Callable[[Project], None]) -> None:
        """
        Register a callback to be called when a project gets activated.

        When called in a situation where some projects are already activated, the callback will be called immediately for each of them.

        When another project gets activated, the callback will be called again.

        """
