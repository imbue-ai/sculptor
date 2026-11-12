"""Resolve the branch-rename hint carried by the auto-rename reminder.

Sculptor creates worktree and clone workspaces on a placeholder branch generated
from the repo's branch-naming pattern, for example `dev/gorgeous-emu` from
`<user>/<slug>`. When branch auto-naming is enabled, the first-message reminder
asks the agent to rename that branch to match the workspace name it chose. The
hint is what the reminder needs for that: the branch as it is now, and the
pattern resolved for this user with the slug left for the agent to fill in
(`dev/<slug>`).

There is no hint for an in-place workspace, whose branch is the user's own; nor
when the current branch does not fit the pattern, which happens when the user
typed a custom name or a clone sits on its source branch; nor when the pattern
has no `<slug>` to replace.
"""

from pathlib import Path

from loguru import logger

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.workspace_service.branch_naming import SLUG_PLACEHOLDER
from sculptor.services.workspace_service.branch_naming import resolve_pattern
from sculptor.services.workspace_service.branch_naming import user_slug_from_full_name
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_repo_queries import read_head_identity

# The user-name query runs on the path that assembles the user's first message,
# so a stuck git must not hold up the prompt.
_GIT_QUERY_TIMEOUT_SECONDS = 5.0


class BranchRenameHint(FrozenModel):
    current_branch: str
    # The naming pattern resolved for this user, with `<slug>` left for the agent to fill in.
    target_template: str


def resolve_branch_rename_hint(environment: AgentExecutionEnvironment, naming_pattern: str) -> BranchRenameHint | None:
    if environment.get_initialization_strategy() == WorkspaceInitializationStrategy.IN_PLACE:
        return None
    git = GitCli(
        environment.concurrency_group, environment.get_tool_binary_path, environment.get_project_env_overrides
    )
    checkout = environment.get_working_directory()
    try:
        current_branch = read_head_identity(git, checkout).branch_name
    except VcsCommandError as e:
        logger.debug("Cannot read the branch checked out in {}: {}", checkout, e)
        return None
    if current_branch is None:
        return None
    full_name = _read_git_user_name(git, checkout)
    template = resolve_pattern(
        naming_pattern, user_slug=user_slug_from_full_name(full_name), name_slug=SLUG_PLACEHOLDER
    )
    if not _fits_template(current_branch, template):
        return None
    return BranchRenameHint(current_branch=current_branch, target_template=template)


def _fits_template(branch: str, template: str) -> bool:
    """Whether `branch` could have come from `template` with some non-empty slug in place of `<slug>`."""
    if template.count(SLUG_PLACEHOLDER) != 1:
        return False
    prefix, suffix = template.split(SLUG_PLACEHOLDER)
    return branch.startswith(prefix) and branch.endswith(suffix) and len(branch) > len(prefix) + len(suffix)


def _read_git_user_name(git: GitCli, checkout: Path) -> str:
    """The `user.name` git uses in `checkout`, or empty when it is unset or cannot be read."""
    try:
        result = git.run_git(
            ["config", "user.name"],
            checkout,
            is_read_only=True,
            is_checked=False,
            timeout=_GIT_QUERY_TIMEOUT_SECONDS,
        )
    except VcsCommandError as e:
        logger.debug("Cannot read the git user name in {}: {}", checkout, e)
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
