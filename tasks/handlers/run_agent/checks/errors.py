from imbue_core.errors import ExpectedError


class ExpectedCheckConfigParsingError(ExpectedError):
    pass


class RestartCheckError(ExpectedError):
    pass


class CheckStopped(ExpectedError):
    pass


class CheckTimeout(ExpectedError, TimeoutError):
    pass


class ConfigValidationError(ExpectedError):
    pass
