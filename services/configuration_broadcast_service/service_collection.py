from sculptor.config.settings import SculptorSettings
from sculptor.services.configuration_broadcast_service.data_types import ConfigurationBroadcastServiceCollection
from sculptor.services.configuration_broadcast_service.default_implementation import (
    DefaultConfigurationBroadcastService,
)
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.task_service.api import TaskService


def get_configuration_broadcast_service_collection(
    settings: SculptorSettings,
    data_model_service: DataModelService,
    task_service: TaskService,
) -> ConfigurationBroadcastServiceCollection:
    configuration_broadcast_service = DefaultConfigurationBroadcastService(
        data_model_service=data_model_service,
        task_service=task_service,
    )

    return ConfigurationBroadcastServiceCollection(
        settings=settings,
        configuration_broadcast_service=configuration_broadcast_service,
        data_model_service=data_model_service,
        task_service=task_service,
    )
