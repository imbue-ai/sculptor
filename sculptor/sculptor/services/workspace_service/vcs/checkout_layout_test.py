from pathlib import Path

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.services.workspace_service.vcs.checkout_layout import checkout_path_for_strategy
from sculptor.services.workspace_service.vcs.checkout_layout import is_isolated_checkout


def test_checkout_path_for_strategy_applies_the_same_rule_to_a_strategy_and_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    environment = tmp_path / "env"

    assert checkout_path_for_strategy(WorkspaceInitializationStrategy.IN_PLACE, repo, environment) == repo
    assert checkout_path_for_strategy(WorkspaceInitializationStrategy.CLONE, repo, environment) == environment / "code"
    assert (
        checkout_path_for_strategy(WorkspaceInitializationStrategy.WORKTREE, None, environment) == environment / "code"
    )
    assert (
        checkout_path_for_strategy(WorkspaceInitializationStrategy.JJ_WORKSPACE, repo, environment)
        == environment / "code"
    )


def test_checkout_path_for_strategy_is_none_when_the_directory_it_lives_under_is_unknown(tmp_path: Path) -> None:
    assert checkout_path_for_strategy(WorkspaceInitializationStrategy.IN_PLACE, None, tmp_path / "env") is None
    assert checkout_path_for_strategy(WorkspaceInitializationStrategy.CLONE, tmp_path / "repo", None) is None


def test_every_workspace_but_an_in_place_one_has_an_isolated_checkout() -> None:
    assert not is_isolated_checkout(WorkspaceInitializationStrategy.IN_PLACE)
    assert is_isolated_checkout(WorkspaceInitializationStrategy.CLONE)
    assert is_isolated_checkout(WorkspaceInitializationStrategy.WORKTREE)
    assert is_isolated_checkout(WorkspaceInitializationStrategy.JJ_WORKSPACE)
