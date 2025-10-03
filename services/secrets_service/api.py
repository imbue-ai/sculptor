from abc import ABC
from abc import abstractmethod
from typing import Mapping
from typing import Sequence

from sculptor.primitives.service import Service
from sculptor.utils.secret import Secret


class SecretsService(Service, ABC):
    @abstractmethod
    def get_secrets(self, secret_names: Sequence[str] | None) -> dict[str, Secret]:
        """
        Retrieve secrets by their names.

        :param secret_names: List of secret names to retrieve.  If None, all secrets should be returned.
        :return: Dictionary mapping secret names to their values.
        """

    @abstractmethod
    def set_secrets(self, secrets: Mapping[str, str | Secret]) -> None:
        """
        Saves all secrets.
        """
