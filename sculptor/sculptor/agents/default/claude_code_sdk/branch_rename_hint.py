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

from loguru import logger

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.workspace_service.branch_naming import SLUG_PLACEHOLDER
from sculptor.services.workspace_service.branch_naming import resolve_pattern
from sculptor.services.workspace_service.branch_naming import user_slug_from_full_name


class BranchRenameHint(FrozenModel):
    current_branch: str
    # The naming pattern resolved for this user, with `<slug>` left for the agent to fill in.
    target_template: str


def resolve_branch_rename_hint(environment: AgentExecutionEnvironment, naming_pattern: str) -> BranchRenameHint | None:
    if environment.get_initialization_strategy() == WorkspaceInitializationStrategy.IN_PLACE:
        return None
    current_branch = _git_stdout(environment, ["git", "symbolic-ref", "--short", "HEAD"])
    if current_branch is None:
        return None
    full_name = _git_stdout(environment, ["git", "config", "user.name"]) or ""
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


def _git_stdout(environment: AgentExecutionEnvironment, command: list[str]) -> str | None:
    """Stripped stdout of a read-only git command run in the workspace checkout, or None if it failed."""
    try:
        result = environment.run_process_to_completion(
            command, secrets={}, cwd=str(environment.get_working_directory()), is_checked_after=False
        )
    except ProcessError as e:
        logger.debug("git query {} failed: {}", " ".join(command), e)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
