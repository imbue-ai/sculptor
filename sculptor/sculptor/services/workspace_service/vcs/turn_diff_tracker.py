from typing import assert_never

from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.workspace_service.vcs.interfaces import TurnDiffTracker
from sculptor.services.workspace_service.vcs.jj_turn_diff_tracker import JjTurnDiffTracker
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners


def make_turn_diff_tracker(environment: AgentExecutionEnvironment) -> TurnDiffTracker:
    """A tracker for the checkout `environment` works in, baselined on the checkout as it is now."""
    match environment.get_initialization_strategy():
        case (
            WorkspaceInitializationStrategy.IN_PLACE
            | WorkspaceInitializationStrategy.CLONE
            | WorkspaceInitializationStrategy.WORKTREE
        ):
            return DiffTracker(environment)
        case WorkspaceInitializationStrategy.JJ_WORKSPACE:
            jj = build_vcs_runners(
                environment.concurrency_group, environment.get_tool_binary_path, environment.get_project_env_overrides
            ).jj
            return JjTurnDiffTracker(jj, environment.get_working_directory(), environment.concurrency_group)
        case _ as unreachable:
            assert_never(unreachable)
