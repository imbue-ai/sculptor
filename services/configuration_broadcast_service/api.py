from abc import ABC
from abc import abstractmethod

from imbue_core.pydantic_serialization import SerializableModel
from sculptor.database.models import ProjectID
from sculptor.database.models import TaskID
from sculptor.primitives.service import Service
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials


class UserConfiguration(SerializableModel):
    """User-level configuration settings."""

    anthropic_credentials: AnthropicCredentials | None = None


class ProjectConfiguration(SerializableModel):
    """Project-level configuration settings."""

    gitlab_token: str | None = None
    gitlab_url: str | None = None
    token_expires_at_iso: str | None = None


class ConfigurationBroadcastService(Service, ABC):
    """
    This service is responsible for broadcasting configuration messages to all active tasks, all active tasks within a given project, or individual tasks.
    """

    @abstractmethod
    def broadcast_configuration_to_all_tasks(self, configuration: UserConfiguration) -> None:
        """
        Broadcast user configuration message to all active tasks.
        """

    @abstractmethod
    def send_configuration_to_task(self, task_id: TaskID, configuration: UserConfiguration) -> None:
        """
        Send user configuration message to a specific task.
        """

    @abstractmethod
    def send_configuration_to_project(self, project_id: ProjectID, configuration: ProjectConfiguration) -> None:
        """
        Send project configuration message to all tasks in a specific project.
        """

    @abstractmethod
    def get_current_user_configuration(self) -> UserConfiguration:
        """
        Get the current user configuration.
        """

    @abstractmethod
    def get_current_project_configuration(self, project_id: ProjectID) -> ProjectConfiguration:
        """
        Get the current project configuration for a specific project.
        """

    @abstractmethod
    def rebroadcast_current_configuration_to_task(self, task_id: TaskID) -> None:
        """
        Rebroadcast the current user configuration to a specific task.
        """

    @abstractmethod
    def is_token_expired(self, configuration: UserConfiguration | ProjectConfiguration) -> bool:
        """
        Check if the current GitLab token is expired or expires within the next day.
        """
