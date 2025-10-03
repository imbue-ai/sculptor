from sculptor.config.settings import SculptorSettings
from sculptor.primitives.service import Service
from sculptor.services.configuration_broadcast_service.service_collection import (
    get_configuration_broadcast_service_collection,
)
from sculptor.services.local_sync_service.default_implementation import DefaultLocalSyncService
from sculptor.services.local_sync_service.service_collection import LocalSyncServiceCollection
from sculptor.services.task_service.data_types import TaskServiceCollection
from sculptor.services.task_service.service_collection import get_task_service_collection
from sculptor.utils.functional import cached_and_locked
from sculptor.utils.timeout import log_runtime


def _resolve_local_sync_service(service_collection: TaskServiceCollection) -> DefaultLocalSyncService:
    return DefaultLocalSyncService(
        git_repo_service=service_collection.git_repo_service,
        data_model_service=service_collection.data_model_service,
        task_service=service_collection.task_service,
    )


class CompleteServiceCollection(LocalSyncServiceCollection):
    @property
    def _services_in_dependency_order(self) -> tuple[Service, ...]:
        return (
            self.secrets_service,
            self.data_model_service,
            self.project_service,
            self.environment_service,
            self.git_repo_service,
            self.task_service,
            self.local_sync_service,
            self.configuration_broadcast_service,
            self.anthropic_credentials_service,
        )

    def start_all(self) -> None:
        for service in self._services_in_dependency_order:
            with log_runtime(f"SERVICES.start.{service.__class__.__name__}"):
                service.start()

    def stop_all(self) -> None:
        for service in reversed(self._services_in_dependency_order):
            with log_runtime(f"SERVICES.stop.{service.__class__.__name__}"):
                service.stop()


@cached_and_locked
def get_services_cached(settings: SculptorSettings) -> CompleteServiceCollection:
    services = get_task_service_collection(settings)

    configuration_broadcast_service = get_configuration_broadcast_service_collection(
        settings=settings,
        data_model_service=services.data_model_service,
        task_service=services.task_service,
    ).configuration_broadcast_service

    services.anthropic_credentials_service.configuration_broadcast_service = configuration_broadcast_service

    return CompleteServiceCollection(
        settings=settings,
        data_model_service=services.data_model_service,
        task_service=services.task_service,
        environment_service=services.environment_service,
        secrets_service=services.secrets_service,
        anthropic_credentials_service=services.anthropic_credentials_service,
        git_repo_service=services.git_repo_service,
        project_service=services.project_service,
        local_sync_service=_resolve_local_sync_service(services),
        configuration_broadcast_service=configuration_broadcast_service,
    )


def get_services(settings: SculptorSettings) -> CompleteServiceCollection:
    services = get_task_service_collection(settings)
    configuration_broadcast_service_collection = get_configuration_broadcast_service_collection(
        settings=settings,
        data_model_service=services.data_model_service,
        task_service=services.task_service,
    )
    services.anthropic_credentials_service.configuration_broadcast_service = (
        configuration_broadcast_service_collection.configuration_broadcast_service
    )
    return CompleteServiceCollection(
        settings=settings,
        data_model_service=services.data_model_service,
        task_service=services.task_service,
        environment_service=services.environment_service,
        secrets_service=services.secrets_service,
        anthropic_credentials_service=services.anthropic_credentials_service,
        git_repo_service=services.git_repo_service,
        project_service=services.project_service,
        local_sync_service=_resolve_local_sync_service(services),
        configuration_broadcast_service=configuration_broadcast_service_collection.configuration_broadcast_service,
    )
