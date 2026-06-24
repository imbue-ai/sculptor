import typer

from sculpt.commands.agent import agent_app
from sculpt.commands.debug import debug_app
from sculpt.commands.repo import repo_app
from sculpt.commands.run import run_cmd
from sculpt.commands.schema import schema_app
from sculpt.commands.signal import signal_app
from sculpt.commands.ui import ui_app
from sculpt.commands.workspace import workspace_app

app = typer.Typer(
    name="sculpt",
    help="CLI client for the Sculptor API",
)

app.add_typer(workspace_app, name="workspace")
app.add_typer(workspace_app, name="ws", hidden=True)
app.add_typer(agent_app, name="agent")
app.add_typer(repo_app, name="repo")
app.add_typer(schema_app, name="schema")
app.add_typer(signal_app, name="signal")
app.add_typer(debug_app, name="debug")
app.add_typer(ui_app, name="ui")
app.command("run")(run_cmd)


def version_callback(value: bool) -> None:
    if value:
        typer.echo("sculpt 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show the sculpt CLI version.",
    ),
) -> None:
    """CLI client for the Sculptor API."""


if __name__ == "__main__":
    app()
