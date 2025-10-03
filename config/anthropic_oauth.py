import socket
import time
from enum import StrEnum
from threading import Event

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import ConfigDict
from uvicorn import Config
from uvicorn import Server

from imbue_core.pydantic_serialization import FrozenModel
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.thread_utils import ObservableThread
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.anthropic_credentials_service.api import ClaudeOauthCredentials
from sculptor.services.anthropic_credentials_service.default_implementation import CLAUDE_CODE_CLIENT_ID
from sculptor.services.anthropic_credentials_service.default_implementation import TokenResponse
from sculptor.utils.secret import Secret
from sculptor.web.auth import generate_pkce_verifier_challenge_and_state

# TODO: This module should be moved somewhere near SecretsService.


class AnthropicAccountType(StrEnum):
    CLAUDE = "CLAUDE"
    ANTHROPIC_CONSOLE = "ANTHROPIC_CONSOLE"


class PortAvailableServer(Server):
    """
    Useful when we're binding to port 0 and need to know the actual port.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.port_available_event = Event()
        self.port: int | None = None

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        self.port = self.servers[0].sockets[0].getsockname()[1]
        self.port_available_event.set()


class State(MutableModel):
    server: PortAvailableServer
    server_thread: ObservableThread
    server_port: int
    anthropic_credentials_service: AnthropicCredentialsService
    account_type: AnthropicAccountType
    pkce_state: str
    pkce_code_verifier: str


class Organization(FrozenModel):
    model_config = ConfigDict(extra="ignore")
    organization_type: str


class ProfileResponse(FrozenModel):
    model_config = ConfigDict(extra="ignore")
    organization: Organization


app_state: State | None = None

app = FastAPI()


# Important: Anthropic requires the redirect_uri to look like http://localhost:{port}/callback;
# other paths won't work.
@app.get("/callback")
async def oauth_callback(code: str, state: str):
    global app_state
    # app_state can be None if you get a callback from a previously instance of Sculptor
    if app_state is None or state != app_state.pkce_state:
        raise HTTPException(status_code=400, detail="Invalid state")
    with httpx.Client() as client:
        raw_response = client.post(
            "https://console.anthropic.com/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"http://localhost:{app_state.server_port}/callback",
                "client_id": CLAUDE_CODE_CLIENT_ID,
                "code_verifier": app_state.pkce_code_verifier,
                # The state parameter is optional in the standard, but required by Anthropic
                "state": app_state.pkce_state,
            },
            headers={"Accept": "application/json"},
        )
        token_response = TokenResponse.model_validate_json(raw_response.content)
    access_token = token_response.access_token

    if app_state.account_type == AnthropicAccountType.CLAUDE:
        refresh_token = token_response.refresh_token
        with httpx.Client() as client:
            raw_response = client.get(
                "https://api.anthropic.com/api/oauth/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_response = ProfileResponse.model_validate_json(raw_response.content)
        subscription_type = profile_response.organization.organization_type.removeprefix("claude_")
        app_state.anthropic_credentials_service.set_anthropic_credentials(
            ClaudeOauthCredentials(
                access_token=Secret(access_token),
                refresh_token=Secret(refresh_token),
                expires_at_unix_ms=int((time.time() + token_response.expires_in) * 1000),
                scopes=token_response.scope.split(" "),
                subscription_type=subscription_type,
            )
        )
    else:
        with httpx.Client() as client:
            api_key_response = client.post(
                "https://api.anthropic.com/api/oauth/claude_cli/create_api_key",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            api_key_json = api_key_response.json()
        anthropic_api_key = api_key_json["raw_key"]

        app_state.anthropic_credentials_service.set_anthropic_credentials(
            AnthropicApiKey(anthropic_api_key=anthropic_api_key, generated_from_oauth=True)
        )

    app_state.server.should_exit = True
    app_state = None
    return RedirectResponse(url="https://console.anthropic.com/oauth/code/success?app=claude-code")


def start_anthropic_oauth(
    anthropic_credentials_service: AnthropicCredentialsService, account_type: AnthropicAccountType
) -> (ObservableThread, str):
    global app_state
    if app_state is not None:
        # Reuse the existing server so that we don't start an unbound number of servers.
        # Assume the previous state is no longer needed.
        server = app_state.server
        server_thread = app_state.server_thread
    else:
        server = PortAvailableServer(config=Config(app, host="127.0.0.1", port=0))
        server_thread = ObservableThread(target=server.run)
        server_thread.start()
        server.port_available_event.wait()

    pkce_state, code_verifier, code_challenge = generate_pkce_verifier_challenge_and_state()
    app_state = State(
        server=server,
        server_thread=server_thread,
        server_port=server.port,
        anthropic_credentials_service=anthropic_credentials_service,
        account_type=account_type,
        pkce_state=pkce_state,
        pkce_code_verifier=code_verifier,
    )
    if account_type == AnthropicAccountType.CLAUDE:
        authorize_url = "https://claude.ai/oauth/authorize"
    else:
        authorize_url = "https://console.anthropic.com/oauth/authorize"
    return (
        server_thread,
        f"{authorize_url}?code=true&client_id={CLAUDE_CODE_CLIENT_ID}&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A{server.port}%2Fcallback&scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainference&code_challenge={code_challenge}&code_challenge_method=S256&state={pkce_state}",
    )


def cancel_anthropic_oauth() -> None:
    global app_state
    if app_state is not None:
        app_state.server.should_exit = True
        app_state = None
