from sculptor.services.configuration_broadcast_service.api import ConfigurationBroadcastService
from sculptor.services.local_sync_service.api import LocalSyncService
from sculptor.services.task_service.data_types import TaskServiceCollection


class LocalSyncServiceCollection(TaskServiceCollection):
    local_sync_service: LocalSyncService
    configuration_broadcast_service: ConfigurationBroadcastService
