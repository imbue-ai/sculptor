"""
Used for manually testing the anthropic_oauth module.
"""
from typing import Annotated

import typer

from sculptor.config.anthropic_oauth import start_anthropic_oauth, AnthropicAccountType
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService, AnthropicCredentials


app = typer.Typer()
class DemoAnthropicCredentialsService(AnthropicCredentialsService):
    def get_anthropic_credentials(self) -> AnthropicCredentials | None:
        return None

    def set_anthropic_credentials(self, anthropic_credentials: AnthropicCredentials):
        print(f"Anthropic credentials: {anthropic_credentials.model_dump_json()}")


@app.command()
def run(
        account_type: Annotated[AnthropicAccountType, typer.Option( "--account-type")] = AnthropicAccountType.ANTHROPIC_CONSOLE
):
    server_thread, url = start_anthropic_oauth(
        DemoAnthropicCredentialsService(),
        account_type,
    )
    print(url)
    server_thread.join()


if __name__ == "__main__":
    app()
