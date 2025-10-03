from sculptor.interfaces.environments.v1.provider_status import DownStatus


class DockerNotAvailableStatus(DownStatus):
    message: str = "Docker is not available"


class DockerDaemonNotRunningStatus(DownStatus):
    message: str = "Docker daemon is not running"


class DockerPermissionDeniedStatus(DownStatus):
    message: str = "Permission denied accessing Docker"
