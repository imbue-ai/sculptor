class ModalExecutorError(Exception):
    pass


class ModalExecutorTransientError(ModalExecutorError):
    pass


class ModalProcessPidError(ModalExecutorError):
    pass


class ModalExecutorTimeoutError(ModalExecutorTransientError):
    pass


class ModalExecutionInvalidError(ModalExecutorError):
    pass
