from imbue_core.pydantic_serialization import FrozenModel
from sculptor.config.settings import SculptorSettings
from sculptor.services.configuration_broadcast_service.api import ConfigurationBroadcastService
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.task_service.api import TaskService


class ConfigurationBroadcastServiceCollection(FrozenModel):
    settings: SculptorSettings
    configuration_broadcast_service: ConfigurationBroadcastService
    data_model_service: DataModelService
    task_service: TaskService
