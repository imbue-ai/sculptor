from imbue_core.errors import ExpectedError
from sculptor.interfaces.environments.v1.errors import ProviderError


class DockerError(ExpectedError):
    pass


class DockerNotInstalledError(DockerError):
    pass


class NoServerPortBoundError(DockerError):
    pass


class ContainerNotRunningError(ProviderError):
    pass


class ContainerPausedError(ProviderError):
    pass


class ProviderIsDownError(ProviderError):
    pass
