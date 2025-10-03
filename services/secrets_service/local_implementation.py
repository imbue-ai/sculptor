import os
from pathlib import Path
from typing import Mapping
from typing import Sequence

from dotenv import dotenv_values
from dotenv import set_key
from loguru import logger

from imbue_core.gitlab_management import GITLAB_TOKEN_NAME
from sculptor.services.secrets_service.api import SecretsService
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.secret import Secret


class LocalSecretsService(SecretsService):
    secret_file_path: Path = get_sculptor_folder() / ".env"

    def start(self) -> None:
        self.secret_file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_secrets(self, secret_names: Sequence[str] | None = None) -> dict[str, Secret]:
        file_secrets = {}
        if self.secret_file_path.exists():
            file_secrets = dotenv_values(self.secret_file_path)

        secrets = file_secrets
        if os.getenv(GITLAB_TOKEN_NAME) is not None:
            # If the user has this token in their environment, propagate it into the agent.
            secrets[GITLAB_TOKEN_NAME] = os.environ[GITLAB_TOKEN_NAME]

        if secret_names is not None:
            secrets = {name: secrets[name] for name in secret_names if name in secrets}

        secrets = {key: Secret(value) for key, value in secrets.items()}

        return secrets

    def set_secrets(self, secrets: Mapping[str, str | Secret]) -> None:
        logger.debug("Saving {} secrets to {}", len(secrets), self.secret_file_path)

        self.secret_file_path.parent.mkdir(parents=True, exist_ok=True)

        for key, value in secrets.items():
            set_key(
                dotenv_path=str(self.secret_file_path),
                key_to_set=key,
                value_to_set=value.unwrap() if isinstance(value, Secret) else value,
                quote_mode="auto",
            )
