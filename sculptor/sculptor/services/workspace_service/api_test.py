from sculptor.services.workspace_service.api import resolve_workspace_setup_command

_DEFAULT_COMMAND = "vcs fetch --quietly"


def test_resolve_workspace_setup_command_runs_the_given_default_for_an_unconfigured_project() -> None:
    assert resolve_workspace_setup_command(None, _DEFAULT_COMMAND) == _DEFAULT_COMMAND


def test_resolve_workspace_setup_command_runs_nothing_once_the_user_clears_it() -> None:
    assert resolve_workspace_setup_command("", _DEFAULT_COMMAND) is None


def test_resolve_workspace_setup_command_runs_the_project_command_instead_of_the_default() -> None:
    assert resolve_workspace_setup_command("make setup", _DEFAULT_COMMAND) == "make setup"
