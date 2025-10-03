import json
import threading
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from loguru import logger
from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from sculptor.database.models import ProjectID
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import SetProjectConfigurationDataUserMessage
from sculptor.interfaces.agents.v1.agent import SetUserConfigurationDataUserMessage
from sculptor.services.configuration_broadcast_service.api import ConfigurationBroadcastService
from sculptor.services.configuration_broadcast_service.api import ProjectConfiguration
from sculptor.services.configuration_broadcast_service.api import UserConfiguration
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.task_service.api import TaskService
from sculptor.utils.build import get_sculptor_folder

USER_CONFIG_FILENAME = "user_config.json"
PROJECT_CONFIG_FILENAME = "project_config.json"


class _ConfigurationFileHandler(FileSystemEventHandler):
    def __init__(self, service: "DefaultConfigurationBroadcastService"):
        self._project_configurations: dict[str, dict[str, str]] = {}
        self.service = service
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return

        with self._lock:
            if Path(event.src_path).name == USER_CONFIG_FILENAME:
                logger.debug("User configuration file modified.")
                self.service._load_user_configuration()
            elif Path(event.src_path).name == PROJECT_CONFIG_FILENAME:
                logger.debug("Project configuration file modified.")
                self.service._load_project_configurations()


class DefaultConfigurationBroadcastService(ConfigurationBroadcastService):
    data_model_service: DataModelService
    task_service: TaskService

    def __init__(self, data_model_service: DataModelService, task_service: TaskService):
        super().__init__(data_model_service=data_model_service, task_service=task_service)
        self._config_dir = get_sculptor_folder() / "configuration"
        self._user_config_file = self._config_dir / USER_CONFIG_FILENAME
        self._project_config_file = self._config_dir / PROJECT_CONFIG_FILENAME
        self._file_handler = _ConfigurationFileHandler(self)
        self._observer: Observer | None = None
        self._lock = threading.Lock()
        self._user_configuration: dict[str, str] = {}
        self._project_configurations: dict[str, dict[str, str]] = {}

    def start(self) -> None:
        logger.debug("Starting configuration broadcast service")

        self._config_dir.mkdir(parents=True, exist_ok=True)

        self._load_user_configuration()
        self._load_project_configurations()

        self._observer = Observer()
        self._observer.schedule(self._file_handler, str(self._config_dir), recursive=False)
        self._observer.start()

        logger.debug("Configuration broadcast service started successfully")

    def stop(self) -> None:
        logger.debug("Stopping configuration broadcast service")

        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        logger.debug("Configuration broadcast service stopped")

    def _load_user_configuration(self) -> None:
        if not self._user_config_file.exists():
            logger.debug("No user configuration file found, using defaults")
            self._user_configuration = {}
            return

        try:
            with open(self._user_config_file, "r") as f:
                config_data = json.load(f)
            self._user_configuration = config_data.get("configuration", {})
        except json.JSONDecodeError as e:
            logger.info("Unable to load user configuration: {}", e)
            self._user_configuration = {}

    def _load_project_configurations(self) -> None:
        if not self._project_config_file.exists():
            logger.debug("No project configuration file found, using defaults")
            self._project_configurations = {}
            return

        try:
            with open(self._project_config_file, "r") as f:
                config_data = json.load(f)
            self._project_configurations = config_data.get("project_configurations", {})
        except json.JSONDecodeError as e:
            logger.info("Unable to load project configurations: {}", e)
            self._project_configurations = {}

    def _save_user_configuration(self) -> None:
        config_data = {
            "configuration": {
                **self._user_configuration,
            }
        }
        try:
            with open(self._user_config_file, "w") as f:
                json.dump(config_data, f, indent=2)
            logger.debug("Saved user configuration to file")
        except OSError as e:
            logger.error("Failed to save user configuration: {}", e)

    def _save_project_configurations(self) -> None:
        config_data = {"project_configurations": self._project_configurations}
        try:
            with open(self._project_config_file, "w") as f:
                json.dump(config_data, f, indent=2)
            logger.debug("Saved project configurations to file")
        except OSError as e:
            logger.error("Failed to save project configurations: {}", e)

    @staticmethod
    def _create_configuration_message(configuration: UserConfiguration) -> SetUserConfigurationDataUserMessage:
        # No conversion has been set up as no user message attributes have been defined.
        message = SetUserConfigurationDataUserMessage(anthropic_credentials=configuration.anthropic_credentials)
        return message

    def _create_project_configuration_message(
        self, project_id: ProjectID, configuration: ProjectConfiguration
    ) -> SetProjectConfigurationDataUserMessage:
        with self._lock:
            project_key = str(project_id)
            if project_key not in self._project_configurations:
                self._project_configurations[project_key] = {}

            current_config = self._project_configurations[project_key].copy()

            if configuration.gitlab_token is not None:
                current_config["gitlab_token"] = configuration.gitlab_token
                logger.debug("Updating GitLab token configuration for project: {}", project_id)

                if configuration.token_expires_at_iso is not None:
                    current_config["token_expires_at_iso"] = configuration.token_expires_at_iso
                    logger.debug("Updating GitLab token expiration time for project: {}", project_id)

            if configuration.gitlab_url is not None:
                current_config["gitlab_url"] = configuration.gitlab_url
                logger.debug("Updating GitLab URL configuration for project: {}", project_id)

            message = SetProjectConfigurationDataUserMessage(
                gitlab_token=current_config.get("gitlab_token", ""), gitlab_url=current_config.get("gitlab_url", "")
            )

            self._project_configurations[project_key] = current_config

            self._save_project_configurations()

            return message

    def broadcast_configuration_to_all_tasks(self, configuration: UserConfiguration) -> None:
        logger.debug("Broadcasting configuration to all active tasks")

        message = self._create_configuration_message(configuration)

        with self.data_model_service.open_task_transaction() as transaction:
            all_tasks = transaction.get_all_tasks()
            active_tasks = [task for task in all_tasks if not task.is_deleted]

            logger.debug("Found {} active tasks to broadcast configuration to", len(active_tasks))

            for task in active_tasks:
                logger.debug("Sending configuration message to task: {}", task.object_id)
                self.task_service.create_message(message, task.object_id, transaction)

        logger.debug("Finished broadcasting configuration message to all active tasks")

    def send_configuration_to_task(self, task_id: TaskID, configuration: UserConfiguration) -> None:
        logger.debug("Sending configuration to specific task: {}", task_id)

        message = self._create_configuration_message(configuration)

        with self.data_model_service.open_task_transaction() as transaction:
            self.task_service.create_message(message, task_id, transaction)

        logger.debug("Finished sending configuration message to task: {}", task_id)

    def rebroadcast_current_configuration_to_task(self, task_id: TaskID) -> None:
        logger.debug("Rebroadcasting current configuration to task: {}", task_id)

        current_config = self.get_current_user_configuration()
        message = self._create_configuration_message(current_config)
        logger.debug("Created rebroadcast configuration message: {}", message)

        with self.data_model_service.open_task_transaction() as transaction:
            self.task_service.create_message(message, task_id, transaction)

        logger.debug("Finished rebroadcasting configuration message to task: {}", task_id)

    def send_configuration_to_project(self, project_id: ProjectID, configuration: ProjectConfiguration) -> None:
        logger.debug("Sending configuration to project: {}", project_id)

        project_key = str(project_id)
        project_config = self._project_configurations.get(project_key, {})

        if configuration.gitlab_token is None and configuration.gitlab_url is None and not project_config:
            logger.debug("No configuration to send to project: {}", project_id)
            return

        message = self._create_project_configuration_message(project_id, configuration)

        with self.data_model_service.open_task_transaction() as transaction:
            project_tasks = transaction.get_tasks_for_project(project_id, is_archived=False)
            active_tasks = [task for task in project_tasks if not task.is_deleted]

            logger.debug("Found {} active tasks in project {} to send configuration to", len(active_tasks), project_id)

            for task in active_tasks:
                logger.debug("Sending project configuration message to task: {}", task.object_id)
                self.task_service.create_message(message, task.object_id, transaction)

        logger.debug("Finished sending configuration message to project: {}", project_id)

    def get_current_user_configuration(self) -> UserConfiguration:
        return UserConfiguration()

    def get_current_project_configuration(self, project_id: ProjectID) -> ProjectConfiguration:
        with self._lock:
            project_key = str(project_id)
            project_config = self._project_configurations.get(project_key, {})

            return ProjectConfiguration(
                gitlab_token=project_config.get("gitlab_token"),
                gitlab_url=project_config.get("gitlab_url"),
                token_expires_at_iso=project_config.get("token_expires_at_iso"),
            )

    def is_token_expired(self, configuration: UserConfiguration | ProjectConfiguration) -> bool:
        if not configuration.token_expires_at_iso:
            logger.debug("No token expiration time set, considering token expired")
            return True

        try:
            expires_at = datetime.fromisoformat(configuration.token_expires_at_iso)
            now = datetime.now()
            one_day_from_now = now + timedelta(days=1)
            is_expired_or_expiring_soon = now >= expires_at or expires_at <= one_day_from_now

            if is_expired_or_expiring_soon:
                if now >= expires_at:
                    logger.debug("GitLab token expired at {}, current time is {}", expires_at, now)
                else:
                    logger.debug("GitLab token expires at {} (within 24 hours)", expires_at, now)
            else:
                logger.debug("GitLab token is still valid, expires at {}", expires_at)

            return is_expired_or_expiring_soon
        except ValueError as e:
            logger.error("Invalid token expiration format: {}, considering token expired", e)
            return True
