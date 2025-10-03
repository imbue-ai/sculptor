"""
Runs frontend `npm run` commands from python.

This allows us to control the behavior of these commands and ensure that they are run in the correct environment.

Run `uv run sculptor_npm_run --help` to see the available commands.

Note: this command must be run from within the Generally Intelligent repo.
"""

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import typer
from typer import Typer

from imbue_core.git import get_git_repo_root


@lru_cache
def get_frontend_path() -> Path:
    return get_git_repo_root() / "sculptor" / "frontend"


def verify_node_is_installed(frontend_path: Path = get_frontend_path()) -> None:
    result = subprocess.run(("node", "--version"), check=True, capture_output=True)
    actual_node_version = result.stdout.decode().strip()
    # TODO: Because of how nvm sets up, this may trigger because you can't run
    # nvm use in the subshell where node is trying to run. We intend to solve
    # this in the future, but for now you may run the command marked "HACK" in
    # crafty/crafty/README.md#1.2 Set Up Node
    expected_node_version = (frontend_path / ".nvmrc").read_text().strip()
    assert actual_node_version == expected_node_version, (
        f"Node version mismatch: expected {expected_node_version} got {actual_node_version}. Install the correct version with: nvm install {expected_node_version} && nvm use {expected_node_version}"
    )


def install_node_packages(frontend_path: Path = get_frontend_path(), is_auto_verifying_node: bool = True) -> None:
    if is_auto_verifying_node:
        verify_node_is_installed(frontend_path=frontend_path)
    subprocess.run(("npm", "install", "--silent"), check=True, cwd=frontend_path)


def run_npm_command(
    sub_command: tuple[str, ...],
    other_args: list[str],
    help: bool = False,
    frontend_path: Path = get_frontend_path(),
    is_auto_verifying_node: bool = True,
    rebase_paths: bool = False,
    allow_failures: bool = False,
) -> None:
    if is_auto_verifying_node:
        verify_node_is_installed(frontend_path=frontend_path)

    if rebase_paths:
        root = frontend_path.resolve()
        other_args_tuple = tuple(
            str(Path(arg).resolve().relative_to(root)) if not arg.startswith("-") else arg for arg in other_args
        )
    else:
        other_args_tuple = tuple(other_args)

    fully_resolved_command = ("npm",) + sub_command + other_args_tuple
    if help:
        fully_resolved_command += ("--help",)

    check_exit_code = not allow_failures
    try:
        subprocess.run(fully_resolved_command, check=check_exit_code, cwd=frontend_path)
    except subprocess.CalledProcessError as error:
        # We intentially only print this error rather than a full stack trace.
        # We only need a simple line, and a stack trace would be overkill.
        print(f"Command '{' '.join(fully_resolved_command)}' failed with exit code {error.returncode}")
        raise typer.Exit(-1)


app = Typer(pretty_exceptions_enable=False)


@app.callback()
def setup(
    skip_install: bool = typer.Option(False, "--skip-install", is_flag=True),
) -> None:
    """Run npm commands with proper environment setup."""
    is_help_present = any(arg in sys.argv for arg in ["--help", "-h"])
    if not skip_install and not is_help_present:
        install_node_packages()


def _get_commands_from_package_json() -> tuple[str, ...]:
    package_json = get_frontend_path() / "package.json"
    package_json_contents = json.loads(package_json.read_text())
    return tuple(package_json_contents["scripts"].keys())


_CUSTOM_COMMANDS: tuple[tuple[str, ...], ...] = (("install",), ("uninstall",))


def _register_command(cmd: tuple[str, ...]) -> None:
    def command_callback(
        other_args: list[str] = typer.Argument(None),
        help: bool = typer.Option(False, "--help", is_flag=True),
        rebase_paths: bool = typer.Option(False, "--rebase-paths", is_flag=True),
        is_auto_verifying_node: bool = typer.Option(True, "--is-auto-verifying-node/--no-is-auto-verifying-node"),
        allow_failures: bool = typer.Option(False, "--allow-failures", is_flag=True),
    ) -> None:
        run_npm_command(
            sub_command=cmd,
            other_args=other_args or [],
            help=help,
            rebase_paths=rebase_paths,
            is_auto_verifying_node=is_auto_verifying_node,
            allow_failures=allow_failures,
        )

    app.command(
        name=cmd[-1],
        help=f"Runs `npm {' '.join(cmd)}`",
    )(command_callback)


def _register_commands() -> None:
    package_json_commands = tuple(("run", command_name) for command_name in _get_commands_from_package_json())
    for cmd in package_json_commands + _CUSTOM_COMMANDS:
        _register_command(cmd)


_register_commands()


if __name__ == "__main__":
    app()
