import json
from abc import ABC
from abc import abstractmethod
from typing import Annotated

from pydantic import Tag

from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from sculptor.primitives.service import Service
from sculptor.utils.secret import Secret


class AnthropicApiKey(SerializableModel):
    object_type: str = "AnthropicApiKey"
    anthropic_api_key: Secret
    # This field was added later, and we may have users who logged in via OAuth before it was added.
    # Keys generated from OAuth are more restricted, so defaulting to True makes more sense.
    generated_from_oauth: bool = True


_MASKED_REFRESH_TOKEN = (
    "sk-ant-ort01-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxx"
)


class ClaudeOauthCredentials(SerializableModel):
    object_type: str = "ClaudeOauthCredentials"
    access_token: Secret
    refresh_token: Secret
    expires_at_unix_ms: int
    scopes: list[str]
    subscription_type: str

    def convert_to_claude_code_credentials_json(self, mask_refresh_token: bool = True) -> str:
        return json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": self.access_token.unwrap(),
                    "refreshToken": (self.refresh_token.unwrap() if not mask_refresh_token else _MASKED_REFRESH_TOKEN),
                    "expiresAt": self.expires_at_unix_ms,
                    "scopes": self.scopes,
                    "subscriptionType": self.subscription_type,
                },
            }
        )


AnthropicCredentials = Annotated[
    Annotated[AnthropicApiKey, Tag("AnthropicApiKey")]
    | Annotated[ClaudeOauthCredentials, Tag("ClaudeOauthCredentials")],
    build_discriminator(),
]


# TODO: This service should be merged into SecretsService;
# See http://go/b/2110.
class AnthropicCredentialsService(Service, ABC):
    @abstractmethod
    def get_anthropic_credentials(self) -> AnthropicCredentials | None: ...

    @abstractmethod
    def set_anthropic_credentials(self, anthropic_credentials: AnthropicCredentials):
        """
        Set Anthropic credentials.

        If the credentials are ClaudeOauthCredentials,
        the service is also responsible for refreshing them.
        """

    @abstractmethod
    def remove_anthropic_credentials(self):
        """Remove the stored Anthropic credentials, and delete the credentials file if it exists."""
