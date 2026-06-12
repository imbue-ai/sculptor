from pathlib import Path
from typing import Final

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from sculptor.utils.build import get_internal_folder

DEFAULT_BACKEND_PORT: Final[int] = 5050

DEFAULT_LOG_PATH: Path = get_internal_folder() / "logs"
TEST_LOG_PATH: Path = Path("/tmp") / "sculptor_test_logs"


# NOTE: the settings keys are all-caps without a prefix in order to be grep-friendly
# (when looking for places where they're being set, e.g. via environment variables).


class TestingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    INTEGRATION_ENABLED: bool = False


class SculptorSettings(BaseSettings):
    """
    This class is for *server* settings *that do not change during runtime*.

    If you want *user* settings or settings that can change while the application is running (eg most settings),
    see `UserConfig` instead.
    """

    model_config = SettingsConfigDict(frozen=True, env_nested_delimiter="__")

    # Add the validation aliases for compatibility with existing code.
    BIND_HOST: str = Field(default="127.0.0.1", validation_alias="SCULPTOR_BIND_HOST")
    BACKEND_PORT: int = Field(default=DEFAULT_BACKEND_PORT, validation_alias="SCULPTOR_API_PORT")
    DATABASE_URL: str = str("sqlite:///" + str(get_internal_folder() / "database.db"))
    LOG_LEVEL: str = "DEBUG"
    TASK_SYNC_DIR: str = str(get_internal_folder() / "artifacts" / "task_sync")
    WORKSPACE_SYNC_DIR: str = str(get_internal_folder() / "artifacts" / "workspace_sync")
    SERVE_STATIC_FILES_DIR: str | None = None
    TESTING: TestingConfig = TestingConfig()
    LOG_PATH: str = str(DEFAULT_LOG_PATH)

    # When provided, all requests are expected to have this exact key in the `x-session-token` header (or GET param or cookie).
    # That way, we can prevent unauthorized access to the API (csrf and similar attacks).
    SESSION_TOKEN: str | None = None

    @property
    def task_sync_path(self) -> Path:
        return Path(self.TASK_SYNC_DIR)

    @property
    def workspace_sync_path(self) -> Path:
        return Path(self.WORKSPACE_SYNC_DIR)

    @property
    def upload_path(self) -> Path:
        return get_internal_folder() / "uploads"


# Think twice before using SculptorSettings directly. We want to be sure to properly inject different settings at test time.
# This is done either by:
#   - Using settings at service collection creation. (All services should take settings values from there, if they need any.)
#   - Using the `get_settings` dependency in FastAPI endpoints.
