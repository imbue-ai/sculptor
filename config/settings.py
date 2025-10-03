from pathlib import Path
from tempfile import gettempdir
from typing import Final

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from sculptor.utils.build import get_sculptor_folder

DEFAULT_FRONTEND_PORT: Final[int] = 5174
DEFAULT_BACKEND_PORT: Final[int] = 5050

DEFAULT_LOG_PATH: Path = get_sculptor_folder() / "logs"
TEST_LOG_PATH: Path = Path("/tmp") / "sculptor_test_logs"


# NOTE: the settings keys are all-caps without a prefix in order to be grep-friendly
# (when looking for places where they're being set, e.g. via environment variables).


class TestingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    INTEGRATION_ENABLED: bool = False
    SNAPSHOT_PATH: str | None = None
    CONTAINER_PREFIX: str | None = None


class SculptorSettings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, env_nested_delimiter="__")

    DOMAIN: str = "localhost"
    PROTOCOL: str = "http"
    IMBUE_GATEWAY_BASE_URL: str = "https://imbue-gateway.fly.dev/api/v1/"
    GITLAB_DEFAULT_TOKEN: str = ""
    # Add the validation aliases for compatibility with existing code.
    BACKEND_PORT: int = Field(default=DEFAULT_BACKEND_PORT, validation_alias="SCULPTOR_API_PORT")
    FRONTEND_PORT: int = Field(default=DEFAULT_FRONTEND_PORT, validation_alias="SCULPTOR_FRONTEND_PORT")
    MODAL_APP_NAME: str = "sculptor-dev"
    DATABASE_URL: str = str("sqlite:///" + str(get_sculptor_folder() / "database.db"))
    LOG_LEVEL: str = "DEBUG"
    # This is a convenience flag that is True by default for now to make local development easier.
    # We should disable it as soon as we think about remote deployments.
    ALLOW_ANONYMOUS_USERS: bool = True
    TASK_SYNC_DIR: str = str(Path(gettempdir()) / "task_sync")
    SERVE_STATIC_FILES_DIR: str | None = None
    TESTING: TestingConfig = TestingConfig()
    LOG_PATH: str = str(DEFAULT_LOG_PATH)
    DEV_MODE: bool = False
    AUTHENTIK_BASE_URL: str = "https://auth.imbue.com/"
    AUTHENTIK_APPLICATION_NAME: str = "sculptor-local"
    # Taken from the provider configuration in Authentik.
    AUTHENTIK_CLIENT_ID: str = "zd0Xy1PMBnH3OJUU1dGZRhmPC83KKWaLI5ckuH7P"
    # When non-empty, is used instead of retrieving the key from Authentik.
    # (Used mostly for testing.)
    JWT_PUBLIC_KEY_PATH: str | None = None
    # A comma-separated list of extra artifact view IDs to enable in the frontend
    #   available artifact views are defined in frontend/src/pages/chat/artifact-views/Registry.ts
    ENABLED_FRONTEND_ARTIFACT_VIEWS: str = ""
    IS_FORKING_ENABLED: bool = False

    # This flag enables checks to be read and start execution, but if users disable the suggestions feature on the settings page, the checks will return early without executing.
    # TODO (andrew.laack): Remove all suggestions/checks related flags and settings once we move the suggestions feature away from 'experimental'.
    IS_CHECKS_ENABLED: bool = True
    IS_IMBUE_VERIFY_CHECK_ENABLED: bool = True

    DOCKER_PROVIDER_ENABLED: bool = True
    MODAL_PROVIDER_ENABLED: bool = False
    LOCAL_PROVIDER_ENABLED: bool = False

    # When provided, all requests are expected to have this exact key in the `x-app-secret` header.
    # That way, we can prevent unauthorized access to the API (csrf and similar attacks).
    # (We used to employ the standard double-submit-cookie pattern but the Electron frontend
    # is served from a different origin (file://) which makes it impossible to set SameSite cookies.)
    ELECTRON_APP_SECRET: str | None = None

    @property
    def task_sync_path(self) -> Path:
        return Path(self.TASK_SYNC_DIR)

    @property
    def is_imbue_gateway_configured(self) -> bool:
        return self.IMBUE_GATEWAY_BASE_URL != ""

    @field_validator("IMBUE_GATEWAY_BASE_URL")
    def must_end_with_slash_or_empty(cls, value: str) -> str:
        """
        To prevent issues with urljoin, we require the base URL to end with a slash.

        Empty string is allowed to disable the gateway integration.

        """
        if value != "" and not value.endswith("/"):
            # This will be wrapped by pydantic into a ValidationError.
            raise ValueError("base_url must be empty or end with a slash '/'")
        return value


# Think twice before using SculptorSettings directly. We want to be sure to properly inject different settings at test time.
# This is done either by:
#   - Using settings at service collection creation. (All services should take settings values from there, if they need any.)
#   - Using the `get_settings` dependency in FastAPI endpoints.
