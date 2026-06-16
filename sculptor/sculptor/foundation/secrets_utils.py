from pydantic import SecretStr


class Secret(SecretStr):
    """Pydantic-aware secret wrapper that hides values in logs."""

    def __str__(self) -> str:
        return "[redacted]"

    __repr__ = __str__

    def unwrap(self) -> str:
        return self.get_secret_value()
