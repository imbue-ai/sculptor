import typer

from sculpt.commands.agent import agent_app
from sculpt.commands.debug import debug_app
from sculpt.commands.extension import extension_app
from sculpt.commands.repo import repo_app
from sculpt.commands.run import run_cmd
from sculpt.commands.schema import schema_app
from sculpt.commands.signal import signal_app
from sculpt.commands.ui import ui_app
from sculpt.commands.workspace import workspace_app

app = typer.Typer(
    name="sculpt",
    help="CLI client for the Sculptor API",
    epilog=(
        "Every Sculptor agent shell exports SCULPT_AGENT_ID, SCULPT_WORKSPACE_ID, and"
        + " SCULPT_PROJECT_ID identifying that shell's own agent, workspace, and repo."
        + " Commands use them as defaults where noted (e.g. `sculpt agent show` with no"
        + " argument shows your own agent). Outside a Sculptor shell, set SCULPT_API_PORT"
        + " or pass --base-url if the app serves a non-default port."
    ),
)

app.add_typer(workspace_app, name="workspace")
app.add_typer(workspace_app, name="ws", hidden=True)
app.add_typer(agent_app, name="agent")
app.add_typer(extension_app, name="extension")
# Hidden compatibility alias: in-flight agent sessions and older skill copies
# still invoke `sculpt plugin`; it runs the same group as `sculpt extension`.
app.add_typer(extension_app, name="plugin", hidden=True)
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
