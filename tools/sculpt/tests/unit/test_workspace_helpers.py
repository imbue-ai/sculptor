from sculpt.client.models.workspace_initialization_strategy import WorkspaceInitializationStrategy
from sculpt.commands._workspace_helpers import resolve_strategy


def test_the_jj_strategy_selects_a_jj_workspace() -> None:
    assert resolve_strategy("jj", json_output=False) == WorkspaceInitializationStrategy.JJ_WORKSPACE
