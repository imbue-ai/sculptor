"""Whether a repository creates jj workspaces, and the facts that decide it."""

from sculptor.database.models import Project
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_repo_queries import is_jj_colocated
from sculptor.web.data_types import JjReadiness


class JjWorkspaceCreationFacts(SerializableModel):
    """The facts that decide whether a repository's new workspaces are jj workspaces."""

    use_jj_for_new_workspaces: bool
    is_colocated: bool
    jj_readiness: JjReadiness


def creates_jj_workspaces(facts: JjWorkspaceCreationFacts) -> bool:
    """New workspaces are jj workspaces when the flag is on, the repository is colocated and jj is available."""
    return facts.use_jj_for_new_workspaces and facts.is_colocated and facts.jj_readiness.blocker is None


def gather_jj_workspace_creation_facts(
    project: Project, jj: JjCli, jj_readiness: JjReadiness
) -> JjWorkspaceCreationFacts:
    """Read the facts for `project`'s repository now, taking jj's readiness as given.

    Checking colocation runs jj, so while jj is unavailable the repository reads as not colocated.
    """
    is_colocated = jj_readiness.blocker is None and is_jj_colocated(jj, project.get_local_user_path())
    return JjWorkspaceCreationFacts(
        use_jj_for_new_workspaces=project.use_jj_for_new_workspaces,
        is_colocated=is_colocated,
        jj_readiness=jj_readiness,
    )
