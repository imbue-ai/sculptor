import json
import time
from pathlib import Path
from threading import Event

import httpx
from loguru import logger
from pydantic import ConfigDict
from pydantic import ValidationError

from imbue_core.pydantic_serialization import FrozenModel
from imbue_core.pydantic_serialization import SerializableModel
from sculptor.config.user_config import get_user_config_instance
from sculptor.primitives.threads import ObservableThread
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.anthropic_credentials_service.api import ClaudeOauthCredentials
from sculptor.services.configuration_broadcast_service.api import ConfigurationBroadcastService
from sculptor.services.configuration_broadcast_service.api import UserConfiguration
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.secret import Secret

# We pretend to be Claude Code when initiating the OAuth flow.
CLAUDE_CODE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_REFRESH_TOKEN_EXPIRY_BUFFER_SECONDS = 60 * 60


class Credentials(SerializableModel):
    anthropic: AnthropicCredentials


class TokenResponse(FrozenModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str
    refresh_token: str
    expires_in: int  # seconds
    scope: str


class DefaultAnthropicCredentialsService(AnthropicCredentialsService):
    anthropic_credentials: AnthropicCredentials | None = None
    token_refresh_stop_event: Event = Event()
    token_refresh_thread: ObservableThread | None = None
    credentials_file_path: Path = get_sculptor_folder() / "credentials.json"
    configuration_broadcast_service: ConfigurationBroadcastService | None = None

    def start(self) -> None:
        try:
            credentials = Credentials.model_validate_json(self.credentials_file_path.read_text())
            self.set_anthropic_credentials(credentials.anthropic)
        except (FileNotFoundError, ValidationError):
            user_config = get_user_config_instance()
            if user_config and user_config.anthropic_api_key:
                self.set_anthropic_credentials(
                    AnthropicApiKey(
                        anthropic_api_key=Secret(user_config.anthropic_api_key), generated_from_oauth=False
                    )
                )

    def stop(self) -> None:
        if self.token_refresh_thread:
            self._stop_token_refresh_thread()

    def get_anthropic_credentials(self) -> AnthropicCredentials | None:
        return self.anthropic_credentials

    def set_anthropic_credentials(self, anthropic_credentials: AnthropicCredentials):
        old_credentials_is_claude_oauth = isinstance(self.anthropic_credentials, ClaudeOauthCredentials)
        new_credentials_is_claude_oauth = isinstance(anthropic_credentials, ClaudeOauthCredentials)
        if old_credentials_is_claude_oauth and not new_credentials_is_claude_oauth:
            self._stop_token_refresh_thread()
        self.anthropic_credentials = anthropic_credentials
        if isinstance(anthropic_credentials, ClaudeOauthCredentials) and self.configuration_broadcast_service:
            self.configuration_broadcast_service.broadcast_configuration_to_all_tasks(
                UserConfiguration(
                    anthropic_credentials=anthropic_credentials,
                )
            )
        populate_credentials_file(self.credentials_file_path, anthropic_credentials)
        if not old_credentials_is_claude_oauth and new_credentials_is_claude_oauth:
            self._start_token_refresh_thread()

    def _start_token_refresh_thread(self) -> None:
        self.token_refresh_thread = ObservableThread(target=self._token_refresh_thread_target)
        self.token_refresh_thread.start()

    def _stop_token_refresh_thread(self) -> None:
        self.token_refresh_stop_event.set()
        self.token_refresh_thread.join()
        self.token_refresh_thread = None
        self.token_refresh_stop_event = Event()

    def _token_refresh_thread_target(self) -> None:
        first_iteration = True
        while True:
            if first_iteration:
                first_iteration = False
            else:
                # Wait for a short time between all iterations,
                # but not before the first iteration -
                # the OAuth token might already have expired when Sculptor starts.
                #
                # The timeout may seem unnecessarily short short,
                # as the token is usually valid for at least a couple of hours.
                # However, the user's computer could go to sleep and we can overshoot the expiry.
                # Minimize that possiblity by checking more frequently.
                should_stop = self.token_refresh_stop_event.wait(timeout=30)
                if should_stop:
                    break
            logger.debug("Claude OAuth token refresh thread has woken up")
            anthropic_credentials = self.anthropic_credentials
            assert isinstance(anthropic_credentials, ClaudeOauthCredentials)
            if time.time() < anthropic_credentials.expires_at_unix_ms / 1000 - _REFRESH_TOKEN_EXPIRY_BUFFER_SECONDS:
                continue
            logger.info("Refreshing Claude OAuth tokens")
            refresh_token = anthropic_credentials.refresh_token.unwrap()
            with httpx.Client() as client:
                try:
                    raw_response = client.post(
                        "https://console.anthropic.com/v1/oauth/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": CLAUDE_CODE_CLIENT_ID,
                        },
                        headers={"Accept": "application/json"},
                    )
                    token_response = TokenResponse.model_validate_json(raw_response.content)
                except Exception as e:
                    logger.error("Error refreshing Claude OAuth credentials: {e}", e=e)
                    # If we have failed, the response wouldn't contain any secret credentials,
                    # so it's safe to log.
                    logger.info("Raw response: {}", raw_response.content)
                    logger.info("Ignoring the error; we'll try again later")
                    continue
            self.anthropic_credentials = ClaudeOauthCredentials(
                access_token=Secret(token_response.access_token),
                refresh_token=Secret(token_response.refresh_token),
                expires_at_unix_ms=int((time.time() + token_response.expires_in) * 1000),
                scopes=token_response.scope.split(" "),
                subscription_type=anthropic_credentials.subscription_type,
            )
            populate_credentials_file(self.credentials_file_path, self.anthropic_credentials)
            if self.configuration_broadcast_service:
                self.configuration_broadcast_service.broadcast_configuration_to_all_tasks(
                    UserConfiguration(
                        anthropic_credentials=self.anthropic_credentials,
                    )
                )

    def remove_anthropic_credentials(self) -> None:
        self.anthropic_credentials = None
        try:
            self.credentials_file_path.unlink()
        except FileNotFoundError:
            pass


def populate_credentials_file(path: Path, anthropic_credentials: AnthropicCredentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_dict = Credentials(anthropic=anthropic_credentials).model_dump()
    if json_dict["anthropic"]["object_type"] == "AnthropicApiKey":
        json_dict["anthropic"]["anthropic_api_key"] = anthropic_credentials.anthropic_api_key.unwrap()
    elif json_dict["anthropic"]["object_type"] == "ClaudeOauthCredentials":
        json_dict["anthropic"]["refresh_token"] = anthropic_credentials.refresh_token.unwrap()
        json_dict["anthropic"]["access_token"] = anthropic_credentials.access_token.unwrap()
    else:
        raise ValueError(f"Unknown object type: {json_dict['anthropic']['object_type']}")
    path.write_text(json.dumps(json_dict))


def populate_credentials_file_for_test(path: Path) -> None:
    populate_credentials_file(path, AnthropicApiKey(anthropic_api_key=Secret("sk-ant-fake-api-key")))
